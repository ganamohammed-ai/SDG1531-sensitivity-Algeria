# -*- coding: utf-8 -*-
# SDG 15.3.1 REFERENCE PIPELINE — STAGE 05B / 08 : Accuracy assessment (Olofsson et al. 2014) — QGIS
"""
ÉTAPE 05B — ÉVALUATION DE L'EXACTITUDE DES CARTES LULC ET SURFACES CORRIGÉES (Olofsson et al. 2014)   |   QGIS / PyQGIS
(à coller dans la Console Python de QGIS ou à exécuter depuis l'éditeur)

ENTRÉES
  - Validation_Points_all.csv (ou Validation_Points.gpkg) de l'étape 05A, dont le champ Reference_Class a été REMPLI par un interprète indépendant ;
  - Sampling_Design.csv de l'étape 05A (surface et poids W_h de chaque strate = classe cartographiée).

CE QUE FAIT LE SCRIPT (pour chaque année, estimateurs d'un échantillonnage ALÉATOIRE STRATIFIÉ)
  - matrice de confusion en effectifs ; matrice des PROPORTIONS DE SURFACE estimées p_hk = W_h n_hk / n_h. ;
  - exactitude globale (OA), exactitude de l'utilisateur (UA, erreur de commission) et du producteur (PA, erreur d'omission), avec ERREURS-TYPES et INTERVALLES DE CONFIANCE À 95 % ;
  - SURFACES CORRIGÉES par classe (surface cartographiée ajustée par les erreurs de classification) avec intervalle de confiance, et biais de la carte (surface cartographiée - surface corrigée) ;
  - contrôles de qualité (taux de points étiquetés, effectif par strate, codes invalides, strates sans variance) et RAPPORT HTML d'étape avec figures.

CHOIX MÉTHODOLOGIQUES : pas de coefficient Kappa (déconseillé par Olofsson et al. 2014, Pontius & Millones 2011) ; variances de l'éq. de Olofsson (OA, UA, PA, surfaces) ; IC de Wald à 95 % (z = 1,96).
LIMITE : valide la CARTE de chaque année ; la surface du CHANGEMENT avec intervalle de confiance exige un échantillon stratifié par classe de changement.
AUTRE ZONE D'ÉTUDE : aucun réglage propre à la zone (la légende CLASS_NAMES doit rester celle des étapes précédentes).
"""
import os
import re
import csv
import json
import time
import math
import platform
import traceback
import numpy as np
from collections import Counter as collections_Counter

AREA_NAME = "Oum El Bouaghi (Algeria)"
REPORT_LANG = "en"
Z95 = 1.96
CLASS_NAMES = {1: "Built-up", 2: "Water", 3: "Sebkha", 4: "Bareland / Rock", 5: "Cropland", 6: "Fallow", 7: "Forest", 8: "Rangeland"}
CLASSES = tuple(sorted(CLASS_NAMES))
MIN_N_PER_STRATUM = 25                      # en dessous, l'estimation d'une classe est jugée fragile (alerte)
OA_FLAG, UA_PA_FLAG = 0.85, 0.70            # seuils de lecture (alertes), PAS des seuils UNCCD

# ============================================================================
# 1. LOGIQUE PURE (testée sans QGIS)
# ============================================================================
def clean_points(rows, classes=CLASSES):
    """
    Points exploitables : (année, classe_carte, classe_référence). rows = dictionnaires avec Year, Map_Class, Reference_Class.
    Retourne (points valides, rapport {"total", "labelled", "invalid_codes": [...], "unlabelled"}).
    """
    pts, rep = [], {"total": 0, "labelled": 0, "invalid_codes": [], "unlabelled": 0}
    for r in rows:
        rep["total"] += 1
        ref = str(r.get("Reference_Class", "")).strip()
        if ref in ("", "None", "NULL", "nan"):
            rep["unlabelled"] += 1
            continue
        try:
            y, m, k = int(float(r["Year"])), int(float(r["Map_Class"])), int(round(float(ref)))
        except (ValueError, KeyError, TypeError):
            rep["invalid_codes"].append((r.get("Point_ID"), ref))
            continue
        if m not in classes or k not in classes:
            rep["invalid_codes"].append((r.get("Point_ID"), ref))
            continue
        rep["labelled"] += 1
        pts.append((y, m, k))
    return pts, rep


def confusion_counts(points, year, classes=CLASSES):
    """Matrice n_hk (ligne h = classe cartographiée, colonne k = classe de référence) d'une année."""
    idx = {c: i for i, c in enumerate(classes)}
    M = np.zeros((len(classes), len(classes)), np.int64)
    for y, m, k in points:
        if y == year:
            M[idx[m], idx[k]] += 1
    return M


def olofsson_estimates(n_hk, N_h):
    """
    Estimateurs d'Olofsson et al. (2014) pour un échantillonnage aléatoire stratifié (strates = classes cartographiées).
      n_hk : effectifs (ligne = carte, colonne = référence) ; N_h : nombre de pixels (ou surface) de chaque strate cartographiée.
    Retourne un dictionnaire de tableaux/valeurs :
      W, n_h, p (proportions de surface estimées p_hk), OA, V_OA, UA, V_UA, PA, V_PA, area_prop (p_.k), V_area_prop, N_total.
    Les variances sont NaN lorsqu'une strate n'a qu'un seul point (variance non définie) ; les classes absentes de la carte ont des NaN.
    """
    n_hk = np.asarray(n_hk, float)
    N_h = np.asarray(N_h, float)
    N = N_h.sum()
    n_h = n_hk.sum(axis=1)
    W = N_h / N if N > 0 else np.zeros_like(N_h)
    with np.errstate(divide="ignore", invalid="ignore"):
        frac = np.where(n_h[:, None] > 0, n_hk / n_h[:, None], 0.0)             # n_hk / n_h.
        p = W[:, None] * frac                                                      # p_hk
        diag = np.diag(frac)                                                       # U_h = n_hh / n_h.
        denom = n_h - 1
        v_frac = np.where(denom[:, None] > 0, frac * (1 - frac) / denom[:, None], np.nan)
        OA = float(np.sum(W * diag))
        V_OA = float(np.sum(W ** 2 * np.where(denom > 0, diag * (1 - diag) / denom, np.nan)))
        UA = np.where(n_h > 0, diag, np.nan)
        V_UA = np.where(denom > 0, diag * (1 - diag) / denom, np.nan)
        area_prop = p.sum(axis=0)                                                  # p_.k
        V_area = np.sum((W[:, None] ** 2) * v_frac, axis=0)
        N_hat_k = np.sum((N_h / np.where(n_h > 0, n_h, np.nan))[:, None] * n_hk, axis=0)     # N^_.k : pixels estimés de la classe de référence k
        PA = np.where(area_prop > 0, W * diag / np.where(area_prop > 0, area_prop, 1.0), np.nan)         # PA_k = p_kk / p_.k
        V_PA = np.full(len(N_h), np.nan)
        for k in range(len(N_h)):
            if not (N_hat_k[k] > 0) or not (denom[k] > 0):
                continue
            others = 0.0
            for h in range(len(N_h)):
                if h != k and denom[h] > 0:
                    others += N_h[h] ** 2 * frac[h, k] * (1 - frac[h, k]) / denom[h]
            V_PA[k] = (N_h[k] ** 2 * (1 - PA[k]) ** 2 * diag[k] * (1 - diag[k]) / denom[k] + PA[k] ** 2 * others) / N_hat_k[k] ** 2
    return {"W": W, "n_h": n_h, "p": p, "OA": OA, "V_OA": V_OA, "UA": UA, "V_UA": V_UA, "PA": PA, "V_PA": V_PA, "area_prop": area_prop, "V_area_prop": V_area, "N_total": N}


