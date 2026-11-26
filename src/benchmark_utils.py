"""Shared loading, scoring and benchmark code for the cut-off analysis (s06b) and the benchmark report (s05c).

Moved verbatim from src/s06b_cutoff_analysis (cells Setup, 'Verify the locked registries ...', 'Load approved applicants ...',
'Benchmarks ...', 'Helpers and Step 1'). Only change: values the notebook took from globals (cfg, models, feature dict,
spark session, seeds, paths) are explicit parameters. No definition changed. READ ONLY: nothing here writes a file or table.
"""
import os, re, json, pickle, hashlib

import numpy as np
import pandas as pd
import lightgbm as lgb
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score

import common

# Benchmarks (spec 8.3): config.cutoff_analysis.compare_with = list of {name, column, higher_is_lower_risk, role[, table, source_table, join_key, definition]}
BENCH_DESC = {"A_SCORE": "current decision score",
              "AECB_SCORE": "bureau score, reference only (pre-upgrade version in OOT; not a model input)"}
ASCORE_OFFSETS = [0, 1]                 # owner 2026-11-18: same score-month rule as the FTS run (table entries with a score date)
FTS_FLAG_NAME = "FTS_Ref_No"            # has_fts_data = flag column non-null and non-empty after trim (segment only)


# ---------------------------------------------------------------- files
def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(p):
    with open(p) as fh:
        return json.load(fh)


def tree_snapshot(root, exclude_dirs=(), exclude_files=()):
    """(size, mtime) of every file under a model folder, excluding the given output folders and files."""
    snap = {}
    ex_dirs = [os.path.abspath(d) for d in exclude_dirs]
    ex_files = {os.path.abspath(f) for f in exclude_files}
    for dp, _, fn in os.walk(root):
        a = os.path.abspath(dp)
        if any(a == d or a.startswith(d + os.sep) for d in ex_dirs):
            continue
        for f in fn:
            p = os.path.join(dp, f)
            if os.path.abspath(p) in ex_files:
                continue
            st = os.stat(p)
            snap[p] = (st.st_size, st.st_mtime)
    return snap


def table_version(spark, t):
    return int(spark.sql(f"DESCRIBE HISTORY {t} LIMIT 1").first()["version"])


# ---------------------------------------------------------------- (a) registries and models
def load_registry(reg_path, label, models):
    """Verify a locked registry (sign-off, every file hash, Platt file hash) and load Models A and C. Read-only."""
    assert os.path.exists(reg_path), f"ABORT: {label} registry not found: {reg_path}"
    reg = read_json(reg_path)
    assert reg.get("locked") is True, f"ABORT: {label} registry is not locked"
    for k in ("decision_rules_signed_by", "signed_date"):
        assert str(reg.get("signoff", {}).get(k) or "").strip(), f"ABORT: {label} sign-off field {k} is empty"
    files = {k: v["path"] for k, v in reg["files"].items()}
    locked_sha = {k: v["sha256"] for k, v in reg["files"].items()}
    bad = [k for k, p in files.items() if not os.path.exists(p) or sha256_file(p) != locked_sha[k]]
    assert not bad, f"ABORT: {label}: {len(bad)} locked model/binning/fold/OOF file(s) changed since the lock: {bad}"
    need = ["models/A/binning_process.pkl", "models/A/lr_sklearn.pkl", "models/C/lgbm.txt", "models/model_spec.json", "oof_predictions.parquet"]
    assert not [k for k in need if k not in files], f"ABORT: {label} registry lacks {[k for k in need if k not in files]}"
    cal_ref = reg["oot_evaluation"]["calibration_file"]
    platt_sha = sha256_file(cal_ref["path"])
    assert platt_sha == cal_ref["sha256"], f"ABORT: {label} Platt calibration file differs from the hash in the registry"
    doc = read_json(cal_ref["path"])
    assert str(doc["registry_version"]) == str(reg["version"]) and doc["method"] == "platt" and doc["fit_on"] == "dev_oof", \
        f"ABORT: {label} Platt file is not the DEV-OOF Platt fit of this version"
    assert doc["oof_sha256"] == locked_sha["oof_predictions.parquet"], f"ABORT: {label} Platt fit on a different OOF file"
    spec = read_json(files["models/model_spec.json"])
    R = {"label": label, "path": reg_path, "reg": reg, "version": str(reg["version"]), "reg_sha": sha256_file(reg_path),
         "files": files, "locked_sha": locked_sha, "cal_ref": cal_ref, "platt_path": cal_ref["path"], "platt_sha": platt_sha,
         "platt": {m: doc["params"][m] for m in models},
         "A_FEATS": reg["features"]["A"], "POOL": reg["features"]["BC_pool"], "BC_COLS": reg["features"]["BC_columns"],
         "WOE_KW": spec["A"]["woe_transform"],
         "A_BP": pickle.load(open(files["models/A/binning_process.pkl"], "rb")),
         "A_LR": pickle.load(open(files["models/A/lr_sklearn.pkl"], "rb")),
         "C_BST": lgb.Booster(model_file=files["models/C/lgbm.txt"])}
    assert R["C_BST"].num_trees() == reg["lightgbm_rounds"]["final_rounds"], f"ABORT: {label} LightGBM trees != locked final rounds"
    R["FEATS"] = list(dict.fromkeys(R["A_FEATS"] + R["POOL"]))
    return R


