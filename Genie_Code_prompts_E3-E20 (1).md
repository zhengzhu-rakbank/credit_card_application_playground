# A Card：Genie Code 模块指令 E3–E20

适用于规格书 v1.0.5（`acard-scorecard` skill）以及你项目里实际使用的 `config/config.yaml`。

## 怎么用

1. **先做第 0 步（只做一次）**：把下面的工程约定追加到项目根目录的 `AGENTS.md`，再把补充配置加到 `config/config.yaml`。之后每个模块的指令都依赖这两处，所以单条指令可以写得短一些，Genie Code 每次也会自动读到这些约定。
2. **一个模块开一个新的 Genie Code 对话**（Agent 模式）。把对应的英文指令整段复制进去。
3. Genie 写好 notebook 之后，**由你自己点 Run all**。每个 notebook 的最后一个 cell 都是验收检查（`assert`），全部通过才进入下一个模块。
4. 运行报错时，把报错信息贴回**同一个对话**，让 Genie 修。
5. 遇到“人工检查点”（见文末）时先停下，把对应的文件填好再继续。

指令用英文写，和规格书的术语保持一致，避免 Genie 理解偏差。

---

## 0. 一次性准备

### 0.1 追加到 `AGENTS.md`（放在现有内容后面）

```markdown
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
```

### 0.2 追加到 `config/config.yaml`

```yaml
runtime:
  lgb_num_threads: 4

review_files:                       # filled by people, read by code
  l1_review: config/l1_review.csv           # E5: feature, review_type(LEAK|DIRECTION), decision(KEEP|DROP), reason, reviewer, date
  psi_decisions: config/psi_decisions.csv   # E7: feature, cause_type, evidence, policy_change_date, decision, reviewer, date
  signoff: config/signoff.yaml              # E12/E13/E16 sign-offs
  reason_code_map: config/reason_code_map.csv  # E13/E18: feature, reason_group, text_en, text_ar
  threshold_changes: config/threshold_changes.csv

strategy:
  proposed_cutoff: null             # score; null = E13 skips approval rate at cut-off and reports by score decile

early_delinquency:                  # Chapter 11 / 14 (report only); actual source column names, null if not available
  fpd_column: null
  dpd30_3m_column: null
  min_mob: 3

reject_inference:
  data: none                        # none | features_only | bureau_outcome (TBC-07)

registry:
  version: "1.0.0"
  register_in_uc: false             # true = register A/B/C in Unity Catalog with alias "locked"

monitoring:                         # Chapter 14 defaults
  score_log_table: null             # production log table; null = simulate on FWD/STRESS
  score_psi: {amber: 0.10, red: 0.25}
  feature_csi: {amber: 0.10, red: 0.25}
  data_failure_increase: {amber: 0.50, red: 1.00}
  watch_approval_gap_pp: {amber: 5, red: 10}
  approval_rate_pp: {amber: 3, red: 5}
  early_delinq_ae_top_quintile: {amber: 1.3, red: 1.5}
  gini_drop: {amber: 0.05, red: 0.10}
  calibration_ratio: {amber: [0.8, 1.25], red: [0.67, 1.5]}
```

### 0.3 新建 `config/signoff.yaml`（先留空，后面再填）

```yaml
decision_rules_signed_by: ""      # E12 before lock
signed_date: ""
model_owner: ""
r4_reason_codes_approved: false   # Compliance approved reason_code_map.csv and method (before E13)
r4_approved_by: ""
central_tendency_target: null     # TBC-11 long-run bad rate; null = use actual 2024-07..2025-06 rate (E16)
central_tendency_approved_by: ""
```
---

### E1

```text
@acard-scorecard Implement module E1 (src/common.py) and its unit tests. Read SKILL.md and the spec sections listed for E1 first.
```

---

### E2a 特征字典和列角色

```text
@acard-scorecard Implement module E2 part A in /Users/<you>/acard_project, as notebook src/s01a_feature_dict.

Read SKILL.md, then spec Sections 2.4 and 2.5 before coding. Use src/common.py for config loading.

Task:
1. Read the table in config.data.raw_snapshot_table. Do not read any other table or view.
2. Classify every column by the rules in spec 2.5, using config.column_roles and the columns used in config.population_filters (those are role FLAG, including the file-type column in config.file_type.source_column).
3. Write config/feature_dict.csv with the fields in spec 2.4. Pre-fill dtype from the schema; propose special_codes from values such as -999 / -998 / -1 that occur in at least 0.5% of rows; set expected_direction = "?"; set compliance_ok = Y for FEATURE columns.
4. Print the count of columns per role, and list every column with role WATCH, FLAG, KEY, PERFORMANCE and UNASSIGNED.
5. If any column is UNASSIGNED, stop and list them. Do not guess a role.

Do not read target values or compute any label-based statistic in this part.
```

---

### E2b 样本状态、过滤和对数

```text
@acard-scorecard Implement module E2 part B in /Users/<you>/acard_project, as notebook src/s01b_data_prep.

Read SKILL.md, then spec Sections 1.2, 2.1, 2.2, 2.3, Chapter 4 and Appendix D.8 before coding. All parameters come from config/config.yaml; use src/common.py and the functions in scripts/acard_reference.py (apply_population_filters).

Task:
1. Read config.data.raw_snapshot_table. Use the target column in config.target_definition.source_column as is; never recompute it. Check it only takes 1, 0, -1, -2; stop if not.
2. File type is precomputed: use config.file_type.source_column as is (no Appendix G derivation). Print its value counts before filtering.
3. Derive sample_status from target via config.target_codes, then apply config.population_filters in order with apply_population_filters (values trimmed and upper-cased; empty string = null). Application-time rules -> EXCLUDED; performance_related rules -> EXCLUDED_PERF. Write the rule name to exclusion_reason.
4. Assign window (DEV / OOT / FWD / STRESS) by config.windows on the application date column, plus app_month and app_quarter.
5. OOT label use: for OOT, compute ONLY aggregate counts (records and Bads) needed for the Section 1.2 reconciliation and the waterfall. No other analysis of OOT labels.
6. Reconcile GOOD+BAD records and Bads against config.expected_counts (ALL, DEV, DEV_EARLY, DEV_LATE, OOT). If any figure differs, stop and print the difference by window and by filter rule. Do not adjust filters to make numbers match.
7. Produce the outputs in spec 4.2, saved under config.databricks.artifacts_root/reports/:
   - exclusion waterfall, one row per filter rule (removed, remaining, remaining GOOD+BAD, remaining Bads);
   - monthly vintage table by app_month (counts per sample_status, Bad Rate, Indeterminate share);
   - missing-rate and special-value share by app_quarter for every FEATURE column;
   - cross-tab of ACTIVE_REPORTING x target in DEV (count and Bad Rate of removed records);
   - monthly Bad Rate chart with dates from config/policy_changes.csv overlaid (skip the overlay if the file has no rows).
   If month-on-book delinquency columns are not available, skip the vintage curves (spec 4.1 step 1.5) and record this in reports/open_questions.md.
8. Save the master table as a Delta table <catalog>.<schema>.acard_master (catalog and schema from config.databricks), including all original columns plus sample_status, exclusion_reason, window, app_month, app_quarter. Do not overwrite the source table.
9. Check every acceptance criterion in spec 4.3 and print PASS / FAIL for each.
```

