# -*- coding: utf-8 -*-
# SDG 15.3.1 REFERENCE PIPELINE — STAGE 04A / 08 : Review of improbable land-cover transitions — QGIS
"""
REVUE INTERACTIVE DES TRANSITIONS IMPROBABLES ENTRE LES CARTES LULC (script COMPLÉMENTAIRE et INDÉPENDANT)
QGIS / PyQGIS — à coller dans la Console Python de QGIS (ou exécuter via l'éditeur).

CE QUE FAIT LE SCRIPT
  1. Vous indiquez le dossier des cartes finales (LULC_<ZONE>_<année>.tif, dossier « LULC/ » ou le dossier de résultats) : toutes les années sont détectées et classées de la plus ANCIENNE à la plus RÉCENTE.
  2. Pour chaque PÉRIODE (années consécutives, + éventuellement la période globale première -> dernière) il compte les transitions IMPROBABLES (ex. Built-up -> Rangeland, Bareland -> Forest...) et les affiche dans un
     tableau récapitulatif (surface en hectares) : vous cochez celles à revoir.
  3. UNE FENÊTRE INTERACTIVE S'OUVRE POUR CHAQUE TRANSITION : la carte montre les pixels concernés (surlignés), la liste des parcelles (surface, position), et vous choisissez :
        - de CORRIGER : l'année récente reprend la classe de l'année ancienne (ex. le bâti ne disparaît pas), OU l'année ancienne reprend la classe de la récente, OU une classe de votre choix dans l'une des deux années ;
          à appliquer à TOUTE la transition, aux PARCELLES sélectionnées, ou à l'intérieur d'un POLYGONE que vous dessinez ;
        - de LAISSER la transition telle quelle (elle est alors considérée comme acceptée).
     Une correction dans une année modifie aussi les périodes voisines : les surfaces restantes sont recalculées à chaque fenêtre (une transition déjà corrigée est sautée).
  4. À la fin : cartes corrigées (<sortie>/LULC/LULC_<ZONE>_<année>.tif), journal de toutes les corrections, tableau AVANT / APRÈS, rapport HTML. Les cartes d'origine ne sont JAMAIS modifiées.

LIMITES (à lire)
  - Une transition « improbable » n'est pas forcément une erreur (un bâti démoli, une carrière rendue au sol nu...). Le script propose, vous décidez ; chaque correction est tracée.
  - Corriger un pixel dans l'année récente en lui redonnant la classe ancienne est une décision de persistance : à justifier par l'image haute résolution ou le terrain (vous pouvez afficher une image HR en fond).
  - La liste des transitions improbables est celle du script de classification (modifiable : champ « transitions supplémentaires » et case « toute disparition du bâti »).
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

PIPELINE_BUILD = "2026.10-d316fcbfa6b3"
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
def review_stage_report(out, session, chosen, ba, bu_before, bu_after, years, px_ha, params, t0, area_name, lang="en", log=print):
    """Rapport HTML de l'étape 04A (revue des transitions improbables) : bilan avant / après, corrections, transitions laissées telles quelles, bâti."""
    en = lang == "en"
    T = lambda a, b: a if en else b
    cls = lambda k: f"{k} — {CLASS_NAMES.get(int(k), '?')}"
    corr = session.corrections
    kept = [q for q in chosen if q["key"] in session.kept]
    summary = [T(f"{len(chosen)} improbable transitions reviewed: {len({(c['older'], c['newer'], c['from'], c['to']) for c in corr})} corrected (in whole or in part), {len(kept)} left as they are", f"{len(chosen)} transitions improbables revues : {len({(c['older'], c['newer'], c['from'], c['to']) for c in corr})} corrigées (en tout ou en partie), {len(kept)} laissées telles quelles"),
               T(f"{len(corr)} corrections; years modified: {', '.join(session.changed_years()) or 'none'}", f"{len(corr)} corrections ; années modifiées : {', '.join(session.changed_years()) or 'aucune'}")]
    tb_ba = [[T("Period", "Période"), T("Transition", "Transition"), T("Before (ha)", "Avant (ha)"), T("After (ha)", "Après (ha)"), T("Difference (ha)", "Différence (ha)")]] + [[f"{r['period'][0]}–{r['period'][1]}", f"{cls(r['from'])} → {cls(r['to'])}", f"{r['ha_before']:.2f}", f"{r['ha_after']:.2f}", f"{r['ha_after'] - r['ha_before']:+.2f}"] for r in ba]
    tb_corr = [[T("Time", "Heure"), T("Year modified", "Année modifiée"), T("Transition", "Transition"), T("Correction", "Correction"), T("Pixels", "Pixels"), T("Area (ha)", "Surface (ha)")]] + [[c.get("timestamp", ""), c["year"], f"{c['older']}→{c['newer']}: {cls(c['from'])} → {cls(c['to'])}", c["text"], c["px"], f"{c['ha']:.2f}"] for c in corr]
    after_by = {r["period"]: r for r in bu_after}
    tb_bu = [[T("Period", "Période"), T("Built-up loss before (ha)", "Perte de bâti avant (ha)"), T("after (ha)", "après (ha)"), T("Detail after", "Détail après")]] + [[f"{r['period'][0]}–{r['period'][1]}", f"{r['total_ha']:.1f}", f"{after_by.get(r['period'], r)['total_ha']:.1f}", ", ".join(f"{CLASS_NAMES[k]} {v:.1f}" for k, v in after_by.get(r["period"], r)["by_class"].items()) or "—"] for r in bu_before]
    tb_kept = [[T("Period", "Période"), T("Transition", "Transition"), T("Area (ha)", "Surface (ha)")]] + [[f"{q['older']}–{q['newer']}", f"{cls(q['from'])} → {cls(q['to'])}", f"{q['ha']:.2f}"] for q in kept]
    left = sum(r["ha_after"] for r in ba)
    checks = [(T("Every reviewed transition has a decision", "Chaque transition revue a une décision"), "PASS" if all((q["key"] in session.kept) or session.pixels_left(q) == 0 or any((c["older"], c["newer"], c["from"], c["to"]) == (q["older"], q["newer"], q["from"], q["to"]) for c in corr) for q in chosen) else "WARN", T("corrected, left as is, or no pixel remaining", "corrigée, laissée telle quelle, ou plus aucun pixel")),
              (T("Source maps untouched", "Cartes d'origine intactes"), "PASS", T("corrected maps are written to a different folder", "les cartes corrigées sont écrites dans un autre dossier")),
              (T("Improbable transitions remaining after review", "Transitions improbables restantes après la revue"), "PASS" if left <= 0.5 else "INFO", f"{left:,.1f} ha")]
    new_tr = [r for r in ba if r["ha_before"] == 0 and r["ha_after"] > 0]
    if new_tr:
        checks.append((T("Cascade: corrections revealed new improbable transitions in neighbouring periods", "Cascade : des corrections ont révélé de nouvelles transitions improbables dans les périodes voisines"), "WARN", f"{len(new_tr)} " + T("transitions (see the before / after table)", "transitions (voir le tableau avant / après)")))
    sections = [{"id": "ba", "title": T("Improbable transitions: before / after", "Transitions improbables : avant / après"), "tables": [(T("All controlled transitions", "Toutes les transitions contrôlées"), tb_ba)]},
                {"id": "corr", "title": T("Corrections applied", "Corrections appliquées"), "intro": T("Each correction is an expert decision, traced with its time, year, transition and area.", "Chaque correction est une décision d'expert, tracée avec son heure, son année, sa transition et sa surface."), "tables": [("", tb_corr)]},
                {"id": "kept", "title": T("Transitions left as they are (accepted)", "Transitions laissées telles quelles (acceptées)"), "tables": [("", tb_kept)]},
                {"id": "bu", "title": T("Built-up losses", "Pertes de bâti"), "tables": [("", tb_bu)]}]
    L = [T("An improbable transition is not necessarily an error (a demolished building, a quarry restored to soil): the tool proposes, the expert decides and justifies.", "Une transition improbable n'est pas forcément une erreur (bâti démoli, carrière rendue au sol) : l'outil propose, l'expert décide et justifie."),
         T("Restoring the class of the older year is a persistence decision: justify it with very-high-resolution imagery or field evidence.", "Redonner la classe de l'année ancienne est une décision de persistance : la justifier par l'imagerie très haute résolution ou le terrain."),
         T("A correction in one year changes the two neighbouring periods; the before / after table shows any new improbable transition.", "Une correction dans une année modifie les deux périodes voisines ; le tableau avant / après montre toute nouvelle transition improbable.")]
    A = [T("The list of improbable transitions is defined in the script (IMPLAUSIBLE_TRANSITIONS) and in the start-up window: adapt it to the landscape of the new area.", "La liste des transitions improbables est définie dans le script (IMPLAUSIBLE_TRANSITIONS) et dans la fenêtre de démarrage : l'adapter au paysage de la nouvelle zone."),
         T("Use a very-high-resolution background image of the new area to decide.", "Utiliser une image de fond très haute résolution de la nouvelle zone pour décider."),
         T("Run this stage after 03 and before 04B, 05A, 06 and 07, and use its output folder (LULC/) as the map folder of the next stages.", "Exécuter cette étape après 03 et avant 04B, 05A, 06 et 07, et utiliser son dossier de sortie (LULC/) comme dossier de cartes des étapes suivantes.")]
    R = ["Pontius, R.G. Jr., Santacruz, A. (2014). Quantity, exchange, and shift components of difference in a square contingency table. International Journal of Remote Sensing 35, 7543–7554.", "UNCCD. Good Practice Guidance for SDG Indicator 15.3.1 (version 2) and its Addendum."]
    spec = {"stage": "04A", "title": T("Review of improbable land-cover transitions", "Revue des transitions improbables de couverture"), "subtitle": T("Interactive correction or acceptance", "Correction ou acceptation interactive"), "lang": lang, "area": area_name, "started": t0, "out_dir": out,
            "params": params, "inputs": [], "summary": summary, "checks": checks, "sections": sections, "limits": L, "adapt": A, "references": R}
    path = os.path.join(out, "Corrections", "Stage_Report_04A_Review.html")
    write_stage_report(path, spec)
    log("[Rapport HTML] " + path)
    return path