# ---------------------------------------------------------------- (c) benchmark settings
def parse_benchmarks(ca, models):
    """config.cutoff_analysis.compare_with -> list of benchmark dicts (key, desc added), keys, key -> name."""
    benches = []
    for e in ca.get("compare_with") or []:
        assert {"name", "column", "higher_is_lower_risk"} <= set(e), f"compare_with entry needs name, column, higher_is_lower_risk: {e}"
        if e.get("table"):
            assert str(e.get("join_key")) == "app_id", f"{e['name']}: join_key must be app_id"
        k = re.sub(r"\W", "_", str(e["name"])).upper()
        assert k not in models and not k.startswith("FTS_")
        benches.append({**e, "key": k, "desc": BENCH_DESC.get(k, str(e.get("role", "")))})
    return benches, [b["key"] for b in benches], {b["key"]: str(b["name"]) for b in benches}


# ---------------------------------------------------------------- (d) approved applicants and windows
def load_master(spark, master_tbl, id_col, date_col, decision_col, watch, segments, benches, feats, fts_flag_name=FTS_FLAG_NAME):
    """Read the needed acard_master columns (read-only), add app_id / app_id_source / has_fts_data.
    Sets b['_master_col'] on benchmark entries without a table (column of acard_master)."""
    m_cols = spark.table(master_tbl).columns
    _lc = {c.lower(): c for c in m_cols}
    watch_cols = [w for w in watch if w in m_cols]
    seg_available = [c for c in segments if c in m_cols]
    seg_missing = [c for c in segments if c not in m_cols]
    fts_flag_col = _lc.get(fts_flag_name.lower())
    assert fts_flag_col, f"FTS flag column {fts_flag_name} not found (case-insensitive) in {master_tbl}"
    for b in benches:                                    # benchmark columns read from acard_master (entries without a table)
        if not b.get("table"):
            b["_master_col"] = _lc.get(str(b["column"]).lower())
            assert b["_master_col"], f"benchmark column {b['column']} not found (case-insensitive) in {master_tbl}"
    all_feats = list(dict.fromkeys(feats))
    assert not [f for f in all_feats if f not in m_cols], "model features missing in master"
    keep = list(dict.fromkeys([id_col, "CREDITCARDNO", date_col, decision_col, "window", "sample_status", fts_flag_col] + watch_cols + seg_available
                              + [b["_master_col"] for b in benches if b.get("_master_col")] + all_feats))
    master = spark.table(master_tbl).select(*keep).toPandas()
    status_counts = master.groupby(["window", "sample_status"]).size().unstack(fill_value=0).reset_index()

    # app_id (benchmark join key), same rule as s00_build_a_score_snapshot: CRNNO (as stored), or CREDITCARDNO where the
    # normalised CRNNO (string, trim, strip '.0', strip leading zeros) is repeated in acard_master
    def _nk(s):
        o = s.astype("string").str.strip().str.replace(r"\.0$", "", regex=True).str.lstrip("0")
        return o.mask(o == "", pd.NA)
    _crn = _nk(master[id_col])
    _dup = (_crn.notna() & _crn.duplicated(keep=False)).to_numpy()
    _card = master["CREDITCARDNO"].astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    master["app_id"] = master[id_col].astype("string").str.strip().where(~_dup, _card).astype(str)
    master["app_id_source"] = np.where(_dup, "CREDITCARDNO (CRNNO repeated)", "CRNNO")
    assert master["app_id"].notna().all() and master["app_id"].is_unique, "app_id rule does not give one row per application"
    _f = master[fts_flag_col].astype("string").str.strip()
    master["has_fts_data"] = np.where(_f.notna() & (_f != ""), "Y", "N")          # segment only, never a feature
    return {"master": master, "m_cols": m_cols, "WATCH_COLS": watch_cols, "SEG_AVAILABLE": seg_available,
            "SEG_MISSING": seg_missing, "FTS_FLAG_COL": fts_flag_col, "ALL_FEATS": all_feats, "STATUS_COUNTS": status_counts}