---

## E3 数据切分 `src/s02_split`

```text
@acard-scorecard Implement module E3 (data split) as notebook src/s02_split.
Read spec 3.2, 5.1, 5.3, 5.4, 5.5 and Appendix D.1–D.2. Follow AGENTS.md.

Input: master table <catalog>.<schema>.acard_master (output of E2b).

1. Using common.assign_window, add: window (DEV/OOT/FWD/STRESS from config.windows, [start, end) on
   config.columns.date; rows outside every window get "OUT_OF_SCOPE" and are reported), app_month (YYYY-MM),
   app_quarter (e.g. 2023Q3), oot_half (Q1/Q2 from config.oot_report_splits, null outside OOT).
   Write back to the master table; row count must not change.
2. R-folds: DEV rows with sample_status in labelled_statuses. RepeatedStratifiedKFold with config.cv.r_folds and
   config.random_seed; stratification key = target + "_" + app_quarter. Store by app_id (not row position):
   columns app_id, scheme="R", repeat, fold, part (train/valid) -> folds/r_folds.parquet.
3. T-folds T1–T3 from config.cv.t_folds on the same population, same format -> folds/t_folds.parquet.
4. Back-test split from config.backtest, same format -> folds/backtest.parquet.
5. Report reports/02_split.xlsx: counts and Bads by window (GOOD+BAD); counts by window x sample_status;
   DEV_EARLY / DEV_LATE; per R-fold n, Bads, Bad Rate and quarter mix of the valid part; per T-fold train/valid n and Bads.

Acceptance cell:
- master row count unchanged; no null window.
- GOOD+BAD records and Bads for ALL, DEV, DEV_EARLY, DEV_LATE equal config.expected_counts exactly.
  OOT: compare with expected_counts.OOT using one aggregate SQL count only (no OOT rows in pandas).
- common.load_window(master, "OOT") raises while model_registry.json is missing or locked != true.
- 15 R-folds; within each repeat every app_id is in exactly one valid fold; each fold's Bad Rate within ±1 pp of DEV.
- T-fold train/valid sets are disjoint and match config dates; all fold app_ids are DEV GOOD+BAD.
```

**你要看**：`02_split.xlsx` 里 DEV 应为 10,526 / 924，DEV early 7,612 / 710，DEV late 2,914 / 214。

---

## E4 L0 数据质量与合规 `src/s03_L0`

**运行前**：`config/feature_dict.csv` 里每个 FEATURE 都要填好 `available_at_decision`（Y/N）、`compliance_ok`（Y/N）、`special_codes`、`expected_direction`（+ / - / 0 / 空），`definition_change_date` 可以为空。可以按数据源批量填，比如经数据团队确认后，`aecb_` 开头的整批填 Y。没填完的话，E4 会停下来，并列出缺哪些。

```text
@acard-scorecard Implement module E4 (funnel L0) as notebook src/s03_L0.
Read spec 2.4, 2.5, 6.0, 6.1, 6.8. Follow AGENTS.md.

Input: master, window = DEV, sample_status in (GOOD, BAD, INDETERMINATE); config/feature_dict.csv, role = FEATURE only.

0. Create (or refresh) <catalog>.<schema>.acard_feature_log: one row per FEATURE with feature, source, dtype.
   Store sha256 of config.funnel as funnel_config_hash in the run summary.
1. Validate feature_dict for every FEATURE: available_at_decision and compliance_ok in {Y, N};
   expected_direction in {+, -, 0, empty}; special_codes parseable; definition_change_date a date or empty.
   If anything is invalid or missing, list it in reports/open_questions.md and stop. Never default these values.
2. Rules in order; the first failure drops the feature (L0_pass = N, L0_reason, dropped_at = L0, drop_rule):
   a. available_at_decision = N -> TIMING_LEAKAGE
   b. role != FEATURE, compliance_ok = N, or derived from a WATCH column per the dictionary -> COMPLIANCE
   c. single_value_share > max_single_value_share -> SINGLE_VALUE.
      single_value_share = count of the most frequent non-missing value (special codes count as values) / all rows.
   d. missing_rate > max_missing_rate -> MISSING, unless informative: in GOOD+BAD rows, the Bad Rate of the missing
      group vs the non-missing group differs by a factor >= missing_informative_ratio (either direction) AND the missing
      group has >= missing_informative_min_bad Bads -> keep, L0_reason = INFORMATIVE_MISSING.
   e. definition_change_date inside the DEV window and the dictionary column restated != Y -> DEFINITION_CHANGE.
3. Columns: L0_pass, L0_reason, single_value_share, missing_rate, missing_bad_rate_ratio.
4. Report reports/03_L0.xlsx: counts by reason and by source; full per-feature table.

Acceptance cell: every FEATURE has L0_pass; every dropped feature has dropped_at and drop_rule; no WATCH/KEY/FLAG/
PERFORMANCE column passes; only DEV GOOD/BAD/INDETERMINATE rows used; feature_log.csv exported.
```

