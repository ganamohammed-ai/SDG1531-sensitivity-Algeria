# -*- coding: utf-8 -*-
# SDG 15.3.1 REFERENCE PIPELINE — STAGE 04B / 08 : Transition matrices, statistics and reviewer report — QGIS
"""
MATRICES DE TRANSITION LULC + STATISTIQUES + FIGURES + CARTES POUR LA REVUE PAR LES PAIRS (script COMPLÉMENTAIRE et INDÉPENDANT)
QGIS / PyQGIS — à coller dans la Console Python de QGIS (ou exécuter via l'éditeur).

À PARTIR des cartes finales LULC_<ZONE>_<année>.tif (toutes les années sont détectées, de la plus ancienne à la plus récente), le script calcule pour CHAQUE PAIRE DE DEUX ANNÉES CONSÉCUTIVES et pour
la période PREMIÈRE -> DERNIÈRE ANNÉE :
  * les MATRICES DE TRANSITION en pixels, en hectares, en % de ligne (destination de chaque classe) et en % de colonne (origine de chaque classe), avec totaux ;
  * les statistiques de PONTIUS : gain, perte, changement net, ÉCHANGE (swap), changement total, persistance, stabilité ; décomposition du paysage en QUANTITÉ + ÉCHANGE + DÉPLACEMENT ;
  * les surfaces par classe et par année, les taux de variation (ha/an, %/an, taux composé) ;
  * l'ANALYSE D'INTENSITÉ (Aldwaik & Pontius 2012) : niveaux intervalle, catégorie et transition, avec la mention Active / Dormante ;
  * des CONTRÔLES de cohérence (sommes des lignes / colonnes, pixels exclus) ;
  * les FIGURES (PNG 300 dpi, SVG ou PDF en option) : surfaces empilées, trajectoires, gains / pertes, cartes de chaleur des matrices, décomposition, intensité, diagramme de flux (Sankey) ;
  * les CARTES (PNG avec légende, échelle, nord) : une par année, une de changement par période, un montage ;
  * un RAPPORT HTML autonome (images incluses), un classeur EXCEL de tableaux supplémentaires, tous les tableaux en CSV, les définitions et références (Methods_and_Definitions.md), la provenance (empreintes SHA-256, versions).
ET exporte chaque carte LULC en « ENVI CLASSIFICATION » (.dat + .hdr avec NOMS DES CLASSES et couleurs), en GeoTIFF classé (palette + noms de catégories) et avec un style QGIS (.qml). Les cartes de changement
(de x 10 + vers) sont exportées de la même façon, avec les noms « Built-up → Water ».

LIMITES (à lire)
  - Les surfaces sont des surfaces CARTOGRAPHIQUES (comptage de pixels), pas des surfaces ajustées par l'exactitude : l'estimation d'aires avec intervalles de confiance exige un échantillon de validation (Olofsson et al. 2014).
  - Seuls les pixels CLASSÉS aux deux dates (dans la zone d'étude s'il y en a une) entrent dans une matrice ; les pixels exclus sont comptés dans les contrôles.
  - Les cartes doivent partager la même grille (taille, géotransformation, projection).
"""
import os
import platform
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

PIPELINE_BUILD = "2026.10-b2c202ecb277"
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
import re
import csv
import json
import time
import math
import base64
import hashlib
import platform
import datetime
import calendar
import html as _html
import numpy as np

from osgeo import gdal, ogr, osr

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap, to_hex
    from matplotlib.patches import Patch, PathPatch, Rectangle
    from matplotlib.path import Path as MplPath     # JAMAIS « Path » : ce nom appartient à pathlib et la console QGIS partage ses noms avec les autres scripts et extensions
    MPL = True
except Exception:  # pragma: no cover
    MPL = False
try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    XLSX = True
except Exception:  # pragma: no cover
    XLSX = False

VERSION = "TRANSITION-REPORT 1.0"
CLASSES = tuple(range(1, 9))
CLASS_NAMES = {1: "Built-up", 2: "Water", 3: "Sebkha", 4: "Bareland / Rock", 5: "Cropland", 6: "Fallow", 7: "Forest", 8: "Rangeland"}
CLASS_COLORS = {1: (220, 50, 50), 2: (100, 140, 210), 3: (214, 230, 245), 4: (185, 195, 205), 5: (255, 225, 130), 6: (240, 175, 0), 7: (135, 185, 120), 8: (100, 245, 140)}
MAP_RE = re.compile(r"^LULC_.*?_((?:19|20)\d{2})\.tif$", re.I)
SKIP_NAME_PARTS = ("_Original", "_Edited", "_Retro", "_Corrige")
REFERENCES = [
    "Pontius, R.G. Jr., Santacruz, A. (2014). Quantity, exchange, and shift components of difference in a square contingency table. International Journal of Remote Sensing 35(21), 7543-7554.",
    "Pontius, R.G. Jr., Shusas, E., McEachern, M. (2004). Detecting important categorical land changes while accounting for persistence. Agriculture, Ecosystems & Environment 101, 251-268.",
    "Aldwaik, S.Z., Pontius, R.G. Jr. (2012). Intensity analysis to unify measurements of size and stationarity of land changes by interval, category, and transition. Landscape and Urban Planning 106, 103-114.",
    "Olofsson, P., Foody, G.M., Herold, M., Stehman, S.V., Woodcock, C.E., Wulder, M.A. (2014). Good practices for estimating area and assessing accuracy of land change. Remote Sensing of Environment 148, 42-57.",
]

TEXT = {
    "en": {"class": "Class", "year": "Year", "area_ha": "Area (ha)", "area_pct": "Area (%)", "from_to": "From \\ To", "total": "Total", "total_in": "Total {y}", "px": "pixels", "ha": "ha", "gain": "Gain (ha)", "loss": "Loss (ha)",
           "net": "Net change (ha)", "swap": "Swap (ha)", "total_change": "Total change (ha)", "persist": "Persistence (ha)", "stability": "Stability (% of class at {y})", "area_y": "Area {y} (ha)",
           "diff": "Difference (ha)", "pct_change": "Change (%)", "ha_yr": "Rate (ha/yr)", "pct_yr": "Rate (%/yr)", "cagr": "Compound rate (%/yr)", "component": "Component", "pct_valid": "% of valid area",
           "quantity": "Quantity (net)", "exchange": "Exchange", "shift": "Shift", "changed": "Total change", "persistence": "Persistence", "interval": "Interval", "years": "Years", "valid_area": "Valid area (ha)",
           "changed_ha": "Changed (ha)", "s_int": "Annual change intensity S (%/yr)", "u_int": "Uniform intensity U (%/yr)", "speed": "Interval is", "fast": "Fast", "slow": "Slow", "uniform": "Uniform",
           "gain_int": "Gain intensity (%/yr)", "loss_int": "Loss intensity (%/yr)", "gain_status": "Gain is", "loss_status": "Loss is", "active": "Active", "dormant": "Dormant", "target": "Target class",
           "source": "Source class", "trans_int": "Transition intensity R (%/yr)", "uni_trans": "Uniform intensity W (%/yr)", "status": "Status", "check": "Check", "value": "Value", "pass": "PASS", "fail": "FAIL",
           "domain_px": "Pixels in domain", "valid_px": "Pixels classified at both dates", "unclass_a": "Unclassified in first year", "unclass_b": "Unclassified in second year", "sum_matrix": "Matrix total = valid pixels",
           "rows_t1": "Row totals = class areas in first year", "cols_t2": "Column totals = class areas in second year", "stable": "Stable", "unclassified": "Unclassified", "other_flows": "Other flows",
           "fig_area_stacked": "Land-cover composition by year", "fig_area_lines": "Class area trajectories", "fig_gain_loss": "Gains and losses by class", "fig_decomp": "Components of landscape change",
           "fig_heat_ha": "Transition matrix (ha)", "fig_heat_pct": "Transition matrix (row %, destination of each class)", "fig_sankey": "Land-cover flows", "fig_int_interval": "Interval level: annual change intensity",
           "fig_int_category": "Category level: gain and loss intensity", "fig_int_trans": "Transition level: intensity of transitions", "scale": "km", "legend": "Legend", "net_first_last": "Net change {a}–{b} (ha)"},
    "fr": {"class": "Classe", "year": "Année", "area_ha": "Surface (ha)", "area_pct": "Surface (%)", "from_to": "De \\ Vers", "total": "Total", "total_in": "Total {y}", "px": "pixels", "ha": "ha", "gain": "Gain (ha)", "loss": "Perte (ha)",
           "net": "Changement net (ha)", "swap": "Échange (ha)", "total_change": "Changement total (ha)", "persist": "Persistance (ha)", "stability": "Stabilité (% de la classe en {y})", "area_y": "Surface {y} (ha)",
           "diff": "Différence (ha)", "pct_change": "Variation (%)", "ha_yr": "Taux (ha/an)", "pct_yr": "Taux (%/an)", "cagr": "Taux composé (%/an)", "component": "Composante", "pct_valid": "% de la surface valide",
           "quantity": "Quantité (net)", "exchange": "Échange", "shift": "Déplacement", "changed": "Changement total", "persistence": "Persistance", "interval": "Intervalle", "years": "Années", "valid_area": "Surface valide (ha)",
           "changed_ha": "Changé (ha)", "s_int": "Intensité annuelle de changement S (%/an)", "u_int": "Intensité uniforme U (%/an)", "speed": "L'intervalle est", "fast": "Rapide", "slow": "Lent", "uniform": "Uniforme",
           "gain_int": "Intensité du gain (%/an)", "loss_int": "Intensité de la perte (%/an)", "gain_status": "Le gain est", "loss_status": "La perte est", "active": "Actif", "dormant": "Dormant", "target": "Classe cible",
           "source": "Classe source", "trans_int": "Intensité de transition R (%/an)", "uni_trans": "Intensité uniforme W (%/an)", "status": "Statut", "check": "Contrôle", "value": "Valeur", "pass": "OK", "fail": "ÉCHEC",
           "domain_px": "Pixels du domaine", "valid_px": "Pixels classés aux deux dates", "unclass_a": "Non classés la 1re année", "unclass_b": "Non classés la 2e année", "sum_matrix": "Total de la matrice = pixels valides",
           "rows_t1": "Totaux des lignes = surfaces de la 1re année", "cols_t2": "Totaux des colonnes = surfaces de la 2e année", "stable": "Stable", "unclassified": "Non classé", "other_flows": "Autres flux",
           "fig_area_stacked": "Composition de l'occupation du sol par année", "fig_area_lines": "Trajectoires des surfaces par classe", "fig_gain_loss": "Gains et pertes par classe", "fig_decomp": "Composantes du changement du paysage",
           "fig_heat_ha": "Matrice de transition (ha)", "fig_heat_pct": "Matrice de transition (% de ligne, destination de chaque classe)", "fig_sankey": "Flux d'occupation du sol", "fig_int_interval": "Niveau intervalle : intensité annuelle de changement",
           "fig_int_category": "Niveau catégorie : intensité du gain et de la perte", "fig_int_trans": "Niveau transition : intensité des transitions", "scale": "km", "legend": "Légende", "net_first_last": "Changement net {a}–{b} (ha)"},
}


TEXT["en"].update({"dates_title": "Choice of the study dates", "role": "Role", "why": "Why this date", "gap": "Years since previous date", "in_main": "In the main analysis", "yes_": "yes", "no_": "no (diagnostic / excluded)"})
TEXT["fr"].update({"dates_title": "Choix des dates d'étude", "role": "Rôle", "why": "Pourquoi cette date", "gap": "Années depuis la date précédente", "in_main": "Dans l'analyse principale", "yes_": "oui", "no_": "non (diagnostique / exclue)"})
TEXT["en"].update({"climate_title": "Climate context of the mapped years", "season_mm": "Rain {s} (mm)", "season_z": "z-score {s}", "rank_dry": "Rank (1 = driest of {n})", "jf_pct": "Jan–Feb rain (% of normal)",
                   "long_mm": "Rain {s} (mm)", "long_z": "z-score {s}", "prod_idx": "Productivity index", "prod_rank": "Productivity rank (1 = lowest of {n})", "drought": "Drought flag", "yes": "DROUGHT", "no": "—", "rain_only": "Rain deficit only", "prod_idx_src": "Productivity index, {src}", "prod_rank_src": "Productivity rank, {src} (1 = lowest of {n})"})
TEXT["fr"].update({"climate_title": "Contexte climatique des années cartographiées", "season_mm": "Pluie {s} (mm)", "season_z": "Écart réduit {s}", "rank_dry": "Rang (1 = la plus sèche sur {n})", "jf_pct": "Pluie jan–fév (% de la normale)",
                   "long_mm": "Pluie {s} (mm)", "long_z": "Écart réduit {s}", "prod_idx": "Indice de productivité", "prod_rank": "Rang de productivité (1 = le plus bas sur {n})", "drought": "Sécheresse", "yes": "SÉCHERESSE", "no": "—", "rain_only": "Déficit de pluie seul", "prod_idx_src": "Indice de productivité, {src}", "prod_rank_src": "Rang de productivité, {src} (1 = le plus bas sur {n})"})


def tr(lang, key, **kw):
    s = TEXT.get(lang, TEXT["en"]).get(key, TEXT["en"].get(key, key))
    return s.format(**kw) if kw else s


# ============================================================================
# 1. LOGIQUE PURE (testée sans QGIS ni GDAL)
# ============================================================================
def find_lulc_maps(folder):
    """{année: chemin} des cartes finales dans `folder` puis `folder/LULC` (copies _Original / _Edited / _Retro / _Corrige ignorées ; le dossier direct est prioritaire)."""
    out = {}
    for d in (os.path.join(folder, "LULC"), folder):
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            m = MAP_RE.match(fn)
            if m and not any(p in fn for p in SKIP_NAME_PARTS):
                out[m.group(1)] = os.path.join(d, fn)
    return dict(sorted(out.items(), key=lambda kv: int(kv[0])))


def normalize_lulc(arr):
    """Codes 1-8 ; l'ancien Matorral (9) est lu comme Forest (7) ; le reste = 0 (non classé)."""
    a = np.asarray(arr).astype(np.int16)
    a = np.where(a == 9, 7, a)
    a[(a < 1) | (a > 8)] = 0
    return a.astype(np.uint8)


def period_list(years, include_first_last=True):
    """Périodes : paires d'années consécutives, + première -> dernière s'il y a plus de deux années."""
    ys = sorted({int(y) for y in years})
    pairs = [(ys[i], ys[i + 1], "consecutive") for i in range(len(ys) - 1)]
    if include_first_last and len(ys) > 2:
        pairs.append((ys[0], ys[-1], "first_last"))
    return pairs


def class_areas_px(arr, domain=None):
    """Pixels par classe (1-8) dans le domaine."""
    a = np.asarray(arr)
    if domain is not None:
        a = a[np.asarray(domain, bool)]
    cnt = np.bincount(a.ravel().astype(np.int64), minlength=10)
    return {k: int(cnt[k]) for k in CLASSES}