def ci(value, variance, z=Z95):
    """Intervalle de confiance de Wald [bas, haut] (NaN si la variance n'est pas définie ; borné à [0, 1] pour une proportion)."""
    se = math.sqrt(variance) if variance == variance and variance >= 0 else float("nan")
    return value - z * se, value + z * se, se


def accuracy_tables(est, mapped_ha, classes=CLASSES):
    """
    Tableaux d'une année : par classe UA / PA avec IC, surface cartographiée, surface corrigée avec IC, biais. mapped_ha = surface cartographiée par classe (même ordre).
    """
    A = float(np.sum(mapped_ha))
    rows = []
    for i, c in enumerate(classes):
        ua, va = est["UA"][i], est["V_UA"][i]
        pa, vp = est["PA"][i], est["V_PA"][i]
        ua_lo, ua_hi, ua_se = ci(ua, va)
        pa_lo, pa_hi, pa_se = ci(pa, vp)
        ap, vap = est["area_prop"][i], est["V_area_prop"][i]
        a_lo, a_hi, a_se = ci(ap * A, vap * A * A)
        rows.append({"class": c, "name": CLASS_NAMES[c], "n": int(est["n_h"][i]), "mapped_ha": float(mapped_ha[i]), "UA": ua, "UA_lo": max(0.0, ua_lo) if ua == ua else ua_lo, "UA_hi": min(1.0, ua_hi) if ua == ua else ua_hi,
                     "PA": pa, "PA_lo": max(0.0, pa_lo) if pa == pa else pa_lo, "PA_hi": min(1.0, pa_hi) if pa == pa else pa_hi,
                     "adjusted_ha": ap * A, "adj_lo": max(0.0, a_lo), "adj_hi": a_hi, "adj_se": a_se, "bias_ha": float(mapped_ha[i]) - ap * A})
    oa_lo, oa_hi, oa_se = ci(est["OA"], est["V_OA"])
    return rows, {"OA": est["OA"], "OA_lo": max(0.0, oa_lo), "OA_hi": min(1.0, oa_hi), "OA_se": oa_se}


def design_for_year(design_rows, year, classes=CLASSES):
    """(N_h en pixels, surface ha) par classe de l'année, depuis Sampling_Design.csv (lignes dict : year, class, mapped_px, mapped_ha)."""
    px = {c: 0.0 for c in classes}
    ha = {c: 0.0 for c in classes}
    for r in design_rows:
        if int(float(r["year"])) == int(year):
            px[int(float(r["class"]))] = float(str(r["mapped_px"]).replace(",", "."))
            ha[int(float(r["class"]))] = float(str(r["mapped_ha"]).replace(",", "."))
    return [px[c] for c in classes], [ha[c] for c in classes]


