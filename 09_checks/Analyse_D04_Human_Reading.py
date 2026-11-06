# -*- coding: utf-8 -*-
"""
Analysis of the blind D04 visual reading by HUMAN readers only (no AI reader).

Run from the folder that contains the files below (or edit the paths in CONFIG):
  READER1   filled D04_Blind_Points_for_readers.csv of reader 1 (column Verdict_Reader)
  READER2   filled D04_Blind_Points_for_readers.csv of reader 2 (column Verdict_Reader)
  THIRD     (step 2) CSV with columns BlindID,Verdict from the third blind reader, only for disputed points
  KEY       D04_KEY_do_not_open_until_done.csv (BlindID, Stratum)  -> open ONLY after both readers finished
  DESIGN    Verification_Design.csv (stratum;area_ha;n_points)

Step 1: python Analyse_D04_Human_Reading.py        -> agreement statistics + D04_disputes_for_third_reader.csv (IDs only, shuffled)
Step 2: put the third reader's file next to it, run again -> final labels, visible share per stratum and for D04.

Verdict values accepted: Degraded / NotDeg / Unclear  (also D / N / U, any case). Empty = missing.
Rules: agreement -> that label; disagreement -> third reader; Unclear or missing = NOT degraded in the lower bound
and DEGRADED in the upper bound.
"""
import csv, os, sys, random, math
from collections import Counter, defaultdict

CONFIG = dict(READER1="Reader1_D04.csv", READER2="Reader2_D04.csv", THIRD="Third_reader_D04.csv",
              KEY="D04_KEY_do_not_open_until_done.csv", DESIGN="Verification_Design.csv", SEED=2026)
DEG_STRATA = ["PERS_LC_only", "PERS_PROD_only", "PERS_SOC_only", "PERS_MULTI",
              "NEW_LC_only", "NEW_PROD_only", "NEW_SOC_only", "NEW_MULTI"]
CTRL_STRATA = ["RECOVERED", "STABLE", "IMPROVED"]

def norm(v):
    v = (v or "").strip().lower()
    if v in ("degraded", "d"): return "D"
    if v in ("notdeg", "not deg", "n", "notdegraded"): return "N"
    if v in ("unclear", "u"): return "U"
    return ""   # missing

def read_csv(path, sep=None):
    with open(path, encoding="utf-8-sig", newline="") as f:
        txt = f.read()
    if sep is None: sep = ";" if txt.split("\n")[0].count(";") > txt.split("\n")[0].count(",") else ","
    return list(csv.DictReader(txt.splitlines(), delimiter=sep))

def kappa(pairs, cats):
    n = len(pairs)
    if n == 0: return float("nan")
    po = sum(a == b for a, b in pairs) / n
    pe = sum((sum(a == c for a, _ in pairs) / n) * (sum(b == c for _, b in pairs) / n) for c in cats)
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")

def wilson(k, n, z=1.96):
    if n == 0: return (float("nan"), float("nan"))
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0, c - h), min(1, c + h))

