# -*- coding: utf-8 -*-
# SDG 15.3.1 REFERENCE PIPELINE — STAGE 02 / 08 : Land productivity dynamics (LPD) from MODIS — QGIS
"""
MODIS_LPD_COMPLETE_QGIS.py
UNCCD / SDG 15.3.1 — SOUS-INDICATEUR PRODUCTIVITÉ (LPD) À PARTIR DE MODIS TERRA  |  <AREA_NAME>  |  QGIS

CHAÎNE COMPLÈTE, DANS L'ORDRE (chaque étape est contrôlée avant la suivante) :
   MODIS MOD13Q1 (2000-2025)  ->  1. QUALITÉ TEMPORELLE (n_valid)  ->  2. SCÉNARIOS DE SENSIBILITÉ
   ->  3. TRAJECTORY (Sen + Mann-Kendall)  ->  4. STATE  ->  5. PERFORMANCE  ->  6. LPD 3 / 5 CLASSES
   ->  7. FIABILITÉ, VARIANTE CORRIGÉE DE LA PLUIE  ->  8. COMPARAISON DES SCÉNARIOS  ->  9. STATISTIQUES + RAPPORT

ENTRÉES
  Dossier MODIS (exports GEE, MODIS_Annual_Productivity_GEE.js) :
      01_Annual_Productivity_MODIS_2000_2025.tif   NDVI moyen mars-juin, une bande par année
      01b_Annual_ValidPeriods_MODIS_2000_2025.tif  nombre de composites de 16 jours retenus (n_valid)
  Facultatif :
      scénario A : mêmes exports avec QA_MAX = 0 et le suffixe _QA0 (voir le script GEE)
      cartes LULC des années de LULC_YEARS (30 m ; l'année diagnostique, ex. 2000, n'est pas utilisée : sécheresse) -> Performance, LPD, statistiques par occupation du sol
      couches pluie et altitude (stratification de Performance)
      ClimateEngine.csv (CHIRPS journalier) -> variante corrigée de la pluie

SCÉNARIOS DE SENSIBILITÉ
      A : QA <= 0 (bonnes données seulement), >= 5 composites   (exports _QA0)
      B : QA <= 1 (bon + marginal),            >= 5 composites   (scénario principal, exports GEE)
      C : QA <= 1,                             >= 6 composites   (dérivé ici à partir de n_valid)
  Pour chacun : Trajectory, State, Performance, LPD ; puis accords avec B (Sen, tau, Mann-Kendall, State, LPD).

SORTIES (dossier choisi)
  00_QA_Temporal_Coverage/  01c_MODIS_DataQuality.tif (11 bandes) + répartition de n_valid par année
  01_Trajectory_State/<scénario>/  03_Trajectory_Sen_Kendall.tif, 04_State.tif (+ State_Reliability_Class.tif pour B)
  02_Performance/  Performance_Layers.tif + statistiques de zones et de seuils
  03_LPD/  LPD_3class / LPD_5class / robustesse (B), LPD 3 classes des scénarios A et C, variante corrigée de la pluie
  04_Statistics/  statistiques de type UNCCD (surfaces par classe, par occupation du sol, par groupe fonctionnel),
                  couverture, sensibilité, fiabilité, comparaison des scénarios
  MODIS_LPD_REPORT.txt

À LIRE AVANT D'INTERPRÉTER
  - Les seuils (|tau| 0,30, State ±10 %, ratio de Performance 0,50, P90, minima d'années) sont des paramètres ANALYTIQUES
    de l'étude, pas des seuils UNCCD ; leur sensibilité est quantifiée.
  - Le LPD principal ne retire pas l'effet du climat : le déclin de la pluie 2021-2025 (~ -30 % par rapport à 2000-2015) peut
    produire du « dégradé ». La variante corrigée de la pluie en est la borne basse.
  - LPD = composante Productivité ; ce n'est PAS le SDG 15.3.1 complet (Land Cover et SOC sont nécessaires).
"""

import os
import platform
# ============================== CONFIGURATION DE LA CHAÎNE (à adapter pour une autre zone d'étude) ==============================
AREA_TAG = "Saida"                 # étiquette des cartes : LULC_<AREA_TAG>_<année>.tif
AREA_NAME = "Saida (Algeria)"      # nom de la zone, affiché dans les rapports HTML
REPORT_LANG = "en"                          # langue des rapports HTML d'étape : "en" ou "fr"
DIAGNOSTIC_YEARS = ["2000"]                 # années à usage DIAGNOSTIQUE (sécheresse documentée) : jamais seule année de référence ; non cochées par défaut en 04B ; signalées en 06 / 07 si elles servent de base
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
LULC_YEARS = [1999, 2000, 2007, 2015, 2020, 2025]   # années des cartes LULC utilisées par cette étape (à adapter ; 2000 = année de sécheresse exceptionnelle à Oum El Bouaghi)
LPD_PERIOD = "monitoring"        # "monitoring" : LPD de la période de SUIVI (série complète, état 2021-2025 contre la base) ; "baseline" : LPD de la période de BASE UNCCD (série arrêtée à 2015, état 2013-2015 contre 2000-2012) ; l'étape 07 (deux fenêtres) demande les deux
BASELINE_STATE_END = 2012         # LPD_PERIOD = "baseline" : fin de la moyenne de référence de l'ÉTAT (début de série -> cette année)
BASELINE_STATE_RECENT = (2013, 2015)   # LPD_PERIOD = "baseline" : fenêtre « récente » de l'ÉTAT ; 3 années sont sensibles à une seule année sèche ou humide : tester (2011, 2015) avec BASELINE_STATE_END = 2010
TREND_START_YEAR = 2000          # première année de la série MODIS utilisée (trajectoire, état, régression pluie) : 2000 = convention UNCCD (base 2000-2015) ; 2003 = test après la faiblesse de 2001-2002 (voir l'étape 02B)
RAIN_WINDOW_MONTHS = (9, 6)        # Saida : (9, 6) = sept.(N-1) -> juin(N), retenue en phase 2.2 avec CHIRPS journalier (skill 0.608 ; Sep-Mai 0.607, quasi-egal) ; (12, 4) = la pire a Saida
# =================================================================================================================================

PIPELINE_BUILD = "2026.10-1c9809135f4f"
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

# >>> STAGE_BUILDER_BEGIN
def lpd_stage_report(out_root, dirs, report_lines, t0, params, inputs, area_name, lang="en", log=print):
    """Rapport HTML de l'étape 02 (LPD) : lit les CSV et rasters écrits par le script. Ne modifie rien ; une erreur ici n'arrête jamais le traitement."""
    S, QA, SC, PF, LP = dirs["stats"], dirs["qa"], dirs["scen"], dirs["perf"], dirs["lpd"]
    rd = lambda d, n: sr_read_csv(os.path.join(d, n))
    area, cov, scen, grid, rel = rd(S, "LPD_Area_Statistics.csv"), rd(S, "LPD_Coverage.csv"), rd(S, "Scenario_Comparison_vs_B.csv"), rd(S, "LPD_Sensitivity_Grid.csv"), rd(S, "LPD_Reliability_Statistics.csv")
    summary, checks = [], []
    # ---- résultats : LPD 3 classes par variante
    var3 = {}
    for r in sr_dict_rows(area):
        if r.get("scheme") == "LPD 3 classes":
            var3.setdefault(r["variant"], {})[r["label"]] = sr_num(r.get("percent_of_assessed_area"))
    for v, d in var3.items():
        summary.append(f"{v} : " + " | ".join(f"{k} {x:.1f} %" for k, x in d.items()) + (" (of the assessed area)" if lang == "en" else " (de la surface évaluée)"))
    adj = [v for v in var3 if "RainAdjusted" in v]
    # ---- contrôles
    cv = {r["Layer"]: sr_num(r["Percent_of_study_area"]) for r in sr_dict_rows(cov)}
    lpd_pct = next((x for k, x in cv.items() if k.startswith("LPD valid")), float("nan"))
    traj_pct = next((x for k, x in cv.items() if k.startswith("Trajectory valid")), float("nan"))
    if cv:
        checks.append(("LPD coverage of the study area" if lang == "en" else "Couverture du LPD", "PASS" if lpd_pct >= 80 else "WARN", f"{lpd_pct:.1f} % of the study area has a valid LPD (threshold 80 %)" if lang == "en" else f"{lpd_pct:.1f} % de la zone a un LPD valide (seuil 80 %)"))
        checks.append(("Trajectory coverage" if lang == "en" else "Couverture de la Trajectory", "PASS" if traj_pct >= 95 else "WARN", f"{traj_pct:.1f} %"))
    else:
        checks.append(("Coverage table" if lang == "en" else "Tableau de couverture", "FAIL", "LPD_Coverage.csv missing"))
    agree = []
    for r in sr_dict_rows(scen):
        for col in ("MannKendall_class_agreement_%", "state_agreement_%"):
            x = sr_num(r.get(col))
            if x == x:
                agree.append((r.get("scenario", "?"), col, x))
    if agree:
        mn = min(a[2] for a in agree)
        checks.append(("Scenario agreement with B (QA / minimum composites)" if lang == "en" else "Accord des scénarios avec B", "PASS" if mn >= 90 else "WARN", f"minimum {mn:.1f} % (threshold 90 %)" if lang == "en" else f"minimum {mn:.1f} % (seuil 90 %)"))
    else:
        checks.append(("Scenario comparison" if lang == "en" else "Comparaison des scénarios", "INFO", "scenarios A / C not provided" if lang == "en" else "scénarios A / C non fournis"))
    dg = [sr_num(r.get("degraded_pct")) for r in sr_dict_rows(grid)]
    dg = [x for x in dg if x == x]
    if dg:
        rng = max(dg) - min(dg)
        checks.append(("Sensitivity to the analytical thresholds" if lang == "en" else "Sensibilité aux seuils analytiques", "PASS" if rng <= 3 else "WARN", f"degraded share varies by {rng:.1f} points over the threshold grid" if lang == "en" else f"la part dégradée varie de {rng:.1f} points sur la grille de seuils"))
    checks.append(("Rain-adjusted variant" if lang == "en" else "Variante corrigée de la pluie", "PASS" if adj else "WARN", ("present: " + ", ".join(adj)) if adj else ("missing: the GPG requires productivity calibrated on moisture" if lang == "en" else "absente : le GPG exige une productivité calibrée sur l'humidité")))
    rr = sr_dict_rows(rel)
    if rr:
        r1 = next((sr_num(r.get("share_of_LPD_%")) for r in rr if str(r.get("reliability_class")) == "1"), float("nan"))
        if r1 == r1:
            checks.append(("Pixels with reliable temporal data" if lang == "en" else "Pixels à données temporelles fiables", "PASS" if r1 >= 95 else "WARN", f"{r1:.2f} % of the LPD in reliability class 1"))
    _vote, _diag = [str(y) for y in globals().get("YEARS", [])], [str(d) for d in globals().get("DIAGNOSTIC_YEARS", [])]
    if _vote:
        checks.append(("Dates voting for the dominant functional group" if lang == "en" else "Dates qui votent pour le groupe fonctionnel dominant", "PASS" if (len(_vote) % 2 == 1 and not set(_vote) & set(_diag)) else "WARN",
                       (f"{', '.join(_vote)} ({len(_vote)} dates" + (f"; diagnostic years excluded: {', '.join(_diag)}" if _diag else "") + "): an odd number allows a strict majority, and no drought year votes") if lang == "en" else
                       (f"{', '.join(_vote)} ({len(_vote)} dates" + (f" ; années diagnostiques exclues : {', '.join(_diag)}" if _diag else "") + ") : un nombre impair permet une majorité stricte et aucune année de sécheresse ne vote")))
    tot_ha = sum(sr_num(r.get("area_ha"), 0) for r in sr_dict_rows(area) if r.get("scheme") == "LPD 3 classes" and r.get("variant") == (next(iter(var3)) if var3 else ""))
    # ---- sections
    qa_tabs = [("n_valid summary", rd(QA, "QA_nvalid_summary.csv")), ("n_valid distribution by year", rd(QA, "QA_nvalid_distribution_by_year.csv")), ("Coverage of the layers", cov)]
    lc = sorted([f for f in os.listdir(S) if f.startswith("LPD_by_LandCover_")]) if os.path.isdir(S) else []
    maps = []
    for fn, title, cl in (("LPD_3class_{}.tif", "LPD 3 classes (main scenario)", {-1: ("#d73027", "Degraded"), 0: ("#fee08b", "Stable"), 1: ("#1a9850", "Improved")}),
                          ("LPD_5class_{}.tif", "LPD 5 classes (main scenario)", {1: ("#d73027", "Declining"), 2: ("#fc8d59", "Moderate decline"), 3: ("#fee08b", "Stressed"), 4: ("#a6d96a", "Stable"), 5: ("#1a9850", "Improving")}),
                          ("LPD_3class_{}_RainAdjusted.tif", "LPD 3 classes (rain-adjusted)", {-1: ("#d73027", "Degraded"), 0: ("#fee08b", "Stable"), 1: ("#1a9850", "Improved")})):
        p = os.path.join(LP, fn.format(params.get("main_scenario", "B_QA1_min5")))
        png = sr_quicklook(p, os.path.join(out_root, "_temp", os.path.basename(p) + ".png"), cl, title=title)
        if png:
            maps.append((title, png))
    sections = [
        {"id": "inq", "title": "Input data quality (MODIS)" if lang == "en" else "Qualité des données d'entrée (MODIS)", "intro": "Number of valid 16-day composites per pixel and year; the productivity of a year is the mean NDVI of the retained composites (March–June)." if lang == "en" else "Nombre de composites de 16 jours valides par pixel et par année ; la productivité d'une année est le NDVI moyen des composites retenus (mars–juin).", "tables": qa_tabs},
        {"id": "sens", "title": "Sensitivity scenarios and thresholds" if lang == "en" else "Scénarios de sensibilité et seuils", "intro": "A = good data only, B = good + marginal (main), C = at least 6 composites. Agreement with B quantifies how much the result depends on the QA choice." if lang == "en" else "A = bonnes données seules, B = bon + marginal (principal), C = au moins 6 composites. L'accord avec B mesure la dépendance au choix du QA.", "tables": [("Scenario comparison versus B", scen), ("Threshold grid (tau × performance)", grid)]},
        {"id": "perf", "title": "Performance (relative productivity)" if lang == "en" else "Performance (productivité relative)", "tables": [("Zone statistics", rd(PF, "Performance_Zone_Statistics.csv")), ("Low-performance share by threshold", rd(PF, "Performance_Threshold_Table.csv"))]},
        {"id": "res", "title": "Land productivity dynamics (LPD) results" if lang == "en" else "Résultats de la dynamique de productivité des terres (LPD)", "intro": "Areas by class and variant; the rain-adjusted variant removes the part of the productivity change explained by rainfall." if lang == "en" else "Surfaces par classe et par variante ; la variante corrigée de la pluie retire la part du changement de productivité expliquée par la pluie.",
         "tables": [("Area statistics", area), ("Reliability of the LPD", rel), ("By functional group", rd(S, "LPD_by_FunctionalGroup.csv"))] + ([(f"By land cover ({lc[-1][17:-4]})", rd(S, lc[-1]))] if lc else [])},
        {"id": "maps", "title": "Maps" if lang == "en" else "Cartes", "images": maps},
        {"id": "log", "title": "Processing log" if lang == "en" else "Journal du traitement", "pre": "\n".join(report_lines[-150:])},
    ]
    L = [("The main LPD does not remove the effect of climate: a rainfall decline can produce 'degraded'. The rain-adjusted variant is the lower bound." if lang == "en" else "Le LPD principal ne retire pas l'effet du climat : un déclin de la pluie peut produire du « dégradé ». La variante corrigée de la pluie en est la borne basse."),
         ("Thresholds (|tau| 0.30, State ±10 %, Performance ratio 0.50, P90, minimum years) are analytical parameters of this study, not UNCCD thresholds; their sensitivity is quantified above." if lang == "en" else "Les seuils (|tau| 0,30, State ±10 %, ratio de Performance 0,50, P90, minima d'années) sont des paramètres analytiques de l'étude, pas des seuils UNCCD ; leur sensibilité est quantifiée."),
         ("250 m pixels are mixed; Performance only concerns cropland, fallow, forest and rangeland." if lang == "en" else "Les pixels de 250 m sont mixtes ; Performance ne concerne que cultures, jachère, forêt et parcours."),
         ("LPD is the productivity component only, not the full SDG 15.3.1." if lang == "en" else "Le LPD est la composante Productivité seulement, pas le SDG 15.3.1 complet.")]
    A = ["Stage 01 (Google Earth Engine): set the asset path of the new study-area boundary, the export CRS (the UTM zone of the area) and the years; export the productivity and n_valid stacks." if lang == "en" else "Étape 01 (GEE) : indiquer l'asset de la limite de la nouvelle zone, le CRS d'export (fuseau UTM de la zone) et les années ; exporter les piles de productivité et de n_valid.",
         "Provide the new study-area shapefile, optionally the LULC maps of the new area (Performance and statistics by land cover), rainfall (CHIRPS CSV) and elevation." if lang == "en" else "Fournir le shapefile de la nouvelle zone, et facultativement les cartes LULC, la pluie (CSV CHIRPS) et l'altitude.",
         "The growing season (March–June here) must match the vegetation calendar of the new area: change SEASON_START_MONTH / SEASON_END_MONTH in the GEE script." if lang == "en" else "La saison de végétation (mars–juin ici) doit correspondre au calendrier de la nouvelle zone : modifier SEASON_START_MONTH / SEASON_END_MONTH dans le script GEE.",
         "Review the analytical thresholds in the script header and re-run the sensitivity grid." if lang == "en" else "Revoir les seuils analytiques en tête de script et relancer la grille de sensibilité."]
    R = ["Sen, P.K. (1968). Estimates of the regression coefficient based on Kendall's tau. Journal of the American Statistical Association 63, 1379–1389.", "Mann, H.B. (1945). Nonparametric tests against trend. Econometrica 13, 245–259.",
         "Didan, K. (2021). MODIS/Terra Vegetation Indices 16-Day L3 Global 250m SIN Grid V061. NASA EOSDIS LP DAAC. doi:10.5067/MODIS/MOD13Q1.061", "UNCCD. Good Practice Guidance for SDG Indicator 15.3.1 (version 2) and its Addendum.",
         "Funk, C. et al. (2015). The climate hazards infrared precipitation with stations — a new environmental record for monitoring extremes. Scientific Data 2, 150066."]
    spec = {"stage": "02", "title": "Land productivity dynamics (LPD) from MODIS" if lang == "en" else "Dynamique de productivité des terres (LPD) à partir de MODIS", "subtitle": "Trajectory + State + Performance", "lang": lang, "area": area_name, "started": t0, "out_dir": out_root,
            "params": params, "inputs": inputs, "summary": summary, "checks": checks, "sections": sections, "limits": L, "adapt": A, "references": R}
    path = os.path.join(out_root, "Stage_Report_02_LPD.html")
    write_stage_report(path, spec)
    log("[Rapport HTML] " + path)
    return path
