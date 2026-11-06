# -*- coding: utf-8 -*-
r"""
SAIDA : STAGE 16 (date de rupture, test de Pettitt par pixel) avec le CHIRPS unique (total mensuel valide)
QGIS / PyQGIS, script autonome (numpy + GDAL seulement). A coller dans l'editeur Python de QGIS.

Methode (reconstruite, le script d'origine n'etait plus disponible) :
 - serie annuelle MODIS 2000-2025 par pixel (250 m), valeurs <= -9990 = manquant (<=3 annees manquantes : interpolation lineaire)
 - serie BRUTE : Pettitt sur la serie telle quelle
 - serie CORRIGEE DE LA PLUIE : regression regionale (moyenne regionale de productivite ~ pluie sept-juin CHIRPS, annee Y = sept Y-1 a juin Y),
   puis chaque pixel est divise par le facteur pluie regional (a moyenne conservee)
 - Pettitt : segments >= 4 ans de chaque cote, p < 0.05, p = 2 exp(-6 K^2 / (n^3 + n^2))
 - BreakYear = premiere annee du 2e segment ; Direction = -1 baisse / +1 hausse ; ShiftPct = (moy2 - moy1)/moy1 x 100
 - le masque de reference des pixels "degrades" = 20_CHIRPS_monthly\09_Designs_LPD\LPD_2000_monitoring_0906 (classe -1)
Verification interne : la part de pixels en baisse (serie brute) doit etre proche de 14.8 % (valeur de l'ancien run).
Sorties : R\20_CHIRPS_monthly\16_Timing\  (4 tifs x 2 series + 3 csv)
"""
import os, csv, traceback
import numpy as np
from osgeo import gdal
gdal.UseExceptions()

R = r"C:\Users\User25\Desktop\résultat Saida"
D = r"C:\Users\User25\Desktop\DATA Saida"
OUT = os.path.join(R, "20_CHIRPS_monthly", "16_Timing")
os.makedirs(OUT, exist_ok=True)
STACK = os.path.join(D, "04_MODIS_2000_2025", "01_Annual_Productivity_MODIS_2000_2025_Saida.tif")
RAIN = os.path.join(R, "02_Rain", "Regional_Monthly_Rain_SAIDA.csv")
LPD_MON = os.path.join(R, "20_CHIRPS_monthly", "09_Designs_LPD", "LPD_2000_monitoring_0906", "03_LPD", "LPD_3class_B_QA1_min5_RainAdjusted.tif")
LULC15 = os.path.join(R, "lulc 2", "LULC_Saida_2015.tif")
NAMES = {1: "Bati", 2: "Eau", 3: "Sebkha", 4: "Sol nu/roche", 5: "Culture", 6: "Jachere", 7: "Foret", 8: "Parcours"}
MINSEG = 4
YRS = np.arange(2000, 2026)
N = len(YRS)


def fnum(s):
    return float(str(s).replace(",", "."))


def seasonal_rain():
    with open(RAIN, encoding="utf-8-sig") as f:
        txt = f.read().splitlines()
    sep = ";" if txt[0].count(";") > txt[0].count(",") else ","
    rd = csv.DictReader(txt, delimiter=sep)
    tot = {}
    for r in rd:
        y, m = int(float(r["year"])), int(float(r["month"]))
        if str(r["chirps_mm"]).strip() == "":
            continue                                   # janvier-aout 1999 vides (hors periode)
        v = fnum(r["chirps_mm"])
        if m >= 9:
            sy = y + 1
        elif m <= 6:
            sy = y
        else:
            continue
        tot[sy] = tot.get(sy, 0.0) + v
    return np.array([tot[y] for y in YRS])


def pettitt(X):
    """X : (P, N). Retourne annee de rupture, direction, shift %, p, pour t restreint a segments >= MINSEG."""
    P = X.shape[0]
    ts = list(range(MINSEG - 1, N - MINSEG))          # t = indice du dernier element du 1er segment
    best = np.zeros(P); bt = np.zeros(P, dtype=int)
    for t in ts:
        a = X[:, :t + 1][:, :, None]; b = X[:, t + 1:][:, None, :]
        U = np.sign(b - a).sum(axis=(1, 2))
        upd = np.abs(U) > best
        best = np.where(upd, np.abs(U), best); bt = np.where(upd, t, bt)
    p = np.minimum(1.0, 2 * np.exp(-6.0 * best ** 2 / (N ** 3 + N ** 2)))
    m1 = np.zeros(P); m2 = np.zeros(P)
    for t in ts:
        s = bt == t
        if s.any():
            m1[s] = X[s, :t + 1].mean(1); m2[s] = X[s, t + 1:].mean(1)
    shift = np.where(m1 > 0, (m2 - m1) / m1 * 100, np.nan)
    return YRS[0] + bt + 1, np.where(m2 < m1, -1, 1), shift, p


