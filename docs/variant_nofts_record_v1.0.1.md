# A Card variant on v1.0.1: model without FTS features

Record of the work to build a no-FTS variant of the locked and OOT-evaluated main model **v1.0.1**.
Keep this file in the branch as `docs/variant_nofts_record_v1.0.1.md` and fill in the blanks (`<…>`).
It replaces the earlier record based on v1.0.0, which is now obsolete.

| Item | Value |
|---|---|
| Variant registry version | `1.0.1-nofts` |
| Git branch | `cc_variant_nofts_v101`, created from `eda` at the v1.0.1 lock commit |
| Base commit | `<commit id>` (must equal `git_commit` in the v1.0.1 registry) |
| Main model | v1.0.1, registry `/Volumes/mis_automation/datascience_pbg/pbg_cc_acore/output/v1.0.1/model_registry.json` |
| Main model status | locked `<date>`; E13 run `<date>`; selected model `<A/B/C>` |
| Requested by / date | `fts removal by Amrita's team(card product), requested by Abhinav, 2026-11-03` |
| Reason | `fts data removal` |
| Intended use | `<analysis only / parallel model for applicants without FTS / candidate replacement>` |
| Old branch `cc_variant_nofts` | based on v1.0.0, obsolete; kept unmerged for the record, not used |

---

## 1. Design principles

1. **FTS is excluded at L0** (`SOURCE_EXCLUDED_BY_SCOPE`), never at training or tuning: every funnel layer depends on
   which features are present (for example L4 may have dropped a non-FTS feature only because of an FTS correlate).
2. **Only FTS differs.** Same master table, folds, thresholds, selection rules, scaling and reason-code method as v1.0.1.
3. **Shared inputs are read-only.** The variant does not run E2 or E3. It reads `acard_master_v101` and the v1.0.1 folds.
4. **Separate outputs, sign-off and lock**: own artefacts folder, own feature-log table, own registry and signature.
5. **OOT has already been read for v1.0.1.** The variant is built for an external reason, not because of OOT results,
   so it may be evaluated on the same OOT. This must be disclosed, the comparison rule must be registered **before**
   the variant reads OOT (section 4), and nothing in the variant is changed after its OOT results are seen.

---

## 2. Branch setup

1. On `eda`: commit and push everything (including any changes made while running v1.0.1 E13).
2. Check the v1.0.1 registry: `version = 1.0.1`, `locked = true`, and its `git_commit`.
   If `eda` has commits after that commit, list them here and confirm they do not change E4–E13 behaviour.
   If possible, tag the lock commit `acard-v1.0.1` in the Git provider.
3. Do **not** reuse the old `cc_variant_nofts` branch: it was created from the v1.0.0 code and its config points to
   v1.0.0 paths. Leave it unmerged (record only).
4. Git dialog → **Create branch** `cc_variant_nofts_v101` from `eda`. Check the top bar shows the new branch.
5. Copy `config/config.yaml` to `docs/config_main_v101_baseline.yaml` (baseline for the diff in 3.3).
6. Save this record in `docs/` and commit: `docs: start variant nofts on v1.0.1 (record + config baseline)`.

---

## 3. Configuration (branch `cc_variant_nofts_v101` only)

### 3.1 Edit `config/config.yaml`

Edit existing keys **in place**; add new keys at top level (not inside `funnel:`). Never append a duplicate section.

| Key | Variant value |
|---|---|
| `feature_scope.exclude_prefixes` | `["fts_"]` |
| `tables.master` | `acard_master_v101` (read-only, unchanged from main) |
| `tables.feature_log` | `acard_feature_log_v101_nofts` |
| `shared_inputs.folds_root` | `"/Volumes/mis_automation/datascience_pbg/pbg_cc_acore/output/v1.0.1/folds"` |
| `main_artifacts_root` | `"/Volumes/mis_automation/datascience_pbg/pbg_cc_acore/output/v1.0.1"` |
| `artifacts_root` (in its current place) | `"/Volumes/mis_automation/datascience_pbg/pbg_cc_acore/output/v1.0.1_nofts"` |
| `registry.version` | `"1.0.1-nofts"` |
| `variant_comparison` | new; see section 4 |
| `review_files.signoff` | unchanged (`config/signoff.yaml`; the branch has its own copy) |