# <<< STAGE_BUILDER_END
import re
import csv
import math
import time
import warnings
import datetime as dt
import traceback

import numpy as np

from osgeo import gdal, osr
try:
    from osgeo import ogr
except ImportError:      # indisponible : la limite vectorielle sera ignorée
    ogr = None

from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox, QApplication, QInputDialog
from qgis.core import QgsProject, QgsRasterLayer, QgsPalettedRasterRenderer


# ============================================================================
# 1. PARAMÈTRES ET OUTILS REPRIS DU SCRIPT LPD_COMPLETE_QGIS.py (code déjà testé)
# ============================================================================


YEARS = [y for y in LULC_YEARS if str(y) not in [str(d) for d in DIAGNOSTIC_YEARS]]   # dates du VOTE de la classe dominante : l'année diagnostique (sécheresse) n'y vote pas ; nombre impair = majorité stricte possible
CLASS_NAMES = {
    1: "Built-up",
    2: "Water",
    3: "Sebkha",
    4: "Bareland / Rock",
    5: "Cropland",
    6: "Fallow",
    7: "Forest / Matorral",
    8: "Rangeland",
}
REFERENCE_CLASSES = [5, 6, 7, 8]
ZONE_DESCRIPTIONS = {
    1: "Forest dominant",
    2: "Cropland dominant",
    3: "Rangeland dominant",
    4: "Fallow dominant",
    5: "Rangeland-Fallow dynamic",
    6: "Rangeland-Cropland dynamic",
    7: "Agro-pastoral dynamic R+C+F",
    8: "Other mixed (reference classes)",
}
DOMINANCE_FRACTION = 0.50
DYNAMIC_PAIR_FRACTION = 0.70
AGRO_PASTORAL_FRACTION = 0.70
MIN_REFERENCE_FRACTION = 0.50
MIN_VALID_LULC_YEARS = 4
PERFORMANCE_PERCENTILE = 90.0
PERFORMANCE_RATIO_THRESHOLD = 0.50
ENV_RAINFALL_BINS = 3
ENV_ELEVATION_BINS = 3
RAINFALL_BREAKS = None
ELEVATION_BREAKS = None
CV_WARNING_THRESHOLD = 0.50
PERFORMANCE_SENSITIVITY_THRESHOLDS = [0.40, 0.50, 0.60]
NODATA_ZONE = 0
NODATA_FLOAT = -9999.0
NODATA_FLAG_UINT8 = 255
GEE_SHARD_RE = re.compile(r"-\d{10}-\d{10}(\.[A-Za-z]+)$")
_EXCLUDED_PRODUCTIVITY_WORDS = (
    "qa", "lpd_", "longterm", "long_term", "potential", "ratio",
    "performance", "trajectory", "state", "kendall", "sen_"
)
_EXCLUDED_LULC_WORDS = (
    "change", "transition", "stagemask", "canvas", "preview",
    "confidence", "qa_", "area", "lpd_", "sebkha_water_state",
    "uncertainty", "publication", "visualedit", "independentpreview"
)
NODATA_I16 = -9999
NODATA_U8 = NODATA_FLAG_UINT8
LPD3_LABELS = {-1: "Degraded", 0: "Stable", 1: "Improved"}
LPD5_LABELS = {
    1: "Declining", 2: "Moderate decline", 3: "Stressed (stable but constrained)",
    4: "Stable", 5: "Improving",
}
LULC_MIN_ACCEPT_SCORE = -300
LULC_VALIDATION_SAMPLE_PX = 1500
FILE_NOTES = []
YEAR_RE = re.compile(r"(?<!\d)(19[89]\d|20[0-4]\d)(?!\d)")
if LPD_PERIOD == "baseline":          # LPD de la période de BASE UNCCD : série arrêtée à 2015 ; état = moyenne (début-2012) contre 2013-2015
    TREND_END_YEAR, BASELINE_YEARS, RECENT_YEARS = 2015, (TREND_START_YEAR, BASELINE_STATE_END), BASELINE_STATE_RECENT
elif LPD_PERIOD == "monitoring":      # LPD de la période de SUIVI : série complète ; état = moyenne (début-2015) contre 2021-2025
    TREND_END_YEAR, BASELINE_YEARS, RECENT_YEARS = 9999, (TREND_START_YEAR, 2015), (2021, 2025)
else:
    raise RuntimeError("LPD_PERIOD doit valoir \"baseline\" ou \"monitoring\" (valeur actuelle : {!r}).".format(LPD_PERIOD))


try:
    _QMB_YES, _QMB_NO = QMessageBox.Yes, QMessageBox.No
except AttributeError:
    _QMB_YES = QMessageBox.StandardButton.Yes
    _QMB_NO = QMessageBox.StandardButton.No



# ----- fonctions pures et outils raster/fichiers (LPD_COMPLETE) -----


def classify_functional_groups(class_counts, valid_n):
    """
    class_counts : {class_id: uint8 array} number of dates in each class
                   (for class ids in REFERENCE_CLASSES)
    valid_n      : uint8 array, number of valid LULC dates per pixel
    returns      : uint8 array with group IDs 1..8 (0 = not in reference)
    """
    denominator = np.maximum(valid_n.astype(np.float32), 1.0)

    forest_f = class_counts[7].astype(np.float32) / denominator
    crop_f = class_counts[5].astype(np.float32) / denominator
    fallow_f = class_counts[6].astype(np.float32) / denominator
    range_f = class_counts[8].astype(np.float32) / denominator

    reference_f = forest_f + crop_f + fallow_f + range_f

    # A pixel is part of the reference population only if the MAJORITY of its
    # valid dates belongs to classes 5-8 (Built-up/Water/Sebkha/Bareland are
    # excluded, not merely ignored).
    enough = (
        (valid_n >= MIN_VALID_LULC_YEARS)
        & (reference_f > MIN_REFERENCE_FRACTION)
    )

    functional = np.zeros(valid_n.shape, dtype=np.uint8)

    def assign(condition, value):
        m = enough & (functional == 0) & condition
        functional[m] = value

    # Dominant groups: STRICT majority. A 3/6 vs 3/6 split is NOT dominant.
    assign(forest_f > DOMINANCE_FRACTION, 1)
    assign(crop_f > DOMINANCE_FRACTION, 2)
    assign(range_f > DOMINANCE_FRACTION, 3)
    assign(fallow_f > DOMINANCE_FRACTION, 4)

    # Dynamic groups.
    assign(
        ((range_f + fallow_f) >= DYNAMIC_PAIR_FRACTION)
        & (range_f >= 0.20) & (fallow_f >= 0.20) & (crop_f < 0.20),
        5
    )
    assign(
        ((range_f + crop_f) >= DYNAMIC_PAIR_FRACTION)
        & (range_f >= 0.20) & (crop_f >= 0.20) & (fallow_f < 0.20),
        6
    )
    assign(
        ((range_f + crop_f + fallow_f) >= AGRO_PASTORAL_FRACTION)
        & (range_f >= 0.10) & (crop_f >= 0.10) & (fallow_f >= 0.10),
        7
    )

    # Everything else that passed the reference test.
    assign(np.ones(valid_n.shape, dtype=bool), 8)

    return functional


def bin_continuous(arr, reference_mask, n_bins, breaks=None):
    """
    Classify a continuous layer into classes 1..n (0 = missing).
    Edges are either user supplied (breaks) or quantiles computed on the
    REFERENCE population only (so each class has a comparable number of
    reference pixels). Returns (bins uint8, edges list).
    """
    if not (2 <= int(n_bins) <= 9):
        raise RuntimeError("Le nombre de classes doit être entre 2 et 9.")

    finite = np.isfinite(arr)

    if breaks is not None:
        edges = sorted(float(b) for b in breaks)
        method = "user"
    else:
        vals = arr[reference_mask & finite]
        if vals.size == 0:
            raise RuntimeError(
                "Aucune valeur de la couche environnementale ne tombe dans la "
                "population de référence (couche vide ou hors emprise ?)."
            )
        qs = np.linspace(0.0, 1.0, int(n_bins) + 1)[1:-1]
        edges = sorted(set(float(e) for e in np.quantile(vals, qs)))
        method = "quantile"

    if len(edges) + 1 > 9:
        raise RuntimeError("Trop de bornes : 9 classes maximum.")

    bins = np.zeros(arr.shape, dtype=np.uint8)
    bins[finite] = (np.digitize(arr[finite], edges) + 1).astype(np.uint8)
    return bins, edges, method


def build_stratified_zones(
    functional, reference_mask, rain_bins=None, elev_bins=None,
    soil_codes=None, min_pixels=2000
):
    """
    zone = functional*1000 + rain*100 + elevation*10 + soil

    Two fallbacks to the PARENT functional zone (functional*1000):
      1. a pixel with NO VALUE (class 0) in ANY active environmental layer is
         never given a stratified zone: a zone with a 0 digit in an active
         layer would pool pixels without real environmental information;
      2. a stratified zone smaller than min_pixels.
    Returns (zones int16, n_zones_before, n_zones_after, fallback_info).
    """
    layers = [
        ("rain", rain_bins, 100),
        ("elevation", elev_bins, 10),
        ("soil", soil_codes, 1),
    ]
    active = [(n, a, w) for (n, a, w) in layers if a is not None]

    parent = functional.astype(np.int32) * 1000
    zones = np.zeros(functional.shape, dtype=np.int32)
    zones[reference_mask] = parent[reference_mask]

    missing_any = np.zeros(functional.shape, dtype=bool)
    missing_by_layer = {}
    for name, arr, weight in active:
        miss = reference_mask & (arr == 0)
        missing_by_layer[name] = int(np.count_nonzero(miss))
        missing_any |= (arr == 0)
        zones[reference_mask] += arr[reference_mask].astype(np.int32) * weight

    # (1) missing environmental information -> parent functional zone
    m_missing = reference_mask & missing_any
    zones[m_missing] = parent[m_missing]
    n_missing_px = int(np.count_nonzero(m_missing))

    ids, counts = np.unique(zones[reference_mask], return_counts=True)
    n_before = int(ids.size)

    # (2) small stratified zones -> parent (never "fall back" a parent itself)
    small = ids[(counts < int(min_pixels)) & (ids % 1000 != 0)]
    n_small_px = 0
    if small.size:
        m_small = reference_mask & np.isin(zones, small)
        n_small_px = int(np.count_nonzero(m_small))
        zones[m_small] = parent[m_small]

    n_after = int(np.unique(zones[reference_mask]).size)

    info = {
        "missing_env_pixels": n_missing_px,
        "missing_by_layer": missing_by_layer,
        "small_zone_pixels": n_small_px,
        "n_small_zones": int(small.size),
    }
    return zones.astype(np.int16), n_before, n_after, info


def compute_performance(zones, long_term_mean, reference_mask, percentile, threshold):
    """
    Potential = P<percentile> of long-term productivity inside each zone.
    Ratio = productivity / potential. Low = ratio < threshold.
    Low raster: 0 = adequate, 1 = low, 255 = NoData.
    Also returns per-zone statistics: N, mean, SD, CV, P10, P25, median,
    P75, P90 (reliability is judged on spread, not only on N).
    """
    potential = np.full(zones.shape, NODATA_FLOAT, dtype=np.float32)
    zone_p = {}
    zone_n = {}
    zone_stats = {}

    pcts = sorted(set([10, 25, 50, 75, 90, float(percentile)]))

    for zid in np.unique(zones[reference_mask]):
        m = (zones == zid) & reference_mask
        vals = long_term_mean[m]
        vals = vals[np.isfinite(vals)]
        zone_n[int(zid)] = int(vals.size)
        if not vals.size:
            continue

        qv = dict(zip(pcts, np.percentile(vals, pcts)))
        mean = float(np.mean(vals))
        sd = float(np.std(vals, ddof=1)) if vals.size > 1 else float("nan")
        cv = (sd / mean) if (mean > 0 and sd == sd) else float("nan")

        p = float(qv[float(percentile)])
        zone_p[int(zid)] = p
        potential[m] = p
        zone_stats[int(zid)] = {
            "n": int(vals.size), "mean": mean, "sd": sd, "cv": cv,
            "p10": float(qv[10]), "p25": float(qv[25]), "p50": float(qv[50]),
            "p75": float(qv[75]), "p90": float(qv[90]),
        }

    valid_ratio = reference_mask & (potential > 0)

    ratio = np.full(zones.shape, NODATA_FLOAT, dtype=np.float32)
    ratio[valid_ratio] = long_term_mean[valid_ratio] / potential[valid_ratio]

    low = np.full(zones.shape, NODATA_FLAG_UINT8, dtype=np.uint8)
    low[valid_ratio] = 0
    low[valid_ratio & (ratio < threshold)] = 1

    return {
        "potential": potential, "ratio": ratio, "low": low,
        "zone_p": zone_p, "zone_n": zone_n, "zone_stats": zone_stats,
    }