---

## E5 L1 OptBinning + IV `src/s03_L1`

**这一步要跑两遍**：第一遍跑完会生成 `reports/03_L1_review_needed.xlsx`。你和业务方在 `config/l1_review.csv` 里给这些特征填好结论，再跑第二遍。

```text
@acard-scorecard Implement module E5 (funnel L1) as notebook src/s03_L1.
Read spec 6.2 (all), 6.8, 7.3. Follow AGENTS.md. Check funnel_config_hash first.

Input: DEV, sample_status in (GOOD, BAD); features with L0_pass = Y; y = (sample_status == "BAD").

1. Fit optbinning OptimalBinning per feature with config.funnel.L1.binning; special_codes from feature_dict;
   categorical dtype with cat_cutoff for categorical features; missing in its own bin (no imputation).
   expected_direction = 0: fit monotonic_trend "peak" and "valley", keep the higher IV, log the reason "U-shape per dictionary".
   Record iv_dev, n_bins, trend (ascending/descending/peak/valley from the fitted table), solver status.
2. direction_conflict = Y when the fitted trend contradicts expected_direction (+ = higher value, higher Bad Rate).
3. IV rules: iv_dev < iv_min -> drop IV_LOW. iv_review_band -> compute iv_cv; drop IV_CV_LOW if iv_cv < iv_min.
   iv_dev > iv_leak_review -> compute iv_cv and set leak_review = PENDING.
   iv_cv (6.2.3): StratifiedKFold(cv_iv_folds, shuffle=True, random_state=seed) on key target + "_" + app_quarter;
   fit binning on 4 folds, apply to the held-out fold, IV from the held-out Good/Bad counts with +0.5 on empty counts; mean.
4. Human review via config/l1_review.csv (read-only for you). For each feature with leak_review = PENDING or
   direction_conflict = Y: row present -> apply it (DROP -> drop_rule LEAKAGE or DIRECTION_CONFLICT; KEEP -> keep,
   copy reason into leak_review / direction_review); no row -> L1_pass = PENDING and list it in
   reports/03_L1_review_needed.xlsx (feature, iv_dev, iv_cv, trend, expected_direction, binning table).
5. Save every fitted binning object to binning/L1/<feature>.pkl and all binning tables
   (bins, counts, Bads, event rate, WoE, IV) to reports/03_L1_binning.xlsx.

Acceptance cell: regular bins meet min_bin_size, min_bin_n_event and max_n_bins; every feature in the review band or
above iv_leak_review has iv_cv; no feature is PENDING (if any are, fail with the list); dropped features have reasons.
```

---

## E6 L2 风险关系的时间稳定性 `src/s03_L2`

```text
@acard-scorecard Implement module E6 (funnel L2) as notebook src/s03_L2.
Read spec 6.3 and D.5. Follow AGENTS.md. Check funnel_config_hash first.

Input: DEV GOOD+BAD; features with L1_pass = Y; L1 binning objects (do NOT refit).

1. Periods S1–S4 with common.equal_bad_segments(n_segments), cut at month ends. Report boundaries, n, Bads, Bad Rate.
2. Per feature and period, with the fixed L1 bins:
   iv_s1..iv_s4 (+0.5 on empty Good/Bad counts);
   rank_corr_sk = Spearman of period vs full-DEV bin Bad Rates over non-missing, non-special bins with
   >= min_bin_count_for_rank records in that period (null if fewer than 3 bins);
   head_tail_flip_sk: H / L = highest / lowest full-DEV Bad Rate among non-missing, non-special bins; flip if period BR(H) <= BR(L);
   WoE sign flip of the missing bin or any special bin across periods.
3. Rules: drop L2_IV_UNSTABLE if #periods with iv < seg_iv_min >= drop_if_low_iv_segments_ge;
   drop HEAD_TAIL_FLIP if any period flips;
   L2_flag = Y (not dropped) if min rank_corr < rank_corr_flag, max/min IV > iv_ratio_flag (min > 0),
   or missing/special WoE sign flip; record L2_flag_reason.
4. Columns iv_s1..iv_s4, rank_corr_min, head_tail_flip, L2_flag, L2_flag_reason, L2_pass.
   Report reports/03_L2.xlsx with per-feature period Bad Rate tables.

Acceptance cell: the 4 period Bad counts are each within ±25% of their mean; every L1-passed feature has L2 columns;
no refit of binning (object hashes unchanged); feature_log.csv exported.
```

---

## E7 L3 PSI `src/s03_L3`

**这一步也要跑两遍**：第一遍跑完看 `reports/03_psi.xlsx` 里的 `psi_decisions_todo` 页，在 `config/psi_decisions.csv` 里给每个红色特征填原因和决定，再跑第二遍。**红色特征没有填决定的，会按 UNKNOWN 处理，直接剔除。**

```text
@acard-scorecard Implement module E7 (funnel L3 PSI) as notebook src/s03_L3.
Read spec 6.4 (all), D.4 and the first row of 11.2. Follow AGENTS.md. Check funnel_config_hash first.

Population P1: sample_status in config.psi_statuses; windows DEV, FWD, STRESS only. OOT is never read. No labels,
except the POLICY head-tail check in step 5 (DEV GOOD+BAD only).
Features: L2_pass = Y. Convert each to its L1 bin index (missing and each special code are separate bins).

1. (1) Each DEV quarter (10) vs all DEV -> psi_max_dev, psi_last_q. (2) Adjacent quarters (9) -> max_adj_psi, jump_quarter.
   (3) FWD vs all DEV -> psi_fwd (null + note if FWD has no feature data).
   (4) STRESS months m1..m7 vs all DEV -> psi_stress_m1..m7 (diagnosis only, never used to drop).
   Use common.psi_from_bins / l3_psi_table with eps from config.
2. psi_status from max(psi_max_dev, psi_fwd): green <= psi_green; yellow <= psi_red; red above.
3. missing_jump = Y if any quarter's missing rate differs from full DEV or from the previous quarter by > missing_jump (flag only).
4. Red features: read config/psi_decisions.csv (feature, cause_type DATA|POLICY|DRIFT|UNKNOWN, evidence,
   policy_change_date, decision KEEP|DROP, reviewer, date). No row -> cause_type UNKNOWN, decision DROP.
   KEEP is valid only with cause_type POLICY, non-empty evidence and policy_change_date; any other KEEP -> stop with an error.
5. For POLICY + KEEP: head-tail check on DEV GOOD+BAD before vs after policy_change_date with the L1 bins;
   a reversal -> drop PSI_POLICY_REVERSAL regardless of the decision.
6. Columns per 6.8 (psi_max_dev, psi_last_q, max_adj_psi, jump_quarter, psi_fwd, missing_jump, psi_status,
   cause_type, psi_decision, psi_stress_m1..m7) and L3_pass.
7. reports/03_psi.xlsx: summary; quarterly PSI matrix; adjacent PSI matrix; quarterly missing-rate matrix;
   red-feature sheet with config/policy_changes.csv dates overlaid on quarters; sheet psi_decisions_todo
   listing red features without a row.

Acceptance cell: every red feature has a decision (missing = UNKNOWN, dropped); no drop is caused by STRESS;
baseline and comparison use the same status filter; zero OOT rows read; feature_log.csv exported.
```

