# -*- coding: utf-8 -*-
# SDG 15.3.1 REFERENCE PIPELINE — STAGE 06 / 08 : Soil organic carbon (SOC) change — QGIS
"""
UNCCD_SOC_FINAL_QGIS.py   —   SOUS-INDICATEUR SOC (COS) : VERSION FINALE V4   |   <AREA_NAME>   |   QGIS

Fondé sur UNCCD_SOC_LULC_QGIS_V3 (grille SOC de référence SoilGrids, LULC agrégée par MODE, QA/QC, aucun facteur inventé),
avec les améliorations suivantes :

  1. FACTEURS PAR CLASSE, DOCUMENTÉS ET COHÉRENTS (au lieu de 64 facteurs de transition libres) :
       f(a -> b) = valeur(b) / valeur(a)  =>  aucune dérive lors d'un aller-retour, et seul le LULC aux deux dates extrêmes compte.
     Chaque facteur doit avoir : valeur, type (measured / literature / ipcc / expert), source, confiance, bornes low/high.
     Une classe observée sans facteur documenté => le script REFUSE de calculer (jamais de valeur par défaut).
  2. FRACTIONS DE CLASSES 30 m -> grille SOC (moyenne GDAL pondérée par la surface) : les classes minoritaires (bâti, eau) ne
     disparaissent plus comme avec le MODE seul ; le MODE est conservé pour les matrices de transition et comme test de sensibilité.
  3. ANCRAGE DE SOILGRIDS RÉGLABLE (année du LULC) : la variation en % n'en dépend pas ; seules les valeurs absolues (t C/ha) en dépendent.
  4. RÉPONSE PROGRESSIVE DU STOCK (20 ans, option) ou instantanée : les cartes sont séparées d'intervalles de 5 à 15 ans ; les
     facteurs du GIEC décrivent un équilibre atteint après ~20 ans.
  5. SOC RECONSTITUÉ pour les dates de YEARS (les années diagnostiques, ex. 2000, en sont exclues par défaut : SOC_USE_DIAGNOSTIC_YEARS) ; variations par période (consécutives, 1999-2025, 2000-2025) en valeur absolue, en %,
     annualisée, et en 3 classes (perte / stable / gain) selon un seuil ANALYTIQUE (10 % par défaut, pas une règle UNCCD mondiale).
  6. INCERTITUDE par Monte-Carlo (facteurs tirés dans [low, high]) : part dégradée P10/P50/P90 et carte de probabilité de dégradation.
  7. STATISTIQUES : surfaces par classe et par période, par occupation du sol, médiane / P10 / P90, stock total (Mt C), sensibilité
     (MODE contre fractions ; progressive contre instantanée), rapport de qualité des données.

ENTRÉES : SoilGrids (stock de C organique 0-30 cm), limite de la zone, cartes LULC des dates de YEARS (1999, 2007, 2015, 2020, 2025 par défaut),
          table des facteurs par classe (le script génère un MODÈLE vide si vous l'annulez).

SORTIES (dossier choisi) : 00_QA, 01_Reference, 02_Transitions, 03_SOC_Reconstructed, 04_SOC_Change, 05_Uncertainty,
          06_Statistics, SOC_Methodology_V4.txt.

IMPORTANT
  - SoilGrids n'est PAS une série temporelle : le SOC historique est une ESTIMATION RECONSTITUÉE (modèle), jamais une observation.
  - Le SOC ne change ici que si la classe LULC change : l'erreur de classification LULC se transmet au SOC (à évaluer).
  - Résolution du SOC = grille SoilGrids recadrée ; elle n'est ni celle du LULC (30 m) ni celle du LPD MODIS (250 m).
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
SOC_USE_DIAGNOSTIC_YEARS = False   # False : les années diagnostiques (DIAGNOSTIC_YEARS, ex. 2000 = sécheresse) sont EXCLUES de la reconstitution du SOC (elles feraient sortir de l'analyse des cellules à TOUTES les dates et fausseraient la réponse sur 20 ans) ; True : toutes les dates de LULC_YEARS
EXTRA_SOC_PAIRS = [(1999, 2015), (2015, 2025), (1999, 2025), (2000, 2025)]   # périodes SOC supplémentaires : t0 -> 2015 (base UNCCD), 2015 -> 2025 (suivi), globales ; lues par l'étape 07 dans le nom SOC_Class_<début>_<fin>.tif
# =================================================================================================================================

PIPELINE_BUILD = "2026.10-ca74f8b5b8bf"
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
def _ne_total_ha(rows):
    """Surface NON ESTIMABLE (ha) d'après SOC_NotEstimable_Area.csv : le fichier contient une ligne par classe (cellules où la classe dépasse la tolérance à AU MOINS UNE date ; les classes se recouvrent) PLUS une ligne « total » ;
    il faut lire la ligne « total » (sommer toutes les lignes compterait les cellules deux fois). Sans ligne « total » : somme des lignes."""
    dr = sr_dict_rows(rows)
    tot = next((sr_num(x.get("area_ha"), 0) for x in dr if str(x.get("class_code", "")).strip().lower() == "total"), None)
    return tot if tot is not None else sum(sr_num(x.get("area_ha"), 0) for x in dr)


def soc_stage_report(out_root, dirs, report_lines, t0, params, inputs, area_name, years, lang="en", log=print):
    """Rapport HTML de l'étape 06 (SOC) : lit les CSV et rasters écrits par le script."""
    en = lang == "en"
    T = lambda a, b: a if en else b
    rd = lambda k, n: sr_read_csv(os.path.join(dirs[k], n))
    stats = dirs["stats"]
    totals, area, perc, mth, fal, mc = rd("stats", "SOC_Totals_MtC.csv"), rd("stats", "SOC_Area_Statistics.csv"), rd("stats", "SOC_Change_Percentiles.csv"), rd("stats", "SOC_Method_Sensitivity.csv"), rd("stats", "SOC_Fallow_Sensitivity.csv"), rd("unc", "SOC_MonteCarlo_Summary.csv")
    fac, qa30, mode_frac, notest = rd("qa", "Factors_Used.csv"), rd("qa", "QA_Transitions_30m_externes.csv"), rd("qa", "LULC_Area_Mode_vs_Fraction.csv"), rd("stats", "SOC_NotEstimable_Area.csv")
    y0, y1 = int(min(years)), int(max(years))
    tag = f"{y0}_{y1}"
    summary, checks = [], []
    pa = {}
    for r in sr_dict_rows(area):
        pa.setdefault(r.get("period"), {})[r.get("class")] = sr_num(r.get("percent"))
    if tag in pa:
        summary.append(T(f"SOC change {y0}–{y1}: ", f"Variation du SOC {y0}–{y1} : ") + " | ".join(f"{k} {v:.1f} %" for k, v in pa[tag].items()))
    tt = sr_dict_rows(totals)
    if len(tt) >= 2:
        a, b = sr_num(tt[0].get("total_SOC_Mt_C")), sr_num(tt[-1].get("total_SOC_Mt_C"))
        summary.append(T(f"Reconstructed SOC stock 0–30 cm: {a:.2f} Mt C ({tt[0].get('year')}) → {b:.2f} Mt C ({tt[-1].get('year')}), {100 * (b - a) / a:+.2f} %" if a else "", f"Stock de SOC reconstitué 0–30 cm : {a:.2f} Mt C ({tt[0].get('year')}) → {b:.2f} Mt C ({tt[-1].get('year')}), {100 * (b - a) / a:+.2f} %" if a else ""))
    pp = {r.get("period"): r for r in sr_dict_rows(perc)}
    if tag in pp:
        summary.append(T(f"Median change {y0}–{y1}: {sr_num(pp[tag].get('pct_median')):+.2f} % (P10 {sr_num(pp[tag].get('pct_P10')):+.2f} ; P90 {sr_num(pp[tag].get('pct_P90')):+.2f})", f"Variation médiane {y0}–{y1} : {sr_num(pp[tag].get('pct_median')):+.2f} % (P10 {sr_num(pp[tag].get('pct_P10')):+.2f} ; P90 {sr_num(pp[tag].get('pct_P90')):+.2f})"))
    # ---- contrôles
    fr = sr_dict_rows(fac)
    if fr:
        undoc = [r.get("class_name") for r in fr if not str(r.get("source", "")).strip()]
        checks.append((T("Documented SOC factors", "Facteurs SOC documentés"), "PASS" if not undoc else "FAIL", T(f"{len(fr)} class factors, each with a source", f"{len(fr)} facteurs de classe, chacun avec une source") if not undoc else T("no source for: ", "sans source : ") + ", ".join(map(str, undoc))))
        dr = [r.get("factor_type", "") for r in fr]
        if any("draft" in str(x).lower() or "brouillon" in str(x).lower() for x in dr):
            checks.append((T("Factor status", "Statut des facteurs"), "WARN", T("some factors are marked as drafts: replace them by documented regional values", "des facteurs sont marqués brouillon : les remplacer par des valeurs régionales documentées")))
    else:
        checks.append((T("Factors table", "Table des facteurs"), "FAIL", "Factors_Used.csv missing"))
    mf = [abs(sr_num(r.get("mode_minus_fraction_pct"), 0)) for r in sr_dict_rows(mode_frac)]
    if mf:
        checks.append((T("Mode-aggregation bias of LULC on the SOC grid", "Biais d'agrégation (mode) du LULC sur la grille SOC"), "PASS" if max(mf) <= 5 else "WARN", T(f"largest difference between mode and fraction-weighted area: {max(mf):.1f} %", f"écart maximal entre surface « mode » et surface pondérée : {max(mf):.1f} %")))
    q = sr_dict_rows(qa30)
    if q:
        bad = [r for r in q if str(r.get("coherent", "")).strip().lower() not in ("true", "1", "oui", "yes", "ok")]
        checks.append((T("Consistency with the external 30 m transition rasters", "Cohérence avec les rasters de transition 30 m externes"), "PASS" if not bad else "WARN", T(f"{len(q) - len(bad)} of {len(q)} consistent", f"{len(q) - len(bad)} cohérents sur {len(q)}")))
    ne = _ne_total_ha(notest)
    tot_area = sr_num(tt[-1].get("area_analyzed_ha")) if tt else float("nan")
    if tt and ne == ne:
        share = 100 * ne / (ne + tot_area) if (ne + tot_area) else 0
        checks.append((T("Area not estimable (class without documented factor)", "Surface non estimable (classe sans facteur documenté)"), "PASS" if share <= 10 else "WARN", T(f"{ne:,.0f} ha = {share:.1f} % of the study area", f"{ne:,.0f} ha = {share:.1f} % de la zone")))
    dg = [sr_num(r.get("degraded_%")) for r in sr_dict_rows(mth)]
    dg = [x for x in dg if x == x]
    if dg:
        checks.append((T("Sensitivity to the method (aggregation × stock response)", "Sensibilité à la méthode (agrégation × réponse du stock)"), "PASS" if max(dg) - min(dg) <= 5 else "WARN", T(f"degraded share varies by {max(dg) - min(dg):.1f} points between methods", f"la part dégradée varie de {max(dg) - min(dg):.1f} points selon la méthode")))
    fd = [sr_num(r.get("degraded_%")) for r in sr_dict_rows(fal)]
    fd = [x for x in fd if x == x]
    if fd:
        checks.append((T("Sensitivity to the fallow assumption", "Sensibilité à l'hypothèse sur la jachère"), "PASS" if max(fd) - min(fd) <= 5 else "WARN", T(f"degraded share varies by {max(fd) - min(fd):.1f} points", f"la part dégradée varie de {max(fd) - min(fd):.1f} points")))
    _diag = [str(d) for d in globals().get("DIAGNOSTIC_YEARS", [])]
    checks.append((T("SOC baseline year is not a diagnostic (drought) year", "L'année de base du SOC n'est pas une année diagnostique (sécheresse)"), "WARN" if str(y0) in _diag else "PASS",
                   T(f"baseline {y0} is declared a diagnostic year: run the same stage with another baseline and compare (stage 08)", f"la base {y0} est déclarée année diagnostique : refaire l'étape avec une autre base et comparer (étape 08)") if str(y0) in _diag else T(f"baseline {y0}; diagnostic years: {', '.join(_diag) or 'none'}", f"base {y0} ; années diagnostiques : {', '.join(_diag) or 'aucune'}")))
    _all, _used = [int(y) for y in globals().get("LULC_YEARS", years)], [int(y) for y in years]
    _skip = [y for y in _all if y not in _used]
    if _skip:
        checks.append((T("Diagnostic years excluded from the SOC dates", "Années diagnostiques exclues des dates du SOC"), "INFO",
                       T(f"{', '.join(map(str, _skip))} not used (SOC_USE_DIAGNOSTIC_YEARS = False): a transient drought state would neither drive the 20-year response nor remove cells from the analysis; dates used: {', '.join(map(str, _used))}",
                         f"{', '.join(map(str, _skip))} non utilisée(s) (SOC_USE_DIAGNOSTIC_YEARS = False) : un état transitoire de sécheresse ne piloterait pas la réponse sur 20 ans et ne retirerait pas de cellules de l'analyse ; dates utilisées : {', '.join(map(str, _used))}")))
    checks.append((T("Monte Carlo uncertainty", "Incertitude Monte Carlo"), "PASS" if mc else "INFO", T("propagated through the factor ranges (low–high)", "propagée à travers les fourchettes de facteurs (bas–haut)") if mc else T("not run", "non exécutée")))
    maps = []
    for fn, title, cl, kw in ((f"SOC_Class_{tag}.tif", T(f"SOC class {y0}–{y1}", f"Classe SOC {y0}–{y1}"), {-1: ("#d73027", T("Loss", "Perte")), 0: ("#fee08b", T("Stable", "Stable")), 1: ("#1a9850", T("Gain", "Gain"))}, "chg"),
                              (f"SOC_Reconstructed_{y1}.tif", T(f"Reconstructed SOC {y1} (t C/ha)", f"SOC reconstitué {y1} (t C/ha)"), None, "soc")):
        p = os.path.join(dirs[kw], fn)
        png = sr_quicklook(p, os.path.join(out_root, "_temp", fn + ".png"), cl, title=title, nodata=-9999.0 if cl is None else None, label="t C/ha" if cl is None else "")
        if png:
            maps.append((title, png))
    byl = sorted(f for f in os.listdir(stats) if f.startswith("SOC_by_LULC_")) if os.path.isdir(stats) else []
    sections = [
        {"id": "fac", "title": T("Relative SOC factors by class (documented)", "Facteurs relatifs de SOC par classe (documentés)"), "intro": T("The script invents nothing: every class factor must come with its source. Historical SOC is a modelled reconstruction, never an observation.", "Le script n'invente rien : chaque facteur doit avoir sa source. Le SOC historique est une reconstitution modélisée, jamais une observation."), "tables": [(T("Factors used", "Facteurs utilisés"), fac), (T("Area not estimable", "Surface non estimable"), notest)]},
        {"id": "tot", "title": T("Reconstructed SOC stock", "Stock de SOC reconstitué"), "tables": [(T("Total SOC 0–30 cm", "SOC total 0–30 cm"), totals), (T("LULC area: mode vs fraction-weighted", "Surface LULC : mode vs pondérée par fractions"), mode_frac)]},
        {"id": "chg", "title": T("SOC change by period", "Variation du SOC par période"), "tables": [(T("Area by class", "Surfaces par classe"), area), (T("Distribution of the change (%)", "Distribution de la variation (%)"), perc)] + ([(T("By land cover", "Par occupation du sol") + f" ({byl[-1][12:-4]})", rd("stats", byl[-1]))] if byl else [])},
        {"id": "sens", "title": T("Sensitivity and uncertainty", "Sensibilité et incertitude"), "tables": [(T("Method sensitivity", "Sensibilité à la méthode"), mth), (T("Fallow assumption", "Hypothèse sur la jachère"), fal), ("Monte Carlo", mc)]},
        {"id": "maps", "title": T("Maps", "Cartes"), "images": maps},
        {"id": "log", "title": T("Processing log", "Journal du traitement"), "pre": "\n".join(report_lines[-150:])}]
    L = [T("SoilGrids is a single map (ISRIC): historical SOC is a RECONSTRUCTION by class factors applied to LULC change, not a measured stock.", "SoilGrids est une carte unique (ISRIC) : le SOC historique est une RECONSTITUTION par facteurs de classe appliqués aux changements de LULC, pas un stock mesuré."),
         T("SOC only changes when the LULC class changes: LULC classification error (see stage 05B) is transmitted to SOC.", "Le SOC ne change que lorsque la classe LULC change : l'erreur de classification (voir étape 05B) se transmet au SOC."),
         T("The ±threshold on the relative change is analytical, not a global UNCCD rule.", "Le seuil ± de variation relative est analytique, pas une règle UNCCD mondiale."),
         T("The SOC analysis grid (SoilGrids, ~230 m) differs from LULC (30 m) and LPD (MODIS 250 m).", "La grille d'analyse du SOC (SoilGrids, ~230 m) diffère du LULC (30 m) et du LPD (MODIS 250 m).")]
    A = [T("Download SoilGrids organic carbon stock 0–30 cm for the new area and crop it to the study-area boundary.", "Télécharger le stock de carbone organique SoilGrids 0–30 cm de la nouvelle zone et le recadrer sur la limite."),
         T("Fill the factor table for the classes present, with documented regional values (IPCC stock-change factors adapted to the climate and soil of the area); keep low/high for the Monte Carlo.", "Remplir la table des facteurs des classes présentes avec des valeurs régionales documentées (facteurs IPCC adaptés au climat et au sol) ; garder bas/haut pour le Monte Carlo."),
         T("Provide the LULC maps of the new area named LULC_<AREA_TAG>_<year>.tif.", "Fournir les cartes LULC de la nouvelle zone nommées LULC_<AREA_TAG>_<année>.tif."),
         T("Decide how classes without a documented factor (water, sebkha, built-up) are treated and report the area concerned.", "Décider du traitement des classes sans facteur documenté (eau, sebkha, bâti) et rapporter la surface concernée.")]
    R = ["IPCC (2006). Guidelines for National Greenhouse Gas Inventories, Vol. 4, Chapter 5 (Cropland) and Chapter 6 (Grassland).", "IPCC (2019). 2019 Refinement to the 2006 IPCC Guidelines, Vol. 4.", "Poggio, L. et al. (2021). SoilGrids 2.0: producing soil information for the globe with quantified spatial uncertainty. SOIL 7, 217–240.",
         "UNCCD. Good Practice Guidance for SDG Indicator 15.3.1 (version 2) and its Addendum."]
    spec = {"stage": "06", "title": T("Soil organic carbon (SOC) change", "Variation du carbone organique du sol (SOC)"), "subtitle": T("Reconstruction from LULC transitions", "Reconstitution à partir des transitions du LULC"), "lang": lang, "area": area_name, "started": t0, "out_dir": out_root,
            "params": params, "inputs": inputs, "summary": summary, "checks": checks, "sections": sections, "limits": L, "adapt": A, "references": R}
    path = os.path.join(out_root, "Stage_Report_06_SOC.html")
    write_stage_report(path, spec)
    log("[Rapport HTML] " + path)
    return path
