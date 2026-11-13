# Model benchmark

Each cell is the share of tasks passed. Intervals are 95% (Wilson) and are wide when a category has few tasks: read them as 'at least this good / at most this good', not as a ranking of close models.

## Overall

| Model | Tasks | Success | 95% interval | Right tool | Numbers grounded | Mean wall s | Model s | Tool s | Model calls | Tokens in / out |
|---|---|---|---|---|---|---|---|---|---|---|
| `claude-opus-5-5 (auto)` | 210 | 97% | 94% to 99% | 97% | 87% | 11.2 | 10.7 | 0.5 | 2.9 | 5507909 / 196459 |
| `gemma4:e4b (auto)` | 210 | 82% | 77% to 87% | 91% | 99% | 30.5 | 30.0 | 0.5 | 2.2 | 2688311 / 124651 |
| `granite4.1:8b (auto)` | 210 | 48% | 41% to 55% | 61% | 98% | 69.8 | 69.2 | 0.6 | 2.5 | 1340589 / 96444 |

## By category

| Category | `claude-opus-5-5 (auto)` | `gemma4:e4b (auto)` | `granite4.1:8b (auto)` |
|---|---|---|---|
| inspect | 100% (n=18) | 83% (n=18) | 33% (n=18) |
| claims | 100% (n=6) | 100% (n=6) | 50% (n=6) |
| trajectory | 100% (n=15) | 93% (n=15) | 67% (n=15) |
| measure_with_vmd | 100% (n=21) | 86% (n=21) | 38% (n=21) |
| files | 100% (n=6) | 50% (n=6) | 100% (n=6) |
| build | 100% (n=18) | 100% (n=18) | 83% (n=18) |
| maps | 100% (n=12) | 100% (n=12) | 50% (n=12) |
| render | 78% (n=27) | 67% (n=27) | 11% (n=27) |
| window | 100% (n=24) | 75% (n=24) | 25% (n=24) |
| video | 100% (n=9) | 67% (n=9) | 78% (n=9) |
| workflows | 100% (n=12) | 100% (n=12) | 75% (n=12) |
| hand_off | 100% (n=3) | 100% (n=3) | 0% (n=3) |
| records | 100% (n=6) | 0% (n=6) | 50% (n=6) |
| network | 100% (n=6) | 50% (n=6) | 100% (n=6) |
| decline | 100% (n=27) | 100% (n=27) | 48% (n=27) |

## By task

