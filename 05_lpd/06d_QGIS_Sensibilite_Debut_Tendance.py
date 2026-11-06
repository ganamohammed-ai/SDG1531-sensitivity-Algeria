# -*- coding: utf-8 -*-
# SDG 15.3.1 REFERENCE PIPELINE — STAGE 02B / 08 : Sensitivity of the productivity trend to the start year — QGIS
"""
ÉTAPE 02B — SENSIBILITÉ DE LA PRODUCTIVITÉ À L'ANNÉE DE DÉBUT DE LA SÉRIE (le « départ en sécheresse »)   |   QGIS / PyQGIS, SCRIPT AUTONOME
(à coller dans la Console Python de QGIS ou à exécuter depuis l'éditeur)

POURQUOI
  La série MODIS commence en 2000, au début d'une sécheresse (2000–2002). Une pente calculée à partir d'un creux tend à donner de l'« amélioration » presque partout. Ce script refait, pour plusieurs années de DÉBUT
  (2000, 2001, 2002, 2003, 2004, 2005), les deux composantes de LPD qui dépendent du temps — la TRAJECTOIRE (pente de Sen + tau de Kendall) et l'ÉTAT (variation relative base -> récent) — avec les mêmes définitions que l'étape 02 :
    - trajectoire « amélioration / dégradation » si |tau| >= TAU_MAIN (0,30) ; variante au seuil de signification P_ALPHA (0,05) ;
    - état : moyenne de la période de base (de l'année de début à BASELINE_END) contre la période récente (RECENT_YEARS), seuil STATE_THRESHOLD (10 %) ;
    - variante CORRIGÉE DE LA PLUIE : régression de la productivité sur la pluie de saison humide (sept. a-1 -> juin a), résidus si R² >= R2_RELIABLE ;
    - « LPD sans Performance » : règle de l'étape 02 avec Performance faible = faux partout (la Performance ne peut que faire basculer certains pixels « améliorés » en « dégradés »).
  Il compare ensuite chaque année de début à la référence (2000) : parts amélioré / stable / dégradé, pente médiane, et QUELS pixels « améliorés » ne le sont plus.

CE QU'IL NE FAIT PAS (à lire)
  - Ce n'est PAS un LPD complet : la composante Performance (groupes fonctionnels, LULC) n'est pas recalculée.
  - Il ne prouve pas la cause d'une différence : une baisse de l'amélioration quand on retire les années 2000–2002 est compatible avec un départ en sécheresse, mais aussi avec une vraie reprise ; le tableau des années (pluie, NDVI moyen) aide à trancher.
  - Une série de 26 ans raccourcie à 21–23 ans a moins de puissance statistique : une baisse de pixels « significatifs » n'est pas toujours un effet du départ.

ENTRÉES : pile annuelle MODIS (une bande par année, nom de bande contenant l'année) ; facultatif : pluie journalière ClimateEngine (CHIRPS) pour la variante corrigée.
SORTIES : tableaux CSV, figures, rasters de trajectoire (pile en un seul fichier), rapport HTML d'étape.
"""
import os
import re
import csv
import json
import math
import time
import datetime as dt
import warnings
import platform
import traceback
import numpy as np

AREA_NAME = "Oum El Bouaghi (Algeria)"
REPORT_LANG = "en"
START_YEARS = [2000, 2001, 2002, 2003, 2004, 2005]    # années de début comparées
REFERENCE_START = 2000                                  # référence (l'étape 02 actuelle)
ALTERNATIVE_START = 2003                                # début « après la sécheresse » dont les rasters sont écrits
BASELINE_END = 2015                                     # fin de la période de base de l'étape 02 (BASELINE_YEARS = (2000, 2015))
RECENT_YEARS = (2021, 2025)
TAU_MAIN = 0.30
P_ALPHA = 0.05
STATE_THRESHOLD = 0.10
R2_RELIABLE = 0.20
MIN_BASELINE_MEAN = 0.05
MIN_BASE_YEARS, MIN_RECENT_YEARS = 8, 3
DROUGHT_Z = -1.0                                        # écart réduit de la pluie de saison humide en dessous duquel une année est « sèche »
RAIN_WINDOWS = {"Sep–Jun (stage 02)": (9, 6), "Oct–Mar": (10, 3), "Nov–Apr": (11, 4), "Dec–Apr": (12, 4), "Jan–Apr": (1, 4), "Jan–Mar": (1, 3), "Feb–May": (2, 5), "Mar–Jun (growing season)": (3, 6), "Jan–Jun": (1, 6)}
DEFAULT_RAIN_WINDOW = "Sep–Jun (stage 02)"              # fenêtre de pluie de l'étape 02 (sept. a-1 -> juin a)
ALT_RAIN_WINDOW = "auto"                                # "auto" : fenêtre au meilleur R² (si le gain dépasse MIN_R2_GAIN) ; None : pas de variante ; ou le nom d'une fenêtre de RAIN_WINDOWS
MIN_R2_GAIN = 0.05                                      # gain de R² (productivité moyenne ~ pluie) au-delà duquel une meilleure fenêtre donne une variante supplémentaire
STUDY_AREA_HA = 628942                                  # surface de la zone d'étude (ha) : sert à vérifier que l'analyse porte sur la zone et non sur tout le rectangle du raster
VARIANT_LABELS = {}                                     # renseigné à l'exécution : fenêtre de pluie de chaque variante corrigée
SPREAD_WARN_POINTS = 5.0                                # baisse de la part « améliorée » (points) au-delà de laquelle le départ en sécheresse est suspecté