def performance_threshold_table(ratio, reference_mask, functional, thresholds):
    """
    Share of pixels classified 'low performance' for each threshold, overall
    ('ALL') and per functional group. Returns a list of dict rows.
    """
    valid = reference_mask & np.isfinite(ratio) & (ratio != NODATA_FLOAT)
    groups = [("ALL", valid)] + [
        (int(g), valid & (functional == g)) for g in range(1, 9)
    ]
    rows = []
    for t in thresholds:
        low = valid & (ratio < t)
        for label, gm in groups:
            nv = int(np.count_nonzero(gm))
            nl = int(np.count_nonzero(gm & low))
            rows.append({
                "threshold": float(t), "group": label,
                "valid_px": nv, "low_px": nl,
                "low_pct": (100.0 * nl / nv) if nv else float("nan"),
            })
    return rows


def performance_robustness(ratio, reference_mask, thresholds):
    """
    uint8 raster = number of thresholds for which the pixel is 'low'
    (ratio < t). With [0.40, 0.50, 0.60]:
        3 = low even at the strictest threshold (robustly low)
        0 = not low at any threshold ; 255 = NoData
    """
    valid = reference_mask & np.isfinite(ratio) & (ratio != NODATA_FLOAT)
    out = np.full(ratio.shape, NODATA_FLAG_UINT8, dtype=np.uint8)
    out[valid] = 0
    for t in thresholds:
        out[valid & (ratio < t)] += 1
    return out


def zone_parts(zid):
    """Decode a zone id into (functional, rain, elevation, soil)."""
    zid = int(zid)
    if zid < 1000:
        return zid, 0, 0, 0
    return zid // 1000, (zid // 100) % 10, (zid // 10) % 10, zid % 10


def describe_zone(zid, n_rain=0, n_elev=0):
    f, r, e, so = zone_parts(zid)
    parts = [ZONE_DESCRIPTIONS.get(f, "Group {}".format(f))]
    if int(zid) >= 1000 and int(zid) % 1000 == 0:
        parts.append("parent group (unstratified / fallback)")
    if r:
        parts.append("rain class {}/{}".format(r, n_rain))
    if e:
        parts.append("elevation class {}/{}".format(e, n_elev))
    if so:
        parts.append("soil {}".format(so))
    return " | ".join(parts)


def lpd_classify(slope, screened, state_class, perf_deg, want5=True):
    """
    slope       : float array (pente de Sen)
    screened    : bool array  (|tau| >= seuil)
    state_class : int array   (1 dégradé, 2 stable, 3 amélioré)
    perf_deg    : bool array  (Performance faible)
    Renvoie (lpd3 int16 : -1/0/1, lpd5 uint8 : 1..5 ou None).
    Les masques de validité sont appliqués par l'appelant.
    """
    dec = (slope < 0) & screened
    imp = (slope > 0) & screened
    stable = ~(dec | imp)            # inclut le cas pathologique pente == 0

    s_deg = state_class == 1
    s_stable = state_class == 2
    s_imp = state_class == 3
    pd = perf_deg

    lpd3 = np.zeros(slope.shape, dtype=np.int16)
    lpd3[dec] = -1
    lpd3[stable & s_deg] = -1
    lpd3[imp & s_deg & pd] = -1
    lpd3[imp & ~(s_deg & pd)] = 1

    lpd5 = None
    if want5:
        lpd5 = np.full(slope.shape, 4, dtype=np.uint8)
        lpd5[dec] = 1
        lpd5[imp & s_deg & pd] = 2
        lpd5[imp & ~(s_deg & pd)] = 5
        lpd5[stable & s_deg & pd] = 1
        lpd5[stable & s_deg & ~pd] = 2
        lpd5[stable & s_stable & pd] = 3
        lpd5[stable & s_imp] = 4

    return lpd3, lpd5


def compare_lpd(new3, valid_new, ref3, valid_ref, px_ha):
    """Accord entre deux LPD_3class sur les pixels valides dans les deux."""
    both = valid_new & valid_ref
    n = int(np.count_nonzero(both))
    labels = (-1, 0, 1)
    confusion = [[int(np.count_nonzero(both & (ref3 == a) & (new3 == b))) for b in labels]
                 for a in labels]                       # lignes = référence, colonnes = nouveau
    agree = sum(confusion[i][i] for i in range(3))
    areas = []
    for c in labels:
        a_ref = int(np.count_nonzero(valid_ref & (ref3 == c)))
        a_new = int(np.count_nonzero(valid_new & (new3 == c)))
        areas.append((c, a_ref, a_new))
    return {
        "common": n, "agreement_pct": (100.0 * agree / n) if n else float("nan"),
        "confusion": confusion, "areas": areas,
        "n_ref": int(np.count_nonzero(valid_ref)), "n_new": int(np.count_nonzero(valid_new)),
    }


def class_table(arr, valid, labels, px_ha):
    """Lignes (classe, libellé, pixels, ha, % des pixels valides)."""
    total = int(np.count_nonzero(valid))
    rows = []
    for cls in sorted(labels):
        n = int(np.count_nonzero(valid & (arr == cls)))
        rows.append((
            cls, labels[cls], n,
            (n * px_ha) if px_ha == px_ha else float("nan"),
            (100.0 * n / total) if total else float("nan"),
        ))
    return rows


def run_sensitivity(slope, tau, state_class, ratio, valid, tau_list, perf_list, px_ha):
    """
    Recalcule LPD_3class pour chaque (seuil tau, seuil Performance).
    valid doit inclure la validité de `ratio`.
    Renvoie (lignes, raster de robustesse uint8, 255 = NoData).
    """
    rows = []
    count = np.zeros(slope.shape, dtype=np.uint8)
    abs_tau = np.abs(tau)
    n_valid = int(np.count_nonzero(valid))

    with np.errstate(invalid="ignore"):
        for t in tau_list:
            screened = abs_tau >= t
            for p in perf_list:
                perf_deg = ratio < p
                lpd3, _ = lpd_classify(slope, screened, state_class, perf_deg, want5=False)
                deg = valid & (lpd3 == -1)
                stab = valid & (lpd3 == 0)
                imp = valid & (lpd3 == 1)
                nd, ns, ni = (int(np.count_nonzero(m)) for m in (deg, stab, imp))
                rows.append({
                    "tau": t, "perf": p, "valid": n_valid,
                    "deg": nd, "stable": ns, "imp": ni,
                    "deg_pct": (100.0 * nd / n_valid) if n_valid else float("nan"),
                    "deg_ha": (nd * px_ha) if px_ha == px_ha else float("nan"),
                })
                count[deg] += 1

    robustness = np.full(slope.shape, NODATA_U8, dtype=np.uint8)
    robustness[valid] = count[valid]
    return rows, robustness


def choose_directory(title, start=""):
    path = QFileDialog.getExistingDirectory(None, title, start)
    if not path:
        raise RuntimeError("Opération annulée.")
    return path


def ask_yes_no(title, text):
    reply = QMessageBox.question(None, title, text, _QMB_YES | _QMB_NO)
    return reply == _QMB_YES


def pick_file(title, folder=""):
    path, _flt = QFileDialog.getOpenFileName(
        None, title, folder, "Raster (*.tif *.tiff *.vrt);;Tous les fichiers (*)")
    if not path:
        raise RuntimeError("Fichier requis non fourni : " + title)
    return path


def raster_files(folder):
    exts = (".tif", ".tiff", ".img", ".vrt")
    out = []
    for root, dirs, files in os.walk(folder):
        for f in files:
            if f.lower().endswith(exts):
                out.append(os.path.join(root, f))
    return sorted(out)


def find_file(folders, must, exclude=(), prefer=()):
    """
    Fichier dont le nom contient tous les mots de `must`.
    Si plusieurs fichiers correspondent (anciens calculs dans des sous-dossiers),
    le plus RÉCENT est retenu et les doublons sont signalés.
    """
    hits = []
    for folder in folders:
        for p in raster_files(folder):
            base = os.path.basename(p).lower()
            if base.startswith("_"):
                continue          # fichiers temporaires créés par les scripts (VRT fusionnés)
            if all(w in base for w in must) and not any(x in base for x in exclude):
                score = sum(1 for w in prefer if w in base)
                hits.append((-score, -os.path.getmtime(p), p))
    hits.sort()
    if not hits:
        return None
    paths = [h[2] for h in hits]
    # Export GEE fragmenté en plusieurs fichiers : fusion VRT
    shards = [p for p in paths if GEE_SHARD_RE.search(os.path.basename(p))]
    if len(shards) > 1 and len(shards) == len(paths):
        print("[INFO] export GEE fragmenté ({} fichiers) -> fusion VRT".format(len(paths)))
        vrt_path = os.path.join(
            os.path.dirname(paths[0]), "_merged_" + must[0] + ".vrt")
        vrt = gdal.BuildVRT(vrt_path, paths)
        if vrt is None:
            raise RuntimeError("Fusion VRT impossible pour : " + must[0])
        vrt.FlushCache()
        vrt = None
        return vrt_path
    if len(paths) > 1:
        FILE_NOTES.append(
            "ATTENTION - {} fichiers correspondent à '{}' : le plus récent est utilisé.\n"
            "   utilisé : {}\n   ignorés : {}".format(
                len(paths), "+".join(must), paths[0], " | ".join(paths[1:4])))
    return paths[0]


def describe_file(path):
    return "{}  [{} | {}]".format(
        os.path.basename(path), os.path.basename(os.path.dirname(path)),
        time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(path))))


def _lulc_candidate_score(base, year):
    """
    Score d'un fichier candidat pour la carte LULC FINALE d'une année.

    Le script LULC écrit, dans le même dossier :
      LULC_<AREA_TAG>_<année>.tif            <- carte FINALE (éditée/validée)
      LULC_<AREA_TAG>_<année>_Original.tif   <- avant édition visuelle
      LULC_<AREA_TAG>_<année>_Edited.tif     <- copie de l'édition
      LULC_<AREA_TAG>_<année>_<horodatage>.tif (repli si fichier verrouillé)
    plus des fichiers de travail (_StageMask_, Canvas_, Preview_, RF_Confidence_,
    QA_Agreement_, SEBKHA_WATER_STATE_, ChangeMap_, Publication_Uncertainty_).
    Seul le nom canonique exact doit gagner.
    """
    score = 0
    if base == "lulc_{}_{}.tif".format(AREA_TAG.lower(), year):
        return 1100                         # nom canonique exact : gagne toujours, même si le nom de la zone contient un mot exclu (ex. « area »)
    if "lulc" in base:
        score += 100
    if "classification" in base:
        score += 60
    if "landcover" in base or "land_cover" in base:
        score += 50
    if "_original" in base or "_edited" in base:
        score -= 300                        # copies intermédiaires
    if any(w in base for w in _EXCLUDED_LULC_WORDS):
        score -= 500                        # fichiers de travail / dérivés
    return score


def year_in_name(base, year):
    """True if `year` appears as a standalone 4-digit number in the name."""
    return re.search(r"(?<!\d){}(?!\d)".format(year), base) is not None


def rank_lulc_candidates(paths, year):
    """Rasters whose NAME contains the year, best score first."""
    ranked = []
    for path in paths:
        base = os.path.basename(path).lower()
        if not year_in_name(base, year):
            continue
        ranked.append((_lulc_candidate_score(base, year), path))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    return ranked


def array_looks_like_lulc(a, min_fraction=0.99):
    """
    Content test (pure NumPy): a LULC map holds integer codes 0..8 and at
    least two different classes among 1..8. Rejects productivity (float),
    RGB, DEM, probability rasters, etc.
    """
    a = np.asarray(a, dtype=np.float64).ravel()
    a = a[np.isfinite(a)]
    if a.size == 0:
        return False
    inside = (a >= 0) & (a <= 8) & (a == np.rint(a))
    if inside.mean() < min_fraction:
        return False
    return np.unique(a[inside & (a >= 1)]).size >= 2