def soc_scenarios_report(batch_root, results, years, area_name, lang="en", periods=None, log=print):
    """
    UN SEUL rapport HTML qui compare TOUS les scénarios de facteurs SOC d'un lot (chaque scénario a déjà son propre rapport dans son sous-dossier).
    results : liste de dict {"label", "out_root", "dirs", "factor_path"} (le premier est le scénario PRINCIPAL) ou {"label", "error", ...} pour un scénario en échec.
    periods : balises de périodes à comparer (ex. ["1999_2015", "2015_2025", "1999_2025"]) ; par défaut la période première -> dernière année.
    """
    en = lang == "en"
    T = lambda a, b: a if en else b
    t0 = time.time()
    y0, y1 = int(min(years)), int(max(years))
    full = f"{y0}_{y1}"
    ok_res = [r for r in results if not r.get("error")]
    bad = [r for r in results if r.get("error")]
    if not ok_res:
        raise RuntimeError("Aucun scénario n'a abouti : pas de comparaison possible.")
    main_r = ok_res[0]
    rd = lambda r, k, n: sr_read_csv(os.path.join(r["dirs"][k], n))
    conv = lambda r: "convention" in r["label"].lower()

    def pick(r, per, cls):
        for x in sr_dict_rows(rd(r, "stats", "SOC_Area_Statistics.csv")):
            if x.get("period") == per and x.get("class") == cls:
                return sr_num(x.get("percent"))
        return float("nan")

    tags = [p for p in (periods or []) if any(sr_dict_rows(rd(main_r, "stats", "SOC_Area_Statistics.csv")) and x.get("period") == p for x in sr_dict_rows(rd(main_r, "stats", "SOC_Area_Statistics.csv")))]
    if full not in tags:
        tags.append(full)
    # ---- 1. facteurs
    names = {5: T("Cropland", "Agriculture"), 6: T("Fallow", "Jachère"), 7: T("Forest", "Forêt"), 8: T("Rangeland", "Parcours"), 1: T("Built-up", "Bâti"), 4: T("Bare land", "Sol nu")}
    tb_f = [[T("Scenario", "Scénario")] + [names[c] for c in (5, 6, 7, 8, 1, 4)]]
    for r in ok_res:
        fr = {int(float(x["class_code"])): x for x in sr_dict_rows(rd(r, "qa", "Factors_Used.csv")) if str(x.get("class_code", "")).strip()}
        cells = []
        for c in (5, 6, 7, 8, 1, 4):
            x = fr.get(c)
            if not x or not str(x.get("relative_soc_factor", "")).strip():
                cells.append(T("not estimable", "non estimable"))
            else:
                v, lo, hi = sr_num(x["relative_soc_factor"]), sr_num(x.get("low")), sr_num(x.get("high"))
                cells.append(f"{v:g}" + (f" ({lo:g}–{hi:g})" if lo == lo and hi == hi and (lo != v or hi != v) else "") + (T(" linked", " lié") + f" {x['link_to']}" if str(x.get("link_to", "")).strip() else ""))
        tb_f.append([r["label"] + ("  ★" if r is main_r else "")] + cells)
    # ---- 2. parts par période
    tb_p = [[T("Period", "Période"), T("Scenario", "Scénario"), T("Degraded %", "Dégradé %"), T("Stable %", "Stable %"), T("Improved %", "Amélioré %"), T("Δ degraded vs main (points)", "Δ dégradé vs principal (points)")]]
    spread, rows_csv = {}, [["period", "scenario", "degraded_pct", "stable_pct", "improved_pct", "delta_degraded_vs_main_points", "is_convention_scenario"]]
    for per in tags:
        base = pick(main_r, per, "degraded")
        vals = []
        for r in ok_res:
            d, st, im = pick(r, per, "degraded"), pick(r, per, "stable"), pick(r, per, "improved")
            fmt = lambda v: "" if v != v else f"{v:.2f}"
            dd = "" if (d != d or base != base) else f"{d - base:+.2f}"
            tb_p.append([per.replace("_", "–"), r["label"] + (" ★" if r is main_r else ""), fmt(d), fmt(st), fmt(im), dd])
            rows_csv.append([per, r["label"], fmt(d), fmt(st), fmt(im), dd, "yes" if conv(r) else "no"])
            if d == d and not conv(r):
                vals.append((d, im))
        if vals:
            spread[per] = (min(v[0] for v in vals), max(v[0] for v in vals), min(v[1] for v in vals), max(v[1] for v in vals))
    tb_s = [[T("Period", "Période"), T("Degraded % min", "Dégradé % min"), T("max", "max"), T("spread (points)", "étendue (points)"), T("Improved % min", "Amélioré % min"), T("max", "max")]] + \
           [[per.replace("_", "–"), f"{a:.2f}", f"{b:.2f}", f"{b - a:.2f}", f"{c:.2f}", f"{d:.2f}"] for per, (a, b, c, d) in spread.items()]
    # ---- 3. stocks
    tb_t = [[T("Scenario", "Scénario"), T(f"SOC {y0} (Mt C)", f"SOC {y0} (Mt C)"), T(f"SOC {y1} (Mt C)", f"SOC {y1} (Mt C)"), T("Change (%)", "Variation (%)"), T("Median cell change (%)", "Variation médiane des cellules (%)"), T("Area analysed (ha)", "Surface analysée (ha)"), T("Not estimable (ha)", "Non estimable (ha)")]]
    chg, areas = {}, {}
    for r in ok_res:
        tt = sr_dict_rows(rd(r, "stats", "SOC_Totals_MtC.csv"))
        a0 = next((sr_num(x["total_SOC_Mt_C"]) for x in tt if int(float(x["year"])) == y0), float("nan"))
        a1 = next((sr_num(x["total_SOC_Mt_C"]) for x in tt if int(float(x["year"])) == y1), float("nan"))
        ar = next((sr_num(x.get("area_analyzed_ha")) for x in tt if int(float(x["year"])) == y1), float("nan"))
        ne = _ne_total_ha(rd(r, "stats", "SOC_NotEstimable_Area.csv"))
        med = next((sr_num(x.get("pct_median")) for x in sr_dict_rows(rd(r, "stats", "SOC_Change_Percentiles.csv")) if x.get("period") == full), float("nan"))
        c = (100 * (a1 - a0) / a0) if (a0 == a0 and a0) else float("nan")
        chg[r["label"]], areas[r["label"]] = c, ar
        f2 = lambda v, nd=2: "" if v != v else f"{v:.{nd}f}"
        tb_t.append([r["label"] + (" ★" if r is main_r else ""), f2(a0), f2(a1), (f"{c:+.2f}" if c == c else ""), f2(med), "" if ar != ar else f"{ar:,.0f}", f"{ne:,.0f}"])
    # ---- 4. Monte Carlo
    tb_m = [[T("Scenario", "Scénario"), T("Degraded share P10 / P50 / P90 (%)", "Part dégradée P10 / P50 / P90 (%)"), T("Cells degraded in ≥ 90 % of draws (%)", "Cellules dégradées dans ≥ 90 % des tirages (%)")]]
    for r in ok_res:
        row = next((x for x in sr_dict_rows(rd(r, "unc", "SOC_MonteCarlo_Summary.csv")) if x.get("period") == full), None)
        if row:
            tb_m.append([r["label"], " / ".join(f"{sr_num(row.get(k)):.1f}" for k in ("degraded_share_P10_%", "degraded_share_P50_%", "degraded_share_P90_%")), f"{sr_num(row.get('robust_degraded_cells_%')):.1f}"])
    # ---- contrôles
    checks = [(T("All scenarios completed", "Tous les scénarios ont abouti"), "PASS" if not bad else "FAIL", T(f"{len(ok_res)} scenarios", f"{len(ok_res)} scénarios") if not bad else "; ".join(f"{b['label']}: {str(b['error'])[:120]}" for b in bad))]
    core = [r for r in ok_res if not conv(r)]
    if full in spread:
        a, b, _c, _d = spread[full]
        checks.append((T(f"Spread of the degraded share across the factor scenarios ({y0}–{y1})", f"Étendue de la part dégradée entre les scénarios de facteurs ({y0}–{y1})"), "PASS" if (b - a) <= 5 else "WARN",
                       T(f"{a:.1f}–{b:.1f} % = {b - a:.1f} points: report this RANGE, not one number", f"{a:.1f}–{b:.1f} % = {b - a:.1f} points : rapporter cette FOURCHETTE, pas un seul chiffre")))
    core_chg = {k: v for k, v in chg.items() if v == v and "convention" not in k.lower()}
    if core_chg:
        big = {k: v for k, v in core_chg.items() if abs(v) >= 1.0}
        signs = {("+" if v > 0 else "-") for v in big.values()}
        mx = max(abs(v) for v in core_chg.values())
        if not big:
            checks.append((T("Net change of the total SOC stock across the scenarios", "Variation nette du stock total de SOC selon les scénarios"), "PASS",
                           T(f"within ±1 % in every scenario (largest {mx:.2f} %): no detectable change of the total stock; the sign is not meaningful at this magnitude", f"dans ±1 % pour tous les scénarios (maximum {mx:.2f} %) : aucun changement détectable du stock total ; le signe n'a pas de sens à cette amplitude")))
        else:
            checks.append((T("Sign of the net SOC change agrees across the scenarios", "Le signe de la variation nette du SOC concorde entre les scénarios"), "PASS" if len(signs) == 1 and len(big) == len(core_chg) else ("PASS" if len(signs) == 1 else "WARN"),
                           T("same direction in every scenario where the change is at least 1 %", "même sens dans tous les scénarios où la variation atteint au moins 1 %") if len(signs) == 1 else T("the conclusion (gain or loss) DEPENDS on the factors", "la conclusion (gain ou perte) DÉPEND des facteurs")))
    ar_core = [v for k, v in areas.items() if v == v and "convention" not in k.lower()]
    if len(ar_core) > 1:
        gap = 100 * (max(ar_core) - min(ar_core)) / max(ar_core)
        checks.append((T("Same area analysed in the factor scenarios", "Même surface analysée dans les scénarios de facteurs"), "PASS" if gap <= 1 else "WARN", f"{gap:.2f} %"))
    if any(conv(r) for r in ok_res):
        checks.append((T("Convention scenario (full coverage)", "Scénario de convention (couverture complète)"), "INFO", T("shown for coverage only: it creates spurious gains and losses (urbanisation counted as a gain, degradation to bare soil invisible); never use it for conclusions or with a drought year as baseline", "montré pour la couverture seulement : il crée des gains et des pertes fictifs (urbanisation comptée comme gain, dégradation en sol nu invisible) ; ne jamais l'utiliser pour conclure ni avec une année de sécheresse comme base")))
    # ---- figure
    png = None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        labs = [r["label"] for r in ok_res]
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
        x = list(range(len(labs)))
        axes[0].bar([i - 0.2 for i in x], [pick(r, full, "degraded") for r in ok_res], 0.4, color="#c62828", label=T("Degraded", "Dégradé"))
        axes[0].bar([i + 0.2 for i in x], [pick(r, full, "improved") for r in ok_res], 0.4, color="#2e7d32", label=T("Improved", "Amélioré"))
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(labs, rotation=30, ha="right", fontsize=8)
        axes[0].set_ylabel("%")
        axes[0].set_title(T(f"Share of the analysed area, {y0}–{y1}", f"Part de la surface analysée, {y0}–{y1}"))
        axes[0].legend(frameon=False, fontsize=8)
        axes[1].bar(x, [chg[l] for l in labs], color=["#1565c0" if "convention" not in l.lower() else "#b0bec5" for l in labs])
        axes[1].axhline(0, color="black", linewidth=0.8)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(labs, rotation=30, ha="right", fontsize=8)
        axes[1].set_ylabel("%")
        axes[1].set_title(T("Net change of the total SOC stock", "Variation nette du stock total de SOC"))
        png = os.path.join(batch_root, "_temp", "scenarios.png")
        os.makedirs(os.path.dirname(png), exist_ok=True)
        fig.savefig(png, dpi=110, bbox_inches="tight", facecolor="white")
        plt.close(fig)
    except Exception:
        png = None
    links = "\n".join(f"{r['label']}  ->  {os.path.relpath(os.path.join(r['out_root'], 'Stage_Report_06_SOC.html'), batch_root).replace(os.sep, '/')}" for r in ok_res)
    with open(os.path.join(batch_root, "SOC_Scenario_Comparison.csv"), "w", newline="", encoding="utf-8-sig") as f:
        import csv as _csv
        _csv.writer(f, delimiter=";").writerows(rows_csv)
    summary = [T(f"{len(ok_res)} factor scenarios compared; main scenario = {main_r['label']}", f"{len(ok_res)} scénarios de facteurs comparés ; scénario principal = {main_r['label']}")]
    if full in spread:
        a, b, c_, d_ = spread[full]
        summary.append(T(f"{y0}–{y1}: degraded share {a:.1f}–{b:.1f} % and improved share {c_:.1f}–{d_:.1f} % across the factor scenarios (the convention scenario excluded)", f"{y0}–{y1} : part dégradée {a:.1f}–{b:.1f} % et part améliorée {c_:.1f}–{d_:.1f} % selon les scénarios de facteurs (scénario de convention exclu)"))
    sections = [{"id": "fac", "title": T("Factors of each scenario", "Facteurs de chaque scénario"), "intro": T("★ = main scenario. The scenarios only differ by the relative factors; the SOC reference, the maps and the thresholds are the same.", "★ = scénario principal. Les scénarios ne diffèrent que par les facteurs relatifs ; le SOC de référence, les cartes et les seuils sont les mêmes."), "tables": [("", tb_f)]},
                {"id": "per", "title": T("Degraded / stable / improved share by period", "Parts dégradée / stable / améliorée par période"), "tables": [("", tb_p), (T("Range across the factor scenarios", "Fourchette entre les scénarios de facteurs"), tb_s)]},
                {"id": "stock", "title": T("Total SOC stock and area analysed", "Stock total de SOC et surface analysée"), "tables": [("", tb_t)], "images": [(T("Comparison of the scenarios", "Comparaison des scénarios"), png)]},
                {"id": "mc", "title": T("Monte Carlo uncertainty within each scenario", "Incertitude Monte Carlo dans chaque scénario"), "tables": [("", tb_m)]},
                {"id": "rep", "title": T("Detailed report of each scenario", "Rapport détaillé de chaque scénario"), "pre": links}]
    L = [T("The scenarios are a METHODOLOGICAL sensitivity (choice of factors), not a statistical confidence interval: report the range between them and the Monte Carlo interval inside each.", "Les scénarios sont une sensibilité MÉTHODOLOGIQUE (choix des facteurs), pas un intervalle de confiance statistique : rapporter la fourchette entre eux et l'intervalle Monte Carlo dans chacun."),
         T("SOC is a reconstruction with relative class factors applied to land-cover change; it is not a measured stock.", "Le SOC est une reconstitution par facteurs relatifs de classe appliqués aux changements de couverture ; ce n'est pas un stock mesuré."),
         T("The factor tables come from IPCC Tier 1 defaults (global, by climate zone); a Tier 2 factor from regional studies would reduce the spread.", "Les tables de facteurs viennent des valeurs par défaut du GIEC niveau 1 (globales, par zone climatique) ; un facteur de niveau 2 issu d'études régionales réduirait l'étendue.")]
    A = [T("Select the main factor table, then add the sensitivity tables in the optional dialog 5b/5: each is computed in its own sub-folder.", "Choisir la table de facteurs principale, puis ajouter les tables de sensibilité dans la boîte facultative 5b/5 : chacune est calculée dans son sous-dossier."),
         T("Keep the same maps, thresholds and SOC reference for all the scenarios of a batch.", "Garder les mêmes cartes, seuils et SOC de référence pour tous les scénarios d'un lot.")]
    spec = {"stage": "06", "title": T("SOC — comparison of the factor scenarios", "SOC — comparaison des scénarios de facteurs"), "subtitle": T("One report for all the factor tables", "Un seul rapport pour toutes les tables de facteurs"), "lang": lang, "area": area_name, "started": t0, "out_dir": batch_root,
            "params": {"Main scenario": main_r["label"], "Scenarios": ", ".join(r["label"] for r in results), "Periods compared": ", ".join(tags)}, "inputs": [{"label": "Factor table — " + r["label"], "path": r.get("factor_path")} for r in results if r.get("factor_path")],
            "summary": summary, "checks": checks, "sections": sections, "limits": L, "adapt": A, "references": ["IPCC (2019). 2019 Refinement to the 2006 IPCC Guidelines for National Greenhouse Gas Inventories, Vol. 4, Chapters 5 and 6.", "Poggio, L. et al. (2021). SoilGrids 2.0. SOIL 7, 217–240."]}
    path = os.path.join(batch_root, "Stage_Report_06_SOC_Scenarios.html")
    write_stage_report(path, spec)
    import shutil
    shutil.rmtree(os.path.join(batch_root, "_temp"), ignore_errors=True)
    log("[Rapport HTML] " + path)
    return path