---

## E8 L4 冗余与共线性 `src/s03_L4`

```text
@acard-scorecard Implement module E8 (funnel L4) as notebook src/s03_L4.
Read spec 6.5. Follow AGENTS.md. Check funnel_config_hash first.

Input: DEV GOOD+BAD; features with L3_pass = Y; WoE from the L1 binning objects (transform metric="woe").

1. priority_rank: psi_status green, then yellow, then red-kept; within that L2_flag N before Y; then iv_dev descending.
2. Greedy correlation de-duplication in priority order: keep a feature only if |Spearman r| <= corr_max against every
   kept feature; otherwise drop CORR with corr_with = the kept feature with the largest |r|.
3. VIF (statsmodels, WoE plus constant): while max VIF > vif_max, drop the highest-VIF feature (tie -> lower priority), recompute.
4. Source diversity: kept count per source; list each source that had features with iv_dev >= 0.05 at L3 but none kept,
   with the best candidates (report only, no automatic change).
5. Save feature_lists/l4_pool.json (ordered: feature, source, dtype, trend, special_codes). Set in_pool_BC, L4_pass, vif.
   Report reports/03_L4.xlsx (correlation matrix of kept features, VIF table, source diversity).

Acceptance cell: pairwise |Spearman| <= corr_max among kept features; all VIF <= vif_max; pool size reported
(≈40 expected, not a hard check); feature_log.csv exported.
```

---

## E9 L5 稳定性选择（Model A 特征）`src/s03_L5`

```text
@acard-scorecard Implement module E9 (funnel L5) as notebook src/s03_L5.
Read spec 6.6 and D.6. Follow AGENTS.md. Check funnel_config_hash first.

Input: DEV GOOD+BAD; L4 pool; WoE from L1 bins.

1. C*: StratifiedKFold(5, shuffle=True, random_state=seed) on key target + "_" + app_quarter; L1 logistic regression
   (liblinear; use the parameter form required by the pinned scikit-learn version) over np.logspace(*config c_grid).
   SE = std/sqrt(5). 1-SE rule: smallest C with mean AUC >= best mean - SE. Fixed L1 bins are used; state in the report
   that binning was not refitted per fold (allowed by 6.6.1).
2. Stability selection with common.stability_selection: n_subsamples, subsample_frac, seed + i, stratified on the key,
   fixed C*. Record select_freq.
3. common.pick_features with select_freq thresholds, floor and the n_features range.
4. statsmodels Logit (with constant) on WoE: repeat until stable: if coefficient signs are not all equal, drop the
   minority-sign feature with the largest p-value; if any p >= pvalue_max, drop the largest p. Then check VIF <= vif_max.
5. Points concentration: Factor = pdo / ln(2); points per bin = -coef * WoE * Factor; points range per feature;
   share = range / sum of ranges; > points_share_flag -> flag for review (no drop).
6. Save feature_lists/model_a.json. Columns select_freq, coef, p_value, points_range_share, L5_pass, final_A.
   Finalise the summary columns dropped_at, drop_rule, final_A, in_pool_BC for every feature.
7. reports/03_L5.xlsx: C path and C*, selection frequencies, threshold used, Logit summary, final list;
   reports/03_funnel_summary.xlsx: features in and out per layer and per source.

Acceptance cell: 10–20 final features (if fewer than 10 after the floor, pass only with an explanation written to the
report and open_questions.md); all coefficient signs equal; all p < pvalue_max; VIF <= vif_max; every feature-log row
has either dropped_at or final status; feature_log.csv exported.
```

**跑完 E9 之后**：漏斗就完成了。建议把 `03_funnel_summary.xlsx` 先发给验证团队看一眼，再开始建模。

---

## E10 调参 `src/s04_tune`