Do **not** change `data`, `windows`, `expected_counts`, `column_roles`, `population_filters`, `funnel`, `tuning`,
`selection`, `strategy_overlay`, `calibration`, `scaling`, `retrain`.

### 3.2 Reset `config/signoff.yaml`

The branch inherited the v1.0.1 sign-off. Blank it, using the structure the code reads (currently the flat fields):

```yaml
decision_rules_signed_by: ""
signed_date: ""
model_owner: ""
role: ""
registry_version: "1.0.1-nofts"
evidence_ref: ""
r4_reason_codes_approved: false
r4_approved_by: ""
central_tendency_target: null
central_tendency_approved_by: ""
```

### 3.3 Check the configuration

```python
import yaml
base = yaml.safe_load(open("../docs/config_main_v101_baseline.yaml"))   # adjust the relative path
var  = yaml.safe_load(open("../config/config.yaml"))
def diff(x, y, path=""):
    for k in sorted(set(x) | set(y)):
        p = f"{path}.{k}" if path else k
        if isinstance(x.get(k), dict) and isinstance(y.get(k), dict):
            diff(x[k], y[k], p)
        elif x.get(k) != y.get(k):
            print(f"{p}: {x.get(k)!r} -> {y.get(k)!r}")
diff(base, var)
```

Only the keys in 3.1 may appear. Commit: `config: variant nofts on v1.0.1`.

---

## 4. Pre-register the comparison (before the variant reads OOT)

The main model's OOT results are already known. To keep the variant's evaluation honest, decide **now** how its result
will be judged, and have it signed with the variant's decision rules at E12. Agree the numbers with the requester and
the model owner; the values below are placeholders.

```yaml
variant_comparison:                       # copied into the variant registry at E12; must not change after the lock
  main_registry: "/Volumes/mis_automation/datascience_pbg/pbg_cc_acore/output/v1.0.1/model_registry.json"
  metric: gini
  acceptable_if: {delta_gini_main_minus_variant_upper_ci_max: 0.03}   # placeholder: variant at most 3 Gini points worse
  segments: [has_fts_data]                # report the comparison separately for applicants with and without FTS data
  cutoff_for_swap: null                   # null = strategy.proposed_cutoff; else a score
```

`has_fts_data` must be a column (or derivable rule) that says whether an applicant had any FTS data at application.
If it does not exist, define it in P1 (for example: all FTS features missing → N).

---

## 5. Code changes (Genie Code, on branch `cc_variant_nofts_v101`)

### P1. Variant support and guards

First check whether `eda` already has these generic changes (search `src/` for `exclude_prefixes`). Add only what is missing.

```text
@acard-scorecard We are on Git branch cc_variant_nofts_v101: a no-FTS variant of the locked main model v1.0.1
(record in docs/variant_nofts_record_v1.0.1.md). Edit files in this Git folder only. Follow AGENTS.md.
1. Config keys (top level): feature_scope.exclude_prefixes, tables.master, tables.feature_log, shared_inputs.folds_root,
   main_artifacts_root, variant_comparison. Defaults when absent must reproduce the main model exactly.
2. E4 (src/s03_L0): before rule a, drop every FEATURE whose name starts with a prefix in feature_scope.exclude_prefixes,
   L0_pass = N, L0_reason = drop_rule = SOURCE_EXCLUDED_BY_SCOPE, dropped_at = L0.
3. All modules use config.tables.*; E5–E11 read folds from shared_inputs.folds_root when set (read-only).
4. Variant guard (artifacts_root != main_artifacts_root): s01a_feature_dict, s01b_data_prep and s02_split raise at the
   first cell ("Variant run: E2/E3 are shared with the main model"); every notebook asserts artifacts_root !=
   main_artifacts_root and tables.feature_log != the main feature log; nothing writes under main_artifacts_root.
5. Every notebook prints branch, artifacts_root, table names and registry.version at the start.
6. E12: copy config.variant_comparison into the registry under pre_registered.variant_comparison; after locked: true it
   must not change (refuse if config differs).
7. If no has_fts_data column exists, add a derived flag in a shared helper: has_fts_data = Y if any fts_ feature is
   non-missing for the applicant, else N (computed from the master table, read-only).
Keep generic, default-preserving changes in commits separate from this branch's config. List the files changed.
```

