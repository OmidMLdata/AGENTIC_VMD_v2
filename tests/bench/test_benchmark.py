import csv
from conftest import DATA, no_real_vmd
import json
import os

import numpy as np
import pytest

from vmd_agent.bench import (
    models, run_benchmark, ground_truth,
    build_questions, build_context, parse_response,
    summarize, paired_difference, classify_fold,
)
from vmd_agent.bench import conditions as C, questions as Q, scorer as S
from vmd_agent.bench import rating_study


# -------------------------------------------------------------- ground truth
def test_ground_truth_values(ubq, lyz, hbb, whey):
    u, l, h, w = (ground_truth(p) for p in (ubq, lyz, hbb, whey))
    assert (u["fold_class"], u["n_protein_chains"], u["n_disulfides"]) == ("mixed", 1, 0)
    assert (l["fold_class"], l["n_disulfides"]) == ("alpha", 4)
    assert h["n_protein_chains"] == 4 and h["has_ligand"] and h["ligand_buried"]
    assert w["n_disulfides"] == 4 and w["has_ligand"]
    assert not u["has_lipid"] and not u["has_nucleic"]


def test_fold_classification_boundaries():
    assert classify_fold(40, 5) == "alpha"
    assert classify_fold(5, 40) == "beta"
    assert classify_fold(20, 20) == "mixed"
    assert classify_fold(10, 10) == "coil"
    assert classify_fold(35, 20) == "mixed"        # sheet >= 15 blocks 'alpha'


def test_ground_truth_error_on_bad_file():
    assert not ground_truth("/nonexistent.pdb")["ok"]


# ---------------------------------------------------------------- questions
def test_questions_carry_sources_and_answers(hbb):
    qs = {q["key"]: q for q in build_questions(ground_truth(hbb), "S0")}
    assert qs["n_chains"]["answer"] == 4
    assert set(qs["n_disulfides"]["sources"]) == {"stats"}      # not visible
    assert "image" in qs["fold_class"]["sources"]
    assert qs["ligand_buried"]["answer"] is True
    assert qs["fold_class"]["kind"] == "choice" and qs["fold_class"]["choices"]


def test_no_ligand_question_when_no_ligand(ubq):
    keys = {q["key"] for q in build_questions(ground_truth(ubq), "S0")}
    assert "ligand_buried" not in keys and "has_ligand" in keys


def test_prompt_demands_json_and_allows_abstention(ubq):
    q = build_questions(ground_truth(ubq), "S0")[0]
    p = Q.format_prompt(q)
    assert '"abstain"' in p and "abstain" in p.lower()


# --------------------------------------------------------------- conditions
def test_answerability_follows_sources():
    chains = {"sources": ["image", "stats"]}
    disulf = {"sources": ["stats"]}
    assert C.is_answerable(chains, "raw") and not C.is_answerable(disulf, "raw")
    assert C.is_answerable(disulf, "legend_stats")
    assert not C.is_answerable(chains, "blind")
    assert C.is_answerable(disulf, "text_only")
    assert not C.is_answerable(disulf, "misleading_legend")


def test_context_assembly():
    assets = {"raw": {"front": "f.png", "side": "s.png"},
              "annotated": {"front": "a.png"}, "legend": ["- **protein**"],
              "stats": ["10 atoms"], "colour_key": ["Structure: ..."],
              "other_legend": ["- other structure"]}
    assert build_context("blind", assets)["images"] == []
    assert build_context("raw", assets) == {"images": ["f.png"], "text": "",
                                            "available": True}
    assert build_context("multiview_legend_stats", assets)["images"] == [
        "f.png", "s.png"]
    assert build_context("annotated", assets)["images"] == ["a.png"]
    t = build_context("legend_stats", assets)["text"]
    assert "VISUAL LEGEND" in t and "STRUCTURE STATISTICS" in t and "**" not in t
    assert "other structure" in build_context("misleading_legend", assets)["text"]
    assert build_context("text_only", assets)["images"] == []
    assert not build_context("raw", {"raw": {}})["available"]