# ============================================================================
# 1. LOGIQUE PURE (testée sans QGIS) — mêmes définitions que l'étape 02
# ============================================================================
def sen_kendall(X, t, min_valid):
    """X : (n_années, n_pixels), NaN = manquant ; t : années. Pente de Sen, tau, n_valid, z, p (Mann-Kendall bilatéral, approximation normale avec correction de continuité) ; NaN si n_valid < min_valid."""
    n_y, n_px = X.shape
    I, J = np.triu_indices(n_y, k=1)
    dt_ = (np.asarray(t)[J] - np.asarray(t)[I]).astype(np.float64)[:, None]
    X = X.astype(np.float64)
    nv = np.isfinite(X).sum(0).astype(np.float64)
    D = X[J] - X[I]
    S = np.nansum(np.sign(D), axis=0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        sen = np.nanmedian(D / dt_, axis=0)
        tau = S / (nv * (nv - 1.0) / 2.0)
        var = nv * (nv - 1.0) * (2.0 * nv + 5.0) / 18.0
        z = np.where(S != 0, (S - np.sign(S)) / np.sqrt(var), 0.0)
    p = np.array([math.erfc(abs(v) / math.sqrt(2.0)) for v in np.ravel(z)], dtype=np.float64).reshape(np.shape(z))
    bad = nv < min_valid
    for arr in (sen, tau, z, p):
        arr[bad] = np.nan
    return {"slope": sen, "tau": tau, "n_valid": nv, "z": z, "p": p}


def sen_kendall_chunked(X, t, min_valid, chunk=20000):
    n_px = X.shape[1]
    out = {k: np.full(n_px, np.nan, dtype=np.float32) for k in ("slope", "tau", "n_valid", "z", "p")}
    for a in range(0, n_px, chunk):
        b = min(n_px, a + chunk)
        r = sen_kendall(X[:, a:b], t, min_valid)
        for k in out:
            out[k][a:b] = r[k]
    return out


def regress_rain(P, R, min_reg):
    """Régression P = a + b R par pixel. Retourne (b, a, r2, ok)."""
    R = np.asarray(R, dtype=np.float64)
    r_ok = np.isfinite(R)
    prod_ok = np.isfinite(P) & (P != 0)
    v = prod_ok & r_ok[:, None]
    Rb = np.where(r_ok, R, 0.0)[:, None]
    Pz = np.where(v, P, 0.0).astype(np.float64)
    n = v.sum(0).astype(np.float64)
    sx, sy = (v * Rb).sum(0), Pz.sum(0)
    sxx, sxy = (v * Rb * Rb).sum(0), (Pz * Rb).sum(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        den = n * sxx - sx * sx
        b = (n * sxy - sx * sy) / den
        a = (sy - b * sx) / n
        pred = a[None] + b[None] * Rb
        ss_res = (v * (Pz - pred) ** 2).sum(0)
        ss_tot = (v * (Pz - (sy / n)[None]) ** 2).sum(0)
        r2 = 1.0 - ss_res / ss_tot
    ok = (n >= min_reg) & (den > 1e-9)
    return np.where(ok, b, np.nan), np.where(ok, a, np.nan), np.where(ok, r2, np.nan), ok


def residual_series(P, R, b, a, reliable):
    """Résidus de la régression là où elle est fiable ; série brute ailleurs (comme l'étape 02)."""
    R = np.asarray(R, dtype=np.float64)
    pred = a[None, :] + b[None, :] * R[:, None]
    out = np.where(reliable[None, :] & np.isfinite(R)[:, None], P - pred, P)
    out = np.where(np.isfinite(P) & (P != 0), out, np.nan)
    return out.astype(np.float32)


def period_stats(P, R, idx):
    m = np.isfinite(P[idx]) & (P[idx] != 0)
    cnt = m.sum(0).astype(np.float64)
    mp = m & np.isfinite(R[idx])[:, None]
    cnt_r = mp.sum(0).astype(np.float64)
    s_p = np.where(m, P[idx], 0.0).sum(0)
    s_r = (mp * np.where(np.isfinite(R[idx]), R[idx], 0.0)[:, None]).sum(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return cnt, s_p / cnt, s_r / cnt_r


def state_relative(P, R, base_idx, rec_idx, b=None, reliable=None):
    """Variation relative base -> récent (observée) ; si b, reliable fournis, version CORRIGÉE de la pluie là où la régression est fiable (comme rain_adjusted_state de l'étape 02)."""
    R = np.full(P.shape[0], np.nan) if R is None else np.asarray(R, dtype=np.float64)
    nb, mb, rb = period_stats(P, R, base_idx)
    nr, mr, rr = period_stats(P, R, rec_idx)
    ok = (nb >= MIN_BASE_YEARS) & (nr >= MIN_RECENT_YEARS) & (mb >= MIN_BASELINE_MEAN)
    with np.errstate(invalid="ignore", divide="ignore"):
        denom = np.maximum(np.abs(mb), 1e-6)
        rel_obs = (mr - mb) / denom
        out = np.where(ok, rel_obs, np.nan)
        if b is not None:
            rel_exp = b * (rr - rb) / denom
            adj = ok & reliable & np.isfinite(rel_exp)
            out = np.where(adj, rel_obs - rel_exp, out)
    return out


def classify_state(rel, thr=STATE_THRESHOLD):
    """0 non valide ; 1 dégradé (<= -thr) ; 2 stable ; 3 amélioré (>= +thr)."""
    cls = np.zeros(rel.shape, dtype=np.uint8)
    valid = np.isfinite(rel)
    cls[valid] = 2
    with np.errstate(invalid="ignore"):
        cls[valid & (rel <= -thr)] = 1
        cls[valid & (rel >= thr)] = 3
    return cls


def classify_trajectory(traj, tau_thr=TAU_MAIN, use_p=False):
    """(classe int8 : -1 déclin, 0 stable, 1 amélioration ; masque valide). Même criblage que lpd_from de l'étape 02."""
    valid = np.isfinite(traj["slope"]) & np.isfinite(traj["tau"])
    slope = np.where(np.isfinite(traj["slope"]), traj["slope"], 0.0)
    if use_p:
        screened = np.isfinite(traj["p"]) & (traj["p"] < P_ALPHA)
    else:
        screened = np.abs(np.where(np.isfinite(traj["tau"]), traj["tau"], 0.0)) >= tau_thr
    cls = np.zeros(slope.shape, dtype=np.int8)
    cls[(slope < 0) & screened] = -1
    cls[(slope > 0) & screened] = 1
    return np.where(valid, cls, 0).astype(np.int8), valid


def lpd3_without_performance(traj_cls, state_cls):
    """Règle de l'étape 02 (lpd_classify) avec Performance faible = faux : -1 si déclin ; -1 si stable et état dégradé ; 1 si amélioration ; sinon 0."""
    out = np.zeros(traj_cls.shape, dtype=np.int8)
    out[traj_cls == -1] = -1
    out[(traj_cls == 0) & (state_cls == 1)] = -1
    out[traj_cls == 1] = 1
    return out


def min_valid_for(n_years):
    """Années valides minimales pour Sen/Kendall : 15 sur 26 à l'étape 02, même proportion pour une série raccourcie (au moins 10)."""
    return max(10, int(round(15.0 / 26.0 * n_years)))


def analyse_start(P, years, R, start, end, R_alt=None):
    """
    Trajectoire + état + LPD sans Performance pour la fenêtre [start, end], variantes BRUTE et CORRIGÉE DE LA PLUIE (si R est fourni).
    P : (années, pixels) ; years : tableau ; R : pluie de saison humide par année (NaN si absente) ou None.
    Retourne {variante: {"traj_tau", "traj_p", "state", "lpd3", "slope", "valid"}}.
    """
    years = np.asarray(years)
    win = np.where((years >= start) & (years <= end))[0]
    t = years[win]
    X = P[win].astype(np.float32)
    n = len(win)
    mv = min_valid_for(n)
    base_idx = [i for i in range(n) if start <= t[i] <= BASELINE_END]
    rec_idx = [i for i in range(n) if RECENT_YEARS[0] <= t[i] <= RECENT_YEARS[1]]
    res = {}
    variants = [("raw", X, None, None)]
    for vname, Rv in (("rain_adjusted", R), ("rain_adjusted_best", R_alt)):
        if Rv is None:
            continue
        Rw = np.asarray(Rv, dtype=np.float64)[win]
        if np.isfinite(Rw).sum() >= max(10, int(0.6 * n)):
            b, a, r2, ok = regress_rain(X, Rw, max(10, int(round(0.6 * n))))
            reliable = ok & np.isfinite(r2) & (r2 >= R2_RELIABLE)
            variants.append((vname, residual_series(X, Rw, b, a, reliable), (b, reliable), Rw))
    if R is not None:                                  # variante EFFICIENCE D'USAGE DE LA PLUIE (RUE = NDVI / pluie) : le rapport, par opposition aux résidus ; remis à l'échelle du NDVI (× pluie moyenne) pour garder les seuils de l'état
        Rr0 = np.asarray(R, dtype=np.float64)[win]
        if np.isfinite(Rr0).sum() >= max(10, int(0.6 * n)):
            ok_r = np.isfinite(Rr0) & (Rr0 > 0)
            with np.errstate(invalid="ignore", divide="ignore"):
                rue = np.where(ok_r[:, None] & np.isfinite(X) & (X != 0), X / np.where(ok_r, Rr0, np.nan)[:, None] * float(np.nanmean(Rr0[ok_r])), np.nan).astype(np.float32)
            variants.append(("rue", rue, None, None))
    for name, S, adj, Rr in variants:
        traj = sen_kendall_chunked(S, t, mv)
        c_tau, v = classify_trajectory(traj, TAU_MAIN, False)
        c_p, _ = classify_trajectory(traj, TAU_MAIN, True)
        if adj is None:
            rel = state_relative(S, None, base_idx, rec_idx)            # brute : S = X ; RUE : S = NDVI / pluie remis à l'échelle du NDVI
        else:
            rel = state_relative(X, Rr, base_idx, rec_idx, adj[0], adj[1])
        sc = classify_state(rel)
        lp = lpd3_without_performance(c_tau, sc)
        valid = v & (sc > 0)
        res[name] = {"traj_tau": c_tau, "traj_p": c_p, "state": sc, "lpd3": np.where(valid, lp, 0).astype(np.int8), "slope": traj["slope"], "valid": valid, "traj_valid": v}
    return res


def share(cls, valid, values=(-1, 0, 1)):
    n = int(np.count_nonzero(valid))
    return {v: (100.0 * int(np.count_nonzero(valid & (cls == v))) / n if n else float("nan")) for v in values}, n


def transition_counts(cls_a, valid_a, cls_b, valid_b):
    """Matrice 3x3 (lignes = référence, colonnes = alternative ; ordre -1, 0, 1) sur les pixels valides dans les deux."""
    both = valid_a & valid_b
    labs = (-1, 0, 1)
    return np.array([[int(np.count_nonzero(both & (cls_a == i) & (cls_b == j))) for j in labs] for i in labs], dtype=np.int64)


def spatial_mean_series(P, years):
    """Productivité moyenne spatiale par année (pixels valides) et nombre de pixels."""
    out = []
    for i, y in enumerate(years):
        m = np.isfinite(P[i]) & (P[i] != 0)
        out.append((int(y), float(P[i][m].mean()) if m.any() else float("nan"), int(m.sum())))
    return out


def zscores(values):
    v = np.asarray(values, float)
    m = np.isfinite(v)
    if m.sum() < 3 or np.nanstd(v[m]) == 0:
        return np.full(v.shape, np.nan)
    return (v - np.nanmean(v[m])) / np.nanstd(v[m], ddof=1)


def parse_daily_rain(text):
    out = {}
    for line in text.splitlines():
        line = line.strip().lstrip("\ufeff")
        if not line:
            continue
        parts = line.split(";") if ";" in line else line.split(",")
        val = parts[1].replace(",", ".") if (";" in line and len(parts) > 1) else (parts[1] if len(parts) > 1 else "")
        try:
            out[dt.date.fromisoformat(parts[0].strip().strip('"'))] = float(val.strip().strip('"'))
        except (ValueError, IndexError):
            continue
    return out


def window_total(daily, start, end, min_cover=0.9):
    n_exp = (end - start).days + 1
    total, n, d = 0.0, 0, start
    while d <= end:
        v = daily.get(d)
        if v is not None:
            total += v
            n += 1
        d += dt.timedelta(days=1)
    return total if n >= min_cover * n_exp else None


def season_rain(daily, years, months):
    """Pluie d'une fenêtre de mois (m0, m1) rattachée à l'année a : de m0 (a-1 si m0 > m1, sinon a) à la fin de m1 de l'année a ; None si la couverture est insuffisante."""
    import calendar
    m0, m1 = months
    out = {}
    for y in years:
        y = int(y)
        start = dt.date(y - 1 if m0 > m1 else y, m0, 1)
        end = dt.date(y, m1, calendar.monthrange(y, m1)[1])
        out[y] = window_total(daily, start, end)
    return out


def wet_season_rain(daily, years):
    """Pluie de saison humide de l'étape 02 : 1er septembre (a-1) -> 30 juin (a) ; None si la couverture est insuffisante."""
    return season_rain(daily, years, (9, 6))


def rain_window_table(series, daily, windows=None):
    """
    Quelle fenêtre de pluie explique le mieux la productivité moyenne annuelle ? Pour chaque fenêtre : R² de la régression productivité moyenne ~ pluie, pente, nombre d'années et RÉSIDU (en écarts-types) des trois premières années.
    Retourne (lignes, meilleure ligne). Attention : 20-26 points seulement, c'est une indication, pas une preuve.
    """
    windows = windows or RAIN_WINDOWS
    ys = [r[0] for r in series]
    P = [r[1] for r in series]
    rows = []
    for nm, months in windows.items():
        rain = season_rain(daily, ys, months)
        pts = [(rain[y], p, y) for y, p in zip(ys, P) if rain[y] is not None and p == p]
        if len(pts) < 10:
            continue
        x = np.array([q[0] for q in pts])
        v = np.array([q[1] for q in pts])
        k, c = np.polyfit(x, v, 1)
        res = v - (c + k * x)
        ss_tot = float(((v - v.mean()) ** 2).sum())
        r2 = 1.0 - float((res ** 2).sum()) / ss_tot if ss_tot > 0 else float("nan")
        sd = float(res.std(ddof=2))
        first = {q[2]: float(res[i] / sd) for i, q in enumerate(pts) if q[2] in ys[:3] and sd > 0}
        rows.append({"window": nm, "months": months, "r2": r2, "slope": float(k), "n": len(pts), "first": first})
    best = max(rows, key=lambda r: r["r2"]) if rows else None
    return rows, best


def vlabel(var, lang="en"):
    """Libellé lisible d'une variante : brute, ou corrigée de la pluie avec sa fenêtre."""
    T = lambda a, b: a if lang == "en" else b
    if var == "raw":
        return T("raw", "brute")
    if var == "rue":
        return T("rain-use efficiency (NDVI ÷ rain)", "efficience d'usage de la pluie (NDVI ÷ pluie)")
    w = VARIANT_LABELS.get(var, "")
    return T("rain-adjusted", "corrigée de la pluie") + (f" ({w})" if w else "")


def apply_study_mask(P, mask):
    """P (années, lignes, colonnes) ; mask booléen (lignes, colonnes), vrai dans la zone d'étude : met NaN en dehors (modifie P sur place). Sans masque, P est rendu tel quel."""
    if mask is None:
        return P
    mask = np.asarray(mask, dtype=bool)
    if mask.shape != P.shape[1:]:
        raise ValueError(f"Le masque ({mask.shape}) n'a pas la grille du raster ({P.shape[1:]}).")
    P[:, ~mask] = np.nan
    return P


def coverage_check(valid_px, px_ha, study_ha, masked, lang="en"):
    """(statut, détail) : la surface des pixels analysés est-elle celle de la zone d'étude ? Sans masque, le raster est souvent un rectangle bien plus grand que la zone."""
    T = lambda a, b: a if lang == "en" else b
    if not (valid_px and px_ha):
        return None
    area = valid_px * px_ha
    if not study_ha:
        return ("INFO", T(f"{valid_px:,} pixels = {area:,.0f} ha analysed", f"{valid_px:,} pixels = {area:,.0f} ha analysés"))
    ratio = area / study_ha
    if masked:
        ok = 0.85 <= ratio <= 1.15
        return ("PASS" if ok else "WARN", T(f"{valid_px:,} pixels = {area:,.0f} ha inside the study-area mask, {ratio:.2f} × the study area ({study_ha:,.0f} ha)" + ("" if ok else ": check the mask and its projection"),
                                           f"{valid_px:,} pixels = {area:,.0f} ha dans le masque de la zone, {ratio:.2f} × la zone d'étude ({study_ha:,.0f} ha)" + ("" if ok else " : vérifier le masque et sa projection")))
    if ratio > 1.15:
        return ("WARN", T(f"NO study-area mask: {valid_px:,} pixels = {area:,.0f} ha, {ratio:.2f} × the study area ({study_ha:,.0f} ha): the shares include land OUTSIDE the study area; give the study-area shapefile",
                          f"AUCUN masque de zone : {valid_px:,} pixels = {area:,.0f} ha, {ratio:.2f} × la zone d'étude ({study_ha:,.0f} ha) : les parts incluent des terres HORS de la zone ; fournir le shapefile de la zone"))
    return ("INFO", T(f"no mask; {valid_px:,} pixels = {area:,.0f} ha ({ratio:.2f} × the study area)", f"pas de masque ; {valid_px:,} pixels = {area:,.0f} ha ({ratio:.2f} × la zone)"))


def band_year_list(descriptions, start_year=None):
    ys = []
    for d in descriptions:
        m = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", str(d or ""))
        ys.append(int(m.group(1)) if m else None)
    if all(y is not None for y in ys) and len(set(ys)) == len(ys):
        return ys
    if start_year is None:
        raise ValueError("Les bandes n'ont pas d'année dans leur nom : indiquez l'année de la première bande.")
    return [int(start_year) + i for i in range(len(descriptions))]


# ============================================================================
# 2. RÉSULTATS ET RAPPORT HTML D'ÉTAPE (bloc partagé : voir tools/sdg_stage_report.py)
# ============================================================================
PIPELINE_BUILD = "2026.10-66c0b6e108a4"
# >>> STAGE_REPORT_BEGIN  (bloc IDENTIQUE dans tous les scripts de la chaîne ; source : tools/sdg_stage_report.py ; synchronisé par tools/sync_stage_report.py)
SR_VERSION = "1.0"
SR_TEXT = {
    "en": {"run": "Run information", "params": "Parameters", "inputs": "Inputs", "summary": "Key results", "checks": "Quality checks", "limits": "Limitations and cautions", "adapt": "Reproducibility: adapting this stage to another study area",
           "outputs": "Output files", "refs": "References", "toc": "Contents", "status": "Status", "check": "Check", "detail": "Detail", "generated": "Generated", "stage": "Stage", "area": "Study area", "duration": "Duration",
           "software": "Software", "file": "File", "size": "Size", "more_rows": "… {n} more rows (see the CSV file)", "no_data": "No data available.", "overall": "Overall quality status", "pass": "PASS", "warn": "WARN", "fail": "FAIL", "info": "INFO",
           "legend": "Legend", "sha": "SHA-256", "path": "Path", "value": "Value"},
    "fr": {"run": "Informations sur l'exécution", "params": "Paramètres", "inputs": "Données d'entrée", "summary": "Résultats principaux", "checks": "Contrôles de qualité", "limits": "Limites et précautions", "adapt": "Reproductibilité : adapter cette étape à une autre zone d'étude",
           "outputs": "Fichiers produits", "refs": "Références", "toc": "Sommaire", "status": "Statut", "check": "Contrôle", "detail": "Détail", "generated": "Généré le", "stage": "Étape", "area": "Zone d'étude", "duration": "Durée",
           "software": "Logiciels", "file": "Fichier", "size": "Taille", "more_rows": "… {n} lignes de plus (voir le fichier CSV)", "no_data": "Aucune donnée disponible.", "overall": "Statut global de qualité", "pass": "OK", "warn": "ATTENTION", "fail": "ÉCHEC", "info": "INFO",
           "legend": "Légende", "sha": "SHA-256", "path": "Chemin", "value": "Valeur"},
}


def sr_t(lang, key, **kw):
    s = SR_TEXT.get(lang, SR_TEXT["en"]).get(key, SR_TEXT["en"].get(key, key))
    return s.format(**kw) if kw else s


def sr_esc(x):
    import html as _h
    return _h.escape("" if x is None else str(x))


def sr_read_csv(path, max_rows=None):
    """Lit un CSV (séparateur ; , ou tabulation détecté, UTF-8 avec ou sans BOM) -> liste de lignes de texte ; [] si le fichier est absent ou vide."""
    import csv as _csv
    if not path or not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
        txt = f.read()
    if not txt.strip():
        return []
    first = txt.splitlines()[0]
    delim = max((";", ",", "\t"), key=lambda d: first.count(d))
    rows = list(_csv.reader(txt.splitlines(), delimiter=delim))
    return rows if max_rows is None else rows[:max_rows]


def sr_dict_rows(rows):
    """Lignes (avec en-tête) -> liste de dictionnaires {colonne: texte}."""
    if len(rows) < 2:
        return []
    return [dict(zip(rows[0], r)) for r in rows[1:]]


def sr_num(v, default=float("nan")):
    """Texte -> nombre (virgule décimale acceptée, % et espaces ignorés)."""
    try:
        return float(str(v).replace(",", ".").replace("%", "").replace("\u202f", "").replace(" ", "").strip())
    except (ValueError, TypeError):
        return default


def sr_table(rows, caption="", max_rows=60):
    """Tableau HTML (première ligne = en-tête ; colonnes numériques alignées à droite ; troncature annoncée)."""
    if not rows:
        return ""
    head, body = rows[0], rows[1:]
    shown = body[:max_rows]
    numeric = [all(re.fullmatch(r"\s*[-+]?[\d\s.,]+\s*%?\s*", str(r[c])) or str(r[c]).strip() == "" for r in shown if c < len(r)) and any(str(r[c]).strip() for r in shown if c < len(r)) for c in range(len(head))]
    out = ["<table>" + (f"<caption>{sr_esc(caption)}</caption>" if caption else ""), "<tr>" + "".join(f"<th>{sr_esc(h)}</th>" for h in head) + "</tr>"]
    for r in shown:
        out.append("<tr>" + "".join(f"<td{' class=n' if (c < len(numeric) and numeric[c]) else ''}>{sr_esc(r[c] if c < len(r) else '')}</td>" for c in range(len(head))) + "</tr>")
    out.append("</table>")
    return "<div class='scroll'>" + "".join(out) + "</div>" + (f"<p class='small'>{sr_esc('… ' + str(len(body) - len(shown)) + ' more rows')}</p>" if len(body) > len(shown) else "")


def sr_hash(path, limit_mb=300, block=1 << 20):
    """SHA-256 d'un fichier (None s'il dépasse limit_mb ou n'existe pas)."""
    import hashlib
    if not path or not os.path.isfile(path) or os.path.getsize(path) > limit_mb * 1024 * 1024:
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(block), b""):
            h.update(chunk)
    return h.hexdigest()


def sr_inventory(out_dir, skip_dirs=("_temp", "__pycache__")):
    """Fichiers produits : [{"rel", "size"}] triés (chemins relatifs au dossier de sortie, séparateur /)."""
    items = []
    for root, dirs, files in os.walk(out_dir):
        dirs[:] = sorted(d for d in dirs if d not in skip_dirs and not d.startswith("."))
        for fn in sorted(files):
            p = os.path.join(root, fn)
            items.append({"rel": os.path.relpath(p, out_dir).replace(os.sep, "/"), "size": os.path.getsize(p)})
    return sorted(items, key=lambda i: i["rel"])


def sr_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0


def sr_env():
    """Versions des logiciels (Python, NumPy, GDAL, Matplotlib, QGIS si disponibles)."""
    v = {"Python": platform.python_version(), "System": platform.system() + " " + platform.release()}
    if globals().get("PIPELINE_BUILD"):
        v["Script build"] = globals()["PIPELINE_BUILD"]            # version + empreinte du script (sha256, 12 caractères) : le rapport est lié à l'exacte version qui l'a produit
    for name, mod in (("NumPy", "numpy"), ("Matplotlib", "matplotlib")):
        try:
            v[name] = __import__(mod).__version__
        except Exception:
            pass
    try:
        from osgeo import gdal as _g
        v["GDAL"] = getattr(_g, "__version__", "") or _g.VersionInfo("RELEASE_NAME")
    except Exception:
        pass
    try:
        from qgis.core import Qgis as _q
        v["QGIS"] = getattr(_q, "QGIS_VERSION", "") or _q.version()
    except Exception:
        pass
    return v


def sr_render_array(arr, png_path, classes=None, title="", nodata=None, max_px=1400, cmap="viridis", label=""):
    """
    Image PNG d'un tableau 2D : valeurs de CLASSES (dict valeur -> (couleur hex ou RVB, libellé)) avec légende, sinon échelle continue avec barre de couleurs.
    Sous-échantillonne au plus proche voisin. Retourne le chemin ou None si matplotlib est absent.
    """
    try:
        import numpy as _np
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as _plt
        from matplotlib.patches import Patch
    except Exception:
        return None
    a = _np.asarray(arr)
    s = max(1, int(_np.ceil(max(a.shape) / float(max_px))))
    a = a[::s, ::s]
    fig, ax = _plt.subplots(figsize=(9, 7 * a.shape[0] / max(a.shape[1], 1) + 0.8))
    if classes:
        img = _np.ones(a.shape + (3,), float) * 0.97
        handles = []
        for val, (col, lab) in classes.items():
            rgb = tuple(c / 255.0 for c in col) if isinstance(col, (tuple, list)) else tuple(int(str(col).lstrip("#")[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
            img[a == val] = rgb
            handles.append(Patch(facecolor=rgb, label=lab))
        ax.imshow(img, interpolation="nearest")
        ax.legend(handles=handles, loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False, fontsize=9)
    else:
        m = _np.ma.masked_invalid(_np.where(a == nodata, _np.nan, a.astype(float)) if nodata is not None else a.astype(float))
        im = ax.imshow(m, cmap=cmap, interpolation="nearest")
        fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02, label=label)
    ax.set_title(title, fontsize=12)
    ax.set_xticks([])
    ax.set_yticks([])
    os.makedirs(os.path.dirname(png_path) or ".", exist_ok=True)
    fig.savefig(png_path, dpi=110, bbox_inches="tight", facecolor="white")
    _plt.close(fig)
    return png_path


def sr_quicklook(tif_path, png_path, classes=None, band=1, title="", nodata=None, max_px=1400, cmap="viridis", label=""):
    """Aperçu PNG d'un raster (lecture sous-échantillonnée par GDAL). None si le raster est absent ou si GDAL / matplotlib manquent."""
    if not tif_path or not os.path.isfile(tif_path):
        return None
    try:
        from osgeo import gdal as _g
        ds = _g.Open(tif_path)
        b = ds.GetRasterBand(band)
        sc = max(1, int(max(ds.RasterXSize, ds.RasterYSize) / float(max_px)))
        arr = b.ReadAsArray(buf_xsize=max(1, ds.RasterXSize // sc), buf_ysize=max(1, ds.RasterYSize // sc))
        nd = b.GetNoDataValue() if nodata is None else nodata
        ds = None
    except Exception:
        return None
    return sr_render_array(arr, png_path, classes, title, nd if not classes else None, max_px, cmap, label)


def sr_img_html(path, caption="", embed=True, rel_to=None):
    if not path or not os.path.isfile(path):
        return ""
    if embed:
        import base64
        with open(path, "rb") as f:
            src = "data:image/png;base64," + base64.b64encode(f.read()).decode()
    else:
        src = sr_esc(os.path.relpath(path, rel_to) if rel_to else path).replace("\\", "/")
    return f"<figure><img alt='{sr_esc(caption)}' src='{src}'><figcaption>{sr_esc(caption)}</figcaption></figure>"


def sr_overall(checks):
    """Statut global : FAIL s'il y a un échec, WARN s'il y a une alerte, sinon PASS."""
    st = [c[1] for c in checks]
    return "FAIL" if "FAIL" in st else ("WARN" if "WARN" in st else "PASS")


def write_stage_report(path, spec, embed=True):
    """
    Écrit le rapport HTML d'une étape (autonome, images incluses) et un fichier .json jumeau (pour l'index général). spec :
      stage ("02"), title, subtitle, lang, area, started (secondes epoch), out_dir, params {nom: valeur}, inputs [{"label", "path"}], summary [textes], checks [(nom, "PASS|WARN|FAIL|INFO", détail)],
      sections [{"id", "title", "intro", "tables": [(légende, lignes)], "images": [(légende, chemin_png)], "pre": texte, "notes": [textes]}], limits [textes], adapt [textes], references [textes].
    """
    import json as _json
    lang = spec.get("lang", "en")
    T = lambda k, **kw: sr_t(lang, k, **kw)
    e = sr_esc
    css = ("body{font-family:Segoe UI,Arial,sans-serif;margin:0;color:#1f2933;background:#fafafa}header{background:#0b3d5c;color:#fff;padding:22px 32px}header h1{margin:0;font-size:25px}header p{margin:4px 0 0;opacity:.85}"
           "main{max-width:1250px;margin:0 auto;padding:10px 32px 40px;background:#fff}h2{font-size:19px;margin-top:34px;border-bottom:2px solid #d9e2ec;padding-bottom:5px;color:#0b3d5c}h3{font-size:15px;margin-top:22px}"
           "table{border-collapse:collapse;margin:8px 0;font-size:12.5px}caption{text-align:left;font-weight:600;padding:4px 0}th,td{border:1px solid #cbd2d9;padding:3px 8px;text-align:left;vertical-align:top}th{background:#eef3f8}td.n{text-align:right}"
           "img{max-width:100%;height:auto;border:1px solid #e4e7eb}figure{margin:14px 0}figcaption{font-size:12px;color:#52606d}.small{color:#616e7c;font-size:12px}.scroll{overflow-x:auto}pre{background:#f4f6f8;padding:10px;overflow:auto;font-size:12px;white-space:pre-wrap}"
           ".badge{display:inline-block;padding:2px 9px;border-radius:11px;font-weight:600;font-size:12px;color:#fff}.PASS{background:#2e7d32}.WARN{background:#ef6c00}.FAIL{background:#c62828}.INFO{background:#546e7a}"
           "nav ul{columns:2;padding-left:18px}li{margin:3px 0}.box{background:#f0f7ff;border-left:4px solid #0b3d5c;padding:8px 14px;margin:10px 0}")
    checks = list(spec.get("checks", []))
    overall = sr_overall(checks) if checks else "INFO"
    gen = time.strftime("%Y-%m-%d %H:%M")
    dur = ""
    if spec.get("started"):
        dur = f"{(time.time() - spec['started']) / 60.0:.1f} min"
    sections = [s for s in spec.get("sections", [])]
    toc = [("summary", T("summary"))] + [(s.get("id") or f"s{i}", s["title"]) for i, s in enumerate(sections)] + [("checks", T("checks")), ("limits", T("limits")), ("adapt", T("adapt")), ("outputs", T("outputs")), ("refs", T("refs"))]
    out = [f"<!DOCTYPE html><html lang='{lang}'><head><meta charset='utf-8'><title>{e(spec.get('title', ''))}</title><style>{css}</style></head><body>",
           f"<header><h1>{e(T('stage'))} {e(spec.get('stage', ''))} — {e(spec.get('title', ''))}</h1><p>{e(spec.get('subtitle', ''))} · {e(spec.get('area', ''))} · <span class='badge {overall}'>{e(T(overall.lower()))}</span></p></header><main>"]
    out.append(f"<h2 id='run'>{T('run')}</h2><table><tr><th>{T('generated')}</th><td>{gen}</td><th>{T('duration')}</th><td>{e(dur or '—')}</td></tr><tr><th>{T('area')}</th><td>{e(spec.get('area', ''))}</td><th>{T('overall')}</th>"
               f"<td><span class='badge {overall}'>{e(T(overall.lower()))}</span></td></tr><tr><th>{T('software')}</th><td colspan=3>{e(', '.join(f'{k} {v}' for k, v in sr_env().items()))} · stage-report {SR_VERSION}</td></tr></table>")
    out.append("<nav><b>" + T("toc") + "</b><ul>" + "".join(f"<li><a href='#{e(i)}'>{e(t)}</a></li>" for i, t in toc) + "</ul></nav>")
    if spec.get("params"):
        out.append(f"<h3>{T('params')}</h3><table>" + "".join(f"<tr><th>{e(k)}</th><td>{e(v)}</td></tr>" for k, v in spec["params"].items()) + "</table>")
    if spec.get("inputs"):
        out.append(f"<h3>{T('inputs')}</h3><table><tr><th>{T('file')}</th><th>{T('path')}</th><th>{T('size')}</th><th>{T('sha')}</th></tr>")
        for it in spec["inputs"]:
            p = it.get("path") or ""
            sz = sr_size(os.path.getsize(p)) if p and os.path.isfile(p) else "—"
            sha = it.get("sha") or (sr_hash(p) if p and os.path.isfile(p) else None)
            out.append(f"<tr><td>{e(it.get('label', ''))}</td><td>{e(p)}</td><td>{e(sz)}</td><td><code>{e((sha or '—')[:16])}{'…' if sha else ''}</code></td></tr>")
        out.append("</table>")
    out.append(f"<h2 id='summary'>{T('summary')}</h2>")
    out.append("<div class='box'><ul>" + "".join(f"<li>{e(s)}</li>" for s in spec.get("summary", [])) + "</ul></div>" if spec.get("summary") else f"<p>{T('no_data')}</p>")
    for i, s in enumerate(sections):
        out.append(f"<h2 id='{e(s.get('id') or f's{i}')}'>{e(s['title'])}</h2>")
        if s.get("intro"):
            out.append(f"<p>{e(s['intro'])}</p>")
        for cap, rows in s.get("tables", []):
            out.append(sr_table(rows, cap) or f"<p class='small'>{e(cap)} — {T('no_data')}</p>")
        for cap, img in s.get("images", []):
            out.append(sr_img_html(img, cap, embed, os.path.dirname(path)))
        if s.get("pre"):
            out.append(f"<pre>{e(s['pre'])}</pre>")
        for n in s.get("notes", []):
            out.append(f"<p class='small'>{e(n)}</p>")
    out.append(f"<h2 id='checks'>{T('checks')}</h2>")
    out.append(f"<table><tr><th>{T('check')}</th><th>{T('status')}</th><th>{T('detail')}</th></tr>" + "".join(f"<tr><td>{e(c[0])}</td><td><span class='badge {e(c[1])}'>{e(T(str(c[1]).lower()))}</span></td><td>{e(c[2])}</td></tr>" for c in checks) + "</table>" if checks else f"<p>{T('no_data')}</p>")
    out.append(f"<h2 id='limits'>{T('limits')}</h2><ul>" + "".join(f"<li>{e(x)}</li>" for x in spec.get("limits", [])) + "</ul>")
    out.append(f"<h2 id='adapt'>{T('adapt')}</h2><ul>" + "".join(f"<li>{e(x)}</li>" for x in spec.get("adapt", [])) + "</ul>")
    inv = sr_inventory(spec["out_dir"]) if spec.get("out_dir") and os.path.isdir(spec["out_dir"]) else []
    out.append(f"<h2 id='outputs'>{T('outputs')}</h2><table><tr><th>{T('file')}</th><th>{T('size')}</th></tr>" + "".join(f"<tr><td>{e(i['rel'])}</td><td class=n>{e(sr_size(i['size']))}</td></tr>" for i in inv[:400]) + "</table>"
               + (f"<p class='small'>… {len(inv) - 400} more files</p>" if len(inv) > 400 else ""))
    out.append(f"<h2 id='refs'>{T('refs')}</h2><ul>" + "".join(f"<li>{e(x)}</li>" for x in spec.get("references", [])) + f"</ul><p class='small'>{e(spec.get('title', ''))} · {gen} · stage-report {SR_VERSION}</p></main></body></html>")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(out))
    with open(os.path.splitext(path)[0] + ".json", "w", encoding="utf-8") as f:
        _json.dump({"stage": spec.get("stage"), "title": spec.get("title"), "area": spec.get("area"), "status": overall, "generated": gen, "html": os.path.basename(path), "n_checks": len(checks),
                    "n_fail": sum(1 for c in checks if c[1] == "FAIL"), "n_warn": sum(1 for c in checks if c[1] == "WARN")}, f, indent=2, ensure_ascii=False)
    return path


def build_master_index(root, lang="en", title="SDG 15.3.1 — stage reports"):
    """Page d'accueil `index.html` : liste, dans l'ordre des étapes, tous les rapports `Stage_Report_*.html` trouvés sous `root` (avec leur statut)."""
    import json as _json
    found = []
    for r, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ("_temp", "__pycache__")]
        for fn in files:
            if fn.startswith("Stage_Report_") and fn.endswith(".json"):
                try:
                    with open(os.path.join(r, fn), encoding="utf-8") as f:
                        d = _json.load(f)
                    d["rel"] = os.path.relpath(os.path.join(r, d["html"]), root).replace(os.sep, "/")
                    found.append(d)
                except Exception:
                    continue
    found.sort(key=lambda d: (str(d.get("stage")), d.get("generated", "")))
    e = sr_esc
    rows = "".join(f"<tr><td>{e(d.get('stage'))}</td><td><a href='{e(d['rel'])}'>{e(d.get('title'))}</a></td><td>{e(d.get('area'))}</td><td><span class='badge {e(d.get('status'))}'>{e(sr_t(lang, str(d.get('status')).lower()))}</span></td>"
                   f"<td>{d.get('n_fail', 0)} / {d.get('n_warn', 0)}</td><td>{e(d.get('generated'))}</td></tr>" for d in found)
    css = "body{font-family:Segoe UI,Arial,sans-serif;margin:30px auto;max-width:1000px}table{border-collapse:collapse}th,td{border:1px solid #ccc;padding:5px 10px}th{background:#eef3f8}.badge{padding:2px 9px;border-radius:11px;color:#fff;font-weight:600}.PASS{background:#2e7d32}.WARN{background:#ef6c00}.FAIL{background:#c62828}.INFO{background:#546e7a}"
    html = (f"<!DOCTYPE html><html lang='{lang}'><head><meta charset='utf-8'><title>{e(title)}</title><style>{css}</style></head><body><h1>{e(title)}</h1><table><tr><th>{sr_t(lang, 'stage')}</th><th>Report</th><th>{sr_t(lang, 'area')}</th>"
            f"<th>{sr_t(lang, 'status')}</th><th>FAIL / WARN</th><th>{sr_t(lang, 'generated')}</th></tr>{rows}</table></body></html>")
    p = os.path.join(root, "index.html")
    with open(p, "w", encoding="utf-8") as f:
        f.write(html)
    return p


def sr_find_files(root, pattern, max_depth=4):
    """Fichiers dont le nom correspond à l'expression régulière `pattern`, recherchés dans `root` et ses sous-dossiers (profondeur limitée). Chemins triés."""
    rx = re.compile(pattern)
    out = []
    base_depth = os.path.normpath(root).count(os.sep)
    for r, dirs, files in os.walk(root):
        if os.path.normpath(r).count(os.sep) - base_depth >= max_depth:
            dirs[:] = []
        dirs[:] = [d for d in dirs if d not in ("_temp", "__pycache__") and not d.startswith(".")]
        out += [os.path.join(r, f) for f in files if rx.search(f)]
    return sorted(out)


def sr_register(json_path, stage, title, area, status, html_name, n_fail=0, n_warn=0):
    """Enregistre dans l'index général un rapport HTML DÉJÀ écrit par un script (jumeau JSON à côté du HTML)."""
    import json as _json
    with open(json_path, "w", encoding="utf-8") as f:
        _json.dump({"stage": stage, "title": title, "area": area, "status": status, "generated": time.strftime("%Y-%m-%d %H:%M"), "html": html_name, "n_checks": n_fail + n_warn, "n_fail": n_fail, "n_warn": n_warn}, f, indent=2, ensure_ascii=False)
    return json_path
# <<< STAGE_REPORT_END


def sensitivity_tables(acc, starts, ref_start, lang="en"):
    """Tableaux de sortie depuis les cumuls : comparaison des années de début, et pixels « améliorés » qui ne le restent pas."""
    T = lambda a, b: a if lang == "en" else b
    rows = [[T("Variant", "Variante"), T("Start year", "Année de début"), T("Years", "Années"), T("Valid pixels", "Pixels valides"), T("Improving %", "Amélioration %"), T("Stable %", "Stable %"), T("Declining %", "Déclin %"),
             T("Improving % (p<0.05)", "Amélioration % (p<0,05)"), T("Declining % (p<0.05)", "Déclin % (p<0,05)"), T("Median Sen slope (NDVI/yr)", "Pente de Sen médiane (NDVI/an)"), T("State improved %", "État amélioré %"), T("State degraded %", "État dégradé %"),
             T("LPD-3 improved % (no Performance)", "LPD-3 amélioré % (sans Performance)"), T("LPD-3 degraded % (no Performance)", "LPD-3 dégradé % (sans Performance)"), T("Δ improving vs reference (points)", "Δ amélioration vs référence (points)"), T("Description", "Description")]]
    out = {}
    for var in sorted({k[0] for k in acc["traj"]}):
        ref = None
        for s in starts:
            key = (var, s)
            if key not in acc["traj"]:
                continue
            c = acc["traj"][key]
            n = c["n"]
            f = lambda k, d=c: (100.0 * d[k] / n if n else float("nan"))
            imp = f("imp")
            if s == ref_start:
                ref = imp
            slopes = np.concatenate(acc["slopes"][key]) if acc["slopes"].get(key) else np.array([])
            med = float(np.nanmedian(slopes)) if slopes.size and np.isfinite(slopes).any() else float("nan")
            ns = c["n_state"]
            fs = lambda k: (100.0 * c[k] / ns if ns else float("nan"))
            nl = c["n_lpd"]
            fl = lambda k: (100.0 * c[k] / nl if nl else float("nan"))
            fmt = lambda v, nd=2: "" if v != v else f"{v:.{nd}f}"
            out[key] = {"imp": imp, "stable": f("stable"), "dec": f("dec"), "imp_p": f("imp_p"), "dec_p": f("dec_p"), "slope": med, "n": n, "n_years": c["n_years"], "lpd_imp": fl("lpd_imp"), "lpd_deg": fl("lpd_deg")}
            rows.append([var, s, c["n_years"], f"{n:,}", fmt(imp), fmt(f("stable")), fmt(f("dec")), fmt(f("imp_p")), fmt(f("dec_p")), fmt(med, 5), fmt(fs("st_imp")), fmt(fs("st_deg")), fmt(fl("lpd_imp")), fmt(fl("lpd_deg")), "" if (ref is None or imp != imp) else f"{imp - ref:+.2f}", vlabel(var, lang)])
    return rows, out


def retention_table(acc, ref_start, alt_start, lang="en"):
    T = lambda a, b: a if lang == "en" else b
    labs = {-1: T("Declining", "Déclin"), 0: T("Stable", "Stable"), 1: T("Improving", "Amélioration")}
    rows, summ = [], {}
    for var in sorted(acc["trans"]):                 # acc["trans"] est indexé par la variante (pas par un couple)
        M = acc["trans"][var]
        rows.append([T(f"Variant: {vlabel(var, lang)} — start {ref_start} (rows) → start {alt_start} (columns), pixels", f"Variante : {vlabel(var, lang)} — début {ref_start} (lignes) → début {alt_start} (colonnes), pixels")] + [labs[j] for j in (-1, 0, 1)] + [T("Total", "Total")])
        for i, li in enumerate((-1, 0, 1)):
            rows.append([labs[li]] + [f"{int(M[i, j]):,}" for j in range(3)] + [f"{int(M[i].sum()):,}"])
        n_imp = int(M[2].sum())
        keep = int(M[2, 2])
        summ[var] = {"imp_ref": n_imp, "imp_kept": keep, "kept_pct": (100.0 * keep / n_imp) if n_imp else float("nan"), "to_stable": int(M[2, 1]), "to_dec": int(M[2, 0]), "new_imp": int(M[0, 2] + M[1, 2])}
    return rows, summ


def year_table(series, rain, lang="en"):
    T = lambda a, b: a if lang == "en" else b
    zy = zscores([r[1] for r in series])
    rv = [rain.get(r[0]) if rain else None for r in series]
    zr = zscores([np.nan if v is None else v for v in rv]) if rain else np.full(len(series), np.nan)
    rows = [[T("Year", "Année"), T("Mean productivity", "Productivité moyenne"), T("z (productivity)", "z (productivité)"), T("Wet-season rain (mm)", "Pluie de saison humide (mm)"), T("z (rain)", "z (pluie)"), T("Dry year (z ≤ −1)", "Année sèche (z ≤ −1)")]]
    for i, (y, m, n) in enumerate(series):
        dry = (zr[i] == zr[i]) and zr[i] <= DROUGHT_Z
        rows.append([y, f"{m:.4f}" if m == m else "", f"{zy[i]:+.2f}" if zy[i] == zy[i] else "", "" if rv[i] is None else f"{rv[i]:.0f}", f"{zr[i]:+.2f}" if zr[i] == zr[i] else "", T("DRY", "SÈCHE") if dry else ""])
    return rows, zy, zr


def sensitivity_checks(summ_stats, ret, series, zy, zr, years, ref_start, alt_start, lang="en"):
    T = lambda a, b: a if lang == "en" else b
    checks = []
    ny = len(years)
    checks.append((T("Years found in the productivity stack", "Années trouvées dans la pile de productivité"), "PASS" if ny >= 20 else "WARN", T(f"{ny} years ({min(years)}–{max(years)})", f"{ny} années ({min(years)}–{max(years)})")))
    low_start = [y for i, (y, _m, _n) in enumerate(series) if i < 4 and zy[i] == zy[i] and zy[i] <= -1.0]
    dry_start = [y for i, (y, _m, _n) in enumerate(series) if i < 5 and zr[i] == zr[i] and zr[i] <= DROUGHT_Z]
    if np.isfinite(zy).any():
        checks.append((T("Weak productivity at the start of the series", "Productivité faible au début de la série"), "WARN" if low_start else "INFO",
                       (T(f"mean productivity z ≤ −1 in {', '.join(map(str, low_start))}", f"productivité moyenne z ≤ −1 en {', '.join(map(str, low_start))}") if low_start else T("no low-productivity year among the first four", "aucune année de faible productivité parmi les quatre premières"))
                       + (T(f"; wet-season rain z ≤ {DROUGHT_Z:g} in {', '.join(map(str, dry_start))}", f" ; pluie de saison humide z ≤ {DROUGHT_Z:g} en {', '.join(map(str, dry_start))}") if dry_start else T("; no dry wet-season among the first years (a low start is then NOT explained by the season total: check the rain window and the data quality of the first years)", " ; aucune saison humide sèche parmi les premières années (un début faible n'est alors PAS expliqué par le total de la saison : vérifier la fenêtre de pluie et la qualité des données des premières années)") if low_start else "")))
    for var in sorted({k[0] for k in summ_stats}):
        a, b = summ_stats.get((var, ref_start)), summ_stats.get((var, alt_start))
        if a and b and a["imp"] == a["imp"] and b["imp"] == b["imp"]:
            d = b["imp"] - a["imp"]
            rel = 100.0 * d / a["imp"] if a["imp"] else float("nan")
            label = T("Improving share, ", "Part en amélioration, ") + vlabel(var, lang)
            checks.append((label + f": {ref_start} → {alt_start}", "WARN" if d <= -SPREAD_WARN_POINTS else "PASS",
                           T(f"{a['imp']:.1f} % → {b['imp']:.1f} % ({d:+.1f} points, {rel:+.0f} % relative)", f"{a['imp']:.1f} % → {b['imp']:.1f} % ({d:+.1f} points, {rel:+.0f} % en relatif)")
                           + (T(" — the improvement depends on the FIRST years of the series (productivity is low there: see the year table), not on the land", " — l'amélioration dépend des PREMIÈRES années de la série (la productivité y est faible : voir le tableau des années), pas de la terre") if d <= -SPREAD_WARN_POINTS else T(" — the improvement does not depend on the first years of the series", " — l'amélioration ne dépend pas des premières années de la série"))))
    for var, r in ret.items():
        if r["imp_ref"]:
            checks.append((T(f"Improving pixels of start {ref_start} still improving at start {alt_start} ({vlabel(var, lang)})", f"Pixels en amélioration (début {ref_start}) qui le restent (début {alt_start}) ({vlabel(var, lang)})"), "INFO",
                           T(f"{r['kept_pct']:.0f} % kept ({r['imp_kept']:,} of {r['imp_ref']:,} px); {r['to_stable']:,} become stable and {r['to_dec']:,} declining; {r['new_imp']:,} pixels become improving",
                             f"{r['kept_pct']:.0f} % conservés ({r['imp_kept']:,} sur {r['imp_ref']:,} px) ; {r['to_stable']:,} deviennent stables et {r['to_dec']:,} en déclin ; {r['new_imp']:,} pixels deviennent en amélioration")))
    return checks


def rain_window_rows(info, lang="en"):
    T = lambda a, b: a if lang == "en" else b
    rows = [[T("Window", "Fenêtre"), T("Months", "Mois"), "R²", T("Slope (NDVI per 100 mm)", "Pente (NDVI par 100 mm)"), T("Years", "Années"), T("Residual of the 1st / 2nd / 3rd year (sd)", "Résidu de la 1re / 2e / 3e année (écarts-types)"), ""]]
    for r in info["rows"]:
        fy = " / ".join(f"{r['first'][y]:+.2f}" for y in sorted(r["first"]))
        tag = (T("stage 02", "étape 02") if r["window"] == DEFAULT_RAIN_WINDOW else "") + (" ★ " + T("best R²", "meilleur R²") if info["best"] and r["window"] == info["best"]["window"] else "")
        mm = ("–".join(str(m) for m in r["months"]))
        rows.append([r["window"], mm, f"{r['r2']:.2f}", f"{100 * r['slope']:.3f}", r["n"], fy, tag.strip()])
    return rows


def stage_report(out_dir, acc, starts, series, rain, ref_start, alt_start, t0, params, inputs, area_name, files_png, lang="en", log=print, rain_info=None, cover=None):
    T = lambda a, b: a if lang == "en" else b
    tb, summ = sensitivity_tables(acc, starts, ref_start, lang)
    rt, ret = retention_table(acc, ref_start, alt_start, lang)
    yt, zy, zr = year_table(series, rain, lang)
    years = [r[0] for r in series]
    checks = sensitivity_checks(summ, ret, series, zy, zr, years, ref_start, alt_start, lang)
    if cover:
        cc = coverage_check(cover["valid_px"], cover["px_ha"], cover["study_ha"], cover["masked"], lang)
        if cc:
            checks.insert(1, (T("Area analysed vs the study area", "Surface analysée par rapport à la zone d'étude"), cc[0], cc[1]))
    if rain_info and rain_info.get("best") and rain_info.get("default"):
        b_, d_ = rain_info["best"], rain_info["default"]
        gain = b_["r2"] - d_["r2"]
        checks.append((T("Rain window used by stage 02", "Fenêtre de pluie de l'étape 02"), "WARN" if gain >= 0.10 else "PASS",
                       T(f"{d_['window']} explains R² = {d_['r2']:.2f} of the mean productivity; the best window, {b_['window']}, explains {b_['r2']:.2f} ({gain:+.2f})", f"{d_['window']} explique R² = {d_['r2']:.2f} de la productivité moyenne ; la meilleure fenêtre, {b_['window']}, explique {b_['r2']:.2f} ({gain:+.2f})")
                       + (T(": a weak rain adjustment leaves rainfall effects in the residuals; compare the rain-adjusted variants below", " : un ajustement faible laisse des effets de pluie dans les résidus ; comparer les variantes corrigées ci-dessous") if gain >= 0.10 else "")))
        fd = d_["first"]
        if fd:
            worst = min(fd.values())
            checks.append((T("Productivity of the first years after the rain adjustment", "Productivité des premières années après correction de la pluie"), "WARN" if worst <= -1.0 else "PASS",
                           T(f"residuals of the first years with {d_['window']}: " + ", ".join(f"{y} {v:+.2f} sd" for y, v in sorted(fd.items())) + f"; with {b_['window']}: " + ", ".join(f"{y} {v:+.2f} sd" for y, v in sorted(b_['first'].items())) + ("; years that stay far below what the rain explains point to something else than the season rain: lagged drought effect, data quality of the first years, or management" if worst <= -1.0 else ""),
                             f"résidus des premières années avec {d_['window']} : " + ", ".join(f"{y} {v:+.2f} é.-t." for y, v in sorted(fd.items())) + f" ; avec {b_['window']} : " + ", ".join(f"{y} {v:+.2f} é.-t." for y, v in sorted(b_['first'].items())) + (" ; des années qui restent très en dessous de ce que la pluie explique relèvent d'autre chose que la pluie de saison : effet différé d'une sécheresse, qualité des premières années, ou gestion" if worst <= -1.0 else ""))))
    summary = []
    for var in sorted({k[0] for k in summ}):
        a, b = summ.get((var, ref_start)), summ.get((var, alt_start))
        if a and b:
            summary.append(T(f"Productivity {vlabel(var, lang)}: improving trajectory {a['imp']:.1f} % (start {ref_start}) → {b['imp']:.1f} % (start {alt_start}); declining {a['dec']:.1f} % → {b['dec']:.1f} %",
                             f"Productivité {vlabel(var, lang)} : trajectoire en amélioration {a['imp']:.1f} % (début {ref_start}) → {b['imp']:.1f} % (début {alt_start}) ; déclin {a['dec']:.1f} % → {b['dec']:.1f} %"))
    sections = [{"id": "cmp", "title": T("Trajectory, state and LPD by start year", "Trajectoire, état et LPD selon l'année de début"),
                 "intro": T("Same definitions as stage 02, recomputed on the window [start year, last year]. LPD-3 here is the stage-02 rule with the Performance component switched off (it can only turn some improving pixels into degraded).", "Mêmes définitions que l'étape 02, recalculées sur la fenêtre [année de début, dernière année]. Le LPD-3 est ici la règle de l'étape 02 sans la composante Performance (elle ne peut que faire basculer certains pixels améliorés en dégradés)."),
                 "tables": [("", tb)], "images": [(T("Share of the trajectory classes by start year", "Part des classes de trajectoire selon l'année de début"), files_png.get("shares"))]},
                {"id": "keep", "title": T(f"Which improving pixels remain (start {ref_start} → {alt_start})", f"Quels pixels en amélioration restent (début {ref_start} → {alt_start})"), "tables": [("", rt)]},
                {"id": "years", "title": T("The years: productivity and wet-season rain", "Les années : productivité et pluie de saison humide"), "tables": [("", yt)], "images": [(T("Mean productivity, rainfall and the two trends", "Productivité moyenne, pluie et les deux tendances"), files_png.get("series"))]}]
    if rain_info and rain_info.get("rows"):
        sections.insert(2, {"id": "rainwin", "title": T("Which rain window explains the productivity?", "Quelle fenêtre de pluie explique la productivité ?"), "intro": T("R² of the regression of the mean annual productivity on the rain of each window, and how far the first three years sit from the fitted line. 20–26 points only: an indication, not a proof.", "R² de la régression de la productivité moyenne annuelle sur la pluie de chaque fenêtre, et écart des trois premières années à la droite ajustée. 20 à 26 points seulement : une indication, pas une preuve."), "tables": [("", rain_window_rows(rain_info, lang))]})
    L = [T("This is not a full LPD: the Performance component is not recomputed.", "Ce n'est pas un LPD complet : la composante Performance n'est pas recalculée."),
         T("A lower improving share when the first years are removed is compatible with a drought start, but also with a real recovery; read it with the year table (rain and mean productivity).", "Une part en amélioration plus faible quand on retire les premières années est compatible avec un départ en sécheresse, mais aussi avec une vraie reprise ; la lire avec le tableau des années (pluie et productivité moyenne)."),
         T("A shorter series has less statistical power: fewer pixels reach the significance or tau threshold, which can lower the improving AND declining shares.", "Une série plus courte a moins de puissance statistique : moins de pixels atteignent le seuil de signification ou de tau, ce qui peut baisser les parts en amélioration ET en déclin."),
         T("The rain-adjusted variant is fitted on each window and needs a reliable rain–NDVI regression (R² ≥ 0.20); elsewhere the raw series is used, as in stage 02.", "La variante corrigée de la pluie est ajustée sur chaque fenêtre et exige une régression pluie–NDVI fiable (R² ≥ 0,20) ; ailleurs la série brute est utilisée, comme à l'étape 02.")]
    A = [T("Provide the annual productivity stack of the new area (one band per year) and its daily rainfall CSV.", "Fournir la pile de productivité annuelle de la nouvelle zone (une bande par année) et son CSV de pluie journalière."),
         T("Set START_YEARS, BASELINE_END and RECENT_YEARS to the same values as stage 02.", "Régler START_YEARS, BASELINE_END et RECENT_YEARS comme à l'étape 02."),
         T("Use the drought years of the new area (year table) to choose the alternative start year.", "Utiliser les années de sécheresse de la nouvelle zone (tableau des années) pour choisir l'année de début alternative.")]
    R = ["UNCCD. Good Practice Guidance for SDG Indicator 15.3.1 (version 2) and its Addendum.", "Sen, P. K. (1968). Estimates of the regression coefficient based on Kendall's tau. JASA 63, 1379–1389.", "Mann, H. B. (1945). Nonparametric tests against trend. Econometrica 13, 245–259."]
    spec = {"stage": "02B", "title": T("Sensitivity of the productivity trend to the start year", "Sensibilité de la tendance de productivité à l'année de début"), "subtitle": T("Is the improvement a drought-start effect?", "L'amélioration est-elle un effet de départ en sécheresse ?"), "lang": lang, "area": area_name, "started": t0, "out_dir": out_dir,
            "params": params, "inputs": inputs, "summary": summary, "checks": checks, "sections": sections, "limits": L, "adapt": A, "references": R}
    path = os.path.join(out_dir, "Stage_Report_02B_Trend_Start_Sensitivity.html")
    write_stage_report(path, spec)
    with open(os.path.join(out_dir, "Trend_Start_Sensitivity.csv"), "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f, delimiter=";").writerows(tb)
    with open(os.path.join(out_dir, "Annual_Mean_Productivity_and_Rain.csv"), "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f, delimiter=";").writerows(yt)
    log("[Rapport HTML] " + path)
    return path


def make_figures(out_dir, acc, starts, series, rain, ref_start, alt_start, lang="en"):
    """Deux figures PNG (ou {} si matplotlib manque) : parts des classes par année de début ; productivité moyenne, pluie et deux tendances."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return {}
    T = lambda a, b: a if lang == "en" else b
    os.makedirs(os.path.join(out_dir, "_temp"), exist_ok=True)
    files = {}
    _tb, summ = sensitivity_tables(acc, starts, ref_start, lang)
    vars_ = sorted({k[0] for k in summ})
    fig, axes = plt.subplots(1, len(vars_), figsize=(5.8 * len(vars_), 4.4), squeeze=False)
    for ax, var in zip(axes[0], vars_):
        ss = [s for s in starts if (var, s) in summ]
        ax.plot(ss, [summ[(var, s)]["imp"] for s in ss], marker="o", color="#2e7d32", label=T("Improving", "Amélioration"))
        ax.plot(ss, [summ[(var, s)]["dec"] for s in ss], marker="o", color="#c62828", label=T("Declining", "Déclin"))
        ax.plot(ss, [summ[(var, s)]["stable"] for s in ss], marker="o", color="#9e9e9e", label=T("Stable", "Stable"))
        ax.set_title(vlabel(var, lang), fontsize=9)
        ax.set_xlabel(T("Start year of the series", "Année de début de la série"))
        ax.set_ylabel(T("% of valid pixels", "% des pixels valides"))
        ax.legend(frameon=False, fontsize=8)
    p1 = os.path.join(out_dir, "_temp", "shares.png")
    fig.savefig(p1, dpi=110, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    files["shares"] = p1
    ys = [r[0] for r in series]
    mv = [r[1] for r in series]
    fig, ax = plt.subplots(figsize=(10, 4.4))
    ax.plot(ys, mv, marker="o", color="#1565c0", label=T("Mean productivity", "Productivité moyenne"))
    for s, col in ((ref_start, "#c62828"), (alt_start, "#2e7d32")):
        m = [(y, v) for y, v in zip(ys, mv) if y >= s and v == v]
        if len(m) > 3:
            k, c = np.polyfit([a for a, _b in m], [b for _a, b in m], 1)
            ax.plot([m[0][0], m[-1][0]], [c + k * m[0][0], c + k * m[-1][0]], color=col, linestyle="--", label=T(f"Linear trend from {s}", f"Tendance linéaire depuis {s}"))
    ax.set_ylabel(T("Mean productivity", "Productivité moyenne"))
    if rain:
        ax2 = ax.twinx()
        ax2.bar([y for y in ys if rain.get(y) is not None], [rain[y] for y in ys if rain.get(y) is not None], color="#90caf9", alpha=0.45)
        ax2.set_ylabel(T("Wet-season rain (mm)", "Pluie de saison humide (mm)"))
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    p2 = os.path.join(out_dir, "_temp", "series.png")
    fig.savefig(p2, dpi=110, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    files["series"] = p2
    return files


# ============================================================================
# 3. CUMULS PAR DALLE + COUCHE GDAL / QGIS (relue, non exécutable hors QGIS)
# ============================================================================
def new_acc():
    return {"traj": {}, "slopes": {}, "trans": {}}


def add_tile(acc, P, years, R, starts, ref_start, alt_start, end, R_alt=None):
    """Ajoute une dalle P (années, lignes, colonnes) aux cumuls (additifs : l'ordre et le découpage des dalles ne comptent pas). Retourne les classes de trajectoire (début de référence et alternatif) pour l'écriture des rasters."""
    nyr, rows, cols = P.shape
    Pf = P.reshape(nyr, rows * cols)
    keep = {}
    for s in starts:
        res = analyse_start(Pf, years, R, s, end, R_alt)
        for var, d in res.items():
            key = (var, s)
            c = acc["traj"].setdefault(key, {"n": 0, "imp": 0, "stable": 0, "dec": 0, "imp_p": 0, "dec_p": 0, "n_state": 0, "st_imp": 0, "st_deg": 0, "n_lpd": 0, "lpd_imp": 0, "lpd_deg": 0, "n_years": int(((np.asarray(years) >= s) & (np.asarray(years) <= end)).sum())})
            v = d["traj_valid"]
            c["n"] += int(v.sum())
            c["imp"] += int(((d["traj_tau"] == 1) & v).sum())
            c["dec"] += int(((d["traj_tau"] == -1) & v).sum())
            c["stable"] += int(((d["traj_tau"] == 0) & v).sum())
            c["imp_p"] += int(((d["traj_p"] == 1) & v).sum())
            c["dec_p"] += int(((d["traj_p"] == -1) & v).sum())
            sv = d["state"] > 0
            c["n_state"] += int(sv.sum())
            c["st_imp"] += int(((d["state"] == 3) & sv).sum())
            c["st_deg"] += int(((d["state"] == 1) & sv).sum())
            lv = d["valid"]
            c["n_lpd"] += int(lv.sum())
            c["lpd_imp"] += int(((d["lpd3"] == 1) & lv).sum())
            c["lpd_deg"] += int(((d["lpd3"] == -1) & lv).sum())
            acc["slopes"].setdefault(key, []).append(d["slope"][v])
            if s in (ref_start, alt_start):
                keep[(var, s)] = d
    for var in {k[0] for k in keep}:
        a, b = keep.get((var, ref_start)), keep.get((var, alt_start))
        if a is not None and b is not None:
            M = transition_counts(a["traj_tau"], a["traj_valid"], b["traj_tau"], b["traj_valid"])
            acc["trans"][var] = acc["trans"].get(var, np.zeros((3, 3), np.int64)) + M
    return keep


def read_stack(path, start_year=None):
    """(années, tableau (années, lignes, colonnes) float32 avec NaN, dataset GDAL) : NoData -> NaN ; productivité 0 -> NaN (comme l'étape 02)."""
    from osgeo import gdal
    ds = gdal.Open(path, gdal.GA_ReadOnly)
    if ds is None:
        raise RuntimeError(f"Raster illisible : {path}")
    years = band_year_list([ds.GetRasterBand(i + 1).GetDescription() for i in range(ds.RasterCount)], start_year)
    out = np.empty((ds.RasterCount, ds.RasterYSize, ds.RasterXSize), np.float32)
    for i in range(ds.RasterCount):
        b = ds.GetRasterBand(i + 1)
        a = b.ReadAsArray().astype(np.float32)
        nd = b.GetNoDataValue()
        if nd is not None and np.isfinite(float(nd)):
            a[a == float(nd)] = np.nan
        a[a <= -9998] = np.nan
        a[a == 0] = np.nan
        out[i] = a
    order = np.argsort(years)
    return [years[i] for i in order], out[order], ds


def tile_family(path):
    folder, base = os.path.split(path)
    m = re.match(r"^(.*?)-\d{10}-\d{10}\.tif$", base, re.I)
    if not m:
        return [path]
    pre = m.group(1)
    return sorted(os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".tif") and re.match(re.escape(pre) + r"-\d{10}-\d{10}\.tif$", f, re.I))


def rasterize_study_area(shp_path, ref_ds):
    """Masque booléen (lignes, colonnes) de la zone d'étude sur la grille du raster de productivité : le shapefile est reprojeté dans le système du raster si nécessaire."""
    from osgeo import gdal, ogr, osr
    src = ogr.Open(shp_path)
    if src is None:
        raise RuntimeError(f"Shapefile illisible : {shp_path}")
    lyr = src.GetLayer(0)
    tgt = osr.SpatialReference()
    tgt.ImportFromWkt(ref_ds.GetProjection())
    tgt.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    mem_v = ogr.GetDriverByName("Memory").CreateDataSource("zone")
    out_l = mem_v.CreateLayer("zone", tgt, ogr.wkbMultiPolygon)
    s_srs = lyr.GetSpatialRef()
    tr = None
    if s_srs is not None:
        s_srs = s_srs.Clone()
        s_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        if not s_srs.IsSame(tgt):
            tr = osr.CoordinateTransformation(s_srs, tgt)
    for ft in lyr:
        g = ft.GetGeometryRef()
        if g is None:
            continue
        g = g.Clone()
        if tr is not None:
            g.Transform(tr)
        nf = ogr.Feature(out_l.GetLayerDefn())
        nf.SetGeometry(g)
        out_l.CreateFeature(nf)
    m = gdal.GetDriverByName("MEM").Create("", ref_ds.RasterXSize, ref_ds.RasterYSize, 1, gdal.GDT_Byte)
    m.SetGeoTransform(ref_ds.GetGeoTransform())
    m.SetProjection(ref_ds.GetProjection())
    gdal.RasterizeLayer(m, [1], out_l, burn_values=[1])
    return m.GetRasterBand(1).ReadAsArray() == 1


def write_class_raster(path, arr, ref_ds, nodata=127):
    from osgeo import gdal
    ds = gdal.GetDriverByName("GTiff").Create(path, ref_ds.RasterXSize, ref_ds.RasterYSize, 1, gdal.GDT_Int16, options=["COMPRESS=LZW"])
    ds.SetGeoTransform(ref_ds.GetGeoTransform())
    ds.SetProjection(ref_ds.GetProjection())
    b = ds.GetRasterBand(1)
    b.SetNoDataValue(nodata)
    b.WriteArray(arr.astype(np.int16))
    ds.FlushCache()
    ds = None


def run_sensitivity(stack_path, rain_csv, out_dir, start_year_first_band=None, lang=REPORT_LANG, log=print, reader=None, writer=None, starts=None, study_shp=None, mask_fn=None):
    t0 = time.time()
    os.makedirs(out_dir, exist_ok=True)
    reader = reader or read_stack
    writer = writer or write_class_raster
    mask_fn = mask_fn or ((lambda ds: rasterize_study_area(study_shp, ds)) if study_shp else None)
    starts = list(starts or START_YEARS)
    tiles = tile_family(stack_path)
    daily = parse_daily_rain(open(rain_csv, encoding="utf-8-sig").read()) if rain_csv else None
    # ---- passe 1 : années et productivité moyenne (cumuls additifs) ; une dalle unique reste en mémoire
    years, kept_tile, sum_p, cnt_p, px_ha = None, None, None, None, None
    for tp in tiles:
        yrs, P, ds = reader(tp, start_year_first_band)
        if years is None:
            years = yrs
        elif yrs != years:
            raise RuntimeError("Les dalles n'ont pas les mêmes années en bandes.")
        if mask_fn is not None:
            apply_study_mask(P, mask_fn(ds))
        if px_ha is None and hasattr(ds, "GetGeoTransform"):
            gt_ = ds.GetGeoTransform()
            px_ha = abs(gt_[1] * gt_[5]) / 10000.0
        ok = np.isfinite(P) & (P != 0)
        s_ = np.where(ok, P, 0.0).sum(axis=(1, 2)).astype(np.float64)
        n_ = ok.sum(axis=(1, 2)).astype(np.int64)
        sum_p, cnt_p = (s_, n_) if sum_p is None else (sum_p + s_, cnt_p + n_)
        if len(tiles) == 1:
            kept_tile = (P, ds)
        log(f"[02B] dalle lue : {os.path.basename(tp)}")
    end = int(max(years))
    starts = [s_y for s_y in starts if s_y < end - 8]
    series = [(int(y), float(sum_p[i] / cnt_p[i]) if cnt_p[i] else float("nan"), int(cnt_p[i])) for i, y in enumerate(years)]
    # ---- fenêtres de pluie : celle de l'étape 02, et la meilleure si elle explique nettement mieux la productivité
    rain, rain_alt, rain_info = None, None, None
    VARIANT_LABELS.clear()
    if daily:
        rows_w, best = rain_window_table(series, daily)
        default = next((r for r in rows_w if r["window"] == DEFAULT_RAIN_WINDOW), None)
        rain_info = {"rows": rows_w, "best": best, "default": default}
        rain = season_rain(daily, years, RAIN_WINDOWS[DEFAULT_RAIN_WINDOW])
        VARIANT_LABELS["rain_adjusted"] = DEFAULT_RAIN_WINDOW
        alt_name = None
        if ALT_RAIN_WINDOW == "auto":
            if best and default and best["window"] != DEFAULT_RAIN_WINDOW and best["r2"] - default["r2"] >= MIN_R2_GAIN:
                alt_name = best["window"]
        elif ALT_RAIN_WINDOW in RAIN_WINDOWS and ALT_RAIN_WINDOW != DEFAULT_RAIN_WINDOW:
            alt_name = ALT_RAIN_WINDOW
        if alt_name:
            rain_alt = season_rain(daily, years, RAIN_WINDOWS[alt_name])
            VARIANT_LABELS["rain_adjusted_best"] = alt_name
    vec = lambda rd: (np.array([np.nan if rd.get(int(y)) is None else rd[int(y)] for y in years], float) if rd else None)
    R, R_alt = vec(rain), vec(rain_alt)
    if R is not None and not np.isfinite(R).any():
        R = None
    if R_alt is not None and not np.isfinite(R_alt).any():
        R_alt = None
    # ---- passe 2 : analyse par dalle
    acc, ref_ds, kept = new_acc(), None, None
    for tp in tiles:
        if kept_tile is not None:
            P, ds = kept_tile
        else:
            _y, P, ds = reader(tp, start_year_first_band)
            if mask_fn is not None:
                apply_study_mask(P, mask_fn(ds))
        keep = add_tile(acc, P, years, R, starts, REFERENCE_START, ALTERNATIVE_START, end, R_alt)
        if len(tiles) == 1:
            ref_ds, kept = ds, keep
    if kept is not None and ref_ds is not None:
        rows_, cols_ = ref_ds.RasterYSize, ref_ds.RasterXSize
        for (var, s_y), d in kept.items():
            cls = np.where(d["traj_valid"], d["traj_tau"], 127).reshape(rows_, cols_)
            writer(os.path.join(out_dir, f"Trajectory_class_{var}_start{s_y}.tif"), cls, ref_ds)
    png = make_figures(out_dir, acc, starts, series, rain, REFERENCE_START, ALTERNATIVE_START, lang)
    params = {"Start years compared": ", ".join(map(str, starts)), "Reference / alternative start": f"{REFERENCE_START} / {ALTERNATIVE_START}", "Trajectory threshold |tau|": TAU_MAIN, "Significance (variant)": P_ALPHA,
              "Baseline period": f"start year – {BASELINE_END}", "Recent period": f"{RECENT_YEARS[0]}–{RECENT_YEARS[1]}", "State threshold": f"{100 * STATE_THRESHOLD:.0f} %",
              "Rain": (f"{DEFAULT_RAIN_WINDOW}" + (f" and {VARIANT_LABELS['rain_adjusted_best']} (best R²)" if "rain_adjusted_best" in VARIANT_LABELS else "")) if rain else "(no rainfall file: raw variant only)",
              "Study-area mask": ("yes: " + os.path.basename(study_shp) if study_shp else "yes") if mask_fn is not None else "NO (the shares cover the whole raster rectangle)",
              "Tiles read": len(tiles), "Rasters written": "yes" if kept is not None else "no (stack in several tiles)"}
    inputs = [{"label": "Annual productivity stack", "path": stack_path}] + ([{"label": "Daily rainfall", "path": rain_csv}] if rain_csv else []) + ([{"label": "Study area", "path": study_shp}] if study_shp else [])
    cover = {"valid_px": int(max(cnt_p)) if cnt_p is not None else 0, "px_ha": px_ha, "study_ha": STUDY_AREA_HA, "masked": mask_fn is not None}
    rep = stage_report(out_dir, acc, starts, series, rain, REFERENCE_START, ALTERNATIVE_START, t0, params, inputs, AREA_NAME, png, lang, log, rain_info, cover)
    import shutil
    shutil.rmtree(os.path.join(out_dir, "_temp"), ignore_errors=True)
    return rep


def _stop(msg):
    print("[Arrêt] " + msg)
    try:
        from qgis.PyQt.QtWidgets import QMessageBox
        QMessageBox.information(None, "02B", msg)
    except Exception:
        pass


def main():
    try:
        _main()
    except Exception:
        tb = traceback.format_exc()
        print(tb)
        try:
            from qgis.PyQt.QtWidgets import QMessageBox
            QMessageBox.critical(None, "02B — erreur", tb[-1500:])
        except Exception:
            pass


def _main():
    from qgis.PyQt.QtWidgets import QFileDialog, QInputDialog, QMessageBox
    from qgis.PyQt.QtCore import QUrl
    ras, _f = QFileDialog.getOpenFileName(None, "02B — pile annuelle de productivité MODIS (une bande par année ; une dalle suffit pour un export GEE découpé)", "", "GeoTIFF (*.tif *.tiff)")
    if not ras:
        return _stop("Annulé : aucun fichier produit.")
    first, ok = QInputDialog.getInt(None, "02B", "Année de la PREMIÈRE bande (utilisée seulement si les bandes n'ont pas d'année dans leur nom) :", 2000, 1972, 2100)
    if not ok:
        return _stop("Annulé.")
    rain, _f = QFileDialog.getOpenFileName(None, "02B — pluie journalière ClimateEngine.csv (facultatif : Annuler = variante brute seulement)", os.path.dirname(ras), "CSV (*.csv)")
    shp, _f = QFileDialog.getOpenFileName(None, "02B — zone d'étude (shp) — RECOMMANDÉ : sans elle les parts portent sur tout le rectangle du raster, souvent bien plus grand que la zone (Annuler pour passer)", os.path.dirname(ras), "Shapefile (*.shp)")
    out = QFileDialog.getExistingDirectory(None, "02B — dossier de SORTIE", os.path.dirname(ras))
    if not out:
        return _stop("Annulé : aucun fichier produit.")
    rep = run_sensitivity(ras, rain or None, os.path.join(out, "02B_Trend_Start_Sensitivity"), first, REPORT_LANG, study_shp=shp or None)
    QMessageBox.information(None, "02B terminé", f"Rapport : {rep}")
    try:
        from qgis.PyQt.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(rep))
    except Exception:
        pass


# ====================== MAIN ======================
main()