### P2. Consistency check against v1.0.1 (run after E7)

```text
@acard-scorecard Write src/s99_variant_consistency (report only, writes only under the variant artifacts_root).
Compare config.tables.feature_log with the main log acard_feature_log_v101 (read-only).
1. Every FTS feature has L0_reason = SOURCE_EXCLUDED_BY_SCOPE in the variant.
2. For every other feature these columns are identical in both logs (tolerance 1e-9): L0_pass, L0_reason,
   single_value_share, missing_rate, iv_dev, iv_cv, n_bins, trend, direction_conflict, iv_s1..iv_s4, rank_corr_min,
   head_tail_flip, L2_flag, L2_pass, psi_max_dev, psi_last_q, max_adj_psi, psi_fwd, psi_status, cause_type,
   psi_decision, L3_pass.
3. List features whose L4/L5 outcome differs between the runs, with the main run's corr_with for each.
4. funnel_config_hash equals the v1.0.1 value.
reports/99_variant_consistency.xlsx; assert 1, 2 and 4.
```

### P3. Comparison with v1.0.1 (add to E13 on this branch)

```text
@acard-scorecard On branch cc_variant_nofts_v101 extend src/s05_oot (E13) with the comparison registered in
pre_registered.variant_comparison (read it from the variant REGISTRY, not config). Do not change anything else.
1. Load the v1.0.1 selected model and its calibration from main_registry (read-only; verify hashes; abort on mismatch).
   Score the same OOT GOOD+BAD applications with v1.0.1 and with the variant's selected model (calibrated PD and score).
2. Paired bootstrap main minus variant (ΔAUC, ΔGini, ΔKS; 95% CI; P(Δ <= 0); config.selection.bootstrap),
   overall, Q1, Q2, and by each segment in variant_comparison.segments (segments with < 50 Bads: monotonicity only).
3. Verdict ACCEPTABLE / NOT_ACCEPTABLE from acceptable_if, exactly as registered.
4. Agreement: Spearman of scores; decile cross-table (diagonal and adjacent share); calibration (CITL, log loss) of each.
5. Decision impact at the cut-off (variant_comparison.cutoff_for_swap, else strategy.proposed_cutoff; if both null, at
   the main model's score deciles): approved by main only / by variant only / by both / by neither, with OOT Bad Rate of
   each group.
6. What replaced FTS: features in the variant not in v1.0.1 (and vice versa), with IV and points share / SHAP share;
   the FTS features' total contribution in v1.0.1.
Sheet "vs_main_v101" in reports/05_oot.xlsx. Descriptive only: it does not change the variant's own R1–R4 selection.
```

---

## 6. Run order and checks (branch `cc_variant_nofts_v101`)

Before each run check the banner: branch, `artifacts_root` ending `/v1.0.1_nofts`, feature log `acard_feature_log_v101_nofts`.

| # | Step | Check | Done |
|---|---|---|---|
| — | E2a, E2b, E3 | **Not run**; guard must stop them | n/a |
| 1 | E4 `s03_L0` | FTS features all `SOURCE_EXCLUDED_BY_SCOPE` | ☐ |
| 2 | E5 `s03_L1` | Reuses `l1_review.csv`; new review items only if any | ☐ |
| 3 | E6 `s03_L2` | — | ☐ |
| 4 | E7 `s03_L3` | Reuses `psi_decisions.csv` | ☐ |
| 5 | P2 | `s99_variant_consistency` asserts pass | ☐ |
| 6 | E8 `s03_L4` | Note features that now survive (former FTS correlates) | ☐ |
| 7 | E9 `s03_L5` | 10–20 features; same signs; p < 0.05 | ☐ |
| 8 | Reason codes | Check every new pool feature is in `reason_code_map.csv`; if the map changes, Compliance must re-approve | ☐ |
| 9 | E10, E11 | — | ☐ |
| 10 | E12 (1st run) | Draft registry with `pre_registered.variant_comparison`; `locked: false` | ☐ |
| 11 | Sign-off | Model owner approves the variant's rules and the comparison rule in writing; fill `signoff.yaml` | ☐ |
| 12 | E12 (2nd run) | `locked: true` | ☐ |
| 13 | R4 | Compliance confirms the reason-code map and method apply to the variant; set `r4_reason_codes_approved` | ☐ |
| 14 | E13 + P3 | Variant R1–R4 selection; sheet `vs_main_v101`; verdict | ☐ |
| 15 | E14–E19 | Only if the variant will be deployed | ☐ |

