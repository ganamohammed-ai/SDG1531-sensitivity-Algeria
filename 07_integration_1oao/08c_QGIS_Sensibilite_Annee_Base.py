# -*- coding: utf-8 -*-
# SDG 15.3.1 REFERENCE PIPELINE — STAGE 08 / 08 : Sensitivity to the baseline year — QGIS
"""
ÉTAPE 08 — SENSIBILITÉ AU CHOIX DE L'ANNÉE DE RÉFÉRENCE (BASE) : COMPARAISON DE DEUX CONCEPTIONS TEMPORELLES   |   QGIS / PyQGIS
(à coller dans la Console Python de QGIS ou à exécuter depuis l'éditeur)

POURQUOI
  Une année de base exceptionnellement sèche (ex. 2000 à Oum El Bouaghi) peut représenter un état TEMPORAIRE de la végétation et non une référence représentative : elle peut gonfler l'amélioration ultérieure.
  Ce script compare deux exécutions complètes de l'étape 07 (intégration 1OAO) :
      CONCEPTION A : base = année A (ex. 2000 -> 2015 -> 2020 -> 2025)        CONCEPTION B : base = année B (ex. 1999 -> 2015 -> 2020 -> 2025)
  Il mesure l'écart de surfaces dégradées / stables / améliorées, l'accord pixel par pixel, les pixels qui changent de statut, et fait la même comparaison pour chaque sous-indicateur (couverture, SOC) disponible.

CE QU'IL NE FAIT PAS (à lire)
  - Il ne décide pas à votre place : la décision d'adopter une autre année de base se prend SÉPARÉMENT pour chaque indicateur selon la méthodologie UNCCD (la productivité LPD garde sa période de base UNCCD ; déplacer l'année de début ne corrige pas à lui seul l'effet de la sécheresse).
  - Un changement de classe LULC ne prouve pas un changement de stock de carbone.
  - Il ne prouve pas que l'année B est plus représentative : il faut vérifier la comparabilité des deux cartes (image, saison, capteur) et leur exactitude (étape 05B, fournie ici facultativement).

ENTRÉES : deux dossiers de résultats de l'étape 07 (ou deux rasters SDG1531_1OAO_primary.tif) ; facultatif : Accuracy_summary.csv (étape 05B), contexte climatique de l'étape 04B.
SORTIES : tableaux CSV, carte de désaccord, rapport HTML d'étape.
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

AREA_NAME = "Oum El Bouaghi (Algeria)"
REPORT_LANG = "en"
DESIGN_A_LABEL = "Baseline 2000"            # conception A : année de base d'origine
DESIGN_B_LABEL = "Baseline 1999"            # conception B : année de base proposée
DIAGNOSTIC_YEARS = ["2000"]                 # années à usage diagnostique (sécheresse documentée), jamais seule référence
BASELINE_YEAR_A, BASELINE_YEAR_B = "2000", "1999"
NA = 127                                     # code « non évalué » des rasters de l'étape 07
CODES = (-1, 0, 1)
LABELS = {-1: "Degraded", 0: "Stable", 1: "Improved"}
AGREEMENT_FLAG = 90.0                        # accord (%) en dessous duquel le choix de l'année de base change matériellement le résultat
REL_DIFF_FLAG = 20.0                         # écart relatif (%) de la surface dégradée au-delà duquel il est signalé
OA_FLAG = 85.0
YEAR_ROLES = {   # année : (rôle EN, justification EN, rôle FR, justification FR) — repris dans les rapports (choix des dates)
    1999: ("Baseline candidate", "Normal growing season just before the exceptional drought: a representative land-cover state for the start of the series, subject to comparability and accuracy checks (stages 05B and 08).",
           "Base candidate", "Saison de végétation normale juste avant la sécheresse exceptionnelle : état d'occupation du sol représentatif du début de la série, sous réserve des contrôles de comparabilité et d'exactitude (étapes 05B et 08)."),
    2000: ("Diagnostic year", "Nominal start of the UNCCD baseline period and of the MODIS series, but a documented drought year: kept to quantify the sensitivity of the results to climate, never the sole reference (excluded from the main matrices and from the land-cover vote of stage 02, analysed in the sensitivity run).",
           "Année diagnostique", "Début nominal de la période de base UNCCD et de la série MODIS, mais année de sécheresse documentée : conservée pour quantifier la sensibilité des résultats au climat, jamais seule référence (exclue des matrices principales et du vote de couverture de l'étape 02, analysée dans l'analyse de sensibilité)."),
    2007: ("Mid-baseline witness", "Normal year inside the 2000–2015 baseline period, 8 years from both 1999 and 2015: an independent check that the 2000 anomaly is transient and of the timing of change.",
           "Témoin de mi-période de base", "Année normale au milieu de la période de base 2000–2015, à 8 ans de 1999 et de 2015 : contrôle indépendant du caractère transitoire de l'anomalie de 2000 et du moment des changements."),
    2015: ("End of the baseline period", "End of the UNCCD baseline period (2000–2015) and start of the monitoring period.",
           "Fin de la période de base", "Fin de la période de base UNCCD (2000–2015) et début de la période de suivi."),
    2020: ("Intermediate monitoring year", "Mid-point of the monitoring period, 5 years from 2015 and 2025: separates early from late change.",
           "Année de suivi intermédiaire", "Milieu de la période de suivi, à 5 ans de 2015 et de 2025 : distingue le changement précoce du changement tardif."),
    2025: ("Latest monitoring year", "End of the series. A rainfall deficit does not necessarily mean a vegetation response: the climate table compares the rainfall z-score with the productivity rank before any exclusion.",
           "Dernière année de suivi", "Fin de la série. Un déficit de pluie n'implique pas forcément une réponse de la végétation : le tableau climatique compare l'écart réduit de la pluie au rang de productivité avant toute exclusion."),
}

# ============================================================================
# 1. LOGIQUE PURE (testée sans QGIS)
# ============================================================================
def assessed(a, nodata=NA):
    return (np.asarray(a) != nodata) & np.isin(np.asarray(a), CODES)


def class_areas(arr, px_ha):
    """Surface (ha) par statut -1 / 0 / 1 + non évalué."""
    a = np.asarray(arr)
    out = {c: float((a == c).sum()) * px_ha for c in CODES}
    out["not_assessed"] = float((~np.isin(a, CODES)).sum()) * px_ha
    return out


def compare_designs(a, b, px_ha):
    """
    Compare deux rasters de statut (-1 dégradé, 0 stable, 1 amélioré, 127 non évalué) définis sur la MÊME grille.
    Retourne : surfaces A et B, matrice d'accord 3x3 (ligne = A, colonne = B ; pixels évalués dans les deux), accord global (%), pixels dégradés dans A seul / B seul / les deux, kappa non rapporté.
    """
    a, b = np.asarray(a), np.asarray(b)
    if a.shape != b.shape:
        raise ValueError(f"Les deux rasters n'ont pas la même taille : {a.shape} et {b.shape} (mêmes grille et zone d'étude requises).")
    both = assessed(a) & assessed(b)
    M = np.zeros((3, 3), np.int64)
    for i, ca in enumerate(CODES):
        for j, cb in enumerate(CODES):
            M[i, j] = int(((a == ca) & (b == cb) & both).sum())
    n = int(M.sum())
    agree = 100.0 * float(np.trace(M)) / n if n else float("nan")
    deg_a, deg_b = (a == -1) & both, (b == -1) & both
    return {"area_a": class_areas(a, px_ha), "area_b": class_areas(b, px_ha), "matrix": M, "n_both": n, "agreement": agree, "both_ha": n * px_ha,
            "deg_both": int((deg_a & deg_b).sum()) * px_ha, "deg_a_only": int((deg_a & ~deg_b).sum()) * px_ha, "deg_b_only": int((deg_b & ~deg_a).sum()) * px_ha,
            "assessed_a_only": int((assessed(a) & ~assessed(b)).sum()) * px_ha, "assessed_b_only": int((assessed(b) & ~assessed(a)).sum()) * px_ha}


def disagreement_codes(a, b):
    """Carte de désaccord : 0 non évalué dans l'un ; 1 d'accord non dégradé ; 2 d'accord dégradé ; 3 dégradé seulement en A ; 4 dégradé seulement en B ; 5 autre changement de statut (stable <-> amélioré)."""
    a, b = np.asarray(a), np.asarray(b)
    both = assessed(a) & assessed(b)
    out = np.zeros(a.shape, np.uint8)
    out[both & (a == b) & (a != -1)] = 1
    out[both & (a == -1) & (b == -1)] = 2
    out[both & (a == -1) & (b != -1)] = 3
    out[both & (b == -1) & (a != -1)] = 4
    out[both & (a != b) & (a != -1) & (b != -1)] = 5
    return out