def transition_matrix_counts(a, b, domain=None):
    """
    Matrice de transition en PIXELS (8 x 8 ; ligne = classe à la date 1, colonne = classe à la date 2) sur les pixels classés aux DEUX dates (et dans le domaine),
    + informations : pixels du domaine, pixels valides, non classés à chaque date.
    """
    a, b = np.asarray(a), np.asarray(b)
    if a.shape != b.shape:
        raise ValueError(f"Les deux cartes n'ont pas la même taille : {a.shape} et {b.shape}.")
    dom = np.ones(a.shape, bool) if domain is None else np.asarray(domain, bool)
    use = (a > 0) & (b > 0) & dom
    cnt = np.bincount(a[use].astype(np.int64) * 10 + b[use].astype(np.int64), minlength=100)
    M = cnt.reshape(10, 10)[1:9, 1:9].astype(np.int64)
    info = {"domain_px": int(dom.sum()), "valid_px": int(use.sum()), "unclassified_a": int((dom & (a == 0)).sum()), "unclassified_b": int((dom & (b == 0)).sum()), "unclassified_either": int((dom & ((a == 0) | (b == 0))).sum())}
    return M, info


def safe_div(n, d):
    n, d = np.asarray(n, float), np.asarray(d, float)
    return np.divide(n, d, out=np.full(np.broadcast(n, d).shape, np.nan), where=d != 0)


def row_percent(M):
    """% de ligne : destination de chaque classe de la date 1 (chaque ligne totalise 100)."""
    return 100.0 * safe_div(M, np.asarray(M).sum(axis=1, keepdims=True))


def col_percent(M):
    """% de colonne : origine de chaque classe de la date 2 (chaque colonne totalise 100)."""
    return 100.0 * safe_div(M, np.asarray(M).sum(axis=0, keepdims=True))


def pontius_class_table(M, px_ha):
    """Par classe : surfaces (matrice), gain, perte, net, ÉCHANGE (swap = 2 x min(gain, perte)), changement total, persistance, stabilité (%). Surfaces en ha."""
    M = np.asarray(M, np.int64)
    rowt, colt, diag = M.sum(axis=1), M.sum(axis=0), np.diag(M)
    rows = []
    for idx, k in enumerate(CLASSES):
        gain, loss = int(colt[idx] - diag[idx]), int(rowt[idx] - diag[idx])
        rows.append({"class": k, "name": CLASS_NAMES[k], "area_t1_ha": rowt[idx] * px_ha, "area_t2_ha": colt[idx] * px_ha, "gain_ha": gain * px_ha, "loss_ha": loss * px_ha, "net_ha": (gain - loss) * px_ha,
                     "swap_ha": 2 * min(gain, loss) * px_ha, "total_change_ha": (gain + loss) * px_ha, "persistence_ha": int(diag[idx]) * px_ha,
                     "stability_pct": (100.0 * diag[idx] / rowt[idx]) if rowt[idx] else float("nan")})
    return rows


def landscape_decomposition(M, px_ha):
    """
    Décomposition du changement TOTAL du paysage (Pontius & Santacruz 2014) : D = Q (quantité, net) + X (échange) + S (déplacement), en ha et en % de la surface valide.
      Q = 1/2 somme |gain_j - perte_j| ; X = somme sur i<j de 2 x min(n_ij, n_ji) ; S = D - Q - X.
    """
    M = np.asarray(M, np.int64)
    n = int(M.sum())
    persist = int(np.trace(M))
    D = n - persist
    loss, gain = M.sum(axis=1) - np.diag(M), M.sum(axis=0) - np.diag(M)
    Q = 0.5 * float(np.abs(gain - loss).sum())
    X = float(sum(2 * min(M[i, j], M[j, i]) for i in range(8) for j in range(i + 1, 8)))
    S = max(0.0, D - Q - X)
    pct = lambda v: (100.0 * v / n) if n else float("nan")
    return {"valid_px": n, "valid_ha": n * px_ha, "persistence_ha": persist * px_ha, "changed_ha": D * px_ha, "quantity_ha": Q * px_ha, "exchange_ha": X * px_ha, "shift_ha": S * px_ha,
            "persistence_pct": pct(persist), "changed_pct": pct(D), "quantity_pct": pct(Q), "exchange_pct": pct(X), "shift_pct": pct(S)}


def annual_rates(area1, area2, dyears):
    """Variation d'une surface entre deux dates : différence, % total, ha/an, %/an (linéaire) et taux composé annuel."""
    d = area2 - area1
    pct = (100.0 * d / area1) if area1 > 0 else float("nan")
    cagr = (100.0 * ((area2 / area1) ** (1.0 / dyears) - 1.0)) if (area1 > 0 and area2 > 0 and dyears > 0) else float("nan")
    return {"diff_ha": d, "pct_change": pct, "ha_per_year": d / dyears if dyears else float("nan"), "pct_per_year": pct / dyears if (dyears and not math.isnan(pct)) else float("nan"), "cagr_pct": cagr}


def intensity_label(x, uniform, eps=1e-12):
    """Active si l'intensité dépasse l'intensité uniforme, Dormante si elle est inférieure."""
    return "active" if x > uniform + eps else ("dormant" if x < uniform - eps else "uniform")


def intensity_analysis(Ms, years, px_ha):
    """
    ANALYSE D'INTENSITÉ (Aldwaik & Pontius 2012) sur des intervalles consécutifs. Ms = [matrice de pixels par intervalle], years = années de début de chaque intervalle + dernière.
      Intervalle : S_t = D_t / (N_t x Δ_t) ; U = somme D_t / somme (N_t x Δ_t) ; rapide si S_t > U.
      Catégorie  : gain_j = (gain_j / Δ) / taille_j(t+1) ; perte_i = (perte_i / Δ) / taille_i(t) ; comparées à S_t.
      Transition (gain de n) : R_in = (c_in / Δ) / taille_i(t) ; W_n = (gain_n / Δ) / (N - taille_n(t)). Transition (perte de m) : Q_mj = (c_mj / Δ) / taille_j(t+1) ; V_m = (perte_m / Δ) / (N - taille_m(t+1)).
    Toutes les intensités en %/an.
    """
    ys = sorted(int(y) for y in years)
    out = {"intervals": [], "category": [], "transition_gain": [], "transition_loss": [], "U": float("nan")}
    num_u = den_u = 0.0
    prepared = []
    for k, M in enumerate(Ms):
        M = np.asarray(M, np.int64)
        a, b = ys[k], ys[k + 1]
        dlt = b - a
        N = int(M.sum())
        D = N - int(np.trace(M))
        num_u += D
        den_u += N * dlt
        prepared.append((a, b, dlt, M, N, D))
    U = (100.0 * num_u / den_u) if den_u else float("nan")
    out["U"] = U
    for (a, b, dlt, M, N, D) in prepared:
        S = (100.0 * D / (N * dlt)) if N and dlt else float("nan")
        out["intervals"].append({"a": a, "b": b, "delta": dlt, "valid_ha": N * px_ha, "changed_ha": D * px_ha, "S": S, "U": U, "label": intensity_label(S, U) if not math.isnan(S) else "uniform"})
        rowt, colt, diag = M.sum(axis=1), M.sum(axis=0), np.diag(M)
        for idx, k_ in enumerate(CLASSES):
            gain, loss = int(colt[idx] - diag[idx]), int(rowt[idx] - diag[idx])
            g_int = (100.0 * (gain / dlt) / colt[idx]) if colt[idx] else float("nan")
            l_int = (100.0 * (loss / dlt) / rowt[idx]) if rowt[idx] else float("nan")
            if rowt[idx] == 0 and colt[idx] == 0:
                continue
            out["category"].append({"a": a, "b": b, "class": k_, "name": CLASS_NAMES[k_], "gain_ha": gain * px_ha, "loss_ha": loss * px_ha, "gain_int": g_int, "loss_int": l_int, "S": S,
                                    "gain_label": intensity_label(g_int, S) if not math.isnan(g_int) else "dormant", "loss_label": intensity_label(l_int, S) if not math.isnan(l_int) else "dormant"})
            if gain > 0:                                         # transitions qui ALIMENTENT la classe n
                W = (100.0 * (gain / dlt) / (N - rowt[idx])) if (N - rowt[idx]) else float("nan")
                for j, i_cls in enumerate(CLASSES):
                    if j == idx or M[j, idx] == 0 or rowt[j] == 0:
                        continue
                    R = 100.0 * (M[j, idx] / dlt) / rowt[j]
                    out["transition_gain"].append({"a": a, "b": b, "target": k_, "target_name": CLASS_NAMES[k_], "source": i_cls, "source_name": CLASS_NAMES[i_cls], "ha": int(M[j, idx]) * px_ha, "R": R, "W": W,
                                                   "label": intensity_label(R, W) if not math.isnan(W) else "uniform"})
            if loss > 0:                                         # transitions qui PRENNENT à la classe m
                V = (100.0 * (loss / dlt) / (N - colt[idx])) if (N - colt[idx]) else float("nan")
                for j, j_cls in enumerate(CLASSES):
                    if j == idx or M[idx, j] == 0 or colt[j] == 0:
                        continue
                    Q = 100.0 * (M[idx, j] / dlt) / colt[j]
                    out["transition_loss"].append({"a": a, "b": b, "source": k_, "source_name": CLASS_NAMES[k_], "target": j_cls, "target_name": CLASS_NAMES[j_cls], "ha": int(M[idx, j]) * px_ha, "Q": Q, "V": V,
                                                   "label": intensity_label(Q, V) if not math.isnan(V) else "uniform"})
    return out


def analyze(maps, years, px_ha, domain=None, include_first_last=True):
    """
    Analyse complète. maps = {année: tableau 1-8}. Retourne {"years", "px_ha", "areas_px", "periods": [{"a", "b", "kind", "delta", "M", "info", "classes", "landscape", "rates"}], "intensity", "domain_px"}.
    Les surfaces par classe de chaque année sont comptées dans le domaine (tous pixels classés de l'année) ; les matrices sur les pixels classés aux deux dates.
    """
    ys = sorted({int(y) for y in years})
    areas_px = {y: class_areas_px(maps[str(y)], domain) for y in ys}
    periods, cons = [], []
    for (a, b, kind) in period_list(ys, include_first_last):
        M, info = transition_matrix_counts(maps[str(a)], maps[str(b)], domain)
        dlt = b - a
        classes = pontius_class_table(M, px_ha)
        rates = {r["class"]: annual_rates(areas_px[a][r["class"]] * px_ha, areas_px[b][r["class"]] * px_ha, dlt) for r in classes}
        periods.append({"a": a, "b": b, "kind": kind, "delta": dlt, "M": M, "info": info, "classes": classes, "landscape": landscape_decomposition(M, px_ha), "rates": rates})
        if kind == "consecutive":
            cons.append(M)
    intensity = intensity_analysis(cons, ys, px_ha) if cons else {"intervals": [], "category": [], "transition_gain": [], "transition_loss": [], "U": float("nan")}
    dom_px = int(np.asarray(domain).sum()) if domain is not None else int(np.asarray(maps[str(ys[0])]).size)
    return {"years": ys, "px_ha": px_ha, "areas_px": areas_px, "periods": periods, "intensity": intensity, "domain_px": dom_px}


def consistency_checks(result):
    """Contrôles par période : total de la matrice = pixels valides ; totaux de lignes = surfaces de la date 1 sur les pixels valides ; totaux de colonnes = surfaces de la date 2 ; pixels exclus."""
    rows = []
    for p in result["periods"]:
        M, info = p["M"], p["info"]
        n = int(M.sum())
        ok_sum = n == info["valid_px"]
        rows.append({"period": f"{p['a']}-{p['b']}", "check": "sum_matrix", "value": n, "expected": info["valid_px"], "ok": ok_sum})
        rows.append({"period": f"{p['a']}-{p['b']}", "check": "rows_t1", "value": int(M.sum(axis=1).sum()), "expected": n, "ok": int(M.sum(axis=1).sum()) == n})
        rows.append({"period": f"{p['a']}-{p['b']}", "check": "cols_t2", "value": int(M.sum(axis=0).sum()), "expected": n, "ok": int(M.sum(axis=0).sum()) == n})
        rows.append({"period": f"{p['a']}-{p['b']}", "check": "domain_px", "value": info["domain_px"], "expected": "", "ok": True})
        rows.append({"period": f"{p['a']}-{p['b']}", "check": "unclass_a", "value": info["unclassified_a"], "expected": "", "ok": True})
        rows.append({"period": f"{p['a']}-{p['b']}", "check": "unclass_b", "value": info["unclassified_b"], "expected": "", "ok": True})
    return rows


# ---------------- contexte climatique (CHIRPS journalier au format ClimateEngine, indice de productivité)
def parse_chirps_csv(path):
    """
    Pluie journalière {date: mm} depuis un CSV « ClimateEngine » : séparateur « ; », virgule décimale, une ligne d'en-tête, « AAAA-MM-JJ;valeur ». ValueError si le fichier n'a pas ce format.
    """
    daily = {}
    with open(path, encoding="utf-8-sig") as f:
        lines = f.read().splitlines()
    for ln in lines[1:]:
        ln = ln.strip().replace('"', "")
        if not ln:
            continue
        parts = ln.split(";")
        if len(parts) < 2:
            raise ValueError(f"Format CSV pluie non reconnu (ligne « {ln[:40]} ») : attendu AAAA-MM-JJ;valeur avec séparateur « ; ».")
        try:
            daily[datetime.date.fromisoformat(parts[0].strip())] = float(parts[1].strip().replace(",", "."))
        except ValueError:
            raise ValueError(f"Format CSV pluie non reconnu (ligne « {ln[:40]} »).")
    if len(daily) < 365 * 10:
        raise ValueError("Le CSV de pluie contient moins de 10 ans de données journalières.")
    return daily


def window_total(daily, year, m0, m1, min_cover=0.95):
    """Cumul de pluie (mm) de la fenêtre mois m0 -> mois m1 se terminant dans l'année `year` (si m0 > m1 la fenêtre commence l'année précédente) ; None si moins de 95 % des jours sont présents."""
    start = datetime.date(year - 1 if m0 > m1 else year, m0, 1)
    end = datetime.date(year, m1, calendar.monthrange(year, m1)[1])
    n = (end - start).days + 1
    vals = [daily[d] for d in (start + datetime.timedelta(days=i) for i in range(n)) if d in daily]
    return sum(vals) if len(vals) >= min_cover * n else None