def quality_checks(rep, per_year, lang="en"):
    """Contrôles : taux d'étiquetage, codes invalides, effectif par strate, OA / UA / PA faibles."""
    T = lambda a, b: a if lang == "en" else b
    out = []
    lab = 100.0 * rep["labelled"] / rep["total"] if rep["total"] else 0.0
    out.append((T("Points labelled with a reference class", "Points étiquetés avec une classe de référence"), "PASS" if lab >= 99.9 else ("WARN" if lab >= 90 else "FAIL"), T(f"{rep['labelled']} of {rep['total']} ({lab:.1f} %)", f"{rep['labelled']} sur {rep['total']} ({lab:.1f} %)")))
    for fn, fy, off in rep.get("year_conflicts", []):
        out.append((T(f"Year of the file {fn} agrees with its points", f"L'année du fichier {fn} concorde avec ses points"), "FAIL", T(f"the file name says {fy} but the Year field says {', '.join(off)} ({sum(off.values())} points): these points were drawn on another year's map", f"le nom du fichier indique {fy} mais le champ Year indique {', '.join(off)} ({sum(off.values())} points) : ces points ont été tirés sur la carte d'une autre année")))
    for fn, fy, old, k in rep.get("forced_years", []):
        out.append((T(f"Year imposed for {fn}", f"Année imposée pour {fn}"), "WARN", T(f"the Year field said {old} ({k} points) but the year {fy} was imposed by the user: confirm it with the map-consistency check", f"le champ Year indiquait {old} ({k} points) mais l'année {fy} a été imposée par l'utilisateur : la confirmer par le contrôle de concordance avec la carte")))
    for y, mc in sorted(rep.get("map_consistency", {}).items()):
        rate = mc["rate"]
        st = "WARN" if (rate == rate and rate > MISMATCH_WARN) else "PASS"
        if rate == rate and rate > MISMATCH_FAIL:
            st = "FAIL"
        if mc["checked"] == 0:
            out.append((T(f"Points agree with the {y} map", f"Les points concordent avec la carte {y}"), "FAIL", T(f"no point falls inside the map: wrong coordinate system or wrong map ({mc['outside']} outside)", f"aucun point ne tombe dans la carte : mauvais système de coordonnées ou mauvaise carte ({mc['outside']} hors carte)")))
            continue
        out.append((T(f"Points agree with the {y} map", f"Les points concordent avec la carte {y}"), st,
                    T(f"{mc['mismatch']} of {mc['checked']} points ({rate:.1f} %) have a mapped class different from the supplied map", f"{mc['mismatch']} points sur {mc['checked']} ({rate:.1f} %) ont une classe cartographiée différente de la carte fournie")
                    + (T(" — the points were drawn on ANOTHER version of the map: do not use this map's areas as weights", " — les points ont été tirés sur une AUTRE version de la carte : ne pas utiliser les surfaces de cette carte comme poids") if st == "FAIL" else "")))
    out.append((T("Valid class codes", "Codes de classe valides"), "PASS" if not rep["invalid_codes"] else "FAIL", T("all codes are 1–8", "tous les codes sont 1–8") if not rep["invalid_codes"] else T(f"{len(rep['invalid_codes'])} invalid, e.g. {rep['invalid_codes'][:3]}", f"{len(rep['invalid_codes'])} invalides, ex. {rep['invalid_codes'][:3]}")))
    for y, d in per_year.items():
        empty = [r["name"] for r in d["rows"] if r["n"] == 0 and r["mapped_ha"] > 0]
        out.append((T(f"Every mapped class has points {y}", f"Chaque classe cartographiée a des points {y}"), "PASS" if not empty else "FAIL", T("all mapped classes are sampled", "toutes les classes cartographiées sont échantillonnées") if not empty else T("no point for: ", "aucun point pour : ") + ", ".join(empty) + T(" (area estimates are biased)", " (les estimations de surface sont biaisées)")))
        thin = [r["name"] for r in d["rows"] if 0 < r["n"] < MIN_N_PER_STRATUM]
        out.append((T(f"Points per stratum {y}", f"Points par strate {y}"), "PASS" if not thin else "WARN", T(f"every stratum has at least {MIN_N_PER_STRATUM} points", f"chaque strate a au moins {MIN_N_PER_STRATUM} points") if not thin else T("fragile estimates for: ", "estimations fragiles pour : ") + ", ".join(thin)))
        oa = d["overall"]
        out.append((T(f"Overall accuracy {y}", f"Exactitude globale {y}"), "PASS" if oa["OA"] >= OA_FLAG else "WARN", f"{100 * oa['OA']:.1f} % (95 % CI {100 * oa['OA_lo']:.1f}–{100 * oa['OA_hi']:.1f})"))
        low = [f"{r['name']} (UA {100 * r['UA']:.0f} %)" for r in d["rows"] if r["UA"] == r["UA"] and r["UA"] < UA_PA_FLAG] + [f"{r['name']} (PA {100 * r['PA']:.0f} %)" for r in d["rows"] if r["PA"] == r["PA"] and r["PA"] < UA_PA_FLAG]
        out.append((T(f"Class accuracies {y}", f"Exactitudes par classe {y}"), "PASS" if not low else "WARN", T(f"all UA and PA >= {100 * UA_PA_FLAG:.0f} %", f"toutes UA et PA >= {100 * UA_PA_FLAG:.0f} %") if not low else T("below ", "sous ") + f"{100 * UA_PA_FLAG:.0f} % : " + ", ".join(low)))
    return out


# ============================================================================
# 2. RAPPORT HTML D'ÉTAPE (bloc partagé : voir tools/sdg_stage_report.py)
# ============================================================================
PIPELINE_BUILD = "2026.10-0c1bc192735c"
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


def _fmt(v, nd=1, pct=False):
    if v is None or (isinstance(v, float) and v != v):
        return ""
    return f"{100 * v:.{nd}f}" if pct else f"{v:,.{nd}f}"