def share_of_assessed(areas):
    tot = sum(areas[c] for c in CODES)
    return {c: (100.0 * areas[c] / tot if tot else float("nan")) for c in CODES}


def design_table(cmp, label_a, label_b):
    """Tableau comparatif des surfaces : ha et % des terres évaluées pour chaque conception, et écart."""
    sa, sb = share_of_assessed(cmp["area_a"]), share_of_assessed(cmp["area_b"])
    rows = [["Status", f"{label_a} (ha)", f"{label_a} (%)", f"{label_b} (ha)", f"{label_b} (%)", "Difference B − A (ha)", "Difference B − A (points)"]]
    for c in CODES:
        rows.append([LABELS[c], f"{cmp['area_a'][c]:,.1f}", f"{sa[c]:.2f}", f"{cmp['area_b'][c]:,.1f}", f"{sb[c]:.2f}", f"{cmp['area_b'][c] - cmp['area_a'][c]:+,.1f}", f"{sb[c] - sa[c]:+.2f}"])
    rows.append(["Not assessed", f"{cmp['area_a']['not_assessed']:,.1f}", "", f"{cmp['area_b']['not_assessed']:,.1f}", "", f"{cmp['area_b']['not_assessed'] - cmp['area_a']['not_assessed']:+,.1f}", ""])
    return rows