def test_misleading_legend_swaps_when_no_other():
    out = C.misleading_legend(["purple helix and yellow strand"])
    assert out == ["yellow strand and purple helix"] or "purple" not in out[0].split()[0]
    assert out != ["purple helix and yellow strand"]


# ------------------------------------------------------------------ scoring
def test_parse_response_variants():
    assert parse_response('{"answer": 4, "confidence": 0.8, "abstain": false}')["answer"] == 4
    assert parse_response('Sure! {"answer": true, "confidence": 0.5}')["answer"] is True
    assert parse_response('{"answer": null, "abstain": true}')["abstain"]
    assert parse_response("")["abstain"]
    assert parse_response("yes")["answer"] is True
    assert parse_response("about 42 percent")["answer"] == 42.0
    assert parse_response("I cannot tell")["abstain"]


def test_correctness_rules():
    num = {"kind": "numeric", "answer": 40.0, "tolerance": 10.0}
    assert S.is_correct(num, 48) and not S.is_correct(num, 55)
    b = {"kind": "boolean", "answer": True}
    assert S.is_correct(b, "yes") and S.is_correct(b, True) and not S.is_correct(b, False)
    ch = {"kind": "choice", "answer": "alpha",
          "choice_labels": {"alpha": "mostly alpha-helical"}}
    assert S.is_correct(ch, "Alpha") and S.is_correct(ch, "mostly alpha-helical")
    assert not S.is_correct(ch, "beta") and not S.is_correct(ch, None)


def test_scoring_flags():
    q = {"kind": "boolean", "answer": True}
    wrong = S.score_response(q, {"answer": False, "confidence": 0.9}, False)
    assert wrong["hallucination"] and wrong["unsupported_assertion"]
    abst = S.score_response(q, {"abstain": True}, False)
    assert abst["appropriate_abstention"] and not abst["hallucination"]
    assert S.score_response(q, {"abstain": True}, True)["over_abstention"]


def test_ece_perfect_and_overconfident():
    assert S.ece([1, 1, 0, 0], [True, True, False, False]) == pytest.approx(0)
    assert S.ece([0.9] * 10, [True] * 5 + [False] * 5) == pytest.approx(0.4)


def _recs(cond, n_struct, acc, rng):
    out = []
    for s in range(n_struct):
        for k in range(6):
            c = rng.random() < acc
            out.append(dict(condition=cond, structure=f"S{s}", key=f"q{k}",
                            answered=True, correct=c, hallucination=not c,
                            answerable=True, unsupported_assertion=False,
                            appropriate_abstention=False, over_abstention=False,
                            abstained=False, confidence=0.8))
    return out


def test_summary_ci_brackets_the_estimate_and_narrows_with_more_structures():
    rng = np.random.default_rng(0)
    small = summarize(_recs("a", 8, 0.7, rng), n_boot=300)["a"]
    large = summarize(_recs("a", 80, 0.7, rng), n_boot=300)["a"]
    for m in (small, large):
        lo, hi = m["ci95"]["accuracy"]
        assert lo <= m["accuracy"] <= hi
    width = lambda m: m["ci95"]["accuracy"][1] - m["ci95"]["accuracy"][0]
    assert width(large) < width(small)
    assert large["n_structures"] == 80


def test_bootstrap_ci_coverage_is_near_nominal():
    """Across many datasets the 95 % interval should contain the truth ~95 %."""
    rng = np.random.default_rng(11)
    hits = 0
    for _ in range(60):
        m = summarize(_recs("a", 25, 0.7, rng), n_boot=150, seed=1)["a"]
        lo, hi = m["ci95"]["accuracy"]
        hits += lo <= 0.7 <= hi
    assert hits / 60 > 0.8


