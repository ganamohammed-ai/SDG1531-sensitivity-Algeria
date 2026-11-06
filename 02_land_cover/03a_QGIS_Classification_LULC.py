# -*- coding: utf-8 -*-
# SDG 15.3.1 REFERENCE PIPELINE — STAGE 03 / 08 : Land-use / land-cover classification — QGIS
"""
LULC Classification & Desertification Monitoring - Version 15 FINAL – Strict Admin / Sebkha First
Years: 1985, 2000, 2007, 2015, 2020, 2025  — TRAITEMENT ASCENDANT par défaut : 2000 -> 2007 -> 2015 -> 2020 -> 2025 (chaque année est comparée à l'année PRÉCÉDENTE) ;
l'ordre DESCENDANT (2025 -> 2000) reste disponible dans la fenêtre de démarrage. Une ANCRE éventuelle est toujours traitée en premier.
Hierarchical order (FINAL):
  0. Strict administrative mask
  1. Stable Sebkha mask (Class 3) + independent dry/wet hydrological state
  2. Built-up (Class 1)
  3. Water outside Sebkha (Class 2; spring/summer)
  4. Bareland/Rock first, then Vegetated mask
  5. Forest, dense or open / ex-Matorral (Class 7) + no-agriculture-in-forest rule
  6. Cropland (Class 5; seasonal amplitude)
  7. Fallow vs Rangeland (Classes 6/8)
  8. Residual valid/NoData handling: nearest-neighbour filling inside admin, then Bareland/Rock
  9. Final AREA QA window (not a classification stage; mandatory per year)
Each stage supports transparent thresholds and Random Forest simultaneously for independent preview,
agreement/difference inspection, then execution by Thresholds, RF, or Hybrid.

AJOUT (masques imposés + années) — sans modifier les étapes ni les calibrations existantes :
  * Au démarrage : traiter UNE année, PLUSIEURS années (cases à cocher) ou TOUTES (comportement habituel).
  * Pour chaque étape (Sebkha, Built-up, Water, Bareland, Forest, Cropland, Fallow, Rangeland) on peut fournir
    un masque IMPOSÉ (.shp/.gpkg/.tif), comme le masque stable Sebkha : ses pixels reçoivent la classe de l'étape
    et ne sont plus reclassés. Un nom finissant par une année (Water_2015.shp) est un masque propre à cette année.
    Une étape fournie par masque (Forest, Cropland, Rangeland, Fallow, Bareland) N'OUVRE AUCUNE FENÊTRE : sa classe
    est extraite avant les fenêtres des autres étapes (ses pixels y sont déjà colorés). Deux modes : hiérarchie respectée
    (Sebkha, Built-up, Water prioritaires) ou masques prioritaires (appliqués avant toute étape automatique).
  * Sans masque et avec « toutes les années », le résultat est identique à la version précédente.
  * PREUVES SUPPLÉMENTAIRES (facultatives) pour séparer Fallow / Rangeland / Bareland : statistiques d'un stack NDVI multi-années (maximum des autres années,
    années actives / basses, bimodalité), corrélation NDVI - précipitations (CHIRPS), pente (MNT), fraction de Cropland alentour (calculée sur la carte).
    Champs « Temp_ », « Terr_ », « Ctx_ » des fenêtres : vides = non utilisés ; ces variables entrent aussi dans le Random Forest des étapes 6-8.
  * TOUTES LES ÉTAPES (1 Sebkha, 2 Built-up, 3 Water, 4 Forest ... 9 Bareland) s'ouvrent dans la MÊME fenêtre complète : carte, seuils
    SUGGÉRÉS (Scientific default), RF / hybride, aperçu, et panneau « Masque de l'étape ». Nomenclature commune : Apr_ / Jul_ + indicateur + min / max.
  * MASQUE DE L'ÉTAPE, DANS LA FENÊTRE DE CHAQUE ÉTAPE : source = shapefile, raster ou
    classe(s) d'un AUTRE raster ; rôle = TOTAL (la classe est le masque) ou LIMITE (classement seulement à l'intérieur, comme l'ancienne limite
    forestière). Le bouton « Afficher l'emprise du masque » dessine le masque sur la carte (aperçu) et donne sa SURFACE en hectares.
    Enregistré dans le preset, rejoué en batch / reprise. Sebkha et Built-up : masque obligatoire (défaut : fichier trouvé), rôle TOTAL.

NOUVELLE HIÉRARCHIE (V16) :
  0 Masque administratif -> 1 Sebkha (masque stable) -> 2 Built-up (masque par année) -> 3 Water
  -> 4 FOREST (classe 7 : forêt dense OU claire / ex-Matorral) -> [5 supprimée] -> 6 Cropland (5) -> 7 FALLOW (6)
  -> 8 Rangeland (8) -> 9 Bareland / Rock (4) (en dernier) -> résidu : voisin classé le plus proche, puis Bareland.
  * AUCUNE limite forestière : le fichier Forest_Final.shp n'est plus requis ni utilisé ; chaque étape travaille sur tous
    les pixels encore non classés. Bareland / Rock n'est plus extrait en premier mais en dernier.
  * Forest et Matorral sont FUSIONNÉS en UNE classe Forest (7) : TOUTE la chaîne (LPD, SOC, intégration, validation) travaille à 8 classes.
    L'étape 5 (Matorral) n'existe plus ; la fenêtre Forest contient deux blocs de seuils : forêt DENSE (champs 1-3) OU forêt CLAIRE / ancien Matorral
    (champs 4-7, valeurs de départ = anciennes valeurs Matorral ; vider ces 4 champs = forêt dense seule). Les étapes sont numérotées 1 à 8 sans trou ; les anciens presets (numérotation à 9 étapes)
    sont RENUMÉROTÉS automatiquement au démarrage, et l'ancien preset Matorral devient le bloc « forêt claire » de l'étape 4.
  * Les polygones d'entraînement codés 9 (ancien Matorral) sont lus comme 7 (Forest) ; codes valides : 1 à 8.
  * Un NOUVEAU dossier de résultats est utilisé : les anciens presets / points de reprise (autre numérotation d'étapes) ne sont pas mélangés.
"""

import os
import platform
import time as _time_mod
_STAGE_T0 = _time_mod.time()
# ============================== CONFIGURATION DE LA CHAÎNE (à adapter pour une autre zone d'étude) ==============================
AREA_TAG = "Oum_El_Bouaghi"                 # étiquette des cartes : LULC_<AREA_TAG>_<année>.tif
AREA_NAME = "Oum El Bouaghi (Algeria)"      # nom de la zone, affiché dans les rapports HTML
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
# =================================================================================================================================

PIPELINE_BUILD = "2026.10-10663c5ae874"
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
def classification_stage_report(output_dir, t0, params, area_name, lang="en", log=print):
    """Rapport HTML de l'étape 03 (classification LULC) : lit les fichiers écrits par le script (Areas_All_Years, Area_QA_*, Metadata_*, cartes LULC)."""
    en = lang == "en"
    T = lambda a, b: a if en else b
    find = lambda pat: sr_find_files(output_dir, pat)
    areas = sr_dict_rows(sr_read_csv(next(iter(find(r"^Areas_All_Years\.csv$")), None)))
    years = sorted({int(float(r["Year"])) for r in areas}) if areas else []
    names = []
    for r in areas:
        if r["Class"] not in names:
            names.append(r["Class"])
    pv = {y: {r["Class"]: sr_num(r["Area_ha"], 0.0) for r in areas if int(float(r["Year"])) == y} for y in years}
    tot = {y: sum(pv[y].values()) for y in years}
    tb = [[T("Class", "Classe")] + [str(y) for y in years] + [T("Change (ha)", "Variation (ha)")]]
    for n in names:
        tb.append([n] + [f"{pv[y].get(n, 0):,.1f}" for y in years] + [f"{pv[years[-1]].get(n, 0) - pv[years[0]].get(n, 0):+,.1f}" if len(years) > 1 else ""])
    tb.append([T("Total", "Total")] + [f"{tot[y]:,.1f}" for y in years] + [""])
    summary, checks = [], []
    if years:
        summary.append(T(f"{len(years)} maps classified: {', '.join(map(str, years))}; study area {tot[years[0]]:,.0f} ha", f"{len(years)} cartes classées : {', '.join(map(str, years))} ; zone d'étude {tot[years[0]]:,.0f} ha"))
    qa_rows, qa_status = [], {}
    for p in find(r"^Area_QA_\d{4}\.csv$"):
        rr = sr_read_csv(p)
        if len(rr) >= 2:
            if not qa_rows:
                qa_rows.append(rr[0])
            qa_rows.append(rr[1])
            d = dict(zip(rr[0], rr[1]))
            qa_status[d.get("Year", os.path.basename(p))] = d
    if qa_status:
        bad = [y for y, d in qa_status.items() if str(d.get("Status", "")).strip().upper() != "PASS"]
        checks.append((T("Area QA of every year (completeness, boundary, consistency)", "Contrôle de surface de chaque année (complétude, limites, cohérence)"), "PASS" if not bad else "FAIL", T(f"{len(qa_status)} years, all PASS", f"{len(qa_status)} années, toutes OK") if not bad else T("failing years: ", "années en échec : ") + ", ".join(bad)))
        unc = sum(int(float(d.get("Unclassified_pixels", 0) or 0)) for d in qa_status.values())
        checks.append((T("No unclassified pixel inside the study area", "Aucun pixel non classé dans la zone d'étude"), "PASS" if unc == 0 else "FAIL", f"{unc} px"))
        gaps = [abs(sr_num(d.get("Raster_minus_Polygon_percent"), 0)) for d in qa_status.values()]
        checks.append((T("Raster vs polygon study-area difference (indicator)", "Écart raster / polygone de la zone d'étude (indicateur)"), "PASS" if max(gaps) <= 0.5 else "WARN", f"max {max(gaps):.3f} %"))
    else:
        checks.append((T("Area QA files", "Fichiers de contrôle de surface"), "FAIL", "Area_QA_<year>.csv missing"))
    if len(tot) > 1:
        spread = (max(tot.values()) - min(tot.values())) / max(tot.values()) * 100
        checks.append((T("Same study area in every year", "Même zone d'étude chaque année"), "PASS" if spread <= 0.01 else "WARN", f"{spread:.4f} %"))
    metas = []
    fills = []
    for p in find(r"^Metadata_\d{4}\.json$"):
        try:
            with open(p, encoding="utf-8") as f:
                m = json.load(f)
        except Exception:
            continue
        stk = m.get("source_stack", "")
        metas.append([m.get("year"), m.get("version"), os.path.basename(str(stk)) if stk else "", m.get("rf_estimators"), m.get("rf_max_depth"), m.get("rf_min_samples_leaf"), m.get("random_state"), m.get("validation_fraction"), len(m.get("implausible_review") or {})])
        fi = m.get("fill") or {}
        if isinstance(fi, dict) and fi:
            fills.append((m.get("year"), fi))
    mt = [["Year", "Version", "Source stack", "RF trees", "RF max depth", "RF min leaf", "Random state", "Validation fraction", T("Reviewed stages", "Étapes revues")]] + metas if metas else []
    if metas:
        checks.append((T("Reproducibility: random-forest parameters and seed stored per year", "Reproductibilité : paramètres du Random Forest et graine enregistrés par année"), "PASS", T(f"{len(metas)} Metadata files", f"{len(metas)} fichiers Metadata")))
    sebk = [pv[y].get("Sebkha") for y in years if pv[y].get("Sebkha") is not None]
    if len(sebk) > 1:
        checks.append((T("Sebkha fixed in time (design rule)", "Sebkha fixe dans le temps (règle de conception)"), "INFO", T(f"{min(sebk):,.1f}–{max(sebk):,.1f} ha: constant by construction, not an observation", f"{min(sebk):,.1f}–{max(sebk):,.1f} ha : constante par construction, pas une observation")))
    vals = []
    for p in find(r"^Validation_\d{4}_Stage\d+\.txt$")[:12]:
        with open(p, encoding="utf-8", errors="replace") as f:
            vals.append(os.path.basename(p) + "\n" + "".join(f.readlines()[:12]))
    maps = []
    for y in years:
        lm = [q for q in find(rf"^LULC_.+_{y}\.tif$") if not any(s in q for s in ("_Original", "_Edited"))]
        if lm:
            png = sr_quicklook(lm[0], os.path.join(output_dir, "_temp", f"lulc_{y}.png"), {1: ("#dc3232", "Built-up"), 2: ("#648cd2", "Water"), 3: ("#d6e6f5", "Sebkha"), 4: ("#b9c3cd", "Bareland / Rock"), 5: ("#ffe182", "Cropland"), 6: ("#f0af00", "Fallow"), 7: ("#87b978", "Forest"), 8: ("#64f58c", "Rangeland")}, title=f"LULC {y}", max_px=900)
            if png:
                maps.append((f"LULC {y}", png))
    sections = [
        {"id": "areas", "title": T("Class areas by year", "Surfaces par classe et par année"), "intro": T("Areas are map areas (pixel counts inside the study area).", "Les surfaces sont des surfaces cartographiques (comptage de pixels dans la zone d'étude)."), "tables": [(T("Area (ha)", "Surface (ha)"), tb)]},
        {"id": "qa", "title": T("Area quality control", "Contrôle de surface"), "tables": [("Area_QA", qa_rows)]},
        {"id": "meta", "title": T("Method parameters per year", "Paramètres de la méthode par année"), "intro": T("Hierarchical rule-based classification with a Random Forest at each stage; the same parameters and seed are stored for every year.", "Classification hiérarchique à règles avec un Random Forest à chaque étape ; les mêmes paramètres et la même graine sont enregistrés pour chaque année."), "tables": [("Metadata", mt)]},
        {"id": "val", "title": T("Internal validation of the random forest (hold-out fraction)", "Validation interne du Random Forest (fraction de contrôle)"), "intro": T("Internal hold-out validation only: it is NOT the independent accuracy assessment, which is stage 05B.", "Validation interne seulement : ce n'est PAS l'évaluation indépendante de l'exactitude, qui est l'étape 05B."), "pre": "\n\n".join(vals)},
        {"id": "maps", "title": T("Maps", "Cartes"), "images": maps}]
    L = [T("The classification is not independently validated here: use stages 05A–05B for accuracy and error-adjusted areas before interpreting changes.", "La classification n'est pas validée de façon indépendante ici : utiliser les étapes 05A–05B (exactitude et surfaces corrigées) avant d'interpréter les changements."),
         T("A drought year can change the vegetation state (failed crops, sparse rangeland) and produce spurious Cropland/Fallow/Bareland transitions: check the climate context of every mapped year (stage 04B).", "Une année de sécheresse peut modifier l'état de la végétation (cultures échouées, parcours clairsemés) et produire de fausses transitions Cropland/Fallow/Bareland : vérifier le contexte climatique de chaque année (étape 04B)."),
         T("Sebkha is imposed from a stable mask: its area is constant by construction.", "La Sebkha est imposée par un masque stable : sa surface est constante par construction."),
         T("Landsat sensors differ (L5, L7, L8, L9): inter-sensor NDVI differences can create apparent change.", "Les capteurs Landsat diffèrent (L5, L7, L8, L9) : les écarts de NDVI entre capteurs peuvent créer un changement apparent.")]
    A = [T("Prepare the Landsat stacks of the new area (one folder per year named S_<year>) with the same band order; set the study-area shapefile.", "Préparer les piles Landsat de la nouvelle zone (un dossier par année nommé S_<année>) avec le même ordre de bandes ; indiquer le shapefile de la zone."),
         T("Set AREA_TAG at the top of the script (maps are written as LULC_<AREA_TAG>_<year>.tif).", "Régler AREA_TAG en tête de script (les cartes sont écrites LULC_<AREA_TAG>_<année>.tif)."),
         T("Provide training samples per stage and review the stage thresholds visually; the presets of a neighbouring year are reused.", "Fournir les échantillons d'apprentissage par étape et revoir visuellement les seuils ; les presets d'une année voisine sont réutilisés."),
         T("Adapt the legend (8 classes) and the stable-class masks (Sebkha, Built-up) to the landscape of the new area.", "Adapter la légende (8 classes) et les masques de classes stables (Sebkha, Bâti) au paysage de la nouvelle zone.")]
    R = ["Breiman, L. (2001). Random forests. Machine Learning 45, 5–32.", "Olofsson, P. et al. (2014). Good practices for estimating area and assessing accuracy of land change. Remote Sensing of Environment 148, 42–57.", "UNCCD. Good Practice Guidance for SDG Indicator 15.3.1 (version 2) and its Addendum."]
    spec = {"stage": "03", "title": T("Land-use / land-cover classification", "Classification de l'occupation / utilisation du sol"), "subtitle": T("Hierarchical rules + Random Forest, per year", "Règles hiérarchiques + Random Forest, par année"), "lang": lang, "area": area_name, "started": t0, "out_dir": output_dir,
            "params": params, "inputs": [], "summary": summary, "checks": checks, "sections": sections, "limits": L, "adapt": A, "references": R}
    path = os.path.join(output_dir, "Stage_Report_03_Classification.html")
    write_stage_report(path, spec)
    import shutil
    shutil.rmtree(os.path.join(output_dir, "_temp"), ignore_errors=True)
    log("[Rapport HTML] " + path)
    return path
# <<< STAGE_BUILDER_END
import glob
import re
import csv
import time
import json
import shutil
import warnings
import numpy as np
from scipy.ndimage import (
    binary_dilation, binary_closing,
    binary_fill_holes, generate_binary_structure,
    distance_transform_edt, uniform_filter
)
from osgeo import gdal, ogr, osr

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import confusion_matrix, classification_report, accuracy_score, cohen_kappa_score, f1_score, balanced_accuracy_score, matthews_corrcoef
    from sklearn.inspection import permutation_importance
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    MATPLOTLIB_AVAILABLE = True
except Exception:
    MATPLOTLIB_AVAILABLE = False

from qgis.PyQt.QtCore import Qt, QVariant, QTimer, QEventLoop

# PyQt/QGIS enum compatibility.
try:
    _QtOrientation = Qt.Orientation
except AttributeError:
    # Qt6/PyQt6-compatible numeric enum values; Qt.Horizontal/Vertical
    # are absent in some QGIS Python bindings.
    class _QtOrientationCompat:
        Horizontal = 1
        Vertical = 2
    Qt.Orientation = _QtOrientationCompat

# ---- Qt enum compatibility used by the RF attribute table ----
def _qt_enum_compat(group_name, member_name, legacy_name, default):
    try:
        group = getattr(Qt, group_name)
        return getattr(group, member_name)
    except Exception:
        try:
            return getattr(Qt, legacy_name)
        except Exception:
            return default

QT_DISPLAY_ROLE = _qt_enum_compat("ItemDataRole", "DisplayRole", "DisplayRole", 0)
QT_USER_ROLE = _qt_enum_compat("ItemDataRole", "UserRole", "UserRole", 256)
QT_ITEM_IS_EDITABLE = _qt_enum_compat("ItemFlag", "ItemIsEditable", "ItemIsEditable", 2)
QT_ASCENDING = _qt_enum_compat("SortOrder", "AscendingOrder", "AscendingOrder", 0)
QT_DESCENDING = _qt_enum_compat("SortOrder", "DescendingOrder", "DescendingOrder", 1)

from qgis.PyQt.QtWidgets import QDialog, QMessageBox      # DOIVENT être importés avant les constantes de compatibilité ci-dessous (le grand import complet est plus bas)

# ---- QDialog result enum compatibility (PyQt5/PyQt6/QGIS) ----
try:
    QDIALOG_ACCEPTED = QDialog.DialogCode.Accepted
    QDIALOG_REJECTED = QDialog.DialogCode.Rejected
except Exception:
    QDIALOG_ACCEPTED = getattr(QDialog, "Accepted", 1)
    QDIALOG_REJECTED = getattr(QDialog, "Rejected", 0)


# ---- QMessageBox enum compatibility ----
def _qmb_button(name, legacy_name=None, default=None):
    try:
        return getattr(QMessageBox.StandardButton, name)
    except Exception:
        try:
            return getattr(QMessageBox, legacy_name or name)
        except Exception:
            return default

QMB_YES = _qmb_button("Yes", "Yes", 0x00004000)
QMB_NO = _qmb_button("No", "No", 0x00010000)
QMB_OK = _qmb_button("Ok", "Ok", 0x00000400)
QMB_CANCEL = _qmb_button("Cancel", "Cancel", 0x00400000)

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QFileDialog, QGroupBox, QGridLayout,
    QTextEdit, QScrollArea, QWidget, QRadioButton, QCheckBox, QSplitter,
    QComboBox, QInputDialog, QTableWidget, QTableWidgetItem, QProgressBar, QSpinBox,
    QDoubleSpinBox, QButtonGroup, QAbstractItemView
)
from qgis.gui import QgsMapCanvas, QgsMapToolEmitPoint, QgsMapToolPan, QgsMapToolZoom, QgsRubberBand
from qgis.core import (
    QgsProject, QgsRasterLayer, QgsVectorLayer, QgsFeature, QgsGeometry,
    QgsPointXY, QgsField, QgsColorRampShader, QgsRasterShader,
    QgsSingleBandPseudoColorRenderer, QgsMultiBandColorRenderer, QgsWkbTypes, QgsDistanceArea,
    QgsSpatialIndex, QgsCoordinateTransform
)
from qgis.PyQt.QtGui import QColor

# ====================== CONFIG ======================
# Pixel area is calculated from the raster geotransform; this constant is only a fallback.
PIXEL_HA = 0.09
TARGET_YEARS = ["1985", "2000", "2007", "2015", "2020", "2025"]
PROCESS_ORDERS = ("ascending", "descending")
PROCESS_ORDER = "ascending"       # ordre de traitement des années : « ascending » = de la plus ANCIENNE à la plus RÉCENTE (2000 -> 2025) ; « descending » = l'inverse. Réglé dans la fenêtre de démarrage.
RF_N_ESTIMATORS = 300
RF_MAX_DEPTH = 18
RF_MIN_SAMPLES_LEAF = 2
RF_RANDOM_STATE = 42
# QGIS-safe: do not spawn joblib/multiprocessing workers inside the QGIS Python process.
RF_N_JOBS = 1
VALIDATION_FRACTION = 0.30
MIN_POLYGONS_PER_CLASS_FOR_SPATIAL_VALIDATION = 2

# Règle métier : aucun Cropland(5) ou Fallow(6) à l’intérieur de la délimitation
# forestière de référence. La délimitation est fournie par un Shapefile polygonal.
FOREST_BUFFER_PX = 0

# (Les tables STAGE_FEATURES / STAGE_POSITIVE / STAGE_NEGATIVE sont définies UNE seule fois, plus bas, avec la numérotation actuelle des étapes 1-8.)
RF_LAST_CONFIDENCE = None

CLASS_NAMES = {
    1: "Built-up",
    2: "Water",
    3: "Sebkha",
    4: "Bareland / Rock",
    5: "Cropland",
    6: "Fallow",
    7: "Forest",
    8: "Rangeland"
}

CLASS_COLORS = {
    1: QColor(220, 50, 50),
    2: QColor(100, 140, 210),
    3: QColor(214, 230, 245),
    4: QColor(185, 195, 205),
    5: QColor(255, 225, 130),
    6: QColor(240, 175, 0),
    7: QColor(135, 185, 120),
    8: QColor(100, 245, 140)
}

all_classes = sorted(CLASS_NAMES.keys())

# ====================== INDICATOR SETS ======================
# Format: {stage_num: {"Grok": {...}, "ChatGPT": {...}, "Google": {...}, "Original": {...}}}
# Each set: {key: (label, default_value, guide_note)}

INDICATOR_SETS = {
    1: {  # Vegetated vs Non-Vegetated
        "Grok": {
            "s1_msavi_min": ("1. Apr_MSAVI2 min", 0.12, "🔴 Le plus fort"),
            "s1_ndvi_min": ("2. Apr_NDVI min", 0.18, "🔴"),
            "s1_dbsi_max": ("3. Apr_DBSI max", 0.20, "🟠"),
            "s1_tcg_min": ("4. Apr_TC_Greenness min", 0.05, "🟠"),
            "s1_amp_min": ("5. Amplitude min", 0.05, "🟡")
        },
        "ChatGPT": {
            "s1_ndvi_min": ("1. Apr_NDVI min", 0.18, ""),
            "s1_msavi_min": ("2. Apr_MSAVI2 min", 0.12, ""),
            "s1_savi_min": ("3. Apr_SAVI min", 0.10, ""),
            "s1_jul_ndvi_min": ("4. Jul_NDVI min", 0.08, ""),
            "s1_delta_min": ("5. Delta_NDVI min", 0.05, "")
        },
        "Google": {
            "s1_msavi_min": ("1. Apr_MSAVI2 min", 0.12, "Important"),
            "s1_ndvi_min": ("2. Apr_NDVI min", 0.18, ""),
            "s1_tcg_min": ("3. Apr_TC_Greenness min", 0.05, ""),
            "s1_ndmi_min": ("4. Apr_NDMI min", -0.10, ""),
            "s1_amp_min": ("5. Amplitude min", 0.05, "")
        },
        "Original": {
            "s1_msavi_min": ("1. MSAVI2 Printemps min", 0.12, ""),
            "s1_ndvi_min": ("2. NDVI Printemps min", 0.18, ""),
            "s1_bsi_max": ("3. BSI Printemps max", 0.22, ""),
            "s1_ndmi_min": ("4. NDMI Printemps min", -0.12, ""),
            "s1_amp_min": ("5. Amplitude min", 0.05, "")
        }
    },
    2: {  # Water
        "Grok": {
            "wat_mndwi_min": ("1. Apr_MNDWI min", 0.00, "🔴"),
            "wat_ndwi_min": ("2. Apr_NDWI min", 0.05, "🔴"),
            "wat_jul_mndwi_min": ("3. Jul_MNDWI min", 0.00, "🟠"),
            "wat_jul_ndwi_min": ("4. Jul_NDWI min", 0.00, "🟠"),
            "wat_nir_max": ("3. Apr_NIR max", 0.15, "🟠"),
            "wat_msavi_max": ("4. Apr_MSAVI2 max", 0.05, "🟡")
        },
        "ChatGPT": {
            "wat_mndwi_min": ("1. Apr_MNDWI min", 0.00, ""),
            "wat_ndwi_min": ("2. Apr_NDWI min", 0.05, ""),
            "wat_jul_mndwi_min": ("3. Jul_MNDWI min", 0.00, ""),
            "wat_jul_ndwi_min": ("4. Jul_NDWI min", 0.00, ""),
            "wat_ndvi_max": ("3. Apr_NDVI max", 0.05, ""),
            "wat_swir1_max": ("4. Apr_SWIR1 max", 0.20, "")
        },
        "Google": {
            "wat_mndwi_min": ("1. Apr_MNDWI min", 0.00, "Important"),
            "wat_ndwi_min": ("2. Apr_NDWI min", 0.05, ""),
            "wat_jul_mndwi_min": ("3. Jul_MNDWI min", 0.00, ""),
            "wat_jul_ndwi_min": ("4. Jul_NDWI min", 0.00, ""),
            "wat_nir_max": ("5. Apr_NIR max", 0.15, ""),
            "wat_blue_max": ("4. Apr_BLUE max", 0.20, ""),
            "wat_tir_max": ("5. Apr_TIR max", 0.30, "")
        },
        "Original": {
            "wat_ndwi_min": ("1. NDWI min", 0.10, ""),
            "wat_nir_max": ("2. NIR max", 0.15, ""),
            "wat_jul_mndwi_min": ("3. Jul_MNDWI min", 0.00, ""),
            "wat_jul_ndwi_min": ("4. Jul_NDWI min", 0.00, ""),
            "wat_ndvi_max": ("5. NDVI max", 0.05, ""),
            "wat_msavi_max": ("4. MSAVI2 max", 0.05, "")
        }
    },
    3: {  # Built-up
        "Grok": {
            "bu_ndbi_min": ("1. Apr_NDBI min", 0.05, "🔴"),
            "bu_dbsi_min": ("2. Apr_DBSI min", 0.10, "🔴"),
            "bu_tcb_min": ("3. Apr_TC_Brightness min", 0.20, "🟠"),
            "bu_msavi_max": ("4. Apr_MSAVI2 max", 0.10, "🟡")
        },
        "ChatGPT": {
            "bu_ndbi_min": ("1. Apr_NDBI min", 0.05, ""),
            "bu_dbsi_min": ("2. Apr_DBSI min", 0.10, ""),
            "bu_swir1_min": ("3. Apr_SWIR1 min", 0.15, ""),
            "bu_swir2_min": ("4. Apr_SWIR2 min", 0.10, ""),
            "bu_tex_min": ("5. Texture_Variance min", 5.0, "")
        },
        "Google": {
            "bu_ndbi_min": ("1. Apr_NDBI min", 0.05, "Important"),
            "bu_dbsi_min": ("2. Apr_DBSI min", 0.10, ""),
            "bu_tcb_min": ("3. Apr_TC_Brightness min", 0.20, ""),
            "bu_swir1_min": ("4. Apr_SWIR1 min", 0.15, ""),
            "bu_tex_min": ("5. Texture_Variance min", 5.0, "")
        },
        "Original": {
            "bu_ndbi_min": ("1. NDBI min", 0.05, ""),
            "bu_msavi_max": ("2. MSAVI2 max", 0.10, ""),
            "bu_bsi_min": ("3. BSI min", 0.15, ""),
            "bu_ndvi_max": ("4. NDVI max", 0.15, "")
        }
    },
    4: {  # Sebkha
        "Grok": {
            "seb_tcb_min": ("1. Apr_TC_Brightness min", 0.30, "🔴"),
            "seb_dbsi_min": ("2. Apr_DBSI min", 0.20, "🔴"),
            "seb_msavi_max": ("3. Apr_MSAVI2 max", 0.08, "🟠"),
            "seb_ndvi_max": ("4. Apr_NDVI max", 0.10, "🟡")
        },
        "ChatGPT": {
            "seb_mndwi_min": ("1. Apr_MNDWI min", -0.10, ""),
            "seb_dbsi_min": ("2. Apr_DBSI min", 0.20, ""),
            "seb_swir1_min": ("3. Apr_SWIR1 min", 0.25, ""),
            "seb_swir2_min": ("4. Apr_SWIR2 min", 0.20, ""),
            "seb_ratio_min": ("5. B5/B4 min", 1.2, "")
        },
        "Google": {
            "seb_ratio_min": ("1. B7/B4 min", 1.3, "Important"),
            "seb_swir2_min": ("2. Apr_SWIR2 min", 0.20, ""),
            "seb_jul_ndvi_max": ("3. Jul_NDVI max", 0.08, ""),
            "seb_mndwi_min": ("4. Apr_MNDWI min", -0.05, ""),
            "seb_green_min": ("5. Jul_GREEN min", 0.15, "")
        },
        "Original": {
            "seb_bsi_min": ("1. BSI min", 0.25, ""),
            "seb_msavi_max": ("2. MSAVI2 max", 0.08, ""),
            "seb_ndvi_max": ("3. NDVI max", 0.10, ""),
            "seb_ndmi_max": ("4. NDMI max", -0.05, "")
        }
    },
    5: {  # Forest / Matorral
        "Grok": {
            "f_jul_msavi_min": ("1. Jul_MSAVI2 min", 0.12, "🔴"),
            "f_jul_ndvi_min": ("2. Jul_NDVI min", 0.15, "🔴"),
            "f_amp_max": ("3. Amplitude max (Faible)", 0.22, "🟠"),
            "f_jul_tcg_min": ("4. Jul_TC_Greenness min", 0.08, "🟡")
        },
        "ChatGPT": {
            "f_apr_ndvi_min": ("1. Apr_NDVI min", 0.20, ""),
            "f_apr_msavi_min": ("2. Apr_MSAVI2 min", 0.15, ""),
            "f_apr_ndmi_min": ("3. Apr_NDMI min", 0.00, ""),
            "f_jul_ndmi_min": ("4. Jul_NDMI min", -0.05, ""),
            "f_nbr_min": ("5. Apr_NBR min", 0.10, "")
        },
        "Google": {
            "f_jul_ndvi_min": ("1. Jul_NDVI min", 0.15, "Important"),
            "f_amp_max": ("2. Amplitude max", 0.22, ""),
            "f_jul_msavi_min": ("3. Jul_MSAVI2 min", 0.12, ""),
            "f_apr_tcg_min": ("4. Apr_TC_Greenness min", 0.10, ""),
            "f_tex_min": ("5. Texture_Variance min", 3.0, "")
        },
        "Original": {
            "f_amp_max": ("1. Amplitude max", 0.25, ""),
            "f_ndvi_sm_min": ("2. NDVI Été min", 0.10, ""),
            "f_msavi_sm_min": ("3. MSAVI Été min", 0.10, ""),
            "f_ndvi_sp_min": ("4. NDVI Printemps min", 0.15, "")
        }
    },
    6: {  # Cropland
        "Grok": {
            "crop_amp_min": ("1. Amplitude min (Élevé)", 0.20, "🔴"),
            "crop_msavi_sp_min": ("2. Apr_MSAVI2 min", 0.22, "🔴"),
            "crop_ndvi_sp_min": ("3. Apr_NDVI min", 0.30, "🟠"),
            "crop_jul_msavi_max": ("4. Jul_MSAVI2 max", 0.12, "🟠"),
            "crop_jul_dbsi_min": ("5. Jul_DBSI min", 0.10, "🟡")
        },
        "ChatGPT": {
            "crop_ndvi_sp_min": ("1. Apr_NDVI min", 0.30, ""),
            "crop_msavi_sp_min": ("2. Apr_MSAVI2 min", 0.22, ""),
            "crop_ndmi_sp_min": ("3. Apr_NDMI min", 0.05, ""),
            "crop_jul_ndvi_max": ("4. Jul_NDVI max", 0.15, ""),
            "crop_jul_msavi_max": ("5. Jul_MSAVI2 max", 0.12, ""),
            "crop_delta_min": ("6. Delta_NDVI min", -0.15, ""),
            "crop_amp_min": ("7. Amplitude min", 0.20, "")
        },
        "Google": {
            "crop_delta_min": ("1. Delta_NDVI min", -0.15, "Important"),
            "crop_amp_min": ("2. Amplitude min", 0.20, ""),
            "crop_ndvi_sp_min": ("3. Apr_NDVI min", 0.30, ""),
            "crop_jul_ndvi_max": ("4. Jul_NDVI max", 0.12, ""),
            "crop_evi_min": ("5. Apr_EVI min", 0.25, "")
        },
        "Original": {
            "crop_amp_min": ("1. Amplitude min", 0.18, ""),
            "crop_msavi_sp_min": ("2. MSAVI2 Printemps min", 0.20, ""),
            "crop_ndvi_sp_min": ("3. NDVI Printemps min", 0.28, "")
        }
    },
    7: {  # Fallow vs Rangeland
        "Grok": {
            "rang_msavi_min": ("1. Apr_MSAVI2 min (Rang)", 0.05, "🔴"),
            "rang_msavi_max": ("2. Apr_MSAVI2 max (Rang)", 0.18, "🔴"),
            "fal_jul_msavi_max": ("3. Jul_MSAVI2 max (Fal)", 0.12, "🟠"),
            "fal_dbsi_min": ("4. Jul_DBSI min (Fal)", 0.12, "🟠"),
            "fal_amp": ("5. Amplitude", 0.15, "🟡")
        },
        "ChatGPT": {
            "rang_msavi_min": ("1. Apr_MSAVI2 min", 0.05, ""),
            "rang_ndvi_min": ("2. Apr_NDVI min", 0.08, ""),
            "fal_jul_msavi_max": ("3. Jul_MSAVI2 max", 0.12, ""),
            "fal_jul_ndvi_max": ("4. Jul_NDVI max", 0.15, ""),
            "fal_delta": ("5. Delta_NDVI", -0.05, ""),
            "fal_dbsi_min": ("6. Apr_DBSI min", 0.10, "")
        },
        "Google": {
            "fal_jul_msavi_max": ("1. Jul_MSAVI2 max", 0.12, "Important"),
            "rang_msavi_min": ("2. Apr_MSAVI2 min", 0.05, ""),
            "fal_dbsi_min": ("3. Apr_DBSI min", 0.12, ""),
            "fal_swir1_min": ("4. Jul_SWIR1 min", 0.15, ""),
            "fal_amp": ("5. Amplitude", 0.15, "")
        },
        "Original": {
            "rang_msavi_min": ("1. Rangeland MSAVI min", 0.05, ""),
            "rang_msavi_max": ("2. Rangeland MSAVI max", 0.18, ""),
            "fal_msavi_min": ("3. Fallow MSAVI min", 0.08, ""),
            "fal_msavi_max": ("4. Fallow MSAVI max", 0.22, ""),
            "fal_bsi_min": ("5. Fallow BSI min", 0.10, "")
        }
    }
}

def _make_free_desktop_window(dlg):
    """UI-only: force a real top-level Windows window with working Minimize/Maximize.

    Important: do not keep the QGIS/main-window parent and do not use any
    modal/window-stays-on-top flag.  The nested event loop used by show_dialog
    keeps the classification flow synchronous while the Windows shell remains
    accessible.
    """
    try:
        dlg.setWindowModality(Qt.NonModal)
    except Exception:
        pass
    try:
        # Detach from QGIS so Windows treats this as a normal top-level window.
        dlg.setParent(None)
    except Exception:
        pass
    try:
        flags = (
            Qt.Window
            | Qt.WindowTitleHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowCloseButtonHint
            | Qt.WindowMinMaxButtonsHint
        )
        # Explicitly remove any stale always-on-top/tool/modal hints.
        try:
            flags &= ~Qt.WindowStaysOnTopHint
        except Exception:
            pass
        try:
            flags &= ~Qt.Tool
        except Exception:
            pass
        dlg.setWindowFlags(flags)
    except Exception:
        try:
            dlg.setWindowFlags(
                dlg.windowFlags()
                | Qt.Window
                | Qt.WindowMinimizeButtonHint
                | Qt.WindowMaximizeButtonHint
                | Qt.WindowCloseButtonHint
                | Qt.WindowSystemMenuHint
                | Qt.WindowMinMaxButtonsHint
            )
        except Exception:
            pass
    for _hint in ("WindowMinimizeButtonHint", "WindowMaximizeButtonHint", "WindowCloseButtonHint", "WindowSystemMenuHint", "WindowTitleHint"):     # renfort : certaines versions de Qt / du gestionnaire de fenêtres ignorent setWindowFlags seul
        try:
            dlg.setWindowFlag(getattr(Qt, _hint), True)
        except Exception:
            pass
    try:
        dlg.setAttribute(Qt.WA_DeleteOnClose, False)
    except Exception:
        pass
    try:
        dlg.setSizeGripEnabled(True)
    except Exception:
        pass
    return dlg


WINDOWS_MAXIMIZED = True        # fenêtres de travail ouvertes en PLEIN ÉCRAN (False = taille normale)


def _window_bar(w, fullscreen_button=True):
    """
    Barre fine en haut de la fenêtre : « 🗕 Réduire » et « ⛶ Plein écran / 🗗 Restaurer ». Ces boutons fonctionnent même quand le gestionnaire de fenêtres n'affiche pas
    les boutons de la barre de titre. Ajoutée UNE seule fois ; sans effet si la fenêtre n'a pas de disposition verticale.
    """
    if getattr(w, "_wbar_added", False):
        return
    lay = w.layout() if hasattr(w, "layout") else None
    if lay is None or not hasattr(lay, "insertLayout"):
        return
    bar = QHBoxLayout()
    bar.addStretch(1)
    b_min = QPushButton("🗕 Réduire")
    b_min.setToolTip("Réduire la fenêtre dans la barre des tâches.")
    b_min.clicked.connect(lambda *_: w.showMinimized())
    bar.addWidget(b_min)
    w._wbar_max_button = None
    if fullscreen_button:
        b_max = QPushButton("🗗 Restaurer" if getattr(w, "isMaximized", lambda: False)() else "⛶ Plein écran")
        b_max.setToolTip("Basculer entre le plein écran et la taille normale.")

        def _toggle(*_a):
            if w.isMaximized():
                w.showNormal()
                b_max.setText("⛶ Plein écran")
            else:
                w.showMaximized()
                b_max.setText("🗗 Restaurer")
        b_max.clicked.connect(_toggle)
        bar.addWidget(b_max)
        w._wbar_max_button = b_max
    lay.insertLayout(0, bar)
    w._wbar_added = True


def present_window(w, maximize=None, fullscreen_button=True):
    """
    Présente une fenêtre : drapeaux (réduire / agrandir / fermer), barre « Réduire / Plein écran » et, par défaut, OUVERTURE EN PLEIN ÉCRAN (WINDOWS_MAXIMIZED).
    maximize = False : taille normale (fenêtres secondaires placées à côté de la carte) ; None : réglage global ou attribut START_MAXIMIZED de la classe.
    """
    _make_free_desktop_window(w)
    _window_bar(w, fullscreen_button)
    mx = getattr(w, "START_MAXIMIZED", None) if maximize is None else maximize
    mx = WINDOWS_MAXIMIZED if mx is None else bool(mx)
    if mx:
        w.showMaximized()
        b = getattr(w, "_wbar_max_button", None)
        if b is not None:
            b.setText("🗗 Restaurer")
    else:
        w.show()
    try:
        w.raise_()
        w.activateWindow()
    except Exception:
        pass
    return w


def make_collapsible_section(owner, title, box, summary_fn=None, expanded=False):
    """
    Section REPLIABLE : un bouton d'en-tête « ▶ Titre : résumé » (« ▼ » quand elle est ouverte) au-dessus du groupe `box`, qui n'est visible que lorsque la section est ouverte.
    Les widgets du groupe restent vivants (leurs valeurs servent même fermés) ; le résumé de l'en-tête (mode, fichier...) reste lisible quand la section est fermée.
    Retourne le conteneur à ajouter à la disposition ; owner._collapsibles garde les sections pour rafraîchir les en-têtes.
    """
    container = QWidget()
    v = QVBoxLayout(container)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(2)
    btn = QPushButton("")
    btn.setStyleSheet("text-align:left;font-weight:bold;padding:5px 8px;")
    btn.setToolTip("Cliquer pour ouvrir / fermer cette section.")
    v.addWidget(btn)
    box.setTitle("")                                   # le titre est dans le bouton
    v.addWidget(box)
    sec = {"title": title, "box": box, "btn": btn, "summary": summary_fn, "expanded": bool(expanded)}

    def refresh():
        txt = ("▼ " if sec["expanded"] else "▶ ") + title
        if summary_fn is not None:
            try:
                s = summary_fn()
            except Exception:
                s = ""
            if s:
                txt += " : " + s
        btn.setText(txt)

    def set_expanded(on):
        sec["expanded"] = bool(on)
        box.setVisible(sec["expanded"])
        refresh()
    btn.clicked.connect(lambda *_: set_expanded(not sec["expanded"]))
    sec["refresh"], sec["set_expanded"] = refresh, set_expanded
    if not hasattr(owner, "_collapsibles"):
        owner._collapsibles = []
    owner._collapsibles.append(sec)
    set_expanded(expanded)
    return container


def refresh_collapsible_headers(owner):
    for sec in getattr(owner, "_collapsibles", []) or []:
        try:
            sec["refresh"]()
        except Exception:
            pass


def show_dialog(dlg):
    """Show dialog without blocking QGIS/Windows desktop.

    We intentionally do NOT use QDialog.exec()/exec_(), because that creates a
    modal dialog and was the reason the user could not reach QGIS/desktop. A
    nested QEventLoop preserves the existing synchronous classification flow:
    the script continues only after the dialog is accepted/rejected/closed.
    """
    loop = QEventLoop()

    def _finish(*_args):
        try:
            loop.quit()
        except Exception:
            pass

    try:
        dlg.finished.connect(_finish)
    except Exception:
        pass

    present_window(dlg)                 # drapeaux + barre Réduire / Plein écran + ouverture en plein écran

    loop.exec_() if hasattr(loop, 'exec_') else loop.exec()
    return getattr(dlg, 'result', lambda: 0)() if hasattr(dlg, 'result') else 0

class StageBackRequested(Exception):
    """Signal interne contrôlé pour le bouton « Précédent »."""
    def __init__(self, stage_num):
        self.stage_num = int(stage_num)
        super().__init__(f"Retour demandé depuis l'étape {self.stage_num}.")


# ====================== CHECKPOINT / REPRISE ======================
# Le point de reprise est volontairement indépendant des seuils : il mémorise
# uniquement les années complètement terminées et leurs sorties finales.
# Ainsi, si 2025 échoue, un nouveau lancement peut reprendre à 2025 sans
# recalculer 1985..2020.
CHECKPOINT_VERSION = "LULC_V17_FOREST_8CLASSES_BARE_LAST"
CHECKPOINT_FILENAME = "LULC_Run_Checkpoint.json"

def _checkpoint_path(output_dir):
    return os.path.join(output_dir, CHECKPOINT_FILENAME)

def load_checkpoint(output_dir):
    path = _checkpoint_path(output_dir)
    if not os.path.exists(path):
        return {"version": CHECKPOINT_VERSION, "completed_years": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("version") != CHECKPOINT_VERSION:
            print("[Checkpoint] ancien checkpoint ignoré (version différente).")
            return {"version": CHECKPOINT_VERSION, "completed_years": []}
        completed = [str(y) for y in data.get("completed_years", [])]
        return {"version": CHECKPOINT_VERSION, "completed_years": completed}
    except Exception as exc:
        print(f"[Checkpoint] lecture impossible, reprise désactivée: {exc}")
        return {"version": CHECKPOINT_VERSION, "completed_years": []}

def save_checkpoint(output_dir, completed_years):
    path = _checkpoint_path(output_dir)
    tmp = path + ".tmp"
    data = {
        "version": CHECKPOINT_VERSION,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "completed_years": [str(y) for y in completed_years]
    }
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception as exc:
        print(f"[Checkpoint] impossible d'enregistrer le point de reprise: {exc}")

LULC_SUBDIR = "LULC"                 # cartes LULC FINALES : un dossier à part
CHANGE_SUBDIR = "Changement"         # cartes et tableaux de CHANGEMENT : un dossier à part


def lulc_dir(output_dir):
    d = os.path.join(output_dir, LULC_SUBDIR)
    os.makedirs(d, exist_ok=True)
    return d


def change_dir(output_dir):
    d = os.path.join(output_dir, CHANGE_SUBDIR)
    os.makedirs(d, exist_ok=True)
    return d


TEMP_SUBDIR = "_temp"                # fichiers de travail (aperçus, masques colorés, fonds) : supprimés au démarrage suivant
ANCHOR_SUBDIR = "Ancre"              # fichiers de transparence de l'ancre
REPORT_SUBDIR = "Rapports"           # rapport HTML de chaque année


def normalize_class_code(code):
    """Code de classe d'un échantillon ou d'un point de référence : l'ancien Matorral (9) est lu comme Forest (7). Point de conversion UNIQUE (entraînement, séparation spatiale, validation)."""
    c = int(code)
    return 7 if c == 9 else c


def normalize_class_array(arr):
    """Même conversion (9 -> 7) pour un tableau de codes ; retourne une copie."""
    a = np.array(arr, copy=True)
    a[a == 9] = 7
    return a


AREA_QA_POLYGON_TOLERANCE = 0.01     # écart relatif toléré entre l'aire du contour vectoriel et celle du contour rastérisé (indicateur, jamais un échec)


def area_qa_assess(admin_pixels, unclassified_inside, nonzero_outside, class_pixels_inside, polygon_ha, raster_ha, tol_rel=AREA_QA_POLYGON_TOLERANCE):
    """
    AREA QA en contrôles SÉPARÉS.
      ÉCHEC DUR (la carte est incomplète ou incohérente) : 1 complétude (aucun pixel administratif non classé) ; 2 limites (aucune classe hors zone) ;
                                                           3 cohérence (les 8 classes SEULES couvrent exactement la zone rastérisée).
      INDICATEUR (jamais un échec) : 4 écart géométrique contour vectoriel / contour rastérisé, relatif ; au-delà de la tolérance : « PASS_AVEC_AVERTISSEMENT »
      (le tracé d'un contour sinueux n'est pas le même objet que sa version en pixels de 30 m).
    """
    checks = {"completeness": int(unclassified_inside) == 0, "boundary": int(nonzero_outside) == 0, "consistency": int(class_pixels_inside) == int(admin_pixels)}
    hard = all(checks.values())
    finite = polygon_ha is not None and np.isfinite(polygon_ha) and polygon_ha > 0
    gap_ha = (raster_ha - polygon_ha) if finite else float("nan")
    gap_pct = (100.0 * gap_ha / polygon_ha) if finite else float("nan")
    geo = "NA" if not finite else ("OK" if abs(gap_pct) <= 100.0 * tol_rel else "WARN")
    status = "FAIL" if not hard else ("PASS_AVEC_AVERTISSEMENT" if geo == "WARN" else "PASS")
    msgs = []
    if not checks["completeness"]:
        msgs.append(f"{int(unclassified_inside):,} pixel(s) de la zone d'étude non classés")
    if not checks["boundary"]:
        msgs.append(f"{int(nonzero_outside):,} pixel(s) classés HORS de la zone d'étude")
    if not checks["consistency"]:
        msgs.append(f"les 8 classes couvrent {int(class_pixels_inside):,} px pour {int(admin_pixels):,} px de zone (codes invalides ?)")
    if geo == "WARN":
        msgs.append(f"écart géométrique du contour {gap_pct:+.2f} % (> {100.0 * tol_rel:g} %) : à documenter, sans effet sur la classification")
    return {"checks": checks, "hard_pass": hard, "geometry": geo, "gap_ha": gap_ha, "gap_percent": gap_pct, "status": status, "messages": msgs}


FILL_WARN_PERCENT = 2.0              # au-delà de cette part de la zone d'étude complétée automatiquement : avertissement (revoir les données / seuils)


def fill_unclassified(lulc, admin_mask):
    """
    Pixels de la zone d'étude encore non classés : classe du plus proche pixel classé (voisin le plus proche) ; ce qui reste (aucun pixel classé du tout) = Bareland (4).
    Hors zone : 0. Retourne (carte complétée, statistiques, carte des pixels complétés : 1 = voisin le plus proche, 2 = repli Bareland). L'entrée n'est pas modifiée.
    """
    out = lulc.copy()
    unresolved = admin_mask & (out == 0)
    seeds = admin_mask & (out > 0)
    n_unres = int(np.count_nonzero(unresolved))
    if n_unres and np.any(seeds):
        rr, cc = distance_transform_edt(~seeds, return_distances=False, return_indices=True)
        out[unresolved] = out[rr[unresolved], cc[unresolved]]
    residual = admin_mask & (out == 0)
    out[residual] = 4
    out[~admin_mask] = 0
    n_res = int(np.count_nonzero(residual))
    code = np.zeros(out.shape, np.uint8)
    code[unresolved] = 1
    code[residual] = 2
    admin_px = int(np.count_nonzero(admin_mask))
    info = {"unresolved_px": n_unres, "nn_filled_px": n_unres - n_res, "bareland_fallback_px": n_res, "admin_px": admin_px,
            "filled_percent": (100.0 * n_unres / admin_px) if admin_px else 0.0}
    return out, info, code


def temp_dir(base):
    d = os.path.join(base, TEMP_SUBDIR)
    os.makedirs(d, exist_ok=True)
    return d


def anchor_dir(output_dir):
    d = os.path.join(output_dir, ANCHOR_SUBDIR)
    os.makedirs(d, exist_ok=True)
    return d


def report_dir(output_dir):
    d = os.path.join(output_dir, REPORT_SUBDIR)
    os.makedirs(d, exist_ok=True)
    return d


def control_dir(output_dir):
    d = os.path.join(output_dir, "Controle")
    os.makedirs(d, exist_ok=True)
    return d


def clean_temp_dir(output_dir):
    """Supprime les fichiers temporaires d'une exécution précédente (au mieux : un fichier ouvert dans QGIS est simplement laissé). Retourne le nombre supprimé."""
    d = os.path.join(output_dir, TEMP_SUBDIR)
    n = 0
    if os.path.isdir(d):
        for f in glob.glob(os.path.join(d, "*")):
            try:
                if os.path.isfile(f):
                    os.remove(f)
                    n += 1
            except Exception:
                pass
    return n


def lulc_map_path(output_dir, year):
    """Chemin de SORTIE de la carte LULC finale d'une année : <résultats>/LULC/LULC_<AREA_TAG>_<année>.tif."""
    return os.path.join(lulc_dir(output_dir), f"LULC_{AREA_TAG}_{year}.tif")


def find_lulc_map(output_dir, year):
    """Carte LULC finale EXISTANTE d'une année : dans LULC/ d'abord, sinon à la racine (résultats produits avant la séparation des dossiers) ; None si absente."""
    name = f"LULC_{AREA_TAG}_{year}.tif"
    for d in (os.path.join(output_dir, LULC_SUBDIR), output_dir):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None


def _load_completed_year_result(year, output_dir):
    """Recharge une année terminée depuis son GeoTIFF final pour une reprise sûre."""
    path = find_lulc_map(output_dir, year)
    if not path:
        return None
    ds = gdal.Open(path, gdal.GA_ReadOnly)
    if ds is None:
        return None
    arr = ds.GetRasterBand(1).ReadAsArray().astype(np.uint8)
    gt = ds.GetGeoTransform()
    prj = ds.GetProjection()
    ds = None
    pxa = pixel_area_ha_from_gt(gt)
    areas = {
        cname: float(np.count_nonzero(arr == cid) * pxa)
        for cid, cname in CLASS_NAMES.items()
    }
    mem = {"year": str(year), "areas": areas}
    return arr, path, gt, prj, mem

def save_thresholds(year, stage, thresholds, output_dir):
    path = os.path.join(output_dir, f"Thresholds_{year}_Stage{stage}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(thresholds, f, indent=4, ensure_ascii=False)
    return path

def load_thresholds(year, stage, output_dir):
    path = os.path.join(output_dir, f"Thresholds_{year}_Stage{stage}.json")
    candidates = [path]
    for cand in candidates:
        if os.path.exists(cand):
            try:
                with open(cand, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            except Exception:
                continue
    return {}


def preset_path(year, stage, output_dir):
    return os.path.join(output_dir, f"Preset_{year}_Stage{stage}.json")


def save_preset(year, stage, output_dir, mode, rf_cfg, thresholds, hi=0.80, lo=0.50, mask_spec=None):
    """Persiste TOUT l'état de calibration d'une étape (mode + RF + seuils + confiance)."""
    if not (year and stage and output_dir):
        return None
    data = {
        "mode": mode,
        "hi": float(hi),
        "lo": float(lo),
        "rf": {
            "shp": rf_cfg.get("shp", ""),
            "field": rf_cfg.get("field", "class"),
        },
        "thresholds": thresholds or {},
    }
    if isinstance(mask_spec, dict) and mask_spec_active(mask_spec):
        data["mask"] = mask_spec          # masque(s) de l'étape (source + rôle, + masque n°2) : rejoués en batch / reprise
    path = preset_path(year, stage, output_dir)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return path
    except Exception:
        return None


def process_order_name(order=None):
    """Ordre de traitement valide : « ascending » (défaut) ou « descending »."""
    o = order or PROCESS_ORDER
    return o if o in PROCESS_ORDERS else "ascending"


def neighbor_years(year, years_order, order=None):
    """Autres années triées de la PLUS PROCHE à la plus éloignée ; à égalité : l'année PRÉCÉDENTE (la plus ancienne) en ordre ascendant, la plus récente en ordre descendant (celle déjà calibrée)."""
    y = int(year)
    asc = process_order_name(order) == "ascending"
    return sorted({str(v) for v in years_order if int(v) != y}, key=lambda s: (abs(int(s) - y), int(s) if asc else -int(s)))


MATORRAL_TO_OPEN_FOREST = {"msavi2_min": "fo_msavi2_min", "msavi2_max": "fo_msavi2_max", "f_apr_ndvi_min": "fo_apr_ndvi_min", "f_amp_max": "fo_amp_max"}


def migrate_stage4_preset(forest_preset, matorral_preset):
    """
    Fusion Forest + Matorral : un ancien preset de l'étape 5 (Matorral, seuils) devient le bloc « forêt claire » (champs fo_*) du preset de l'étape 4,
    s'il n'a pas déjà ce bloc. Les presets en RF / hybride ne sont pas migrés (le RF de l'étape 4 lit les polygones : les codes 9 sont lus comme 7).
    """
    if not isinstance(forest_preset, dict) or not isinstance(matorral_preset, dict):
        return forest_preset
    th = forest_preset.get("thresholds")
    if not isinstance(th, dict) or any(str(k).startswith("fo_") for k in th) or matorral_preset.get("mode", "thresholds") != "thresholds":
        return forest_preset
    th5 = matorral_preset.get("thresholds") or {}
    moved = {new: th5[old] for old, new in MATORRAL_TO_OPEN_FOREST.items() if th5.get(old) is not None}
    if not moved:
        return forest_preset
    out = dict(forest_preset)
    out["thresholds"] = {**th, **moved}
    out["migrated_from_matorral_stage5"] = True
    return out


def _read_preset_file(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            return {}
    return {}


def load_preset(year, stage, output_dir):
    """Retourne le preset dict ou {} s'il est absent. (Les anciens presets à 9 étapes sont renumérotés une fois pour toutes par migrate_presets_to_8_stages.)"""
    if not (year and stage and output_dir):
        return {}
    return _read_preset_file(preset_path(year, stage, output_dir))


PRESET_SCHEME_FILE = "Presets_Scheme.json"
STAGE_OLD_TO_NEW = {1: 1, 2: 2, 3: 3, 4: 4, 6: 5, 7: 6, 8: 7, 9: 8}      # ancienne numérotation (9 étapes, la 5 = Matorral) -> numérotation actuelle (8 étapes)


def migrate_presets_to_8_stages(output_dir):
    """
    Une seule fois par dossier de résultats (marqueur Presets_Scheme.json) : RENUMÉROTE les presets et seuils enregistrés avec l'ancienne numérotation à 9 étapes.
      1. le preset Matorral (ancienne étape 5) est fusionné dans le bloc « forêt claire » du preset de l'étape 4, puis mis de côté (…_Stage5_ancien_Matorral.json) ;
      2. Cropland 6->5, Fallow 7->6, Rangeland 8->7, Bareland 9->8 (fichiers Preset_* et Thresholds_*).
    Retourne le nombre de fichiers renumérotés (0 si déjà fait ou rien à faire).
    """
    if not output_dir or not os.path.isdir(output_dir):
        return 0
    marker = os.path.join(output_dir, PRESET_SCHEME_FILE)
    if os.path.exists(marker):
        return 0
    pat = re.compile(r"^(Preset|Thresholds)_(.+)_Stage(\d+)\.json$")
    groups = {}
    for p in glob.glob(os.path.join(output_dir, "Preset_*_Stage*.json")) + glob.glob(os.path.join(output_dir, "Thresholds_*_Stage*.json")):
        m = pat.match(os.path.basename(p))
        if m:
            groups.setdefault((m.group(1), m.group(2)), {})[int(m.group(3))] = p
    n = 0
    for (kind, year), stages in sorted(groups.items()):
        if kind == "Preset" and 4 in stages and 5 in stages:
            p4 = _read_preset_file(stages[4])
            merged = migrate_stage4_preset(p4, _read_preset_file(stages[5]))
            if merged is not p4:
                with open(stages[4], "w", encoding="utf-8") as f:
                    json.dump(merged, f, indent=4, ensure_ascii=False)
        if 5 in stages:
            os.replace(stages[5], os.path.join(output_dir, f"{kind}_{year}_Stage5_ancien_Matorral.json"))
        for old in (6, 7, 8, 9):
            if old in stages:
                os.replace(stages[old], os.path.join(output_dir, f"{kind}_{year}_Stage{STAGE_OLD_TO_NEW[old]}.json"))
                n += 1
    with open(marker, "w", encoding="utf-8") as f:
        json.dump({"stage_scheme": 2, "stages": "1 Sebkha, 2 Built-up, 3 Water, 4 Forest, 5 Cropland, 6 Fallow, 7 Rangeland, 8 Bareland", "files_renumbered": n}, f, indent=2, ensure_ascii=False)
    return n


def migrate_v16_presets(old_dir, new_dir):
    """Copie les presets (Preset_*_Stage*.json) d'un ancien dossier de résultats V16 (9 classes) vers le nouveau dossier ; retourne le nombre copié."""
    import shutil
    n = 0
    if not (old_dir and new_dir and os.path.isdir(old_dir)):
        return 0
    os.makedirs(new_dir, exist_ok=True)
    for p in sorted(glob.glob(os.path.join(old_dir, "Preset_*_Stage*.json"))):
        dst = os.path.join(new_dir, os.path.basename(p))
        if not os.path.exists(dst):
            shutil.copy2(p, dst)
            n += 1
    return n


def find_previous_preset(year, stage, output_dir, years_order):
    """
    Cherche le preset de l'étape `stage` de l'année VOISINE la plus proche de `year` (années déjà calibrées : en ordre ascendant, ce sont les années plus anciennes ; en ordre descendant, les plus récentes).
    Retourne (année trouvée, preset) ou (None, {}).
    """
    if str(year) not in [str(v) for v in years_order]:
        return None, {}
    for prev in neighbor_years(year, years_order):
        p = load_preset(prev, stage, output_dir)
        if p:
            return prev, p
    return None, {}

def calculate_jm_distance(X1, X2):
    if len(X1) < 2 or len(X2) < 2:
        return 0.0
    m1, m2 = np.mean(X1, axis=0), np.mean(X2, axis=0)
    c1 = np.cov(X1, rowvar=False) + np.eye(X1.shape[1]) * 1e-5
    c2 = np.cov(X2, rowvar=False) + np.eye(X2.shape[1]) * 1e-5
    c = (c1 + c2) / 2.0
    try:
        inv_c = np.linalg.inv(c)
        d_mean = m1 - m2
        t1 = 0.125 * np.dot(np.dot(d_mean, inv_c), d_mean.T)
        log_term = np.linalg.slogdet(c)[1] - 0.5 * (np.linalg.slogdet(c1)[1] + np.linalg.slogdet(c2)[1])
        bhattacharyya = t1 + 0.5 * log_term
        return float(2.0 * (1.0 - np.exp(-np.clip(bhattacharyya, 0, 50))))
    except Exception:
        return float(np.clip(np.linalg.norm(m1 - m2) * 2.0, 0.0, 2.0))

# ====================== MAP TOOLS ======================
class ThresholdSamplingPolygonTool(QgsMapToolEmitPoint):
    def __init__(self, canvas, parent_dialog):
        super().__init__(canvas)
        self.canvas = canvas
        self.dialog = parent_dialog
        self.points = []
        self.rubber_band = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        self.rubber_band.setColor(QColor(0, 188, 212, 110))
        self.rubber_band.setWidth(2)

    def reset_tool(self):
        self.points = []
        self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)

    def canvasPressEvent(self, e):
        btn = e.button()
        pt = self.toMapCoordinates(e.pos())
        is_left = is_right = False
        if hasattr(btn, 'value'):
            is_left = (btn.value == 1)
            is_right = (btn.value == 2)
        elif hasattr(btn, 'name'):
            is_left = 'Left' in str(btn.name)
            is_right = 'Right' in str(btn.name)
        else:
            try:
                val = int(btn)
                is_left = (val == 1)
                is_right = (val == 2)
            except Exception:
                pass
        if is_left:
            self.points.append(pt)
            self.rubber_band.addPoint(pt, True)
            self.rubber_band.show()
            self.dialog.probe_readout.setText(f"📐 Sommets : {len(self.points)}. Clic droit = moyenne.")
        elif is_right:
            if len(self.points) >= 3:
                pts = list(self.points)
                self.reset_tool()
                self.dialog.apply_thresholds_from_polygon(pts)
            else:
                self.dialog.probe_readout.setText("⚠️ Minimum 3 points.")
                self.reset_tool()


class DirectPolygonMapTool(QgsMapToolEmitPoint):
    def __init__(self, canvas, parent_dialog):
        super().__init__(canvas)
        self.canvas = canvas
        self.dialog = parent_dialog
        self.points = []
        self.rubber_band = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        self.rubber_band.setColor(QColor(255, 235, 59, 120))
        self.rubber_band.setWidth(2)

    def reset_tool(self):
        self.points = []
        self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)

    def canvasPressEvent(self, e):
        btn = e.button()
        pt = self.toMapCoordinates(e.pos())
        is_left = is_right = False
        if hasattr(btn, 'value'):
            is_left = (btn.value == 1)
            is_right = (btn.value == 2)
        elif hasattr(btn, 'name'):
            is_left = 'Left' in str(btn.name)
            is_right = 'Right' in str(btn.name)
        else:
            try:
                val = int(btn)
                is_left = (val == 1)
                is_right = (val == 2)
            except Exception:
                pass
        if is_left:
            self.points.append(pt)
            self.rubber_band.addPoint(pt, True)
            self.rubber_band.show()
            self.dialog.probe_readout.setText(f"✏️ Sommet {len(self.points)}. Clic droit = valider.")
        elif is_right:
            if len(self.points) >= 3:
                pts = list(self.points)
                self.reset_tool()
                self.dialog.finish_drawn_polygon(pts)
            else:
                self.dialog.probe_readout.setText("⚠️ Minimum 3 points.")
                self.reset_tool()



# ====================== INDEPENDENT METHOD PREVIEWS ======================
class ClassificationPreviewDialog(QDialog):
    """Fenêtre indépendante de prévisualisation d'une méthode."""

    def __init__(self, title, raster_arr, geo_tf, proj_wkt, class_id,
                 output_dir, pixel_area_ha, stats_html="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(990, 715)

        layout = QVBoxLayout(self)
        head = QLabel(f"<b>{title}</b>")
        layout.addWidget(head)

        self.info = QTextEdit()
        self.info.setReadOnly(True)
        self.info.setMaximumHeight(125)
        self.info.setHtml(stats_html)
        layout.addWidget(self.info)

        self.canvas = QgsMapCanvas()
        self.canvas.setCanvasColor(QColor(245, 245, 245))
        self.canvas.enableAntiAliasing(True)
        layout.addWidget(self.canvas, 1)

        path = os.path.join(
            temp_dir(output_dir),
            f"_IndependentPreview_{int(time.time()*1000)}_{class_id}.tif"
        )
        write_raster(path, raster_arr.astype(np.uint8), geo_tf, proj_wkt,
                     gdal.GDT_Byte, 0)
        layer = QgsRasterLayer(path, title)
        if layer.isValid():
            items = [
                QgsColorRampShader.ColorRampItem(cid, col, CLASS_NAMES[cid])
                for cid, col in CLASS_COLORS.items()
            ]
            shader = QgsRasterShader()
            ramp = QgsColorRampShader()
            ramp.setColorRampType(QgsColorRampShader.Exact)
            ramp.setColorRampItemList(items)
            shader.setRasterShaderFunction(ramp)
            layer.setRenderer(QgsSingleBandPseudoColorRenderer(
                layer.dataProvider(), 1, shader
            ))
            self.canvas.setLayers([layer])
            self.canvas.setExtent(layer.extent())
            self.canvas.refresh()


class MethodComparisonDialog(QDialog):
    """Résumé de la similarité / différence entre les seuils et Random Forest."""

    def __init__(self, title, threshold_mask, rf_mask, base_mask,
                 geo_tf, pixel_area_ha, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(682, 473)

        base = np.asarray(base_mask, dtype=bool)
        th = np.asarray(threshold_mask, dtype=bool) & base
        rf = np.asarray(rf_mask, dtype=bool) & base
        both = th & rf
        neither = base & (~th) & (~rf)
        th_only = th & (~rf)
        rf_only = rf & (~th)
        n = int(np.count_nonzero(base))

        def pct(x):
            return 100.0 * x / n if n else 0.0

        a = int(np.count_nonzero(both))
        d = int(np.count_nonzero(neither))
        b = int(np.count_nonzero(th_only))
        cc = int(np.count_nonzero(rf_only))

        po = (a + d) / n if n else 0.0
        p_th_pos = (a + b) / n if n else 0.0
        p_rf_pos = (a + cc) / n if n else 0.0
        p_th_neg = (d + cc) / n if n else 0.0
        p_rf_neg = (d + b) / n if n else 0.0
        pe = p_th_pos * p_rf_pos + p_th_neg * p_rf_neg
        kappa = (po - pe) / (1.0 - pe) if (1.0 - pe) > 1e-12 else 1.0

        union_pos = a + b + cc
        jaccard = (a / union_pos) if union_pos > 0 else 1.0

        def kappa_label(k):
            if k >= 0.81:
                return "Presque parfait"
            if k >= 0.61:
                return "Substantiel"
            if k >= 0.41:
                return "Modéré"
            if k >= 0.21:
                return "Passable"
            if k >= 0.0:
                return "Faible"
            return "Pire que le hasard"

        html = (
            f"<h3>{title}</h3>"
            f"<b>Pixels actifs :</b> {n:,} — {n*pixel_area_ha:,.2f} ha<br><br>"
            f"🟢 Accord positif : {a:,} ({pct(a):.2f}%)<br>"
            f"⚪ Accord négatif : {d:,} ({pct(d):.2f}%)<br>"
            f"🔵 RF seul : {cc:,} ({pct(cc):.2f}%)<br>"
            f"🟠 Seuils seuls : {b:,} ({pct(b):.2f}%)<br><br>"
            f"<b>Accord global :</b> {pct(a + d):.2f}%<br>"
            f"<b>Désaccord global :</b> {pct(b + cc):.2f}%<br>"
            f"<b>Différence de surface :</b> {abs((a + b) - (a + cc)) * pixel_area_ha:,.2f} ha<br><br>"
            f"<b>📐 Indice de Jaccard</b> (zone positive) : {jaccard:.3f}<br>"
            f"<b>📊 Kappa de Cohen</b> : {kappa:.3f} — <i>{kappa_label(kappa)}</i>"
        )

        layout = QVBoxLayout(self)
        box = QTextEdit()
        box.setReadOnly(True)
        box.setHtml(html)
        layout.addWidget(box)

        self.threshold_mask = th
        self.rf_mask = rf


def _show_method_comparison_windows(th_win, rf_win, cmp, storage):
    """UI-only manager for Threshold/RF comparison preview windows.

    The comparison dialog owns the lifecycle of the two preview windows: when
    the comparison is closed, the Threshold and RF preview windows are closed
    too. This prevents orphan windows accumulating over repeated comparisons.
    """
    for w in (th_win, rf_win, cmp):
        try:
            _make_free_desktop_window(w)
            w.setAttribute(Qt.WA_DeleteOnClose, True)
        except Exception:
            pass
    try:
        cmp.finished.connect(lambda _result: (th_win.close(), rf_win.close()))
    except Exception:
        pass
    for _w in (th_win, rf_win, cmp):
        present_window(_w, maximize=False)
    storage.extend([th_win, rf_win, cmp])


# ====================== STAGE DIALOG ======================
class TrainingAttributeTableDialog(QDialog):
    """Fenêtre attributaire indépendante pour contrôler les polygones RF.

    Permet de modifier les attributs, supprimer des polygones, actualiser la table
    et enregistrer immédiatement les modifications dans le shapefile.
    """
    def __init__(self, shp_path, field_name="class", parent=None):
        super().__init__(parent)
        self.shp_path = shp_path
        self.field_name = field_name or "class"
        self.setWindowTitle("🧾 Table attributaire — Échantillons Random Forest")
        self.resize(1155, 715)
        self.layer = None
        self.fid_col = 0
        self.area_col = 1
        self.sort_area_col = 1
        self.sort_class_col = None

        layout = QVBoxLayout(self)
        info = QLabel(
            "Modifiez les attributs ou supprimez les polygones d'échantillonnage. "
            "Les changements sont enregistrés dans le Shapefile avant l'entraînement RF."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        # PyQt6 exposes item-view enums through nested enum classes;
        # older QGIS/PyQt5 builds expose the legacy attributes directly.
        try:
            selection_rows = QAbstractItemView.SelectionBehavior.SelectRows
            selection_extended = QAbstractItemView.SelectionMode.ExtendedSelection
            edit_triggers = (
                QAbstractItemView.EditTrigger.DoubleClicked |
                QAbstractItemView.EditTrigger.SelectedClicked |
                QAbstractItemView.EditTrigger.EditKeyPressed
            )
        except AttributeError:
            # Final numeric fallback works across PyQt5/PyQt6 bindings.
            selection_rows = 1          # QAbstractItemView.SelectRows
            selection_extended = 3      # QAbstractItemView.ExtendedSelection
            edit_triggers = 0x0F       # DoubleClicked | SelectedClicked | EditKeyPressed
        self.table.setSelectionBehavior(selection_rows)
        self.table.setSelectionMode(selection_extended)
        self.table.setSortingEnabled(True)
        self.table.setEditTriggers(edit_triggers)
        layout.addWidget(self.table)

        buttons = QHBoxLayout()
        self.btn_sort_area_asc = QPushButton("📐 Superficie ↑")
        self.btn_sort_area_desc = QPushButton("📐 Superficie ↓")
        self.btn_sort_class_asc = QPushButton("🏷 Classe ↑")
        self.btn_sort_class_desc = QPushButton("🏷 Classe ↓")
        self.btn_sort_area_asc.clicked.connect(lambda: self.sort_by_area(False))
        self.btn_sort_area_desc.clicked.connect(lambda: self.sort_by_area(True))
        self.btn_sort_class_asc.clicked.connect(lambda: self.sort_by_class(False))
        self.btn_sort_class_desc.clicked.connect(lambda: self.sort_by_class(True))
        self.btn_refresh = QPushButton("🔄 Actualiser")
        self.btn_refresh.clicked.connect(self.load_table)
        self.btn_delete = QPushButton("🗑 Supprimer le(s) polygone(s)")
        self.btn_delete.clicked.connect(self.delete_selected)
        self.btn_save = QPushButton("💾 Enregistrer")
        self.btn_save.clicked.connect(self.save_changes)
        self.btn_close = QPushButton("Fermer")
        self.btn_close.clicked.connect(self.close)
        for b in (self.btn_sort_area_asc, self.btn_sort_area_desc, self.btn_sort_class_asc, self.btn_sort_class_desc, self.btn_refresh, self.btn_delete, self.btn_save, self.btn_close):
            buttons.addWidget(b)
        layout.addLayout(buttons)

        self.status = QLabel()
        layout.addWidget(self.status)
        self.load_table()

    def _open_layer(self):
        if self.layer and self.layer.isValid():
            return self.layer
        self.layer = QgsVectorLayer(self.shp_path, "RF_Samples_Editor", "ogr")
        if not self.layer.isValid():
            raise RuntimeError(f"Shapefile invalide : {self.shp_path}")
        return self.layer

    def load_table(self):
        try:
            layer = self._open_layer()
            fields = layer.fields()
            self.table.blockSignals(True)
            self.table.setSortingEnabled(False)
            self.table.clear()
            headers = ["FID", "Area (ha)", "Class Name"] + [f.name() for f in fields]
            self.table.setColumnCount(len(headers))
            self.table.setHorizontalHeaderLabels(headers)
            self.class_id_col = 3 + fields.indexOf(self.field_name) if fields.indexOf(self.field_name) >= 0 else None
            self.class_name_col = 2
            self.sort_class_col = self.class_id_col
            self.table.horizontalHeader().setToolTip(
                "Cliquez sur un en-tête pour trier. Les boutons ci-dessous trient directement par surface ou classe."
            )
            feats = list(layer.getFeatures())
            self.table.setRowCount(len(feats))

            # Calcul de surface robuste : m² -> hectares. Pour une couche géographique,
            # QgsDistanceArea utilise l'ellipsoïde du projet pour éviter une surface fausse.
            da = QgsDistanceArea()
            try:
                da.setSourceCrs(layer.crs(), QgsProject.instance().transformContext())
                da.setEllipsoid(QgsProject.instance().ellipsoid() or "WGS84")
            except Exception:
                pass

            for r, feat in enumerate(feats):
                item = QTableWidgetItem(str(feat.id()))
                item.setData(QT_USER_ROLE, int(feat.id()))
                item.setFlags(item.flags() & ~QT_ITEM_IS_EDITABLE)
                self.table.setItem(r, 0, item)

                try:
                    area_m2 = da.measureArea(feat.geometry())
                    area_ha = abs(float(area_m2)) / 10000.0
                except Exception:
                    area_ha = abs(float(feat.geometry().area())) / 10000.0
                area_item = QTableWidgetItem()
                area_item.setData(QT_DISPLAY_ROLE, round(area_ha, 4))
                area_item.setData(QT_USER_ROLE, area_ha)
                area_item.setFlags(area_item.flags() & ~QT_ITEM_IS_EDITABLE)
                self.table.setItem(r, self.area_col, area_item)

                class_value = feat[self.field_name]
                try:
                    class_id = int(class_value)
                except (TypeError, ValueError):
                    class_id = None
                class_name = CLASS_NAMES.get(class_id, "Unknown")
                name_item = QTableWidgetItem(class_name)
                name_item.setData(QT_USER_ROLE, class_id if class_id is not None else -1)
                name_item.setFlags(name_item.flags() & ~QT_ITEM_IS_EDITABLE)
                self.table.setItem(r, self.class_name_col, name_item)

                for c, fld in enumerate(fields, 3):
                    val = feat[fld.name()]
                    cell = QTableWidgetItem()
                    # Keep numeric fields numerically sortable while remaining editable.
                    if val is not None and isinstance(val, (int, float)) and not isinstance(val, bool):
                        cell.setData(QT_DISPLAY_ROLE, val)
                        cell.setData(QT_USER_ROLE, val)
                    else:
                        cell.setData(QT_DISPLAY_ROLE, "" if val is None else str(val))
                    self.table.setItem(r, c, cell)
            self.table.resizeColumnsToContents()
            self.table.horizontalHeader().setStretchLastSection(True)
            self.status.setText(f"{len(feats)} polygone(s) — champ RF : {self.field_name} — Cliquez sur les en-têtes pour trier")
            self.table.blockSignals(False)
            self.table.setSortingEnabled(True)
            try:
                self.table.cellChanged.disconnect(self._class_id_changed)
            except Exception:
                pass
            self.table.cellChanged.connect(self._class_id_changed)
        except Exception as exc:
            self.status.setText(f"Erreur : {exc}")
            QMessageBox.critical(self, "Table attributaire", str(exc))

    def sort_by_area(self, descending=False):
        self.table.setSortingEnabled(True)
        self.table.sortItems(self.area_col, QT_DESCENDING if descending else QT_ASCENDING)
        self.status.setText("Tri par surface (ha) : " + ("décroissant" if descending else "croissant"))

    def sort_by_class(self, descending=False):
        if self.sort_class_col is None:
            QMessageBox.warning(self, "Tri par classe", f"Le champ RF '{self.field_name}' n'existe pas dans la couche.")
            return
        self.table.setSortingEnabled(True)
        self.table.sortItems(self.sort_class_col, QT_DESCENDING if descending else QT_ASCENDING)
        self.status.setText("Tri par classe : " + ("décroissant" if descending else "croissant"))

    def _class_id_changed(self, row, column):
        """Update Class Name immediately when Class ID is edited."""
        if getattr(self, "class_id_col", None) is None or column != self.class_id_col:
            return
        id_item = self.table.item(row, column)
        name_item = self.table.item(row, self.class_name_col)
        if id_item is None or name_item is None:
            return
        try:
            cid = int(float(id_item.text().strip()))
        except (TypeError, ValueError):
            cid = None
        name_item.setText(CLASS_NAMES.get(cid, "Unknown"))
        name_item.setData(QT_USER_ROLE, cid if cid is not None else -1)

    def delete_selected(self):

        sel_model = self.table.selectionModel()
        try:
            selected = sel_model.selectedRows()
        except Exception:
            selected = [idx for idx in sel_model.selectedIndexes()
                        if idx.column() == 0]
        rows = sorted({idx.row() for idx in selected}, reverse=True)
        if not rows:
            QMessageBox.information(self, "Suppression", "Sélectionnez au moins un polygone.")
            return
        reply = QMessageBox.question(
            self, "Confirmer",
            f"Supprimer {len(rows)} polygone(s) du Shapefile ?",
            QMB_YES | QMB_NO, QMB_NO
        )
        if reply != QMB_YES:
            return
        layer = self._open_layer()
        fids = [int(self.table.item(r, 0).data(QT_USER_ROLE)) for r in rows]
        if not layer.isEditable() and not layer.startEditing():
            QMessageBox.critical(self, "Suppression", "Impossible de passer la couche en édition.")
            return
        if not layer.deleteFeatures(fids):
            layer.rollBack()
            QMessageBox.critical(self, "Suppression", "La suppression a échoué.")
            return
        if not layer.commitChanges():
            errs = "; ".join(layer.commitErrors())
            layer.rollBack()
            QMessageBox.critical(self, "Suppression", errs or "Impossible d'enregistrer.")
            return
        self.load_table()
        self._refresh_project_layer()

    def save_changes(self):
        layer = self._open_layer()
        fields = layer.fields()
        field_names = [f.name() for f in fields]
        try:
            if not layer.isEditable() and not layer.startEditing():
                raise RuntimeError("Impossible de passer la couche en édition.")
            for r in range(self.table.rowCount()):
                fid = int(self.table.item(r, 0).data(QT_USER_ROLE))
                for c, name in enumerate(field_names, 3):
                    text = self.table.item(r, c).text() if self.table.item(r, c) else ""
                    idx = fields.indexOf(name)
                    fld = fields[idx]
                    if text == "":
                        value = None
                    elif fld.type() in (2, 3, 4, 5):  # integer-like QVariant types
                        try:
                            value = int(float(text))
                        except ValueError:
                            value = text
                    else:
                        value = text
                    layer.changeAttributeValue(fid, idx, value)
            if not layer.commitChanges():
                errs = "; ".join(layer.commitErrors())
                layer.rollBack()
                raise RuntimeError(errs or "Échec de l'enregistrement.")
            self._refresh_project_layer()
            self.status.setText("✓ Modifications enregistrées dans le Shapefile.")
            self.load_table()
        except Exception as exc:
            if layer.isEditable():
                layer.rollBack()
            QMessageBox.critical(self, "Enregistrement", str(exc))

    def _refresh_project_layer(self):
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if os.path.normcase(lyr.source().split("|")[0]) == os.path.normcase(self.shp_path):
                    lyr.reload()
                    lyr.triggerRepaint()
            except Exception:
                pass




class SevenPolygonThresholdMapTool(QgsMapToolEmitPoint):
    """Draw exactly up to seven sampling polygons; right click closes each polygon."""
    def __init__(self, canvas, dialog):
        super().__init__(canvas)
        self.canvas = canvas
        self.dialog = dialog
        self.points = []
        self.rubber = QgsRubberBand(canvas, QgsWkbTypes.PolygonGeometry)
        self.rubber.setColor(QColor(0, 188, 212, 110))
        self.rubber.setWidth(2)

    def reset_current(self):
        self.points = []
        self.rubber.reset(QgsWkbTypes.PolygonGeometry)

    def canvasPressEvent(self, e):
        btn = e.button()
        pt = self.toMapCoordinates(e.pos())
        is_left = is_right = False
        if hasattr(btn, 'value'):
            is_left = (btn.value == 1); is_right = (btn.value == 2)
        elif hasattr(btn, 'name'):
            is_left = ('Left' in str(btn.name)); is_right = ('Right' in str(btn.name))
        else:
            try:
                v = int(btn); is_left = (v == 1); is_right = (v == 2)
            except Exception:
                pass
        if is_left and len(self.dialog.polygons) < 7:
            self.points.append(pt)
            self.rubber.addPoint(pt, True)
            self.rubber.show()
            self.dialog.lbl_progress.setText(
                f"Polygone {len(self.dialog.polygons)+1}/7 — sommets: {len(self.points)}. Clic droit pour terminer."
            )
        elif is_right:
            if len(self.points) >= 3:
                pts = list(self.points)
                self.reset_current()
                self.dialog.add_polygon(pts)
            else:
                self.dialog.lbl_progress.setText("⚠️ Minimum 3 sommets pour un polygone.")
                self.reset_current()


class SevenPolygonThresholdDialog(QDialog):
    """Select seven polygons and use the equal-weight mean of their index means as thresholds."""
    def __init__(self, parent_stage, parent=None):
        super().__init__(parent or parent_stage)
        self.stage = parent_stage
        self.polygons = []
        self.polygon_values = []
        self.setWindowTitle("📐 7 Polygones — Moyenne des seuils")
        self.resize(1265, 836)

        root = QVBoxLayout(self)
        info = QLabel(
            "Dessinez exactement 7 polygones d'échantillonnage. Pour chaque polygone, "
            "la moyenne de chaque indice sélectionné est calculée; le seuil final est "
            "la moyenne des 7 moyennes (chaque polygone a le même poids)."
        )
        info.setWordWrap(True)
        root.addWidget(info)

        top = QHBoxLayout()
        top.addWidget(QLabel("<b>Couches / indices utilisés :</b>"))
        self.btn_all = QPushButton("Tout sélectionner")
        self.btn_none = QPushButton("Tout désélectionner")
        self.btn_all.clicked.connect(lambda: self._set_all(True))
        self.btn_none.clicked.connect(lambda: self._set_all(False))
        top.addWidget(self.btn_all); top.addWidget(self.btn_none); top.addStretch()
        root.addLayout(top)

        self.checks = {}
        checks_box = QWidget(); checks_layout = QHBoxLayout(checks_box)
        for key in self.stage.spectral_arrays.keys():
            cb = QCheckBox(str(key)); cb.setChecked(True)
            self.checks[key] = cb; checks_layout.addWidget(cb)
        checks_layout.addStretch()
        root.addWidget(checks_box)

        split = QSplitter()
        self.canvas = QgsMapCanvas()
        self.canvas.setCanvasColor(QColor(245, 245, 245))
        if self.stage.current_layer and self.stage.current_layer.isValid():
            self.canvas.setLayers([self.stage.current_layer])
            self.canvas.setExtent(self.stage.current_layer.extent())
        self.tool = SevenPolygonThresholdMapTool(self.canvas, self)
        self.canvas.setMapTool(self.tool)
        split.addWidget(self.canvas)

        right = QWidget(); rv = QVBoxLayout(right)
        self.lbl_progress = QLabel("Polygones: 0/7")
        self.lbl_progress.setWordWrap(True)
        rv.addWidget(self.lbl_progress)
        self.table = QTableWidget(0, 1 + len(self.stage.spectral_arrays))
        self.table.setHorizontalHeaderLabels(["Polygon"] + [str(k) for k in self.stage.spectral_arrays.keys()])
        self.table.setSortingEnabled(False)
        rv.addWidget(self.table)
        self.lbl_final = QLabel("Moyennes finales: —")
        self.lbl_final.setWordWrap(True)
        rv.addWidget(self.lbl_final)
        self.btn_reset = QPushButton("↺ Réinitialiser les 7 polygones")
        self.btn_reset.clicked.connect(self.reset_all)
        rv.addWidget(self.btn_reset)
        rv.addStretch()
        split.addWidget(right)
        split.setSizes([700, 420])
        root.addWidget(split)

        buttons = QHBoxLayout()
        self.btn_apply = QPushButton("✅ Appliquer la moyenne des 7 polygones")
        self.btn_apply.clicked.connect(self.apply)
        self.btn_close = QPushButton("Fermer")
        self.btn_close.clicked.connect(self.reject)
        buttons.addWidget(self.btn_apply); buttons.addWidget(self.btn_close)
        root.addLayout(buttons)
        self._refresh_state()

    def _set_all(self, state):
        for cb in self.checks.values(): cb.setChecked(state)

    def selected_keys(self):
        return [k for k, cb in self.checks.items() if cb.isChecked()]

    def _polygon_mask(self, pts):
        arrays = self.stage.spectral_arrays
        if not arrays or not self.stage.geo_tf: return None
        sample_arr = next(iter(arrays.values()))
        rows, cols = sample_arr.shape
        wkt_pts = ", ".join(f"{p.x()} {p.y()}" for p in pts) + f", {pts[0].x()} {pts[0].y()}"
        mem_drv = gdal.GetDriverByName("MEM")
        ds = mem_drv.Create("", cols, rows, 1, gdal.GDT_Byte)
        ds.SetGeoTransform(self.stage.geo_tf)
        if self.stage.proj_wkt: ds.SetProjection(self.stage.proj_wkt)
        vds = ogr.GetDriverByName("Memory").CreateDataSource("mem7")
        srs = osr.SpatialReference()
        if self.stage.proj_wkt: srs.ImportFromWkt(self.stage.proj_wkt)
        lyr = vds.CreateLayer("p", srs, ogr.wkbPolygon)
        feat = ogr.Feature(lyr.GetLayerDefn())
        feat.SetGeometry(ogr.CreateGeometryFromWkt(f"POLYGON(({wkt_pts}))"))
        lyr.CreateFeature(feat)
        gdal.RasterizeLayer(ds, [1], lyr, burn_values=[1])
        return ds.GetRasterBand(1).ReadAsArray() == 1

    def add_polygon(self, pts):
        if len(self.polygons) >= 7: return
        keys = self.selected_keys()
        if not keys:
            QMessageBox.warning(self, "Indices", "Sélectionnez au moins un indice.")
            return
        mask = self._polygon_mask(pts)
        if mask is None or not np.any(mask):
            QMessageBox.warning(self, "Polygone", "Aucun pixel valide dans ce polygone.")
            return
        vals = {}
        for k in keys:
            arr = self.stage.spectral_arrays[k]
            valid = arr[mask & np.isfinite(arr) & (arr != -9999.0)]
            if len(valid) == 0:
                vals[k] = np.nan
            else:
                vals[k] = float(np.mean(valid))
        self.polygons.append(pts)
        self.polygon_values.append(vals)
        row = self.table.rowCount(); self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(f"P{row+1}"))
        for c, k in enumerate(self.stage.spectral_arrays.keys(), 1):
            v = vals.get(k, np.nan)
            self.table.setItem(row, c, QTableWidgetItem("" if not np.isfinite(v) else f"{v:.6f}"))
        self._refresh_state()

    def _refresh_state(self):
        n = len(self.polygons)
        self.lbl_progress.setText(f"<b>Polygones sélectionnés : {n}/7</b>")
        keys = self.selected_keys()
        finals = {}
        for k in keys:
            vv = [d[k] for d in self.polygon_values if k in d and np.isfinite(d[k])]
            if vv: finals[k] = float(np.mean(vv))
        if finals:
            self.lbl_final.setText("Moyennes finales : " + " | ".join(f"{k}={v:.6f}" for k,v in finals.items()))
        else:
            self.lbl_final.setText("Moyennes finales : —")
        self.btn_apply.setEnabled(n == 7 and bool(finals))

    def reset_all(self):
        self.polygons.clear(); self.polygon_values.clear(); self.table.setRowCount(0)
        self.tool.reset_current(); self._refresh_state()

    def apply(self):
        if len(self.polygons) != 7:
            QMessageBox.warning(self, "7 polygones requis", "Veuillez sélectionner exactement 7 polygones.")
            return
        keys = self.selected_keys()
        if not keys: return
        finals = {}
        for k in keys:
            vv = [d[k] for d in self.polygon_values if k in d and np.isfinite(d[k])]
            if vv: finals[k] = float(np.mean(vv))
        # Apply each selected spectral indicator to the corresponding threshold
        # field. Threshold field names often contain a class prefix/suffix
        # (e.g. bu_ndbi_min, texture_variance_min), while spectral keys are
        # seasonal (e.g. apr_ndbi). The previous direct string comparison was
        # case-sensitive and failed for labels such as "Apr_NDBI min".
        def norm(s):
            return re.sub(r"[^a-z0-9]+", "", str(s).lower())

        def feature_core(sk):
            n = norm(sk)
            # Remove common temporal prefixes so apr_ndbi -> ndbi,
            # jul_ndvi -> ndvi, etc.
            for prefix in ("apr", "jul", "may", "jun", "aug", "sep", "amp"):
                if n.startswith(prefix) and len(n) > len(prefix):
                    n = n[len(prefix):]
                    break
            return n

        applied = 0
        unmatched = []
        mappings = []

        for sk, sv in finals.items():
            # Exact feature identity from the raster feature key.
            sk_norm = feature_core(sk)
            candidates = []
            for input_key, widget in self.stage.inputs.items():
                bound = widget.property("feature_key")
                if not bound:
                    continue
                # Do not use one mean value to overwrite the universal MSAVI2 range.
                if input_key in ("msavi2_min", "msavi2_max"):
                    continue
                # Compare normalized semantic keys, preserving season.
                if bound == sk:
                    candidates.append((input_key, widget))
                    continue
                if sk_norm and bound == sk_norm:
                    candidates.append((input_key, widget))

            if candidates:
                # Prefer the shortest/most specific matching field.
                candidates.sort(key=lambda x: len(norm(x[0])))
                input_key, widget = candidates[0]
                widget.setText(f"{sv:.3f}")
                applied += 1
                mappings.append(f"{sk} → {input_key} = {sv:.3f}")
            else:
                unmatched.append(sk)

        msg = f"📐 Moyenne des 7 polygones appliquée : {applied}/{len(finals)} seuils."
        if mappings:
            msg += "\n" + " | ".join(mappings)
        if unmatched:
            msg += "\n⚠️ Non associés : " + ", ".join(unmatched)

        self.stage.probe_readout.setText(msg)
        self.stage.log_area.setPlainText(msg)
        self.accept()


UI_STATE = {"thr_detached": False, "thr_geometry": None, "split_sizes": None, "thr_on_top": True}      # disposition mémorisée d'une fenêtre d'étape à l'autre
THR_MIN_PX, LOG_MIN_PX, TOP_MIN_PX = 330, 230, 60


def split_layout_sizes(total, mode="normal", min_thr=THR_MIN_PX, min_log=LOG_MIN_PX, min_top=TOP_MIN_PX):
    """
    Hauteurs [haut (masques, modes), SEUILS, rapport] du panneau de droite pour une hauteur totale `total` (la somme vaut toujours `total`).
      normal : les SEUILS reçoivent la moitié, le rapport ≥ 230 px, le haut le reste ;
      focus  : le rapport est MASQUÉ (0), le haut est réduit au minimum : tout le reste va aux SEUILS.
    """
    total = max(int(total), 0)
    if mode == "focus":
        top = min(min_top, total)
        return [top, total - top, 0]
    thr = max(int(total * 0.50), min(min_thr, total))
    log = max(int(total * 0.22), min(min_log, total - thr)) if total - thr > 0 else 0
    top = total - thr - log
    if top < min_top and total >= min_top + min_thr + min_log:        # le haut est un panneau défilant : on lui laisse un minimum
        top = min_top
        thr = total - top - log
    elif top < 0:
        thr, top = max(0, total - log), 0
    return [max(top, 0), max(thr, 0), max(log, 0)]


def _vertical_orientation():
    """Orientation verticale compatible PyQt5 / PyQt6."""
    for path in (("Orientation", "Vertical"), ("Vertical",)):
        try:
            o = Qt
            for part in path:
                o = getattr(o, part)
            return o
        except Exception:
            continue
    return 2


class FloatingThresholdsWindow(QWidget):
    """Fenêtre FLOTTANTE et DÉPLAÇABLE qui accueille le mixe « Définition des Seuils » : à poser n'importe où (même sur un second écran), au premier plan par défaut."""

    def __init__(self, owner):
        super().__init__(None)
        self.owner = owner
        self.setWindowTitle(f"Seuils — {owner.windowTitle()}")
        self.resize(560, 740)
        lay = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.chk_top = QCheckBox("📌 Toujours au premier plan")
        self.chk_top.setChecked(bool(UI_STATE.get("thr_on_top", True)))
        self.chk_top.toggled.connect(self.apply_on_top)
        self.btn_back = QPushButton("⤓ Rattacher à la fenêtre")
        self.btn_back.clicked.connect(lambda *_: owner.reattach_thresholds())
        bar.addWidget(self.chk_top)
        bar.addStretch(1)
        bar.addWidget(self.btn_back)
        lay.addLayout(bar)

    def apply_on_top(self, on=True):
        UI_STATE["thr_on_top"] = bool(on)
        try:
            self.setWindowFlag(Qt.WindowStaysOnTopHint, bool(on))
            self.show()                                    # changer un drapeau cache la fenêtre : on la réaffiche
        except Exception:
            pass

    def closeEvent(self, event):                           # la croix RATTACHE les seuils (ils ne se perdent jamais)
        try:
            self.owner.reattach_thresholds(from_close=True)
        except Exception:
            pass
        try:
            event.accept()
        except Exception:
            pass


class StageCalibrationDialog(QDialog):
    def __init__(self, stage_title, stage_num, preview_callback,
                 available_bands_dict=None, geo_tf=None, proj_wkt=None,
                 spectral_arrays=None, all_prev_memories=None,
                 can_go_back=False, shp_selector_info=None,
                 year=None, output_dir=None, parent=None,
                 comparison_callback=None,
                 initial_lulc=None, active_mask=None, mask_callback=None, stack_bands=None, change_ctx=None, optimize_callback=None, anchor_optimize_callback=None):
        super().__init__(parent)
        self.anchor_optimize_callback = anchor_optimize_callback
        self.optimize_callback = optimize_callback
        self._change_auto_done = False
        self.mask_callback = mask_callback
        self.stack_bands = stack_bands or {}
        self.change_ctx = change_ctx                # {prev, prev_year, yr, px_ha, domain} à partir de la 2e année, sinon None
        self.change_analysis, self.change_window, self.change_layer = None, None, None
        self.change_mode, self.change_pair = "none", None
        self._change_cur, self._change_stage_class = None, None
        self.setWindowTitle(stage_title)
        self.resize(1430, 902)
        # UI-ONLY: flags are also enforced by show_dialog() immediately before
        # showing the window. Keeping this local setup preserves the same window
        # behaviour even if the dialog is opened from another code path.
        _make_free_desktop_window(self)
        self.preview_callback = preview_callback
        self.stage_num = stage_num
        self.inputs = {}
        self.action = "NEXT"
        self.shp_path_le = None
        self.rf_shp_le = None
        self.rf_field_le = None
        self.year = year
        self.output_dir = output_dir
        self.geo_tf = geo_tf
        self.proj_wkt = proj_wkt
        self.spectral_arrays = spectral_arrays or {}
        self.available_bands_dict = available_bands_dict or {}
        self.current_set_name = "ChatGPT"
        self.comparison_callback = comparison_callback
        self.training_attr_dialog = None
        # Current cumulative LULC and the active domain of this stage.
        # They are used for a direct mask overlay and for guarding RF polygon
        # drawing so samples cannot be placed over classes already removed.
        self.initial_lulc = np.asarray(initial_lulc).copy() if initial_lulc is not None else None
        self.active_mask = np.asarray(active_mask, dtype=bool).copy() if active_mask is not None else None
        self.mask_layer = None
        self.mask_overlay_enabled = True
        # Thresholds inherited automatically from the nearest previous year.
        # These stay in memory and are used when rebuilding the indicator fields.
        self.inherited_thresholds = {}
        self.inherited_from_year = None

        main_layout = QVBoxLayout(self)
        splitter = QSplitter()
        try:
            splitter.setOrientation(Qt.Orientation.Horizontal)
        except Exception:
            pass

        # ---------- Control Panel ----------
        control_panel = QWidget()
        control_layout = QVBoxLayout(control_panel)

        if all_prev_memories:
            memo_box = QGroupBox("📌 Bilan des surfaces des années déjà classées")
            memo_box.setStyleSheet("QGroupBox { font-weight: bold; color: #0d47a1; background-color: #e3f2fd; border: 1px solid #90caf9; border-radius: 4px; padding: 4px; }")
            memo_layout = QVBoxLayout(memo_box)
            for m in all_prev_memories:
                y = m.get("year")
                ar = m.get("areas", {})
                parts = [f"<b>{c}</b>: <span style='color:#2e7d32'>{v:,.1f} ha</span>" for c, v in ar.items()]
                memo_layout.addWidget(QLabel(f"<b>[{y}]</b> : " + " | ".join(parts)))
            control_layout.addWidget(memo_box)

        # Indicator set selector
        set_box = QGroupBox("📚 Source des indices")
        set_layout = QHBoxLayout(set_box)
        set_layout.addWidget(QLabel("<b>Choisir les indices :</b>"))
        self.cb_indicator_set = QComboBox()
        self.cb_indicator_set.addItems(["Scientific default", "Transparent fallback", "Legacy set 3", "Legacy original"])
        self.cb_indicator_set.currentIndexChanged.connect(self.on_indicator_set_changed)
        set_layout.addWidget(self.cb_indicator_set)
        control_layout.addWidget(set_box)

        if shp_selector_info:
            control_layout.addWidget(_build_stage_mask_panel(self))
            control_layout.addWidget(_build_mask2_panel(self))          # masque n°2 : LIMITER ou EXCLURE une zone

        # Mode selector (Seuils / RF / Hybride)
        mode_box = QGroupBox("Mode de classification")
        mode_vbox = QVBoxLayout(mode_box)
        self.mode_group = QButtonGroup(self)
        self.radio_th = QRadioButton("📏 Seuils (transparent)")
        self.radio_rf = QRadioButton("🤖 Random Forest")
        self.radio_hybrid = QRadioButton("🔀 Hybride (RF piloté par les seuils)")
        self.radio_th.setChecked(True)
        for r in (self.radio_th, self.radio_rf, self.radio_hybrid):
            self.mode_group.addButton(r)
            mode_vbox.addWidget(r)
        self.mode_group.buttonClicked.connect(lambda _: self.apply_mode_state())

        # Hybrid confidence thresholds
        hyb_row1 = QHBoxLayout()
        hyb_row1.addWidget(QLabel("Proba RF ≥ (suivre RF) :"))
        self.spin_hi = QDoubleSpinBox()
        self.spin_hi.setRange(0.50, 1.00)
        self.spin_hi.setSingleStep(0.05)
        self.spin_hi.setValue(0.80)
        hyb_row1.addWidget(self.spin_hi)
        mode_vbox.addLayout(hyb_row1)
        hyb_row2 = QHBoxLayout()
        hyb_row2.addWidget(QLabel("Proba RF ≤ (suivre seuils) :"))
        self.spin_lo = QDoubleSpinBox()
        self.spin_lo.setRange(0.00, 0.90)
        self.spin_lo.setSingleStep(0.05)
        self.spin_lo.setValue(0.50)
        hyb_row2.addWidget(self.spin_lo)
        mode_vbox.addLayout(hyb_row2)
        self.lbl_hyb_hint = QLabel(
            "Entre les deux = zone ambiguë (RF par défaut, marquée incertaine)."
        )
        self.lbl_hyb_hint.setWordWrap(True)
        self.lbl_hyb_hint.setStyleSheet("color:#6d4c41;font-size:11px;")
        mode_vbox.addWidget(self.lbl_hyb_hint)
        control_layout.addWidget(make_collapsible_section(self, "Mode de classification", mode_box, self._mode_summary, expanded=False))

        # RF box
        rf_box = QGroupBox("Échantillons Random Forest")
        rf_vbox = QVBoxLayout(rf_box)
        rf_grid = QGridLayout()
        self.rf_shp_le = QLineEdit()
        self.btn_rf_browse = QPushButton("Parcourir...")
        self.btn_rf_browse.clicked.connect(self.browse_rf_shp)
        self.btn_create_shp = QPushButton("➕ Créer Shapefile")
        self.btn_create_shp.clicked.connect(self.create_training_shapefile)
        self.rf_field_le = QLineEdit("class")
        rf_grid.addWidget(QLabel("Shapefile :"), 0, 0)
        rf_grid.addWidget(self.rf_shp_le, 0, 1)
        rf_grid.addWidget(self.btn_rf_browse, 0, 2)
        rf_grid.addWidget(QLabel("Champ :"), 1, 0)
        rf_grid.addWidget(self.rf_field_le, 1, 1)
        rf_grid.addWidget(self.btn_create_shp, 1, 2)
        rf_vbox.addLayout(rf_grid)
        sep_btn_box = QHBoxLayout()
        self.btn_eval_sep = QPushButton("📊 Séparabilité JM")
        self.btn_eval_sep.clicked.connect(self.evaluate_separability)
        self.btn_feat_imp = QPushButton("📈 Importance")
        self.btn_feat_imp.clicked.connect(self.calculate_feature_importance)
        self.btn_export_samples = QPushButton("📥 CSV")
        self.btn_export_samples.clicked.connect(self.export_training_samples)
        self.btn_attr_table = QPushButton("🧾 Table attributaire")
        self.btn_attr_table.clicked.connect(self.open_training_attribute_table)
        sep_btn_box.addWidget(self.btn_eval_sep)
        sep_btn_box.addWidget(self.btn_feat_imp)
        sep_btn_box.addWidget(self.btn_export_samples)
        sep_btn_box.addWidget(self.btn_attr_table)
        rf_vbox.addLayout(sep_btn_box)
        control_layout.addWidget(make_collapsible_section(self, "Échantillons Random Forest", rf_box, self._rf_summary, expanded=False))
        self._rf_section = self._collapsibles[-1]
        try:
            self.rf_shp_le.textChanged.connect(lambda *_: refresh_collapsible_headers(self))
            self.spin_hi.valueChanged.connect(lambda *_: refresh_collapsible_headers(self))        # le résumé « Hybride (RF ≥ … · seuils ≤ …) » suit les curseurs
            self.spin_lo.valueChanged.connect(lambda *_: refresh_collapsible_headers(self))
        except Exception:
            pass

        # Thresholds box
        self.thresholds_box = QGroupBox("Définition des Seuils")
        t_box_layout = QVBoxLayout(self.thresholds_box)
        th_tools = QHBoxLayout()
        self.btn_sample_point = QPushButton("🎯 Point Seuil")
        self.btn_sample_point.clicked.connect(self.set_probe_mode)
        self.btn_sample_poly = QPushButton("📐 Poly Seuil")
        self.btn_sample_poly.clicked.connect(self.set_sample_polygon_mode)
        self.btn_sample_7poly = QPushButton("📐 7 Polygones → Moyenne")
        self.btn_sample_7poly.clicked.connect(self.open_seven_polygon_threshold_dialog)
        th_tools.addWidget(QLabel("<b>Échantillonner :</b>"))
        th_tools.addWidget(self.btn_sample_point)
        th_tools.addWidget(self.btn_sample_poly)
        th_tools.addWidget(self.btn_sample_7poly)
        t_box_layout.addLayout(th_tools)
        _py = (change_ctx or {}).get("prev_year")
        self.btn_optimize = QPushButton(f"🎯 Optimiser pour Max Accord {_py}" if _py else "🎯 Optimiser pour Max Accord (2e année et suivantes)")
        self.btn_optimize.setToolTip("Cherche, par centiles des pixels stables de la classe l'année précédente, les seuils qui donnent le meilleur accord (F1) "
                                     "avec cette classe (Persistence Maximizer). Mode « Seuils » ; sans masque TOTAL.")
        self.btn_optimize.setEnabled(bool(_py and optimize_callback))
        self.btn_optimize.clicked.connect(self.optimize_for_previous_year)
        t_box_layout.addWidget(self.btn_optimize)
        self.btn_optimize_anchor = QPushButton(f"🎯 Optimiser sur les pixels STABLES de l'ancre {ANCHOR_CTX.get('anchor_year')}" if ANCHOR_CTX.get("active") else "🎯 Optimiser sur l'ancre (anciennes années)")
        self.btn_optimize_anchor.setToolTip("Cherche, par centiles, les seuils qui séparent au mieux les pixels STABLES (classe fiable de l'ancre) : positifs = classe de cette étape, "
                                            "négatifs = pixels stables d'autres classes. Aucun échantillon à dessiner.")
        self.btn_optimize_anchor.setEnabled(bool(ANCHOR_CTX.get("active") and anchor_optimize_callback))
        self.btn_optimize_anchor.clicked.connect(lambda _checked=False: self.optimize_for_previous_year("anchor"))
        t_box_layout.addWidget(self.btn_optimize_anchor)
        self.lbl_msavi_range = QLabel(
            "<b>Indicateurs :</b> Apr_ = 1re période du stack, Jul_ = 2e période (été) · 🔴 principal · 🟠 secondaire · 🟡 support · 🔒 limite générale · "
            "💡 suggestion facultative (champ vide = non utilisé)."
        )
        self.lbl_msavi_range.setWordWrap(True)
        self.lbl_msavi_range.setStyleSheet("color:#37474f;font-size:11px;")
        t_box_layout.addWidget(self.lbl_msavi_range)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.grid = QGridLayout(self.scroll_content)
        self.scroll.setWidget(self.scroll_content)
        self.scroll.setMinimumHeight(260)                 # les indicateurs et leurs seuils doivent rester LISIBLES
        t_box_layout.addWidget(self.scroll, 1)
        # Conteneur des SEUILS : barre d'outils (détacher / agrandir) + le groupe ; le groupe peut être DÉTACHÉ dans une fenêtre flottante déplaçable.
        self.thr_detached, self._thr_window, self._focus_prev = False, None, None
        self.thr_container = QWidget()
        tc = QVBoxLayout(self.thr_container)
        tc.setContentsMargins(0, 0, 0, 0)
        tc.setSpacing(2)
        thr_bar = QHBoxLayout()
        self.btn_thr_detach = QPushButton("⤢ Détacher les seuils (fenêtre déplaçable)")
        self.btn_thr_detach.setToolTip("Sort le mixe des seuils dans une fenêtre FLOTTANTE que vous posez où vous voulez (même sur un 2e écran), au premier plan par défaut.")
        self.btn_thr_detach.clicked.connect(self.toggle_thresholds_detached)
        self.btn_thr_focus = QPushButton("🔍 Agrandir les seuils")
        self.btn_thr_focus.setToolTip("Donne presque toute la hauteur du panneau aux seuils (masque le rapport). Cliquez encore pour revenir. Vous pouvez aussi faire GLISSER les barres grises entre les sections.")
        self.btn_thr_focus.clicked.connect(self.focus_thresholds)
        thr_bar.addWidget(self.btn_thr_detach)
        thr_bar.addWidget(self.btn_thr_focus)
        thr_bar.addStretch(1)
        tc.addLayout(thr_bar)
        tc.addWidget(self.thresholds_box, 1)
        self._thr_tc_layout = tc
        self.thr_placeholder = QLabel("Les seuils sont dans une fenêtre séparée (bouton « ⤓ Rattacher… »).")
        self.thr_placeholder.setStyleSheet("color:#6d4c41;padding:6px;")
        self.thr_placeholder.setVisible(False)
        tc.addWidget(self.thr_placeholder)
        self.apply_mode_state()

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMinimumHeight(230)       # le rapport (surface classée, entonnoir des seuils, masque) ne tenait pas dans 100 px fixes
        self.log_area.setMaximumHeight(480)
        # Panneau de droite REDIMENSIONNABLE : le haut (masques, modes...) devient défilant ; trois sections séparées par des barres GLISSABLES.
        top_scroll = QScrollArea()
        top_scroll.setWidgetResizable(True)
        top_scroll.setWidget(control_panel)
        top_scroll.setMinimumHeight(TOP_MIN_PX)
        self.right_split = QSplitter(_vertical_orientation())
        self.right_split.setHandleWidth(9)
        self.right_split.setChildrenCollapsible(False)
        self.right_split.setStyleSheet("QSplitter::handle{background:#b0bec5;} QSplitter::handle:hover{background:#4fc3f7;}")
        self.right_split.setToolTip("Faites glisser les barres grises pour agrandir une section.")
        self.right_split.addWidget(top_scroll)
        self.right_split.addWidget(self.thr_container)
        self.right_split.addWidget(self.log_area)
        self.right_split.setStretchFactor(0, 3)
        self.right_split.setStretchFactor(1, 5)
        self.right_split.setStretchFactor(2, 2)

        # ---------- Canvas ----------
        canvas_panel = QWidget()
        canvas_layout = QVBoxLayout(canvas_panel)
        canvas_header = QHBoxLayout()
        self.cb_composition = QComboBox()
        self.cb_composition.addItems([
            "Agriculture (SWIR1 / NIR / Red)",
            "Végétation Standard (NIR / Red / Green)",
            "Sol Nu & Géologie (SWIR2 / SWIR1 / Red)",
            "Couleur Naturelle (Red / Green / Blue)",
            COMP_ITEM_CUSTOM,
            COMP_ITEM_HR
        ])
        self._comp_prev_index = 0
        self.cb_composition.currentIndexChanged.connect(self.update_canvas_composition)
        self.btn_hr_image = QPushButton("🖼 Image HR…")
        self.btn_hr_image.setToolTip("Afficher une image haute résolution de votre disque comme fond (pour faciliter l'échantillonnage). Revenez au stack avec la liste « Comp ».")
        self.btn_hr_image.clicked.connect(self.choose_hr_image)
        self.btn_change = QPushButton("📊 Changement")
        self.btn_change.setToolTip("Tableau Net ≠ Échange (stabilité %, perte, gain, net, swap) et carte interactive vs l'année précédente (à partir de la 2e année).")
        self.btn_change.clicked.connect(self.open_change_window)
        self.btn_hr_fast = QPushButton("⚡ Zoom rapide")
        self.btn_hr_fast.setToolTip("Crée une copie TUILÉE avec pyramides internes de l'image haute résolution : zoom et déplacement quasi instantanés, au prix de plus d'espace disque.")
        self.btn_hr_fast.clicked.connect(self.optimize_hr_image)
        self.btn_pan = QPushButton("✋ Pan")
        self.btn_pan.clicked.connect(self.set_pan_mode)
        self.btn_zoom_in = QPushButton("🔍+")
        self.btn_zoom_in.setToolTip("Zoom sur un RECTANGLE : glissez sur la carte.")
        self.btn_zoom_in.clicked.connect(self.set_zoom_in_mode)
        self.btn_zoom_plus = QPushButton("➕")
        self.btn_zoom_plus.setToolTip("Zoom avant d'un cran (centré sur la vue). La molette de la souris fait la même chose.")
        self.btn_zoom_plus.clicked.connect(self.zoom_step_in)
        self.btn_zoom_minus = QPushButton("➖")
        self.btn_zoom_minus.setToolTip("Zoom arrière d'un cran (centré sur la vue).")
        self.btn_zoom_minus.clicked.connect(self.zoom_step_out)
        self.btn_zoom_full = QPushButton("🌐 Extent")
        self.btn_zoom_full.clicked.connect(self.zoom_to_layer_extent)
        self.btn_draw_poly = QPushButton("✏️ RF Poly (masque actif)")
        self.btn_draw_poly.clicked.connect(self.set_draw_polygon_mode)
        self.btn_toggle_mask = QPushButton("🗺 Masque")
        self.btn_toggle_mask.setCheckable(True)
        self.btn_toggle_mask.setChecked(True)
        self.btn_toggle_mask.setToolTip(
            "Afficher/masquer le masque cumulatif des étapes déjà classées. "
            "Les zones hors du masque actif sont refusées pour les polygones RF."
        )
        self.btn_toggle_mask.clicked.connect(self.toggle_mask_overlay)
        canvas_header.addWidget(QLabel("<b>Comp:</b>"))
        canvas_header.addWidget(self.cb_composition)
        canvas_header.addWidget(self.btn_hr_image)
        canvas_header.addWidget(self.btn_hr_fast)
        canvas_header.addWidget(self.btn_pan)
        canvas_header.addWidget(self.btn_zoom_in)
        canvas_header.addWidget(self.btn_zoom_minus)
        canvas_header.addWidget(self.btn_zoom_plus)
        canvas_header.addWidget(self.btn_zoom_full)
        canvas_header.addWidget(self.btn_draw_poly)
        canvas_header.addWidget(self.btn_toggle_mask)
        canvas_header.addWidget(self.btn_change)
        canvas_layout.addLayout(canvas_header)

        self.canvas = QgsMapCanvas()
        self.canvas.setCanvasColor(QColor(245, 245, 245))
        self.canvas.enableAntiAliasing(True)
        self.current_layer = None
        canvas_layout.addWidget(self.canvas)

        self.probe_readout = QLabel("Prêt. Utilisez Point ou Polygone pour charger les seuils.")
        self.probe_readout.setStyleSheet("background-color:#f1f8e9; padding:5px; border:1px solid #c8e6c9;")
        canvas_layout.addWidget(self.probe_readout)

        self.tool_point = QgsMapToolEmitPoint(self.canvas)
        self.tool_point.canvasClicked.connect(self.on_pixel_clicked)
        self.tool_pan = QgsMapToolPan(self.canvas)
        self.tool_zoom_in = QgsMapToolZoom(self.canvas, False)
        self.tool_draw_polygon = DirectPolygonMapTool(self.canvas, self)
        self.tool_sample_polygon = ThresholdSamplingPolygonTool(self.canvas, self)
        self.canvas.setMapTool(self.tool_point)

        splitter.addWidget(canvas_panel)
        splitter.addWidget(self.right_split)
        splitter.setSizes([620, 660])
        main_layout.addWidget(splitter)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton("✖ Annuler")
        self.btn_cancel.clicked.connect(self.cancel_op)
        btn_layout.addWidget(self.btn_cancel)
        if can_go_back:
            self.btn_back = QPushButton("◀ Précédent")
            self.btn_back.clicked.connect(self.go_back)
            btn_layout.addWidget(self.btn_back)
        self.btn_save_th = QPushButton("💾 Sauver")
        self.btn_save_th.clicked.connect(self.save_current_thresholds)
        btn_layout.addWidget(self.btn_save_th)
        self.btn_load_th = QPushButton("📂 Charger")
        self.btn_load_th.clicked.connect(self.load_saved_thresholds)
        btn_layout.addWidget(self.btn_load_th)
        self.btn_reuse_prev = QPushButton("⏮ Réutiliser année voisine")
        self.btn_reuse_prev.setToolTip(
            "Recharge les seuils + le mode + la config RF sauvegardés pour cette "
            "même étape à l'année VOISINE la plus proche (à égalité : l'année PRÉCÉDENTE en ordre ascendant, la plus récente en ordre descendant) : en général l'année déjà calibrée juste avant."
        )
        self.btn_reuse_prev.clicked.connect(self.reuse_previous_year)
        btn_layout.addWidget(self.btn_reuse_prev)
        self.btn_preview = QPushButton("🔍 Aperçu")
        self.btn_preview.clicked.connect(self.run_preview)
        btn_layout.addWidget(self.btn_preview)
        self.btn_compare = QPushButton("⚖ Comparer Seuils ↔ RF")
        self.btn_compare.clicked.connect(self.run_comparison)
        btn_layout.addWidget(self.btn_compare)
        self.btn_apply = QPushButton("✓ Valider ▶")
        self.btn_apply.setStyleSheet("background-color:#c8e6c9; font-weight:bold;")
        self.btn_apply.clicked.connect(self.go_next)
        btn_layout.addWidget(self.btn_apply)
        main_layout.addLayout(btn_layout)

        # Load initial scientific default fields
        self.rebuild_fields("Scientific default" if self.stage_num in (1, 2, 3, 4, 5, 6, 7, 8) else "ChatGPT")
        # For a new year, automatically inherit the nearest previous year's
        # thresholds unless this year already has saved calibration.
        self.auto_load_previous_year_thresholds()
        self.update_canvas_composition()
        self._restore_view_state()
        self._show_missing_evidence_hint()
        self._restore_layout_state()

    # ---------- disposition du panneau de droite : seuils détachables / agrandissables ----------
    def toggle_thresholds_detached(self):
        if self.thr_detached:
            self.reattach_thresholds()
        else:
            self.detach_thresholds()

    def detach_thresholds(self):
        """Sort le groupe « Définition des Seuils » dans une fenêtre flottante déplaçable. Les champs restent les MÊMES widgets : tout (aperçu, Max Accord, sauvegarde) fonctionne à l'identique."""
        if self.thr_detached:
            return
        win = self._thr_window
        if win is None:
            win = FloatingThresholdsWindow(self)
            self._thr_window = win
        self._thr_tc_layout.removeWidget(self.thresholds_box)
        win.layout().addWidget(self.thresholds_box, 1)
        self.thresholds_box.setVisible(True)
        self.thr_placeholder.setVisible(True)
        self.thr_detached = True
        UI_STATE["thr_detached"] = True
        self.btn_thr_detach.setText("⤓ Rattacher les seuils à la fenêtre")
        self.btn_thr_focus.setEnabled(False)
        g = UI_STATE.get("thr_geometry")
        if g:
            try:
                win.setGeometry(int(g[0]), int(g[1]), int(g[2]), int(g[3]))
            except Exception:
                pass
        present_window(win, maximize=False, fullscreen_button=False)
        try:
            win.apply_on_top(UI_STATE.get("thr_on_top", True))
        except Exception:
            pass

    def reattach_thresholds(self, from_close=False):
        """Remet les seuils dans le panneau de la fenêtre d'étape ; la position de la fenêtre flottante est mémorisée."""
        if not self.thr_detached:
            return
        win = self._thr_window
        try:
            UI_STATE["thr_geometry"] = (win.x(), win.y(), win.width(), win.height())
        except Exception:
            pass
        win.layout().removeWidget(self.thresholds_box)
        self._thr_tc_layout.insertWidget(1, self.thresholds_box, 1)
        self.thresholds_box.setVisible(True)
        self.thr_placeholder.setVisible(False)
        self.thr_detached = False
        UI_STATE["thr_detached"] = False
        self.btn_thr_detach.setText("⤢ Détacher les seuils (fenêtre déplaçable)")
        self.btn_thr_focus.setEnabled(True)
        if not from_close:
            try:
                win.hide()
            except Exception:
                pass

    def focus_thresholds(self):
        """🔍 : masque le rapport et réduit le haut pour donner presque toute la hauteur aux seuils ; un second clic restaure."""
        if self._focus_prev is None:
            self._focus_prev = list(self.right_split.sizes())
            total = sum(self._focus_prev) or 1
            self.log_area.setVisible(False)
            self.right_split.setSizes(split_layout_sizes(total, "focus"))
            self.btn_thr_focus.setText("↩ Disposition normale")
        else:
            self.log_area.setVisible(True)
            self.right_split.setSizes(self._focus_prev)
            self._focus_prev = None
            self.btn_thr_focus.setText("🔍 Agrandir les seuils")

    def _save_layout_state(self):
        try:
            if not self.thr_detached and self._focus_prev is None:
                sizes = list(self.right_split.sizes())
                if len(sizes) == 3 and sum(sizes) > 0:
                    UI_STATE["split_sizes"] = sizes
        except Exception:
            pass

    def _restore_layout_state(self):
        """Reprend la disposition de la fenêtre précédente : hauteurs des sections, et seuils détachés si c'était le cas."""
        try:
            sizes = UI_STATE.get("split_sizes")
            if sizes and len(sizes) == 3 and sum(sizes) > 0:
                self.right_split.setSizes([int(v) for v in sizes])
            if UI_STATE.get("thr_detached"):
                QTimer.singleShot(250, self.detach_thresholds)
        except Exception as exc:
            print(f"[Disposition] état précédent non restauré : {exc}")

    def done(self, result):
        """À la fermeture de la fenêtre d'étape : disposition mémorisée, fenêtre flottante rattachée puis cachée (l'état « détaché » est repris à l'étape suivante)."""
        was_detached = bool(getattr(self, "thr_detached", False))
        try:
            self._save_layout_state()
            if was_detached:
                self.reattach_thresholds()
            if getattr(self, "_thr_window", None) is not None:
                self._thr_window.hide()
            UI_STATE["thr_detached"] = was_detached
        except Exception:
            pass
        QDialog.done(self, result)

    def on_indicator_set_changed(self, idx):
        # BUGFIX: l'ancienne liste ["ChatGPT","ChatGPT","Google","Original"] dupliquait
        # "ChatGPT" et rendait le jeu "Grok" totalement inaccessible depuis l'interface,
        # alors qu'il est bien défini dans INDICATOR_SETS pour chaque étape.
        if idx == 0 and self.stage_num in (1, 2, 3, 4, 5, 6, 7, 8):
            self.current_set_name = "Scientific default"
        else:
            names = ["Grok", "ChatGPT", "Google", "Original"]
            self.current_set_name = names[idx] if idx < len(names) else "Grok"
        self.rebuild_fields(self.current_set_name)

    def rebuild_fields(self, set_name):
        # Clear existing widgets
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.inputs.clear()

        if set_name == "Scientific default" and self.stage_num in SCIENTIFIC_DEFAULT_STAGE_FIELDS:
            fields = dict(SCIENTIFIC_DEFAULT_STAGE_FIELDS[self.stage_num])
        else:
            fields = dict(INDICATOR_SETS.get(self.stage_num, {}).get(set_name, {}) or {})
        # Universal MSAVI2 range is retained for the legacy/fallback panels.
        # The requested Scientific default panels define their own exact fields
        # for stages 4-7, so no extra hidden/automatic MSAVI2 controls are added.
        if self.stage_num in (1, 2, 3, 4, 5, 6, 7, 8) and not (
            set_name == "Scientific default" and self.stage_num in (1, 2, 3, 4, 5, 6, 7, 8)
        ):
            fields.setdefault(
                "msavi2_min",
                ("MSAVI2 min — limite inférieure", -1.0, "🔒 Limite générale MSAVI2 de l'étape")
            )
            fields.setdefault(
                "msavi2_max",
                ("MSAVI2 max — limite supérieure", 1.0, "🔒 Limite générale MSAVI2 de l'étape")
            )

        raw_saved = load_thresholds(self.year, self.stage_num, self.output_dir) if self.year and self.output_dir else {}
        # Treat None/empty/non-numeric entries as "missing" so a partially saved
        # or previously failed calibration cannot blank the UI or block inheritance.
        def _valid_threshold_value(v):
            if v is None:
                return False
            if isinstance(v, str) and not v.strip():
                return False
            try:
                float(v)
                return True
            except (TypeError, ValueError):
                return False

        saved = {k: v for k, v in (raw_saved or {}).items() if _valid_threshold_value(v)}
        fallback_saved = {
            k: v for k, v in (self.inherited_thresholds or {}).items()
            if _valid_threshold_value(v)
        }

        row = 0
        for key, (label_text, default_val, guide_note) in fields.items():
            lbl = QLabel(f"<b>{label_text}</b>")
            if key in saved:
                val = saved[key]
            elif key in fallback_saved:
                val = fallback_saved[key]
            else:
                val = default_val
            le = QLineEdit(str(val) if val is not None else "")
            le.setFixedWidth(80)
            le.setProperty("label_text", label_text)          # sert à « 🎯 Max Accord » (sens min / max du seuil)
            # Bind the widget to an exact semantic feature derived from BOTH
            # the internal key and the visible label. This prevents collisions
            # such as NDVI min/max vs Spring NDVI vs July NDVI.
            semantic_key = self._label_to_feature_key(label_text, key)
            if semantic_key:
                le.setProperty("feature_key", semantic_key)
            self.grid.addWidget(lbl, row, 0)
            self.grid.addWidget(le, row, 1)
            self.grid.addWidget(QLabel(f"<span style='color:#455a64'>{guide_note}</span>"), row, 2)
            self.inputs[key] = le
            row += 1
        self.scroll_content.adjustSize()

    def auto_load_previous_year_thresholds(self):
        """Automatically inherit thresholds from the nearest prior year.

        This is silent with respect to the workflow (no modal dialog). The inherited
        values are kept in memory so switching indicator sets does not erase them.
        Existing current-year calibration always has priority.
        """
        if not (self.year and self.stage_num and self.output_dir):
            return

        # Never overwrite an already calibrated current year.
        current_thresholds_raw = load_thresholds(self.year, self.stage_num, self.output_dir)
        current_thresholds = {
            k: v for k, v in (current_thresholds_raw or {}).items()
            if v is not None and (not isinstance(v, str) or v.strip() != "")
        }
        current_preset = load_preset(self.year, self.stage_num, self.output_dir)
        current_preset_thresholds = {
            k: v for k, v in ((current_preset or {}).get("thresholds", {}) or {}).items()
            if v is not None and (not isinstance(v, str) or v.strip() != "")
        }
        # Only a genuinely calibrated current year should block inheritance.
        if current_thresholds or current_preset_thresholds:
            return

        prev_year = None
        prev_thresholds = {}

        try:
            idx = TARGET_YEARS.index(str(self.year))
        except ValueError:
            idx = None

        if idx is not None:
            for prev in neighbor_years(self.year, TARGET_YEARS):
                # Prefer the saved threshold JSON for the previous year.
                prev_raw = load_thresholds(prev, self.stage_num, self.output_dir)
                prev_thresholds = {
                    k: v for k, v in (prev_raw or {}).items()
                    if v is not None and (not isinstance(v, str) or v.strip() != "")
                }
                if prev_thresholds:
                    prev_year = prev
                    break
                # Fallback to the thresholds embedded in its preset.
                prev_preset = load_preset(prev, self.stage_num, self.output_dir)
                if prev_preset and prev_preset.get("thresholds"):
                    prev_thresholds = {
                        k: v for k, v in (prev_preset.get("thresholds") or {}).items()
                        if v is not None and (not isinstance(v, str) or v.strip() != "")
                    }
                    if prev_thresholds:
                        prev_year = prev
                        break

        if not prev_thresholds:
            return

        self.inherited_thresholds = dict(prev_thresholds)
        self.inherited_from_year = prev_year

        # Update only fields that exist in the current indicator set.
        for key, value in self.inherited_thresholds.items():
            widget = self.inputs.get(key)
            if widget is not None and value is not None:
                widget.setText(str(value))

        if hasattr(self, "log_area"):
            self.log_area.setPlainText(
                f"⏮ Seuils hérités automatiquement de l'année {prev_year} "
                f"pour l'étape {self.stage_num}. "
                "Vous pouvez les modifier avant validation."
            )

    def get_mode(self):
        """'thresholds' | 'rf' | 'hybrid'."""
        if self.radio_rf.isChecked():
            return "rf"
        if self.radio_hybrid.isChecked():
            return "hybrid"
        return "thresholds"

    def set_mode(self, mode):
        if mode == "rf":
            self.radio_rf.setChecked(True)
        elif mode == "hybrid":
            self.radio_hybrid.setChecked(True)
        else:
            self.radio_th.setChecked(True)
        self.apply_mode_state()

    def _mode_summary(self):
        """Résumé affiché dans l'en-tête de la section « Mode de classification » (visible même fermée)."""
        mode = self.get_mode()
        if mode == "rf":
            return "🤖 Random Forest"
        if mode == "hybrid":
            return f"🔀 Hybride (RF ≥ {self.spin_hi.value():.2f} · seuils ≤ {self.spin_lo.value():.2f})"
        return "📏 Seuils"

    def _rf_summary(self):
        """Résumé de la section « Échantillons Random Forest » : fichier choisi, et si le RF est actif."""
        shp = (self.rf_shp_le.text() or "").strip() if getattr(self, "rf_shp_le", None) else ""
        name = os.path.basename(shp) if shp else "aucun shapefile"
        return name + (" (inactif : mode Seuils)" if self.get_mode() == "thresholds" else "")

    def apply_mode_state(self):
        """Active/désactive les widgets selon le mode choisi."""
        mode = self.get_mode()
        prev_mode = getattr(self, "_prev_mode_state", None)
        self._prev_mode_state = mode
        if mode in ("rf", "hybrid") and prev_mode != mode and getattr(self, "_rf_section", None):
            self._rf_section["set_expanded"](True)          # RF / Hybride demandent un shapefile d'échantillons : on ouvre la section (une seule fois par changement de mode)
        refresh_collapsible_headers(self)
        rf_widgets = [self.rf_shp_le, self.btn_rf_browse, self.btn_create_shp,
                      self.rf_field_le, self.btn_eval_sep, self.btn_feat_imp,
                      self.btn_export_samples, self.btn_attr_table]
        rf_on = mode in ("rf", "hybrid")
        for w in rf_widgets:
            if w:
                w.setEnabled(rf_on)
        if rf_on and getattr(self, "rf_shp_le", None) and self.rf_shp_le.text().strip():
            if os.path.exists(self.rf_shp_le.text().strip()):
                # Ouvre la table séparément dès que RF/Hybride est activé.
                QTimer.singleShot(0, self.open_training_attribute_table)
        # Seuils utilisables en mode Seuils ET Hybride.
        self.thresholds_box.setEnabled(mode in ("thresholds", "hybrid"))
        # Curseurs de confiance uniquement en Hybride.
        hyb_on = (mode == "hybrid")
        self.spin_hi.setEnabled(hyb_on)
        self.spin_lo.setEnabled(hyb_on)
        self.lbl_hyb_hint.setEnabled(hyb_on)
        # Masque TOTAL : la classe = le masque -> seuils et RF sans objet pour cette étape.
        try:
            if self.mask_is_total():
                self.thresholds_box.setEnabled(False)
        except Exception:
            pass

    def browse_shp(self):
        f, _ = QFileDialog.getOpenFileName(self, "Shapefile", "", "Shapefile (*.shp)")
        if f:
            self.shp_path_le.setText(f)

    # ---------- Masque de l'étape (source + rôle) ----------
    def browse_mask(self):
        src = MASK_SOURCES[self.cb_mask_source.currentIndex()]
        flt = ("Vecteur (*.shp *.gpkg *.geojson *.json);;Tous (*)" if src == "vector"
               else "Raster (*.tif *.tiff *.img *.vrt);;Tous (*)")
        f, _ = QFileDialog.getOpenFileName(self, "Masque de l'étape", self.le_mask_path.text().strip(), flt)
        if f:
            self.le_mask_path.setText(f)

    def mask_is_total(self):
        cb = getattr(self, "cb_mask_source", None)
        return bool(cb) and MASK_SOURCES[cb.currentIndex()] != "none" and MASK_ROLES[self.cb_mask_role.currentIndex()] == "total"

    def on_mask_source_changed(self, _idx=None):
        src = MASK_SOURCES[self.cb_mask_source.currentIndex()]
        on = src != "none"
        self.le_mask_path.setEnabled(on)
        self.btn_mask_browse.setEnabled(on)
        self.le_mask_classes.setEnabled(src == "raster_class")
        self.sb_mask_band.setEnabled(src in ("raster", "raster_class"))
        self.cb_mask_role.setEnabled(on and len(getattr(self, "allowed_roles", [0, 1, 2])) > 1)
        self.btn_mask_show.setEnabled(on)
        is_anchor = src == "anchor"
        if is_anchor:
            self.le_mask_path.setEnabled(False)
            self.btn_mask_browse.setEnabled(False)
            if self.cb_mask_role.currentIndex() == 1:            # « limite » n'a pas de sens pour l'ancre : on propose l'UNION
                self.cb_mask_role.setCurrentIndex(2)
        if getattr(self, "cb_anchor_level", None) is not None:
            self.cb_anchor_level.setEnabled(is_anchor)
        self.on_mask_role_changed()

    def on_mask_role_changed(self, _idx=None):
        if not self.mask_is_total():
            on = MASK_SOURCES[self.cb_mask_source.currentIndex()] != "none"
            self.lbl_mask_hint.setText(
                "LIMITE : la classe n'est cherchée (seuils / RF) qu'à l'intérieur du masque ; hors masque, les pixels restent disponibles pour les étapes suivantes."
                if on else "")
        else:
            self.lbl_mask_hint.setText(
                "TOTAL : la classe EST le masque (pixels du masque encore non classés). Les seuils et le RF sont ignorés pour cette étape.")
        if MASK_ROLES[self.cb_mask_role.currentIndex()] == "union" and MASK_SOURCES[self.cb_mask_source.currentIndex()] != "none":
            self.lbl_mask_hint.setText(
                "UNION : les pixels du masque sont classés d'office, et le reste du domaine est classé par les seuils / le RF." +
                (" ⚓ Ancre : les pixels spectralement STABLES héritent de la classe de l'ancre ; ceux d'autres classes ne sont pas revendiqués par cette étape ; "
                 "les pixels qui ont changé sont classés par les seuils / le RF (le RF s'entraîne tout seul sur les pixels stables)."
                 if MASK_SOURCES[self.cb_mask_source.currentIndex()] == "anchor" else ""))
        if hasattr(self, "thresholds_box"):
            self.apply_mode_state()

    def get_mask_spec(self):
        """Spécification du masque de l'étape (dict) ; ValueError si les champs sont invalides."""
        if not getattr(self, "cb_mask_source", None):
            return {"source": "none"}
        lvl = self.cb_anchor_level.currentIndex() if getattr(self, "cb_anchor_level", None) is not None else 0
        spec = build_mask_spec(self.cb_mask_source.currentIndex(), self.le_mask_path.text(), self.le_mask_classes.text(),
                               self.sb_mask_band.value(), self.cb_mask_role.currentIndex(), lvl)
        m2 = self.get_mask2_spec()
        if m2:
            spec = dict(spec)
            spec["mask2"] = m2                                           # le masque n°2 voyage dans la même spécification (aperçu, preset, batch)
        return spec

    def _mask_spec_or_warn(self):
        try:
            sp = self.get_mask_spec()
            if sp.get("source") == "anchor" and not ANCHOR_CTX.get("active"):
                QMessageBox.warning(self, "Ancre", "Aucune ancre n'est active pour cette année : l'année en cours EST l'ancre, ou aucune ancre n'a été choisie au démarrage.")
                return None
            return sp
        except ValueError as exc:
            QMessageBox.warning(self, "Masque de l'étape", str(exc))
            return None

    def show_mask_footprint(self):
        """Affiche l'EMPRISE du masque sur la carte et sa SURFACE (ha), sans lancer le classement."""
        spec = self._mask_spec_or_warn()
        if spec is None:
            return
        cb = getattr(self, "mask_callback", None)
        if not cb:
            QMessageBox.information(self, "Masque de l'étape", "L'affichage de l'emprise n'est pas disponible pour cette étape.")
            return
        try:
            html = cb(spec)
        except Exception as exc:
            QMessageBox.critical(self, "Masque de l'étape", f"Impossible d'afficher le masque :\n{exc}")
            return
        self.log_area.setHtml(html or "")

    def set_mask_spec(self, spec):
        if not getattr(self, "cb_mask_source", None):
            return
        spec = spec if isinstance(spec, dict) else {"source": "none"}
        src = spec.get("source", "none")
        self.cb_mask_source.setCurrentIndex(MASK_SOURCES.index(src) if src in MASK_SOURCES else 0)
        self.le_mask_path.setText(str(spec.get("path", "") or ""))
        self.le_mask_classes.setText(",".join(str(c) for c in spec.get("classes", []) or []))
        self.sb_mask_band.setValue(int(spec.get("band", 1) or 1))
        role = spec.get("role", "boundary")
        ridx = MASK_ROLES.index(role) if role in MASK_ROLES else 1
        allowed = getattr(self, "allowed_roles", [0, 1, 2])
        if ridx not in allowed:
            ridx = allowed[0]
        self.cb_mask_role.setCurrentIndex(ridx)
        if getattr(self, "cb_anchor_level", None) is not None:
            self.cb_anchor_level.setCurrentIndex(max(0, min(1, int(spec.get("level", 1) or 1) - 1)))
        self.on_mask_source_changed()
        self.set_mask2_spec(spec.get("mask2"))

    # ---------- Masque n°2 (limiter / exclure une zone) ----------
    def browse_mask2(self):
        src = MASK2_SOURCES[self.cb_mask2_source.currentIndex()]
        flt = ("Vecteur (*.shp *.gpkg *.geojson *.json);;Tous (*)" if src == "vector" else "Raster (*.tif *.tiff *.img *.vrt);;Tous (*)")
        f, _ = QFileDialog.getOpenFileName(self, "Masque n°2", self.le_mask2_path.text().strip(), flt)
        if f:
            self.le_mask2_path.setText(f)

    def on_mask2_source_changed(self, _idx=None):
        src = MASK2_SOURCES[self.cb_mask2_source.currentIndex()]
        on = src != "none"
        self.le_mask2_path.setEnabled(on)
        self.btn_mask2_browse.setEnabled(on)
        self.le_mask2_classes.setEnabled(src == "raster_class")
        self.sb_mask2_band.setEnabled(src in ("raster", "raster_class"))
        self.cb_mask2_role.setEnabled(on)
        self.btn_mask2_show.setEnabled(on)
        self.on_mask2_role_changed()

    def on_mask2_role_changed(self, _idx=None):
        if MASK2_SOURCES[self.cb_mask2_source.currentIndex()] == "none":
            self.lbl_mask2_hint.setText("")
        elif MASK2_ROLES[self.cb_mask2_role.currentIndex()] == "limit":
            self.lbl_mask2_hint.setText("LIMITER : l'étape ne travaille qu'à l'intérieur de cette zone (en plus du masque de l'étape) ; hors zone, les pixels restent disponibles pour les étapes suivantes.")
        else:
            self.lbl_mask2_hint.setText("EXCLURE : cette zone est retirée du domaine de l'étape (aucun classement ici, même avec un masque TOTAL) ; ses pixels restent disponibles pour les étapes suivantes.")

    def get_mask2_spec(self):
        """Spécification du masque n°2 (dict) ou None ; ValueError si les champs sont invalides."""
        if not getattr(self, "cb_mask2_source", None):
            return None
        return build_mask2_spec(self.cb_mask2_source.currentIndex(), self.le_mask2_path.text(), self.le_mask2_classes.text(), self.sb_mask2_band.value(), self.cb_mask2_role.currentIndex())

    def set_mask2_spec(self, spec2):
        if not getattr(self, "cb_mask2_source", None):
            return
        spec2 = spec2 if isinstance(spec2, dict) else {"source": "none"}
        src = spec2.get("source", "none")
        self.cb_mask2_source.setCurrentIndex(MASK2_SOURCES.index(src) if src in MASK2_SOURCES else 0)
        self.le_mask2_path.setText(str(spec2.get("path", "") or ""))
        self.le_mask2_classes.setText(",".join(str(c) for c in spec2.get("classes", []) or []))
        self.sb_mask2_band.setValue(int(spec2.get("band", 1) or 1))
        role = spec2.get("role", "limit")
        self.cb_mask2_role.setCurrentIndex(MASK2_ROLES.index(role) if role in MASK2_ROLES else 0)
        self.on_mask2_source_changed()

    def show_mask2_footprint(self):
        """Affiche l'EMPRISE du masque n°2 sur la carte et sa SURFACE (ha), sans lancer le classement."""
        try:
            m2 = self.get_mask2_spec()
        except ValueError as exc:
            QMessageBox.warning(self, "Masque n°2", str(exc))
            return
        if m2 is None:
            return
        cb = getattr(self, "mask_callback", None)
        if not cb:
            QMessageBox.information(self, "Masque n°2", "L'affichage de l'emprise n'est pas disponible pour cette étape.")
            return
        try:
            html = cb(dict(m2, role="boundary"))                       # l'emprise s'affiche comme un masque ordinaire (magenta) ; le rôle est rappelé dessous
        except Exception as exc:
            QMessageBox.critical(self, "Masque n°2", f"Impossible d'afficher le masque n°2 :\n{exc}")
            return
        role_txt = MASK2_ROLE_LABELS[MASK2_ROLES.index(m2["role"])]
        self.log_area.setHtml((html or "") + f"<br><i>Rôle du masque n°2 : {role_txt}.</i>")

    def browse_rf_shp(self):
        f, _ = QFileDialog.getOpenFileName(self, "Shapefile RF", "", "Shapefile (*.shp)")
        if f:
            self.rf_shp_le.setText(f)
            if self.get_mode() in ("rf", "hybrid"):
                self.open_training_attribute_table()

    def open_training_attribute_table(self):
        cfg = self.get_rf_config()
        if not cfg["shp"] or not os.path.exists(cfg["shp"]):
            QMessageBox.warning(self, "Table attributaire", "Sélectionnez d'abord un Shapefile RF valide.")
            return
        try:
            if self.training_attr_dialog is None:
                self.training_attr_dialog = TrainingAttributeTableDialog(
                    cfg["shp"], cfg["field"], self
                )
            else:
                self.training_attr_dialog.shp_path = cfg["shp"]
                self.training_attr_dialog.field_name = cfg["field"]
                self.training_attr_dialog.load_table()
            present_window(self.training_attr_dialog, maximize=False)
            self.training_attr_dialog.raise_()
            self.training_attr_dialog.activateWindow()
        except Exception as exc:
            QMessageBox.critical(self, "Table attributaire", str(exc))

    def get_shp_path(self):
        return self.shp_path_le.text().strip() if self.shp_path_le else ""

    def get_rf_config(self):
        mode = self.get_mode()
        return {
            # "enabled" conservé pour compatibilité : True si RF est utilisé (rf ou hybride).
            "enabled": mode in ("rf", "hybrid"),
            "mode": mode,
            "shp": self.rf_shp_le.text().strip(),
            "field": self.rf_field_le.text().strip() or "class",
            "hi": float(self.spin_hi.value()),
            "lo": float(self.spin_lo.value()),
        }

    def get_values(self):
        vals = {}
        for k, le in self.inputs.items():
            t = le.text().strip()
            if t:
                try:
                    vals[k] = float(t)
                except ValueError:
                    vals[k] = None
            else:
                vals[k] = None
        return vals

    def save_current_thresholds(self):
        if self.year and self.stage_num and self.output_dir:
            path = save_thresholds(self.year, self.stage_num, self.get_values(), self.output_dir)
            QMessageBox.information(self, "Succès", f"Seuils sauvegardés :\n{path}")

    def load_saved_thresholds(self):
        if self.year and self.stage_num and self.output_dir:
            loaded = load_thresholds(self.year, self.stage_num, self.output_dir)
            if loaded:
                for k, v in loaded.items():
                    if k in self.inputs and v is not None:
                        self.inputs[k].setText(str(v))
                QMessageBox.information(self, "Succès", "Seuils chargés.")
            else:
                QMessageBox.warning(self, "Attention", "Aucun seuil trouvé.")

    def run_preview(self):
        spec = self._mask_spec_or_warn()
        if spec is None:
            return
        html = self.preview_callback(self.get_values(), spec, self.get_rf_config())
        self.log_area.setHtml(html)

    def run_comparison(self):
        if not self.comparison_callback:
            QMessageBox.information(self, "Comparaison",
                                    "La comparaison n'est pas disponible pour cette étape.")
            return
        try:
            spec = self._mask_spec_or_warn()
            if spec is None:
                return
            html = self.comparison_callback(
                self.get_values(), spec, self.get_rf_config()
            )
            self.log_area.setHtml(html or "Comparaison exécutée.")
        except Exception as exc:
            QMessageBox.critical(self, "Comparaison", f"Échec de la comparaison :\n{exc}")

    def go_back(self):
        self.action = "BACK"
        self.reject()

    def go_next(self):
        mask_spec = self._mask_spec_or_warn()
        if mask_spec is None:
            return
        vals = self.get_values()
        save_thresholds(self.year, self.stage_num, vals, self.output_dir)
        rf_cfg = self.get_rf_config()
        save_preset(self.year, self.stage_num, self.output_dir,
                    rf_cfg["mode"], rf_cfg, vals, rf_cfg["hi"], rf_cfg["lo"], mask_spec=mask_spec)
        self.action = "NEXT"
        self.accept()

    def reuse_previous_year(self):
        if not (self.year and self.stage_num and self.output_dir):
            QMessageBox.warning(self, "Attention", "Année / étape / dossier non définis.")
            return
        prev_year, preset = find_previous_preset(
            self.year, self.stage_num, self.output_dir, TARGET_YEARS
        )
        if not preset:
            QMessageBox.warning(
                self, "Aucun preset",
                f"Aucun preset trouvé pour l'étape {self.stage_num} aux autres années "
                f"(la plus proche est cherchée en premier ; à égalité : l'année précédente en ordre ascendant, la plus récente en ordre descendant)."
            )
            return
        self.set_mode(preset.get("mode", "thresholds"))
        self.set_mask_spec(preset.get("mask"))
        rf = preset.get("rf", {})
        if rf.get("shp"):
            self.rf_shp_le.setText(rf["shp"])
        if rf.get("field"):
            self.rf_field_le.setText(rf["field"])
        if preset.get("hi") is not None:
            self.spin_hi.setValue(float(preset["hi"]))
        if preset.get("lo") is not None:
            self.spin_lo.setValue(float(preset["lo"]))
        th = preset.get("thresholds", {})
        self.inherited_thresholds = dict(th or {})
        self.inherited_from_year = prev_year
        applied = 0
        for k, v in th.items():
            if k in self.inputs and v is not None:
                self.inputs[k].setText(str(v))
                applied += 1
        mode = preset.get("mode", "thresholds")
        self.log_area.setHtml(
            f"⏮ Preset de <b>{prev_year}</b> rechargé — étape {self.stage_num}, "
            f"mode <b>{mode}</b>, {applied} seuil(s) appliqué(s)."
        )
        QMessageBox.information(
            self, "Réutilisé",
            f"Preset de {prev_year} rechargé\n(mode {mode}, {applied} seuils)."
        )

    def cancel_op(self):
        self.action = "CANCEL"
        self.reject()

    def showEvent(self, event):
        super().showEvent(event)
        # AMÉLIORATION : QgsMapCanvas peut rester vide tant que le widget n'est
        # pas réellement visible à l'écran, même si les couches (dont le masque
        # coloré — Sebkha, etc.) ont déjà été correctement assignées pendant
        # __init__. On force un rafraîchissement juste après l'affichage réel
        # de la fenêtre pour garantir que le masque coloré apparaisse
        # IMMÉDIATEMENT en entrant dans l'étape, avant tout clic sur "Aperçu".
        QTimer.singleShot(150, self._ensure_mask_visible_on_open)

    def _ensure_mask_visible_on_open(self):
        try:
            if self.initial_lulc is not None:
                self.update_stage_mask_overlay(self.initial_lulc)
            elif self.mask_layer is not None:
                self.canvas.refresh()
        except Exception:
            pass

    def toggle_mask_overlay(self, checked):
        self.mask_overlay_enabled = bool(checked)
        if self.mask_layer is not None:
            self.mask_layer.setOpacity(1.0 if self.mask_overlay_enabled else 0.0)
            self.canvas.refresh()
        state = "activé" if self.mask_overlay_enabled else "masqué"
        self.probe_readout.setText(
            f"🎨 Masque coloré des zones déjà classées {state}."
        )

    def update_stage_mask_overlay(self, lulc_array):
        """Show already-classified areas colour-coded by class, instead of a
        uniform black mask.

        Pixel value written to the overlay raster:
          0   -> transparent (active/available domain for this stage)
          1-8 -> already classified by a previous stage -> that class's own
                 colour (CLASS_COLORS), fully opaque
          255 -> not yet classified but outside this stage's eligible domain
                 (outside the administrative boundary, or excluded by a
                 stage-specific restriction e.g. the vegetated-only domain)
                 -> semi-transparent black
        """
        if lulc_array is None or not self.geo_tf or not self.proj_wkt:
            return
        try:
            arr = np.asarray(lulc_array)
            if arr.ndim != 2:
                return
            out_dir = self.output_dir or os.path.join(os.getcwd(), "tmp")
            os.makedirs(out_dir, exist_ok=True)
            # BUGFIX: réutiliser un nom de fichier fixe forçait à supprimer
            # l'ancien fichier avant chaque redessin. Sur Windows, tant que
            # QGIS n'a pas fini de libérer le verrou de la couche précédente,
            # cette suppression échoue ("Permission denied") et la fonction
            # s'arrête silencieusement AVANT de dessiner le nouveau masque —
            # c'est pour cela que le masque coloré n'apparaissait pas de façon
            # fiable dès l'étape 2. Un nom unique par appel évite totalement
            # ce conflit ; les anciens fichiers sont nettoyés en best-effort.
            old_layer = self.mask_layer
            path = os.path.join(
                temp_dir(out_dir),
                f"_StageMask_{self.year}_S{self.stage_num}_{int(time.time() * 1000)}.tif"
            )

            ds = gdal.GetDriverByName("GTiff").Create(
                path, arr.shape[1], arr.shape[0], 1, gdal.GDT_Byte,
                ["COMPRESS=LZW"]
            )
            ds.SetGeoTransform(self.geo_tf)
            ds.SetProjection(self.proj_wkt)

            # BUGFIX / AMÉLIORATION : masque colorié par classe au lieu d'un
            # aplat noir. 0 reste transparent (domaine actif) ; 1-8 reprennent
            # la couleur officielle de chaque classe (CLASS_COLORS) ; 255 =
            # non classé mais hors domaine éligible de cette étape.
            not_yet_classified = (arr <= 0)
            outside_stage_domain = not_yet_classified.copy()
            if self.active_mask is not None and self.active_mask.shape == arr.shape:
                outside_stage_domain &= ~self.active_mask
            else:
                outside_stage_domain[:] = False

            mask_arr = np.where(arr > 0, arr, 0).astype(np.uint8)
            mask_arr[outside_stage_domain] = 255

            band = ds.GetRasterBand(1)
            band.WriteArray(mask_arr)
            band.SetNoDataValue(0)
            band.FlushCache()
            ds.FlushCache()
            ds = None

            layer = QgsRasterLayer(path, f"Masque coloré S{self.stage_num}")
            if not layer.isValid():
                return

            provider = layer.dataProvider()
            shader = QgsColorRampShader()
            shader.setColorRampType(QgsColorRampShader.Exact)
            items = [
                QgsColorRampShader.ColorRampItem(
                    float(cid), QColor(c.red(), c.green(), c.blue(), 255),
                    f"{cid} - {CLASS_NAMES.get(cid, '')} (déjà classé)"
                )
                for cid, c in CLASS_COLORS.items()
            ]
            items.append(
                QgsColorRampShader.ColorRampItem(
                    255.0, QColor(0, 0, 0, 140), "Hors domaine actif de cette étape"
                )
            )
            # Emprise du masque de l'étape (rôle LIMITE) : magenta semi-transparent, visible dans l'aperçu.
            items.append(
                QgsColorRampShader.ColorRampItem(
                    254.0, QColor(255, 0, 200, 150), "Emprise du masque de l'étape"
                )
            )
            items.sort(key=lambda it: it.value)          # le mode « Exact » exige une liste triée par valeur
            shader.setColorRampItemList(items)
            raster_shader = QgsRasterShader()
            raster_shader.setRasterShaderFunction(shader)
            renderer = QgsSingleBandPseudoColorRenderer(provider, 1, raster_shader)
            layer.setRenderer(renderer)
            layer.setOpacity(1.0 if self.mask_overlay_enabled else 0.0)
            self.mask_layer = layer

            # Keep the coloured mask above the RGB source image.
            layers = [self.mask_layer]
            if self.current_layer is not None and self.current_layer.isValid():
                layers.append(self.current_layer)
            self.canvas.setLayers(self._with_change_layer(layers))
            self._fit_extent_after_overlay()
            self.canvas.refresh()
            self.probe_readout.setText(
                "🎨 Masque coloré actif : couleurs = classes déjà attribuées, "
                "noir semi-transparent = hors domaine, transparent = zone active."
            )

            # Best-effort cleanup of the previous layer/file, done AFTER the
            # new mask is already visible so a locked old file never blocks
            # the new one from showing.
            try:
                if old_layer is not None and old_layer.isValid():
                    QgsProject.instance().removeMapLayer(old_layer.id())
            except Exception:
                pass
            try:
                for f in glob.glob(os.path.join(temp_dir(out_dir), f"_StageMask_{self.year}_S{self.stage_num}_*.tif")):
                    if f != path:
                        try:
                            os.remove(f)
                        except Exception:
                            pass  # still locked/in use: skip, harmless leftover
            except Exception:
                pass
        except Exception as exc:
            try:
                self.log_area.append(f"⚠️ Masque coloré étape: {exc}")
            except Exception:
                pass

    def set_probe_mode(self):
        self.canvas.setMapTool(self.tool_point)
        self.probe_readout.setText("🎯 Mode Point activé.")

    def set_pan_mode(self):
        self.canvas.setMapTool(self.tool_pan)

    def set_zoom_in_mode(self):
        self.canvas.setMapTool(self.tool_zoom_in)

    def zoom_step_in(self):
        """➕ : zoom avant d'un cran (facteur 2), centré sur la vue ; n'interrompt pas l'outil actif (dessin de polygone, échantillonnage...)."""
        self.canvas.zoomIn()

    def zoom_step_out(self):
        """➖ : zoom arrière d'un cran (facteur 2), centré sur la vue ; n'interrompt pas l'outil actif."""
        self.canvas.zoomOut()

    # ---------- Changement vs année précédente : tableau Net / Échange + carte interactive ----------
    def _base_layers(self):
        layers = []
        if self.mask_layer is not None and self.mask_layer.isValid():
            layers.append(self.mask_layer)
        if self.current_layer is not None and self.current_layer.isValid():
            layers.append(self.current_layer)
        return layers

    def _with_change_layer(self, layers):
        """La couche de changement (si une carte est choisie) est placée AU-DESSUS de toutes les autres."""
        lyr = getattr(self, "change_layer", None)
        if lyr is not None and getattr(self, "change_mode", "none") != "none":
            try:
                if lyr.isValid():
                    return [lyr] + list(layers)
            except Exception:
                pass
        return list(layers)

    def _stage_class_for_change(self):
        return next(iter(STAGE_POSITIVE.get(self.stage_num, {None})))

    def open_change_window(self):
        ctx = getattr(self, "change_ctx", None)
        if not ctx:
            QMessageBox.information(self, "Changement", "Première année traitée : aucune autre année n'est encore classée (ni en mémoire ni dans le dossier de résultats).\n"
                                                        "Le tableau Net ≠ Échange et la carte de changement apparaissent dès qu'une autre année est classée (la 2e année traitée, et les suivantes, sont comparées à l'année déjà classée la plus adaptée).")
            return
        if self.change_analysis is None and self.initial_lulc is not None:
            # pas encore d'aperçu : on analyse l'état actuel (classes déjà attribuées par les étapes précédentes)
            self.set_change_analysis(analyze_change(ctx["prev"], self.initial_lulc, ctx["px_ha"], domain=ctx.get("domain"), prev_year=ctx["prev_year"],
                                                    reverse=bool(ctx.get("reverse")), cur_year=ctx.get("yr")),
                                     self.initial_lulc, self._stage_class_for_change())
        if self.change_analysis is None:
            return
        if self.change_window is None:
            self.change_window = ChangeStatsDialog(self)
        self.change_window.set_data(self.change_analysis, self._change_stage_class, ctx)
        present_window(self.change_window, maximize=False)
        try:
            self.change_window.raise_()
            self.change_window.activateWindow()
        except Exception:
            pass

    def set_change_analysis(self, analysis, cur_state, stage_class, from_preview=False):
        """
        Appelé à chaque aperçu : mémorise l'analyse, rafraîchit la fenêtre des tableaux et la carte si elle est affichée.
        Au PREMIER aperçu d'une fenêtre : la carte passe en mode « Origine » (stable = vert, sinon couleur de la classe précédente) et le tableau s'ouvre.
        """
        self.change_analysis, self._change_cur, self._change_stage_class = analysis, cur_state, stage_class
        first = bool(from_preview and not self._change_auto_done and self.change_ctx)
        if first:
            self._change_auto_done = True
            if self.change_mode == "none":
                self.change_mode = "origin"
        if self.change_window is not None:
            try:
                self.change_window.set_data(analysis, stage_class, self.change_ctx)
            except Exception as exc:
                print(f"[Changement] tableau non rafraîchi : {exc}")
        if self.change_mode != "none":
            self._update_change_overlay()
        if first and self.change_window is None:
            self.open_change_window()

    def _optimizable_fields(self):
        """Champs de seuils dont on connaît la variable ET le sens (min / max) : {clé: {feature, op}}."""
        out = {}
        for key, w in self.inputs.items():
            fk = w.property("feature_key") or self._threshold_feature_key(key)
            if not fk:
                continue
            m = re.search(r"\b(min|max)\b", str(w.property("label_text") or "")) or re.search(r"_(min|max)$", key)
            if m:
                out[key] = {"feature": fk, "op": m.group(1)}
        return out

    def optimize_for_previous_year(self, which="previous"):
        """
        🎯 Max Accord : remplit les champs avec les seuils qui reproduisent au mieux la classe de l'année précédente (which="previous"),
        ou qui séparent au mieux les pixels STABLES de l'ancre (which="anchor"), puis lance l'aperçu.
        """
        if which == "anchor":
            cb = getattr(self, "anchor_optimize_callback", None)
            if not ANCHOR_CTX.get("active") or not cb:
                QMessageBox.information(self, "Ancre", "Aucune ancre active pour cette année (l'année en cours est l'ancre, ou aucune ancre n'a été choisie au démarrage).")
                return
            ctx = {"prev_year": ANCHOR_CTX["anchor_year"], "px_ha": ANCHOR_CTX["px_ha"]}
        else:
            ctx, cb = getattr(self, "change_ctx", None), getattr(self, "optimize_callback", None)
        if not ctx or not cb:
            QMessageBox.information(self, "Max Accord", "Disponible à partir de la 2e année (une carte de l'année précédente est nécessaire).")
            return
        if self.get_rf_config().get("mode") != "thresholds":
            QMessageBox.information(self, "Max Accord", "L'optimisation concerne le mode « Seuils (transparent) ». Choisissez ce mode.")
            return
        spec = self._mask_spec_or_warn()
        if spec is None:
            return
        if spec.get("source", "none") != "none" and spec.get("role") == "total":
            QMessageBox.information(self, "Max Accord", "Le masque est en rôle TOTAL : la classe est le masque, les seuils ne servent pas.")
            return
        fields = self._optimizable_fields()
        try:
            res = cb(self.get_values(), fields, spec)
        except Exception as exc:
            QMessageBox.critical(self, "Max Accord", f"Optimisation impossible :\n{exc}")
            return
        name = CLASS_NAMES.get(self._stage_class_for_change(), "")
        labels = {k: re.sub(r"^\d+\.\s*", "", str(self.inputs[k].property("label_text") or k)) for k in fields if k in self.inputs}
        self.log_area.setHtml(optimizer_report_html(res, ctx.get("prev_year"), name, labels, ctx.get("px_ha"), anchor=(which == "anchor")))
        if not res.get("ok"):
            return
        for k, _old, new in res["changes"]:
            if k in self.inputs:
                self.inputs[k].setText("" if new is None else f"{float(new):g}")
        try:
            self.run_preview()
        except Exception as exc:
            print(f"[Max Accord] aperçu automatique impossible : {exc}")

    def set_change_map_mode(self, mode):
        self.change_mode = mode if mode in dict(CHANGE_MAP_MODES) else "none"
        self._update_change_overlay()

    def show_transition_on_map(self, i, j):
        """Clic sur une ligne du tableau des transitions : les pixels de cette transition sont surlignés sur la carte."""
        self.change_pair = (int(i), int(j))
        self.change_mode = "transition"
        self._update_change_overlay()

    def _write_change_layer(self, codes):
        """Raster Byte (0 transparent) + palette CHANGE_MAP_COLORS ; retourne la couche QGIS."""
        out_dir = self.output_dir or os.path.join(os.getcwd(), "tmp")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(temp_dir(out_dir), f"_StageChange_{self.year}_S{self.stage_num}_{int(time.time() * 1000)}.tif")
        ds = gdal.GetDriverByName("GTiff").Create(path, codes.shape[1], codes.shape[0], 1, gdal.GDT_Byte, ["COMPRESS=LZW"])
        ds.SetGeoTransform(self.geo_tf)
        ds.SetProjection(self.proj_wkt)
        band = ds.GetRasterBand(1)
        band.WriteArray(codes)
        band.SetNoDataValue(0)
        band.FlushCache()
        ds.FlushCache()
        ds = None
        layer = QgsRasterLayer(path, f"Changement S{self.stage_num}")
        if not layer.isValid():
            return None
        shader = QgsColorRampShader()
        shader.setColorRampType(QgsColorRampShader.Exact)
        shader.setColorRampItemList(sorted([QgsColorRampShader.ColorRampItem(float(v), QColor(*rgba), lab) for v, (lab, rgba) in change_palette(reverse=bool((self.change_ctx or {}).get("reverse")),
                                                                                                                         cur_year=(self.change_ctx or {}).get("yr"), ref_year=(self.change_ctx or {}).get("prev_year")).items()],
                                           key=lambda it: it.value))
        rs = QgsRasterShader()
        rs.setRasterShaderFunction(shader)
        layer.setRenderer(QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, rs))
        layer.setOpacity(1.0)
        return layer

    def _update_change_overlay(self):
        ctx = getattr(self, "change_ctx", None)
        if not ctx or self._change_cur is None:
            return
        try:
            codes = change_codes_for_mode(self.change_mode, ctx["prev"], self._change_cur, self._change_stage_class, self.change_pair, bool(ctx.get("reverse")))
            old = self.change_layer
            if codes is None:
                self.change_layer = None
            else:
                self.change_layer = self._write_change_layer(codes)
            self.canvas.setLayers(self._with_change_layer(self._base_layers()))
            self.canvas.refresh()
            if old is not None:
                try:
                    QgsProject.instance().removeMapLayer(old.id())
                except Exception:
                    pass
        except Exception as exc:
            print(f"[Changement] carte non mise à jour : {exc}")

    def _fit_extent_after_overlay(self):
        """
        Étendue du canevas après (re)dessin du masque. Fond « stack » : étendue de la couche (comportement d'origine). Fond « image HR » :
        l'étendue de l'image est dans SON CRS, pas celui du canevas (CRS du stack) : on cadre la ZONE D'ÉTUDE, une seule fois (le zoom
        de l'utilisateur est ensuite conservé).
        """
        if HR_VIEW_STATE.get("mode") == "hr" and self.geo_tf:
            if not getattr(self, "_hr_extent_done", False):
                self.canvas.setExtent(self._stack_extent())
                self._hr_extent_done = True
        elif self.current_layer is not None:
            self.canvas.setExtent(self.current_layer.extent())

    def zoom_to_layer_extent(self):
        if HR_VIEW_STATE.get("mode") == "hr" and self.geo_tf:
            self.canvas.setExtent(self._stack_extent())          # l'étendue d'étude, pas celle (autre CRS) de l'image HR
            self.canvas.refresh()
        elif self.current_layer and self.current_layer.isValid():
            self.canvas.setExtent(self.current_layer.extent())
            self.canvas.refresh()

    def open_seven_polygon_threshold_dialog(self):
        dlg = SevenPolygonThresholdDialog(self, self)
        # IMPORTANT: never use QDialog.exec()/exec_() here.  The threshold
        # window must remain a free desktop window so QGIS itself stays usable.
        show_dialog(dlg)

    def set_sample_polygon_mode(self):
        self.tool_sample_polygon.reset_tool()
        self.canvas.setMapTool(self.tool_sample_polygon)
        self.probe_readout.setText("📐 Polygone Seuil : Clics gauches + Clic droit.")

    def set_draw_polygon_mode(self):
        cfg = self.get_rf_config()
        if not cfg["shp"] or not os.path.exists(cfg["shp"]):
            QMessageBox.warning(self, "Attention", "Sélectionnez un Shapefile RF d'abord.")
            return
        self.tool_draw_polygon.reset_tool()
        self.canvas.setMapTool(self.tool_draw_polygon)
        self.probe_readout.setText("✏️ Dessin RF activé.")

    def create_training_shapefile(self):
        save_p, _ = QFileDialog.getSaveFileName(
            self, "Créer Shapefile",
            os.path.join(self.output_dir or "", f"Samples_{self.year}_S{self.stage_num}.shp"),
            "Shapefile (*.shp)"
        )
        if not save_p:
            return
        drv = ogr.GetDriverByName("ESRI Shapefile")
        if os.path.exists(save_p):
            drv.DeleteDataSource(save_p)
        srs = osr.SpatialReference()
        if self.proj_wkt:
            srs.ImportFromWkt(self.proj_wkt)
        else:
            srs.ImportFromEPSG(32632)
        ds = drv.CreateDataSource(save_p)
        lyr = ds.CreateLayer(os.path.splitext(os.path.basename(save_p))[0], srs, ogr.wkbPolygon)
        lyr.CreateField(ogr.FieldDefn("class", ogr.OFTInteger))
        ds = None
        self.rf_shp_le.setText(save_p)
        self.rf_field_le.setText("class")
        v_layer = QgsVectorLayer(save_p, os.path.splitext(os.path.basename(save_p))[0], "ogr")
        if v_layer.isValid():
            QgsProject.instance().addMapLayer(v_layer)
        QMessageBox.information(self, "Succès", f"Créé :\n{save_p}")

    def finish_drawn_polygon(self, qgs_points):
        cfg = self.get_rf_config()
        shp_p = cfg["shp"]
        fld = cfg["field"]
        if not shp_p or not os.path.exists(shp_p):
            return

        # Prevent training polygons from crossing zones already classified in
        # earlier stages or outside the current active domain.
        if self.active_mask is not None and self.geo_tf and self.proj_wkt:
            try:
                sample_arr = next(iter(self.spectral_arrays.values()))
                rows, cols = sample_arr.shape
                wkt_pts = ", ".join(
                    [f"{pt.x()} {pt.y()}" for pt in qgs_points]
                ) + f", {qgs_points[0].x()} {qgs_points[0].y()}"

                mem_drv = gdal.GetDriverByName("MEM")
                t_ds = mem_drv.Create("", cols, rows, 1, gdal.GDT_Byte)
                t_ds.SetGeoTransform(self.geo_tf)
                t_ds.SetProjection(self.proj_wkt)

                v_ds = ogr.GetDriverByName("Memory").CreateDataSource("mem_guard")
                srs = osr.SpatialReference()
                srs.ImportFromWkt(self.proj_wkt)
                lyr = v_ds.CreateLayer("poly_guard", srs, ogr.wkbPolygon)
                feat_guard = ogr.Feature(lyr.GetLayerDefn())
                feat_guard.SetGeometry(
                    ogr.CreateGeometryFromWkt(f"POLYGON(({wkt_pts}))")
                )
                lyr.CreateFeature(feat_guard)
                gdal.RasterizeLayer(t_ds, [1], lyr, burn_values=[1])
                poly_mask = t_ds.GetRasterBand(1).ReadAsArray() == 1
                outside = poly_mask & (~self.active_mask)

                n_poly = int(np.count_nonzero(poly_mask))
                n_out = int(np.count_nonzero(outside))
                if n_poly == 0:
                    self.probe_readout.setText("⚠️ Le polygone ne contient aucun pixel du raster.")
                    return
                if n_out > 0:
                    pct = 100.0 * n_out / n_poly
                    QMessageBox.warning(
                        self,
                        "⛔ Polygone hors domaine actif",
                        f"Le polygone RF traverse une zone déjà classée/exclue.\n\n"
                        f"Pixels du polygone : {n_poly:,}\n"
                        f"Pixels hors domaine actif : {n_out:,} ({pct:.2f} %)\n\n"
                        "Le polygone n'a PAS été enregistré. "
                        "Utilisez le masque visible pour dessiner uniquement "
                        "dans la zone encore active."
                    )
                    return
            except Exception as exc:
                QMessageBox.warning(
                    self,
                    "Contrôle du masque",
                    f"Impossible de vérifier le polygone contre le masque actif :\n{exc}\n\n"
                    "Le polygone n'a PAS été enregistré."
                )
                return

        class_id, ok = QInputDialog.getInt(self, "Classe", "Identifiant de classe :", 1, 1, 50, 1)
        if not ok:
            return
        v_layer = QgsVectorLayer(shp_p, "temp", "ogr")
        if not v_layer.isValid():
            return
        pr = v_layer.dataProvider()
        if v_layer.fields().indexFromName(fld) == -1:
            pr.addAttributes([QgsField(fld, QVariant.Int)])
            v_layer.updateFields()
        feat = QgsFeature(v_layer.fields())
        feat.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(pt.x(), pt.y()) for pt in qgs_points]]))
        feat.setAttribute(v_layer.fields().indexFromName(fld), int(class_id))
        pr.addFeatures([feat])
        v_layer.updateExtents()
        self.probe_readout.setText(f"✅ Polygone enregistré (Classe {class_id})")
        if self.training_attr_dialog is not None:
            self.training_attr_dialog.load_table()
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.source().split("|")[0] == shp_p:
                lyr.triggerRepaint()

    def _label_to_feature_key(self, label_text, input_key=None):
        """Resolve a visible threshold label to one exact feature array key."""
        raw = str(label_text or "")
        n = re.sub(r"[^a-z0-9]+", "", raw.lower())
        if input_key in TEMPORAL_FEATURE_KEYS:          # preuve temporelle : variable calculée à partir des NDVI annuels / LPD
            return TEMPORAL_FEATURE_KEYS[input_key]

        # General MSAVI2 min/max are range constraints, not point-sampled values.
        if n.startswith("msavi2") and (n.endswith("min") or n.endswith("max")):
            return None

        # Detect explicit season/month wording FIRST; generic NDVI/NDMI/etc. fields
        # fall back to April only when the label/key provides no season.
        temporal = None
        if any(tok in n for tok in ("juillet", "july", "jul")):
            temporal = "jul"
        elif any(tok in n for tok in ("printemps", "spring", "avr", "april", "apr")):
            temporal = "apr"
        elif "ete" in n or "summer" in n:
            temporal = "jul"

        # Map the scientific index from the visible label.
        base = None
        aliases = [
            ("texturevariance", "texture_variance"),
            ("ndviamplitude", "amp"),
            ("amplitude", "amp"),
            ("deltandvi", "delta"),
            ("msavi2", "msavi"),
            ("ndvi", "ndvi"),
            ("msavi", "msavi"),
            ("savi", "savi"),
            ("ndmi", "ndmi"),
            ("mndwi", "mndwi"),
            ("ndwi", "ndwi"),
            ("ndbi", "ndbi"),
            ("dbsi", "dbsi"),
            ("bsi", "dbsi"),
            ("nbr", "nbr"),
            ("swir1", "swir1"),
            ("swir2", "swir2"),
            ("nir", "nir"),
            ("red", "red"),
            ("green", "green"),
            ("blue", "blue"),
            ("tcgreenness", "tcg"),
            ("tcbrightness", "tcb"),
            ("tir", "tir"),
            ("evi", "evi"),
        ]
        for token, mapped in aliases:
            if token in n:
                base = mapped
                break

        # Direct temporal/non-temporal fields.
        if "delta" in n and "ndvi" in n:
            return "delta"
        if base == "amp":
            return "amp"
        if base == "texture_variance":
            return "texture_variance"

        if base is None:
            return self._threshold_feature_key(input_key) if input_key else None

        # Recover season from the internal key when the label is abbreviated
        # (e.g. crop_ndvi_sp_min / crop_jul_ndvi_max).
        if temporal is None and input_key:
            ik = re.sub(r"[^a-z0-9]+", "", str(input_key).lower())
            if "jul" in ik or ik.endswith("smmin") or ik.endswith("smmax"):
                temporal = "jul"
            elif "apr" in ik or ik.endswith("spmin") or ik.endswith("spmax"):
                temporal = "apr"

        # Generic indicator labels such as "NDVI min/max" are intentionally
        # interpreted as the spring/April feature, matching the historical
        # convention of the script.
        if temporal is None:
            temporal = "apr"

        return f"{temporal}_{base}"

    def _threshold_feature_key(self, input_key):
        """Resolve a visible threshold field to the exact scientific feature array.

        This mapping is intentionally semantic rather than substring-based.
        The previous implementation matched any shared token such as ``apr``;
        therefore Apr_NDVI, Apr_MSAVI2 and Apr_NDMI could all receive the
        Apr_NDVI value. This resolver prevents cross-indicator contamination and
        adapts to every indicator set.
        """
        if str(input_key) in TEMPORAL_FEATURE_KEYS:
            return TEMPORAL_FEATURE_KEYS[str(input_key)]
        raw = str(input_key).strip().lower()
        n = re.sub(r"[^a-z0-9]+", "", raw)

        # General MSAVI2 min/max are a range constraint, not a point threshold.
        if n in {"msavi2min", "msavi2max", "msavimin", "msavimax"}:
            return None

        # Remove known class/preset prefixes and the threshold direction suffix.
        n = re.sub(r"^(s\d+|wat|bu|seb|crop|rang|fal|f)", "", n)
        n = re.sub(r"(min|max)$", "", n)

        # Normalize common aliases.
        aliases = {
            "msavi2": "msavi", "msavi": "msavi",
            "texturevariance": "texture_variance",
            "amplitude": "amp",
            "ndviamplitude": "amp",
            "deltandvi": "delta",
            "bs": "dbsi", "bsi": "dbsi",
        }
        for old, new in aliases.items():
            n = n.replace(old, new)

        # Temporal marker encoded in the field name.
        temporal = "apr"
        if n.startswith("jul"):
            temporal = "jul"
            n = n[3:]
        elif n.startswith("apr"):
            temporal = "apr"
            n = n[3:]
        elif n.endswith("sm"):
            temporal = "jul"
            n = n[:-2]
        elif n.endswith("sp"):
            temporal = "apr"
            n = n[:-2]

        # Direct non-seasonal features.
        if n in {"delta"}:
            return "delta"
        if n in {"amp", "phenologynviamplitude"}:
            return "amp"

        feature_map = {
            "ndvi": "ndvi", "msavi": "msavi", "savi": "savi",
            "ndmi": "ndmi", "ndwi": "ndwi", "mndwi": "mndwi",
            "ndbi": "ndbi", "dbsi": "dbsi", "nbr": "nbr",
            "swir1": "swir1", "swir2": "swir2", "nir": "nir",
            "red": "red", "green": "green", "blue": "blue",
            "tcg": "tcg", "tcb": "tcb", "tir": "tir",
            "evi": "evi", "texturevariance": "texture_variance",
            "ratioswir1nir": "ratio_swir1_nir",
        }
        base = feature_map.get(n)
        if not base:
            return None

        # Texture variance is not seasonal in the current feature stack.
        if base == "texture_variance":
            return base
        return f"{temporal}_{base}"

    def _point_to_pixel(self, point):
        """Convert map coordinates to raster row/column robustly, including rotation."""
        if not self.geo_tf:
            return None
        x, y = float(point.x()), float(point.y())
        gt = self.geo_tf
        a, b, c, d, e, f = gt
        det = b * f - c * e
        if abs(det) < 1e-15:
            return None
        dx, dy = x - a, y - d
        col = (dx * f - c * dy) / det
        row = (b * dy - e * dx) / det
        return int(np.floor(row)), int(np.floor(col))

    def _apply_threshold_values_from_feature_map(self, values, source_label):
        """Fill only fields that have an exact semantic feature mapping ; report EVERY field left unchanged and WHY."""
        applied = []
        skipped = []                 # champ sans variable associée (pas d'échantillonnage possible)
        not_loaded = []              # la variable n'existe pas dans cette session (preuves non chargées)
        no_value = []                # la variable existe mais n'a pas de valeur valide ici (NaN / hors données)
        for input_key, widget in self.inputs.items():
            feature_key = widget.property("feature_key") or self._threshold_feature_key(input_key)
            if not feature_key:
                skipped.append(input_key)
                continue
            if feature_key not in values:
                (no_value if feature_key in (self.spectral_arrays or {}) else not_loaded).append(input_key)
                continue
            value = values.get(feature_key)
            if value is None or not np.isfinite(value):
                no_value.append(input_key)
                continue
            widget.setText(f"{float(value):.3f}")
            applied.append(f"{input_key} = {float(value):.3f}")

        msg = f"{source_label}: {len(applied)} seuil(s) mis à jour."
        if applied:
            msg += "\n" + " | ".join(applied)
        if not_loaded:
            msg += ("\n⚠ NON mis à jour — variable non chargée dans cette session : " + ", ".join(_rule_label(k) for k in not_loaded)
                    + "\n   (ces champs sont ignorés au classement ; relancez le script et fournissez les données à la question « Preuves supplémentaires »)")
        if no_value:
            msg += "\n⚠ NON mis à jour — aucune valeur valide à cet endroit (NaN) : " + ", ".join(_rule_label(k) for k in no_value)
        if skipped:
            msg += "\nNon associés/non disponibles: " + ", ".join(skipped)
        self.probe_readout.setText(msg)
        self.log_area.setPlainText(msg)
        return applied

    def _missing_evidence_fields(self):
        """Champs de preuves (Temp_ / Terr_ / Ctx_) dont la variable n'est pas chargée : leurs seuils seraient ignorés."""
        have = self.spectral_arrays or {}
        return [k for k in self.inputs if k in TEMPORAL_FEATURE_KEYS and TEMPORAL_FEATURE_KEYS[k] not in have]

    def _show_missing_evidence_hint(self):
        """À l'ouverture : signale les champs de preuves sans données (au lieu de les laisser muets)."""
        try:
            miss = self._missing_evidence_fields()
            if miss:
                self.log_area.setPlainText(
                    "ℹ Variables NON chargées dans cette session — champs ignorés au classement, non remplis par Point / Poly / 7 Polygones :\n"
                    + ", ".join(_rule_label(k) for k in miss)
                    + "\n(pour les utiliser : relancez le script et choisissez les données à la question « Preuves supplémentaires »)")
        except Exception as exc:
            print(f"[Preuves] avertissement non affiché : {exc}")

    def apply_thresholds_from_polygon(self, qgs_points):
        if not self.geo_tf or not self.spectral_arrays:
            return
        sample_arr = next(iter(self.spectral_arrays.values()))
        rows, cols = sample_arr.shape
        wkt_pts = ", ".join([f"{pt.x()} {pt.y()}" for pt in qgs_points]) + f", {qgs_points[0].x()} {qgs_points[0].y()}"
        mem_drv = gdal.GetDriverByName("MEM")
        t_ds = mem_drv.Create("", cols, rows, 1, gdal.GDT_Byte)
        t_ds.SetGeoTransform(self.geo_tf)
        if self.proj_wkt:
            t_ds.SetProjection(self.proj_wkt)
        v_ds = ogr.GetDriverByName("Memory").CreateDataSource("mem")
        srs = osr.SpatialReference()
        if self.proj_wkt:
            srs.ImportFromWkt(self.proj_wkt)
        lyr = v_ds.CreateLayer("p", srs, ogr.wkbPolygon)
        feat = ogr.Feature(lyr.GetLayerDefn())
        feat.SetGeometry(ogr.CreateGeometryFromWkt(f"POLYGON(({wkt_pts}))"))
        lyr.CreateFeature(feat)
        gdal.RasterizeLayer(t_ds, [1], lyr, burn_values=[1])
        poly_mask = t_ds.GetRasterBand(1).ReadAsArray() == 1
        if not np.any(poly_mask):
            self.probe_readout.setText("⚠️ Aucun pixel.")
            return
        vals = {}
        for k, arr in self.spectral_arrays.items():
            valid = arr[poly_mask & np.isfinite(arr) & (arr != -9999.0)]
            if len(valid) > 0:
                vals[k] = float(np.mean(valid))
        self._apply_threshold_values_from_feature_map(vals, "📐 Moyennes du polygone")

    def on_pixel_clicked(self, point):
        if not self.geo_tf or not self.spectral_arrays:
            return
        rc = self._point_to_pixel(point)
        if rc is None:
            self.probe_readout.setText("⚠️ Géotransformation raster invalide.")
            return
        r, c = rc
        sample_arr = next(iter(self.spectral_arrays.values()))
        rows, cols = sample_arr.shape
        if not (0 <= r < rows and 0 <= c < cols):
            self.probe_readout.setText("⚠️ Le point est hors du raster.")
            return

        # Read the actual scientific feature arrays, not raw bands and not
        # substring-matched names. This keeps every indicator independent.
        vals = {}
        for k, arr in self.spectral_arrays.items():
            try:
                v = float(arr[r, c])
            except Exception:
                v = float("nan")
            if np.isfinite(v) and v != -9999.0:
                vals[k] = v

        applied = self._apply_threshold_values_from_feature_map(
            vals, f"🎯 Pixel [R:{r}, C:{c}] → valeurs exactes (étape {self.stage_num})"
        )
        if not applied:
            self.probe_readout.setText(
                f"🎯 Pixel [R:{r}, C:{c}] — aucun champ de seuil compatible avec les indicateurs actuels."
            )

    def stretch_band_to_byte(self, arr):
        valid = np.isfinite(arr) & (arr != -9999.0)
        if not np.any(valid):
            return np.zeros(arr.shape, dtype=np.uint8)
        p_low, p_high = np.percentile(arr[valid], (2, 98))
        if p_high <= p_low:
            p_high = p_low + 1e-4
        scaled = np.clip((arr - p_low) / (p_high - p_low), 0.0, 1.0) * 255.0
        scaled[~valid] = 0
        return scaled.astype(np.uint8)

    def update_canvas_composition(self):
        if not self.available_bands_dict or not self.geo_tf:
            return
        choice = self.cb_composition.currentText()
        if choice == COMP_ITEM_HR:
            self.show_hr_image()
            return
        if choice == COMP_ITEM_CUSTOM:
            arrays = self._pick_custom_bands()
            if arrays is None:
                self._revert_composition()
                return
            r, g, b_ = arrays
            HR_VIEW_STATE["mode"] = "custom"
        else:
            b = self.available_bands_dict
            if "Agriculture" in choice:
                r, g, b_ = b.get("swir1"), b.get("nir"), b.get("red")
            elif "Standard" in choice:
                r, g, b_ = b.get("nir"), b.get("red"), b.get("green")
            elif "Sol Nu" in choice:
                r, g, b_ = b.get("swir2"), b.get("swir1"), b.get("red")
            else:
                r, g, b_ = b.get("red"), b.get("green"), b.get("blue")
            HR_VIEW_STATE["mode"] = "stack"
        if r is None or g is None or b_ is None:
            return
        self._hr_extent_done = False
        self._render_rgb(r, g, b_)
        self._comp_prev_index = self.cb_composition.currentIndex()

    def _render_rgb(self, r, g, b_):
        """Écrit la composition RVB (étirement 2-98 %) et l'affiche sous le masque des étapes déjà classées."""
        rows, cols = r.shape
        comp_path = os.path.join(temp_dir(self.output_dir or "/tmp"), f"Canvas_{self.year}_{int(time.time()*1000)}.tif")
        for f in glob.glob(os.path.join(temp_dir(self.output_dir or "/tmp"), f"Canvas_{self.year}_*.tif")):
            try:
                os.remove(f)
            except Exception:
                pass
        ds = gdal.GetDriverByName("GTiff").Create(comp_path, cols, rows, 3, gdal.GDT_Byte, ["COMPRESS=LZW"])
        ds.SetGeoTransform(self.geo_tf)
        if self.proj_wkt:
            ds.SetProjection(self.proj_wkt)
        ds.GetRasterBand(1).WriteArray(self.stretch_band_to_byte(r))
        ds.GetRasterBand(2).WriteArray(self.stretch_band_to_byte(g))
        ds.GetRasterBand(3).WriteArray(self.stretch_band_to_byte(b_))
        ds.FlushCache()
        ds = None
        if self.current_layer:
            self.canvas.setLayers([])
        self.current_layer = QgsRasterLayer(comp_path, f"Comp_{self.year}")
        if self.current_layer.isValid():
            renderer = QgsMultiBandColorRenderer(self.current_layer.dataProvider(), 1, 2, 3)
            self.current_layer.setRenderer(renderer)
            layers = []
            if self.mask_layer is not None and self.mask_layer.isValid():
                layers.append(self.mask_layer)
            layers.append(self.current_layer)
            self.canvas.setLayers(self._with_change_layer(layers))
            self.canvas.setExtent(self.current_layer.extent())
            self.canvas.refresh()

        # Rebuild the cumulative mask over the new composition.
        if self.initial_lulc is not None:
            self.update_stage_mask_overlay(self.initial_lulc)

    # ---------- fond de carte : fausse couleur libre / image haute résolution ----------
    def _set_combo_silently(self, text):
        i = self.cb_composition.findText(text)
        if i >= 0:
            self.cb_composition.blockSignals(True)
            self.cb_composition.setCurrentIndex(i)
            self.cb_composition.blockSignals(False)
            self._comp_prev_index = i

    def _revert_composition(self):
        self.cb_composition.blockSignals(True)
        self.cb_composition.setCurrentIndex(getattr(self, "_comp_prev_index", 0))
        self.cb_composition.blockSignals(False)

    def _arrays_from_labels(self, labels):
        pool = build_composite_pool(self.stack_bands, self.spectral_arrays)
        if len(labels or []) == 3 and all(x in pool for x in labels):
            return [pool[x] for x in labels]
        return None

    def _pick_custom_bands(self):
        pool = build_composite_pool(self.stack_bands, self.spectral_arrays)
        if not pool:
            QMessageBox.information(self, "Fausse couleur", "Aucune bande disponible pour une composition personnalisée.")
            return None
        dlg = CompositionPickerDialog(list(pool), HR_VIEW_STATE.get("custom"), self)
        show_dialog(dlg)
        if dlg.result() != QDIALOG_ACCEPTED:
            return None
        labels = dlg.selection()
        HR_VIEW_STATE["custom"] = labels
        return self._arrays_from_labels(labels)

    def _ask_hr_path(self):
        start = os.path.dirname(HR_VIEW_STATE.get("hr_path") or "") or (self.output_dir or "")
        f, _ = QFileDialog.getOpenFileName(
            self, "Image haute résolution (pour faciliter l'échantillonnage)", start,
            "Images (*.tif *.tiff *.jp2 *.png *.jpg *.jpeg *.vrt *.img);;Tous (*)")
        return f or None

    def choose_hr_image(self):
        f = self._ask_hr_path()
        if not f:
            return
        HR_VIEW_STATE["hr_path"] = f
        if self.cb_composition.currentText() == COMP_ITEM_HR:
            self.show_hr_image()
        else:
            self.cb_composition.setCurrentIndex(self.cb_composition.findText(COMP_ITEM_HR))

    def _stack_extent(self):
        arr = self.initial_lulc if self.initial_lulc is not None else next(iter(self.available_bands_dict.values()))
        rows, cols = arr.shape
        x0, px, _r1, y0, _r2, py = self.geo_tf
        xs = (x0, x0 + cols * px)
        ys = (y0, y0 + rows * py)
        return QgsRectangle(min(xs), min(ys), max(xs), max(ys))

    def _study_crs(self):
        crs = QgsCoordinateReferenceSystem() if QgsCoordinateReferenceSystem is not None else None
        if crs is not None and self.proj_wkt and crs.createFromWkt(self.proj_wkt):
            return crs
        return None

    def _hr_layer_info(self, lyr, path):
        """Diagnostic de l'image : taille, CRS, recouvrement avec la zone d'étude (calculé dans le CRS du stack)."""
        info = {"path": path, "width": lyr.width(), "height": lyr.height(), "bands": lyr.bandCount(), "authid": "", "assumed_crs": False,
                "overlap": None, "pyramids": False, "size_mb": 0.0}
        try:
            info["size_mb"] = os.path.getsize(path) / 1048576.0
        except Exception:
            pass
        try:
            info["pyramids"] = bool(lyr.dataProvider().hasPyramids())
        except Exception:
            pass
        study = self._study_crs()
        img_crs = lyr.crs()
        if img_crs is None or not img_crs.isValid():
            info["assumed_crs"] = True
            if study is not None:
                lyr.setCrs(study)                      # image sans CRS : supposée dans le CRS du stack
                img_crs = study
        info["authid"] = img_crs.authid() if img_crs is not None and img_crs.isValid() else ""
        try:
            ext = lyr.extent()
            if study is not None and img_crs is not None and img_crs.isValid() and img_crs != study:
                ext = QgsCoordinateTransform(img_crs, study, QgsProject.instance()).transformBoundingBox(ext)
            info["overlap"] = hr_overlap_fraction(self._stack_extent(), ext)
            info["image_extent"] = _rect_tuple(ext)
        except Exception as exc:
            print(f"[Image HR] recouvrement non calculable : {exc}")
        return info

    def _resolve_hr_path(self, path):
        """La copie RAPIDE de cette image si elle existe (et est à jour), sinon l'original."""
        for d in (HR_VIEW_STATE.get("fast_dir"), os.path.join(self.output_dir or os.path.dirname(path), "HR_rapide")):
            if d:
                cand = fast_copy_target(path, d)
                if is_fast_copy_fresh(path, cand):
                    return cand
        return path

    def optimize_hr_image(self):
        """
        ⚡ Copie rapide de l'image haute résolution : TUILÉE 512 + pyramides INTERNES. Zoom / déplacement quasi instantanés ; prend plus de disque
        (par défaut SANS compression : le plus rapide). L'original n'est pas modifié ; la copie est réutilisée dans toutes les fenêtres et au lancement suivant.
        """
        path = HR_VIEW_STATE.get("hr_path")
        if not path or not os.path.exists(path):
            path = self._ask_hr_path()
            if not path:
                return False
            HR_VIEW_STATE["hr_path"] = path
        info = hr_source_info(path)
        if info is None:
            QMessageBox.warning(self, "Zoom rapide", f"Image illisible par GDAL :\n{path}")
            return False
        w, h, nb, bps = info
        est = estimate_fast_copy_mb(w, h, nb, bps)
        default_dir = HR_VIEW_STATE.get("fast_dir") or os.path.join(self.output_dir or os.path.dirname(path), "HR_rapide")
        folder = QFileDialog.getExistingDirectory(
            self, f"Dossier de la copie rapide (≈ {est / 1024:,.1f} Go sans compression)", default_dir if os.path.isdir(default_dir) else (self.output_dir or os.path.dirname(path)))
        if not folder:
            return False
        try:
            free_mb = shutil.disk_usage(folder).free / 1048576.0
        except OSError:
            free_mb = None
        if free_mb is not None and free_mb < est * 1.1:
            QMessageBox.warning(self, "Zoom rapide", f"Espace disque insuffisant dans ce dossier : besoin ≈ {est / 1024:,.1f} Go, libre {free_mb / 1024:,.1f} Go.\n"
                                                      "Choisissez un autre disque, ou une copie compressée (réponse « Non » à la question suivante) si elle tient.")
        compress = "NONE" if QMessageBox.question(
            self, "Zoom rapide",
            f"Image : {w}×{h} px, {nb} bande(s) — original {os.path.getsize(path) / 1048576.0:,.0f} Mo.\n\n"
            f"SANS compression : ≈ {est / 1024:,.1f} Go avec les pyramides, zoom le PLUS rapide.\n"
            "Compression LZW : plus petit (taux variable selon l'image), un peu plus lent.\n\n"
            "Cela peut prendre plusieurs minutes (QGIS ne répond plus pendant ce temps ; la progression s'affiche dans la console Python).\n\n"
            "Oui = sans compression (recommandé).\nNon = LZW.", QMB_YES | QMB_NO, QMB_YES) == QMB_YES else "LZW"
        if compress == "NONE" and free_mb is not None and free_mb < est * 1.1:
            return False
        dst = fast_copy_target(path, folder)
        last = {"p": -1}

        def _progress(frac, _msg, _data):
            pct = int(frac * 100)
            if pct // 10 != last["p"] // 10:
                print(f"[Zoom rapide] {pct} %")
            last["p"] = pct
            return 1

        try:
            build_fast_hr_copy(path, dst, compress, _progress)
        except Exception as exc:
            QMessageBox.critical(self, "Zoom rapide", f"La copie rapide n'a pas pu être créée :\n{exc}")
            return False
        HR_VIEW_STATE["fast_dir"] = folder
        QMessageBox.information(self, "Zoom rapide", f"Copie rapide créée ({os.path.getsize(dst) / 1048576.0:,.0f} Mo) :\n{dst}\n\nElle sera utilisée automatiquement.")
        self.show_hr_image()
        return True

    def show_hr_image(self):
        """Affiche l'image haute résolution du disque comme fond ; le canevas reste dans le CRS du stack (les clics restent exacts)."""
        path = HR_VIEW_STATE.get("hr_path")
        if not path or not os.path.exists(path):
            path = self._ask_hr_path()
            if not path:
                self._revert_composition()
                return
            HR_VIEW_STATE["hr_path"] = path
        shown = self._resolve_hr_path(path)
        lyr = QgsRasterLayer(shown, "Image HR")
        if not lyr.isValid():
            QMessageBox.warning(self, "Image haute résolution", f"Image illisible par QGIS :\n{shown}")
            HR_VIEW_STATE["hr_path"] = None
            self._revert_composition()
            return
        info = self._hr_layer_info(lyr, shown)
        info["fast"] = shown != path
        if info["overlap"] is not None and info["overlap"] <= 0.0:
            QMessageBox.warning(self, "Image haute résolution",
                                "Cette image ne recouvre PAS la zone d'étude (CRS différent mal reconnu, ou emprise ailleurs).\n\n"
                                f"Zone d'étude (CRS du stack) : {tuple(round(v, 1) for v in _rect_tuple(self._stack_extent()))}\n"
                                f"Image (ramenée au CRS du stack) : {tuple(round(v, 1) for v in info.get('image_extent', ()))}\n"
                                f"CRS de l'image : {info['authid'] or 'inconnu'}")
            HR_VIEW_STATE["hr_path"] = None
            self._revert_composition()
            return
        if shown == path and hr_needs_pyramids(info["width"], info["height"], info["size_mb"], info["pyramids"]):
            if QMessageBox.question(
                    self, "Image volumineuse : zoom lent",
                    f"Image de {info['width']}×{info['height']} px ({info['size_mb']:,.0f} Mo) sans pyramides : le zoom sera lent.\n\n"
                    "Créer une COPIE RAPIDE (tuilée + pyramides internes, plus d'espace disque, zoom quasi instantané) ?\n"
                    "(vous pouvez aussi le faire plus tard avec le bouton « ⚡ Zoom rapide »)", QMB_YES | QMB_NO, QMB_YES) == QMB_YES:
                if self.optimize_hr_image():
                    return
        study = self._study_crs()
        if study is not None:
            self.canvas.setDestinationCrs(study)
        self.current_layer = lyr
        layers = []
        if self.mask_layer is not None and self.mask_layer.isValid():
            layers.append(self.mask_layer)
        layers.append(lyr)
        self.canvas.setLayers(self._with_change_layer(layers))
        self.canvas.setExtent(self._stack_extent())
        self._hr_extent_done = True
        self.canvas.refresh()
        HR_VIEW_STATE["mode"] = "hr"
        self._comp_prev_index = self.cb_composition.currentIndex()
        if self.initial_lulc is not None:
            self.update_stage_mask_overlay(self.initial_lulc)
        try:
            self.log_area.setHtml(hr_diagnostic_html(info))
        except Exception:
            pass
        print("[Image HR] " + re.sub(r"<[^>]+>", "", hr_diagnostic_html(info)).replace("\n", " | "))

    def _restore_view_state(self):
        """Chaque nouvelle fenêtre d'étape reprend le fond choisi précédemment (image HR ou fausse couleur personnalisée)."""
        try:
            mode = HR_VIEW_STATE.get("mode")
            if mode == "hr" and HR_VIEW_STATE.get("hr_path") and os.path.exists(HR_VIEW_STATE["hr_path"]):
                self._set_combo_silently(COMP_ITEM_HR)
                self.show_hr_image()
            elif mode == "custom" and HR_VIEW_STATE.get("custom"):
                arrays = self._arrays_from_labels(HR_VIEW_STATE["custom"])
                if arrays:
                    self._set_combo_silently(COMP_ITEM_CUSTOM)
                    self._render_rgb(*arrays)
        except Exception as exc:
            print(f"[Fond de carte] état précédent non restauré : {exc}")

    def extract_samples_by_class(self, shp_path, field_name, feature_names=None):
        if not self.spectral_arrays or not self.geo_tf:
            return {}
        sample_arr = next(iter(self.spectral_arrays.values()))
        rows, cols = sample_arr.shape
        v_ds = ogr.Open(shp_path)
        if not v_ds:
            return {}
        lyr = v_ds.GetLayer()
        if lyr.FindFieldIndex(field_name, True) == -1:
            field_name = "class"
        mem_drv = gdal.GetDriverByName("MEM")
        t_ds = mem_drv.Create("", cols, rows, 1, gdal.GDT_Int32)
        t_ds.SetGeoTransform(self.geo_tf)
        gdal.RasterizeLayer(t_ds, [1], lyr, options=[f"ATTRIBUTE={field_name}"])
        train_labels = t_ds.GetRasterBand(1).ReadAsArray()
        names = feature_names or list(self.spectral_arrays.keys())
        names = [n for n in names if n in self.spectral_arrays]
        features = np.stack([self.spectral_arrays[n] for n in names], axis=-1)
        return {
            c: features[(train_labels == c) & np.all(np.isfinite(features), axis=-1)]
            for c in np.unique(train_labels[train_labels > 0])
        }

    def evaluate_separability(self):
        cfg = self.get_rf_config()
        if not cfg["shp"] or not os.path.exists(cfg["shp"]):
            return
        sample_dict = self.extract_samples_by_class(cfg["shp"], cfg["field"], STAGE_FEATURES.get(self.stage_num))
        if len(sample_dict) < 2:
            return
        report = ["<b>Séparabilité JM :</b><br>"]
        classes = sorted(sample_dict.keys())
        for i in range(len(classes)):
            for j in range(i + 1, len(classes)):
                jm = calculate_jm_distance(sample_dict[classes[i]], sample_dict[classes[j]])
                report.append(f"• {classes[i]} vs {classes[j]} : JM = {jm:.3f}")
        self.log_area.setHtml("<br>".join(report))

    def calculate_feature_importance(self):
        if not SKLEARN_AVAILABLE:
            self.log_area.setHtml("Scikit-learn non disponible.")
            return
        cfg = self.get_rf_config()
        if not cfg["shp"] or not os.path.exists(cfg["shp"]):
            return
        sample_dict = self.extract_samples_by_class(cfg["shp"], cfg["field"], STAGE_FEATURES.get(self.stage_num))
        if len(sample_dict) < 2:
            return
        feature_names = [n for n in STAGE_FEATURES.get(self.stage_num, list(self.spectral_arrays.keys())) if n in self.spectral_arrays]
        X_list, y_list = [], []
        for cid, mat in sample_dict.items():
            X_list.append(mat)
            y_list.append(np.full(len(mat), cid, dtype=int))
        rf = RandomForestClassifier(n_estimators=100, max_depth=15, random_state=42, n_jobs=RF_N_JOBS)
        rf.fit(np.vstack(X_list), np.concatenate(y_list))
        imp = rf.feature_importances_
        order = np.argsort(imp)[::-1]
        report = ["<b>Feature Importance :</b><br>"]
        for rank, idx in enumerate(order, 1):
            report.append(f"<b>{rank}. {feature_names[idx]}</b> : {imp[idx]*100:.2f} %")
        self.log_area.setHtml("<br>".join(report))

    def export_training_samples(self):
        cfg = self.get_rf_config()
        if not cfg["shp"] or not os.path.exists(cfg["shp"]):
            return
        sample_dict = self.extract_samples_by_class(cfg["shp"], cfg["field"], STAGE_FEATURES.get(self.stage_num))
        if not sample_dict:
            return
        csv_p = os.path.join(self.output_dir or "", f"Echantillons_{self.year}_S{self.stage_num}.csv")
        with open(csv_p, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["Classe_ID"] + [n for n in STAGE_FEATURES.get(self.stage_num, list(self.spectral_arrays.keys())) if n in self.spectral_arrays])
            for cid, matrix in sample_dict.items():
                for row in matrix:
                    w.writerow([cid] + [f"{v:.4f}" for v in row])
        QMessageBox.information(self, "Succès", f"Exporté :\n{csv_p}")

    def closeEvent(self, event):
        if hasattr(self, 'canvas'):
            self.canvas.setLayers([])
        super().closeEvent(event)



# ====================== FINAL SCIENTIFIC STAGE MAPPING (V16) ======================
# Hiérarchie exposée à l'utilisateur (numéro d'étape = ordre d'exécution) :
# 0 Administrative -> 1 Sebkha (masque stable) -> 2 Built-up -> 3 Water
# -> 4 Forest (7, dense + claire) -> [5 supprimée] -> 6 Cropland (5) -> 7 Fallow (6) -> 8 Rangeland (8)
# -> 9 Bareland / Rock (4) -> résidu (voisin le plus proche, puis Bareland).
# Aucune limite forestière ; aucune étape « végétation » intermédiaire.
STAGE_FEATURES = {
    1: ["apr_mndwi", "apr_dbsi", "apr_swir1", "apr_swir2", "apr_ndvi", "apr_msavi"],
    2: ["apr_ndbi", "apr_dbsi", "apr_swir1", "apr_swir2", "texture_variance", "apr_msavi"],
    3: ["apr_mndwi", "apr_ndwi", "jul_mndwi", "jul_ndwi", "apr_ndvi", "apr_swir1", "jul_swir1", "apr_msavi"],
    4: ["apr_msavi", "apr_ndvi", "amp"],
    5: ["apr_msavi", "amp", "jul_ndmi"],
    6: ["apr_msavi", "amp", "apr_dbsi", "ndvi_other_max", "ndvi_interannual_range", "ndvi_all_mean", "ndvi_all_std", "ndvi_low_frac", "ndvi_high_frac",
        "ndvi_bimodality", "terrain_slope_deg", "crop_frac_ctx"],
    7: ["apr_msavi", "amp", "apr_dbsi", "ndvi_other_max", "ndvi_interannual_range", "ndvi_all_mean", "ndvi_all_std", "ndvi_low_frac", "ndvi_high_frac",
        "ndvi_bimodality", "terrain_slope_deg", "crop_frac_ctx"],
    8: ["apr_dbsi", "apr_ndvi", "amp", "apr_msavi", "ndvi_other_max", "ndvi_interannual_range", "ndvi_all_mean", "ndvi_all_std", "ndvi_low_frac", "ndvi_high_frac",
        "ndvi_bimodality", "terrain_slope_deg", "crop_frac_ctx"],
}

# Codes de classe des polygones d'entraînement : 1 Built-up, 2 Water, 3 Sebkha, 4 Bareland, 5 Cropland, 6 Fallow,
# 7 Forest (y compris l'ancien Matorral : les polygones codés 9 sont lus comme 7), 8 Rangeland. Les négatifs d'une étape = les classes encore présentes dans son domaine.
# Étapes numérotées 1 à 8 : 1 Sebkha, 2 Built-up, 3 Water, 4 Forest, 5 Cropland, 6 Fallow, 7 Rangeland, 8 Bareland (anciens presets : migrés au démarrage).
STAGE_POSITIVE = {
    1: {3},              # Sebkha
    2: {1},              # Built-up
    3: {2},              # Water
    4: {7},              # Forest (dense + claire)
    5: {5},              # Cropland
    6: {6},              # Fallow
    7: {8},              # Rangeland
    8: {4},              # Bareland / Rock
}
STAGE_NEGATIVE = {
    1: {1, 2, 4, 5, 6, 7, 8},
    2: {2, 4, 5, 6, 7, 8},
    3: {1, 4, 5, 6, 7, 8},
    4: {5, 8, 6, 4},
    5: {8, 6, 4},
    6: {8, 4},
    7: {4},
    8: {5, 6, 7, 8},
}

# Reuse the original scientific threshold panels under the new stage numbers.
# Old: 1=Vegetation, 2=Water, 3=Built-up, 4=Sebkha
# New: 2=Built-up, 3=Water, 4=Vegetation.
_ORIG_INDICATOR_SETS = INDICATOR_SETS
# Stage 4 is now a dedicated Bareland/Rock stage.  Stage 5 is the Vegetated
# candidate mask, followed by Forest, Cropland, and Fallow/Rangeland.
_BARELAND_INDICATORS = {
    "Grok": {
        "bare_dbsi_min": ("1. Apr_DBSI min", 0.15, "🔴"),
        "bare_ndbi_min": ("2. Apr_NDBI min", -0.10, "🟠"),
        "bare_swir1_min": ("3. Apr_SWIR1 min", 0.20, "🟠"),
        "bare_swir2_min": ("4. Apr_SWIR2 min", 0.15, "🟡"),
        "bare_ndvi_max": ("5. Apr_NDVI max", 0.18, "🟡"),
        "bare_msavi_max": ("6. Apr_MSAVI2 max", 0.20, "🔒"),
        "bare_tex_min": ("7. Texture Variance min", 0.0, "🟢"),
    },
    "ChatGPT": {
        "bare_dbsi_min": ("1. Apr_DBSI min", 0.15, ""),
        "bare_ndbi_min": ("2. Apr_NDBI min", -0.10, ""),
        "bare_swir1_min": ("3. Apr_SWIR1 min", 0.20, ""),
        "bare_swir2_min": ("4. Apr_SWIR2 min", 0.15, ""),
        "bare_ndvi_max": ("5. Apr_NDVI max", 0.18, ""),
        "bare_msavi_max": ("6. Apr_MSAVI2 max", 0.20, ""),
        "bare_tex_min": ("7. Texture Variance min", 0.0, ""),
    },
    "Google": {
        "bare_dbsi_min": ("1. Apr_DBSI min", 0.15, "Important"),
        "bare_ndbi_min": ("2. Apr_NDBI min", -0.10, ""),
        "bare_swir1_min": ("3. Apr_SWIR1 min", 0.20, ""),
        "bare_swir2_min": ("4. Apr_SWIR2 min", 0.15, ""),
        "bare_ndvi_max": ("5. Apr_NDVI max", 0.18, ""),
        "bare_msavi_max": ("6. Apr_MSAVI2 max", 0.20, ""),
        "bare_tex_min": ("7. Texture Variance min", 0.0, ""),
    },
    "Original": {
        "bare_dbsi_min": ("1. DBSI min", 0.15, ""),
        "bare_ndbi_min": ("2. NDBI min", -0.10, ""),
        "bare_swir1_min": ("3. SWIR1 min", 0.20, ""),
        "bare_swir2_min": ("4. SWIR2 min", 0.15, ""),
        "bare_ndvi_max": ("5. NDVI max", 0.18, ""),
        "bare_msavi_max": ("6. MSAVI2 max", 0.20, ""),
        "bare_tex_min": ("7. Texture Variance min", 0.0, ""),
    },
}
_FALLOW_INDICATORS = {
    "Grok": {
        "fal_jul_msavi_max": ("1. Jul_MSAVI2 max — soutien", 0.12, "🟢"),
        "fal_jul_ndvi_max": ("2. Jul_NDVI max — soutien", 0.15, "🟡"),
        "fal_delta": ("3. Delta_NDVI — soutien", -0.05, "🟠"),
        "fal_dbsi_min": ("4. Apr_DBSI min — soutien", 0.10, "🟡"),
        "fal_amp": ("5. Amplitude — soutien", 0.15, "🟢"),
    },
    "ChatGPT": {
        "fal_jul_msavi_max": ("1. Jul_MSAVI2 max — soutien", 0.12, ""),
        "fal_jul_ndvi_max": ("2. Jul_NDVI max — soutien", 0.15, ""),
        "fal_delta": ("3. Delta_NDVI — soutien", -0.05, ""),
        "fal_dbsi_min": ("4. Apr_DBSI min — soutien", 0.10, ""),
        "fal_amp": ("5. Amplitude — soutien", 0.15, ""),
    },
    "Google": {
        "fal_jul_msavi_max": ("1. Jul_MSAVI2 max — soutien", 0.12, "Important"),
        "fal_jul_ndvi_max": ("2. Jul_NDVI max — soutien", 0.12, ""),
        "fal_delta": ("3. Delta_NDVI — soutien", -0.05, ""),
        "fal_dbsi_min": ("4. Apr_DBSI min — soutien", 0.12, ""),
        "fal_swir1_min": ("5. Jul/Spring SWIR1 min — soutien", 0.15, ""),
    },
    "Original": {
        "fal_msavi_max": ("3. MSAVI2 max — soutien", 0.22, ""),
        "fal_msavi_min": ("4. MSAVI2 min — soutien", 0.08, ""),
        "fal_bsi_min": ("5. BSI min — soutien", 0.10, ""),
    },
}

_RANGELAND_INDICATORS = {
    _set: {
        "rang_msavi_min": ("1. Rangeland MSAVI2 min", 0.15, "🔴"),
        "rang_msavi_max": ("2. Rangeland MSAVI2 max", 0.25, "🔴"),
        "rang_amp_max": ("3. Rangeland NDVI Amplitude max", 0.30, "🟠"),
    }
    for _set in ("Grok", "ChatGPT", "Google", "Original")
}

INDICATOR_SETS = {
    1: _ORIG_INDICATOR_SETS[4],    # Sebkha
    2: _ORIG_INDICATOR_SETS[3],
    3: _ORIG_INDICATOR_SETS[2],
    4: _ORIG_INDICATOR_SETS[1],    # Forest (dense + claire)
    5: _ORIG_INDICATOR_SETS[5],    # Cropland
    6: _FALLOW_INDICATORS,         # Fallow
    7: _RANGELAND_INDICATORS,      # Rangeland
    8: _BARELAND_INDICATORS,       # Bareland / Rock
}

# Scientific-default panel requested for the final scientific stages only.
# Stages 1-3 are intentionally left unchanged.
# NOMENCLATURE COMMUNE (toutes les étapes) :
#   « N. <Apr_|Jul_><INDICATEUR> <min|max> [— note] »  ;  Apr_ = 1re période du stack, Jul_ = 2e période (été) ;
#   « NDVI Amplitude », « Texture_Variance » sans période. Cette forme est comprise par les outils d'échantillonnage (Point / Poly / 7 Polygones).
#   Pastilles : 🔴 principal · 🟠 secondaire · 🟡 support · 🔒 limite générale · 💡 suggestion facultative (champ vide = non utilisé).
SCIENTIFIC_DEFAULT_STAGE_FIELDS = {
    1: {   # Sebkha (par défaut : masque stable ; ces seuils servent si vous choisissez « Aucun » ou un masque en LIMITE)
        "seb_tcb_min": ("1. Apr_TC_Brightness min", 0.30, "🔴 principal"),
        "seb_dbsi_min": ("2. Apr_DBSI min", 0.20, "🔴 principal"),
        "seb_msavi_max": ("3. Apr_MSAVI2 max", 0.08, "🟠 secondaire"),
        "seb_ndvi_max": ("4. Apr_NDVI max", 0.10, "🟡 support"),
        "seb_mndwi_min": ("5. Apr_MNDWI min", None, "💡 suggestion facultative : -0.10"),
        "seb_swir1_min": ("6. Apr_SWIR1 min", None, "💡 suggestion facultative : 0.25"),
        "seb_swir2_min": ("7. Apr_SWIR2 min", None, "💡 suggestion facultative : 0.20"),
        "seb_jul_ndvi_max": ("8. Jul_NDVI max", None, "💡 suggestion facultative : 0.08"),
    },
    2: {   # Built-up (par défaut : masque de l'année ; ces seuils servent si vous choisissez « Aucun » ou un masque en LIMITE)
        "bu_ndbi_min": ("1. Apr_NDBI min", 0.05, "🔴 principal"),
        "bu_dbsi_min": ("2. Apr_DBSI min", 0.10, "🔴 principal"),
        "bu_tcb_min": ("3. Apr_TC_Brightness min", 0.20, "🟠 secondaire"),
        "bu_msavi_max": ("4. Apr_MSAVI2 max", 0.10, "🟡 support"),
        "bu_swir1_min": ("5. Apr_SWIR1 min", None, "💡 suggestion facultative : 0.15"),
        "bu_swir2_min": ("6. Apr_SWIR2 min", None, "💡 suggestion facultative : 0.10"),
        "bu_tex_min": ("7. Texture_Variance min", None, "💡 suggestion facultative : 5.0"),
    },
    3: {   # Water : choix de l'étude = seulement les deux MNDWI >= 0 ; les autres indicateurs sont proposés mais NON utilisés tant qu'ils sont vides
        "wat_mndwi_min": ("1. Apr_MNDWI min", 0.00, "🔴 principal"),
        "wat_jul_mndwi_min": ("2. Jul_MNDWI min", 0.00, "🔴 principal"),
        "wat_ndwi_min": ("3. Apr_NDWI min", None, "💡 suggestion facultative : 0.05"),
        "wat_jul_ndwi_min": ("4. Jul_NDWI min", None, "💡 suggestion facultative : 0.00"),
        "wat_ndvi_max": ("5. Apr_NDVI max", None, "💡 suggestion facultative : 0.05"),
        "wat_swir1_max": ("6. Apr_SWIR1 max", None, "💡 suggestion facultative : 0.20"),
        "wat_nir_max": ("7. Apr_NIR max", None, "💡 suggestion facultative : 0.15"),
        "wat_msavi_max": ("8. Apr_MSAVI2 max", None, "💡 suggestion facultative : 0.05"),
    },
    4: {   # Forest = UNE classe (7) : forêt DENSE (bloc A) OU forêt CLAIRE / ancien Matorral (bloc B). Vider le bloc B = forêt dense seule.
        "msavi2_min": ("1. Apr_MSAVI2 min — limite inférieure", 0.20, "🔒 limite générale"),
        "f_apr_ndvi_min": ("2. Apr_NDVI min", 0.20, "🔴 principal"),
        "f_amp_max": ("3. NDVI Amplitude max", 0.18, "🟠 secondaire"),
        "fo_msavi2_min": ("4. Apr_MSAVI2 min — forêt claire (ex-Matorral)", 0.12, "🔒 limite générale"),
        "fo_msavi2_max": ("5. Apr_MSAVI2 max — forêt claire (ex-Matorral)", 0.20, "🔒 limite générale"),
        "fo_apr_ndvi_min": ("6. Apr_NDVI min — forêt claire (ex-Matorral)", 0.12, "🔴 principal"),
        "fo_amp_max": ("7. NDVI Amplitude max — forêt claire (ex-Matorral)", 0.25, "🟠 secondaire"),
    },
    5: {   # Cropland
        "msavi2_min": ("1. Apr_MSAVI2 min — limite inférieure", 0.20, "🔒 limite générale"),
        "crop_amp_min": ("2. NDVI Amplitude min", 0.30, "🔴 principal"),
        "crop_jul_ndmi_min": ("3. Jul_NDMI min", None, "🟠 secondaire"),
        "crop_jul_ndmi_max": ("4. Jul_NDMI max", None, "🟠 secondaire"),
    },
    6: {   # Fallow — AVANT Rangeland. Preuve temporelle (NDVI annuels, LPD) : champs « Temp_ » vides = non utilisés.
        "fal_msavi_max": ("1. Apr_MSAVI2 max", 0.10, "🟠 secondaire"),
        "fal_amp": ("2. NDVI Amplitude min", 0.10, "🟡 support"),
        "fal_dbsi_min": ("3. Apr_DBSI min", None, "🟡 support"),
        "fal_tmax_min": ("4. Temp_NDVI_Max min", None, "💡 suggestion facultative : 0.30"),
        "fal_tcount_min": ("5. Temp_NDVI_Annees_actives min", None, "💡 suggestion facultative : 1"),
        "fal_tamp_min": ("6. Temp_NDVI_Amplitude min", None, "💡 suggestion facultative : 0.20"),
        "fal_lpd_min": ("7. Temp_LPD min", None, "🟡 support (LPD : preuve secondaire)"),
        "fal_bimod_min": ("8. Temp_NDVI_Bimodality min", None, "💡 suggestion facultative : 0.30"),
        "fal_rain_corr_max": ("9. Temp_NDVI_Rain_Corr max", None, "💡 suggestion facultative : 0.40"),
        "fal_ctx_crop_min": ("10. Ctx_Crop_Fraction min", None, "💡 suggestion facultative : 0.15"),
        "fal_slope_max": ("11. Terr_Slope max", None, "💡 suggestion facultative : 8"),
    },
    7: {   # Rangeland
        "rang_msavi_min": ("1. Apr_MSAVI2 min", 0.15, "🔴 principal"),
        "rang_msavi_max": ("2. Apr_MSAVI2 max", 0.25, "🔴 principal"),
        "rang_amp_max": ("3. NDVI Amplitude max", 0.30, "🟠 secondaire"),
        "rang_mean_min": ("4. Temp_NDVI_Mean min", None, "💡 suggestion facultative : 0.12"),
        "rang_std_max": ("5. Temp_NDVI_Std max", None, "💡 suggestion facultative : 0.10"),
        "rang_rain_corr_min": ("6. Temp_NDVI_Rain_Corr min", None, "💡 suggestion facultative : 0.50"),
        "rang_ctx_crop_max": ("7. Ctx_Crop_Fraction max", None, "💡 suggestion facultative : 0.10"),
    },
    8: {   # Bareland / Rock
        "bare_dbsi_min": ("1. Apr_DBSI min", 0.15, "🔴 principal"),
        "bare_msavi_max": ("2. Apr_MSAVI2 max — limite supérieure", 0.10, "🔒 limite générale"),
        "bare_ndvi_max": ("3. Apr_NDVI max", 0.10, "🟠 secondaire"),
        "bare_amp_max": ("4. NDVI Amplitude max", 0.10, "🟡 support"),
        "bare_tmax_max": ("5. Temp_NDVI_Max max", None, "💡 suggestion facultative : 0.20"),
        "bare_tamp_max": ("6. Temp_NDVI_Amplitude max", None, "💡 suggestion facultative : 0.15"),
        "bare_lpd_max": ("7. Temp_LPD max", None, "🟡 support (LPD : preuve secondaire)"),
        "bare_lowfrac_min": ("8. Temp_NDVI_Low_Years min", None, "💡 suggestion facultative : 0.80"),
        "bare_slope_min": ("9. Terr_Slope min", None, "💡 suggestion facultative : 15"),
    },
}

# ---------------------------------------------------------------------------------------------------
# PREUVE TEMPORELLE (Fallow <-> Bareland) : NDVI annuels des AUTRES années + LPD. Jamais « LPD > seuil => Fallow » :
# la LPD est une preuve SECONDAIRE ; la preuve principale est le comportement NDVI sur plusieurs années.
# Un champ vide = non utilisé. Les variables ci-dessous n'existent que si une configuration temporelle est chargée.
# ---------------------------------------------------------------------------------------------------
TEMPORAL_ACTIVE_NDVI = 0.25       # NDVI annuel >= 0.25 : « année active » (modifiable)
TEMPORAL_FEATURE_KEYS = {
    # Fallow
    "fal_tmax_min": "ndvi_other_max", "fal_tcount_min": "ndvi_other_active_n", "fal_tamp_min": "ndvi_interannual_range", "fal_lpd_min": "lpd_class",
    "fal_bimod_min": "ndvi_bimodality", "fal_rain_corr_max": "ndvi_rain_corr", "fal_ctx_crop_min": "crop_frac_ctx", "fal_slope_max": "terrain_slope_deg",
    # Rangeland
    "rang_mean_min": "ndvi_all_mean", "rang_std_max": "ndvi_all_std", "rang_rain_corr_min": "ndvi_rain_corr", "rang_ctx_crop_max": "crop_frac_ctx",
    # Bareland
    "bare_tmax_max": "ndvi_other_max", "bare_tamp_max": "ndvi_interannual_range", "bare_lpd_max": "lpd_class",
    "bare_lowfrac_min": "ndvi_low_frac", "bare_slope_min": "terrain_slope_deg",
}
FALLOW_TEMPORAL_RULES = [("fal_tmax_min", "ndvi_other_max", ">="), ("fal_tcount_min", "ndvi_other_active_n", ">="),
                         ("fal_tamp_min", "ndvi_interannual_range", ">="), ("fal_lpd_min", "lpd_class", ">="),
                         ("fal_bimod_min", "ndvi_bimodality", ">="), ("fal_rain_corr_max", "ndvi_rain_corr", "<="),
                         ("fal_ctx_crop_min", "crop_frac_ctx", ">="), ("fal_slope_max", "terrain_slope_deg", "<=")]
RANGELAND_EVIDENCE_RULES = [("rang_mean_min", "ndvi_all_mean", ">="), ("rang_std_max", "ndvi_all_std", "<="),
                            ("rang_rain_corr_min", "ndvi_rain_corr", ">="), ("rang_ctx_crop_max", "crop_frac_ctx", "<=")]
BARELAND_TEMPORAL_RULES = [("bare_tmax_max", "ndvi_other_max", "<="), ("bare_tamp_max", "ndvi_interannual_range", "<="), ("bare_lpd_max", "lpd_class", "<="),
                           ("bare_lowfrac_min", "ndvi_low_frac", ">="), ("bare_slope_min", "terrain_slope_deg", ">=")]
# Variables ajoutées aux jeux de variables du Random Forest des étapes 6-8 (utilisées seulement si elles existent ; sans NaN fréquents)
EVIDENCE_RF_FEATURES = ["ndvi_other_max", "ndvi_interannual_range", "ndvi_all_mean", "ndvi_all_std", "ndvi_low_frac", "ndvi_high_frac",
                        "ndvi_bimodality", "terrain_slope_deg", "crop_frac_ctx"]

# Règles de seuillage des étapes 1-3 (clé du champ, variable, sens) : un champ VIDE n'est pas utilisé.
_MSAVI_GENERAL = [("msavi2_min", "apr_msavi", ">="), ("msavi2_max", "apr_msavi", "<=")]
SEBKHA_RULES = [("seb_tcb_min", "apr_tcb", ">="), ("seb_dbsi_min", "apr_dbsi", ">="), ("seb_msavi_max", "apr_msavi", "<="), ("seb_ndvi_max", "apr_ndvi", "<="),
                ("seb_mndwi_min", "apr_mndwi", ">="), ("seb_swir1_min", "apr_swir1", ">="), ("seb_swir2_min", "apr_swir2", ">="), ("seb_jul_ndvi_max", "jul_ndvi", "<="),
                ("seb_bsi_min", "apr_dbsi", ">="), ("seb_ndmi_max", "apr_ndmi", "<=")] + _MSAVI_GENERAL
BUILTUP_RULES = [("bu_ndbi_min", "apr_ndbi", ">="), ("bu_dbsi_min", "apr_dbsi", ">="), ("bu_tcb_min", "apr_tcb", ">="), ("bu_msavi_max", "apr_msavi", "<="),
                 ("bu_swir1_min", "apr_swir1", ">="), ("bu_swir2_min", "apr_swir2", ">="), ("bu_tex_min", "texture_variance", ">="), ("bu_bsi_min", "apr_dbsi", ">="),
                 ("bu_ndvi_max", "apr_ndvi", "<=")] + _MSAVI_GENERAL
WATER_RULES = [("wat_mndwi_min", "apr_mndwi", ">="), ("wat_jul_mndwi_min", "jul_mndwi", ">="), ("wat_ndwi_min", "apr_ndwi", ">="), ("wat_jul_ndwi_min", "jul_ndwi", ">="),
               ("wat_ndvi_max", "apr_ndvi", "<="), ("wat_swir1_max", "apr_swir1", "<="), ("wat_nir_max", "apr_nir", "<="), ("wat_msavi_max", "apr_msavi", "<="),
               ("wat_blue_max", "apr_blue", "<=")] + _MSAVI_GENERAL
_RULE_WARNED = set()


RULE_TRACE = []          # journal de l'ENTONNOIR : une entrée par condition appliquée (vidé par l'aperçu)


def rule_trace_note(label, before, after, note=""):
    """Ajoute une étape à l'entonnoir (ex. le bloc de seuils spectraux d'une étape)."""
    RULE_TRACE.append({"label": label, "before": int(before), "after": int(after), "note": note})
    if len(RULE_TRACE) > 400:
        del RULE_TRACE[:200]


def th_by_rules(th, base, rules, features):
    """
    Applique les seuils renseignés (champ vide = ignoré) ; un NaN ne satisfait jamais un seuil.
    Variable absente du stack, ou SANS valeur valide sur >= 99 % des pixels restants (fichier mal aligné, hors zone...) : condition ignorée
    avec un avertissement, au lieu de vider silencieusement la classe. Chaque condition est consignée dans RULE_TRACE (entonnoir de l'aperçu).
    """
    c = base.copy()
    for key, feat, op in rules:
        v = th.get(key)
        if v is None or (isinstance(v, str) and not v.strip()):
            continue
        n_before = int(np.count_nonzero(c))
        entry = {"key": key, "feat": feat, "op": op, "value": float(v), "before": n_before, "after": n_before, "note": "", "nan_pct": 0.0}
        if feat not in features:
            entry["note"] = "ignorée : variable absente (non chargée)"
            if (key, feat) not in _RULE_WARNED:
                _RULE_WARNED.add((key, feat))
                print(f"    [ATTENTION] seuil « {key} » ignoré : la variable {feat} est absente du stack.")
            RULE_TRACE.append(entry)
            continue
        arr = features[feat]
        n_fin = int(np.count_nonzero(c & np.isfinite(arr)))
        entry["nan_pct"] = 100.0 * (1.0 - n_fin / n_before) if n_before else 0.0
        if n_before > 0 and n_fin < max(1, int(0.01 * n_before)):
            entry["note"] = "ignorée : variable sans valeur valide sur ≥ 99 % des pixels (fichier mal aligné ? hors zone ?)"
            if (key, feat, "nan") not in _RULE_WARNED:
                _RULE_WARNED.add((key, feat, "nan"))
                print(f"    [ATTENTION] seuil « {key} » IGNORÉ : la variable {feat} n'a de valeur valide que sur {n_fin:,} des {n_before:,} pixels restants "
                      "(vérifiez l'alignement / le CRS / l'emprise du fichier source).")
            RULE_TRACE.append(entry)
            continue
        c &= (arr >= float(v)) if op == ">=" else (arr <= float(v))
        entry["after"] = int(np.count_nonzero(c))
        if entry["nan_pct"] >= 30.0:
            entry["note"] = f"variable invalide (NaN) sur {entry['nan_pct']:.0f} % des pixels restants : ces pixels ne satisfont jamais la condition"
        RULE_TRACE.append(entry)
        if len(RULE_TRACE) > 400:
            del RULE_TRACE[:200]
    return c


def _rule_label(key):
    for fields in SCIENTIFIC_DEFAULT_STAGE_FIELDS.values():
        if key in fields:
            return re.sub(r"^\d+\.\s*", "", fields[key][0])
    return key


def funnel_lines(n_domain, trace, n_final, px_ha=None):
    """Entonnoir des seuils (HTML) : pixels restants après chaque condition, et la PREMIÈRE condition qui vide le résultat. [] si aucun seuil."""
    if not trace:
        return []

    def fmt(n):
        return f"{n:,} px" + (f" = {n * px_ha:,.1f} ha" if px_ha else "")
    out = ["<br><b>Entonnoir des seuils (pixels restants après chaque condition) :</b><br>", f"• Domaine de l'étape : {fmt(int(n_domain))}<br>"]
    culprit = None
    for e in trace:
        label = e["label"] if "label" in e else f"{_rule_label(e['key'])} {'≥' if e['op'] == '>=' else '≤'} {e['value']:g}"
        note = e.get("note", "")
        out.append(f"• {label} : <b>{fmt(e['after'])}</b>" + (f" <i>— {note}</i>" if note else "") + "<br>")
        if culprit is None and e["before"] > 0 and e["after"] == 0 and not note.startswith("ignorée"):
            culprit = label
    if int(n_final) == 0 and culprit is not None:
        out.append(f"<span style='color:#c62828;font-weight:bold'>⚠ Le résultat devient vide à cause de : {culprit}</span> — élargissez ou videz ce champ.<br>")
    elif int(n_final) == 0:
        out.append("<span style='color:#c62828;font-weight:bold'>⚠ Résultat vide : voir les conditions ci-dessus.</span><br>")
    return out


def scientific_default_values(stage_n):
    """Valeurs par défaut (non vides) du panneau « Scientific default » d'une étape."""
    return {k: v[1] for k, v in SCIENTIFIC_DEFAULT_STAGE_FIELDS.get(stage_n, {}).items() if v[1] is not None}


# ====================== MAIN PROCESSING ======================

class ChangeStatsDialog(QDialog):
    """
    Changement vs année précédente : NET ≠ ÉCHANGE. Onglets : « Classe de l'étape » (tableau + origine du gain / destination de la perte),
    « Toutes les classes » (stabilité %, perte, gain, net, swap, brut + ligne PAYSAGE), « Transitions » (clic sur une ligne = pixels surlignés
    sur la carte de la fenêtre d'étape). Les transitions improbables sont marquées 🔴 / 🟠. Aucune carte ni aucun fichier n'est modifié.
    """

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle("Changement entre deux années — Net ≠ Échange")
        self.resize(1180, 680)
        self._trans_pairs = []
        self._data = None
        lay = QVBoxLayout(self)
        self.banner = QLabel("")
        self.banner.setWordWrap(True)
        lay.addWidget(self.banner)
        self.tabs = QTabWidget()
        w1 = QWidget()
        l1 = QVBoxLayout(w1)
        self.tbl_stage, self.tbl_break = QTableWidget(), QTableWidget()
        self.lbl_stage_title = QLabel("<b>Classe de cette étape</b>")
        self.lbl_break_title = QLabel("<b>Gagné et perdu : d'où vient la classe, où elle part</b>")
        self.lbl_break_title.setWordWrap(True)
        l1.addWidget(self.lbl_stage_title)
        l1.addWidget(self.tbl_stage)
        l1.addWidget(self.lbl_break_title)
        l1.addWidget(self.tbl_break)
        self.tbl_all, self.tbl_trans = QTableWidget(), QTableWidget()
        self.tabs.addTab(w1, "Classe de l'étape")
        self.tabs.addTab(self.tbl_all, "Toutes les classes")
        w3 = QWidget()
        l3 = QVBoxLayout(w3)
        self.chk_stage = QCheckBox("Seulement les transitions de la classe de cette étape (décochez pour voir aussi les classes des étapes déjà validées)")
        self.chk_stage.setChecked(True)
        self.chk_stage.toggled.connect(self.refresh)
        l3.addWidget(self.chk_stage)
        l3.addWidget(self.tbl_trans)
        self.tabs.addTab(w3, "Transitions (clic = carte)")
        lay.addWidget(self.tabs, 1)
        for tbl in (self.tbl_stage, self.tbl_break, self.tbl_all, self.tbl_trans):
            for enum_path in (("NoEditTriggers",), ("EditTrigger", "NoEditTriggers")):
                try:
                    e = QAbstractItemView
                    for part in enum_path:
                        e = getattr(e, part)
                    tbl.setEditTriggers(e)
                    break
                except Exception:
                    continue
            for enum_path in (("SelectRows",), ("SelectionBehavior", "SelectRows")):
                try:
                    e = QAbstractItemView
                    for part in enum_path:
                        e = getattr(e, part)
                    tbl.setSelectionBehavior(e)
                    break
                except Exception:
                    continue
        self.tbl_trans.itemSelectionChanged.connect(self.on_transition_selected)
        row = QHBoxLayout()
        row.addWidget(QLabel("<b>Carte :</b>"))
        self.cb_map = QComboBox()
        self.cb_map.addItems([lab for _m, lab in CHANGE_MAP_MODES])
        self.cb_map.currentIndexChanged.connect(self.on_map_mode_changed)
        row.addWidget(self.cb_map, 1)
        self.lbl_legend = QLabel(change_legend_html(None))
        self.lbl_legend.setWordWrap(True)
        row.addWidget(self.lbl_legend, 3)
        lay.addLayout(row)
        row2 = QHBoxLayout()
        b_csv = QPushButton("💾 Exporter les tableaux (CSV)")
        b_csv.clicked.connect(self.export_csv)
        b_close = QPushButton("Fermer")
        b_close.clicked.connect(self.close)
        row2.addWidget(b_csv)
        row2.addWidget(b_close)
        lay.addLayout(row2)

    def set_data(self, analysis, stage_class, ctx):
        self._data = (analysis, stage_class, ctx)
        try:
            modes = [m for m, _l in CHANGE_MAP_MODES]
            self.cb_map.blockSignals(True)
            self.cb_map.setCurrentIndex(modes.index(getattr(self.owner, "change_mode", "none")))
            self.cb_map.blockSignals(False)
        except Exception:
            pass
        lab = change_labels(analysis, ctx)
        hdr = change_table_headers(analysis, ctx)
        py, yr = analysis.get("prev_year"), (ctx or {}).get("yr")
        if analysis.get("reverse"):
            py, yr = analysis.get("older_year"), analysis.get("newer_year")
        gap = (int(yr) - int(py)) if (yr and py) else None
        cls_name = CLASS_NAMES.get(int(stage_class), "") if stage_class else ""
        try:
            self.setWindowTitle(f"Changement {lab['O']} → {lab['N']} — Net ≠ Échange" if lab else "Changement entre deux années — Net ≠ Échange")
            self.lbl_legend.setText(change_legend_html(lab))
            for _i, _t in enumerate(change_mode_labels(lab)):
                self.cb_map.setItemText(_i, _t)
            self.lbl_stage_title.setText(f"<b>« {cls_name} » : {lab['O']} → {lab['N']}</b>" if (lab and cls_name) else "<b>Classe de cette étape</b>")
            self.lbl_break_title.setText(
                f"<b>« {cls_name} » entre {lab['O']} et {lab['N']} : d'où vient ce qui est GAGNÉ, où part ce qui est PERDU</b><br>"
                f"<i>GAGNÉ = c'est « {cls_name} » en {lab['N']} mais pas en {lab['O']} (la ligne dit ce que c'était en {lab['O']}). "
                f"PERDU = c'était « {cls_name} » en {lab['O']} mais plus en {lab['N']} (la ligne dit ce que c'est devenu en {lab['N']}).</i>" if (lab and cls_name) else
                "<b>Gagné et perdu : d'où vient la classe, où elle part</b>")
        except Exception:
            pass
        ls = analysis["landscape"]
        n = max(ls["compared_px"], 1)
        px = analysis["px_ha"]
        lines = [(f"<b>Comparaison {lab['O']} → {lab['N']}</b> (Δ {lab['gap']} ans) — année en cours : <b>{lab['cur']}</b> · année de référence : <b>{lab['ref']}</b>. "
                  f"Les tableaux suivent toujours le sens du temps : {lab['O']} est l'année la plus ancienne." if lab else f"<b>Comparaison {py} → {yr}</b>") + f" — {ls['compared_px'] * px:,.0f} ha classés aux 2 dates"
                 + (f", {analysis['pending_px'] * px:,.0f} ha pas encore classés à cette étape" if analysis["pending_px"] else "")
                 + f"<br>Changement total <b>{100.0 * ls['changed_px'] / n:.1f} %</b> = net {100.0 * ls['net_px'] / n:.1f} % + échange (swap) {100.0 * ls['exchange_px'] / n:.1f} % "
                   f"+ déplacement {100.0 * ls['shift_px'] / n:.1f} %. Seul le NET est une vraie variation de quantité ; échange et déplacement = remplacement spatial."]
        mine, others = relevant_alerts(analysis, stage_class)
        for a in mine[:6]:
            lines.append(f"<span style='color:{'#c62828' if a['level'] == 'red' else '#ef6c00'};font-weight:bold'>{'🔴' if a['level'] == 'red' else '🟠'} {a['text']}</span>")
        if not mine:
            lines.append(f"<span style='color:#2e7d32'>✅ Aucune transition improbable concernant la classe « {CLASS_NAMES.get(int(stage_class), '')} » de cette étape.</span>" if stage_class
                         else "<span style='color:#2e7d32'>✅ Aucune transition improbable importante.</span>")
        if others:
            lines.append(f"<i>ℹ {len(others)} alerte(s) concernent des classes d'étapes déjà validées (ex. {others[0]['text'].split(' :')[0]}) : "
                         "elles ne dépendent pas des seuils de cette étape — décochez la case de l'onglet « Transitions » pour les voir.</i>")
        self.banner.setText("<br>".join(lines))
        classes = {int(stage_class)} if stage_class else None
        stage_rows = [r for r in change_class_table(analysis, classes=classes)[:-1]] if classes else []
        fill_change_table(self.tbl_stage, hdr["classes"], stage_rows)
        fill_change_table(self.tbl_break, breakdown_headers(analysis, ctx), stage_class_breakdown(analysis, stage_class, ctx) if stage_class else [])
        all_rows = change_class_table(analysis)
        colors = {}
        for ri, r in enumerate(all_rows[:-1]):
            cid = int(r[0].split(" ")[0])
            if stage_class and cid == int(stage_class):
                colors[ri] = (205, 225, 255)                      # la classe de CETTE étape en bleu clair
            elif any(a["from"] == cid and a["kind"] == "stability" for a in analysis["alerts"]):
                colors[ri] = (255, 225, 205)
        fill_change_table(self.tbl_all, hdr["classes"], all_rows, colors)
        only = stage_class if (stage_class and self.chk_stage.isChecked()) else None
        trans = filtered_transitions(analysis, only, 120)
        self._trans_pairs = [(t["from"], t["to"]) for t in trans]
        alert_level = {(a["from"], a["to"]): a["level"] for a in analysis["alerts"] if a["kind"] == "transition"}
        tcolors = {ri: ((255, 215, 215) if alert_level[p] == "red" else (255, 235, 205)) for ri, p in enumerate(self._trans_pairs) if p in alert_level}
        fill_change_table(self.tbl_trans, hdr["transitions"], change_transition_table(analysis, limit=120, only_class=only), tcolors)

    def refresh(self, *_a):
        """Redessine les tableaux avec la case « seulement cette classe » (sans recalculer l'analyse)."""
        if self._data:
            self.set_data(*self._data)

    def on_transition_selected(self):
        try:
            r = self.tbl_trans.currentRow()
            if 0 <= r < len(self._trans_pairs):
                self.owner.show_transition_on_map(*self._trans_pairs[r])
                self.cb_map.blockSignals(True)
                self.cb_map.setCurrentIndex([m for m, _l in CHANGE_MAP_MODES].index("transition"))
                self.cb_map.blockSignals(False)
        except Exception as exc:
            print(f"[Changement] sélection de transition : {exc}")

    def on_map_mode_changed(self, idx=None):
        i = self.cb_map.currentIndex()
        self.owner.set_change_map_mode(CHANGE_MAP_MODES[i][0] if 0 <= i < len(CHANGE_MAP_MODES) else "none")

    def export_csv(self):
        if not self._data:
            return
        analysis, stage_class, ctx = self._data
        out = change_dir(self.owner.output_dir or os.getcwd())          # <résultats>/Changement/
        tag = f"Stage{self.owner.stage_num}_{ctx.get('prev_year')}_{ctx.get('yr')}"
        hdr = change_table_headers(analysis, ctx)
        p1 = write_csv_rows(os.path.join(out, f"Change_{tag}_Classes.csv"), [hdr["classes"]] + change_class_table(analysis))
        p2 = write_csv_rows(os.path.join(out, f"Change_{tag}_Transitions.csv"), [hdr["transitions"]] + change_transition_table(analysis, limit=10 ** 6))
        QMessageBox.information(self, "Changement", f"Tableaux exportés :\n{p1}\n{p2}")


def vector_area_ha_in_raster_crs(shp_path, raster_wkt):
    """True polygon area (ha) after transforming to the raster CRS.
    Used only by final AREA QA; it does not alter classification.
    """
    if not shp_path or not os.path.exists(shp_path):
        return float("nan")
    ds = ogr.Open(shp_path)
    if ds is None:
        return float("nan")
    lyr = ds.GetLayer()
    src_srs = lyr.GetSpatialRef()
    if src_srs is None or not raster_wkt:
        return float("nan")
    dst_srs = osr.SpatialReference()
    if dst_srs.ImportFromWkt(raster_wkt) != 0:
        return float("nan")
    ct = None
    if not src_srs.IsSame(dst_srs):
        ct = osr.CoordinateTransformation(src_srs, dst_srs)
    area_m2 = 0.0
    for feat in lyr:
        geom = feat.GetGeometryRef()
        if geom is None:
            continue
        g = geom.Clone()
        if ct is not None:
            try:
                g.Transform(ct)
            except Exception:
                continue
        area_m2 += abs(float(g.GetArea()))
    ds = None
    return area_m2 / 10000.0


def make_vector_mask(shp_path, rows, cols, geo_tf, proj_wkt):
    mask = np.zeros((rows, cols), dtype=bool)
    if not shp_path or not os.path.exists(shp_path):
        return mask
    ds = ogr.Open(shp_path)
    if not ds:
        return mask
    mem = gdal.GetDriverByName("MEM").Create("", cols, rows, 1, gdal.GDT_Byte)
    mem.SetGeoTransform(geo_tf)
    if proj_wkt:
        mem.SetProjection(proj_wkt)
    gdal.RasterizeLayer(mem, [1], ds.GetLayer(), burn_values=[1])
    mask = mem.GetRasterBand(1).ReadAsArray() == 1
    return mask


def _find_named_input(parent_dir, stem, allowed_exts=(".shp", ".tif", ".tiff")):
    """Find an input by exact filename stem, recursively, without user interaction."""
    wanted = stem.lower()
    candidates = []
    for root, dirs, files in os.walk(parent_dir):
        for fn in files:
            base, ext = os.path.splitext(fn)
            if ext.lower() in allowed_exts and base.lower() == wanted:
                candidates.append(os.path.join(root, fn))
    candidates.sort(key=lambda x: (len(x), x.lower()))
    return candidates[0] if candidates else None


def _find_forest_boundary(parent_dir):
    """Find the forest boundary polygon automatically from common exact names, then by keyword."""
    preferred = [
        "Forest_Finale", "Forest_Final", "Forest_Boundary", "ForestBoundary",
        "Foret_Finale", "Foret_Final", "Foret_Boundary", "Foret", "Forest"
    ]
    for stem in preferred:
        hit = _find_named_input(parent_dir, stem, (".shp",))
        if hit:
            return hit
    hits = []
    for root, dirs, files in os.walk(parent_dir):
        for fn in files:
            base, ext = os.path.splitext(fn)
            if ext.lower() != ".shp":
                continue
            low = base.lower()
            if any(k in low for k in ("forest", "foret", "foretieres", "forest_boundary")):
                hits.append(os.path.join(root, fn))
    hits.sort(key=lambda x: (len(x), x.lower()))
    return hits[0] if hits else None


def _mask_from_input(path, rows, cols, geo_tf, proj_wkt):
    """Raster/vector mask reader for automatic Built-up masks."""
    if not path or not os.path.exists(path):
        return np.zeros((rows, cols), dtype=bool)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".shp":
        return make_vector_mask(path, rows, cols, geo_tf, proj_wkt)
    ds = gdal.Open(path, gdal.GA_ReadOnly)
    if ds is None or ds.RasterCount < 1:
        return np.zeros((rows, cols), dtype=bool)
    arr = ds.GetRasterBand(1).ReadAsArray()
    if arr is None:
        return np.zeros((rows, cols), dtype=bool)
    if arr.shape != (rows, cols):
        mem = gdal.GetDriverByName("MEM").Create("", cols, rows, 1, gdal.GDT_Byte)
        mem.SetGeoTransform(geo_tf)
        if proj_wkt:
            mem.SetProjection(proj_wkt)
        gdal.ReprojectImage(ds, mem, ds.GetProjection(), proj_wkt or ds.GetProjection(), gdal.GRA_NearestNeighbour)
        arr = mem.GetRasterBand(1).ReadAsArray()
    return np.isfinite(arr) & (arr != 0)


def _detect_temporal_periods(names):
    """
    Détecte les préfixes temporels réellement présents dans le stack.

    Exemples:
      Apr_1985_B4_NIR -> Apr
      Mar_2007_B4_NIR -> Mar
      Jul_2007_B4_NIR -> Jul

    Le script ne suppose donc plus que la première date est toujours ``Apr``.
    """
    periods = []
    for n in names:
        m = re.match(r'^\s*([A-Za-z]{3,12})[_-]\d{4}[_-]', str(n))
        if m:
            p = m.group(1)
            if p.lower() not in {x.lower() for x in periods}:
                periods.append(p)
    if not periods:
        raise RuntimeError(
            "Impossible de détecter les périodes temporelles dans le stack.\n"
            "Les noms attendus ressemblent à 'Apr_1985_B4_NIR' ou 'Mar_2007_B4_NIR'.\n"
            f"Bands disponibles (premiers): {names[:20]}"
        )

    # La seconde période est normalement Jul/Aug. Si elle n'existe pas, on
    # prend la deuxième période réellement présente.
    summer = next((p for p in periods if p.lower() in ('jul', 'aug')), None)
    if summer is None and len(periods) >= 2:
        summer = periods[1]
    if summer is None:
        summer = periods[0]
    return periods[0], summer, periods


def read_stack_bands(stack_path):
    ds = gdal.Open(stack_path, gdal.GA_ReadOnly)
    if ds is None:
        raise RuntimeError(f"Impossible d'ouvrir le stack: {stack_path}")

    cols, rows = ds.RasterXSize, ds.RasterYSize
    geo_tf = ds.GetGeoTransform()
    proj_wkt = ds.GetProjection()

    names = []
    hdr = os.path.splitext(stack_path)[0] + ".hdr"
    hdr_ignore = None
    if os.path.exists(hdr):
        try:
            txt = open(hdr, "r", encoding="utf-8", errors="ignore").read()
            m = re.search(r'band names\s*=\s*\{([^}]+)\}', txt, re.I | re.S)
            if m:
                names = [x.strip().replace('"', '').replace("'", "") for x in m.group(1).split(",")]
            mi = re.search(r'(?:data\s+ignore\s+value|data\s+ignore\s+value)\s*=\s*([-+0-9.eE]+)', txt, re.I)
            if mi:
                hdr_ignore = float(mi.group(1))
        except Exception:
            pass

    if len(names) != ds.RasterCount:
        names = []
        for i in range(1, ds.RasterCount + 1):
            d = ds.GetRasterBand(i).GetDescription()
            names.append(d if d else f"B{i}")

    arrays = {}
    for i, n in enumerate(names, 1):
        progress_tick(i - 1, len(names), f"bande {i} / {len(names)} : {n}")
        try:
            band = ds.GetRasterBand(i)
            arr = band.ReadAsArray().astype(np.float32)
            nodata = band.GetNoDataValue()
            if nodata is None:
                nodata = hdr_ignore
            if nodata is not None and np.isfinite(nodata):
                arr[arr == float(nodata)] = np.nan
            arrays[n] = arr
        except Exception:
            arrays[n] = np.full((rows, cols), np.nan, dtype=np.float32)

    # Fail fast if the stack metadata is unusable. This replaces the previous
    # silent all-zero behaviour that could corrupt both the preview and the
    # classification.
    first_period, summer_period, all_periods = _detect_temporal_periods(names)
    print(
        f"[Stack] {os.path.basename(stack_path)} | "
        f"période principale={first_period} | été={summer_period} | "
        f"périodes détectées={all_periods}"
    )

    return ds, rows, cols, geo_tf, proj_wkt, names, arrays


_MISSING_BAND_WARNINGS = []


def find_band(names, arrays, patterns, fallback=None, required=False, label=None):
    """Recherche robuste d'un band. Un band requis ne peut plus devenir des zéros silencieusement."""
    if isinstance(patterns, str):
        patterns = [patterns]
    for n in names:
        for p in patterns:
            if re.search(p, n, re.I):
                arr = arrays[n]
                if required and not np.any(np.isfinite(arr)):
                    raise RuntimeError(
                        f"Band trouvé mais inutilisable: {label or n}.\n"
                        f"Nom du band: {n}\nLe band ne contient aucune valeur finie."
                    )
                return arr
    if fallback is not None:
        return fallback
    if required:
        preview = ", ".join(str(x) for x in names[:40])
        raise RuntimeError(
            f"BAND OBLIGATOIRE INTROUVABLE: {label or patterns}.\n"
            "Le script refuse maintenant de remplacer un band manquant par des zéros.\n"
            f"Bands disponibles (jusqu'à 40): {preview}"
        )
    # Optional bands remain NaN (never zero), but the omission is explicitly
    # recorded so it can be shown to the user at the beginning of the year.
    _MISSING_BAND_WARNINGS.append(str(label or patterns))
    return np.full_like(next(iter(arrays.values())), np.nan, dtype=np.float32)


def _unload_layers_by_path(path):
    """
    BUGFIX (Windows "Permission denied" lors de la ré-exécution d'une année) :
    si ce .tif est encore chargé comme couche QGIS (ex: résultat d'un run
    précédent dans la même session), le fichier reste verrouillé par le
    système, et GDAL échoue en essayant de le supprimer avant de le recréer :
        RuntimeError: Deleting <path> failed: Permission denied
    On retire donc du projet toute couche qui pointe vers ce fichier exact
    avant de tenter de le supprimer/recréer.
    """
    try:
        norm_path = os.path.normcase(os.path.abspath(path))
        to_remove = []
        for lyr_id, lyr in QgsProject.instance().mapLayers().items():
            try:
                src = lyr.source().split("|")[0]
                if os.path.normcase(os.path.abspath(src)) == norm_path:
                    to_remove.append(lyr_id)
            except Exception:
                continue
        for lyr_id in to_remove:
            QgsProject.instance().removeMapLayer(lyr_id)
    except Exception:
        pass


def _unique_renamed_path(path):
    """Chemin horodaté unique à côté de `path` (repli si fichier verrouillé)."""
    base, ext = os.path.splitext(path)
    stamp = time.strftime('%Y%m%d_%H%M%S')
    candidate = f"{base}_{stamp}{ext}"
    i = 1
    while os.path.exists(candidate):
        candidate = f"{base}_{stamp}_{i}{ext}"
        i += 1
    return candidate


def _write_raster_to(path, arr, geo_tf, proj_wkt, dtype, nodata):
    """Écrit effectivement le raster GDAL vers `path`. Lève une exception si échec."""
    rows, cols = arr.shape
    ds = gdal.GetDriverByName("GTiff").Create(
        path, cols, rows, 1, dtype,
        ["COMPRESS=LZW", "TILED=YES"]
    )
    if ds is None:
        raise RuntimeError(f"GDAL n'a pas pu créer '{path}' (retour None).")
    ds.SetGeoTransform(geo_tf)
    if proj_wkt:
        ds.SetProjection(proj_wkt)
    if nodata is not None:
        ds.GetRasterBand(1).SetNoDataValue(nodata)
    ds.GetRasterBand(1).WriteArray(arr)
    ds.FlushCache()
    ds = None


def write_raster(path, arr, geo_tf, proj_wkt, dtype=gdal.GDT_Byte, nodata=None):
    """
    Écrit un raster. Si le fichier cible est verrouillé (ouvert dans QGIS /
    Explorateur / visionneuse), le script RENOMME AUTOMATIQUEMENT la sortie
    (suffixe horodaté) au lieu de planter, et retourne le chemin réellement écrit.
    """
    if os.path.dirname(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        _unload_layers_by_path(path)

        deleted = False
        for attempt in range(5):
            try:
                drv_existing = gdal.IdentifyDriver(path)
                if drv_existing is not None:
                    drv_existing.Delete(path)   # supprime aussi .aux.xml/.ovr etc.
                else:
                    os.remove(path)
                deleted = True
                break
            except Exception:
                time.sleep(0.3)  # laisse le temps à Windows de libérer le verrou
        if not deleted:
            try:
                os.remove(path)
            except Exception:
                pass

    # 1) Tentative sur le chemin cible.
    try:
        _write_raster_to(path, arr, geo_tf, proj_wkt, dtype, nodata)
        return path
    except Exception as exc:
        locked = isinstance(exc, PermissionError) or "Permission" in str(exc) or "ermission denied" in str(exc)
        if not locked:
            # Erreur non liée à un verrou : on la remonte telle quelle.
            raise

    # 2) Repli : renommage automatique horodaté.
    alt = _unique_renamed_path(path)
    try:
        _write_raster_to(alt, arr, geo_tf, proj_wkt, dtype, nodata)
        print(
            f"⚠️ '{os.path.basename(path)}' est verrouillé (ouvert dans QGIS / "
            f"Explorateur / visionneuse ?). Renommé automatiquement en : "
            f"{os.path.basename(alt)}"
        )
        return alt
    except Exception as exc2:
        raise RuntimeError(
            f"Impossible d'écrire le raster '{path}' ni le repli '{alt}'.\n"
            "Fermez le fichier (QGIS / Explorateur / visionneuse) puis relancez.\n"
            f"Détail : {exc2}"
        ) from exc2


def write_csv_rows(path, rows):
    """
    Écrit des lignes CSV de façon robuste :
      1) quelques tentatives sur le chemin cible (le verrou Windows peut sauter),
      2) sinon repli sur un nom horodaté à côté, pour ne JAMAIS perdre le run
         à la dernière étape si le fichier est ouvert dans Excel.
    Retourne le chemin réellement écrit.
    """
    if os.path.dirname(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def _attempt(target):
        with open(target, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerows(rows)

    last_err = None
    for _ in range(3):
        try:
            _attempt(path)
            return path
        except PermissionError as e:
            last_err = e
            time.sleep(0.4)

    alt = _unique_renamed_path(path)
    try:
        _attempt(alt)
        print(
            f"⚠️ '{os.path.basename(path)}' est verrouillé (ouvert dans Excel ?). "
            f"Résultat écrit dans : {os.path.basename(alt)}"
        )
        return alt
    except Exception as e2:
        raise RuntimeError(
            f"Impossible d'écrire le CSV '{path}' ni le repli '{alt}'.\n"
            "Fermez le fichier (Excel / autre logiciel) puis relancez le script.\n"
            f"Détail : {e2}"
        ) from (last_err or e2)


def save_lulc_layer(path, year, lulc, geo_tf, proj_wkt):
    # BUGFIX: retirer l'ancienne couche du projet AVANT d'écrire le nouveau
    # fichier, sinon addMapLayer ci-dessous finit par empiler plusieurs couches
    # portant le même nom/fichier au fil des exécutions.
    _unload_layers_by_path(path)
    actual_path = write_raster(path, lulc, geo_tf, proj_wkt, gdal.GDT_Byte, 0)
    layer = QgsRasterLayer(actual_path, f"LULC_{year}")
    if layer.isValid():
        items = [
            QgsColorRampShader.ColorRampItem(cid, col, CLASS_NAMES[cid])
            for cid, col in CLASS_COLORS.items()
        ]
        shader = QgsRasterShader()
        ramp = QgsColorRampShader()
        ramp.setColorRampType(QgsColorRampShader.Exact)
        ramp.setColorRampItemList(items)
        shader.setRasterShaderFunction(ramp)
        layer.setRenderer(
            QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
        )
        QgsProject.instance().addMapLayer(layer)
    return actual_path


def build_features(ds, rows, cols, names, arrays):
    """
    Construit toutes les variables en conservant les clés historiques
    ``apr_*`` / ``jul_*`` utilisées ailleurs dans le script.

    IMPORTANT : ``apr_*`` signifie désormais « première période disponible »
    et non littéralement avril. Cela corrige les stacks comme 2007 dont la
    première période est ``Mar_2007_*``.
    """
    first_period, summer_period, all_periods = _detect_temporal_periods(names)
    first = re.escape(first_period)
    summer = re.escape(summer_period)

    def P(period, *tokens):
        # Le premier motif exige le préfixe temporel + token; les variantes Bn
        # couvrent les stacks où le nom d'indice n'est pas présent.
        return [rf"{re.escape(period)}.*{t}" for t in tokens]

    progress_tick(0, 3, "première période : NDVI, MSAVI2, NDMI, MNDWI, DBSI, tasseled cap...")
    # --- Première période (historiquement appelée Apr dans le reste du code) ---
    apr_ndvi = find_band(names, arrays, P(first_period, r"NDVI") + [r"NDVI"], fallback=np.full((rows, cols), np.nan, dtype=np.float32))
    apr_msavi = find_band(names, arrays, P(first_period, r"MSAVI") + [r"MSAVI"], fallback=np.full((rows, cols), np.nan, dtype=np.float32))
    apr_savi = find_band(names, arrays, P(first_period, r"SAVI") + [r"SAVI"])
    apr_ndmi = find_band(names, arrays, P(first_period, r"NDMI") + [r"NDMI"])
    apr_nbr = find_band(names, arrays, P(first_period, r"NBR") + [r"NBR"])
    apr_ndwi = find_band(names, arrays, P(first_period, r"NDWI") + [r"NDWI"])
    apr_mndwi = find_band(names, arrays, P(first_period, r"MNDWI") + [r"MNDWI"])
    apr_ndbi = find_band(names, arrays, P(first_period, r"NDBI") + [r"NDBI"])
    apr_dbsi = find_band(names, arrays, P(first_period, r"DBSI", r"BSI") + [r"DBSI", r"BSI"])
    apr_tcb = find_band(names, arrays, P(first_period, r"TC_Brightness") + [r"TC_Brightness"])
    apr_tcg = find_band(names, arrays, P(first_period, r"TC_Greenness") + [r"TC_Greenness"])

    apr_nir = find_band(names, arrays, P(first_period, r"NIR", r"B4") , required=True, label=f"{first_period} NIR")
    apr_swir1 = find_band(names, arrays, P(first_period, r"SWIR1", r"B5"), required=True, label=f"{first_period} SWIR1")
    apr_swir2 = find_band(names, arrays, P(first_period, r"SWIR2", r"B7"), required=True, label=f"{first_period} SWIR2")
    apr_red = find_band(names, arrays, P(first_period, r"RED", r"B3"), required=True, label=f"{first_period} RED")
    apr_green = find_band(names, arrays, P(first_period, r"GREEN", r"B2"), required=True, label=f"{first_period} GREEN")
    apr_blue = find_band(names, arrays, P(first_period, r"BLUE", r"B1"), required=True, label=f"{first_period} BLUE")
    progress_tick(2, 3, "texture et variables dérivées")
    texture = find_band(names, arrays, P(first_period, r"Texture_Variance") + [r"Texture_Variance", r"Variance"])

    # Les indices NDVI/MSAVI peuvent être absents du stack : dans ce cas ils
    # sont dérivés à partir des bandes physiques déjà validées.
    if not np.any(np.isfinite(apr_ndvi)):
        apr_ndvi = (apr_nir - apr_red) / (apr_nir + apr_red + 1e-6)
    if not np.any(np.isfinite(apr_msavi)):
        L = 0.5
        apr_msavi = (2.0 * apr_nir + 1.0 - np.sqrt(np.maximum((2.0 * apr_nir + 1.0) ** 2 - 8.0 * (apr_nir - apr_red), 0.0))) / 2.0

    progress_tick(1, 3, "seconde période (été)")
    # --- Seconde période (historiquement appelée Jul dans le reste du code) ---
    jul_nir = find_band(names, arrays, P(summer_period, r"NIR", r"B4"), fallback=np.full((rows, cols), np.nan, dtype=np.float32))
    jul_red = find_band(names, arrays, P(summer_period, r"RED", r"B3"), fallback=np.full((rows, cols), np.nan, dtype=np.float32))
    jul_ndvi = find_band(names, arrays, P(summer_period, r"NDVI") + [r"NDVI.*Jul", r"NDVI.*Aug"], fallback=np.full((rows, cols), np.nan, dtype=np.float32))
    jul_msavi = find_band(names, arrays, P(summer_period, r"MSAVI") + [r"MSAVI.*Jul", r"MSAVI.*Aug"], fallback=np.full((rows, cols), np.nan, dtype=np.float32))
    jul_ndmi = find_band(names, arrays, P(summer_period, r"NDMI") + [r"NDMI.*Jul", r"NDMI.*Aug"])
    jul_ndwi = find_band(names, arrays, P(summer_period, r"NDWI") + [r"NDWI.*Jul", r"NDWI.*Aug"])
    jul_mndwi = find_band(names, arrays, P(summer_period, r"MNDWI") + [r"MNDWI.*Jul", r"MNDWI.*Aug"])
    jul_tcg = find_band(names, arrays, P(summer_period, r"TC_Greenness") + [r"TC_Greenness.*Jul", r"TC_Greenness.*Aug"])
    jul_dbsi = find_band(names, arrays, P(summer_period, r"DBSI", r"BSI") + [r"DBSI.*Jul", r"DBSI.*Aug", r"BSI.*Jul", r"BSI.*Aug"])
    if not np.any(np.isfinite(jul_ndvi)) and np.any(np.isfinite(jul_nir)) and np.any(np.isfinite(jul_red)):
        jul_ndvi = (jul_nir - jul_red) / (jul_nir + jul_red + 1e-6)
    if not np.any(np.isfinite(jul_msavi)) and np.any(np.isfinite(jul_nir)) and np.any(np.isfinite(jul_red)):
        jul_msavi = (2.0 * jul_nir + 1.0 - np.sqrt(np.maximum((2.0 * jul_nir + 1.0) ** 2 - 8.0 * (jul_nir - jul_red), 0.0))) / 2.0

    # Some RF feature configurations historically referenced jul_swir1.
    # Provide it when present, otherwise keep a safe zero array (optional).
    jul_swir1 = find_band(names, arrays, P(summer_period, r"SWIR1", r"B5"))

    delta = find_band(names, arrays, [r"Delta_NDVI", r"Delta.*NDVI"])
    amp = find_band(names, arrays, [r"Phenology_NDVI_Amplitude", r"NDVI.*Amplitude", r"Phenology.*Amplitude"])
    if not np.any(np.isfinite(amp)) or np.nanstd(amp) < 1e-8:
        if np.any(np.isfinite(jul_ndvi)):
            amp = np.abs(jul_ndvi - apr_ndvi)
        else:
            amp = np.zeros_like(apr_ndvi, dtype=np.float32)

    ratio = find_band(names, arrays, P(first_period, r"B5_div_B4") + [r"B5_div_B4", r"SWIR1.*NIR"])
    if not np.any(np.isfinite(ratio)) or np.nanstd(ratio) < 1e-8:
        ratio = apr_swir1 / (np.abs(apr_nir) + 1e-6)

    # Robust fallback for DBSI if the named index is missing.
    if not np.any(np.isfinite(apr_dbsi)) or np.nanstd(apr_dbsi) < 1e-8:
        den = apr_swir1 + apr_red + apr_nir + apr_blue + 1e-6
        apr_dbsi = ((apr_swir1 + apr_red) - (apr_nir + apr_blue)) / den

    apr_evi = find_band(names, arrays, P(first_period, r"EVI") + [r"EVI.*Apr", r"EVI.*Mar"])
    if not np.any(np.isfinite(apr_evi)) or np.nanstd(apr_evi) < 1e-8:
        evi_den = (apr_nir + 6.0 * apr_red - 7.5 * apr_blue + 1.0)
        evi_den = np.where(np.abs(evi_den) < 1e-6, 1e-6, evi_den)
        apr_evi = 2.5 * (apr_nir - apr_red) / evi_den

    apr_tir = find_band(names, arrays, P(first_period, r"TIR", r"Thermal", r"B6", r"B10"))

    # Diagnostic: jamais accepter un premier canal spectral entièrement nul.
    core = {
        "NIR": apr_nir, "RED": apr_red, "GREEN": apr_green,
        "BLUE": apr_blue, "SWIR1": apr_swir1, "SWIR2": apr_swir2,
        "NDVI": apr_ndvi, "MSAVI": apr_msavi
    }
    bad = [k for k, v in core.items() if not np.any(np.isfinite(v))]
    if bad:
        raise RuntimeError(
            f"Stack invalide: bandes principales sans données finies pour la période {first_period}: {bad}."
        )

    print(
        f"[Features] première période={first_period} -> clés apr_* | "
        f"seconde période={summer_period} -> clés jul_* | "
        f"NIR/RED/SWIR1 OK"
    )

    return {
        "apr_ndvi": apr_ndvi, "jul_ndvi": jul_ndvi,
        "apr_msavi": apr_msavi, "jul_msavi": jul_msavi,
        "apr_savi": apr_savi, "apr_ndmi": apr_ndmi, "jul_ndmi": jul_ndmi,
        "apr_nbr": apr_nbr, "apr_ndwi": apr_ndwi, "jul_ndwi": jul_ndwi, "apr_mndwi": apr_mndwi, "jul_mndwi": jul_mndwi,
        "apr_ndbi": apr_ndbi, "apr_dbsi": apr_dbsi, "jul_dbsi": jul_dbsi,
        "apr_tcb": apr_tcb, "apr_tcg": apr_tcg, "jul_tcg": jul_tcg,
        "apr_nir": apr_nir, "apr_swir1": apr_swir1, "apr_swir2": apr_swir2,
        "apr_red": apr_red, "apr_green": apr_green, "apr_blue": apr_blue,
        "jul_swir1": jul_swir1,
        "texture_variance": texture, "delta": delta, "amp": amp,
        "ratio_swir1_nir": ratio, "apr_evi": apr_evi, "apr_tir": apr_tir
    }


def enforce_forest_no_agriculture(lulc, forest_boundary_mask):
    """
    Compatibility function only.

    The former rule that forced Cropland/Fallow inside the forest polygon
    to Rangeland is disabled. The forest polygon is now used only as a
    spatial boundary for Forest (class 7, dense + open).
    """
    lulc = np.asarray(lulc).copy()
    forest_boundary_mask = np.asarray(forest_boundary_mask, dtype=bool)

    if forest_boundary_mask.shape != lulc.shape:
        raise RuntimeError(
            "Le masque de délimitation forestière n'a pas la même taille que le raster LULC."
        )

    # No forced reclassification.
    return lulc, 0


def calibrate_and_process_year(yr, y_info, shp_seb, admin_lyr, built_up_mask_path=None, all_prev_memories=None, output_dir=None, forest_cfg=None, auto_cfg=None, start_stage=1, stage_masks=None, mask_priority=False, temporal_cfg=None, anchor_cfg=None, review_implausible=False):
    """
    FINAL HIERARCHY (V16 — no forest boundary)

        0. STRICT ADMINISTRATIVE MASK
        1. STABLE SEBKHA MASK  <-- FIRST, NEVER RECLASSIFIED
        2. BUILT-UP
        3. WATER (outside Sebkha)
        4. FOREST (class 7)
        5. (removed: Matorral is merged into FOREST, class 7)
        6. CROPLAND (class 5)
        7. FALLOW (class 6; before Rangeland; optional temporal evidence)
        8. RANGELAND (class 8)
        9. BARELAND / ROCK (class 4) — now LAST
       10. FINAL RESIDUAL + nearest-neighbour filling (residual -> Bareland)
    """

    # Keep independent preview windows alive during the year calibration.
    method_preview_windows = []

    # Reset optional-index QA for this year. Missing optional indices are never
    # converted to zeros; they are reported explicitly to the user.
    _MISSING_BAND_WARNINGS.clear()

    _prep_plan = [(f"Lecture du Stack {yr}", 4), ("Calcul des indices spectraux", 3)]
    if temporal_cfg:
        _prep_plan.append(("Preuves supplémentaires (NDVI multi-années, pluies, MNT)", 6))
    _prep_plan += [("Carte de référence (année classée la plus proche)", 1), ("Zone d'étude et masques imposés", 1)]
    if anchor_cfg and int(yr) != int(anchor_cfg["year"]):
        _prep_plan.append(("Stabilité spectrale avec l'ancre", 5))
    progress_open(f"Année {yr} — préparation des données", _prep_plan)
    _pstep = {"n": -1}

    def _next_prep_step():
        _pstep["n"] += 1
        progress_step(_pstep["n"])

    _next_prep_step()
    ref_ds, rows, cols, geo_tf, proj_wkt, band_names, raw_arrays = read_stack_bands(y_info["stack"])
    _next_prep_step()
    features = build_features(ref_ds, rows, cols, band_names, raw_arrays)
    # Bandes brutes du stack (pour choisir une fausse couleur libre dans la fenêtre d'échantillonnage).
    stack_bands_view = raw_arrays if isinstance(raw_arrays, dict) else dict(zip(band_names, raw_arrays))
    if temporal_cfg:
        _next_prep_step()                                          # preuves supplémentaires (tics par bande NDVI)
        if temporal_cfg.get("years"):
            try:
                _tf = temporal_ndvi_features(temporal_cfg, yr, rows, cols, geo_tf, proj_wkt)
                features.update(_tf)
                print(f"[Preuve temporelle {yr}] variables : {', '.join(sorted(_tf))} | années : "
                      f"{', '.join(str(y) for y in sorted(int(k) for k in temporal_cfg['years'] if int(k) != int(yr)))}")
            except Exception as exc:
                print(f"[Preuve temporelle {yr}] IGNORÉE : {exc}")
        if temporal_cfg.get("dem_path"):
            try:
                _tr = terrain_features(temporal_cfg, rows, cols, geo_tf, proj_wkt)
                features.update(_tr)
                print(f"[MNT {yr}] variables : {', '.join(sorted(_tr))}")
            except Exception as exc:
                print(f"[MNT {yr}] IGNORÉ : {exc}")

    # ---------- COMPARAISON AVEC L'ANNÉE PRÉCÉDENTE (à partir de la 2e année) ----------
    _next_prep_step()
    prev_year, prev_map, _prev_src = get_previous_map(output_dir, yr, TARGET_YEARS, rows, cols, geo_tf, proj_wkt)
    change_ctx = ({"prev": prev_map, "prev_year": prev_year, "yr": yr, "reverse": int(prev_year) > int(yr)} if prev_map is not None else None)
    if prev_map is not None:
        print(f"[Changement] comparaison avec {prev_year} (source : {_prev_src} ; référence = année déjà classée "
              + ("SUIVANTE, PLUS RÉCENTE : analyse orientée dans le temps" if change_ctx["reverse"] else "PRÉCÉDENTE") + f" ; ordre de traitement {process_order_name()}) : tableau, carte et « 🎯 Max Accord » dans chaque fenêtre.")
    else:
        print("[Changement] première année traitée (aucune autre année déjà classée en mémoire ni dans le dossier de résultats) : pas de comparaison.")

    if _MISSING_BAND_WARNINGS:
        _uniq_missing = list(dict.fromkeys(_MISSING_BAND_WARNINGS))
        _msg = (
            f"Année {yr} — certains indices optionnels sont absents du stack.\n\n"
            + "\n".join(f"• {x}" for x in _uniq_missing)
            + "\n\nIls restent NaN et ne sont JAMAIS remplacés silencieusement par 0."
        )
        print("[INDEX QA] " + _msg.replace("\n", " | "))
        QMessageBox.warning(None, "INDEX QA — indices manquants", _msg)

    # ---------- 0. STRICT ADMIN MASK ----------
    _next_prep_step()
    admin_mask = np.ones((rows, cols), dtype=bool)
    if admin_lyr and admin_lyr.isValid():
        admin_path = admin_lyr.source().split("|")[0]
        m = make_vector_mask(admin_path, rows, cols, geo_tf, proj_wkt)
        if np.any(m):
            admin_mask = m

    valid = admin_mask & np.isfinite(features["apr_ndvi"]) & np.isfinite(features["apr_msavi"])
    lulc = np.zeros((rows, cols), dtype=np.uint8)

    # ---------- MASQUES IMPOSÉS PAR ÉTAPE (optionnels ; vides = comportement inchangé) ----------
    forced = _load_forced_masks(stage_masks, rows, cols, geo_tf, proj_wkt, admin_mask, yr)
    forced_all = np.zeros((rows, cols), dtype=bool)
    for _fm in forced.values():
        forced_all |= _fm
    forced_log = []   # (code de classe, pixels imposés, pixels ignorés car déjà classés par une étape antérieure)

    # ---------- 1. SEBKHA : la fenêtre s'ouvre plus bas (après la définition des outils de calibration) ----------
    # Le masque Sebkha n'est PLUS exigé à l'avance : s'il a été trouvé par son nom il est proposé par défaut dans la fenêtre de l'étape 1,
    # sinon vous choisissez (shapefile, raster, classes d'un autre raster) ou classez par seuils dans cette fenêtre.
    if shp_seb and not os.path.exists(shp_seb):
        shp_seb = None

    # ---------- RF UTILITIES ----------
    def rasterize_labels(shp_path, field):
        ds = ogr.Open(shp_path)
        if not ds:
            raise RuntimeError(f"Impossible d'ouvrir: {shp_path}")
        lyr = ds.GetLayer()
        if lyr.FindFieldIndex(field, True) == -1:
            field = "class"
        mem = gdal.GetDriverByName("MEM").Create("", cols, rows, 1, gdal.GDT_Int32)
        mem.SetGeoTransform(geo_tf)
        if proj_wkt:
            mem.SetProjection(proj_wkt)
        gdal.RasterizeLayer(mem, [1], lyr, options=[f"ATTRIBUTE={field}"])
        return normalize_class_array(mem.GetRasterBand(1).ReadAsArray())      # anciens polygones « Matorral » (code 9) : fusionnés dans Forest (7)

    def spatial_polygon_split(shp_path, field, active_mask, target, needed_classes=None):
        """
        Polygon-level validation when >=2 polygons/class are available.
        Entire polygons are kept together, avoiding pixel leakage.

        BUGFIX: this used to derive `needed` from `target` (the BINARY 0/1/-1 array
        built from STAGE_POSITIVE/STAGE_NEGATIVE), then check `by_class.get(c)` for
        c in {0, 1} — but `by_class` is keyed by the RAW multi-class shapefile codes
        (1..8), where the code "0" essentially never exists. As a result this
        polygon-count check almost always failed, `spatial_ok` was almost always
        False, and the whole polygon-level (leakage-safe) validation silently never
        ran: every stage silently fell back to the random pixel-level split instead,
        defeating the tool's main anti-leakage safeguard.
        Fix: pass the actual raw class codes relevant to this stage
        (STAGE_POSITIVE[stage] | STAGE_NEGATIVE[stage]) via `needed_classes`.
        """
        ds = ogr.Open(shp_path)
        if not ds:
            return None, None, False
        lyr = ds.GetLayer()
        if lyr.FindFieldIndex(field, True) == -1:
            field = "class"

        by_class = {}
        for ft in lyr:
            geom = ft.GetGeometryRef()
            if geom is None:
                continue
            try:
                cid = normalize_class_code(ft.GetField(field))          # 9 (ancien Matorral) -> 7 AVANT toute séparation entraînement / validation
            except Exception:
                continue
            if cid > 0:
                by_class.setdefault(cid, []).append(geom.Clone())

        # Need at least two polygons for every relevant RAW class code.
        if needed_classes is not None:
            needed = set(int(c) for c in needed_classes)
        else:
            needed = set(np.unique(target[active_mask]).tolist())
            needed.discard(-1)
        if any(len(by_class.get(c, [])) < 2 for c in needed):
            return None, None, False

        rng = np.random.RandomState(RF_RANDOM_STATE)
        memdrv = gdal.GetDriverByName("MEM")
        train = memdrv.Create("", cols, rows, 1, gdal.GDT_Byte)
        val = memdrv.Create("", cols, rows, 1, gdal.GDT_Byte)
        train.SetGeoTransform(geo_tf); val.SetGeoTransform(geo_tf)
        if proj_wkt:
            train.SetProjection(proj_wkt); val.SetProjection(proj_wkt)

        ogrdrv = ogr.GetDriverByName("Memory")
        dtr = ogrdrv.CreateDataSource("train")
        dva = ogrdrv.CreateDataSource("val")
        srs = osr.SpatialReference()
        if proj_wkt:
            srs.ImportFromWkt(proj_wkt)
        else:
            srs.ImportFromEPSG(32632)

        ltr = dtr.CreateLayer("train", srs, ogr.wkbPolygon)
        lva = dva.CreateLayer("val", srs, ogr.wkbPolygon)
        ltr.CreateField(ogr.FieldDefn(field, ogr.OFTInteger))
        lva.CreateField(ogr.FieldDefn(field, ogr.OFTInteger))

        for cid, geoms in by_class.items():
            if cid not in needed:
                continue
            idx = np.arange(len(geoms))
            rng.shuffle(idx)
            n_val = max(1, int(round(len(idx) * VALIDATION_FRACTION)))
            val_idx = set(idx[:n_val].tolist())
            for i, geom in enumerate(geoms):
                out_lyr = lva if i in val_idx else ltr
                ft = ogr.Feature(out_lyr.GetLayerDefn())
                ft.SetGeometry(geom)
                ft.SetField(field, int(cid))
                out_lyr.CreateFeature(ft)

        gdal.RasterizeLayer(train, [1], ltr, burn_values=[1])
        gdal.RasterizeLayer(val, [1], lva, burn_values=[1])

        return (
            train.GetRasterBand(1).ReadAsArray().astype(bool) & active_mask,
            val.GetRasterBand(1).ReadAsArray().astype(bool) & active_mask,
            True
        )

    def run_rf(shp_path, field, active_mask, stage_num):
        if not SKLEARN_AVAILABLE:
            raise RuntimeError("Scikit-learn n'est pas disponible.")

        use_anchor = (not str(shp_path or "").strip()) and bool(ANCHOR_CTX.get("active"))
        if not use_anchor and not str(shp_path or "").strip():
            raise RuntimeError("Aucun shapefile d'échantillons RF et aucune ancre active : fournissez des échantillons ou activez l'ancre au démarrage.")
        labels = anchor_rf_labels(ANCHOR_CTX) if use_anchor else rasterize_labels(shp_path, field)
        pos = STAGE_POSITIVE[stage_num]
        neg = STAGE_NEGATIVE[stage_num]

        y = np.full(labels.shape, -1, dtype=np.int8)
        y[np.isin(labels, list(pos))] = 1
        y[np.isin(labels, list(neg))] = 0

        feature_names = [n for n in STAGE_FEATURES[stage_num] if n in features]
        if len(feature_names) < 2:
            raise RuntimeError(f"Feature set insuffisant pour Stage {stage_num}.")

        X = np.stack([features[n] for n in feature_names], axis=-1)
        finite = np.all(np.isfinite(X), axis=-1)
        candidates = finite & (y >= 0) & (active_mask | (labels > 0))

        n_pos = int(np.count_nonzero(candidates & (y == 1)))
        n_neg = int(np.count_nonzero(candidates & (y == 0)))
        if n_pos < 10 or n_neg < 10:
            raise RuntimeError(
                f"Stage {stage_num}: échantillons insuffisants "
                f"(positive={n_pos}, negative={n_neg})."
            )

        if use_anchor:
            train_mask, val_mask = anchor_block_split(candidates, y=y)          # blocs spatiaux : pas de fuite entre pixels voisins
            spatial_ok = True
        else:
            train_mask, val_mask, spatial_ok = spatial_polygon_split(
                shp_path, field, candidates, labels, needed_classes=(pos | neg)
            )

        if spatial_ok:
            train_mask &= finite & (y >= 0)
            val_mask &= finite & (y >= 0)
        else:
            # Explicit fallback only when polygon count is insufficient.
            idx = np.flatnonzero(candidates)
            rng = np.random.RandomState(RF_RANDOM_STATE)
            rng.shuffle(idx)
            cut = max(1, int(len(idx) * (1 - VALIDATION_FRACTION)))
            train_mask = np.zeros_like(candidates, dtype=bool)
            val_mask = np.zeros_like(candidates, dtype=bool)
            train_mask.flat[idx[:cut]] = True
            val_mask.flat[idx[cut:]] = True

        if use_anchor and int(train_mask.sum()) > 300000:                    # les pixels stables sont très nombreux : sous-échantillon d'entraînement
            _idx = np.flatnonzero(train_mask.ravel())
            _keep = np.random.RandomState(RF_RANDOM_STATE).choice(_idx, 300000, replace=False)
            train_mask = np.zeros_like(train_mask)
            train_mask.ravel()[_keep] = True
        Xtr = X[train_mask]
        ytr = y[train_mask]
        Xva = X[val_mask]
        yva = y[val_mask]

        if len(np.unique(ytr)) < 2:
            raise RuntimeError(f"Stage {stage_num}: train ne contient pas les deux classes.")

        rf = RandomForestClassifier(
            n_estimators=RF_N_ESTIMATORS,
            max_depth=RF_MAX_DEPTH,
            min_samples_leaf=RF_MIN_SAMPLES_LEAF,
            class_weight="balanced",
            random_state=RF_RANDOM_STATE,
            n_jobs=RF_N_JOBS,
            oob_score=True
        )
        rf.fit(Xtr, ytr)

        # ----- independent validation report -----
        if len(Xva) > 0:
            pred = rf.predict(Xva)
            cm = confusion_matrix(yva, pred, labels=[0, 1])
            acc = accuracy_score(yva, pred)
            kap = cohen_kappa_score(yva, pred) if len(np.unique(yva)) > 1 else np.nan
            f1 = f1_score(yva, pred, average="binary", zero_division=0)

            vdir = os.path.join(output_dir, "Validation")
            os.makedirs(vdir, exist_ok=True)

            with open(
                os.path.join(vdir, f"Validation_{yr}_Stage{stage_num}.txt"),
                "w", encoding="utf-8"
            ) as f:
                f.write(f"Year={yr}\nStage={stage_num}\nSpatialPolygonSplit={spatial_ok}\n")
                f.write("TrainingSource=" + (f"ANCHOR {ANCHOR_CTX.get('anchor_year')} (pixels spectralement stables, séparation par blocs)" if use_anchor else str(shp_path)) + "\n")
                f.write(f"Features={feature_names}\n")
                f.write(f"TrainPixels={len(Xtr)}\nValidationPixels={len(Xva)}\n")
                f.write(f"Accuracy={acc:.6f}\nKappa={kap:.6f}\nF1={f1:.6f}\n")
                f.write(f"OOB={getattr(rf, 'oob_score_', np.nan):.6f}\n")
                f.write("Confusion matrix [rows=true, cols=pred], labels=[0,1]\n")
                f.write(np.array2string(cm))
                f.write("\n\n")
                f.write(classification_report(
                    yva, pred, labels=[0, 1],
                    target_names=["Negative", "Positive"],
                    zero_division=0
                ))

            with open(
                os.path.join(vdir, f"FeatureImportance_{yr}_Stage{stage_num}.csv"),
                "w", newline="", encoding="utf-8-sig"
            ) as f:
                w = csv.writer(f)
                w.writerow(["Feature", "GiniImportance"])
                for n, v in sorted(
                    zip(feature_names, rf.feature_importances_),
                    key=lambda z: z[1], reverse=True
                ):
                    w.writerow([n, f"{v:.8f}"])

            if len(Xva) >= 20:
                try:
                    perm = permutation_importance(
                        rf, Xva, yva,
                        n_repeats=10,
                        random_state=RF_RANDOM_STATE,
                        n_jobs=RF_N_JOBS,
                        scoring="f1"
                    )
                    with open(
                        os.path.join(vdir, f"PermutationImportance_{yr}_Stage{stage_num}.csv"),
                        "w", newline="", encoding="utf-8-sig"
                    ) as f:
                        w = csv.writer(f)
                        w.writerow(["Feature", "MeanDecreaseF1", "Std"])
                        for i in np.argsort(perm.importances_mean)[::-1]:
                            w.writerow([
                                feature_names[i],
                                f"{perm.importances_mean[i]:.8f}",
                                f"{perm.importances_std[i]:.8f}"
                            ])
                except Exception as exc:
                    with open(
                        os.path.join(vdir, f"PermutationImportance_{yr}_Stage{stage_num}_ERROR.txt"),
                        "w", encoding="utf-8"
                    ) as f:
                        f.write(str(exc))

        # ----- prediction + confidence -----
        pred_bin = np.zeros((rows, cols), dtype=np.uint8)
        confidence = np.zeros((rows, cols), dtype=np.float32)
        active_pred = active_mask & finite

        if np.any(active_pred):
            xp = X[active_pred]
            pb = rf.predict(xp)
            pp = rf.predict_proba(xp)
            pred_bin[active_pred] = pb.astype(np.uint8)
            confidence[active_pred] = np.max(pp, axis=1).astype(np.float32)

        conf_path = os.path.join(output_dir, f"RF_Confidence_{yr}_Stage{stage_num}.tif")
        write_raster(conf_path, confidence, geo_tf, proj_wkt, gdal.GDT_Float32, 0)

        return (pred_bin == 1), confidence

    # Couleurs de la carte d'accord QA (RF vs seuils).
    QA_AGREEMENT_COLORS = {
        1: QColor(46, 125, 50),    # accord POSITIF (les deux) — vert
        2: QColor(190, 190, 190),  # accord NÉGATIF (les deux) — gris
        3: QColor(30, 136, 229),   # RF positif seul — bleu
        4: QColor(255, 167, 38),   # seuils positifs seuls — orange
        5: QColor(211, 47, 47),    # désaccord ambigu (confiance médiane) — rouge
    }

    def compute_stage_mask(mode, th, base, threshold_func, rf_cfg, stage_num, write_qa=False):
        """
        Résout le masque positif d'une étape selon le mode :
          - 'thresholds' : règles de seuils transparentes,
          - 'rf'         : Random Forest seul,
          - 'hybrid'     : RF à confiance pilotée par les seuils.
        Retourne (masque_bool, stats_ou_None).
        """
        mode = mode or ("rf" if rf_cfg.get("enabled") else "thresholds")
        hi = float(rf_cfg.get("hi", 0.80))
        lo = float(rf_cfg.get("lo", 0.50))
        if lo > hi:
            lo, hi = hi, lo

        if mode == "thresholds":
            return threshold_func(th, base), None

        rf_mask, rf_conf = run_rf(rf_cfg["shp"], rf_cfg["field"], base, stage_num)
        rf_mask = rf_mask & base

        if mode == "rf":
            return rf_mask, None

        # ----- HYBRIDE -----
        th_mask = threshold_func(th, base) & base
        # RF peu sûr (conf <= lo) -> on suit les seuils ; sinon on suit RF.
        final = np.where(rf_conf <= lo, th_mask, rf_mask) & base

        stats = None
        if write_qa:
            agree_pos = base & rf_mask & th_mask
            agree_neg = base & (~rf_mask) & (~th_mask)
            rf_only = base & rf_mask & (~th_mask)
            th_only = base & th_mask & (~rf_mask)
            uncertain = base & (rf_conf > lo) & (rf_conf < hi) & (rf_mask != th_mask)

            qa = np.zeros(base.shape, dtype=np.uint8)
            qa[agree_pos] = 1
            qa[agree_neg] = 2
            qa[rf_only] = 3
            qa[th_only] = 4
            qa[uncertain] = 5

            qa_path = os.path.join(output_dir, f"QA_Agreement_{yr}_Stage{stage_num}.tif")
            qa_path = write_raster(qa_path, qa, geo_tf, proj_wkt, gdal.GDT_Byte, 0)
            add_colored_raster_layer(
                qa_path, f"QA_Stage{stage_num}_{yr}", QA_AGREEMENT_COLORS
            )
            stats = {
                "agree_pos": int(np.count_nonzero(agree_pos)),
                "agree_neg": int(np.count_nonzero(agree_neg)),
                "rf_only": int(np.count_nonzero(rf_only)),
                "th_only": int(np.count_nonzero(th_only)),
                "uncertain": int(np.count_nonzero(uncertain)),
            }
        return final, stats

    def stage_report_html(title, base_mask, classified_mask, extra_lines=None, tail_lines=None):
        """
        Rapport HTML coloré affiché après chaque calcul d'aperçu :
          - surface classée à CETTE étape
          - surface non classée restante DANS le masque de cette étape (base_mask)
          - surface totale non classée AVANT cette étape (globale, sur tout le domaine valide)
          - surface totale non classée APRÈS cette étape (globale, estimation si validé)
        """
        n_base = int(np.count_nonzero(base_mask))
        n_cls = int(np.count_nonzero(classified_mask))
        n_left_stage = max(0, n_base - n_cls)
        n_global_before = int(np.count_nonzero(valid & (lulc == 0)))
        n_global_after = max(0, n_global_before - n_cls)

        lines = [f"<b>{title}</b><br>"]
        lines.append(
            "<span style='color:#2e7d32;font-weight:bold'>✅ Classée (cette étape)</span> : "
            f"{n_cls:,} px — {n_cls * pixel_area_ha:,.2f} ha<br>"
        )
        if tail_lines:
            lines.extend(tail_lines)          # entonnoir des seuils (juste sous la surface classée)
        if extra_lines:
            lines.extend(extra_lines)
        lines.append(
            "<span style='color:#c62828;font-weight:bold'>◻ Non classée restante (masque de l'étape)</span> : "
            f"{n_left_stage:,} px — {n_left_stage * pixel_area_ha:,.2f} ha<br>"
        )
        lines.append(
            "<span style='color:#ef6c00;font-weight:bold'>⏳ Non classée AVANT cette étape (globale)</span> : "
            f"{n_global_before:,} px — {n_global_before * pixel_area_ha:,.2f} ha<br>"
        )
        lines.append(
            "<span style='color:#1565c0;font-weight:bold'>🔵 Non classée APRÈS cette étape (globale, estimée)</span> : "
            f"{n_global_after:,} px — {n_global_after * pixel_area_ha:,.2f} ha"
        )
        return "".join(lines)

    stage_mask_log = {}          # étape -> masque effectivement utilisé (provenance, écrit dans les métadonnées)
    stage_review_log = {}        # étape -> correction des transitions improbables (fenêtre dédiée), écrit dans les métadonnées et le rapport

    def stage_dialog(stage_num, title, active_mask, positive_class, threshold_func=None, default_mask=None, default_thresholds=None):
        """
        Ouvre la fenêtre de calibration de l'étape (mode Seuils / RF / Hybride).
        En mode batch (auto_cfg fourni), aucune fenêtre : le preset est rejoué.
        """
        dialog_holder = {"dlg": None}
        # ---------- BATCH : pas d'interface ----------
        if auto_cfg is not None:
            preset = (auto_cfg.get("stages", {}) or {}).get(stage_num, {}) or {}
            # Étape sans preset (1-3) : masque et seuils PAR DÉFAUT ; preset sans seuils : seuils par défaut.
            th = (preset.get("thresholds") if "thresholds" in preset else (default_thresholds or {})) or {}
            rf_cfg = preset.get("rf", {"enabled": False}) or {"enabled": False}
            mode = preset.get("mode", "thresholds")
            rf_cfg = dict(rf_cfg)
            rf_cfg.setdefault("hi", preset.get("hi", 0.80))
            rf_cfg.setdefault("lo", preset.get("lo", 0.50))
            rf_cfg["mode"] = mode
            base = active_mask
            if mode in ("rf", "hybrid") and not rf_cfg.get("shp") and not ANCHOR_CTX.get("active"):
                print(f"    [Batch] Étape {stage_num} : pas de shapefile RF dans le "
                      f"preset → repli sur les seuils.")
                mode = "thresholds"
            _mspec = (preset.get("mask") if preset else default_mask) or {}
            stage_mask_log[stage_num] = _mspec if mask_spec_active(_mspec) else None
            c, _qa, _base, _minfo = apply_stage_mask(
                _mspec, active_mask, rows, cols, geo_tf, proj_wkt,
                lambda b_: compute_stage_mask(mode, th, b_, threshold_func, rf_cfg, stage_num, write_qa=False), stage_class=positive_class)
            if mask_info_active(_minfo):
                print("    [Batch] " + describe_stage_mask(_minfo, mask_stage_px_ha(geo_tf)))
            return "NEXT", c

        # ---------- INTERACTIF ----------
        progress_hide()                                            # la fenêtre d'attente ne doit pas gêner la calibration
        def preview(th, shp_path, rf_cfg):
            # shp_path = spécification du masque de l'étape (dict) ; une chaîne reste acceptée (ancien polygone).
            RULE_TRACE.clear()
            c, _qa, base, _minfo = apply_stage_mask(
                shp_path, active_mask, rows, cols, geo_tf, proj_wkt,
                lambda b_: compute_stage_mask(rf_cfg.get("mode"), th, b_, threshold_func,
                                              rf_cfg, stage_num, write_qa=False), stage_class=positive_class)

            preview_arr = lulc.copy()
            preview_arr[c] = positive_class
            if _minfo.get("source", "none") != "none" and _minfo.get("role") == "boundary":
                # LIMITE : l'emprise du masque (domaine d'étude de l'étape) reste visible là où rien n'est encore classé.
                preview_arr[(preview_arr == 0) & base] = 254

            # Update the direct on-image mask so the user can see exactly which
            # areas are already classified before drawing RF samples.
            if dialog_holder.get("dlg") is not None:
                try:
                    dialog_holder["dlg"].update_stage_mask_overlay(preview_arr)
                except Exception as _exc:
                    print(f"[Masque coloré] mise à jour impossible : {_exc}")

            p = os.path.join(
                temp_dir(output_dir),
                f"Preview_{yr}_Stage{stage_num}_{int(time.time()*1000)}.tif"
            )
            write_raster(p, preview_arr, geo_tf, proj_wkt, gdal.GDT_Byte, 0)

            _extra = [describe_stage_mask(_minfo, pixel_area_ha) + "<br>"] if mask_info_active(_minfo) else None
            _tail = funnel_lines(int(np.count_nonzero(base)), list(RULE_TRACE), int(np.count_nonzero(c)), pixel_area_ha) if rf_cfg.get("mode") == "thresholds" else []
            if ANCHOR_CTX.get("active"):
                _tail = list(_tail) + anchor_summary_lines(ANCHOR_CTX, positive_class)
            if change_ctx is not None:
                try:
                    _cur_state = lulc.copy()
                    _cur_state[c] = positive_class
                    _an = analyze_change(change_ctx["prev"], _cur_state, pixel_area_ha, domain=admin_mask, prev_year=change_ctx["prev_year"],
                                         reverse=change_ctx["reverse"], cur_year=yr)
                    _tail = list(_tail) + change_summary_html(_an, positive_class, yr)
                    if dialog_holder.get("dlg") is not None:
                        dialog_holder["dlg"].set_change_analysis(_an, _cur_state, positive_class, from_preview=True)
                except Exception as _exc:
                    print(f"[Changement] analyse de l'aperçu impossible : {_exc}")
            return stage_report_html(title, base, c, extra_lines=_extra, tail_lines=_tail)

        def compare_methods(th, shp_path, rf_cfg):
            base = stage_domain_from_spec(shp_path, active_mask, rows, cols, geo_tf, proj_wkt, positive_class)
            th_mask = threshold_func(th, base) & base
            rf_shp = rf_cfg.get("shp", "").strip()
            if not rf_shp or not os.path.exists(rf_shp):
                raise RuntimeError(
                    "Sélectionnez un Shapefile d'échantillons RF valide avant la comparaison."
                )

            # Check the stage-specific RF labels before training so the user gets
            # a useful diagnostic instead of a generic traceback.
            rf_field = rf_cfg.get("field", "class")
            labels_cmp = rasterize_labels(rf_shp, rf_field)
            pos_cmp = STAGE_POSITIVE[stage_num]
            neg_cmp = STAGE_NEGATIVE[stage_num]
            finite_cmp = np.ones_like(base, dtype=bool)
            for _fn in STAGE_FEATURES[stage_num]:
                if _fn in features:
                    finite_cmp &= np.isfinite(features[_fn])
            sample_domain_cmp = finite_cmp & (labels_cmp > 0)
            n_pos_cmp = int(np.count_nonzero(sample_domain_cmp & np.isin(labels_cmp, list(pos_cmp))))
            n_neg_cmp = int(np.count_nonzero(sample_domain_cmp & np.isin(labels_cmp, list(neg_cmp))))
            if n_pos_cmp < 10 or n_neg_cmp < 10:
                raise RuntimeError(
                    f"Étape {stage_num} — échantillons RF insuffisants pour la comparaison.\n"
                    f"Positifs attendus : {sorted(pos_cmp)} → {n_pos_cmp} pixels "
                    f"(minimum 10).\n"
                    f"Négatifs attendus : {sorted(neg_cmp)} → {n_neg_cmp} pixels "
                    f"(minimum 10).\n\n"
                    "Utilisez « Table attributaire » pour corriger Class ID, "
                    "supprimer les mauvais polygones ou ajouter des échantillons."
                )

            rf_mask, _ = run_rf(rf_shp, rf_field, base, stage_num)

            # Two independent map windows: one for thresholds, one for RF.
            th_arr = lulc.copy()
            rf_arr = lulc.copy()
            th_arr[th_mask] = positive_class
            rf_arr[rf_mask] = positive_class
            stats_th = stage_report_html(
                f"{title} — Seuils", base, th_mask
            )
            stats_rf = stage_report_html(
                f"{title} — Random Forest", base, rf_mask
            )
            th_win = ClassificationPreviewDialog(
                f"{title} — SEUILS",
                th_arr, geo_tf, proj_wkt, positive_class,
                output_dir, pixel_area_ha, stats_th
            )
            rf_win = ClassificationPreviewDialog(
                f"{title} — RANDOM FOREST",
                rf_arr, geo_tf, proj_wkt, positive_class,
                output_dir, pixel_area_ha, stats_rf
            )
            cmp = MethodComparisonDialog(
                f"Comparaison — {title}",
                th_mask, rf_mask, base, geo_tf, pixel_area_ha
            )
            _show_method_comparison_windows(th_win, rf_win, cmp, method_preview_windows)
            return (
                "<b>Comparaison exécutée.</b><br>"
                "Deux fenêtres indépendantes ont été ouvertes (Seuils / RF) "
                "ainsi qu'une fenêtre de concordance/désaccord."
            )

        def mask_footprint(spec):
            """Bouton « Afficher l'emprise du masque » : dessine le masque sur la carte (magenta ; couleur de classe si rôle TOTAL) et donne sa surface."""
            m = mask_from_spec(spec, rows, cols, geo_tf, proj_wkt, positive_class)
            if m is None:
                return "<b>Aucun masque sélectionné.</b>"
            role = (spec.get("role") if isinstance(spec, dict) else None) or "boundary"
            free = m & active_mask
            info = {"source": spec.get("source") if isinstance(spec, dict) else "vector", "role": role,
                    "mask_pixels": int(np.count_nonzero(m)), "in_domain": int(np.count_nonzero(free))}
            arr_ = lulc.copy()
            arr_[free & (arr_ == 0)] = positive_class if role == "total" else 254
            if dialog_holder.get("dlg") is not None:
                try:
                    dialog_holder["dlg"].update_stage_mask_overlay(arr_)
                except Exception as _exc:
                    print(f"[Masque coloré] mise à jour impossible : {_exc}")
            return f"<b>{title}</b><br>" + describe_stage_mask(info, pixel_area_ha)

        _cctx = dict(change_ctx, px_ha=pixel_area_ha, domain=admin_mask) if change_ctx is not None else None

        def optimize_for_previous(cur_th, specs, mask_spec):
            """« 🎯 Max Accord » : seuils qui reproduisent au mieux la classe de l'année précédente (centiles des pixels de référence)."""
            dom_ = stage_domain_from_spec(mask_spec, active_mask, rows, cols, geo_tf, proj_wkt, positive_class)
            return optimize_agreement(threshold_func, features, dom_, (change_ctx["prev"] == positive_class) & dom_, cur_th, specs)

        def optimize_for_anchor(cur_th, specs, mask_spec):
            """« 🎯 Optimiser (stables de l'ancre) » : seuils appris UNIQUEMENT sur les pixels spectralement STABLES (classe connue et fiable) ; positifs = classe de l'ancre,
            négatifs = pixels stables d'autres classes."""
            sp = mask_spec if isinstance(mask_spec, dict) else {}
            base_ = active_mask if sp.get("source") == "anchor" else stage_domain_from_spec(mask_spec, active_mask, rows, cols, geo_tf, proj_wkt, positive_class)
            ev_ = base_ & anchor_stable(ANCHOR_CTX)
            return optimize_agreement(threshold_func, features, ev_, (ANCHOR_CTX["anchor_map"] == positive_class) & ev_, cur_th, specs)

        dlg = StageCalibrationDialog(
            f"Année {yr} – {title}",
            stage_num,
            preview,
            available_bands_dict={
                "swir1": features["apr_swir1"],
                "swir2": features["apr_swir2"],
                "nir": features["apr_nir"],
                "red": features["apr_red"],
                "green": features["apr_green"],
                "blue": features["apr_blue"]
            },
            geo_tf=geo_tf,
            proj_wkt=proj_wkt,
            spectral_arrays=features,
            stack_bands=stack_bands_view,
            all_prev_memories=all_prev_memories,
            can_go_back=(stage_num > 1),
            shp_selector_info={
                "box_title": "Échantillons RF / masque optionnel",
                "label": "Polygone :",
                "default": ""
            },
            year=yr,
            output_dir=output_dir,
            comparison_callback=compare_methods,
            initial_lulc=lulc.copy(),
            active_mask=active_mask.copy(),
            mask_callback=mask_footprint,
            change_ctx=_cctx,
            optimize_callback=(optimize_for_previous if (change_ctx is not None and threshold_func is not None) else None),
            anchor_optimize_callback=(optimize_for_anchor if (ANCHOR_CTX.get("active") and threshold_func is not None) else None)
        )

        dialog_holder["dlg"] = dlg
        if default_mask:
            dlg.set_mask_spec(default_mask)       # masque par défaut (ex. Sebkha_Finale, Built_up_<année>) : modifiable dans la fenêtre
        # Ensure the cumulative mask is visible immediately, before the first Preview.
        try:
            dlg.update_stage_mask_overlay(lulc.copy())
        except Exception:
            pass

        show_dialog(dlg)
        try:                                                       # fond de carte réutilisé par la fenêtre des transitions improbables
            _bg = dlg.current_layer.source() if getattr(dlg, "current_layer", None) is not None else ""
            STAGE_BACKGROUND["path"] = _bg.split("|")[0] if _bg else ""
        except Exception:
            STAGE_BACKGROUND["path"] = ""

        if dlg.action == "CANCEL":
            raise RuntimeError("Opération annulée.")
        if dlg.action == "BACK":
            return "BACK", None

        th = dlg.get_values()
        rf_cfg = dlg.get_rf_config()

        RULE_TRACE.clear()
        c, qa_stats, base, _minfo = apply_stage_mask(
            dlg.get_mask_spec(), active_mask, rows, cols, geo_tf, proj_wkt,
            lambda b_: compute_stage_mask(
                rf_cfg.get("mode"), th, b_, threshold_func, rf_cfg, stage_num,
                write_qa=(rf_cfg.get("mode") == "hybrid")
            ),
            stage_class=positive_class
        )
        for _fl in funnel_lines(int(np.count_nonzero(base)), list(RULE_TRACE), int(np.count_nonzero(c)), pixel_area_ha):
            print("    " + re.sub(r"<[^>]+>", "", _fl.replace("<br>", " ")).strip())
        _spec_used = dlg.get_mask_spec()
        stage_mask_log[stage_num] = _spec_used if mask_spec_active(_spec_used) else None
        if mask_info_active(_minfo):
            print("    " + describe_stage_mask(_minfo, pixel_area_ha))
        if qa_stats:
            print(f"    [QA étape {stage_num}] accord+ {qa_stats['agree_pos']:,} | "
                  f"accord- {qa_stats['agree_neg']:,} | RF seul {qa_stats['rf_only']:,} | "
                  f"seuils seuls {qa_stats['th_only']:,} | ambigu {qa_stats['uncertain']:,}")

        return "NEXT", c

    # Pixel area from GeoTransform; fallback only if needed.
    try:
        pixel_area_ha = abs(
            geo_tf[1] * geo_tf[5] - geo_tf[2] * geo_tf[4]
        ) / 10000.0
        if not np.isfinite(pixel_area_ha) or pixel_area_ha <= 0:
            pixel_area_ha = PIXEL_HA
    except Exception:
        pixel_area_ha = PIXEL_HA

    # ---------- ANCRE : stabilité spectrale Stack-à-Stack de CETTE année par rapport à l'ancre (anciennes années seulement) ----------
    ANCHOR_CTX.clear()
    ANCHOR_CTX["active"] = False
    _anchor_meta = None
    if anchor_cfg and int(yr) != int(anchor_cfg["year"]):
        _next_prep_step()                                          # stabilité spectrale (tics par bande)
        try:
            _amap, _asrc = get_map_for_year(output_dir, anchor_cfg["year"], rows, cols, geo_tf, proj_wkt)
            if _amap is None:
                raise RuntimeError(f"la carte finale de l'ancre {anchor_cfg['year']} est introuvable (ni en mémoire ni dans le dossier de résultats) : classez d'abord {anchor_cfg['year']}.")
            _anames = stack_band_names(anchor_cfg["stack"])
            _stab = anchor_stability(band_names, raw_arrays, _anames,
                                     lambda _i: anchor_band_reader(anchor_cfg["stack"], _i, rows, cols, geo_tf, proj_wkt), valid & admin_mask)
            ANCHOR_CTX.update(build_anchor_ctx(yr, anchor_cfg["year"], _amap, _stab, pixel_area_ha, anchor_cfg.get("min_level", 1), source=_asrc))
            export_anchor_outputs(output_dir, ANCHOR_CTX, geo_tf, proj_wkt)
            _anchor_meta = {"anchor_year": ANCHOR_CTX["anchor_year"], "year": ANCHOR_CTX["year"], "weight": round(float(ANCHOR_CTX["weight"]), 4), "n_bands": ANCHOR_CTX["n_bands"],
                            "min_level": ANCHOR_CTX["min_level"], "source": ANCHOR_CTX["source"]}
            print(f"[Ancre {anchor_cfg['year']}→{yr}] {_stab['n_bands']} bandes comparées ({_stab['n_common']} communes ; texture / thermique exclues), carte de l'ancre : {_asrc}.")
            for _ln in anchor_summary_lines(ANCHOR_CTX):
                print("    " + re.sub(r"<[^>]+>", "", _ln.replace("<br>", " ")).strip())
        except Exception as _exc:
            print(f"[Ancre] IGNORÉE pour {yr} : {_exc}")
            ANCHOR_CTX.clear()
            ANCHOR_CTX["active"] = False

    def run_simple_stage(stage_n, title, active_mask, class_code, threshold_func, default_mask=None):
        """
        Étape calibrée, MÊME FENÊTRE pour les 9 étapes (Sebkha ... Bareland) : seuils / RF / hybride + panneau « Masque de l'étape ».
        default_mask : masque proposé par défaut (Sebkha_Finale, Built_up_<année>) ; modifiable dans la fenêtre. Interactif : fenêtre ;
        batch / reprise : preset rejoué (étapes 1-3 sans preset : masque et seuils par défaut). Retourne les pixels positifs de la classe.
        Étapes 4-8 : si la classe est fournie par un masque programmatique, aucune fenêtre (la classe = le masque). Étapes 1-3 : un masque
        programmatique s'AJOUTE au résultat de la fenêtre (union).
        """
        if auto_cfg is not None:
            progress_tick(stage_n - 1, 8, title)                   # fenêtre de progression (mode batch)
        if default_mask is None and ANCHOR_CTX.get("active") and stage_n >= 3:
            default_mask = {"source": "anchor", "role": "union", "level": ANCHOR_CTX["min_level"]}     # ancienne année : l'ancre est proposée par défaut
        if class_code in forced and stage_n >= 4:
            print(f"    [MASQUE IMPOSÉ] {title} : classe fournie par masque → fenêtre de calibration ignorée.")
            return np.zeros(active_mask.shape, dtype=bool)
        if int(start_stage) > stage_n:
            _p = load_preset(yr, stage_n, output_dir)
            _has = bool(_p)
            if not _has:
                if stage_n > 3:
                    raise RuntimeError(f"Impossible de reprendre à l'étape {start_stage}: preset de l'étape {stage_n} introuvable pour {yr}.")
                _p = {"mode": "thresholds", "thresholds": scientific_default_values(stage_n), "rf": {"enabled": False}}
            _th = (_p.get("thresholds") if "thresholds" in _p else scientific_default_values(stage_n)) or {}
            _rf = _p.get("rf", {"enabled": False}) or {"enabled": False}
            _mode = _p.get("mode", "thresholds")
            _ms = (_p.get("mask") if _has else default_mask) or {}
            stage_mask_log[stage_n] = _ms if mask_spec_active(_ms) else None
            c_, _qa, _b, _minfo = apply_stage_mask(
                _ms, active_mask, rows, cols, geo_tf, proj_wkt,
                lambda b_: compute_stage_mask(_mode, _th, b_, threshold_func, _rf, stage_n, write_qa=False), stage_class=class_code)
            if mask_info_active(_minfo):
                print("    [Reprise] " + describe_stage_mask(_minfo, mask_stage_px_ha(geo_tf)))
            return c_
        status_, c_ = stage_dialog(stage_n, title, active_mask, class_code, threshold_func, default_mask=default_mask,
                                   default_thresholds=scientific_default_values(stage_n))
        if status_ == "BACK":
            raise StageBackRequested(stage_n)
        if review_implausible and auto_cfg is None and prev_map is not None:
            c_ = review_stage_transitions(stage_n, title, active_mask, class_code, threshold_func, default_mask, c_)
        return c_

    def review_stage_transitions(stage_n, title, active_mask, class_code, threshold_func, default_mask, c0):
        """Fenêtre indépendante des transitions improbables de CETTE étape (si elles existent) : corrections avant l'étape suivante."""
        reverse = bool(change_ctx and change_ctx.get("reverse"))
        info = {"title": title, "stage_n": stage_n, "year": yr, "ref_year": prev_year, "class_code": class_code, "reverse": reverse}

        def reopen():
            st_, cc_ = stage_dialog(stage_n, title, active_mask, class_code, threshold_func, default_mask=default_mask, default_thresholds=scientific_default_values(stage_n))
            if st_ == "BACK":
                raise StageBackRequested(stage_n)
            return cc_

        def show(sets, c_cur):
            progress_hide()
            dlg_r = ImplausibleTransitionsDialog(info, sets, prev_map, geo_tf, proj_wkt, pixel_area_ha, temp_dir(output_dir), STAGE_BACKGROUND.get("path", ""))
            show_dialog(dlg_r)
            return dlg_r.result_info
        return apply_stage_review(c0, prev_map, class_code, reverse, lulc, pixel_area_ha, show, reopen, stage_n, stage_review_log)

    # ==========================================================
    # 1. SEBKHA (classe 3) — fenêtre complète ; par défaut le masque STABLE (jamais reclassé), sinon seuils / RF
    # ==========================================================
    def th_sebkha(th, base):
        return th_by_rules(th, base, SEBKHA_RULES, features)

    def th_builtup(th, base):
        return th_by_rules(th, base, BUILTUP_RULES, features)

    def th_water(th, base):
        return th_by_rules(th, base, WATER_RULES, features)

    if auto_cfg is not None:                                       # mode batch : la fenêtre reste visible pendant les 8 étapes rejouées
        progress_open(f"Année {yr} — classification (mode batch)", [("Étapes 1 à 8 : presets rejoués", 1)])
        progress_step(0)
    else:                                                          # mode interactif : la fenêtre se cache pendant les fenêtres de calibration
        progress_hide()
    active = admin_mask & (lulc == 0)
    c = run_simple_stage(1, "Étape 1 : Sebkha", active, 3, th_sebkha,
                         default_mask=({"source": "vector", "path": shp_seb, "role": "total"} if shp_seb else None))
    sebkha_mask = (c | forced.get(3, False)) & admin_mask
    if not np.any(sebkha_mask):
        print("    [ATTENTION] Aucune Sebkha dans la zone d'étude (masque : CRS / emprise ? seuils trop stricts ?).")
    lulc[sebkha_mask] = 3
    if 3 in forced:
        forced_log.append((3, int(np.count_nonzero(forced[3] & admin_mask)), 0))
    if mask_priority:
        # Masques PRIORITAIRES (usage programmatique) : appliqués avant toute étape suivante, dans l'ordre hiérarchique.
        for _code in (1, 2, 7, 5, 6, 8, 4):
            if _code in forced:
                _n, _ign = apply_forced_mask(lulc, forced[_code], _code, admin_mask)
                forced_log.append((_code, _n, _ign))

    # Separate hydrological state INSIDE Sebkha; the LULC class remains Sebkha.
    seb_state = np.zeros((rows, cols), dtype=np.uint8)
    seb_state[sebkha_mask] = 1  # dry/exposed surface
    wet = sebkha_mask & ((features["apr_mndwi"] > 0.10) | (features["apr_ndwi"] > 0.05))
    seb_state[wet] = 2           # wet/inundated
    state_path = os.path.join(output_dir, f"SEBKHA_WATER_STATE_{yr}.tif")
    state_path = write_raster(state_path, seb_state, geo_tf, proj_wkt, gdal.GDT_Byte, 0)

    # ==========================================================
    # 2. BUILT-UP (classe 1) — fenêtre complète ; par défaut le masque de l'année, sinon seuils / RF
    # ==========================================================
    active = valid & (lulc == 0)
    if built_up_mask_path and not os.path.exists(str(built_up_mask_path)):
        built_up_mask_path = None
    _bu_ext = os.path.splitext(str(built_up_mask_path))[1].lower()
    c = run_simple_stage(2, "Étape 2 : Built-up", active, 1, th_builtup,
                         default_mask=({"source": "vector" if _bu_ext in STAGE_MASK_VECTOR_EXTS else "raster", "path": built_up_mask_path, "role": "total"}
                                       if built_up_mask_path else None))
    built_mask = (c | forced.get(1, False)) & admin_mask & (~sebkha_mask)
    if (1 in forced) and (not mask_priority):
        forced_log.append((1, int(np.count_nonzero(forced[1] & admin_mask & (~sebkha_mask))), int(np.count_nonzero(forced[1] & sebkha_mask))))
    if not np.any(built_mask):
        print(f"    [ATTENTION] Aucun Built-up {yr} dans la zone d'étude (masque : CRS / emprise ? seuils trop stricts ?).")
    lulc[built_mask] = 1
    print(f"[Built-up {yr}] {int(np.count_nonzero(built_mask)):,} pixels")

    # ==========================================================
    # 3. WATER (classe 2) — fenêtre complète ; par défaut seuils MNDWI (printemps / été) >= 0, masque facultatif
    # ==========================================================
    if (2 in forced) and (not mask_priority):
        _n, _ign = apply_forced_mask(lulc, forced[2], 2, admin_mask)
        forced_log.append((2, _n, _ign))
    active = valid & (lulc == 0)
    c = run_simple_stage(3, "Étape 3 : Water", active, 2, th_water)
    lulc[c] = 2
    print(f"[Water {yr}] {int(np.count_nonzero(c)):,} pixels")

    # ==========================================================
    # HIÉRARCHIE : 4 Forest (dense + claire) -> 5 Cropland -> 6 Fallow -> 7 Rangeland -> 8 Bareland / Rock -> résidu.
    # Aucune limite spatiale forestière : chaque étape travaille sur TOUS les pixels encore non classés (et valides).
    # Un masque imposé (facultatif) pour la classe de l'étape est appliqué juste avant l'étape.
    # ==========================================================
    # ---------- CLASSES FOURNIES PAR MASQUE (Forest, Cropland, Rangeland, Fallow, Bareland) ----------
    # Une classe donnée par un masque est EXTRAITE AVANT toute fenêtre de calibration : ses pixels apparaissent déjà colorés dans les
    # fenêtres des autres étapes, sont exclus de leur domaine, et SA PROPRE ÉTAPE N'OUVRE AUCUNE FENÊTRE (la classe = le masque).
    # Hiérarchie respectée pour les classes 1-3 : Sebkha, Built-up et Water gardent la priorité sur ces masques.
    # (Mode « prioritaires » : tous les masques ont déjà été appliqués au tout début.)
    if not mask_priority:
        for _code in (7, 5, 6, 8, 4):
            if _code in forced:
                _n, _ign = apply_forced_mask(lulc, forced[_code], _code, admin_mask)
                forced_log.append((_code, _n, _ign))

    # ---------- 4. FOREST (classe 7) ----------
    active = valid & (lulc == 0)

    def th_forest_block(th, base):
        c = base.copy()
        if th.get("msavi2_min") is not None:
            c &= features["apr_msavi"] >= th["msavi2_min"]
        if th.get("msavi2_max") is not None:
            c &= features["apr_msavi"] <= th["msavi2_max"]
        if th.get("f_apr_ndvi_min") is not None:
            c &= features["apr_ndvi"] >= th["f_apr_ndvi_min"]
        if th.get("f_apr_msavi_min") is not None:
            c &= features["apr_msavi"] >= th["f_apr_msavi_min"]
        if th.get("f_apr_ndmi_min") is not None:
            c &= features["apr_ndmi"] >= th["f_apr_ndmi_min"]
        if th.get("f_jul_ndmi_min") is not None:
            c &= features["jul_ndmi"] >= th["f_jul_ndmi_min"]
        if th.get("f_nbr_min") is not None:
            c &= features["apr_nbr"] >= th["f_nbr_min"]
        if th.get("f_jul_msavi_min") is not None:
            c &= features["jul_msavi"] >= th["f_jul_msavi_min"]
        if th.get("f_jul_ndvi_min") is not None:
            c &= features["jul_ndvi"] >= th["f_jul_ndvi_min"]
        if th.get("f_amp_max") is not None:
            c &= features["amp"] <= th["f_amp_max"]
        if th.get("f_jul_tcg_min") is not None:
            c &= features["jul_tcg"] >= th["f_jul_tcg_min"]
        # BUGFIX: champs affichés (Google/Original) mais jamais appliqués.
        if th.get("f_apr_tcg_min") is not None:
            c &= features["apr_tcg"] >= th["f_apr_tcg_min"]
        if th.get("f_tex_min") is not None:
            c &= features["texture_variance"] >= th["f_tex_min"]
        if th.get("f_ndvi_sm_min") is not None:  # NDVI "Été" (summer) ~ Jul_NDVI
            c &= features["jul_ndvi"] >= th["f_ndvi_sm_min"]
        if th.get("f_msavi_sm_min") is not None:  # MSAVI "Été" (summer) ~ Jul_MSAVI2
            c &= features["jul_msavi"] >= th["f_msavi_sm_min"]
        if th.get("f_ndvi_sp_min") is not None:  # NDVI "Printemps" (spring) ~ Apr_NDVI
            c &= features["apr_ndvi"] >= th["f_ndvi_sp_min"]
        return c

    def th_forest(th, base):
        """
        Forest = UNE classe : forêt DENSE (bloc A : champs 1-3 et indicateurs facultatifs) OU forêt CLAIRE, ancien Matorral (bloc B : champs fo_*).
        Bloc B vide (tous les champs fo_* vides) = forêt dense seule. Le bloc B ne s'applique qu'aux pixels que le bloc A n'a pas retenus.
        """
        dense = th_forest_block(th, base)
        open_th = {"msavi2_min": th.get("fo_msavi2_min"), "msavi2_max": th.get("fo_msavi2_max"),
                   "f_apr_ndvi_min": th.get("fo_apr_ndvi_min"), "f_amp_max": th.get("fo_amp_max")}
        if all(v is None for v in open_th.values()):
            return dense
        return dense | th_forest_block(open_th, base & ~dense)

    c = run_simple_stage(4, "Étape 4 : Forest (dense + claire)", active, 7, th_forest)
    lulc[c] = 7
    # (l'ancienne étape 5 « Matorral » est fusionnée dans Forest ; les étapes suivantes sont numérotées 5 à 8)

    # ---------- 6. CROPLAND (classe 5) ----------
    active = valid & (lulc == 0)

    def th_crop(th, base):
        c = base.copy()
        if th.get("msavi2_min") is not None:
            c &= features["apr_msavi"] >= th["msavi2_min"]
        if th.get("msavi2_max") is not None:
            c &= features["apr_msavi"] <= th["msavi2_max"]
        if th.get("crop_amp_min") is not None:
            c &= features["amp"] >= th["crop_amp_min"]
        if th.get("crop_msavi_sp_min") is not None:
            c &= features["apr_msavi"] >= th["crop_msavi_sp_min"]
        if th.get("crop_ndvi_sp_min") is not None:
            c &= features["apr_ndvi"] >= th["crop_ndvi_sp_min"]
        if th.get("crop_ndmi_sp_min") is not None:
            c &= features["apr_ndmi"] >= th["crop_ndmi_sp_min"]
        if th.get("crop_jul_ndvi_max") is not None:
            c &= features["jul_ndvi"] <= th["crop_jul_ndvi_max"]
        if th.get("crop_jul_msavi_max") is not None:
            c &= features["jul_msavi"] <= th["crop_jul_msavi_max"]
        if th.get("crop_jul_ndmi_min") is not None:
            c &= features["jul_ndmi"] >= th["crop_jul_ndmi_min"]
        if th.get("crop_jul_ndmi_max") is not None:
            c &= features["jul_ndmi"] <= th["crop_jul_ndmi_max"]
        if th.get("crop_delta_min") is not None:
            c &= features["delta"] <= th["crop_delta_min"]
        if th.get("crop_jul_dbsi_min") is not None:
            c &= features["jul_dbsi"] >= th["crop_jul_dbsi_min"]
        # BUGFIX: champ affiché (Google) mais jamais appliqué (aucun EVI n'était calculé).
        if th.get("crop_evi_min") is not None:
            c &= features["apr_evi"] >= th["crop_evi_min"]
        return c

    c = run_simple_stage(5, "Étape 5 : Cropland", active, 5, th_crop)
    lulc[c] = 5
    # Contexte spatial : fraction de Cropland dans un rayon de CONTEXT_RADIUS_M (disponible dans les fenêtres Fallow, Rangeland et Bareland).
    features["crop_frac_ctx"] = crop_context_feature(lulc, admin_mask, geo_tf, CONTEXT_RADIUS_M)

    # ---------- 7. FALLOW (classe 6) : AVANT Rangeland ; preuve temporelle (NDVI multi-années, LPD) facultative ----------
    active = valid & (lulc == 0)

    def th_fallow(th, base):
        """Threshold Fallow using the universal Apr_MSAVI2 range as the primary gate.

        The MSAVI2 min/max interval defines the candidate Fallow domain. Other
        indicators are supporting evidence, handled as a soft score rather than
        an all-AND chain. This prevents the Fallow class from collapsing to zero
        because one secondary indicator is too restrictive.
        """
        # ---- PRIMARY BASIS: Apr_MSAVI2 min/max ----
        msavi_base = base.copy()
        if th.get("msavi2_min") is not None:
            msavi_base &= features["apr_msavi"] >= th["msavi2_min"]
        if th.get("msavi2_max") is not None:
            msavi_base &= features["apr_msavi"] <= th["msavi2_max"]

        n_dom = int(np.count_nonzero(base))
        if not np.any(msavi_base):
            rule_trace_note("Seuils spectraux (plage MSAVI2)", n_dom, 0)
            return msavi_base

        # ---- SECONDARY / SUPPORTING EVIDENCE ----
        support = []
        if th.get("fal_jul_msavi_max") is not None:
            support.append(features["jul_msavi"] <= th["fal_jul_msavi_max"])
        if th.get("fal_jul_ndvi_max") is not None:
            support.append(features["jul_ndvi"] <= th["fal_jul_ndvi_max"])
        if th.get("fal_delta") is not None:
            support.append(features["delta"] <= th["fal_delta"])
        if th.get("fal_dbsi_min") is not None:
            support.append(features["apr_dbsi"] >= th["fal_dbsi_min"])
        if th.get("fal_bsi_min") is not None:
            support.append(features["apr_dbsi"] >= th["fal_bsi_min"])
        if th.get("fal_amp") is not None:
            support.append(features["amp"] >= th["fal_amp"])
        if th.get("fal_swir1_min") is not None:
            support.append(features["apr_swir1"] >= th["fal_swir1_min"])
        if th.get("fal_msavi_min") is not None:
            support.append(features["apr_msavi"] >= th["fal_msavi_min"])
        if th.get("fal_msavi_max") is not None:
            support.append(features["apr_msavi"] <= th["fal_msavi_max"])

        if not support:
            # MSAVI2 range alone is sufficient when no secondary evidence is configured.
            rule_trace_note("Seuils spectraux (plage MSAVI2 seule)", n_dom, np.count_nonzero(msavi_base))
            return th_by_rules(th, msavi_base, FALLOW_TEMPORAL_RULES, features)

        score = np.zeros(msavi_base.shape, dtype=np.uint8)
        for cond in support:
            score += cond.astype(np.uint8)

        # MSAVI2 is mandatory; at least one independent supporting signal is enough.
        spectral = msavi_base & (score >= 1)
        rule_trace_note("Seuils spectraux (MSAVI2 + au moins un signal de soutien)", n_dom, np.count_nonzero(spectral))
        return th_by_rules(th, spectral, FALLOW_TEMPORAL_RULES, features)

    c = run_simple_stage(6, "Étape 6 : Fallow", active, 6, th_fallow)
    lulc[c] = 6

    # ---------- 8. RANGELAND (classe 8) ----------
    active = valid & (lulc == 0)

    def th_rangeland(th, base):
        c = base.copy()
        if th.get("msavi2_min") is not None:
            c &= features["apr_msavi"] >= th["msavi2_min"]
        if th.get("msavi2_max") is not None:
            c &= features["apr_msavi"] <= th["msavi2_max"]
        if th.get("rang_msavi_min") is not None:
            c &= features["apr_msavi"] >= th["rang_msavi_min"]
        if th.get("rang_msavi_max") is not None:
            c &= features["apr_msavi"] <= th["rang_msavi_max"]
        if th.get("rang_amp_max") is not None:
            c &= features["amp"] <= th["rang_amp_max"]
        rule_trace_note("Seuils spectraux (MSAVI2, amplitude)", np.count_nonzero(base), np.count_nonzero(c))
        return th_by_rules(th, c, RANGELAND_EVIDENCE_RULES, features)

    c = run_simple_stage(7, "Étape 7 : Rangeland", active, 8, th_rangeland)
    lulc[c] = 8

    # ---------- 9. BARELAND / ROCK (classe 4) : désormais en DERNIER ----------
    active = valid & (lulc == 0)

    def th_bareland(th, base):
        c = base.copy()
        if th.get("msavi2_min") is not None:
            c &= features["apr_msavi"] >= th["msavi2_min"]
        if th.get("msavi2_max") is not None:
            c &= features["apr_msavi"] <= th["msavi2_max"]
        if th.get("bare_dbsi_min") is not None:
            c &= features["apr_dbsi"] >= th["bare_dbsi_min"]
        if th.get("bare_ndbi_min") is not None:
            c &= features["apr_ndbi"] >= th["bare_ndbi_min"]
        if th.get("bare_swir1_min") is not None:
            c &= features["apr_swir1"] >= th["bare_swir1_min"]
        if th.get("bare_swir2_min") is not None:
            c &= features["apr_swir2"] >= th["bare_swir2_min"]
        if th.get("bare_ndvi_max") is not None:
            c &= features["apr_ndvi"] <= th["bare_ndvi_max"]
        if th.get("bare_amp_max") is not None:
            c &= features["amp"] <= th["bare_amp_max"]
        if th.get("bare_msavi_max") is not None:
            c &= features["apr_msavi"] <= th["bare_msavi_max"]
        if th.get("bare_tex_min") is not None:
            c &= features["texture_variance"] >= th["bare_tex_min"]
        rule_trace_note("Seuils spectraux (DBSI, NDVI, MSAVI2, amplitude, texture)", np.count_nonzero(base), np.count_nonzero(c))
        return th_by_rules(th, c, BARELAND_TEMPORAL_RULES, features)

    c = run_simple_stage(8, "Étape 8 : Bareland / Rock", active, 4, th_bareland)
    lulc[c] = 4

    # ---------- 10. RÉSIDU + REMPLISSAGE PAR LE VOISIN CLASSÉ LE PLUS PROCHE ----------
    # Les pixels encore non classés dans la zone d'étude reçoivent la classe du plus proche pixel classé ;
    # tout résidu restant devient Bareland / Rock. Hors masque administratif : NoData (0).
    progress_open(f"Année {yr} — finalisation", [("Remplissage des pixels non classés", 1), ("Enregistrement de la carte et des fichiers de contrôle", 2),
                                                 ("Enregistrement de la carte finale (après édition visuelle)", 1), ("Analyse du changement", 3), ("Tableaux, rapport HTML et métadonnées", 2)])
    progress_step(0)
    prefill_map = lulc.copy()                                  # classification AVANT remplissage (sauvegardée dans Controle/)
    lulc, fill_info, fill_code = fill_unclassified(lulc, admin_mask)
    print(f"[Remplissage] {fill_info['unresolved_px']:,} px non classés après les 8 étapes ({fill_info['filled_percent']:.2f} % de la zone d'étude) : "
          f"{fill_info['nn_filled_px']:,} complétés par le voisin classé le plus proche, {fill_info['bareland_fallback_px']:,} par le repli Bareland.")
    if fill_info["filled_percent"] > FILL_WARN_PERCENT:
        print(f"    ⚠ Plus de {FILL_WARN_PERCENT:g} % de la zone est complétée automatiquement : vérifiez la couverture des images, les masques NoData et les seuils avant d'accepter la carte "
              f"(cartes dans Controle/ : PreFill_Map_{yr}.tif et Fill_Mask_{yr}.tif).")

    # ---------- AUDIT DES MASQUES IMPOSÉS ----------
    if forced_log:
        _audit = [["Year", "Class_ID", "Class", "Mask_pixels_in_study_area", "Imposed_pixels", "Ignored_pixels_already_classified", "Final_pixels_of_class_inside_mask", "Retention_percent"]]
        for _code, _n, _ign in forced_log:
            _inside = int(np.count_nonzero(forced[_code] & admin_mask))
            _kept = int(np.count_nonzero(forced[_code] & admin_mask & (lulc == _code)))
            _ret = (100.0 * _kept / _inside) if _inside else 100.0
            _audit.append([yr, _code, CLASS_NAMES[_code], _inside, _n, _ign, _kept, f"{_ret:.2f}"])
            print(f"    [MASQUE IMPOSÉ] {CLASS_NAMES[_code]}: {_inside:,} px dans la zone | imposés {_n:,} | "
                  f"ignorés (classe antérieure) {_ign:,} | conservés à la fin {_kept:,} ({_ret:.1f} %)")
        write_csv_rows(os.path.join(output_dir, f"Stage_Masks_Applied_{yr}.csv"), _audit)

    # ---------- OUTPUT ----------
    progress_step(1)
    out_path = lulc_map_path(output_dir, yr)                 # <résultats>/LULC/LULC_<AREA_TAG>_<année>.tif
    out_path = save_lulc_layer(out_path, yr, lulc, geo_tf, proj_wkt)
    try:                                                     # traçabilité : classification avant remplissage + pixels complétés (1 = voisin, 2 = repli Bareland)
        write_raster(os.path.join(control_dir(output_dir), f"PreFill_Map_{yr}.tif"), prefill_map, geo_tf, proj_wkt, gdal.GDT_Byte, 0)
        write_raster(os.path.join(control_dir(output_dir), f"Fill_Mask_{yr}.tif"), fill_code, geo_tf, proj_wkt, gdal.GDT_Byte, 0)
    except Exception as _exc:
        print(f"[Remplissage] cartes de contrôle non écrites : {_exc}")

    # ---------- VISUAL LULC QA/QC EDITING ----------
    # The original raster is preserved as *_Original.tif. The user may inspect
    # the map visually and apply polygon edits. The edited array then becomes
    # the final LULC used by the downstream AREA QA and independent Accuracy
    # Assessment. No validation samples are consulted by this module.
    progress_hide()                                            # fenêtre d'édition visuelle : pas de fenêtre d'attente par-dessus
    _visual_editor = VisualLULCEditingDialog(
        yr, lulc, geo_tf, proj_wkt, output_dir, pixel_area_ha, parent=None
    )
    show_dialog(_visual_editor)
    if _visual_editor.result() != QDIALOG_ACCEPTED:
        raise RuntimeError(
            f"Visual LULC QA/QC annulée pour {yr}. "
            "La carte n'est pas validée pour continuer vers Accuracy Assessment."
        )
    lulc, _visual_edited_path, _visual_edits = _visual_editor.get_result()
    progress_show()
    progress_step(2)
    # Canonical LULC filename now represents the edited/final map, while the
    # untouched pre-edit version remains available as *_Original.tif.
    out_path = save_lulc_layer(out_path, yr, lulc, geo_tf, proj_wkt)
    classified_arrays[yr] = lulc.copy() if 'classified_arrays' in globals() else lulc.copy()
    register_previous_map(yr, lulc, geo_tf)          # les années suivantes la comparent depuis la MÉMOIRE
    ANCHOR_CTX.clear()
    ANCHOR_CTX["active"] = False

    # ---------- CHANGEMENT vs ANNÉE PRÉCÉDENTE : tableaux CSV + carte (de x 10 + vers) + alertes ----------
    progress_step(3)
    _an_f = None
    if prev_map is not None:
        try:
            # fichiers et tableaux toujours en sens CHRONOLOGIQUE : ancien -> récent (les deux cartes sont complètes)
            _older, _newer, _a_old, _a_new = ((yr, prev_year, lulc, prev_map) if change_ctx["reverse"] else (prev_year, yr, prev_map, lulc))
            _an_f = analyze_change(_a_old, _a_new, pixel_area_ha, domain=admin_mask, prev_year=_older, cur_year=_newer)
            export_change_reports(output_dir, _older, _newer, _an_f, _a_old, _a_new, geo_tf, proj_wkt)
            _ls = _an_f["landscape"]
            _n = max(_ls["compared_px"], 1)
            print(f"[Changement {_older}→{_newer}] changement total {100.0 * _ls['changed_px'] / _n:.1f} % = net {100.0 * _ls['net_px'] / _n:.1f} % "
                  f"+ échange {100.0 * _ls['exchange_px'] / _n:.1f} % + déplacement {100.0 * _ls['shift_px'] / _n:.1f} % | fichiers Change_*_{_older}_{_newer}.*")
            for _a in _an_f["alerts"]:
                print(f"    {'🔴' if _a['level'] == 'red' else '🟠'} {_a['text']}")
        except Exception as _exc:
            print(f"[Changement {prev_year}↔{yr}] export impossible : {_exc}")

    # ---------- AREA TABLE ----------
    progress_step(4)
    area_path = os.path.join(output_dir, f"Areas_{yr}.csv")
    _rows = [["Year", "Class_ID", "Class", "Area_ha", "Area_km2", "Percent_admin"]]
    total_ha = np.count_nonzero(admin_mask) * pixel_area_ha
    for cid, cname in CLASS_NAMES.items():
        ha = np.count_nonzero(lulc == cid) * pixel_area_ha
        pct = (ha / total_ha * 100.0) if total_ha > 0 else 0.0
        _rows.append([yr, cid, cname, f"{ha:.4f}", f"{ha/100:.4f}", f"{pct:.4f}"])
    write_csv_rows(area_path, _rows)

    # ---------- METADATA ----------
    meta = {
        "version": "V17_HIERARCHIE_FOREST_8CLASSES_BARE_LAST",
        "year": yr,
        "hierarchy": [
            "STRICT_ADMIN_MASK",
            "STABLE_SEBKHA_MASK_FIRST",
            "BUILT_UP",
            "WATER_OUTSIDE_SEBKHA",
            "FOREST_7_DENSE_OR_OPEN",
            "CROPLAND_5",
            "FALLOW_6",
            "RANGELAND_8",
            "BARELAND_ROCK_4_LAST",
            "FINAL_RESIDUAL_NEAREST_NEIGHBOUR_THEN_BARELAND"
        ],
        "forest_boundary": "SUPPRIMEE : aucune limite spatiale forestiere",
        "stage_masks": {str(_n): stage_mask_log.get(_n) for _n in range(1, 9)},
        "implausible_review": {str(k): {kk: vv for kk, vv in v.items()} for k, v in stage_review_log.items()},
        "anchor": _anchor_meta,
        "stable_sebkha_is_not_reclassified": True,
        "sebkha_water_state_output": os.path.basename(state_path),
        "stage_features": STAGE_FEATURES,
        "rf_estimators": RF_N_ESTIMATORS,
        "rf_max_depth": RF_MAX_DEPTH,
        "rf_min_samples_leaf": RF_MIN_SAMPLES_LEAF,
        "random_state": RF_RANDOM_STATE,
        "validation_fraction": VALIDATION_FRACTION,
        "pixel_area_ha": float(pixel_area_ha),
        "nearest_neighbour_fill": True,
        "fill": fill_info,
        "source_stack": y_info["stack"]
    }
    with open(
        os.path.join(output_dir, f"Metadata_{yr}.json"),
        "w", encoding="utf-8"
    ) as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    # ---------- RAPPORT HTML DE L'ANNÉE (<résultats>/Rapports/Rapport_<année>.html) ----------
    try:
        _areas = [(cid, cname, np.count_nonzero(lulc == cid) * pixel_area_ha,
                   (np.count_nonzero(lulc == cid) * pixel_area_ha / total_ha * 100.0) if total_ha > 0 else 0.0) for cid, cname in CLASS_NAMES.items()]
        _files = [("Carte LULC", os.path.join(LULC_SUBDIR, f"LULC_{AREA_TAG}_{yr}.tif")), ("Surfaces (CSV)", f"Areas_{yr}.csv"), ("Métadonnées", f"Metadata_{yr}.json")]
        if _an_f is not None:
            _files.append(("Changement (carte et tableaux)", os.path.join(CHANGE_SUBDIR, f"Change_*_{_an_f['older_year']}_{_an_f['newer_year']}.*")))
        if _anchor_meta:
            _files.append(("Ancre (niveaux, étiquettes, tableaux)", os.path.join(ANCHOR_SUBDIR, f"Anchor_*_{_anchor_meta['anchor_year']}_{yr}.*")))
        _rep_path = write_year_report(output_dir, yr, build_year_report_html(yr, _areas, pixel_area_ha, stage_rows_from_presets(yr, output_dir), _anchor_meta, _an_f, _files, fill=fill_info, reviews=stage_review_log))
        print(f"[Rapport] {_rep_path}")
    except Exception as _exc:
        print(f"[Rapport] rapport HTML non écrit : {_exc}")

    progress_close()
    return lulc, out_path, geo_tf, proj_wkt, {
        "year": yr,
        "areas": {
            cname: float(np.count_nonzero(lulc == cid) * pixel_area_ha)
            for cid, cname in CLASS_NAMES.items()
        }
    }



# ====================== CHANGE DETECTION ======================
# Analyse de changement basée sur les tableaux LULC déjà classifiés.
# Codes de classe identiques à CLASS_NAMES (1..8). 0 = NoData / hors masque.


def pixel_area_ha_from_gt(geo_tf):
    """Surface d'un pixel en hectares à partir du géotransform."""
    try:
        return abs(geo_tf[1] * geo_tf[5] - geo_tf[2] * geo_tf[4]) / 10000.0
    except Exception:
        return PIXEL_HA


def transition_matrix(a, b):
    """Retourne mat[(from,to)] = nombre de pixels. 0 ignoré (NoData)."""
    a = np.asarray(a).astype(np.int32)
    b = np.asarray(b).astype(np.int32)
    if a.shape != b.shape:
        raise ValueError(
            f"Les tableaux {a.shape} et {b.shape} n'ont pas la même taille."
        )
    valid = (a > 0) & (b > 0)
    af = a[valid]
    bf = b[valid]
    mat = {}
    for f, t in zip(af, bf):
        mat[(int(f), int(t))] = mat.get((int(f), int(t)), 0) + 1
    return mat


def build_change_map(a, b):
    """Raster uint16 où valeur = from*10 + to (0 si pas de changement valide)."""
    a = np.asarray(a).astype(np.int32)
    b = np.asarray(b).astype(np.int32)
    valid = (a > 0) & (b > 0)
    out = np.zeros(a.shape, dtype=np.uint16)
    out[valid] = (a[valid] * 10 + b[valid]).astype(np.uint16)
    return out


def change_map_color_dict():
    """Couleurs pour la carte From-To : inchangé = couleur classe, changé = mélange."""
    colors = {}
    for f in all_classes:
        for t in all_classes:
            code = f * 10 + t
            cf = CLASS_COLORS[f]
            ct = CLASS_COLORS[t]
            if f == t:
                colors[code] = QColor(cf)
            else:
                # Mélange pour rendre le changement visible.
                colors[code] = QColor(
                    int((cf.red() + ct.red()) / 2),
                    int((cf.green() + ct.green()) / 2),
                    int((cf.blue() + ct.blue()) / 2),
                )
    return colors


def export_change_matrix_csv(mat, pixel_ha, y1, y2, out_dir):
    """Écrit la matrice de transition en pixels, hectares et pourcentage de ligne."""
    path = os.path.join(out_dir, f"Transition_Matrix_{y1}_{y2}.csv")
    rows = [[f"From_{y1} \\ To_{y2}"] +
            [CLASS_NAMES[c] for c in all_classes] +
            ["Row_Total_px", "Row_Total_ha"]]
    for fr in all_classes:
        row_px = [mat.get((fr, to), 0) for to in all_classes]
        tot = sum(row_px)
        rows.append([CLASS_NAMES[fr]] + row_px + [tot, f"{tot * pixel_ha:.4f}"])
    col_tot = [sum(mat.get((fr, to), 0) for fr in all_classes) for to in all_classes]
    grand = sum(col_tot)
    rows.append(["Col_Total_px"] + col_tot + [grand, f"{grand * pixel_ha:.4f}"])
    rows.append(["Col_Total_ha"] +
                [f"{c * pixel_ha:.4f}" for c in col_tot] +
                ["", f"{grand * pixel_ha:.4f}"])

    # A second CSV is easier for statistical reporting: row-normalized
    # transition percentages (From-class denominator).
    pct_path = os.path.join(out_dir, f"Transition_Matrix_Percent_{y1}_{y2}.csv")
    pct_rows = [[f"From_{y1} \\ To_{y2}"] +
                [CLASS_NAMES[c] for c in all_classes] + ["Row_Total_%"]]
    for fr in all_classes:
        row_px = [mat.get((fr, to), 0) for to in all_classes]
        tot = float(sum(row_px))
        vals = [f"{(v / tot * 100.0 if tot else 0.0):.4f}" for v in row_px]
        pct_rows.append([CLASS_NAMES[fr]] + vals + ["100.0000" if tot else "0.0000"])
    write_csv_rows(pct_path, pct_rows)
    return write_csv_rows(path, rows)


def gain_loss_summary(mat, pixel_ha):
    """Gain/perte nets par classe (px et ha) à partir de la matrice."""
    summary = {}
    for c in all_classes:
        gained = sum(v for (f, t), v in mat.items() if t == c and f != c)
        lost = sum(v for (f, t), v in mat.items() if f == c and t != c)
        initial_px = sum(v for (f, t), v in mat.items() if f == c)
        final_px = sum(v for (f, t), v in mat.items() if t == c)
        summary[c] = {
            "gain_px": gained,
            "loss_px": lost,
            "net_px": gained - lost,
            "gain_ha": gained * pixel_ha,
            "loss_ha": lost * pixel_ha,
            "net_ha": (gained - lost) * pixel_ha,
            "initial_px": initial_px,
            "final_px": final_px,
            "gain_pct_initial": (100.0 * gained / initial_px) if initial_px else 0.0,
            "loss_pct_initial": (100.0 * lost / initial_px) if initial_px else 0.0,
        }
    return summary


def export_gain_loss_csv(summary, y1, y2, out_dir):
    path = os.path.join(out_dir, f"Gain_Loss_{y1}_{y2}.csv")
    rows = [["Class_ID", "Class", "Gain_px", "Loss_px", "Net_px",
             "Gain_ha", "Loss_ha", "Net_ha",
             "Gain_pct_initial", "Loss_pct_initial"]]
    for c in all_classes:
        s = summary[c]
        gain_pct = s.get("gain_pct_initial", 0.0)
        loss_pct = s.get("loss_pct_initial", 0.0)
        rows.append([c, CLASS_NAMES[c], s["gain_px"], s["loss_px"], s["net_px"],
                     f"{s['gain_ha']:.4f}", f"{s['loss_ha']:.4f}", f"{s['net_ha']:.4f}",
                     f"{gain_pct:.4f}", f"{loss_pct:.4f}"])
    return write_csv_rows(path, rows)


def strongest_transitions(mat, pixel_ha, top_n=10, only_changes=True):
    lst = []
    for (f, t), v in mat.items():
        if only_changes and f == t:
            continue
        lst.append((f, t, v, v * pixel_ha))
    lst.sort(key=lambda x: x[2], reverse=True)
    return lst[:top_n]


def add_colored_raster_layer(path, name, color_dict, nodata=0):
    """Charge un raster avec un rendu Exact coloré dans le projet QGIS."""
    _unload_layers_by_path(path)
    layer = QgsRasterLayer(path, name)
    if not layer.isValid():
        return None
    items = [
        QgsColorRampShader.ColorRampItem(code, col, str(code))
        for code, col in sorted(color_dict.items())
    ]
    shader = QgsRasterShader()
    ramp = QgsColorRampShader()
    ramp.setColorRampType(QgsColorRampShader.Exact)
    ramp.setColorRampItemList(items)
    shader.setRasterShaderFunction(ramp)
    layer.setRenderer(
        QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
    )
    QgsProject.instance().addMapLayer(layer)
    return layer


def write_change_map_raster(path, change_arr, geo_tf, proj_wkt):
    """Écrit la carte From-To (uint16) via write_raster robuste. Retourne le chemin écrit."""
    return write_raster(path, change_arr, geo_tf, proj_wkt, gdal.GDT_UInt16, 0)


# ---------- Export de graphiques PNG ----------

def chart_areas_stacked(yearly_areas_data, years, out_dir):
    if not MATPLOTLIB_AVAILABLE:
        return None
    fig, ax = plt.subplots(figsize=(10, 6))
    bottom = np.zeros(len(years))
    hex_colors = {c: CLASS_COLORS[c].name() for c in all_classes}
    for c in all_classes:
        vals = np.array([yearly_areas_data.get(y, {}).get(CLASS_NAMES[c], 0.0)
                         for y in years])
        ax.bar(years, vals, bottom=bottom, label=CLASS_NAMES[c], color=hex_colors[c])
        bottom += vals
    ax.set_ylabel("Surface (ha)")
    ax.set_title("Répartition des classes LULC par année")
    ax.legend(loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=8)
    fig.tight_layout()
    path = os.path.join(out_dir, "Chart_Areas_Stacked.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def chart_class_trends(yearly_areas_data, years, out_dir):
    if not MATPLOTLIB_AVAILABLE:
        return None
    fig, ax = plt.subplots(figsize=(10, 6))
    hex_colors = {c: CLASS_COLORS[c].name() for c in all_classes}
    for c in all_classes:
        vals = [yearly_areas_data.get(y, {}).get(CLASS_NAMES[c], 0.0) for y in years]
        ax.plot(years, vals, marker="o", label=CLASS_NAMES[c], color=hex_colors[c])
    ax.set_ylabel("Surface (ha)")
    ax.set_title("Tendances temporelles par classe")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=8)
    fig.tight_layout()
    path = os.path.join(out_dir, "Chart_Class_Trends.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def chart_transition_heatmap(mat, y1, y2, out_dir):
    if not MATPLOTLIB_AVAILABLE:
        return None
    n = len(all_classes)
    M = np.zeros((n, n), dtype=float)
    for i, f in enumerate(all_classes):
        for j, t in enumerate(all_classes):
            M[i, j] = mat.get((f, t), 0)
    fig, ax = plt.subplots(figsize=(9, 8))
    im = ax.imshow(M, cmap="YlOrRd")
    labels = [CLASS_NAMES[c] for c in all_classes]
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
    ax.set_yticklabels(labels, fontsize=7)
    ax.set_xlabel(f"Vers ({y2})")
    ax.set_ylabel(f"Depuis ({y1})")
    ax.set_title(f"Matrice de transition {y1} → {y2} (pixels)")
    for i in range(n):
        for j in range(n):
            v = int(M[i, j])
            if v > 0:
                ax.text(j, i, f"{v:,}", ha="center", va="center",
                        fontsize=6, color="black")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    path = os.path.join(out_dir, f"Chart_Transition_Heatmap_{y1}_{y2}.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def chart_gain_loss(summary, y1, y2, out_dir):
    if not MATPLOTLIB_AVAILABLE:
        return None
    fig, ax = plt.subplots(figsize=(10, 6))
    labels = [CLASS_NAMES[c] for c in all_classes]
    gains = [summary[c]["gain_ha"] for c in all_classes]
    losses = [-summary[c]["loss_ha"] for c in all_classes]
    x = np.arange(len(labels))
    ax.bar(x - 0.2, gains, width=0.4, label="Gain", color="#2e7d32")
    ax.bar(x + 0.2, losses, width=0.4, label="Perte", color="#c62828")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Surface (ha)")
    ax.set_title(f"Gain / Perte nets {y1} → {y2}")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.legend()
    fig.tight_layout()
    path = os.path.join(out_dir, f"Chart_Gain_Loss_{y1}_{y2}.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def export_strongest_transitions_csv(pairs_data, out_dir):
    """pairs_data: liste de (y1, y2, top_list)."""
    path = os.path.join(out_dir, "Strongest_Transitions.csv")
    rows = [["From_Year", "To_Year", "From_Class", "To_Class", "Pixels", "Hectares"]]
    for y1, y2, top in pairs_data:
        for f_, t_, px, ha in top:
            rows.append([y1, y2, CLASS_NAMES[f_], CLASS_NAMES[t_], px, f"{ha:.4f}"])
    return write_csv_rows(path, rows)


# ====================== CHANGE DETECTION DIALOG ======================
class ChangeDetectionDialog(QDialog):
    """Fenêtre interactive pour piloter l'analyse de changement."""

    def __init__(self, classified_arrays, yearly_areas_data, year_geo,
                 output_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Analyse de Changement — LULC")
        self.resize(836, 682)
        self.classified_arrays = classified_arrays
        self.yearly_areas_data = yearly_areas_data
        self.year_geo = year_geo  # {yr: (geo_tf, proj_wkt, pixel_ha)}
        self.output_dir = output_dir
        self.years = sorted(classified_arrays.keys(), key=lambda s: int(s))

        layout = QVBoxLayout(self)

        title = QLabel("🔀 Détection de changement (Transition Matrix • From-To Map • PNG)")
        title.setStyleSheet("font-size:14px;font-weight:bold;color:#0d47a1;")
        layout.addWidget(title)

        # --- Sélection des années ---
        sel_box = QGroupBox("Périodes")
        sel_layout = QGridLayout(sel_box)
        sel_layout.addWidget(QLabel("De (année initiale) :"), 0, 0)
        self.cb_from = QComboBox()
        self.cb_to = QComboBox()
        self.cb_from.addItems(self.years)
        self.cb_to.addItems(self.years)
        if len(self.years) >= 2:
            self.cb_to.setCurrentIndex(len(self.years) - 1)
        sel_layout.addWidget(self.cb_from, 0, 1)
        sel_layout.addWidget(QLabel("Vers (année finale) :"), 1, 0)
        sel_layout.addWidget(self.cb_to, 1, 1)
        layout.addWidget(sel_box)

        # --- Options ---
        opt_box = QGroupBox("Options")
        opt_layout = QVBoxLayout(opt_box)
        self.chk_all_pairs = QCheckBox("Traiter TOUTES les paires consécutives")
        self.chk_all_pairs.setChecked(True)
        self.chk_first_last = QCheckBox("Inclure aussi la paire première → dernière année")
        self.chk_first_last.setChecked(True)
        self.chk_png = QCheckBox("Exporter les graphiques PNG")
        self.chk_png.setChecked(True)
        self.chk_map = QCheckBox("Générer + charger la carte From-To colorée dans QGIS")
        self.chk_map.setChecked(True)
        opt_layout.addWidget(self.chk_all_pairs)
        opt_layout.addWidget(self.chk_first_last)
        opt_layout.addWidget(self.chk_png)
        opt_layout.addWidget(self.chk_map)
        layout.addWidget(opt_box)

        # --- Dossier sortie ---
        out_box = QGroupBox("Dossier de sortie")
        out_layout = QHBoxLayout(out_box)
        self.le_out = QLineEdit(os.path.join(change_dir(self.output_dir), "Analyse_Multi_Annees"))      # cartes ChangeMap_*, matrices, graphiques : sous Changement/
        btn_browse = QPushButton("Parcourir…")
        btn_browse.clicked.connect(self._browse_out)
        out_layout.addWidget(self.le_out)
        out_layout.addWidget(btn_browse)
        layout.addWidget(out_box)

        # --- Progression ---
        self.progress = QProgressBar()
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        # --- Log ---
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet("font-family:Consolas,monospace;font-size:11px;")
        layout.addWidget(self.log, 1)

        # --- Boutons ---
        btn_row = QHBoxLayout()
        btn_run = QPushButton("▶ Lancer l'analyse")
        btn_run.setStyleSheet("background-color:#2e7d32;color:white;font-weight:bold;padding:6px;")
        btn_run.clicked.connect(self.run_analysis)
        btn_close = QPushButton("Fermer")
        btn_close.clicked.connect(self.accept)
        btn_row.addStretch()
        btn_row.addWidget(btn_run)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _browse_out(self):
        d = QFileDialog.getExistingDirectory(self, "Dossier de sortie", self.le_out.text())
        if d:
            self.le_out.setText(d)

    def _log(self, msg):
        self.log.append(msg)
        self.log.repaint()

    def _build_pairs(self):
        pairs = []
        yrs = self.years
        if self.chk_all_pairs.isChecked():
            for i in range(len(yrs) - 1):
                pairs.append((yrs[i], yrs[i + 1]))
        else:
            y1 = self.cb_from.currentText()
            y2 = self.cb_to.currentText()
            if y1 and y2 and y1 != y2:
                pairs.append((y1, y2))
        if self.chk_first_last.isChecked() and len(yrs) >= 2:
            fl = (yrs[0], yrs[-1])
            if fl not in pairs:
                pairs.append(fl)
        return pairs

    def run_analysis(self):
        out_dir = self.le_out.text().strip() or self.output_dir
        os.makedirs(out_dir, exist_ok=True)
        charts_dir = os.path.join(out_dir, "Charts")
        os.makedirs(charts_dir, exist_ok=True)

        pairs = self._build_pairs()
        if not pairs:
            QMessageBox.warning(self, "Analyse de changement",
                                "Aucune paire d'années à traiter.")
            return

        self._log("=" * 60)
        self._log(f"Début analyse — {len(pairs)} paire(s) : {pairs}")
        self.progress.setMaximum(len(pairs))

        pairs_top = []
        try:
            for idx, (y1, y2) in enumerate(pairs):
                a = self.classified_arrays.get(y1)
                b = self.classified_arrays.get(y2)
                if a is None or b is None:
                    self._log(f"⚠️ {y1} ou {y2} indisponible — ignoré.")
                    self.progress.setValue(idx + 1)
                    continue
                if a.shape != b.shape:
                    self._log(f"⚠️ {y1}{a.shape} ≠ {y2}{b.shape} — ignoré.")
                    self.progress.setValue(idx + 1)
                    continue

                # pixel_ha : préfère la géométrie de l'année finale
                geo = self.year_geo.get(y2) or self.year_geo.get(y1)
                pixel_ha = geo[2] if geo else PIXEL_HA

                mat = transition_matrix(a, b)

                # 1) Matrice de transition CSV
                csv_path = export_change_matrix_csv(mat, pixel_ha, y1, y2, out_dir)
                self._log(f"[✓] Matrice transition : {os.path.basename(csv_path)}")

                # 2) Gain/perte
                summary = gain_loss_summary(mat, pixel_ha)
                gl_path = export_gain_loss_csv(summary, y1, y2, out_dir)
                self._log(f"[✓] Gain/Perte : {os.path.basename(gl_path)}")

                # 3) Transitions dominantes
                top = strongest_transitions(mat, pixel_ha, top_n=10)
                pairs_top.append((y1, y2, top))
                if top:
                    top_str = ", ".join(
                        f"{CLASS_NAMES[f]}→{CLASS_NAMES[t]} ({ha:,.1f} ha)"
                        for f, t, px, ha in top[:5]
                    )
                    self._log(f"    Dominantes {y1}→{y2}: {top_str}")

                # 4) Carte From-To
                if self.chk_map.isChecked() and geo:
                    gtf, prj, _ = geo
                    cmap = build_change_map(a, b)
                    map_path = os.path.join(out_dir, f"ChangeMap_{y1}_{y2}.tif")
                    map_path = write_change_map_raster(map_path, cmap, gtf, prj)
                    add_colored_raster_layer(
                        map_path, f"Change_{y1}_{y2}", change_map_color_dict()
                    )
                    self._log(f"[✓] Carte From-To : {os.path.basename(map_path)}")

                # 5) PNG
                if self.chk_png.isChecked():
                    try:
                        p = chart_transition_heatmap(mat, y1, y2, charts_dir)
                        if p:
                            self._log(f"[✓] Heatmap : {os.path.basename(p)}")
                        p = chart_gain_loss(summary, y1, y2, charts_dir)
                        if p:
                            self._log(f"[✓] Gain/Loss : {os.path.basename(p)}")
                    except Exception as e:
                        self._log(f"⚠️ PNG {y1}-{y2} échec : {e}")

                self.progress.setValue(idx + 1)

            # Transitions dominantes consolidées
            if pairs_top:
                st_path = export_strongest_transitions_csv(pairs_top, out_dir)
                self._log(f"[✓] Transitions dominantes : {os.path.basename(st_path)}")

            # PNG globaux (toutes années)
            if self.chk_png.isChecked() and len(self.years) >= 2:
                try:
                    p = chart_areas_stacked(self.yearly_areas_data, self.years, charts_dir)
                    if p:
                        self._log(f"[✓] Aires empilées : {os.path.basename(p)}")
                    p = chart_class_trends(self.yearly_areas_data, self.years, charts_dir)
                    if p:
                        self._log(f"[✓] Tendances : {os.path.basename(p)}")
                except Exception as e:
                    self._log(f"⚠️ PNG globaux échec : {e}")

            self._log("=" * 60)
            self._log("[✓] ANALYSE DE CHANGEMENT TERMINÉE.")
            self._log(f"    Sorties : {out_dir}")
            if self.chk_png.isChecked():
                self._log(f"    Graphiques : {charts_dir}")
            QMessageBox.information(self, "Analyse de changement",
                                    "Analyse terminée avec succès.\n\n"
                                    f"Résultats :\n{out_dir}")
        except Exception as e:
            import traceback
            self._log("❌ ERREUR : " + str(e))
            self._log(traceback.format_exc())
            QMessageBox.critical(self, "Erreur", f"Échec de l'analyse :\n{e}")


# ====================== MASQUES IMPOSÉS PAR ÉTAPE + CHOIX DES ANNÉES (AJOUT) ======================
# Ajout NON intrusif. Sans masque fourni et avec « toutes les années », le comportement est identique à la
# version précédente. Un masque imposé agit comme le masque stable Sebkha : ses pixels reçoivent la classe de
# l'étape et ne sont plus reclassés ensuite.
STAGE_MASK_SPECS = [
    # (code de classe, clé, libellé de l'étape) — dans l'ORDRE D'EXÉCUTION
    (3, "sebkha",    "Étape 1 — Sebkha (s'AJOUTE au masque stable Sebkha_Finale.shp)"),
    (1, "builtup",   "Étape 2 — Built-up (s'AJOUTE au masque Built_up_<année>)"),
    (2, "water",     "Étape 3 — Water"),
    (7, "forest",    "Étape 4 — Forest (dense + claire : l'ancien Matorral est inclus)"),
    (5, "cropland",  "Étape 5 — Cropland"),
    (6, "fallow",    "Étape 6 — Fallow (jachère)"),
    (8, "rangeland", "Étape 7 — Rangeland"),
    (4, "bareland",  "Étape 8 — Bareland / Rock"),
]
STAGE_MASK_VECTOR_EXTS = (".shp", ".gpkg", ".geojson", ".json")
STAGE_MASK_EXTS = STAGE_MASK_VECTOR_EXTS + (".tif", ".tiff")
STAGE_MASK_CONFIG = "Stage_Masks_Config.json"


def _split_year_suffix(path, years):
    """Si le nom (sans extension) se termine par une année de `years` : (dossier, préfixe, année, extension), sinon None."""
    base, ext = os.path.splitext(os.path.basename(path))
    m = re.match(r"^(.*?)(?<!\d)((?:19|20)\d{2})$", base)
    if m and m.group(2) in set(str(y) for y in years):
        return os.path.dirname(path), m.group(1), m.group(2), ext
    return None


def resolve_stage_mask_path(path, year, years):
    """
    Masque STATIQUE (nom sans année finale) : le même fichier pour toutes les années.
    Masque PAR ANNÉE (nom finissant par une année, ex. Water_2015.shp) : le fichier de CETTE année dans le même dossier
    (même préfixe ; extension identique ou une autre extension de masque) ; None s'il n'existe pas (jamais le masque d'une autre année).
    """
    if not path:
        return None
    sp = _split_year_suffix(path, years)
    if sp is None:
        return path if os.path.exists(path) else None
    folder, prefix, _y0, ext = sp
    for e in (ext,) + tuple(x for x in STAGE_MASK_EXTS if x != ext.lower()):
        cand = os.path.join(folder, f"{prefix}{year}{e}")
        if os.path.exists(cand):
            return cand
    return None


def apply_forced_mask(lulc, mask, class_code, admin_mask):
    """
    Impose `class_code` aux pixels du masque, dans la zone d'étude, qui sont ENCORE non classés (lulc == 0) : une classe
    d'une étape antérieure garde la priorité (même logique que la hiérarchie automatique).
    Retourne (pixels imposés, pixels du masque ignorés car déjà classés).
    """
    m = np.asarray(mask, dtype=bool) & np.asarray(admin_mask, dtype=bool)
    free = m & (lulc == 0)
    lulc[free] = int(class_code)
    return int(np.count_nonzero(free)), int(np.count_nonzero(m & ~free))


def _mask_from_array(arr, nodata=None):
    """Masque booléen d'un raster : pixels finis, non nuls et différents de la valeur NoData (contrairement à un simple « != 0 »)."""
    arr = np.asarray(arr)
    ok = np.isfinite(arr) & (arr != 0)
    if nodata is not None and np.isfinite(nodata):
        ok &= (arr != nodata)
    return ok


def read_stage_mask(path, rows, cols, geo_tf, proj_wkt):
    """Lit un masque (vecteur .shp/.gpkg/.geojson ou raster .tif) sur la grille du stack ; raster rééchantillonné au plus proche voisin."""
    empty = np.zeros((rows, cols), dtype=bool)
    if not path or not os.path.exists(path):
        return empty
    ext = os.path.splitext(path)[1].lower()
    if ext in STAGE_MASK_VECTOR_EXTS:
        return make_vector_mask(path, rows, cols, geo_tf, proj_wkt)
    ds = gdal.Open(path, gdal.GA_ReadOnly)
    if ds is None or ds.RasterCount < 1:
        return empty
    band = ds.GetRasterBand(1)
    nodata = band.GetNoDataValue()
    same_grid = (
        ds.RasterXSize == cols and ds.RasterYSize == rows
        and tuple(round(float(v), 6) for v in ds.GetGeoTransform()) == tuple(round(float(v), 6) for v in geo_tf)
    )
    if same_grid:
        arr = band.ReadAsArray().astype(np.float64)
    else:
        mem = gdal.GetDriverByName("MEM").Create("", cols, rows, 1, gdal.GDT_Float32)
        mem.SetGeoTransform(geo_tf)
        if proj_wkt:
            mem.SetProjection(proj_wkt)
        nod = float(nodata) if nodata is not None else -9999.0
        mem.GetRasterBand(1).SetNoDataValue(nod)
        mem.GetRasterBand(1).Fill(nod)
        gdal.ReprojectImage(ds, mem, ds.GetProjection(), proj_wkt or ds.GetProjection(), gdal.GRA_NearestNeighbour)
        arr = mem.GetRasterBand(1).ReadAsArray().astype(np.float64)
        nodata = nod
    return _mask_from_array(arr, nodata)


def _load_forced_masks(stage_masks, rows, cols, geo_tf, proj_wkt, admin_mask, year):
    """{code de classe: masque booléen} pour l'année ; les masques vides dans la zone d'étude sont signalés puis ignorés."""
    out = {}
    for code, path in (stage_masks or {}).items():
        if not path:
            continue
        m = read_stage_mask(path, rows, cols, geo_tf, proj_wkt) & admin_mask
        if not np.any(m):
            print(f"    [MASQUE IMPOSÉ][{year}] {CLASS_NAMES.get(int(code), code)} : le masque {os.path.basename(path)} ne contient AUCUN pixel "
                  "dans la zone d'étude (CRS / emprise ?) → ignoré.")
            continue
        out[int(code)] = m
    return out


def _stage_masks_for_year(masks_cfg, year, years):
    """Résout, pour une année, le chemin réel de chaque masque configuré (statique ou propre à l'année)."""
    out = {}
    for code, path in (masks_cfg or {}).items():
        p = resolve_stage_mask_path(path, year, years)
        if p:
            out[int(code)] = p
        else:
            print(f"    [MASQUE IMPOSÉ][{year}] {CLASS_NAMES.get(int(code), code)} : aucun masque pour cette année ({os.path.basename(path)}) → étape sans masque imposé.")
    return out


def merge_checkpoint_years(previous_completed, selected_years, newly_completed, order):
    """
    Années terminées à enregistrer : celles de CE traitement + celles d'exécutions précédentes qui n'ont PAS été
    traitées ici (un traitement d'une seule année ne doit pas effacer le point de reprise des autres).
    """
    keep = {str(y) for y in previous_completed if str(y) not in {str(s) for s in selected_years}}
    keep |= {str(y) for y in newly_completed}
    ordered = [str(y) for y in order if str(y) in keep]
    return ordered + sorted(y for y in keep if y not in ordered)


def merge_area_rows(existing_rows, new_rows, year_order):
    """
    Fusionne l'ancien tableau des surfaces (Year, Class_ID, Class, Area_ha) avec les années recalculées : les années
    recalculées remplacent leurs anciennes lignes, les autres années sont conservées. Entêtes inchangées.
    """
    header = ["Year", "Class_ID", "Class", "Area_ha"]
    new_years = {str(r[0]) for r in new_rows[1:]}
    old = [list(r) for r in (existing_rows or [])[1:] if r and str(r[0]) not in new_years]
    allrows = old + [list(r) for r in new_rows[1:]]
    pos = {str(y): i for i, y in enumerate(year_order)}
    allrows.sort(key=lambda r: (pos.get(str(r[0]), 10 ** 6), str(r[0]), int(r[1])))
    return [header] + allrows


def _read_csv_rows(path):
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            return [r for r in csv.reader(f)]
    except Exception:
        return []


_YEAR_FOLDER_RE = re.compile(r"^(?:(?:S|Stack)_)?((?:19|20)\d{2})$|^(?:S|Stack)_((?:19|20)\d{2})_.+$")

STACK_EXTS = (".dat", ".tif", ".tiff", ".img", ".vrt")                                   # extensions de Stack acceptées (insensibles à la casse)
STACK_EXCLUDE = ("LULC_", "Preview_", "RF_Confidence_", "SEBKHA_WATER_STATE_", "Anchor_", "Change_", "Built_up", "Canvas_")      # produits dérivés / masques : jamais un Stack


def _skip_dir(name):
    return name.startswith(".") or name.startswith("Resultats_")


def list_stack_rasters(folder):
    """Rasters candidats : directement dans le dossier (extensions STACK_EXTS, casse ignorée), sinon dans ses sous-dossiers DIRECTS. Les produits dérivés (LULC_, Preview_, masques Built_up...) sont exclus."""
    def good(fn):
        return os.path.splitext(fn)[1].lower() in STACK_EXTS and not any(w in fn for w in STACK_EXCLUDE)
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    out = [os.path.join(folder, n) for n in names if os.path.isfile(os.path.join(folder, n)) and good(n)]
    if out:
        return out
    for n in names:
        sub = os.path.join(folder, n)
        if os.path.isdir(sub) and not _skip_dir(n):
            try:
                out += [os.path.join(sub, f) for f in sorted(os.listdir(sub)) if os.path.isfile(os.path.join(sub, f)) and good(f)]
            except OSError:
                pass
    return out


def pick_stack(rasters):
    """Le Stack parmi les rasters d'un dossier d'année : le premier dont le nom contient « stack » ou « master », sinon le premier."""
    return next((r for r in rasters if "stack" in os.path.basename(r).lower() or "master" in os.path.basename(r).lower()), rasters[0] if rasters else None)


def find_year_folder(parent_dir, yr):
    """
    Dossier d'une année : (dossier, rasters) ou None. Candidats = dossiers dont le nom est exactement « <année> », « S_<année> », « Stack_<année> » (prioritaires), puis commençant par ces préfixes,
    puis contenant l'année. Le premier candidat qui CONTIENT un Stack est retenu : un dossier sans Stack (ex. « Bati_1999 ») ne masque plus le vrai dossier de l'année.
    """
    yr = str(yr)
    cands = []
    if not (parent_dir and os.path.isdir(parent_dir)):
        return None
    base_depth = os.path.normpath(parent_dir).count(os.sep)
    for root, dirs, _files in os.walk(parent_dir):
        dirs[:] = [d for d in dirs if not _skip_dir(d)]
        if os.path.normpath(root) == os.path.normpath(parent_dir):
            continue
        base = os.path.basename(root)
        if base in (yr, f"S_{yr}", f"Stack_{yr}"):
            pr = 0
        elif base.startswith((f"S_{yr}", f"Stack_{yr}", f"{yr}_")):
            pr = 1
        elif yr in base:
            pr = 2
        else:
            continue
        cands.append((pr, os.path.normpath(root).count(os.sep) - base_depth, root))
    for _pr, _depth, root in sorted(cands):
        rasters = list_stack_rasters(root)
        if rasters:
            return root, rasters
    return None


def year_folder_report(parent_dir):
    """
    Compte rendu des dossiers d'année (S_1999, 1999, Stack_1999, S_1999_xxx) : [{"folder", "year", "ok", "message"}]. Un dossier refusé dit POURQUOI (aucun raster, extensions acceptées, contenu vu) ;
    plusieurs dossiers pour la même année sont signalés (le premier est utilisé).
    """
    rows, by_year = [], {}
    if not (parent_dir and os.path.isdir(parent_dir)):
        return rows
    for root, dirs, _files in os.walk(parent_dir):
        dirs[:] = [d for d in dirs if not _skip_dir(d)]
        if os.path.normpath(root) == os.path.normpath(parent_dir):
            continue
        base = os.path.basename(root)
        m = _YEAR_FOLDER_RE.match(base)
        if not m:
            continue
        yr = m.group(1) or m.group(2)
        rasters = list_stack_rasters(root)
        if rasters:
            rows.append({"folder": root, "year": yr, "ok": True, "message": f"{base} : Stack = {os.path.basename(pick_stack(rasters))}"})
            by_year.setdefault(yr, []).append(root)
        else:
            try:
                seen = sorted(os.listdir(root))[:8]
            except OSError:
                seen = []
            rows.append({"folder": root, "year": yr, "ok": False,
                         "message": f"{base} : AUCUN raster ({', '.join(STACK_EXTS)}) dans ce dossier ni dans ses sous-dossiers directs ; contenu vu : {', '.join(seen) or 'vide'}"})
    for yr, folders in sorted(by_year.items()):
        if len(folders) > 1:
            rows.append({"folder": folders[0], "year": yr, "ok": False,
                         "message": f"{yr} : {len(folders)} dossiers contiennent un Stack ({', '.join(os.path.basename(f) for f in folders)}) : le premier est utilisé"})
    return rows


def _scan_available_years(parent_dir, years):
    """Années de `years` qui ont un dossier et un stack raster (même logique de détection que la boucle principale ; n'exige PAS le masque Built-up)."""
    return [yr for yr in years if find_year_folder(parent_dir, yr)]



def discover_years(parent_dir):
    """
    Années PRÉSENTES dans le dossier principal : un dossier nommé « S_1999 », « 1999 », « Stack_1999 » ou « S_1999_xxx » qui contient un Stack raster. Toute année ajoutée est donc prise en compte
    sans modifier le script. Les dossiers de résultats (Resultats_*) et les dossiers cachés sont ignorés. Retourne la liste triée (chaînes).
    """
    cands = set()
    if parent_dir and os.path.isdir(parent_dir):
        for root, dirs, _files in os.walk(parent_dir):
            dirs[:] = [d for d in dirs if not d.startswith((".", "Resultats_"))]
            for d in dirs:
                m = _YEAR_FOLDER_RE.match(d)
                if m:
                    cands.add(m.group(1) or m.group(2))
    return sorted(_scan_available_years(parent_dir, sorted(cands, key=int)), key=int) if cands else []


def register_years(years):
    """Ajoute des années à la liste globale TARGET_YEARS (modification SUR PLACE : toutes les fonctions la voient), triée ; idempotent. Retourne les années nouvellement ajoutées."""
    new = sorted({str(y) for y in years} - set(TARGET_YEARS), key=int)
    if new:
        TARGET_YEARS[:] = sorted(set(TARGET_YEARS) | set(new), key=int)
    return new


def _save_stage_mask_config(path, masks, priority):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"), "priority": bool(priority),
                       "masks": {str(int(c)): p for c, p in masks.items() if p}}, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        print(f"[Masques imposés] configuration non enregistrée : {exc}")


def _load_stage_mask_config(path):
    """{'masks': {code: chemin existant}, 'priority': bool} ou None."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        masks = {int(c): p for c, p in (data.get("masks") or {}).items() if p}
        return {"masks": masks, "priority": bool(data.get("priority", False))}
    except Exception:
        return None


class _YearChoiceDialog(QDialog):
    START_MAXIMIZED = False
    """Cases à cocher des années à traiter."""
    def __init__(self, years, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Années à traiter")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Cochez les années à traiter (au moins une) :"))
        self.checks = {}
        for y in years:
            cb = QCheckBox(str(y))
            cb.setChecked(True)
            lay.addWidget(cb)
            self.checks[str(y)] = cb
        row = QHBoxLayout()
        b_all, b_none = QPushButton("Tout cocher"), QPushButton("Tout décocher")
        b_all.clicked.connect(lambda *_: [c.setChecked(True) for c in self.checks.values()])
        b_none.clicked.connect(lambda *_: [c.setChecked(False) for c in self.checks.values()])
        row.addWidget(b_all)
        row.addWidget(b_none)
        lay.addLayout(row)
        row2 = QHBoxLayout()
        b_ok, b_cancel = QPushButton("OK"), QPushButton("Annuler")
        b_ok.clicked.connect(self.accept)
        b_cancel.clicked.connect(self.reject)
        row2.addWidget(b_ok)
        row2.addWidget(b_cancel)
        lay.addLayout(row2)

    def selected(self):
        return [y for y, cb in self.checks.items() if cb.isChecked()]


def _ask_year_mode():
    """Première question du script : une année, plusieurs années ou toutes."""
    items = ["1 – Une seule année", "2 – Plusieurs années (je choisis)", "3 – Toutes les années détectées (comportement habituel)"]
    choice, ok = QInputDialog.getItem(None, "Mode de traitement", "Que voulez-vous traiter ?", items, 2, False)
    if not ok:
        raise RuntimeError("Opération annulée.")
    return {"1": "one", "2": "several", "3": "all"}[choice[0]]


def _ask_years(available, mode):
    """Années à traiter selon le mode choisi. Mode « toutes » : la liste complète TARGET_YEARS (comportement historique)."""
    if mode == "all":
        return list(TARGET_YEARS)
    if mode == "one":
        y, ok = QInputDialog.getItem(None, "Année à traiter", "Choisissez l'année à traiter :", list(available), len(available) - 1, False)
        if not ok:
            raise RuntimeError("Opération annulée.")
        return [str(y)]
    while True:
        dlg = _YearChoiceDialog(available)
        res = show_dialog(dlg)
        sel = dlg.selected()
        del dlg
        if not res:
            raise RuntimeError("Opération annulée.")
        if sel:
            return [y for y in available if y in sel]
        QMessageBox.warning(None, "Années à traiter", "Cochez au moins une année.")


def _ask_stage_masks(parent_dir, output_dir, years):
    """
    Masques imposés par étape (facultatifs). Retourne ({code de classe: chemin}, priorité).
    Un nom finissant par une année (ex. Water_2015.shp) est un masque propre à cette année.
    """
    cfg_path = os.path.join(output_dir, STAGE_MASK_CONFIG)
    prev = _load_stage_mask_config(cfg_path)
    if prev:
        prev_ok = {c: p for c, p in prev["masks"].items() if os.path.exists(p) or _split_year_suffix(p, TARGET_YEARS)}
        if prev_ok:
            lines = "\n".join(f"• {CLASS_NAMES.get(c, c)} : {os.path.basename(p)}" for c, p in sorted(prev_ok.items()))
            r0 = QMessageBox.question(
                None, "Masques imposés — configuration précédente",
                "Une configuration de masques imposés a été trouvée :\n\n" + lines +
                f"\n\nMode : {'PRIORITAIRES' if prev['priority'] else 'à leur étape'}\n\nLa réutiliser ?",
                QMB_YES | QMB_NO, QMB_YES)
            if r0 == QMB_YES:
                return prev_ok, prev["priority"]
    r = QMessageBox.question(
        None, "Masques imposés par étape",
        "Voulez-vous fournir des masques IMPOSÉS pour certaines étapes (comme le masque stable Sebkha) ?\n\n"
        "Oui = une fenêtre par étape (Annuler dans une fenêtre = pas de masque pour cette étape).\n"
        "Non = classification inchangée.\n\n"
        "Une étape fournie par masque (Forest, Cropland, Rangeland, Fallow, Bareland) n'ouvre PAS de fenêtre de calibration.\n\n"
        "Astuce : un nom finissant par une année (Water_2015.shp) est un masque propre à cette année ;\n"
        "sinon le même masque s'applique à toutes les années traitées.",
        QMB_YES | QMB_NO, QMB_NO)
    if r != QMB_YES:
        return {}, False
    masks = {}
    for code, _key, label in STAGE_MASK_SPECS:
        res = QFileDialog.getOpenFileName(
            None, f"{label} — masque imposé de la classe « {CLASS_NAMES[code]} » (Annuler = aucun)", parent_dir,
            "Masques (*.shp *.gpkg *.geojson *.json *.tif *.tiff);;Tous (*)")
        path = res[0] if isinstance(res, (tuple, list)) else res
        if path:
            masks[code] = path
            kind = "propre à chaque année" if _split_year_suffix(path, TARGET_YEARS) else "identique pour toutes les années"
            print(f"[MASQUE IMPOSÉ] {CLASS_NAMES[code]} : {path} ({kind})")
    priority = False
    if masks:
        rp = QMessageBox.question(
            None, "Priorité des masques imposés",
            "Comment appliquer les masques imposés ?\n\n"
            "Oui = HIÉRARCHIE RESPECTÉE : Sebkha, Built-up et Water gardent la priorité ; les masques des autres classes sont appliqués juste après.\n"
            "Non = PRIORITAIRES : tous les masques appliqués dès le début, avant toute étape automatique.\n\n"
            "Dans les deux cas, une étape fournie par masque N'OUVRE PAS de fenêtre de calibration.",
            QMB_YES | QMB_NO, QMB_YES)
        priority = (rp == QMB_NO)
        _save_stage_mask_config(cfg_path, masks, priority)
        print(f"[MASQUE IMPOSÉ] mode : {'PRIORITAIRES' if priority else 'à leur étape'} | configuration enregistrée : {cfg_path}")
    return masks, priority


def _find_or_ask_input(parent_dir, stem, exts, what, expected_name):
    """Recherche automatique par nom exact ; sinon fenêtre de choix manuel (Annuler = arrêt avec le message d'origine)."""
    hit = _find_named_input(parent_dir, stem, exts)
    if hit:
        return hit
    msg = (f"{what} introuvable automatiquement (nom attendu : {expected_name}) dans :\n{parent_dir}\n\n"
           "Choisissez le fichier à la main dans la fenêtre suivante.")
    print("[MANUEL] " + msg.replace("\n", " "))
    QMessageBox.information(None, "Fichier introuvable", msg)
    flt = "Fichiers (" + " ".join("*" + e for e in exts) + ");;Tous (*)"
    while True:
        res = QFileDialog.getOpenFileName(None, f"{what} — choisir le fichier ({expected_name})", parent_dir, flt)
        path = res[0] if isinstance(res, (tuple, list)) else res
        if not path:
            raise RuntimeError(f"{what} introuvable automatiquement. Nom obligatoire : {expected_name} (aucun fichier choisi).")
        if os.path.exists(path) and os.path.splitext(path)[1].lower() in exts:
            print(f"[MANUEL] {what} : {path}")
            return path
        QMessageBox.warning(None, "Fichier invalide", f"Choisissez un fichier existant parmi : {', '.join(exts)}.")


# ====================== MASQUE D'ÉTAPE : SOURCE + RÔLE (AJOUT) ======================
# Dans la fenêtre de chaque étape (Forest ... Bareland) l'utilisateur peut choisir un masque :
#   source : shapefile / vecteur | raster (pixels != 0) | classe(s) d'un AUTRE raster (ex. classes 5,6 d'une carte LULC)
#   rôle   : TOTAL  = la classe EST le masque (seuils / RF ignorés)
#            LIMITE = la classe n'est cherchée qu'à l'INTÉRIEUR du masque (comme l'ancienne limite forestière)
# Le masque est enregistré dans le preset de l'étape et rejoué à l'identique en batch / reprise.
MASK_SOURCES = ["none", "vector", "raster", "raster_class", "anchor"]
MASK_SOURCE_LABELS = ["Aucun", "Shapefile / vecteur", "Raster (pixels ≠ 0)", "Classe(s) d'un autre raster", "⚓ Ancre : pixels spectralement STABLES (hérités)"]
MASK_ROLES = ["total", "boundary", "union"]
MASK_ROLE_LABELS = ["Masque TOTAL : la classe = le masque (seuils / RF ignorés)", "LIMITE : classer seulement à l'intérieur du masque",
                    "UNION : le masque est classé d'office ET le reste est classé par seuils / RF"]
try:
    from qgis.PyQt.QtWidgets import QSpinBox
except Exception:  # pragma: no cover
    QSpinBox = None
try:
    from qgis.PyQt.QtWidgets import QInputDialog
except Exception:  # pragma: no cover
    QInputDialog = None
try:
    from qgis.PyQt.QtWidgets import QTabWidget
except Exception:  # pragma: no cover
    QTabWidget = None


# ---------------- MASQUE n°2 : limiter ou exclure une zone (en plus du masque de l'étape) ----------------
MASK2_SOURCES = ["none", "vector", "raster", "raster_class"]
MASK2_SOURCE_LABELS = ["Aucun", "Shapefile / vecteur", "Raster (pixels ≠ 0)", "Classe(s) d'un raster"]
MASK2_ROLES = ["limit", "exclude"]
MASK2_ROLE_LABELS = ["LIMITER : classer seulement à l'intérieur de cette zone", "EXCLURE : ne pas classer dans cette zone"]


def build_mask2_spec(source_idx, path, classes_text, band, role_idx):
    """Spécification (dict JSON) du masque n°2 ; None si « Aucun »."""
    src = MASK2_SOURCES[int(source_idx)]
    if src == "none":
        return None
    path = str(path or "").strip()
    if not path:
        raise ValueError("Choisissez le fichier du masque n°2.")
    spec = {"source": src, "path": path, "band": max(1, int(band or 1)), "role": MASK2_ROLES[int(role_idx)]}
    if src == "raster_class":
        spec["classes"] = parse_class_values(classes_text)
        if not spec["classes"]:
            raise ValueError("Indiquez la ou les classes du raster pour le masque n°2 (ex. 5 ou 5,6).")
    return spec


def mask2_active(spec):
    """Vrai si la spécification d'étape porte un masque n°2."""
    m2 = spec.get("mask2") if isinstance(spec, dict) else None
    return bool(m2) and m2.get("source", "none") != "none"


def mask_spec_active(spec):
    """Vrai si l'étape a un masque (n°1 ou n°2) : sert au journal d'audit et aux messages."""
    if not isinstance(spec, dict):
        return bool(spec)
    return spec.get("source", "none") != "none" or mask2_active(spec)


def mask_info_active(info):
    return bool(info) and (info.get("source", "none") != "none" or bool(info.get("mask2")))


def restrict_domain_by_mask2(m2, active_mask, rows, cols, geo_tf, proj_wkt):
    """
    Applique le masque n°2 au DOMAINE de l'étape (avant le masque n°1) :
      LIMITER : domaine = domaine ET zone ; EXCLURE : domaine = domaine privé de la zone.
    Les pixels retirés restent non classés, donc disponibles pour les étapes suivantes. Retourne (nouveau domaine, informations).
    """
    mk = mask_from_spec(m2, rows, cols, geo_tf, proj_wkt)
    if mk is None:
        return active_mask, {"source": "none", "role": m2.get("role", "limit"), "mask_pixels": 0, "domain_before": int(np.count_nonzero(active_mask)), "domain_after": int(np.count_nonzero(active_mask))}
    role = m2.get("role", "limit")
    dom = (active_mask & mk) if role == "limit" else (active_mask & ~mk)
    return dom, {"source": m2.get("source"), "role": role, "mask_pixels": int(np.count_nonzero(mk)), "domain_before": int(np.count_nonzero(active_mask)), "domain_after": int(np.count_nonzero(dom))}


def describe_mask2(info2, pixel_area_ha=None):
    """Texte du masque n°2 : rôle, surface du masque, domaine de l'étape avant / après."""
    if not info2:
        return ""
    lab = dict(zip(MASK2_SOURCES, MASK2_SOURCE_LABELS)).get(info2.get("source"), info2.get("source"))
    role = "LIMITER (classement seulement à l'intérieur de cette zone)" if info2.get("role") == "limit" else "EXCLURE (aucun classement dans cette zone)"

    def px(n):
        return f"{n:,} px" + (f" = {n * pixel_area_ha:,.2f} ha" if pixel_area_ha else "")
    txt = (f"Masque n°2 : {lab} | {role} | SURFACE du masque : {px(info2.get('mask_pixels', 0))} ; domaine de l'étape : {px(info2.get('domain_before', 0))} → {px(info2.get('domain_after', 0))}.")
    if info2.get("domain_after", 0) == 0:
        txt += " ATTENTION : le masque n°2 vide tout le domaine de l'étape — vérifiez le CRS, l'emprise ou le rôle (limiter / exclure)."
    elif info2.get("role") == "limit" and info2.get("mask_pixels", 0) == 0:
        txt += " ATTENTION : masque vide."
    return txt


def _build_mask2_panel(owner):
    """Panneau « Masque n°2 » : source (shapefile / raster / classe(s) d'un raster), rôle (LIMITER / EXCLURE), bouton d'emprise. Les widgets deviennent des attributs de `owner`."""
    box = QGroupBox("Masque n°2 — LIMITER ou EXCLURE une zone (shapefile, raster ou classe(s) d'un raster)")
    v = QVBoxLayout(box)
    r1 = QHBoxLayout()
    r1.addWidget(QLabel("Source :"))
    owner.cb_mask2_source = QComboBox()
    owner.cb_mask2_source.addItems(MASK2_SOURCE_LABELS)
    owner.cb_mask2_source.currentIndexChanged.connect(owner.on_mask2_source_changed)
    r1.addWidget(owner.cb_mask2_source)
    v.addLayout(r1)
    r2 = QHBoxLayout()
    owner.le_mask2_path = QLineEdit("")
    owner.le_mask2_path.setPlaceholderText("Fichier du masque n°2…")
    owner.btn_mask2_browse = QPushButton("Parcourir...")
    owner.btn_mask2_browse.clicked.connect(owner.browse_mask2)
    r2.addWidget(owner.le_mask2_path)
    r2.addWidget(owner.btn_mask2_browse)
    v.addLayout(r2)
    r3 = QHBoxLayout()
    r3.addWidget(QLabel("Classe(s) du raster :"))
    owner.le_mask2_classes = QLineEdit("")
    owner.le_mask2_classes.setPlaceholderText("ex. 5  ou  5,6  ou  5-7")
    r3.addWidget(owner.le_mask2_classes)
    r3.addWidget(QLabel("Bande :"))
    owner.sb_mask2_band = QSpinBox()
    owner.sb_mask2_band.setRange(1, 99)
    owner.sb_mask2_band.setValue(1)
    r3.addWidget(owner.sb_mask2_band)
    v.addLayout(r3)
    r4 = QHBoxLayout()
    r4.addWidget(QLabel("Rôle :"))
    owner.cb_mask2_role = QComboBox()
    owner.cb_mask2_role.addItems(MASK2_ROLE_LABELS)
    owner.cb_mask2_role.currentIndexChanged.connect(owner.on_mask2_role_changed)
    r4.addWidget(owner.cb_mask2_role)
    v.addLayout(r4)
    owner.btn_mask2_show = QPushButton("👁 Afficher l'emprise du masque n°2 + sa surface (ha)")
    owner.btn_mask2_show.clicked.connect(owner.show_mask2_footprint)
    v.addWidget(owner.btn_mask2_show)
    owner.lbl_mask2_hint = QLabel("")
    owner.lbl_mask2_hint.setWordWrap(True)
    v.addWidget(owner.lbl_mask2_hint)
    owner.on_mask2_source_changed(0)
    return box


def _build_stage_mask_panel(owner, allowed_roles=None):
    """
    Panneau « Masque de l'étape » partagé par toutes les fenêtres d'étape : source (shapefile / raster / classe(s) d'un autre raster),
    rôle (TOTAL : la classe = le masque ; LIMITE : classer seulement à l'intérieur), et bouton « Afficher le masque + surface ».
    Crée les widgets comme attributs de `owner` et retourne le QGroupBox.
    """
    owner.allowed_roles = list(allowed_roles) if allowed_roles else [0, 1, 2]
    mask_box = QGroupBox("Masque de l'étape — shapefile, raster ou classe(s) d'un autre raster")
    mask_v = QVBoxLayout(mask_box)
    row1 = QHBoxLayout()
    row1.addWidget(QLabel("Source :"))
    owner.cb_mask_source = QComboBox()
    owner.cb_mask_source.addItems(MASK_SOURCE_LABELS)
    owner.cb_mask_source.currentIndexChanged.connect(owner.on_mask_source_changed)
    row1.addWidget(owner.cb_mask_source)
    mask_v.addLayout(row1)
    row2 = QHBoxLayout()
    owner.le_mask_path = QLineEdit("")
    owner.le_mask_path.setPlaceholderText("Fichier du masque…")
    owner.btn_mask_browse = QPushButton("Parcourir...")
    owner.btn_mask_browse.clicked.connect(owner.browse_mask)
    row2.addWidget(owner.le_mask_path)
    row2.addWidget(owner.btn_mask_browse)
    mask_v.addLayout(row2)
    row3 = QHBoxLayout()
    row3.addWidget(QLabel("Classe(s) du raster :"))
    owner.le_mask_classes = QLineEdit("")
    owner.le_mask_classes.setPlaceholderText("ex. 5  ou  5,6  ou  5-7")
    row3.addWidget(owner.le_mask_classes)
    row3.addWidget(QLabel("Bande :"))
    owner.sb_mask_band = QSpinBox()
    owner.sb_mask_band.setRange(1, 99)
    owner.sb_mask_band.setValue(1)
    row3.addWidget(owner.sb_mask_band)
    mask_v.addLayout(row3)
    row4 = QHBoxLayout()
    row4.addWidget(QLabel("Rôle :"))
    owner.cb_mask_role = QComboBox()
    owner.cb_mask_role.addItems(MASK_ROLE_LABELS)
    owner.cb_mask_role.setCurrentIndex(1 if 1 in owner.allowed_roles else owner.allowed_roles[-1])      # défaut : LIMITE si permis, sinon TOTAL
    owner.cb_mask_role.currentIndexChanged.connect(owner.on_mask_role_changed)
    row4.addWidget(owner.cb_mask_role)
    mask_v.addLayout(row4)
    row5 = QHBoxLayout()
    row5.addWidget(QLabel("⚓ Ancre — niveau de stabilité :"))
    owner.cb_anchor_level = QComboBox()
    owner.cb_anchor_level.addItems(ANCHOR_LEVEL_LABELS)
    row5.addWidget(owner.cb_anchor_level)
    mask_v.addLayout(row5)
    owner.btn_mask_show = QPushButton("👁 Afficher l'emprise du masque + sa surface (ha)")
    owner.btn_mask_show.clicked.connect(owner.show_mask_footprint)
    mask_v.addWidget(owner.btn_mask_show)
    owner.lbl_mask_hint = QLabel("")
    owner.lbl_mask_hint.setWordWrap(True)
    mask_v.addWidget(owner.lbl_mask_hint)
    owner.on_mask_source_changed(0)
    return mask_box


# ====================== FOND DE CARTE : STACK (FAUSSE COULEUR LIBRE) OU IMAGE HAUTE RÉSOLUTION (AJOUT) ======================
HR_VIEW_STATE = {"mode": "stack", "hr_path": None, "custom": None, "fast_dir": None}      # conservé d'une fenêtre d'étape à l'autre
COMP_ITEM_CUSTOM = "Personnalisée — choisir les bandes R / V / B…"
COMP_ITEM_HR = "Image haute résolution (fichier du disque)"
try:
    from qgis.core import QgsRectangle, QgsCoordinateReferenceSystem
except Exception:  # pragma: no cover
    QgsRectangle = QgsCoordinateReferenceSystem = None


def _rect_tuple(r):
    """(xmin, ymin, xmax, ymax) d'un QgsRectangle ou d'un tuple."""
    if isinstance(r, (tuple, list)):
        return tuple(float(v) for v in r)
    return (float(r.xMinimum()), float(r.yMinimum()), float(r.xMaximum()), float(r.yMaximum()))


def hr_overlap_fraction(study_rect, other_rect):
    """Part (0-1) de la zone d'étude couverte par l'image (deux rectangles dans le MÊME CRS)."""
    sx0, sy0, sx1, sy1 = _rect_tuple(study_rect)
    ox0, oy0, ox1, oy1 = _rect_tuple(other_rect)
    area = (sx1 - sx0) * (sy1 - sy0)
    if area <= 0:
        return 0.0
    ix = max(0.0, min(sx1, ox1) - max(sx0, ox0))
    iy = max(0.0, min(sy1, oy1) - max(sy0, oy0))
    return float(ix * iy / area)


def hr_needs_pyramids(width, height, size_mb, has_pyramids):
    """Image volumineuse SANS pyramides (aperçus) : l'affichage peut être très lent."""
    return (not has_pyramids) and (float(width) * float(height) >= 50e6 or float(size_mb) >= 300.0)


def hr_diagnostic_html(info):
    """Résumé lisible de l'image haute résolution affichée (CRS, taille, recouvrement, pyramides)."""
    rows = [f"<b>Image HR :</b> {os.path.basename(info.get('path', ''))}" + (" — <b>copie rapide</b> (tuilée + pyramides internes)" if info.get("fast") else ""),
            f"{info.get('width', '?')} × {info.get('height', '?')} px, {info.get('bands', '?')} bande(s), {info.get('size_mb', 0):,.0f} Mo",
            f"CRS : {info.get('authid') or 'inconnu'}" + (" — <b>absent : supposé identique au stack</b>" if info.get("assumed_crs") else "")]
    ov = info.get("overlap")
    if ov is None:
        rows.append("Recouvrement avec la zone d'étude : non calculable (reprojection impossible)")
    else:
        rows.append(f"Recouvrement avec la zone d'étude : <b>{ov * 100:.0f} %</b>" + (" — <b>partiel : la zone hors image reste vide</b>" if 0 < ov < 0.95 else ""))
    rows.append("Pyramides : " + ("oui" if info.get("pyramids") else "<b>non</b> (zoom lent sur une grande image : utilisez « ⚡ Zoom rapide »)"))
    return "<br>".join(rows)


def fast_hr_overview_levels(width, height, min_side=256):
    """Niveaux de pyramide 2, 4, 8 ... jusqu'à ce que le petit côté passe sous `min_side` px."""
    levels, f = [], 2
    while min(int(width), int(height)) // f >= min_side:
        levels.append(f)
        f *= 2
    return levels or [2]


def estimate_fast_copy_mb(width, height, bands, bytes_per_sample, with_overviews=True):
    """Taille d'une copie SANS compression (Mo). Les pyramides ajoutent 1/4 + 1/16 + ... = 1/3 de la taille de base."""
    base = float(width) * float(height) * float(bands) * float(bytes_per_sample)
    return base * (1.0 + (1.0 / 3.0 if with_overviews else 0.0)) / 1048576.0


def fast_copy_target(src_path, dst_dir):
    """Chemin déterministe de la copie rapide d'une image (réutilisée d'une fenêtre / d'un lancement à l'autre)."""
    stem = os.path.splitext(os.path.basename(src_path))[0]
    return os.path.join(dst_dir, f"{stem}__rapide.tif")


def is_fast_copy_fresh(src_path, dst_path):
    """La copie existe, n'est pas vide et n'est pas plus ancienne que l'original."""
    try:
        return os.path.exists(dst_path) and os.path.getsize(dst_path) > 0 and os.path.getmtime(dst_path) >= os.path.getmtime(src_path)
    except OSError:
        return False


def hr_source_info(path):
    """(largeur, hauteur, bandes, octets par échantillon) de l'image, ou None si GDAL ne peut pas la lire."""
    ds = gdal.Open(path, gdal.GA_ReadOnly)
    if ds is None:
        return None
    try:
        bps = max(1, int(gdal.GetDataTypeSize(ds.GetRasterBand(1).DataType)) // 8)
        return int(ds.RasterXSize), int(ds.RasterYSize), int(ds.RasterCount), bps
    finally:
        ds = None


def build_fast_hr_copy(src_path, dst_path, compress="NONE", progress=None):
    """
    Copie TUILÉE (blocs 512 x 512) + pyramides INTERNES : le zoom et le déplacement ne lisent que les blocs utiles, quelle que soit la taille.
    compress = "NONE" : le plus RAPIDE mais le plus gros (réglage par défaut) ; "LZW" : plus petit, un peu plus lent.
    L'original n'est jamais modifié. Écriture dans un fichier .part renommé à la fin (pas de fichier à moitié écrit).
    """
    info = hr_source_info(src_path)
    if info is None:
        raise RuntimeError(f"Image illisible par GDAL : {src_path}")
    w, h, nb, bps = info
    est_bytes = estimate_fast_copy_mb(w, h, nb, bps) * 1048576.0
    opts = ["TILED=YES", "BLOCKXSIZE=512", "BLOCKYSIZE=512", f"COMPRESS={compress}", "BIGTIFF=YES" if est_bytes > 3.5e9 else "BIGTIFF=IF_SAFER", "NUM_THREADS=ALL_CPUS"]
    os.makedirs(os.path.dirname(dst_path) or ".", exist_ok=True)
    part = dst_path + ".part"
    for stale in (part,):
        if os.path.exists(stale):
            os.remove(stale)
    gdal.SetConfigOption("GDAL_NUM_THREADS", "ALL_CPUS")
    try:
        ds = gdal.Translate(part, src_path, format="GTiff", creationOptions=opts, callback=progress)
        if ds is None:
            raise RuntimeError("La conversion de l'image a échoué (espace disque ? droits d'écriture ?).")
        gdal.SetConfigOption("COMPRESS_OVERVIEW", compress)
        gdal.SetConfigOption("GDAL_TIFF_OVR_BLOCKSIZE", "512")
        rc = ds.BuildOverviews("AVERAGE", fast_hr_overview_levels(w, h), callback=progress)
        ds.FlushCache()
        ds = None
        if rc != 0:
            raise RuntimeError("La construction des pyramides a échoué.")
        os.replace(part, dst_path)
    except Exception:
        if os.path.exists(part):
            try:
                os.remove(part)
            except OSError:
                pass
        raise
    finally:
        gdal.SetConfigOption("COMPRESS_OVERVIEW", None)
        gdal.SetConfigOption("GDAL_TIFF_OVR_BLOCKSIZE", None)
    return dst_path


def build_composite_pool(stack_bands, spectral_arrays):
    """Bandes proposées pour une fausse couleur libre : TOUTES les bandes du stack d'origine, puis les variables calculées (indices)."""
    pool = {}
    for k, v in (stack_bands or {}).items():
        if getattr(v, "ndim", 0) == 2:
            pool[f"[stack] {k}"] = v
    for k, v in (spectral_arrays or {}).items():
        if getattr(v, "ndim", 0) == 2:
            pool[f"[variable] {k}"] = v
    return pool


class CompositionPickerDialog(QDialog):
    START_MAXIMIZED = False
    """Choix des 3 bandes (Rouge, Vert, Bleu) d'une fausse couleur libre."""

    def __init__(self, labels, current=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fausse couleur personnalisée")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Choisissez les bandes affichées dans les canaux Rouge / Vert / Bleu\n(bandes du stack d'origine, puis variables calculées) :"))
        self.combos = []
        cur = list(current or [])
        for i, name in enumerate(("Rouge", "Vert", "Bleu")):
            row = QHBoxLayout()
            row.addWidget(QLabel(f"{name} :"))
            cb = QComboBox()
            cb.addItems(list(labels))
            if i < len(cur) and cur[i] in labels:
                cb.setCurrentIndex(list(labels).index(cur[i]))
            self.combos.append(cb)
            row.addWidget(cb)
            lay.addLayout(row)
        row = QHBoxLayout()
        b_ok = QPushButton("✔ Afficher")
        b_ok.clicked.connect(self.accept)
        b_no = QPushButton("Annuler")
        b_no.clicked.connect(self.reject)
        row.addWidget(b_no)
        row.addWidget(b_ok)
        lay.addLayout(row)

    def selection(self):
        return [cb.currentText() for cb in self.combos]


def parse_class_values(text):
    """« 5 », « 5,6 », « 5 6 », « 5-7 » -> liste triée d'entiers ; ValueError si vide ou invalide."""
    vals = set()
    for part in re.split(r"[;,\s]+", str(text or "").strip()):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)-(\d+)", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a > b or b - a > 255:
                raise ValueError(f"Intervalle de classes invalide : {part}")
            vals.update(range(a, b + 1))
        elif re.fullmatch(r"\d+", part):
            vals.add(int(part))
        else:
            raise ValueError(f"Valeur de classe invalide : « {part} » (attendu : entiers, ex. 5 ou 5,6 ou 5-7)")
    if not vals:
        raise ValueError("Indiquez au moins une classe (ex. 5 ou 5,6).")
    return sorted(vals)


def build_mask_spec(source_idx, path, classes_text, band, role_idx, level_idx=0):
    """Spécification (dict JSON) du masque d'une étape à partir des champs de la fenêtre."""
    src = MASK_SOURCES[int(source_idx)]
    if src == "none":
        return {"source": "none"}
    if src == "anchor":                        # l'ancre n'a pas de fichier : classes stables de l'année d'ancrage
        return {"source": "anchor", "role": MASK_ROLES[int(role_idx)] if MASK_ROLES[int(role_idx)] in ("total", "union") else "union", "level": int(level_idx) + 1}
    path = str(path or "").strip()
    if not path:
        raise ValueError("Choisissez le fichier du masque.")
    spec = {"source": src, "path": path, "band": max(1, int(band or 1)), "role": MASK_ROLES[int(role_idx)]}
    if src == "raster_class":
        spec["classes"] = parse_class_values(classes_text)
    return spec


def _read_raster_band_on_grid(path, band, rows, cols, geo_tf, proj_wkt):
    """Lit une bande sur la grille du stack (plus proche voisin si la grille diffère). Retourne (tableau float64, NoData)."""
    ds = gdal.Open(path, gdal.GA_ReadOnly)
    if ds is None or ds.RasterCount < int(band):
        return None, None
    b = ds.GetRasterBand(int(band))
    nodata = b.GetNoDataValue()
    same = (ds.RasterXSize == cols and ds.RasterYSize == rows
            and tuple(round(float(v), 6) for v in ds.GetGeoTransform()) == tuple(round(float(v), 6) for v in geo_tf))
    if same:
        return b.ReadAsArray().astype(np.float64), nodata
    mem = gdal.GetDriverByName("MEM").Create("", cols, rows, 1, gdal.GDT_Float32)
    mem.SetGeoTransform(geo_tf)
    if proj_wkt:
        mem.SetProjection(proj_wkt)
    nod = float(nodata) if nodata is not None else -9999.0
    mem.GetRasterBand(1).SetNoDataValue(nod)
    mem.GetRasterBand(1).Fill(nod)
    gdal.ReprojectImage(ds, mem, ds.GetProjection(), proj_wkt or ds.GetProjection(), gdal.GRA_NearestNeighbour)
    return mem.GetRasterBand(1).ReadAsArray().astype(np.float64), nod


def mask_from_spec(spec, rows, cols, geo_tf, proj_wkt, stage_class=None):
    """Masque booléen d'une spécification ; None si « Aucun ». Une simple chaîne = ancien comportement (polygone, rôle limite)."""
    if not spec:
        return None
    if isinstance(spec, str):
        spec = {"source": "vector", "path": spec, "role": "boundary"}
    src = spec.get("source", "none")
    if src == "none":
        return None
    if src == "anchor":
        if not ANCHOR_CTX.get("active") or not stage_class:
            raise RuntimeError("Ancre non disponible pour cette année (aucune ancre configurée, ou cette année EST l'ancre).")
        return anchor_inherit_mask(ANCHOR_CTX, stage_class, spec.get("level") or ANCHOR_CTX["min_level"])
    path = spec.get("path")
    if not path or not os.path.exists(path):
        raise RuntimeError(f"Masque d'étape introuvable : {path}")
    if src == "vector":
        return make_vector_mask(path, rows, cols, geo_tf, proj_wkt)
    arr, nodata = _read_raster_band_on_grid(path, spec.get("band", 1), rows, cols, geo_tf, proj_wkt)
    if arr is None:
        raise RuntimeError(f"Raster illisible ou bande absente : {path} (bande {spec.get('band', 1)})")
    if src == "raster":
        return _mask_from_array(arr, nodata)
    if src == "raster_class":
        cls = spec.get("classes") or []
        if not cls:
            raise RuntimeError("Aucune classe indiquée pour le masque « classe(s) d'un autre raster ».")
        ok_ = np.isfinite(arr) & np.isin(arr, cls)
        if nodata is not None and np.isfinite(nodata):
            ok_ &= (arr != nodata)
        return ok_
    raise RuntimeError(f"Source de masque inconnue : {src}")


def apply_stage_mask(spec, active_mask, rows, cols, geo_tf, proj_wkt, compute_fn, stage_class=None):
    """
    Applique les masques d'une étape. Le MASQUE n°2 (spec["mask2"], facultatif) restreint d'abord le domaine (LIMITER à une zone / EXCLURE une zone) ;
    le masque n°1 (source / rôle TOTAL, LIMITE, UNION, ancre) s'applique ensuite DANS ce domaine réduit : même un masque TOTAL ne classe rien dans une zone exclue.
    Retourne (pixels positifs, stats, domaine utilisé, informations dont info["mask2"]).
    """
    if mask2_active(spec):
        domain2, info2 = restrict_domain_by_mask2(spec["mask2"], active_mask, rows, cols, geo_tf, proj_wkt)
        c, qa, base, info = _apply_stage_mask_core(spec, domain2, rows, cols, geo_tf, proj_wkt, compute_fn, stage_class)
        info = dict(info)
        info["mask2"] = info2
        return c, qa, base, info
    return _apply_stage_mask_core(spec, active_mask, rows, cols, geo_tf, proj_wkt, compute_fn, stage_class)


def _apply_stage_mask_core(spec, active_mask, rows, cols, geo_tf, proj_wkt, compute_fn, stage_class=None):
    """
    Applique le masque n°1 d'une étape. compute_fn(base) -> (pixels positifs, stats QA).
      Aucun   : base = domaine actif.
      LIMITE  : base = domaine actif ET masque ; la classe est calculée (seuils / RF) à l'intérieur seulement.
      TOTAL   : la classe = domaine actif ET masque ; aucun seuil.
      UNION   : le masque est classé d'office ET le reste du domaine est classé par seuils / RF.
      ⚓ ANCRE : pixels stables de la classe = hérités (union) ; les pixels stables d'AUTRES classes sont exclus du seuillage (ils seront hérités par leur classe).
    Retourne (pixels positifs, stats, base, info).
    """
    if isinstance(spec, dict) and spec.get("source") == "anchor":
        if not ANCHOR_CTX.get("active") or not stage_class:
            # preset « ancre » rejoué sans ancre active (ancre en échec, reprise, année = ancre) : l'étape est classée SANS masque, avec avertissement
            print("    [Ancre] masque « ancre » ignoré : aucune ancre active pour cette année → étape classée sans masque (seuils / RF seuls).")
            c0, qa0 = compute_fn(active_mask)
            return c0, qa0, active_mask, {"source": "none", "role": "boundary", "mask_pixels": 0, "in_domain": 0}
        ml = spec.get("level") or ANCHOR_CTX["min_level"]
        all_inherit = anchor_inherit_mask(ANCHOR_CTX, stage_class, ml)
        inherit = all_inherit & active_mask
        other = anchor_other_stable_mask(ANCHOR_CTX, stage_class, ml) & active_mask
        arole = "total" if spec.get("role") == "total" else "union"
        ainfo = {"source": "anchor", "role": arole, "mask_pixels": int(all_inherit.sum()), "in_domain": int(inherit.sum()), "excluded_px": int(other.sum())}
        if arole == "total":
            return inherit, None, inherit, ainfo
        dom = active_mask & ~other
        c, qa = compute_fn(dom)
        return (c & dom) | inherit, qa, dom, ainfo
    mask = mask_from_spec(spec, rows, cols, geo_tf, proj_wkt, stage_class)
    role = (spec.get("role") if isinstance(spec, dict) else None) or "boundary"
    info = {"source": (spec.get("source") if isinstance(spec, dict) else ("vector" if spec else "none")) or "none", "role": role, "mask_pixels": 0, "in_domain": 0}
    if mask is None:
        info["source"] = "none"
        c, qa = compute_fn(active_mask)
        return c, qa, active_mask, info
    inside = mask & active_mask
    info["mask_pixels"], info["in_domain"] = int(np.count_nonzero(mask)), int(np.count_nonzero(inside))
    if role == "total":
        return inside, None, inside, info
    if role == "union":
        c, qa = compute_fn(active_mask)
        return c | inside, qa, active_mask, info
    c, qa = compute_fn(inside)
    return c, qa, inside, info


def describe_stage_mask(info, pixel_area_ha=None):
    """Texte des masques de l'étape : masque n°1 puis masque n°2 (s'il existe)."""
    if not info:
        return ""
    parts = [t for t in (_describe_main_mask(info, pixel_area_ha), describe_mask2(info.get("mask2"), pixel_area_ha)) if t]
    return " ".join(parts)


def _describe_main_mask(info, pixel_area_ha=None):
    """Texte du masque n°1 : source, rôle, pixels ET SURFACE en hectares (dans le masque et dans le domaine encore non classé)."""
    if not info or info.get("source", "none") == "none":
        return ""
    lab = dict(zip(MASK_SOURCES, MASK_SOURCE_LABELS)).get(info["source"], info["source"])
    role = {"total": "TOTAL (la classe = le masque)", "union": "UNION (le masque est classé d'office ET le reste par seuils / RF)"}.get(info["role"], "LIMITE (classement à l'intérieur du masque)")

    def px(n):
        return f"{n:,} px" + (f" = {n * pixel_area_ha:,.2f} ha" if pixel_area_ha else "")
    if info["source"] == "anchor":
        return (f"Masque d'étape : {lab} | rôle {role} | pixels stables de la classe dans l'ancre : {px(info['mask_pixels'])} ; hérités (encore non classés) : {px(info['in_domain'])} ; "
                f"stables d'AUTRES classes exclus du seuillage : {px(info.get('excluded_px', 0))}.")
    txt = (f"Masque d'étape : {lab} | rôle {role} | SURFACE du masque : {px(info['mask_pixels'])} ; "
           f"dans le domaine encore non classé : {px(info['in_domain'])}.")
    if info["in_domain"] == 0:
        txt += " ATTENTION : aucun pixel — vérifiez le CRS, l'emprise ou les classes."
    return txt


def mask_stage_px_ha(geo_tf):
    try:
        v = abs(geo_tf[1] * geo_tf[5] - geo_tf[2] * geo_tf[4]) / 10000.0
        return v if np.isfinite(v) and v > 0 else None
    except Exception:
        return None


# ====================== PREUVES SUPPLÉMENTAIRES : NDVI MULTI-ANNÉES, PRÉCIPITATIONS, MNT, CONTEXTE (AJOUT) ======================
# Séries annuelles (NDVI, précipitations) : (a) un raster PAR ANNÉE dans un dossier (l'année est dans le nom) ;
#                                           (b) UN STACK multi-bandes : une bande par année (ex. 41 bandes, 1985 -> 2025).
# cfg["years"] / cfg["rain_years"] = {année: chemin}  ou  {année: {"path": chemin, "band": n}}.
TEMPORAL_LOW_NDVI = 0.15           # NDVI annuel < 0.15 : « année basse » (modifiable)
RAIN_MIN_PAIRS = 10                # nombre minimal d'années (NDVI, pluie) pour calculer une corrélation
CONTEXT_RADIUS_M = 300.0           # rayon du voisinage pour la fraction de Cropland alentour


def parse_year_from_text(text):
    """Première année 19xx / 20xx isolée dans un texte (nom de fichier, description de bande) ; None sinon."""
    m = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", str(text or ""))
    return int(m.group(1)) if m else None


def years_from_band_descriptions(descs):
    """{bande (à partir de 1): année} si au moins 90 % des bandes portent une année et que les années sont uniques ; sinon None."""
    yrs = [parse_year_from_text(d) for d in (descs or [])]
    found = [y for y in yrs if y is not None]
    if not yrs or len(found) < 0.9 * len(yrs) or len(set(found)) != len(found):
        return None
    return {i + 1: y for i, y in enumerate(yrs) if y is not None}


def stack_band_years(nb, first_year):
    """Bandes annuelles consécutives : bande 1 = first_year."""
    return {i: int(first_year) + i - 1 for i in range(1, int(nb) + 1)}


def read_stack_band_descriptions(path):
    """Descriptions (noms) des bandes d'un raster multi-bandes ; liste vide si illisible."""
    ds = gdal.Open(path, gdal.GA_ReadOnly)
    if ds is None:
        return []
    try:
        return [str(ds.GetRasterBand(i).GetDescription() or "") for i in range(1, int(ds.RasterCount) + 1)]
    finally:
        ds = None


def scan_temporal_ndvi_folder(folder, prefer=("ndvi",)):
    """Cherche un raster par année dans un dossier (l'année est dans le nom : NDVI_1985.tif ...). Retourne {année: chemin}."""
    exts = (".tif", ".tiff", ".img", ".vrt")
    found = {}
    for root, _d, files in os.walk(folder):
        for fn in sorted(files):
            if os.path.splitext(fn)[1].lower() not in exts:
                continue
            yr_ = parse_year_from_text(fn)
            if yr_ is None:
                continue
            full = os.path.join(root, fn)
            score = (0 if any(p in fn.lower() for p in prefer) else 1, len(full))      # on préfère un nom contenant le mot attendu
            if yr_ not in found or score < found[yr_][0]:
                found[yr_] = (score, full)
    return {y: v[1] for y, v in sorted(found.items())}


def _year_specs(cfg, key="years"):
    """{année: (chemin, bande)} triée, pour les deux formes de configuration."""
    out = {}
    for y, v in (cfg.get(key) or {}).items():
        out[int(y)] = (v["path"], int(v.get("band", 1) or 1)) if isinstance(v, dict) else (v, 1)
    return dict(sorted(out.items()))


def _load_ndvi_band(cfg, path, band, rows, cols, geo_tf, proj_wkt):
    """Une bande NDVI sur la grille du stack : float32, NoData -> NaN, NDVI x10000 détecté et remis à l'échelle."""
    arr, nod = _read_raster_band_on_grid(path, int(band), rows, cols, geo_tf, proj_wkt)
    if arr is None:
        raise RuntimeError(f"Raster NDVI illisible : {path} (bande {band})")
    a = np.asarray(arr, dtype=np.float32).copy()
    if nod is not None and np.isfinite(nod):
        a[a == nod] = np.nan
    a[~np.isfinite(a)] = np.nan
    if np.any(np.isfinite(a)) and float(np.nanmax(np.abs(a))) > 2.0:
        a = a / 10000.0                                                    # NDVI mis à l'échelle (x10000)
        warned = cfg.setdefault("_cache", {}).setdefault("scaled_warned", set())
        if path not in warned:
            warned.add(path)
            print(f"    [Preuve temporelle] {os.path.basename(path)} : NDVI divisé par 10000 (valeurs > 2 détectées).")
    a[(a < -1.0) | (a > 1.0)] = np.nan
    return a


def _load_rain_band(cfg, path, band, rows, cols, geo_tf, proj_wkt):
    """Une bande de précipitations (mm) sur la grille du stack : float32, NoData et valeurs négatives -> NaN."""
    arr, nod = _read_raster_band_on_grid(path, int(band), rows, cols, geo_tf, proj_wkt)
    if arr is None:
        raise RuntimeError(f"Raster de précipitations illisible : {path} (bande {band})")
    a = np.asarray(arr, dtype=np.float32).copy()
    if nod is not None and np.isfinite(nod):
        a[a == nod] = np.nan
    a[~np.isfinite(a)] = np.nan
    a[a < 0] = np.nan
    return a


def _temporal_summary(cfg, rows, cols, geo_tf, proj_wkt):
    """
    UN SEUL passage sur toutes les années (chaque bande lue une fois, jamais empilées : 41 bandes ne tiennent pas en mémoire d'un coup).
    Retient par pixel : les 2 NDVI les plus élevés et l'année du maximum, le minimum, la somme et la somme des carrés, le nombre d'années
    actives / basses / valides et, si des précipitations sont données, les sommes nécessaires à la corrélation NDVI-pluie.
    Le « maximum des AUTRES années » d'une année donnée s'en déduit sans relire la série : max global si l'année n'est pas le maximum, sinon le 2e.
    """
    cache = cfg.setdefault("_cache", {})
    rain_specs = _year_specs(cfg, "rain_years")
    key = ("summary", rows, cols, tuple(float(v) for v in geo_tf), bool(rain_specs))
    if key in cache:
        return cache[key]
    specs = _year_specs(cfg)
    years = list(specs)
    neg, pos = np.float32(-np.inf), np.float32(np.inf)
    shp = (rows, cols)
    top1, top2 = np.full(shp, neg, np.float32), np.full(shp, neg, np.float32)
    arg = np.full(shp, -1, np.int16)
    gmin = np.full(shp, pos, np.float32)
    s1, s2 = np.zeros(shp, np.float32), np.zeros(shp, np.float32)
    active, nlow, nvalid = (np.zeros(shp, np.int16) for _ in range(3))
    if rain_specs:
        n_p = np.zeros(shp, np.int16)
        sx, sy, sxy, sxx, syy = (np.zeros(shp, np.float32) for _ in range(5))
        rc = rs = None                              # centrage / échelle de la pluie : valeurs ~1, pas d'annulation catastrophique en float32
    for idx, y in enumerate(years):
        progress_tick(idx, len(years), f"NDVI {y} ({idx + 1} / {len(years)})" + (" + pluie" if rain_specs and y in rain_specs else ""))
        path, band = specs[y]
        a = _load_ndvi_band(cfg, path, band, rows, cols, geo_tf, proj_wkt)
        with np.errstate(invalid="ignore"):
            valid = np.isfinite(a)
            af = np.where(valid, a, neg)
            better = af > top1
            top2 = np.where(better, top1, np.maximum(top2, af))
            arg = np.where(better, np.int16(idx), arg)
            top1 = np.where(better, af, top1)
            gmin = np.minimum(gmin, np.where(valid, a, pos))
            s1 += np.where(valid, a, 0).astype(np.float32)
            s2 += np.where(valid, a * a, 0).astype(np.float32)
            active += (af >= TEMPORAL_ACTIVE_NDVI)
            nlow += (valid & (a < TEMPORAL_LOW_NDVI))
            nvalid += valid
            if rain_specs and y in rain_specs:
                r = _load_rain_band(cfg, rain_specs[y][0], rain_specs[y][1], rows, cols, geo_tf, proj_wkt)
                if rc is None and np.any(np.isfinite(r)):
                    rc, rs = float(np.nanmean(r)), (float(np.nanstd(r)) or 1.0)
                if rc is not None:
                    pv = valid & np.isfinite(r)
                    xs = np.where(pv, a - 0.3, 0).astype(np.float32)
                    ys = np.where(pv, (r - rc) / rs, 0).astype(np.float32)
                    n_p += pv
                    sx += xs
                    sy += ys
                    sxy += xs * ys
                    sxx += xs * xs
                    syy += ys * ys
    out = {"years": years, "top1": top1, "top2": top2, "arg": arg, "gmin": gmin, "active": active, "nvalid": nvalid, "s1": s1, "s2": s2, "nlow": nlow}
    if rain_specs:
        out.update({"n_p": n_p, "sx": sx, "sy": sy, "sxy": sxy, "sxx": sxx, "syy": syy})
    cache[key] = out
    return out


def temporal_ndvi_features(cfg, year, rows, cols, geo_tf, proj_wkt):
    """
    Variables de preuve temporelle pour `year`, sur la grille du stack :
      ndvi_other_max         : NDVI maximal des AUTRES années (une année sèche comme 2000 ne l'affecte pas : c'est un maximum)
      ndvi_other_active_n    : nombre d'AUTRES années où NDVI >= TEMPORAL_ACTIVE_NDVI
      ndvi_interannual_range : amplitude interannuelle (max - min) sur toutes les années disponibles
      ndvi_all_mean / ndvi_all_std : moyenne et écart-type du NDVI sur toutes les années
      ndvi_low_frac / ndvi_high_frac : part des années « basses » (< TEMPORAL_LOW_NDVI) / « actives » (>= TEMPORAL_ACTIVE_NDVI)
      ndvi_bimodality        : 4 x part basse x part haute (0 -> 1) : fort pour une JACHÈRE (années basses ET hautes), faible pour un sol nu
                               permanent (toujours bas), une culture ou une forêt (toujours hautes), un parcours stable (toujours moyen)
      ndvi_rain_corr         : corrélation NDVI - précipitations sur les années (si un raster de précipitations est configuré) : forte pour un
                               PARCOURS (NDVI suit la pluie), faible pour une parcelle gérée (jachère, culture) ou un sol nu
      lpd_class              : classe LPD (preuve secondaire) si un raster LPD est configuré
    """
    year_i = int(year)
    specs = _year_specs(cfg)
    if not [y for y in specs if y != year_i]:
        raise RuntimeError(f"Aucune autre année que {year_i} dans la série NDVI annuelle.")
    sm = _temporal_summary(cfg, rows, cols, geo_tf, proj_wkt)
    if year_i in sm["years"]:
        cache = cfg.setdefault("_cache", {})
        ykey = ("year", year_i, rows, cols)
        if ykey not in cache:
            path, band = specs[year_i]
            cache[ykey] = _load_ndvi_band(cfg, path, band, rows, cols, geo_tf, proj_wkt)
        ay = cache[ykey]
        valid_y = np.isfinite(ay)
        idx = sm["years"].index(year_i)
        other_max = np.where(sm["arg"] == idx, sm["top2"], sm["top1"])
        with np.errstate(invalid="ignore"):
            other_active = sm["active"] - (valid_y & (ay >= TEMPORAL_ACTIVE_NDVI)).astype(np.int16)
        other_valid = sm["nvalid"] - valid_y.astype(np.int16)
    else:
        other_max, other_active, other_valid = sm["top1"], sm["active"], sm["nvalid"]
    has_other = other_valid > 0
    nv = sm["nvalid"].astype(np.float32)
    ok_n = nv > 0
    safe_n = np.maximum(nv, 1.0)
    mean = np.where(ok_n, sm["s1"] / safe_n, np.nan).astype(np.float32)
    var = np.where(ok_n, sm["s2"] / safe_n - mean * mean, np.nan)
    low_frac = np.where(ok_n, sm["nlow"] / safe_n, np.nan).astype(np.float32)
    high_frac = np.where(ok_n, sm["active"] / safe_n, np.nan).astype(np.float32)
    out = {
        "ndvi_other_max": np.where(has_other, other_max, np.nan).astype(np.float32),
        "ndvi_other_active_n": np.where(has_other, other_active, np.nan).astype(np.float32),
        "ndvi_interannual_range": np.where(sm["nvalid"] >= 2, sm["top1"] - sm["gmin"], np.nan).astype(np.float32),
        "ndvi_all_mean": mean,
        "ndvi_all_std": np.sqrt(np.maximum(var, 0.0)).astype(np.float32),
        "ndvi_low_frac": low_frac,
        "ndvi_high_frac": high_frac,
        "ndvi_bimodality": (4.0 * low_frac * high_frac).astype(np.float32),
    }
    if "n_p" in sm:
        n = sm["n_p"].astype(np.float32)
        varx, vary = n * sm["sxx"] - sm["sx"] ** 2, n * sm["syy"] - sm["sy"] ** 2
        good = (n >= RAIN_MIN_PAIRS) & (varx > 1e-4 * n * n) & (vary > 1e-3 * n * n)       # variance du NDVI > 1e-4 (écart-type 0.01)
        corr = (n * sm["sxy"] - sm["sx"] * sm["sy"]) / np.sqrt(np.maximum(varx * vary, 1e-30))
        out["ndvi_rain_corr"] = np.where(good, np.clip(corr, -1.0, 1.0), np.nan).astype(np.float32)
    lpd_path = cfg.get("lpd_path")
    if lpd_path:
        arr, nod = _read_raster_band_on_grid(lpd_path, int(cfg.get("lpd_band", 1) or 1), rows, cols, geo_tf, proj_wkt)
        if arr is not None:
            lp = np.asarray(arr, dtype=np.float32).copy()
            if nod is not None and np.isfinite(nod):
                lp[lp == nod] = np.nan
            lp[~np.isfinite(lp)] = np.nan
            out["lpd_class"] = lp
    return out


def terrain_features(cfg, rows, cols, geo_tf, proj_wkt):
    """Altitude et pente (degrés) du MNT, sur la grille du stack. Le sol nu / la roche dominent les pentes, la jachère les plaines."""
    cache = cfg.setdefault("_cache", {})
    key = ("terrain", rows, cols, tuple(float(v) for v in geo_tf))
    if key in cache:
        return cache[key]
    arr, nod = _read_raster_band_on_grid(cfg["dem_path"], int(cfg.get("dem_band", 1) or 1), rows, cols, geo_tf, proj_wkt)
    if arr is None:
        raise RuntimeError(f"MNT illisible : {cfg['dem_path']}")
    z = np.asarray(arr, dtype=np.float32).copy()
    if nod is not None and np.isfinite(nod):
        z[z == nod] = np.nan
    z[~np.isfinite(z)] = np.nan
    z[z < -500] = np.nan                                   # valeurs sentinelles (-9999, -32768 ...)
    px, py = abs(float(geo_tf[1])), abs(float(geo_tf[5]))
    if px < 1.0 or py < 1.0:
        print("    [MNT] taille de pixel < 1 unité de carte : le CRS du stack est-il en degrés ? la pente ne serait pas fiable.")
    with np.errstate(invalid="ignore"):
        gy, gx = np.gradient(z, py, px)
        slope = np.degrees(np.arctan(np.hypot(gx, gy))).astype(np.float32)
    cache[key] = {"terrain_elevation": z, "terrain_slope_deg": slope}
    return cache[key]


def crop_context_feature(lulc, admin_mask, geo_tf, radius_m=CONTEXT_RADIUS_M):
    """Fraction de Cropland (classe 5) dans le voisinage carré (rayon `radius_m`), rapportée à la surface d'étude du voisinage.
    Une jachère est entourée de champs ; un parcours ou un sol nu forment de grandes surfaces sans champs."""
    px = abs(float(geo_tf[1])) or 30.0
    size = 2 * max(1, int(round(float(radius_m) / px))) + 1
    num = uniform_filter((lulc == 5).astype(np.float32), size=size, mode="constant", cval=0.0)
    den = uniform_filter(np.asarray(admin_mask, dtype=np.float32), size=size, mode="constant", cval=0.0)
    return np.clip(np.where(den > 1e-6, num / np.maximum(den, 1e-6), 0.0), 0.0, 1.0).astype(np.float32)


def _years_from_stack_file(path, what="NDVI"):
    """Stack multi-bandes -> {année: {"path", "band"}} : années lues dans les noms des bandes, sinon demandées (bandes annuelles consécutives)."""
    descs = read_stack_band_descriptions(path)
    if not descs:
        QMessageBox.warning(None, "Preuves supplémentaires", f"Raster illisible ou sans bande :\n{path}")
        return None
    nb = len(descs)
    mapping = years_from_band_descriptions(descs)
    origin = "lues dans les noms des bandes"
    if mapping is None:
        default = max(int(y) for y in TARGET_YEARS) - nb + 1
        first, ok_ = QInputDialog.getInt(
            None, "Année de la 1re bande",
            f"Ce stack ({what}) a {nb} bandes, sans année lisible dans leurs noms.\nQuelle est l'année de la BANDE 1 ?\n"
            f"(les bandes sont supposées annuelles et consécutives : bande {nb} = année de la bande 1 + {nb - 1})",
            default, 1950, 2100)
        if not ok_:
            return None
        mapping = stack_band_years(nb, first)
        origin = f"supposées consécutives à partir de {first}"
    ys = sorted(mapping.values())
    rep_ = QMessageBox.question(
        None, "Preuves supplémentaires",
        f"{what} : {len(mapping)} bandes sur {nb} → années {ys[0]} … {ys[-1]} ({origin}).\n\nCes années sont-elles correctes ?\n"
        f"« Année active » = NDVI ≥ {TEMPORAL_ACTIVE_NDVI} ; « année basse » = NDVI < {TEMPORAL_LOW_NDVI}.\n\nOui = utiliser ce stack.\nNon = annuler.", QMB_YES | QMB_NO, QMB_YES)
    if rep_ != QMB_YES:
        return None
    return {y: {"path": path, "band": b} for b, y in sorted(mapping.items())}


def _pick_series(what, prefer, start_dir):
    """Série annuelle : stack multi-bandes (une bande par année) OU dossier de rasters (un par année). Retourne ({année: spec}, infos) ou (None, None)."""
    f, _ = QFileDialog.getOpenFileName(None, f"{what} : stack multi-bandes (une bande par année) — Annuler pour choisir un dossier de rasters annuels",
                                       start_dir, "Raster (*.tif *.tiff *.img *.vrt);;Tous (*)")
    if f:
        years = _years_from_stack_file(f, what)
        return ({str(y): v for y, v in years.items()}, {"stack": f}) if years else (None, None)
    folder = QFileDialog.getExistingDirectory(None, f"{what} : dossier de rasters annuels (un par année) — Annuler = sans {what}", start_dir)
    if not folder:
        return None, None
    found = scan_temporal_ndvi_folder(folder, prefer)
    if len(found) < 2:
        QMessageBox.warning(None, "Preuves supplémentaires",
                            f"Au moins 2 rasters avec une année dans le nom sont nécessaires.\nTrouvés : {len(found)} dans\n{folder}\n\n"
                            "Si vos données sont dans UN SEUL fichier multi-bandes (une bande par année), choisissez ce fichier à la fenêtre précédente.")
        return None, None
    lines = "\n".join(f"  {y} : {os.path.basename(p)}" for y, p in found.items())
    QMessageBox.information(None, "Preuves supplémentaires", f"{what} : {len(found)} années trouvées :\n{lines}\n\n« Année active » = NDVI ≥ {TEMPORAL_ACTIVE_NDVI}.")
    return {str(y): p for y, p in found.items()}, {"folder": folder}


def describe_evidence_cfg(cfg):
    """Résumé d'une configuration de preuves (pour les messages et le journal)."""
    if not cfg:
        return "non utilisée"
    parts = []
    if cfg.get("years"):
        parts.append(f"{len(cfg['years'])} années NDVI")
    if cfg.get("rain_years"):
        parts.append(f"{len(cfg['rain_years'])} années de précipitations")
    if cfg.get("dem_path"):
        parts.append("MNT")
    if cfg.get("lpd_path"):
        parts.append("LPD")
    return " + ".join(parts) or "vide"


def _ask_temporal_evidence(output_dir, start_dir=None, enabled=None):
    """
    Preuves supplémentaires (NDVI multi-années, précipitations, MNT, LPD) pour séparer Fallow / Rangeland / Bareland.
    enabled = None : pose la question oui / non (ancien comportement) ; False : aucune preuve ; True : choix déjà fait dans la fenêtre de démarrage -> demande directement les fichiers.
    """
    if enabled is False:
        return None
    cfg_path = os.path.join(output_dir, "Temporal_Evidence_Config.json")
    if os.path.exists(cfg_path):
        try:
            cfg = json.load(open(cfg_path, encoding="utf-8"))
            if cfg.get("years") or cfg.get("dem_path"):
                rep_ = QMessageBox.question(
                    None, "Preuves supplémentaires",
                    f"Une configuration existe : {describe_evidence_cfg(cfg)}.\n\nOui = la réutiliser.\nNon = choisir à nouveau.", QMB_YES | QMB_NO, QMB_YES)
                if rep_ == QMB_YES:
                    return cfg
        except Exception:
            pass
    rep_ = QMB_YES if enabled is True else QMessageBox.question(
        None, "Preuves supplémentaires (Fallow / Rangeland / Bareland)",
        "Utiliser des PREUVES SUPPLÉMENTAIRES pour séparer Fallow, Rangeland et Bareland ?\n\n"
        "• NDVI de plusieurs années : UN STACK multi-bandes (une bande par année, ex. 41 bandes 1985-2025) OU un dossier de rasters (un par année). "
        "Idéalement le NDVI MAXIMAL saisonnier.\n"
        "• Précipitations annuelles (CHIRPS, une bande par année) : le NDVI d'un parcours suit la pluie, pas celui d'une jachère ni d'un sol nu\n"
        "• MNT (altitude → pente)\n• LPD (facultatif) comme preuve SECONDAIRE\n\n"
        "Les fenêtres Fallow, Rangeland et Bareland proposent alors des champs « Temp_ », « Terr_ » (vides = non utilisés).\n\n"
        "Oui = choisir les données.\nNon = classification inchangée.", QMB_YES | QMB_NO, QMB_NO)
    if rep_ != QMB_YES:
        return None
    cfg = {"years": {}, "lpd_path": None, "lpd_band": 1}
    base_dir = start_dir or output_dir
    years, info = _pick_series("NDVI", ("ndvi",), base_dir)
    if years:
        cfg["years"] = years
        cfg.update(info)
        if QMessageBox.question(None, "Précipitations", "Ajouter les PRÉCIPITATIONS annuelles (une valeur par année, ex. cumul saisonnier CHIRPS en mm) ?\n"
                                "Elles permettent de mesurer si le NDVI SUIT la pluie (parcours) ou non (jachère, sol nu).", QMB_YES | QMB_NO, QMB_NO) == QMB_YES:
            rain, rinfo = _pick_series("Précipitations", ("chirps", "rain", "precip", "pluie", "pr_"), base_dir)
            if rain:
                cfg["rain_years"] = rain
                cfg.update({"rain_" + k: v for k, v in rinfo.items()})
        if QMessageBox.question(None, "Preuves supplémentaires", "Ajouter un raster LPD comme preuve SECONDAIRE ?\n(jamais « LPD > seuil ⇒ Fallow » : la LPD mesure la dynamique de productivité, pas le type de couverture)",
                                QMB_YES | QMB_NO, QMB_NO) == QMB_YES:
            f2, _ = QFileDialog.getOpenFileName(None, "Raster LPD", base_dir, "Raster (*.tif *.tiff *.img *.vrt);;Tous (*)")
            if f2:
                cfg["lpd_path"] = f2
    if QMessageBox.question(None, "MNT", "Ajouter un MNT (altitude) ?\nLa pente aide à séparer la roche / le sol nu (versants) de la jachère (plaines).", QMB_YES | QMB_NO, QMB_NO) == QMB_YES:
        f3, _ = QFileDialog.getOpenFileName(None, "MNT (altitude en mètres)", base_dir, "Raster (*.tif *.tiff *.img *.vrt);;Tous (*)")
        if f3:
            cfg["dem_path"] = f3
    if not cfg["years"] and not cfg.get("dem_path"):
        return None
    try:
        json.dump({k: v for k, v in cfg.items() if not k.startswith("_")}, open(cfg_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    except Exception as exc:
        print(f"[Preuves supplémentaires] configuration non enregistrée : {exc}")
    return cfg


# ====================== ANALYSE DU CHANGEMENT : NET ≠ ÉCHANGE (Pontius), STABILITÉ, PERTE, GAIN (AJOUT) ======================
# À partir de la 2e année : la carte en cours est comparée à la carte de l'année PRÉCÉDENTE (LULC_<AREA_TAG>_<année>.tif du dossier de résultats).
# Dans chaque fenêtre d'étape, le bouton « 📊 Changement » ouvre le tableau (classe de l'étape, toutes les classes, transitions) et la carte interactive.
# Un changement BRUT se décompose en NET (variation de quantité) + ÉCHANGE (swap : ce que A perd au profit de B, B le perd au profit de A)
# + DÉPLACEMENT (shift, rotations entre 3 classes ou plus) : seule la part NETTE est une vraie évolution de quantité ; l'échange et le déplacement
# sont du « bruit spatial » probable (seuils différents entre les deux années) ou des rotations (jachères).
CHANGE_CLASSES = sorted(CLASS_NAMES)                  # 8 classes (Forest et l'ancien Matorral sont fusionnés)
# Transitions IMPROBABLES (échelle de quelques années à quelques décennies) : si elles pèsent beaucoup, un seuil d'UNE des deux années est suspect.
# Liste MODIFIABLE : c'est une décision du thématicien (ajoutez / retirez des couples (de, vers)).
IMPLAUSIBLE_TRANSITIONS = {
    (1, 5), (1, 6), (1, 7), (1, 8),                              # Built-up -> champs / forêt / parcours
    (3, 1), (3, 5), (3, 6), (3, 7), (3, 8),                      # Sebkha (forme stable) -> bâti / champs / végétation
    (4, 7),                                                      # Sol nu / roche -> FORÊT (ex. 25 % de la roche devenue forêt en 5 ans)
    (2, 7),                                                      # Eau -> forêt
    (7, 2), (7, 3),                                              # Forêt -> eau / sebkha
    (8, 2), (8, 3),                                              # Parcours -> eau / sebkha
}
ALERT_SHARE_PREV = 0.05          # une transition improbable pesant >= 5 % de la classe PRÉCÉDENTE ...
ALERT_SHARE_CUR = 0.10           # ... ou >= 10 % de la classe ACTUELLE est signalée
ALERT_MIN_HA = 100.0             # (en dessous de cette surface : bruit, pas d'alerte)
ALERT_RED_SHARE = 0.20           # >= 20 % : alerte rouge
EXPECTED_MIN_STABILITY = {1: 0.85, 3: 0.80, 7: 0.75}      # classes qui doivent rester stables : Built-up, Sebkha, Forest
CHANGE_MAP_COLORS = {
    1: ("Persistance (même classe aux 2 dates)", (46, 160, 67, 150)),
    2: ("Gain (devient cette classe)", (30, 100, 230, 210)),
    3: ("Perte (devient une autre classe)", (220, 40, 40, 220)),
    4: ("Perte probable / en attente (pas encore classé)", (255, 150, 0, 200)),
    6: ("Transition choisie dans le tableau", (255, 235, 0, 255)),
}
CHANGE_MAP_MODES = [("none", "Aucune"), ("origin", "Origine des pixels de la classe : stable (vert) / couleur de la classe précédente"),
                    ("class", "Classe de l'étape : persistance / gain / perte"),
                    ("stability", "Toutes les classes : stable / changé"), ("transition", "Transition choisie dans le tableau")]


def change_matrix(prev, cur, domain=None):
    """
    Matrice M[i-1, j] en PIXELS : i = classe de l'année précédente (1..9), j = classe actuelle (0..9 ; 0 = pas encore classé / hors classes).
    Seuls les pixels classés l'année précédente (et dans `domain`) sont comptés.
    """
    prev, cur = np.asarray(prev), np.asarray(cur)
    valid = (prev >= 1) & (prev <= 9)
    if domain is not None:
        valid &= np.asarray(domain, dtype=bool)
    p = prev[valid].astype(np.int64)
    c = cur[valid].astype(np.int64)
    c = np.where((c >= 0) & (c <= 9), c, 0)
    return np.bincount(p * 10 + c, minlength=100).reshape(10, 10)[1:, :].astype(np.int64)


def class_change_rows(M, px_ha, reverse=False):
    """
    Une ligne par classe : surfaces (ha), persistance, perte CERTAINE, perte / gain EN ATTENTE (pas encore classé à cette étape), gain, net, échange (swap), brut, stabilité (%), couverture (%).
    Toujours en sens CHRONOLOGIQUE : « préc. » = l'année la plus ANCIENNE, « actuel » = la plus RÉCENTE.
      reverse = False : la référence (lignes de M) est l'année la plus ancienne, la carte en cours (colonnes) la plus récente ; l'attente concerne la perte.
      reverse = True  : la référence (lignes) est plus RÉCENTE, la carte en cours (colonnes) est plus ancienne ; l'attente concerne le gain.
    Brut = Net + Échange.
    """
    rows = []
    for k in CHANGE_CLASSES:
        if not reverse:
            a1, a2, pers, pend = int(M[k - 1].sum()), int(M[:, k].sum()), int(M[k - 1, k]), int(M[k - 1, 0])
            classified = a1 - pend
            loss, gain = classified - pers, a2 - pers
            stab_den, cov = classified, ((classified / a1) if a1 else float("nan"))
        else:
            a1, a2, pers, pend = int(M[:, k].sum()), int(M[k - 1].sum()), int(M[k - 1, k]), int(M[k - 1, 0])
            loss, gain = a1 - pers, a2 - pers - pend
            stab_den, cov = a1, (((a2 - pend) / a2) if a2 else float("nan"))
        rows.append({
            "class": k, "name": CLASS_NAMES.get(k, str(k)),
            "prev_px": a1, "cur_px": a2, "persist_px": pers, "loss_px": loss, "pending_px": pend, "gain_px": gain,
            "net_px": gain - loss, "exchange_px": 2 * min(gain, loss), "gross_px": gain + loss, "quantity_px": abs(gain - loss),
            "stability_pct": (100.0 * pers / stab_den) if stab_den else float("nan"),
            "coverage_pct": 100.0 * cov,
            "prev_ha": a1 * px_ha, "cur_ha": a2 * px_ha, "persist_ha": pers * px_ha, "loss_ha": loss * px_ha, "pending_ha": pend * px_ha,
            "gain_ha": gain * px_ha, "net_ha": (gain - loss) * px_ha, "exchange_ha": 2 * min(gain, loss) * px_ha, "gross_ha": (gain + loss) * px_ha,
        })
    return rows


def landscape_decomposition(M):
    """
    Décomposition de Pontius sur les pixels CLASSÉS aux deux dates : changement total D = NET (Q) + ÉCHANGE (X) + DÉPLACEMENT (S).
      Q = 1/2 somme |gain_k - perte_k|            (variation de quantité des classes)
      X = somme_{i<j} 2 x min(n_ij, n_ji)          (swap : A->B compensé par B->A)
      S = D - Q - X >= 0                           (rotations A->B->C->A et autres déplacements)
    """
    K = M[:, 1:].astype(np.int64)
    n = int(K.sum())
    persist = int(np.trace(K))
    D = n - persist
    loss = K.sum(axis=1) - np.diag(K)
    gain = K.sum(axis=0) - np.diag(K)
    Q = 0.5 * float(np.abs(gain - loss).sum())
    X = float(sum(2 * min(K[i, j], K[j, i]) for i in range(9) for j in range(i + 1, 9)))
    return {"compared_px": n, "persist_px": persist, "changed_px": D, "net_px": Q, "exchange_px": X, "shift_px": max(0.0, D - Q - X)}


def transition_rows(M, px_ha, reverse=False):
    """
    Toutes les transitions ANCIEN -> RÉCENT (de = classe de l'année la plus ancienne ; 0 = pas encore classé), triées par surface décroissante.
    reverse = True : la carte en cours est la plus ancienne (colonnes de M), la référence la plus récente (lignes).
    """
    out = []
    if not reverse:
        for i in CHANGE_CLASSES:
            a1 = int(M[i - 1].sum())
            for j in range(0, 10):
                if j == i or M[i - 1, j] == 0:
                    continue
                n = int(M[i - 1, j])
                a2 = int(M[:, j].sum()) if j >= 1 else 0
                out.append({"from": i, "to": j, "px": n, "ha": n * px_ha, "pct_prev": 100.0 * n / a1 if a1 else float("nan"),
                            "pct_cur": (100.0 * n / a2) if (j >= 1 and a2) else float("nan"), "implausible": (i, j) in IMPLAUSIBLE_TRANSITIONS})
    else:
        for j in CHANGE_CLASSES:                       # classe de l'année la plus RÉCENTE (référence)
            a_new = int(M[j - 1].sum())
            for i in range(0, 10):                     # classe de l'année la plus ANCIENNE (carte en cours) ; 0 = pas encore classé
                if i == j or M[j - 1, i] == 0:
                    continue
                n = int(M[j - 1, i])
                a_old = int(M[:, i].sum()) if i >= 1 else 0
                out.append({"from": i, "to": j, "px": n, "ha": n * px_ha, "pct_prev": (100.0 * n / a_old) if (i >= 1 and a_old) else float("nan"),
                            "pct_cur": 100.0 * n / a_new if a_new else float("nan"), "implausible": (i, j) in IMPLAUSIBLE_TRANSITIONS})
    return sorted(out, key=lambda r: -r["ha"])


def implausible_alerts(M, px_ha, prev_year=None, reverse=False, newer_year=None):
    """
    Alertes : transitions improbables importantes (toujours dans le sens ANCIEN -> RÉCENT), et classes censées rester stables qui ne le sont pas.
    prev_year = l'année la plus ANCIENNE de la comparaison. reverse = True : la carte en cours est la plus ancienne (colonnes de M), la référence la plus récente (lignes).
    """
    alerts = []
    for (i, j) in sorted(IMPLAUSIBLE_TRANSITIONS):
        if not reverse:
            n, a1, a2 = int(M[i - 1, j]), int(M[i - 1].sum()), int(M[:, j].sum())
        else:
            n, a1, a2 = int(M[j - 1, i]), int(M[:, i].sum()), int(M[j - 1].sum())
        if n == 0:
            continue
        ha = n * px_ha
        sp, sc = (n / a1 if a1 else 0.0), (n / a2 if a2 else 0.0)
        if ha >= ALERT_MIN_HA and (sp >= ALERT_SHARE_PREV or sc >= ALERT_SHARE_CUR):
            yr_txt = f" de {prev_year}" if prev_year else " précédente"
            new_txt = f" de {newer_year}" if newer_year else " plus récente"
            alerts.append({"level": "red" if max(sp, sc) >= ALERT_RED_SHARE else "orange", "kind": "transition", "from": i, "to": j, "ha": ha,
                           "pct_prev": 100 * sp, "pct_cur": 100 * sc, "size": max(sp, sc),
                           "text": f"{CLASS_NAMES[i]} → {CLASS_NAMES[j]} : {ha:,.0f} ha = {100 * sp:.1f} % de la classe « {CLASS_NAMES[i]} »{yr_txt} "
                                   f"et {100 * sc:.1f} % de la classe « {CLASS_NAMES[j]} »{new_txt} — transition improbable : vérifiez les seuils des DEUX années."})
    for k, thr in EXPECTED_MIN_STABILITY.items():
        if not reverse:
            row = M[k - 1]
            classified, pers = int(row.sum() - row[0]), int(row[k])
        else:
            classified, pers = int(M[:, k].sum()), int(M[k - 1, k])
        if classified * px_ha < ALERT_MIN_HA:
            continue
        stab = pers / classified
        if stab < thr:
            alerts.append({"level": "red" if stab < thr - 0.15 else "orange", "kind": "stability", "from": k, "to": k, "ha": (classified - pers) * px_ha,
                           "pct_prev": 100 * stab, "pct_cur": float("nan"), "size": thr - stab,
                           "text": f"{CLASS_NAMES[k]} : seulement {100 * stab:.0f} % de la classe{' de ' + str(prev_year) if prev_year else ''} reste « {CLASS_NAMES[k]} » "
                                   f"(attendu ≥ {100 * thr:.0f} %) — vérifiez les seuils."})
    return sorted(alerts, key=lambda a: (0 if a["level"] == "red" else 1, -a["size"]))


def analyze_change(prev, cur, px_ha, domain=None, prev_year=None, reverse=False, cur_year=None):
    """
    Analyse complète référence (`prev`) / carte en cours (`cur`) : matrice, tableau par classe, décomposition du paysage, transitions, alertes.
    Les résultats sont toujours en sens CHRONOLOGIQUE (ancien -> récent). reverse = True quand la référence est PLUS RÉCENTE que l'année en cours
    (traitement décroissant) ; prev_year = année de la référence, cur_year = année en cours.
    """
    M = change_matrix(prev, cur, domain)
    older, newer = (cur_year, prev_year) if reverse else (prev_year, cur_year)
    return {"M": M, "rows": class_change_rows(M, px_ha, reverse), "landscape": landscape_decomposition(M), "transitions": transition_rows(M, px_ha, reverse),
            "alerts": implausible_alerts(M, px_ha, older, reverse, newer), "px_ha": px_ha, "prev_year": older, "older_year": older, "newer_year": newer, "reverse": bool(reverse),
            "current_year": cur_year, "reference_year": prev_year,
            "pending_px": int(M[:, 0].sum()), "prev_px": int(M.sum())}


def change_map_codes(prev, cur, k, reverse=False):
    """
    Carte d'UNE classe, en sens chronologique : 1 persistance, 2 gain (devient la classe k), 3 perte (cesse d'être k), 4 attente (pas encore classé).
    reverse = True : la référence (prev) est plus RÉCENTE que l'année en cours (cur).
    """
    prev, cur = np.asarray(prev), np.asarray(cur)
    out = np.zeros(prev.shape, np.uint8)
    pk, ck = prev == k, cur == k
    out[pk & ck] = 1
    if not reverse:
        out[(~pk) & ck & (prev >= 1)] = 2
        out[pk & (cur >= 1) & (cur <= 9) & (~ck)] = 3
    else:
        out[pk & (cur >= 1) & (cur <= 9) & (~ck)] = 2
        out[(~pk) & ck & (prev >= 1)] = 3
    out[pk & ((cur == 0) | (cur > 9))] = 4
    return out


def stability_map_codes(prev, cur):
    """Toutes les classes : 1 stable (même classe), 3 changé (autre classe), 4 pas encore classé."""
    prev, cur = np.asarray(prev), np.asarray(cur)
    out = np.zeros(prev.shape, np.uint8)
    known = (prev >= 1) & (prev <= 9)
    now = (cur >= 1) & (cur <= 9)
    out[known & now & (prev == cur)] = 1
    out[known & now & (prev != cur)] = 3
    out[known & ~now] = 4
    return out


def transition_map_codes(prev, cur, i, j, reverse=False):
    """Les pixels qui passent de la classe i (année la plus ANCIENNE) à la classe j (la plus RÉCENTE) : code 6."""
    out = np.zeros(np.asarray(prev).shape, np.uint8)
    if not reverse:
        out[(np.asarray(prev) == i) & (np.asarray(cur) == j)] = 6
    else:
        out[(np.asarray(cur) == i) & (np.asarray(prev) == j)] = 6
    return out


def change_codes_for_mode(mode, prev, cur, stage_class=None, pair=None, reverse=False):
    if prev is None or cur is None or mode in (None, "none"):
        return None
    if mode == "origin" and stage_class:
        return origin_map_codes(prev, cur, int(stage_class))
    if mode == "class" and stage_class:
        return change_map_codes(prev, cur, int(stage_class), reverse)
    if mode == "stability":
        return stability_map_codes(prev, cur)
    if mode == "transition" and pair:
        return transition_map_codes(prev, cur, int(pair[0]), int(pair[1]), reverse)
    return None


def find_previous_lulc(output_dir, year, years):
    """Dernière carte LULC d'une année ANTÉRIEURE déjà produite dans le dossier de résultats : (année, chemin) ou (None, None) pour la 1re année."""
    for y in sorted((int(v) for v in years if int(v) < int(year)), reverse=True):
        p = find_lulc_map(output_dir, y)
        if p:
            return y, p
    return None, None


def load_previous_lulc(path, rows, cols, geo_tf, proj_wkt):
    """Carte de l'année précédente sur la grille du stack (codes 1-9, 0 ailleurs)."""
    arr, _nod = _read_raster_band_on_grid(path, 1, rows, cols, geo_tf, proj_wkt)
    if arr is None:
        return None
    a = np.rint(np.where(np.isfinite(arr), arr, 0)).astype(np.int32)
    a[(a < 0) | (a > 9)] = 0
    a[a == 9] = 7                                   # ancienne carte à 9 classes : le Matorral (9) est fusionné dans Forest (7)
    return a.astype(np.uint8)


def _fmt_ha(v):
    return f"{v:,.0f}"


def change_labels(analysis, ctx=None):
    """
    Libellés des deux années comparées, TOUJOURS dans le sens du temps : O = la plus ancienne, N = la plus récente. Chaque année est étiquetée « (année en cours) » ou « (référence) »
    pour que l'on sache laquelle est celle que l'on est en train de classer. None si les années ne sont pas connues.
    """
    if not analysis:
        return None
    ctx = ctx or {}
    cur = analysis.get("current_year") or ctx.get("yr")
    ref = analysis.get("reference_year") or ctx.get("prev_year") if not analysis.get("reverse") else (analysis.get("reference_year") or ctx.get("prev_year"))
    if analysis.get("reverse"):
        older, newer = analysis.get("older_year") or cur, analysis.get("newer_year") or ref
    else:
        older, newer = analysis.get("older_year") or ref, analysis.get("newer_year") or cur
    if not older or not newer:
        return None
    tag = lambda y: f"{y} (année en cours)" if cur and str(y) == str(cur) else (f"{y} (référence)" if ref and str(y) == str(ref) else str(y))
    gap = abs(int(newer) - int(older))
    return {"O": str(older), "N": str(newer), "older": tag(older), "newer": tag(newer), "cur": str(cur) if cur else None, "ref": str(ref) if ref else None, "gap": gap}


def change_table_headers(analysis=None, ctx=None):
    """En-têtes des tableaux. Avec une analyse dont les années sont connues : en-têtes explicites (« 2020 (année en cours) (ha) », « Perdu 2020→2025 (ha) »...)."""
    base = {"classes": ["Classe", "Année préc. (ha)", "Actuel (ha)", "Stabilité %", "Perte (ha)", "Gain (ha)", "Net = Gain − Perte (ha)", "Échange / swap (ha)",
                        "Brut = Net + Échange (ha)", "En attente (ha)", "Couverture %"],
            "transitions": ["De", "Vers", "Surface (ha)", "% de la classe précédente", "% de la classe actuelle", "Alerte"]}
    lab = change_labels(analysis, ctx) if analysis else None
    if not lab:
        return base
    O, N = lab["O"], lab["N"]
    return {"classes": ["Classe", f"{lab['older']} (ha)", f"{lab['newer']} (ha)", f"Stabilité {O}→{N} (%)", f"Perdu {O}→{N} (ha)", f"Gagné {O}→{N} (ha)", "Net = Gagné − Perdu (ha)",
                        "Échange / swap (ha)", "Brut = Net + Échange (ha)", "En attente (ha)", "Couverture %"],
            "transitions": [f"Classe en {O}", f"Classe en {N}", "Surface (ha)", f"% de la classe en {O}", f"% de la classe en {N}", "Alerte"]}


def breakdown_headers(analysis=None, ctx=None):
    lab = change_labels(analysis, ctx) if analysis else None
    return ["Sens", "Classe", "Surface (ha)", "% du gagné / du perdu" if not lab else "% de cette ligne dans le total", "Alerte"]


def change_mode_labels(lab):
    """Textes des modes de la carte (même ordre que CHANGE_MAP_MODES), avec les années explicites."""
    if not lab:
        return [m[1] for m in CHANGE_MAP_MODES]
    cur, ref, O, N = lab["cur"] or lab["N"], lab["ref"] or lab["O"], lab["O"], lab["N"]
    texts = {"none": "Aucune", "origin": f"Origine : pixels de la classe en {cur}, colorés selon leur classe en {ref} (stable = vert)",
             "class": f"Classe de l'étape : stable / gagné / perdu entre {O} et {N}", "stability": "Toutes les classes : stable / changé", "transition": "Transition choisie dans le tableau"}
    return [texts[m] for m, _l in CHANGE_MAP_MODES]


def change_legend_html(lab):
    """Légende de la carte de changement avec les années explicites."""
    if lab:
        O, N, cur, ref = lab["O"], lab["N"], lab["cur"] or lab["N"], lab["ref"] or lab["O"]
        names = {1: f"Stable (même classe en {O} et en {N})", 2: f"Gagné (cette classe en {N}, autre classe en {O})", 3: f"Perdu (cette classe en {O}, autre classe en {N})",
                 4: "En attente (pas encore classé à cette étape)", 6: "Transition choisie dans le tableau"}
        tail = f" · mode « Origine » : chaque pixel de la classe de cette étape en {cur} est coloré selon sa <b>classe en {ref}</b>"
    else:
        names = {k: v[0] for k, v in CHANGE_MAP_COLORS.items()}
        tail = " · mode « Origine » : chaque pixel changé prend la <b>couleur de sa classe dans l'autre année</b>"
    return " ".join(f"<span style='background:rgba({r},{g},{b},{a / 255:.2f});'>&nbsp;&nbsp;&nbsp;</span> {names[v]}" for v, (_l, (r, g, b, a)) in CHANGE_MAP_COLORS.items()) + tail


def change_class_table(analysis, classes=None):
    """Lignes affichables (chaînes) du tableau « classes » : seules les classes présentes (ou demandées) ; + ligne de total."""
    px = analysis["px_ha"]
    rows = []
    for r in analysis["rows"]:
        if classes is not None and r["class"] not in classes:
            continue
        if classes is None and r["prev_px"] == 0 and r["cur_px"] == 0:
            continue
        rows.append([f"{r['class']} — {r['name']}", _fmt_ha(r["prev_ha"]), _fmt_ha(r["cur_ha"]),
                     "—" if np.isnan(r["stability_pct"]) else f"{r['stability_pct']:.1f}", _fmt_ha(r["loss_ha"]), _fmt_ha(r["gain_ha"]),
                     f"{r['net_ha']:+,.0f}", _fmt_ha(r["exchange_ha"]), _fmt_ha(r["gross_ha"]), _fmt_ha(r["pending_ha"]),
                     "—" if np.isnan(r["coverage_pct"]) else f"{r['coverage_pct']:.0f}"])
    ls = analysis["landscape"]
    n = max(ls["compared_px"], 1)
    rows.append(["PAYSAGE (pixels classés aux 2 dates)", "", _fmt_ha(ls["compared_px"] * px), f"{100.0 * ls['persist_px'] / n:.1f}", "", "", f"net {ls['net_px'] * px:,.0f}",
                 f"échange {ls['exchange_px'] * px:,.0f}", f"déplacement {ls['shift_px'] * px:,.0f}", _fmt_ha(analysis["pending_px"] * px), ""])
    return rows


def relevant_alerts(analysis, stage_class=None):
    """
    (alertes de la classe de CETTE étape, alertes des AUTRES classes). Une alerte concerne la classe k si elle part de k, arrive à k, ou porte sur la stabilité de k.
    Sans classe d'étape (carte finale) : toutes les alertes sont pertinentes.
    """
    al = analysis["alerts"]
    if not stage_class:
        return list(al), []
    k = int(stage_class)
    mine = [a for a in al if a["from"] == k or a["to"] == k]
    return mine, [a for a in al if not (a["from"] == k or a["to"] == k)]


def filtered_transitions(analysis, only_class=None, limit=120):
    """Transitions (les plus grandes d'abord) ; only_class = ne garder que celles qui partent de cette classe ou y arrivent."""
    ts = analysis["transitions"]
    if only_class:
        k = int(only_class)
        ts = [t for t in ts if t["from"] == k or t["to"] == k]
    return ts[:limit]


def change_transition_table(analysis, limit=60, only_class=None):
    """Lignes affichables du tableau « transitions » (les plus grandes d'abord) avec l'alerte éventuelle."""
    out = []
    alert_by_pair = {(a["from"], a["to"]): a for a in analysis["alerts"] if a["kind"] == "transition"}
    for t in filtered_transitions(analysis, only_class, limit):
        al = alert_by_pair.get((t["from"], t["to"]))
        out.append(["pas encore classé" if t["from"] == 0 else f"{t['from']} — {CLASS_NAMES.get(t['from'], '')}", "pas encore classé" if t["to"] == 0 else f"{t['to']} — {CLASS_NAMES.get(t['to'], '')}",
                    _fmt_ha(t["ha"]), f"{t['pct_prev']:.1f}", "—" if np.isnan(t["pct_cur"]) else f"{t['pct_cur']:.1f}",
                    ("🔴 improbable" if al["level"] == "red" else "🟠 improbable") if al else ("improbable (faible)" if t["implausible"] else "")])
    return out


def stage_class_breakdown(analysis, k, ctx=None):
    """
    Pour la classe k, entre l'année O (la plus ancienne) et l'année N (la plus récente) :
      GAGNÉ : « cette classe » en N mais pas en O -> la ligne dit ce que c'était en O ;
      PERDU : « cette classe » en O mais plus en N -> la ligne dit ce que c'est devenu en N.
    """
    M, px = analysis["M"], analysis["px_ha"]
    rev = bool(analysis.get("reverse"))
    lab = change_labels(analysis, ctx)
    k = int(k)
    alerts = {(a["from"], a["to"]): a for a in analysis["alerts"] if a["kind"] == "transition"}
    g_lab = f"GAGNÉ : en {lab['O']} c'était" if lab else "GAIN ← vient de"
    l_lab = f"PERDU : en {lab['N']} c'est devenu" if lab else "PERTE → part vers"
    pend = f"pas encore classé en {lab['cur']} (en attente)" if (lab and lab["cur"]) else "pas encore classé (en attente)"

    def mark(pair):
        al = alerts.get(pair)
        return ("🔴 improbable" if al["level"] == "red" else "🟠 improbable") if al else ("improbable (faible)" if pair in IMPLAUSIBLE_TRANSITIONS else "")
    rows = []
    if not rev:
        gains = sorted(((i, int(M[i - 1, k])) for i in CHANGE_CLASSES if i != k and M[i - 1, k] > 0), key=lambda t: -t[1])
        losses = sorted(((j, int(M[k - 1, j])) for j in range(0, 10) if j != k and M[k - 1, j] > 0), key=lambda t: -t[1])
    else:
        gains = sorted(((i, int(M[k - 1, i])) for i in range(0, 10) if i != k and M[k - 1, i] > 0), key=lambda t: -t[1])
        losses = sorted(((j, int(M[j - 1, k])) for j in CHANGE_CLASSES if j != k and M[j - 1, k] > 0), key=lambda t: -t[1])
    g_tot, l_tot = sum(n for _i, n in gains), sum(n for _j, n in losses)
    for i, n in gains:
        rows.append([g_lab, pend if i == 0 else f"{i} — {CLASS_NAMES.get(i, '')}", _fmt_ha(n * px), f"{100.0 * n / g_tot:.1f}", mark((i, k))])
    for j, n in losses:
        rows.append([l_lab, pend if j == 0 else f"{j} — {CLASS_NAMES.get(j, '')}", _fmt_ha(n * px), f"{100.0 * n / l_tot:.1f}", mark((k, j))])
    return rows


def change_summary_html(analysis, stage_class=None, yr=None):
    """Bloc HTML du rapport d'aperçu : classe de l'étape, décomposition Net / Échange / Déplacement du paysage, alertes. Les deux années sont nommées (en cours / référence)."""
    if not analysis:
        return []
    py = analysis.get("prev_year")
    lab = change_labels(analysis, {"yr": yr, "prev_year": py})
    if lab:
        out = [f"<br><b>📊 Changement {lab['O']} → {lab['N']}</b> (Δ {lab['gap']} ans) — année en cours : <b>{lab['cur']}</b>, référence : <b>{lab['ref']}</b> :<br>"
               f"<i>Sens du temps : {lab['O']} est la plus ancienne. « Perdu » = présent en {lab['O']} et absent en {lab['N']} ; « gagné » = présent en {lab['N']} et absent en {lab['O']}.</i><br>"]
    else:
        out = [f"<br><b>📊 Changement vs {py} :</b><br>"]
    px = analysis["px_ha"]
    if stage_class:
        r = next((x for x in analysis["rows"] if x["class"] == int(stage_class)), None)
        if r and (r["prev_px"] or r["cur_px"]):
            stab = "—" if np.isnan(r["stability_pct"]) else f"{r['stability_pct']:.0f} %"
            yrs = f" {lab['O']}→{lab['N']}" if lab else ""
            out.append(f"• « {r['name']} »{yrs} : stabilité <b>{stab}</b> | perdu {r['loss_ha']:,.0f} ha | gagné {r['gain_ha']:,.0f} ha | "
                       f"net <b>{r['net_ha']:+,.0f} ha</b> | échange (swap) {r['exchange_ha']:,.0f} ha"
                       + (f" | <i>en attente {r['pending_ha']:,.0f} ha (pas encore classés)</i>" if r["pending_px"] else "") + "<br>")
    ls = analysis["landscape"]
    if ls["compared_px"]:
        n = ls["compared_px"]
        out.append(f"• Paysage ({n * px:,.0f} ha classés aux 2 dates) : changement total <b>{100.0 * ls['changed_px'] / n:.1f} %</b> = net {100.0 * ls['net_px'] / n:.1f} % "
                   f"+ échange {100.0 * ls['exchange_px'] / n:.1f} % + déplacement {100.0 * ls['shift_px'] / n:.1f} %<br>")
    mine, others = relevant_alerts(analysis, stage_class)
    for a in mine[:5]:
        col = "#c62828" if a["level"] == "red" else "#ef6c00"
        out.append(f"<span style='color:{col};font-weight:bold'>{'🔴' if a['level'] == 'red' else '🟠'} {a['text']}</span><br>")
    if len(mine) > 5:
        out.append(f"<i>… et {len(mine) - 5} autre(s) alerte(s) sur cette classe : voir « 📊 Changement ».</i><br>")
    if stage_class and not mine:
        out.append(f"<span style='color:#2e7d32'>✅ Aucune transition improbable concernant la classe « {CLASS_NAMES.get(int(stage_class), '')} ».</span><br>")
    if others:
        out.append(f"<i>ℹ {len(others)} alerte(s) concernent des classes d'étapes DÉJÀ validées (ex. {others[0]['text'].split(' :')[0]}) : elles ne dépendent pas des seuils de cette étape.</i><br>")
    return out


def export_change_reports(output_dir, prev_year, year, analysis, prev, cur, geo_tf, proj_wkt):
    """Fichiers de la 2e année et suivantes : tableaux CSV (classes, transitions, paysage) et carte de changement (de x 10 + vers)."""
    px = analysis["px_ha"]
    hdr = change_table_headers(analysis, {"yr": year, "prev_year": prev_year})
    paths = {}
    cdir = change_dir(output_dir)                              # <résultats>/Changement/
    paths["classes"] = write_csv_rows(os.path.join(cdir, f"Change_Classes_{prev_year}_{year}.csv"),
                                      [hdr["classes"]] + change_class_table(analysis, classes=set(CHANGE_CLASSES)))
    paths["transitions"] = write_csv_rows(os.path.join(cdir, f"Change_Transitions_{prev_year}_{year}.csv"),
                                          [hdr["transitions"]] + change_transition_table(analysis, limit=10 ** 6))
    ls = analysis["landscape"]
    n = max(ls["compared_px"], 1)
    paths["landscape"] = write_csv_rows(os.path.join(cdir, f"Change_Landscape_{prev_year}_{year}.csv"), [
        ["Composante", "Surface (ha)", "% des pixels classés aux 2 dates"],
        ["Comparé (classé aux 2 dates)", f"{ls['compared_px'] * px:.2f}", "100.0"],
        ["Persistance (inchangé)", f"{ls['persist_px'] * px:.2f}", f"{100.0 * ls['persist_px'] / n:.2f}"],
        ["Changement total", f"{ls['changed_px'] * px:.2f}", f"{100.0 * ls['changed_px'] / n:.2f}"],
        ["  dont NET (variation de quantité)", f"{ls['net_px'] * px:.2f}", f"{100.0 * ls['net_px'] / n:.2f}"],
        ["  dont ÉCHANGE (swap)", f"{ls['exchange_px'] * px:.2f}", f"{100.0 * ls['exchange_px'] / n:.2f}"],
        ["  dont DÉPLACEMENT (shift)", f"{ls['shift_px'] * px:.2f}", f"{100.0 * ls['shift_px'] / n:.2f}"],
        ["Alertes", len(analysis["alerts"]), ""]] + [["", a["text"], ""] for a in analysis["alerts"]])
    code = np.zeros(prev.shape, np.uint8)
    both = (prev >= 1) & (prev <= 9) & (cur >= 1) & (cur <= 9)
    code[both] = (prev[both].astype(np.int32) * 10 + cur[both].astype(np.int32)).astype(np.uint8)
    paths["map"] = write_raster(os.path.join(cdir, f"Change_Map_{prev_year}_{year}.tif"), code, geo_tf, proj_wkt, gdal.GDT_Byte, 0)
    return paths


def fill_change_table(table, headers, rows, row_colors=None):
    """Remplit un QTableWidget (liste de listes de chaînes) ; row_colors = {indice de ligne: (r, v, b)} facultatif."""
    table.setRowCount(len(rows))
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(list(headers))
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            it = QTableWidgetItem(str(val))
            if row_colors and ri in row_colors:
                try:
                    it.setBackground(QColor(*row_colors[ri]))
                except Exception:
                    pass
            table.setItem(ri, ci, it)
    try:
        table.resizeColumnsToContents()
    except Exception:
        pass


# ====================== CARTE DE L'ANNÉE PRÉCÉDENTE EN MÉMOIRE + ORIGINE DES PIXELS + « MAX ACCORD » (AJOUT) ======================
PREVIOUS_MAPS = {}      # année (int) -> {"arr": uint8, "geo_tf": tuple} : cartes FINALES des années déjà traitées dans cette session (mémoire)


def register_previous_map(year, lulc, geo_tf):
    """Mémorise la carte finale d'une année : la fenêtre des années suivantes la compare sans relire de fichier."""
    PREVIOUS_MAPS[int(year)] = {"arr": np.asarray(lulc).astype(np.uint8).copy(), "geo_tf": tuple(float(v) for v in geo_tf)}


def _same_grid(a, b, tol=1e-6):
    return len(a) == len(b) and all(abs(float(x) - float(y)) <= tol for x, y in zip(a, b))


def reference_candidates(year, years, order=None):
    """
    Années candidates comme RÉFÉRENCE de la comparaison, de la meilleure à la moins bonne.
      ascendant  : l'année PRÉCÉDENTE la plus proche d'abord (2015 -> 2007, pas 2020), puis seulement les années plus récentes si aucune année plus ancienne n'existe ;
      descendant : l'année la plus PROCHE (à égalité la plus récente).
    """
    y0 = int(year)
    ys = {int(v) for v in years} - {y0}
    if process_order_name(order) == "ascending":
        return sorted((y for y in ys if y < y0), key=lambda y: y0 - y) + sorted((y for y in ys if y > y0), key=lambda y: y - y0)
    return sorted(ys, key=lambda c: (abs(c - y0), -c))


def get_previous_map(output_dir, year, years, rows, cols, geo_tf, proj_wkt, order=None):
    """
    Carte de RÉFÉRENCE de la comparaison (voir reference_candidates) : en ordre ASCENDANT l'année classée juste AVANT ; en ordre descendant la plus proche (en général la suivante, plus récente).
    MÉMOIRE d'abord (déjà classée dans cette session, même grille), sinon fichier LULC_<AREA_TAG>_<année>.tif du dossier de résultats.
    Retourne (année, tableau uint8, source) ; (None, None, None) si aucune autre année n'est classée.
    """
    y0 = int(year)
    for y in reference_candidates(y0, {int(v) for v in years} | set(PREVIOUS_MAPS), order):
        m = PREVIOUS_MAPS.get(y)
        if m is not None and m["arr"].shape == (rows, cols) and _same_grid(m["geo_tf"], geo_tf):
            return y, m["arr"], "mémoire"
        p = find_lulc_map(output_dir, y)
        if p:
            arr = load_previous_lulc(p, rows, cols, geo_tf, proj_wkt)
            if arr is not None:
                return y, arr, "fichier"
    return None, None, None


def origin_map_codes(prev, cur, k):
    """
    Pixels de la classe k (année en cours) : 1 = STABLE (même classe l'année précédente) ; 10 + c = VIENT de la classe c ;
    20 = vient d'une zone non classée l'année précédente.
    """
    prev, cur = np.asarray(prev), np.asarray(cur)
    out = np.zeros(prev.shape, np.uint8)
    ck = cur == k
    known = (prev >= 1) & (prev <= 9)
    out[ck & (prev == k)] = 1
    ch = ck & known & (prev != k)
    out[ch] = (10 + prev[ch].astype(np.int32)).astype(np.uint8)
    out[ck & ~known] = 20
    return out


def change_palette(class_rgb=None, reverse=False, cur_year=None, ref_year=None):
    """Palette de la carte de changement : codes de base + (mode « origine ») une couleur par classe de l'AUTRE année (la référence)."""
    pal = dict(CHANGE_MAP_COLORS)
    if class_rgb is None:
        try:
            class_rgb = {c: (CLASS_COLORS[c].red(), CLASS_COLORS[c].green(), CLASS_COLORS[c].blue()) for c in CLASS_COLORS}
        except Exception:
            class_rgb = {}
    where = f"en {ref_year}" if ref_year else ("dans la référence plus récente" if reverse else "dans l'année précédente")
    for c in CHANGE_CLASSES:
        r, g, b = class_rgb.get(c, (128, 128, 128))
        pal[10 + c] = (f"Classe {where} : {c} — {CLASS_NAMES.get(c, '')}", (r, g, b, 235))
    pal[20] = (f"Zone non classée {where}", (150, 150, 150, 170))
    return pal


# ---------------- « Persistence Maximizer » : seuils qui reproduisent au mieux la classe de l'année précédente ----------------
MIN_PCTS = (0.5, 1, 2, 5, 10, 15, 25, 35, 50)        # candidats pour un seuil « min » : bas de la distribution des pixels de référence
MAX_PCTS = (50, 65, 75, 85, 90, 95, 98, 99, 99.5)    # candidats pour un seuil « max » : haut de la distribution


def agreement_metrics(pred, ref, dom):
    """Accord entre le masque proposé `pred` et la classe de référence `ref` dans le domaine `dom` : F1 (Dice), Jaccard, précision, rappel (= persistance)."""
    pred, ref, dom = np.asarray(pred, bool) & dom, np.asarray(ref, bool) & dom, np.asarray(dom, bool)
    tp = int(np.count_nonzero(pred & ref))
    fp = int(np.count_nonzero(pred & ~ref & dom))
    fn = int(np.count_nonzero(~pred & ref))
    d1, d2 = 2 * tp + fp + fn, tp + fp + fn
    return {"tp": tp, "fp": fp, "fn": fn, "pred_px": tp + fp, "ref_px": tp + fn,
            "precision": tp / (tp + fp) if tp + fp else 0.0, "recall": tp / (tp + fn) if tp + fn else 0.0,
            "f1": 2 * tp / d1 if d1 else 0.0, "jaccard": tp / d2 if d2 else 0.0}


def optimize_agreement(threshold_func, features, dom, ref, cur_th, specs, max_passes=3, max_pixels=600000, min_gain=1e-4, max_evals=600):
    """
    Cherche les seuils qui donnent le MEILLEUR ACCORD (F1) entre le masque de l'étape et la classe de l'année précédente (`ref`), dans le domaine `dom`.
    Les candidats d'un champ sont les MÉDIANES / MINIMA / MAXIMA robustes (centiles) de la variable sur les pixels de référence ; recherche par
    coordonnées (champ par champ, 3 passes). `threshold_func(th, base)` est la fonction de seuils réelle de l'étape (boîte noire) ; le calcul se fait
    sur un sous-échantillon régulier (<= max_pixels). Un champ inutile est laissé VIDE (parcimonie). Retourne un dict (ok, th, before, after, changes, pcts...).
    specs = {clé du champ: {"feature": variable, "op": "min" | "max"}}.
    """
    H, W = dom.shape
    stride = max(1, int(np.ceil(np.sqrt(H * W / float(max_pixels)))))
    dom_s = dom[::stride, ::stride]
    ref_s = ref[::stride, ::stride] & dom_s
    if not dom_s.any():
        return {"ok": False, "reason": "no_domain"}
    if not ref_s.any():
        return {"ok": False, "reason": "no_reference"}
    backup = dict(features)
    sub = {k: v[::stride, ::stride] for k, v in backup.items() if getattr(v, "ndim", 0) == 2}
    usable = {k: s for k, s in specs.items() if s["feature"] in sub}
    evals = [0]
    try:
        features.clear()
        features.update(sub)

        def run(th):
            evals[0] += 1
            return agreement_metrics(threshold_func(th, dom_s) & dom_s, ref_s, dom_s)

        cands, pcts = {}, {}
        for key, s in usable.items():
            v = sub[s["feature"]][ref_s]
            v = v[np.isfinite(v)]
            if v.size == 0:
                continue
            q = np.percentile(v, list(MIN_PCTS if s["op"] == "min" else MAX_PCTS))
            cands[key] = sorted({round(float(x), 3) for x in q})
            pcts[key] = tuple(round(float(x), 3) for x in np.percentile(v, (5, 50, 95)))
        best_th = {k: (cur_th.get(k) if cur_th.get(k) is not None else None) for k in set(cur_th) | set(cands)}
        before = run(best_th)
        best = before
        for _p in range(max_passes):
            changed = False
            for key in cands:
                if evals[0] >= max_evals:
                    break
                cur_v = best_th.get(key)
                scored = [(cur_v, best)]
                for c in [None] + cands[key]:
                    if c == cur_v:
                        continue
                    th2 = dict(best_th)
                    th2[key] = c
                    scored.append((c, run(th2)))
                top = max(m["f1"] for _c, m in scored)
                near = [(c, m) for c, m in scored if m["f1"] >= top - min_gain]
                choice = next(((c, m) for c, m in near if c is None), None) or next(((c, m) for c, m in near if c == cur_v), None) or max(near, key=lambda t: t[1]["f1"])
                if choice[0] != cur_v and (choice[1]["f1"] > best["f1"] + min_gain or choice[0] is None):
                    best_th[key], best, changed = choice[0], choice[1], True
            if not changed or evals[0] >= max_evals:
                break
    finally:
        features.clear()
        features.update(backup)
        RULE_TRACE.clear()
    changes = [(k, cur_th.get(k), best_th.get(k)) for k in cands if cur_th.get(k) != best_th.get(k)]
    return {"ok": True, "th": {k: best_th.get(k) for k in best_th}, "before": before, "after": best, "changes": changes, "pcts": pcts,
            "stride": stride, "evals": evals[0], "sample_px": int(dom_s.sum()), "ref_px": int(ref_s.sum())}


def optimizer_report_html(res, prev_year, stage_name, labels=None, px_ha=None, anchor=False):
    """Rapport lisible de l'optimiseur : accord avant / après, champs modifiés, centiles des pixels de référence, mise en garde."""
    if not res.get("ok"):
        why = {"no_reference": f"aucun pixel de la classe « {stage_name} » en {prev_year} dans le domaine de cette étape : rien à reproduire.",
               "no_domain": "le domaine de cette étape est vide."}.get(res.get("reason"), "échec.")
        return f"<b>🎯 Optimisation impossible</b> : {why}"
    b, a = res["before"], res["after"]
    lab = (labels or {})
    out = [f"<b>🎯 Max Accord {prev_year} — classe « {stage_name} »</b><br>",
           f"Accord (F1) : <b>{100 * b['f1']:.1f} % → {100 * a['f1']:.1f} %</b> | précision {100 * b['precision']:.0f} % → {100 * a['precision']:.0f} % | "
           f"rappel (persistance) {100 * b['recall']:.0f} % → {100 * a['recall']:.0f} %<br>"]
    if px_ha:
        s2 = res["stride"] ** 2
        out.append(f"Masque proposé ≈ {a['pred_px'] * s2 * px_ha:,.0f} ha ; classe en {prev_year} ≈ {a['ref_px'] * s2 * px_ha:,.0f} ha (estimations sur un sous-échantillon 1/{s2}).<br>")
    if res["changes"]:
        out.append("<b>Champs modifiés :</b><br>")
        for k, old, new in res["changes"]:
            p = res["pcts"].get(k)
            out.append(f"• {lab.get(k, k)} : {'vide' if old is None else f'{float(old):g}'} → <b>{'vide (inutile)' if new is None else f'{float(new):g}'}</b>"
                       + (f" <i>(pixels de {prev_year} : P5 {p[0]:g} · médiane {p[1]:g} · P95 {p[2]:g})</i>" if p else "") + "<br>")
    else:
        out.append("Aucun champ à modifier : les seuils actuels sont déjà optimaux pour cet accord.<br>")
    if anchor:
        out.append(f"<i>⚓ Seuils appris UNIQUEMENT sur les pixels spectralement stables de l'ancre {prev_year} (classe fiable) : ils décrivent la classe « {stage_name} » telle qu'elle était "
                   f"quand elle ne changeait pas. Les pixels qui ont changé sont classés avec ces seuils : appuyez sur Aperçu et contrôlez le tableau « 📊 Changement ».</i>")
    else:
        out.append(f"<i>⚠ Cette optimisation REPRODUIT la carte de {prev_year} : les vrais changements seront atténués. Point de départ, pas vérité : "
                   f"appuyez sur Aperçu et examinez le tableau « 📊 Changement ».</i>")
    return "".join(out)


# ====================== ANCRE HAUTE PRÉCISION (ex. 2025) : STABILITÉ SPECTRALE STACK-À-STACK (cadre de preuves intégré) ======================
# Principe (repris du Spectral Evidence Framework) : pour une ANCIENNE année, le SPECTRE décide seul de la stabilité d'un pixel par rapport au Stack de l'ANCRE :
#   écart de chaque bande commune (ancre - année), médiane (le décalage global entre capteurs / saisons est ABSORBÉ) et écart robuste (MAD x 1.4826),
#   intervalle de variation FAIBLE = médiane +- 2.5 x MAD (indices clés : +- 0.05 en mode absolu), part des bandes dans l'intervalle -> 5 niveaux de confiance.
# Un pixel spectralement STABLE (niveau 1 : >= 90 % des bandes ; niveau 2 : >= 75 %) garde probablement la classe de l'ancre : c'est un « CANDIDAT STABLE ».
#   * HÉRITAGE : ces pixels reçoivent la classe de l'ancre (rôle « union » du masque d'étape, source « Ancre ») ;
#   * ENTRAÎNEMENT AUTOMATIQUE : leurs classes servent d'échantillons (Random Forest, seuils optimisés) : plus besoin de dessiner des échantillons pour chaque ancienne année ;
#   * les pixels INSTABLES (changés) sont classés par les seuils / le RF de la fenêtre d'étape.
# Le poids du transfert décroît avec l'écart d'années (demi-vie 10 ans) ; l'ancre n'est JAMAIS une vérité historique : c'est un APPUI.
ANCHOR_TOL_Z = 2.5
ANCHOR_ABS_TOL = 0.05
ANCHOR_CONF_THRESHOLDS = (0.90, 0.75, 0.50, 0.25)      # niveaux 1 (stable haute) / 2 (stable modérée) / 3 (révision) / 4 (instable modérée) / 5
ANCHOR_HALF_LIFE = 10.0
ANCHOR_MIN_BANDS = 8
ANCHOR_SAMPLE_TARGET = 250000
ANCHOR_KEY_INDEX_RE = re.compile(r"^[A-Za-z]{3}_(NDVI|EVI|SAVI|MSAVI2|NDMI|NBR|NBR2|NDWI|MNDWI|AWEI_nsh|NDBI|UI|IBI|DBSI)$")
_ANCHOR_YEAR_RE = re.compile(r"(?<![0-9])(?:19|20)[0-9]{2}(?![0-9])")
ANCHOR_LEVEL_LABELS = ["Stable haute confiance (≥ 90 % des bandes dans l'intervalle)", "Stable (≥ 75 % des bandes)"]
ANCHOR_CTX = {"active": False}          # contexte de l'ANCRE de l'année en cours de traitement (vidé / recréé à chaque année)


def anchor_normalize_name(name):
    """Retire l'année d'un nom de bande : 'Apr_2015_B4_NIR' -> 'Apr_B4_NIR' (pour apparier les bandes de deux Stacks)."""
    return re.sub(r"_+", "_", _ANCHOR_YEAR_RE.sub("", str(name))).strip("_ ")


def anchor_name_keys(name):
    """(clé exacte, clé sans numéro de bande) : 'Apr_B4_NIR' -> ('Apr_B4_NIR', 'Apr_NIR') ; la 2e clé apparie L5/L7 (B4 = NIR) avec L8/L9 (B5 = NIR)."""
    k1 = anchor_normalize_name(name)
    k2 = re.sub(r"_+", "_", re.sub(r"(^|_)B[0-9]+(?=_|$)", r"\1", k1)).strip("_ ")
    return k1, k2


def anchor_band_group(name):
    """Famille d'une bande : Texture et Thermique sont EXCLUES de la décision principale (trop bruitées d'une date à l'autre)."""
    n = str(name)
    if "Texture" in n:
        return "Texture"
    if "TIR" in n or re.search(r"(^|_)B10(_|$)", n):
        return "Thermique"
    if n.startswith("Delta_") or n.startswith("Phenology"):
        return "Phenologie"
    if "TC_" in n:
        return "Tasseled Cap"
    if "_div_" in n:
        return "Rapports de bandes"
    if re.search(r"_(NDVI|EVI|SAVI|MSAVI2)$", n):
        return "Indices de verdure"
    if re.search(r"_(NDMI|NBR|NBR2)$", n):
        return "Indices humidite/feu"
    if re.search(r"_(NDWI|MNDWI|AWEI_nsh)$", n):
        return "Indices eau"
    if re.search(r"_(NDBI|DBSI|UI|IBI)$", n):
        return "Indices bati/sol nu"
    if re.search(r"_B[0-9]+_", n):
        return "Reflectance"
    return "Autres"


def anchor_common_bands(names_cur, names_anchor):
    """
    Bandes présentes UNE seule fois dans chaque Stack. 1re tentative : même nom sans l'année ; 2e tentative (bandes restantes) : même nom sans année NI numéro de bande.
    Retourne ([(étiquette, nom dans l'année en cours, indice dans l'ancre)], ambiguës).
    """
    ka = [anchor_name_keys(n) for n in names_anchor]
    kc = [anchor_name_keys(n) for n in names_cur]
    pairs, used_c, used_a, amb = [], set(), set(), set()
    for pos in (0, 1):
        cnt_c, cnt_a = {}, {}
        for i, k in enumerate(kc):
            if i not in used_c and k[pos]:
                cnt_c[k[pos]] = cnt_c.get(k[pos], 0) + 1
        for i, k in enumerate(ka):
            if i not in used_a and k[pos]:
                cnt_a[k[pos]] = cnt_a.get(k[pos], 0) + 1
        ia = {k[pos]: i for i, k in enumerate(ka) if i not in used_a and k[pos]}
        for ic, k in enumerate(kc):
            key = k[pos]
            if ic in used_c or not key:
                continue
            if cnt_c.get(key, 0) == 1 and cnt_a.get(key, 0) == 1:
                pairs.append((key, names_cur[ic], ia[key]))
                used_c.add(ic)
                used_a.add(ia[key])
            elif cnt_c.get(key, 0) > 1 or cnt_a.get(key, 0) > 1:
                amb.add(key)
    return pairs, sorted(amb)


def anchor_half_width(label, mad, tau=ANCHOR_TOL_Z, mode="robust", abs_tol=ANCHOR_ABS_TOL):
    """Demi-largeur de l'intervalle de variation faible d'une bande : tau x écart robuste ; mode « abs » : valeur FIXE pour les indices clés."""
    if str(mode).startswith("abs") and ANCHOR_KEY_INDEX_RE.match(str(label)):
        return float(abs_tol)
    return float(tau) * float(mad)


def anchor_confidence_levels(share, thr=ANCHOR_CONF_THRESHOLDS):
    """1 stable haute confiance, 2 stable modérée, 3 zone de révision, 4 instable modérée, 5 instable haute confiance ; 0 = non évalué."""
    t1, t2, t3, t4 = thr
    share = np.asarray(share)
    out = np.zeros(share.shape, np.uint8)
    ok = np.isfinite(share)
    out[ok & (share >= t1)] = 1
    out[ok & (share < t1) & (share >= t2)] = 2
    out[ok & (share < t2) & (share >= t3)] = 3
    out[ok & (share < t3) & (share >= t4)] = 4
    out[ok & (share < t4)] = 5
    return out


def anchor_temporal_weight(delta_years, half_life=ANCHOR_HALF_LIFE):
    """Poids du transfert temporel : divisé par 2 tous les `half_life` ans (indicatif : l'ancre est un APPUI, pas une vérité historique)."""
    return 0.5 ** (abs(float(delta_years)) / float(half_life))


def anchor_stability(cur_names, cur_arrays, anchor_names, read_anchor_band, valid, tau=ANCHOR_TOL_Z, mode="robust", abs_tol=ANCHOR_ABS_TOL,
                     include_noisy=False, thresholds=ANCHOR_CONF_THRESHOLDS, sample_target=ANCHOR_SAMPLE_TARGET, min_valid_frac=0.5, seed=7):
    """
    Stabilité spectrale de l'année en cours par rapport au Stack de l'ancre, pixel par pixel : part des bandes communes dont l'écart reste dans l'intervalle de
    variation faible (médiane +- tau x MAD, décalage global absorbé). Deux passages (la médiane / MAD d'une bande se calcule sur un échantillon, puis tous les pixels
    sont comptés) : une bande de l'ancre n'est jamais gardée en mémoire. read_anchor_band(i) -> tableau float (NaN = NoData) sur la grille de l'année en cours.
    """
    pairs, amb = anchor_common_bands(cur_names, anchor_names)
    n_common = len(pairs)
    if not include_noisy:
        pairs = [p for p in pairs if anchor_band_group(p[0]) not in ("Texture", "Thermique")]
    pairs = [p for p in pairs if p[1] in cur_arrays]
    if len(pairs) < ANCHOR_MIN_BANDS:
        raise RuntimeError(f"Bandes communes insuffisantes avec l'ancre : {len(pairs)} utilisables (minimum {ANCHOR_MIN_BANDS}). "
                           f"Les deux Stacks doivent avoir les mêmes bandes (noms identiques à l'année près).")
    valid = np.asarray(valid, bool)
    vidx = np.flatnonzero(valid.ravel())
    if vidx.size == 0:
        raise RuntimeError("Aucun pixel valide dans la zone d'étude pour l'analyse de stabilité.")
    rng = np.random.default_rng(seed)
    samp = vidx if vidx.size <= sample_target else rng.choice(vidx, int(sample_target), replace=False)
    stats = []
    for _k, (label, ncur, ia) in enumerate(pairs):
        progress_tick(_k, 2 * len(pairs), f"ancre : statistiques de la bande {label} ({_k + 1} / {len(pairs)})")
        a = np.asarray(read_anchor_band(ia), dtype=np.float32)
        d = (a.ravel()[samp] - np.asarray(cur_arrays[ncur], dtype=np.float32).ravel()[samp]).astype(np.float64)
        d = d[np.isfinite(d)]
        if d.size < 50:
            stats.append(None)
            continue
        med = float(np.median(d))
        mad = 1.4826 * float(np.median(np.abs(d - med)))
        if not np.isfinite(mad) or mad <= 1e-9:
            sd = float(np.std(d))
            mad = sd if np.isfinite(sd) and sd > 1e-9 else 1.0
        stats.append({"label": label, "name": ncur, "idx_anchor": ia, "median": med, "mad": mad, "half_width": anchor_half_width(label, mad, tau, mode, abs_tol),
                      "group": anchor_band_group(label)})
    used = [s for s in stats if s is not None]
    if len(used) < ANCHOR_MIN_BANDS:
        raise RuntimeError(f"Trop peu de bandes avec assez de pixels valides ({len(used)}).")
    n_in = np.zeros(valid.shape, np.int16)
    n_ok = np.zeros(valid.shape, np.int16)
    for _k, s in enumerate(used):
        progress_tick(len(pairs) + _k, 2 * len(pairs), f"ancre : comptage des pixels stables, bande {s['label']} ({_k + 1} / {len(used)})")
        a = np.asarray(read_anchor_band(s["idx_anchor"]), dtype=np.float32)
        with np.errstate(invalid="ignore"):
            d = a - np.asarray(cur_arrays[s["name"]], dtype=np.float32)
            ok = np.isfinite(d)
            n_ok += ok
            n_in += ok & (np.abs(d - np.float32(s["median"])) <= np.float32(s["half_width"]))
    share = np.full(valid.shape, np.nan, np.float32)
    good = valid & (n_ok >= max(3, int(min_valid_frac * len(used))))
    share[good] = n_in[good] / n_ok[good]
    return {"share": share, "level": anchor_confidence_levels(share, thresholds), "n_bands": len(used), "n_common": n_common, "stats": used, "ambiguous": amb,
            "n_valid_px": int(good.sum())}


def anchor_stable_mask(level, anchor_map, min_level=1):
    """Candidats STABLES : niveau de confiance 1..min_level ET un pixel classé dans l'ancre."""
    level = np.asarray(level)
    am = np.asarray(anchor_map)
    return (level >= 1) & (level <= int(min_level)) & (am >= 1) & (am <= 9)


def anchor_training_labels(anchor_map, level, min_level=1):
    """Étiquettes d'entraînement AUTOMATIQUES : la classe de l'ancre sur les pixels stables, 0 ailleurs (aucun échantillon manuel)."""
    st = anchor_stable_mask(level, anchor_map, min_level)
    out = np.zeros(np.asarray(anchor_map).shape, np.uint8)
    out[st] = np.asarray(anchor_map)[st].astype(np.uint8)
    return out


def anchor_class_rows(anchor_map, level, min_level, px_ha, domain=None):
    """Par classe de l'ancre : surface, surface stable (candidats), part stable (%), surface d'entraînement."""
    am = np.asarray(anchor_map)
    inside = (am >= 1) & (am <= 9)
    if domain is not None:
        inside &= np.asarray(domain, bool)
    st = anchor_stable_mask(level, am, min_level) & inside
    rows = []
    for k in CHANGE_CLASSES:
        m = inside & (am == k)
        n, ns = int(m.sum()), int((m & st).sum())
        if n:
            rows.append({"class": k, "name": CLASS_NAMES.get(k, str(k)), "area_ha": n * px_ha, "stable_ha": ns * px_ha, "stable_pct": 100.0 * ns / n, "train_ha": ns * px_ha})
    return rows


def build_anchor_ctx(year, anchor_year, anchor_map, stab, px_ha, min_level=1, half_life=ANCHOR_HALF_LIFE, source="mémoire"):
    """Contexte de l'ancre pour l'année en cours (utilisé par le masque « Ancre », l'optimiseur et le Random Forest)."""
    return {"active": True, "year": int(year), "anchor_year": int(anchor_year), "anchor_map": np.asarray(anchor_map, np.uint8), "level": stab["level"], "share": stab["share"],
            "min_level": int(min_level), "px_ha": float(px_ha), "weight": anchor_temporal_weight(int(year) - int(anchor_year), half_life), "half_life": half_life,
            "n_bands": stab["n_bands"], "stats": stab["stats"], "source": source, "labels_cache": {}}


def anchor_stable(ctx, min_level=None):
    return anchor_stable_mask(ctx["level"], ctx["anchor_map"], ctx["min_level"] if min_level is None else int(min_level))


def anchor_inherit_mask(ctx, k, min_level=None):
    """Pixels spectralement stables dont la classe dans l'ancre est k : ils HÉRITENT de la classe k."""
    return anchor_stable(ctx, min_level) & (ctx["anchor_map"] == int(k))


def anchor_other_stable_mask(ctx, k, min_level=None):
    """Pixels stables d'une AUTRE classe de l'ancre : ils ne doivent pas être revendiqués par les seuils / le RF de la classe k."""
    return anchor_stable(ctx, min_level) & (ctx["anchor_map"] != int(k))


def anchor_rf_labels(ctx, min_level=None):
    """Étiquettes de classes (1-9) des pixels stables pour entraîner le Random Forest d'une étape, sans polygones dessinés."""
    ml = ctx["min_level"] if min_level is None else int(min_level)
    if ml not in ctx["labels_cache"]:
        ctx["labels_cache"][ml] = anchor_training_labels(ctx["anchor_map"], ctx["level"], ml)
    return ctx["labels_cache"][ml]


def anchor_block_split(candidates, block=None, val_fraction=0.3, seed=11, y=None):
    """
    Séparation entraînement / validation par BLOCS spatiaux (des pixels voisins, très corrélés, ne se retrouvent jamais des deux côtés).
    block = None : taille adaptée à l'image (au plus 64 px, au moins 8 px, environ 8 blocs par côté). y (facultatif) : si l'entraînement ne contient pas
    au moins deux classes, repli sur une séparation aléatoire.
    """
    rows, cols = candidates.shape
    block = int(block) if block else int(max(8, min(64, min(rows, cols) // 8)))
    br, bc = (np.arange(rows) // block)[:, None], (np.arange(cols) // block)[None, :]
    nbc = (cols + block - 1) // block
    bid = br * nbc + bc
    rng = np.random.default_rng(seed)
    is_val = rng.random(int(bid.max()) + 1) < val_fraction
    val = candidates & is_val[bid]
    train = candidates & ~is_val[bid]
    bad = train.sum() == 0 or val.sum() == 0 or (y is not None and len(np.unique(np.asarray(y)[train])) < 2)
    if bad:                                           # trop peu de blocs (ou une seule classe à l'entraînement) : séparation aléatoire de repli
        idx = np.flatnonzero(candidates.ravel())
        rng.shuffle(idx)
        cut = max(1, int(len(idx) * (1 - val_fraction)))
        train, val = np.zeros(candidates.shape, bool), np.zeros(candidates.shape, bool)
        train.ravel()[idx[:cut]] = True
        val.ravel()[idx[cut:]] = True
    return train, val


def stack_band_names(stack_path):
    """Noms des bandes d'un Stack (fichier .hdr ENVI « band names », sinon descriptions GDAL, sinon B1, B2...) : la MÊME règle que la lecture du Stack."""
    ds = gdal.Open(stack_path, gdal.GA_ReadOnly)
    if ds is None:
        raise RuntimeError(f"Impossible d'ouvrir le stack de l'ancre : {stack_path}")
    try:
        names = []
        hdr = os.path.splitext(stack_path)[0] + ".hdr"
        if os.path.exists(hdr):
            try:
                m = re.search(r'band names\s*=\s*\{([^}]+)\}', open(hdr, "r", encoding="utf-8", errors="ignore").read(), re.I | re.S)
                if m:
                    names = [x.strip().replace('"', '').replace("'", "") for x in m.group(1).split(",")]
            except Exception:
                names = []
        if len(names) != ds.RasterCount:
            names = [(ds.GetRasterBand(i).GetDescription() or f"B{i}") for i in range(1, ds.RasterCount + 1)]
        return names
    finally:
        ds = None


def anchor_band_reader(stack_path, idx, rows, cols, geo_tf, proj_wkt):
    """Une bande (indice 0) du Stack de l'ancre sur la grille de l'année en cours : float32, NoData -> NaN."""
    arr, nod = _read_raster_band_on_grid(stack_path, int(idx) + 1, rows, cols, geo_tf, proj_wkt)
    if arr is None:
        return np.full((rows, cols), np.nan, np.float32)
    a = np.asarray(arr, dtype=np.float32).copy()
    if nod is not None and np.isfinite(nod):
        a[a == np.float32(nod)] = np.nan
    a[a == np.float32(-9999.0)] = np.nan
    a[~np.isfinite(a)] = np.nan
    return a


def get_map_for_year(output_dir, year, rows, cols, geo_tf, proj_wkt):
    """Carte finale EXACTE d'une année : mémoire (même grille) d'abord, sinon fichier LULC_<AREA_TAG>_<année>.tif. (tableau, source) ou (None, None)."""
    y = int(year)
    m = PREVIOUS_MAPS.get(y)
    if m is not None and m["arr"].shape == (rows, cols) and _same_grid(m["geo_tf"], geo_tf):
        return m["arr"], "mémoire"
    p = find_lulc_map(output_dir, y)
    if p:
        arr = load_previous_lulc(p, rows, cols, geo_tf, proj_wkt)
        if arr is not None:
            return arr, "fichier"
    return None, None


def anchor_summary_lines(ctx, stage_class=None):
    """Texte (HTML) pour le rapport d'aperçu : ancre, poids temporel, part stable, pixels hérités par la classe de l'étape."""
    if not ctx or not ctx.get("active"):
        return []
    px = ctx["px_ha"]
    st = anchor_stable(ctx)
    inside = (ctx["anchor_map"] >= 1) & (ctx["anchor_map"] <= 9)
    n_in, n_st = int(inside.sum()), int((st & inside).sum())
    out = [f"<br><b>⚓ Ancre {ctx['anchor_year']} → {ctx['year']}</b> : {ctx['n_bands']} bandes comparées | poids du transfert <b>{ctx['weight']:.2f}</b> "
           f"(demi-vie {ctx['half_life']:.0f} ans) | pixels spectralement stables : <b>{100.0 * n_st / max(n_in, 1):.0f} %</b> ({n_st * px:,.0f} ha)<br>"]
    if stage_class:
        k = int(stage_class)
        n_k = int((inside & (ctx["anchor_map"] == k)).sum())
        n_h = int(anchor_inherit_mask(ctx, k).sum())
        out.append(f"• « {CLASS_NAMES.get(k, k)} » dans l'ancre : {n_k * px:,.0f} ha, dont stables (héritables) <b>{n_h * px:,.0f} ha</b> "
                   f"({100.0 * n_h / max(n_k, 1):.0f} %) ; le reste a changé spectralement : classé par seuils / RF<br>")
    return out


def export_anchor_outputs(output_dir, ctx, geo_tf, proj_wkt):
    """Fichiers de transparence de l'ancre : niveaux de confiance, part de bandes stables, étiquettes d'entraînement automatiques, tableaux par classe et par bande."""
    ay, yr, px = ctx["anchor_year"], ctx["year"], ctx["px_ha"]
    tag = f"{ay}_{yr}"
    paths = {}
    adir = anchor_dir(output_dir)                              # <résultats>/Ancre/
    paths["level"] = write_raster(os.path.join(adir, f"Anchor_Level_{tag}.tif"), ctx["level"], geo_tf, proj_wkt, gdal.GDT_Byte, 0)
    paths["share"] = write_raster(os.path.join(adir, f"Anchor_Share_{tag}.tif"), np.nan_to_num(ctx["share"], nan=-1.0).astype(np.float32), geo_tf, proj_wkt, gdal.GDT_Float32, -1)
    paths["labels"] = write_raster(os.path.join(adir, f"Anchor_Training_Labels_{tag}.tif"), anchor_rf_labels(ctx), geo_tf, proj_wkt, gdal.GDT_Byte, 0)
    rows = anchor_class_rows(ctx["anchor_map"], ctx["level"], ctx["min_level"], px)
    paths["classes"] = write_csv_rows(os.path.join(adir, f"Anchor_Classes_{tag}.csv"),
                                      [["Classe", "Surface ancre (ha)", "Stable / héritable (ha)", "Stable %", "Entraînement auto (ha)"]]
                                      + [[f"{r['class']} — {r['name']}", f"{r['area_ha']:.2f}", f"{r['stable_ha']:.2f}", f"{r['stable_pct']:.1f}", f"{r['train_ha']:.2f}"] for r in rows])
    paths["bands"] = write_csv_rows(os.path.join(adir, f"Anchor_Bands_{tag}.csv"),
                                    [["Bande", "Famille", "Décalage médian (ancre - année)", "Écart robuste (MAD)", "Demi-largeur de l'intervalle"]]
                                    + [[s["label"], s["group"], f"{s['median']:.5f}", f"{s['mad']:.5f}", f"{s['half_width']:.5f}"] for s in ctx["stats"]])
    return paths


# ====================== ANCRE : QUESTION INITIALE, ORDRE DE TRAITEMENT, DOMAINE D'UNE ÉTAPE (AJOUT) ======================
def stage_domain_from_spec(spec, active_mask, rows, cols, geo_tf, proj_wkt, stage_class=None):
    """
    Domaine sur lequel les seuils / le RF d'une étape sont ÉVALUÉS selon le masque : LIMITE ou TOTAL -> domaine actif ET masque ;
    UNION -> domaine actif (avec l'ancre : sans les pixels stables d'AUTRES classes, qui ne sont pas à revendiquer) ; aucun masque -> domaine actif.
    """
    if not spec:
        return active_mask
    if mask2_active(spec):                                        # le masque n°2 restreint d'abord le domaine
        active_mask, _i2 = restrict_domain_by_mask2(spec["mask2"], active_mask, rows, cols, geo_tf, proj_wkt)
    sp = {"source": "vector", "path": spec, "role": "boundary"} if isinstance(spec, str) else spec
    src, role = sp.get("source", "none"), sp.get("role", "boundary")
    if src == "none":
        return active_mask
    if src == "anchor":
        if not ANCHOR_CTX.get("active") or not stage_class:
            raise RuntimeError("Ancre non disponible pour cette année (aucune ancre configurée, ou cette année EST l'ancre).")
        return active_mask & ~anchor_other_stable_mask(ANCHOR_CTX, stage_class, sp.get("level") or ANCHOR_CTX["min_level"])
    mk = mask_from_spec(sp, rows, cols, geo_tf, proj_wkt, stage_class)
    if role == "union":
        return active_mask
    return active_mask & mk


def _find_year_stack(parent_dir, yr):
    """Stack d'une année dans le dossier de travail (même règle de recherche que la découverte des années) ; None si introuvable."""
    found = find_year_folder(parent_dir, str(yr))
    return pick_stack(found[1]) if found else None


def _process_order(years, anchor_cfg, order=None, anchor_ready=False):
    """
    Ordre de traitement : ASCENDANT (2000 -> 2007 -> 2015 -> 2020 -> 2025, défaut) ou DESCENDANT.
    L'ANCRE (si elle est choisie) ne passe en premier QUE si sa carte finale n'existe pas encore (anchor_ready = False) : les autres années en ont besoin. Si cette carte existe déjà
    (traitement précédent ou mémoire), l'ordre choisi est respecté : l'ancre est alors classée à sa place chronologique.
    """
    ys = sorted(years, key=lambda y: int(y), reverse=(process_order_name(order) == "descending"))
    if anchor_cfg and not anchor_ready and str(anchor_cfg["year"]) in [str(y) for y in ys]:
        a = next(y for y in ys if str(y) == str(anchor_cfg["year"]))
        return [a] + [y for y in ys if y != a]
    return ys


def _ask_anchor(parent_dir, selected_years, year_data, output_dir, target_years):
    """
    Question facultative : classer les ANCIENNES années à partir d'une ANCRE de haute précision (ex. 2025) par stabilité spectrale Stack-à-Stack.
    Retourne {"year", "stack", "min_level"} ou None. L'ancre doit être classée AVANT (même session) ou avoir sa carte finale dans le dossier de résultats.
    """
    rep_ = QMessageBox.question(
        None, "Ancre haute précision (Stack-à-Stack)",
        "Classer les ANCIENNES années à partir d'une ANCRE de haute précision (ex. 2025) ?\n\n"
        "Pour chaque ancienne année, le SPECTRE compare son Stack à celui de l'ancre : les pixels spectralement STABLES héritent de la classe de l'ancre "
        "et servent d'échantillons d'entraînement AUTOMATIQUES (aucun échantillon à dessiner) ; les pixels qui ont changé sont classés par les seuils / le RF.\n\n"
        "L'ancre sera traitée en PREMIER (ou sa carte finale doit déjà exister dans le dossier de résultats).\n\n"
        "Oui = utiliser une ancre.\nNon = classification inchangée.", QMB_YES | QMB_NO, QMB_NO)
    if rep_ != QMB_YES:
        return None
    years = sorted({str(y) for y in target_years}, key=int)
    item, ok_ = QInputDialog.getItem(None, "Ancre", "Année de l'ANCRE (haute précision) :", years, len(years) - 1, False)
    if not ok_ or not item:
        return None
    ay = int(item)
    stack = (year_data.get(str(ay)) or {}).get("stack") or _find_year_stack(parent_dir, ay)
    if not stack:
        QMessageBox.warning(None, "Ancre", f"Stack de l'ancre {ay} introuvable dans\n{parent_dir}")
        return None
    in_run = str(ay) in [str(y) for y in selected_years]
    has_file = (find_lulc_map(output_dir, ay) is not None) or int(ay) in PREVIOUS_MAPS
    if not (in_run or has_file):
        QMessageBox.warning(None, "Ancre", f"Aucune carte finale de l'ancre {ay} : sélectionnez {ay} parmi les années à traiter (elle sera classée en premier), "
                                           f"ou classez-la d'abord.")
        return None
    lvl = QMessageBox.question(None, "Ancre : niveau de stabilité",
                               "Quels pixels sont jugés STABLES ?\n\nOui = haute confiance seulement (≥ 90 % des bandes dans l'intervalle)\n"
                               "Non = haute confiance + modérée (≥ 75 % des bandes)", QMB_YES | QMB_NO, QMB_YES)
    return {"year": ay, "stack": stack, "min_level": 1 if lvl == QMB_YES else 2}


# ====================== RAPPORT HTML D'UNE ANNÉE (AJOUT) ======================
def build_year_report_html(year, areas_rows, px_ha, stage_rows, anchor_meta=None, analysis=None, files=None, generated=None, fill=None, reviews=None):
    """
    Rapport autonome (HTML) d'une année classée : surfaces par classe, calibration de chaque étape (mode, masque, seuils renseignés), ancre éventuelle,
    changement vs l'année la plus proche (net / échange / déplacement, alertes) et liste des fichiers produits.
    areas_rows = [(code, nom, ha, %)] ; stage_rows = [{"stage", "class", "mode", "mask", "thresholds": {clé: valeur}}] ; files = [(libellé, chemin relatif)].
    """
    import html as _h
    e = lambda x: _h.escape(str(x))
    css = ("body{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#222;max-width:1100px}h1{font-size:22px}h2{font-size:17px;margin-top:26px;border-bottom:2px solid #ddd;padding-bottom:4px}"
           "table{border-collapse:collapse;margin:8px 0}th,td{border:1px solid #ccc;padding:4px 9px;font-size:13px;text-align:left}th{background:#f2f2f2}td.n{text-align:right}"
           ".red{color:#c62828;font-weight:bold}.orange{color:#ef6c00;font-weight:bold}.ok{color:#2e7d32}.sw{display:inline-block;width:12px;height:12px;margin-right:6px;vertical-align:middle;border:1px solid #888}"
           ".small{color:#666;font-size:12px}")
    out = [f"<!DOCTYPE html><html lang='fr'><head><meta charset='utf-8'><title>Rapport LULC {e(year)}</title><style>{css}</style></head><body>",
           f"<h1>Rapport de classification LULC — {e(year)}</h1>",
           f"<p class='small'>Généré le {e(generated or time.strftime('%Y-%m-%d %H:%M'))} · surface d'un pixel : {px_ha:.4f} ha · 8 classes (Forest inclut l'ancien Matorral)</p>"]
    # ---- surfaces
    total = sum(r[2] for r in areas_rows) or 1.0
    out.append("<h2>Surfaces par classe</h2><table><tr><th>Classe</th><th>Surface (ha)</th><th>Surface (km²)</th><th>% de la zone d'étude</th></tr>")
    for code, name, ha, pct in areas_rows:
        sw = ""
        try:
            c = CLASS_COLORS[code]
            sw = f"<span class='sw' style='background:rgb({c.red()},{c.green()},{c.blue()})'></span>"
        except Exception:
            pass
        out.append(f"<tr><td>{sw}{e(code)} — {e(name)}</td><td class='n'>{ha:,.2f}</td><td class='n'>{ha / 100:,.2f}</td><td class='n'>{pct:.2f}</td></tr>")
    out.append(f"<tr><th>Total classé</th><th class='n'>{total:,.2f}</th><th class='n'>{total / 100:,.2f}</th><th></th></tr></table>")
    # ---- étapes
    out.append("<h2>Calibration des étapes</h2><table><tr><th>Étape</th><th>Classe</th><th>Mode</th><th>Masque</th><th>Seuils renseignés (champ vide = non utilisé)</th></tr>")
    for s in stage_rows:
        th = ", ".join(f"{e(k)} = {e(v)}" for k, v in sorted((s.get("thresholds") or {}).items()) if v not in (None, ""))
        out.append(f"<tr><td>{e(s['stage'])}</td><td>{e(s['class'])}</td><td>{e(s['mode'])}</td><td>{e(s['mask'])}</td><td>{th or '<span class=small>—</span>'}</td></tr>")
    out.append("</table>")
    # ---- transitions improbables revues dans la fenêtre dédiée
    if reviews:
        out.append("<h2>Transitions improbables revues (fenêtre dédiée, par étape)</h2><table><tr><th>Étape</th><th>Transition</th><th>Surface (ha)</th><th>Gardés (ha)</th><th>Retirés (ha)</th><th>Classe de la référence (ha)</th></tr>")
        for st_, lg in sorted(reviews.items()):
            for t_ in lg.get("transitions", []):
                out.append(f"<tr><td>{e(st_)}</td><td>{e(t_['label'])}</td><td class='n'>{t_['px'] * px_ha:,.1f}</td><td class='n'>{t_.get('kept_px', t_['px'] if lg.get('result') == 'skip' else 0) * px_ha:,.1f}</td>"
                           f"<td class='n'>{t_.get('removed_px', 0) * px_ha:,.1f}</td><td class='n'>{t_.get('reference_px', 0) * px_ha:,.1f}</td></tr>")
        out.append("</table>")
    # ---- pixels complétés automatiquement (voisin le plus proche / repli Bareland)
    if fill:
        warn = fill["filled_percent"] > FILL_WARN_PERCENT
        out.append("<h2>Pixels complétés automatiquement</h2>")
        out.append(f"<p class='{'red' if warn else 'ok'}'>{'⚠ ' if warn else ''}{fill['unresolved_px'] * px_ha:,.1f} ha ({fill['filled_percent']:.2f} % de la zone d'étude) n'étaient classés par aucune des 8 étapes : "
                   f"{fill['nn_filled_px'] * px_ha:,.1f} ha par le voisin classé le plus proche, {fill['bareland_fallback_px'] * px_ha:,.1f} ha par le repli Bareland. "
                   f"{'Au-delà de ' + format(FILL_WARN_PERCENT, 'g') + ' % : revoyez la couverture des images et les seuils avant d accepter la carte. ' if warn else ''}"
                   "Cartes : <code>Controle/PreFill_Map_" + e(year) + ".tif</code> (avant remplissage) et <code>Controle/Fill_Mask_" + e(year) + ".tif</code> (1 = voisin, 2 = Bareland).</p>")
    # ---- ancre
    if anchor_meta:
        out.append(f"<h2>Ancre haute précision</h2><p>Ancre <b>{e(anchor_meta['anchor_year'])}</b> → {e(anchor_meta['year'])} · {e(anchor_meta['n_bands'])} bandes comparées · poids du transfert "
                   f"<b>{anchor_meta['weight']:.2f}</b> · niveau de stabilité ≤ {e(anchor_meta['min_level'])} · carte de l'ancre : {e(anchor_meta['source'])}. "
                   "L'ancre est un APPUI, jamais une vérité historique.</p>")
    # ---- changement
    if analysis:
        ls, px = analysis["landscape"], analysis["px_ha"]
        n = max(ls["compared_px"], 1)
        out.append(f"<h2>Changement {e(analysis.get('older_year'))} → {e(analysis.get('newer_year'))}</h2>")
        out.append(f"<p>Pixels classés aux deux dates : {ls['compared_px'] * px:,.0f} ha. Changement total <b>{100.0 * ls['changed_px'] / n:.1f} %</b> = net {100.0 * ls['net_px'] / n:.1f} % "
                   f"+ échange (swap) {100.0 * ls['exchange_px'] / n:.1f} % + déplacement {100.0 * ls['shift_px'] / n:.1f} %. "
                   "Seul le NET est une vraie variation de quantité ; échange et déplacement sont du remplacement spatial.</p>")
        hdr = change_table_headers(analysis)["classes"]
        out.append("<table><tr>" + "".join(f"<th>{e(h)}</th>" for h in hdr) + "</tr>")
        for row in change_class_table(analysis):
            out.append("<tr>" + "".join(f"<td{' class=n' if i else ''}>{e(v)}</td>" for i, v in enumerate(row)) + "</tr>")
        out.append("</table>")
        if analysis["alerts"]:
            out.append("<p><b>Transitions improbables :</b></p><ul>")
            for a in analysis["alerts"]:
                out.append(f"<li class='{'red' if a['level'] == 'red' else 'orange'}'>{'🔴' if a['level'] == 'red' else '🟠'} {e(a['text'])}</li>")
            out.append("</ul>")
        else:
            out.append("<p class='ok'>✅ Aucune transition improbable importante.</p>")
    # ---- fichiers
    if files:
        out.append("<h2>Fichiers produits</h2><ul>" + "".join(f"<li>{e(lab)} : <code>{e(rel)}</code></li>" for lab, rel in files) + "</ul>")
    out.append("</body></html>")
    return "".join(out)


def write_year_report(output_dir, year, html_text):
    """Écrit <résultats>/Rapports/Rapport_<année>.html ; retourne le chemin."""
    p = os.path.join(report_dir(output_dir), f"Rapport_{year}.html")
    with open(p, "w", encoding="utf-8") as f:
        f.write(html_text)
    return p


def stage_rows_from_presets(year, output_dir):
    """Une ligne par étape (1-8) à partir des presets enregistrés : classe, mode, masque, seuils."""
    rows = []
    for s in sorted(STAGE_POSITIVE):
        p = load_preset(year, s, output_dir) or {}
        m = p.get("mask") or {}
        mask = "aucun" if not m or m.get("source", "none") == "none" else f"{m.get('source')} / rôle {m.get('role', 'boundary')}"
        if mask2_active(m):
            mask = ("" if mask == "aucun" else mask + " + ") + f"masque n°2 ({m['mask2'].get('source')} / {'limiter' if m['mask2'].get('role') == 'limit' else 'exclure'})"
        rows.append({"stage": s, "class": CLASS_NAMES.get(next(iter(STAGE_POSITIVE[s])), "?"), "mode": p.get("mode", "—") if p else "(défaut)", "mask": mask, "thresholds": p.get("thresholds") or {}})
    return rows


# ====================== FENÊTRE DE DÉMARRAGE UNIQUE (AJOUT) ======================
# Remplace la suite de questions (mode, dossier, années, preuves, batch, reprise, ancre) par UNE fenêtre ; les choix sont mémorisés pour la prochaine fois.
RUN_SETTINGS_FILE = os.path.join(os.path.expanduser("~"), ".sdg1531_lulc_v17_settings.json")


def load_run_settings(path=None):
    """Derniers réglages utilisés ({} s'il n'y en a pas ou si le fichier est illisible)."""
    try:
        with open(path or RUN_SETTINGS_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_run_settings(settings, path=None):
    """Mémorise les réglages (jamais d'échec bloquant). Retourne True si écrit."""
    try:
        with open(path or RUN_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def detect_folder_state(parent_dir, target_years=None):
    """
    Ce que le dossier choisi contient : années disponibles (dossier + stack), zone d'étude trouvée par son nom, presets déjà enregistrés,
    années déjà terminées (point de reprise). Sert à activer / désactiver les options de la fenêtre.
    """
    target_years = list(target_years or TARGET_YEARS)
    state = {"parent_dir": parent_dir, "valid": bool(parent_dir) and os.path.isdir(parent_dir), "available_years": [], "study_area": None, "presets": 0, "completed": []}
    if not state["valid"]:
        return state
    out = os.path.join(parent_dir, "Resultats_LULC_V17_Hierarchie_Forest")
    state["output_dir"] = out
    found = discover_years(parent_dir)                             # années présentes dans le dossier (S_1999, ...) : ajoutées automatiquement à la liste
    if found:
        register_years(found)
        target_years = sorted(set(target_years) | set(found), key=int)
    state["available_years"] = _scan_available_years(parent_dir, target_years)
    state["study_area"] = _find_named_input(parent_dir, "Study_Area_Final", (".shp",))
    if os.path.isdir(out):
        state["presets"] = len(glob.glob(os.path.join(out, "Preset_*_Stage*.json")))
        state["completed"] = [y for y in load_checkpoint(out).get("completed_years", []) if y in state["available_years"]]
    return state


def default_run_settings(state, last=None):
    """Réglages proposés : ceux de la dernière fois s'ils sont compatibles avec le dossier, sinon des valeurs sûres (tout interactif, toutes les années)."""
    last = last or {}
    avail = state.get("available_years", [])
    years = [y for y in last.get("years", []) if y in avail] or list(avail)
    anchor = dict(last.get("anchor") or {})
    return {"parent_dir": state.get("parent_dir", ""), "years": years,
            "batch": bool(last.get("batch")) and state.get("presets", 0) > 0,
            "resume": bool(state.get("completed")) and bool(last.get("resume", True)),
            "evidence": bool(last.get("evidence", False)),
            "review_implausible": bool(last.get("review_implausible", True)),
            "order": last.get("order") if last.get("order") in PROCESS_ORDERS else "ascending",
            "anchor": {"use": bool(anchor.get("use", False)), "year": str(anchor.get("year", max(avail) if avail else "")), "min_level": int(anchor.get("min_level", 1))},
            "study_area": state.get("study_area") or ""}


def validate_run_settings(s, state):
    """Liste des problèmes qui empêchent de lancer (vide = OK)."""
    errs = []
    if not state.get("valid"):
        errs.append("Choisissez le dossier principal (celui qui contient S_1985, S_2000...).")
        return errs
    if not s.get("years"):
        errs.append("Cochez au moins une année à traiter.")
    if not s.get("study_area") or not os.path.exists(s["study_area"]):
        errs.append("La zone d'étude (Study_Area_Final.shp) est introuvable : indiquez-la.")
    a = s.get("anchor") or {}
    if a.get("use"):
        ay = str(a.get("year", ""))
        if ay not in state.get("available_years", []):
            errs.append(f"Ancre {ay or '?'} : aucun dossier d'année avec Stack n'a été trouvé pour cette année.")
        elif ay not in s.get("years", []) and not os.path.exists(os.path.join(state.get("output_dir", ""), LULC_SUBDIR, f"LULC_{AREA_TAG}_{ay}.tif")) \
                and not os.path.exists(os.path.join(state.get("output_dir", ""), f"LULC_{AREA_TAG}_{ay}.tif")):
            errs.append(f"Ancre {ay} : cochez {ay} parmi les années à traiter (elle sera classée en premier) ou classez-la d'abord.")
    return errs


def _resolve_anchor(a, parent_dir, selected_years, year_data, output_dir, target_years):
    """Réglage « ancre » de la fenêtre de démarrage -> {"year", "stack", "min_level"} ou None (avec avertissement si le réglage est inutilisable). Aucune question."""
    if not a or not a.get("use"):
        return None
    ay = int(a["year"])
    stack = (year_data.get(str(ay)) or {}).get("stack") or _find_year_stack(parent_dir, ay)
    if not stack:
        QMessageBox.warning(None, "Ancre", f"Stack de l'ancre {ay} introuvable dans\n{parent_dir}\nL'ancre est désactivée.")
        return None
    if not (str(ay) in [str(y) for y in selected_years] or find_lulc_map(output_dir, ay) is not None or int(ay) in PREVIOUS_MAPS):
        QMessageBox.warning(None, "Ancre", f"Aucune carte finale de l'ancre {ay} : cochez {ay} parmi les années à traiter (elle sera classée en premier) ou classez-la d'abord.\nL'ancre est désactivée.")
        return None
    return {"year": ay, "stack": stack, "min_level": 1 if int(a.get("min_level", 1)) <= 1 else 2}


class RunSettingsDialog(QDialog):
    """UNE fenêtre au démarrage : dossier, années, mode, reprise, preuves supplémentaires, ancre, zone d'étude."""

    def __init__(self, last=None):
        super().__init__(None)
        self.setWindowTitle(f"LULC {AREA_NAME} — Paramètres de l'exécution")
        self.resize(760, 560)
        self.last = last or {}
        self.state = detect_folder_state(self.last.get("parent_dir", ""))
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("<b>Tout se règle ici, en une seule fois.</b> Vos choix sont mémorisés pour la prochaine exécution."))
        # ---- dossier
        g1 = QGroupBox("1. Dossier principal (celui qui contient S_1985, S_2000, ...)")
        l1 = QHBoxLayout(g1)
        self.le_dir = QLineEdit(self.last.get("parent_dir", ""))
        b_dir = QPushButton("Parcourir…")
        b_dir.clicked.connect(self.browse_dir)
        self.le_dir.editingFinished.connect(self.refresh_from_folder)
        l1.addWidget(self.le_dir, 1)
        l1.addWidget(b_dir)
        lay.addWidget(g1)
        # ---- zone d'étude
        g2 = QGroupBox("2. Zone d'étude (Study_Area_Final.shp)")
        l2 = QHBoxLayout(g2)
        self.le_study = QLineEdit(self.last.get("study_area", ""))
        b_study = QPushButton("Parcourir…")
        b_study.clicked.connect(self.browse_study)
        l2.addWidget(self.le_study, 1)
        l2.addWidget(b_study)
        lay.addWidget(g2)
        # ---- années
        g3 = QGroupBox("3. Années à traiter (cochez ; l'ORDRE de traitement se choisit en 4) — les années du dossier (S_1999, ...) sont détectées automatiquement")
        l3 = QHBoxLayout(g3)
        self.years_box = QHBoxLayout()
        l3.addLayout(self.years_box)
        self.year_checks = {}
        for y in sorted(TARGET_YEARS, key=int):
            cb = QCheckBox(str(y))
            cb.toggled.connect(self.update_anchor_years)
            self.year_checks[str(y)] = cb
            self.years_box.addWidget(cb)
        b_all, b_none = QPushButton("Toutes"), QPushButton("Aucune")
        b_all.clicked.connect(lambda *_: [c.setChecked(True) for c in self.year_checks.values() if c.isEnabled()])
        b_none.clicked.connect(lambda *_: [c.setChecked(False) for c in self.year_checks.values()])
        l3.addWidget(b_all)
        l3.addWidget(b_none)
        lay.addWidget(g3)
        # ---- mode / reprise
        g4 = QGroupBox("4. Mode d'exécution")
        l4 = QVBoxLayout(g4)
        self.rb_inter = QRadioButton("Interactif : une fenêtre de calibration par étape (à choisir la première fois)")
        self.rb_batch = QRadioButton("Batch : rejouer automatiquement les presets enregistrés (sans ouvrir les étapes)")
        self.rb_inter.setChecked(True)
        self.chk_resume = QCheckBox("Reprendre les années déjà terminées (point de reprise)")
        self.lbl_state = QLabel("")
        self.lbl_state.setWordWrap(True)
        row_o = QHBoxLayout()
        row_o.addWidget(QLabel("<b>Ordre de traitement des années :</b>"))
        self.cb_order = QComboBox()
        self.cb_order.addItems(["ASCENDANT : de la plus ancienne à la plus récente (2000 → 2025) — chaque année est comparée à la précédente",
                                "DESCENDANT : de la plus récente à la plus ancienne (2025 → 2000) — chaque année est comparée à la suivante"])
        self.cb_order.setCurrentIndex(0 if (self.last.get("order") or "ascending") != "descending" else 1)
        row_o.addWidget(self.cb_order, 1)
        for w in (self.rb_inter, self.rb_batch, self.chk_resume):
            l4.addWidget(w)
        l4.addLayout(row_o)
        l4.addWidget(self.lbl_state)
        lay.addWidget(g4)
        # ---- options avancées
        g5 = QGroupBox("5. Options avancées (facultatives : à ignorer pour une première utilisation)")
        l5 = QVBoxLayout(g5)
        self.chk_evidence = QCheckBox("Preuves supplémentaires pour Fallow / Rangeland / Bareland (NDVI multi-années, pluies CHIRPS, MNT, LPD) : les fichiers seront demandés ensuite")
        self.chk_evidence.setChecked(bool(self.last.get("evidence", False)))
        self.chk_anchor = QCheckBox("Ancre haute précision : classer les anciennes années à partir d'une année de référence (stabilité spectrale Stack-à-Stack)")
        row = QHBoxLayout()
        row.addWidget(QLabel("   Année de l'ancre :"))
        self.cb_anchor_year = QComboBox()
        row.addWidget(self.cb_anchor_year)
        row.addWidget(QLabel("Stabilité :"))
        self.cb_anchor_level = QComboBox()
        self.cb_anchor_level.addItems(ANCHOR_LEVEL_LABELS)
        row.addWidget(self.cb_anchor_level, 1)
        self.chk_review = QCheckBox("Fenêtre des TRANSITIONS IMPROBABLES à la fin de chaque étape (si une carte de référence existe) : corriger avant l'étape suivante")
        self.chk_review.setChecked(bool(self.last.get("review_implausible", True)))
        for w in (self.chk_evidence, self.chk_review, self.chk_anchor):
            l5.addWidget(w)
        l5.addLayout(row)
        lay.addWidget(g5)
        self.lbl_err = QLabel("")
        self.lbl_err.setWordWrap(True)
        lay.addWidget(self.lbl_err)
        btns = QHBoxLayout()
        b_run, b_cancel = QPushButton("▶ Lancer"), QPushButton("Annuler")
        b_run.clicked.connect(self.on_run)
        b_cancel.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(b_run)
        btns.addWidget(b_cancel)
        lay.addLayout(btns)
        self.refresh_from_folder(initial=True)

    # ---- logique (testable) ----
    def browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Sélectionner le dossier principal contenant S_1985, S_2000...", self.le_dir.text() or "")
        if d:
            self.le_dir.setText(d)
            self.refresh_from_folder()

    def browse_study(self):
        f, _ = QFileDialog.getOpenFileName(self, "Zone d'étude (Study_Area_Final.shp)", self.le_dir.text() or "", "Shapefile (*.shp)")
        if f:
            self.le_study.setText(f)

    def refresh_from_folder(self, initial=False):
        """Après le choix du dossier : années disponibles, presets, reprise possible, zone d'étude trouvée."""
        st = detect_folder_state(self.le_dir.text().strip(), TARGET_YEARS)
        self.state = st
        d = default_run_settings(st, self.last)
        sync = getattr(self, "_sync_year_checks", None)
        if sync is not None:
            sync()                                                  # une année découverte dans le dossier (ex. 1999) obtient sa case
            d = default_run_settings(st, self.last)
        for y, cb in self.year_checks.items():
            has = y in st["available_years"]
            cb.setEnabled(has)
            cb.blockSignals(True)
            cb.setChecked(has and y in d["years"])
            cb.blockSignals(False)
        self.rb_batch.setEnabled(st["presets"] > 0)
        (self.rb_batch if d["batch"] else self.rb_inter).setChecked(True)
        self.chk_resume.setEnabled(bool(st["completed"]))
        self.chk_resume.setChecked(d["resume"])
        if st.get("study_area") and not (initial and self.le_study.text().strip()):
            self.le_study.setText(st["study_area"])
        a = d["anchor"]
        self.chk_review.setChecked(d["review_implausible"])
        self.cb_order.setCurrentIndex(0 if d["order"] != "descending" else 1)
        self.chk_anchor.setChecked(a["use"] and a["year"] in st["available_years"])
        self.cb_anchor_level.setCurrentIndex(0 if a["min_level"] <= 1 else 1)
        self.update_anchor_years()
        if a["year"] in st["available_years"]:
            self.cb_anchor_year.setCurrentIndex(max(0, self.cb_anchor_year.findText(a["year"])))
        if not st["valid"]:
            self.lbl_state.setText("Choisissez le dossier principal.")
        else:
            bad = [r_["message"] for r_ in year_folder_report(st["parent_dir"]) if not r_["ok"]]
            for m_ in bad:
                print("[Années] ⚠ " + m_)
            self.lbl_state.setText(f"Années trouvées : {', '.join(st['available_years']) or 'aucune'} · presets enregistrés : {st['presets']} · années déjà terminées : {', '.join(st['completed']) or 'aucune'}"
                                   + ("".join(f"\n⚠ {m_}" for m_ in bad)))

    def _sync_year_checks(self):
        """Une case à cocher par année de TARGET_YEARS (années du dossier incluses) : les cases existantes gardent leur état, les nouvelles apparaissent à leur place chronologique."""
        years = sorted({str(y) for y in TARGET_YEARS}, key=int)
        if sorted(self.year_checks, key=int) == years:
            return
        old = {y: cb.isChecked() for y, cb in self.year_checks.items()}
        for cb in self.year_checks.values():
            self.years_box.removeWidget(cb)
            cb.setParent(None)
            cb.deleteLater()
        self.year_checks = {}
        for y in years:
            cb = QCheckBox(y)
            cb.setChecked(old.get(y, False))
            cb.toggled.connect(self.update_anchor_years)
            self.years_box.addWidget(cb)
            self.year_checks[y] = cb

    def update_anchor_years(self, *_a):
        cur = self.cb_anchor_year.currentText()
        self.cb_anchor_year.clear()
        self.cb_anchor_year.addItems(sorted(self.state.get("available_years", []), key=int))
        if cur:
            self.cb_anchor_year.setCurrentIndex(max(0, self.cb_anchor_year.findText(cur)))

    def get_settings(self):
        return {"parent_dir": self.le_dir.text().strip(), "years": [y for y in sorted(self.year_checks, key=int) if self.year_checks[y].isChecked()],
                "batch": bool(self.rb_batch.isChecked()), "resume": bool(self.chk_resume.isChecked()), "evidence": bool(self.chk_evidence.isChecked()), "review_implausible": bool(self.chk_review.isChecked()),
                "order": "descending" if self.cb_order.currentIndex() == 1 else "ascending",
                "anchor": {"use": bool(self.chk_anchor.isChecked()), "year": self.cb_anchor_year.currentText(), "min_level": 1 if self.cb_anchor_level.currentIndex() == 0 else 2},
                "study_area": self.le_study.text().strip()}

    def on_run(self):
        s = self.get_settings()
        errs = validate_run_settings(s, self.state)
        if errs:
            self.lbl_err.setText("<span style='color:#c62828'>" + "<br>".join("• " + e for e in errs) + "</span>")
            return
        self.settings = s
        self.accept()


def _ask_run_settings(settings_path=None):
    """Affiche la fenêtre unique de démarrage ; retourne les réglages validés (et les mémorise). Annuler = arrêt."""
    dlg = RunSettingsDialog(load_run_settings(settings_path))
    res = show_dialog(dlg)
    if not res or not getattr(dlg, "settings", None):
        raise RuntimeError("Opération annulée.")
    s = dlg.settings
    save_run_settings(s, settings_path)
    return s


# ====================== FENÊTRE DES TRANSITIONS IMPROBABLES (AJOUT) ======================
# À la fin de chaque étape interactive (après « Valider »), si des pixels que l'étape vient de classer constituent une transition IMPROBABLE par rapport à la carte de référence
# (ex. Built-up -> Rangeland, Bareland -> Forest), une fenêtre INDÉPENDANTE s'ouvre : seules ces transitions y sont affichées (tableau + carte) et on peut les corriger AVANT l'étape suivante :
#   - garder, retirer de cette étape (les pixels restent non classés, disponibles pour les étapes suivantes) ou reprendre la classe de la carte de référence ;
#   - par transition entière, ou localement en dessinant un polygone ; - ou rouvrir l'étape pour ajuster les seuils.
IMPLAUSIBLE_REVIEW_MIN_PX = 20            # en dessous de ce nombre de pixels, une transition improbable n'ouvre pas la fenêtre (bruit)
REVIEW_ACTIONS = ["keep", "remove", "reference"]
REVIEW_ACTION_LABELS = ["Garder cette transition", "Retirer de cette étape (pixels non classés, disponibles aux étapes suivantes)", "Reprendre la classe de la carte de référence"]
REVIEW_PALETTE = [(220, 50, 50), (255, 140, 0), (150, 70, 200), (0, 170, 170), (30, 120, 220), (200, 60, 160), (110, 110, 110), (120, 160, 40), (160, 100, 60)]
REVIEW_HIGHLIGHT = 200
STAGE_BACKGROUND = {"path": ""}            # fond de carte de la dernière fenêtre d'étape (réutilisé par la fenêtre des transitions)


def implausible_label(pair):
    """« Built-up → Rangeland » : transition chronologique (ancienne année → année récente)."""
    return f"{CLASS_NAMES.get(pair[0], pair[0])} → {CLASS_NAMES.get(pair[1], pair[1])}"


def implausible_pixel_sets(c_mask, prev_map, class_code, reverse, min_px=IMPLAUSIBLE_REVIEW_MIN_PX):
    """
    Transitions IMPROBABLES parmi les pixels positifs de la classe de l'étape. La transition est chronologique : si la référence est PLUS ANCIENNE, (référence -> classe de l'étape) ;
    si elle est PLUS RÉCENTE (ordre décroissant), (classe de l'étape -> référence). Ne retient que les paires de IMPLAUSIBLE_TRANSITIONS portant sur au moins min_px pixels.
    Retourne [{"ref_class", "pair", "mask", "px"}] par nombre de pixels décroissant.
    """
    c = np.asarray(c_mask, bool)
    prev = np.asarray(prev_map)
    out = []
    if not c.any():
        return out
    for r in sorted(set(np.unique(prev[c]).tolist()) - {0, int(class_code)}):
        pair = (int(class_code), int(r)) if reverse else (int(r), int(class_code))
        if pair not in IMPLAUSIBLE_TRANSITIONS:
            continue
        m = c & (prev == r)
        n = int(np.count_nonzero(m))
        if n >= int(min_px):
            out.append({"ref_class": int(r), "pair": pair, "mask": m, "px": n})
    out.sort(key=lambda d: -d["px"])
    return out


def apply_implausible_decisions(c_mask, prev_map, sets, actions, polygon_edits=None):
    """
    Applique les décisions : une action par transition (keep / remove / reference), puis des corrections LOCALES (polygones, dans l'ordre : la dernière l'emporte) qui ne touchent
    que des pixels de transition improbable. remove : le pixel quitte la classe de l'étape (non classé) ; reference : il prend la classe de la carte de référence.
    Retourne (nouveaux pixels positifs, pixels à affecter à la classe de la référence, résumé).
    """
    c = np.asarray(c_mask, bool)
    code = {"keep": 1, "remove": 2, "reference": 3}
    act = np.zeros(c.shape, np.uint8)
    for s, a in zip(sets, actions):
        act[s["mask"]] = code[a]
    any_imp = act > 0
    for pm, a in (polygon_edits or []):
        act[np.asarray(pm, bool) & any_imp] = code[a]
    remove, ref = act == 2, act == 3
    new_c = c & ~(remove | ref)
    summ = {"kept_px": int(np.count_nonzero(act == 1)), "removed_px": int(np.count_nonzero(remove)), "reference_px": int(np.count_nonzero(ref)),
            "polygons": len(polygon_edits or []), "by_transition": []}
    for s, a in zip(sets, actions):
        m = s["mask"]
        summ["by_transition"].append({"pair": list(s["pair"]), "label": implausible_label(s["pair"]), "px": s["px"], "kept_px": int(np.count_nonzero(act[m] == 1)),
                                      "removed_px": int(np.count_nonzero(act[m] == 2)), "reference_px": int(np.count_nonzero(act[m] == 3)), "action": a})
    return new_c, ref, summ


def implausible_overlay_codes(shape, sets, selected=None):
    """Carte des transitions improbables : 0 = rien ; 1..9 = n° de la transition ; REVIEW_HIGHLIGHT = la transition sélectionnée dans le tableau."""
    out = np.zeros(shape, np.uint8)
    for i, s in enumerate(sets):
        out[s["mask"]] = min(i + 1, 9)
    if selected is not None and 0 <= selected < len(sets):
        out[sets[selected]["mask"]] = REVIEW_HIGHLIGHT
    return out


def review_implausible_stage(c_mask, prev_map, class_code, reverse, show_review, reopen=None, min_px=IMPLAUSIBLE_REVIEW_MIN_PX):
    """
    Boucle de contrôle d'UNE étape : tant qu'il existe des transitions improbables, show_review(sets, c) propose la fenêtre ; elle retourne
    {"result": "apply" | "skip" | "reopen", "actions": [...], "polygons": [(masque, action)]}. « reopen » rappelle reopen() (nouvelle calibration de l'étape) puis recommence.
    Retourne (pixels positifs, pixels à affecter à la classe de la référence, journal).
    """
    c = np.asarray(c_mask, bool)
    reopened = 0
    while True:
        sets = implausible_pixel_sets(c, prev_map, class_code, reverse, min_px)
        if not sets:
            return c, np.zeros(c.shape, bool), {"reviewed": reopened > 0, "result": "none", "reopened": reopened, "transitions": []}
        res = show_review(sets, c) or {"result": "skip"}
        if res.get("result") == "reopen" and reopen is not None:
            c = np.asarray(reopen(), bool)
            reopened += 1
            continue
        if res.get("result") in ("skip", "reopen"):
            return c, np.zeros(c.shape, bool), {"reviewed": True, "result": "skip", "reopened": reopened,
                                                "transitions": [{"pair": list(s["pair"]), "label": implausible_label(s["pair"]), "px": s["px"], "action": "keep"} for s in sets]}
        new_c, ref, summ = apply_implausible_decisions(c, prev_map, sets, res["actions"], res.get("polygons"))
        return new_c, ref, dict(summ, reviewed=True, result="apply", reopened=reopened, transitions=summ["by_transition"])


def apply_stage_review(c0, prev_map, class_code, reverse, lulc, pixel_area_ha, show, reopen, stage_n, stage_review_log, min_px=IMPLAUSIBLE_REVIEW_MIN_PX):
    """
    Contrôle des transitions improbables d'UNE étape + effets : les pixels « Reprendre la classe de la référence » reçoivent cette classe dans `lulc` (s'ils sont encore non classés),
    le journal de l'étape est enregistré et résumé dans la console. Retourne les nouveaux pixels positifs de l'étape.
    """
    c_new, ref_assign, log = review_implausible_stage(c0, prev_map, class_code, reverse, show, reopen, min_px)
    if log.get("reviewed"):
        free = ref_assign & (lulc == 0)
        if free.any():
            lulc[free] = prev_map[free]
        log["pixel_ha"] = pixel_area_ha
        stage_review_log[stage_n] = log
        print(f"    [Transitions improbables] étape {stage_n} : " + ("ignorées (tout gardé)" if log.get("result") == "skip" else
              f"gardés {log['kept_px'] * pixel_area_ha:,.1f} ha · retirés {log['removed_px'] * pixel_area_ha:,.1f} ha · classe de la référence {log['reference_px'] * pixel_area_ha:,.1f} ha")
              + (f" · étape rouverte {log['reopened']} fois" if log.get("reopened") else ""))
    return c_new


def polygon_to_mask(geom, shape, geo_tf, proj_wkt):
    """Polygone QGIS -> masque de pixels sur la grille de l'étape (rasterisation GDAL)."""
    rows, cols = shape
    ds = gdal.GetDriverByName("MEM").Create("", cols, rows, 1, gdal.GDT_Byte)
    ds.SetGeoTransform(geo_tf)
    ds.SetProjection(proj_wkt)
    band = ds.GetRasterBand(1)
    band.Fill(0)
    vds = ogr.GetDriverByName("Memory").CreateDataSource("review_mem")
    srs = osr.SpatialReference()
    try:
        srs.ImportFromWkt(proj_wkt)
    except Exception:
        srs = None
    lyr = vds.CreateLayer("poly", srs=srs, geom_type=ogr.wkbPolygon)
    feat = ogr.Feature(lyr.GetLayerDefn())
    feat.SetGeometry(ogr.CreateGeometryFromWkb(bytes(geom.asWkb())))
    lyr.CreateFeature(feat)
    gdal.RasterizeLayer(ds, [1], lyr, burn_values=[1])
    return band.ReadAsArray().astype(bool)


class ImplausibleTransitionsDialog(QDialog):
    """Fenêtre INDÉPENDANTE : seules les transitions improbables de l'étape (tableau + carte) ; corrections avant l'étape suivante."""

    def __init__(self, info, sets, prev_map, geo_tf, proj_wkt, pixel_area_ha, temp_folder, background_path=""):
        super().__init__(None)
        self.info, self.sets, self.prev_map = info, sets, prev_map
        self.geo_tf, self.proj_wkt, self.pixel_area_ha, self.temp_folder, self.background_path = geo_tf, proj_wkt, pixel_area_ha, temp_folder, background_path
        self.shape = sets[0]["mask"].shape
        self.polygons = []
        self.result_info = {"result": "skip", "actions": ["keep"] * len(sets), "polygons": []}
        self.setWindowTitle(f"Transitions improbables — {info.get('title', '')}")
        self.resize(1400, 860)
        root = QVBoxLayout(self)
        O, N = (info["ref_year"], info["year"]) if not info.get("reverse") else (info["year"], info["ref_year"])
        self.lbl_head = QLabel(f"<b>{info.get('title', '')} — transitions improbables {O} → {N}</b> (année en cours : {info['year']} · référence : {info['ref_year']}).<br>"
                               "Seules les transitions improbables sont affichées. Choisissez une action par transition, ou corrigez localement en dessinant un polygone, puis « Appliquer ». "
                               "<i>Retirer</i> laisse les pixels non classés (les étapes suivantes peuvent les classer) ; <i>Reprendre la référence</i> leur donne la classe de la carte de référence.")
        self.lbl_head.setWordWrap(True)
        root.addWidget(self.lbl_head)
        splitter = QSplitter()
        # ---- carte
        left = QWidget()
        lv = QVBoxLayout(left)
        self.canvas = QgsMapCanvas()
        self.canvas.setCanvasColor(QColor(245, 245, 245))
        lv.addWidget(self.canvas, 1)
        nav = QHBoxLayout()
        self.btn_pan, self.btn_zoom_in_tool, self.btn_zoom_out, self.btn_zoom_in, self.btn_full = (QPushButton(t) for t in ("✋ Pan", "🔍+", "➖", "➕", "🌐 Extent"))
        self.btn_pan.clicked.connect(self.set_pan_mode)
        self.btn_zoom_in_tool.clicked.connect(self.set_zoom_rect_mode)
        self.btn_zoom_out.clicked.connect(self.zoom_step_out)
        self.btn_zoom_in.clicked.connect(self.zoom_step_in)
        self.btn_full.clicked.connect(self.zoom_full)
        for b in (self.btn_pan, self.btn_zoom_in_tool, self.btn_zoom_out, self.btn_zoom_in, self.btn_full):
            nav.addWidget(b)
        nav.addStretch(1)
        lv.addLayout(nav)
        self.probe_readout = QLabel("Sélectionnez une ligne du tableau pour la repérer en jaune sur la carte.")
        self.probe_readout.setWordWrap(True)
        lv.addWidget(self.probe_readout)
        splitter.addWidget(left)
        # ---- tableau + actions
        right = QWidget()
        rv = QVBoxLayout(right)
        self.table = QTableWidget(len(sets), 4)
        self.table.setHorizontalHeaderLabels(["Transition (ancienne → récente)", "Surface (ha)", "Pixels", "Action"])
        self.action_combos = []
        for i, s in enumerate(sets):
            self.table.setItem(i, 0, QTableWidgetItem(f"{i + 1}. {implausible_label(s['pair'])}"))
            self.table.setItem(i, 1, QTableWidgetItem(f"{s['px'] * pixel_area_ha:,.1f}"))
            self.table.setItem(i, 2, QTableWidgetItem(f"{s['px']:,}"))
            cb = QComboBox()
            cb.addItems(REVIEW_ACTION_LABELS)
            cb.currentIndexChanged.connect(self.update_summary)
            self.table.setCellWidget(i, 3, cb)
            self.action_combos.append(cb)
        self.table.itemSelectionChanged.connect(self.on_select)
        rv.addWidget(self.table, 2)
        quick = QHBoxLayout()
        for txt, act in (("Tout garder", "keep"), ("Tout retirer", "remove"), ("Tout reprendre la référence", "reference")):
            b = QPushButton(txt)
            b.clicked.connect(lambda _c=False, a=act: self.set_all(a))
            quick.addWidget(b)
        rv.addLayout(quick)
        box = QGroupBox("Correction locale : dessiner un polygone")
        bv = QVBoxLayout(box)
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Dans le polygone, appliquer :"))
        self.cb_poly_action = QComboBox()
        self.cb_poly_action.addItems(REVIEW_ACTION_LABELS)
        self.cb_poly_action.setCurrentIndex(1)
        r1.addWidget(self.cb_poly_action, 1)
        bv.addLayout(r1)
        r2 = QHBoxLayout()
        self.btn_poly = QPushButton("✏ Dessiner un polygone (clic gauche = sommet, clic droit = terminer)")
        self.btn_poly.clicked.connect(self.start_polygon)
        self.btn_undo_poly = QPushButton("↶ Annuler le dernier polygone")
        self.btn_undo_poly.clicked.connect(self.undo_polygon)
        r2.addWidget(self.btn_poly, 1)
        r2.addWidget(self.btn_undo_poly)
        bv.addLayout(r2)
        rv.addWidget(box)
        self.lbl_summary = QLabel("")
        self.lbl_summary.setWordWrap(True)
        rv.addWidget(self.lbl_summary)
        rv.addStretch(1)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)
        bot = QHBoxLayout()
        self.btn_apply = QPushButton("✓ Appliquer et continuer")
        self.btn_apply.clicked.connect(self.on_apply)
        self.btn_reopen = QPushButton("↩ Rouvrir l'étape (ajuster les seuils)")
        self.btn_reopen.clicked.connect(self.on_reopen)
        self.btn_skip = QPushButton("Ignorer : tout garder")
        self.btn_skip.clicked.connect(self.on_skip)
        for b in (self.btn_reopen, self.btn_skip):
            bot.addWidget(b)
        bot.addStretch(1)
        bot.addWidget(self.btn_apply)
        root.addLayout(bot)
        try:
            self.tool_pan = QgsMapToolPan(self.canvas)
            self.tool_zoom = QgsMapToolZoom(self.canvas, False)
            self.tool_poly = DirectPolygonMapTool(self.canvas, self)
        except Exception:
            self.tool_pan = self.tool_zoom = self.tool_poly = None
        self.bg_layer = None
        try:
            if background_path and os.path.exists(background_path):
                self.bg_layer = QgsRasterLayer(background_path, "Fond")
        except Exception:
            self.bg_layer = None
        self.overlay_layer = None
        self.update_summary()
        self.refresh_overlay(None)
        self.zoom_full()

    # ---------- logique (testable) ----------
    def current_actions(self):
        return [REVIEW_ACTIONS[max(0, min(cb.currentIndex(), len(REVIEW_ACTIONS) - 1))] for cb in self.action_combos]

    def set_all(self, action):
        i = REVIEW_ACTIONS.index(action)
        for cb in self.action_combos:
            cb.setCurrentIndex(i)
        self.update_summary()

    def decisions_preview(self):
        c = np.zeros(self.shape, bool)
        for s in self.sets:
            c |= s["mask"]
        return apply_implausible_decisions(c, self.prev_map, self.sets, self.current_actions(), self.polygons)[2]

    def update_summary(self, *_a):
        s = self.decisions_preview()
        ha = self.pixel_area_ha
        self.lbl_summary.setText(f"<b>Bilan prévu :</b> gardés {s['kept_px'] * ha:,.1f} ha · retirés de l'étape {s['removed_px'] * ha:,.1f} ha · classe de la référence {s['reference_px'] * ha:,.1f} ha"
                                 + (f" · {len(self.polygons)} polygone(s) de correction" if self.polygons else ""))

    def finish_drawn_polygon(self, pts):
        """Appelée par l'outil de dessin : ajoute une correction locale (masque du polygone + action choisie)."""
        if len(pts) < 3:
            return
        try:
            self.canvas.unsetMapTool(self.tool_poly)
        except Exception:
            pass
        geom = QgsGeometry.fromPolygonXY([pts])
        if geom.isEmpty():
            return
        mask = polygon_to_mask(geom, self.shape, self.geo_tf, self.proj_wkt)
        act = REVIEW_ACTIONS[max(0, min(self.cb_poly_action.currentIndex(), len(REVIEW_ACTIONS) - 1))]
        self.polygons.append((mask, act))
        inside = int(sum(np.count_nonzero(mask & s["mask"]) for s in self.sets))
        self.probe_readout.setText(f"Polygone {len(self.polygons)} : « {REVIEW_ACTION_LABELS[REVIEW_ACTIONS.index(act)]} » sur {inside:,} pixel(s) de transition improbable.")
        self.update_summary()

    def undo_polygon(self):
        if self.polygons:
            self.polygons.pop()
            self.probe_readout.setText(f"Dernier polygone annulé ({len(self.polygons)} restant(s)).")
            self.update_summary()

    def _finish(self, result):
        self.result_info = {"result": result, "actions": self.current_actions() if result == "apply" else ["keep"] * len(self.sets),
                            "polygons": list(self.polygons) if result == "apply" else []}
        self.accept()

    def on_apply(self):
        self._finish("apply")

    def on_reopen(self):
        self._finish("reopen")

    def on_skip(self):
        self._finish("skip")

    # ---------- carte ----------
    def on_select(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        sel = rows[0] if rows else None
        self.refresh_overlay(sel)
        if sel is not None:
            self.probe_readout.setText(f"Transition {sel + 1} : {implausible_label(self.sets[sel]['pair'])} ({self.sets[sel]['px'] * self.pixel_area_ha:,.1f} ha) en jaune.")

    def refresh_overlay(self, selected):
        """Écrit la carte des transitions improbables (couleur par transition, jaune = sélection) et recompose les couches."""
        codes = implausible_overlay_codes(self.shape, self.sets, selected)
        p = os.path.join(self.temp_folder, f"_Review_S{self.info.get('stage_n', 0)}_{int(time.time() * 1000)}.tif")
        write_raster(p, codes, self.geo_tf, self.proj_wkt, gdal.GDT_Byte, 0)
        lyr = QgsRasterLayer(p, "Transitions improbables")
        try:
            from qgis.core import QgsPalettedRasterRenderer
            cls = [QgsPalettedRasterRenderer.Class(i + 1, QColor(*REVIEW_PALETTE[i % len(REVIEW_PALETTE)]), f"{i + 1}. {implausible_label(s['pair'])}") for i, s in enumerate(self.sets[:9])]
            cls.append(QgsPalettedRasterRenderer.Class(REVIEW_HIGHLIGHT, QColor(255, 235, 0), "Transition sélectionnée"))
            lyr.setRenderer(QgsPalettedRasterRenderer(lyr.dataProvider(), 1, cls))
        except Exception:
            pass
        self.overlay_layer = lyr
        layers = [lyr] + ([self.bg_layer] if self.bg_layer is not None else [])
        try:
            study = QgsCoordinateReferenceSystem()
            study.createFromWkt(self.proj_wkt)
            self.canvas.setDestinationCrs(study)
        except Exception:
            pass
        self.canvas.setLayers(layers)
        self.canvas.refresh()

    def _extent(self):
        rows, cols = self.shape
        x0, px, _r1, y0, _r2, py = self.geo_tf
        xs, ys = (x0, x0 + cols * px), (y0, y0 + rows * py)
        return QgsRectangle(min(xs), min(ys), max(xs), max(ys))

    def zoom_full(self):
        self.canvas.setExtent(self._extent())
        self.canvas.refresh()

    def set_pan_mode(self):
        self.canvas.setMapTool(self.tool_pan)

    def set_zoom_rect_mode(self):
        self.canvas.setMapTool(self.tool_zoom)

    def zoom_step_in(self):
        self.canvas.zoomIn()

    def zoom_step_out(self):
        self.canvas.zoomOut()

    def start_polygon(self):
        self.canvas.setMapTool(self.tool_poly)
        self.probe_readout.setText("✏️ Dessinez le polygone : clic gauche = sommet, clic droit = terminer (3 sommets minimum).")

    def closeEvent(self, event):
        self.result_info = {"result": "skip", "actions": ["keep"] * len(self.sets), "polygons": []}      # fermer la fenêtre = ne rien corriger
        try:
            super().closeEvent(event)
        except Exception:
            pass


# ====================== FENÊTRE DE PROGRESSION (AJOUT) ======================
# Les phases longues (lecture des Stacks, indices spectraux, preuves supplémentaires, ancre, enregistrement) s'affichent dans UNE fenêtre d'attente : étape en cours,
# barre de progression, détail (« bande 12 / 41 »), liste des étapes faites (avec leur durée), temps écoulé et reste estimé. Elle se cache pendant les fenêtres de
# calibration et revient pour la finalisation. « Annuler » arrête proprement le traitement.
class ProgressCancelled(RuntimeError):
    """Levée quand l'utilisateur annule depuis la fenêtre de progression."""


def format_duration(seconds):
    s = int(max(0, round(float(seconds))))
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


class ProgressModel:
    """
    Logique PURE de la progression (testée sans Qt). plan = [(libellé, poids)] ; la barre = (poids des étapes finies + poids de l'étape en cours x avancement) / poids total.
    Le reste estimé se déduit du temps déjà écoulé et de la fraction accomplie (disponible à partir de 3 %).
    """

    def __init__(self, plan, clock=None):
        self.clock = clock or time.time
        self.steps = [{"label": str(lab), "weight": max(float(w), 0.0), "state": "pending", "t0": None, "t1": None} for lab, w in plan]
        self.total = sum(s["weight"] for s in self.steps) or float(len(self.steps) or 1)
        self.t_start = self.clock()
        self.cur = -1
        self.sub = 0.0
        self.detail = ""

    def begin(self, index):
        """Passe à l'étape `index` : les précédentes sont terminées."""
        if not (0 <= index < len(self.steps)):
            return
        now = self.clock()
        for i, s in enumerate(self.steps):
            if i < index and s["state"] != "done":
                if s["t0"] is None:
                    s["t0"] = now
                s["state"], s["t1"] = "done", now
        s = self.steps[index]
        s["state"], s["t0"] = "running", now
        self.cur, self.sub, self.detail = index, 0.0, ""

    def tick(self, done, total, detail=""):
        """Avancement à l'intérieur de l'étape en cours (done sur total)."""
        self.sub = 0.0 if not total else min(max(float(done) / float(total), 0.0), 1.0)
        if detail:
            self.detail = str(detail)

    def finish(self):
        now = self.clock()
        for s in self.steps:
            if s["state"] != "done":
                if s["t0"] is None:
                    s["t0"] = now
                s["state"], s["t1"] = "done", now
        self.cur, self.sub = len(self.steps) - 1, 1.0

    def fraction(self):
        w = self.total if self.total else 1.0
        done = sum(s["weight"] for s in self.steps if s["state"] == "done")
        if 0 <= self.cur < len(self.steps) and self.steps[self.cur]["state"] == "running":
            done += self.steps[self.cur]["weight"] * self.sub
        return min(max(done / w, 0.0), 1.0)

    def elapsed(self):
        return self.clock() - self.t_start

    def eta(self):
        f = self.fraction()
        return None if f < 0.03 else self.elapsed() * (1.0 - f) / f

    def time_text(self):
        e, r = self.elapsed(), self.eta()
        return f"Temps écoulé {format_duration(e)}" + (f" · reste estimé ≈ {format_duration(r)}" if r is not None else "")

    def steps_html(self):
        now, out = self.clock(), []
        for s in self.steps:
            if s["state"] == "done":
                out.append(f"<span style='color:#2e7d32'>✓ {s['label']}</span> <span style='color:#777'>— {format_duration((s['t1'] or now) - (s['t0'] or now))}</span>")
            elif s["state"] == "running":
                out.append(f"<b>▶ {s['label']}</b>" + (f" <span style='color:#555'>— {format_duration(now - (s['t0'] or now))}</span>" if s["t0"] else ""))
            else:
                out.append(f"<span style='color:#999'>○ {s['label']}</span>")
        return "<br>".join(out)

    def current_label(self):
        return self.steps[self.cur]["label"] if 0 <= self.cur < len(self.steps) else (self.steps[0]["label"] if self.steps else "")


class ProgressWindow(QDialog):
    """Fenêtre d'attente non bloquante : étape en cours, barre, détail, étapes faites, temps, bouton Annuler."""

    def __init__(self, title, plan, subtitle=""):
        super().__init__(None)
        from qgis.PyQt.QtWidgets import QProgressBar
        self.setWindowTitle(f"LULC {AREA_NAME} — traitement en cours")
        self.resize(620, 430)
        self.cancelled = False
        self._last = 0.0
        self.model = ProgressModel(plan)
        lay = QVBoxLayout(self)
        self.lbl_title = QLabel("")
        self.lbl_title.setWordWrap(True)
        self.lbl_task = QLabel("")
        self.lbl_task.setWordWrap(True)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.lbl_detail = QLabel("")
        self.lbl_steps = QLabel("")
        self.lbl_steps.setWordWrap(True)
        self.lbl_time = QLabel("")
        self.lbl_note = QLabel("<i>Ne fermez pas QGIS : pendant les calculs lourds la fenêtre peut sembler ne pas répondre, c'est normal.</i>")
        self.lbl_note.setWordWrap(True)
        self.btn_cancel = QPushButton("Annuler le traitement")
        self.btn_cancel.clicked.connect(self.request_cancel)
        for w in (self.lbl_title, self.lbl_task, self.bar, self.lbl_detail, self.lbl_steps, self.lbl_time, self.lbl_note):
            lay.addWidget(w)
        lay.addStretch(1)
        lay.addWidget(self.btn_cancel)
        self.set_plan(title, plan, subtitle)

    def set_plan(self, title, plan, subtitle=""):
        self.model = ProgressModel(plan)
        self.lbl_title.setText(f"<b>{title}</b>" + (f" — {subtitle}" if subtitle else ""))
        self.update_view(force=True)

    def update_view(self, force=False):
        now = time.time()
        if not force and now - self._last < 0.12:
            return
        self._last = now
        m = self.model
        self.lbl_task.setText(f"<span style='font-size:13pt'><b>{m.current_label()}</b></span>")
        self.bar.setValue(int(round(1000 * m.fraction())))
        self.lbl_detail.setText(m.detail)
        self.lbl_steps.setText(m.steps_html())
        self.lbl_time.setText(m.time_text())
        try:
            from qgis.PyQt.QtWidgets import QApplication
            QApplication.processEvents()
        except Exception:
            pass

    def _check_cancel(self):
        if self.cancelled:
            raise ProgressCancelled("Traitement annulé depuis la fenêtre de progression.")

    def begin(self, index):
        self.model.begin(index)
        self.update_view(force=True)
        self._check_cancel()

    def tick(self, done, total, detail=""):
        self.model.tick(done, total, detail)
        self.update_view()
        self._check_cancel()

    def request_cancel(self):
        self.cancelled = True
        self.lbl_detail.setText("Annulation demandée : arrêt à la prochaine vérification…")

    def finish(self):
        self.model.finish()
        self.update_view(force=True)

    def show_window(self):
        self.cancelled = False
        present_window(self, maximize=False, fullscreen_button=False)
        try:
            self.raise_()
        except Exception:
            pass
        self.update_view(force=True)

    def hide_window(self):
        self.hide()

    def close_window(self):
        self.hide()
        try:
            self.deleteLater()
        except Exception:
            pass

    def closeEvent(self, event):                       # la croix masque la fenêtre sans annuler
        try:
            event.ignore()
        except Exception:
            pass
        self.hide()


PROGRESS = None
YEAR_PROGRESS_TEXT = ""            # « année 2 sur 6 » (renseigné par la boucle des années)


def progress_open(title, plan, subtitle=None):
    """Ouvre (ou réutilise) la fenêtre de progression avec un nouveau plan. Sans effet visible si la fenêtre ne peut pas être créée."""
    global PROGRESS
    try:
        sub = YEAR_PROGRESS_TEXT if subtitle is None else subtitle
        if PROGRESS is None:
            PROGRESS = ProgressWindow(title, plan, sub)
        else:
            PROGRESS.set_plan(title, plan, sub)
        PROGRESS.show_window()
    except ProgressCancelled:
        raise
    except Exception as exc:
        PROGRESS = None
        print(f"[Progression] fenêtre non disponible : {exc}")


def progress_step(index):
    if PROGRESS is not None:
        PROGRESS.begin(index)


def progress_tick(done, total, detail=""):
    if PROGRESS is not None:
        PROGRESS.tick(done, total, detail)


def progress_hide():
    if PROGRESS is not None:
        PROGRESS.hide_window()


def progress_show():
    if PROGRESS is not None:
        PROGRESS.show_window()


def progress_close():
    global PROGRESS
    if PROGRESS is not None:
        try:
            PROGRESS.finish()
            PROGRESS.close_window()
        except Exception:
            pass
        PROGRESS = None


# ====================== MAIN ======================
RUN = _ask_run_settings()          # UNE seule fenêtre : dossier, zone d'étude, années, mode, reprise, preuves, ancre
parent_dir = RUN["parent_dir"]
_new_years = register_years(discover_years(parent_dir))
if _new_years:
    print(f"[ANNÉES] années découvertes dans le dossier et ajoutées à la liste : {', '.join(_new_years)}")
PROCESS_ORDER = RUN.get("order") if RUN.get("order") in PROCESS_ORDERS else "ascending"
print(f"[ORDRE] Traitement des années : {'ASCENDANT (de la plus ancienne à la plus récente)' if PROCESS_ORDER == 'ascending' else 'DESCENDANT (de la plus récente à la plus ancienne)'} ; "
      "chaque année est comparée à " + ("l'année PRÉCÉDENTE" if PROCESS_ORDER == "ascending" else "l'année SUIVANTE") + " déjà classée (fenêtres « 📊 Changement » orientées dans le sens du temps).")

output_dir = os.path.join(
    parent_dir,
    "Resultats_LULC_V17_Hierarchie_Forest"
)
os.makedirs(output_dir, exist_ok=True)

# ---------- ANCIEN DOSSIER V16 (9 classes) : reprise des PRESETS (l'étape Matorral est migrée dans Forest) ----------
_old_v16 = os.path.join(parent_dir, "Resultats_LULC_V16_Hierarchie_Forest_Matorral")
if os.path.isdir(_old_v16) and not glob.glob(os.path.join(output_dir, "Preset_*_Stage*.json")) and glob.glob(os.path.join(_old_v16, "Preset_*_Stage*.json")):
    if QMessageBox.question(None, "Presets de la version à 9 classes",
                            "Un dossier de résultats de la version à 9 classes (Forest + Matorral séparés) existe.\n\n"
                            "Reprendre ses PRESETS (seuils, masques) ? Les seuils de l'ancienne étape Matorral deviennent le bloc « forêt claire » de l'étape Forest.\n"
                            "(Les cartes et points de reprise de l'ancienne version ne sont pas repris : elles sont recalculées à 8 classes.)",
                            QMB_YES | QMB_NO, QMB_YES) == QMB_YES:
        print(f"[Migration] {migrate_v16_presets(_old_v16, output_dir)} preset(s) repris de l'ancien dossier V16.")
_n_tmp = clean_temp_dir(output_dir)
if _n_tmp:
    print(f"[Nettoyage] {_n_tmp} fichier(s) temporaire(s) d'une exécution précédente supprimés (_temp/).")
_n_ren = migrate_presets_to_8_stages(output_dir)
if _n_ren:
    print(f"[Migration] {_n_ren} fichier(s) de presets / seuils renumérotés (étapes 1 à 8 : Cropland 5, Fallow 6, Rangeland 7, Bareland 8) ; le preset Matorral est fusionné dans l'étape Forest.")

# ---------- AUTOMATIC FIXED INPUTS ----------
# 1) Study area: Study_Area_Final.shp
# 2) Stable Sebkha: Sebkha_Finale.shp
# 3) Built-up: Built_up_<year>.shp or Built_up_<year>.tif
# Si un fichier n'est pas trouvé par son nom exact, une fenêtre permet de le choisir à la main.
shp_admin = RUN["study_area"] or _find_or_ask_input(parent_dir, "Study_Area_Final", (".shp",), "Zone d'étude", "Study_Area_Final.shp")
# Sebkha et Built-up : recherche SILENCIEUSE par nom (aucune fenêtre d'erreur) ; trouvés = masque proposé par défaut dans la fenêtre de l'étape,
# introuvables = la fenêtre s'ouvre sans masque et vous choisissez le fichier ou classez par seuils.
shp_sebkha = _find_named_input(parent_dir, "Sebkha_Finale", (".shp",))

print(f"[AUTO] Study area  : {shp_admin}")
print(f"[AUTO] Sebkha      : {shp_sebkha or 'non trouvé → à choisir dans la fenêtre de l’étape 1'}")

admin_layer = QgsVectorLayer(shp_admin, "Admin_Strict", "ogr")
if not admin_layer.isValid():
    raise RuntimeError("La couche administrative sélectionnée est invalide.")

# ---------- CHOIX DES ANNÉES À TRAITER (une / plusieurs / toutes) ----------
_available_years = _scan_available_years(parent_dir, TARGET_YEARS)
if not _available_years:
    raise RuntimeError("Aucune année valide n'a été détectée (dossier d'année + stack raster introuvables).")
SELECTED_YEARS = [y for y in _available_years if y in RUN["years"]]          # années cochées dans la fenêtre de démarrage ET disponibles
if not SELECTED_YEARS:
    raise RuntimeError("Aucune des années cochées n'est disponible dans ce dossier.")
print(f"[AUTO] Années disponibles : {_available_years} | années à traiter : {SELECTED_YEARS}")

year_data = {}
for yr in SELECTED_YEARS:
    found_ = find_year_folder(parent_dir, yr)
    if not found_:
        print(f"⚠️ {yr} : aucun dossier d'année contenant un Stack (extensions {', '.join(STACK_EXTS)}) n'a été trouvé dans {parent_dir}.")
        for _r in year_folder_report(parent_dir):
            if str(_r["year"]) == str(yr):
                print("     → " + _r["message"])
        continue
    yr_dir, rasters = found_
    stack_file = pick_stack(rasters)

    if stack_file:
        built_up_path = _find_named_input(parent_dir, f"Built_up_{yr}", (".shp", ".tif", ".tiff"))
        if not built_up_path:
            print(f"[AUTO] Built-up {yr} : masque non trouvé → à choisir (ou seuils) dans la fenêtre de l'étape 2.")
        year_data[yr] = {"stack": stack_file, "built_up_mask": built_up_path}
        print(f"[AUTO] {yr}: Built-up mask -> {built_up_path}")
    else:
        print(f"⚠️ Aucun stack raster trouvé pour {yr}")

if not year_data:
    raise RuntimeError("Aucune année valide n'a été détectée.")

print("=" * 70)
print("LULC DESERTIFICATION — V17 : 8 CLASSES, HIÉRARCHIE, VALIDATION DE PUBLICATION")
print(f"[i] RF_N_JOBS={RF_N_JOBS} — mode QGIS-safe sans multiprocessing enfant.")
print("HIERARCHY: ADMIN → SEBKHA MASK → BUILT-UP → WATER → FOREST (dense + claire)")
print("          → CROPLAND → FALLOW → RANGELAND → BARELAND → RESIDUAL/FILL   (8 classes)")
print("=" * 70)
print("Années détectées:", list(year_data.keys()))

# ---------- LIMITE FORESTIÈRE : SUPPRIMÉE ----------
# Aucune délimitation forestière n'est requise ni utilisée. forest_cfg est conservé (désactivé) uniquement
# pour la compatibilité du module de validation.
forest_cfg = {"enabled": False, "boundary_path": ""}
print("[AUTO] Limite forestière : SUPPRIMÉE (Forest est classée sur tous les pixels encore non classés).")

# ---------- MASQUES IMPOSÉS PAR ÉTAPE (facultatifs) ----------
# Les masques se choisissent désormais DANS LA FENÊTRE DE CHAQUE ÉTAPE (Sebkha, Built-up, Water, Forest ... Bareland) : plus de question préalable.
_stage_mask_cfg, _mask_priority = {}, False
print("[MASQUES] Choisissez le masque de chaque étape dans sa fenêtre (shapefile, raster ou classe(s) d'un autre raster ; rôle TOTAL ou LIMITE).")
_temporal_cfg = _ask_temporal_evidence(output_dir, parent_dir, enabled=RUN["evidence"])
print("[PREUVES SUPPLÉMENTAIRES] " + describe_evidence_cfg(_temporal_cfg))

# ---------- Choix du mode : INTERACTIF ou BATCH (rejoue les presets) ----------
import glob as _glob
_existing_presets = _glob.glob(os.path.join(output_dir, "Preset_*_Stage*.json"))
batch_mode = False
if _existing_presets:
    batch_mode = bool(RUN["batch"])                         # choix fait dans la fenêtre de démarrage
else:
    print("[i] Aucun preset trouvé → mode INTERACTIF "
          "(les presets seront créés pour un futur batch)." + (" (le mode batch demandé n'est pas possible sans preset)" if RUN["batch"] else ""))

if batch_mode:
    print(f"[→] MODE BATCH activé — {len(_existing_presets)} preset(s) seront rejoués.")


def build_auto_cfg(year):
    """Assemble les presets par étape pour une année (repli sur l'année précédente)."""
    stages = {}
    missing = []
    for s in (1, 2, 3, 4, 5, 6, 7, 8):
        p = load_preset(year, s, output_dir)
        if not p:
            _, p = find_previous_preset(year, s, output_dir, TARGET_YEARS)
        if not p and s >= 4:           # étapes 1-3 : le masque trouvé par son nom sert de défaut (preset facultatif)
            missing.append(s)
        stages[s] = p
    return {"stages": stages}, missing



# ====================== PUBLICATION VALIDATION MODULE ======================
# Independent, reproducible validation and audit pack for Q1/Q2-oriented reporting.
# The module does NOT change the classification map. It operates on the final
# classified arrays and independent validation/reference data.

PUB_CLASS_TO_STAGE = {3: 1, 1: 2, 2: 3, 7: 4, 5: 5, 6: 6, 8: 7, 4: 8}
PUB_COLORS = {
    1: QColor(220, 50, 50),
    2: QColor(100, 140, 210),
    3: QColor(214, 230, 245),
    4: QColor(185, 195, 205),
}


def _pub_point_xy_from_pixel(gt, row, col):
    x = gt[0] + (col + 0.5) * gt[1] + (row + 0.5) * gt[2]
    y = gt[3] + (col + 0.5) * gt[4] + (row + 0.5) * gt[5]
    return float(x), float(y)


def _pub_pixel_from_point(gt, x, y):
    # General affine inverse for north-up and rotated rasters.
    a, b, c, d, e, f = gt
    det = b * f - c * e
    if abs(det) < 1e-15:
        return None
    col = ((x - a) * f - c * (y - d)) / det - 0.5
    row = (b * (y - d) - (x - a) * e) / det - 0.5
    return int(round(row)), int(round(col))


def _pub_make_point_layer(path, year, points, crs_wkt):
    drv = ogr.GetDriverByName('ESRI Shapefile')
    if os.path.exists(path):
        drv.DeleteDataSource(path)
    srs = osr.SpatialReference()
    if crs_wkt:
        srs.ImportFromWkt(crs_wkt)
    else:
        srs.ImportFromEPSG(32632)
    ds = drv.CreateDataSource(path)
    lyr = ds.CreateLayer(os.path.splitext(os.path.basename(path))[0], srs, ogr.wkbPoint)
    for name, typ, width in [
        ('sample_id', ogr.OFTString, 60),
        ('year', ogr.OFTInteger, 8),
        ('map_cls', ogr.OFTInteger, 8),
        ('ref_cls', ogr.OFTInteger, 8),
    ]:
        fld = ogr.FieldDefn(name, typ)
        if typ == ogr.OFTString:
            fld.SetWidth(width)
        lyr.CreateField(fld)
    defn = lyr.GetLayerDefn()
    for rec in points:
        ft = ogr.Feature(defn)
        ft.SetField('sample_id', rec['sample_id'])
        ft.SetField('year', int(year))
        ft.SetField('map_cls', int(rec['map_cls']))
        ft.SetField('ref_cls', int(rec.get('ref_cls', 0)))
        geom = ogr.Geometry(ogr.wkbPoint)
        geom.AddPoint(rec['x'], rec['y'])
        ft.SetGeometry(geom)
        lyr.CreateFeature(ft)
    ds = None
    return path


def _pub_area_ha(arr, cid, pixel_ha):
    return float(np.count_nonzero(np.asarray(arr) == cid) * pixel_ha)


def _pub_confusion_metrics(y_true, y_pred, weights=None, classes=None):
    classes = list(classes or all_classes)
    y_true = np.asarray(y_true, dtype=int)
    y_pred = np.asarray(y_pred, dtype=int)
    if weights is None:
        weights = np.ones(len(y_true), dtype=float)
    else:
        weights = np.asarray(weights, dtype=float)
    mat = np.zeros((len(classes), len(classes)), dtype=float)
    cidx = {c: i for i, c in enumerate(classes)}
    for t, p, w in zip(y_true, y_pred, weights):
        if t in cidx and p in cidx:
            mat[cidx[t], cidx[p]] += w
    total = float(mat.sum())
    oa = float(np.trace(mat) / total) if total else np.nan
    row = mat.sum(axis=1)
    col = mat.sum(axis=0)
    # BUGFIX: mat[true, pred] → row totals = reference(true) counts, col totals =
    # mapped(predicted) counts. User's Accuracy must divide by the MAP total
    # (col) and Producer's Accuracy by the REFERENCE total (row); these were
    # swapped, so every exported "UserAccuracy"/"ProducerAccuracy" column held
    # the other metric's value.
    ua = np.divide(np.diag(mat), col, out=np.full_like(col, np.nan), where=col > 0)
    pa = np.divide(np.diag(mat), row, out=np.full_like(row, np.nan), where=row > 0)
    f1 = np.divide(2 * ua * pa, ua + pa, out=np.full_like(ua, np.nan), where=(ua + pa) > 0)
    macro_f1 = float(np.nanmean(f1)) if np.any(np.isfinite(f1)) else np.nan
    # Unweighted sklearn diagnostics are retained for comparability.
    try:
        kappa = float(cohen_kappa_score(y_true, y_pred, labels=classes))
    except Exception:
        kappa = np.nan
    try:
        bal = float(balanced_accuracy_score(y_true, y_pred))
    except Exception:
        bal = np.nan
    try:
        mcc = float(matthews_corrcoef(y_true, y_pred))
    except Exception:
        mcc = np.nan
    return {
        'matrix': mat,
        'oa': oa,
        'kappa': kappa,
        'balanced_accuracy': bal,
        'mcc': mcc,
        'ua': ua,
        'pa': pa,
        'f1': f1,
        'macro_f1': macro_f1,
        'row_area': row,
        'col_area': col,
        'total': total,
    }


def _pub_bootstrap_ci(records_by_stratum, classes, B=400, seed=42):
    rng = np.random.RandomState(seed)
    oa_vals=[]
    ua_vals={c:[] for c in classes}
    pa_vals={c:[] for c in classes}
    for _ in range(B):
        ys=[]; ps=[]; ws=[]
        for map_cls, recs in records_by_stratum.items():
            if not recs:
                continue
            n=len(recs)
            idx=rng.randint(0,n,size=n)
            for j in idx:
                t,p,w=recs[j]
                ys.append(t); ps.append(p); ws.append(w)
        if not ys:
            continue
        m=_pub_confusion_metrics(ys,ps,ws,classes)
        oa_vals.append(m['oa'])
        for i,c in enumerate(classes):
            ua_vals[c].append(m['ua'][i])
            pa_vals[c].append(m['pa'][i])
    out={'oa':(np.nanpercentile(oa_vals,2.5),np.nanpercentile(oa_vals,97.5)) if oa_vals else (np.nan,np.nan), 'ua':{},'pa':{}}
    for c in classes:
        out['ua'][c]=(np.nanpercentile(ua_vals[c],2.5),np.nanpercentile(ua_vals[c],97.5)) if ua_vals[c] else (np.nan,np.nan)
        out['pa'][c]=(np.nanpercentile(pa_vals[c],2.5),np.nanpercentile(pa_vals[c],97.5)) if pa_vals[c] else (np.nan,np.nan)
    return out


def _pub_perturb_thresholds(obj, factor):
    import copy
    out=copy.deepcopy(obj)
    th=out.get('thresholds',{}) if isinstance(out,dict) else {}
    for k,v in list(th.items()):
        if isinstance(v,(int,float)) and np.isfinite(v) and not isinstance(v,bool):
            if abs(float(v)) > 1e-12:
                th[k]=float(v)*(1.0+factor)
    # Keep universal MSAVI bounds ordered if both exist.
    if 'msavi2_min' in th and 'msavi2_max' in th:
        try:
            if float(th['msavi2_min']) > float(th['msavi2_max']):
                th['msavi2_min'], th['msavi2_max'] = th['msavi2_max'], th['msavi2_min']
        except Exception:
            pass
    out['thresholds']=th
    return out


def _pub_build_auto_cfg(year, output_dir, years_order):
    stages={}; missing=[]
    for s in (2,3,4,5,6,7,8):
        p=load_preset(year,s,output_dir)
        if not p:
            _,p=find_previous_preset(year,s,output_dir,years_order)
        if not p:
            missing.append(s)
        stages[s]=p
    return {'stages':stages}, missing


class FinalYearAreaQADialog(QDialog):
    """Mandatory visible end-of-year AREA QA window.

    This is a QA report, not an additional classification stage.  It is shown
    after every completed year so the user can verify that the eight classes
    cover exactly the administrative Study Area.
    """
    def __init__(self, year, study_area_ha, class_rows, sum_ha, difference_ha,
                 coverage_pct, status, admin_pixels, unclassified_pixels,
                 outside_pixels, parent=None, geometry_note=""):
        super().__init__(parent)
        self.setWindowTitle(f"AREA QA — Année {year}")
        self.resize(860, 650)
        self.setMinimumSize(760, 560)

        root = QVBoxLayout(self)
        title = QLabel(f"<h2>YEAR {year} — AREA QA FINAL</h2>")
        root.addWidget(title)

        info = QLabel(
            f"<b>Study Area raster :</b> {study_area_ha:,.2f} ha &nbsp;&nbsp; | &nbsp;&nbsp;"
            f"<b>Pixels administratifs :</b> {admin_pixels:,}<br>"
            f"<b>Pixels non classés dans Study Area :</b> {unclassified_pixels:,} &nbsp;&nbsp; | &nbsp;&nbsp;"
            f"<b>Pixels hors Study Area avec classe :</b> {outside_pixels:,}"
        )
        info.setWordWrap(True)
        root.addWidget(info)

        self.table = QTableWidget(len(class_rows), 3)
        self.table.setHorizontalHeaderLabels(["Class", "Area (ha)", "% Study Area"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        for r, (name, area_ha) in enumerate(class_rows):
            pct = (100.0 * area_ha / study_area_ha) if study_area_ha else 0.0
            self.table.setItem(r, 0, QTableWidgetItem(str(name)))
            self.table.setItem(r, 1, QTableWidgetItem(f"{area_ha:,.2f}"))
            self.table.setItem(r, 2, QTableWidgetItem(f"{pct:.4f}"))
        root.addWidget(self.table, 1)

        summary = QLabel(
            f"<b>SUM CLASSES :</b> {sum_ha:,.2f} ha<br>"
            f"<b>DIFFERENCE :</b> {difference_ha:,.8f} ha<br>"
            f"<b>COVERAGE :</b> {coverage_pct:.4f} %<br>"
            f"<b>STATUS :</b> {status}"
            + (f"<br><b>CONTOUR :</b> {geometry_note}" if geometry_note else "")
        )
        summary.setWordWrap(True)
        summary.setStyleSheet("font-size:14px; padding:8px;")
        root.addWidget(summary)

        btn = QPushButton(f"✓ Continuer vers l'année suivante")
        btn.clicked.connect(self.accept)
        root.addWidget(btn)
        self.btn_continue = btn

        # Enter/Escape-friendly normal dialog behaviour.
        try:
            btn.setDefault(True)
        except Exception:
            pass



class VisualLULCEditingDialog(QDialog):
    """Visual post-classification QA/QC editor.

    The editor never destroys the first classification: it stores an exact
    ``*_Original.tif`` copy, an ``*_Edited.tif`` copy, and a GeoJSON/CSV audit
    trail describing every polygon edit.  The edited raster is returned to the
    main workflow so Accuracy Assessment can be run on the final map.
    """
    def __init__(self, year, raster_arr, geo_tf, proj_wkt, output_dir, pixel_area_ha, parent=None):
        super().__init__(parent)
        self.year = int(year)
        self.arr_original = raster_arr.astype(np.uint8, copy=True)
        self.arr = raster_arr.astype(np.uint8, copy=True)
        self.geo_tf = geo_tf
        self.proj_wkt = proj_wkt
        self.output_dir = output_dir
        self.pixel_area_ha = float(pixel_area_ha)
        self.edits = []
        self._pending_points = []

        edit_dir = os.path.join(lulc_dir(output_dir), "Edition_visuelle")        # <résultats>/LULC/Edition_visuelle/ : originaux, éditions, journaux
        os.makedirs(edit_dir, exist_ok=True)
        self.original_path = os.path.join(edit_dir, f"LULC_{AREA_TAG}_{year}_Original.tif")
        self.edited_path = os.path.join(edit_dir, f"LULC_{AREA_TAG}_{year}_Edited.tif")
        self.log_csv = os.path.join(edit_dir, f"Visual_Edit_Log_{year}.csv")
        self.log_geojson = os.path.join(edit_dir, f"Visual_Edit_Log_{year}.geojson")

        # Preserve an exact copy before any manual editing.
        write_raster(self.original_path, self.arr_original, self.geo_tf, self.proj_wkt,
                     gdal.GDT_Byte, 0)

        self.setWindowTitle(f"🗺 Visual LULC Editing — {year}")
        self.resize(1280, 820)
        root = QVBoxLayout(self)

        title = QLabel(
            f"<b>Visual LULC QA/QC — {year}</b><br>"
            "Examinez visuellement la carte. Toute correction est appliquée à un polygone entier et enregistrée automatiquement. "
            "La carte originale est conservée et n'est pas supprimée."
        )
        title.setWordWrap(True)
        root.addWidget(title)

        top = QHBoxLayout()
        top.addWidget(QLabel("Classe source à l'intérieur du polygone :"))
        self.source_class_combo = QComboBox()
        self.source_class_combo.addItem("Toutes les classes", -1)
        for cid, name in CLASS_NAMES.items():
            self.source_class_combo.addItem(f"{cid} — {name}", cid)
        top.addWidget(self.source_class_combo)

        top.addWidget(QLabel("Nouvelle classe :"))
        self.class_combo = QComboBox()
        for cid, name in CLASS_NAMES.items():
            self.class_combo.addItem(f"{cid} — {name}", cid)
        top.addWidget(self.class_combo)

        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText("Motif de correction / remarque facultative")
        top.addWidget(self.note_edit, 1)

        self.btn_draw = QPushButton("✏️ Dessiner un polygone")
        self.btn_draw.clicked.connect(self.start_drawing)
        top.addWidget(self.btn_draw)

        self.btn_undo = QPushButton("↩ Annuler la dernière modification")
        self.btn_undo.clicked.connect(self.undo_last)
        top.addWidget(self.btn_undo)
        root.addLayout(top)

        # ---- image HAUTE RÉSOLUTION en fond : pour corriger en voyant le terrain ----
        self._hr_layer = None
        self._canvas_layer = None
        self._extent_done = False
        hr_row = QHBoxLayout()
        self.btn_hr = QPushButton("🖼 Image HR…")
        self.btn_hr.setToolTip("Choisir une image haute résolution du disque : elle s'affiche SOUS la classification (le choix est repris par toutes les fenêtres).")
        self.btn_hr.clicked.connect(self.choose_hr_image)
        self.btn_hr_fast = QPushButton("⚡ Zoom rapide")
        self.btn_hr_fast.setToolTip("Crée une copie tuilée avec pyramides de l'image : zoom et déplacement quasi instantanés.")
        self.btn_hr_fast.clicked.connect(self.optimize_hr_image)
        self.chk_hr = QCheckBox("Image HR")
        self.chk_hr.setChecked(True)
        self.chk_lulc = QCheckBox("Classification")
        self.chk_lulc.setChecked(True)
        self.sp_opacity = QSpinBox()
        self.sp_opacity.setRange(0, 100)
        self.sp_opacity.setSingleStep(5)
        self.sp_opacity.setSuffix(" %")
        self.sp_opacity.setValue(int(HR_VIEW_STATE.get("edit_opacity", 100)))
        self.sp_opacity.setToolTip("Opacité de la classification au-dessus de l'image HR : baissez-la pour voir l'image à travers les classes.")
        self.chk_hr.toggled.connect(self.on_view_options_changed)
        self.chk_lulc.toggled.connect(self.on_view_options_changed)
        self.sp_opacity.valueChanged.connect(self.on_view_options_changed)
        self.btn_pan = QPushButton("✋ Pan")
        self.btn_pan.clicked.connect(self.set_pan_mode)
        self.btn_zoom_in = QPushButton("🔍+")
        self.btn_zoom_in.setToolTip("Zoom sur un RECTANGLE : glissez sur la carte.")
        self.btn_zoom_in.clicked.connect(self.set_zoom_in_mode)
        self.btn_zoom_plus = QPushButton("➕")
        self.btn_zoom_plus.setToolTip("Zoom avant d'un cran (centré sur la vue). La molette de la souris fait la même chose.")
        self.btn_zoom_plus.clicked.connect(self.zoom_step_in)
        self.btn_zoom_minus = QPushButton("➖")
        self.btn_zoom_minus.setToolTip("Zoom arrière d'un cran (centré sur la vue).")
        self.btn_zoom_minus.clicked.connect(self.zoom_step_out)
        self.btn_zoom_full = QPushButton("🌐 Extent")
        self.btn_zoom_full.clicked.connect(self.zoom_full)
        for w_ in (self.btn_hr, self.btn_hr_fast, self.chk_hr, self.chk_lulc, QLabel("Opacité de la classification :"), self.sp_opacity, self.btn_pan, self.btn_zoom_in, self.btn_zoom_minus, self.btn_zoom_plus, self.btn_zoom_full):
            hr_row.addWidget(w_)
        hr_row.addStretch(1)
        root.addLayout(hr_row)

        self.canvas = QgsMapCanvas()
        self.canvas.setCanvasColor(QColor(245, 245, 245))
        self.canvas.enableAntiAliasing(True)
        root.addWidget(self.canvas, 1)

        bottom = QHBoxLayout()
        self.info = QLabel("Choisissez la classe, puis cliquez sur « Dessiner un polygone ». Clic gauche pour ajouter les sommets, clic droit pour terminer le polygone. "
                           "Pour voir le terrain : « 🖼 Image HR… », puis baissez l'opacité de la classification.")
        self.info.setWordWrap(True)
        bottom.addWidget(self.info, 1)
        # Alias used by the generic polygon map tool.
        # The Visual editor historically exposes its status widget as `info`,
        # while DirectPolygonMapTool expects `probe_readout`.
        self.probe_readout = self.info
        self.btn_cancel = QPushButton("Annuler — conserver l’original")
        self.btn_cancel.clicked.connect(self.reject)
        bottom.addWidget(self.btn_cancel)
        self.btn_save = QPushButton("✓ Enregistrer le LULC édité et continuer")
        self.btn_save.clicked.connect(self.save_and_accept)
        bottom.addWidget(self.btn_save)
        root.addLayout(bottom)

        self.tool_pan = QgsMapToolPan(self.canvas)
        self.tool_zoom_in = QgsMapToolZoom(self.canvas, False)
        self._refresh_canvas()
        self.tool = DirectPolygonMapTool(self.canvas, self)
        self._restore_hr_state()

    # ---- image HR : mêmes outils que les fenêtres d'étape (fichier, copie rapide, diagnostic, recouvrement) ----
    _ask_hr_path = StageCalibrationDialog._ask_hr_path
    _study_crs = StageCalibrationDialog._study_crs
    _hr_layer_info = StageCalibrationDialog._hr_layer_info
    _resolve_hr_path = StageCalibrationDialog._resolve_hr_path
    optimize_hr_image = StageCalibrationDialog.optimize_hr_image

    def _stack_extent(self):
        rows, cols = self.arr.shape
        x0, px, _r1, y0, _r2, py = self.geo_tf
        xs = (x0, x0 + cols * px)
        ys = (y0, y0 + rows * py)
        return QgsRectangle(min(xs), min(ys), max(xs), max(ys))

    def choose_hr_image(self):
        f = self._ask_hr_path()
        if not f:
            return
        HR_VIEW_STATE["hr_path"] = f
        HR_VIEW_STATE["mode"] = "hr"
        self.show_hr_image()

    def show_hr_image(self, quiet=False):
        """Affiche l'image haute résolution SOUS la classification (opacité réglable). quiet = sans question (reprise automatique à l'ouverture)."""
        path = HR_VIEW_STATE.get("hr_path")
        if not path or not os.path.exists(path):
            path = self._ask_hr_path()
            if not path:
                return False
            HR_VIEW_STATE["hr_path"] = path
        shown = self._resolve_hr_path(path)
        lyr = QgsRasterLayer(shown, "Image HR")
        if not lyr.isValid():
            QMessageBox.warning(self, "Image haute résolution", f"Image illisible par QGIS :\n{shown}")
            HR_VIEW_STATE["hr_path"] = None
            return False
        info = self._hr_layer_info(lyr, shown)
        info["fast"] = shown != path
        if info["overlap"] is not None and info["overlap"] <= 0.0:
            QMessageBox.warning(self, "Image haute résolution",
                                "Cette image ne recouvre PAS la zone d'étude (CRS différent mal reconnu, ou emprise ailleurs).\n\n"
                                f"Zone d'étude (CRS du stack) : {tuple(round(v, 1) for v in _rect_tuple(self._stack_extent()))}\n"
                                f"Image (ramenée au CRS du stack) : {tuple(round(v, 1) for v in info.get('image_extent', ()))}\n"
                                f"CRS de l'image : {info['authid'] or 'inconnu'}")
            HR_VIEW_STATE["hr_path"] = None
            return False
        if not quiet and shown == path and hr_needs_pyramids(info["width"], info["height"], info["size_mb"], info["pyramids"]):
            if QMessageBox.question(
                    self, "Image volumineuse : zoom lent",
                    f"Image de {info['width']}×{info['height']} px ({info['size_mb']:,.0f} Mo) sans pyramides : le zoom sera lent.\n\n"
                    "Créer une COPIE RAPIDE (tuilée + pyramides internes, plus d'espace disque, zoom quasi instantané) ?\n"
                    "(vous pouvez aussi le faire plus tard avec le bouton « ⚡ Zoom rapide »)", QMB_YES | QMB_NO, QMB_YES) == QMB_YES:
                if self.optimize_hr_image():
                    return True
        self._hr_layer = lyr
        HR_VIEW_STATE["mode"] = "hr"
        self.chk_hr.blockSignals(True)
        self.chk_hr.setChecked(True)
        self.chk_hr.blockSignals(False)
        if int(self.sp_opacity.value()) >= 100:                  # sans réglage préalable : classification semi-transparente pour voir l'image
            self.sp_opacity.blockSignals(True)
            self.sp_opacity.setValue(55)
            self.sp_opacity.blockSignals(False)
            HR_VIEW_STATE["edit_opacity"] = 55
        self._apply_layers(reset_extent=True)
        try:
            self.info.setText(hr_diagnostic_html(info))
        except Exception:
            pass
        print("[Image HR] " + re.sub(r"<[^>]+>", " ", hr_diagnostic_html(info)).replace("\n", " | "))
        return True

    def _restore_hr_state(self):
        """L'image HR choisie dans une fenêtre précédente (étape ou édition) est reprise automatiquement."""
        try:
            p = HR_VIEW_STATE.get("hr_path")
            if HR_VIEW_STATE.get("mode") == "hr" and p and os.path.exists(p):
                self.show_hr_image(quiet=True)
        except Exception as exc:
            print(f"[Image HR] reprise automatique impossible : {exc}")

    def _apply_layers(self, reset_extent=False):
        """Recompose la carte : classification (opacité réglée) au-dessus de l'image HR. Le zoom courant est CONSERVÉ (sauf reset_extent)."""
        has_hr = self._hr_layer is not None and self.chk_hr.isChecked()
        layers = []
        if self._canvas_layer is not None and self.chk_lulc.isChecked():
            layers.append(self._canvas_layer)
        if has_hr:
            layers.append(self._hr_layer)
        if not layers and self._canvas_layer is not None:
            layers = [self._canvas_layer]                       # jamais une carte vide
        if self._canvas_layer is not None:
            self._canvas_layer.setOpacity(int(self.sp_opacity.value()) / 100.0 if has_hr else 1.0)
        study = self._study_crs()
        if study is not None:
            self.canvas.setDestinationCrs(study)
        ext = None if (reset_extent or not self._extent_done) else self.canvas.extent()
        self.canvas.setLayers(layers)
        self.canvas.setExtent(self._stack_extent() if ext is None else ext)
        self._extent_done = True
        self.canvas.refresh()

    def on_view_options_changed(self, *_a):
        HR_VIEW_STATE["edit_opacity"] = int(self.sp_opacity.value())
        self._apply_layers()

    def set_pan_mode(self):
        self.canvas.setMapTool(self.tool_pan)

    def set_zoom_in_mode(self):
        self.canvas.setMapTool(self.tool_zoom_in)

    def zoom_step_in(self):
        """➕ : zoom avant d'un cran (facteur 2), centré sur la vue ; n'interrompt pas l'outil actif (dessin de polygone, échantillonnage...)."""
        self.canvas.zoomIn()

    def zoom_step_out(self):
        """➖ : zoom arrière d'un cran (facteur 2), centré sur la vue ; n'interrompt pas l'outil actif."""
        self.canvas.zoomOut()

    def zoom_full(self):
        self.canvas.setExtent(self._stack_extent())
        self.canvas.refresh()

    def _renderer_layer(self, path, name):
        layer = QgsRasterLayer(path, name)
        if layer.isValid():
            items = [QgsColorRampShader.ColorRampItem(cid, col, CLASS_NAMES[cid])
                     for cid, col in CLASS_COLORS.items()]
            shader = QgsRasterShader()
            ramp = QgsColorRampShader()
            ramp.setColorRampType(QgsColorRampShader.Exact)
            ramp.setColorRampItemList(items)
            shader.setRasterShaderFunction(ramp)
            layer.setRenderer(QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader))
        return layer

    def _refresh_canvas(self):
        # Use a unique preview filename on every refresh. QGIS keeps the
        # previous raster provider open, so rewriting the same TIFF can be
        # locked on Windows.
        stamp = time.strftime("%Y%m%d_%H%M%S")
        preview = os.path.join(
            temp_dir(self.output_dir),
            f"_VisualEditPreview_{self.year}_{stamp}_{id(self)}_{len(self.edits)}.tif"
        )
        write_raster(preview, self.arr, self.geo_tf, self.proj_wkt, gdal.GDT_Byte, 0)
        layer = self._renderer_layer(preview, f"LULC {self.year} — Edited preview")
        if layer.isValid():
            self._canvas_layer = layer
            self._apply_layers()                                # le zoom courant et l'image HR sont conservés après chaque correction

    def start_drawing(self):
        self._pending_points = []
        self.tool.reset_tool()
        self.canvas.setMapTool(self.tool)
        cid = int(self.class_combo.currentData())
        src = int(self.source_class_combo.currentData())
        src_txt = "Toutes les classes" if src == -1 else f"{src} — {CLASS_NAMES[src]}"
        self.info.setText(
            f"✏️ Dessiner un polygone : convertir {src_txt} → {cid} — {CLASS_NAMES[cid]}. "
            "Gauche = ajouter un sommet, droite = terminer."
        )

    def finish_drawn_polygon(self, pts):
        if len(pts) < 3:
            return
        self.canvas.unsetMapTool(self.tool)
        geom = QgsGeometry.fromPolygonXY([pts])
        if geom.isEmpty():
            return
        self.apply_polygon(geom, pts)

    def _polygon_mask(self, geom):
        rows, cols = self.arr.shape
        drv = gdal.GetDriverByName("MEM")
        ds = drv.Create("", cols, rows, 1, gdal.GDT_Byte)
        ds.SetGeoTransform(self.geo_tf)
        ds.SetProjection(self.proj_wkt)
        band = ds.GetRasterBand(1)
        band.Fill(0)
        mem_drv = ogr.GetDriverByName("Memory")
        vds = mem_drv.CreateDataSource("visual_edit_mem")
        srs = osr.SpatialReference()
        try:
            srs.ImportFromWkt(self.proj_wkt)
        except Exception:
            srs = None
        lyr = vds.CreateLayer("poly", srs=srs, geom_type=ogr.wkbPolygon)
        feat = ogr.Feature(lyr.GetLayerDefn())
        og = ogr.CreateGeometryFromWkb(bytes(geom.asWkb()))
        feat.SetGeometry(og)
        lyr.CreateFeature(feat)
        feat = None
        gdal.RasterizeLayer(ds, [1], lyr, burn_values=[1])
        mask = band.ReadAsArray().astype(bool)
        vds = None
        ds = None
        return mask

    def apply_polygon(self, geom, pts):
        mask = self._polygon_mask(geom)
        mask &= (self.arr > 0)
        source_cid = int(self.source_class_combo.currentData())
        if source_cid >= 0:
            mask &= (self.arr == source_cid)
        n = int(np.count_nonzero(mask))
        if n == 0:
            if source_cid >= 0:
                QMessageBox.warning(
                    self, "Visual QA/QC",
                    f"Aucun pixel de la classe {source_cid} — {CLASS_NAMES[source_cid]} à l’intérieur du polygone."
                )
            else:
                QMessageBox.warning(self, "Visual QA/QC", "Aucun pixel classé à l’intérieur du polygone.")
            return
        new_cid = int(self.class_combo.currentData())
        old_vals = self.arr[mask].copy()
        changed = old_vals != new_cid
        changed_n = int(np.count_nonzero(changed))
        if changed_n == 0:
            QMessageBox.information(self, "Visual QA/QC", "La zone est déjà classée dans la classe sélectionnée.")
            return

        # Store exact before/after pixel state through the polygon mask.
        old_counts = {}
        for cid in all_classes:
            cnt = int(np.count_nonzero(old_vals == cid))
            if cnt:
                old_counts[cid] = cnt
        self.arr[mask] = np.uint8(new_cid)

        try:
            wkt = geom.asWkt()
        except Exception:
            wkt = ""
        rec = {
            "year": self.year,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source_class_id": source_cid,
            "source_class": "Toutes les classes" if source_cid < 0 else CLASS_NAMES[source_cid],
            "new_class_id": new_cid,
            "new_class": CLASS_NAMES[new_cid],
            "changed_pixels": changed_n,
            "changed_area_ha": changed_n * self.pixel_area_ha,
            "old_class_counts": old_counts,
            "note": self.note_edit.text().strip(),
            "wkt": wkt,
            "mask": mask.copy(),
            "before": old_vals.copy(),
        }
        self.edits.append(rec)
        self.note_edit.clear()
        self._refresh_canvas()
        src_txt = "Toutes les classes" if source_cid < 0 else f"{source_cid} — {CLASS_NAMES[source_cid]}"
        self.info.setText(
            f"✓ Correction effectuée : {changed_n:,} px = {changed_n*self.pixel_area_ha:,.4f} ha | "
            f"{src_txt} → {new_cid} — {CLASS_NAMES[new_cid]}. Total des modifications : {len(self.edits)}"
        )

    def undo_last(self):
        if not self.edits:
            self.info.setText("Aucune modification à annuler.")
            return
        rec = self.edits.pop()
        mask = rec["mask"]
        before = rec["before"]
        self.arr[mask] = before
        self._refresh_canvas()
        self.info.setText(f"↩ Dernière modification annulée. Modifications restantes : {len(self.edits)}")

    def _write_audit(self):
        rows = [["Year","Edit_ID","Timestamp","Source_Class_ID","Source_Class",
                 "New_Class_ID","New_Class","Changed_Pixels","Changed_Area_ha","Old_Class_Counts","Note","WKT"]]
        for i, rec in enumerate(self.edits, 1):
            rows.append([
                self.year, i, rec["timestamp"], rec["source_class_id"], rec["source_class"],
                rec["new_class_id"], rec["new_class"],
                rec["changed_pixels"], f"{rec['changed_area_ha']:.6f}",
                json.dumps(rec["old_class_counts"], ensure_ascii=False),
                rec["note"], rec["wkt"]
            ])
        write_csv_rows(self.log_csv, rows)

        # GeoJSON audit layer: one feature per accepted polygon edit.
        features = []
        for i, rec in enumerate(self.edits, 1):
            if not rec["wkt"]:
                continue
            features.append({
                "type": "Feature",
                "geometry": json.loads(QgsGeometry.fromWkt(rec["wkt"]).asJson()),
                "properties": {
                    "year": self.year,
                    "edit_id": i,
                    "timestamp": rec["timestamp"],
                    "source_class_id": rec["source_class_id"],
                    "source_class": rec["source_class"],
                    "new_class_id": rec["new_class_id"],
                    "new_class": rec["new_class"],
                    "changed_pixels": rec["changed_pixels"],
                    "changed_area_ha": rec["changed_area_ha"],
                    "old_class_counts": json.dumps(rec["old_class_counts"], ensure_ascii=False),
                    "note": rec["note"],
                }
            })
        geojson = {"type":"FeatureCollection","features":features}
        try:
            with open(self.log_geojson, "w", encoding="utf-8") as f:
                json.dump(geojson, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ Visual Edit GeoJSON non écrit: {e}")

    def save_and_accept(self):
        # Save both the explicit edited copy and the canonical final raster.
        write_raster(self.edited_path, self.arr, self.geo_tf, self.proj_wkt, gdal.GDT_Byte, 0)
        self._write_audit()
        self.result_path = self.edited_path
        self.accept()

    def get_result(self):
        return self.arr.copy(), self.result_path, self.edits

class PublicationValidationDialog(QDialog):
    """Independent publication-grade validation/audit module.

    Core outputs:
      - 8-class final confusion matrix and class-wise accuracy
      - map-stratified area-adjusted accuracy and bootstrap 95% CIs
      - independent validation sample generation and reference-label attachment
      - uncertainty maps from RF confidence rasters (where available)
      - spatial rule audit (admin/Sebkha/forest) and temporal transition audit
      - global threshold sensitivity scenarios (±5/±10%)
      - RF feature ablation for a selected year/stage
      - reproducibility/provenance package
    """
    def __init__(self, classified_arrays, yearly_areas_data, year_geo, output_dir,
                 year_data, admin_layer, shp_sebkha, forest_cfg, parent=None):
        super().__init__(parent)
        self.setWindowTitle('📚 Publication Validation Module — Q1/Q2')
        self.resize(1210, 836)
        self.classified_arrays=classified_arrays
        self.yearly_areas_data=yearly_areas_data
        self.year_geo=year_geo
        self.output_dir=output_dir
        self.year_data=year_data
        self.admin_layer=admin_layer
        self.shp_sebkha=shp_sebkha
        self.forest_cfg=forest_cfg or {}
        self.pub_dir=os.path.join(output_dir,'Publication_Validation')
        os.makedirs(self.pub_dir,exist_ok=True)
        self.years=sorted(classified_arrays.keys(),key=lambda s:int(s))

        lay=QVBoxLayout(self)
        title=QLabel('📚 Publication Validation Module — independent accuracy, uncertainty, spatial/temporal audit')
        title.setStyleSheet('font-size:15px;font-weight:bold;color:#0d47a1;')
        lay.addWidget(title)
        info=QLabel(
            'Cette fenêtre ne modifie pas les cartes LULC. Elle travaille sur les cartes finales et sur des données de référence indépendantes. '
            'Pour une validation d\'aire ajustée réellement défendable, utilisez les points générés stratifiés par classe cartographique puis renseignez ref_cls.'
        )
        info.setWordWrap(True); info.setStyleSheet('color:#37474f;'); lay.addWidget(info)

        box=QGroupBox('1. Validation indépendante')
        g=QGridLayout(box)
        g.addWidget(QLabel('Dossier des échantillons :'),0,0)
        self.le_samples=QLineEdit(self.pub_dir); g.addWidget(self.le_samples,0,1)
        b=QPushButton('Parcourir…'); b.clicked.connect(self.pick_samples_dir); g.addWidget(b,0,2)
        g.addWidget(QLabel('Points / classe / année :'),1,0)
        self.sp_n=QSpinBox(); self.sp_n.setRange(10,1000); self.sp_n.setValue(50); g.addWidget(self.sp_n,1,1)
        g.addWidget(QLabel('Distance minimale (pixels) :'),2,0)
        self.sp_dist=QSpinBox(); self.sp_dist.setRange(0,50); self.sp_dist.setValue(3); g.addWidget(self.sp_dist,2,1)
        self.btn_gen=QPushButton('🎯 Générer échantillons stratifiés')
        self.btn_gen.clicked.connect(self.generate_samples); g.addWidget(self.btn_gen,3,0,1,3)
        g.addWidget(QLabel('Couche de référence indépendante :'),4,0)
        self.le_ref=QLineEdit(); g.addWidget(self.le_ref,4,1)
        br=QPushButton('Parcourir…'); br.clicked.connect(self.pick_ref); g.addWidget(br,4,2)
        g.addWidget(QLabel('Champ Classe référence :'),5,0)
        self.le_ref_field=QLineEdit('class'); g.addWidget(self.le_ref_field,5,1)
        g.addWidget(QLabel('Champ Année (optionnel) :'),6,0)
        self.le_ref_year=QLineEdit(); g.addWidget(self.le_ref_year,6,1)
        self.btn_join=QPushButton('🔗 Affecter ref_cls depuis la référence')
        self.btn_join.clicked.connect(self.attach_reference_labels); g.addWidget(self.btn_join,7,0,1,3)
        self.btn_eval=QPushButton('📊 Évaluer toutes les années + IC 95%')
        self.btn_eval.clicked.connect(self.evaluate_all_years); g.addWidget(self.btn_eval,8,0,1,3)
        lay.addWidget(box)

        box2=QGroupBox('2. Diagnostics de publication')
        h=QHBoxLayout(box2)
        for label,slot in [
            ('🗺 Incertitude',self.make_uncertainty_maps),
            ('🛡 Audit spatial / temporel',self.run_spatial_temporal_audit),
            ('📉 Sensibilité ±5/±10%',self.run_sensitivity),
            ('🧪 Ablation RF',self.run_ablation),
            ('📦 Export publication',self.export_publication_pack),
        ]:
            btn=QPushButton(label); btn.clicked.connect(slot); h.addWidget(btn)
        lay.addWidget(box2)

        stage_box=QGroupBox("3. Paramètres de l'ablation RF")
        sg=QHBoxLayout(stage_box)
        sg.addWidget(QLabel('Année :'))
        self.cb_ab_year=QComboBox(); self.cb_ab_year.addItems(self.years); sg.addWidget(self.cb_ab_year)
        sg.addWidget(QLabel('Étape :'))
        self.cb_ab_stage=QComboBox(); self.cb_ab_stage.addItems([str(x) for x in (2,3,4,5,6,7,8)]); sg.addWidget(self.cb_ab_stage)
        sg.addWidget(QLabel('Validation :'))
        self.lbl_ab_info=QLabel("Suppression d'une feature à la fois, split spatial par polygones si possible.")
        self.lbl_ab_info.setWordWrap(True); sg.addWidget(self.lbl_ab_info,1)
        lay.addWidget(stage_box)

        self.log=QTextEdit(); self.log.setReadOnly(True); lay.addWidget(self.log,1)
        btnclose=QPushButton('Fermer'); btnclose.clicked.connect(self.close); lay.addWidget(btnclose)
        self.log_append('[i] Module indépendant prêt. Dossier: '+self.pub_dir)

    def log_append(self,msg):
        self.log.append(msg); print('[Publication]',msg)

    def pick_samples_dir(self):
        p=QFileDialog.getExistingDirectory(self,'Dossier des échantillons',self.pub_dir)
        if p: self.le_samples.setText(p)
    def pick_ref(self):
        p,_=QFileDialog.getOpenFileName(self,'Couche de référence indépendante','','Shapefile (*.shp);;GeoPackage (*.gpkg);;Tous les fichiers (*)')
        if p: self.le_ref.setText(p)

    def _sample_path(self,year):
        return os.path.join(self.le_samples.text().strip() or self.pub_dir,f'ValidationSamples_{year}.shp')

    def generate_samples(self):
        outdir=self.le_samples.text().strip() or self.pub_dir; os.makedirs(outdir,exist_ok=True)
        rng=np.random.RandomState(RF_RANDOM_STATE)
        n=int(self.sp_n.value()); min_d=int(self.sp_dist.value())
        made=[]
        for year in self.years:
            arr=np.asarray(self.classified_arrays[year]); gt,prj,_=self.year_geo[year]
            rows,cols=arr.shape; points=[]
            for cid in all_classes:
                pos=np.argwhere(arr==cid)
                if len(pos)==0: continue
                order=rng.permutation(len(pos)); selected=[]
                # Fast spatially-separated greedy selection.
                for j in order:
                    r,c=[int(x) for x in pos[j]]
                    if min_d>0 and any((r-r0)**2+(c-c0)**2 < min_d**2 for r0,c0 in selected):
                        continue
                    selected.append((r,c))
                    if len(selected)>=n: break
                for k,(r,c) in enumerate(selected,1):
                    x,y=_pub_point_xy_from_pixel(gt,r,c)
                    points.append({'sample_id':f'{year}_{cid}_{k}','map_cls':cid,'ref_cls':0,'x':x,'y':y})
            p=_pub_make_point_layer(os.path.join(outdir,f'ValidationSamples_{year}.shp'),year,points,prj)
            made.append(p)
            layer=QgsVectorLayer(p,os.path.basename(p),'ogr')
            if layer.isValid(): QgsProject.instance().addMapLayer(layer)
            self.log_append(f'{year}: {len(points)} points générés.')
        self.log_append(f'✓ Génération terminée: {len(made)} couches.')

    def _reference_features(self, target_crs=None):
        p=self.le_ref.text().strip(); fld=self.le_ref_field.text().strip() or 'class'
        if not p or not os.path.exists(p): raise RuntimeError('Sélectionnez une couche de référence valide.')
        lyr=QgsVectorLayer(p,'PublicationReference','ogr')
        if not lyr.isValid(): raise RuntimeError('Couche de référence invalide.')
        if lyr.fields().indexFromName(fld)<0: raise RuntimeError(f"Champ de référence introuvable: {fld}")
        # BUGFIX: la couche de référence et les points de validation peuvent être
        # dans des CRS différents. Sans reprojection, contains()/intersects()
        # compare des coordonnées incompatibles et échoue silencieusement
        # (ref_cls reste à 0 partout, sans aucun message d'erreur).
        xform = None
        if (target_crs is not None and target_crs.isValid()
                and lyr.crs().isValid() and lyr.crs() != target_crs):
            xform = QgsCoordinateTransform(lyr.crs(), target_crs, QgsProject.instance())
            self.log_append(
                f"⚠ CRS de la référence ({lyr.crs().authid()}) différent des échantillons "
                f"({target_crs.authid()}) — reprojection à la volée appliquée."
            )
        idx = QgsSpatialIndex()
        feats = {}
        for f in lyr.getFeatures():
            f2 = QgsFeature(f)
            if xform is not None:
                g = QgsGeometry(f.geometry())
                try:
                    g.transform(xform)
                    f2.setGeometry(g)
                except Exception:
                    continue
            feats[f2.id()] = f2
            idx.addFeature(f2)
        return lyr, idx, feats, fld

    def attach_reference_labels(self):
        # Determine the CRS of the validation sample points (from the first
        # available year) so the reference layer can be reprojected to match.
        sample_crs = None
        for year in self.years:
            v0 = QgsVectorLayer(self._sample_path(year), 'ValidationCRS', 'ogr')
            if v0.isValid():
                sample_crs = v0.crs()
                break
        try: lyr,idx,feats,fld=self._reference_features(target_crs=sample_crs)
        except Exception as e: QMessageBox.warning(self,'Référence',str(e)); return
        year_fld=self.le_ref_year.text().strip()
        for year in self.years:
            p=self._sample_path(year)
            v=QgsVectorLayer(p,'ValidationEdit','ogr')
            if not v.isValid(): continue
            if v.fields().indexOf('ref_cls')<0: continue
            if not v.isEditable() and not v.startEditing(): continue
            for ft in v.getFeatures():
                pt=ft.geometry()
                ids=idx.intersects(pt.boundingBox())
                assigned=0
                for fid in ids:
                    rf=feats[fid]
                    if year_fld and lyr.fields().indexOf(year_fld)>=0:
                        try:
                            if int(rf[year_fld])!=int(year): continue
                        except Exception: continue
                    geom=rf.geometry()
                    if geom and (geom.contains(pt) or geom.intersects(pt)):
                        try: assigned=int(rf[fld])
                        except Exception: assigned=0
                        if assigned in all_classes: break
                v.changeAttributeValue(ft.id(),v.fields().indexOf('ref_cls'),assigned)
            v.commitChanges(); v.triggerRepaint()
            self.log_append(f'{year}: référence spatiale affectée.')
        self.log_append('✓ Affectation ref_cls terminée.')

    def _read_validation_records(self,year):
        p=self._sample_path(year)
        lyr=QgsVectorLayer(p,'ValidationSamples','ogr')
        if not lyr.isValid(): return []
        gt=self.year_geo[year][0]; arr=np.asarray(self.classified_arrays[year])
        rec=[]
        for ft in lyr.getFeatures():
            try: ref=normalize_class_code(ft['ref_cls'])
            except Exception: ref=0
            if ref not in all_classes: continue
            geom=ft.geometry(); pt=geom.asPoint(); rc=_pub_pixel_from_point(gt,pt.x(),pt.y())
            if rc is None: continue
            r,c=rc
            if r<0 or c<0 or r>=arr.shape[0] or c>=arr.shape[1]: continue
            mp=int(arr[r,c])
            if mp not in all_classes: continue
            rec.append((mp,ref))
        return rec

    def evaluate_all_years(self):
        rows=[]
        for year in self.years:
            rec=self._read_validation_records(year)
            if not rec:
                self.log_append(f'{year}: aucun ref_cls valide.'); continue
            arr=np.asarray(self.classified_arrays[year]); pixel_ha=self.year_geo[year][2]
            # Map-stratified design weights: mapped area / selected valid sample count per mapped class.
            by_map={cid:[r for r in rec if r[0]==cid] for cid in all_classes}
            weights=[]
            for mp,rf in rec:
                denom=len(by_map.get(mp,[])) or 1
                weights.append(_pub_area_ha(arr,mp,pixel_ha)/float(denom))
            ypred=[x[0] for x in rec]; ytrue=[x[1] for x in rec]
            met=_pub_confusion_metrics(ytrue,ypred,weights,all_classes)
            # Native/unweighted diagnostics.
            try: oa_u=accuracy_score(ytrue,ypred); kap_u=cohen_kappa_score(ytrue,ypred,labels=all_classes)
            except Exception: oa_u=kap_u=np.nan
            records_by_stratum={cid:[] for cid in all_classes}
            for (mp,rf),w in zip(rec,weights): records_by_stratum.setdefault(mp,[]).append((rf,mp,w))
            ci=_pub_bootstrap_ci(records_by_stratum,all_classes,B=300,seed=RF_RANDOM_STATE)
            base=os.path.join(self.pub_dir,f'Validation_{year}')
            cm_path=write_csv_rows(base+'_ConfusionMatrix.csv',[["True\\Pred"]+[CLASS_NAMES[c] for c in all_classes]]+
                [[CLASS_NAMES[t]]+list(np.round(met['matrix'][i],4)) for i,t in enumerate(all_classes)])
            mrows=[['Year','OverallAccuracy','AreaAdjustedOA','Kappa','BalancedAccuracy','MCC','MacroF1','N_valid']]
            mrows.append([year, f'{oa_u:.6f}', f'{met["oa"]:.6f}', f'{kap_u:.6f}', f'{met["balanced_accuracy"]:.6f}', f'{met["mcc"]:.6f}', f'{met["macro_f1"]:.6f}',len(rec)])
            write_csv_rows(base+'_Summary.csv',mrows)
            crows=[['Year','Class_ID','Class','UserAccuracy','ProducerAccuracy','F1','UA_CI95_low','UA_CI95_high','PA_CI95_low','PA_CI95_high','Area_ha']]
            for i,cid in enumerate(all_classes):
                crows.append([year,cid,CLASS_NAMES[cid],f'{met["ua"][i]:.6f}',f'{met["pa"][i]:.6f}',f'{met["f1"][i]:.6f}',f'{ci["ua"][cid][0]:.6f}',f'{ci["ua"][cid][1]:.6f}',f'{ci["pa"][cid][0]:.6f}',f'{ci["pa"][cid][1]:.6f}',f'{_pub_area_ha(arr,cid,pixel_ha):.4f}'])
            write_csv_rows(base+'_ByClass.csv',crows)
            rows.append([year,oa_u,met['oa'],met['kappa'],met['balanced_accuracy'],met['mcc'],met['macro_f1'],len(rec),ci['oa'][0],ci['oa'][1]])
            self.log_append(f'{year}: OA={oa_u:.3f} | area-adjusted OA={met["oa"]:.3f} | Kappa={met["kappa"]:.3f} | N={len(rec)}')
            if MATPLOTLIB_AVAILABLE:
                fig,ax=plt.subplots(figsize=(8,7)); ax.imshow(met['matrix'],cmap='Blues'); ax.set_xticks(range(len(all_classes))); ax.set_yticks(range(len(all_classes))); ax.set_xticklabels([CLASS_NAMES[c] for c in all_classes],rotation=45,ha='right',fontsize=7); ax.set_yticklabels([CLASS_NAMES[c] for c in all_classes],fontsize=7); ax.set_xlabel('Predicted / Map'); ax.set_ylabel('Reference'); ax.set_title(f'Final 8-class confusion matrix {year}'); fig.tight_layout(); fig.savefig(base+'_ConfusionMatrix.png',dpi=220); plt.close(fig)
        if rows:
            write_csv_rows(os.path.join(self.pub_dir,'Publication_Accuracy_AllYears.csv'),[['Year','OA','AreaAdjustedOA','Kappa','BalancedAccuracy','MCC','MacroF1','N_valid','OA_CI95_low','OA_CI95_high']]+rows)
            self.log_append('✓ Validation annuelle exportée.')
        else:
            QMessageBox.warning(self,'Validation','Aucune année ne possède des points de référence validés (ref_cls > 0).')

    def make_uncertainty_maps(self):
        made=0
        for year in self.years:
            arr=np.asarray(self.classified_arrays[year]); gt,prj,_=self.year_geo[year]
            unc=np.zeros(arr.shape,dtype=np.uint8)
            for cid in all_classes:
                if cid==3:
                    unc[arr==3]=1; continue
                st=PUB_CLASS_TO_STAGE.get(cid)
                if st is None: continue
                p=os.path.join(self.output_dir,f'RF_Confidence_{year}_Stage{st}.tif')
                if not os.path.exists(p): continue
                ds=gdal.Open(p,gdal.GA_ReadOnly)
                if ds is None: continue
                conf=ds.GetRasterBand(1).ReadAsArray().astype(np.float32); ds=None
                m=(arr==cid)
                unc[m & (conf>=0.80)]=1
                unc[m & (conf>=0.60) & (conf<0.80)]=2
                unc[m & (conf<0.60) & (conf>0)]=3
                unc[m & (conf<=0)]=4
            out=os.path.join(self.pub_dir,f'Publication_Uncertainty_{year}.tif')
            write_raster(out,unc,gt,prj,gdal.GDT_Byte,0)
            add_colored_raster_layer(out,f'Publication_Uncertainty_{year}',{1:QColor(46,125,50),2:QColor(255,193,7),3:QColor(211,47,47),4:QColor(120,120,120)},0)
            made+=1
        self.log_append(f'✓ {made} cartes d\'incertitude créées. 1=haute, 2=moyenne, 3=faible, 4=RF indisponible; Sebkha fixe=1.')

    def run_spatial_temporal_audit(self):
        rows=[]
        # Administrative NoData audit.
        admin_path=self.admin_layer.source().split('|')[0] if self.admin_layer and self.admin_layer.isValid() else ''
        forest_path=str(self.forest_cfg.get('boundary_path','') or '')
        for year in self.years:
            arr=np.asarray(self.classified_arrays[year]); gt,prj,_=self.year_geo[year]
            admin_mask=make_vector_mask(admin_path,arr.shape[0],arr.shape[1],gt,prj) if admin_path else np.ones(arr.shape,dtype=bool)
            outside_nonzero=int(np.count_nonzero((~admin_mask)&(arr!=0)))
            seb=make_vector_mask(self.shp_sebkha,arr.shape[0],arr.shape[1],gt,prj) if self.shp_sebkha else np.zeros(arr.shape,dtype=bool)
            seb_leak=int(np.count_nonzero(seb&(arr!=3)))
            forest_leak=-1
            if forest_path and os.path.exists(forest_path):
                fm=make_vector_mask(forest_path,arr.shape[0],arr.shape[1],gt,prj)
                forest_leak=int(np.count_nonzero(fm&((arr==5)|(arr==6))))
            rows.append([year,outside_nonzero,seb_leak,forest_leak,int(np.count_nonzero(admin_mask&(arr==0)))])
        write_csv_rows(os.path.join(self.pub_dir,'Spatial_Rules_Audit.csv'),[['Year','NonZeroOutsideAdmin','SebkhaLeakagePixels','AgricultureInsideForestBoundary','NoDataInsideAdmin']]+rows)
        # Temporal transitions.
        tr=[]
        for y1,y2 in zip(self.years[:-1],self.years[1:]):
            a=np.asarray(self.classified_arrays[y1]); b=np.asarray(self.classified_arrays[y2]); m=transition_matrix(a,b)
            pairs=sorted([(px,f,t) for (f,t),px in m.items() if f!=t],reverse=True)[:15]
            for px,f,t in pairs: tr.append([y1,y2,f,t,CLASS_NAMES[f],CLASS_NAMES[t],px,px*(self.year_geo[y2][2] if y2 in self.year_geo else PIXEL_HA)])
        write_csv_rows(os.path.join(self.pub_dir,'Temporal_Transitions_Audit.csv'),[['FromYear','ToYear','From_ID','To_ID','From_Class','To_Class','Pixels','Hectares']]+tr)
        self.log_append('✓ Audit spatial + temporel exporté.')

    def _load_pub_presets(self,year):
        cfg,missing=_pub_build_auto_cfg(year,self.output_dir,self.years)
        return cfg,missing

    def run_sensitivity(self):
        reply=QMessageBox.question(self,'Sensibilité','Lancer 4 scénarios globaux (-10%, -5%, +5%, +10%) sur les seuils des années disposant de presets ?\n\nCette opération peut être longue.',QMB_YES,QMB_NO)
        if reply!=QMB_YES: return
        base=os.path.join(self.pub_dir,'ThresholdSensitivity'); os.makedirs(base,exist_ok=True)
        summary=[]
        for delta in (-0.10,-0.05,0.05,0.10):
            scen=f'{delta:+.0%}'.replace('+','plus').replace('-','moins').replace('%','pct')
            scen_dir=os.path.join(base,scen); os.makedirs(scen_dir,exist_ok=True)
            for year in self.years:
                cfg,missing=self._load_pub_presets(year)
                if missing:
                    self.log_append(f'Sensibilité {year} {delta:+.0%}: presets manquants {missing} → ignoré.')
                    continue
                for s in cfg['stages']:
                    cfg['stages'][s]=_pub_perturb_thresholds(cfg['stages'][s],delta)
                try:
                    arr_s,*_=calibrate_and_process_year(year,self.year_data[year],self.shp_sebkha,self.admin_layer,built_up_mask_path=self.year_data[year].get("built_up_mask"),all_prev_memories=[],output_dir=scen_dir,forest_cfg=self.forest_cfg,auto_cfg=cfg)
                    base_arr=np.asarray(self.classified_arrays[year]); pix=self.year_geo[year][2]
                    for cid in all_classes:
                        h0=_pub_area_ha(base_arr,cid,pix); h1=_pub_area_ha(arr_s,cid,pix)
                        summary.append([year,delta,cid,CLASS_NAMES[cid],f'{h0:.4f}',f'{h1:.4f}',f'{(h1-h0):.4f}',f'{(100*(h1-h0)/h0 if h0 else np.nan):.4f}'])
                    self.log_append(f'Sensibilité {year} {delta:+.0%}: OK')
                except Exception as e:
                    self.log_append(f'Sensibilité {year} {delta:+.0%}: ERREUR {e}')
        if summary:
            write_csv_rows(os.path.join(base,'Sensitivity_Global_Thresholds.csv'),[['Year','Delta','Class_ID','Class','Baseline_ha','Scenario_ha','Delta_ha','Delta_pct']]+summary)
            self.log_append('✓ Sensibilité globale exportée.')

    def _pub_stage_split(self,shp_path,field,labels,candidates,needed):
        ds=ogr.Open(shp_path); 
        if not ds: return None,None,False
        lyr=ds.GetLayer(); by={}
        for ft in lyr:
            geom=ft.GetGeometryRef()
            if geom is None: continue
            try: cid=normalize_class_code(ft.GetField(field))
            except Exception: continue
            if cid in needed: by.setdefault(cid,[]).append(geom.Clone())
        if any(len(by.get(c,[]))<2 for c in needed): return None,None,False
        rows,cols=labels.shape; gt=self._ab_gt; prj=self._ab_prj
        memdrv=gdal.GetDriverByName('MEM'); tr=memdrv.Create('',cols,rows,1,gdal.GDT_Byte); va=memdrv.Create('',cols,rows,1,gdal.GDT_Byte); tr.SetGeoTransform(gt); va.SetGeoTransform(gt)
        if prj: tr.SetProjection(prj); va.SetProjection(prj)
        odrv=ogr.GetDriverByName('Memory'); ds1=odrv.CreateDataSource('ab_tr'); ds2=odrv.CreateDataSource('ab_va'); srs=osr.SpatialReference(); srs.ImportFromWkt(prj) if prj else srs.ImportFromEPSG(32632)
        ltr=ds1.CreateLayer('tr',srs,ogr.wkbPolygon); lva=ds2.CreateLayer('va',srs,ogr.wkbPolygon); ltr.CreateField(ogr.FieldDefn(field,ogr.OFTInteger)); lva.CreateField(ogr.FieldDefn(field,ogr.OFTInteger)); rng=np.random.RandomState(RF_RANDOM_STATE)
        for cid,geoms in by.items():
            ids=np.arange(len(geoms)); rng.shuffle(ids); n=max(1,int(round(len(ids)*VALIDATION_FRACTION))); vi=set(ids[:n].tolist())
            for i,g in enumerate(geoms):
                out=lva if i in vi else ltr; ft=ogr.Feature(out.GetLayerDefn()); ft.SetGeometry(g); ft.SetField(field,int(cid)); out.CreateFeature(ft)
        gdal.RasterizeLayer(tr,[1],ltr,burn_values=[1]); gdal.RasterizeLayer(va,[1],lva,burn_values=[1])
        return tr.GetRasterBand(1).ReadAsArray().astype(bool)&candidates, va.GetRasterBand(1).ReadAsArray().astype(bool)&candidates, True

    def run_ablation(self):
        if not SKLEARN_AVAILABLE:
            QMessageBox.warning(self,'Ablation','Scikit-learn non disponible.'); return
        year=self.cb_ab_year.currentText(); stage=int(self.cb_ab_stage.currentText())
        preset=load_preset(year,stage,self.output_dir)
        if not preset:
            _,preset=find_previous_preset(year,stage,self.output_dir,self.years)
        rf_cfg=(preset or {}).get('rf',{}) if preset else {}
        shp=rf_cfg.get('shp',''); field=rf_cfg.get('field','class')
        if not shp or not os.path.exists(shp):
            QMessageBox.warning(self,'Ablation','Aucun Shapefile RF valide dans le preset de cette étape/année.'); return
        ds,rows,cols,gt,prj,names,raw=read_stack_bands(self.year_data[year]['stack']); feats=build_features(ds,rows,cols,names,raw); self._ab_gt=gt; self._ab_prj=prj
        labels=np.zeros((rows,cols),dtype=np.int32); mem=gdal.GetDriverByName('MEM').Create('',cols,rows,1,gdal.GDT_Int32); mem.SetGeoTransform(gt); mem.SetProjection(prj or ''); lyr=ogr.Open(shp).GetLayer(); gdal.RasterizeLayer(mem,[1],lyr,options=[f'ATTRIBUTE={field}']); labels=mem.GetRasterBand(1).ReadAsArray()
        pos=STAGE_POSITIVE[stage]; neg=STAGE_NEGATIVE[stage]; y=np.full(labels.shape,-1,dtype=np.int8); y[np.isin(labels,list(pos))]=1; y[np.isin(labels,list(neg))]=0
        names_stage=[n for n in STAGE_FEATURES[stage] if n in feats]
        if len(names_stage)<2: QMessageBox.warning(self,'Ablation','Feature set insuffisant.'); return
        Xall=np.stack([feats[n] for n in names_stage],axis=-1); finite=np.all(np.isfinite(Xall),axis=-1); cand=finite&(y>=0)
        tr,va,spok=self._pub_stage_split(shp,field,labels,cand,pos|neg)
        if not spok:
            idx=np.flatnonzero(cand); rng=np.random.RandomState(RF_RANDOM_STATE); rng.shuffle(idx); cut=max(1,int(len(idx)*(1-VALIDATION_FRACTION))); tr=np.zeros_like(cand); va=np.zeros_like(cand); tr.flat[idx[:cut]]=True; va.flat[idx[cut:]]=True
        baseline=None; out=[]
        feature_sets=[('All',names_stage,None)] + [(f'Without_{n}',[x for x in names_stage if x!=n],n) for n in names_stage]
        for label_set,flist,removed in feature_sets:
            X=np.stack([feats[n] for n in flist],axis=-1); Xtr=X[tr]; ytr=y[tr]; Xva=X[va]; yva=y[va]
            if len(np.unique(ytr))<2: continue
            rf=RandomForestClassifier(n_estimators=RF_N_ESTIMATORS,max_depth=RF_MAX_DEPTH,min_samples_leaf=RF_MIN_SAMPLES_LEAF,class_weight='balanced',random_state=RF_RANDOM_STATE,n_jobs=RF_N_JOBS)
            rf.fit(Xtr,ytr); pred=rf.predict(Xva); f1=f1_score(yva,pred,average='binary',zero_division=0); oa=accuracy_score(yva,pred); kap=cohen_kappa_score(yva,pred,labels=[0,1]) if len(np.unique(yva))>1 else np.nan
            if label_set=='All': baseline=f1
            out.append([year,stage,label_set,removed or '',len(flist),f'{oa:.6f}',f'{kap:.6f}',f'{f1:.6f}',f'{(f1-baseline):.6f}' if baseline is not None else '0'])
        path=write_csv_rows(os.path.join(self.pub_dir,f'Ablation_{year}_Stage{stage}.csv'),[['Year','Stage','Model','RemovedFeature','NFeatures','Accuracy','Kappa','F1','DeltaF1_vsAll']]+out)
        self.log_append(f'✓ Ablation exportée: {os.path.basename(path)}')

    def export_publication_pack(self):
        prov={
            'module':'Publication Validation Module',
            'script':os.path.basename(globals().get('__file__','QGIS Console')),
            'years':self.years,
            'classes':{str(k):v for k,v in CLASS_NAMES.items()},
            'rf':{'n_estimators':RF_N_ESTIMATORS,'max_depth':RF_MAX_DEPTH,'min_samples_leaf':RF_MIN_SAMPLES_LEAF,'random_state':RF_RANDOM_STATE,'n_jobs':RF_N_JOBS},
            'validation':{'samples_per_map_class':int(self.sp_n.value()),'min_distance_pixels':int(self.sp_dist.value()),'area_adjusted':True,'bootstrap_iterations':300},
            'admin_source':self.admin_layer.source() if self.admin_layer and self.admin_layer.isValid() else '',
            'stable_sebkha_source':self.shp_sebkha,
            'forest_boundary_source':self.forest_cfg.get('boundary_path',''),
            'publication_directory':self.pub_dir,
            'output_files':[p for p in sorted(os.listdir(self.pub_dir))],
        }
        path=os.path.join(self.pub_dir,'Publication_Provenance.json')
        with open(path,'w',encoding='utf-8') as f: json.dump(prov,f,indent=2,ensure_ascii=False)
        # README for reproducibility.
        readme=os.path.join(self.pub_dir,'Publication_README.txt')
        with open(readme,'w',encoding='utf-8') as f:
            f.write('PUBLICATION VALIDATION PACK\n')
            f.write('===========================\n')
            f.write('1) Generate independent stratified validation samples.\n')
            f.write('2) Fill ref_cls using an independent reference source.\n')
            f.write('3) Run the all-years accuracy module.\n')
            f.write('4) Review area-adjusted OA and 95% bootstrap CIs.\n')
            f.write('5) Review Spatial_Rules_Audit and Temporal_Transitions_Audit.\n')
            f.write('6) Run threshold sensitivity and RF feature ablation as supporting analyses.\n')
            f.write('Important: metrics are publication-grade only when reference data are genuinely independent of training data.\n')
        self.log_append('✓ Publication provenance + README exportés.')
        QMessageBox.information(self,'Publication Pack',f'Fichiers exportés dans:\n{self.pub_dir}')


classified_arrays = {}
yearly_areas_data = {}
cumulative_memories = []
year_geo = {}

# ---------- REPRISE AUTOMATIQUE ----------
_checkpoint = load_checkpoint(output_dir)
_completed = [y for y in SELECTED_YEARS if y in _checkpoint.get("completed_years", [])]
_resume_years = set()
if _completed:
    print(f"[Checkpoint] Années déjà terminées : {', '.join(_completed)} — reprise {'ACTIVÉE' if RUN['resume'] else 'désactivée'} (réglage de la fenêtre de démarrage).")
    if RUN["resume"]:
        for _y in _completed:
            if _y not in year_data:
                continue
            _loaded = _load_completed_year_result(_y, output_dir)
            if _loaded is None:
                print(f"[Checkpoint] sortie finale absente/invalide pour {_y} → recalcul.")
                continue
            _arr, _path, _gt, _prj, _mem = _loaded
            classified_arrays[_y] = _arr
            yearly_areas_data[_y] = _mem["areas"]
            cumulative_memories.append(_mem)
            year_geo[_y] = (_gt, _prj, pixel_area_ha_from_gt(_gt))
            _resume_years.add(_y)
            print(f"[Checkpoint] ✓ année {_y} rechargée depuis la sortie finale.")
        print(f"[Checkpoint] reprise active — années rechargées: {sorted(_resume_years)}")
    else:
        print("[Checkpoint] l'utilisateur a choisi de recommencer toutes les années.")

# ---------- ANCRE haute précision (facultative) : l'ancre est traitée en PREMIER ----------
_anchor_cfg = _resolve_anchor(RUN["anchor"], parent_dir, SELECTED_YEARS, year_data, output_dir, TARGET_YEARS)
print("[ANCRE] " + (f"{_anchor_cfg['year']} (stack : {os.path.basename(str(_anchor_cfg['stack']))}) — niveau de stabilité ≤ {_anchor_cfg['min_level']}" if _anchor_cfg else "non utilisée"))

# L'ancre n'est classée EN PREMIER que si sa carte finale n'existe pas encore : sinon l'ordre choisi (ascendant : de la plus ancienne à la plus récente) est respecté.
_anchor_ready = bool(_anchor_cfg) and (find_lulc_map(output_dir, _anchor_cfg["year"]) is not None or int(_anchor_cfg["year"]) in PREVIOUS_MAPS)
_PROCESS_SEQ = _process_order(SELECTED_YEARS, _anchor_cfg, anchor_ready=_anchor_ready)
print("[ORDRE] Séquence de traitement : " + " → ".join(_PROCESS_SEQ))
if _anchor_cfg:
    if _anchor_ready:
        print(f"[ORDRE] L'ancre {_anchor_cfg['year']} a déjà une carte finale : elle sert d'appui à toutes les autres années et n'est PAS traitée en premier.")
    elif str(_anchor_cfg["year"]) in _PROCESS_SEQ and _PROCESS_SEQ[0] == str(_anchor_cfg["year"]) and len(_PROCESS_SEQ) > 1:
        print(f"[ORDRE] ⚠ L'ancre {_anchor_cfg['year']} n'a pas encore de carte finale : elle est classée EN PREMIER (les autres années en ont besoin), puis les autres années dans l'ordre choisi.")
_year_seq = [y_ for y_ in _PROCESS_SEQ if y_ in year_data and y_ not in _resume_years]
for yr in _PROCESS_SEQ:
    if yr not in year_data:
        continue
    if yr in _resume_years:
        print(f"[Checkpoint] ⏭ {yr} déjà terminée — recalcul ignoré.")
        continue
    YEAR_PROGRESS_TEXT = f"année {_year_seq.index(yr) + 1} sur {len(_year_seq)}"

    print(f"\n{'='*70}")
    print(f"TRAITEMENT DE L'ANNÉE {yr}")
    print(f"{'='*70}")

    start_stage = 1
    while True:
        auto_cfg = None
        if batch_mode and start_stage == 1:
            auto_cfg, missing = build_auto_cfg(yr)
            if missing:
                print(f"⚠️ [{yr}] Presets manquants pour étape(s) {missing} → cette année repasse en INTERACTIF.")
                auto_cfg = None
        try:
            arr, path, gtf, prj, mem = calibrate_and_process_year(
                yr,
                year_data[yr],
                shp_sebkha,
                admin_layer,
                built_up_mask_path=year_data[yr].get("built_up_mask"),
                all_prev_memories=cumulative_memories,
                output_dir=output_dir,
                forest_cfg=forest_cfg,
                auto_cfg=auto_cfg,
                start_stage=start_stage,
                stage_masks=_stage_masks_for_year(_stage_mask_cfg, yr, TARGET_YEARS),
                mask_priority=_mask_priority,
                temporal_cfg=_temporal_cfg,
                anchor_cfg=_anchor_cfg,
                review_implausible=RUN.get("review_implausible", True)
            )
            break
        except StageBackRequested as back:
            start_stage = max(1, int(back.stage_num) - 1)
            auto_cfg = None
            print(f"[↩] Précédent depuis l'étape {back.stage_num} → réouverture de l'étape {start_stage}.")
            continue
        except BaseException:
            progress_close()                                       # une erreur ou une annulation ne laisse jamais la fenêtre d'attente ouverte
            raise

    classified_arrays[yr] = arr
    yearly_areas_data[yr] = mem["areas"]
    cumulative_memories.append(mem)
    year_geo[yr] = (gtf, prj, pixel_area_ha_from_gt(gtf))

    # ---------- FINAL AREA QA : contrôles SÉPARÉS ----------
    # Échec dur : complétude, limites, cohérence des 8 classes. Indicateur (jamais un échec) : écart contour vectoriel / contour rastérisé.
    admin_src = admin_layer.source().split("|")[0] if admin_layer and admin_layer.isValid() else ""
    if not admin_src:
        raise RuntimeError("AREA QA: Study Area layer invalide ou source introuvable.")
    admin_mask_qa = make_vector_mask(
        admin_src, arr.shape[0], arr.shape[1], gtf, prj
    )
    admin_pixels_qa = int(np.count_nonzero(admin_mask_qa))
    classified_inside_qa = int(np.count_nonzero(admin_mask_qa & (arr > 0)))
    unclassified_inside_qa = int(np.count_nonzero(admin_mask_qa & (arr == 0)))
    nonzero_outside_qa = int(np.count_nonzero((~admin_mask_qa) & (arr != 0)))
    class_pixels_inside_qa = sum(int(np.count_nonzero(admin_mask_qa & (arr == cid))) for cid in all_classes)
    pixel_ha_qa = pixel_area_ha_from_gt(gtf)
    study_area_raster_qa = admin_pixels_qa * pixel_ha_qa
    study_area_polygon_qa = vector_area_ha_in_raster_crs(admin_src, prj)
    class_area_sum_qa = sum(
        float(np.count_nonzero(arr == cid)) * pixel_ha_qa
        for cid in all_classes
    )
    area_difference_qa = class_area_sum_qa - study_area_raster_qa           # cohérence interne : doit être 0
    _qa = area_qa_assess(admin_pixels_qa, unclassified_inside_qa, nonzero_outside_qa, class_pixels_inside_qa, study_area_polygon_qa, study_area_raster_qa)
    raster_polygon_gap_qa = _qa["gap_ha"]
    study_area_qa = study_area_raster_qa
    qa_csv = os.path.join(output_dir, f"Area_QA_{yr}.csv")
    _fmt = lambda v: "" if not np.isfinite(v) else f"{v:.6f}"
    qa_rows = [
        ["Year", "StudyArea_Polygon_ha", "StudyArea_Raster_ha", "Classified_ha", "Classified_minus_Raster_ha", "Raster_minus_Polygon_ha", "Raster_minus_Polygon_percent",
         "Admin_pixels", "Classified_pixels", "Unclassified_pixels", "NonZeroOutsideAdmin_pixels", "Coverage_percent",
         "Check_completeness", "Check_boundary", "Check_consistency", "Geometry_indicator", "Status"],
        [yr, _fmt(study_area_polygon_qa), f"{study_area_raster_qa:.4f}", f"{class_area_sum_qa:.4f}", f"{area_difference_qa:.8f}", _fmt(raster_polygon_gap_qa), _fmt(_qa["gap_percent"]),
         admin_pixels_qa, classified_inside_qa, unclassified_inside_qa, nonzero_outside_qa,
         f"{(100.0 * classified_inside_qa / admin_pixels_qa) if admin_pixels_qa else 0.0:.6f}",
         "PASS" if _qa["checks"]["completeness"] else "FAIL", "PASS" if _qa["checks"]["boundary"] else "FAIL", "PASS" if _qa["checks"]["consistency"] else "FAIL",
         _qa["geometry"], _qa["status"]]
    ]
    write_csv_rows(qa_csv, qa_rows)
    # ---------- VISIBLE FINAL AREA QA WINDOW ----------
    # La fenêtre s'affiche TOUJOURS avant toute exception. Seul un échec DUR (complétude / limites / cohérence) arrête le traitement.
    _coverage_qa = (100.0 * classified_inside_qa / admin_pixels_qa) if admin_pixels_qa else 0.0
    _qa_pass = _qa["hard_pass"]
    _qa_status = {"PASS": "✓ PASS", "PASS_AVEC_AVERTISSEMENT": "⚠ PASS (écart géométrique du contour à documenter)", "FAIL": "✗ FAIL"}[_qa["status"]]
    _geo_note = ("indicateur non calculable (aire du contour vectoriel indisponible)" if _qa["geometry"] == "NA" else
                 f"aire vectorielle {study_area_polygon_qa:,.2f} ha · aire rastérisée {study_area_raster_qa:,.2f} ha · écart {raster_polygon_gap_qa:+,.2f} ha ({_qa['gap_percent']:+.3f} %) — "
                 f"{'dans la tolérance' if _qa['geometry'] == 'OK' else 'AU-DELÀ de la tolérance de ' + format(100.0 * AREA_QA_POLYGON_TOLERANCE, 'g') + ' % : à documenter'}")
    _qa_class_rows = []
    for _cid in all_classes:
        _cname = CLASS_NAMES[_cid]
        _carea = float(np.count_nonzero(arr == _cid)) * pixel_ha_qa
        _qa_class_rows.append((_cname, _carea))

    print("\n" + "━" * 80)
    print(f"YEAR {yr} — AREA QA")
    print("━" * 80)
    print(f"Study Area raster : {study_area_raster_qa:,.2f} ha ({admin_pixels_qa:,} px)")
    print(f"Contour           : {_geo_note}")
    for _cname, _carea in _qa_class_rows:
        print(f"{_cname:<19}: {_carea:,.2f} ha")
    print("-" * 80)
    print(f"{'SUM CLASSES':<19}: {class_area_sum_qa:,.2f} ha")
    print(f"{'DIFFERENCE':<19}: {area_difference_qa:,.8f} ha  (classes - zone rastérisée ; doit être 0)")
    print(f"{'COVERAGE':<19}: {_coverage_qa:,.4f} %")
    print(f"{'STATUS':<19}: {_qa_status}")
    for _m in _qa["messages"]:
        print(f"   • {_m}")
    print("━" * 80 + "\n")

    _qa_dlg = FinalYearAreaQADialog(
        yr, study_area_qa, _qa_class_rows, class_area_sum_qa,
        area_difference_qa, _coverage_qa, _qa_status,
        admin_pixels_qa, unclassified_inside_qa, nonzero_outside_qa,
        parent=None, geometry_note=_geo_note
    )
    show_dialog(_qa_dlg)
    del _qa_dlg

    if not _qa_pass:
        raise RuntimeError(
            f"AREA QA FAILED [{yr}] : " + " | ".join(_qa["messages"]) +
            f" | Zone rastérisée={study_area_raster_qa:.4f} ha | Classes={class_area_sum_qa:.4f} ha | Différence={area_difference_qa:.8f} ha"
        )

    # CHECKPOINT: l'année est marquée comme terminée seulement après
    # l'écriture du LULC, des statistiques et la validation AREA QA.
    _completed_now = merge_checkpoint_years(
        _checkpoint.get("completed_years", []), SELECTED_YEARS, list(classified_arrays.keys()), TARGET_YEARS
    )
    save_checkpoint(output_dir, _completed_now)
    print(f"[Checkpoint] ✓ année {yr} validée et enregistrée.")

# Global area table
global_area_csv = os.path.join(output_dir, "Areas_All_Years.csv")
_area_rows = [["Year", "Class_ID", "Class", "Area_ha"]]
for yr, data in yearly_areas_data.items():
    for cid, cname in CLASS_NAMES.items():
        _area_rows.append([yr, cid, cname, f"{data.get(cname, 0.0):.4f}"])
if set(SELECTED_YEARS) != set(TARGET_YEARS):
    # Traitement partiel : on conserve les surfaces des autres années déjà calculées.
    _area_rows = merge_area_rows(_read_csv_rows(global_area_csv), _area_rows, TARGET_YEARS)
write_csv_rows(global_area_csv, _area_rows)

print("\n[✓] TRAITEMENT TERMINÉ.")
print(f"[✓] Résultats: {output_dir}")
print("[✓] Sebkha imposée UNE SEULE FOIS au début par masque stable.")
print("[✓] Sebkha jamais reclassée comme Water/Bareland.")
print("[✓] Nearest-neighbour filling à l’intérieur des limites administratives puis résidu Bareland.")
print("[✓] RF avec variables spécifiques à chaque étape.")

print("[✓] Validation + confidence maps + permutation importance.")
try:
    classification_stage_report(output_dir, _STAGE_T0, {"Years classified": ", ".join(str(_y) for _y in sorted(classified_arrays)), "RF trees": RF_N_ESTIMATORS, "RF max depth": RF_MAX_DEPTH,
                                "RF min leaf": RF_MIN_SAMPLES_LEAF, "Random state": RF_RANDOM_STATE, "Validation fraction": VALIDATION_FRACTION, "Checkpoint version": CHECKPOINT_VERSION}, AREA_NAME, REPORT_LANG)
except Exception as _exc:
    print("[Rapport HTML d'étape] échec (le traitement lui-même est terminé) : " + str(_exc))

# ====================== ANALYSE DE CHANGEMENT (AUTO + INTERACTIVE) ======================
if len(classified_arrays) >= 2:
    print("\n[→] Ouverture de la fenêtre d'analyse de changement…")
    change_dlg = ChangeDetectionDialog(
        classified_arrays,
        yearly_areas_data,
        year_geo,
        output_dir
    )
    # Auto-run once so the full time series is processed immediately, then keep
    # the window open for additional user-selected pairs.
    change_dlg.run_analysis()
    show_dialog(change_dlg)
else:
    print("\n⚠️ Moins de 2 années classifiées — analyse de changement ignorée.")

# ====================== PUBLICATION VALIDATION MODULE ======================
print("\n[→] Ouverture du Publication Validation Module…")
pub_validation_dlg = PublicationValidationDialog(
    classified_arrays,
    yearly_areas_data,
    year_geo,
    output_dir,
    year_data,
    admin_layer,
    shp_sebkha,
    forest_cfg,
)
show_dialog(pub_validation_dlg)