```text
@acard-scorecard Implement module E10 (tuning) as notebook src/s04_tune.
Read spec 5.5, 7.1, 7.2, 7.3, 7.4, 7.5. Follow AGENTS.md.

Data: DEV GOOD+BAD only; R-folds and T-folds from E3 (join on app_id).
Features: Model A = feature_lists/model_a.json; Models B and C = feature_lists/l4_pool.json (raw values).

1. Put in common.py (reused by E11, E13, E16, API): prepare_raw(df, features, feature_dict) -> special codes to NaN plus
   indicator <feature>_is_special_<code>; categorical features as pandas category.
   monotone vector for C: +1 ascending L1 trend, -1 descending, 0 for peak/valley/categorical/indicators.
2. Model A reference: 15 R-fold AUC with Pipeline([BinningProcess(L1 params, special codes), LogisticRegression(no penalty,
   max_iter=2000)]) so binning is refitted per fold. No tuning.
3. Stage 1 (Optuna TPESampler(seed)): C = tuning.lightgbm_trials trials over the 7.5 ranges (fixed: binary/auc,
   bagging_freq 1, monotone_constraints_method "advanced", deterministic, seed, num_threads, categorical_feature,
   min_data_per_group 100, cat_smooth 20). Each trial: lgb.cv on the 15 R-folds, early_stopping lgb_early_stopping,
   max lgb_max_rounds; score = mean AUC at the best iteration; store mean, std and best_iter.
   B = tuning.ebm_trials trials over the 7.4 grid (categorical choices; fixed interactions 0, outer_bags 14,
   validation_size 0.15, early_stopping_rounds 100, random_state seed); score = mean 15-fold AUC; store mean, std.
4. Stage 2: shortlist trials with mean >= best mean - std(best), top max_candidates by mean. Evaluate on T1–T3
   (LightGBM rounds = the trial's stage-1 best_iter x T-train size / R-fold train size, rounded; no early stopping on
   the T validation block). t_auc_mean, t_auc_std. Pick the highest t_auc_mean, then among trials within
   simplicity_tolerance choose the simplest (C: smaller num_leaves, smaller max_depth, larger min_child_samples,
   larger lambda_l2; B: smaller max_bins, smaller max_leaves, larger min_samples_leaf).
5. Stage 3 (C): lgb.cv with the chosen params on R-fold repeat 1 (5 folds), early stopping 100, max 3000 -> best_iter;
   final rounds = round(best_iter x lgb_round_multiplier).
6. Outputs: reports/04_tuning.xlsx (all trials, shortlist, T-fold results, choice and reason);
   params/chosen_params.json (A: features + binning params; B: params; C: params, final rounds, monotone vector, num_threads).

Acceptance cell: 60 C trials and 30 B trials recorded; re-applying the stage-2 selection logic to the saved trial table
gives the same single parameter set; no OOT rows read.
```

---

## E11 训练与 OOF `src/s04_train`

```text
@acard-scorecard Implement module E11 (final DEV models and OOF) as notebook src/s04_train.
Read spec 5.5 (mandatory note), 7.3–7.6. Follow AGENTS.md.

Data: DEV GOOD+BAD; params/chosen_params.json; folds from E3.

1. Final models on all DEV:
   A: BinningProcess on Model A features -> WoE -> sklearn LogisticRegression (no penalty) and statsmodels Logit;
      assert max |coef difference| < 1e-4; save coefficients, SE, p-values, VIF; points table with optbinning Scorecard
      and config.scaling (higher score = lower risk).
   B: EBM with chosen params, interactions=0; monotonize features whose expected_direction is + or - and agrees with the
      L1 trend (check the signature for the pinned interpret version). Shape check: refit on T1, T2, T3 training parts,
      plot each feature's shape; ebm_shape_check = FAIL for any head-tail reversal across fits, else PASS.
   C: LightGBM with chosen params and fixed final rounds; no early stopping.
2. OOF: R-fold repeat 1 (5 folds). Each fold fitted from scratch (A includes binning; B/C include prepare_raw).
   Save oof_predictions.parquet (app_id, model, fold, p_oof). DEV OOF AUC, Gini, KS per model.
3. T-fold AUC per model (A refits binning in each T-fold) -> t_auc_mean, t_auc_std (input to rule R3).
4. Save models under models/ (A: binning process, sklearn and statsmodels objects, points table; B: EBM pickle;
   C: LightGBM model text and pickle) and write sha256 for every file.
   reports/04_training.xlsx: coefficients, EBM shapes, LightGBM feature importance, OOF and T-fold metrics.

Acceptance cell: every DEV GOOD+BAD app_id appears exactly once per model in OOF; for every fold the valid app_ids never
entered the binning or model fit (assert disjoint); Model A signs equal and p < pvalue_max; sklearn vs statsmodels
difference < 1e-4; no OOT rows read.
```

---

## E12 模型锁定 `src/s04_lock`

**人工检查点**：第一遍运行会生成 `locked: false` 的注册表。把 8.1 的决策规则和注册表发给模型负责人确认，在 `config/signoff.yaml` 里填 `decision_rules_signed_by` 和 `signed_date`，然后再跑一遍，才会变成 `locked: true`。

```text
@acard-scorecard Implement module E12 (model lock) as notebook src/s04_lock.
Read spec 7.7, 8.1, F.3, F.4. Follow AGENTS.md.

1. Build model_registry.json: version (config.registry.version), created time, git commit, config sha256,
   funnel_config_hash, feature lists (A, B/C pool), binning and model file paths with sha256, chosen params,
   LightGBM final rounds, DEV OOF metrics, t_auc_mean/std per model, EBM shape-check result,
   decision rules R1–R4 and the selection logic with the actual thresholds copied from config.selection,
   bootstrap settings, Platt method (fit on DEV OOF). Also copy config.strategy_overlay into model_registry.json under "pre_registered.strategy_overlay";
   after locked: true it must not change (refuse if the config value differs from the registry).
2. Read config/signoff.yaml. Set locked: true only if decision_rules_signed_by and signed_date are filled AND every
   file hash re-verifies; copy the sign-off fields and lock time into the registry. Otherwise write locked: false and stop
   with a message saying what is missing.
3. If a registry with locked: true already exists and anything would change, refuse; a change needs a new
   config.registry.version and is recorded as a new version.
4. If config.registry.register_in_uc is true, register A/B/C as <catalog>.<schema>.acard_model_a/b/c with alias "locked".

Acceptance cell: all hashes verify; locked is true only with sign-off; common.load_window(master, "OOT") raises before
the lock and does not raise after it (call it only after the lock is written).
```

**可选加固（F.4）**：锁定之后，再让平台团队给开发账号开放 OOT 标签表的读权限。

---

## E13 OOT 评估与模型选择 `src/s05_oot`

**运行前**：
1. 准备好 `config/reason_code_map.csv`（每个模型特征对应一个原因组和说明文字）。
2. 让合规确认原因码的分组和计算方法，确认后在 `signoff.yaml` 里设 `r4_reason_codes_approved: true`。没设的话，R4 会是 PENDING，选出来的模型只能算“暂定”。

