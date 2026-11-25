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

## Deviations from the plan (spec v1.0.5)
- <e.g. decisions made in the E3–E20 prompts not in the spec; v1.0.1 clean rebuild; variant; RI universe changes>

## Open items
- <FTS approval; target approval rate; SAS migration; Implementation Plan>