def matrix_table(cmp, label_a, label_b, px_ha):
    M = cmp["matrix"]
    rows = [[f"{label_a} \\ {label_b} (ha)"] + [LABELS[c] for c in CODES] + ["Total"]]
    for i, c in enumerate(CODES):
        rows.append([LABELS[c]] + [f"{M[i, j] * px_ha:,.1f}" for j in range(3)] + [f"{M[i].sum() * px_ha:,.1f}"])
    rows.append(["Total"] + [f"{M[:, j].sum() * px_ha:,.1f}" for j in range(3)] + [f"{M.sum() * px_ha:,.1f}"])
    return rows


def read_accuracy_summary(path):
    """{année: (OA %, borne basse %, borne haute %)} depuis Accuracy_summary.csv de l'étape 05B ; {} si absent."""
    rows = sr_read_csv(path) if path else []
    out = {}
    for r in sr_dict_rows(rows):
        try:
            out[str(int(float(r["year"])))] = (sr_num(r["OA_%"]), sr_num(r.get("OA_lo_%")), sr_num(r.get("OA_hi_%")))
        except (KeyError, ValueError):
            continue
    return out


def baseline_checks(cmp, label_a, label_b, year_a, year_b, acc, lang="en"):
    """Contrôles de la comparaison : même couverture, accord, écart de la surface dégradée, comparabilité des cartes de base (exactitude)."""
    T = lambda x, y: x if lang == "en" else y
    out = []
    tot_a, tot_b = sum(cmp["area_a"][c] for c in CODES), sum(cmp["area_b"][c] for c in CODES)
    gap = abs(tot_a - tot_b) / max(tot_a, tot_b, 1e-9) * 100
    out.append((T("Same assessed land in both designs", "Même surface évaluée dans les deux conceptions"), "PASS" if gap <= 2 else "WARN", T(f"assessed area differs by {gap:.2f} % ({tot_a:,.0f} vs {tot_b:,.0f} ha)", f"la surface évaluée diffère de {gap:.2f} % ({tot_a:,.0f} contre {tot_b:,.0f} ha)")))
    out.append((T("Pixel agreement between the two designs", "Accord pixel par pixel entre les deux conceptions"), "PASS" if cmp["agreement"] >= AGREEMENT_FLAG else "WARN",
                T(f"{cmp['agreement']:.1f} % of the land assessed in both has the same status", f"{cmp['agreement']:.1f} % des terres évaluées dans les deux ont le même statut") + T(" — a lower value means the baseline year changes the result materially: report both", " — une valeur basse signifie que l'année de base change matériellement le résultat : rapporter les deux")))
    da, db = cmp["area_a"][-1], cmp["area_b"][-1]
    rel = 100.0 * (db - da) / da if da else float("nan")
    out.append((T("Degraded area: relative difference B vs A", "Surface dégradée : écart relatif B par rapport à A"), "PASS" if (rel == rel and abs(rel) <= REL_DIFF_FLAG) else "WARN", f"{db - da:+,.0f} ha ({rel:+.1f} %)"))
    both_bad = cmp["deg_both"]
    sw = cmp["deg_a_only"] + cmp["deg_b_only"]
    out.append((T("Degraded pixels that change status with the baseline year", "Pixels dégradés qui changent de statut avec l'année de base"), "INFO", T(f"{sw:,.0f} ha switch (A only {cmp['deg_a_only']:,.0f}, B only {cmp['deg_b_only']:,.0f}); {both_bad:,.0f} ha are degraded in both", f"{sw:,.0f} ha basculent (A seule {cmp['deg_a_only']:,.0f}, B seule {cmp['deg_b_only']:,.0f}) ; {both_bad:,.0f} ha sont dégradés dans les deux")))
    ya, yb = acc.get(str(year_a)), acc.get(str(year_b))
    if ya and yb:
        worse = yb[0] < ya[0] - 2.0 or yb[0] < OA_FLAG
        out.append((T("Accuracy of the candidate baseline map", "Exactitude de la carte de base candidate"), "WARN" if worse else "PASS",
                    T(f"overall accuracy {year_b}: {yb[0]:.1f} % vs {year_a}: {ya[0]:.1f} %", f"exactitude globale {year_b} : {yb[0]:.1f} % contre {year_a} : {ya[0]:.1f} %") + (T(" — the candidate is not demonstrably as reliable: reconsider", " — la candidate n'est pas démontrée aussi fiable : reconsidérer") if worse else "")))
    else:
        out.append((T("Accuracy of the candidate baseline map", "Exactitude de la carte de base candidate"), "WARN", T(f"no accuracy assessment for {year_a} and {year_b} (run stage 05B): comparability is not demonstrated", f"pas d'évaluation d'exactitude pour {year_a} et {year_b} (exécuter l'étape 05B) : la comparabilité n'est pas démontrée")))
    if str(year_b) in [str(y) for y in DIAGNOSTIC_YEARS]:
        out.append((T("Candidate baseline is not a diagnostic year", "La base candidate n'est pas une année diagnostique"), "FAIL", T(f"{year_b} is declared a diagnostic (drought) year", f"{year_b} est déclarée année diagnostique (sécheresse)")))
    return out