def climate_context(daily, map_years, season=(10, 3), long_season=(9, 5), baseline=(1991, 2020), z_flag=-1.0, productivity=None, productivity2=None, prod_labels=None):
    """
    Pour chaque année cartographiée : pluie de la saison de croissance (par défaut oct–mars) et de la saison longue (sept–mai), écart réduit par rapport à la normale `baseline`, rang parmi toutes les saisons disponibles
    (1 = la plus sèche), pluie de janvier–février en % de la normale, indice de productivité (si fourni) et son rang, DRAPEAU de sécheresse (écart réduit de la saison de croissance <= z_flag).
    Les deux saisons sont données car le verdict dépend de la fenêtre : un mois de mai très pluvieux peut masquer un hiver très sec dans le cumul sept–mai.
    """
    ys_all = sorted({d.year for d in daily})
    def series(win):
        return {y: v for y, v in ((y, window_total(daily, y, *win)) for y in ys_all) if v is not None}
    s1, s2, jf = series(season), series(long_season), series((1, 2))
    def stats(ser):
        base = [ser[y] for y in range(baseline[0], baseline[1] + 1) if y in ser]
        if len(base) < 10:
            raise ValueError(f"Normale {baseline[0]}–{baseline[1]} : moins de 10 saisons complètes dans le CSV de pluie.")
        return float(np.mean(base)), float(np.std(base, ddof=1))
    (m1_, sd1), (m2_, sd2), (mj, _sdj) = stats(s1), stats(s2), stats(jf)
    prank = None
    if productivity:
        vals = list(productivity.values())
        prank = {y: 1 + sum(1 for v in vals if v < productivity[y]) for y in productivity}
    prank2 = None
    if productivity2:
        vals2 = list(productivity2.values())
        prank2 = {y: 1 + sum(1 for v in vals2 if v < productivity2[y]) for y in productivity2}
    labels = tuple(prod_labels or PRODUCTIVITY_LABELS)
    rows = []
    for y in sorted(int(v) for v in map_years):
        v1, v2, j = s1.get(y), s2.get(y), jf.get(y)
        z1 = (v1 - m1_) / sd1 if (v1 is not None and sd1 > 0) else float("nan")
        z2 = (v2 - m2_) / sd2 if (v2 is not None and sd2 > 0) else float("nan")
        rows.append({"year": y, "season": season, "long_season": long_season, "season_mm": v1, "season_z": z1, "season_rank": (1 + sum(1 for w in s1.values() if w < v1)) if v1 is not None else None, "n_seasons": len(s1),
                     "jan_feb_pct": (100.0 * j / mj) if (j is not None and mj > 0) else float("nan"), "long_mm": v2, "long_z": z2,
                     "prod_idx": (productivity or {}).get(y), "prod_rank": (prank or {}).get(y), "n_prod": len(productivity) if productivity else 0, "drought": bool(not math.isnan(z1) and z1 <= z_flag),
                     "prod2_idx": (productivity2 or {}).get(y), "prod2_rank": (prank2 or {}).get(y), "n_prod2": len(productivity2) if productivity2 else 0, "prod_labels": labels if productivity2 else None})
        r = rows[-1]
        # CONFIRMATION par la végétation : avec l'indice de productivité, la sécheresse n'est confirmée que si l'année est parmi les 25 % les plus basses ; sans l'indice, rien à confirmer (None)
        # avec deux séries : la PREMIÈRE qui couvre l'année fait foi (ex. MODIS ; Landsat seulement pour une année absente de MODIS, comme 1999) ; les rangs ne sont jamais comparés d'une série à l'autre
        if r["prod_rank"]:
            r["confirmed"] = bool(r["drought"] and r["prod_rank"] <= max(1, round(0.25 * r["n_prod"])))
        elif r["prod2_rank"]:
            r["confirmed"] = bool(r["drought"] and r["prod2_rank"] <= max(1, round(0.25 * r["n_prod2"])))
        else:
            r["confirmed"] = None
    return rows


MIN_PROD_COVERAGE_PCT = 50.0       # une année couverte à moins de ce % du maximum de pixels valides n'est pas classée (moyenne calculée sur une surface partielle)
PRODUCTIVITY_LABELS = ("MODIS", "Landsat")      # noms des deux séries : principale (champ 5), secondaire (champ 5b, pour les années absentes de la principale, ex. 1999)


def parse_productivity_csv(path, return_info=False):
    """
    Série de productivité par année {année: valeur}. Deux formats :
      - celui de l'étape 01B / du pipeline : colonne « year » et première colonne « index_… » (de préférence index_tous) ;
      - un export simple « Year, Mean_Productivity, Valid_Pixels_Count » (moyenne spatiale par année).
    Si le nombre de pixels valides est connu (n_tous ou Valid_Pixels_Count), les années couvertes à moins de MIN_PROD_COVERAGE_PCT % du maximum sont EXCLUES du classement.
    return_info=True : (série, {"format", "excluded": [années], "max_pixels"}).
    """
    with open(path, encoding="utf-8-sig") as f:
        _text = f.read()
    _first = _text.split("\n", 1)[0]
    rd = csv.DictReader(_text.splitlines(), delimiter=(";" if _first.count(";") > _first.count(",") else ","))       # virgule ou point-virgule (Excel en français)
    cols = rd.fieldnames or []
    rows = list(rd)
    low = {c.strip().lower(): c for c in cols}
    info = {"format": None, "excluded": [], "max_pixels": None}
    icol = "index_tous" if "index_tous" in cols else next((c for c in cols if c.lower().startswith("index")), None)
    if "year" in low and icol is not None:
        ycol, vcol, ncol, info["format"] = low["year"], icol, low.get("n_tous"), "index"
    elif "year" in low and "mean_productivity" in low:
        ycol, vcol, ncol, info["format"] = low["year"], low["mean_productivity"], low.get("valid_pixels_count"), "mean"
    else:
        raise ValueError("CSV de productivité : colonnes « year » et « index_… » (ou « Year » et « Mean_Productivity ») introuvables.")
    num = lambda v: float(str(v).replace(",", ".").strip())
    pts = {}
    for r in rows:
        try:
            y = int(float(str(r[ycol]).strip()))
            v = num(r[vcol])
            n = num(r[ncol]) if (ncol and str(r.get(ncol, "")).strip() != "") else None
        except (ValueError, TypeError):
            continue
        pts[y] = (v, n)
    ns = [n for _v, n in pts.values() if n is not None]
    mx = max(ns) if ns else None
    info["max_pixels"] = mx
    out = {}
    for y, (v, n) in sorted(pts.items()):
        if mx and n is not None and 100.0 * n / mx < MIN_PROD_COVERAGE_PCT:
            info["excluded"].append(y)
            continue
        out[y] = v
    return (out, info) if return_info else out


def month_name_range(win):
    names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{names[win[0] - 1]}–{names[win[1] - 1]}"


def table_climate(rows, lang="en"):
    if not rows:
        return []
    s, ls, n = month_name_range(rows[0]["season"]), month_name_range(rows[0]["long_season"]), rows[0]["n_seasons"]
    hdr = [tr(lang, "year"), tr(lang, "season_mm", s=s), tr(lang, "season_z", s=s), tr(lang, "rank_dry", n=n), tr(lang, "jf_pct"), tr(lang, "long_mm", s=ls), tr(lang, "long_z", s=ls)]
    has_prod = any(r["prod_idx"] is not None for r in rows)
    has_prod2 = any(r.get("prod2_idx") is not None for r in rows)
    labels = next((r["prod_labels"] for r in rows if r.get("prod_labels")), None)
    if has_prod2:                       # deux séries : colonnes séparées, nommées par leur source (jamais fusionnées)
        n1, n2 = next((r["n_prod"] for r in rows if r["n_prod"]), 0), next((r["n_prod2"] for r in rows if r["n_prod2"]), 0)
        hdr += [tr(lang, "prod_rank_src", src=labels[0], n=n1), tr(lang, "prod_rank_src", src=labels[1], n=n2)]
    elif has_prod:
        hdr += [tr(lang, "prod_idx"), tr(lang, "prod_rank", n=next((r["n_prod"] for r in rows if r["n_prod"]), 0))]
    hdr.append(tr(lang, "drought"))
    out = [hdr]
    for r in rows:
        line = [r["year"], _f(r["season_mm"], 0) if r["season_mm"] is not None else "", _f(r["season_z"]), r["season_rank"] if r["season_rank"] is not None else "", _f(r["jan_feb_pct"], 0), _f(r["long_mm"], 0) if r["long_mm"] is not None else "", _f(r["long_z"])]
        if has_prod2:
            line += [r["prod_rank"] if r["prod_rank"] is not None else "", r["prod2_rank"] if r.get("prod2_rank") is not None else ""]
        elif has_prod:
            line += [_f(r["prod_idx"], 3) if r["prod_idx"] is not None else "", r["prod_rank"] if r["prod_rank"] is not None else ""]
        line.append(tr(lang, "rain_only" if (r["drought"] and r.get("confirmed") is False) else ("yes" if r["drought"] else "no")))
        out.append(line)
    return out


def table_dates(all_years, climate=None, excluded=None, lang="en"):
    """
    Tableau « choix des dates » (à reprendre dans la méthode) : pour chaque date d'étude, son RÔLE et sa justification (YEAR_ROLES de la configuration), l'intervalle depuis la date précédente et, si le contexte
    climatique est fourni, l'écart réduit de la pluie de saison de croissance, le déficit de janvier–février, le rang de productivité, l'indicateur de sécheresse et la présence dans l'analyse principale.
    """
    roles = globals().get("YEAR_ROLES", {})
    ys = sorted(int(y) for y in all_years)
    ex = {str(y) for y in (excluded or [])}
    cl = {r["year"]: r for r in (climate or [])}
    hdr = [tr(lang, "year"), tr(lang, "role"), tr(lang, "why"), tr(lang, "gap")]
    two = bool(climate) and any(r.get("prod2_rank") is not None for r in climate)
    if climate:
        lab = next((r["prod_labels"] for r in climate if r.get("prod_labels")), ("1", "2"))
        pr_hdr = ([tr(lang, "prod_rank_src", src=lab[0], n=next((r["n_prod"] for r in climate if r["n_prod"]), 0)), tr(lang, "prod_rank_src", src=lab[1], n=next((r["n_prod2"] for r in climate if r["n_prod2"]), 0))] if two
                  else [tr(lang, "prod_rank", n=next((r["n_prod"] for r in climate if r["n_prod"]), 0))])
        hdr += [tr(lang, "season_z", s=month_name_range(climate[0]["season"])), tr(lang, "jf_pct")] + pr_hdr + [tr(lang, "drought")]
    hdr.append(tr(lang, "in_main"))
    rows = [hdr]
    for i, y in enumerate(ys):
        rl = roles.get(y)
        role, why = ((rl[0], rl[1]) if lang == "en" else (rl[2], rl[3])) if rl else ("—", "")
        line = [y, role, why, (y - ys[i - 1]) if i else ""]
        if climate:
            r = cl.get(y)
            if r:
                line += [_f(r["season_z"]), _f(r["jan_feb_pct"], 0)] + ([r["prod_rank"] if r["prod_rank"] is not None else "", r["prod2_rank"] if r.get("prod2_rank") is not None else ""] if two else [r["prod_rank"] if r["prod_rank"] is not None else ""]) \
                    + [tr(lang, "rain_only" if (r["drought"] and r.get("confirmed") is False) else ("yes" if r["drought"] else "no"))]
            else:
                line += [""] * (4 + (1 if two else 0))
        line.append(tr(lang, "no_" if str(y) in ex else "yes_"))
        rows.append(line)
    return rows


DATE_CRITERIA = {"en": ("Dates are chosen so that they (i) cover the UNCCD baseline period (2000–2015) and the monitoring years; (ii) never use an anomalous year as the sole reference: a documented drought year is kept as a DIAGNOSTIC date and analysed in a separate sensitivity run; "
                        "(iii) include a normal-year witness inside the baseline interval; (iv) keep intervals as comparable as possible, the unequal lengths being handled by annualised rates and intensities; "
                        "(v) rest on maps of comparable classification whose accuracy is assessed independently (stage 05B)."),
                 "fr": ("Les dates sont choisies pour (i) couvrir la période de base UNCCD (2000–2015) et les années de suivi ; (ii) ne jamais prendre une année anormale pour seule référence : une année de sécheresse documentée est conservée comme date DIAGNOSTIQUE et analysée dans une analyse de sensibilité séparée ; "
                        "(iii) inclure une année témoin normale à l'intérieur de l'intervalle de base ; (iv) garder des intervalles aussi comparables que possible, les longueurs inégales étant traitées par des taux et des intensités annualisés ; "
                        "(v) s'appuyer sur des cartes de classification comparable dont l'exactitude est évaluée indépendamment (étape 05B).")}


def select_years(all_years, wanted):
    """Années retenues pour l'analyse principale (ordre chronologique) : l'intersection avec les années disponibles ; ValueError s'il en reste moins de deux."""
    ys = [str(y) for y in sorted((int(y) for y in all_years))]
    keep = [y for y in ys if wanted is None or y in {str(w) for w in wanted}]
    if len(keep) < 2:
        raise ValueError("Il faut au moins DEUX années cochées pour l'analyse.")
    return keep


# ---------------- tableaux (listes de lignes) pour CSV / XLSX / HTML
def _f(v, nd=2):
    return "" if (v is None or (isinstance(v, float) and math.isnan(v))) else (f"{v:.{nd}f}" if isinstance(v, (float, np.floating)) else v)


def table_areas(result, lang="en"):
    ys, px = result["years"], result["px_ha"]
    hdr = [tr(lang, "class")] + [tr(lang, "area_y", y=y) for y in ys] + [tr(lang, "area_pct") + f" {y}" for y in ys]
    rows = [hdr]
    tot = {y: sum(result["areas_px"][y].values()) for y in ys}
    for k in CLASSES:
        rows.append([f"{k} — {CLASS_NAMES[k]}"] + [_f(result["areas_px"][y][k] * px) for y in ys] + [_f(100.0 * result["areas_px"][y][k] / tot[y]) if tot[y] else "" for y in ys])
    rows.append([tr(lang, "total")] + [_f(tot[y] * px) for y in ys] + ["100.00"] * len(ys))
    return rows


def table_rates(result, lang="en"):
    """Taux de variation par classe pour chaque période (consécutive et première -> dernière)."""
    rows = [[tr(lang, "class"), tr(lang, "interval"), tr(lang, "diff"), tr(lang, "pct_change"), tr(lang, "ha_yr"), tr(lang, "pct_yr"), tr(lang, "cagr")]]
    for p in result["periods"]:
        for k in CLASSES:
            r = p["rates"][k]
            rows.append([f"{k} — {CLASS_NAMES[k]}", f"{p['a']}–{p['b']}", _f(r["diff_ha"]), _f(r["pct_change"]), _f(r["ha_per_year"]), _f(r["pct_per_year"]), _f(r["cagr_pct"], 3)])
    return rows