def main():
    C = CONFIG
    r1 = {int(r["BlindID"]): norm(r["Verdict_Reader"]) for r in read_csv(C["READER1"])}
    r2 = {int(r["BlindID"]): norm(r["Verdict_Reader"]) for r in read_csv(C["READER2"])}
    conf1 = {int(r["BlindID"]): (r.get("Conf") or "").strip().upper() for r in read_csv(C["READER1"])}
    conf2 = {int(r["BlindID"]): (r.get("Conf") or "").strip().upper() for r in read_csv(C["READER2"])}
    ids = sorted(set(r1) & set(r2))
    both = [i for i in ids if r1[i] and r2[i]]
    print(f"Points: reader 1 = {sum(1 for i in r1 if r1[i])}, reader 2 = {sum(1 for i in r2 if r2[i])}, read by both = {len(both)}")
    # --- agreement
    p3 = [(r1[i], r2[i]) for i in both]
    pb = [("D" if a == "D" else "N", "D" if b == "D" else "N") for a, b in p3]
    bd = sum(a == "D" and b == "D" for a, b in pb); a_only = sum(a == "D" and b == "N" for a, b in pb)
    b_only = sum(a == "N" and b == "D" for a, b in pb); nn = sum(a == "N" and b == "N" for a, b in pb)
    po = (bd + nn) / len(pb)
    print("\nAGREEMENT (readers 1 and 2)")
    print(f"  both degraded / R1 only / R2 only / neither: {bd} / {a_only} / {b_only} / {nn}")
    print(f"  raw agreement (degraded vs not; unclear = not): {po*100:.1f}%")
    print(f"  kappa three categories: {kappa(p3, ['D','N','U']):.2f};  two categories: {kappa(pb, ['D','N']):.2f}")
    print(f"  prevalence-adjusted kappa (PABAK): {2*po-1:.2f};  positive agreement: {2*bd/(2*bd+a_only+b_only)*100 if (2*bd+a_only+b_only) else float('nan'):.0f}%")
    hh = [(r1[i], r2[i]) for i in both if conf1.get(i) == "H" and conf2.get(i) == "H"]
    if hh:
        hb = [("D" if a == "D" else "N", "D" if b == "D" else "N") for a, b in hh]
        print(f"  both readings high confidence: n = {len(hh)}, kappa (2 cat.) = {kappa(hb, ['D','N']):.2f}")
    # --- disputes
    disputes = [i for i in both if ("D" if r1[i] == "D" else "N") != ("D" if r2[i] == "D" else "N")]
    missing_one = [i for i in ids if (r1[i] == "") != (r2[i] == "")]
    disputes = sorted(set(disputes) | set(missing_one))
    random.Random(C["SEED"]).shuffle(disputes)
    with open("D04_disputes_for_third_reader.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(["BlindID", "Verdict_Third", "ChangeType", "Conf", "Notes"])
        for i in disputes: w.writerow([i, "", "", "", ""])
    print(f"\nDisputed or half-missing points: {len(disputes)} -> D04_disputes_for_third_reader.csv (IDs in random order, no hints)")
    if not os.path.exists(C["THIRD"]):
        print("Step 2: give the file to the third reader, save his verdicts as", C["THIRD"], "and run again."); return
    # --- final labels
    t = {int(r["BlindID"]): norm(r.get("Verdict_Third") or r.get("Verdict")) for r in read_csv(C["THIRD"])}
    final = {}
    for i in ids:
        a, b = r1[i], r2[i]
        if i in disputes: final[i] = t.get(i, "")
        else: final[i] = a   # agreement (both D, both N, both U)
    agree3 = Counter()
    for i in disputes:
        v = t.get(i, "")
        agree3["R1" if v == r1[i] and v else "R2" if v == r2[i] and v else "neither"] += 1
    print("Third reader sided with:", dict(agree3))
    # --- strata
    key = {int(r["BlindID"]): r["Stratum"] for r in read_csv(C["KEY"])}
    design = {r["stratum"]: float(r["area_ha"]) for r in read_csv(C["DESIGN"], ";")}
    res = {}
    for s in DEG_STRATA + CTRL_STRATA:
        pts = [i for i in final if key.get(i) == s]
        n = len(pts); k = sum(final[i] == "D" for i in pts); u = sum(final[i] in ("D", "U", "") for i in pts)
        res[s] = dict(n=n, k=k, u=u)
    print("\nVISIBLE DEGRADATION BY STRATUM (final labels)")
    print(f"{'stratum':16s}{'n':>4s}{'degraded':>10s}{'share':>8s}{'Wilson 95%':>16s}{'upper':>8s}")
    for s in DEG_STRATA + CTRL_STRATA:
        r = res[s]
        if r["n"]:
            lo, hi = wilson(r["k"], r["n"]); print(f"{s:16s}{r['n']:4d}{r['k']:10d}{r['k']/r['n']*100:7.1f}%{lo*100:8.0f}-{hi*100:.0f}%{r['u']/r['n']*100:7.1f}%")
    A = sum(design[s] for s in DEG_STRATA)
    est = sum(design[s] / A * res[s]["k"] / res[s]["n"] for s in DEG_STRATA if res[s]["n"])
    ub = sum(design[s] / A * res[s]["u"] / res[s]["n"] for s in DEG_STRATA if res[s]["n"])
    var = sum((design[s] / A) ** 2 * (res[s]["k"] / res[s]["n"]) * (1 - res[s]["k"] / res[s]["n"]) / (res[s]["n"] - 1) for s in DEG_STRATA if res[s]["n"] > 1)
    se = math.sqrt(var)
    print(f"\nD04 mapped degraded area = {A:,.0f} ha")
    print(f"VISIBLE DEGRADATION (lower bound): {est*100:.1f}%  (95% interval {max(0,est-1.96*se)*100:.1f}-{(est+1.96*se)*100:.1f}%),  upper bound {ub*100:.1f}%,  = {est*A:,.0f} ha")
    kc = sum(res[s]["k"] for s in CTRL_STRATA); nc = sum(res[s]["n"] for s in CTRL_STRATA)
    if nc: lo, hi = wilson(kc, nc); print(f"Control strata with visible degradation: {kc}/{nc} = {kc/nc*100:.1f}% (Wilson {lo*100:.1f}-{hi*100:.1f}%)")
    with open("D04_human_reading_results.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(["stratum", "n", "degraded_final", "share", "wilson_lo", "wilson_hi", "upper_bound_share", "area_ha"])
        for s in DEG_STRATA + CTRL_STRATA:
            r = res[s]
            if r["n"]:
                lo, hi = wilson(r["k"], r["n"]); w.writerow([s, r["n"], r["k"], round(r["k"]/r["n"], 4), round(lo, 4), round(hi, 4), round(r["u"]/r["n"], 4), design.get(s, "")])
        w.writerow(["D04_TOTAL_degraded_map", sum(res[s]["n"] for s in DEG_STRATA), sum(res[s]["k"] for s in DEG_STRATA), round(est, 4), round(max(0, est-1.96*se), 4), round(est+1.96*se, 4), round(ub, 4), round(A, 1)])
    print("Saved: D04_human_reading_results.csv")

if __name__ == "__main__":
    main()