# <<< STAGE_BUILDER_END
import re
import csv
import math
import time
import warnings
import traceback

import numpy as np

from osgeo import gdal, osr
try:
    from osgeo import ogr
except ImportError:      # nécessaire seulement si SoilGrids est en coordonnées géographiques
    ogr = None

from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox, QApplication, QInputDialog
from qgis.core import QgsRasterLayer, QgsProject


# ============================================================================
# 1. CONSTANTES ET OUTILS REPRIS DE V3 ET DU SCRIPT LPD (code déjà testé)
# ============================================================================


YEARS = [y for y in LULC_YEARS if SOC_USE_DIAGNOSTIC_YEARS or str(y) not in [str(d) for d in DIAGNOSTIC_YEARS]]      # dates de la RECONSTITUTION du SOC : l'année diagnostique (sécheresse) en est exclue par défaut
OVERALL_PAIRS = [(a, b) for a, b in EXTRA_SOC_PAIRS if a in YEARS and b in YEARS]      # périodes non consécutives calculées en plus (base t0 -> 2015, suivi 2015 -> fin, période globale)
CLASS_CODES = list(range(1, 9))
DEFAULT_CLASSES = {
    1: "Bâti",
    2: "Eau",
    3: "Sebkha",
    4: "Sol nu",
    5: "Agriculture",
    6: "Jachère",
    7: "Forêt",
    8: "Parcours"
}
GEE_SHARD_RE = re.compile(r"-\d{10}-\d{10}(\.[A-Za-z]+)$")
_EXCLUDED_LULC_WORDS = (
    "change", "transition", "stagemask", "canvas", "preview",
    "confidence", "qa_", "area", "lpd_", "sebkha_water_state",
    "uncertainty", "publication", "visualedit", "independentpreview"
)
LULC_MIN_ACCEPT_SCORE = -300
LULC_VALIDATION_SAMPLE_PX = 1500
FILE_NOTES = []
YEAR_RE = re.compile(r"(?<!\d)(19[89]\d|20[0-4]\d)(?!\d)")
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
NODATA_FLOAT = -9999.0


try:
    _QMB_YES, _QMB_NO = QMessageBox.Yes, QMessageBox.No
except AttributeError:
    _QMB_YES = QMessageBox.StandardButton.Yes
    _QMB_NO = QMessageBox.StandardButton.No



# ----- fonctions (V3 / LPD) -----


def ensure_dir(folder):
    os.makedirs(folder, exist_ok=True)


def open_ds(path):
    ds = gdal.Open(path, gdal.GA_ReadOnly)
    if ds is None:
        raise RuntimeError("Impossible d'ouvrir le raster : {}".format(path))
    return ds


def raster_info(path):
    ds = open_ds(path)
    b = ds.GetRasterBand(1)
    gt = ds.GetGeoTransform()
    return {
        "cols": ds.RasterXSize,
        "rows": ds.RasterYSize,
        "bands": ds.RasterCount,
        "gt": gt,
        "proj": ds.GetProjection(),
        "nodata": b.GetNoDataValue(),
        "dtype": gdal.GetDataTypeName(b.DataType),
        "xres": abs(float(gt[1])),
        "yres": abs(float(gt[5])),
        "xmin": float(gt[0]),
        "ymax": float(gt[3]),
        "xmax": float(gt[0] + ds.RasterXSize * gt[1] + ds.RasterYSize * gt[2]),
        "ymin": float(gt[3] + ds.RasterXSize * gt[4] + ds.RasterYSize * gt[5]),
    }


def projection_epsg(path):
    wkt = open_ds(path).GetProjection()
    if not wkt:
        return None
    srs = osr.SpatialReference()
    srs.ImportFromWkt(wkt)
    auth = srs.GetAuthorityCode(None)
    return int(auth) if auth else None


def normalized_gt(gt):
    return tuple(round(float(v), 10) for v in gt)


def grid_signature(path):
    ds = open_ds(path)
    return (
        ds.RasterXSize,
        ds.RasterYSize,
        normalized_gt(ds.GetGeoTransform()),
        ds.GetProjection().strip()
    )


def assert_same_grid(path_a, path_b, label_a="Raster A", label_b="Raster B"):
    sa = grid_signature(path_a)
    sb = grid_signature(path_b)
    if sa != sb:
        ia = raster_info(path_a)
        ib = raster_info(path_b)
        raise RuntimeError(
            "GRILLES INCOMPATIBLES.\n\n"
            "{} : {} x {} | résolution {:.8g} x {:.8g} | EPSG={}\n"
            "{} : {} x {} | résolution {:.8g} x {:.8g} | EPSG={}\n\n"
            "Aucune opération NumPy ne peut être effectuée avant harmonisation.".format(
                label_a, ia["cols"], ia["rows"], ia["xres"], ia["yres"],
                projection_epsg(path_a),
                label_b, ib["cols"], ib["rows"], ib["xres"], ib["yres"],
                projection_epsg(path_b)
            )
        )


def write_geotiff(path, array, gt, proj, dtype=gdal.GDT_Float32,
                  nodata=None, compress="DEFLATE"):
    rows, cols = array.shape
    drv = gdal.GetDriverByName("GTiff")
    ds = drv.Create(
        path, cols, rows, 1, dtype,
        options=[
            "TILED=YES",
            "COMPRESS={}".format(compress),
            "BIGTIFF=IF_SAFER"
        ]
    )
    if ds is None:
        raise RuntimeError("Création impossible : {}".format(path))
    ds.SetGeoTransform(gt)
    ds.SetProjection(proj)
    b = ds.GetRasterBand(1)
    if nodata is not None:
        b.SetNoDataValue(nodata)
    b.WriteArray(array)
    b.FlushCache()
    ds.FlushCache()
    ds = None
    return path


def vector_info(path):
    v = ogr.Open(path)
    if v is None:
        raise RuntimeError("Impossible d'ouvrir la limite : {}".format(path))
    lyr = v.GetLayer(0)
    srs = lyr.GetSpatialRef()
    return {
        "epsg": int(srs.GetAuthorityCode(None)) if srs and srs.GetAuthorityCode(None) else None
    }


def _utm_epsg_for_lonlat(lon, lat):
    """EPSG UTM approprié (WGS84) pour une longitude/latitude donnée."""
    zone = int(math.floor((lon + 180.0) / 6.0) + 1)
    return (32600 if lat >= 0 else 32700) + zone