def scope(master, name, cfg, reg_path, base_statuses, date_col, decision_col):
    """One window via common.load_window (OOT read lock); approval base = approval_base_statuses (EXCLUDED left out)."""
    df = common.load_window(master, name, cfg, registry_path=reg_path)
    df = df[df["sample_status"].isin(base_statuses)].reset_index(drop=True)
    d, a = pd.to_datetime(df[date_col]), pd.to_datetime(df[decision_col])
    df["app_month"] = d.dt.to_period("M").astype(str)
    df["approve_month"] = a.dt.to_period("M").astype(str)
    df["gap_days"] = (a - d).dt.days
    return df


def add_oot_split(oot, splits, date_col):
    """oot_split = config.oot_report_splits quarter of the application date (in place)."""
    _d = pd.to_datetime(oot[date_col])
    oot["oot_split"] = None
    for q, (s, e) in splits.items():
        oot.loc[(_d >= s) & (_d < e), "oot_split"] = q
    assert oot["oot_split"].notna().all(), "OOT rows outside config.oot_report_splits"
    return oot


# ---------------------------------------------------------------- (b) E13 scoring
def score_e13(df, R, cfg, fdict, models, prefix=""):
    """E13 scoring (s05_oot 'Score with the locked models'): raw PD -> Platt (DEV OOF) -> common score scaling."""
    XA = df[R["A_FEATS"]].apply(pd.to_numeric, errors="coerce")
    raw = {"A": R["A_LR"].predict_proba(np.asarray(R["A_BP"].transform(XA, metric="woe", **R["WOE_KW"]), dtype=float))[:, 1]}
    XR = common.prepare_raw(df, R["POOL"], fdict)
    assert list(XR.columns) == R["BC_COLS"], f"{R['label']}: prepare_raw columns differ from the locked B/C columns"
    raw["C"] = R["C_BST"].predict(XR)
    for m in models:
        cal = common.apply_platt(raw[m], R["platt"][m])
        assert np.isfinite(cal).all() and ((cal > 0) & (cal < 1)).all(), f"{R['label']} {m}: PD outside (0, 1)"
        df[f"raw_{prefix}{m}"], df[f"pd_{prefix}{m}"], df[f"score_{prefix}{m}"] = raw[m], cal, common.pd_to_score(cal, cfg)
    return df


def spot_check(spark, oot, R, prefix, stored, models, seed):
    """OOT scores reproduce the stored E13 scores of the same registry (1,000 rows, keyed on CREDITCARDNO)."""
    st = spark.table(stored).select("CREDITCARDNO", *[f"prob_{m}_cal" for m in models], *[f"score_{m}" for m in models]).toPandas()
    st["CREDITCARDNO"] = st["CREDITCARDNO"].astype(str)
    st = st[~st["CREDITCARDNO"].duplicated(keep=False)].set_index("CREDITCARDNO")
    card = oot["CREDITCARDNO"].astype(str)
    cand = sorted(set(card[~card.duplicated(keep=False)]) & set(st.index))
    spot = set(np.random.default_rng(seed).choice(cand, size=min(1000, len(cand)), replace=False))
    sel = np.where(card.isin(spot).to_numpy())[0]
    out = []
    for m in models:
        s_ = st.loc[card.iloc[sel]]
        out.append({"registry": R["label"], "version": R["version"], "model": m, "stored_table": stored, "n": len(sel),
                    "max_abs_pd_diff": float(np.abs(oot[f"pd_{prefix}{m}"].to_numpy()[sel] - s_[f"prob_{m}_cal"].to_numpy()).max()),
                    "n_score_diff": int((oot[f"score_{prefix}{m}"].to_numpy()[sel] != s_[f"score_{m}"].to_numpy()).sum())})
    return out