def test_paired_difference_detects_real_gap():
    rng = np.random.default_rng(1)
    recs = _recs("good", 25, 0.9, rng) + _recs("bad", 25, 0.4, rng)
    d = paired_difference(recs, "good", "bad", "correct", n_boot=300)
    assert d["mean_difference"] > 0.3 and d["ci95"][0] > 0
    same = paired_difference(recs, "good", "good", "correct", n_boot=50)
    assert same["mean_difference"] == 0


def test_paired_difference_key_filter_and_alpha():
    recs = []
    for st in range(20):
        for key, pa, pb in (("easy", 1, 1), ("hard", 1, 0)):
            for cond, c in (("a", pa), ("b", pb)):
                recs.append({"structure": f"s{st}", "key": key,
                             "condition": cond, "correct": float(c)})
    both = paired_difference(recs, "a", "b", n_boot=200)
    hard = paired_difference(recs, "a", "b", n_boot=200, keys=["hard"])
    assert both["n_pairs"] == 40 and hard["n_pairs"] == 20
    assert both["mean_difference"] == 0.5 and hard["mean_difference"] == 1.0
    assert paired_difference(recs, "a", "b", keys=["nope"])["n_pairs"] == 0
    rng = np.random.default_rng(3)
    noisy = _recs("a", 25, 0.8, rng) + _recs("b", 25, 0.5, rng)
    wide = paired_difference(noisy, "a", "b", n_boot=400, alpha=0.01)["ci"]
    narrow = paired_difference(noisy, "a", "b", n_boot=400, alpha=0.2)["ci"]
    assert wide[0] <= narrow[0] and wide[1] >= narrow[1]


# ---------------------------------------------------------------- full runs
@pytest.fixture(scope="module")
def structures():
    here = DATA
    return [os.path.join(here, f) for f in ("1ubq.pdb", "1lyz.pdb", "4hhb.pdb",
                                            "1beb.pdb")]


def test_oracle_is_perfect_and_constant_is_not(structures, tmp_path):
    o = run_benchmark(structures, models.OracleModel(), str(tmp_path / "o"),
                      renderer="matplotlib", views=("front",), n_boot=20)
    assert all(m["accuracy"] == 1.0 for m in o["by_condition"].values())
    c = run_benchmark(structures, models.ConstantModel(), str(tmp_path / "c"),
                      renderer="matplotlib", views=("front",), n_boot=20)
    assert c["by_condition"]["raw"]["accuracy"] < 0.7


def test_stats_reader_shows_grounding_effect(structures, tmp_path):
    s = run_benchmark(structures, models.StatsReaderModel(),
                      str(tmp_path / "s"), renderer="matplotlib",
                      views=("front",), n_boot=100)
    bc = s["by_condition"]
    assert bc["raw"]["accuracy"] == 0 and bc["blind"]["accuracy"] == 0
    assert bc["legend_stats"]["accuracy"] > 0.85
    assert bc["legend_stats"]["accuracy"] > bc["legend"]["accuracy"] > 0
    assert bc["raw"]["appropriate_abstention_rate"] == 1.0   # abstains w/o evidence
    d = s["paired_contrasts"]["legend_stats - raw"]["accuracy"]
    assert d["mean_difference"] > 0.8 and d["ci95"][0] > 0.5
    assert bc["misleading_legend"]["accuracy"] < bc["legend"]["accuracy"]


def test_outputs_written(structures, tmp_path):
    out = tmp_path / "o"
    run_benchmark(structures[:2], models.StatsReaderModel(), str(out),
                  renderer="matplotlib", views=("front",), n_boot=20)
    for f in ("records.jsonl", "summary.json", "summary.md", "manifest.json"):
        assert (out / f).exists()
    rec = json.loads(open(out / "records.jsonl").readline())
    assert {"condition", "structure", "correct", "reply"} <= set(rec)
    man = json.load(open(out / "manifest.json"))
    assert man["structures"][0]["sha256"] and man["renderer"]["name"] == "matplotlib"
    assert "| condition |" in (out / "summary.md").read_text()