def _vector_centroid_lonlat(mask_vector):
    """Centroïde de la couche de limite, reprojeté en EPSG:4326 (lon/lat)."""
    v = ogr.Open(mask_vector)
    lyr = v.GetLayer(0)
    src_srs = lyr.GetSpatialRef()
    extent = lyr.GetExtent()  # (minx, maxx, miny, maxy)
    cx = (extent[0] + extent[1]) / 2.0
    cy = (extent[2] + extent[3]) / 2.0
    if src_srs is None:
        return cx, cy  # déjà supposé lon/lat
    wgs84 = osr.SpatialReference()
    wgs84.ImportFromEPSG(4326)
    if hasattr(osr, "OAMS_TRADITIONAL_GIS_ORDER"):
        wgs84.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        src_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    transform = osr.CoordinateTransformation(src_srs, wgs84)
    lon, lat, _ = transform.TransformPoint(cx, cy)
    return lon, lat


def clip_soc_reference(src_soc, mask_vector, out_soc):
    """
    Crée la grille SOC de référence.
    Le raster source conserve sa résolution; le crop est aligné sur les pixels
    de la source. Aucun resampling catégoriel n'est effectué.

    BUGFIX (« La grille SOC est en coordonnées géographiques ») : SoilGrids
    est très souvent distribué/recadré en coordonnées géographiques (degrés),
    ce qui rendait tout calcul de surface en hectares impossible en aval
    (pixel_area_ha refusait alors l'exécution). Au lieu de simplement refuser,
    la grille est maintenant automatiquement REPROJETÉE vers l'UTM WGS84
    approprié (calculé depuis le centroïde de la zone d'étude) si et
    seulement si la source est en coordonnées géographiques -- SoilGrids
    reste la grille de référence, seule sa projection change, sa résolution
    native (en degrés) est convertie en mètres à la latitude de la zone pour
    ne pas changer le niveau de détail. Si la source est déjà projetée,
    rien ne change par rapport au comportement précédent (son CRS/résolution
    sont conservés tels quels).
    """
    if not os.path.exists(src_soc):
        raise RuntimeError("SoilGrids introuvable : {}".format(src_soc))
    if not os.path.exists(mask_vector):
        raise RuntimeError("Limite d'étude introuvable : {}".format(mask_vector))

    src = open_ds(src_soc)
    src_proj = src.GetProjection()
    src_gt = src.GetGeoTransform()
    if not src_proj:
        raise RuntimeError("SoilGrids ne contient pas de projection.")

    src_srs = osr.SpatialReference()
    src_srs.ImportFromWkt(src_proj)

    if src_srs.IsProjected():
        dst_srs_wkt = src_proj
        x_res = abs(src_gt[1])
        y_res = abs(src_gt[5])
    else:
        lon, lat = _vector_centroid_lonlat(mask_vector)
        target_epsg = _utm_epsg_for_lonlat(lon, lat)
        dst_srs = osr.SpatialReference()
        dst_srs.ImportFromEPSG(target_epsg)
        dst_srs_wkt = dst_srs.ExportToWkt()
        # Conversion approchée degrés -> mètres à la latitude de la zone,
        # pour conserver la résolution native de la source (pas un choix
        # arbitraire type 250 m, au cas où la source ait déjà été rééchantillonnée).
        deg_to_m_lat = 111320.0
        deg_to_m_lon = 111320.0 * math.cos(math.radians(lat))
        x_res = abs(src_gt[1]) * deg_to_m_lon
        y_res = abs(src_gt[5]) * deg_to_m_lat
        print(
            "AVIS : SOC source en coordonnées géographiques -> reprojection "
            "automatique vers EPSG:{} (UTM), résolution ~{:.1f} x {:.1f} m.".format(
                target_epsg, x_res, y_res
            )
        )

    # Warp avec cropToCutline ; resampling bilinéaire car le SOC est une
    # variable CONTINUE (jamais de plus-proche-voisin/mode ici, réservés aux
    # données catégorielles comme le LULC).
    opts = gdal.WarpOptions(
        format="GTiff",
        cutlineDSName=mask_vector,
        cropToCutline=True,
        dstSRS=dst_srs_wkt,
        xRes=x_res,
        yRes=y_res,
        targetAlignedPixels=True,
        # Plus-proche-voisin suffit pour un simple découpage sans changement
        # de projection (pixels déjà alignés) ; bilinéaire dès qu'une vraie
        # reprojection (géographique -> UTM) a lieu, car le SOC est continu.
        resampleAlg=gdal.GRA_NearestNeighbour if src_srs.IsProjected() else gdal.GRA_Bilinear,
        srcNodata=src.GetRasterBand(1).GetNoDataValue(),
        dstNodata=-9999.0,
        multithread=True,
        creationOptions=[
            "TILED=YES", "COMPRESS=DEFLATE", "BIGTIFF=IF_SAFER"
        ]
    )
    out = gdal.Warp(out_soc, src_soc, options=opts)
    if out is None:
        raise RuntimeError("Échec du découpage SoilGrids.")
    out = None
    return out_soc


def warp_lulc_exact(src_lulc, ref_soc, out_lulc):
    """
    LULC -> grille SOC exacte.
    La grille de sortie est définie par :
      - projection SOC
      - emprise SOC
      - largeur/hauteur SOC
      - géotransform SOC
    Resampling MODE pour données catégorielles.
    """
    ref = open_ds(ref_soc)
    gt = ref.GetGeoTransform()
    cols = ref.RasterXSize
    rows = ref.RasterYSize
    proj = ref.GetProjection()

    # Pour les grilles north-up classiques, outputBounds est calculé
    # directement depuis le GeoTransform de référence.
    if abs(gt[2]) > 1e-12 or abs(gt[4]) > 1e-12:
        raise RuntimeError(
            "La grille SOC est tournée/rotée. Cette version attend une grille north-up."
        )

    minx = gt[0]
    maxy = gt[3]
    maxx = gt[0] + cols * gt[1]
    miny = gt[3] + rows * gt[5]

    src = open_ds(src_lulc)
    src_nd = src.GetRasterBand(1).GetNoDataValue()

    opts = gdal.WarpOptions(
        format="GTiff",
        outputBounds=(minx, miny, maxx, maxy),
        width=cols,
        height=rows,
        dstSRS=proj,
        resampleAlg=gdal.GRA_Mode,
        srcNodata=src_nd if src_nd is not None else 0,
        dstNodata=0,
        multithread=True,
        creationOptions=[
            "TILED=YES", "COMPRESS=DEFLATE", "BIGTIFF=IF_SAFER"
        ]
    )
    out = gdal.Warp(out_lulc, src_lulc, options=opts)
    if out is None:
        raise RuntimeError("Échec de l'harmonisation LULC : {}".format(src_lulc))
    out = None

    # Contrôle strict
    assert_same_grid(out_lulc, ref_soc, "LULC harmonisée", "SOC référence")
    return out_lulc


def read_array(path, dtype=None):
    ds = open_ds(path)
    arr = ds.GetRasterBand(1).ReadAsArray()
    if dtype is not None:
        arr = arr.astype(dtype)
    return ds, arr


def valid_mask(arr, nodata):
    m = np.isfinite(arr)
    if nodata is not None:
        m &= (arr != nodata)
    return m


def pixel_area_ha_path(path):
    ds = open_ds(path)
    gt = ds.GetGeoTransform()
    proj = ds.GetProjection()
    srs = osr.SpatialReference()
    srs.ImportFromWkt(proj)

    if srs.IsProjected():
        return abs(gt[1] * gt[5]) / 10000.0

    raise RuntimeError(
        "La grille SOC est en coordonnées géographiques. "
        "Pour les surfaces en hectares, utilisez une grille SOC projetée."
    )


def class_area_stats(lulc_path, class_names):
    ds = open_ds(lulc_path)
    arr = ds.GetRasterBand(1).ReadAsArray()
    pxha = pixel_area_ha_path(lulc_path)
    out = []
    for c in CLASS_CODES:
        n = int(np.count_nonzero(arr == c))
        out.append((c, class_names[c], n, n * pxha))
    return out


def transition_matrix(lulc_a, lulc_b):
    assert_same_grid(lulc_a, lulc_b, "LULC A", "LULC B")
    _, a = read_array(lulc_a, np.uint16)
    _, b = read_array(lulc_b, np.uint16)
    if a.shape != b.shape:
        raise RuntimeError("Shapes transition incompatibles.")
    valid = (a > 0) & (b > 0)
    mat = np.zeros((len(CLASS_CODES), len(CLASS_CODES)), dtype=np.int64)
    for i, fr in enumerate(CLASS_CODES):
        for j, to in enumerate(CLASS_CODES):
            mat[i, j] = int(np.count_nonzero(valid & (a == fr) & (b == to)))
    return mat


def write_transition_matrix_csv(path, matrix, class_names, from_year, to_year, pxha):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Transition", from_year, "vers", to_year])
        w.writerow(["Unité", "pixels", "hectares"])
        w.writerow(["Classe départ", "Classe arrivée", "Pixels", "ha"])
        for i, fr in enumerate(CLASS_CODES):
            for j, to in enumerate(CLASS_CODES):
                n = int(matrix[i, j])
                if n:
                    w.writerow([
                        class_names[fr],
                        class_names[to],
                        n,
                        n * pxha
                    ])


def create_transition(lulc_a, lulc_b, out_path):
    assert_same_grid(lulc_a, lulc_b, "LULC année A", "LULC année B")
    dsa, a = read_array(lulc_a, np.uint16)
    _, b = read_array(lulc_b, np.uint16)
    if a.shape != b.shape:
        raise RuntimeError("Shapes différentes après harmonisation.")
    valid = (a > 0) & (b > 0)
    tr = np.zeros(a.shape, dtype=np.uint16)
    tr[valid] = a[valid] * 10 + b[valid]
    return write_geotiff(
        out_path, tr, dsa.GetGeoTransform(), dsa.GetProjection(),
        gdal.GDT_UInt16, 0
    )


def validate_lulc_classes(path, year):
    """
    QA/QC (suite à revue méthodologique) : vérifie que le raster LULC ne
    contient AUCUN code en dehors de CLASS_CODES (1-8). Jusqu'ici, un code
    inattendu (ex: 9, ou 0 utilisé comme vraie classe plutôt que NoData)
    passait inaperçu -- seul load_factors_csv ignorait silencieusement
    (via `continue`) les lignes de facteurs hors 1-8, mais rien ne
    contrôlait les rasters LULC eux-mêmes. Exactement le même type d'erreur
    silencieuse que la permutation 4/7/8 précédemment corrigée.
    Lève une RuntimeError explicite plutôt que de laisser des surfaces/
    transitions incomplètes se calculer sans avertissement.
    """
    ds = open_ds(path)
    arr = ds.GetRasterBand(1).ReadAsArray()
    valid = arr[arr > 0]

    if valid.size == 0:
        raise RuntimeError(
            "LULC {} : aucune classe valide (tout est <= 0) dans {}.".format(year, path)
        )

    unique = sorted(int(c) for c in np.unique(valid))
    unexpected = [c for c in unique if c not in CLASS_CODES]

    if unexpected:
        raise RuntimeError(
            "LULC {} ({}) contient des codes inconnus : {}.\n"
            "Codes autorisés (CLASS_CODES) : {}.\n"
            "Corrigez le raster ou mettez à jour CLASS_CODES/DEFAULT_CLASSES "
            "avant de poursuivre.".format(year, path, unexpected, CLASS_CODES)
        )

    return unique


def external_transition_qa(path, original_a, original_b):
    dtr = open_ds(path)
    da = open_ds(original_a)
    db = open_ds(original_b)

    tr = dtr.GetRasterBand(1).ReadAsArray().astype(np.uint16)
    a = da.GetRasterBand(1).ReadAsArray().astype(np.uint16)
    b = db.GetRasterBand(1).ReadAsArray().astype(np.uint16)

    if tr.shape != a.shape or tr.shape != b.shape:
        return False, "Dimensions incompatibles"

    expected = np.zeros(a.shape, dtype=np.uint16)
    valid = (a > 0) & (b > 0)
    expected[valid] = a[valid] * 10 + b[valid]
    diff = int(np.count_nonzero(tr != expected))
    if diff == 0:
        return True, "100 % cohérent"
    return False, "Pixels différents : {}".format(diff)


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
    Auto-detect the six FINAL LULC rasters.
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


def resolve_lulc_files(lulc_folder):
    """Les six cartes LULC : détection automatique, sinon sélection manuelle."""
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


def choose_directory(title, start=""):
    path = QFileDialog.getExistingDirectory(None, title, start)
    if not path:
        raise RuntimeError("Opération annulée.")
    return path


def ask_yes_no(title, text):
    reply = QMessageBox.question(None, title, text, _QMB_YES | _QMB_NO)
    return reply == _QMB_YES


# ============================================================================
# 3. PARAMÈTRES V4
# ============================================================================

MIN_COVER = 0.50                  # part minimale d'une cellule SOC couverte par des pixels LULC valides
EQUILIBRIUM_YEARS = 20            # durée d'atteinte du nouvel équilibre (GIEC : 20 ans par défaut)
DEFAULT_THRESHOLD_PCT = 10.0      # seuil ANALYTIQUE (pas une règle UNCCD mondiale)
DEFAULT_MC_DRAWS = 300
SOC_SANITY_MEDIAN_MAX = 200.0     # t C/ha : au-delà, l'unité est probablement x10 (valeurs brutes SoilGrids)
ALLOWED_FACTOR_TYPES = ("measured", "literature", "ipcc", "expert")
ALLOWED_CONFIDENCE = ("high", "medium", "low")
PLACEHOLDER_SOURCES = ("a renseigner", "à renseigner", "documenter la source", "todo", "tbd", "?")
NODATA_SOC = -9999.0
UNDOC_TOLERANCE = 0.10            # part max. de classes SANS facteur documenté tolérée dans une cellule (au-delà : non estimable)


# ============================================================================
# 4. LOGIQUE PURE (NumPy) — facteurs, indice d'état, reconstruction, incertitude
# ============================================================================