# <<< STAGE_BUILDER_END
import re
import csv
import json
import time
import shutil
import html as _html
import numpy as np
from scipy import ndimage

from osgeo import gdal, ogr, osr

CLASS_NAMES = {1: "Built-up", 2: "Water", 3: "Sebkha", 4: "Bareland / Rock", 5: "Cropland", 6: "Fallow", 7: "Forest", 8: "Rangeland"}
CLASS_COLORS = {1: (220, 50, 50), 2: (100, 140, 210), 3: (214, 230, 245), 4: (185, 195, 205), 5: (255, 225, 130), 6: (240, 175, 0), 7: (135, 185, 120), 8: (100, 245, 140)}
# Transitions IMPROBABLES (ancienne année -> année récente) : les mêmes que le script de classification.
IMPLAUSIBLE_TRANSITIONS = {(1, 5), (1, 6), (1, 7), (1, 8), (3, 1), (3, 5), (3, 6), (3, 7), (3, 8), (4, 7), (2, 7), (7, 2), (7, 3), (8, 2), (8, 3)}
MIN_HA_DEFAULT = 0.0
MAP_RE = re.compile(r"^LULC_.*?_((?:19|20)\d{2})\.tif$", re.I)
SKIP_NAME_PARTS = ("_Original", "_Edited", "_Retro", "_Corrige")
CORRECTION_MODES = ["newer_takes_older", "older_takes_newer", "newer_class", "older_class"]


# ============================================================================
# 1. LOGIQUE PURE (testée sans QGIS ni GDAL)
# ============================================================================
def class_label(k):
    return f"{k} — {CLASS_NAMES.get(int(k), '?')}"


def find_lulc_maps(folder):
    """{année: chemin} des cartes finales dans `folder` puis `folder/LULC` (les copies _Original / _Edited / _Retro / _Corrige sont ignorées ; le dossier direct est prioritaire)."""
    out = {}
    for d in (os.path.join(folder, "LULC"), folder):                      # le dossier direct écrase LULC/ si les deux existent
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            m = MAP_RE.match(fn)
            if m and not any(p in fn for p in SKIP_NAME_PARTS):
                out[m.group(1)] = os.path.join(d, fn)
    return dict(sorted(out.items(), key=lambda kv: int(kv[0])))


def normalize_lulc(arr):
    """Codes 1-8 ; l'ancien Matorral (9) est lu comme Forest (7) ; tout le reste = 0 (non classé)."""
    a = np.asarray(arr).astype(np.int16)
    a = np.where(a == 9, 7, a)
    a[(a < 1) | (a > 8)] = 0
    return a.astype(np.uint8)


def period_pairs(years, include_overall=False):
    """Périodes à analyser : années consécutives (de la plus ancienne à la plus récente), + la période globale première -> dernière si demandé et s'il y a plus de deux années."""
    ys = sorted({int(y) for y in years})
    pairs = [(ys[i], ys[i + 1]) for i in range(len(ys) - 1)]
    if include_overall and len(ys) > 2:
        pairs.append((ys[0], ys[-1]))
    return pairs


def parse_pairs_text(text):
    """« 5-1, 7-4 » ou « 5>1 ; 7>4 » -> {(5, 1), (7, 4)} ; ValueError si invalide ou hors des classes 1-8."""
    out = set()
    for tok in re.split(r"[,;\s]+", str(text or "").strip()):
        if not tok:
            continue
        m = re.fullmatch(r"(\d)\s*[-–>]+\s*(\d)", tok)
        if not m:
            raise ValueError(f"Transition invalide : « {tok} » (format attendu : 5-1, 7-4 ...).")
        a, b = int(m.group(1)), int(m.group(2))
        if a not in CLASS_NAMES or b not in CLASS_NAMES or a == b:
            raise ValueError(f"Transition invalide : {tok} (classes de 1 à 8, différentes).")
        out.add((a, b))
    return out


def build_pair_set(builtup_any=True, extra_text=""):
    """Transitions à contrôler : celles du script de classification, + toute disparition du bâti (Built-up -> n'importe quelle autre classe), + celles que vous ajoutez."""
    s = set(IMPLAUSIBLE_TRANSITIONS)
    if builtup_any:
        s |= {(1, k) for k in CLASS_NAMES if k != 1}
    s |= parse_pairs_text(extra_text)
    return s


def transition_table(older, newer, px_ha, pair_set, domain=None):
    """Transitions de `pair_set` présentes entre deux cartes : [{"from", "to", "px", "ha"}] par surface décroissante (seuls les pixels classés aux deux dates comptent)."""
    o, n = np.asarray(older), np.asarray(newer)
    valid = (o > 0) & (n > 0) & (o != n)
    if domain is not None:
        valid &= np.asarray(domain, bool)
    if not valid.any():
        return []
    counts = np.bincount(o[valid].astype(np.int64) * 10 + n[valid].astype(np.int64), minlength=100)
    rows = []
    for a, b in sorted(pair_set):
        k = int(counts[a * 10 + b])
        if k > 0:
            rows.append({"from": a, "to": b, "px": k, "ha": k * px_ha})
    return sorted(rows, key=lambda r: -r["px"])


def build_queue(maps, years, px_ha, pair_set, include_overall=False, domain=None, min_ha=MIN_HA_DEFAULT):
    """File des transitions à revoir : [{"older", "newer", "from", "to", "px", "ha", "key"}] par période (ancienne d'abord) puis surface décroissante."""
    queue = []
    for (a, b) in period_pairs(years, include_overall):
        for r in transition_table(maps[str(a)], maps[str(b)], px_ha, pair_set, domain):
            if r["ha"] >= min_ha:
                queue.append({"older": a, "newer": b, "from": r["from"], "to": r["to"], "px": r["px"], "ha": r["ha"], "key": f"{a}_{b}_{r['from']}_{r['to']}"})
    return queue


