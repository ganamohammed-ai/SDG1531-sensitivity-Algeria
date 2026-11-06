# -*- coding: utf-8 -*-
r"""
SAIDA : REPRISE DES CONTROLES AVEC LE CHIRPS UNIQUE (total mensuel valide)   |   QGIS / PyQGIS, script autonome (numpy + GDAL seulement)
1) Tests par blocs (CHIRPS lu dans 02_Rain\Regional_Monthly_Rain_SAIDA.csv, et non plus dans la table issue des images tif defectueuses)
2) Test fonctionnel (pixels degrades par produit : CHIRPS = 20_CHIRPS_monthly ; ERA5 et TerraClimate = 14_RainProducts, inchanges)
Sorties : R\20_CHIRPS_monthly\15_Phase5\Rain_Product_BlockTests_SAIDA.csv et Functional_NDVI_Test_SAIDA.csv
"""
import os, csv, traceback
import numpy as np
from osgeo import gdal
gdal.UseExceptions()

R = r"C:\Users\User25\Desktop\résultat Saida"
D = r"C:\Users\User25\Desktop\DATA Saida"
OUT = os.path.join(R, "20_CHIRPS_monthly", "15_Phase5")
os.makedirs(OUT, exist_ok=True)


# ----------------------------------------------------------------------------- 1) TESTS PAR BLOCS
def linfit(x, y):
    sl, ic = np.polyfit(x, y, 1)
    return sl, ic