### Results

| Result | v1.0.1 | 1.0.1-nofts |
|---|---|---|
| L4 pool size / Model A features | `<…>` | `<…>` |
| Selected model | `<…>` | `<…>` |
| OOT Gini overall / Q1 / Q2 | `<…>` | `<…>` |
| ΔGini main − variant (95% CI) | — | `<…>` |
| ΔGini, applicants with FTS data / without | — | `<…>` / `<…>` |
| Verdict (pre-registered rule) | — | `<ACCEPTABLE / NOT_ACCEPTABLE>` |
| Decisions changed at cut-off (share) | — | `<…>` |

---

## 7. How to read the comparison

| Finding | Meaning |
|---|---|
| ΔGini small, CI includes 0, verdict ACCEPTABLE | FTS adds little beyond AECB/CASA/APP; the variant can serve where FTS is unavailable |
| ΔGini clearly positive overall, but ≈ 0 for applicants without FTS data | FTS helps only where it exists; the variant is a good model for the no-FTS segment |
| ΔGini large for applicants with FTS data | Dropping FTS costs real discrimination for bank customers; keep the main model for them |
| Many decisions change at the cut-off despite similar Gini | Same overall power but different people approved; review with Risk/Strategy before any use |
| Calibration differs (CITL, log loss) | Recalibrate (E15/E16) before comparing score-based strategies |

The OOT has ~392 Bads (about 195 per quarter), and fewer within segments: differences of 2–3 Gini points are usually
within noise. Use the CIs, not point estimates.

---

## 8. Branch rules and merging

- Commit before switching branches; check the branch name before running anything; don't run main jobs while on
  the variant branch; tell Genie the branch at the start of each chat; switch back to `eda` at the end of a session.
- Generic code commits (default-preserving) may be merged back to `eda` through a pull request; after merging, run
  E4 on `eda` with v1.0.1's config into a scratch folder and confirm the feature log equals `acard_feature_log_v101`.
- Branch config and `signoff.yaml` are never merged back.

---

## 9. For the model document

- Why the variant was built, by whom, for what use; method (FTS excluded at L0, everything else identical to v1.0.1);
- P2 evidence that only FTS differs; features that entered because their FTS correlates were removed;
- separate sign-off and lock of `1.0.1-nofts`, including the pre-registered comparison rule;
- OOT statement: *"The OOT window (2025-01 to 2025-06) was used to evaluate v1.0.1 before the no-FTS variant was built.
  The variant was requested for <reason>, independently of OOT results; its comparison rule was registered before it
  read OOT, and no design choice was changed after its OOT results were seen."*;
- P3 results overall, by quarter and by FTS availability; decision impact at the cut-off; the verdict.

---

## 10. Checklist

- [ ] `eda` committed; v1.0.1 lock commit recorded (and tagged)
- [ ] New branch `cc_variant_nofts_v101` from `eda`; baseline config and this record committed
- [ ] `config.yaml` edited (3.1 only); diff check passes; `signoff.yaml` blanked
- [ ] Comparison rule agreed and written to `variant_comparison`
- [ ] P1 done; E2/E3 guards stop; generic code committed separately
- [ ] E4–E7; P2 passes
- [ ] E8–E11; reason-code map covers the new pool
- [ ] E12 draft → written approval (rules + comparison rule) → lock
- [ ] R4 confirmation recorded
- [ ] E13 + P3; results and verdict recorded
- [ ] Deployment decision recorded (E14–E19 if yes)
- [ ] Model document section written