def accuracy_figures(per_year, out_dir, lang="en"):
    """Figures PNG : UA / PA avec IC ; surface cartographiée vs surface corrigée avec IC ; matrice de confusion. {clé: chemin}."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return {}
    figs = {}
    os.makedirs(out_dir, exist_ok=True)
    for y, d in per_year.items():
        rows = [r for r in d["rows"] if r["n"] > 0]
        if not rows:
            continue
        x = np.arange(len(rows))
        fig, ax = plt.subplots(figsize=(9, 4.8))
        for off, key, lo, hi, col, lab in ((-0.18, "UA", "UA_lo", "UA_hi", "#1565c0", "User's accuracy (1 − commission)" if lang == "en" else "Exactitude de l'utilisateur"), (0.18, "PA", "PA_lo", "PA_hi", "#ef6c00", "Producer's accuracy (1 − omission)" if lang == "en" else "Exactitude du producteur")):
            v = np.array([r[key] for r in rows], float) * 100
            e = np.array([[(r[key] - r[lo]) * 100 for r in rows], [(r[hi] - r[key]) * 100 for r in rows]], float)
            ax.bar(x + off, np.nan_to_num(v), 0.34, yerr=np.nan_to_num(e), color=col, capsize=3, label=lab)
        ax.axhline(100 * UA_PA_FLAG, color="grey", linestyle=":", linewidth=1)
        ax.set_xticks(x)
        ax.set_xticklabels([r["name"] for r in rows], rotation=30, ha="right")
        ax.set_ylabel("%")
        ax.set_ylim(0, 105)
        ax.set_title(f"{y} — OA {100 * d['overall']['OA']:.1f} % (95 % CI {100 * d['overall']['OA_lo']:.1f}–{100 * d['overall']['OA_hi']:.1f})")
        ax.legend(frameon=False, fontsize=8, loc="lower right")
        fig.savefig(os.path.join(out_dir, f"Fig_Accuracy_{y}.png"), dpi=110, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        figs[f"acc_{y}"] = os.path.join(out_dir, f"Fig_Accuracy_{y}.png")
        fig, ax = plt.subplots(figsize=(9, 4.8))
        mp = np.array([r["mapped_ha"] for r in rows])
        ad = np.array([r["adjusted_ha"] for r in rows])
        er = np.array([[r["adjusted_ha"] - r["adj_lo"] for r in rows], [r["adj_hi"] - r["adjusted_ha"] for r in rows]])
        ax.bar(x - 0.18, mp, 0.34, color="#90a4ae", label="Mapped area" if lang == "en" else "Surface cartographiée")
        ax.bar(x + 0.18, ad, 0.34, yerr=np.nan_to_num(er), color="#2e7d32", capsize=3, label="Error-adjusted area (95 % CI)" if lang == "en" else "Surface corrigée (IC 95 %)")
        ax.set_xticks(x)
        ax.set_xticklabels([r["name"] for r in rows], rotation=30, ha="right")
        ax.set_ylabel("ha")
        ax.set_title(f"{y} — " + ("mapped vs error-adjusted area" if lang == "en" else "surface cartographiée vs corrigée"))
        ax.legend(frameon=False, fontsize=8)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: f"{v:,.0f}"))
        fig.savefig(os.path.join(out_dir, f"Fig_AdjustedArea_{y}.png"), dpi=110, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        figs[f"area_{y}"] = os.path.join(out_dir, f"Fig_AdjustedArea_{y}.png")
    return figs


def accuracy_stage_report(out_dir, per_year, rep, t0, params, inputs, area_name, lang="en", log=print):
    en = lang == "en"
    T = lambda a, b: a if en else b
    figs = accuracy_figures(per_year, os.path.join(out_dir, "_temp"), lang)
    summary, sections = [], []
    for y, d in per_year.items():
        o = d["overall"]
        summary.append(T(f"{y}: overall accuracy {100 * o['OA']:.1f} % (95 % CI {100 * o['OA_lo']:.1f}–{100 * o['OA_hi']:.1f}) from {int(d['n_total'])} points", f"{y} : exactitude globale {100 * o['OA']:.1f} % (IC 95 % {100 * o['OA_lo']:.1f}–{100 * o['OA_hi']:.1f}) à partir de {int(d['n_total'])} points"))
        hdr = [T("Class", "Classe"), "n", T("Mapped area (ha)", "Surface cartographiée (ha)"), "UA %", "UA 95 % CI", "PA %", "PA 95 % CI", T("Adjusted area (ha)", "Surface corrigée (ha)"), "95 % CI (ha)", T("Map bias (ha)", "Biais de la carte (ha)")]
        tb = [hdr] + [[f"{r['class']} — {r['name']}", r["n"], _fmt(r["mapped_ha"], 0), _fmt(r["UA"], 1, True), f"{_fmt(r['UA_lo'], 1, True)}–{_fmt(r['UA_hi'], 1, True)}", _fmt(r["PA"], 1, True), f"{_fmt(r['PA_lo'], 1, True)}–{_fmt(r['PA_hi'], 1, True)}",
                                  _fmt(r["adjusted_ha"], 0), f"{_fmt(r['adj_lo'], 0)}–{_fmt(r['adj_hi'], 0)}", _fmt(r["bias_ha"], 0)] for r in d["rows"] if r["n"] > 0]
        names = [CLASS_NAMES[c] for c in CLASSES]
        cm = [[T("Map \\ Reference", "Carte \\ Référence")] + names + ["Σ"]] + [[names[i]] + [int(v) for v in d["counts"][i]] + [int(d["counts"][i].sum())] for i in range(len(CLASSES)) if d["counts"][i].sum() > 0]
        pm = [[T("Map \\ Reference", "Carte \\ Référence")] + names] + [[names[i]] + [f"{d['est']['p'][i, j]:.5f}" for j in range(len(CLASSES))] for i in range(len(CLASSES)) if d["counts"][i].sum() > 0]
        sections.append({"id": f"y{y}", "title": T(f"Accuracy and adjusted areas — {y}", f"Exactitude et surfaces corrigées — {y}"),
                         "intro": T("UA = share of the mapped class that is correct; PA = share of the true class that is mapped correctly; the adjusted area corrects the pixel count for the classification errors.", "UA = part de la classe cartographiée qui est correcte ; PA = part de la classe réelle correctement cartographiée ; la surface corrigée corrige le comptage de pixels des erreurs de classification."),
                         "tables": [(T("Accuracy by class", "Exactitude par classe"), tb), (T("Confusion matrix (sample counts)", "Matrice de confusion (effectifs de l'échantillon)"), cm), (T("Estimated area proportions p_hk (population level)", "Proportions de surface estimées p_hk (niveau population)"), pm)],
                         "images": [(T("User's and producer's accuracy with 95 % CI", "Exactitudes de l'utilisateur et du producteur (IC 95 %)"), figs.get(f"acc_{y}")), (T("Mapped vs error-adjusted area", "Surface cartographiée vs corrigée"), figs.get(f"area_{y}"))]})
    checks = quality_checks(rep, per_year, lang)
    L = [T("Areas are estimated for each year's MAP. The area of CHANGE with confidence intervals needs a sample stratified by change class (Olofsson et al. 2014).", "Les surfaces sont estimées pour la CARTE de chaque année. La surface du CHANGEMENT avec intervalles de confiance exige un échantillon stratifié par classe de changement (Olofsson et al. 2014)."),
         T("The reference labels are only as good as the interpreter and the imagery; report the inter-interpreter agreement.", "Les étiquettes de référence valent ce que valent l'interprète et l'imagerie ; rapporter l'accord inter-interprètes."),
         T("Kappa is deliberately not reported (Pontius & Millones 2011; Olofsson et al. 2014).", "Kappa n'est volontairement pas rapporté (Pontius & Millones 2011 ; Olofsson et al. 2014)."),
         T("Wald 95 % intervals can be too narrow for rare classes with few points.", "Les intervalles de Wald à 95 % peuvent être trop étroits pour les classes rares à peu de points."),
         T("The thresholds used to flag weak accuracy (OA 85 %, UA/PA 70 %) are reading aids, not UNCCD requirements.", "Les seuils d'alerte (OA 85 %, UA/PA 70 %) sont des aides à la lecture, pas des exigences UNCCD.")]
    A = [T("Run stage 05A for the new area, label Reference_Class blind, then point this script to the labelled CSV and Sampling_Design.csv.", "Exécuter l'étape 05A pour la nouvelle zone, étiqueter Reference_Class en aveugle, puis indiquer à ce script le CSV étiqueté et Sampling_Design.csv."),
         T("Keep the same legend (classes 1–8). If the legend changes, edit CLASS_NAMES here and in the other stages.", "Garder la même légende (classes 1–8). Si elle change, modifier CLASS_NAMES ici et dans les autres étapes."),
         T("Use the accuracy results to decide how much confidence the land-cover and SOC sub-indicators deserve in stage 07.", "Utiliser les exactitudes pour décider du degré de confiance accordé aux sous-indicateurs couverture et SOC à l'étape 07.")]
    R = ["Olofsson, P., Foody, G.M., Herold, M., Stehman, S.V., Woodcock, C.E., Wulder, M.A. (2014). Good practices for estimating area and assessing accuracy of land change. Remote Sensing of Environment 148, 42–57.",
         "Olofsson, P., Foody, G.M., Stehman, S.V., Woodcock, C.E. (2013). Making better use of accuracy data in land change studies: Estimating accuracy and area and quantifying uncertainty using stratified estimation. Remote Sensing of Environment 129, 122–131.",
         "Pontius, R.G. Jr., Millones, M. (2011). Death to Kappa: birth of quantity disagreement and allocation disagreement for accuracy assessment. International Journal of Remote Sensing 32, 4407–4429."]
    spec = {"stage": "05B", "title": T("Map accuracy assessment and error-adjusted areas", "Évaluation de l'exactitude des cartes et surfaces corrigées"), "subtitle": "Olofsson et al. (2014)", "lang": lang, "area": area_name, "started": t0, "out_dir": out_dir,
            "params": params, "inputs": inputs, "summary": summary, "checks": checks, "sections": sections, "limits": L, "adapt": A, "references": R}
    path = os.path.join(out_dir, "Stage_Report_05B_Accuracy.html")
    write_stage_report(path, spec)
    import shutil
    shutil.rmtree(os.path.join(out_dir, "_temp"), ignore_errors=True)
    log("[Rapport HTML] " + path)
    return path


# ============================================================================
# 3. ENTRÉES / SORTIES ET COUCHE QGIS (relue, non exécutable hors QGIS)
# ============================================================================
REF_ALIASES = ("reference_class", "ref_class", "reference_", "reference", "ref")      # « Reference_Class » est tronqué en « Reference_ » par un Shapefile : tous ces noms sont acceptés


def normalize_point_keys(row):
    """Ramène l'un des alias du champ de référence à « Reference_Class » (insensible à la casse) ; les autres champs sont conservés."""
    out = dict(row)
    if "Reference_Class" not in out:
        for k in list(out):
            if str(k).strip().lower() in REF_ALIASES:
                out["Reference_Class"] = out[k]
                break
    return out