```text
@acard-scorecard Implement module E13 (OOT evaluation and model selection) as notebook src/s05_oot.
Read spec 5.4, 6.7, 8.1–8.5, 9.1, 9.3 and D.3. Follow AGENTS.md.

Precondition: model_registry.json locked: true; re-verify every file hash; abort on any mismatch.
Data: OOT GOOD+BAD via common.load_window; DEV OOF from oof_predictions.parquet.

1. Score OOT with the locked A, B, C (raw PD). For R2, fit Platt per model on DEV OOF only
   (logit(PD) = a + b * logit(p_raw)); save to calibration/platt_dev_oof.json (E15 must reproduce it).
2. Metrics per 8.2 for each model, overall, Q1 and Q2:
   AUC, Gini, KS with stratified bootstrap 95% CI (selection.bootstrap); DEV -> OOT decay (DEV from OOF);
   score-band Bad Rate table using deciles of the final model's DEV scores as fixed cut-points (and quintiles) plus a
   monotonicity check; top 10% / 20% Bad capture; CITL, calibration slope, Brier, log loss (calibrated PD);
   calibration by decile; score PSI OOT vs DEV on DEV score deciles.
   Segments: config.columns.segments and every WATCH column (nationality group, gender, age band): AUC and quintile
   Bad Rates; segments with < 50 Bads report monotonicity only. Approval rate by watch variable at
   strategy.proposed_cutoff if set; otherwise report by score decile and note it.
3. Paired bootstrap (common.paired_bootstrap, PD direction) for B-A, C-A, C-B: mean, 2.5%, 97.5% and P(Δ <= 0) of
   ΔAUC, ΔGini, ΔKS. DeLong on AUC as a cross-check.
4. Rules with thresholds read from the REGISTRY (not config): R1 lower CI of ΔGini(X-A) > r1_gini_lift_lower;
   R2 calibrated log loss X <= A; R3 t_auc_std(X) <= r3_tfold_std_ratio x t_auc_std(A) AND KS drop Q1->Q2 of
   X <= A's drop + r3_q2_ks_drop_margin; R4 = signoff r4_reason_codes_approved AND (for B) ebm_shape_check PASS,
   else PENDING. Selection logic exactly as 8.1 (C over B needs lower CI of ΔGini(C-B) > c_over_b_gini_lift_lower).
   If any R4 is PENDING, label the choice PROVISIONAL.
5. L6 report (6.7) for every feature used by A, B or C: OOT IV, Bad Rate by bin, WoE direction vs DEV, PSI vs DEV,
   overall/Q1/Q2. Write oot_iv, oot_psi, oot_direction_ok to the feature log. Never drop or change features.
6a. If every model's Gini decays by more than 0.10 vs DEV OOF, add a diagnosis sheet (8.5); change nothing.
6b. Strategy overlay (from registry pre_registered.strategy_overlay, never from config):
   Use the selected model's calibrated PD/score. Fit band cut-points on DEV only:
   own score by own_score_bands, external_score by external_bands (missing external_score = its own band).
   method = matrix: on OOT (overall, Q1, Q2) report a cross-table with count, share, Bads and Bad Rate per cell,
   monotonicity along each axis, Spearman correlation of the two scores, and the missing rate of external_score.
   method = logit_combine: fit logit(PD) = a + blogit(own OOF PD) + cexternal_score (+ missing indicator) on
   DEV OOF only; on OOT run the paired bootstrap combined vs own model; adopt only if the lower 95% CI of
   ΔGini > combine_rule.gini_lift_lower.
   State in the sheet that DEV/OOT external_score values predate version_change_date and that cut-points or
   coefficients cannot be applied to the new score version without re-validation.
   Write the result to the "strategy_overlay" sheet of reports/05_oot.xlsx; it does not affect model selection.
7. Write the result into model_registry.json under a new "oot_evaluation" key (do not touch locked fields).
   reports/05_oot.xlsx with all of the above.

Acceptance cell: exactly one selected model with the rule-by-rule reasons; thresholds used equal the registry;
every metric reported overall, Q1 and Q2; no feature-log selection columns changed; locked fields unchanged.
```

---

## E14 补充回测 `src/s05_backtest`

```text
@acard-scorecard Implement module E14 (supplementary back-test) as notebook src/s05_backtest.
Read spec 5.3 and 8.4. Follow AGENTS.md.

Use folds/backtest.parquet (train 2022-07..2024-06, test 2024-07..2024-12, DEV GOOD+BAD only).
For A, B, C: use the LOCKED feature lists and hyperparameters from the registry; refit binning and models on the train
part; LightGBM rounds = round(final DEV rounds x 7612 / 10526) computed from actual counts.
Report on the test part: AUC, Gini, KS with bootstrap CI, score-band Bad Rates (deciles/quintiles), top 10/20% capture.
reports/05_backtest.xlsx with a note: "Supporting evidence only; the test period was used in feature selection and
tuning; not part of the 8.1 decision rules."

Acceptance cell: features and params equal the registry; train/test counts equal expected_counts DEV_EARLY/DEV_LATE;
rounds scaled as specified.
```

---

## E15 校准与评分刻度 `src/s06_calibrate`

```text
@acard-scorecard Implement module E15 (calibration and score scaling) as notebook src/s06_calibrate.
Read spec 9.1, 9.3, D.7. Follow AGENTS.md.

1. Platt for A, B, C fitted on DEV OOF only; assert the parameters equal calibration/platt_dev_oof.json from E13.
   Never fit on in-sample predictions or on OOT. No isotonic regression.
2. OOT tests per model, overall/Q1/Q2, after calibration: CITL, calibration slope, Brier, log loss, decile calibration table.
3. Score mapping with common.pd_to_score and config.scaling; put unit tests in the acceptance cell
   (PD = 1/21 -> 600, PD = 1/41 -> 620, PD = 1/11 -> 580). Report the share capped at score_min and score_max.
4. Save calibration/calibration.json (a, b per model, scaling parameters, Factor, Offset).
   reports/06_calibration.xlsx.

Acceptance cell: parameters fitted on OOF only and equal to E13; unit tests pass; capped shares reported
(warn if either > 0.5%).
```

---

## E16 全量重训 `src/s07_retrain`

**运行前**：风险管理部要确认长期平均坏账率（TBC-11）。确认的数值填进 `signoff.yaml` 的 `central_tendency_target`；如果留空，就默认用 2024-07 到 2025-06 的实际坏账率。