def block_tests():
    prod = {int(r["year"]): float(r["index_tous"]) for r in csv.DictReader(open(os.path.join(R, "03_Productivity", "Productivity_Index_By_Year_SAIDA.csv"), encoding="utf-8-sig"))}
    rows = list(csv.DictReader(open(os.path.join(R, "02_Rain", "Regional_Monthly_Rain_SAIDA.csv"), encoding="utf-8-sig")))
    cols = {"CHIRPS": "chirps_mm", "TerraClimate": "terraclimate_ppt_mm", "ERA5": "era5_mm_daily_mean"}

    def ser(col, win):
        d = {}
        for r in rows:
            if r[col] != "":
                v = float(r[col])
                d[(int(r["year"]), int(r["month"]))] = v
        m0, m1 = win
        out = {}
        for y in range(2000, 2026):
            ms = ([(y - 1, m) for m in range(m0, 13)] + [(y, m) for m in range(1, m1 + 1)]) if m0 > m1 else [(y, m) for m in range(m0, m1 + 1)]
            if all(k in d for k in ms):
                out[y] = sum(d[k] for k in ms)
        return out

    Y = np.array(sorted(prod)); P = np.array([prod[y] for y in Y]); sd = P.std(ddof=1)
    out = [["window", "product", "R2_in_sample", "block", "skill", "bias_pred_minus_obs_in_sd"]]
    for win, wn in (((9, 6), "Sep-Jun"), ((12, 4), "Dec-Apr")):
        for name, col in cols.items():
            s = ser(col, win)
            x = np.array([s[y] for y in Y]); r2 = np.corrcoef(x, P)[0, 1] ** 2
            for bn, te, tr in (("2013-15, train all other years", (Y >= 2013) & (Y <= 2015), None), ("2016-25, train 2000-15", Y >= 2016, Y < 2016), ("2021-25, train 2000-20", Y >= 2021, Y < 2021)):
                if tr is None:
                    tr = ~te
                sl, ic = linfit(x[tr], P[tr]); pr = ic + sl * x[te]; ob = P[te]
                sk = 1 - np.sqrt(np.mean((pr - ob) ** 2)) / np.sqrt(np.mean((P[tr].mean() - ob) ** 2))
                out.append([wn, name, round(r2, 3), bn, round(sk, 3), round(float(np.mean(pr - ob) / sd), 3)])
    path = os.path.join(OUT, "Rain_Product_BlockTests_SAIDA.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f, delimiter=";").writerows(out)
    print("\n".join(";".join(str(c) for c in r) for r in out))
    print("-> " + path)


# ----------------------------------------------------------------------------- 2) TEST FONCTIONNEL
def read_tif(p):
    ds = gdal.Open(p)
    a = ds.ReadAsArray()
    return a, ds


def functional_test():
    stack_path = os.path.join(D, "04_MODIS_2000_2025", "01_Annual_Productivity_MODIS_2000_2025_Saida.tif")
    a, ds = read_tif(stack_path)
    st = np.transpose(a.astype("float64"), (1, 2, 0)) if a.ndim == 3 else None      # (H, W, 26)
    st[st <= -9990] = np.nan
    yrs = np.arange(2000, 2026)
    paths = {"CHIRPS": os.path.join(R, "20_CHIRPS_monthly", "09_Designs_LPD"), "TerraClimate": os.path.join(R, "14_RainProducts", "TerraClimate"), "ERA5": os.path.join(R, "14_RainProducts", "ERA5")}
    sub = {"baseline": "LPD_2000_baseline_0906_s2012_r2013-2015", "monitoring": "LPD_2000_monitoring_0906"}
    f = os.path.join("03_LPD", "LPD_3class_B_QA1_min5_RainAdjusted.tif")

    def rd(p):
        c, d = read_tif(p)
        c = c.astype(int)
        if c.shape != st.shape[:2]:
            raise RuntimeError("Grille differente (%s) : %s contre %s" % (p, c.shape, st.shape[:2]))
        return c

    def metric(per):
        if per == "baseline":
            i = (yrs >= 2000) & (yrs <= 2015); x = yrs[i] - yrs[i].mean(); y = st[:, :, i]
            m = np.nanmean(y, axis=2); ok = np.isfinite(y).sum(2) >= 12
            yc = np.where(np.isfinite(y), y - m[:, :, None], 0)
            s = (yc * x).sum(2) / ((x ** 2)[None, None, :] * np.isfinite(y)).sum(2)
            return np.where(ok & (m > 0), s / m * 100, np.nan)
        a_ = np.nanmean(st[:, :, (yrs >= 2021)], axis=2); b_ = np.nanmean(st[:, :, yrs <= 2012], axis=2)
        return np.where(b_ > 0, (a_ - b_) / b_ * 100, np.nan)

    rows = []; masks = {}
    for per in sub:
        met = metric(per)
        for p, base in paths.items():
            c = rd(os.path.join(base, sub[per], f)); valid = (c != -9999) & np.isfinite(met)
            masks[(per, p)] = (c == -1) & valid
            n = valid.sum()
            for k, nm in [(-1, "degrade"), (0, "stable"), (1, "ameliore")]:
                v = met[valid & (c == k)]
                rows.append([per, p, nm, int((valid & (c == k)).sum()), round(100 * (valid & (c == k)).sum() / n, 2), round(float(np.mean(v)), 3) if len(v) else "", round(float(np.median(v)), 3) if len(v) else ""])
    path = os.path.join(OUT, "Functional_NDVI_Test_SAIDA.csv")
    with open(path, "w", encoding="utf-8-sig") as fo:
        fo.write("periode;produit_pluie;classe;pixels;part_%;mean_metrique;median_metrique\n")
        for r in rows:
            fo.write(";".join(str(x).replace(".", ",") for x in r) + "\n")
        fo.write("\nmetrique: baseline=pente 2000-2015 en %/an ; monitoring=(moy2021-25 - moy2000-12)/moy2000-12 en %\n")
        fo.write("\nrecouvrement des masques degrade (Jaccard)\nperiode;A;B;Jaccard;pixels_communs\n")
        for per in sub:
            ps = list(paths)
            for i in range(3):
                for j in range(i + 1, 3):
                    a_, b_ = masks[(per, ps[i])], masks[(per, ps[j])]
                    fo.write(("%s;%s;%s;%.3f;%d\n" % (per, ps[i], ps[j], (a_ & b_).sum() / max((a_ | b_).sum(), 1), (a_ & b_).sum())).replace(".", ","))
    print(open(path, encoding="utf-8-sig").read())
    print("-> " + path)


for fn in (block_tests, functional_test):
    try:
        print("=" * 70 + "\n" + fn.__name__ + "\n" + "=" * 70)
        fn()
    except Exception:
        print(traceback.format_exc())
print("TERMINE")
