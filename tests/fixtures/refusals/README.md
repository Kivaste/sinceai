# Refusal fixtures (ticket 04)

Hand-made synthetic releases; no values come from the challenge kit. `contract.json` is shared by every case.
Each `<case>/release/` is a candidate release folder; `<case>/expected.json` names the checks that must fail,
with the expected file, column, count and row locations of each high-severity violation.

The row-map *file* case is planted at test time (`test_row_map_file_in_release_is_refused`), because
`rowmap_*.csv` is gitignored and must never be committed.