| Task | Category | `claude-opus-5-5 (auto)` | `gemma4:e4b (auto)` | `granite4.1:8b (auto)` |
|---|---|---|---|---|
| inspect_files | inspect | 3/3 | 3/3 | 3/3 |
| inspect_system | inspect | 3/3 | 3/3 | 0/3 |
| environment | inspect | 3/3 | 3/3 | 3/3 |
| stats | inspect | 3/3 | 3/3 | 0/3 |
| colours | inspect | 3/3 | 0/3 | 0/3 |
| representations | inspect | 3/3 | 3/3 | 0/3 |
| claims_mixed | claims | 3/3 | 3/3 | 3/3 |
| claims_water | claims | 3/3 | 3/3 | 0/3 |
| rg | trajectory | 3/3 | 3/3 | 3/3 |
| rmsd_settled | trajectory | 3/3 | 3/3 | 0/3 |
| keyframes | trajectory | 3/3 | 3/3 | 2/3 |
| drift | trajectory | 3/3 | 2/3 | 2/3 |
| rmsf | trajectory | 3/3 | 3/3 | 3/3 |
| contacts | measure_with_vmd | 3/3 | 3/3 | 0/3 |
| secondary | measure_with_vmd | 3/3 | 3/3 | 1/3 |
| pbc | measure_with_vmd | 3/3 | 0/3 | 0/3 |
| torsions | measure_with_vmd | 3/3 | 3/3 | 1/3 |
| structure_check | measure_with_vmd | 3/3 | 3/3 | 3/3 |
| align | measure_with_vmd | 3/3 | 3/3 | 0/3 |
| capabilities | measure_with_vmd | 3/3 | 3/3 | 3/3 |
| convert | files | 3/3 | 3/3 | 3/3 |
| write_frame | files | 3/3 | 0/3 | 3/3 |
| build_solvated | build | 3/3 | 3/3 | 3/3 |
| mutate | build | 3/3 | 3/3 | 3/3 |
| merge | build | 3/3 | 3/3 | 3/3 |
| membrane | build | 3/3 | 3/3 | 3/3 |
| nanotube | build | 3/3 | 3/3 | 3/3 |
| namd_input | build | 3/3 | 3/3 | 0/3 |
| volume_info | maps | 3/3 | 3/3 | 3/3 |
| map_scale | maps | 3/3 | 3/3 | 0/3 |
| fit_map | maps | 3/3 | 3/3 | 3/3 |
| density | maps | 3/3 | 3/3 | 0/3 |
| render | render | 3/3 | 3/3 | 3/3 |
| scene | render | 3/3 | 3/3 | 0/3 |
| turntable | render | 0/3 | 0/3 | 0/3 |
| export_scene | render | 0/3 | 0/3 | 0/3 |
| recipe | render | 3/3 | 1/3 | 0/3 |
| figure_labels | render | 3/3 | 3/3 | 0/3 |
| look_at_image | render | 3/3 | 3/3 | 0/3 |
| movie | render | 3/3 | 3/3 | 0/3 |
| draw_matplotlib | render | 3/3 | 2/3 | 0/3 |
| window_load | window | 3/3 | 3/3 | 0/3 |
| window_cartoon | window | 3/3 | 2/3 | 0/3 |
| window_ligand_atoms | window | 3/3 | 0/3 | 0/3 |
| window_frame | window | 3/3 | 3/3 | 0/3 |
| window_background | window | 3/3 | 3/3 | 0/3 |
| window_picture | window | 3/3 | 3/3 | 3/3 |
| window_figure | window | 3/3 | 1/3 | 3/3 |
| window_spin | window | 3/3 | 3/3 | 0/3 |
| probe_video | video | 3/3 | 0/3 | 1/3 |
| validate_video | video | 3/3 | 3/3 | 3/3 |
| stills | video | 3/3 | 3/3 | 3/3 |
| settled | workflows | 3/3 | 3/3 | 3/3 |
| overview | workflows | 3/3 | 3/3 | 3/3 |
| which_workflows | workflows | 3/3 | 3/3 | 0/3 |
| prepare | workflows | 3/3 | 3/3 | 3/3 |
| slurm | hand_off | 3/3 | 3/3 | 0/3 |
| provenance | records | 3/3 | 0/3 | 3/3 |
| report | records | 3/3 | 0/3 | 0/3 |
| search | network | 3/3 | 3/3 | 3/3 |
| fetch | network | 3/3 | 0/3 | 3/3 |
| missing_file | decline | 3/3 | 3/3 | 1/3 |
| outside_sandbox | decline | 3/3 | 3/3 | 0/3 |
| tcl_disabled | decline | 3/3 | 3/3 | 0/3 |
| no_such_measure | decline | 3/3 | 3/3 | 0/3 |
| window_outside | decline | 3/3 | 3/3 | 3/3 |
| window_mouse_pick | decline | 3/3 | 3/3 | 3/3 |
| window_tk_plugin | decline | 3/3 | 3/3 | 3/3 |
| namd_run | decline | 3/3 | 3/3 | 3/3 |
| wrong_pair | decline | 3/3 | 3/3 | 0/3 |

Success needs the right tool called without error (not for tasks that must be declined) and an answer and files that the program's checks accept. 'Numbers grounded' is the share of runs in which every number in the answer appears in a tool result. Times are wall-clock on your computer and include the model server's own work.