def table_design(roles, acc, excluded, lang="en"):
    """Conception temporelle : chaque date, son rôle, sa justification, l'intervalle depuis la date précédente et l'exactitude globale (étape 05B) si elle est fournie."""
    T = lambda x, y: x if lang == "en" else y
    ys = sorted(int(y) for y in roles)
    rows = [[T("Year", "Année"), T("Role", "Rôle"), T("Why this date", "Pourquoi cette date"), T("Years since previous", "Années depuis la précédente"), T("Overall accuracy (05B, %)", "Exactitude globale (05B, %)"), T("Used as", "Utilisée comme")]]
    for i, y in enumerate(ys):
        r = roles[y]
        a_ = acc.get(str(y))
        rows.append([y, r[0] if lang == "en" else r[2], r[1] if lang == "en" else r[3], (y - ys[i - 1]) if i else "", f"{a_[0]:.1f}" if a_ else T("not assessed", "non évaluée"), T("diagnostic only", "diagnostique seulement") if str(y) in [str(e) for e in excluded] else T("study date", "date d'étude")])
    return rows


JUSTIFICATION_EN = ("Given the exceptionally dry conditions documented for {ya} and the unusually large increase in mapped bareland relative to {yb}, followed by a substantial decline in later maps, the representativeness of {ya} "
                    "as the baseline for long-term land-cover change assessment was critically examined. The {yb} land-cover map was therefore considered as an alternative baseline, subject to classification comparability and accuracy assessment "
                    "(see the checks above). The {ya} map was retained as a diagnostic reference to evaluate the sensitivity of the results to the anomalous climatic conditions. This approach helps distinguish potentially transient drought-related surface "
                    "conditions from more persistent land-cover changes and reduces the risk of overestimating subsequent improvement. It does not by itself prove that {yb} is the better baseline, and the decision is taken separately for each sub-indicator "
                    "(land productivity keeps the UNCCD baseline period).")