def table_matrix(M, a, b, px_ha, unit="ha", lang="en"):
    """Matrice avec totaux (unit = 'px' | 'ha' | 'row_pct' | 'col_pct')."""
    M = np.asarray(M)
    if unit == "px":
        V, nd = M.astype(np.int64), 0
    elif unit == "ha":
        V, nd = M * px_ha, 2
    elif unit == "row_pct":
        V, nd = row_percent(M), 2
    else:
        V, nd = col_percent(M), 2
    fmt = (lambda v: int(v)) if unit == "px" else (lambda v: _f(float(v), nd))
    hdr = [f"{tr(lang, 'from_to')} ({a} → {b})"] + [f"{k} — {CLASS_NAMES[k]}" for k in CLASSES] + [tr(lang, "total_in", y=a)]
    rows = [hdr]
    for i, k in enumerate(CLASSES):
        total = V[i].sum() if unit in ("px", "ha") else (100.0 if (unit == "row_pct" and M[i].sum()) else float("nan"))
        rows.append([f"{k} — {CLASS_NAMES[k]}"] + [fmt(V[i, j]) for j in range(8)] + [fmt(total)])
    if unit in ("px", "ha"):
        rows.append([tr(lang, "total_in", y=b)] + [fmt(V[:, j].sum()) for j in range(8)] + [fmt(V.sum())])
    elif unit == "col_pct":
        rows.append([tr(lang, "total_in", y=b)] + ["100.00" if M[:, j].sum() else "" for j in range(8)] + [""])
    return rows


def table_classes(p, lang="en"):
    a, b = p["a"], p["b"]
    rows = [[tr(lang, "class"), tr(lang, "area_y", y=a), tr(lang, "area_y", y=b), tr(lang, "gain"), tr(lang, "loss"), tr(lang, "net"), tr(lang, "swap"), tr(lang, "total_change"), tr(lang, "persist"), tr(lang, "stability", y=a)]]
    for r in p["classes"]:
        rows.append([f"{r['class']} — {r['name']}"] + [_f(r[k]) for k in ("area_t1_ha", "area_t2_ha", "gain_ha", "loss_ha", "net_ha", "swap_ha", "total_change_ha", "persistence_ha", "stability_pct")])
    return rows


def table_landscape(result, lang="en"):
    rows = [[tr(lang, "interval"), tr(lang, "years"), tr(lang, "valid_area"), tr(lang, "persistence") + " (ha)", tr(lang, "persistence") + " (%)", tr(lang, "changed") + " (ha)", tr(lang, "changed") + " (%)",
             tr(lang, "quantity") + " (ha)", tr(lang, "quantity") + " (%)", tr(lang, "exchange") + " (ha)", tr(lang, "exchange") + " (%)", tr(lang, "shift") + " (ha)", tr(lang, "shift") + " (%)"]]
    for p in result["periods"]:
        L = p["landscape"]
        rows.append([f"{p['a']}–{p['b']}", p["delta"], _f(L["valid_ha"]), _f(L["persistence_ha"]), _f(L["persistence_pct"]), _f(L["changed_ha"]), _f(L["changed_pct"]), _f(L["quantity_ha"]), _f(L["quantity_pct"]),
                     _f(L["exchange_ha"]), _f(L["exchange_pct"]), _f(L["shift_ha"]), _f(L["shift_pct"])])
    return rows


def table_intensity_interval(result, lang="en"):
    rows = [[tr(lang, "interval"), tr(lang, "years"), tr(lang, "valid_area"), tr(lang, "changed_ha"), tr(lang, "s_int"), tr(lang, "u_int"), tr(lang, "speed")]]
    for r in result["intensity"]["intervals"]:
        rows.append([f"{r['a']}–{r['b']}", r["delta"], _f(r["valid_ha"]), _f(r["changed_ha"]), _f(r["S"], 4), _f(r["U"], 4), tr(lang, {"active": "fast", "dormant": "slow"}.get(r["label"], "uniform"))])
    return rows


def table_intensity_category(result, lang="en"):
    rows = [[tr(lang, "interval"), tr(lang, "class"), tr(lang, "gain"), tr(lang, "gain_int"), tr(lang, "gain_status"), tr(lang, "loss"), tr(lang, "loss_int"), tr(lang, "loss_status"), tr(lang, "s_int")]]
    for r in result["intensity"]["category"]:
        rows.append([f"{r['a']}–{r['b']}", f"{r['class']} — {r['name']}", _f(r["gain_ha"]), _f(r["gain_int"], 4), tr(lang, r["gain_label"] if r["gain_label"] != "uniform" else "uniform"), _f(r["loss_ha"]), _f(r["loss_int"], 4),
                     tr(lang, r["loss_label"] if r["loss_label"] != "uniform" else "uniform"), _f(r["S"], 4)])
    return rows


def table_intensity_transition(result, kind="gain", lang="en"):
    key = "transition_gain" if kind == "gain" else "transition_loss"
    first, second = ("target", "source") if kind == "gain" else ("source", "target")
    rows = [[tr(lang, "interval"), tr(lang, first), tr(lang, second), tr(lang, "ha"), tr(lang, "trans_int"), tr(lang, "uni_trans"), tr(lang, "status")]]
    for r in result["intensity"][key]:
        rows.append([f"{r['a']}–{r['b']}", f"{r[first]} — {r[first + '_name']}", f"{r[second]} — {r[second + '_name']}", _f(r["ha"]), _f(r["R"] if kind == "gain" else r["Q"], 4), _f(r["W"] if kind == "gain" else r["V"], 4),
                     tr(lang, r["label"] if r["label"] != "uniform" else "uniform")])
    return rows


def table_checks(result, lang="en"):
    rows = [[tr(lang, "interval"), tr(lang, "check"), tr(lang, "value"), "Expected", tr(lang, "status")]]
    names = {"sum_matrix": "sum_matrix", "rows_t1": "rows_t1", "cols_t2": "cols_t2", "domain_px": "domain_px", "unclass_a": "unclass_a", "unclass_b": "unclass_b"}
    for r in consistency_checks(result):
        rows.append([r["period"], tr(lang, names[r["check"]]), r["value"], r["expected"], tr(lang, "pass" if r["ok"] else "fail") if r["expected"] != "" else ""])
    return rows


def build_all_tables(result, lang="en", climate=None, all_years=None, excluded=None):
    """Tous les tableaux nommés (ordre de publication) : {nom: lignes}. Les noms servent de noms de fichiers CSV et de feuilles Excel (31 caractères maximum)."""
    t = {"01_Class_areas": table_areas(result, lang), "02_Change_rates": table_rates(result, lang), "03_Landscape_components": table_landscape(result, lang)}
    if climate:
        t["04_Climate_context"] = table_climate(climate, lang)
    if globals().get("YEAR_ROLES"):
        t["05_Date_selection"] = table_dates(all_years or result["years"], climate, excluded, lang)
    for p in result["periods"]:
        tag = f"{p['a']}_{p['b']}"
        t[f"M_px_{tag}"] = table_matrix(p["M"], p["a"], p["b"], result["px_ha"], "px", lang)
        t[f"M_ha_{tag}"] = table_matrix(p["M"], p["a"], p["b"], result["px_ha"], "ha", lang)
        t[f"M_rowpct_{tag}"] = table_matrix(p["M"], p["a"], p["b"], result["px_ha"], "row_pct", lang)
        t[f"M_colpct_{tag}"] = table_matrix(p["M"], p["a"], p["b"], result["px_ha"], "col_pct", lang)
        t[f"Classes_{tag}"] = table_classes(p, lang)
    t["Intensity_interval"] = table_intensity_interval(result, lang)
    t["Intensity_category"] = table_intensity_category(result, lang)
    t["Intensity_trans_gain"] = table_intensity_transition(result, "gain", lang)
    t["Intensity_trans_loss"] = table_intensity_transition(result, "loss", lang)
    t["Checks"] = table_checks(result, lang)
    return t


def methods_markdown(result, params, lang="en"):
    """Définitions, formules et références (texte à reprendre dans la section Méthodes / les matériaux supplémentaires)."""
    ys = result["years"]
    s = [f"# Land-cover transition analysis — methods and definitions\n", f"Generated by {VERSION} on {time.strftime('%Y-%m-%d %H:%M')}.\n",
         f"**Maps:** {', '.join(str(y) for y in ys)} · **pixel area:** {result['px_ha']:.4f} ha · **domain pixels:** {result['domain_px']:,}\n",
         "## Transition matrix\nFor two dates t1 and t2 the matrix cell (i, j) is the number of pixels (or hectares) of class i at t1 that are class j at t2, over the pixels classified at BOTH dates (inside the study area when one is given). "
         "Row totals are the class areas at t1, column totals the class areas at t2. Row % gives the destination of each class, column % the origin of each class.\n",
         "## Gain, loss, net change, swap\nFor class j: gain = column total − diagonal ; loss = row total − diagonal ; net = gain − loss ; swap = 2·min(gain, loss) ; total change = gain + loss ; stability = diagonal / row total.\n",
         "## Components of landscape change (Pontius & Santacruz 2014)\nTotal change D = off-diagonal sum = quantity Q + exchange X + shift S, with Q = ½ Σ|gain_j − loss_j| (net change in quantity), X = Σ_{i<j} 2·min(n_ij, n_ji) (pairwise exchange) and S = D − Q − X (allocation shift, e.g. cyclic transitions among three or more classes).\n",
         "## Annual rates\nlinear rate = (A2 − A1)/Δt (ha/yr) ; relative linear rate = 100·(A2 − A1)/(A1·Δt) (%/yr) ; compound annual rate = 100·((A2/A1)^(1/Δt) − 1).\n",
         "## Intensity analysis (Aldwaik & Pontius 2012)\nInterval level: S_t = 100·D_t/(N_t·Δ_t) (%/yr), uniform intensity U = 100·ΣD_t/Σ(N_t·Δ_t); an interval is fast if S_t > U, slow otherwise. "
         "Category level (within interval t): gain intensity G_j = 100·(gain_j/Δ)/size_j(t+1), loss intensity L_i = 100·(loss_i/Δ)/size_i(t); a category is active if its intensity exceeds S_t, dormant otherwise. "
         "Transition level: for gain of n, R_in = 100·(c_in/Δ)/size_i(t) against W_n = 100·(gain_n/Δ)/(N − size_n(t)); for loss of m, Q_mj = 100·(c_mj/Δ)/size_j(t+1) against V_m = 100·(loss_m/Δ)/(N − size_m(t+1)). A transition is active if its intensity exceeds the uniform one.\n",
         "## Limitations\nAreas are MAP areas (pixel counts), not accuracy-adjusted estimates: confidence intervals for areas require an independent reference sample (Olofsson et al. 2014). Pixels unclassified at either date are excluded from the matrix and counted in the consistency table.\n",
         "## Parameters\n" + "\n".join(f"- {k}: {v}" for k, v in params.items()) + "\n", "## References\n" + "\n".join(f"- {r}" for r in REFERENCES) + "\n"]
    return "\n".join(s)


# ---------------- ENVI classification, QML, noms de classes
def class_tables(names_by_code, colors_by_code, max_code=None):
    """(noms, couleurs) indexés de 0 à max_code (0 = Unclassified, noir ; trous = « Class k »)."""
    mc = max(names_by_code) if max_code is None else int(max_code)
    names, cols = ["Unclassified"], [(0, 0, 0)]
    for k in range(1, mc + 1):
        names.append(names_by_code.get(k, f"Class {k}"))
        cols.append(tuple(colors_by_code.get(k, (0, 0, 0))))
    return names, cols


def envi_header_text(rows, cols, names_by_code, colors_by_code, description, map_info=None, coord_sys=None, max_code=None, band_name="Class"):
    """En-tête ENVI d'une CLASSIFICATION : file type = ENVI Classification, classes, class lookup (RVB), class names."""
    names, colors = class_tables(names_by_code, colors_by_code, max_code)
    lookup = ", ".join(str(int(c)) for rgb in colors for c in rgb)
    lines = ["ENVI", f"description = {{{description}}}", f"samples = {cols}", f"lines = {rows}", "bands = 1", "header offset = 0", "file type = ENVI Classification", "data type = 1", "interleave = bsq", "byte order = 0"]
    if map_info:
        lines.append(f"map info = {{{map_info}}}")
    if coord_sys:
        lines.append(f"coordinate system string = {{{coord_sys}}}")
    lines += [f"classes = {len(names)}", f"class lookup = {{{lookup}}}", f"class names = {{{', '.join(names)}}}", "data ignore value = 0", f"band names = {{{band_name}}}"]
    return "\n".join(lines) + "\n"


def write_envi_classification(base_path, arr, names_by_code, colors_by_code, description, map_info=None, coord_sys=None, max_code=None):
    """Écrit <base>.dat (octets BSQ) et <base>.hdr (ENVI Classification avec noms et couleurs des classes). Retourne (dat, hdr)."""
    arr = np.ascontiguousarray(np.asarray(arr).astype(np.uint8))
    os.makedirs(os.path.dirname(base_path) or ".", exist_ok=True)
    dat, hdr = base_path + ".dat", base_path + ".hdr"
    arr.tofile(dat)
    with open(hdr, "w", encoding="utf-8") as f:
        f.write(envi_header_text(arr.shape[0], arr.shape[1], names_by_code, colors_by_code, description, map_info, coord_sys, max_code))
    return dat, hdr


def qml_style_text(names_by_code, colors_by_code):
    """Style QGIS (.qml) à valeurs uniques : un libellé et une couleur par classe."""
    entries = "\n".join(f'    <paletteEntry value="{k}" label="{_html.escape(names_by_code[k])}" color="#{colors_by_code[k][0]:02x}{colors_by_code[k][1]:02x}{colors_by_code[k][2]:02x}" alpha="255"/>' for k in sorted(names_by_code))
    return ("<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>\n<qgis version=\"3.22.0\" styleCategories=\"AllStyleCategories\">\n <pipe>\n  <rasterrenderer opacity=\"1\" alphaBand=\"-1\" band=\"1\" type=\"paletted\">\n"
            "   <rasterTransparency/>\n   <colorPalette>\n" + entries + "\n   </colorPalette>\n  </rasterrenderer>\n </pipe>\n <blendMode>0</blendMode>\n</qgis>\n")


def change_class_definitions(present_codes=None):
    """Classes de la carte de changement (code = de x 10 + vers) : noms « Built-up → Water », couleur = mélange des deux classes (persistance : couleur de la classe)."""
    names, colors = {}, {}
    for a in CLASSES:
        for b in CLASSES:
            code = a * 10 + b
            if present_codes is not None and code not in present_codes:
                continue
            names[code] = f"{CLASS_NAMES[a]} (stable)" if a == b else f"{CLASS_NAMES[a]} → {CLASS_NAMES[b]}"
            ca, cb = CLASS_COLORS[a], CLASS_COLORS[b]
            colors[code] = ca if a == b else tuple(int((x + y) / 2) for x, y in zip(ca, cb))
    return names, colors