MAP_RE = re.compile(r"^LULC_(.+?)_((?:19|20)\d{2})\.tif$", re.I)
SKIP_MAP_PARTS = ("_Original", "_Edited", "_Retro", "_Corrige")
MISMATCH_WARN, MISMATCH_FAIL = 1.0, 5.0     # % de points dont la classe cartographiée diffère de la carte fournie


def find_lulc_maps(folder):
    """{année: chemin} des cartes LULC_<ZONE>_<année>.tif d'un dossier (et de son sous-dossier LULC/) ; copies _Original / _Edited / _Retro / _Corrige ignorées."""
    out = {}
    for d in (os.path.join(folder, "LULC"), folder):
        if os.path.isdir(d):
            for fn in sorted(os.listdir(d)):
                m = MAP_RE.match(fn)
                if m and not any(x in fn for x in SKIP_MAP_PARTS):
                    out[int(m.group(2))] = os.path.join(d, fn)
    return dict(sorted(out.items()))


def scan_point_files(folder):
    """{année: [Shapefiles]} : tous les .shp d'un dossier (et de ses sous-dossiers) dont le NOM contient une année (Validation_Points_2020.shp, Reference_Points_2007.shp, ...)."""
    out = {}
    for r, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fn in sorted(files):
            if fn.lower().endswith(".shp"):
                y = year_from_filename(fn)
                if y:
                    out.setdefault(y, []).append(os.path.join(r, fn))
    return dict(sorted(out.items()))


def map_class_counts(arr):
    """Pixels par classe 1-8 d'une carte (les autres valeurs sont ignorées)."""
    cnt = np.bincount(np.asarray(arr).ravel().astype(np.int64), minlength=max(CLASSES) + 2)
    return {c: int(cnt[c]) for c in CLASSES if c < len(cnt)}


def design_rows_from_map(year, counts, px_ha, points_per_class):
    """Plan d'échantillonnage reconstitué à partir de la CARTE (au lieu de Sampling_Design.csv) : mêmes colonnes ; valable seulement si les points ont été tirés sur cette carte."""
    return [{"year": str(year), "class": str(c), "name": CLASS_NAMES[c], "mapped_px": str(counts[c]), "mapped_ha": f"{counts[c] * px_ha:.4f}", "weight": "", "n_allocated": str(points_per_class.get(c, 0))} for c in CLASSES if counts.get(c, 0) > 0]