# ============================================================================
# 2. RAPPORT HTML D'ÉTAPE (bloc partagé : voir tools/sdg_stage_report.py)
# ============================================================================
PIPELINE_BUILD = "2026.10-d7fe2da16525"
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


def baseline_stage_report(out_dir, results, acc, t0, params, inputs, area_name, year_a, year_b, label_a, label_b, px_ha, lang="en", log=print):
    """results = {"indicator": cmp, "land cover (robust)": cmp, ...} ; le premier est l'indicateur final."""
    T = lambda x, y: x if lang == "en" else y
    main = results["indicator"]
    checks = baseline_checks(main, label_a, label_b, year_a, year_b, acc, lang)
    summary = [T(f"Degraded land: {main['area_a'][-1]:,.0f} ha ({label_a}) vs {main['area_b'][-1]:,.0f} ha ({label_b}); pixel agreement {main['agreement']:.1f} %", f"Terres dégradées : {main['area_a'][-1]:,.0f} ha ({label_a}) contre {main['area_b'][-1]:,.0f} ha ({label_b}) ; accord {main['agreement']:.1f} %")]
    sections = [{"id": "ind", "title": T("SDG 15.3.1 indicator under the two baseline designs", "Indicateur ODD 15.3.1 selon les deux conceptions de base"), "intro": T("The two runs of stage 07 differ only by the baseline year of the land-cover and SOC sub-indicators; productivity keeps its UNCCD baseline period.", "Les deux exécutions de l'étape 07 ne diffèrent que par l'année de base des sous-indicateurs couverture et SOC ; la productivité garde sa période de base UNCCD."),
                 "tables": [(T("Areas by status", "Surfaces par statut"), design_table(main, label_a, label_b)), (T("Agreement matrix (pixels assessed in both)", "Matrice d'accord (pixels évalués dans les deux)"), matrix_table(main, label_a, label_b, px_ha))],
                 "images": [(T("Where the two designs disagree", "Où les deux conceptions divergent"), results.get("_png"))]}]
    for k, c in results.items():
        if k in ("indicator", "_png"):
            continue
        sections.append({"id": "sub_" + re.sub(r"\W+", "_", k), "title": T(f"Sub-indicator: {k}", f"Sous-indicateur : {k}"), "tables": [(T("Areas by status", "Surfaces par statut"), design_table(c, label_a, label_b)), (T("Agreement matrix", "Matrice d'accord"), matrix_table(c, label_a, label_b, px_ha))]})
    if YEAR_ROLES:
        sections.insert(0, {"id": "dates", "title": T("Choice of the study dates", "Choix des dates d'étude"), "intro": T("Each date has a stated role; a documented drought year is kept as a diagnostic date, not as the sole reference.", "Chaque date a un rôle déclaré ; une année de sécheresse documentée est conservée comme date diagnostique, jamais comme seule référence."),
                            "tables": [(T("Temporal design", "Conception temporelle"), table_design(YEAR_ROLES, acc, DIAGNOSTIC_YEARS, lang))]})
    sections.append({"id": "just", "title": T("Wording for the methods section (to adapt to your verified results)", "Formulation pour la section méthodes (à adapter à vos résultats vérifiés)"), "pre": JUSTIFICATION_EN.format(ya=year_a, yb=year_b)})
    L = [T("The decision to adopt another baseline year is taken separately for each sub-indicator under the UNCCD methodology: land productivity keeps its baseline period; shifting the start year alone does not remove the effect of a drought.", "La décision d'adopter une autre année de base se prend séparément pour chaque sous-indicateur selon la méthodologie UNCCD : la productivité garde sa période de base ; déplacer l'année de début ne retire pas à lui seul l'effet d'une sécheresse."),
         T("A change of land-cover class does not prove a change of soil carbon stock: SOC is reconstructed from class factors.", "Un changement de classe de couverture ne prouve pas un changement de stock de carbone : le SOC est reconstitué à partir de facteurs par classe."),
         T("Bareland that returns to other classes later is not proof that the earlier increase was artificial: crop rotation and classification errors also contribute.", "Des sols nus qui retournent ensuite vers d'autres classes ne prouvent pas que l'augmentation initiale était artificielle : la rotation des cultures et les erreurs de classification y contribuent aussi."),
         T("If a review of the imagery shows that the candidate year is not comparable (season, sensor) or less reliable, the choice must be reconsidered.", "Si l'examen des images montre que l'année candidate n'est pas comparable (saison, capteur) ou moins fiable, le choix doit être reconsidéré.")]
    A = [T("Run stage 07 twice with the same inputs, once with SOC_Class_<baseline A>_<end>.tif and once with SOC_Class_<baseline B>_<end>.tif; keep the two result folders.", "Exécuter l'étape 07 deux fois avec les mêmes entrées, une fois avec SOC_Class_<base A>_<fin>.tif et une fois avec SOC_Class_<base B>_<fin>.tif ; garder les deux dossiers de résultats."),
         T("Set BASELINE_YEAR_A / B, the labels and DIAGNOSTIC_YEARS at the top of this script.", "Régler BASELINE_YEAR_A / B, les libellés et DIAGNOSTIC_YEARS en tête de ce script."),
         T("Provide the stage 05B accuracy summary so that the comparability of the two baseline maps is checked.", "Fournir le résumé d'exactitude de l'étape 05B pour vérifier la comparabilité des deux cartes de base.")]
    R = ["UNCCD. Good Practice Guidance for SDG Indicator 15.3.1 (version 2) and its Addendum.", "Olofsson, P. et al. (2014). Good practices for estimating area and assessing accuracy of land change. Remote Sensing of Environment 148, 42–57."]
    spec = {"stage": "08", "title": T("Sensitivity to the baseline year", "Sensibilité à l'année de base"), "subtitle": f"{label_a} vs {label_b}", "lang": lang, "area": area_name, "started": t0, "out_dir": out_dir,
            "params": params, "inputs": inputs, "summary": summary, "checks": checks, "sections": sections, "limits": L, "adapt": A, "references": R}
    path = os.path.join(out_dir, "Stage_Report_08_Baseline_Sensitivity.html")
    write_stage_report(path, spec)
    log("[Rapport HTML] " + path)
    return path