def test_models_never_see_the_answer(structures, tmp_path):
    seen = []

    def spy(prompt, images, text, question=None):
        seen.append(question)
        return json.dumps({"answer": None, "abstain": True})

    run_benchmark(structures[:1], spy, str(tmp_path), renderer="matplotlib",
                  views=("front",), n_boot=5, conditions=["raw"])
    assert seen and all("answer" not in q for q in seen)
    assert all(q["id"] for q in seen)


def test_structures_are_anonymised(structures, tmp_path):
    texts = []

    def spy(prompt, images, text, question=None):
        texts.append(prompt + (text or ""))
        return "{}"

    run_benchmark(structures[:1], spy, str(tmp_path), renderer="matplotlib",
                  views=("front",), n_boot=5)
    joined = " ".join(texts)
    assert "1ubq" not in joined.lower() and "ubiquitin" not in joined.lower()
    ann = list((tmp_path / "structures" / "S000").glob("annotated_*.png"))
    assert ann and "1ubq" not in ann[0].name


def test_model_errors_do_not_abort_the_run(structures, tmp_path):
    def boom(prompt, images, text):
        raise RuntimeError("api down")

    s = run_benchmark(structures[:1], boom, str(tmp_path), renderer="matplotlib",
                      views=("front",), n_boot=5, conditions=["raw"])
    assert s["by_condition"]["raw"]["accuracy"] == 0.0 and s["n_records"] > 0


def test_unknown_condition_rejected(structures, tmp_path):
    with pytest.raises(ValueError):
        run_benchmark(structures[:1], models.OracleModel(), str(tmp_path),
                      conditions=["nope"])


def test_unloadable_structure_is_skipped_and_reported(structures, tmp_path):
    s = run_benchmark(["/nonexistent.pdb", structures[0]], models.OracleModel(),
                      str(tmp_path), renderer="matplotlib", views=("front",),
                      n_boot=5)
    assert len(s["skipped_structures"]) == 1 and s["n_structures"] == 1


def test_image_conditions_skipped_without_a_renderer(structures, tmp_path):
    s = run_benchmark(structures[:2], models.OracleModel(), str(tmp_path),
                      renderer="matplotlib", render=False, n_boot=5)
    assert "raw" not in s["by_condition"] and s["skipped_cells"]
    assert "text_only" in s["by_condition"] and "blind" in s["by_condition"]


# ------------------------------------------------------- Anthropic adapter
def _adapter(tmp_path, model="some-model"):
    """The adapter with a real (never used) SDK client, to inspect its request."""
    anthropic = pytest.importorskip("anthropic")
    return models.AnthropicModel(model, client=anthropic.Anthropic(
        api_key="unused-in-this-test"))


def test_anthropic_request_is_multimodal_and_forbids_recognition(tmp_path):
    from PIL import Image
    img = tmp_path / "a.png"
    Image.new("RGB", (4, 4)).save(img)
    kw = _adapter(tmp_path).build_request("Is it?", [str(img)], "LEGEND text")
    assert kw["model"] == "some-model" and kw["temperature"] == 0.0
    assert "memory" in kw["system"].lower()                  # no recognition by memory
    content = kw["messages"][0]["content"]
    assert content[0]["type"] == "image" and content[0]["source"]["data"]
    assert "LEGEND text" in content[-1]["text"] and "Is it?" in content[-1]["text"]


def test_anthropic_adapter_requires_explicit_model(tmp_path):
    with pytest.raises(ValueError):
        models.AnthropicModel("", client=object())


@pytest.mark.requires_api
def test_a_real_model_answers_a_question_about_a_real_image(tmp_path):
    """Live: one tiny call. A solid red square; the model must say it is red."""
    from PIL import Image
    from vmd_agent.bench.questions import format_prompt
    img = tmp_path / "red.png"
    Image.new("RGB", (64, 64), (255, 0, 0)).save(img)
    q = {"id": "t:red", "key": "red", "kind": "boolean",
         "text": "Is the image a solid red square?"}
    model = models.AnthropicModel(os.environ.get("VMD_AGENT_LIVE_MODEL",
                                                 "claude-haiku-4-5-20251001"))
    parsed = parse_response(model(format_prompt(q), [str(img)], ""))
    assert parsed["parsed"] and parsed["answer"] is True


