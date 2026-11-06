# -*- coding: utf-8 -*-
"""
Stage 4 - Accuracy of land-cover CHANGE: analysis of the interpreted sample.
Estimators: Olofsson et al. (2014), Remote Sensing of Environment 148:42-57 (stratified random sampling).

INPUT  (in IN_DIR, produced by Stage4_Make_Change_Sample.py):
   Sample_<tag>_for_labelling.csv   <- the file YOU filled in (Ref_From, Ref_To, Confidence)
   Sample_<tag>_KEY_do_not_open.csv  <- stratum of every point (opened only now)
   Strata_<tag>.csv                  <- N of pixels per stratum (weights)
   Rules_Effects.csv                 <- (from,to) -> stratum / effect
OUTPUT (in IN_DIR):
   Result_<tag>_stratum_matrix.csv, Result_<tag>_effect_matrix.csv, Result_<tag>_metrics.csv,
   Result_<tag>_areas.csv, Report_Change_Accuracy.html

Run:  python Stage4_Analyse_Change_Accuracy.py            (set S4_OUT_DIR to the folder, or edit IN_DIR)
Labels: Ref_From / Ref_To = land-cover code 1-8 at date 1 / date 2 as YOU read it on the imagery;
        0 = cannot be interpreted (excluded from the estimates, reported separately).
Effect level uses the STRICT rule effects (D = degradation, I = improvement, S = stable/neutral).
"""
import os, sys, html
import numpy as np
import pandas as pd

IN_DIR = os.environ.get("S4_OUT_DIR", r"C:\Users\User25\Desktop\Claude files\LULC BEST\Validation LCLU\05C_Change_Accuracy")
TAGS = ["1999_2015", "2015_2025"]
PIX_HA = 0.09
MIN_N_WARN = 20          # warn if a class keeps fewer interpretable points than this
MAX_UNCLEAR_WARN = 0.20  # warn if more than 20 % of points are "0 = unclear"
Z = 1.96

STRATA = ["D1_Range_to_Crop", "D2_Range_to_Bare_or_Fallow", "D3_Crop_or_Fallow_to_Bare", "D4_Forest_loss",
          "D5_To_Built", "I1_Bare_to_Range", "I2_Bare_to_Crop_or_Fallow", "I3_To_Forest",
          "S1_Stable", "S2_Other_change"]
EFFECTS = ["D", "I", "S"]
STRATUM_EFFECT = {s: s[0] if s[0] in "DI" else "S" for s in STRATA}   # map effect of a stratum (strict)


# ----------------------------------------------------------------------------- Olofsson estimators
def olofsson(nij, N_i):
    """nij: (q x q) counts, rows = map class (stratum), cols = reference class. N_i: population size per row.
    Returns dict with p (adjusted area proportions), OA, UA, PA and their standard errors."""
    n = np.asarray(nij, float)
    N_i = np.asarray(N_i, float)
    q = n.shape[0]
    n_i = n.sum(1)
    Ntot = N_i.sum()
    W = N_i / Ntot
    with np.errstate(divide="ignore", invalid="ignore"):
        frac = np.where(n_i[:, None] > 0, n / n_i[:, None], 0.0)       # n_ij / n_i
        den = np.where(n_i > 1, n_i - 1, np.nan)                        # n_i - 1
    p = W[:, None] * frac                                               # p_ij
    p_col = p.sum(0)                                                    # p_.j  (reference proportions)
    OA = np.trace(p)
    U = np.diag(frac)
    se_OA = np.sqrt(np.nansum(W**2 * U * (1 - U) / den))
    UA = np.where(n_i > 0, U, np.nan)
    se_UA = np.sqrt(U * (1 - U) / den)
    PA = np.where(p_col > 0, np.diag(p) / np.where(p_col > 0, p_col, 1), np.nan)
    # variance of PA_j (Olofsson 2014, eq. 7)
    N_col = (N_i[:, None] * frac).sum(0)                                # N^_.j
    se_PA = np.full(q, np.nan)
    for j in range(q):
        if not (N_col[j] > 0):
            continue
        t1 = (N_i[j] ** 2) * (1 - PA[j]) ** 2 * U[j] * (1 - U[j]) / den[j] if n_i[j] > 1 else 0.0
        t2 = 0.0
        for i in range(q):
            if i != j and n_i[i] > 1:
                t2 += (N_i[i] ** 2) * frac[i, j] * (1 - frac[i, j]) / den[i]
        t2 *= PA[j] ** 2
        se_PA[j] = np.sqrt((t1 + t2) / N_col[j] ** 2)
    # SE of the reference proportion p_.j
    se_p = np.sqrt(np.nansum((W[:, None] ** 2) * frac * (1 - frac) / den[:, None], axis=0))
    return dict(p=p, p_col=p_col, p_row=p.sum(1), OA=OA, se_OA=se_OA, UA=UA, se_UA=se_UA,
                PA=PA, se_PA=se_PA, se_p=se_p, n_i=n_i, W=W)


