# Replication package: model-written integrations of an acquired organisation's data into an existing pipeline

This repository holds the run records, result tables and analysis code of the study. Every table and every number in the paper can be recomputed from the stored records with one command and compared byte for byte with the files here.

## Reproduce

Requires Python 3.9 or later. Only the standard library is used.

    python3 reproduce.py

The script makes three checks and prints one line for each:

1. **Result tables.** It runs `paper/analysis.py` on `runs/full/final.jsonl` and `runs/prepare/` in a scratch folder. It then compares every file it writes with `results/`.
2. **Numbers in the text.** It runs `analysis/analyse.py` on `runs/` and compares the output with `analysis/numbers.json`.
3. **Population archive.** It checks the sha256 of `runs/prepare/population.tar.gz` against the value recorded in `runs/prepare/population.json`.

The last line reads `REPRODUCE OK` when all files match; the exit code is then 0.

To redraw the two figures, run `python3 analysis/make_figures.py`. This step needs matplotlib, and the figures are written to `figures/`.

`SHA256SUMS` lists the sha256 of every file in the repository. On macOS, check it with `shasum -a 256 -c SHA256SUMS`; on Linux, with `sha256sum -c SHA256SUMS`.

## Layout

| Path | Content |
|---|---|
| `paper/` | Study code. `spec.py` defines the formats, domains, tasks, arms and hypotheses. `worlds.py`, `dialects.py` and `products.py` build the acquirer and acquired worlds, the three CSV dialects and the four wide data products. `prompts.py` and `hints.py` hold the prompts and the mapping hint sheets. `gen.py` holds the generation and repair turns. `score.py` holds the cell-level scoring. `study.py` holds the evaluation of one candidate. `analysis.py` writes the result tables. |
| `paper/refsql/` | Reference integrations written by the authors, one per format and domain. |
| `paper/manifest/engine-requirements.txt` | Pinned wheels of the SQL engine (dbt-core, dbt-duckdb, DuckDB), each with its sha256. |
| `config/` | Models and their settings (`models.yaml`), prices used for cost accounting (`prices.yaml`), stage plan (`plan.yaml`), and pinned third-party sources with their commits and licences (`data_pins.json`). |
| `rh/` | Shared file helpers used by the study code (paths, JSON lines). |
| `runs/prepare/` | Prepared inputs: the archived synthetic population (`population.tar.gz`, with its checksum in `population.json`), the patient split, the reference check, the per-task prompt context and the reference solutions. |
| `runs/full/` | Run records: `gen.jsonl` (first calls), `rep1.jsonl` and `rep2.jsonl` (repair turns), `eval0.jsonl` to `eval2.jsonl` (evaluation after each turn) and `final.jsonl` (final outcome of every integration). Generation and repair records hold the model reply and the extracted SQL; evaluation records hold the SQL, the scores and the feedback shown to the model. |
| `runs/ledger.jsonl` | One line per model call: model, stage, token counts and cost. |
| `runs/pins.lock.json` | Commits of the pipeline and its packages as resolved at run time. |
| `logs/api_*.jsonl` | Every model exchange, one file per model: the prompt as sent, the reply, token counts, latency and response headers. The files also hold the calls of the pilot and canary stages and of one tooling check that ran before the main run. |
| `results/` | Result tables written by `paper/analysis.py` (see below), and a copy of `runs/prepare/` without the archive. |
| `analysis/` | `analyse.py` recomputes every number quoted in the text into `numbers.json`. `make_figures.py` draws the figures from `numbers.json`. `per_task.py` prints the per-task counts of the appendix table from `results/cells.csv`. |
| `reproduce.py` | The check described above. |

## Files behind the paper's tables and figures

| In the paper | File |
|---|---|
| Exact staging integrations by source format and arm; figure of exact shares | `results/t1_correctness.csv`; `analysis/numbers.json` (`format_arm`) |
| Staging integrations by model and arm (built, passing, exact, silent wrong) | `results/t2_silent_wrong.csv`, `results/t5_arms.csv` |
| Outcome of the staging integrations of each arm (figure) | `analysis/numbers.json` (`arm_stg`) |
| Paired comparisons (McNemar, Holm) | `results/t6_comparisons.csv`; recomputed in `analysis/numbers.json` (`pairs`) |
| Existing rows: content and key stability, rebuild controls | `results/t3_non_regression.csv` |
| Wide data products | `results/t4_wide_contract.csv` |
| Hypotheses and outcomes | `results/hypotheses.csv` |
| Per-task counts (appendix) | `results/cells.csv`, printed by `analysis/per_task.py` |
| Cell-level outcome of every integration | `results/cells.csv` |

`results/t6_comparisons.csv` labels the two sides of each pair in reverse order. The paper recomputes every pair from the cell-level records (`analysis/analyse.py`).

## Data and licences

- The patients are synthetic. They were generated by Synthea 3.0.0 (Apache-2.0) with a fixed seed. The generator simulates each patient up to the wall-clock time of the run, so the same seed produces a slightly different population on another day. For this reason the population of the run is archived in `runs/prepare/population.tar.gz`.
- The existing pipeline is OHDSI dbt-synthea (Apache-2.0), used unmodified at the commit in `config/data_pins.json` and `runs/pins.lock.json`. Its packages, dbt-utils and dbt-expectations, are pinned in the same files. These projects are not copied into this repository.
- Model replies are released unedited.

## Not included

- The orchestration layer that scheduled the model calls and the compute. It does not affect any reply, score or table.
- API keys.

Without these, the model calls cannot be repeated from this repository. Every analysis can be repeated from the stored records.

## Line endings

The result tables are CSV files with CRLF line endings, which is what Python's `csv` module writes. `.gitattributes` turns off line-ending conversion for every file, so a clone holds the same bytes as the original files on any platform.