```text
@acard-scorecard Implement module E16 (full-data refit) as notebook src/s07_retrain.
Read spec Chapter 10 and 9.2. Follow AGENTS.md.

Model: the model selected in E13 (registry oot_evaluation; stop if it is PROVISIONAL).
Data: DEV + OOT, GOOD+BAD (2022-07-01 to 2025-06-30).

1. M_full: feature list, binning settings and hyperparameters FIXED from the registry; bin cut-points and model
   parameters refitted; LightGBM rounds = round(DEV final rounds x full GOOD+BAD count / DEV GOOD+BAD count).
2. Calibration: Platt refitted on 5-fold OOF over all data (StratifiedKFold, seed, key target + "_" + app_quarter);
   then adjust only the intercept a so the mean PD on the full training sample equals
   signoff.central_tendency_target, or, if null, the actual Bad Rate of GOOD+BAD applications in
   config.calibration.central_tendency. Record which source was used.
3. Consistency checks 10.2 on OOT (M_full vs M_dev): binning direction per feature; if the selected model is A,
   all signs equal and p < pvalue_max; Spearman of scores >= retrain.score_spearman_min; decile cross-table
   diagonal + adjacent >= retrain.decile_agreement_min; M_full OOT AUC >= M_dev OOT AUC - retrain.auc_tolerance
   (label this in-sample, check only).
4. Sensitivity 10.3: M_full_ex refitted without applications in retrain.exclude_shock_sensitivity; compare
   M_full vs M_full_ex with the same correlation and decile criteria.
5. Save the production package under models/production/ (model, binning, Platt + adjusted intercept, scaling,
   feature list, sha256) and add a "production" section to the registry. If register_in_uc, give it alias "champion"
   only when every check passes. reports/07_retrain_consistency.xlsx.

Acceptance cell: every 10.2 check passes (else stop, no champion alias); sensitivity result reported with a
PASS/REFER_TO_RISK verdict; performance conclusions in the report reference M_dev OOT results only.
```

---

## E17 压力测试 `src/s08_stress`

```text
@acard-scorecard Implement module E17 (stress test) as notebook src/s08_stress.
Read spec Chapter 11 and 6.4.3 item 4. Follow AGENTS.md.

Data: STRESS and FWD (P1 statuses). Diagnosis only: nothing here changes features or models.
Model: production package from E16.

1. Monthly feature PSI for production-model features vs all DEV (reuse L1 bins; same as psi_stress_m1..m7).
2. Monthly score PSI vs DEV score distribution (DEV score deciles).
3. Population mix by month: shares by every WATCH column and config.columns.segments (P1; P2 too if
   reject_inference.data != none).
4. Policy timeline: config/policy_changes.csv vs monthly volume; approval rate only if declined applications exist,
   otherwise state it is not available.
5. Early delinquency: applications 2026-03 to 2026-06 with >= early_delinquency.min_mob months on book; FPD and
   3M 30+ DPD rates by production-score quintile; monotonicity check. If the columns in config.early_delinquency are null,
   skip, say so in the report and add an open question.
6. For each model feature, a suggested pattern from 11.3 (TEMPORARY / STRUCTURAL / MEANING_CHANGE / PRE_EXISTING)
   based on the PSI path and early-delinquency monotonicity, marked "for review".
7. Recommended monitoring thresholds (Chapter 14) for features that are shifting.
   reports/08_stress_report.xlsx with charts.

Acceptance cell: every 11.2 analysis is present or explicitly marked not available with a reason; the feature log
and the registry are unchanged.
```

---

## E17b 拒绝推断与政策变更影响 `src/s09_reject_policy`

规格书 Appendix E 里没有这一步，但第 12 章要求有产出。所以我补了一个模块。

```text
@acard-scorecard Implement Step 9 (spec Chapter 12) as notebook src/s09_reject_policy. Follow AGENTS.md.

1. Reject inference by config.reject_inference.data:
   none -> write the limitation statement from 12.2 to the report; no analysis.
   features_only -> compare approved vs declined on model features and production scores; share of declined
     applicants in each approved score band; no statistical inference.
   bureau_outcome -> stop and write to open_questions.md which columns hold declined applicants' bureau 12M 90+ DPD
     and the compliance approval reference; continue only once they are in config.
2. Policy impact (12.3): overlay policy_changes.csv on the monthly Bad Rate (DEV GOOD+BAD), the L3 adjacent-quarter
   PSI of model features and (if available) the approval rate. One row per policy change: affected months,
   Bad Rate shift, PSI jumps, assessed model impact (blank for the modeller to complete).
3. Early vs late DEV Bad Rate (9.33% vs 7.34%): shift-share decomposition into mix effect and rate effect by
   segments, watch variables and the bins of each Model A feature.
   reports/09_reject_policy.xlsx.

Acceptance cell: the branch used matches config; the decomposition reconciles to the total Bad Rate difference.
```

---

## E18 原因码 `src/s10_reason_codes`

```text
@acard-scorecard Implement module E18 (reason codes) as notebook src/s10_reason_codes.
Read spec 13.1, 13.2. Follow AGENTS.md.

1. Create src/acard_scoring.py (the single scoring library for offline use AND the API):
   score(raw_df) -> calibrated pd, score, reason_codes (top config.reason_codes.n_codes), model_version, data_status,
   features. It must reuse common.prepare_raw, the production binning/model, calibration and pd_to_score.
2. Reason codes:
   A / B (additive): points_i per feature (A from the points table; B from EBM term scores converted to points),
   max_points_i over all bins including missing/special; gap_i = max_points_i - points_i; sum by reason_group from
   config/reason_code_map.csv; top groups with gap > 0; ties ordered by group code.
   C: shap.TreeExplainer on log-odds; baseline = expected_value on DEV (record it); add special-value indicators to
   their parent feature; sum by reason_group; top groups with contribution > 0.
3. Validate reason_code_map.csv: every production feature mapped; unmapped -> stop with the list.
4. On OOT (and FWD for the score only): frequency of each group as primary reason (flag > 50%);
   a sheet of the 50 lowest-scoring applications (or below proposed_cutoff if set) with their reason codes
   for manual business review. reports/10_reason_codes.xlsx.

Acceptance cell: determinism (same input twice -> identical outputs, including tie order); every returned group has
gap/contribution > 0; codes are aggregated by group, never by single feature.
```