def change_from_to_codes(a, b):
    """Carte de changement : de x 10 + vers sur les pixels classés aux deux dates (0 ailleurs)."""
    a, b = np.asarray(a).astype(np.int32), np.asarray(b).astype(np.int32)
    out = np.zeros(a.shape, np.uint8)
    ok = (a > 0) & (b > 0)
    out[ok] = (a[ok] * 10 + b[ok]).astype(np.uint8)
    return out


def change_type_codes(a, b):
    """Carte « type de changement » : 0 non classé ; 1 stable ; 10 + k = devenu la classe k."""
    a, b = np.asarray(a).astype(np.int32), np.asarray(b).astype(np.int32)
    out = np.zeros(a.shape, np.uint8)
    ok = (a > 0) & (b > 0)
    out[ok & (a == b)] = 1
    ch = ok & (a != b)
    out[ch] = (10 + b[ch]).astype(np.uint8)
    return out


# ============================================================================
# 2. FIGURES (matplotlib ; PNG 300 dpi, SVG / PDF en option)
# ============================================================================
def _save(fig, path, formats=("png",), dpi=300):
    """Enregistre la figure dans chaque format demandé ; retourne la liste des fichiers écrits."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    base = os.path.splitext(path)[0]
    out = []
    for ext in formats:
        p = f"{base}.{ext}"
        fig.savefig(p, dpi=dpi, bbox_inches="tight", facecolor="white")
        out.append(p)
    plt.close(fig)
    return out


def _col(k):
    return tuple(v / 255.0 for v in CLASS_COLORS[k])


def fig_area_stacked(result, path, lang="en", formats=("png",), dpi=300):
    ys = result["years"]
    fig, ax = plt.subplots(figsize=(9, 5.5))
    bottom = np.zeros(len(ys))
    for k in CLASSES:
        vals = np.array([result["areas_px"][y][k] * result["px_ha"] for y in ys])
        ax.bar([str(y) for y in ys], vals, bottom=bottom, color=_col(k), edgecolor="white", linewidth=0.4, label=f"{k} — {CLASS_NAMES[k]}")
        bottom += vals
    ax.set_ylabel(tr(lang, "area_ha"))
    ax.set_title(tr(lang, "fig_area_stacked"))
    ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=8, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: f"{v:,.0f}"))
    return _save(fig, path, formats, dpi)


def fig_area_lines(result, path, lang="en", formats=("png",), dpi=300):
    ys = result["years"]
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for k in CLASSES:
        ax.plot(ys, [result["areas_px"][y][k] * result["px_ha"] for y in ys], marker="o", color=_col(k), label=f"{k} — {CLASS_NAMES[k]}", linewidth=1.8)
    ax.set_xlabel(tr(lang, "year"))
    ax.set_ylabel(tr(lang, "area_ha"))
    ax.set_title(tr(lang, "fig_area_lines"))
    ax.set_xticks(ys)
    ax.grid(alpha=0.3)
    ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=8, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: f"{v:,.0f}"))
    return _save(fig, path, formats, dpi)


def fig_gain_loss(period, path, lang="en", formats=("png",), dpi=300):
    rows = period["classes"]
    fig, ax = plt.subplots(figsize=(9, 5.5))
    x = np.arange(len(rows))
    ax.bar(x, [r["gain_ha"] for r in rows], width=0.6, color="#2e7d32", label=tr(lang, "gain"))
    ax.bar(x, [-r["loss_ha"] for r in rows], width=0.6, color="#c62828", label=tr(lang, "loss"))
    ax.scatter(x, [r["net_ha"] for r in rows], color="black", zorder=3, s=28, label=tr(lang, "net"))
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([r["name"] for r in rows], rotation=35, ha="right", fontsize=9)
    ax.set_ylabel("ha")
    ax.set_title(f"{tr(lang, 'fig_gain_loss')} {period['a']}–{period['b']}")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: f"{v:,.0f}"))
    return _save(fig, path, formats, dpi)


def fig_decomposition(result, path, lang="en", formats=("png",), dpi=300):
    ps = result["periods"]
    labels = [f"{p['a']}–{p['b']}" for p in ps]
    fig, ax = plt.subplots(figsize=(max(7, 1.3 * len(ps) + 3), 5.5))
    x = np.arange(len(ps))
    q = np.array([p["landscape"]["quantity_pct"] for p in ps])
    e = np.array([p["landscape"]["exchange_pct"] for p in ps])
    s = np.array([p["landscape"]["shift_pct"] for p in ps])
    ax.bar(x, q, color="#1565c0", label=tr(lang, "quantity"))
    ax.bar(x, e, bottom=q, color="#ef6c00", label=tr(lang, "exchange"))
    ax.bar(x, s, bottom=q + e, color="#6a1b9a", label=tr(lang, "shift"))
    for i, p in enumerate(ps):
        ax.text(i, q[i] + e[i] + s[i] + 0.05, f"{p['landscape']['changed_pct']:.2f}%", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.set_ylabel(tr(lang, "pct_valid"))
    ax.set_title(tr(lang, "fig_decomp"))
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    return _save(fig, path, formats, dpi)


def fig_heatmap(period, px_ha, path, mode="ha", lang="en", formats=("png",), dpi=300):
    M = np.asarray(period["M"])
    V = M * px_ha if mode == "ha" else row_percent(M)
    fig, ax = plt.subplots(figsize=(9.5, 8))
    show = np.where(M > 0, V, np.nan)
    pos = show[np.isfinite(show) & (show > 0)]
    from matplotlib.colors import LogNorm, Normalize
    norm = LogNorm(vmin=max(pos.min(), 1e-3), vmax=max(pos.max(), 1e-2)) if (mode == "ha" and pos.size) else Normalize(vmin=0, vmax=100)
    im = ax.imshow(show, cmap="YlOrRd", norm=norm)
    names = [CLASS_NAMES[k] for k in CLASSES]
    ax.set_xticks(range(8))
    ax.set_yticks(range(8))
    ax.set_xticklabels(names, rotation=40, ha="right", fontsize=9)
    ax.set_yticklabels(names, fontsize=9)
    ax.set_xlabel(f"{period['b']}")
    ax.set_ylabel(f"{period['a']}")
    ax.set_title(f"{tr(lang, 'fig_heat_ha' if mode == 'ha' else 'fig_heat_pct')} {period['a']}→{period['b']}")
    for i in range(8):
        for j in range(8):
            if M[i, j] > 0:
                v = V[i, j]
                ax.text(j, i, f"{v:,.0f}" if (mode == "ha" and v >= 10) else (f"{v:,.1f}" if mode == "ha" else f"{v:.1f}"), ha="center", va="center", fontsize=7.5, color="black" if (np.isfinite(norm(v)) and norm(v) < 0.65) else "white", fontweight="bold" if i == j else "normal")
    for i in range(8):
        ax.add_patch(Rectangle((i - 0.5, i - 0.5), 1, 1, fill=False, edgecolor="#1565c0", linewidth=1.2))
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03, label="ha" if mode == "ha" else "%")
    return _save(fig, path, formats, dpi)


def fig_sankey(period, px_ha, path, include_persistence=False, min_share=0.002, lang="en", formats=("png",), dpi=300):
    """Diagramme de flux entre deux dates : barres de classes à gauche (date 1) et à droite (date 2), rubans proportionnels aux surfaces ; flux < min_share du total regroupés (gris)."""
    M = np.asarray(period["M"], float)
    flows = M.copy()
    if not include_persistence:
        np.fill_diagonal(flows, 0)
    tot = flows.sum()
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.axis("off")
    if tot <= 0:
        ax.text(0.5, 0.5, "No change" if lang == "en" else "Aucun changement", ha="center", va="center", fontsize=14)
        return _save(fig, path, formats, dpi)
    small = (flows < min_share * tot) & (flows > 0)
    other = flows[small].sum()
    flows_k = np.where(small, 0.0, flows)
    left = flows.sum(axis=1)
    right = flows.sum(axis=0)
    gap = 0.012 * tot
    def stack(sizes):
        pos, y = {}, 0.0
        for i, s in enumerate(sizes):
            if s > 0:
                pos[i] = (y, y + s)
                y += s + gap
        return pos, y
    lp, ltot = stack(left)
    rp, rtot = stack(right)
    H = max(ltot, rtot)
    xl, xr, w = 0.0, 1.0, 0.035
    for i, (y0, y1) in lp.items():
        ax.add_patch(Rectangle((xl - w, y0), w, y1 - y0, color=_col(CLASSES[i]), ec="white", lw=0.5))
        ax.text(xl - w - 0.01, (y0 + y1) / 2, CLASS_NAMES[CLASSES[i]], ha="right", va="center", fontsize=8)
    for j, (y0, y1) in rp.items():
        ax.add_patch(Rectangle((xr, y0), w, y1 - y0, color=_col(CLASSES[j]), ec="white", lw=0.5))
        ax.text(xr + w + 0.01, (y0 + y1) / 2, CLASS_NAMES[CLASSES[j]], ha="left", va="center", fontsize=8)
    cur_l = {i: lp[i][0] for i in lp}
    cur_r = {j: rp[j][0] for j in rp}
    order = sorted(((i, j) for i in range(8) for j in range(8) if flows[i, j] > 0), key=lambda ij: (ij[0], ij[1]))
    for (i, j) in order:
        v = flows[i, j]
        gray = small[i, j]
        y0l, y0r = cur_l[i], cur_r[j]
        cur_l[i] += v
        cur_r[j] += v
        xm = (xl + xr) / 2
        verts = [(xl, y0l), (xm, y0l), (xm, y0r), (xr, y0r), (xr, y0r + v), (xm, y0r + v), (xm, y0l + v), (xl, y0l + v), (xl, y0l)]
        codes = [MplPath.MOVETO, MplPath.CURVE4, MplPath.CURVE4, MplPath.CURVE4, MplPath.LINETO, MplPath.CURVE4, MplPath.CURVE4, MplPath.CURVE4, MplPath.CLOSEPOLY]
        ax.add_patch(PathPatch(MplPath(verts, codes), facecolor=(0.6, 0.6, 0.6, 0.35) if gray else (*_col(CLASSES[i]), 0.55), edgecolor="none"))
    ax.set_xlim(-0.2, 1.2)
    ax.set_ylim(-0.07 * H, 1.06 * H)
    ax.invert_yaxis()                                                      # le haut de la figure = début des empilements
    ax.text(xl - w / 2, -0.015 * H, str(period["a"]), ha="center", va="bottom", fontsize=12, fontweight="bold")
    ax.text(xr + w / 2, -0.015 * H, str(period["b"]), ha="center", va="bottom", fontsize=12, fontweight="bold")
    ax.set_title(f"{tr(lang, 'fig_sankey')} {period['a']}→{period['b']}" + ("" if include_persistence else " (" + ("changes only" if lang == "en" else "changements seulement") + ")"))
    if other > 0:
        ax.text(0.5, 1.04 * H, f"{tr(lang, 'other_flows')} < {100 * min_share:.1f}% : {other * px_ha:,.0f} ha", ha="center", va="bottom", fontsize=8, color="#666666")
    return _save(fig, path, formats, dpi)


def fig_intensity_interval(result, path, lang="en", formats=("png",), dpi=300):
    iv = result["intensity"]["intervals"]
    fig, ax = plt.subplots(figsize=(max(6.5, 1.4 * len(iv) + 3), 5))
    labels = [f"{r['a']}–{r['b']}" for r in iv]
    vals = [r["S"] for r in iv]
    ax.bar(labels, vals, color=["#c62828" if r["label"] == "active" else "#1565c0" for r in iv])
    U = result["intensity"]["U"]
    ax.axhline(U, color="black", linestyle="--", label=f"U = {U:.3f} %/yr")
    for i, v in enumerate(vals):
        ax.text(i, v, f"{v:.3f}", ha="center", va="bottom", fontsize=8)
    ax.set_ylabel(tr(lang, "s_int"))
    ax.set_title(tr(lang, "fig_int_interval"))
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    return _save(fig, path, formats, dpi)


def fig_intensity_category(result, path, lang="en", formats=("png",), dpi=300):
    iv = result["intensity"]["intervals"]
    cat = result["intensity"]["category"]
    n = max(len(iv), 1)
    fig, axes = plt.subplots(1, n, figsize=(5.2 * n, 5), squeeze=False)
    for ax, r in zip(axes[0], iv):
        rows = [c for c in cat if (c["a"], c["b"]) == (r["a"], r["b"])]
        x = np.arange(len(rows))
        g = [0 if math.isnan(c["gain_int"]) else c["gain_int"] for c in rows]
        l = [0 if math.isnan(c["loss_int"]) else c["loss_int"] for c in rows]
        ax.bar(x - 0.2, g, width=0.4, color="#2e7d32", label=tr(lang, "gain_int"))
        ax.bar(x + 0.2, l, width=0.4, color="#c62828", label=tr(lang, "loss_int"))
        ax.axhline(r["S"], color="black", linestyle="--", linewidth=1, label=f"S = {r['S']:.3f}")
        ax.set_xticks(x)
        ax.set_xticklabels([c["name"] for c in rows], rotation=60, ha="right", fontsize=7.5)
        ax.set_title(f"{r['a']}–{r['b']}", fontsize=10)
        ax.set_ylabel("%/yr")
        ax.spines[["top", "right"]].set_visible(False)
    axes[0][0].legend(frameon=False, fontsize=7.5)
    fig.suptitle(tr(lang, "fig_int_category"), y=1.02)
    return _save(fig, path, formats, dpi)


def fig_intensity_transition(result, path, kind="gain", lang="en", formats=("png",), dpi=300, top=8):
    key = "transition_gain" if kind == "gain" else "transition_loss"
    rows = result["intensity"][key]
    fig, ax = plt.subplots(figsize=(9, 6))
    if not rows:
        ax.axis("off")
        ax.text(0.5, 0.5, "No transitions" if lang == "en" else "Aucune transition", ha="center", va="center")
        return _save(fig, path, formats, dpi)
    val = "R" if kind == "gain" else "Q"
    uni = "W" if kind == "gain" else "V"
    rows = sorted(rows, key=lambda r: -(r["ha"]))[:top * 2]
    labels = [f"{r['source_name']} → {r['target_name']}\n{r['a']}–{r['b']}" for r in rows]
    y = np.arange(len(rows))
    ax.barh(y, [r[val] for r in rows], color=["#c62828" if r["label"] == "active" else "#1565c0" for r in rows])
    ax.scatter([r[uni] for r in rows], y, color="black", marker="|", s=200, zorder=3, label=uni)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=7.5)
    ax.invert_yaxis()
    ax.set_xlabel("%/yr")
    ax.set_title(f"{tr(lang, 'fig_int_trans')} ({'gain' if kind == 'gain' else 'loss'})")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    return _save(fig, path, formats, dpi)


def _nice_length_m(width_m):
    """Longueur ronde de barre d'échelle (m) d'environ 20 % de la largeur de la carte."""
    target = width_m * 0.2
    if target <= 0:
        return 0
    mag = 10 ** math.floor(math.log10(target))
    return min((m * mag for m in (1, 2, 5, 10)), key=lambda c: abs(math.log(c / target)))


def _decorate_map(ax, shape, px_m, stride, lang):
    rows, cols = shape
    ax.set_xticks([])
    ax.set_yticks([])
    ax.text(0.03, 0.97, "N\n↑", transform=ax.transAxes, ha="center", va="top", fontsize=11, fontweight="bold", color="black", bbox=dict(facecolor="white", alpha=0.7, edgecolor="none", pad=1.5))
    if px_m:
        width_m = cols * stride * px_m
        L = _nice_length_m(width_m)
        if L > 0:
            frac = L / width_m
            x0, y0 = 0.05, 0.04
            ax.add_patch(Rectangle((x0, y0), frac, 0.012, transform=ax.transAxes, color="black", clip_on=False))
            ax.text(x0 + frac / 2, y0 + 0.02, f"{L / 1000:g} {tr(lang, 'scale')}", transform=ax.transAxes, ha="center", va="bottom", fontsize=8, bbox=dict(facecolor="white", alpha=0.7, edgecolor="none", pad=1))


def downsample(arr, max_px=2500):
    """Sous-échantillonnage au plus proche voisin (les classes restent des classes). Retourne (tableau, pas)."""
    a = np.asarray(arr)
    s = max(1, int(math.ceil(max(a.shape) / float(max_px))))
    return a[::s, ::s], s


def map_png_lulc(arr, year, path, px_m=None, lang="en", max_px=2500, formats=("png",), dpi=300):
    a, s = downsample(arr, max_px)
    cmap = ListedColormap([(0.97, 0.97, 0.97)] + [_col(k) for k in CLASSES])
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.imshow(a, cmap=cmap, vmin=0, vmax=8, interpolation="nearest")
    ax.set_title(f"LULC {year}", fontsize=14)
    _decorate_map(ax, a.shape, px_m, s, lang)
    ax.legend(handles=[Patch(facecolor=_col(k), label=f"{k} — {CLASS_NAMES[k]}") for k in CLASSES], loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False, title=tr(lang, "legend"), fontsize=9)
    return _save(fig, path, formats, dpi)


def map_png_change(a_arr, b_arr, ya, yb, path, px_m=None, lang="en", max_px=2500, formats=("png",), dpi=300):
    """Carte de changement : stable en gris clair, pixel changé coloré selon sa classe à la date 2."""
    codes = change_type_codes(a_arr, b_arr)
    cs, s = downsample(codes, max_px)
    img = np.ones(cs.shape + (3,), float) * 0.97
    img[cs == 1] = (0.85, 0.85, 0.85)
    for k in CLASSES:
        img[cs == 10 + k] = _col(k)
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.imshow(img, interpolation="nearest")
    ax.set_title(f"{ya}→{yb}", fontsize=14)
    _decorate_map(ax, cs.shape, px_m, s, lang)
    handles = [Patch(facecolor=(0.85, 0.85, 0.85), label=tr(lang, "stable"))] + [Patch(facecolor=_col(k), label=("→ " if lang == "en" else "→ ") + CLASS_NAMES[k]) for k in CLASSES]
    ax.legend(handles=handles, loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False, title=tr(lang, "legend"), fontsize=9)
    return _save(fig, path, formats, dpi)


def fig_montage_lulc(maps, years, path, px_m=None, lang="en", max_px=900, formats=("png",), dpi=300):
    n = len(years)
    ncol = min(3, n)
    nrow = int(math.ceil(n / ncol))
    cmap = ListedColormap([(0.97, 0.97, 0.97)] + [_col(k) for k in CLASSES])
    first, _s0 = downsample(maps[str(years[0])], max_px)
    aspect = first.shape[0] / float(max(first.shape[1], 1))
    fig, axes = plt.subplots(nrow, ncol, figsize=(5.2 * ncol, (5.2 * aspect + 0.5) * nrow + 0.9), squeeze=False)
    for ax in axes.ravel():
        ax.axis("off")
    for ax, y in zip(axes.ravel(), years):
        a, s = downsample(maps[str(y)], max_px)
        ax.axis("on")
        ax.imshow(a, cmap=cmap, vmin=0, vmax=8, interpolation="nearest")
        ax.set_title(str(y), fontsize=12)
        ax.set_xticks([])
        ax.set_yticks([])
    fig.legend(handles=[Patch(facecolor=_col(k), label=f"{k} — {CLASS_NAMES[k]}") for k in CLASSES], loc="lower center", ncol=4, frameon=False, fontsize=9)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    return _save(fig, path, formats, dpi)


# ============================================================================
# 3. EXPORTS (CSV, XLSX, HTML, provenance)
# ============================================================================
def write_csv_table(path, rows):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f, delimiter=";").writerows(rows)
    return path


def write_xlsx(path, tables):
    """Classeur Excel (une feuille par tableau, 31 caractères maximum) ; None si openpyxl n'est pas installé."""
    if not XLSX:
        return None
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in tables.items():
        ws = wb.create_sheet(title=re.sub(r"[\\/*?:\[\]]", "_", name)[:31])
        for r in rows:
            vals = []
            for v in r:
                if isinstance(v, str):
                    try:
                        vals.append(float(v) if re.fullmatch(r"-?\d+(\.\d+)?", v) and not re.fullmatch(r"\d{4}[–-]\d{4}", v) else v)
                    except ValueError:
                        vals.append(v)
                else:
                    vals.append(v)
            ws.append(vals)
        for c in ws[1]:
            c.font = Font(bold=True)
            c.fill = PatternFill("solid", fgColor="DDEBF7")
            c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.column_dimensions["A"].width = 30
        ws.freeze_panes = "B2"
    wb.save(path)
    return path