# ----------------------------------------------------------- rating study
def test_rating_sheet_is_blinded_and_analysable(tmp_path):
    from PIL import Image
    imgs = {}
    for s in range(6):
        imgs[f"S{s}"] = {}
        for p in ("auto", "lines"):
            f = tmp_path / f"{s}_{p}.png"
            Image.new("RGB", (4, 4), (s * 10, 0, 0)).save(f)
            imgs[f"S{s}"][p] = str(f)
    out = rating_study.make_sheet_from_images(imgs, str(tmp_path / "sheet"),
                                              seed=1)
    assert out["n_images"] == 12
    names = os.listdir(tmp_path / "sheet" / "images")
    assert all("auto" not in n and "lines" not in n for n in names)
    key = json.load(open(out["key"]))
    rng = np.random.default_rng(0)
    rows = list(csv.DictReader(open(out["sheet"])))
    for r in rows:
        auto = key[r["blind_id"]]["policy"] == "auto"
        for c in rating_study.CRITERIA:
            r[c] = str(int(np.clip(rng.normal(4.5 if auto else 2.0, 0.4), 1, 5)))
    with open(out["sheet"], "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    res = rating_study.summarize_ratings(out["sheet"], out["key"], n_boot=100)
    leg = res["legibility"]
    assert leg["per_policy"]["auto"]["mean"] > leg["per_policy"]["lines"]["mean"] + 1
    assert leg["vs_auto"]["lines"]["mean_diff_auto_minus_other"] > 1
    assert leg["vs_auto"]["lines"]["wilcoxon_p"] < 0.05


@no_real_vmd
def test_rating_sheet_needs_vmd_for_representation_policies(ubq, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "")
    r = rating_study.make_rating_sheet([ubq], str(tmp_path))
    assert not r["ok"] and "VMD" in r["error"]


# ------------------------------------------------------------ audit fixes
def test_parser_survives_trailing_prose_and_braces():
    """'{json} (note: {x})' used to fail the greedy match and be scored as 0.9."""
    p = parse_response('{"answer": true, "confidence": 0.9} (note: {unused})')
    assert p["answer"] is True and p["confidence"] == 0.9
    p = parse_response('Sure {not json} then {"answer": 4, "confidence": 0.7, '
                       '"abstain": false} done')
    assert p["answer"] == 4 and p["confidence"] == 0.7
    p = parse_response('{"confidence": 0.5}{"answer": 7}')
    assert p["answer"] == 7


def test_boolean_is_not_a_numeric_answer():
    from vmd_agent.bench import scorer as S
    q = {"kind": "numeric", "answer": 1, "tolerance": 0}
    assert not S.is_correct(q, True) and S.is_correct(q, 1)


def test_paired_difference_averages_repeats_instead_of_keeping_the_last():
    from vmd_agent.bench import paired_difference
    recs = []
    for rep, a in enumerate([1, 0, 1, 1]):                 # A right 3 of 4
        recs.append(dict(condition="A", structure="S", key="q", repeat=rep,
                         correct=a))
        recs.append(dict(condition="B", structure="S", key="q", repeat=rep,
                         correct=0))
    d = paired_difference(recs, "A", "B", "correct", n_boot=20)
    assert d["mean_difference"] == pytest.approx(0.75) and d["n_pairs"] == 1


def test_ece_penalises_underconfidence_too():
    from vmd_agent.bench import scorer as S
    assert S.ece([0.5] * 10, [True] * 9 + [False]) == pytest.approx(0.4)
    assert S.ece([0.9] * 10, [True] * 5 + [False] * 5) == pytest.approx(0.4)
