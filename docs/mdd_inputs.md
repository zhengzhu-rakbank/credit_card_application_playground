# MDD human inputs

## Roles
- Model owner: Rehan Riaz Ahmad, Business Head - Cards • Cards Product
- Model developer(s): Zheng Zhu
- Business sponsor: <name, role>
- Validation contact: Girish Govinda Shenoy

## Purpose and intended use
- Business purpose: To improve credit decisions for thin-file salaried credit card applicants, where bureau data is
  sparse and the current A-Score discriminates poorly, by estimating the 12-month probability of 90+ DPD from bureau
  and internal data. The model supports approve/decline decisions at a Credit Policy cut-off, aiming to reduce bad
  accounts at the current approval rate or increase approvals at the same risk.
- Decisions supported: approve/decline at cut-off <TBC by Credit Policy>; 
- Population: thin-file, salaried, credit card applications (spec 2.3)
- Model proposed for deployment: no deployment decision yet. Both models are documented for validation: ModelC with FTS (v1.0.1) and Model C without FTS (nofts_c, v1.0.1-nofts). Developer recommendation: FTS If FTS is approved for production    use and available at decision time; otherwise nofts_c; Use: approve/decline at a cut-off to be set by Credit Policy (target approval rate TBC). Decision Owners: <> (FTS approval), Credit Policy (cut-off). Status: pending, expected 2026-12-12    fallback: If FTS is not approved by go-live or data is not available at decision time, nofts_c is deployed and fts_c is introduced later as a challenger. If no new model is approved, the current A-Score remains in use. Operational fallback    (bureau data unavailable): no score, manual review
- Deployment platform and timing: <after SAS migration; owner; date TBC>

## Decisions and approvals (date, who, evidence)
- Target definition (12M, bucket 4+): BAD is bucket 4 or worse (90+ days past due), GOOD is bucket 0 only, buckets 1–3 are INDETERMINATE. Codes: BAD 1, GOOD 0, INDETERMINATE −1, IMMATURE −2. Decided 2026-10-07 by Policy Team. Evidence: <email "RE: [Placeholder] CC Application scorecard update">
- Population filters agreed with Risk Analysis: application-time exclusions (VIP, ruling family, supplementary cards, SALARIED-IM, segment policy,
  STAFF/SME class codes), inclusions (cards, salaried, thin file), performance-related exclusions (fraud status,
  ACTIVE_REPORTING ≠ Y). Agreed 2026-10-13 with Risk Analysis on 2026-09
- AECB score excluded by policy: <Abhinav, the score is a blackbox to us and it may change, 2026-10>
- FTS removal request (variant): Abhinav, 2026-11-03, card product team (Amrita)
- Decision rules signed (registry): <…>
- Central tendency target: null
- Reject-inference universe definition: Thin File declines with reason INTERNAL SCORE DECLINE, with hard-policy and retained-rule reasons excluded.
- Target approval rate (Credit Policy): <TBC>
-  Model C is proposed instead because it beats Model A on out-of-time (OOT) data in both versions, and it declines more bad applicants at the same approval rate. No-FTS (v1.0.1-nofts): OOT Gini is 0.489 for C vs 0.463 for A, and the gain is statistically above zero. Calibrated OOT log loss is 0.26666 vs 0.27066. C declines at least as many bads as A at all 10 approval rates from 60% to 97.5%. The 95% CI of net bads avoided excludes zero at 60%, 70%, 85% and 90% (for example 70%: 22 [8, 36]; 90%: 19 [7, 31]). Applicants that only C declines are riskier than those that only A declines (bad rate 13.7% vs 7.8% at 70%; 23.6% vs 12.2% at 90%). FTS (v1.0.1): OOT Gini is 0.522 for C vs 0.492 for A (average gain +0.029, statistically above zero). Calibrated OOT log loss is 0.26015 vs 0.26420. C passes R2, R3 and R4 (reason codes approved). The cut-off evidence is weaker here: C is ahead at 8 of 10 approval rates and level at 85% and 97.5%. The CI excludes zero only at 70% (net 15 [1, 29]). At 87.5% C is worse than A (−6 [−17, 5]), though not significantly. Rules failed by C: R1 in both versions. The lower 95% CI bound of the Gini gain over A is 0.0061 (no-FTS) and 0.0066 (FTS), below the 0.02 required. Evidence: cut off analysis and R1 to R4. Model A is retained as the benchmark and fallback model.

## Deviations from the plan (spec v1.0.5)
 
 - Model C is proposed instead because it beats Model A on out-of-time (OOT) data in both versions, and it declines more bad applicants at the same approval rate. No-FTS (v1.0.1-nofts): OOT Gini is 0.489 for C vs 0.463 for A, and the gain is statistically above zero. Calibrated OOT log loss is 0.26666 vs 0.27066. C declines at least as many bads as A at all 10 approval rates from 60% to 97.5%. The 95% CI of net bads avoided excludes zero at 60%, 70%, 85% and 90% (for example 70%: 22 [8, 36]; 90%: 19 [7, 31]). Applicants that only C declines are riskier than those that only A declines (bad rate 13.7% vs 7.8% at 70%; 23.6% vs 12.2% at 90%). FTS (v1.0.1): OOT Gini is 0.522 for C vs 0.492 for A (average gain +0.029, statistically above zero). Calibrated OOT log loss is 0.26015 vs 0.26420. C passes R2, R3 and R4 (reason codes approved). The cut-off evidence is weaker here: C is ahead at 8 of 10 approval rates and level at 85% and 97.5%. The CI excludes zero only at 70% (net 15 [1, 29]). At 87.5% C is worse than A (−6 [−17, 5]), though not significantly. Rules failed by C: R1 in both versions. The lower 95% CI bound of the Gini gain over A is 0.0061 (no-FTS) and 0.0066 (FTS), below the 0.02 required. C passes R2 and R3 in both versions. R4 passes for FTS and is still pending for no-FTS (compliance has not yet approved the reason codes), so it is not a failure.

## Open items
- <FTS approval; target approval rate; SAS migration; Implementation Plan>