def write_factor_template(path):
    """Modèle de facteurs PAR CLASSE : aucune valeur n'est pré-remplie (aucun facteur inventé)."""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["class_code", "class_name", "relative_soc_factor", "low", "high",
                    "factor_type", "confidence", "source", "comment", "link_to"])
        general = ("relative_soc_factor = stock de C du sol (0-30 cm) de cette classe sur une échelle COMMUNE à toutes les "
                   "classes (ex. FLU x FMG x FI du GIEC pour le climat et le sol de la zone, ou stock mesuré / stock de "
                   "référence). Seuls les RAPPORTS entre classes comptent. low/high = bornes d'incertitude (facultatif). "
                   "factor_type : measured | literature | ipcc | expert. confidence : high | medium | low. "
                   "source : référence précise (tableau, page, année). Laisser VIDE si aucun facteur documenté n'existe "
                   "(la classe sera alors traitée comme non estimable ou le calcul refusé, selon votre choix). "
                   "link_to (facultatif) : code d'une AUTRE classe dont cette classe partage le facteur ET les tirages "
                   "Monte-Carlo (ex. jachère de rotation = même système que Cropland) ; relative_soc_factor reste alors vide, "
                   "mais la source (justification) est obligatoire.")
        fallow = (" JACHÈRE (6) : en rotation céréalière elle est souvent pâturée. Les lignes directrices du GIEC "
                  "(2006, vol. 4, chap. 5, tableau 5.5, et Raffinement 2019 - À VÉRIFIER dans le tableau) distinguent des "
                  "catégories de terres cultivées (ex. culture de longue durée, terre mise en jachère de moins de 20 ans). "
                  "Choisissez, JUSTIFIEZ et citez ; ne copiez aucune valeur sans vérifier son applicabilité. Le script calcule "
                  "aussi, sans rien inventer, des scénarios où la jachère est assimilée à Cropland (5) ou à Rangeland (8).")
        for c in CLASS_CODES:
            w.writerow([c, DEFAULT_CLASSES[c], "", "", "", "", "", "", general + (fallow if c == 6 else ""), ""])
    return path


def dict_rows_any_delimiter(f):
    """Lignes d'un CSV en dictionnaires ; le séparateur (virgule ou point-virgule, selon la langue d'Excel) est reconnu sur la ligne d'en-tête."""
    text = f.read()
    first = text.split("\n", 1)[0]
    delim = ";" if first.count(";") > first.count(",") else ","
    return list(csv.DictReader(text.splitlines(), delimiter=delim))


def read_factor_table(path, observed_codes, require_all=True):
    """
    Lit et VALIDE la table de facteurs par classe. Refuse toute classe observée sans facteur documenté.
    Renvoie {code: {factor, low, high, type, confidence, source}}.
    """
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = dict_rows_any_delimiter(f)
    need = {"class_code", "relative_soc_factor", "factor_type", "source"}
    fields = set(rows[0].keys()) if rows else set()
    if not need.issubset(fields):
        raise RuntimeError(
            "La table de facteurs doit contenir les colonnes : class_code, relative_soc_factor, factor_type, source "
            "(+ low, high, confidence). Colonnes trouvées : {}.\nUtilisez le modèle généré par le script.".format(sorted(fields)))
    table, problems, linked = {}, [], []
    for r in rows:
        try:
            code = int(str(r["class_code"]).strip())
        except ValueError:
            continue
        if code not in CLASS_CODES:
            continue
        txt = (r.get("relative_soc_factor") or "").strip().replace(",", ".")
        link_txt = (r.get("link_to") or "").strip()
        if link_txt:
            try:
                target = int(link_txt)
            except ValueError:
                problems.append("classe {} : link_to '{}' n'est pas un code de classe".format(code, link_txt))
                continue
            if txt:
                problems.append("classe {} : renseignez SOIT relative_soc_factor, SOIT link_to (pas les deux)".format(code))
                continue
            lsrc = (r.get("source") or "").strip()
            if not lsrc or lsrc.lower() in PLACEHOLDER_SOURCES:
                problems.append("classe {} : link_to exige une SOURCE (justification de l'assimilation à la classe {})".format(code, target))
                continue
            if target == code or target not in CLASS_CODES:
                problems.append("classe {} : link_to {} invalide".format(code, target))
                continue
            linked.append((code, target, lsrc))
            continue
        if not txt:
            continue                                        # classe sans facteur : jugée plus bas selon les classes observées
        try:
            fac = float(txt)
        except ValueError:
            problems.append("classe {} : facteur non numérique '{}'".format(code, txt))
            continue
        if not (np.isfinite(fac) and fac > 0):
            problems.append("classe {} : facteur doit être > 0".format(code))
            continue
        src = (r.get("source") or "").strip()
        if not src or src.lower() in PLACEHOLDER_SOURCES:
            problems.append("classe {} : SOURCE manquante ou « à renseigner » (un facteur non documenté n'est pas accepté)".format(code))
            continue
        ftype = (r.get("factor_type") or "").strip().lower()
        if ftype not in ALLOWED_FACTOR_TYPES:
            problems.append("classe {} : factor_type '{}' invalide (attendu : {})".format(code, ftype, "|".join(ALLOWED_FACTOR_TYPES)))
            continue
        try:
            low = float((r.get("low") or "").strip().replace(",", ".")) if (r.get("low") or "").strip() else fac
            high = float((r.get("high") or "").strip().replace(",", ".")) if (r.get("high") or "").strip() else fac
        except ValueError:
            problems.append("classe {} : bornes low/high non numériques".format(code))
            continue
        if not (0 < low <= fac <= high):
            problems.append("classe {} : il faut 0 < low <= facteur <= high (low={}, facteur={}, high={})".format(code, low, fac, high))
            continue
        conf = (r.get("confidence") or "").strip().lower()
        table[code] = {"factor": fac, "low": low, "high": high, "type": ftype,
                       "confidence": conf if conf in ALLOWED_CONFIDENCE else "not stated", "source": src, "link_to": None}
    for code, target, lsrc in linked:
        if target not in table:
            problems.append("classe {} : link_to {} pointe vers une classe sans facteur documenté propre (pas de chaînage)".format(code, target))
        else:
            t = table[target]
            table[code] = {"factor": t["factor"], "low": t["low"], "high": t["high"], "type": t["type"],
                           "confidence": t["confidence"], "source": lsrc, "link_to": target}
    missing = sorted(c for c in observed_codes if c not in table)
    if missing and require_all:
        problems.append("facteur documenté manquant pour les classes observées : {}".format(
            ", ".join("{} ({})".format(c, DEFAULT_CLASSES[c]) for c in missing)))
    if not table and not problems:
        problems.append("aucune classe n'a de facteur documenté")
    if problems:
        raise RuntimeError("TABLE DE FACTEURS REFUSÉE :\n  - " + "\n  - ".join(problems))
    return table


def factor_vector(table, key="factor"):
    """Vecteur (8,) indexé par CLASS_CODES ; classes sans facteur = NaN."""
    return np.array([table[c][key] if c in table else np.nan for c in CLASS_CODES], dtype=np.float64)


def state_index(F, s):
    """
    F : (8, lignes, colonnes) fractions de chaque classe (somme = 1 sur les cellules couvertes) ;
    s : (8,) valeurs relatives de stock par classe. Renvoie l'indice d'état moyen pondéré par la surface.
    """
    S = np.zeros(F.shape[1:], dtype=np.float64)
    for i in range(F.shape[0]):
        if np.isfinite(s[i]):
            S += F[i] * s[i]
    return S


def normalize_fractions(F_list, s, tol=UNDOC_TOLERANCE):
    """
    Ne garde que les classes à facteur documenté (s non NaN) et renormalise les fractions. Une cellule est NON ESTIMABLE si, à
    une date quelconque, la part des classes sans facteur dépasse `tol` (ou si aucune classe documentée n'y figure).
    Renvoie (liste des fractions renormalisées, masque des cellules non estimables, {indice de classe: masque des cellules où
    cette classe sans facteur dépasse tol}).
    """
    doc = np.isfinite(s)
    shape = F_list[0].shape[1:]
    excluded = np.zeros(shape, dtype=bool)
    cause = {i: np.zeros(shape, dtype=bool) for i in range(len(doc)) if not doc[i]}
    out = []
    for F in F_list:
        Fd = np.where(doc[:, None, None], F, 0.0).astype(np.float32)
        tot = Fd.sum(0)
        undoc = F[~doc].sum(0) if (~doc).any() else np.zeros(shape, dtype=np.float32)
        excluded |= (undoc > tol) | (tot <= 0)
        for i in cause:
            cause[i] |= F[i] > tol
        with np.errstate(invalid="ignore", divide="ignore"):
            out.append(np.where(tot[None] > 0, Fd / np.maximum(tot[None], 1e-12), 0.0).astype(np.float32))
    return out, excluded, cause


def fallow_scenarios(s):
    """Scénarios sur la jachère (classe 6) : facteur propre, assimilée à Cropland (5), assimilée à Rangeland (8)."""
    out = []
    if np.isfinite(s[5]):
        out.append(("Jachère : facteur propre (table)", s.copy()))
    if np.isfinite(s[4]):
        s2 = s.copy(); s2[5] = s[4]
        out.append(("Jachère assimilée à Cropland (facteur de la classe 5)", s2))
    if np.isfinite(s[7]):
        s3 = s.copy(); s3[5] = s[7]
        out.append(("Jachère assimilée à Rangeland (facteur de la classe 8)", s3))
    return out


def effective_states(S_list, years, progressive, eq_years=EQUILIBRIUM_YEARS):
    """
    Réponse du stock : instantanée (S_eff = S) ou progressive. En mode progressif, à chaque intervalle de durée dt la
    fraction w = min(1, dt / eq_years) de l'écart à l'état d'équilibre est comblée :
        S_eff[k] = S_eff[k-1] + w * (S[k] - S_eff[k-1])
    """
    out = [S_list[0].copy()]
    for k in range(1, len(S_list)):
        if progressive:
            w = min(1.0, (years[k] - years[k - 1]) / float(eq_years))
            out.append(out[-1] + w * (S_list[k] - out[-1]))
        else:
            out.append(S_list[k].copy())
    return out


def reconstruct_soc(soc_ref, S_eff, anchor_idx):
    """SOC_t = SOC_ref x S_eff[t] / S_eff[ancrage]  (modèle multiplicatif ; estimation reconstituée, pas une mesure)."""
    base = S_eff[anchor_idx]
    with np.errstate(invalid="ignore", divide="ignore"):
        return [np.where(base > 0, soc_ref * S / base, np.nan) for S in S_eff]


def pct_change(S_eff, i0, i1):
    """Variation relative du stock entre deux dates : S_eff[i1] / S_eff[i0] - 1 (indépendante de la valeur SoilGrids)."""
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(S_eff[i0] > 0, S_eff[i1] / S_eff[i0] - 1.0, np.nan)


def classify_soc(pct, thr_fraction):
    """-1 = perte <= -seuil ; 0 = stable ; +1 = gain >= +seuil ; 127 = non valide (int8)."""
    out = np.full(pct.shape, 127, dtype=np.int8)
    ok = np.isfinite(pct)
    out[ok] = 0
    with np.errstate(invalid="ignore"):
        out[ok & (pct <= -thr_fraction)] = -1
        out[ok & (pct >= thr_fraction)] = 1
    return out


def monte_carlo(F_list, low, high, years, progressive, i0, i1, thr_fraction, draws, seed, valid, links=None):
    """
    Tire les facteurs de chaque classe uniformément dans [low, high] et recalcule la variation i0 -> i1.
    F_list : liste de (8, L, C) ; valid : masque (L, C). Renvoie dict : p_deg, p_imp (probabilités par cellule),
    deg_share, imp_share, mean_pct (tableaux de longueur `draws`, parts en % des cellules valides).
    """
    rng = np.random.default_rng(seed)
    idx = np.where(valid)
    Fv = [F[:, idx[0], idx[1]] for F in F_list]                  # (8, n) par date
    n = idx[0].size
    cnt_deg = np.zeros(n, dtype=np.int32)
    cnt_imp = np.zeros(n, dtype=np.int32)
    deg_share, imp_share, mean_pct = [], [], []
    lo, hi = np.nan_to_num(low, nan=1.0), np.nan_to_num(high, nan=1.0)
    for _ in range(draws):
        s = rng.uniform(lo, hi)
        if links:
            for i_, j_ in links.items():                 # classes liées : même facteur, même tirage
                s[i_] = s[j_]
        S = [np.tensordot(s, Fk, axes=(0, 0)) for Fk in Fv]
        eff = effective_states(S, years, progressive)
        p = pct_change(eff, i0, i1)
        okp = np.isfinite(p)
        d = okp & (p <= -thr_fraction)
        im = okp & (p >= thr_fraction)
        cnt_deg += d
        cnt_imp += im
        m = max(1, int(okp.sum()))
        deg_share.append(100.0 * d.sum() / m)
        imp_share.append(100.0 * im.sum() / m)
        mean_pct.append(100.0 * float(np.nanmean(p)) if okp.any() else float("nan"))
    p_deg = np.full(valid.shape, np.nan, dtype=np.float32)
    p_imp = np.full(valid.shape, np.nan, dtype=np.float32)
    p_deg[idx] = cnt_deg / float(draws)
    p_imp[idx] = cnt_imp / float(draws)
    return {"p_deg": p_deg, "p_imp": p_imp, "deg_share": np.array(deg_share), "imp_share": np.array(imp_share),
            "mean_pct": np.array(mean_pct)}


def percentiles(a):
    a = a[np.isfinite(a)]
    if not a.size:
        return {k: float("nan") for k in ("n", "min", "p10", "p25", "median", "mean", "p75", "p90", "max")}
    q = np.percentile(a, [10, 25, 50, 75, 90])
    return {"n": int(a.size), "min": float(a.min()), "p10": float(q[0]), "p25": float(q[1]), "median": float(q[2]),
            "mean": float(a.mean()), "p75": float(q[3]), "p90": float(q[4]), "max": float(a.max())}


