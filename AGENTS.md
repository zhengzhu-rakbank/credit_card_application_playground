# A Card scorecard project

This Git folder implements the thin-file credit card application scorecard (A Card).

- The specification is the `acard-scorecard` skill (`.assistant/skills/acard-scorecard/`). Read its `SKILL.md` and the relevant sections of `references/spec.md` before writing or changing any code here.
- Implement one module (E1–E20, spec Appendix E) per request, in order, and check the module's acceptance criteria before moving on.
- All thresholds and parameters come from `config/config.yaml`. Never hard-code them.
- Never read OOT labels (applications 2025-01-01 to 2025-06-30) before the model lock (spec 3.2 and 7.7).
- `target` is precomputed in the source table (1, 0, −1, −2); never recompute it. Label-based work must filter `sample_status in ("GOOD", "BAD")`.
- Column roles come from `config.column_roles` and the rules in spec 2.5; stop if any column is UNASSIGNED. Nationality, gender and other sensitive variables are watch variables only, never model features; age is a permitted model feature.
- Population filters: derive FILE_TYPE (Appendix G) and keep THIN File only; then apply exactly the rules in `config.population_filters`, in order, after upper-casing values. CLASSCODE removes only STAFF and SME. Application-time rules → EXCLUDED (out of training and PSI); GENERALSTAT and ACTIVE_REPORTING rules → EXCLUDED_PERF (out of training, kept in PSI).
- If the specification does not cover a situation, write the question to `reports/open_questions.md` and stop. Do not guess.

## Engineering conventions for every module (E3–E20)

- Locations: catalog and schema come from config.databricks; every file artefact goes under config artifacts_root
  (sub-folders: folds/, binning/, models/, params/, feature_lists/, calibration/, reports/, reports/run_summaries/;
  plus model_registry.json and oof_predictions.parquet at the root). Master table: <catalog>.<schema>.acard_master.
  Feature log: <catalog>.<schema>.acard_feature_log, exported to reports/feature_log.csv after every funnel module.
- Notebook layout: cell 1 `%pip install -r requirements.lock` then `dbutils.library.restartPython()`;
  cell 2 adds src/ to sys.path, imports common, loads config, sets the seed; the LAST cell is an acceptance cell of
  `assert` statements (clear messages) for the module's acceptance criteria, followed by writing
  reports/run_summaries/<notebook>.json (run time, git commit, config hash, row counts, key metrics, pass/fail).
- Every report workbook has a first sheet "meta": module, run time, git commit, config sha256.
- Idempotent: re-running a module overwrites its own outputs and its own feature-log columns. Never append duplicate
  rows, never delete feature-log rows. A feature dropped at a layer keeps its row; later layers skip it.
- Data access only through common.load_window(); never filter OOT by hand. E3–E12 never load OOT labels into pandas
  (aggregate SQL counts for reconciliation are allowed).
- Labels: label-based work uses sample_status in config.labelled_statuses; y = (sample_status == "BAD").
- Funnel thresholds are frozen at E4: E4 stores sha256 of config.funnel; E5–E9 recompute it and stop if it changed,
  unless config/threshold_changes.csv has a row (parameter, old, new, reason, date) explaining the change.
- Randomness: config.random_seed passed explicitly everywhere; Optuna TPESampler(seed); LightGBM deterministic=True
  and num_threads = config.runtime.lgb_num_threads.
- Shared logic (special-value handling, WoE transform, scoring, calibration, score mapping, reason codes) lives in
  src/common.py or src/acard_scoring.py and is reused by later modules and the API. Never copy-paste it.
- MLflow: one run per module in config.databricks.mlflow_experiment (params, metrics, config hash, git commit, reports).
- Human-maintained files are read-only for you: config/*.yaml, feature_dict.csv (after E2a), l1_review.csv,
  psi_decisions.csv, policy_changes.csv, signoff.yaml, reason_code_map.csv, threshold_changes.csv.
- Anything not covered by the spec or these instructions: append the question to reports/open_questions.md and stop.