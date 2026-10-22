"""Module E1 — common utilities for the A Card thin-file credit card scorecard.

All thresholds and parameters are read from config.yaml (Appendix C).
Reference implementations follow Appendix D of the specification (v1.0.5-EN).

Spec sections: 3.2, 3.3, Appendix C, Appendix D, 16.3.
"""

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
import sklearn
import yaml
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, roc_curve
from sklearn.model_selection import RepeatedStratifiedKFold, StratifiedShuffleSplit

_SK_VER = tuple(int(x) for x in sklearn.__version__.split(".")[:2])

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration  (Appendix C)
# ---------------------------------------------------------------------------

def load_config(path: str = "config/config.yaml") -> dict:
    """Load the project configuration from a YAML file."""
    with open(path) as f:
        cfg = yaml.safe_load(f)
    return cfg


def config_hash(cfg: dict) -> str:
    """SHA-256 hash of the configuration for traceability (spec 3.2)."""
    raw = yaml.dump(cfg, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()


def artifacts_path(cfg: dict) -> str:
    """Return the base artifacts path from config."""
    return "/" + cfg["databricks"]["artifacts_root"].lstrip("/")


def find_project_root(start: str) -> str:
    """Walk up from *start* until ``config/config.yaml`` is found."""
    p = os.path.abspath(start)
    while p != "/":
        if os.path.exists(os.path.join(p, "config", "config.yaml")):
            return p
        p = os.path.dirname(p)
    raise FileNotFoundError(f"config/config.yaml not found above {start}")


def git_commit(root: str) -> str:
    """Current commit of the Git folder at *root* (reads .git directly); 'unknown' if unavailable."""
    try:
        head = open(os.path.join(root, ".git", "HEAD")).read().strip()
        if not head.startswith("ref:"):
            return head
        ref = head.split(" ", 1)[1]
        p = os.path.join(root, ".git", ref)
        if os.path.exists(p):
            return open(p).read().strip()
        pr = os.path.join(root, ".git", "packed-refs")
        if os.path.exists(pr):
            for line in open(pr):
                if line.strip().endswith(ref):
                    return line.split()[0]
    except Exception:
        pass
    return "unknown"


# ---------------------------------------------------------------------------
# Label guard  (spec 2.2 — mandatory rule)
# ---------------------------------------------------------------------------

def assert_labelled(df: pd.DataFrame, cfg: dict) -> None:
    """Raise if the DataFrame contains records outside GOOD / BAD.

    Every label-based calculation MUST filter ``sample_status in (GOOD, BAD)``.
    This guard prevents accidental use of INDETERMINATE / IMMATURE / EXCLUDED
    records.  When ``sample_status`` has not yet been derived, the check falls
    back to *target* values.
    """
    status_col = cfg["columns"]["status"]
    labelled = set(cfg["labelled_statuses"])
    target_col = cfg["columns"]["target"]
    target_codes = cfg["target_codes"]
    allowed_targets = {target_codes["GOOD"], target_codes["BAD"]}

    if status_col in df.columns:
        actual = set(df[status_col].unique())
        bad = actual - labelled
        if bad:
            raise ValueError(
                f"Label-based function received records with sample_status "
                f"in {bad}. Filter to sample_status in {labelled} first."
            )
    elif target_col in df.columns:
        target_vals = set(df[target_col].unique())
        bad_targets = target_vals - allowed_targets
        if bad_targets:
            raise ValueError(
                f"Label-based function received records with target "
                f"in {bad_targets}. Filter to sample_status in {labelled} first."
            )


# ---------------------------------------------------------------------------
# D.1  Window assignment and OOT read lock  (spec 3.2)
# ---------------------------------------------------------------------------

def assign_window(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Assign time windows (DEV / OOT / FWD / STRESS) from ``config.windows``.

    Also creates ``app_month`` and ``app_quarter`` columns.
    Uses the date column specified in ``cfg['columns']['date']``.
    """
    date_col = cfg["columns"]["date"]
    d = pd.to_datetime(df[date_col])
    df = df.copy()
    df["window"] = pd.NA
    for name, (s, e) in cfg["windows"].items():
        df.loc[(d >= s) & (d < e), "window"] = name
    df["app_month"] = d.dt.to_period("M")
    df["app_quarter"] = d.dt.to_period("Q")
    return df


def load_window(
    master: pd.DataFrame,
    name: str,
    cfg: dict,
    registry_path: Optional[str] = None,
) -> pd.DataFrame:
    """Return records for one window.

    OOT is locked until ``model_registry.json`` has ``locked: true``
    (spec 3.2).  Raises ``PermissionError`` if the lock is not in place.
    """
    if registry_path is None:
        registry_path = os.path.join(
            artifacts_path(cfg), "model_registry.json"
        )
    if name == "OOT":
        try:
            with open(registry_path) as f:
                locked = json.load(f).get("locked", False)
        except FileNotFoundError:
            locked = False
        if not locked:
            raise PermissionError(
                "OOT is locked until model_registry.json has locked=true"
            )
    return master[master["window"] == name].copy()


# ---------------------------------------------------------------------------
# D.2  Cross-validation splits  (spec 5.5)
# ---------------------------------------------------------------------------

def r_folds(dev: pd.DataFrame, cfg: dict) -> list:
    """Repeated stratified k-fold splits (spec 5.5.1).

    Stratification key = ``target`` x ``app_quarter``.
    *dev* MUST contain GOOD + BAD only.
    """
    assert_labelled(dev, cfg)
    cv_cfg = cfg["cv"]["r_folds"]
    seed = cfg["random_seed"]
    target_col = cfg["columns"]["target"]
    strat = (
        dev[target_col].astype(int).astype(str)
        + "_"
        + dev["app_quarter"].astype(str)
    )
    rskf = RepeatedStratifiedKFold(
        n_splits=cv_cfg["n_splits"],
        n_repeats=cv_cfg["n_repeats"],
        random_state=seed,
    )
    return list(rskf.split(np.zeros(len(dev)), strat))


def t_folds(dev: pd.DataFrame, cfg: dict) -> list:
    """Time-based expanding-window folds T1-T3 (spec 5.5.2)."""
    date_col = cfg["columns"]["date"]
    d = pd.to_datetime(dev[date_col]).to_numpy()
    out = []
    for fold_name, fold_cfg in cfg["cv"]["t_folds"].items():
        ts, te = fold_cfg["train"]
        vs, ve = fold_cfg["valid"]
        tr = np.where(
            (d >= np.datetime64(ts)) & (d < np.datetime64(te))
        )[0]
        va = np.where(
            (d >= np.datetime64(vs)) & (d < np.datetime64(ve))
        )[0]
        out.append((tr, va))
    return out


# ---------------------------------------------------------------------------
# D.3  Paired bootstrap  (spec 8.1)
# ---------------------------------------------------------------------------

def ks_stat(y: np.ndarray, p: np.ndarray) -> float:
    """KS statistic: max |TPR - FPR|."""
    fpr, tpr, _ = roc_curve(y, p)
    return float(np.max(tpr - fpr))


def paired_bootstrap(
    y: np.ndarray,
    pd_x: np.ndarray,
    pd_y: np.ndarray,
    cfg: dict,
) -> pd.DataFrame:
    """Paired bootstrap comparison of two models (spec 8.1).

    Stratified resampling of Good and Bad separately.
    Returns DataFrame with dAUC, dGini, dKS statistics and CIs.
    """
    boot_cfg = cfg["selection"]["bootstrap"]
    n_boot = boot_cfg["n"]
    seed = boot_cfg["seed"]
    rng = np.random.default_rng(seed)
    y, pd_x, pd_y = map(np.asarray, (y, pd_x, pd_y))
    i_bad = np.where(y == 1)[0]
    i_good = np.where(y == 0)[0]
    rec = {"dAUC": [], "dGini": [], "dKS": []}
    for _ in range(n_boot):
        idx = np.concatenate([
            rng.choice(i_bad, len(i_bad), replace=True),
            rng.choice(i_good, len(i_good), replace=True),
        ])
        yb = y[idx]
        a_x = roc_auc_score(yb, pd_x[idx])
        a_y = roc_auc_score(yb, pd_y[idx])
        rec["dAUC"].append(a_x - a_y)
        rec["dGini"].append(2 * (a_x - a_y))
        rec["dKS"].append(ks_stat(yb, pd_x[idx]) - ks_stat(yb, pd_y[idx]))
    rows = []
    for k, v in rec.items():
        v = np.asarray(v)
        rows.append({
            "metric": k,
            "mean": v.mean(),
            "ci_low": np.percentile(v, 2.5),
            "ci_high": np.percentile(v, 97.5),
            "p_le_0": float(np.mean(v <= 0)),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# D.4  PSI  (spec 6.4)
# ---------------------------------------------------------------------------

def psi_from_bins(
    expected: pd.Series,
    actual: pd.Series,
    eps: float = 1e-4,
) -> float:
    """PSI from bin-index series (spec 6.4).

    Empty bins are floored to *eps* to avoid log(0).
    """
    e = expected.value_counts(normalize=True, dropna=False)
    a = actual.value_counts(normalize=True, dropna=False)
    idx = e.index.union(a.index)
    e = e.reindex(idx, fill_value=0).clip(lower=eps)
    a = a.reindex(idx, fill_value=0).clip(lower=eps)
    return float(((a - e) * np.log(a / e)).sum())


def l3_psi_table(
    dev_bins: pd.DataFrame,
    dev_q: pd.Series,
    fwd_bins: Optional[pd.DataFrame],
    features: list,
    cfg: dict,
) -> pd.DataFrame:
    """Build the L3 PSI summary table (spec 6.4).

    For each feature: PSI of each DEV quarter vs all DEV,
    adjacent-quarter PSI, and PSI of FWD vs all DEV.
    """
    eps = cfg["funnel"]["L3"]["eps"]
    psi_green = cfg["funnel"]["L3"]["psi_green"]
    psi_red = cfg["funnel"]["L3"]["psi_red"]
    quarters = sorted(dev_q.unique())
    rows = []
    for f in features:
        full = dev_bins[f]
        psi_q = [
            psi_from_bins(full, dev_bins.loc[dev_q == q, f], eps)
            for q in quarters
        ]
        psi_adj = [
            psi_from_bins(
                dev_bins.loc[dev_q == a, f],
                dev_bins.loc[dev_q == b, f],
                eps,
            )
            for a, b in zip(quarters[:-1], quarters[1:])
        ]
        psi_fwd = (
            psi_from_bins(full, fwd_bins[f], eps)
            if fwd_bins is not None
            else np.nan
        )
        m = np.nanmax([max(psi_q), psi_fwd])
        rows.append({
            "feature": f,
            "psi_max_dev": max(psi_q),
            "psi_last_q": psi_q[-1],
            "max_adj_psi": max(psi_adj),
            "jump_quarter": str(quarters[1:][int(np.argmax(psi_adj))]),
            "psi_fwd": psi_fwd,
            "psi_status": (
                "red" if m > psi_red
                else ("yellow" if m > psi_green else "green")
            ),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# D.5  Equal-Bad segments  (spec 6.3)
# ---------------------------------------------------------------------------

def equal_bad_segments(dev: pd.DataFrame, cfg: dict) -> pd.Series:
    """Split DEV months into periods with equal Bad counts (spec 6.3).

    *dev* MUST contain GOOD + BAD only.
    Returns Series: ``app_month`` -> S1 .. Sn.
    """
    assert_labelled(dev, cfg)
    n_seg = cfg["funnel"]["L2"]["n_segments"]
    target_col = cfg["columns"]["target"]
    m = dev.groupby("app_month")[target_col].sum().sort_index()
    cum = m.cumsum() / m.sum()
    seg = np.minimum(
        (np.ceil(cum * n_seg - 1e-9)).astype(int), n_seg
    )
    seg = seg.clip(lower=1)
    return ("S" + seg.astype(str)).rename("segment")


# ---------------------------------------------------------------------------
# D.6  Stability selection  (spec 6.6)
# ---------------------------------------------------------------------------

def stability_selection(
    X_woe: pd.DataFrame,
    y: pd.Series,
    strat: pd.Series,
    C: float,
    cfg: dict,
) -> pd.Series:
    """L1-penalised stability selection (spec 6.6).

    Returns Series: feature name -> selection frequency.
    """
    l5 = cfg["funnel"]["L5"]
    n_sub = l5["n_subsamples"]
    frac = l5["subsample_frac"]
    seed = cfg["random_seed"]
    counts = pd.Series(0, index=X_woe.columns, dtype=float)
    for i in range(n_sub):
        sss = StratifiedShuffleSplit(
            n_splits=1, train_size=frac, random_state=seed + i
        )
        idx, _ = next(sss.split(X_woe, strat))
        lr = lr_l1(C)
        lr.fit(X_woe.iloc[idx], y.iloc[idx])
        counts += (np.abs(lr.coef_[0]) > 1e-8).astype(float)
    return (counts / n_sub).sort_values(ascending=False)


def pick_features(freq: pd.Series, cfg: dict) -> Tuple[list, float]:
    """Select features by stability-selection frequency (spec 6.6).

    Returns ``(selected_feature_names, threshold_used)``.
    """
    l5 = cfg["funnel"]["L5"]
    lo, hi = l5["n_features"]
    thresholds = l5["select_freq"]
    floor = l5["select_freq_floor"]
    sel = pd.Series(dtype=float)  # initialise for safety
    for thr in thresholds:
        sel = freq[freq >= thr]
        if len(sel) <= hi:
            break
    if len(sel) < lo:
        thr = floor
        sel = freq[freq >= thr]
    return list(sel.index), thr


# ---------------------------------------------------------------------------
# D.7  Score mapping  (spec 9.3)
# ---------------------------------------------------------------------------

def pd_to_score(
    pd_: np.ndarray,
    cfg: dict,
) -> np.ndarray:
    """Convert calibrated PD to integer score (spec 9.3).

    Good:Bad odds scale — higher score = lower risk.

    Unit-test anchors (section 16.3)::

        PD = 1/21  -> 600   (base score at base odds 20:1)
        PD = 1/41  -> 620   (double the odds -> +20 points)
    """
    sc = cfg["scaling"]
    base_score = sc["base_score"]
    base_odds = sc["base_odds"]
    pdo = sc["pdo"]
    lo = sc["score_min"]
    hi = sc["score_max"]
    pd_ = np.clip(np.asarray(pd_, dtype=float), 1e-6, 1 - 1e-6)
    factor = pdo / np.log(2)
    offset = base_score - factor * np.log(base_odds)
    score = offset + factor * np.log((1 - pd_) / pd_)
    return np.clip(np.round(score), lo, hi).astype(int)


# ---------------------------------------------------------------------------
# D.8  Population filters and waterfall  (spec 2.3)
# ---------------------------------------------------------------------------

def _norm(s: pd.Series) -> pd.Series:
    """Upper-case and trim string values; empty strings become null.

    Numbers are compared as text ("0", "1").
    """
    out = s.astype("string").str.strip().str.upper()
    return out.mask(out == "")


def _rule_mask(df: pd.DataFrame, rule: dict) -> pd.Series:
    """True where the rule's condition holds (values upper-cased in config)."""
    col = _norm(df[rule["column"]])
    op = rule["op"]
    if op == "eq":
        return (col == str(rule["value"]).upper()).fillna(False).astype(bool)
    if op == "in":
        return (
            col.isin([str(v).upper() for v in rule["value"]])
            .fillna(False)
            .astype(bool)
        )
    if op == "is_null":
        return col.isna()
    raise ValueError(f"unknown op {op}")


def derive_file_type(df: pd.DataFrame, cfg: dict) -> pd.Series:
    """Bureau file type per Appendix G, evaluated as at APPROVEDATE.

    If ``config.file_type.source_column`` is set, that column is used
    as-is (normalised).  Otherwise, derive from three bureau inputs:
    THICK first, then NO_FILE, else THIN.
    """
    ft_cfg = cfg["file_type"]
    if ft_cfg.get("source_column"):
        return _norm(df[ft_cfg["source_column"]])
    c = ft_cfg["inputs"]
    oldest = pd.to_numeric(
        df[c["oldest_contract_age_months"]], errors="coerce"
    )
    active = pd.to_numeric(
        df[c["oldest_active_contract_age_months"]], errors="coerce"
    )
    closed = _norm(
        df[c["closed_last_6m_with_contract_age_ge_12m"]]
    ).isin(["1", "Y", "TRUE"])
    thick = (oldest >= 12) & ((active >= 9) | closed)
    no_file = ~thick & (active.isna() | (active < 4))
    return pd.Series(
        np.where(thick, "THICK", np.where(no_file, "NO_FILE", "THIN")),
        index=df.index,
    )


def apply_population_filters(
    df: pd.DataFrame, cfg: dict
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Assign ``sample_status`` / ``exclusion_reason`` and return
    ``(df, waterfall)``.

    Order: application-time rules -> EXCLUDED;
           then performance-related rules -> EXCLUDED_PERF.
    A record is attributed to the **first** rule it fails (spec 2.3).
    """
    target_map = cfg["target_codes"]
    filters = cfg["population_filters"]
    target_col = cfg["columns"]["target"]

    df = df.copy()
    status_from_target = {v: k for k, v in target_map.items()}
    df["sample_status"] = df[target_col].map(status_from_target)
    assert df["sample_status"].notna().all(), (
        f"target has values outside target_codes: "
        f"{set(df[target_col].unique()) - set(target_map.values())}"
    )
    df["exclusion_reason"] = pd.NA
    alive = pd.Series(True, index=df.index)
    rows = [{
        "step": "start",
        "removed": 0,
        "remaining": int(alive.sum()),
        "remaining_good_bad": int(df[target_col].isin([0, 1]).sum()),
        "remaining_bads": int((df[target_col] == 1).sum()),
    }]
    for stage, status in (
        ("application_time", "EXCLUDED"),
        ("performance_related", "EXCLUDED_PERF"),
    ):
        for kind in ("exclude", "include"):
            for rule in filters[stage].get(kind, []):
                hit = _rule_mask(df, rule)
                fail = alive & (hit if kind == "exclude" else ~hit)
                df.loc[fail, "sample_status"] = status
                df.loc[fail, "exclusion_reason"] = rule["name"]
                alive &= ~fail
                kept = df[alive]
                rows.append({
                    "step": f"{stage}:{kind}:{rule['name']}",
                    "removed": int(fail.sum()),
                    "remaining": int(alive.sum()),
                    "remaining_good_bad": int(
                        kept[target_col].isin([0, 1]).sum()
                    ),
                    "remaining_bads": int(
                        (kept[target_col] == 1).sum()
                    ),
                })
    return df, pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Column role assignment  (spec 2.5)
# ---------------------------------------------------------------------------

def assign_column_roles(
    columns: list, cfg: dict
) -> pd.DataFrame:
    """Classify every column by the rules in spec 2.5.

    Returns a DataFrame with columns ``[feature, role, rule]``.
    Any UNASSIGNED column MUST stop the pipeline.
    """
    roles = cfg["column_roles"]
    filters = cfg["population_filters"]

    # Collect FLAG columns from population_filters
    flag_cols: set = set()
    for stage in ("application_time", "performance_related"):
        for kind in ("exclude", "include"):
            for rule in filters[stage].get(kind, []):
                flag_cols.add(rule["column"])
    # Also add file_type source_column if set
    ft_cfg = cfg.get("file_type", {})
    if ft_cfg.get("source_column"):
        flag_cols.add(ft_cfg["source_column"])

    prefixes = tuple(p.lower() for p in roles["feature_prefixes"])
    key_set = set(roles["key"])
    perf_set = set(roles["performance"])
    watch_set = set(roles.get("watch", []))
    override_set = set(roles.get("feature_override", []))

    records = []
    for col in columns:
        if col in key_set:
            records.append({"feature": col, "role": "KEY", "rule": "column_roles.key"})
        elif col in perf_set:
            records.append({"feature": col, "role": "PERFORMANCE", "rule": "column_roles.performance"})
        elif col in flag_cols:
            records.append({"feature": col, "role": "FLAG", "rule": "population_filters"})
        elif col in watch_set and col not in override_set:
            # Watch unless also in feature_override (age exception, TBC-08)
            records.append({"feature": col, "role": "WATCH", "rule": "column_roles.watch"})
        elif col in override_set:
            records.append({"feature": col, "role": "FEATURE", "rule": "column_roles.feature_override"})
        elif col.lower().startswith(prefixes):
            matched = next(p for p in prefixes if col.lower().startswith(p))
            records.append({"feature": col, "role": "FEATURE", "rule": f"prefix:{matched}"})
        else:
            records.append({"feature": col, "role": "UNASSIGNED", "rule": ""})

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Logistic-regression factories (scikit-learn version-aware, App. D note)
# ---------------------------------------------------------------------------

def lr_l1(C: float, max_iter: int = 2000) -> LogisticRegression:
    """L1-penalised liblinear logistic regression (spec 6.6)."""
    if _SK_VER >= (1, 8):
        return LogisticRegression(l1_ratio=1.0, solver="liblinear", C=C, max_iter=max_iter)
    return LogisticRegression(penalty="l1", solver="liblinear", C=C, max_iter=max_iter)


def lr_unpenalised(max_iter: int = 2000, tol: float = 1e-10) -> LogisticRegression:
    """Unregularised logistic regression (spec 7.3: penalty=None; C=np.inf form for sklearn >= 1.8).

    Default *tol* is 1e-10 (tighter than sklearn's 1e-4) so that the MLE matches
    statsmodels Logit to < 1e-4 — the E11 acceptance criterion.
    """
    if _SK_VER >= (1, 8):
        return LogisticRegression(C=np.inf, max_iter=max_iter, tol=tol)
    return LogisticRegression(penalty=None, max_iter=max_iter, tol=tol)


# ---------------------------------------------------------------------------
# Raw-value preparation for Models B and C  (spec 7.4, 7.5)
# ---------------------------------------------------------------------------

def parse_special_codes(val: Any) -> list:
    """Parse the feature-dictionary ``special_codes`` cell into a list.

    Accepts NaN / empty (-> []), a JSON / Python list string such as
    ``"[-1, -999]"``, a ``;``- or ``|``-separated string, or a scalar.
    """
    if val is None:
        return []
    if isinstance(val, (list, tuple)):
        return list(val)
    if isinstance(val, float) and np.isnan(val):
        return []
    s = str(val).strip()
    if s == "" or s.lower() in ("nan", "none", "[]"):
        return []
    try:
        out = json.loads(s)
        return out if isinstance(out, list) else [out]
    except (ValueError, TypeError):
        pass
    parts = [p.strip() for p in s.strip("[]").replace("|", ";").replace(",", ";").split(";") if p.strip()]
    res = []
    for p in parts:
        try:
            res.append(json.loads(p))
        except (ValueError, TypeError):
            res.append(p.strip("'\""))
    return res


def special_indicator_name(feature: str, code: Any) -> str:
    """Name of the special-value indicator column: ``<feature>_is_special_<code>``."""
    return f"{feature}_is_special_{code}"


def prepare_raw(
    df: pd.DataFrame,
    features: list,
    feature_dict: pd.DataFrame,
    categories: Optional[Dict[str, list]] = None,
) -> pd.DataFrame:
    """Raw feature matrix for Models B and C (spec 7.4, 7.5).

    - Numerical features: coerced to float; each special code from the feature
      dictionary is set to NaN and an int indicator ``<feature>_is_special_<code>``
      is added (always created, so the column set is deterministic).
    - Categorical features: kept as pandas ``category`` (missing stays NaN);
      special codes get the same NaN + indicator treatment.  Pass *categories*
      (feature -> list) to fix the category levels when scoring new data.
    Column order: each feature followed by its indicators, in *features* order.
    """
    fd = feature_dict.set_index("feature") if "feature" in feature_dict.columns else feature_dict
    cols: Dict[str, pd.Series] = {}
    for f in features:
        dtype = str(fd.loc[f, "dtype"]).lower() if f in fd.index else "numerical"
        codes = parse_special_codes(fd.loc[f, "special_codes"]) if f in fd.index and "special_codes" in fd.columns else []
        if dtype == "categorical":
            s = df[f].astype("object").where(df[f].notna(), np.nan)
            s = s.map(lambda v: v if (isinstance(v, float) and np.isnan(v)) else str(v).strip())
            code_vals = [str(c) for c in codes]
        else:
            s = pd.to_numeric(df[f], errors="coerce").astype(float)
            code_vals = [float(c) for c in codes]
        inds = {}
        for c, cv in zip(codes, code_vals):
            hit = (s == cv).fillna(False)
            inds[special_indicator_name(f, c)] = hit.astype(int)
            s = s.mask(hit)
        if dtype == "categorical":
            levels = (categories or {}).get(f)
            s = pd.Categorical(s, categories=levels) if levels is not None else pd.Categorical(s)
            s = pd.Series(s, index=df.index)
        cols[f] = s
        cols.update(inds)
    return pd.DataFrame(cols, index=df.index)


def binning_trend(optb) -> str:
    """Risk trend of a fitted OptimalBinning object from its regular bins.

    Returns ``ascending`` (higher value -> higher Bad Rate), ``descending``,
    ``categorical`` or ``non_monotonic`` (peak / valley / other).
    Special and Missing bins are ignored.
    """
    if str(getattr(optb, "dtype", "numerical")) == "categorical":
        return "categorical"
    bt = optb.binning_table.build()
    bt = bt[bt.index != "Totals"]
    reg = bt[~bt["Bin"].astype(str).isin(["Special", "Missing"])]
    er = pd.to_numeric(reg["Event rate"], errors="coerce").dropna().to_numpy()
    if len(er) < 2:
        return "non_monotonic"
    d = np.diff(er)
    if (d >= 0).all() and (d > 0).any():
        return "ascending"
    if (d <= 0).all() and (d < 0).any():
        return "descending"
    return "non_monotonic"


def monotone_vector(
    columns: list,
    features: list,
    binning_objects: Dict[str, Any],
    feature_dict: pd.DataFrame,
) -> List[int]:
    """LightGBM monotone_constraints aligned with *columns* (spec 7.5).

    +1 for an ascending L1 trend, -1 for descending, 0 for peak / valley /
    other, categorical features and special-value indicator columns.
    """
    fd = feature_dict.set_index("feature") if "feature" in feature_dict.columns else feature_dict
    out = []
    for c in columns:
        if c not in features:
            out.append(0)
            continue
        if c in fd.index and str(fd.loc[c, "dtype"]).lower() == "categorical":
            out.append(0)
            continue
        t = binning_trend(binning_objects[c])
        out.append(1 if t == "ascending" else (-1 if t == "descending" else 0))
    return out


# ---------------------------------------------------------------------------
# Tuning stage-2 selection rules  (spec 7.2)
# ---------------------------------------------------------------------------

SIMPLICITY_KEYS = {
    # (parameter, ascending?)  -> smaller num_leaves first, ... larger lambda_l2 first
    "C": [("num_leaves", True), ("max_depth", True), ("min_child_samples", False), ("lambda_l2", False)],
    "B": [("max_bins", True), ("max_leaves", True), ("min_samples_leaf", False)],
}


def shortlist_trials(
    trials: pd.DataFrame,
    cfg: dict,
    mean_col: str = "cv_auc_mean",
    std_col: str = "cv_auc_std",
    param_cols: Optional[list] = None,
) -> Tuple[pd.DataFrame, float]:
    """Stage-2 shortlist: mean >= best mean - keep_within_sd x std(best), top max_candidates by mean.

    If *param_cols* is given, repeated trials of an identical parameter set (possible with
    categorical search spaces) count once: the lowest trial number is kept.
    """
    t = cfg["tuning"]
    best = trials.loc[trials[mean_col].idxmax()]
    thr = float(best[mean_col] - t["keep_within_sd"] * best[std_col])
    sl = trials[trials[mean_col] >= thr].sort_values([mean_col, "trial"], ascending=[False, True])
    if param_cols:
        sl = sl.drop_duplicates(subset=param_cols, keep="first")
    sl = sl.head(t["max_candidates"])
    return sl.reset_index(drop=True), thr


def pick_simplest(tres: pd.DataFrame, model: str, cfg: dict) -> Tuple[int, pd.DataFrame]:
    """Stage-2 choice: highest t_auc_mean, then the simplest set within simplicity_tolerance.

    *tres* needs columns ``trial``, ``t_auc_mean`` and the simplicity parameters.
    Ties after the simplicity keys: higher t_auc_mean, then lower trial number.
    Returns ``(chosen_trial, candidates_within_tolerance)``.
    """
    tol = cfg["tuning"]["simplicity_tolerance"]
    best = float(tres["t_auc_mean"].max())
    near = tres[tres["t_auc_mean"] >= best - tol]
    keys = SIMPLICITY_KEYS[model]
    by = [k for k, _ in keys] + ["t_auc_mean", "trial"]
    asc = [a for _, a in keys] + [False, True]
    near = near.sort_values(by, ascending=asc).reset_index(drop=True)
    return int(near.loc[0, "trial"]), near