---

## E19 上线一致性回放 `src/s10_replay`

```text
@acard-scorecard Implement module E19 (replay test) as notebook src/s10_replay.
Read spec 13.1, 13.3, 13.5 and F.6. Follow AGENTS.md.

1. Wrap src/acard_scoring.py in an MLflow pyfunc model (artifacts: production package, reason_code_map,
   requirements.lock) and log it to the experiment; register it in UC if register_in_uc is true.
2. Data failure rule: inputs carry a per-source status; if AECB or another external source is TIMEOUT/ERROR,
   return data_status, no pd/score, route = MANUAL_REVIEW. Never score with missing values in place of a failed lookup.
3. Replay sample >= deployment.replay_n_min applications covering DEV, OOT and FWD, including rows with missing and
   special values (stratified sample, seed). Offline result = batch scoring of the raw rows through the training-time
   path (E16 package as used in E16/E18); online result = mlflow.pyfunc.load_model(...).predict on the same raw rows
   (and the serving endpoint if one exists).
4. Compare per record: numeric features |diff| <= deployment.numeric_tol; categorical features exact; score exact;
   reason codes exact; also test the TIMEOUT path. reports/10_replay.xlsx with every mismatch listed.

Acceptance cell: zero mismatches; replay size >= replay_n_min; all windows covered; TIMEOUT rows return no score.
```

---

## E20 上线后监控 `src/s11_monitor`

```text
@acard-scorecard Implement module E20 (monitoring) as notebook src/s11_monitor.
Read spec Chapter 14 and 13.4. Follow AGENTS.md.

Input: config.monitoring.score_log_table (per-application log: app_id, timestamp, features, pd, score, reason codes,
model_version, data_status). If null, simulate the log by scoring FWD and STRESS with acard_scoring.score so the
report can be tested before launch, and label the report SIMULATED.
Parameters: report month (widget), frequency (monthly/weekly for the shadow-run variant).

1. Every Chapter 14 metric with amber/red status from config.monitoring: score PSI and feature CSI vs the training
   sample; data-failure rate vs the shadow-run baseline; approval rate and score distribution; by watch variable
   (approval-rate gap between groups); early delinquency actual/expected for the highest-risk quintile and quintile
   rank-ordering (two consecutive non-monotonic months = red); quarterly 12M 90+ Gini vs the OOT Gini and calibration
   ratio once mature (skip with a note when not mature).
2. Shadow-run weekly variant (13.4): score distribution, simulated approval rate at proposed_cutoff, cross-table vs
   current strategy decisions (if available), data-failure rate, exit-criteria check (score PSI vs FWD < 0.10).
3. Append every amber/red trigger to <catalog>.<schema>.acard_monitoring_log (date, metric, value, status, action required).
   reports/monitoring/<YYYY-MM>.xlsx.

Acceptance cell: every Chapter 14 metric present or marked not yet available with a reason; statuses match the
config thresholds on a small hand-checked example; triggers written to the log table.
```

---

## 人工检查点（按顺序）

| 时间点 | 你要做的 | 文件 |
|---|---|---|
| E4 之前 | 补全特征字典里的时效、合规、特殊值、预期方向 | `config/feature_dict.csv` |
| E5 第一遍之后 | 给高 IV 泄漏审查、方向冲突的特征逐个下结论 | `config/l1_review.csv` |
| E7 第一遍之后 | 给红色 PSI 特征填原因和决定 | `config/psi_decisions.csv` |
| E9 之后 | 把漏斗汇总发给验证团队（建议） | `03_funnel_summary.xlsx` |
| E12 两遍之间 | 模型负责人签字确认决策规则 | `config/signoff.yaml` |
| E13 之前 | 合规确认原因码映射；可选：开放 OOT 标签表权限 | `reason_code_map.csv`、`signoff.yaml` |
| E16 之前 | 风险管理部确认长期平均坏账率（TBC-11） | `signoff.yaml` |
| E18 之后 | 业务人工审查 50 笔低分申请的原因码 | `10_reason_codes.xlsx` |

## 规格书没写、这里替你定的做法

下面这些规格书没有写明，我在指令里给了具体做法，避免 Genie 停下来问或者自己乱猜。建议你确认后写进规格书 v1.0.6，方便验证团队对照：

1. **L0 单值占比的分母**：用全部记录，分子是出现最多的非缺失值（特殊值也算一个值）。这样“缺失”只由缺失率规则处理，“有信息量的缺失”这条例外也不会被单值规则提前剔除。
2. **L1 人工审查文件** `l1_review.csv`：规格书要求做泄漏审查和方向冲突的业务审查，但没定义结论记在哪里。
3. **L3 POLICY 保留**：`psi_decisions.csv` 新增 `policy_change_date` 一列，代码会在政策变更前后各做一次头尾反转检查。只有 POLICY 类可以 KEEP。
4. **调参第 1、2 阶段的 LightGBM 轮数**：第 1 阶段用 `lgb.cv` 早停；第 2 阶段的 T-fold 不早停，轮数按样本量从第 1 阶段折算。
5. **R2 在 E13 里就要用到校准后的结果**：所以 E13 先用 DEV OOF 拟合 Platt（符合 9.1），E15 再核对参数是否一致。
6. **R4 的顺序问题**：原因码的完整验收在 E18，但 E13 选模型时就要用 R4。所以改成在 E13 之前，先让合规确认原因码的映射和方法；没确认的话，选出来的模型标为“暂定”，E16 不会继续执行。
7. **评分分档切点**：用最终 DEV 模型在 DEV 上的分数十分位；DEV→OOT 的衰减用 OOF 指标。
8. **新增 E17b**（第 12 章）和统一评分库 `src/acard_scoring.py`（第 13.3 节“一套代码”的落地方式）。
9. **监控阈值放进 config**（`monitoring:`），不在代码里写死。