def matrix(df, map_col, ref_col, classes):
    ix = {c: k for k, c in enumerate(classes)}
    m = np.zeros((len(classes), len(classes)), int)
    for a, b in zip(df[map_col], df[ref_col]):
        m[ix[a], ix[b]] += 1
    return m


# ----------------------------------------------------------------------------- main per period
def analyse_period(tag, rules):
    lab = pd.read_csv(os.path.join(IN_DIR, "Sample_%s_for_labelling.csv" % tag), encoding="utf-8-sig")
    key = pd.read_csv(os.path.join(IN_DIR, "Sample_%s_KEY_do_not_open.csv" % tag), encoding="utf-8-sig")
    st = pd.read_csv(os.path.join(IN_DIR, "Strata_%s.csv" % tag), encoding="utf-8-sig")
    d = lab[["ID", "Ref_From", "Ref_To", "Confidence"]].merge(key, on="ID", how="left", validate="1:1")
    flags, out = [], {}

    n_all = len(d)
    done = d[(d.Ref_From.between(1, 8)) & (d.Ref_To.between(1, 8))]
    unclear = d[(d.Ref_From == 0) | (d.Ref_To == 0)]
    pending = d[~d.index.isin(done.index) & ~d.index.isin(unclear.index)]
    flags.append(("PASS" if len(pending) == 0 else "FAIL",
                  "Points not yet interpreted (Ref_From/Ref_To outside 0-8): %d of %d" % (len(pending), n_all)))
    flags.append(("PASS" if len(unclear) / n_all <= MAX_UNCLEAR_WARN else "WARN",
                  "Unclear points (code 0): %d (%.1f%%)" % (len(unclear), 100 * len(unclear) / n_all)))
    if len(done) == 0:
        return None, flags, None

    pair = {(int(a), int(b)): (s, e) for a, b, s, e in zip(rules.from_code, rules.to_code, rules.stratum, rules.effect_strict)}
    done = done.copy()
    done["ref_stratum"] = [pair[(int(a), int(b))][0] for a, b in zip(done.Ref_From, done.Ref_To)]
    done["ref_effect"] = [pair[(int(a), int(b))][1] for a, b in zip(done.Ref_From, done.Ref_To)]
    done["map_effect"] = done.stratum.map(STRATUM_EFFECT)
    done["from_ok"] = done.Ref_From == done.map_from
    done["to_ok"] = done.Ref_To == done.map_to
    done["both_ok"] = done.from_ok & done.to_ok

    Nmap = st.set_index("stratum").loc[STRATA, "N_pixels"].values.astype(float)
    Ntot = Nmap.sum()

    # ---- stratum level
    ms = matrix(done, "stratum", "ref_stratum", STRATA)
    rs = olofsson(ms, Nmap)
    # ---- effect level (map effect = sum of strata of that effect)
    Neff = np.array([sum(Nmap[k] for k, s in enumerate(STRATA) if STRATUM_EFFECT[s] == e) for e in EFFECTS])
    # effect-level estimation keeps the sampling strata as the stratification: collapse columns, keep rows by stratum
    # reference effect counts per stratum -> p_{stratum,effect}; then aggregate rows to map-effect classes.
    cols = np.zeros((len(STRATA), 3))
    for k, s in enumerate(STRATA):
        sub = done[done.stratum == s]
        for j, e in enumerate(EFFECTS):
            cols[k, j] = (sub.ref_effect == e).sum()
    re_ = olofsson_effect(cols, Nmap)

    # ---- tables
    sm = pd.DataFrame(ms, index=["map:" + s for s in STRATA], columns=["ref:" + s for s in STRATA])
    sm.insert(0, "n_interpretable", ms.sum(1))
    sm.insert(1, "N_pixels", Nmap.astype(int))
    sm.to_csv(os.path.join(IN_DIR, "Result_%s_stratum_matrix.csv" % tag), encoding="utf-8-sig")

    em = pd.DataFrame(re_["counts"], index=["map:" + e for e in EFFECTS], columns=["ref:" + e for e in EFFECTS])
    em.insert(0, "N_pixels", Neff.astype(int))
    em.to_csv(os.path.join(IN_DIR, "Result_%s_effect_matrix.csv" % tag), encoding="utf-8-sig")

    met = []
    for k, s in enumerate(STRATA):
        sub = done[done.stratum == s]
        met.append(dict(level="stratum", cls=s, n=int(rs["n_i"][k]),
                        UA=rs["UA"][k], UA_se=rs["se_UA"][k], PA=rs["PA"][k], PA_se=rs["se_PA"][k],
                        exact_from_to_ok=float(sub.both_ok.mean()) if len(sub) else np.nan,
                        from_ok=float(sub.from_ok.mean()) if len(sub) else np.nan,
                        to_ok=float(sub.to_ok.mean()) if len(sub) else np.nan))
    for j, e in enumerate(EFFECTS):
        met.append(dict(level="effect", cls=e, n=int(re_["n_i"][j]), UA=re_["UA"][j], UA_se=re_["se_UA"][j],
                        PA=re_["PA"][j], PA_se=re_["se_PA"][j]))
    met.append(dict(level="stratum", cls="OVERALL", n=int(rs["n_i"].sum()), UA=rs["OA"], UA_se=rs["se_OA"]))
    met.append(dict(level="effect", cls="OVERALL", n=int(re_["n_i"].sum()), UA=re_["OA"], UA_se=re_["se_OA"]))
    met = pd.DataFrame(met)
    met.rename(columns={"UA": "UA_or_OA"}, inplace=True)
    met.to_csv(os.path.join(IN_DIR, "Result_%s_metrics.csv" % tag), index=False, encoding="utf-8-sig")

    A_ha = Ntot * PIX_HA
    area = []
    for j, e in enumerate(EFFECTS):
        mapped = Neff[j] / Ntot
        area.append(dict(level="effect", cls=e, mapped_share=mapped, mapped_ha=mapped * A_ha,
                         ref_share=re_["p_col"][j], ref_se=re_["se_p"][j],
                         ref_ha=re_["p_col"][j] * A_ha,
                         ref_ha_lo=max(0, re_["p_col"][j] - Z * re_["se_p"][j]) * A_ha,
                         ref_ha_hi=(re_["p_col"][j] + Z * re_["se_p"][j]) * A_ha))
    for k, s in enumerate(STRATA):
        mapped = Nmap[k] / Ntot
        area.append(dict(level="stratum", cls=s, mapped_share=mapped, mapped_ha=mapped * A_ha,
                         ref_share=rs["p_col"][k], ref_se=rs["se_p"][k], ref_ha=rs["p_col"][k] * A_ha,
                         ref_ha_lo=max(0, rs["p_col"][k] - Z * rs["se_p"][k]) * A_ha,
                         ref_ha_hi=(rs["p_col"][k] + Z * rs["se_p"][k]) * A_ha))
    area = pd.DataFrame(area)
    area.to_csv(os.path.join(IN_DIR, "Result_%s_areas.csv" % tag), index=False, encoding="utf-8-sig")

    low = [STRATA[k] for k in range(len(STRATA)) if rs["n_i"][k] < MIN_N_WARN]
    flags.append(("PASS" if not low else "WARN",
                  "Strata with fewer than %d interpretable points: %s" % (MIN_N_WARN, ", ".join(low) if low else "none")))
    cf = done.Confidence.value_counts().to_dict()
    flags.append(("INFO", "Confidence (1 high - 3 low) counts: %s" % {int(k): int(v) for k, v in sorted(cf.items())}))
    # sensitivity: only confidence 1-2
    hi = done[done.Confidence.isin([1, 2])]
    sens = None
    if len(hi) >= 0.5 * len(done):
        c2 = np.zeros((len(STRATA), 3))
        for k, s in enumerate(STRATA):
            sub = hi[hi.stratum == s]
            for j, e in enumerate(EFFECTS):
                c2[k, j] = (sub.ref_effect == e).sum()
        if (c2.sum(1) > 0).all():
            sens = olofsson_effect(c2, Nmap)
    return dict(tag=tag, met=met, area=area, em=em, sm=sm, re=re_, rs=rs, n=n_all, done=len(done), A_ha=A_ha,
                sens=sens, Neff=Neff, Ntot=Ntot), flags, done