def area_by_class(cls, valid, px_ha):
    """Surfaces (ha) perte / stable / gain sur les cellules valides."""
    tot = int(valid.sum())
    out = {}
    for name, v in (("degraded", -1), ("stable", 0), ("improved", 1)):
        n = int((valid & (cls == v)).sum())
        out[name] = (n, n * px_ha, 100.0 * n / tot if tot else float("nan"))
    out["total"] = (tot, tot * px_ha, 100.0 if tot else float("nan"))
    return out


# ============================================================================
# 5. ENTRÉES / SORTIES RASTER
# ============================================================================

def class_fractions_on_grid(lulc_path, ref_soc_path):
    """
    Fractions de chaque classe LULC (30 m) dans chaque cellule de la grille SOC, par moyenne GDAL de masques binaires
    (pondération par la surface). Renvoie (F (8, L, C), fraction de la cellule couverte par des pixels LULC valides).
    Les pixels LULC non valides (<= 0 ou NoData) n'entrent ni au numérateur ni au dénominateur de F.
    """
    src = open_ds(lulc_path)
    band = src.GetRasterBand(1)
    arr = band.ReadAsArray().astype(np.int16)
    nd = band.GetNoDataValue()
    valid = arr > 0
    if nd is not None and nd > 0:
        valid &= (arr != int(nd))
    ref = open_ds(ref_soc_path)
    gt, rows, cols, proj = ref.GetGeoTransform(), ref.RasterYSize, ref.RasterXSize, ref.GetProjection()
    bounds = (gt[0], gt[3] + rows * gt[5], gt[0] + cols * gt[1], gt[3])

    def warp_avg(values):
        mem = gdal.GetDriverByName("MEM").Create("", arr.shape[1], arr.shape[0], 1, gdal.GDT_Float32)
        mem.SetGeoTransform(src.GetGeoTransform())
        mem.SetProjection(src.GetProjection())
        b = mem.GetRasterBand(1)
        b.WriteArray(values.astype(np.float32))
        b.SetNoDataValue(-9999.0)
        opts = gdal.WarpOptions(format="MEM", outputBounds=bounds, width=cols, height=rows, dstSRS=proj,
                                resampleAlg=gdal.GRA_Average, srcNodata=-9999.0, dstNodata=-9999.0,
                                outputType=gdal.GDT_Float32)
        out = gdal.Warp("", mem, options=opts)
        if out is None:
            raise RuntimeError("Échec de l'agrégation par moyenne pour : " + lulc_path)
        res = out.GetRasterBand(1).ReadAsArray().astype(np.float32)
        res[res <= -9998] = np.nan
        return res

    vf = warp_avg(valid.astype(np.float32))
    F = np.zeros((len(CLASS_CODES), rows, cols), dtype=np.float32)
    for i, c in enumerate(CLASS_CODES):
        m = (arr == c)
        if not m.any():
            continue
        f = warp_avg(np.where(valid, m.astype(np.float32), -9999.0))
        F[i] = np.where(np.isfinite(f), f, 0.0)
    return F, np.where(np.isfinite(vf), vf, 0.0).astype(np.float32)


def read_first_band(path):
    """Lit la bande 1. Le dataset reste référencé pendant la lecture : enchaîner open_ds(...).GetRasterBand(1).ReadAsArray()
    détruit le dataset avant la lecture et provoque « TypeError: in method 'Band_XSize_get' » avec GDAL."""
    ds = open_ds(path)
    arr = ds.GetRasterBand(1).ReadAsArray()
    ds = None
    return arr


def write_f32(path, arr, ref_path, nodata=NODATA_SOC):
    ref = open_ds(ref_path)
    out = np.where(np.isfinite(arr), arr, nodata).astype(np.float32)
    write_geotiff(path, out, ref.GetGeoTransform(), ref.GetProjection(), gdal.GDT_Float32, nodata)


def write_i8(path, arr, ref_path, nodata=127):
    ref = open_ds(ref_path)
    write_geotiff(path, arr.astype(np.int8), ref.GetGeoTransform(), ref.GetProjection(), gdal.GDT_Int16, nodata)


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(r)


def fmt(v, nd=2):
    return "" if v is None or (isinstance(v, float) and not np.isfinite(v)) else "{:.{}f}".format(v, nd)


def add_layer(path, name):
    layer = QgsRasterLayer(path, name)
    if layer.isValid():
        QgsProject.instance().addMapLayer(layer)


# ============================================================================
# 6. PROGRAMME PRINCIPAL
# ============================================================================

def scenario_label(path):
    """Nom court d'un scénario : nom du fichier de facteurs sans extension ni préfixe « SOC_Factors_ », caractères sûrs pour un nom de dossier."""
    b = os.path.splitext(os.path.basename(path))[0]
    if b.lower().startswith("soc_factors_"):
        b = b[len("SOC_Factors_"):]
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", b).strip("_") or "scenario"