# ---------------------------------------------------------------- (c) benchmark data
def attach_benchmarks(spark, benches, windows, labelled, base_statuses, date_col, master_tbl, ascore_offsets=ASCORE_OFFSETS):
    """Add score_/has_/pd_/bench_month_offset_<KEY> to every window DataFrame (in place) and return the coverage, timing,
    direction and source tables. windows: list of (name, DataFrame); the direction check uses the window named OOT.
    Table entries: read-only from the benchmark table, joined on app_id, one row per app_id asserted (never the source table,
    never load_a_score). Entries without a table: column of acard_master. Column names resolved case-insensitively;
    score oriented so that higher = lower risk (approve if score >= cut-off). Comparisons only where the benchmark is non-missing."""
    OOT = dict(windows)["OOT"]
    BENCH_COV, BENCH_TIMING, BENCH_DIR, BENCH_DIR_SUMM, BENCH_SRC, BENCH_UNIQUE = [], [], [], [], [], {}
    for b in benches:
        k, nm = b["key"], b["name"]
        sign = 1.0 if b["higher_is_lower_risk"] else -1.0
        if b.get("table"):
            bt = spark.table(b["table"])
            cmap = {c.lower(): c for c in bt.columns}
            col, jk = cmap.get(str(b["column"]).lower()), cmap.get(str(b["join_key"]).lower())
            dcol = cmap.get(str(b.get("date_column", "score_date")).lower())
            assert col and jk, f"{nm}: column {b['column']} / join key {b['join_key']} not in {b['table']}"
            bpd = bt.select(jk, col, *([dcol] if dcol else [])).toPandas()
            bpd[jk] = bpd[jk].astype(str).str.strip()
            BENCH_UNIQUE[k] = bool(bpd[jk].is_unique)
            assert BENCH_UNIQUE[k], f"{b['table']}: more than one row per {jk}"
            bpd = bpd.rename(columns={jk: "app_id", col: "_bscore", **({dcol: "_bdate"} if dcol else {})})
            offsets = ascore_offsets if dcol else None
            src = {"benchmark": nm, "description": b["desc"], "table": b["table"], "source_table": b.get("source_table"), "column": col,
                   "join_key": jk, "date_column": dcol, "score_month_offsets_used": offsets, "definition": b.get("definition"),
                   "higher_is_lower_risk": b["higher_is_lower_risk"], "rows_in_table": len(bpd), "one_row_per_join_key": BENCH_UNIQUE[k]}
        else:
            offsets = None
            src = {"benchmark": nm, "description": b["desc"], "table": master_tbl, "source_table": b.get("source_table"), "column": b["_master_col"],
                   "join_key": "(same row)", "date_column": None, "score_month_offsets_used": None, "definition": b.get("definition"),
                   "higher_is_lower_risk": b["higher_is_lower_risk"], "rows_in_table": None, "one_row_per_join_key": None}
        BENCH_SRC.append(src)
        for w, df in windows:
            if b.get("table"):
                mg = df[["app_id"]].merge(bpd, on="app_id", how="left", validate="m:1")
                assert len(mg) == len(df) and (mg["app_id"].to_numpy() == df["app_id"].to_numpy()).all(), f"{w}: benchmark merge changed rows"
                raw = pd.to_numeric(mg["_bscore"], errors="coerce")
                if offsets is not None:
                    gap = (pd.to_datetime(mg["_bdate"]).dt.to_period("M") - pd.to_datetime(df[date_col]).dt.to_period("M")).map(
                        lambda x: x.n if pd.notna(x) else np.nan)
                else:
                    gap = pd.Series(np.nan, index=df.index)
            else:
                raw = pd.to_numeric(df[b["_master_col"]], errors="coerce")
                gap = pd.Series(np.nan, index=df.index)
            joined = raw.notna().to_numpy()
            use = joined & (gap.isin(offsets).to_numpy() if offsets is not None else True)
            df[f"score_{k}"] = np.where(use, sign * raw.to_numpy(), np.nan)
            df[f"has_{k}"], df[f"pd_{k}"], df[f"bench_month_offset_{k}"] = use, np.nan, gap.to_numpy()
            stt = df["sample_status"].to_numpy()
            gb, bd = np.isin(stt, labelled), stt == "BAD"
            BENCH_COV.append({"benchmark": nm, "window": w, "approval_base_n": len(df), "joined": int(joined.sum()),
                              "joined_but_outside_score_months": int((joined & ~use).sum()), "used": int(use.sum()),
                              "coverage_approval_base": use.mean(), "good_bad_n": int(gb.sum()), "good_bad_used": int((use & gb).sum()),
                              "coverage_good_bad": (use & gb).sum() / gb.sum() if gb.any() else np.nan,
                              "bads_n": int(bd.sum()), "bads_used": int((use & bd).sum()),
                              **{f"coverage_{s}": use[stt == s].mean() if (stt == s).any() else np.nan for s in base_statuses}})
            if offsets is not None:
                vc = gap[joined].value_counts().sort_index()
                BENCH_TIMING += [{"benchmark": nm, "window": w, "months_score_date_minus_application": int(kk), "n": int(v), "used": int(kk) in offsets}
                                 for kk, v in vc.items()]
        # Direction check on OOT GOOD/BAD with the benchmark: bad rate by benchmark decile (1 = lowest oriented score = highest risk)
        d = OOT[OOT["sample_status"].isin(labelled) & OOT[f"has_{k}"]].copy()
        d["y"] = (d["sample_status"] == "BAD").astype(int)
        d["decile"] = pd.qcut(d[f"score_{k}"].rank(method="first"), 10, labels=False) + 1
        t = d.groupby("decile").agg(n=("y", "size"), bads=("y", "sum"), score_min=(f"score_{k}", "min"), score_max=(f"score_{k}", "max")).reset_index()
        t["bad_rate"] = t["bads"] / t["n"]
        BENCH_DIR.append(t.assign(benchmark=nm))
        auc = roc_auc_score(d["y"], -d[f"score_{k}"])
        rho = spearmanr(t["decile"], t["bad_rate"]).correlation
        BENCH_DIR_SUMM.append({"benchmark": nm, "n_good_bad": len(d), "bads": int(d["y"].sum()), "auc_oriented": auc, "gini": 2 * auc - 1,
                               "spearman_decile_vs_bad_rate": rho, "direction_ok (bad rate falls as score rises)": bool(rho < 0 and auc > 0.5)})
    BENCH_COV, BENCH_TIMING, BENCH_SRC = pd.DataFrame(BENCH_COV), pd.DataFrame(BENCH_TIMING), pd.DataFrame(BENCH_SRC)
    BENCH_DIR = pd.concat(BENCH_DIR, ignore_index=True) if BENCH_DIR else pd.DataFrame()
    BENCH_DIR_SUMM = pd.DataFrame(BENCH_DIR_SUMM)
    assert BENCH_DIR_SUMM.empty or BENCH_DIR_SUMM.iloc[:, -1].all(), "benchmark direction check failed: check higher_is_lower_risk"
    return {"BENCH_COV": BENCH_COV, "BENCH_TIMING": BENCH_TIMING, "BENCH_DIR": BENCH_DIR, "BENCH_DIR_SUMM": BENCH_DIR_SUMM,
            "BENCH_SRC": BENCH_SRC, "BENCH_UNIQUE": BENCH_UNIQUE}


# ---------------------------------------------------------------- bootstrap
def boot_idx(bad_gb, key, boot):
    """Stratified (GOOD/BAD) bootstrap indices over the GOOD+BAD rows; seed = config.selection.bootstrap.seed + fixed key."""
    rng = np.random.default_rng([boot["seed"], key])
    ib, ig = np.where(bad_gb)[0], np.where(~bad_gb)[0]
    if not boot.get("stratified", True):
        return rng.choice(len(bad_gb), (boot["n"], len(bad_gb))).astype(np.int32)
    return np.concatenate([rng.choice(ib, (boot["n"], len(ib))), rng.choice(ig, (boot["n"], len(ig)))], axis=1).astype(np.int32)