def olofsson_effect(cnt_by_stratum, Nmap):
    """Effect-level estimates when the sampling strata are the 10 strata but the classes are D/I/S.
    cnt_by_stratum: (10 x 3) reference-effect counts per sampled stratum."""
    n = cnt_by_stratum.astype(float)
    n_i = n.sum(1)
    W = Nmap / Nmap.sum()
    with np.errstate(divide="ignore", invalid="ignore"):
        frac = np.where(n_i[:, None] > 0, n / n_i[:, None], 0.0)
        den = np.where(n_i > 1, n_i - 1, np.nan)
    p = W[:, None] * frac                              # p_{stratum, ref effect}
    p_col = p.sum(0)
    se_p = np.sqrt(np.nansum((W[:, None] ** 2) * frac * (1 - frac) / den[:, None], axis=0))
    # map-effect classes = groups of strata
    idx = {e: [k for k, s in enumerate(STRATA) if STRATUM_EFFECT[s] == e] for e in EFFECTS}
    counts = np.zeros((3, 3), int)
    for a, e in enumerate(EFFECTS):
        counts[a] = n[idx[e]].sum(0)
    # map-class probabilities
    Wc = np.array([W[idx[e]].sum() for e in EFFECTS])
    # P(ref = j & map = i) = sum over strata in i of p ; UA_i = that / Wc_i
    pij = np.zeros((3, 3))
    for a, e in enumerate(EFFECTS):
        pij[a] = p[idx[e]].sum(0)
    UA = np.array([pij[a, a] / Wc[a] if Wc[a] > 0 else np.nan for a in range(3)])
    PA = np.array([pij[j, j] / p_col[j] if p_col[j] > 0 else np.nan for j in range(3)])
    OA = np.trace(pij)
    # SE by exact variance of a sum of stratified proportions (strata are the sampling units' groups)
    def se_ratio_free(weights_per_stratum, target):
        # variance of sum_h W_h * w_h * mean_h  with per-stratum indicator
        v = 0.0
        for k in range(len(STRATA)):
            if n_i[k] > 1:
                pk = target[k]
                v += (W[k] * weights_per_stratum[k]) ** 2 * pk * (1 - pk) / (n_i[k] - 1)
        return np.sqrt(v)
    # OA: indicator = reference effect equals the map effect of the stratum
    ind = np.array([frac[k, EFFECTS.index(STRATUM_EFFECT[STRATA[k]])] for k in range(len(STRATA))])
    se_OA = se_ratio_free(np.ones(len(STRATA)), ind)
    se_UA = np.full(3, np.nan)
    for a, e in enumerate(EFFECTS):
        v = 0.0
        for k in idx[e]:
            if n_i[k] > 1:
                v += (W[k] / Wc[a]) ** 2 * frac[k, a] * (1 - frac[k, a]) / (n_i[k] - 1)
        se_UA[a] = np.sqrt(v)
    # PA_j = pij_jj / p_.j : delta method with per-stratum Bernoulli proportions
    se_PA = np.full(3, np.nan)
    for j, e in enumerate(EFFECTS):
        if p_col[j] <= 0:
            continue
        R = PA[j]
        v = 0.0
        for k in range(len(STRATA)):
            if n_i[k] > 1:
                inj = k in idx[e]
                # d(PA)/d(frac_kj) = ((1 if in class j) - R) * W_k / p_.j
                g = ((1.0 if inj else 0.0) - R) * W[k] / p_col[j]
                v += g ** 2 * frac[k, j] * (1 - frac[k, j]) / (n_i[k] - 1)
        se_PA[j] = np.sqrt(v)
    return dict(counts=counts, n_i=counts.sum(1), p_col=p_col, se_p=se_p, UA=UA, se_UA=se_UA, PA=PA, se_PA=se_PA,
                OA=OA, se_OA=se_OA, pij=pij)