def main(preset=None):
    t0 = time.time()
    QMessageBox.information(
        None, "SOC – version finale V4",
        "SOC de référence (SoilGrids 0-30 cm) + cartes LULC + facteurs par classe DOCUMENTÉS.\n\n"
        "Le SOC historique est une ESTIMATION RECONSTITUÉE (modèle), jamais une observation : SoilGrids n'est pas une "
        "série temporelle. Le script n'invente aucun facteur : sans table de facteurs documentés, il s'arrête.")

    _KEYS = ("soc_src", "mask_vec", "lulc_dir", "out_root", "factor_path", "strict_txt", "anchor_txt", "mode_txt", "thr_pct", "divisor", "draws")
    extra_factors, batch_root = [], None
    if preset is not None:                       # scénario suivant d'un lot : les réponses du premier passage sont réutilisées, seule la table de facteurs change
        soc_src, mask_vec, lulc_dir, out_root, factor_path, strict_txt, anchor_txt, mode_txt, thr_pct, divisor, draws = (preset[k] for k in _KEYS)
    else:
        soc_src, _f = QFileDialog.getOpenFileName(None, "1/5 – SoilGrids : stock de carbone organique 0-30 cm (GeoTIFF)", "",
                                                  "Raster (*.tif *.tiff *.vrt);;Tous les fichiers (*)")
        if not soc_src:
            raise RuntimeError("Opération annulée.")
        mask_vec, _f = QFileDialog.getOpenFileName(None, "2/5 – Limite de la zone d'étude (Study_Area_Final)", os.path.dirname(soc_src),
                                                   "Vecteur (*.shp *.gpkg *.geojson *.json);;Tous les fichiers (*)")
        if not mask_vec:
            raise RuntimeError("Opération annulée.")
        lulc_dir = choose_directory("3/5 – Dossier des cartes LULC (" + ", ".join(str(_y) for _y in YEARS) + ")")
        out_root = choose_directory("4/5 – Dossier de sortie")

        factor_path, _f = QFileDialog.getOpenFileName(
            None, "5/5 – Table des facteurs SOC PAR CLASSE (CSV documenté) – annuler pour générer un modèle", out_root,
            "CSV (*.csv);;Tous les fichiers (*)")
        if not factor_path:
            tpl = write_factor_template(os.path.join(out_root, "SOC_Factors_TEMPLATE.csv"))
            QMessageBox.information(
                None, "Modèle de facteurs créé",
                "Aucune table de facteurs fournie : modèle écrit dans\n{}\n\nRemplissez, POUR CHAQUE CLASSE PRÉSENTE : "
                "relative_soc_factor, factor_type, source (+ low/high, confidence), puis relancez.".format(tpl))
            return

        # tables de SENSIBILITÉ supplémentaires (facultatif) : chacune est calculée dans son sous-dossier, puis toutes sont comparées dans UN SEUL rapport HTML
        _gfn = getattr(QFileDialog, "getOpenFileNames", None)
        if _gfn is not None:
            _ps, _f = _gfn(None, "5b/5 – Tables de SENSIBILITÉ supplémentaires (facultatif : Annuler pour passer ; chacune sera calculée dans un sous-dossier et toutes seront comparées dans UN SEUL rapport HTML)",
                           os.path.dirname(factor_path), "CSV (*.csv);;Tous les fichiers (*)")
            extra_factors = [p for p in (_ps or []) if os.path.normpath(p) != os.path.normpath(factor_path)]

        strict_txt, ok = QInputDialog.getItem(
            None, "Classes sans facteur documenté",
            "Si une classe présente dans les cartes n'a pas de facteur documenté (ex. sebkha, eau, bâti) :\n"
            "- Exclure : ces cellules sont déclarées NON ESTIMABLES (surface rapportée), les autres sont calculées ;\n"
            "- Refuser : le script s'arrête (aucun résultat).",
            ["Exclure les cellules concernées (non estimables)", "Refuser le calcul (strict)"], 0, False)
        if not ok:
            raise RuntimeError("Opération annulée.")
        anchor_txt, ok = QInputDialog.getItem(
            None, "Année d'ancrage de SoilGrids",
            "SoilGrids est une carte UNIQUE : à quelle date des cartes LULC la rattachez-vous ? (n'affecte que les valeurs "
            "ABSOLUES en t C/ha, pas les variations en %)", [str(y) for y in YEARS], YEARS.index(2015), False)
        if not ok:
            raise RuntimeError("Opération annulée.")
        mode_txt, ok = QInputDialog.getItem(
            None, "Réponse du stock au changement",
            "Progressive : à chaque intervalle, la fraction (durée / 20 ans) de l'écart à l'équilibre est comblée.\n"
            "Instantanée : le nouveau stock est atteint dès la date suivante (surestime le changement sur les intervalles courts).",
            ["Progressive (20 ans)", "Instantanée"], 0, False)
        if not ok:
            raise RuntimeError("Opération annulée.")
        thr_pct, ok = QInputDialog.getDouble(None, "Seuil analytique de variation du SOC (%)",
                                             "Perte <= -seuil : dégradé ; gain >= +seuil : amélioré (seuil ANALYTIQUE, pas une règle UNCCD mondiale) :",
                                             DEFAULT_THRESHOLD_PCT, 1.0, 100.0, 1)
        if not ok:
            raise RuntimeError("Opération annulée.")
        divisor, ok = QInputDialog.getDouble(None, "Unité de SoilGrids",
                                             "Diviseur à appliquer aux valeurs du raster pour obtenir des t C/ha "
                                             "(1 si déjà en t C/ha ; 10 pour les valeurs brutes SoilGrids x10) :",
                                             1.0, 0.0001, 10000.0, 4)
        if not ok:
            raise RuntimeError("Opération annulée.")
        draws, ok = QInputDialog.getInt(None, "Incertitude (Monte-Carlo)", "Nombre de tirages (0 = désactivé) :",
                                        DEFAULT_MC_DRAWS, 0, 5000)
        if not ok:
            raise RuntimeError("Opération annulée.")

    require_all = strict_txt.startswith("Refuser")
    anchor_year = int(anchor_txt)
    progressive = mode_txt.startswith("Progressive")
    thr = thr_pct / 100.0
    if extra_factors:                            # lot de scénarios : chaque table a son sous-dossier
        batch_root = out_root
        out_root = os.path.join(batch_root, "Scenario_" + scenario_label(factor_path))

    dirs = {k: os.path.join(out_root, v) for k, v in (
        ("qa", "00_QA"), ("ref", "01_Reference"), ("trans", "02_Transitions"), ("soc", "03_SOC_Reconstructed"),
        ("chg", "04_SOC_Change"), ("unc", "05_Uncertainty"), ("stats", "06_Statistics"))}
    for d in dirs.values():
        ensure_dir(d)
    answers = dict(zip(_KEYS, (soc_src, mask_vec, lulc_dir, out_root, factor_path, strict_txt, anchor_txt, mode_txt, thr_pct, divisor, draws)))

    report = []

    def log(line=""):
        print(line)
        report.append(line)

    log("SOC – VERSION FINALE V4 (estimation reconstituée, pas une observation)")
    log("=" * 78)

    # ------------------------------------------------------------------ LULC : sélection et validation
    lulc_files = resolve_lulc_files(lulc_dir)
    for y in YEARS:
        print("[LULC] {} -> {}".format(y, lulc_files[y]))
    first = raster_info(lulc_files[YEARS[0]])
    for y in YEARS:
        inf = raster_info(lulc_files[y])
        if (inf["cols"], inf["rows"], normalized_gt(inf["gt"]), inf["proj"].strip()) != (
                first["cols"], first["rows"], normalized_gt(first["gt"]), first["proj"].strip()):
            raise RuntimeError("Les LULC originales ne partagent pas la même grille (anomalie en {}).".format(y))
    _skipped = [y for y in globals().get("LULC_YEARS", YEARS) if y not in YEARS]
    log("Dates utilisées pour le SOC : {}".format(", ".join(map(str, YEARS))) + ("  |  années diagnostiques EXCLUES de la reconstitution (le SOC d'un état transitoire de sécheresse ne doit ni piloter la réponse sur 20 ans ni retirer des cellules de l'analyse) : {}  (SOC_USE_DIAGNOSTIC_YEARS = True pour les inclure)".format(", ".join(map(str, _skipped))) if _skipped else ""))
    observed = set()
    for y in YEARS:
        observed |= set(validate_lulc_classes(lulc_files[y], y))
    log("LULC : {} cartes sur la même grille ({} x {} px, {:.1f} m) ; classes observées : {}".format(
        len(YEARS), first["cols"], first["rows"], first["xres"], sorted(observed)))

    # ------------------------------------------------------------------ facteurs documentés
    table = read_factor_table(factor_path, observed, require_all=require_all)
    s_mid, s_low, s_high = factor_vector(table), factor_vector(table, "low"), factor_vector(table, "high")
    log("")
    log("FACTEURS RELATIFS DE STOCK PAR CLASSE (documentés ; seuls les rapports comptent)")
    rows_f = []
    for c in CLASS_CODES:
        if c in table:
            t = table[c]
            lk = " (lié à la classe {})".format(t["link_to"]) if t.get("link_to") else ""
            log("   {} {:<12s} facteur {:.3f} [{:.3f} - {:.3f}]{} | {} | confiance {} | {}".format(
                c, DEFAULT_CLASSES[c], t["factor"], t["low"], t["high"], lk, t["type"], t["confidence"], t["source"]))
            rows_f.append([c, DEFAULT_CLASSES[c], t["factor"], t["low"], t["high"], t["type"], t["confidence"], t["source"], t.get("link_to") or ""])
    no_factor = [c for c in sorted(observed) if c not in table]
    for c in no_factor:
        log("   {} {:<12s} AUCUN FACTEUR DOCUMENTÉ -> classe non estimable (cellules concernées exclues et rapportées)".format(c, DEFAULT_CLASSES[c]))
        rows_f.append([c, DEFAULT_CLASSES[c], "", "", "", "", "", "NON DOCUMENTÉ - non estimable", ""])
    write_csv(os.path.join(dirs["qa"], "Factors_Used.csv"),
              ["class_code", "class_name", "relative_soc_factor", "low", "high", "factor_type", "confidence", "source", "link_to"], rows_f)
    links = {c - 1: table[c]["link_to"] - 1 for c in table if table[c].get("link_to")}

    # ------------------------------------------------------------------ SOC de référence
    soc_ref_raw = os.path.join(dirs["ref"], "SOC_Reference_SoilGrids_0_30cm.tif")
    clip_soc_reference(soc_src, mask_vec, soc_ref_raw)
    si, ri = raster_info(soc_src), raster_info(soc_ref_raw)
    pxha = pixel_area_ha_path(soc_ref_raw)
    soc_ds = open_ds(soc_ref_raw)
    soc_b = soc_ds.GetRasterBand(1)
    soc_arr = soc_b.ReadAsArray().astype(np.float64)
    soc_nd = soc_b.GetNoDataValue()
    soc_valid = valid_mask(soc_arr, soc_nd) & (soc_arr > 0)
    soc_t = np.where(soc_valid, soc_arr / divisor, np.nan)
    soc_ref = os.path.join(dirs["ref"], "SOC_Reference_tCha.tif")
    write_f32(soc_ref, soc_t, soc_ref_raw)
    st = percentiles(soc_t[soc_valid])
    log("")
    log("RÉFÉRENCE SOC (SoilGrids, observée/modélisée par ISRIC ; PAS une série temporelle)")
    log("   source : {} x {} px | {:.8g} x {:.8g} | EPSG {} | NoData {}".format(
        si["cols"], si["rows"], si["xres"], si["yres"], projection_epsg(soc_src), si["nodata"]))
    log("   grille d'analyse SOC : {} x {} px | {:.1f} x {:.1f} m | EPSG {} | pixel {:.2f} ha  (résolution du SOC != 30 m du LULC ni 250 m MODIS)".format(
        ri["cols"], ri["rows"], ri["xres"], ri["yres"], projection_epsg(soc_ref_raw), pxha))
    log("   cellules valides : {:,} ({:.1f} % de la grille) | diviseur d'unité appliqué : {:g}".format(
        int(soc_valid.sum()), 100.0 * soc_valid.mean(), divisor))
    log("   t C/ha : min {:.1f} | P10 {:.1f} | P25 {:.1f} | médiane {:.1f} | moyenne {:.1f} | P75 {:.1f} | P90 {:.1f} | max {:.1f}".format(
        st["min"], st["p10"], st["p25"], st["median"], st["mean"], st["p75"], st["p90"], st["max"]))
    if st["median"] > SOC_SANITY_MEDIAN_MAX:
        log("   ATTENTION UNITÉ : médiane {:.0f} t C/ha très élevée : valeurs brutes x10 ? relancer avec le diviseur 10.".format(st["median"]))
    if st["median"] < 5:
        log("   ATTENTION UNITÉ : médiane {:.1f} t C/ha très faible : vérifier l'unité de la couche.".format(st["median"]))

    # ------------------------------------------------------------------ LULC sur la grille SOC (MODE) + transitions
    harmonized = {}
    for y in YEARS:
        p = os.path.join(dirs["ref"], "LULC_{}_SOC_grid_mode.tif".format(y))
        warp_lulc_exact(lulc_files[y], soc_ref_raw, p)
        harmonized[y] = p
    areas_mode = {}
    with open(os.path.join(dirs["stats"], "LULC_Area_ha_SOC_grid_mode.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["year", "code", "class", "pixels", "area_ha"])
        for y in YEARS:
            for code, name, n, ha in class_area_stats(harmonized[y], DEFAULT_CLASSES):
                w.writerow([y, code, name, n, ha])
                areas_mode[(y, code)] = ha
    for i in range(len(YEARS) - 1):
        a, b = YEARS[i], YEARS[i + 1]
        create_transition(harmonized[a], harmonized[b], os.path.join(dirs["trans"], "Transition_{}_{}.tif".format(a, b)))
        write_transition_matrix_csv(os.path.join(dirs["trans"], "Matrice_{}_{}.csv".format(a, b)),
                                    transition_matrix(harmonized[a], harmonized[b]), DEFAULT_CLASSES, a, b, pxha)
    create_transition(harmonized[YEARS[0]], harmonized[YEARS[-1]], os.path.join(dirs["trans"], "Transition_{}_{}.tif".format(YEARS[0], YEARS[-1])))
    write_transition_matrix_csv(os.path.join(dirs["trans"], "Matrice_{}_{}.csv".format(YEARS[0], YEARS[-1])),
                                transition_matrix(harmonized[YEARS[0]], harmonized[YEARS[-1]]), DEFAULT_CLASSES,
                                YEARS[0], YEARS[-1], pxha)
    ext_rows = []
    for a, b in [(YEARS[i], YEARS[i + 1]) for i in range(len(YEARS) - 1)] + [(YEARS[0], YEARS[-1])]:
        cands = [os.path.join(os.path.dirname(lulc_files[a]), "{}_{}.tif".format(a, b)),
                 os.path.join(os.path.dirname(lulc_files[a]), "Transition_{}_{}.tif".format(a, b))]
        cand = next((p for p in cands if os.path.exists(p)), None)
        if cand:
            okq, msg = external_transition_qa(cand, lulc_files[a], lulc_files[b])
            ext_rows.append(["{}_{}".format(a, b), cand, okq, msg])
        else:
            ext_rows.append(["{}_{}".format(a, b), "", "NON", "Fichier non fourni"])
    write_csv(os.path.join(dirs["qa"], "QA_Transitions_30m_externes.csv"), ["transition", "fichier", "coherent", "details"], ext_rows)

    # ------------------------------------------------------------------ fractions de classes (30 m -> grille SOC, pondérées par la surface)
    log("")
    log("LULC 30 m -> grille SOC : fractions par classe (moyenne pondérée par la surface) et classe dominante (MODE)")
    F_list, cover_ok = [], np.ones(soc_valid.shape, dtype=bool)
    cover_rows = []
    for y in YEARS:
        F, vf = class_fractions_on_grid(lulc_files[y], soc_ref_raw)
        F_list.append(F)
        cover_ok &= (vf >= MIN_COVER)
        cover_rows.append((y, 100.0 * float(np.mean(vf[soc_valid] >= MIN_COVER)) if soc_valid.any() else float("nan")))
        log("   {} : cellules SOC avec >= {:.0f} % de pixels LULC valides : {:.1f} %".format(y, 100 * MIN_COVER, cover_rows[-1][1]))
    Fdoc, excl, cause = normalize_fractions(F_list, s_mid)
    analyzable = soc_valid & cover_ok
    valid = analyzable & ~excl
    n_valid = int(valid.sum())
    n_excl = int((analyzable & excl).sum())
    if n_excl:
        log("")
        log("SURFACE NON ESTIMABLE (classes sans facteur documenté) : {:,.0f} ha = {:.1f} % de la zone analysable".format(
            n_excl * pxha, 100.0 * n_excl / max(1, int(analyzable.sum()))))
        ne_rows = []
        for i, mcause in sorted(cause.items()):
            c = CLASS_CODES[i]
            if c in observed:
                nn = int((analyzable & mcause).sum())
                log("   classe {} ({}) > {:.0f} % de la cellule à au moins une date : {:,} cellules ({:,.0f} ha)".format(
                    c, DEFAULT_CLASSES[c], 100 * UNDOC_TOLERANCE, nn, nn * pxha))
                ne_rows.append([c, DEFAULT_CLASSES[c], nn, fmt(nn * pxha, 1)])
        ne_rows.append(["total", "cellules non estimables", n_excl, fmt(n_excl * pxha, 1)])
        write_csv(os.path.join(dirs["stats"], "SOC_NotEstimable_Area.csv"), ["class_code", "class", "cells", "area_ha"], ne_rows)
        mask_out = np.where(soc_valid, np.where(analyzable & excl, 1.0, 0.0), np.nan)
        write_f32(os.path.join(dirs["qa"], "SOC_NotEstimable_Mask.tif"), mask_out, soc_ref_raw)
        if n_excl > 0.10 * int(analyzable.sum()):
            log("   ATTENTION : plus de 10 % de la zone est non estimable : les résultats ne représentent PAS toute la zone.")
    log("   cellules analysées (SOC valide ET LULC valide aux {} dates) : {:,} sur {:,} cellules SOC valides ({:.1f} %)".format(
        len(YEARS), n_valid, int(soc_valid.sum()), 100.0 * n_valid / max(1, int(soc_valid.sum()))))
    if n_valid == 0:
        raise RuntimeError("Aucune cellule valide pour l'analyse (vérifier l'emprise SOC / LULC).")

    # QA : biais de l'agrégation MODE par rapport aux fractions (surfaces par classe, 2025 et 1999)
    cmp_rows = []
    for y in (YEARS[0], YEARS[-1]):
        Fy = F_list[YEARS.index(y)]
        lc = read_first_band(harmonized[y])
        for i, c in enumerate(CLASS_CODES):
            a_frac = float(np.nansum(Fy[i][valid])) * pxha
            a_mode = float(np.count_nonzero((lc == c) & valid)) * pxha
            cmp_rows.append([y, c, DEFAULT_CLASSES[c], fmt(a_mode, 1), fmt(a_frac, 1),
                             fmt(100.0 * (a_mode - a_frac) / a_frac, 1) if a_frac > 0 else ""])
    write_csv(os.path.join(dirs["qa"], "LULC_Area_Mode_vs_Fraction.csv"),
              ["year", "code", "class", "area_mode_ha", "area_fraction_weighted_ha", "mode_minus_fraction_pct"], cmp_rows)
    big = max((abs(float(r[5])) for r in cmp_rows if r[5] != ""), default=0.0)
    log("   biais maximal de la classe dominante (MODE) par rapport aux fractions : {:.1f} % de la surface d'une classe "
        "(voir LULC_Area_Mode_vs_Fraction.csv)".format(big))

    # ------------------------------------------------------------------ indice d'état, SOC reconstitué
    S_list = [state_index(Fd, s_mid) for Fd in Fdoc]
    S_eff = effective_states(S_list, YEARS, progressive)
    S_eff = [np.where(valid, S, np.nan) for S in S_eff]
    anchor_idx = YEARS.index(anchor_year)
    soc_years = reconstruct_soc(soc_t, S_eff, anchor_idx)

    log("")
    log("SOC RECONSTITUÉ (modèle multiplicatif ; ancrage SoilGrids = {} ; réponse {})".format(
        anchor_year, "progressive (20 ans)" if progressive else "instantanée"))
    totals = []
    for y, arr in zip(YEARS, soc_years):
        write_f32(os.path.join(dirs["soc"], "SOC_Reconstructed_{}.tif".format(y)), arr, soc_ref_raw)
        tot = float(np.nansum(np.where(valid, arr, 0.0))) * pxha / 1e6
        totals.append((y, tot))
    write_csv(os.path.join(dirs["stats"], "SOC_Totals_MtC.csv"), ["year", "total_SOC_Mt_C", "area_analyzed_ha"],
              [[y, fmt(t, 4), fmt(n_valid * pxha, 1)] for y, t in totals])
    log("   stock total 0-30 cm sur {:,.0f} ha : ".format(n_valid * pxha) + " | ".join("{} {:.2f} Mt C".format(y, t) for y, t in totals))

    # ------------------------------------------------------------------ variations par période
    pairs = [(YEARS[i], YEARS[i + 1]) for i in range(len(YEARS) - 1)] + [p for p in OVERALL_PAIRS if p not in [(YEARS[i], YEARS[i + 1]) for i in range(len(YEARS) - 1)]]
    lulc_cat = read_first_band(harmonized[YEARS[-1]])
    stat_rows, perc_rows, lulc_rows = [], [], []
    log("")
    log("VARIATION DU SOC PAR PÉRIODE (seuil analytique ±{:g} %)".format(thr_pct))
    for a, b in pairs:
        i0, i1 = YEARS.index(a), YEARS.index(b)
        p = pct_change(S_eff, i0, i1)
        absch = soc_years[i1] - soc_years[i0]
        cls = classify_soc(p, thr)
        cls = np.where(valid, cls, 127).astype(np.int8)
        tag = "{}_{}".format(a, b)
        write_f32(os.path.join(dirs["chg"], "SOC_Change_{}.tif".format(tag)), absch, soc_ref_raw)
        write_f32(os.path.join(dirs["chg"], "SOC_ChangePct_{}.tif".format(tag)), 100.0 * p, soc_ref_raw)
        write_f32(os.path.join(dirs["chg"], "SOC_ChangeAnnual_{}.tif".format(tag)), absch / float(b - a), soc_ref_raw)
        write_i8(os.path.join(dirs["chg"], "SOC_Class_{}.tif".format(tag)), cls, soc_ref_raw)
        ar = area_by_class(cls, valid, pxha)
        pc = percentiles(100.0 * p[valid])
        pa = percentiles(absch[valid])
        log("   {} : médiane {:+.2f} % [P10 {:+.2f} ; P90 {:+.2f}] | dégradé {:,.0f} ha ({:.1f} %) | stable {:.1f} % | amélioré {:,.0f} ha ({:.1f} %)".format(
            tag, pc["median"], pc["p10"], pc["p90"], ar["degraded"][1], ar["degraded"][2], ar["stable"][2], ar["improved"][1], ar["improved"][2]))
        for k in ("degraded", "stable", "improved"):
            stat_rows.append([tag, k, ar[k][0], fmt(ar[k][1], 1), fmt(ar[k][2], 2)])
        perc_rows.append([tag, pc["n"], fmt(pc["min"]), fmt(pc["p10"]), fmt(pc["p25"]), fmt(pc["median"]), fmt(pc["mean"]),
                          fmt(pc["p75"]), fmt(pc["p90"]), fmt(pc["max"]), fmt(pa["median"], 3), fmt(pa["mean"], 3)])
        if (a, b) in OVERALL_PAIRS:
            for c in CLASS_CODES:
                m = valid & (lulc_cat == c)
                n = int(m.sum())
                if n:
                    lulc_rows.append([tag, c, DEFAULT_CLASSES[c], n, fmt(n * pxha, 1),
                                      fmt(100.0 * float((cls[m] == -1).sum()) / n, 2), fmt(100.0 * float((cls[m] == 1).sum()) / n, 2),
                                      fmt(float(np.nanmedian(100.0 * p[m])), 2)])
    write_csv(os.path.join(dirs["stats"], "SOC_Area_Statistics.csv"), ["period", "class", "pixels", "area_ha", "percent"], stat_rows)
    write_csv(os.path.join(dirs["stats"], "SOC_Change_Percentiles.csv"),
              ["period", "cells", "pct_min", "pct_P10", "pct_P25", "pct_median", "pct_mean", "pct_P75", "pct_P90", "pct_max",
               "abs_change_median_tCha", "abs_change_mean_tCha"], perc_rows)
    write_csv(os.path.join(dirs["stats"], "SOC_by_LULC_{}.csv".format(YEARS[-1])),
              ["period", "class_code", "class", "cells", "area_ha", "degraded_%", "improved_%", "median_change_%"], lulc_rows)

    # ------------------------------------------------------------------ sensibilité : mode de réponse et méthode de classe dominante
    sens_rows = []
    log("")
    log("SENSIBILITÉ DU CHOIX DE MÉTHODE (période {}-{}, facteurs centraux)".format(YEARS[0], YEARS[-1]))
    mode_S = []
    for y in YEARS:
        lc = read_first_band(harmonized[y])
        Sm = np.full(lc.shape, np.nan)
        for i, c in enumerate(CLASS_CODES):
            if np.isfinite(s_mid[i]):
                Sm[lc == c] = s_mid[i]
        mode_S.append(np.where(valid, Sm, np.nan))
    for label, SL in (("fractions 30 m (méthode retenue)", [np.where(valid, Sx, np.nan) for Sx in S_list]), ("classe dominante (MODE)", mode_S)):
        for prog in (True, False):
            eff = effective_states([np.where(valid, S, np.nan) for S in SL], YEARS, prog)
            p = pct_change(eff, 0, len(YEARS) - 1)
            cl = classify_soc(p, thr)
            ar = area_by_class(np.where(valid, cl, 127), valid, pxha)
            pc_ = percentiles(100.0 * p[valid])
            sens_rows.append([label, "progressive" if prog else "instantanée", fmt(pc_["median"], 2), fmt(pc_["mean"], 2),
                              fmt(pc_["p10"], 2), fmt(pc_["p90"], 2), fmt(ar["degraded"][2], 2), fmt(ar["improved"][2], 2),
                              fmt(ar["degraded"][1], 1)])
            log("   {:<34s} {:<12s} moyenne {:+.2f} % [P10 {:+.2f} ; P90 {:+.2f}] | dégradé {:.1f} % | amélioré {:.1f} %".format(
                label, "progressive" if prog else "instantanée", pc_["mean"], pc_["p10"], pc_["p90"], ar["degraded"][2], ar["improved"][2]))
    write_csv(os.path.join(dirs["stats"], "SOC_Method_Sensitivity.csv"),
              ["land cover aggregation", "stock response", "median_change_%", "mean_change_%", "P10_change_%", "P90_change_%",
               "degraded_%", "improved_%", "degraded_ha"], sens_rows)

    # ------------------------------------------------------------------ sensibilité à la définition de la jachère (classe 6)
    if 6 in observed:
        fs_rows = []
        log("")
        log("SENSIBILITÉ À LA JACHÈRE (en zone semi-aride elle est souvent pâturée : ni franchement Cropland ni franchement Rangeland)")
        for label, s_scn in fallow_scenarios(s_mid):
            Fd_s, excl_s, _c = normalize_fractions(F_list, s_scn)
            valid_s = analyzable & ~excl_s
            S_s = [np.where(valid_s, state_index(Fd, s_scn), np.nan) for Fd in Fd_s]
            eff_s = effective_states(S_s, YEARS, progressive)
            for a, b in OVERALL_PAIRS:
                p = pct_change(eff_s, YEARS.index(a), YEARS.index(b))
                cl = np.where(valid_s, classify_soc(p, thr), 127).astype(np.int8)
                ar = area_by_class(cl, valid_s, pxha)
                pc_ = percentiles(100.0 * p[valid_s])
                fs_rows.append([label, fmt(s_scn[5], 4), "{}_{}".format(a, b), int(valid_s.sum()), fmt(valid_s.sum() * pxha, 1),
                                fmt(pc_["median"], 2), fmt(pc_["mean"], 2), fmt(pc_["p10"], 2), fmt(pc_["p90"], 2),
                                fmt(ar["degraded"][2], 2), fmt(ar["improved"][2], 2), fmt(ar["degraded"][1], 1)])
                log("   {:<58s} {}-{} : {:,.0f} ha analysés | dégradé {:.1f} % | amélioré {:.1f} %".format(
                    label, a, b, valid_s.sum() * pxha, ar["degraded"][2], ar["improved"][2]))
        if fs_rows:
            write_csv(os.path.join(dirs["stats"], "SOC_Fallow_Sensitivity.csv"),
                      ["fallow assumption", "fallow_factor_used", "period", "cells_analyzed", "area_analyzed_ha", "median_change_%",
                       "mean_change_%", "P10_change_%", "P90_change_%", "degraded_%", "improved_%", "degraded_ha"], fs_rows)
        else:
            log("   (aucune hypothèse possible : ni la jachère, ni Cropland (5), ni Rangeland (8) n'a de facteur documenté)")

    # ------------------------------------------------------------------ incertitude Monte-Carlo
    if draws > 0:
        varying = np.any(np.nan_to_num(s_high - s_low) > 0)
        log("")
        if not varying:
            log("INCERTITUDE : bornes low/high absentes ou égales au facteur central : Monte-Carlo non exécuté "
                "(renseignez low/high pour quantifier l'incertitude).")
        else:
            log("INCERTITUDE (Monte-Carlo, {} tirages ; facteurs de chaque classe tirés dans [low, high], indépendamment)".format(draws))
            mc_rows = []
            for a, b in OVERALL_PAIRS:
                i0, i1 = YEARS.index(a), YEARS.index(b)
                Fv = [np.where(valid[None], Fd, 0.0) for Fd in Fdoc]
                mc = monte_carlo(Fv, s_low, s_high, YEARS, progressive, i0, i1, thr, draws, 12345, valid, links=links)
                tag = "{}_{}".format(a, b)
                write_f32(os.path.join(dirs["unc"], "SOC_Prob_Degraded_{}.tif".format(tag)), mc["p_deg"], soc_ref_raw)
                write_f32(os.path.join(dirs["unc"], "SOC_Prob_Improved_{}.tif".format(tag)), mc["p_imp"], soc_ref_raw)
                q = lambda v: np.percentile(v, [10, 50, 90])
                dq, iq, mq = q(mc["deg_share"]), q(mc["imp_share"]), q(mc["mean_pct"])
                robust = float(np.mean(mc["p_deg"][valid] >= 0.9)) * 100.0
                mc_rows.append([tag, draws, fmt(dq[0]), fmt(dq[1]), fmt(dq[2]), fmt(iq[0]), fmt(iq[1]), fmt(iq[2]),
                                fmt(mq[0]), fmt(mq[1]), fmt(mq[2]), fmt(robust)])
                log("   {} : part dégradée P10 {:.1f} % | médiane {:.1f} % | P90 {:.1f} % ; part améliorée médiane {:.1f} % ; "
                    "cellules dégradées dans >= 90 % des tirages : {:.1f} % de la zone analysée".format(
                        tag, dq[0], dq[1], dq[2], iq[1], robust))
            write_csv(os.path.join(dirs["unc"], "SOC_MonteCarlo_Summary.csv"),
                      ["period", "draws", "degraded_share_P10_%", "degraded_share_P50_%", "degraded_share_P90_%",
                       "improved_share_P10_%", "improved_share_P50_%", "improved_share_P90_%",
                       "mean_change_P10_%", "mean_change_P50_%", "mean_change_P90_%", "robust_degraded_cells_%"], mc_rows)

    # ------------------------------------------------------------------ rapports
    log("")
    log("LIMITES (à reprendre dans la méthodologie)")
    log("  - SoilGrids est une carte UNIQUE (ISRIC) : le SOC {}-{} ci-dessus est une estimation RECONSTITUÉE par un modèle de".format(YEARS[0], YEARS[-1]))
    log("    facteurs relatifs par classe appliqué aux changements de LULC ; ce n'est pas un SOC mesuré en {}.".format(YEARS[0]))
    log("  - Les variations en % ne dépendent que des facteurs et du LULC (modèle multiplicatif) ; SoilGrids fixe seulement les valeurs absolues.")
    log("  - Le SOC change uniquement quand la classe LULC change : l'erreur de classification de LULC (non évaluée ici) se transmet au SOC.")
    log("  - Le seuil ±{:g} % est ANALYTIQUE : ce n'est pas une règle UNCCD mondiale.".format(thr_pct))
    log("  - Résolution d'analyse SOC : {:.0f} m (grille SoilGrids recadrée), distincte du LULC 30 m et du LPD MODIS 250 m.".format(ri["xres"]))
    log("")
    log("Durée : {:.1f} min | Sorties : {}".format((time.time() - t0) / 60.0, out_root))
    with open(os.path.join(dirs["qa"], "SOC_Data_Quality_Report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    with open(os.path.join(out_root, "SOC_Methodology_V4.txt"), "w", encoding="utf-8") as f:
        f.write("SOC – MÉTHODOLOGIE ET TRAÇABILITÉ (V4)\n" + "=" * 78 + "\n\n" +
                "Séparation stricte :\n"
                "  1. SOC de RÉFÉRENCE : SoilGrids 0-30 cm (carte unique, non temporelle), recadrée sur la zone d'étude.\n"
                "  2. SOC RECONSTITUÉ : modèle SOC_t = SOC_réf x S_t / S_ancrage, S = indice d'état moyen pondéré par la surface\n"
                "     des facteurs relatifs par classe documentés (Factors_Used.csv).\n"
                "  3. VARIATION attribuable aux transitions de LULC, par période, en valeur absolue, en %, annualisée.\n\n" +
                "\n".join(report))
    add_layer(os.path.join(dirs["chg"], "SOC_ChangePct_{}_{}.tif".format(YEARS[0], YEARS[-1])), "SOC – variation {}-{} (%, estimation reconstituée)".format(YEARS[0], YEARS[-1]))
    add_layer(os.path.join(dirs["chg"], "SOC_Class_{}_{}.tif".format(YEARS[0], YEARS[-1])), "SOC – classe {}-{} (-1 perte, 0 stable, 1 gain ; 127 = non valide)".format(YEARS[0], YEARS[-1]))
    add_layer(os.path.join(dirs["soc"], "SOC_Reconstructed_2025.tif"), "SOC reconstitué 2025 (t C/ha)")
    try:
        _inp = [{"label": "SoilGrids SOC 0-30 cm", "path": soc_src}, {"label": "Study-area boundary", "path": mask_vec}, {"label": "SOC factor table", "path": factor_path}] + [{"label": f"LULC {_y}", "path": lulc_files[_y]} for _y in YEARS if _y in lulc_files]
        soc_stage_report(out_root, dirs, report, t0, {"Equilibrium years": EQUILIBRIUM_YEARS, "Undocumented-class tolerance": UNDOC_TOLERANCE, "Change threshold (%)": thr_pct, "Monte Carlo draws": locals().get("draws", "-")}, _inp, AREA_NAME, YEARS, REPORT_LANG)
    except Exception as _exc:
        print("[Rapport HTML d'étape] échec (le traitement lui-même est terminé) : " + str(_exc))
    if not (preset and preset.get("quiet")):
        QMessageBox.information(None, "SOC V4 terminé", "\n".join(report[:60]))
    return {"label": scenario_label(factor_path), "out_root": out_root, "dirs": dirs, "report": report, "factor_path": factor_path, "answers": answers, "extra_factors": extra_factors, "batch_root": batch_root}


def run_all():
    """Premier passage interactif ; si des tables de sensibilité supplémentaires ont été choisies, chacune est calculée dans son sous-dossier puis TOUTES sont comparées dans UN SEUL rapport HTML."""
    first = main()
    if not first or not first.get("extra_factors"):
        return first
    batch_root = first["batch_root"]
    results = [first]
    for fp in first["extra_factors"]:
        label = scenario_label(fp)
        preset = dict(first["answers"], factor_path=fp, out_root=os.path.join(batch_root, "Scenario_" + label), quiet=True)
        print("\n" + "=" * 78 + "\nSCÉNARIO : " + label + "\n" + "=" * 78)
        try:
            results.append(main(preset))
        except Exception as exc:
            print("[Scénario " + label + "] échec : " + str(exc))
            results.append({"label": label, "error": str(exc), "out_root": preset["out_root"], "factor_path": fp})
    path = soc_scenarios_report(batch_root, results, YEARS, AREA_NAME, REPORT_LANG, [f"{a}_{b}" for a, b in OVERALL_PAIRS])
    QMessageBox.information(None, "SOC — comparaison des scénarios", "{} scénarios calculés ({} en échec).\n\nRapport comparatif UNIQUE :\n{}".format(len(results), sum(1 for r in results if r.get("error")), path))
    try:
        from qgis.PyQt.QtCore import QUrl
        from qgis.PyQt.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    except Exception:
        pass
    return path


try:
    run_all()
except Exception as exc:
    msg = "SOC V4 - échec.\n\n" + str(exc) + "\n\n" + traceback.format_exc()
    print(msg)
    try:
        QMessageBox.critical(None, "Erreur SOC V4", msg)
    except Exception:
        pass