def sha256_file(path, block=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(block), b""):
            h.update(chunk)
    return h.hexdigest()


def provenance(map_paths, params, versions=None):
    """Provenance : empreintes SHA-256 des cartes d'entrée, paramètres, versions des logiciels, horodatage."""
    v = {"python": platform.python_version(), "numpy": np.__version__, "script": VERSION}
    if versions:
        v.update(versions)
    return {"generated": time.strftime("%Y-%m-%d %H:%M:%S"), "versions": v, "parameters": params, "inputs": {y: {"path": p, "sha256": sha256_file(p) if os.path.exists(p) else None, "bytes": os.path.getsize(p) if os.path.exists(p) else None} for y, p in map_paths.items()}}


def _html_table(rows, caption=""):
    e = _html.escape
    out = [f"<table><caption>{e(caption)}</caption>" if caption else "<table>"]
    for i, r in enumerate(rows):
        tag = "th" if i == 0 else "td"
        out.append("<tr>" + "".join(f"<{tag}{'' if (i == 0 or c == 0) else ' class=n'}>{e(str(v))}</{tag}>" for c, v in enumerate(r)) + "</tr>")
    out.append("</table>")
    return "".join(out)


def _img_tag(path, embed=True, rel_to=None, alt=""):
    if not path or not os.path.exists(path):
        return ""
    if embed:
        with open(path, "rb") as f:
            return f"<img alt='{_html.escape(alt)}' src='data:image/png;base64,{base64.b64encode(f.read()).decode()}'>"
    return f"<img alt='{_html.escape(alt)}' src='{_html.escape(os.path.relpath(path, rel_to) if rel_to else path)}'>"


def build_report_html(result, tables, figures, params, lang="en", embed=True, rel_to=None, generated=None):
    """Rapport HTML autonome : surfaces, chaque période (matrices, statistiques, figures, carte), décomposition, analyse d'intensité, contrôles, méthodes, références. figures = {clé: chemin PNG}."""
    e = _html.escape
    css = ("body{font-family:Segoe UI,Arial,sans-serif;margin:24px auto;max-width:1250px;color:#222;padding:0 16px}h1{font-size:24px}h2{font-size:19px;margin-top:34px;border-bottom:2px solid #ddd;padding-bottom:5px}h3{font-size:15px;margin-top:22px}"
           "table{border-collapse:collapse;margin:8px 0;font-size:12.5px}caption{text-align:left;font-weight:600;padding:4px 0}th,td{border:1px solid #ccc;padding:3px 8px;text-align:left}th{background:#eef3f8}td.n{text-align:right}"
           "img{max-width:100%;height:auto;margin:8px 0;border:1px solid #eee}.small{color:#666;font-size:12px}.scroll{overflow-x:auto}code{background:#f4f4f4;padding:1px 4px}")
    ys = result["years"]
    out = [f"<!DOCTYPE html><html lang='{lang}'><head><meta charset='utf-8'><title>LULC transition analysis</title><style>{css}</style></head><body>",
           f"<h1>Land-cover transition analysis {ys[0]}–{ys[-1]}</h1>" if lang == "en" else f"<h1>Analyse des transitions d'occupation du sol {ys[0]}–{ys[-1]}</h1>",
           f"<p class='small'>{e(generated or time.strftime('%Y-%m-%d %H:%M'))} · {e(VERSION)} · years: {e(', '.join(str(y) for y in ys))} · pixel {result['px_ha']:.4f} ha · domain {result['domain_px']:,} px</p>"]
    out.append("<h2>1. Class areas</h2><div class='scroll'>" + _html_table(tables["01_Class_areas"]) + "</div>")
    for key in ("area_stacked", "area_lines", "montage"):
        if key in figures:
            out.append(_img_tag(figures[key], embed, rel_to, key))
    if "04_Climate_context" in tables:
        ex = params.get("Years excluded", "")
        out.append("<h2>1b. Climate context of the mapped years</h2><p class='small'>z-score = (season rainfall − 1991–2020 mean) / standard deviation; the drought flag is z ≤ the chosen threshold on the growing season. "
                   "The vegetation state of a drought year (failed crops, sparse rangeland) can be classified as Fallow or Bareland: transitions to and from such a year reflect climate-driven vegetation state rather than a change of land use.</p>"
                   + (f"<p><b>Years excluded from this analysis: {e(str(ex))}.</b></p>" if ex else "") + "<div class='scroll'>" + _html_table(tables["04_Climate_context"]) + "</div>")
    if "05_Date_selection" in tables:
        out.append(f"<h2>1c. {tr(lang, 'dates_title')}</h2><p class='small'>{e(DATE_CRITERIA.get(lang, DATE_CRITERIA['en']))}</p><div class='scroll'>" + _html_table(tables["05_Date_selection"]) + "</div>")
    out.append("<h2>2. Annual change rates</h2><div class='scroll'>" + _html_table(tables["02_Change_rates"]) + "</div>")
    out.append("<h2>3. Components of landscape change</h2><div class='scroll'>" + _html_table(tables["03_Landscape_components"]) + "</div>")
    if "decomposition" in figures:
        out.append(_img_tag(figures["decomposition"], embed, rel_to, "decomposition"))
    n = 4
    for p in result["periods"]:
        tag = f"{p['a']}_{p['b']}"
        kind = "first → last year" if p["kind"] == "first_last" else "consecutive years"
        out.append(f"<h2>{n}. Transition {p['a']} → {p['b']} ({kind}, {p['delta']} yr)</h2>")
        n += 1
        i = p["info"]
        out.append(f"<p class='small'>Domain {i['domain_px']:,} px · classified at both dates {i['valid_px']:,} px · unclassified in {p['a']}: {i['unclassified_a']:,} · unclassified in {p['b']}: {i['unclassified_b']:,}</p>")
        for nm, cap in ((f"M_ha_{tag}", "Transition matrix (ha)"), (f"M_rowpct_{tag}", "Row % (destination of each class)"), (f"M_colpct_{tag}", "Column % (origin of each class)"), (f"M_px_{tag}", "Transition matrix (pixels)"), (f"Classes_{tag}", "Gain, loss, net change, swap, persistence by class")):
            out.append("<div class='scroll'>" + _html_table(tables[nm], cap) + "</div>")
        for key in (f"heat_ha_{tag}", f"heat_pct_{tag}", f"gainloss_{tag}", f"sankey_{tag}", f"sankey_all_{tag}", f"map_{tag}"):
            if key in figures:
                out.append(_img_tag(figures[key], embed, rel_to, key))
    out.append(f"<h2>{n}. Intensity analysis</h2>")
    n += 1
    out.append("<h3>Interval level</h3><div class='scroll'>" + _html_table(tables["Intensity_interval"]) + "</div>")
    if "int_interval" in figures:
        out.append(_img_tag(figures["int_interval"], embed, rel_to, "int_interval"))
    out.append("<h3>Category level</h3><div class='scroll'>" + _html_table(tables["Intensity_category"]) + "</div>")
    if "int_category" in figures:
        out.append(_img_tag(figures["int_category"], embed, rel_to, "int_category"))
    out.append("<h3>Transition level — gain</h3><div class='scroll'>" + _html_table(tables["Intensity_trans_gain"]) + "</div>")
    out.append("<h3>Transition level — loss</h3><div class='scroll'>" + _html_table(tables["Intensity_trans_loss"]) + "</div>")
    for key in ("int_trans_gain", "int_trans_loss"):
        if key in figures:
            out.append(_img_tag(figures[key], embed, rel_to, key))
    out.append(f"<h2>{n}. Consistency checks</h2><div class='scroll'>" + _html_table(tables["Checks"]) + "</div>")
    n += 1
    out.append(f"<h2>{n}. Methods and limitations</h2><ul>"
               "<li>Areas are map areas (pixel counts), not accuracy-adjusted estimates (Olofsson et al. 2014).</li>"
               "<li>Only pixels classified at both dates enter a matrix.</li><li>Formulas and definitions: Methods_and_Definitions.md.</li></ul><h3>References</h3><ul>" + "".join(f"<li>{e(r)}</li>" for r in REFERENCES) + "</ul>")
    out.append("<h2>Parameters</h2><table>" + "".join(f"<tr><th>{e(str(k))}</th><td>{e(str(v))}</td></tr>" for k, v in params.items()) + "</table></body></html>")
    return "".join(out)


# ============================================================================
# 4. COUCHE GDAL / QGIS (relue, non exécutable hors QGIS)
# ============================================================================
def read_map(path):
    ds = gdal.Open(path, gdal.GA_ReadOnly)
    if ds is None:
        raise RuntimeError(f"Carte illisible : {path}")
    return normalize_lulc(ds.GetRasterBand(1).ReadAsArray()), ds.GetGeoTransform(), ds.GetProjection()