def builtup_loss_table(maps, years, px_ha, include_overall=False, domain=None):
    """Par période : surface de Built-up qui devient chaque AUTRE classe (comme le bilan « Built-up -> ... »). [{"period", "total_ha", "by_class": {classe: ha}}]."""
    out = []
    for (a, b) in period_pairs(years, include_overall):
        o, n = np.asarray(maps[str(a)]), np.asarray(maps[str(b)])
        valid = (o == 1) & (n > 0) & (n != 1)
        if domain is not None:
            valid &= np.asarray(domain, bool)
        cnt = np.bincount(n[valid].astype(np.int64), minlength=10)
        by = {k: int(cnt[k]) * px_ha for k in CLASS_NAMES if k != 1 and cnt[k] > 0}
        out.append({"period": (a, b), "total_ha": sum(by.values()), "by_class": dict(sorted(by.items(), key=lambda kv: -kv[1]))})
    return out


def transition_mask(older, newer, a, b, domain=None):
    m = (np.asarray(older) == a) & (np.asarray(newer) == b)
    if domain is not None:
        m &= np.asarray(domain, bool)
    return m


def label_patches(mask, px_ha=0.09, geo_tf=None):
    """
    Parcelles (composantes connexes 8) d'un masque : (matrice d'étiquettes, [{"id", "px", "ha", "row", "col", "x", "y", "bbox": (r0, r1, c0, c1)}]) par surface décroissante.
    Les centroïdes sont calculés sur les seuls pixels du masque (rapide même sur une grande image).
    """
    mask = np.asarray(mask, bool)
    labels, n = ndimage.label(mask, structure=np.ones((3, 3), bool))
    if n == 0:
        return labels, []
    rr, cc = np.nonzero(labels)
    lab = labels[rr, cc]
    px = np.bincount(lab, minlength=n + 1)
    sr, sc = np.bincount(lab, weights=rr, minlength=n + 1), np.bincount(lab, weights=cc, minlength=n + 1)
    boxes = ndimage.find_objects(labels)
    patches = []
    for i in range(1, n + 1):
        r_, c_ = sr[i] / px[i], sc[i] / px[i]
        sl = boxes[i - 1]
        d = {"id": i, "px": int(px[i]), "ha": float(px[i]) * px_ha, "row": float(r_), "col": float(c_), "bbox": (sl[0].start, sl[0].stop, sl[1].start, sl[1].stop)}
        if geo_tf is not None:
            d["x"] = float(geo_tf[0] + (c_ + 0.5) * geo_tf[1] + (r_ + 0.5) * geo_tf[2])
            d["y"] = float(geo_tf[3] + (c_ + 0.5) * geo_tf[4] + (r_ + 0.5) * geo_tf[5])
        patches.append(d)
    return labels, sorted(patches, key=lambda p: -p["px"])


def mask_from_patches(labels, ids):
    return np.isin(labels, list(ids)) if len(ids) else np.zeros(labels.shape, bool)


def correction_text(mode, older, newer, a, b, new_class=None):
    """Phrase lisible d'une correction (journal, rapport, bouton)."""
    if mode == "newer_takes_older":
        return f"{newer} : « {class_label(b)} » → « {class_label(a)} » (reprend la classe de {older})"
    if mode == "older_takes_newer":
        return f"{older} : « {class_label(a)} » → « {class_label(b)} » (reprend la classe de {newer})"
    if mode == "newer_class":
        return f"{newer} : « {class_label(b)} » → « {class_label(new_class)} »"
    if mode == "older_class":
        return f"{older} : « {class_label(a)} » → « {class_label(new_class)} »"
    return str(mode)


def apply_correction(maps, older, newer, a, b, mask, mode, new_class=None):
    """
    Applique une correction aux pixels de `mask` (pixels de la transition a -> b entre les années `older` et `newer`), directement dans maps[année].
      newer_takes_older : l'année RÉCENTE reprend la classe de l'ancienne (a) ; older_takes_newer : l'ANCIENNE reprend celle de la récente (b) ;
      newer_class / older_class : une classe choisie dans l'année récente / ancienne.
    Retourne l'enregistrement de la correction (pour l'annulation et le journal) ou None si le masque est vide.
    """
    if mode not in CORRECTION_MODES:
        raise ValueError(f"Mode de correction inconnu : {mode}")
    mask = np.asarray(mask, bool)
    if mode in ("newer_class", "older_class"):
        if new_class not in CLASS_NAMES:
            raise ValueError("Choisissez une classe (1 à 8).")
    year = str(newer if mode in ("newer_takes_older", "newer_class") else older)
    arr = maps[year]
    # on ne touche que les pixels qui sont ENCORE dans la transition (une correction précédente a pu en modifier)
    cur_o, cur_n = maps[str(older)], maps[str(newer)]
    live = mask & (cur_o == a) & (cur_n == b)
    if not live.any():
        return None
    value = {"newer_takes_older": a, "older_takes_newer": b}.get(mode, new_class)
    before = arr[live].copy()
    arr[live] = np.uint8(value)
    return {"year": year, "older": int(older), "newer": int(newer), "from": int(a), "to": int(b), "mode": mode, "new_class": int(value), "mask": live, "before": before, "px": int(live.sum()), "text": correction_text(mode, older, newer, a, b, new_class)}


def undo_correction(maps, rec):
    maps[rec["year"]][rec["mask"]] = rec["before"]


