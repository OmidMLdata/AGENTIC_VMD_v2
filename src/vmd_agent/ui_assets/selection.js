"use strict";
/* A VMD-style atom selection language, evaluated in the page on the atoms the server sent.
 *
 *   protein, nucleic, water, backbone, sidechain, hydrogen, noh, all, none
 *   name CA CB   resname ALA GLY   chain A   element C N   resid 1 to 20 25   index 0 to 99
 *   within 5 of (resname LIG)       same residue as (within 4 of resname LIG)
 *   not X,  X and Y,  X or Y,  ( X )
 *
 * Names and values are case-insensitive and may use * as a wildcard (name C*). This is a subset of VMD's language, with its spelling, so a selection that
 * works here reads the same in VMD. `compile(text, mol, xyz)` returns a Uint8Array with 1 for each selected atom, or throws a SyntaxError that says what is wrong.
 * No dependencies: it runs in the browser and under node (the tests).
 */
(function (root) {
  const WORDS = new Set(["and", "or", "not", "all", "none", "protein", "nucleic", "water", "backbone", "sidechain", "hydrogen", "noh", "name", "resname", "chain", "element",
                         "resid", "index", "within", "of", "same", "residue", "as", "to"]);
  const FIELDS = new Set(["name", "resname", "chain", "element", "resid", "index"]);

  function tokenize(text) {
    const out = []; const re = /\s*(\(|\)|"[^"]*"|'[^']*'|[^\s()]+)/g; let m;
    while ((m = re.exec(text)) !== null) { let t = m[1]; if (/^["']/.test(t)) t = t.slice(1, -1); out.push({ text: t, quoted: /^["']/.test(m[1]) }); }
    return out;
  }
  const glob = pat => new RegExp("^" + pat.replace(/[.+^${}|[\]\\]/g, "\\$&").replace(/\*/g, ".*").replace(/\?/g, ".") + "$", "i");

  function compile(text, mol, xyz) {
    const n = mol.n_atoms, toks = tokenize(String(text || "").trim()); let pos = 0;
    if (!toks.length) throw new SyntaxError("the selection is empty (try: all, protein, name CA, resname LIG)");
    const peek = () => (pos < toks.length ? toks[pos] : null), word = () => { const t = peek(); return t && !t.quoted ? t.text.toLowerCase() : null; };
    const take = () => toks[pos++];
    const fresh = () => new Uint8Array(n);
    const nameOf = i => mol.names[mol.name[i]], resnameOf = i => mol.resnames[mol.resname[i]], chainOf = i => mol.chains[mol.chain[i]], elOf = i => mol.elements[mol.element[i]];
    const isH = i => elOf(i).toUpperCase() === "H" || /^H/i.test(nameOf(i)) && elOf(i).length <= 1;
    const BB = new Set(["N", "CA", "C", "O"]);
    const by = f => { const m = fresh(); for (let i = 0; i < n; i++) if (f(i)) m[i] = 1; return m; };

    function parseOr() { let a = parseAnd(); while (word() === "or") { take(); const b = parseAnd(); for (let i = 0; i < n; i++) a[i] = a[i] | b[i]; } return a; }
    function parseAnd() { let a = parseNot(); while (word() === "and") { take(); const b = parseNot(); for (let i = 0; i < n; i++) a[i] = a[i] & b[i]; } return a; }
    function parseNot() { if (word() === "not") { take(); const a = parseNot(); for (let i = 0; i < n; i++) a[i] = a[i] ? 0 : 1; return a; } return parseAtom(); }

    function values(field) {                                // the words after a field keyword, up to the word that ends the list
      const vals = [];
      while (peek()) {
        const t = peek(), w = t.quoted ? null : t.text.toLowerCase();
        if (!t.quoted && (t.text === ")" || t.text === "(" || w === "and" || w === "or" || w === "not" || FIELDS.has(w))) break;
        vals.push(take().text);
      }
      if (!vals.length) throw new SyntaxError(`"${field}" needs at least one value (for example: ${field} ${field === "resid" ? "1 to 20" : "CA"})`);
      return vals;
    }
    function numeric(field, vals) {
      const ranges = [];
      for (let k = 0; k < vals.length; k++) {
        const a = Number(vals[k]); if (!Number.isFinite(a)) throw new SyntaxError(`"${vals[k]}" is not a number (in ${field})`);
        if (String(vals[k + 1]).toLowerCase() === "to") { const b = Number(vals[k + 2]); if (!Number.isFinite(b)) throw new SyntaxError(`"to" needs a number after it (in ${field})`); ranges.push([a, b]); k += 2; } else ranges.push([a, a]);
      }
      return v => ranges.some(([a, b]) => v >= Math.min(a, b) && v <= Math.max(a, b));
    }
    function within(r, sel) {                               // atoms closer than r angstrom to any atom of sel (a grid of cells of size r)
      const m = fresh(), cell = Math.max(r, 0.5), grid = new Map(), key = (x, y, z) => x + "," + y + "," + z;
      for (let i = 0; i < n; i++) if (sel[i]) { const k = key(Math.floor(xyz[3 * i] / cell), Math.floor(xyz[3 * i + 1] / cell), Math.floor(xyz[3 * i + 2] / cell)); (grid.get(k) || grid.set(k, []).get(k)).push(i); }
      const r2 = r * r;
      for (let i = 0; i < n; i++) {
        const cx = Math.floor(xyz[3 * i] / cell), cy = Math.floor(xyz[3 * i + 1] / cell), cz = Math.floor(xyz[3 * i + 2] / cell);
        outer: for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) for (let dz = -1; dz <= 1; dz++) {
          const cellAtoms = grid.get(key(cx + dx, cy + dy, cz + dz)); if (!cellAtoms) continue;
          for (const j of cellAtoms) { const ax = xyz[3 * i] - xyz[3 * j], ay = xyz[3 * i + 1] - xyz[3 * j + 1], az = xyz[3 * i + 2] - xyz[3 * j + 2]; if (ax * ax + ay * ay + az * az <= r2) { m[i] = 1; break outer; } }
        }
      }
      return m;
    }
    function parseAtom() {
      const t = peek(); if (!t) throw new SyntaxError("the selection ends too early (a word like protein or name CA is missing)");
      if (t.text === "(" && !t.quoted) { take(); const a = parseOr(); if (!peek() || peek().text !== ")") throw new SyntaxError("a closing ) is missing"); take(); return a; }
      const w = word(); if (w === null) throw new SyntaxError(`unexpected "${t.text}"`);
      take();
      switch (w) {
        case "all": return by(() => true);
        case "none": return fresh();
        case "protein": return by(i => !!mol.is_protein[i]);
        case "nucleic": return by(i => !!mol.is_nucleic[i]);
        case "water": return by(i => !!mol.is_water[i]);
        case "backbone": return by(i => !!mol.is_protein[i] && BB.has(nameOf(i).toUpperCase()));
        case "sidechain": return by(i => !!mol.is_protein[i] && !BB.has(nameOf(i).toUpperCase()) && !isH(i));
        case "hydrogen": return by(isH);
        case "noh": return by(i => !isH(i));
        case "within": {
          const r = Number(peek() ? take().text : NaN); if (!Number.isFinite(r) || r <= 0) throw new SyntaxError('"within" needs a distance, as in: within 5 of resname LIG');
          if (word() !== "of") throw new SyntaxError('"within 5" must be followed by "of"'); take();
          return within(r, parseNot());
        }
        case "same": {
          if (word() !== "residue") throw new SyntaxError('only "same residue as" is supported'); take(); if (word() !== "as") throw new SyntaxError('"same residue" must be followed by "as"'); take();
          const s = parseNot(), keys = new Set(); for (let i = 0; i < n; i++) if (s[i]) keys.add(mol.chain[i] + ":" + mol.resid[i] + ":" + mol.resname[i]);
          return by(i => keys.has(mol.chain[i] + ":" + mol.resid[i] + ":" + mol.resname[i]));
        }
        case "name": case "resname": case "chain": case "element": {
          const vals = values(w).map(glob), get = { name: nameOf, resname: resnameOf, chain: chainOf, element: elOf }[w];
          return by(i => vals.some(rx => rx.test(get(i))));
        }
        case "resid": case "index": {
          const ok = numeric(w, values(w)), get = w === "resid" ? (i => mol.resid[i]) : (i => i);
          return by(i => ok(get(i)));
        }
        default: throw new SyntaxError(`unexpected "${t.text}" (selections use words like protein, water, name CA, resid 1 to 20, within 5 of ...)`);
      }
    }
    const mask = parseOr();
    if (pos < toks.length) throw new SyntaxError(`unexpected "${toks[pos].text}" after the selection`);
    return mask;
  }

  const api = { compile, tokenize };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.VASelection = api;
})(typeof window !== "undefined" ? window : globalThis);