def admin_mask_from_shp(shp_path, rows, cols, gt, wkt):
    ds = ogr.Open(shp_path)
    if ds is None:
        raise RuntimeError(f"Zone d'étude illisible : {shp_path}")
    mem = gdal.GetDriverByName("MEM").Create("", cols, rows, 1, gdal.GDT_Byte)
    mem.SetGeoTransform(gt)
    mem.SetProjection(wkt)
    gdal.RasterizeLayer(mem, [1], ds.GetLayer(), burn_values=[1])
    return mem.GetRasterBand(1).ReadAsArray() == 1


def write_geotiff_classified(path, arr, gt, wkt, names_by_code, colors_by_code, max_code=None):
    """
    GeoTIFF à PALETTE avec NOMS de catégories (affichés par QGIS / ENVI / ArcGIS).
    ORDRE IMPORTANT : la palette (qui fixe PhotometricInterpretation) et les noms de catégories sont définis AVANT d'écrire les pixels ; après l'écriture, le pilote GTiff refuse
    (« Cannot modify tag PhotometricInterpretation while writing »). Si la palette est refusée malgré tout, la carte est écrite sans palette (le fichier .qml donne les noms et les couleurs).
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    names, cols = class_tables(names_by_code, colors_by_code, max_code)
    ds = gdal.GetDriverByName("GTiff").Create(path, arr.shape[1], arr.shape[0], 1, gdal.GDT_Byte, ["COMPRESS=LZW", "TILED=YES"])
    ds.SetGeoTransform(gt)
    ds.SetProjection(wkt)
    band = ds.GetRasterBand(1)
    band.SetNoDataValue(0)
    try:
        band.SetColorInterpretation(gdal.GCI_PaletteIndex)
        ct = gdal.ColorTable()
        for code, rgb in enumerate(cols):
            ct.SetColorEntry(code, (int(rgb[0]), int(rgb[1]), int(rgb[2]), 255 if code else 0))
        band.SetRasterColorTable(ct)
        band.SetCategoryNames(names)
    except Exception as exc:
        print(f"[Avertissement] palette non écrite dans {os.path.basename(path)} ({exc}) : les noms et couleurs sont dans le fichier .qml et dans l'export ENVI Classification.")
    band.WriteArray(np.asarray(arr).astype(np.uint8))
    band.FlushCache()
    ds = None
    return path


def envi_map_info(gt, wkt):
    """Chaîne « map info » ENVI (UTM si le CRS l'est, sinon Arbitrary) et chaîne « coordinate system string »."""
    srs = osr.SpatialReference()
    try:
        srs.ImportFromWkt(wkt)
    except Exception:
        return None, None
    ulx, xres, uly, yres = gt[0], gt[1], gt[3], abs(gt[5])
    zone = None
    try:
        z = srs.GetUTMZone()
        zone = int(z) if z else None
    except Exception:
        zone = None
    if zone:
        datum = (srs.GetAttrValue("DATUM") or "WGS-84").replace("WGS_1984", "WGS-84").replace("_", " ")
        info = f"UTM, 1.000, 1.000, {ulx:.6f}, {uly:.6f}, {xres:.8f}, {yres:.8f}, {abs(zone)}, {'South' if zone < 0 else 'North'}, {datum}, units=Meters"
    else:
        info = f"Arbitrary, 1.000, 1.000, {ulx:.6f}, {uly:.6f}, {xres:.8f}, {yres:.8f}"
    return info, wkt.replace("\n", "").replace("\r", "")


def _stop(msg="Opération annulée : aucun fichier n'a été produit."):
    """Sortie ANNONCÉE (console + boîte de message) : un script qui s'arrête ne doit jamais le faire en silence."""
    print("[Arrêt] " + msg)
    try:
        from qgis.PyQt.QtWidgets import QMessageBox
        QMessageBox.information(None, "Arrêt du script", msg)
    except Exception:
        pass


def main():
    """Lance _main() ; une erreur n'est jamais avalée : trace complète dans la console ET boîte de message."""
    try:
        _main()
    except Exception:
        import traceback
        tb = traceback.format_exc()
        print(tb)
        try:
            from qgis.PyQt.QtWidgets import QMessageBox
            QMessageBox.critical(None, "Erreur", "Le traitement s'est arrêté sur une erreur (trace complète dans la console Python) :\n\n" + tb[-1500:])
        except Exception:
            pass


def run_export(cfg, log=print):
    """
    Calcule et exporte TOUT. cfg : maps {année: chemin}, out, study, lang, formats (tuple), embed, dpi, max_px, envi, geotiff, xlsx, include_first_last.
    Retourne {"report", "out", "n_files"}.
    """
    global AREA_TAG
    for _p in cfg["maps"].values():
        _m = re.match(r"^LULC_(.+)_(?:19|20)\d{2}\.tif$", os.path.basename(_p))
        if _m:
            AREA_TAG = _m.group(1)
            break
    out = cfg["out"]
    lang, fmts, dpi = cfg.get("lang", "en"), tuple(cfg.get("formats", ("png",))), int(cfg.get("dpi", 300))
    dirs = {k: os.path.join(out, v) for k, v in {"report": "00_Report", "csv": "01_Tables_CSV", "fig": "02_Figures", "map": "03_Maps_PNG", "envi": "04_ENVI_Classification", "tif": "05_GeoTIFF_Classified"}.items()}
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)
    all_years = list(cfg["maps"])
    years = select_years(all_years, cfg.get("years"))                      # années de l'analyse principale (les autres sont documentées comme exclues)
    excluded = [y for y in all_years if y not in years]
    maps, gt, wkt, shape = {}, None, None, None
    for y in years:
        arr, g, w = read_map(cfg["maps"][y])
        if gt is None:
            gt, wkt, shape = g, w, arr.shape
        elif arr.shape != shape:
            raise RuntimeError(f"La carte {y} n'a pas la même taille que {years[0]} ({arr.shape} contre {shape}).")
        maps[y] = arr
    px_ha = abs(gt[1] * gt[5] - gt[2] * gt[4]) / 10000.0
    px_m = abs(gt[1]) if "PROJCS" in (wkt or "") else None
    domain = admin_mask_from_shp(cfg["study"], shape[0], shape[1], gt, wkt) if cfg.get("study") else None
    log(f"[1/6] Calcul des matrices et des statistiques ({len(years)} années)…")
    result = analyze(maps, years, px_ha, domain, cfg.get("include_first_last", True))
    climate = None
    if cfg.get("chirps"):
        prod, pinfo = parse_productivity_csv(cfg["prod"], True) if cfg.get("prod") else (None, None)
        prod2, pinfo2 = parse_productivity_csv(cfg["prod2"], True) if cfg.get("prod2") else (None, None)
        climate = climate_context(parse_chirps_csv(cfg["chirps"]), all_years, productivity=prod, productivity2=prod2, z_flag=float(cfg.get("z_flag", -1.0)))
        for _nm, _inf in ((PRODUCTIVITY_LABELS[0], pinfo), (PRODUCTIVITY_LABELS[1], pinfo2)):
            if _inf and _inf["excluded"]:
                log(f"[1/6] Productivité {_nm} : années non classées (couverture < {MIN_PROD_COVERAGE_PCT:.0f} % des pixels) : {', '.join(map(str, _inf['excluded']))}")
        log("[1/6] Contexte climatique : " + (", ".join(f"{r['year']} (z = {r['season_z']:+.2f}" + (", déficit de pluie seul" if r.get("confirmed") is False else "") + ")" for r in climate if r["drought"]) or "aucune année de sécheresse détectée") + ".")
    tables = build_all_tables(result, lang, climate, all_years, excluded)
    n_files = 0
    for name, rows in tables.items():
        write_csv_table(os.path.join(dirs["csv"], f"{name}.csv"), rows)
        n_files += 1
    xlsx = write_xlsx(os.path.join(dirs["csv"], "Supplementary_Tables.xlsx"), tables) if cfg.get("xlsx", True) else None
    figures = {}
    if MPL:
        log("[2/6] Figures…")
        figures["area_stacked"] = fig_area_stacked(result, os.path.join(dirs["fig"], "Fig01_Area_stacked"), lang, fmts, dpi)[0]
        figures["area_lines"] = fig_area_lines(result, os.path.join(dirs["fig"], "Fig02_Area_trajectories"), lang, fmts, dpi)[0]
        figures["decomposition"] = fig_decomposition(result, os.path.join(dirs["fig"], "Fig03_Change_components"), lang, fmts, dpi)[0]
        for p in result["periods"]:
            tag = f"{p['a']}_{p['b']}"
            figures[f"heat_ha_{tag}"] = fig_heatmap(p, px_ha, os.path.join(dirs["fig"], f"Fig_Matrix_ha_{tag}"), "ha", lang, fmts, dpi)[0]
            figures[f"heat_pct_{tag}"] = fig_heatmap(p, px_ha, os.path.join(dirs["fig"], f"Fig_Matrix_rowpct_{tag}"), "pct", lang, fmts, dpi)[0]
            figures[f"gainloss_{tag}"] = fig_gain_loss(p, os.path.join(dirs["fig"], f"Fig_GainLoss_{tag}"), lang, fmts, dpi)[0]
            figures[f"sankey_{tag}"] = fig_sankey(p, px_ha, os.path.join(dirs["fig"], f"Fig_Flows_{tag}"), False, 0.002, lang, fmts, dpi)[0]
            if p["kind"] == "first_last":                                  # première -> dernière année : aussi avec la persistance (vue d'ensemble du paysage)
                figures[f"sankey_all_{tag}"] = fig_sankey(p, px_ha, os.path.join(dirs["fig"], f"Fig_Flows_with_persistence_{tag}"), True, 0.002, lang, fmts, dpi)[0]
        if result["intensity"]["intervals"]:
            figures["int_interval"] = fig_intensity_interval(result, os.path.join(dirs["fig"], "Fig_Intensity_interval"), lang, fmts, dpi)[0]
            figures["int_category"] = fig_intensity_category(result, os.path.join(dirs["fig"], "Fig_Intensity_category"), lang, fmts, dpi)[0]
            figures["int_trans_gain"] = fig_intensity_transition(result, os.path.join(dirs["fig"], "Fig_Intensity_transition_gain"), "gain", lang, fmts, dpi)[0]
            figures["int_trans_loss"] = fig_intensity_transition(result, os.path.join(dirs["fig"], "Fig_Intensity_transition_loss"), "loss", lang, fmts, dpi)[0]
        log("[3/6] Cartes PNG…")
        max_px = int(cfg.get("max_px", 2500))
        for y in years:
            map_png_lulc(maps[y], y, os.path.join(dirs["map"], f"LULC_{y}"), px_m, lang, max_px, fmts, dpi)
        figures["montage"] = fig_montage_lulc(maps, years, os.path.join(dirs["map"], "LULC_all_years_montage"), px_m, lang, 900, fmts, dpi)[0]
        for p in result["periods"]:
            tag = f"{p['a']}_{p['b']}"
            figures[f"map_{tag}"] = map_png_change(maps[str(p["a"])], maps[str(p["b"])], p["a"], p["b"], os.path.join(dirs["map"], f"Change_{tag}"), px_m, lang, max_px, fmts, dpi)[0]
    else:
        log("[2/6] matplotlib indisponible : figures et cartes PNG ignorées.")
    names, colors = CLASS_NAMES, CLASS_COLORS
    if cfg.get("envi", True):
        log("[4/6] Export ENVI Classification…")
        map_info, coord = envi_map_info(gt, wkt)
        for y in years:
            write_envi_classification(os.path.join(dirs["envi"], f"LULC_{AREA_TAG}_{y}"), maps[y], names, colors, f"LULC {AREA_TAG} {y} — classification", map_info, coord, 8)
        cn, cc = change_class_definitions()
        for p in result["periods"]:
            code = change_from_to_codes(maps[str(p["a"])], maps[str(p["b"])])
            write_envi_classification(os.path.join(dirs["envi"], f"Change_FromTo_{p['a']}_{p['b']}"), code, cn, cc, f"Change {p['a']}→{p['b']} — from x 10 + to", map_info, coord, 88)
        n_files += 2 * len(years)
    if cfg.get("geotiff", True):
        log("[5/6] Export GeoTIFF classés…")
        for y in years:
            write_geotiff_classified(os.path.join(dirs["tif"], f"LULC_{AREA_TAG}_{y}.tif"), maps[y], gt, wkt, names, colors, 8)
            with open(os.path.join(dirs["tif"], f"LULC_{AREA_TAG}_{y}.qml"), "w", encoding="utf-8") as f:
                f.write(qml_style_text(names, colors))
        cn, cc = change_class_definitions()
        for p in result["periods"]:
            code = change_from_to_codes(maps[str(p["a"])], maps[str(p["b"])])
            write_geotiff_classified(os.path.join(dirs["tif"], f"Change_FromTo_{p['a']}_{p['b']}.tif"), code, gt, wkt, cn, cc, 88)
            with open(os.path.join(dirs["tif"], f"Change_FromTo_{p['a']}_{p['b']}.qml"), "w", encoding="utf-8") as f:
                f.write(qml_style_text(cn, cc))
    log("[6/6] Rapport HTML, méthodes, provenance…")
    params = {"Maps folder": os.path.dirname(next(iter(cfg["maps"].values()))), "Study area": cfg.get("study") or "(whole grid)", "Language": lang, "Figure formats": ",".join(fmts), "DPI": dpi, "First-last period": bool(cfg.get("include_first_last", True)),
              "Years analysed": ", ".join(years), "Years excluded": ", ".join(excluded) or "none", "Rainfall file": cfg.get("chirps") or "(not provided)", "Productivity file": cfg.get("prod") or "(not provided)", "Productivity file 2": cfg.get("prod2") or "(not provided)"}
    html = build_report_html(result, tables, figures, params, lang, embed=bool(cfg.get("embed", True)), rel_to=dirs["report"])
    rep = os.path.join(dirs["report"], "Transition_Report.html")
    with open(rep, "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(dirs["report"], "Methods_and_Definitions.md"), "w", encoding="utf-8") as f:
        f.write(methods_markdown(result, params, lang))
    ver = {"gdal": getattr(gdal, "__version__", ""), "matplotlib": matplotlib.__version__ if MPL else "n/a"}
    with open(os.path.join(dirs["report"], "Provenance.json"), "w", encoding="utf-8") as f:
        json.dump(provenance({y: cfg["maps"][y] for y in years}, params, ver), f, indent=2, ensure_ascii=False, default=str)
    return {"report": rep, "out": out, "n_files": n_files, "xlsx": xlsx, "figures": len(figures), "years": years, "excluded": excluded, "drought": [r["year"] for r in (climate or []) if r["drought"] and r.get("confirmed") is not False], "checks_ok": all(c["ok"] for c in consistency_checks(result))}


def build_setup_dialog():
    from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog, QCheckBox, QComboBox, QSpinBox, QDoubleSpinBox, QGroupBox)

    class Setup(QDialog):
        def __init__(self):
            super().__init__(None)
            self.setWindowTitle("Matrices de transition LULC — rapport pour la revue par les pairs")
            self.resize(860, 760)
            lay = QVBoxLayout(self)
            lay.addWidget(QLabel("<b>Matrices de transition, statistiques, figures et cartes</b> pour chaque paire d'années consécutives et pour la période première → dernière année ; export ENVI Classification."))
            self.le_in, self.le_out, self.le_study, self.le_chirps, self.le_prod, self.le_prod2 = QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit()
            for label, le, kind in (("1. Dossier des cartes LULC (LULC_<ZONE>_<année>.tif ou sous-dossier LULC/)", self.le_in, "dir"), ("2. Dossier de SORTIE", self.le_out, "dir"), ("3. Zone d'étude (shp) — facultatif", self.le_study, "shp"),
                                    ("4. Pluie journalière CHIRPS (CSV ClimateEngine) — facultatif : contexte climatique et détection des années de sécheresse", self.le_chirps, "csv"),
                                    ("5. Indice de productivité par année (Productivity_Index_By_Year.csv, produit par l'étape 01B) — facultatif : distingue une sécheresse confirmée par la végétation d'un simple déficit de pluie", self.le_prod, "csv"),
                                    ("5b. Série de productivité SECONDAIRE (ex. Landsat, export Year / Mean_Productivity / Valid_Pixels_Count) — facultatif : seulement pour les années absentes de la série principale (ex. 1999 si la principale est MODIS) ; les rangs des deux séries ne sont jamais fusionnés", self.le_prod2, "csv")):
                box = QGroupBox(label)
                h = QHBoxLayout(box)
                h.addWidget(le, 1)
                b = QPushButton("Parcourir…")
                b.clicked.connect(lambda _c=False, le_=le, k=kind: self.browse(le_, k))
                h.addWidget(b)
                lay.addWidget(box)
            self.le_chirps.editingFinished.connect(self.refresh_climate)
            self.le_in.editingFinished.connect(self.refresh_years)
            gy = QGroupBox("6. Années de l'analyse PRINCIPALE (décochez une année de sécheresse : elle n'entre pas dans les matrices, mais reste documentée)")
            vy = QVBoxLayout(gy)
            self.years_box = QHBoxLayout()
            vy.addLayout(self.years_box)
            self.year_checks = {}
            self.flagged = []
            self.lbl_years = QLabel("")
            self.lbl_years.setWordWrap(True)
            vy.addWidget(self.lbl_years)
            self.lbl_climate = QLabel("")
            self.lbl_climate.setWordWrap(True)
            vy.addWidget(self.lbl_climate)
            rowz = QHBoxLayout()
            rowz.addWidget(QLabel("Seuil de sécheresse (écart réduit de la saison oct–mars) :"))
            self.sp_z = QDoubleSpinBox()
            self.sp_z.setRange(-5.0, 0.0)
            self.sp_z.setSingleStep(0.1)
            self.sp_z.setValue(-1.0)
            self.sp_z.editingFinished.connect(self.refresh_climate)
            rowz.addWidget(self.sp_z)
            self.btn_excl = QPushButton("Exclure les années de sécheresse détectées")
            self.btn_excl.clicked.connect(self.on_exclude_drought)
            rowz.addWidget(self.btn_excl)
            vy.addLayout(rowz)
            lay.addWidget(gy)
            opt = QGroupBox("7. Options")
            ov = QVBoxLayout(opt)
            self.chk_sens = QCheckBox("Produire AUSSI l'analyse de sensibilité avec TOUTES les années (dossiers Analyse_principale et Sensibilite_Toutes_Annees)")
            self.chk_sens.setChecked(True)
            self.chk_fl = QCheckBox("Inclure la période première → dernière année")
            self.chk_fl.setChecked(True)
            self.chk_envi = QCheckBox("Exporter les cartes en ENVI Classification (.dat + .hdr avec noms et couleurs des classes)")
            self.chk_envi.setChecked(True)
            self.chk_tif = QCheckBox("Exporter aussi des GeoTIFF classés (palette + noms) avec style QGIS (.qml)")
            self.chk_tif.setChecked(True)
            self.chk_xlsx = QCheckBox("Classeur Excel de tableaux supplémentaires")
            self.chk_xlsx.setChecked(True)
            self.chk_vec = QCheckBox("Figures aussi en SVG et PDF (vectoriel, pour les revues)")
            self.chk_embed = QCheckBox("Rapport HTML autonome (images incluses)")
            self.chk_embed.setChecked(True)
            row = QHBoxLayout()
            row.addWidget(QLabel("Langue des tableaux et figures :"))
            self.cb_lang = QComboBox()
            self.cb_lang.addItems(["English (publication)", "Français"])
            row.addWidget(self.cb_lang)
            row.addWidget(QLabel("Résolution (dpi) :"))
            self.sp_dpi = QSpinBox()
            self.sp_dpi.setRange(100, 600)
            self.sp_dpi.setValue(300)
            row.addWidget(self.sp_dpi)
            row.addWidget(QLabel("Taille max. des cartes PNG (px) :"))
            self.sp_px = QSpinBox()
            self.sp_px.setRange(500, 8000)
            self.sp_px.setValue(2500)
            row.addWidget(self.sp_px)
            for w in (self.chk_sens, self.chk_fl, self.chk_envi, self.chk_tif, self.chk_xlsx, self.chk_vec, self.chk_embed):
                ov.addWidget(w)
            ov.addLayout(row)
            lay.addWidget(opt)
            self.lbl_err = QLabel("")
            self.lbl_err.setWordWrap(True)
            lay.addWidget(self.lbl_err)
            btns = QHBoxLayout()
            go, cancel = QPushButton("▶ Calculer et exporter"), QPushButton("Annuler")
            go.clicked.connect(self.on_go)
            cancel.clicked.connect(self.reject)
            btns.addStretch(1)
            btns.addWidget(go)
            btns.addWidget(cancel)
            lay.addLayout(btns)
            self.settings = None

        def browse(self, le, kind):
            if kind == "dir":
                p = QFileDialog.getExistingDirectory(self, "Dossier", le.text() or "")
            else:
                p, _ = QFileDialog.getOpenFileName(self, "Fichier", le.text() or "", "Shapefile (*.shp)" if kind == "shp" else "CSV (*.csv);;Tous (*)")
            if p:
                le.setText(p)
                if le is self.le_in:
                    self.refresh_years()
                    if not self.le_out.text().strip():
                        self.le_out.setText(os.path.join(p, "Rapport_Transitions"))
                elif le is self.le_chirps:
                    self.refresh_climate()

        def refresh_years(self):
            """Une case par carte trouvée (état conservé) puis le contexte climatique."""
            maps = find_lulc_maps(self.le_in.text().strip()) if self.le_in.text().strip() else {}
            old = {y: cb.isChecked() for y, cb in self.year_checks.items()}
            for cb in self.year_checks.values():
                self.years_box.removeWidget(cb)
                cb.setParent(None)
                cb.deleteLater()
            self.year_checks = {}
            for y in maps:
                cb = QCheckBox(y)
                cb.setChecked(old.get(y, y not in [str(d) for d in DIAGNOSTIC_YEARS]))      # une année diagnostique (sécheresse) n'entre pas dans l'analyse principale par défaut
                self.years_box.addWidget(cb)
                self.year_checks[y] = cb
            self.lbl_years.setText(("Cartes trouvées : " + ", ".join(maps) + f" ({len(maps)})") if maps else "Aucune carte LULC_<ZONE>_<année>.tif trouvée dans ce dossier.")
            self.refresh_climate()

        def refresh_climate(self):
            """Années de sécheresse détectées avec le CSV de pluie (fenêtre oct–mars) ; les deux saisons sont montrées car le verdict dépend de la fenêtre."""
            self.flagged = []
            path = self.le_chirps.text().strip()
            if not path or not self.year_checks:
                self.lbl_climate.setText("")
                return
            try:
                prod = parse_productivity_csv(self.le_prod.text().strip()) if self.le_prod.text().strip() else None
                le2 = getattr(self, "le_prod2", None)
                prod2 = parse_productivity_csv(le2.text().strip()) if (le2 is not None and le2.text().strip()) else None
                rows = climate_context(parse_chirps_csv(path), [int(y) for y in self.year_checks], productivity=prod, productivity2=prod2, z_flag=float(self.sp_z.value()))
            except (ValueError, OSError) as exc:
                self.lbl_climate.setText(f"<span style='color:#c62828'>Contexte climatique impossible : {exc}</span>")
                return
            self.flagged = [str(r["year"]) for r in rows if r["drought"] and r.get("confirmed") is not False]      # avec l'indice de productivité : seulement les sécheresses CONFIRMÉES par la végétation
            lines = []
            for r in rows:
                tag = "ok" if not r["drought"] else ("⚠ déficit de pluie seul (végétation normale : année conservée)" if r.get("confirmed") is False else "⚠ SÉCHERESSE")
                lines.append(f"{tag} {r['year']} : oct–mars {r['season_mm']:.0f} mm (z = {r['season_z']:+.2f}) · jan–fév {r['jan_feb_pct']:.0f} % de la normale · sept–mai z = {r['long_z']:+.2f}" + (f" · productivité {PRODUCTIVITY_LABELS[0] if r.get('prod_labels') else ''} rang {r['prod_rank']}/{r['n_prod']}".replace("  ", " ") if r["prod_rank"] else "") + (f" · productivité {PRODUCTIVITY_LABELS[1]} rang {r['prod2_rank']}/{r['n_prod2']}" if r.get("prod2_rank") else ""))
            self.lbl_climate.setText("<br>".join(lines))

        def on_exclude_drought(self):
            for y in self.flagged:
                if y in self.year_checks:
                    self.year_checks[y].setChecked(False)

        def on_go(self):
            maps = find_lulc_maps(self.le_in.text().strip())
            errs = []
            if len(maps) < 2:
                errs.append("Il faut au moins DEUX cartes LULC (années différentes) dans le dossier choisi.")
            if not self.le_out.text().strip():
                errs.append("Choisissez le dossier de sortie.")
            elif os.path.normpath(self.le_out.text().strip()) == os.path.normpath(self.le_in.text().strip()):
                errs.append("Le dossier de sortie doit être DIFFÉRENT du dossier des cartes.")
            if self.le_study.text().strip() and not os.path.exists(self.le_study.text().strip()):
                errs.append("La zone d'étude indiquée n'existe pas.")
            for le, nm in ((self.le_chirps, "pluie CHIRPS"), (self.le_prod, "productivité"), (getattr(self, "le_prod2", None) or self.le_prod, "productivité (série secondaire)")):
                if le.text().strip() and not os.path.exists(le.text().strip()):
                    errs.append(f"Le fichier {nm} indiqué n'existe pas.")
            chosen = [y for y, cb in self.year_checks.items() if cb.isChecked()] if self.year_checks else list(maps)
            try:
                years = select_years(list(maps), chosen)
            except ValueError as exc:
                errs.append(str(exc))
                years = []
            if self.le_chirps.text().strip() and os.path.exists(self.le_chirps.text().strip()):
                try:
                    parse_chirps_csv(self.le_chirps.text().strip())
                    if self.le_prod.text().strip() and os.path.exists(self.le_prod.text().strip()):
                        parse_productivity_csv(self.le_prod.text().strip())
                    _l2 = getattr(self, "le_prod2", None)
                    if _l2 is not None and _l2.text().strip() and os.path.exists(_l2.text().strip()):
                        parse_productivity_csv(_l2.text().strip())
                except (ValueError, OSError) as exc:
                    errs.append(str(exc))
            if errs:
                self.lbl_err.setText("<span style='color:#c62828'>" + "<br>".join("• " + x for x in errs) + "</span>")
                return
            self.settings = {"maps": maps, "years": years, "out": self.le_out.text().strip(), "study": self.le_study.text().strip(), "chirps": self.le_chirps.text().strip(), "prod": self.le_prod.text().strip(), "prod2": (getattr(self, "le_prod2", None).text().strip() if getattr(self, "le_prod2", None) is not None else ""), "z_flag": float(self.sp_z.value()),
                             "sensitivity": bool(self.chk_sens.isChecked() and set(years) != set(maps)), "include_first_last": self.chk_fl.isChecked(), "envi": self.chk_envi.isChecked(), "geotiff": self.chk_tif.isChecked(),
                             "xlsx": self.chk_xlsx.isChecked(), "formats": ("png", "svg", "pdf") if self.chk_vec.isChecked() else ("png",), "embed": self.chk_embed.isChecked(),
                             "lang": "en" if self.cb_lang.currentIndex() == 0 else "fr", "dpi": int(self.sp_dpi.value()), "max_px": int(self.sp_px.value())}
            self.accept()

    return Setup