# ============================================================================
# 3. COUCHE GDAL / QGIS (relue, non exécutable hors QGIS)
# ============================================================================
def read_raster(path):
    from osgeo import gdal
    ds = gdal.Open(path, gdal.GA_ReadOnly)
    if ds is None:
        raise RuntimeError(f"Raster illisible : {path}")
    return ds.GetRasterBand(1).ReadAsArray(), ds.GetGeoTransform()


def find_in(folder, pattern):
    hits = sr_find_files(folder, pattern)
    return hits[0] if hits else None


def run_comparison(folder_a, folder_b, out_dir, acc_csv=None, year_a=BASELINE_YEAR_A, year_b=BASELINE_YEAR_B, label_a=DESIGN_A_LABEL, label_b=DESIGN_B_LABEL, lang=REPORT_LANG, log=print):
    t0 = time.time()
    os.makedirs(out_dir, exist_ok=True)
    pairs = [("indicator", r"^SDG1531_1OAO_primary\.tif$"), ("land cover (robust)", r"^LC_Class_\d{4}_\d{4}_robust\.tif$"), ("land cover (strict)", r"^LC_Class_\d{4}_\d{4}_strict\.tif$"), ("SOC", r"^SOC_Class_on_LULC_grid\.tif$")]
    results, inputs, px_ha = {}, [], None
    for name, pat in pairs:
        pa, pb = find_in(folder_a, pat), find_in(folder_b, pat)
        if not pa or not pb:
            if name == "indicator":
                raise RuntimeError(f"SDG1531_1OAO_primary.tif introuvable dans {'A' if not pa else 'B'} : indiquez le dossier de résultats de l'étape 07.")
            continue
        a, gt = read_raster(pa)
        b, _gt = read_raster(pb)
        px_ha = px_ha or abs(gt[1] * gt[5]) / 10000.0
        results[name] = compare_designs(a, b, px_ha)
        inputs += [{"label": f"{name} — {label_a}", "path": pa}, {"label": f"{name} — {label_b}", "path": pb}]
        if name == "indicator":
            results["_png"] = sr_render_array(disagreement_codes(a, b), os.path.join(out_dir, "_temp", "disagreement.png"), {1: ("#e0e0e0", "Same status, not degraded"), 2: ("#b2182b", "Degraded in both"), 3: ("#ef8a62", f"Degraded only with {label_a}"), 4: ("#67a9cf", f"Degraded only with {label_b}"), 5: ("#fddbc7", "Stable <-> improved")}, title=f"{label_a} vs {label_b}")
            with open(os.path.join(out_dir, "Baseline_Comparison_indicator.csv"), "w", newline="", encoding="utf-8-sig") as f:
                csv.writer(f, delimiter=";").writerows(design_table(results[name], label_a, label_b))
    acc = read_accuracy_summary(acc_csv) if acc_csv else {}
    params = {"Design A": f"{label_a} ({folder_a})", "Design B": f"{label_b} ({folder_b})", "Diagnostic years": ", ".join(DIAGNOSTIC_YEARS), "Pixel agreement flag": f"{AGREEMENT_FLAG} %", "Accuracy summary (05B)": acc_csv or "(not provided)"}
    rep = baseline_stage_report(out_dir, results, acc, t0, params, inputs, AREA_NAME, year_a, year_b, label_a, label_b, px_ha, lang, log)
    import shutil
    shutil.rmtree(os.path.join(out_dir, "_temp"), ignore_errors=True)
    return rep