class ReviewSession:
    """État d'une revue : cartes en mémoire (copies), cartes d'origine, file des transitions, corrections et transitions laissées telles quelles."""

    def __init__(self, maps, years, px_ha, pair_set, queue, domain=None, geo_tf=None):
        self.years = [str(y) for y in sorted(years, key=int)]
        self.original = {y: np.asarray(maps[y]).copy() for y in self.years}
        self.maps = {y: np.asarray(maps[y]).copy() for y in self.years}
        self.px_ha, self.pair_set, self.queue, self.domain, self.geo_tf = px_ha, pair_set, queue, domain, geo_tf
        self.corrections, self.kept, self.undo_stack = [], set(), []

    def pixels_left(self, item):
        """Pixels de la transition encore présents (après les corrections déjà faites, y compris celles des périodes voisines)."""
        return int(transition_mask(self.maps[str(item["older"])], self.maps[str(item["newer"])], item["from"], item["to"], self.domain).sum())

    def next_index(self, i, step=1):
        """Prochaine transition à montrer dans le sens `step` : celles dont tous les pixels ont déjà été corrigés sont sautées. None s'il n'y en a plus."""
        j = i + step
        while 0 <= j < len(self.queue):
            if self.pixels_left(self.queue[j]) > 0:
                return j
            j += step
        return None

    def first_index(self):
        if self.queue and self.pixels_left(self.queue[0]) > 0:
            return 0
        return self.next_index(0, 1) if self.queue else None

    def patches(self, item):
        m = transition_mask(self.maps[str(item["older"])], self.maps[str(item["newer"])], item["from"], item["to"], self.domain)
        return m, label_patches(m, self.px_ha, self.geo_tf)

    def apply(self, item, mask, mode, new_class=None):
        mask = np.asarray(mask, bool)
        if self.domain is not None:
            mask = mask & self.domain
        rec = apply_correction(self.maps, item["older"], item["newer"], item["from"], item["to"], mask, mode, new_class)
        if rec is None:
            return None
        rec["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
        rec["ha"] = rec["px"] * self.px_ha
        self.corrections.append(rec)
        self.undo_stack.append(rec)
        self.kept.discard(item["key"])
        return rec

    def keep(self, item):
        """Laisser la transition telle quelle (acceptée)."""
        self.kept.add(item["key"])

    def undo(self):
        if not self.undo_stack:
            return None
        rec = self.undo_stack.pop()
        undo_correction(self.maps, rec)
        self.corrections.remove(rec)
        return rec

    def changed_years(self):
        return [y for y in self.years if not np.array_equal(self.maps[y], self.original[y])]

    def before_after(self, include_overall=False):
        """[{"period", "from", "to", "ha_before", "ha_after"}] pour toutes les transitions de la liste de contrôle."""
        out = []
        for (a, b) in period_pairs(self.years, include_overall):
            before = {(r["from"], r["to"]): r["px"] for r in transition_table(self.original[str(a)], self.original[str(b)], self.px_ha, self.pair_set, self.domain)}
            after = {(r["from"], r["to"]): r["px"] for r in transition_table(self.maps[str(a)], self.maps[str(b)], self.px_ha, self.pair_set, self.domain)}
            for k in sorted(set(before) | set(after), key=lambda t: -before.get(t, 0)):
                out.append({"period": (a, b), "from": k[0], "to": k[1], "ha_before": before.get(k, 0) * self.px_ha, "ha_after": after.get(k, 0) * self.px_ha})
        return out


def corrections_csv_rows(corrections):
    rows = [["Horodatage", "Annee_modifiee", "Periode", "Transition", "Correction", "Classe_posee", "Pixels", "Surface_ha"]]
    for r in corrections:
        rows.append([r.get("timestamp", ""), r["year"], f"{r['older']}-{r['newer']}", f"{class_label(r['from'])} -> {class_label(r['to'])}", r["text"], class_label(r["new_class"]), r["px"], f"{r['ha']:.4f}"])
    return rows


def before_after_csv_rows(ba):
    rows = [["Periode", "Transition", "Avant_ha", "Apres_ha", "Difference_ha"]]
    for r in ba:
        rows.append([f"{r['period'][0]}-{r['period'][1]}", f"{class_label(r['from'])} -> {class_label(r['to'])}", f"{r['ha_before']:.2f}", f"{r['ha_after']:.2f}", f"{r['ha_after'] - r['ha_before']:+.2f}"])
    return rows


def build_report_html(years, ba, builtup_before, builtup_after, corrections, kept, queue, params, generated=None):
    """Rapport HTML autonome : bilan AVANT / APRÈS, corrections, transitions laissées, bilan « Built-up -> autres classes »."""
    e = lambda x: _html.escape(str(x))
    css = ("body{font-family:Segoe UI,Arial,sans-serif;margin:24px;max-width:1150px;color:#222}h1{font-size:22px}h2{font-size:17px;margin-top:24px;border-bottom:2px solid #ddd;padding-bottom:4px}"
           "table{border-collapse:collapse;margin:8px 0}th,td{border:1px solid #ccc;padding:4px 9px;font-size:13px;text-align:left}th{background:#f2f2f2}td.n{text-align:right}.small{color:#666;font-size:12px}")
    out = [f"<!DOCTYPE html><html lang='fr'><head><meta charset='utf-8'><title>Revue des transitions improbables</title><style>{css}</style></head><body>",
           "<h1>Revue des transitions improbables — cartes LULC</h1>", f"<p class='small'>Généré le {e(generated or time.strftime('%Y-%m-%d %H:%M'))} · années : {e(', '.join(years))}</p>"]
    out.append("<h2>Paramètres</h2><table>" + "".join(f"<tr><th>{e(k)}</th><td>{e(v)}</td></tr>" for k, v in params.items()) + "</table>")
    n_kept = sum(1 for q in queue if q["key"] in kept)
    out.append(f"<p>Transitions revues : <b>{len(queue)}</b> · corrigées (au moins en partie) : <b>{len({(c['older'], c['newer'], c['from'], c['to']) for c in corrections})}</b> · laissées telles quelles : <b>{n_kept}</b> · corrections : <b>{len(corrections)}</b>.</p>")
    out.append("<h2>Transitions improbables : avant / après correction (ha)</h2><table><tr><th>Période</th><th>Transition</th><th>Avant</th><th>Après</th><th>Différence</th></tr>")
    for r in ba:
        out.append(f"<tr><td>{r['period'][0]}→{r['period'][1]}</td><td>{e(class_label(r['from']))} → {e(class_label(r['to']))}</td><td class='n'>{r['ha_before']:,.2f}</td><td class='n'>{r['ha_after']:,.2f}</td><td class='n'>{r['ha_after'] - r['ha_before']:+,.2f}</td></tr>")
    out.append("</table><h2>Bilan « Built-up → autres classes » (ha)</h2><table><tr><th>Période</th><th>Avant : total</th><th>Après : total</th><th>Détail après</th></tr>")
    after_by = {r["period"]: r for r in builtup_after}
    for r in builtup_before:
        a = after_by.get(r["period"], r)
        det = ", ".join(f"{CLASS_NAMES[k]} {v:,.1f}" for k, v in a["by_class"].items()) or "—"
        out.append(f"<tr><td>{r['period'][0]}→{r['period'][1]}</td><td class='n'>{r['total_ha']:,.1f}</td><td class='n'>{a['total_ha']:,.1f}</td><td>{e(det)}</td></tr>")
    out.append("</table><h2>Corrections appliquées</h2>")
    if corrections:
        out.append("<table><tr><th>Heure</th><th>Année modifiée</th><th>Transition</th><th>Correction</th><th>Pixels</th><th>Surface (ha)</th></tr>")
        for c in corrections:
            out.append(f"<tr><td>{e(c.get('timestamp', ''))}</td><td>{e(c['year'])}</td><td>{c['older']}→{c['newer']} : {e(class_label(c['from']))} → {e(class_label(c['to']))}</td><td>{e(c['text'])}</td><td class='n'>{c['px']:,}</td><td class='n'>{c['ha']:,.2f}</td></tr>")
        out.append("</table>")
    else:
        out.append("<p>Aucune correction : toutes les transitions ont été laissées telles quelles.</p>")
    out.append("<h2>Comment lire</h2><ul><li>Une transition improbable n'est pas forcément une erreur : chaque correction est une décision d'expert, tracée dans le journal CSV.</li>"
               "<li>Les cartes d'origine ne sont pas modifiées ; les cartes corrigées sont dans le dossier de sortie, sous les mêmes noms.</li></ul></body></html>")
    return "".join(out)


# ============================================================================
# 2. COUCHE GDAL / QGIS (relue, non exécutable hors QGIS)
# ============================================================================
def read_map(path):
    ds = gdal.Open(path, gdal.GA_ReadOnly)
    if ds is None:
        raise RuntimeError(f"Carte illisible : {path}")
    return normalize_lulc(ds.GetRasterBand(1).ReadAsArray()), ds.GetGeoTransform(), ds.GetProjection()


def write_raster(path, arr, gt, wkt, dtype=gdal.GDT_Byte, nodata=0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ds = gdal.GetDriverByName("GTiff").Create(path, arr.shape[1], arr.shape[0], 1, dtype, ["COMPRESS=LZW", "TILED=YES"])
    ds.SetGeoTransform(gt)
    ds.SetProjection(wkt)
    b = ds.GetRasterBand(1)
    b.WriteArray(arr)
    if nodata is not None:
        b.SetNoDataValue(nodata)
    b.FlushCache()
    ds = None
    return path


def admin_mask_from_shp(shp_path, rows, cols, gt, wkt):
    ds = ogr.Open(shp_path)
    if ds is None:
        raise RuntimeError(f"Zone d'étude illisible : {shp_path}")
    mem = gdal.GetDriverByName("MEM").Create("", cols, rows, 1, gdal.GDT_Byte)
    mem.SetGeoTransform(gt)
    mem.SetProjection(wkt)
    gdal.RasterizeLayer(mem, [1], ds.GetLayer(), burn_values=[1])
    return mem.GetRasterBand(1).ReadAsArray() == 1


def polygon_to_mask(geom, shape, geo_tf, proj_wkt):
    rows, cols = shape
    ds = gdal.GetDriverByName("MEM").Create("", cols, rows, 1, gdal.GDT_Byte)
    ds.SetGeoTransform(geo_tf)
    ds.SetProjection(proj_wkt)
    band = ds.GetRasterBand(1)
    band.Fill(0)
    vds = ogr.GetDriverByName("Memory").CreateDataSource("rv_mem")
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


def paletted_layer(path, name, classes):
    """Couche raster à valeurs uniques ; classes = {valeur: ((r, g, b, a), libellé)}."""
    from qgis.core import QgsRasterLayer, QgsPalettedRasterRenderer
    from qgis.PyQt.QtGui import QColor
    lyr = QgsRasterLayer(path, name)
    if not lyr.isValid():
        return None
    cl = [QgsPalettedRasterRenderer.Class(int(v), QColor(*rgba), lab) for v, (rgba, lab) in classes.items()]
    lyr.setRenderer(QgsPalettedRasterRenderer(lyr.dataProvider(), 1, cl))
    return lyr


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


def present(dlg, maximize=True):
    """Fenêtre libre (réduire / agrandir), ouverte en plein écran, qui attend sa fermeture sans bloquer QGIS."""
    from qgis.PyQt.QtCore import Qt, QEventLoop
    try:
        dlg.setParent(None)
        dlg.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
        for h in ("WindowMinimizeButtonHint", "WindowMaximizeButtonHint", "WindowCloseButtonHint"):
            dlg.setWindowFlag(getattr(Qt, h), True)
    except Exception:
        pass
    loop = QEventLoop()
    try:
        dlg.finished.connect(lambda *_: loop.quit())
    except Exception:
        pass
    dlg.showMaximized() if maximize else dlg.show()
    try:
        dlg.raise_()
        dlg.activateWindow()
    except Exception:
        pass
    loop.exec_() if hasattr(loop, "exec_") else loop.exec()
    return getattr(dlg, "result", lambda: 0)()


def make_classes_palette():
    return {k: ((*CLASS_COLORS[k], 255), class_label(k)) for k in CLASS_COLORS}


def build_dialogs():
    """Crée les classes de fenêtres (PyQt importé ici pour que les fonctions pures restent importables sans QGIS)."""
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtGui import QColor
    from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog, QMessageBox, QCheckBox, QDoubleSpinBox, QTableWidget,
                                     QTableWidgetItem, QSplitter, QWidget, QGroupBox, QComboBox, QRadioButton, QButtonGroup, QAbstractItemView, QTextEdit)
    from qgis.gui import QgsMapCanvas, QgsMapToolPan, QgsMapToolZoom, QgsMapToolEmitPoint, QgsRubberBand
    from qgis.core import QgsRasterLayer, QgsGeometry, QgsRectangle, QgsCoordinateReferenceSystem, QgsWkbTypes

    class Setup(QDialog):
        def __init__(self):
            super().__init__(None)
            self.setWindowTitle("Revue des transitions improbables — paramètres")
            self.resize(780, 520)
            lay = QVBoxLayout(self)
            lay.addWidget(QLabel("<b>Revue interactive des transitions improbables</b> : une fenêtre pour chaque transition, pour la corriger ou la laisser."))
            self.le_in, self.le_out, self.le_study, self.le_hr, self.le_extra = QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit()
            for label, le, kind in (("1. Dossier des cartes LULC (contient LULC_<ZONE>_<année>.tif ou un sous-dossier LULC/)", self.le_in, "dir"), ("2. Dossier de SORTIE (cartes corrigées, journal, rapport)", self.le_out, "dir"),
                                    ("3. Zone d'étude (Study_Area_Final.shp) — facultatif : limite l'analyse à la zone", self.le_study, "shp"), ("4. Image haute résolution de fond — facultatif", self.le_hr, "img")):
                box = QGroupBox(label)
                h = QHBoxLayout(box)
                h.addWidget(le, 1)
                b = QPushButton("Parcourir…")
                b.clicked.connect(lambda _c=False, le_=le, k=kind: self.browse(le_, k))
                h.addWidget(b)
                lay.addWidget(box)
            self.lbl_years = QLabel("")
            self.lbl_years.setWordWrap(True)
            lay.addWidget(self.lbl_years)
            self.le_in.editingFinished.connect(self.refresh_years)
            opt = QGroupBox("5. Options")
            ov = QVBoxLayout(opt)
            self.chk_bu = QCheckBox("Considérer TOUTE disparition du bâti (Built-up → n'importe quelle autre classe) comme improbable")
            self.chk_bu.setChecked(True)
            self.chk_overall = QCheckBox("Revoir aussi la période GLOBALE (première → dernière année) : attention, une correction y modifie la première ou la dernière carte")
            self.chk_copy = QCheckBox("Copier aussi dans le dossier de sortie les années NON modifiées (dossier complet et directement utilisable)")
            self.chk_copy.setChecked(True)
            row = QHBoxLayout()
            row.addWidget(QLabel("Surface minimale d'une transition à revoir (ha) :"))
            self.sp_min = QDoubleSpinBox()
            self.sp_min.setRange(0.0, 100000.0)
            self.sp_min.setDecimals(2)
            self.sp_min.setValue(MIN_HA_DEFAULT)
            row.addWidget(self.sp_min)
            row.addWidget(QLabel("Transitions supplémentaires (ex. 5-1, 7-4) :"))
            self.le_extra.setPlaceholderText("ancienne-récente, ex. 5-1, 7-4")
            row.addWidget(self.le_extra, 1)
            for w in (self.chk_bu, self.chk_overall, self.chk_copy):
                ov.addWidget(w)
            ov.addLayout(row)
            lay.addWidget(opt)
            self.lbl_err = QLabel("")
            self.lbl_err.setWordWrap(True)
            lay.addWidget(self.lbl_err)
            btns = QHBoxLayout()
            go, cancel = QPushButton("▶ Calculer le bilan"), QPushButton("Annuler")
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
                flt = "Shapefile (*.shp)" if kind == "shp" else "Images (*.tif *.tiff *.jp2 *.png *.jpg *.vrt *.img);;Tous (*)"
                p, _ = QFileDialog.getOpenFileName(self, "Fichier", le.text() or "", flt)
            if p:
                le.setText(p)
                if le is self.le_in:
                    self.refresh_years()
                    if not self.le_out.text().strip():
                        self.le_out.setText(os.path.join(p, "Revue_Transitions"))

        def refresh_years(self):
            maps = find_lulc_maps(self.le_in.text().strip()) if self.le_in.text().strip() else {}
            self.lbl_years.setText(("Cartes trouvées : " + ", ".join(f"{y}" for y in maps) + f" ({len(maps)})") if maps else "Aucune carte LULC_<ZONE>_<année>.tif trouvée dans ce dossier.")

        def on_go(self):
            maps = find_lulc_maps(self.le_in.text().strip())
            errs = []
            if len(maps) < 2:
                errs.append("Il faut au moins DEUX cartes LULC (années différentes) dans le dossier choisi.")
            if not self.le_out.text().strip():
                errs.append("Choisissez le dossier de sortie.")
            elif os.path.normpath(self.le_out.text().strip()) == os.path.normpath(self.le_in.text().strip()):
                errs.append("Le dossier de sortie doit être DIFFÉRENT du dossier des cartes (les cartes d'origine ne sont jamais écrasées).")
            if self.le_study.text().strip() and not os.path.exists(self.le_study.text().strip()):
                errs.append("La zone d'étude indiquée n'existe pas.")
            try:
                extra = build_pair_set(self.chk_bu.isChecked(), self.le_extra.text())
            except ValueError as exc:
                errs.append(str(exc))
                extra = None
            if errs:
                self.lbl_err.setText("<span style='color:#c62828'>" + "<br>".join("• " + x for x in errs) + "</span>")
                return
            self.settings = {"maps": maps, "out": self.le_out.text().strip(), "study": self.le_study.text().strip(), "hr": self.le_hr.text().strip(), "pairs": extra,
                             "overall": self.chk_overall.isChecked(), "copy_unchanged": self.chk_copy.isChecked(), "min_ha": float(self.sp_min.value()), "builtup_any": self.chk_bu.isChecked(), "extra_text": self.le_extra.text().strip()}
            self.accept()

    class Summary(QDialog):
        def __init__(self, queue, builtup_rows, px_ha):
            super().__init__(None)
            self.setWindowTitle("Bilan des transitions improbables")
            self.resize(900, 640)
            self.queue, self.checks = queue, []
            lay = QVBoxLayout(self)
            lay.addWidget(QLabel("<b>Transitions improbables trouvées</b> : cochez celles à revoir (une fenêtre interactive s'ouvrira pour chacune, de la période la plus ancienne à la plus récente)."))
            self.table = QTableWidget(len(queue), 5)
            self.table.setHorizontalHeaderLabels(["Revoir", "Période", "Transition (ancienne → récente)", "Surface (ha)", "Pixels"])
            for i, q in enumerate(queue):
                cb = QCheckBox()
                cb.setChecked(True)
                self.checks.append(cb)
                self.table.setCellWidget(i, 0, cb)
                for j, t in enumerate((f"{q['older']} → {q['newer']}", f"{class_label(q['from'])} → {class_label(q['to'])}", f"{q['ha']:,.2f}", f"{q['px']:,}"), 1):
                    self.table.setItem(i, j, QTableWidgetItem(t))
            try:
                self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            except Exception:
                pass
            lay.addWidget(self.table, 1)
            tot = QTextEdit()
            tot.setReadOnly(True)
            tot.setMaximumHeight(150)
            lines = ["<b>Disparition du bâti (Built-up → autres classes) par période :</b>"]
            for r in builtup_rows:
                det = ", ".join(f"{CLASS_NAMES[k]} {v:,.1f} ha" for k, v in r["by_class"].items()) or "aucune"
                lines.append(f"{r['period'][0]} – {r['period'][1]} : <b>{r['total_ha']:,.1f} ha</b> ({det})")
            tot.setHtml("<br>".join(lines))
            lay.addWidget(tot)
            row = QHBoxLayout()
            b_all, b_none = QPushButton("Tout cocher"), QPushButton("Tout décocher")
            b_all.clicked.connect(lambda *_: [c.setChecked(True) for c in self.checks])
            b_none.clicked.connect(lambda *_: [c.setChecked(False) for c in self.checks])
            go, cancel = QPushButton("▶ Lancer la revue des transitions cochées"), QPushButton("Annuler")
            go.clicked.connect(self.accept)
            cancel.clicked.connect(self.reject)
            for w in (b_all, b_none):
                row.addWidget(w)
            row.addStretch(1)
            row.addWidget(go)
            row.addWidget(cancel)
            lay.addLayout(row)

        def selected(self):
            return [q for q, c in zip(self.queue, self.checks) if c.isChecked()]

    class PolyTool(QgsMapToolEmitPoint):
        def __init__(self, canvas, owner):
            super().__init__(canvas)
            self.canvas, self.owner, self.points = canvas, owner, []
            self.rb = QgsRubberBand(canvas, QgsWkbTypes.PolygonGeometry)
            self.rb.setColor(QColor(255, 235, 59, 120))
            self.rb.setWidth(2)

        def reset_tool(self):
            self.points = []
            self.rb.reset(QgsWkbTypes.PolygonGeometry)

        def canvasPressEvent(self, e):
            btn = e.button()
            pt = self.toMapCoordinates(e.pos())
            try:
                left, right = (btn.value == 1), (btn.value == 2)
            except Exception:
                left, right = (int(btn) == 1), (int(btn) == 2)
            if left:
                self.points.append(pt)
                self.rb.addPoint(pt, True)
                self.owner.lbl_info.setText(f"✏ Sommet {len(self.points)} : clic droit = terminer.")
            elif right:
                pts = list(self.points)
                self.reset_tool()
                if len(pts) >= 3:
                    self.owner.finish_polygon(pts)
                else:
                    self.owner.lbl_info.setText("⚠ Minimum 3 sommets.")

    class Review(QDialog):
        """Une fenêtre PAR transition : carte, parcelles, correction (toute la transition / parcelles choisies / polygone) ou « laisser »."""

        def __init__(self, session, index, total, tmp_dir, geo_tf, proj_wkt, hr_path=""):
            super().__init__(None)
            self.s, self.i, self.total, self.tmp, self.gt, self.wkt, self.hr_path = session, index, total, tmp_dir, geo_tf, proj_wkt, hr_path
            self.item = session.queue[index]
            self.outcome, self.polygon_mask, self.labels, self.patches, self.overlay_n = "next", None, None, [], 0
            it = self.item
            self.setWindowTitle(f"Transition improbable {index + 1}/{total} — {it['older']} → {it['newer']} : {CLASS_NAMES[it['from']]} → {CLASS_NAMES[it['to']]}")
            self.resize(1500, 900)
            root = QVBoxLayout(self)
            self.lbl_head = QLabel("")
            self.lbl_head.setWordWrap(True)
            root.addWidget(self.lbl_head)
            split = QSplitter()
            left = QWidget()
            lv = QVBoxLayout(left)
            top = QHBoxLayout()
            top.addWidget(QLabel("Fond :"))
            self.cb_bg = QComboBox()
            self.cb_bg.addItems([f"Carte LULC {it['newer']}", f"Carte LULC {it['older']}", "Image haute résolution (fichier)", "Aucun"])
            self.cb_bg.currentIndexChanged.connect(self.refresh_layers)
            top.addWidget(self.cb_bg, 1)
            for txt, slot in (("✋ Pan", self.set_pan), ("🔍+", self.set_zoom), ("➖", lambda: self.canvas.zoomOut()), ("➕", lambda: self.canvas.zoomIn()), ("🌐 Étendue", self.zoom_full)):
                b = QPushButton(txt)
                b.clicked.connect(lambda _c=False, f=slot: f())
                top.addWidget(b)
            lv.addLayout(top)
            self.canvas = QgsMapCanvas()
            self.canvas.setCanvasColor(QColor(245, 245, 245))
            lv.addWidget(self.canvas, 1)
            self.lbl_info = QLabel("Sélectionnez une parcelle dans la liste pour la repérer ; ou dessinez un polygone.")
            self.lbl_info.setWordWrap(True)
            lv.addWidget(self.lbl_info)
            split.addWidget(left)
            right = QWidget()
            rv = QVBoxLayout(right)
            self.table = QTableWidget(0, 4)
            self.table.setHorizontalHeaderLabels(["N°", "Surface (ha)", "Pixels", "Position (X ; Y)"])
            try:
                self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
                self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
                self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            except Exception:
                pass
            self.table.itemSelectionChanged.connect(self.on_select)
            rv.addWidget(QLabel("<b>Parcelles de cette transition</b> (la plus grande d'abord ; Ctrl / Maj pour en choisir plusieurs) :"))
            rv.addWidget(self.table, 2)
            sc = QGroupBox("À quoi appliquer la décision ?")
            sv = QVBoxLayout(sc)
            self.rb_all, self.rb_sel, self.rb_poly = QRadioButton("Toute la transition"), QRadioButton("Les parcelles sélectionnées"), QRadioButton("Dans le polygone dessiné")
            self.rb_all.setChecked(True)
            self.scope_group = QButtonGroup(self)
            for r in (self.rb_all, self.rb_sel, self.rb_poly):
                self.scope_group.addButton(r)
                sv.addWidget(r)
            bp = QHBoxLayout()
            self.btn_poly = QPushButton("✏ Dessiner un polygone")
            self.btn_poly.clicked.connect(self.start_polygon)
            self.btn_clear_poly = QPushButton("Effacer le polygone")
            self.btn_clear_poly.clicked.connect(self.clear_polygon)
            bp.addWidget(self.btn_poly)
            bp.addWidget(self.btn_clear_poly)
            sv.addLayout(bp)
            rv.addWidget(sc)
            cg = QGroupBox("Correction")
            cv = QVBoxLayout(cg)
            self.cb_mode = QComboBox()
            self.cb_mode.addItems([f"Année récente {it['newer']} : reprendre la classe de {it['older']} ({class_label(it['from'])})", f"Année ancienne {it['older']} : reprendre la classe de {it['newer']} ({class_label(it['to'])})",
                                   f"Année récente {it['newer']} : choisir une classe…", f"Année ancienne {it['older']} : choisir une classe…"])
            self.cb_class = QComboBox()
            for k in CLASS_NAMES:
                self.cb_class.addItem(class_label(k), k)
            self.cb_mode.currentIndexChanged.connect(self.on_mode)
            cv.addWidget(self.cb_mode)
            cv.addWidget(self.cb_class)
            rv.addWidget(cg)
            self.lbl_state = QLabel("")
            self.lbl_state.setWordWrap(True)
            rv.addWidget(self.lbl_state)
            row1 = QHBoxLayout()
            self.btn_apply_next = QPushButton("✓ Corriger puis suivante")
            self.btn_apply_next.clicked.connect(lambda *_: self.on_apply(go_next=True))
            self.btn_apply = QPushButton("Corriger (rester ici)")
            self.btn_apply.clicked.connect(lambda *_: self.on_apply(go_next=False))
            self.btn_undo = QPushButton("↶ Annuler la dernière correction")
            self.btn_undo.clicked.connect(self.on_undo)
            for b in (self.btn_apply_next, self.btn_apply, self.btn_undo):
                row1.addWidget(b)
            rv.addLayout(row1)
            row2 = QHBoxLayout()
            self.btn_keep = QPushButton("✋ Laisser telle quelle → suivante")
            self.btn_keep.clicked.connect(self.on_keep)
            self.btn_prev = QPushButton("◀ Précédente")
            self.btn_prev.clicked.connect(lambda *_: self.finish_with("prev"))
            self.btn_stop = QPushButton("■ Terminer la revue")
            self.btn_stop.clicked.connect(lambda *_: self.finish_with("stop"))
            for b in (self.btn_prev, self.btn_keep, self.btn_stop):
                row2.addWidget(b)
            rv.addLayout(row2)
            split.addWidget(right)
            split.setStretchFactor(0, 3)
            split.setStretchFactor(1, 2)
            root.addWidget(split, 1)
            self.tool_pan, self.tool_zoom, self.tool_poly = QgsMapToolPan(self.canvas), QgsMapToolZoom(self.canvas, False), PolyTool(self.canvas, self)
            self.layers_cache = {}
            self.on_mode()
            self.reload()
            self.zoom_full()

        # ---- logique ----
        def mode_and_class(self):
            mode = CORRECTION_MODES[max(0, min(self.cb_mode.currentIndex(), 3))]
            return mode, (self.cb_class.currentData() if mode.endswith("_class") else None)

        def on_mode(self, *_a):
            self.cb_class.setEnabled(self.cb_mode.currentIndex() >= 2)

        def selected_ids(self):
            return sorted({self.patches[r]["id"] for r in {i.row() for i in self.table.selectedIndexes()} if 0 <= r < len(self.patches)})

        def scope_mask(self, base):
            if self.rb_sel.isChecked():
                return mask_from_patches(self.labels, self.selected_ids()) & base
            if self.rb_poly.isChecked():
                return (self.polygon_mask & base) if self.polygon_mask is not None else np.zeros(base.shape, bool)
            return base

        def reload(self):
            """Recalcule la transition (après une correction) : parcelles, texte d'état, couches."""
            self.base, (self.labels, self.patches) = self.s.patches(self.item)
            it = self.item
            n = int(self.base.sum())
            self.lbl_head.setText(f"<b>Transition {self.i + 1} sur {self.total} — période {it['older']} → {it['newer']} : {class_label(it['from'])} → {class_label(it['to'])}</b><br>"
                                  f"Il reste <b>{n * self.s.px_ha:,.2f} ha</b> ({n:,} px) en <b>{len(self.patches)}</b> parcelle(s) (au départ {it['ha']:,.2f} ha). En {it['older']} ces pixels étaient « {CLASS_NAMES[it['from']]} », en {it['newer']} « {CLASS_NAMES[it['to']]} » : "
                                  "transition improbable. Corrigez-la, ou laissez-la si elle est réelle.")
            self.table.setRowCount(len(self.patches))
            for r, p in enumerate(self.patches):
                vals = (str(p["id"]), f"{p['ha']:,.3f}", f"{p['px']:,}", f"{p.get('x', 0):,.0f} ; {p.get('y', 0):,.0f}")
                for c, v in enumerate(vals):
                    self.table.setItem(r, c, QTableWidgetItem(v))
            done = [c for c in self.s.corrections if (c["older"], c["newer"], c["from"], c["to"]) == (it["older"], it["newer"], it["from"], it["to"])]
            self.lbl_state.setText((f"✓ {len(done)} correction(s) déjà appliquée(s) à cette transition ({sum(c['ha'] for c in done):,.2f} ha). " if done else "") + ("✋ Marquée « laissée telle quelle ». " if it["key"] in self.s.kept else ""))
            self.refresh_layers()

        def _lulc_layer(self, year):
            self.overlay_n += 1
            p = write_raster(os.path.join(self.tmp, f"_rv_{year}_{self.overlay_n}.tif"), self.s.maps[str(year)], self.gt, self.wkt)
            return paletted_layer(p, f"LULC {year}", make_classes_palette())

        def refresh_layers(self, *_a, selected_ids=None):
            """Couches : surlignage de la transition (jaune = parcelles sélectionnées / polygone, rouge = reste) au-dessus du fond choisi."""
            codes = np.zeros(self.base.shape, np.uint8)
            codes[self.base] = 2
            if selected_ids:
                codes[mask_from_patches(self.labels, selected_ids) & self.base] = 3
            if self.polygon_mask is not None:
                codes[self.polygon_mask & self.base] = 3
            self.overlay_n += 1
            p = write_raster(os.path.join(self.tmp, f"_rv_ov_{self.overlay_n}.tif"), codes, self.gt, self.wkt)
            ov = paletted_layer(p, "Transition", {2: ((255, 0, 0, 230), "Transition improbable"), 3: ((255, 235, 0, 255), "Sélection / polygone")})
            layers = [ov] if ov is not None else []
            bg = self.cb_bg.currentIndex()
            it = self.item
            if bg == 0:
                layers.append(self._lulc_layer(it["newer"]))
            elif bg == 1:
                layers.append(self._lulc_layer(it["older"]))
            elif bg == 2 and self.hr_path and os.path.exists(self.hr_path):
                hr = QgsRasterLayer(self.hr_path, "Image HR")
                if hr.isValid():
                    layers.append(hr)
            try:
                crs = QgsCoordinateReferenceSystem()
                crs.createFromWkt(self.wkt)
                self.canvas.setDestinationCrs(crs)
            except Exception:
                pass
            self.canvas.setLayers([l for l in layers if l is not None])
            self.canvas.refresh()

        def on_select(self):
            ids = self.selected_ids()
            self.refresh_layers(selected_ids=ids)
            if ids:
                ps = [p for p in self.patches if p["id"] in ids]
                self.lbl_info.setText(f"{len(ids)} parcelle(s) sélectionnée(s) : {sum(p['ha'] for p in ps):,.3f} ha.")
                r0, r1, c0, c1 = ps[0]["bbox"]
                m = 25
                x0, px, _r1, y0, _r2, py = self.gt
                xs = (x0 + (c0 - m) * px, x0 + (c1 + m) * px)
                ys = (y0 + (r0 - m) * py, y0 + (r1 + m) * py)
                self.canvas.setExtent(QgsRectangle(min(xs), min(ys), max(xs), max(ys)))
                self.canvas.refresh()

        def start_polygon(self):
            self.tool_poly.reset_tool()
            self.canvas.setMapTool(self.tool_poly)
            self.lbl_info.setText("✏ Dessinez le polygone : clic gauche = sommet, clic droit = terminer.")

        def finish_polygon(self, pts):
            try:
                self.canvas.unsetMapTool(self.tool_poly)
            except Exception:
                pass
            geom = QgsGeometry.fromPolygonXY([pts])
            if geom.isEmpty():
                return
            self.polygon_mask = polygon_to_mask(geom, self.base.shape, self.gt, self.wkt)
            self.rb_poly.setChecked(True)
            n = int((self.polygon_mask & self.base).sum())
            self.lbl_info.setText(f"Polygone : {n:,} pixel(s) de la transition ({n * self.s.px_ha:,.3f} ha).")
            self.refresh_layers()

        def clear_polygon(self):
            self.polygon_mask = None
            self.rb_all.setChecked(True)
            self.refresh_layers()

        def on_apply(self, go_next=True):
            mode, new_class = self.mode_and_class()
            mask = self.scope_mask(self.base)
            if not mask.any():
                QMessageBox.warning(self, "Correction", "Rien à corriger : la portée choisie ne contient aucun pixel de cette transition (sélectionnez des parcelles ou dessinez un polygone).")
                return
            rec = self.s.apply(self.item, mask, mode, new_class)
            if rec is None:
                QMessageBox.information(self, "Correction", "Ces pixels ne sont plus dans la transition.")
                self.reload()
                return
            self.lbl_info.setText(f"✓ {rec['px']:,} pixels = {rec['ha']:,.3f} ha corrigés : {rec['text']}")
            self.polygon_mask = None
            self.rb_all.setChecked(True)
            self.reload()
            if go_next:
                self.finish_with("next")

        def on_undo(self):
            rec = self.s.undo()
            self.lbl_info.setText("Aucune correction à annuler." if rec is None else f"↶ Annulée : {rec['text']} ({rec['px']:,} px)")
            self.reload()

        def on_keep(self):
            self.s.keep(self.item)
            self.finish_with("next")

        def finish_with(self, outcome):
            self.outcome = outcome
            self.accept()

        def closeEvent(self, event):
            self.outcome = "stop"
            try:
                super().closeEvent(event)
            except Exception:
                pass

        def set_pan(self):
            self.canvas.setMapTool(self.tool_pan)

        def set_zoom(self):
            self.canvas.setMapTool(self.tool_zoom)

        def zoom_full(self):
            rows, cols = self.base.shape
            x0, px, _r1, y0, _r2, py = self.gt
            xs, ys = (x0, x0 + cols * px), (y0, y0 + rows * py)
            self.canvas.setExtent(QgsRectangle(min(xs), min(ys), max(xs), max(ys)))
            self.canvas.refresh()

    return Setup, Summary, Review


def detect_area_tag(paths):
    """Étiquette de zone lue dans les noms LULC_<ZONE>_<année>.tif des cartes d'entrée (sinon la valeur de configuration)."""
    for p in paths:
        m = re.match(r"^LULC_(.+)_(?:19|20)\d{2}\.tif$", os.path.basename(p))
        if m:
            return m.group(1)
    return AREA_TAG


def _main():
    global AREA_TAG
    _t_start = time.time()
    from qgis.PyQt.QtWidgets import QMessageBox
    Setup, Summary, Review = build_dialogs()
    dlg = Setup()
    if not present(dlg, maximize=False) or not dlg.settings:
        return _stop("Annulé à la fenêtre des paramètres : aucun fichier n'a été produit.")
    cfg = dlg.settings
    AREA_TAG = detect_area_tag(cfg["maps"].values())
    years = list(cfg["maps"])
    maps, gt, wkt = {}, None, None
    for y in years:
        arr, g, w = read_map(cfg["maps"][y])
        if gt is None:
            gt, wkt, shape = g, w, arr.shape
        elif arr.shape != shape:
            raise RuntimeError(f"La carte {y} n'a pas la même taille que {years[0]} ({arr.shape} contre {shape}) : toutes les cartes doivent partager la même grille.")
        maps[y] = arr
    px_ha = abs(gt[1] * gt[5] - gt[2] * gt[4]) / 10000.0
    domain = admin_mask_from_shp(cfg["study"], shape[0], shape[1], gt, wkt) if cfg["study"] else None
    queue = build_queue(maps, years, px_ha, cfg["pairs"], cfg["overall"], domain, cfg["min_ha"])
    bu_before = builtup_loss_table(maps, years, px_ha, cfg["overall"], domain)
    print("=" * 70)
    print("Bilan « Built-up → autres classes » (ha) :")
    for r in bu_before:
        print(f"  {r['period'][0]} – {r['period'][1]} : {r['total_ha']:,.1f} ha  " + ", ".join(f"{CLASS_NAMES[k]} {v:,.1f}" for k, v in r["by_class"].items()))
    print(f"Transitions improbables à revoir : {len(queue)}")
    if not queue:
        return _stop("Aucune transition improbable (au-dessus de la surface minimale) : rien à revoir, aucun fichier n'a été produit.")
    sm = Summary(queue, bu_before, px_ha)
    if not present(sm, maximize=False):
        return _stop("Annulé au bilan : aucun fichier n'a été produit.")
    chosen = sm.selected()
    if not chosen:
        return _stop("Aucune transition cochée : rien à revoir.")
    session = ReviewSession(maps, years, px_ha, cfg["pairs"], chosen, domain, gt)
    tmp = os.path.join(cfg["out"], "_temp")
    os.makedirs(tmp, exist_ok=True)
    i = session.first_index()
    while i is not None and 0 <= i < len(chosen):
        rv = Review(session, i, len(chosen), tmp, gt, wkt, cfg["hr"])
        present(rv)
        if rv.outcome == "stop":
            break
        step = -1 if rv.outcome == "prev" else 1
        nxt = session.next_index(i, step)
        if nxt is None and step == 1:
            break
        i = i if nxt is None else nxt
    # ---- sorties
    out = cfg["out"]
    os.makedirs(os.path.join(out, "LULC"), exist_ok=True)
    os.makedirs(os.path.join(out, "Corrections"), exist_ok=True)
    changed = session.changed_years()
    for y in years:
        dst = os.path.join(out, "LULC", f"LULC_{AREA_TAG}_{y}.tif")
        if y in changed:
            write_raster(dst, session.maps[y], gt, wkt)
            diff = (session.maps[y] != session.original[y]).astype(np.uint8)
            write_raster(os.path.join(out, "Corrections", f"Correction_Mask_{y}.tif"), diff, gt, wkt)
        elif cfg["copy_unchanged"]:
            shutil.copy2(cfg["maps"][y], dst)
    ba = session.before_after(cfg["overall"])
    rows_c = corrections_csv_rows(session.corrections)
    with open(os.path.join(out, "Corrections", "Corrections_Log.csv"), "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f, delimiter=";").writerows(rows_c)
    with open(os.path.join(out, "Corrections", "Transitions_Avant_Apres.csv"), "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f, delimiter=";").writerows(before_after_csv_rows(ba))
    bu_after = builtup_loss_table(session.maps, years, px_ha, cfg["overall"], domain)
    params = {"Dossier des cartes": os.path.dirname(next(iter(cfg["maps"].values()))), "Années": ", ".join(years), "Surface minimale (ha)": cfg["min_ha"], "Période globale": "oui" if cfg["overall"] else "non",
              "Toute disparition du bâti": "oui" if cfg["builtup_any"] else "non", "Transitions supplémentaires": cfg["extra_text"] or "—", "Zone d'étude": cfg["study"] or "(toute la grille)"}
    with open(os.path.join(out, "Corrections", "Rapport_Corrections.html"), "w", encoding="utf-8") as f:
        f.write(build_report_html(years, ba, bu_before, bu_after, session.corrections, session.kept, chosen, params))
    with open(os.path.join(out, "Corrections", "Info.json"), "w", encoding="utf-8") as f:
        json.dump({"params": params, "years_modified": changed, "n_corrections": len(session.corrections), "n_kept": len(session.kept), "n_reviewed": len(chosen)}, f, indent=2, ensure_ascii=False)
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        review_stage_report(out, session, chosen, ba, bu_before, bu_after, years, px_ha, {"Minimum area (ha)": cfg["min_ha"], "Overall period": cfg["overall"], "Any built-up loss is improbable": cfg["builtup_any"], "Extra transitions": cfg["extra_text"] or "-"}, _t_start, AREA_NAME, REPORT_LANG)
    except Exception as _exc:
        print("[Rapport HTML d'étape] échec (le traitement lui-même est terminé) : " + str(_exc))
    QMessageBox.information(None, "Revue terminée", f"Corrections : {len(session.corrections)} ({', '.join(changed) or 'aucune année modifiée'})\nLaissées telles quelles : {len(session.kept)}\n\nCartes corrigées, journal et rapport dans :\n{out}")


# ====================== MAIN ======================
main()