def looks_like_lulc(path, sample_px=LULC_VALIDATION_SAMPLE_PX, min_fraction=0.99):
    """Reads a decimated copy of band 1 and applies array_looks_like_lulc."""
    try:
        ds = gdal.Open(path, gdal.GA_ReadOnly)
        if ds is None or ds.RasterCount < 1:
            return False
        band = ds.GetRasterBand(1)
        xs, ys = ds.RasterXSize, ds.RasterYSize
        step = max(1, int(max(xs, ys) / float(sample_px)))
        arr = band.ReadAsArray(
            0, 0, xs, ys, max(1, xs // step), max(1, ys // step)
        )
        if arr is None:
            return False
        a = arr.astype(np.float64)
        nd = band.GetNoDataValue()
        if nd is not None:
            a = a[a != nd]
        return array_looks_like_lulc(a, min_fraction)
    except Exception:
        return False


def find_lulc_files(folder):
    """
    Auto-detect the five FINAL LULC rasters.
    Returns (result {year: path}, diagnostic lines).

    1. candidates = rasters whose name contains the year as a number;
    2. working/derived files (StageMask, Canvas, ChangeMap, ...) are ignored;
    3. the best-scored candidate whose CONTENT looks like a LULC map
       (integer codes 1-8) is kept.
    A name without any keyword (e.g. 'Oum_El_Bouaghi_1999.tif') is accepted.
    """
    all_rasters = raster_files(folder)
    result = {}

    diag = [
        "Dossier analysé : {}".format(folder),
        "Rasters trouvés (sous-dossiers inclus) : {}".format(len(all_rasters)),
    ]
    for p in all_rasters[:40]:
        diag.append("   - {}".format(os.path.relpath(p, folder)))
    if len(all_rasters) > 40:
        diag.append("   ... (+{} autres)".format(len(all_rasters) - 40))

    for year in YEARS:
        ranked_all = rank_lulc_candidates(all_rasters, year)
        ranked = [c for c in ranked_all if c[0] >= LULC_MIN_ACCEPT_SCORE]

        chosen = None
        for score, path in ranked[:6]:
            if looks_like_lulc(path):
                chosen = (score, path)
                break
            diag.append(
                "   {} : {} rejeté (le contenu n'est pas une carte à codes 1-8)"
                .format(year, os.path.basename(path))
            )

        if chosen:
            result[year] = chosen[1]
            if chosen[0] < 1000:
                print(
                    "[AVERTISSEMENT] LULC {} : nom canonique "
                    "LULC_{tag}_{}.tif introuvable ; utilisation de {}"
                    .format(year, year, os.path.basename(chosen[1]), tag=AREA_TAG)
                )
        else:
            diag.append("{} : aucun candidat valide trouvé".format(year))
            for sc, p in ranked_all[:5]:
                diag.append(
                    "      nom contenant {} (score {}) : {}".format(
                        year, sc, os.path.basename(p))
                )

    return result, diag


def _merge_gee_shards(paths, output_folder_hint):
    """If Earth Engine split one export in several files, mosaic them in a VRT."""
    vrt_path = os.path.join(
        output_folder_hint, "_LPD_Annual_Productivity_mosaic.vrt"
    )
    vrt = gdal.BuildVRT(vrt_path, list(paths))
    if vrt is None:
        raise RuntimeError("Impossible de fusionner les fichiers GEE en VRT.")
    vrt.FlushCache()
    vrt = None
    return vrt_path


def find_environmental_files(folder):
    """Find optional environmental rasters by file name keywords."""
    files = [
        p for p in raster_files(folder)
        if "lpd_" not in os.path.basename(p).lower()
    ]

    def pick(words):
        hits = [
            p for p in files
            if any(w in os.path.basename(p).lower() for w in words)
        ]
        return sorted(hits, key=lambda p: -os.path.getmtime(p))[0] if hits else None

    return {
        "rain": pick(("rain", "precip", "chirps")),
        "elev": pick(("elev", "altitude", "srtm", "nasadem", "_dem", "dem_")),
        "soil": pick(("soil", "sol_", "pedo")),
    }


def open_raster(path):
    ds = gdal.Open(path, gdal.GA_ReadOnly)
    if ds is None:
        raise RuntimeError("Impossible d'ouvrir le raster:\n" + path)
    return ds


def same_crs(ds_a, ds_b):
    wa, wb = ds_a.GetProjection(), ds_b.GetProjection()
    if not wa or not wb:
        return False
    sa, sb = osr.SpatialReference(), osr.SpatialReference()
    sa.ImportFromWkt(wa)
    sb.ImportFromWkt(wb)
    return bool(sa.IsSame(sb))


def same_grid(ds_a, ds_b, tol=1e-6):
    if ds_a.RasterXSize != ds_b.RasterXSize:
        return False
    if ds_a.RasterYSize != ds_b.RasterYSize:
        return False
    for a, b in zip(ds_a.GetGeoTransform(), ds_b.GetGeoTransform()):
        if abs(a - b) > tol:
            return False
    return same_crs(ds_a, ds_b)


def read_band(ds, band_index=1):
    band = ds.GetRasterBand(band_index)
    arr = band.ReadAsArray().astype(np.float32)

    nd = band.GetNoDataValue()
    if nd is not None:
        try:
            if np.isfinite(float(nd)):
                arr[arr == float(nd)] = np.nan
        except Exception:
            pass

    return arr


def warp_to_grid(src_path, ref_ds, resampling, src_band=1, src_nodata=None):
    """
    Reproject/resample ONE band of src_path onto the reference grid.

    gdal.Warp has no 'bandList' option (that is a gdal.Translate option), so
    the requested band is first isolated in an in-memory VRT.
    """
    src_ds = open_raster(src_path)
    declared = src_ds.GetRasterBand(src_band).GetNoDataValue()
    nodata = src_nodata if src_nodata is not None else declared

    single = gdal.Translate("", src_ds, format="VRT", bandList=[src_band])
    if single is None:
        raise RuntimeError(
            "Impossible d'isoler la bande {} de:\n{}".format(src_band, src_path)
        )

    gt = ref_ds.GetGeoTransform()
    width, height = ref_ds.RasterXSize, ref_ds.RasterYSize

    kwargs = dict(
        format="MEM",
        width=width,
        height=height,
        outputBounds=(
            gt[0],
            gt[3] + gt[5] * height,
            gt[0] + gt[1] * width,
            gt[3],
        ),
        dstSRS=ref_ds.GetProjection(),
        resampleAlg=resampling,
        outputType=gdal.GDT_Float32,     # -9999 must be representable
        dstNodata=NODATA_FLOAT,
    )
    if nodata is not None:
        kwargs["srcNodata"] = nodata

    mem = gdal.Warp("", single, **kwargs)
    if mem is None:
        raise RuntimeError("GDAL Warp a échoué pour:\n" + src_path)

    arr = mem.GetRasterBand(1).ReadAsArray().astype(np.float32)
    arr[arr <= -9998] = np.nan

    single = None
    mem = None
    src_ds = None

    return arr


def read_aligned_lulc(path, ref_ds):
    ds = open_raster(path)

    if same_grid(ds, ref_ds):
        arr = read_band(ds, 1)
    else:
        arr = warp_to_grid(path, ref_ds, LULC_RESAMPLING, 1)

    arr = np.rint(arr)

    # Valid LULC codes are 1..8. Zero / negative = NoData (even if the file
    # declares no NoData value).
    arr[arr <= 0] = np.nan

    unexpected = np.isfinite(arr) & ~np.isin(arr, list(CLASS_NAMES.keys()))
    n_bad = int(np.count_nonzero(unexpected))
    if n_bad:
        print(
            "[AVERTISSEMENT] {} : {:,} pixels avec un code LULC hors 1-8 "
            "(traités comme NoData).".format(os.path.basename(path), n_bad)
        )
        arr[unexpected] = np.nan

    return arr


def read_aligned_env(path, ref_ds, categorical=False):
    """Environmental layer on the reference grid (declared NoData only)."""
    ds = open_raster(path)
    if same_grid(ds, ref_ds):
        return read_band(ds, 1)
    return warp_to_grid(
        path, ref_ds,
        LULC_RESAMPLING if categorical else PRODUCTIVITY_RESAMPLING, 1
    )


def create_geotiff(path, arr, ref_ds, dtype, nodata, compress="LZW"):
    driver = gdal.GetDriverByName("GTiff")

    ds = driver.Create(
        path,
        ref_ds.RasterXSize,
        ref_ds.RasterYSize,
        1,
        dtype,
        ["COMPRESS=" + compress, "TILED=YES", "BIGTIFF=IF_SAFER"]
    )

    if ds is None:
        raise RuntimeError("Impossible de créer:\n" + path)

    ds.SetGeoTransform(ref_ds.GetGeoTransform())
    ds.SetProjection(ref_ds.GetProjection())

    band = ds.GetRasterBand(1)
    band.WriteArray(arr)
    band.SetNoDataValue(nodata)
    band.FlushCache()

    ds.FlushCache()
    ds = None


def add_layer(path, name):
    layer = QgsRasterLayer(path, name)
    if layer.isValid():
        QgsProject.instance().addMapLayer(layer)


def add_paletted(path, name, entries):
    layer = QgsRasterLayer(path, name)
    if not layer.isValid():
        return
    try:
        classes = [
            QgsPalettedRasterRenderer.Class(v, QColor("#" + col), lab)
            for (v, col, lab) in entries
        ]
        layer.setRenderer(
            QgsPalettedRasterRenderer(layer.dataProvider(), 1, classes))
    except Exception as exc:
        print("[INFO] style non appliqué pour {} ({})".format(name, exc))
    QgsProject.instance().addMapLayer(layer)


def pixel_area_ha(ds):
    srs = osr.SpatialReference()
    srs.ImportFromWkt(ds.GetProjection())
    if srs.IsProjected():
        gt = ds.GetGeoTransform()
        return abs(gt[1] * gt[5]) / 10000.0
    return float("nan")


def sample_valid_fraction(path, n_bands_sampled=3, sample_px=1200):
    """
    Part de pixels NON NULS et finis dans quelques bandes (lecture decimee, rapide).
    Renvoie (fraction maximale, nombre de bandes, remarque).
    """
    try:
        ds = gdal.Open(path, gdal.GA_ReadOnly)
    except Exception:
        ds = None
    if ds is None or ds.RasterCount < 1:
        return 0.0, 0, "illisible"
    nb = ds.RasterCount
    idxs = sorted(set(
        max(1, min(nb, int(round(v)))) for v in np.linspace(1, nb, n_bands_sampled + 2)[1:-1]))
    xs, ys = ds.RasterXSize, ds.RasterYSize
    step = max(1, int(max(xs, ys) / float(sample_px)))
    fracs = []
    for i in idxs:
        band = ds.GetRasterBand(i)
        try:
            arr = band.ReadAsArray(0, 0, xs, ys, max(1, xs // step), max(1, ys // step))
        except Exception:
            arr = None
        if arr is None:
            continue
        a = arr.astype(np.float64)
        ok = np.isfinite(a) & (a != 0)
        nd = band.GetNoDataValue()
        if nd is not None:
            ok &= (a != nd)
        fracs.append(float(ok.mean()))
    return (max(fracs) if fracs else 0.0), nb, ("ok" if fracs else "lecture impossible")


def resolve_lulc_files(lulc_folder):
    """Les cinq cartes LULC : détection automatique, sinon sélection manuelle."""
    lulc_files, lulc_diag = find_lulc_files(lulc_folder)
    missing_lulc = [y for y in YEARS if y not in lulc_files]
    if missing_lulc:
        print("\n".join(lulc_diag))
        for y in list(missing_lulc):
            picked, _flt = QFileDialog.getOpenFileName(
                None,
                "LULC {} non détectée automatiquement – choisissez le fichier "
                "de la carte {}".format(y, y),
                lulc_folder,
                "Raster (*.tif *.tiff *.img *.vrt);;Tous les fichiers (*)"
            )
            if not picked:
                raise RuntimeError(
                    "Carte LULC {} non fournie.\n\n".format(y) + "\n".join(lulc_diag[:60]))
            if not looks_like_lulc(picked, min_fraction=0.90):
                raise RuntimeError(
                    "Le fichier choisi pour {} ne ressemble pas à une carte LULC "
                    "(codes entiers 1-8 attendus) :\n{}".format(y, picked))
            lulc_files[y] = picked
            print("[LULC] {} : sélection manuelle -> {}".format(y, picked))
    return lulc_files


# ============================================================================
# 8. MODIS — PARAMÈTRES PROPRES À CE SCRIPT
# ============================================================================

FIRST_YEAR, LAST_YEAR = 2000, 2025
MODIS_YEAR_RE = re.compile(r"(?<!\d)(20[0-4]\d)(?!\d)")

MIN_VALID_COMPOSITES_EXPORT = 5      # seuil appliqué dans GEE (scénario B) : contrôle de cohérence
SCENARIO_C_MIN_VALID = 6             # scénario C : QA <= 1 et >= 6 composites (dérivé ici)
PERSISTENT_LOW_NVALID = 5            # « faible » = n_valid <= 5
PERSISTENT_LOW_FRACTION = 0.50       # persistant si faible dans >= 50 % des années

MIN_VALID_YEARS_TRAJ = 15            # années valides minimales pour Sen / Mann-Kendall (sur 26)
MIN_BASE_YEARS, MIN_RECENT_YEARS = 8, 3
MIN_SERIES_YEARS = 10                 # années minimales de la série utilisée (trajectoire, état) ; la période de base doit garder au moins MIN_BASE_YEARS années
MIN_REG_YEARS = 15
R2_RELIABLE = 0.20
MIN_BASELINE_MEAN = 0.05             # NDVI de référence minimal pour une variation relative

TAU_MAIN = 0.30
TAU_SENSITIVITY = [0.20, 0.30, 0.40]
P_ALPHA = 0.05
STATE_THRESHOLD = 0.10

MIN_PRODUCTIVITY_YEARS = 15          # années minimales pour la productivité moyenne de Performance
MIN_PIXELS_STRATIFIED_ZONE = 500     # MODIS 250 m : 500 px ~ 3 100 ha (le seuil 2000 était calibré sur 30 m)

RELIABLE_MEAN_NVALID = 6.0           # confiance élevée : moyenne de composites >= 6 dans les deux périodes
RELIABLE_MIN_YEARS = 20              # ... et >= 20 années valides

STATS_LULC_YEARS = [2015, 2025]      # années LULC utilisées pour les statistiques par occupation du sol

LULC_RESAMPLING = gdal.GRA_Mode      # LULC 30 m -> grille MODIS : classe dominante dans chaque pixel MODIS
PRODUCTIVITY_RESAMPLING = gdal.GRA_Bilinear

SCEN_A, SCEN_B, SCEN_C = "A_QA0_min5", "B_QA1_min5", "C_QA1_min6"
MODIS_DESCRIPTION = (
    "MODIS Terra MOD13Q1 Collection 6.1 fournit un produit d'indice de végétation à capteur unique, "
    "temporellement cohérent, avec une calibration et un traitement améliorés par rapport aux "
    "collections précédentes."
)


# ============================================================================
# 9. LOGIQUE PURE — SEN / KENDALL, STATE, PLUIE (NumPy)
# ============================================================================

def _erfc_vec(x):
    return np.array([math.erfc(v) for v in np.ravel(x)], dtype=np.float64).reshape(np.shape(x))


def sen_kendall(X, t, min_valid):
    """
    X : (n_années, n_pixels), NaN = manquant ; t : années.
    Renvoie slope (pente de Sen), tau, n_valid, z, p (Mann-Kendall bilatéral, approximation normale
    avec correction de continuité) ; NaN si n_valid < min_valid.
    """
    n_y, n_px = X.shape
    I, J = np.triu_indices(n_y, k=1)
    dt_ = (t[J] - t[I]).astype(np.float64)[:, None]
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
    p = _erfc_vec(np.abs(z) / math.sqrt(2.0))
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


def period_means(P, idx):
    sub = P[idx]
    ok = np.isfinite(sub) & (sub != 0)
    cnt = ok.sum(0).astype(np.float64)
    s = np.where(ok, sub, 0.0).sum(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return s / cnt, cnt


def state_original(P, base_idx, rec_idx, min_base, min_rec, min_mean=MIN_BASELINE_MEAN):
    """Moyennes, variation relative, comptes. NaN si trop peu d'années ou moyenne de référence < min_mean."""
    mb, nb = period_means(P, base_idx)
    mr, nr = period_means(P, rec_idx)
    ok = (nb >= min_base) & (nr >= min_rec) & (mb >= min_mean)
    with np.errstate(invalid="ignore", divide="ignore"):
        rel = (mr - mb) / np.maximum(np.abs(mb), 1e-6)
    return mb, mr, np.where(ok, rel, np.nan), nb, nr


def classify_state(rel, thr):
    """0 = non valide ; 1 = dégradé (<= -thr) ; 2 = stable ; 3 = amélioré (>= +thr)."""
    cls = np.zeros(rel.shape, dtype=np.uint8)
    valid = np.isfinite(rel)
    cls[valid] = 2
    with np.errstate(invalid="ignore"):
        cls[valid & (rel <= -thr)] = 1
        cls[valid & (rel >= thr)] = 3
    return cls


def shares(cls, mask=None):
    """Parts (%) de chaque classe de State (1, 2, 3) sur les pixels valides (cls > 0) du masque."""
    m = (cls > 0) if mask is None else (mask & (cls > 0))
    n = int(m.sum())
    if n == 0:
        return {1: float("nan"), 2: float("nan"), 3: float("nan"), "n": 0}
    out = {c: 100.0 * float(((cls == c) & m).sum()) / n for c in (1, 2, 3)}
    out["n"] = n
    return out


def rain_adjusted_state(P, R, base_idx, rec_idx, min_reg, min_base, min_rec, min_mean=MIN_BASELINE_MEAN):
    """Régression P = a + b R par pixel ; variation attendue = b (R_récent - R_réf) ; corrigée = observée - attendue."""
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
    reg_ok = (n >= min_reg) & (den > 1e-9)
    b = np.where(reg_ok, b, np.nan)
    a_icpt = np.where(reg_ok, a, np.nan)
    r2 = np.where(reg_ok, r2, np.nan)

    def period(idx):
        m = prod_ok[idx]
        cnt = m.sum(0).astype(np.float64)
        mp = m * r_ok[idx][:, None]
        cnt_r = mp.sum(0).astype(np.float64)
        s_p = np.where(m, P[idx], 0.0).sum(0)
        s_r = (mp * np.where(r_ok[idx], R[idx], 0.0)[:, None]).sum(0)
        with np.errstate(invalid="ignore", divide="ignore"):
            return cnt, s_p / cnt, s_r / cnt_r

    nb, mb, rb = period(base_idx)
    nr, mr, rr = period(rec_idx)
    ok = (nb >= min_base) & (nr >= min_rec) & (mb >= min_mean)
    with np.errstate(invalid="ignore", divide="ignore"):
        denom = np.maximum(np.abs(mb), 1e-6)
        rel_obs = (mr - mb) / denom
        rel_exp = b * (rr - rb) / denom
        rel_adj = rel_obs - rel_exp
    adj_ok = ok & reg_ok & np.isfinite(rel_exp)
    return {
        "rel_obs": np.where(ok, rel_obs, np.nan), "rel_adj": np.where(adj_ok, rel_adj, np.nan),
        "rel_exp": np.where(adj_ok, rel_exp, np.nan), "slope": b, "r2": r2, "intercept": a_icpt,
    }


def hybrid_relative_change(rel_obs, rel_adj, r2, r2_min):
    reliable = np.isfinite(rel_adj) & np.isfinite(r2) & (r2 >= r2_min)
    return np.where(reliable, rel_adj, rel_obs), reliable


def residual_series(P, R, slope, intercept, reliable):
    """Résidus de la régression là où elle est fiable ; série brute ailleurs."""
    R = np.asarray(R, dtype=np.float64)
    pred = intercept[None, :] + slope[None, :] * R[:, None]
    out = np.where(reliable[None, :] & np.isfinite(R)[:, None], P - pred, P)
    out = np.where(np.isfinite(P) & (P != 0), out, np.nan)
    return out.astype(np.float32)


def parse_daily_rain(text):
    out = {}
    for line in text.splitlines():
        line = line.strip().lstrip("\ufeff")
        if not line:
            continue
        if ";" in line:
            parts = line.split(";")
            val = parts[1].replace(",", ".") if len(parts) > 1 else ""
        else:
            parts = line.split(",")
            val = parts[1] if len(parts) > 1 else ""
        try:
            out[dt.date.fromisoformat(parts[0].strip().strip('"'))] = float(val.strip().strip('"'))
        except (ValueError, IndexError):
            continue
    return out


def window_total(daily, start, end):
    n_exp = (end - start).days + 1
    total, n, d = 0.0, 0, start
    while d <= end:
        v = daily.get(d)
        if v is not None:
            total += v
            n += 1
        d += dt.timedelta(days=1)
    return total if n == n_exp else float("nan")


def rain_window_label():
    m0, m1 = RAIN_WINDOW_MONTHS
    names = ["jan.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
    return "{}{}-{}".format(names[m0 - 1], "(N-1)" if m0 > m1 else "", names[m1 - 1])


def wet_season_rain(daily, years):
    """Pluie de la fenêtre RAIN_WINDOW_MONTHS (m0, m1) rattachée à l'année N : de m0 (N-1 si m0 > m1, sinon N) à la fin de m1 de N ; défaut (9, 6) = sept.(N-1) - juin(N). NaN si un jour manque."""
    import calendar
    m0, m1 = RAIN_WINDOW_MONTHS
    return {y: window_total(daily, dt.date(y - 1 if m0 > m1 else y, m0, 1), dt.date(y, m1, calendar.monthrange(y, m1)[1])) for y in years}


def scaled_min(base, n_years):
    """Années valides minimales proportionnelles à la longueur de la série : `base` pour 26 ans (valeurs de l'étape 02 inchangées), au moins 10 pour une série raccourcie."""
    return max(10, int(round(base * n_years / 26.0)))


# ============================================================================
# 10. LOGIQUE PURE — QUALITÉ TEMPORELLE (n_valid), SCÉNARIOS, FIABILITÉ
# ============================================================================

def nvalid_distribution(NV, P, years, min_valid):
    """
    Pour chaque année : répartition (nombre de pixels) des valeurs de n_valid sur la zone d'étude.
    Renvoie (lignes, masque de la zone d'étude, nmax).
    """
    aoi = np.isfinite(NV).any(axis=0)
    nmax = int(np.nanmax(NV))
    rows = []
    for i, y in enumerate(years):
        nv = NV[i][aoi]
        counts = {k: int(np.sum(nv == k)) for k in range(0, nmax + 1)}
        n_aoi = int(nv.size)
        rows.append({
            "year": y, "n_aoi": n_aoi, "counts": counts,
            "no_nvalid": n_aoi - sum(counts.values()),
            "valid_productivity": int(np.isfinite(P[i][aoi]).sum()),
            "ge5": int(np.sum(nv >= 5)), "ge6": int(np.sum(nv >= 6)), "ge7": int(np.sum(nv >= 7)),
            "full": counts[nmax],
            "excluded": int(np.sum(nv < min_valid)) + (n_aoi - sum(counts.values())),
        })
    return rows, aoi, nmax


def pixel_quality_layers(P, NV, nmax, aoi, low_nvalid=PERSISTENT_LOW_NVALID, low_fraction=PERSISTENT_LOW_FRACTION):
    """Couches de qualité par pixel (01c_MODIS_DataQuality)."""
    ny = NV.shape[0]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        mean_nv = np.nanmean(NV, axis=0)
        min_nv = np.nanmin(NV, axis=0)
        max_nv = np.nanmax(NV, axis=0)
    years_prod = np.isfinite(P).sum(0).astype(np.float32)
    ge5 = (NV >= 5).sum(0).astype(np.float32)
    ge6 = (NV >= 6).sum(0).astype(np.float32)
    ge7 = (NV >= 7).sum(0).astype(np.float32)
    full = (NV == nmax).sum(0).astype(np.float32)
    low = (NV <= low_nvalid).sum(0).astype(np.float32)
    layers = {
        "mean_nvalid": mean_nv, "min_nvalid": min_nv, "max_nvalid": max_nv,
        "years_with_productivity": years_prod, "years_n_ge5": ge5, "years_n_ge6": ge6, "years_n_ge7": ge7,
        "years_full": full, "share_full_pct": 100.0 * full / ny,
        "share_nodata_pct": 100.0 * (ny - years_prod) / ny,
        "persistent_low_flag": (low / ny >= low_fraction).astype(np.float32),
    }
    return {k: np.where(aoi, v, np.nan).astype(np.float32) for k, v in layers.items()}


def apply_min_valid(P, NV, min_valid):
    """Scénario dérivé : on retire les pixels-années ayant moins de `min_valid` composites."""
    return np.where(NV >= min_valid, P, np.nan).astype(np.float32)


def reliability_class(P, NV, base_idx, rec_idx, min_mean=RELIABLE_MEAN_NVALID, min_years=RELIABLE_MIN_YEARS):
    """
    1 = fiabilité élevée : nombre moyen de composites >= min_mean dans la période de référence ET la période
        récente (sur les années valides) et >= min_years années valides ; 2 = fiabilité moindre ; 0 = inconnue.
    """
    valid = np.isfinite(P)

    def mean_nv(idx):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            return np.nanmean(np.where(valid[idx], NV[idx], np.nan), axis=0)

    mb, mr = mean_nv(base_idx), mean_nv(rec_idx)
    yv = valid.sum(0)
    known = np.isfinite(mb) & np.isfinite(mr)
    high = known & (mb >= min_mean) & (mr >= min_mean) & (yv >= min_years)
    cls = np.zeros(P.shape[1:], dtype=np.uint8)
    cls[known] = 2
    cls[high] = 1
    return cls, mb, mr


def pearson(a, b):
    if a.size < 3 or np.std(a) == 0 or np.std(b) == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def compare_scenarios(ref, alt, ref_lpd3, alt_lpd3, ref_valid, alt_valid, ref_ltm, alt_ltm, px_ha):
    """Compare un scénario `alt` au scénario de référence `ref` (dicts de couches 2-D)."""
    out = {}
    m = np.isfinite(ref["slope"]) & np.isfinite(alt["slope"])
    out["traj_common"] = int(m.sum())
    out["sen_corr"] = pearson(ref["slope"][m], alt["slope"][m])
    out["sen_mad"] = float(np.mean(np.abs(ref["slope"][m] - alt["slope"][m]))) if m.any() else float("nan")
    out["tau_corr"] = pearson(ref["tau"][m], alt["tau"][m])
    sr, sa = np.abs(ref["tau"][m]) >= TAU_MAIN, np.abs(alt["tau"][m]) >= TAU_MAIN
    out["tau_screen_agree"] = 100.0 * float(np.mean(sr == sa)) if m.any() else float("nan")
    out["tau_screen_ref"] = 100.0 * float(np.mean(sr)) if m.any() else float("nan")
    out["tau_screen_alt"] = 100.0 * float(np.mean(sa)) if m.any() else float("nan")

    def pclass(d):
        c = np.zeros(d["slope"].shape, dtype=np.int8)
        sig = np.isfinite(d["p"]) & (d["p"] < P_ALPHA)
        c[sig & (d["slope"] < 0)] = -1
        c[sig & (d["slope"] > 0)] = 1
        return c
    pr, pa = pclass(ref)[m], pclass(alt)[m]
    out["mk_class_agree"] = 100.0 * float(np.mean(pr == pa)) if m.any() else float("nan")

    ms = (ref["state_class"] > 0) & (alt["state_class"] > 0)
    out["state_common"] = int(ms.sum())
    out["state_agree"] = 100.0 * float(np.mean(ref["state_class"][ms] == alt["state_class"][ms])) if ms.any() else float("nan")
    for tag, d in (("ref", ref), ("alt", alt)):
        c = d["state_class"][ms]
        out["state_deg_" + tag] = 100.0 * float(np.mean(c == 1)) if ms.any() else float("nan")
        out["state_imp_" + tag] = 100.0 * float(np.mean(c == 3)) if ms.any() else float("nan")

    ml = np.isfinite(ref_ltm) & np.isfinite(alt_ltm)
    out["ltm_corr"] = pearson(ref_ltm[ml], alt_ltm[ml])
    out["ltm_mean_rel_diff_pct"] = 100.0 * float(np.mean((alt_ltm[ml] - ref_ltm[ml]) / np.maximum(np.abs(ref_ltm[ml]), 1e-6))) if ml.any() else float("nan")
    out["lpd"] = compare_lpd(alt_lpd3, alt_valid, ref_lpd3, ref_valid, px_ha)
    return out


# ============================================================================
# 11. ENTRÉES MODIS
# ============================================================================

def choose_by_content(folder, must, exclude, scratch_dir, label):
    """
    Fichier (ou export GEE fragmenté, fusionné dans un VRT neuf) dont le nom contient tous les mots de `must`,
    choisi par son CONTENU (part de pixels non nuls). Renvoie (chemin, lignes de diagnostic) ou (None, ...).
    """
    files = [p for p in raster_files(folder)
             if all(w in os.path.basename(p).lower() for w in must)
             and not os.path.basename(p).startswith("_")
             and not any(w in os.path.basename(p).lower() for w in exclude)]
    singles, groups = [], {}
    for p in files:
        base = os.path.basename(p)
        m = GEE_SHARD_RE.search(base)
        if m:
            groups.setdefault((os.path.dirname(p), GEE_SHARD_RE.sub(m.group(1), base)), []).append(p)
        else:
            singles.append(p)
    cands = [(p, [p]) for p in singles]
    for k, (key, grp) in enumerate(sorted(groups.items())):
        if len(grp) > 1:
            vrt = os.path.join(scratch_dir, "_{}_mosaic_{}.vrt".format(label, k))
            v = gdal.BuildVRT(vrt, sorted(grp))
            if v is None:
                continue
            v.FlushCache()
            v = None
            cands.append((vrt, grp))
        else:
            cands.append((grp[0], grp))
    if not cands:
        return None, ["Aucun fichier '{}' dans {}".format("+".join(must), folder)]
    scored = []
    for path, grp in cands:
        frac, nb, _note = sample_valid_fraction(path)
        scored.append((frac, nb, max(os.path.getmtime(g) for g in grp), path))
    scored.sort(key=lambda t: (-t[0], -t[1], -t[2]))
    diag = ["[{}] candidats :".format(label)]
    for fr, nb, mt, path in scored:
        diag.append("    {:5.1f} %  {:>3d} bandes  {}  [{}]".format(
            100 * fr, nb, os.path.basename(path), time.strftime("%Y-%m-%d %H:%M", time.localtime(mt))))
    if scored[0][0] < 0.01:
        return None, diag + ["Aucun candidat ne contient de pixels valides (< 1 %)."]
    diag.append("    retenu : " + scored[0][3])
    return scored[0][3], diag


def modis_band_years(ds):
    years = {}
    for b in range(1, ds.RasterCount + 1):
        found = [int(y) for y in MODIS_YEAR_RE.findall(ds.GetRasterBand(b).GetDescription() or "")
                 if FIRST_YEAR <= int(y) <= LAST_YEAR]
        if found:
            years[found[-1]] = b
    if len(years) < 10 and ds.RasterCount == LAST_YEAR - FIRST_YEAR + 1:
        years = {FIRST_YEAR + i: i + 1 for i in range(ds.RasterCount)}
        print("[AVERTISSEMENT] pas d'année dans les noms de bandes : ordre chronologique 2000-2025 supposé")
    return years


def read_year_stack(ds, by_year, years, kind):
    """(années, lignes, colonnes) float32 ; NoData (-9999) -> NaN ; productivité : 0 -> NaN aussi."""
    rows, cols = ds.RasterYSize, ds.RasterXSize
    out = np.empty((len(years), rows, cols), dtype=np.float32)
    for i, y in enumerate(years):
        band = ds.GetRasterBand(by_year[y])
        arr = band.ReadAsArray().astype(np.float32)
        nd = band.GetNoDataValue()
        if nd is not None and np.isfinite(float(nd)):
            arr[arr == float(nd)] = np.nan
        arr[arr <= -9998] = np.nan
        if kind == "prod":
            arr[arr == 0] = np.nan
        out[i] = arr
    return out


def load_modis_pair(folder, scratch_dir, label, must_extra=(), exclude_extra=("qa0",)):
    """Pile de productivité + pile du nombre de composites valides, sur la même grille."""
    exclude_prod = ("qa", "lpd_", "sensitivity", "validperiods", "nvalid") if not must_extra else (
        "lpd_", "sensitivity", "validperiods", "nvalid")
    exclude_nv = ("lpd_",) + (() if must_extra else ("qa0",))
    p_path, d1 = choose_by_content(folder, ["annual_productivity"] + list(must_extra), exclude_prod, scratch_dir, label + "_prod")
    n_path, d2 = choose_by_content(folder, ["validperiods"] + list(must_extra), exclude_nv, scratch_dir, label + "_nv")
    if not p_path:
        raise RuntimeError("Pile de productivité MODIS introuvable ({}).\n{}".format(label, "\n".join(d1)))
    if not n_path:
        raise RuntimeError("Pile 01b_Annual_ValidPeriods_MODIS introuvable ({}).\n{}".format(label, "\n".join(d2)))
    pds, nds = open_raster(p_path), open_raster(n_path)
    if (pds.RasterXSize, pds.RasterYSize) != (nds.RasterXSize, nds.RasterYSize):
        raise RuntimeError("Les piles productivité et n_valid n'ont pas la même taille ({}x{} / {}x{}).".format(
            pds.RasterXSize, pds.RasterYSize, nds.RasterXSize, nds.RasterYSize))
    if not same_grid(pds, nds):
        raise RuntimeError("Les piles productivité et n_valid n'ont pas la même géo-référence.")
    if pds.RasterXSize * pds.RasterYSize > 4_000_000:
        raise RuntimeError("Grille trop grande pour une pile MODIS 250 m : {} x {} px.".format(
            pds.RasterXSize, pds.RasterYSize))
    py, ny = modis_band_years(pds), modis_band_years(nds)
    years = sorted(y for y in py if y in ny and TREND_START_YEAR <= y <= TREND_END_YEAR)      # TREND_START_YEAR : première année utilisée (2000 = convention UNCCD ; 2003 = test après la sécheresse de début de série)
    if TREND_START_YEAR > BASELINE_YEARS[1] - MIN_BASE_YEARS + 1:
        raise RuntimeError("TREND_START_YEAR = {} laisse moins de {} années dans la période de base ({}-{}).".format(TREND_START_YEAR, MIN_BASE_YEARS, TREND_START_YEAR, BASELINE_YEARS[1]))
    if len(years) < MIN_SERIES_YEARS:           # 10 : plancher de scaled_min() ; une série de 13 ans (base 2003-2015) est un test de robustesse, moins puissant qu'une série de 16 ans
        raise RuntimeError("Seulement {} années communes aux deux piles (minimum {} ; TREND_START_YEAR = {}, TREND_END_YEAR = {}).".format(len(years), MIN_SERIES_YEARS, TREND_START_YEAR, TREND_END_YEAR))
    P = read_year_stack(pds, py, years, "prod")
    NV = read_year_stack(nds, ny, years, "nvalid")
    return {"P": P, "NV": NV, "years": years, "ref_ds": pds, "prod_path": p_path, "nv_path": n_path,
            "diag": d1 + d2}


def aoi_mask_from_vector(path, ref_ds):
    """Masque booléen (grille MODIS) des pixels dont le centre est dans la limite vectorielle (GDAL RasterizeLayer)."""
    if ogr is None:
        raise RuntimeError("Le module osgeo.ogr est indisponible.")
    src = ogr.Open(path)
    if src is None or src.GetLayerCount() < 1:
        raise RuntimeError("Limite vectorielle illisible : " + path)
    layer = src.GetLayer(0)
    mem = gdal.GetDriverByName("MEM").Create("", ref_ds.RasterXSize, ref_ds.RasterYSize, 1, gdal.GDT_Byte)
    mem.SetGeoTransform(ref_ds.GetGeoTransform())
    mem.SetProjection(ref_ds.GetProjection())
    gdal.RasterizeLayer(mem, [1], layer, burn_values=[1])
    mask = mem.GetRasterBand(1).ReadAsArray().astype(bool)
    n = int(mask.sum())
    if n == 0 or n == mask.size:
        raise RuntimeError("Masque vectoriel vide ou couvrant toute la grille ({} px) : système de coordonnées ?".format(n))
    return mask


# ============================================================================
# 12. ÉCRITURE
# ============================================================================

def write_multiband(path, arrays, descriptions, ref_ds, nodata=NODATA_FLOAT):
    rows, cols = ref_ds.RasterYSize, ref_ds.RasterXSize
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ds = gdal.GetDriverByName("GTiff").Create(
        path, cols, rows, len(arrays), gdal.GDT_Float32, ["COMPRESS=LZW", "TILED=YES", "BIGTIFF=IF_SAFER"])
    ds.SetGeoTransform(ref_ds.GetGeoTransform())
    ds.SetProjection(ref_ds.GetProjection())
    for i, (arr, desc) in enumerate(zip(arrays, descriptions), start=1):
        b = ds.GetRasterBand(i)
        a = np.where(np.isfinite(arr), arr, nodata).astype(np.float32)
        b.WriteArray(a.reshape(rows, cols))
        b.SetNoDataValue(nodata)
        b.SetDescription(desc)
    ds.FlushCache()
    ds = None


def write_csv(path, header, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(r)


def fmt(v, nd=1):
    return "" if v is None or (isinstance(v, float) and not np.isfinite(v)) else "{:.{}f}".format(v, nd)


# ============================================================================
# 13. ANALYSE D'UN SCÉNARIO
# ============================================================================

def analyze_scenario(P, years, base_idx, rec_idx):
    """Trajectory (Sen, Mann-Kendall) et State pour une pile de productivité (années, lignes, colonnes)."""
    ny, rows, cols = P.shape
    X = P.reshape(ny, -1)
    t = np.array(years, dtype=np.float64)
    tr = sen_kendall_chunked(X, t, scaled_min(MIN_VALID_YEARS_TRAJ, len(t)))
    mb, mr, rel, nb, nr = state_original(X, base_idx, rec_idx, MIN_BASE_YEARS, MIN_RECENT_YEARS)
    cls = classify_state(rel, STATE_THRESHOLD)
    sh = (rows, cols)
    d = {k: tr[k].reshape(sh) for k in tr}
    d.update({"state_class": cls.reshape(sh), "state_rel": rel.reshape(sh).astype(np.float32),
              "base_mean": mb.reshape(sh).astype(np.float32), "recent_mean": mr.reshape(sh).astype(np.float32),
              "base_n": nb.reshape(sh).astype(np.float32), "recent_n": nr.reshape(sh).astype(np.float32)})
    d["traj_valid"] = np.isfinite(d["slope"]) & np.isfinite(d["tau"])
    return d


def long_term_mean(P):
    ok = np.isfinite(P)
    cnt = ok.sum(0)
    s = np.where(ok, P, 0.0).sum(0, dtype=np.float64)
    ltm = np.full(P.shape[1:], np.nan, dtype=np.float32)
    h = cnt > 0
    ltm[h] = (s[h] / cnt[h]).astype(np.float32)
    return ltm, cnt


def performance_for(P, functional, rain_arr, elev_arr, min_years):
    """Performance (P90 par zone, ratio, faible) pour une pile de productivité ; zones stratifiées si pluie/altitude."""
    ltm, cnt = long_term_mean(P)
    ref = (functional > 0) & (cnt >= min_years) & np.isfinite(ltm)
    zones_f = np.zeros(functional.shape, dtype=np.int16)
    zones_f[ref] = functional[ref]
    perf_f = compute_performance(zones_f, ltm, ref, PERFORMANCE_PERCENTILE, PERFORMANCE_RATIO_THRESHOLD)
    zones_main, perf_main, stratified, strat_info, fb = zones_f, perf_f, False, [], None
    if rain_arr is not None or elev_arr is not None:
        rb = eb = None
        if rain_arr is not None:
            rb, edges, method = bin_continuous(rain_arr, ref, ENV_RAINFALL_BINS, RAINFALL_BREAKS)
            strat_info.append(("rainfall", edges, method))
        if elev_arr is not None:
            eb, edges, method = bin_continuous(elev_arr, ref, ENV_ELEVATION_BINS, ELEVATION_BREAKS)
            strat_info.append(("elevation", edges, method))
        zones_main, zb, za, fb = build_stratified_zones(functional, ref, rb, eb, None, MIN_PIXELS_STRATIFIED_ZONE)
        perf_main = compute_performance(zones_main, ltm, ref, PERFORMANCE_PERCENTILE, PERFORMANCE_RATIO_THRESHOLD)
        stratified = True
    return {
        "ltm": ltm, "count": cnt, "reference": ref, "zones": zones_main, "zones_functional": zones_f,
        "perf": perf_main, "perf_functional": perf_f, "stratified": stratified, "strat_info": strat_info,
        "robustness": performance_robustness(perf_main["ratio"], ref, PERFORMANCE_SENSITIVITY_THRESHOLDS),
        "threshold_rows": performance_threshold_table(perf_main["ratio"], ref, functional, PERFORMANCE_SENSITIVITY_THRESHOLDS),
    }


def lpd_from(traj, state_class, low, tau_thr=TAU_MAIN, use_p=False):
    """
    LPD 3 et 5 classes. traj : dict (slope, tau, p). state_class : uint8 (0 = non valide). low : uint8 (0/1, 255 = NoData).
    Renvoie (lpd3 int16, lpd5 uint8, masque de validité).
    """
    perf_ok = np.isin(low, (0, 1))
    valid = np.isfinite(traj["slope"]) & np.isfinite(traj["tau"]) & (state_class > 0) & perf_ok
    slope = np.where(np.isfinite(traj["slope"]), traj["slope"], 0.0)
    if use_p:
        screened = np.isfinite(traj["p"]) & (traj["p"] < P_ALPHA)
    else:
        screened = np.isfinite(traj["tau"]) & (np.abs(np.where(np.isfinite(traj["tau"]), traj["tau"], 0.0)) >= tau_thr)
    lpd3, lpd5 = lpd_classify(slope, screened, state_class.astype(np.int16), low == 1, want5=True)
    lpd3 = np.where(valid, lpd3, NODATA_I16).astype(np.int16)
    lpd5 = np.where(valid, lpd5, NODATA_U8).astype(np.uint8)
    return lpd3, lpd5, valid


def share_rows(lpd3, valid, category, labels, px_ha):
    """Lignes : catégorie, libellé, pixels évalués, ha, dégradé/stable/amélioré (ha et %)."""
    rows = []
    for cid in sorted(labels):
        m = valid & (category == cid)
        n = int(m.sum())
        d, s, i = (int((m & (lpd3 == c)).sum()) for c in (-1, 0, 1))
        rows.append((cid, labels[cid], n, n * px_ha, d * px_ha, 100.0 * d / n if n else float("nan"),
                     s * px_ha, 100.0 * s / n if n else float("nan"),
                     i * px_ha, 100.0 * i / n if n else float("nan")))
    return rows


# ============================================================================
# 14. PROGRAMME PRINCIPAL
# ============================================================================

def main():
    t0 = time.time()
    QMessageBox.information(
        None, "MODIS – LPD complet (productivité UNCCD)",
        "Chaîne complète à partir des exports MODIS (01_Annual_Productivity_MODIS + 01b_Annual_ValidPeriods_MODIS) :\n\n"
        "1. Qualité temporelle (n_valid) -> 01c_MODIS_DataQuality\n"
        "2. Scénarios de sensibilité (A : QA=0 ; B : QA<=1, >=5 ; C : QA<=1, >=6)\n"
        "3. Trajectory (Sen + Mann-Kendall)  4. State  5. Performance  6. LPD 3/5 classes\n"
        "7. Fiabilité, variante corrigée de la pluie, statistiques de type UNCCD, rapport.")

    modis_dir = choose_directory("1/6 – Dossier des exports MODIS (01 + 01b)")
    qa0_dir = None
    if ask_yes_no("Scénario A (QA = 0)",
                  "Avez-vous exporté les piles du scénario A (QA_MAX = 0, fichiers avec le suffixe _QA0) ?\n\n"
                  "OUI : choisir ensuite leur dossier.\nNON : scénarios B et C seulement."):
        qa0_dir = choose_directory("2/6 – Dossier des exports MODIS du scénario A (suffixe _QA0)", modis_dir)

    lulc_files, env_files = None, None
    if ask_yes_no("LULC / Performance",
                  "Calculer Performance et LPD ? Il faut les cartes LULC (" + ", ".join(str(_y) for _y in YEARS) + ").\n\n"
                  "NON : seulement qualité, Trajectory et State."):
        lulc_dir = choose_directory("3/6 – Dossier des cartes LULC")
        lulc_files = resolve_lulc_files(lulc_dir)
        if ask_yes_no("Stratification environnementale (optionnelle)",
                      "Stratifier les zones de référence par pluie et altitude ?\n\n"
                      "OUI : choisir le dossier des couches (Env_Rainfall..., Env_Elevation...)."):
            env_files = find_environmental_files(choose_directory("4/6 – Dossier des couches environnementales"))
    aoi_vec_path = ""
    if ask_yes_no("Limite de la zone d'étude (optionnel)",
                  "Fournir la limite vectorielle de la zone d'étude (Study_Area_Final.shp) ?\n\n"
                  "Les exports MODIS couvrent le RECTANGLE englobant de la zone, pas son contour : sans limite, "
                  "la zone d'étude est déduite de l'emprise des cartes LULC (si fournies)."):
        aoi_vec_path, _f = QFileDialog.getOpenFileName(
            None, "Limite de la zone d'étude (Study_Area_Final.shp)", modis_dir,
            "Vecteur (*.shp *.gpkg *.geojson *.json);;Tous les fichiers (*)")
    rain_path = ""
    if ask_yes_no("Pluie (optionnel)",
                  "Calculer aussi la variante corrigée de la pluie (State et Trajectory) ?\n\n"
                  "OUI : choisir le CSV journalier CHIRPS (ClimateEngine.csv)."):
        rain_path, _f = QFileDialog.getOpenFileName(
            None, "5/6 – Fichier de pluie (CSV journalier)", modis_dir, "CSV (*.csv *.txt);;Tous les fichiers (*)")
    out_root = choose_directory("6/6 – Dossier de sortie")
    min_prod_years = MIN_PRODUCTIVITY_YEARS
    if lulc_files:
        min_prod_years, ok = QInputDialog.getInt(
            None, "Performance – années minimales de productivité",
            "Années de productivité valides exigées pour appartenir à la population de référence de Performance "
            "(26 années disponibles, 15 par défaut) :", MIN_PRODUCTIVITY_YEARS, 5, 26)
        if not ok:
            raise RuntimeError("Opération annulée.")

    dirs = {k: os.path.join(out_root, v) for k, v in (
        ("qa", "00_QA_Temporal_Coverage"), ("scen", "01_Trajectory_State"), ("perf", "02_Performance"),
        ("lpd", "03_LPD"), ("stats", "04_Statistics"))}
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)
    report = []

    def log(line=""):
        print(line)
        report.append(line)

    # ===================================================== ENTRÉES + COHÉRENCE
    main_pair = load_modis_pair(modis_dir, out_root, "MODIS_B")
    print("\n".join(main_pair["diag"]))
    years = main_pair["years"]
    P_B, NV = main_pair["P"], main_pair["NV"]
    ref_ds = main_pair["ref_ds"]
    ny, rows, cols = P_B.shape
    px_ha = pixel_area_ha(ref_ds)
    base_idx = [i for i, y in enumerate(years) if BASELINE_YEARS[0] <= y <= BASELINE_YEARS[1]]
    rec_idx = [i for i, y in enumerate(years) if RECENT_YEARS[0] <= y <= RECENT_YEARS[1]]
    viol_a = int(np.sum(np.isfinite(P_B) & (NV < MIN_VALID_COMPOSITES_EXPORT)))
    viol_b = int(np.sum(~np.isfinite(P_B) & (NV >= MIN_VALID_COMPOSITES_EXPORT)))

    log("MODIS – LPD COMPLET (productivité)")
    log("=" * 70)
    log(MODIS_DESCRIPTION)
    log("Productivité : {}".format(main_pair["prod_path"]))
    log("n_valid       : {}".format(main_pair["nv_path"]))
    log("Grille {} x {} px | pixel {} ha | {} années ({}-{})".format(
        cols, rows, fmt(px_ha, 2), ny, years[0], years[-1]))
    log("Contrôle de cohérence productivité / n_valid : pixels-années valides avec n_valid < {} : {:,} ; "
        "NoData avec n_valid >= {} : {:,}  (attendu : 0 et 0)".format(
            MIN_VALID_COMPOSITES_EXPORT, viol_a, MIN_VALID_COMPOSITES_EXPORT, viol_b))

    # ===================================================== ZONE D'ÉTUDE (les exports GEE sont des rectangles)
    lulc_on_grid, functional, valid_lulc_n = {}, None, None
    if lulc_files:
        class_counts = {cid: np.zeros((rows, cols), dtype=np.uint8) for cid in REFERENCE_CLASSES}
        valid_lulc_n = np.zeros((rows, cols), dtype=np.uint8)
        for y in YEARS:
            arr = read_aligned_lulc(lulc_files[y], ref_ds)
            lulc_on_grid[y] = arr
            v = np.isfinite(arr)
            valid_lulc_n[v] += 1
            for cid in REFERENCE_CLASSES:
                class_counts[cid][v & (arr == cid)] += 1
        functional = classify_functional_groups(class_counts, valid_lulc_n)
        del class_counts
    study, study_src = None, ""
    if aoi_vec_path:
        try:
            study, study_src = aoi_mask_from_vector(aoi_vec_path, ref_ds), "limite vectorielle fournie"
        except Exception as exc:
            print("[AVERTISSEMENT] limite vectorielle non utilisée : {}".format(exc))
    if study is None and valid_lulc_n is not None:
        study, study_src = valid_lulc_n > 0, "empreinte des cartes LULC (au moins une date valide)"
    if study is None:
        study, study_src = np.ones((rows, cols), dtype=bool), "TOUTE la grille (rectangle d'export non découpé)"
    log("")
    log("ZONE D'ÉTUDE : {} -> {:,} pixels sur {:,} ({:.1f} % du rectangle d'export)".format(
        study_src, int(study.sum()), rows * cols, 100.0 * study.sum() / (rows * cols)))
    if study.all():
        log("   ATTENTION : aucune limite ni carte LULC pour découper la zone : les statistiques portent sur le RECTANGLE "
            "d'export (zone hors contour incluse).")
    P_B[:, ~study] = np.nan
    NV[:, ~study] = np.nan

    # ===================================================== 1. QUALITÉ TEMPORELLE
    log("")
    log("1. QUALITÉ TEMPORELLE (n_valid = composites de 16 jours retenus sur la saison mars-juin)")
    dist_rows, aoi, nmax = nvalid_distribution(NV, P_B, years, MIN_VALID_COMPOSITES_EXPORT)
    n_aoi_px = int(aoi.sum())
    header = ["year", "pixels_aoi"] + ["n_valid={}_pct".format(k) for k in range(0, nmax + 1)] + [
        "no_nvalid_pct", "valid_productivity_pct", "n_valid>=5_pct", "n_valid>=6_pct", "n_valid>=7_pct",
        "full_{}_pct".format(nmax), "excluded_pct"]
    csv_rows, tot = [], {k: 0 for k in range(0, nmax + 1)}
    for r in dist_rows:
        N = max(1, r["n_aoi"])
        csv_rows.append([r["year"], r["n_aoi"]] + [fmt(100.0 * r["counts"][k] / N, 2) for k in range(0, nmax + 1)] + [
            fmt(100.0 * r["no_nvalid"] / N, 2), fmt(100.0 * r["valid_productivity"] / N, 2),
            fmt(100.0 * r["ge5"] / N, 2), fmt(100.0 * r["ge6"] / N, 2), fmt(100.0 * r["ge7"] / N, 2),
            fmt(100.0 * r["full"] / N, 2), fmt(100.0 * r["excluded"] / N, 2)])
        for k in tot:
            tot[k] += r["counts"][k]
    write_csv(os.path.join(dirs["qa"], "QA_nvalid_distribution_by_year.csv"), header, csv_rows)
    n_all = max(1, sum(r["n_aoi"] for r in dist_rows))
    summary_rows = [["n_valid = {}".format(k), tot[k], fmt(100.0 * tot[k] / n_all, 2)] for k in range(0, nmax + 1)]
    ge = lambda k: sum(tot[j] for j in range(k, nmax + 1))
    summary_rows += [["n_valid >= {}".format(k), ge(k), fmt(100.0 * ge(k) / n_all, 2)] for k in (5, 6, 7) if k <= nmax]
    write_csv(os.path.join(dirs["qa"], "QA_nvalid_summary.csv"), ["Category (pixel-years)", "Pixel_years", "Percent"], summary_rows)
    log("   Zone d'étude : {:,} pixels ({:,.0f} ha, approximation par pixels) | n_valid maximal observé : {}".format(
        n_aoi_px, n_aoi_px * px_ha, nmax))
    log("   Répartition sur l'ensemble des pixels-années : " + " | ".join(
        "{} composites {:.1f} %".format(k, 100.0 * tot[k] / n_all) for k in range(nmax, -1, -1) if tot[k] / n_all >= 0.0005))
    log("   n_valid >= 5 : {:.2f} % | >= 6 : {:.2f} % | >= 7 : {:.2f} % des pixels-années".format(
        100.0 * ge(5) / n_all, 100.0 * ge(6) / n_all, 100.0 * ge(7) / n_all))
    worst = sorted(dist_rows, key=lambda r: r["valid_productivity"] / max(1, r["n_aoi"]))[:3]
    log("   Années à la couverture la plus faible : " + ", ".join(
        "{} ({:.1f} % valide)".format(r["year"], 100.0 * r["valid_productivity"] / max(1, r["n_aoi"])) for r in worst))
    layers = pixel_quality_layers(P_B, NV, nmax, aoi)
    write_multiband(os.path.join(dirs["qa"], "01c_MODIS_DataQuality.tif"), list(layers.values()), list(layers.keys()), ref_ds)
    pers = layers["persistent_low_flag"]
    n_pers = int(np.nansum(pers))
    log("   Pixels à n_valid <= {} dans >= {:.0f} % des années (qualité faible persistante) : {:,} ({:.2f} % de la zone)".format(
        PERSISTENT_LOW_NVALID, 100 * PERSISTENT_LOW_FRACTION, n_pers, 100.0 * n_pers / max(1, n_aoi_px)))
    log("   Part moyenne de pixels-années à couverture complète ({} composites) : {:.1f} %".format(
        nmax, float(np.nanmean(layers["share_full_pct"]))))
    log("   -> 00_QA_Temporal_Coverage/ : 01c_MODIS_DataQuality.tif + 2 CSV")

    # ===================================================== 2. SCÉNARIOS
    scenarios = {SCEN_B: P_B, SCEN_C: apply_min_valid(P_B, NV, SCENARIO_C_MIN_VALID)}
    if qa0_dir:
        pair_a = load_modis_pair(qa0_dir, out_root, "MODIS_A", must_extra=("qa0",))
        if pair_a["years"] != years or pair_a["P"].shape != P_B.shape:
            raise RuntimeError("Le scénario A n'a pas les mêmes années ou la même grille que le scénario B.")
        pair_a["P"][:, ~study] = np.nan
        scenarios[SCEN_A] = pair_a["P"]
        log("   Scénario A (QA = 0) chargé : {}".format(pair_a["prod_path"]))
    log("")
    log("2. SCÉNARIOS DE SENSIBILITÉ")
    for name, P_s in scenarios.items():
        n_vy = int(np.isfinite(P_s).sum())
        log("   {:<12s} pixels-années valides : {:,} ({:.2f} % de ceux du scénario B)".format(
            name, n_vy, 100.0 * n_vy / max(1, int(np.isfinite(P_B).sum()))))

    # ===================================================== 3-4. TRAJECTORY ET STATE
    log("")
    log("3-4. TRAJECTORY (Sen + Mann-Kendall) ET STATE par scénario")
    res = {}
    for name, P_s in scenarios.items():
        res[name] = analyze_scenario(P_s, years, base_idx, rec_idx)
        d = res[name]
        v = d["traj_valid"]
        n_t = int(v.sum())
        sig_neg = 100.0 * float(np.mean((d["p"][v] < P_ALPHA) & (d["slope"][v] < 0))) if n_t else float("nan")
        sig_pos = 100.0 * float(np.mean((d["p"][v] < P_ALPHA) & (d["slope"][v] > 0))) if n_t else float("nan")
        scr = 100.0 * float(np.mean(np.abs(d["tau"][v]) >= TAU_MAIN)) if n_t else float("nan")
        sh = shares(d["state_class"], v)
        log("   {:<12s} Trajectory : {:,} px | |tau| >= {:.2f} : {:.1f} % | Mann-Kendall p < {} : négatif {:.1f} %, positif {:.1f} %".format(
            name, n_t, TAU_MAIN, scr, P_ALPHA, sig_neg, sig_pos))
        log("   {:<12s} State (±{:.0f} %) : dégradé {:.1f} % | stable {:.1f} % | amélioré {:.1f} %".format(
            "", 100 * STATE_THRESHOLD, sh[1], sh[2], sh[3]))
        sub = os.path.join(dirs["scen"], name)
        write_multiband(os.path.join(sub, "03_Trajectory_Sen_Kendall.tif"),
                        [d["slope"], d["tau"], d["n_valid"], d["z"], d["p"],
                         np.where(d["traj_valid"], (np.abs(d["tau"]) >= TAU_MAIN).astype(np.float32), np.nan)],
                        ["sen_slope", "mk_tau", "mk_n_valid", "mk_z", "mk_p", "mk_tau_abs_ge_030"], ref_ds)
        write_multiband(os.path.join(sub, "04_State.tif"),
                        [d["base_mean"], d["recent_mean"], d["state_rel"],
                         np.where(d["state_class"] > 0, d["state_class"], np.nan), d["base_n"], d["recent_n"]],
                        ["baseline_mean", "recent_mean", "state_relative_change", "state_class", "baseline_n", "recent_n"], ref_ds)
    n_low_base = int((res[SCEN_B]["traj_valid"] & np.isfinite(res[SCEN_B]["base_mean"])
                      & (res[SCEN_B]["base_mean"] < MIN_BASELINE_MEAN)).sum())
    log("   Exclus de State (NDVI moyen de référence < {:.2f} : eau, sebkha, sol nu) : {:,} px".format(MIN_BASELINE_MEAN, n_low_base))

    RELIABLE_YEARS_USED = scaled_min(RELIABLE_MIN_YEARS, len(years))         # 20 années valides sur 26 ; proportionnel pour une série plus courte (base 2000-2015 : 12)
    rel_cls, mnb, mnr = reliability_class(P_B, NV, base_idx, rec_idx, min_years=RELIABLE_YEARS_USED)
    create_geotiff(os.path.join(dirs["scen"], SCEN_B, "State_Reliability_Class.tif"),
                   np.where(rel_cls > 0, rel_cls, NODATA_U8).astype(np.uint8), ref_ds, gdal.GDT_Byte, NODATA_U8)

    if not lulc_files:
        log("")
        log("Performance et LPD non calculés (cartes LULC non fournies).")
        _finish(report, dirs, out_root, t0, log)
        return

    # ===================================================== 5. PERFORMANCE
    log("")
    log("5. PERFORMANCE (zones de référence issues du LULC, P90 de la productivité moyenne)")
    rain_arr = elev_arr = None
    if env_files:
        if env_files.get("rain"):
            rain_arr = read_aligned_env(env_files["rain"], ref_ds)
        if env_files.get("elev"):
            elev_arr = read_aligned_env(env_files["elev"], ref_ds)
    _requested = min_prod_years
    min_prod_years = min(min_prod_years, max(5, len(years) - 1))      # on ne peut pas exiger plus d'années valides que la série n'en compte : inchangé pour 16 ans et plus (15), ramené à 12 pour une série de 13 ans
    if min_prod_years != _requested:
        log("Performance : années minimales de productivité ramenées de {} à {} (série de {} années).".format(_requested, min_prod_years, len(years)))
    perfs = {name: performance_for(P_s, functional, rain_arr, elev_arr, min_prod_years) for name, P_s in scenarios.items()}
    pB = perfs[SCEN_B]
    n_ref = int(pB["reference"].sum())
    log("   Population de référence (>= {} années de productivité, LULC cultures/jachère/forêt/parcours) : {:,} px ({:.1f} % de la zone)".format(
        min_prod_years, n_ref, 100.0 * n_ref / max(1, n_aoi_px)))
    log("   Zones : {}".format("stratifiées par pluie/altitude (repli < {} px)".format(MIN_PIXELS_STRATIFIED_ZONE)
                              if pB["stratified"] else "groupes fonctionnels seuls"))
    nlow = int(np.sum(pB["perf"]["low"] == 1))
    nok = int(np.sum(np.isin(pB["perf"]["low"], (0, 1))))
    log("   Performance faible (ratio < {:.2f}) : {:,} px ({:.2f} % des pixels de référence)".format(
        PERFORMANCE_RATIO_THRESHOLD, nlow, 100.0 * nlow / max(1, nok)))
    write_multiband(os.path.join(dirs["perf"], "Performance_Layers.tif"),
                    [np.where(pB["reference"], functional, np.nan), pB["zones"].astype(np.float32), pB["ltm"],
                     np.where(pB["perf"]["ratio"] > -9998, pB["perf"]["ratio"], np.nan),
                     np.where(np.isin(pB["perf"]["low"], (0, 1)), pB["perf"]["low"], np.nan),
                     np.where(pB["robustness"] != NODATA_U8, pB["robustness"], np.nan)],
                    ["functional_group", "zone_id", "longterm_mean", "performance_ratio", "low_performance", "low_robustness"], ref_ds)
    zs_rows = []
    for zid, st in sorted(pB["perf"]["zone_stats"].items()):
        zs_rows.append([zid, describe_zone(zid), st["n"], fmt(st["mean"], 4), fmt(st["sd"], 4), fmt(st["cv"], 3),
                        fmt(st["p10"], 4), fmt(st["p50"], 4), fmt(st["p90"], 4)])
    write_csv(os.path.join(dirs["perf"], "Performance_Zone_Statistics.csv"),
              ["zone_id", "description", "pixels", "mean", "sd", "cv", "p10", "median", "p90"], zs_rows)
    write_csv(os.path.join(dirs["perf"], "Performance_Threshold_Table.csv"),
              ["threshold", "group", "valid_px", "low_px", "low_pct"],
              [[r["threshold"], r["group"], r["valid_px"], r["low_px"], fmt(r["low_pct"], 2)] for r in pB["threshold_rows"]])

    # ===================================================== 6. LPD
    log("")
    log("6. LPD (Trajectory + State + Performance)")
    lpd = {}
    for name in scenarios:
        l3, l5, v = lpd_from(res[name], res[name]["state_class"], perfs[name]["perf"]["low"])
        lpd[name] = {"l3": l3, "l5": l5, "valid": v}
    LB = lpd[SCEN_B]
    n_lpd = int(LB["valid"].sum())
    aoi_ha = n_aoi_px * px_ha
    log("   Pixels LPD valides (scénario B) : {:,} = {:,.0f} ha = {:.1f} % de la zone d'étude".format(
        n_lpd, n_lpd * px_ha, 100.0 * n_lpd / max(1, n_aoi_px)))
    t3 = class_table(LB["l3"], LB["valid"], LPD3_LABELS, px_ha)
    t5 = class_table(LB["l5"], LB["valid"], LPD5_LABELS, px_ha)
    log("   LPD 3 classes (B) : " + " | ".join("{} {:,.0f} ha ({:.1f} %)".format(r[1], r[3], r[4]) for r in t3))
    log("   LPD 5 classes (B) : " + " | ".join("{} {:.1f} %".format(r[1], r[4]) for r in t5))

    sens_rows, robust = run_sensitivity(
        np.where(np.isfinite(res[SCEN_B]["slope"]), res[SCEN_B]["slope"], 0.0),
        np.where(np.isfinite(res[SCEN_B]["tau"]), res[SCEN_B]["tau"], 0.0),
        res[SCEN_B]["state_class"].astype(np.int16),
        np.where(pB["perf"]["ratio"] > -9998, pB["perf"]["ratio"], np.inf),
        LB["valid"], TAU_SENSITIVITY, PERFORMANCE_SENSITIVITY_THRESHOLDS, px_ha)
    degs = [r["deg_pct"] for r in sens_rows]
    log("   Sensibilité (tau {} x Performance {}) : dégradé de {:.1f} % à {:.1f} %".format(
        TAU_SENSITIVITY, PERFORMANCE_SENSITIVITY_THRESHOLDS, min(degs), max(degs)))
    write_csv(os.path.join(dirs["stats"], "LPD_Sensitivity_Grid.csv"),
              ["tau_threshold", "performance_threshold", "valid_px", "degraded_px", "stable_px", "improved_px", "degraded_pct", "degraded_ha"],
              [[r["tau"], r["perf"], r["valid"], r["deg"], r["stable"], r["imp"], fmt(r["deg_pct"], 2), fmt(r["deg_ha"], 1)] for r in sens_rows])
    lp3, lp5, vp = lpd_from(res[SCEN_B], res[SCEN_B]["state_class"], pB["perf"]["low"], use_p=True)
    nd_p = int(((lp3 == -1) & vp).sum())
    log("   Critère de tendance Mann-Kendall p < {} au lieu de |tau| >= {:.2f} : dégradé {:.1f} % (tau : {:.1f} %)".format(
        P_ALPHA, TAU_MAIN, 100.0 * nd_p / max(1, int(vp.sum())), t3[0][4]))

    create_geotiff(os.path.join(dirs["lpd"], "LPD_3class_{}.tif".format(SCEN_B)), LB["l3"], ref_ds, gdal.GDT_Int16, NODATA_I16)
    create_geotiff(os.path.join(dirs["lpd"], "LPD_5class_{}.tif".format(SCEN_B)), LB["l5"], ref_ds, gdal.GDT_Byte, NODATA_U8)
    create_geotiff(os.path.join(dirs["lpd"], "LPD_Degradation_Robustness_{}.tif".format(SCEN_B)), robust, ref_ds, gdal.GDT_Byte, NODATA_U8)
    for name in (SCEN_A, SCEN_C):
        if name in lpd:
            create_geotiff(os.path.join(dirs["lpd"], "LPD_3class_{}.tif".format(name)), lpd[name]["l3"], ref_ds, gdal.GDT_Int16, NODATA_I16)

    # --- fiabilité
    rel_valid = LB["valid"] & (rel_cls > 0)
    rel_rows = []
    for cid, lab in ((1, "High (mean composites >= {:.0f} in both periods, >= {} valid years)".format(RELIABLE_MEAN_NVALID, RELIABLE_YEARS_USED)),
                     (2, "Lower reliability")):
        m = rel_valid & (rel_cls == cid)
        n = int(m.sum())
        d, s, i = (int((m & (LB["l3"] == c)).sum()) for c in (-1, 0, 1))
        rel_rows.append([cid, lab, n, fmt(n * px_ha, 1), fmt(100.0 * n / max(1, n_lpd), 2), fmt(100.0 * d / max(1, n), 2),
                         fmt(100.0 * s / max(1, n), 2), fmt(100.0 * i / max(1, n), 2)])
    write_csv(os.path.join(dirs["stats"], "LPD_Reliability_Statistics.csv"),
              ["reliability_class", "label", "pixels", "area_ha", "share_of_LPD_%", "degraded_%", "stable_%", "improved_%"], rel_rows)
    for r in rel_rows:
        log("   Fiabilité {} : {:>9,} px ({}) | dégradé {} % | stable {} % | amélioré {} %".format(
            r[0], r[2], r[4] + " % du LPD", r[5], r[6], r[7]))

    # --- variante corrigée de la pluie
    adj = None
    if rain_path:
        with open(rain_path, encoding="utf-8-sig", errors="replace") as f:
            daily = parse_daily_rain(f.read())
        if len(daily) < 3000:
            raise RuntimeError("Le CSV de pluie doit être JOURNALIER (>= 3000 jours lus ; lus : {}).".format(len(daily)))
        rain = wet_season_rain(daily, years)
        R = np.array([rain[y] for y in years], dtype=np.float64)
        X = P_B.reshape(ny, -1)
        ra = rain_adjusted_state(X, R, base_idx, rec_idx, scaled_min(MIN_REG_YEARS, ny), MIN_BASE_YEARS, MIN_RECENT_YEARS)
        rel_h, reliable = hybrid_relative_change(ra["rel_obs"], ra["rel_adj"], ra["r2"], R2_RELIABLE)
        cls_h = classify_state(rel_h, STATE_THRESHOLD).reshape(rows, cols)
        P_res = residual_series(X, R, ra["slope"], ra["intercept"], reliable)
        tr_adj = sen_kendall_chunked(P_res, np.array(years, dtype=np.float64), scaled_min(MIN_VALID_YEARS_TRAJ, ny))
        tr_adj = {k: v.reshape(rows, cols) for k, v in tr_adj.items()}
        l3a, l5a, va = lpd_from(tr_adj, cls_h, pB["perf"]["low"])
        adj = {"l3": l3a, "l5": l5a, "valid": va, "state_class": cls_h, "traj": tr_adj}
        rb_ = float(np.nanmean([rain[y] for y in years if BASELINE_YEARS[0] <= y <= BASELINE_YEARS[1]]))
        rr_ = float(np.nanmean([rain[y] for y in years if RECENT_YEARS[0] <= y <= RECENT_YEARS[1]]))
        r2v = ra["r2"][np.isfinite(ra["r2"])]
        ta = class_table(l3a, va, LPD3_LABELS, px_ha)
        log("")
        log("7. VARIANTE CORRIGÉE DE LA PLUIE (State hybride + Trajectory sur résidus, correction là où R² >= {:.2f})".format(R2_RELIABLE))
        log("   Pluie {} : {}-{} = {:.0f} mm | {}-{} = {:.0f} mm | écart {:+.1f} %".format(
            rain_window_label(),            BASELINE_YEARS[0], BASELINE_YEARS[1], rb_, RECENT_YEARS[0], RECENT_YEARS[1], rr_, 100 * (rr_ - rb_) / rb_))
        log("   R² médian pluie -> productivité : {:.2f} ; pixels avec R² >= {:.2f} : {:.0f} %".format(
            float(np.median(r2v)) if r2v.size else float("nan"), R2_RELIABLE,
            100.0 * float(np.mean(r2v >= R2_RELIABLE)) if r2v.size else float("nan")))
        log("   LPD 3 classes (variante corrigée) : " + " | ".join("{} {:,.0f} ha ({:.1f} %)".format(r[1], r[3], r[4]) for r in ta))
        log("   -> le LPD du scénario B est la borne HAUTE du dégradé ; la variante corrigée en est une borne BASSE.")
        create_geotiff(os.path.join(dirs["lpd"], "LPD_3class_{}_RainAdjusted.tif".format(SCEN_B)), l3a, ref_ds, gdal.GDT_Int16, NODATA_I16)
        create_geotiff(os.path.join(dirs["lpd"], "LPD_5class_{}_RainAdjusted.tif".format(SCEN_B)), l5a, ref_ds, gdal.GDT_Byte, NODATA_U8)

    # ===================================================== COMPARAISON DES SCÉNARIOS
    cmp_rows, cmp_lines = [], []
    for name in scenarios:
        if name == SCEN_B:
            continue
        c = compare_scenarios(res[SCEN_B], res[name], LB["l3"], lpd[name]["l3"], LB["valid"], lpd[name]["valid"],
                              pB["ltm"], perfs[name]["ltm"], px_ha)
        cmp_rows.append([name, c["traj_common"], fmt(c["sen_corr"], 4), fmt(c["sen_mad"], 6), fmt(c["tau_corr"], 4),
                         fmt(c["tau_screen_agree"], 2), fmt(c["mk_class_agree"], 2), c["state_common"], fmt(c["state_agree"], 2),
                         fmt(c["state_deg_ref"], 2), fmt(c["state_deg_alt"], 2), fmt(c["ltm_corr"], 4),
                         fmt(c["ltm_mean_rel_diff_pct"], 2), fmt(c["lpd"]["agreement_pct"], 2)])
        cmp_lines.append("   {} contre B : corrélation Sen {:.3f} | accord |tau| >= {:.2f} {:.1f} % | accord Mann-Kendall {:.1f} % | "
                         "accord State {:.1f} % (dégradé {:.1f} % -> {:.1f} %) | accord LPD 3 classes {:.1f} %".format(
                             name, c["sen_corr"], TAU_MAIN, c["tau_screen_agree"], c["mk_class_agree"], c["state_agree"],
                             c["state_deg_ref"], c["state_deg_alt"], c["lpd"]["agreement_pct"]))
    write_csv(os.path.join(dirs["stats"], "Scenario_Comparison_vs_B.csv"),
              ["scenario", "trajectory_common_px", "Sen_corr", "Sen_mean_abs_diff", "tau_corr", "tau_screen_agreement_%",
               "MannKendall_class_agreement_%", "state_common_px", "state_agreement_%", "state_degraded_B_%", "state_degraded_alt_%",
               "longterm_mean_corr", "longterm_mean_rel_diff_%", "LPD_3class_agreement_%"], cmp_rows)
    log("")
    log("8. COMPARAISON DES SCÉNARIOS (robustesse)")
    for ln in cmp_lines:
        log(ln)
    if not cmp_lines:
        log("   (un seul scénario disponible)")
    log("   Si ces accords sont élevés (> 90 %), les résultats ne dépendent pas du choix du QA ni du minimum de composites.")

    # ===================================================== STATISTIQUES DE TYPE UNCCD
    log("")
    log("9. STATISTIQUES DE TYPE UNCCD (productivité) -> 04_Statistics/")

    def class_rows(tbl, valid_n):
        return [[r[0], r[1], r[2], fmt(r[3], 1), fmt(r[4], 2), fmt(100.0 * r[2] / max(1, n_aoi_px), 2)] for r in tbl]
    stat_rows = []
    variants = [(SCEN_B, LB)] + [(n, lpd[n]) for n in (SCEN_A, SCEN_C) if n in lpd]
    if adj:
        variants.append((SCEN_B + "_RainAdjusted", adj))
    for vname, vd in variants:
        for r in class_table(vd["l5"], vd["valid"], LPD5_LABELS, px_ha):
            stat_rows.append([vname, "LPD 5 classes", r[0], r[1], r[2], fmt(r[3], 1), fmt(r[4], 2),
                              fmt(100.0 * r[2] / max(1, n_aoi_px), 2)])
        for r in class_table(vd["l3"], vd["valid"], LPD3_LABELS, px_ha):
            stat_rows.append([vname, "LPD 3 classes", r[0], r[1], r[2], fmt(r[3], 1), fmt(r[4], 2),
                              fmt(100.0 * r[2] / max(1, n_aoi_px), 2)])
    write_csv(os.path.join(dirs["stats"], "LPD_Area_Statistics.csv"),
              ["variant", "scheme", "class", "label", "pixels", "area_ha", "percent_of_assessed_area", "percent_of_study_area"], stat_rows)

    cov_rows = [
        ["Study area (MODIS pixels with data)", n_aoi_px, fmt(n_aoi_px * px_ha, 1), "100.00"],
        ["Trajectory valid (>= {} years)".format(scaled_min(MIN_VALID_YEARS_TRAJ, ny)), int(res[SCEN_B]["traj_valid"].sum()),
         fmt(res[SCEN_B]["traj_valid"].sum() * px_ha, 1), fmt(100.0 * res[SCEN_B]["traj_valid"].sum() / max(1, n_aoi_px), 2)],
        ["State valid", int((res[SCEN_B]["state_class"] > 0).sum()), fmt((res[SCEN_B]["state_class"] > 0).sum() * px_ha, 1),
         fmt(100.0 * (res[SCEN_B]["state_class"] > 0).sum() / max(1, n_aoi_px), 2)],
        ["Performance valid (reference land cover)", nok, fmt(nok * px_ha, 1), fmt(100.0 * nok / max(1, n_aoi_px), 2)],
        ["LPD valid (all three)", n_lpd, fmt(n_lpd * px_ha, 1), fmt(100.0 * n_lpd / max(1, n_aoi_px), 2)],
    ]
    write_csv(os.path.join(dirs["stats"], "LPD_Coverage.csv"), ["Layer", "Pixels", "Area_ha", "Percent_of_study_area"], cov_rows)
    log("   LPD_Area_Statistics.csv (5 et 3 classes, par variante) | LPD_Coverage.csv | LPD_Sensitivity_Grid.csv | "
        "Scenario_Comparison_vs_B.csv | LPD_Reliability_Statistics.csv")

    hdr = ["category_id", "category", "assessed_px", "assessed_ha", "degraded_ha", "degraded_%", "stable_ha", "stable_%",
           "improved_ha", "improved_%"]
    for y in STATS_LULC_YEARS:
        if y in lulc_on_grid:
            cat = np.where(np.isfinite(lulc_on_grid[y]), lulc_on_grid[y], 0).astype(np.int16)
            rws = share_rows(LB["l3"], LB["valid"], cat, CLASS_NAMES, px_ha)
            all_cat = {cid: int(((cat == cid) & aoi).sum()) for cid in CLASS_NAMES}
            out_rows = [[r[0], r[1], r[2], fmt(r[3], 1), fmt(r[4], 1), fmt(r[5], 2), fmt(r[6], 1), fmt(r[7], 2), fmt(r[8], 1), fmt(r[9], 2)]
                        for r in rws]
            write_csv(os.path.join(dirs["stats"], "LPD_by_LandCover_{}.csv".format(y)), hdr + ["class_area_in_study_area_ha"],
                      [o + [fmt(all_cat[o[0]] * px_ha, 1)] for o in out_rows])
    ftab = share_rows(LB["l3"], LB["valid"], functional.astype(np.int16), ZONE_DESCRIPTIONS, px_ha)
    write_csv(os.path.join(dirs["stats"], "LPD_by_FunctionalGroup.csv"), hdr,
              [[r[0], r[1], r[2], fmt(r[3], 1), fmt(r[4], 1), fmt(r[5], 2), fmt(r[6], 1), fmt(r[7], 2), fmt(r[8], 1), fmt(r[9], 2)] for r in ftab])
    last = max(y for y in STATS_LULC_YEARS if y in lulc_on_grid) if any(y in lulc_on_grid for y in STATS_LULC_YEARS) else None
    if last:
        cat = np.where(np.isfinite(lulc_on_grid[last]), lulc_on_grid[last], 0).astype(np.int16)
        for r in share_rows(LB["l3"], LB["valid"], cat, CLASS_NAMES, px_ha):
            if r[2]:
                log("   LULC {} | {:<18s} : {:>8,.0f} ha évalués | dégradé {:.1f} % | amélioré {:.1f} %".format(last, r[1], r[3], r[5], r[9]))

    add_paletted(os.path.join(dirs["lpd"], "LPD_3class_{}.tif".format(SCEN_B)), "MODIS LPD 3 classes (scénario B)",
                 [(-1, "d73027", "Degraded"), (0, "fee08b", "Stable"), (1, "1a9850", "Improved")])
    add_paletted(os.path.join(dirs["lpd"], "LPD_5class_{}.tif".format(SCEN_B)), "MODIS LPD 5 classes (scénario B)",
                 [(1, "d73027", "Declining"), (2, "fc8d59", "Moderate decline"), (3, "fee08b", "Stressed"),
                  (4, "a6d96a", "Stable"), (5, "1a9850", "Improving")])
    if adj:
        add_paletted(os.path.join(dirs["lpd"], "LPD_3class_{}_RainAdjusted.tif".format(SCEN_B)), "MODIS LPD 3 classes (corrigé de la pluie)",
                     [(-1, "d73027", "Degraded"), (0, "fee08b", "Stable"), (1, "1a9850", "Improved")])
    _finish(report, dirs, out_root, t0, log)


def _finish(report, dirs, out_root, t0, log):
    log("")
    log("MÉTHODE ET LIMITES (à reprendre dans le texte de la méthodologie)")
    log("  - " + MODIS_DESCRIPTION)
    log("  - Productivité annuelle = moyenne du NDVI des composites de 16 jours retenus (QA, minimum de composites) sur mars-juin.")
    log("  - Les seuils (|tau| 0,30, State ±10 %, ratio de Performance 0,50, P90, minima d'années) sont des paramètres ANALYTIQUES")
    log("    de l'étude, pas des seuils imposés par l'UNCCD ; leur sensibilité est quantifiée (04_Statistics/).")
    log("  - Mann-Kendall : p bilatéral par approximation normale (variance sans correction d'ex-aequo).")
    log("  - LULC échantillonné à 5 dates et ramené à 250 m par la classe dominante ; Performance concerne les classes cultures, jachère,")
    log("    forêt/matorral et parcours ; bâti, eau, sebkha et sol nu ne sont pas évalués par Performance.")
    log("  - 250 m : des pixels mixtes ; LPD = composante Productivité, ce n'est PAS le SDG 15.3.1 complet (Land Cover et SOC requis).")
    log("  - L'effet du climat n'est pas retiré du LPD principal : la variante corrigée de la pluie en est le complément.")
    log("")
    log("Durée : {:.1f} min | Sorties : {}".format((time.time() - t0) / 60.0, out_root))
    with open(os.path.join(out_root, "MODIS_LPD_REPORT.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    try:
        _inp = []
        for _l in report:
            _m = re.match(r"^(Productivité|n_valid)\s*:\s*(.+\.tif)\s*$", _l.strip())
            if _m:
                _inp.append({"label": _m.group(1), "path": _m.group(2)})
        _par = {n: globals()[n] for n in ("LPD_PERIOD", "TREND_START_YEAR", "RAIN_WINDOW_MONTHS", "BASELINE_STATE_END", "BASELINE_STATE_RECENT", "TAU_MAIN", "MIN_VALID_YEARS_TRAJ", "MIN_BASELINE_MEAN", "SCEN_A", "SCEN_B", "SCEN_C") if n in globals()}
        _par["main_scenario"] = globals().get("SCEN_B", "B_QA1_min5")
        lpd_stage_report(out_root, dirs, report, t0, _par, _inp, AREA_NAME, REPORT_LANG)
    except Exception as _exc:
        print("[Rapport HTML d'étape] échec (le traitement lui-même est terminé) : " + str(_exc))
    QMessageBox.information(None, "MODIS LPD terminé", "\n".join(report[:70]))


try:
    main()
except Exception as exc:
    msg = "MODIS LPD complet - échec.\n\n" + str(exc) + "\n\n" + traceback.format_exc()
    print(msg)
    try:
        QMessageBox.critical(None, "Erreur MODIS LPD", msg)
    except Exception:
        pass