# ----------------------------------------------------------------------------- report
def pct(x, d=1):
    return "–" if x is None or (isinstance(x, float) and np.isnan(x)) else "%.*f%%" % (d, 100 * x)


def ha(x):
    return "–" if x is None or (isinstance(x, float) and np.isnan(x)) else "{:,.0f}".format(x)


def build_report(results):
    h = ["<html><head><meta charset='utf-8'><title>Stage 4 - Accuracy of land-cover change</title>",
         "<style>body{font-family:Segoe UI,Arial;margin:30px;max-width:1100px}table{border-collapse:collapse;margin:8px 0}"
         "td,th{border:1px solid #bbb;padding:4px 8px;font-size:13px;text-align:right}th{background:#eee}"
         "td:first-child,th:first-child{text-align:left}.PASS{color:#1a7f37}.WARN{color:#b26a00}.FAIL{color:#b00020}.INFO{color:#555}"
         "</style></head><body><h1>Stage 4 – Accuracy of land-cover change (OEB)</h1>",
         "<p>Estimators: Olofsson et al. (2014). Map classes = sampling strata (defined from the 20 transition rules); "
         "reference = your interpretation of the two dates. Effect level uses strict rule effects (D/I/S). "
         "Points coded 0 (unclear) are excluded.</p>"]
    for tag, (r, flags) in results.items():
        h.append("<h2>Period %s</h2><ul>" % tag.replace("_", " → "))
        for lv, msg in flags:
            h.append("<li class='%s'><b>%s</b> %s</li>" % (lv, lv, html.escape(msg)))
        h.append("</ul>")
        if r is None:
            h.append("<p>No interpretable points yet.</p>")
            continue
        m, a = r["met"], r["area"]
        o = m[(m.level == "effect") & (m.cls == "OVERALL")].iloc[0]
        os_ = m[(m.level == "stratum") & (m.cls == "OVERALL")].iloc[0]
        h.append("<p>Overall accuracy – effect level (D/I/S): <b>%s ± %s</b> &nbsp; | &nbsp; stratum level (10 classes): <b>%s ± %s</b> "
                 "(± = 95%% CI half-width; n = %d interpretable of %d)</p>" %
                 (pct(o.UA_or_OA), pct(Z * o.UA_se), pct(os_.UA_or_OA), pct(Z * os_.UA_se), r["done"], r["n"]))
        h.append("<h3>Area of degradation / improvement: mapped vs reference-corrected</h3><table><tr><th>Effect</th><th>Mapped (ha)</th>"
                 "<th>Mapped share</th><th>Corrected share (95% CI)</th><th>Corrected area ha (95% CI)</th></tr>")
        for _, x in a[a.level == "effect"].iterrows():
            h.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s (%s – %s)</td><td>%s (%s – %s)</td></tr>" % (
                x.cls, ha(x.mapped_ha), pct(x.mapped_share, 2), pct(x.ref_share, 2),
                pct(max(0, x.ref_share - Z * x.ref_se), 2), pct(x.ref_share + Z * x.ref_se, 2),
                ha(x.ref_ha), ha(x.ref_ha_lo), ha(x.ref_ha_hi)))
        h.append("</table><h3>User's / producer's accuracy by class</h3><table><tr><th>Level</th><th>Class</th><th>n</th>"
                 "<th>UA (±95%)</th><th>PA (±95%)</th><th>From&amp;To exactly right</th></tr>")
        for _, x in m[m.cls != "OVERALL"].iterrows():
            h.append("<tr><td>%s</td><td>%s</td><td>%d</td><td>%s ± %s</td><td>%s ± %s</td><td>%s</td></tr>" % (
                x.level, x.cls, x.n, pct(x.UA_or_OA), pct(Z * x.UA_se) if not np.isnan(x.UA_se) else "–",
                pct(x.PA), pct(Z * x.PA_se) if not np.isnan(x.PA_se) else "–",
                pct(x.exact_from_to_ok) if "exact_from_to_ok" in x and not pd.isna(x.exact_from_to_ok) else "–"))
        h.append("</table><h3>Effect-level error matrix (counts; rows = map)</h3>" + r["em"].to_html())
        if r["sens"] is not None:
            s = r["sens"]
            h.append("<p>Sensitivity (confidence 1–2 only): OA = %s; corrected D share = %s (map: %s)</p>" %
                     (pct(s["OA"]), pct(s["p_col"][0], 2), pct(r["Neff"][0] / r["Ntot"], 2)))
    h.append("<p><i>Interpretation guide: if UA(D) is low, the mapped degradation contains many false alarms "
             "(commission); if PA(D) is low, true degradation is missed (omission). The corrected share with its CI "
             "is the figure to report for the area of land-cover-driven degradation.</i></p></body></html>")
    open(os.path.join(IN_DIR, "Report_Change_Accuracy.html"), "w", encoding="utf-8").write("\n".join(h))


def main():
    rules = pd.read_csv(os.path.join(IN_DIR, "Rules_Effects.csv"), encoding="utf-8-sig")
    results = {}
    for tag in TAGS:
        r, flags, _ = analyse_period(tag, rules)
        results[tag] = (r, flags)
        print(tag)
        for lv, msg in flags:
            print("  [%s] %s" % (lv, msg))
        if r:
            m = r["met"]
            print(m.to_string(index=False, float_format=lambda v: "%.3f" % v))
    build_report(results)
    print("Report:", os.path.join(IN_DIR, "Report_Change_Accuracy.html"))


if __name__ == "__main__":
    main()