def _stop(msg):
    print("[Arrêt] " + msg)
    try:
        from qgis.PyQt.QtWidgets import QMessageBox
        QMessageBox.information(None, "08", msg)
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
            QMessageBox.critical(None, "08 — erreur", tb[-1500:])
        except Exception:
            pass


def _main():
    from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox
    from qgis.PyQt.QtCore import QUrl
    fa = QFileDialog.getExistingDirectory(None, f"08 — dossier de résultats de l'étape 07, CONCEPTION A ({DESIGN_A_LABEL})")
    if not fa:
        return _stop("Annulé : aucun fichier produit.")
    fb = QFileDialog.getExistingDirectory(None, f"08 — dossier de résultats de l'étape 07, CONCEPTION B ({DESIGN_B_LABEL})", os.path.dirname(fa))
    if not fb or os.path.normpath(fa) == os.path.normpath(fb):
        return _stop("Dossier B absent ou identique au dossier A : annulé.")
    acc, _f = QFileDialog.getOpenFileName(None, "08 — Accuracy_summary.csv de l'étape 05B (facultatif : Annuler pour passer)", os.path.dirname(fa), "CSV (*.csv)")
    out = QFileDialog.getExistingDirectory(None, "08 — dossier de SORTIE", os.path.dirname(fa))
    if not out:
        return _stop("Annulé : aucun fichier produit.")
    rep = run_comparison(fa, fb, os.path.join(out, "08_Baseline_Sensitivity"), acc or None)
    QMessageBox.information(None, "08 terminé", f"Rapport : {rep}")
    try:
        from qgis.PyQt.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(rep))
    except Exception:
        pass


# ====================== MAIN ======================
main()