def _main():
    from qgis.PyQt.QtWidgets import QMessageBox
    from qgis.PyQt.QtCore import QUrl
    Setup = build_setup_dialog()
    dlg = Setup()
    if not dlg.exec_() if hasattr(dlg, "exec_") else not dlg.exec():
        return _stop("Annulé à la fenêtre des paramètres : aucun fichier n'a été produit.")
    if not dlg.settings:
        return _stop("Paramètres invalides : aucun fichier n'a été produit.")
    cfg = dlg.settings
    root = cfg["out"]
    main_cfg = dict(cfg, out=os.path.join(root, "Analyse_principale") if cfg["sensitivity"] else root)
    res = run_export(main_cfg)
    try:
        _in_main = [y for y in res["drought"] if str(y) in res["years"]]
        sr_register(os.path.join(os.path.dirname(res["report"]), "Stage_Report_04B_Transitions.json"), "04B", "Transition matrices, statistics and reviewer report", AREA_NAME,
                    "FAIL" if not res["checks_ok"] else ("WARN" if _in_main else "PASS"), os.path.basename(res["report"]), 0 if res["checks_ok"] else 1, 1 if _in_main else 0)
    except Exception as _exc:
        print("[Rapport HTML d'étape] enregistrement impossible : " + str(_exc))
    lines = [f"Analyse principale : années {', '.join(res['years'])}" + (f" (exclues : {', '.join(res['excluded'])})" if res["excluded"] else "") + f" · {res['figures']} figures.", f"Rapport : {res['report']}"]
    if res["drought"]:
        lines.append(f"Années de sécheresse détectées : {', '.join(str(y) for y in res['drought'])}.")
    if cfg["sensitivity"]:
        res2 = run_export(dict(cfg, out=os.path.join(root, "Sensibilite_Toutes_Annees"), years=None))
        lines += ["", f"Analyse de sensibilité (toutes les années : {', '.join(res2['years'])}) :", f"Rapport : {res2['report']}"]
    msg = "\n".join(lines) + f"\n\nDossier : {root}"
    print(msg)
    QMessageBox.information(None, "Rapport terminé", msg)
    try:
        from qgis.PyQt.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(res["report"]))
    except Exception:
        pass


# ====================== MAIN ======================
main()