def map_consistency(rows, arr, gt):
    """
    Compare la classe CARTOGRAPHIÉE enregistrée dans chaque point (Map_Class) à la valeur de la carte fournie à l'emplacement du point (X, Y en coordonnées de la carte).
    Retourne {"n", "outside", "checked", "mismatch", "rate", "by_class": {classe: (n, désaccords)}}. Un taux élevé = les points ont été tirés sur une AUTRE version de la carte.
    """
    a = np.asarray(arr)
    n = outside = checked = mism = 0
    by = {}
    for r in rows:
        try:
            x, y, m = float(r["X"]), float(r["Y"]), int(float(r["Map_Class"]))
        except (KeyError, ValueError, TypeError):
            continue
        n += 1
        col = int((x - gt[0]) // gt[1]) if gt[1] else -1
        row = int((y - gt[3]) // gt[5]) if gt[5] else -1
        if not (0 <= row < a.shape[0] and 0 <= col < a.shape[1]):
            outside += 1
            continue
        checked += 1
        n_c, bad = by.get(m, (0, 0))
        by[m] = (n_c + 1, bad + (1 if int(a[row, col]) != m else 0))
        mism += 1 if int(a[row, col]) != m else 0
    return {"n": n, "outside": outside, "checked": checked, "mismatch": mism, "rate": (100.0 * mism / checked) if checked else float("nan"), "by_class": by}


def year_from_filename(path):
    m = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", os.path.basename(path))
    return int(m.group(1)) if m else None


def read_shapefile_points(path):
    """
    Lit un Shapefile de POINTS (.shp + .dbf) en Python pur (sans GDAL) : une ligne dict par point, champs du .dbf (texte), plus X et Y lus dans le .shp s'ils manquent.
    Les enregistrements marqués supprimés sont ignorés ; l'encodage est UTF-8 (repli latin-1).
    """
    import struct
    base = os.path.splitext(path)[0]
    with open(base + ".dbf", "rb") as f:
        raw = f.read()
    n, hlen, rlen = struct.unpack("<IHH", raw[4:12])
    fields, pos = [], 32
    while raw[pos] != 0x0D:
        fd = raw[pos:pos + 32]
        fields.append((fd[:11].split(b"\x00")[0].decode("ascii", "replace"), fd[16]))
        pos += 32
    rows, deleted = [], []
    for i in range(n):
        rec = raw[hlen + i * rlen: hlen + (i + 1) * rlen]
        deleted.append(rec[:1] == b"*")
        off, d = 1, {}
        for name, ln in fields:
            chunk = rec[off:off + ln]
            try:
                d[name] = chunk.decode("utf-8").strip()
            except UnicodeDecodeError:
                d[name] = chunk.decode("latin-1").strip()
            off += ln
        rows.append(d)
    xy = []
    try:
        with open(base + ".shp", "rb") as f:
            shp = f.read()
        p = 100
        while p + 8 <= len(shp):
            clen = struct.unpack(">i", shp[p + 4:p + 8])[0] * 2
            typ = struct.unpack("<i", shp[p + 8:p + 12])[0]
            xy.append(struct.unpack("<2d", shp[p + 12:p + 28]) if typ == 1 else (None, None))
            p += 8 + clen
    except OSError:
        xy = []
    out = []
    for i, d in enumerate(rows):
        if deleted[i]:
            continue
        if i < len(xy) and xy[i][0] is not None:
            d.setdefault("X", repr(xy[i][0]))
            d.setdefault("Y", repr(xy[i][1]))
        out.append(d)
    return out


def read_points(path):
    """Points depuis un CSV (séparateur ; , ou tabulation), un Shapefile (lecture Python pure) ou un GeoPackage (OGR, toutes les couches). Le champ de référence est ramené à « Reference_Class »."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        return [normalize_point_keys(dict(r)) for r in sr_dict_rows(sr_read_csv(path))]
    if ext == ".shp":
        return [normalize_point_keys(r) for r in read_shapefile_points(path)]
    from osgeo import ogr
    ds = ogr.Open(path)
    if ds is None:
        raise RuntimeError(f"Points illisibles : {path}")
    out = []
    for i in range(ds.GetLayerCount()):
        lyr = ds.GetLayer(i)
        names = [lyr.GetLayerDefn().GetFieldDefn(j).GetName() for j in range(lyr.GetLayerDefn().GetFieldCount())]
        for ft in lyr:
            out.append(normalize_point_keys({n: ft.GetField(n) for n in names}))
    return out


def read_class_map(path):
    """(tableau, géotransformation) d'une carte LULC (GDAL)."""
    from osgeo import gdal
    ds = gdal.Open(path, gdal.GA_ReadOnly)
    if ds is None:
        raise RuntimeError(f"Carte illisible : {path}")
    return ds.GetRasterBand(1).ReadAsArray(), ds.GetGeoTransform()


def normalize_entries(points_path):
    """Entrées [(année imposée ou None, chemin)] depuis : un chemin, une liste de chemins, ou une liste de couples (année, chemin)."""
    if isinstance(points_path, str):
        return [(None, points_path)]
    out = []
    for e in points_path:
        out.append((int(e[0]) if e[0] else None, e[1]) if isinstance(e, (tuple, list)) else (None, e))
    return out


def run_accuracy(points_path, design_path, out_dir, lang=REPORT_LANG, log=print, maps=None, force_year=False, map_reader=None):
    """
    points_path : un fichier, une liste de fichiers (un Shapefile par année) ou une liste de couples (année, fichier).
    design_path : Sampling_Design.csv de 05A ; si vide, les poids W_h sont CALCULÉS à partir des cartes LULC `maps` ({année: chemin}), valable seulement si les points ont été tirés sur ces cartes.
    maps        : cartes LULC {année: chemin} : sert aussi à contrôler que la classe cartographiée de chaque point concorde avec la carte à son emplacement.
    force_year  : impose l'année donnée (ou celle du nom de fichier) quand le champ Year des points est faux ; sans cela, un désaccord est un contrôle en ÉCHEC.
    """
    t0 = time.time()
    os.makedirs(out_dir, exist_ok=True)
    entries = normalize_entries(points_path)
    rows, conflicts, forced = [], [], []
    for yr, pth in entries:
        part = read_points(pth)
        fy = yr or (year_from_filename(pth) if (len(entries) > 1 or os.path.splitext(pth)[1].lower() == ".shp") else None)
        if fy:
            ys = collections_Counter(int(float(r["Year"])) for r in part if str(r.get("Year", "")).strip() != "")
            off = {str(y): k for y, k in ys.items() if y != fy}
            if off and force_year:
                for r in part:
                    r["Year"] = str(fy)
                for old, k in off.items():
                    forced.append((os.path.basename(pth), fy, old, k))
            elif off:
                conflicts.append((os.path.basename(pth), fy, off))
            elif not ys:
                for r in part:
                    r["Year"] = str(fy)
        rows += part
    pts, rep = clean_points(rows)
    rep["year_conflicts"], rep["forced_years"], rep["map_consistency"] = conflicts, forced, {}
    if not pts:
        raise RuntimeError("Aucun point étiqueté : remplissez le champ Reference_Class / Ref_Class (étape 05A) avant de lancer 05B.")
    years = sorted({y for y, _m, _k in pts})
    reader = map_reader or read_class_map
    maps = {int(k): v for k, v in (maps or {}).items()}
    design = sr_dict_rows(sr_read_csv(design_path)) if design_path else []
    if not design:
        missing = [y for y in years if y not in maps]
        if missing and conflicts:
            fn, fy, off = conflicts[0]
            raise RuntimeError(f"Le fichier {fn} est indiqué pour l'année {fy} mais ses points portent l'année {', '.join(off)} : les poids ne peuvent pas être calculés. Si le champ Year des points est faux (points tirés sur la carte {fy}), cochez « Imposer l'année » ; sinon corrigez l'année de la ligne.")
        if missing:
            raise RuntimeError("Sampling_Design.csv absent et pas de carte LULC pour : " + ", ".join(map(str, missing)) + " (indiquez le plan d'échantillonnage de 05A ou le dossier des cartes LULC).")
    cache = {}
    for y in years:
        if y in maps:
            cache[y] = reader(maps[y])
            rep["map_consistency"][y] = map_consistency([r for r in rows if str(r.get("Year", "")).strip() and int(float(r["Year"])) == y], cache[y][0], cache[y][1])
        if not design_path:
            arr, gt = cache[y]
            px_ha = abs(gt[1] * gt[5]) / 10000.0
            n_pc = collections_Counter(m for yy, m, _k in pts if yy == y)
            design += design_rows_from_map(y, map_class_counts(arr), px_ha, n_pc)
    per_year, summ = {}, [["year", "n_points", "OA_%", "OA_lo_%", "OA_hi_%", "OA_SE_%"]]
    for y in years:
        n_hk = confusion_counts(pts, y)
        N_h, ha = design_for_year(design, y)
        est = olofsson_estimates(n_hk, N_h)
        rws, ov = accuracy_tables(est, ha)
        per_year[y] = {"counts": n_hk, "est": est, "rows": rws, "overall": ov, "n_total": n_hk.sum()}
        summ.append([y, int(n_hk.sum()), f"{100 * ov['OA']:.2f}", f"{100 * ov['OA_lo']:.2f}", f"{100 * ov['OA_hi']:.2f}", f"{100 * ov['OA_se']:.2f}"])
        with open(os.path.join(out_dir, f"Accuracy_by_class_{y}.csv"), "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["class", "name", "n", "mapped_ha", "UA", "UA_lo", "UA_hi", "PA", "PA_lo", "PA_hi", "adjusted_ha", "adj_lo", "adj_hi", "adj_SE", "bias_ha"])
            for r in rws:
                w.writerow([r["class"], r["name"], r["n"]] + [("" if (isinstance(r[k], float) and r[k] != r[k]) else f"{r[k]:.6f}") for k in ("mapped_ha", "UA", "UA_lo", "UA_hi", "PA", "PA_lo", "PA_hi", "adjusted_ha", "adj_lo", "adj_hi", "adj_se", "bias_ha")])
        with open(os.path.join(out_dir, f"Confusion_matrix_{y}.csv"), "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["map \\ reference"] + [CLASS_NAMES[c] for c in CLASSES])
            for i, c in enumerate(CLASSES):
                w.writerow([CLASS_NAMES[c]] + [int(v) for v in n_hk[i]])
        log(f"[05B] {y} : OA {100 * ov['OA']:.1f} % ({int(n_hk.sum())} points)")
    with open(os.path.join(out_dir, "Accuracy_summary.csv"), "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f, delimiter=";").writerows(summ)
    params = {"Estimator": "Olofsson et al. (2014), stratified random sampling", "Confidence level": "95 % (Wald, z = 1.96)", "Labelled points": f"{rep['labelled']} of {rep['total']}", "Years": ", ".join(map(str, years)),
              "Files": "; ".join(f"{y or '?'}: {os.path.basename(p)}" for y, p in entries), "Weights from": design_path or "LULC maps (points assumed drawn on these maps)", "Year imposed": "yes" if forced else "no"}
    inputs = [{"label": "Reference points — " + os.path.basename(p), "path": p} for _y, p in entries] + ([{"label": "Sampling design", "path": design_path}] if design_path else []) + [{"label": f"LULC map {y}", "path": p} for y, p in sorted(maps.items()) if y in years]
    return accuracy_stage_report(out_dir, per_year, rep, t0, params, inputs, AREA_NAME, lang, log)


def _stop(msg):
    print("[Arrêt] " + msg)
    try:
        from qgis.PyQt.QtWidgets import QMessageBox
        QMessageBox.information(None, "05B", msg)
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
            QMessageBox.critical(None, "05B — erreur", tb[-1500:])
        except Exception:
            pass


def build_input_dialog():
    """Fenêtre de saisie : UN FICHIER DE POINTS PAR ANNÉE (ou un fichier multi-années), plan d'échantillonnage et / ou cartes LULC. PyQt est importé ici pour que le reste reste importable sans QGIS."""
    from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog, QCheckBox, QComboBox, QGroupBox, QTableWidget, QTableWidgetItem, QSpinBox, QAbstractItemView)

    class Inputs(QDialog):
        def __init__(self):
            super().__init__(None)
            self.setWindowTitle("05B — exactitude des cartes LULC : points de validation par année")
            self.resize(920, 700)
            self.entries = []                                   # [{"year": int (0 = à préciser), "path": str}]
            lay = QVBoxLayout(self)
            lay.addWidget(QLabel("<b>1. Points de validation ÉTIQUETÉS : un fichier par année</b> (Shapefile, GeoPackage ou CSV). Indiquez l'année de chaque ligne ; elle est lue dans le nom du fichier quand il en contient une."))
            self.table = QTableWidget(0, 2)
            self.table.setHorizontalHeaderLabels(["Année", "Fichier de points"])
            self.table.setColumnWidth(0, 90)
            self.table.horizontalHeader().setStretchLastSection(True)
            try:
                self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
                self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            except Exception:
                pass
            lay.addWidget(self.table, 1)
            row = QHBoxLayout()
            for txt, slot in (("➕ Ajouter des fichiers…", self.on_add_files), ("📁 Détecter dans un dossier…", self.on_add_folder), ("➖ Retirer la ligne choisie", self.remove_selected)):
                b = QPushButton(txt)
                b.clicked.connect(lambda _c=False, f=slot: f())
                row.addWidget(b)
            row.addStretch(1)
            lay.addLayout(row)
            self.lbl_files = QLabel("")
            self.lbl_files.setWordWrap(True)
            lay.addWidget(self.lbl_files)
            self.le_design, self.le_maps, self.le_out = QLineEdit(), QLineEdit(), QLineEdit()
            for label, le, kind in (("2. Plan d'échantillonnage Sampling_Design.csv (étape 05A) — donne les poids W_h ; facultatif si vous fournissez les cartes", self.le_design, "csv"),
                                    ("3. Dossier des cartes LULC (LULC_<ZONE>_<année>.tif) — facultatif avec le plan : active le contrôle « la classe du point concorde avec la carte » ; SANS plan : les poids sont calculés sur ces cartes", self.le_maps, "dir"),
                                    ("4. Dossier de SORTIE", self.le_out, "dir")):
                box = QGroupBox(label)
                h = QHBoxLayout(box)
                h.addWidget(le, 1)
                bb = QPushButton("Parcourir…")
                bb.clicked.connect(lambda _c=False, le_=le, k=kind: self.browse(le_, k))
                h.addWidget(bb)
                lay.addWidget(box)
            self.chk_force = QCheckBox("Imposer l'année indiquée dans la table (à cocher SEULEMENT si le champ Year des points est faux ; le contrôle de concordance avec la carte le vérifie)")
            lay.addWidget(self.chk_force)
            r2 = QHBoxLayout()
            r2.addWidget(QLabel("Langue du rapport :"))
            self.cb_lang = QComboBox()
            self.cb_lang.addItems(["English (publication)", "Français"])
            r2.addWidget(self.cb_lang)
            r2.addStretch(1)
            lay.addLayout(r2)
            self.lbl_err = QLabel("")
            self.lbl_err.setWordWrap(True)
            lay.addWidget(self.lbl_err)
            bt = QHBoxLayout()
            go, cancel = QPushButton("▶ Calculer l'exactitude"), QPushButton("Annuler")
            go.clicked.connect(self.on_go)
            cancel.clicked.connect(self.reject)
            bt.addStretch(1)
            bt.addWidget(go)
            bt.addWidget(cancel)
            lay.addLayout(bt)
            self.settings = None

        # ---- logique (testée avec de faux widgets)
        def add_paths(self, paths):
            known = {os.path.normpath(e["path"]) for e in self.entries}
            for p in paths:
                if os.path.normpath(p) not in known:
                    self.entries.append({"year": year_from_filename(p) or 0, "path": p})
                    known.add(os.path.normpath(p))
            self.entries.sort(key=lambda e: (e["year"] == 0, e["year"], e["path"]))
            self.refresh_table()

        def add_folder(self, folder):
            found = scan_point_files(folder)
            self.add_paths([p for ps in found.values() for p in ps])
            return found

        def set_year(self, i, y):
            if 0 <= i < len(self.entries):
                self.entries[i]["year"] = int(y)
                self.refresh_table(keep_order=True)

        def selected_rows(self):
            return sorted({i.row() for i in self.table.selectedIndexes()})

        def remove_selected(self):
            for r in reversed(self.selected_rows()):
                if 0 <= r < len(self.entries):
                    del self.entries[r]
            self.refresh_table()

        def refresh_table(self, keep_order=False):
            ys = [e["year"] for e in self.entries]
            dup = sorted({y for y in ys if y and ys.count(y) > 1})
            self.lbl_files.setText((f"⚠ Plusieurs fichiers pour : {', '.join(map(str, dup))} (leurs points seront réunis)." if dup else "") + ("  ⚠ Année à préciser (0) pour certaines lignes." if 0 in ys else ""))
            tbl = getattr(self, "table", None)
            if tbl is None or not hasattr(tbl, "setRowCount"):
                return
            tbl.setRowCount(len(self.entries))
            for i, e in enumerate(self.entries):
                sp = QSpinBox()
                sp.setRange(0, 2100)
                sp.setValue(e["year"])
                sp.valueChanged.connect(lambda v, i_=i: self.entries.__setitem__(i_, dict(self.entries[i_], year=int(v))))
                tbl.setCellWidget(i, 0, sp)
                tbl.setItem(i, 1, QTableWidgetItem(e["path"]))

        def on_add_files(self):
            ps, _f = QFileDialog.getOpenFileNames(self, "Points de validation (un ou plusieurs fichiers)", "", "Points (*.shp *.gpkg *.csv)")
            if ps:
                self.add_paths(ps)

        def on_add_folder(self):
            d = QFileDialog.getExistingDirectory(self, "Dossier contenant les Shapefile de points (années dans les noms)")
            if d:
                found = self.add_folder(d)
                if not found:
                    self.lbl_err.setText("Aucun Shapefile dont le nom contient une année dans ce dossier.")

        def browse(self, le, kind):
            if kind == "dir":
                p = QFileDialog.getExistingDirectory(self, "Dossier", le.text() or "")
            else:
                p, _f = QFileDialog.getOpenFileName(self, "Fichier", le.text() or "", "CSV (*.csv)")
            if p:
                le.setText(p)

        def on_go(self):
            errs = []
            ents = [e for e in self.entries]
            if not ents:
                errs.append("Ajoutez au moins un fichier de points (un par année).")
            for e in ents:
                if not os.path.exists(e["path"]):
                    errs.append(f"Fichier introuvable : {e['path']}")
                if not e["year"] and os.path.splitext(e["path"])[1].lower() == ".shp":
                    errs.append(f"Précisez l'année de {os.path.basename(e['path'])} (colonne « Année »).")
            design, maps_dir, out = self.le_design.text().strip(), self.le_maps.text().strip(), self.le_out.text().strip()
            maps = {}
            if design and not os.path.exists(design):
                errs.append("Le plan d'échantillonnage indiqué n'existe pas.")
            if maps_dir:
                maps = find_lulc_maps(maps_dir) if os.path.isdir(maps_dir) else {}
                if not maps:
                    errs.append("Aucune carte LULC_<ZONE>_<année>.tif dans le dossier des cartes.")
            if not design and not maps_dir:
                errs.append("Indiquez le plan d'échantillonnage (05A) OU le dossier des cartes LULC (les poids W_h en dépendent).")
            if not design and maps:
                need = sorted({e["year"] for e in ents if e["year"]})
                miss = [y for y in need if y not in maps]
                if miss:
                    errs.append("Pas de carte LULC pour : " + ", ".join(map(str, miss)) + " (nécessaire pour calculer les poids).")
            if not out:
                errs.append("Choisissez le dossier de sortie.")
            if errs:
                self.lbl_err.setText("<span style='color:#c62828'>" + "<br>".join("• " + x for x in errs) + "</span>")
                return
            self.settings = {"entries": [(e["year"] or None, e["path"]) for e in ents], "design": design, "maps": maps_dir, "out": out, "force_year": bool(self.chk_force.isChecked()), "lang": "en" if self.cb_lang.currentIndex() == 0 else "fr"}
            self.accept()

    return Inputs


def _main():
    from qgis.PyQt.QtWidgets import QMessageBox
    from qgis.PyQt.QtCore import QUrl
    Inputs = build_input_dialog()
    dlg = Inputs()
    if not dlg.exec_() if hasattr(dlg, "exec_") else not dlg.exec():
        return _stop("Annulé : aucun fichier produit.")
    if not dlg.settings:
        return _stop("Paramètres invalides : aucun fichier produit.")
    cfg = dlg.settings
    maps = find_lulc_maps(cfg["maps"]) if cfg["maps"] else {}
    rep = run_accuracy(cfg["entries"], cfg["design"] or None, os.path.join(cfg["out"], "05B_Accuracy_Assessment"), cfg["lang"], print, maps, cfg["force_year"])
    QMessageBox.information(None, "05B terminé", f"Exactitudes, surfaces corrigées et rapport écrits dans :\n{cfg['out']}\n\nRapport : {rep}")
    try:
        from qgis.PyQt.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(rep))
    except Exception:
        pass


# ====================== MAIN ======================
main()