def run():
    ds = gdal.Open(STACK)
    a = ds.ReadAsArray().astype("float64")
    st = np.transpose(a, (1, 2, 0)) if a.shape[0] == N else a
    H, W = st.shape[:2]
    gt, prj = ds.GetGeoTransform(), ds.GetProjection()
    st[st <= -9990] = np.nan
    lpd = gdal.Open(LPD_MON).ReadAsArray().astype(int)
    assert lpd.shape == (H, W), "grille LPD differente"
    nmiss = np.isnan(st).sum(2)
    ok = (nmiss <= 3) & (nmiss < N)
    X = st[ok]                                         # (P, N)
    for i in np.where(np.isnan(X).any(1))[0]:           # interpolation des rares annees manquantes
        g = np.isfinite(X[i]); X[i] = np.interp(YRS, YRS[g], X[i, g])
    rain = seasonal_rain()
    M = X.mean(0)
    b, a0 = np.polyfit(rain, M, 1)
    Mhat = a0 + b * rain
    fac = Mhat / Mhat.mean()
    r2 = np.corrcoef(rain, M)[0, 1] ** 2
    print("Regression regionale productivite ~ pluie sept-juin : R2 = %.3f ; pluie min/moy/max = %.0f/%.0f/%.0f mm" % (r2, rain.min(), rain.mean(), rain.max()))
    Xc = X / fac[None, :]
    # LULC 2015 sur la grille MODIS (classe majoritaire)
    xmin, ymax = gt[0], gt[3]; xmax = xmin + gt[1] * W; ymin = ymax + gt[5] * H
    wr = gdal.Warp("/vsimem/l15.tif", LULC15, format="GTiff", outputBounds=(xmin, ymin, xmax, ymax), width=W, height=H, dstSRS=prj, resampleAlg="mode")
    lulc = wr.ReadAsArray().astype(int); wr = None

    res = {}
    for nm, XX in (("brute", X), ("corrigee_pluie", Xc)):
        by, di, sh, pv = pettitt(XX)
        sig = pv < 0.05
        full = {k: np.full((H, W), np.nan, "float32") for k in ("BreakYear", "BreakDirection", "BreakShiftPct", "PettittP")}
        full["BreakYear"][ok] = np.where(sig, by, np.nan); full["BreakDirection"][ok] = np.where(sig, di, 0)
        full["BreakShiftPct"][ok] = np.where(sig, sh, np.nan); full["PettittP"][ok] = pv
        for k, arr in full.items():
            arr = np.where(np.isfinite(arr), arr, -9999).astype("float32")
            drv = gdal.GetDriverByName("GTiff").Create(os.path.join(OUT, "T_%s_%s.tif" % (k, nm)), W, H, 1, gdal.GDT_Float32)
            drv.SetGeoTransform(gt); drv.SetProjection(prj)
            bnd = drv.GetRasterBand(1); bnd.WriteArray(arr); bnd.SetNoDataValue(-9999); drv.FlushCache(); drv = None
        res[nm] = {k: (np.where(np.isfinite(v), v, np.nan)) for k, v in full.items()}
        # direction complete (0 = pas de rupture) sur les pixels valides
        d = np.full((H, W), 0, int); d[ok] = np.where(sig, di, 0); res[nm]["dir"] = d

    # --- tables
    lp_ok = (lpd != -9999) & ok
    rows_l = []
    for nm in res:
        d = res[nm]["dir"]; by = res[nm]["BreakYear"]; sh = res[nm]["BreakShiftPct"]
        for lab, k in (("TOUT (LPD valide)", None), ("degrade", -1), ("stable", 0), ("ameliore", 1)):
            m = lp_ok if k is None else lp_ok & (lpd == k)
            n = int(m.sum())
            dn = m & (d == -1); up = m & (d == 1)
            rows_l.append([nm, lab, n, round(100 * dn.sum() / max(n, 1), 1), round(100 * up.sum() / max(n, 1), 1),
                           int(np.nanmedian(by[dn])) if dn.any() else "", round(float(np.nanmean(sh[dn])), 1) if dn.any() else "",
                           int(np.nanmedian(by[up])) if up.any() else ""])
    rows_u = []
    for nm in res:
        d = res[nm]["dir"]; by = res[nm]["BreakYear"]; sh = res[nm]["BreakShiftPct"]
        for k, cn in list(NAMES.items()) + [(0, "TOUT")]:
            m = ok if k == 0 else ok & (lulc == k)
            n = int(m.sum())
            if n == 0 or k == 2:
                continue
            dn = m & (d == -1); up = m & (d == 1)
            rows_u.append([nm, cn, n, round(100 * dn.sum() / n, 1), round(100 * up.sum() / n, 1),
                           int(np.nanmedian(by[dn])) if dn.any() else "", round(float(np.nanmean(sh[dn])), 1) if dn.any() else ""])
    rows_y = []
    for nm in res:
        d = res[nm]["dir"]; by = res[nm]["BreakYear"]
        for y in YRS[MINSEG:N - MINSEG + 1]:
            rows_y.append([nm, int(y), int(((d == -1) & (by == y) & ok).sum()), int(((d == 1) & (by == y) & ok).sum()),
                           int(((d == -1) & (by == y) & lp_ok & (lpd == -1)).sum())])

    def wcsv(name, head, rows, note=None):
        p = os.path.join(OUT, name)
        with open(p, "w", encoding="utf-8-sig") as f:
            f.write(";".join(head) + "\n")
            for r in rows:
                f.write(";".join(str(x).replace(".", ",") for x in r) + "\n")
            if note:
                f.write("\n" + note + "\n")
        print(open(p, encoding="utf-8-sig").read()); print("-> " + p)

    wcsv("Stage16_Break_vs_LPD.csv", ["serie", "classe_LPD_monitoring", "pixels", "pct_baisse", "pct_hausse", "annee_mediane_baisse", "chgt_moyen_baisse_pct", "annee_mediane_hausse"], rows_l,
         "Regression pluie regionale : R2=%.3f ; rupture = Pettitt p<0.05, segments>=4 ans ; BreakYear = 1re annee du 2e segment" % r2)
    wcsv("Stage16_Break_by_LULC2015.csv", ["serie", "classe_LULC_2015", "pixels", "pct_baisse", "pct_hausse", "annee_mediane_baisse", "chgt_moyen_baisse_pct"], rows_u)
    wcsv("Stage16_BreakYear_Distribution.csv", ["serie", "annee", "pixels_baisse", "pixels_hausse", "pixels_baisse_LPD_degrade"], rows_y)


try:
    run()
except Exception:
    print(traceback.format_exc())
print("TERMINE")
