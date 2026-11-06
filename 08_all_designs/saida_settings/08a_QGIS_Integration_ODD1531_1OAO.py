# -*- coding: utf-8 -*-
# SDG 15.3.1 REFERENCE PIPELINE — STAGE 07 / 08 : SDG 15.3.1 integration (one-out, all-out) — QGIS
"""
UNCCD_SDG1531_INTEGRATION_QGIS.py   —   INDICATEUR ODD 15.3.1 : INTÉGRATION FINALE (one-out, all-out)   |   <AREA_NAME>   |   QGIS

Combine les trois sous-indicateurs du guide de bonnes pratiques de la CNULCD (GPG, ODD 15.3.1) :
  1. COUVERTURE TERRESTRE : transitions entre deux cartes LULC classées D (dégradation) / S (stable) / I (amélioration) par une matrice
     NATIONALE (CSV, deux variantes : « strict » et « robust » = transitions entre classes sensibles à l'humidité jugées stables).
  2. PRODUCTIVITÉ : LPD MODIS 3 classes de MODIS_LPD_COMPLETE_QGIS.py, variante CORRIGÉE DE LA PLUIE (le GPG exige une calibration sur
     l'humidité) et variante non corrigée (borne haute).
  3. CARBONE ORGANIQUE DU SOL : SOC_Class_<début>_<fin>.tif de UNCCD_SOC_FINAL_QGIS.py (estimation à partir des changements de LULC).

Règle 1OAO : dégradé si AU MOINS un sous-indicateur évalué est dégradé ; amélioré si au moins un l'est et aucun n'est dégradé ; stable sinon.
Un gain n'en compense pas une perte. Sorties : indicateur, nombre de sous-indicateurs évalués, classes de soutien (GPG, tableau 4),
anomalies explicables (productivité dégradée seulement avant correction de la pluie), statut de référence t0 facultatif (GPG, tableau 3),
statistiques par scénario (8 combinaisons : matrice x productivité x avec/sans SOC), par classe d'occupation du sol, rapport.

Grille de calcul : LULC 30 m ; LPD (250 m) et SOC (~230 m) rééchantillonnés au plus proche voisin. Surface terrestre (dénominateur) : pixels
LULC valides à la date finale, eau exclue (option).

RIEN N'EST INVENTÉ : une transition absente de la matrice est « non évaluable » ; un D ou un I exige une justification ; sans matrice, le
script écrit un modèle vide et s'arrête.
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
TWO_WINDOW_MODE = True       # True : DEUX fenêtres successives (période de BASE puis période de SUIVI, calculées dans une seule exécution) ; False : ancien mode à boîtes de dialogue (une seule période)
AUTO_RUN = True              # False : charger les fonctions sans lancer le traitement (tests)
# =================================================================================================================================

PIPELINE_BUILD = "2026.10-7a49f4aecc81"
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
def integration_stage_report(out_root, dirs, report_lines, t0, params, inputs, area_name, y0, y1, lang="en", log=print):
    """Rapport HTML de l'étape 07 (intégration 1OAO) : sous-indicateurs, grille de scénarios, classes de soutien, transitions de couverture, cartes."""
    en = lang == "en"
    T = lambda a, b: a if en else b
    rd = lambda n: sr_read_csv(os.path.join(dirs["stats"], n))
    sub, grid, sup, obs, prim = rd("SubIndicator_Areas.csv"), rd("Scenario_Grid.csv"), rd("SupportClass_Areas.csv"), sr_read_csv(next((q for q in (os.path.join(dirs.get("qa", ""), "LC_Transitions_Observed.csv"), os.path.join(dirs["stats"], "LC_Transitions_Observed.csv")) if os.path.exists(q)), os.path.join(dirs["stats"], "LC_Transitions_Observed.csv"))), rd("Primary_Area_Statistics.csv")
    byl = sorted(f for f in os.listdir(dirs["stats"]) if f.startswith("Primary_by_LULC_")) if os.path.isdir(dirs["stats"]) else []
    summary, checks = [], []
    for r in sr_dict_rows(prim):
        summary.append(f"{r.get('category')} : {sr_num(r.get('area_ha')):,.0f} ha")
    sg = sr_dict_rows(grid)
    dl = [sr_num(r.get("degraded_%_of_land")) for r in sg]
    dl = [x for x in dl if x == x]
    if dl:
        summary.append(T(f"Degraded land across the {len(dl)} scenarios: {min(dl):.2f} % – {max(dl):.2f} % of the land area", f"Terres dégradées dans les {len(dl)} scénarios : {min(dl):.2f} % – {max(dl):.2f} % de la surface terrestre"))
        checks.append((T("Dependence on analytical choices (scenario grid)", "Dépendance aux choix analytiques (grille de scénarios)"), "PASS" if max(dl) - min(dl) <= 10 else "WARN", T(f"the degraded share ranges over {max(dl) - min(dl):.1f} points between scenarios; the main scenario must be justified and the range reported", f"la part dégradée varie de {max(dl) - min(dl):.1f} points selon les scénarios ; justifier le scénario principal et rapporter la fourchette")))
    else:
        checks.append((T("Scenario grid", "Grille de scénarios"), "FAIL", "Scenario_Grid.csv missing"))
    si = sr_dict_rows(sub)
    na = [(r.get("sub_indicator"), sr_num(r.get("not_assessed_ha"), 0)) for r in si]
    _pr = sr_dict_rows(prim)
    land = (next((sr_num(r.get("area_ha"), 0) for r in _pr if str(r.get("category", "")).strip().lower() == "total"), None)
            or sum(sr_num(r.get("area_ha"), 0) for r in _pr if str(r.get("category", "")).strip().lower() != "total") or float("nan"))      # la ligne « total » EST la surface : l'ajouter aux catégories la compterait deux fois
    for nm, v in na:
        pct = 100 * v / land if land == land and land else float("nan")
        checks.append((T(f"Sub-indicator assessed: {nm}", f"Sous-indicateur évalué : {nm}"), "PASS" if pct == pct and pct <= 20 else "WARN", T(f"{v:,.0f} ha not assessed ({pct:.1f} % of the land)", f"{v:,.0f} ha non évalués ({pct:.1f} % des terres)")))
    sp = {str(r.get("support_class")): sr_num(r.get("area_ha"), 0) for r in sr_dict_rows(sup)}
    deg3 = sum(v for k, v in sp.items() if k in {"1", "2", "3", "4", "5", "6", "7"})
    single = sum(v for k, v in sp.items() if k in {"4", "6", "7"})
    deg_all = next((sr_num(r.get("area_ha"), 0) for r in _pr if str(r.get("category", "")).strip().lower() == "degraded"), float("nan"))
    if deg3:
        share = 100 * single / deg3
        cov = (100 * deg3 / deg_all) if (deg_all == deg_all and deg_all) else float("nan")
        checks.append((T("Degradation flagged by a single sub-indicator (false-positive risk of 1OAO)", "Dégradation signalée par un seul sous-indicateur (risque de faux positifs du 1OAO)"), "PASS" if share <= 50 else "WARN", T(f"{share:.0f} % of the degraded pixels assessed on all 3 sub-indicators ({deg3:,.0f} ha" + (f", {cov:.0f} % of the degraded area" if cov == cov else "") + f") are flagged by ONE sub-indicator only; {deg3 - single:,.0f} ha are flagged by two or three: the sub-indicators rarely agree, so the degraded area is potential degradation to verify",
                          f"{share:.0f} % des pixels dégradés évalués sur les 3 sous-indicateurs ({deg3:,.0f} ha" + (f", {cov:.0f} % de la surface dégradée" if cov == cov else "") + f") ne sont signalés que par UN sous-indicateur ; {deg3 - single:,.0f} ha le sont par deux ou trois : les sous-indicateurs concordent rarement, la surface dégradée est une dégradation potentielle à vérifier")))
    _diag = [str(d) for d in globals().get("DIAGNOSTIC_YEARS", [])]
    checks.append((T("Baseline year is not a diagnostic (drought) year", "L'année de base n'est pas une année diagnostique (sécheresse)"), "WARN" if str(y0) in _diag else "PASS",
                   T(f"baseline {y0} is declared a diagnostic year: compare with another baseline (stage 08) before interpreting any improvement", f"la base {y0} est déclarée année diagnostique : comparer avec une autre base (étape 08) avant d'interpréter une amélioration") if str(y0) in _diag else T(f"baseline {y0}; diagnostic years: {', '.join(_diag) or 'none'}", f"base {y0} ; années diagnostiques : {', '.join(_diag) or 'aucune'}")))
    _miss = lambda v: str(v).strip().upper() in ("", "NA", "N/A", "NONE") or str(v).strip().upper().startswith("NON")      # le script écrit « NON ÉVALUABLE » pour une transition absente de la matrice
    na_tr = [r for r in sr_dict_rows(obs) if _miss(r.get("effect_strict", "x")) or _miss(r.get("effect_robust", "x"))]
    ta = sum(sr_num(r.get("area_ha"), 0) for r in na_tr)
    checks.append((T("Land-cover transitions missing from the national matrix", "Transitions de couverture absentes de la matrice nationale"), "PASS" if not na_tr else "WARN", T("every observed transition is classified D/S/I", "toute transition observée est classée D/S/I") if not na_tr else T(f"{len(na_tr)} transitions ({ta:,.0f} ha) are 'not evaluable'", f"{len(na_tr)} transitions ({ta:,.0f} ha) « non évaluables »")))
    maps = []
    for fn, title, cl in (("SDG1531_1OAO_primary.tif", T("SDG 15.3.1 — 1OAO (main scenario)", "ODD 15.3.1 — 1OAO (scénario principal)"), {-1: ("#d73027", T("Degraded", "Dégradé")), 0: ("#fee08b", T("Stable", "Stable")), 1: ("#1a9850", T("Improved", "Amélioré"))}),
                          ("SDG1531_SupportClass_primary.tif", T("Support classes (1 = D,D,D … 8 = N,N,N)", "Classes de soutien (1 = O,O,O … 8 = N,N,N)"), {1: ("#7f0000", "1"), 2: ("#b30000", "2"), 3: ("#d7301f", "3"), 4: ("#ef6548", "4"), 5: ("#fc8d59", "5"), 6: ("#fdbb84", "6"), 7: ("#fdd49e", "7"), 8: ("#e0e0e0", "8")})):
        p = os.path.join(dirs["ind"], fn)
        png = sr_quicklook(p, os.path.join(out_root, "_temp", fn + ".png"), cl, title=title)
        if png:
            maps.append((title, png))
    ia_path = os.path.join(dirs["stats"], "Improved_by_Transition_Group.csv")
    ia_rows = sr_dict_rows(sr_read_csv(ia_path)) if os.path.exists(ia_path) else []
    GL = {"natural_stable": T("Natural → natural (no conversion)", "Naturel → naturel (sans conversion)"), "agri_stable": T("Agricultural → agricultural (greening may come from inputs)", "Agricole → agricole (verdissement possible par intrants)"),
          "natural_to_agri": T("Natural → agricultural (conversion: FALSE GREENING)", "Naturel → agricole (conversion : FAUX VERDISSEMENT)"), "agri_to_natural": T("Agricultural → natural (abandonment)", "Agricole → naturel (abandon)"), "other": T("Other (built-up, water, sebkha)", "Autre (bâti, eau, sebkha)")}
    ia_tab = []
    if ia_rows:
        _land_tot = sum(sr_num(r["area_ha"]) for r in ia_rows)
        _imp_tot = sum(sr_num(r["indicator_improved_ha"]) for r in ia_rows)
        ia_tab = [[T("Group (land cover at the start → at the end)", "Groupe (couverture au début → à la fin)"), T("Area (ha)", "Surface (ha)"), T("% of the land", "% des terres"), T("Productivity improved (ha)", "Productivité améliorée (ha)"), T("% of the group", "% du groupe"),
                   T("Indicator improved (ha)", "Indicateur amélioré (ha)"), T("% of all improved", "% de l'amélioration totale"), T("Improvement share ÷ land share", "Part de l'amélioration ÷ part des terres"), T("Indicator degraded (ha)", "Indicateur dégradé (ha)"), T("Degraded % of the group", "Dégradé % du groupe")]]
        for r in ia_rows:
            ar, im, dg = sr_num(r["area_ha"]), sr_num(r["indicator_improved_ha"]), sr_num(r["indicator_degraded_ha"])
            ia_tab.append([GL.get(r["group"], r["group"]), f"{ar:,.0f}", f"{100 * ar / _land_tot:.1f}" if _land_tot else "", f"{sr_num(r['productivity_improved_ha']):,.0f}", f"{sr_num(r['productivity_improved_%_of_group']):.1f}", f"{im:,.0f}",
                           f"{sr_num(r['indicator_improved_%_of_all_improved']):.1f}", (f"{(im / _imp_tot) / (ar / _land_tot):.2f}" if (_imp_tot and ar and _land_tot) else ""), f"{dg:,.0f}", f"{100 * dg / ar:.1f}" if ar else ""])
        by = {r["group"]: r for r in ia_rows}
        g = lambda k, f: sr_num(by.get(k, {}).get(f), 0)
        imp_tot = _imp_tot
        sus, sus_area = g("agri_stable", "indicator_improved_ha") + g("natural_to_agri", "indicator_improved_ha"), g("agri_stable", "area_ha") + g("natural_to_agri", "area_ha")
        nat = g("natural_stable", "indicator_improved_ha") + g("agri_to_natural", "indicator_improved_ha")
        sh = (100 * sus / imp_tot) if imp_tot else float("nan")
        land_sh = (100 * sus_area / _land_tot) if _land_tot else float("nan")
        ratio = (sh / land_sh) if (sh == sh and land_sh == land_sh and land_sh) else float("nan")
        conv_ha, conv_deg = g("natural_to_agri", "area_ha"), g("natural_to_agri", "indicator_degraded_ha")
        if ratio == ratio:
            over = ratio > 1.25
            checks.append((T("Improvement concentrated on agricultural or converted land (false greening)", "Amélioration concentrée sur des terres agricoles ou converties (faux verdissement)"), "WARN" if over else "PASS",
                           T(f"agricultural land and land converted from natural hold {sh:.0f} % of the improved area ({sus:,.0f} of {imp_tot:,.0f} ha) and {land_sh:.0f} % of the land (ratio {ratio:.2f}): ", f"les terres agricoles et converties de terres naturelles portent {sh:.0f} % de la surface améliorée ({sus:,.0f} sur {imp_tot:,.0f} ha) et {land_sh:.0f} % des terres (rapport {ratio:.2f}) : ")
                           + (T("improvement is OVER-represented there: inputs or conversion may inflate it", "l'amélioration y est SUR-représentée : intrants ou conversion peuvent la gonfler") if over else T("no over-representation, the greening is not specific to agricultural land", "pas de sur-représentation, le verdissement n'est pas propre aux terres agricoles"))
                           + T(f"; {nat:,.0f} ha ({100 * nat / imp_tot:.0f} %) are on land that stayed natural or was abandoned", f" ; {nat:,.0f} ha ({100 * nat / imp_tot:.0f} %) sont sur des terres restées naturelles ou abandonnées")))
        if conv_ha:
            conv_imp = g("natural_to_agri", "indicator_improved_ha")
            checks.append((T("Land converted from natural to agricultural: how the indicator treats it", "Terres converties de naturelles à agricoles : traitement par l'indicateur"), "INFO" if conv_deg / conv_ha >= 0.5 else "WARN",
                           T(f"{conv_ha:,.0f} ha converted: {100 * conv_deg / conv_ha:.0f} % flagged degraded, {100 * conv_imp / conv_ha:.0f} % flagged improved. If the conversion is degradation (national decision), the land-cover matrix must say so; treating every such conversion as degraded would give about {(sr_num(next((r['area_ha'] for r in sr_dict_rows(prim) if str(r.get('category')).strip() == 'degraded'), 0)) - conv_deg + conv_ha):,.0f} ha degraded",
                             f"{conv_ha:,.0f} ha converties : {100 * conv_deg / conv_ha:.0f} % signalées dégradées, {100 * conv_imp / conv_ha:.0f} % signalées améliorées. Si la conversion est une dégradation (décision nationale), la matrice de couverture doit le dire ; traiter toute conversion de ce type comme dégradée donnerait environ {(sr_num(next((r['area_ha'] for r in sr_dict_rows(prim) if str(r.get('category')).strip() == 'degraded'), 0)) - conv_deg + conv_ha):,.0f} ha dégradés")))
        if sh == sh:
            summary.append(T(f"Improved area on land that stayed natural or was abandoned: {nat:,.0f} ha ({100 * nat / imp_tot:.0f} % of the improved area); on agricultural or converted land: {sus:,.0f} ha ({sh:.0f} %, against {land_sh:.0f} % of the land)", f"Surface améliorée sur des terres restées naturelles ou abandonnées : {nat:,.0f} ha ({100 * nat / imp_tot:.0f} % de la surface améliorée) ; sur des terres agricoles ou converties : {sus:,.0f} ha ({sh:.0f} %, pour {land_sh:.0f} % des terres)"))
    sections = [
        {"id": "ind", "title": T("Indicator and sub-indicators", "Indicateur et sous-indicateurs"), "intro": T(f"One-out, all-out (1OAO): a pixel is degraded if at least one assessed sub-indicator is degraded. Period {y0}–{y1}.", f"Un-sorti-tous-sortis (1OAO) : un pixel est dégradé si au moins un sous-indicateur évalué l'est. Période {y0}–{y1}."), "tables": [(T("Primary statistics", "Statistiques principales"), prim), (T("Sub-indicator areas", "Surfaces par sous-indicateur"), sub)]},
        {"id": "grid", "title": T("Scenario grid", "Grille de scénarios"), "intro": T("Land-cover matrix (strict / robust / persistent) × productivity (rain-adjusted / not) × SOC (with / without).", "Matrice de couverture (stricte / robuste / persistante) × productivité (corrigée / non) × SOC (avec / sans)."), "tables": [(T("Scenarios", "Scénarios"), grid)]},
        {"id": "sup", "title": T("Support classes (GPG table 4)", "Classes de soutien (GPG tableau 4)"), "tables": [(T("Combinations of sub-indicators", "Combinaisons de sous-indicateurs"), sup)]},
        {"id": "lc", "title": T("Land-cover transitions and their classification", "Transitions de couverture et leur classification"), "intro": T("Degradation by transition is a NATIONAL DECISION: the matrix must be justified transition by transition.", "La dégradation par transition est une DÉCISION NATIONALE : la matrice doit être justifiée transition par transition."), "tables": [(T("Observed transitions", "Transitions observées"), obs)] + ([(T("By land cover", "Par occupation du sol") + f" ({byl[-1][16:-4]})", rd(byl[-1]))] if byl else [])},
        {"id": "fg", "title": T("Where is the improvement? (false-greening check)", "Où se trouve l'amélioration ? (contrôle du faux verdissement)"), "intro": T("Greening on agricultural land can come from intensified inputs (fertiliser, irrigation, improved varieties, state support) and, where natural land became agricultural, from the conversion itself. Neither is land recovery. The 1OAO rule already counts a degraded land cover as degradation, but a productivity gain on such land is still counted as improvement unless the land-cover matrix marks the conversion as degraded.", "Le verdissement sur terres agricoles peut venir de l'intensification (engrais, irrigation, variétés améliorées, soutien de l'État) et, là où des terres naturelles sont devenues agricoles, de la conversion elle-même. Ni l'un ni l'autre n'est une restauration. La règle 1OAO compte déjà une couverture dégradée comme dégradation, mais un gain de productivité sur ces terres reste compté comme amélioration si la matrice de couverture ne marque pas la conversion comme dégradée."), "tables": [(T("Improvement by what happened to the land cover", "Amélioration selon ce qui est arrivé à la couverture"), ia_tab)] if ia_tab else []},
        {"id": "maps", "title": T("Maps", "Cartes"), "images": maps},
        {"id": "log", "title": T("Processing log", "Journal du traitement"), "pre": "\n".join(report_lines[-150:])}]
    per_path = os.path.join(dirs["stats"], "LC_Persistence_by_Transition.csv")
    per_rows = sr_dict_rows(sr_read_csv(per_path)) if os.path.exists(per_path) else []
    if per_rows:
        nat_, agr_ = tuple(globals().get("NATURAL_CLASSES", (4, 7, 8))), tuple(globals().get("AGRI_CLASSES", (5, 6)))
        per_tab = [[T("From", "De"), T("To", "Vers"), T("Area (ha)", "Surface (ha)"), T("Persistent (ha)", "Persistante (ha)"), T("Persistent %", "Persistante %"), T("Strict matrix", "Matrice stricte")]]
        for r in sorted(per_rows, key=lambda r: -sr_num(r["area_ha"]))[:14]:
            per_tab.append([r["from_class"], r["to_class"], f"{sr_num(r['area_ha']):,.0f}", f"{sr_num(r['persistent_ha']):,.0f}", f"{sr_num(r['persistent_%']):.0f}", r["effect_strict"]])
        for sec in sections:
            if sec["id"] == "lc":
                sec["tables"] = list(sec["tables"]) + [(T("Persistence of the land-cover conversions (a change counts only if it is single and holds at 2 or more dates; diagnostic years ignored)", "Persistance des conversions de couverture (un changement ne compte que s'il est unique et se maintient à 2 dates ou plus ; années diagnostiques ignorées)"), per_tab)]
        na_ = [r for r in per_rows if int(float(r["from"])) in nat_ and int(float(r["to"])) in agr_]
        if na_:
            tot_, per_ = sum(sr_num(r["area_ha"]) for r in na_), sum(sr_num(r["persistent_ha"]) for r in na_)
            checks.append((T("Conversions from natural to agricultural land that persist", "Conversions de terres naturelles en terres agricoles qui persistent"), "INFO",
                           T(f"{per_:,.0f} of {tot_:,.0f} ha ({100 * per_ / tot_:.0f} %) are single changes that hold at two or more dates; the rest are round trips (rotation, moisture) or changes seen only at the last date and are not counted as land-cover change by the persistent variant",
                             f"{per_:,.0f} sur {tot_:,.0f} ha ({100 * per_ / tot_:.0f} %) sont des changements uniques qui se maintiennent à deux dates ou plus ; le reste sont des allers-retours (rotation, humidité) ou des changements vus à la seule dernière date, non comptés par la variante persistante")))
    cov_path = os.path.join(dirs["stats"], "Coverage_Table.csv")
    cov_rows_ = sr_dict_rows(sr_read_csv(cov_path)) if os.path.exists(cov_path) else []
    if cov_rows_:
        CN = {"land": T("Land (denominator)", "Terres (dénominateur)"), "assessed_land_cover": T("Assessed by land cover", "Évaluées par la couverture"), "assessed_productivity": T("Assessed by productivity", "Évaluées par la productivité"), "assessed_soc": T("Assessed by SOC", "Évaluées par le SOC"),
              "final_assessed_at_least_one": T("Assessed in the result (at least one sub-indicator)", "Évaluées dans le résultat (au moins un sous-indicateur)"), "sum_of_statuses_degraded_stable_improved_not_assessed": T("Sum of degraded + stable + improved + not assessed", "Somme dégradé + stable + amélioré + non évalué")}
        cov_tab = [[T("Item", "Élément"), T("Area (ha)", "Surface (ha)"), T("% of the land", "% des terres")]]
        for r in cov_rows_:
            nm = CN.get(r["item"]) or (T(f"Pixels assessed by {r['item'].split('_')[2]} sub-indicators", f"Pixels évalués par {r['item'].split('_')[2]} sous-indicateurs") if r["item"].startswith("assessed_by_") else r["item"])
            cov_tab.append([nm, f"{sr_num(r['area_ha']):,.0f}", f"{sr_num(r['percent_of_land']):.2f}"])
        for sec in sections:
            if sec["id"] == "lc":
                break
        sections.insert(1, {"id": "cov", "title": T("Valid area of each sub-indicator and of the result (NoData handling)", "Surface valide de chaque sous-indicateur et du résultat (traitement des NoData)"),
                            "intro": T("A pixel without data for one sub-indicator is judged by the others and is never counted as stable by default; it is 'not assessed' only when no sub-indicator can be assessed. This is why the result can have no 'not assessed' area while a sub-indicator has some.", "Un pixel sans donnée pour un sous-indicateur est jugé par les autres et n'est jamais compté comme stable par défaut ; il est « non évalué » seulement si aucun sous-indicateur n'est évaluable. C'est pourquoi le résultat peut n'avoir aucune surface « non évaluée » alors qu'un sous-indicateur en a."),
                            "tables": [("", cov_tab)]})
        tot_c = next((sr_num(r["area_ha"]) for r in cov_rows_ if r["item"] == "land"), float("nan"))
        sum_c = next((sr_num(r["area_ha"]) for r in cov_rows_ if r["item"].startswith("sum_of_statuses")), float("nan"))
        if tot_c == tot_c and sum_c == sum_c:
            checks.append((T("The four statuses add up to the land area", "Les quatre statuts s'additionnent à la surface terrestre"), "PASS" if abs(tot_c - sum_c) <= max(1.0, 1e-4 * tot_c) else "FAIL", f"{sum_c:,.1f} ha / {tot_c:,.1f} ha"))
        one = next((sr_num(r["area_ha"]) for r in cov_rows_ if r["item"] == "assessed_by_1_subindicators"), 0.0)
        if tot_c == tot_c and tot_c:
            checks.append((T("Land judged by a single sub-indicator", "Terres jugées par un seul sous-indicateur"), "INFO" if one / tot_c <= 0.25 else "WARN", T(f"{one:,.0f} ha ({100 * one / tot_c:.1f} % of the land) have data for one sub-indicator only: their status rests on it alone", f"{one:,.0f} ha ({100 * one / tot_c:.1f} % des terres) n'ont de donnée que pour un sous-indicateur : leur statut ne repose que sur lui")))
    ru_path = os.path.join(dirs["qa"], "LC_Matrix_Rules_Used.csv")
    ru_rows = sr_dict_rows(sr_read_csv(ru_path)) if os.path.exists(ru_path) else []
    if ru_rows:
        ru_tab = [[T("From", "De"), T("To", "Vers"), T("Strict", "Stricte"), T("Robust", "Robuste"), T("Confidence", "Confiance"), T("Observed (ha)", "Observée (ha)"), T("Source", "Source"), T("Rationale", "Justification")]]
        for r in sorted(ru_rows, key=lambda r: -sr_num(r["observed_area_ha"], 0)):
            ru_tab.append([r["from_class"], r["to_class"], r["effect_strict"], r["effect_robust"], r["confidence"], f"{sr_num(r['observed_area_ha'], 0):,.0f}", r["source"], r["rationale"]])
        for sec in sections:
            if sec["id"] == "lc":
                sec["tables"] = list(sec["tables"]) + [(T("Rules of the national matrix that were applied (D or I), with their confidence and source", "Règles de la matrice nationale appliquées (D ou I), avec leur confiance et leur source"), ru_tab)]
        missing = [r for r in ru_rows if r["confidence"] in ("", "not given")]
        low_ha = sum(sr_num(r["observed_area_ha"], 0) for r in ru_rows if r["effect_strict"] == "D" and r["confidence"] == "low")
        deg_ha = sum(sr_num(r["observed_area_ha"], 0) for r in ru_rows if r["effect_strict"] == "D")
        checks.append((T("Every D or I rule of the matrix has a confidence level", "Chaque règle D ou I de la matrice a un niveau de confiance"), "PASS" if not missing else "WARN",
                       T("all rules have a confidence level", "toutes les règles ont un niveau de confiance") if not missing else T(f"{len(missing)} rule(s) without confidence level: fill the 'confidence' and 'source' columns of the matrix", f"{len(missing)} règle(s) sans niveau de confiance : renseigner les colonnes « confidence » et « source » de la matrice")))
        if deg_ha:
            checks.append((T("Strict degradation resting on low-confidence rules", "Dégradation stricte reposant sur des règles de faible confiance"), "INFO" if low_ha / deg_ha <= 0.5 else "WARN", T(f"{low_ha:,.0f} of {deg_ha:,.0f} ha ({100 * low_ha / deg_ha:.0f} %)", f"{low_ha:,.0f} sur {deg_ha:,.0f} ha ({100 * low_ha / deg_ha:.0f} %)")))
    L = [T("The persistent land-cover variant applies the strict matrix only to conversions that are single and hold at two or more dates; a conversion seen only at the last date cannot be confirmed and counts as stable, and a path through a third class (e.g. rangeland → bare land → cropland) is not persistent. Class 'agriculture' and 'fallow' form one group.", "La variante persistante de couverture applique la matrice stricte aux seules conversions uniques et maintenues à deux dates ou plus ; une conversion vue à la seule dernière date ne peut pas être confirmée et compte pour stable, et un passage par une troisième classe (ex. parcours → sol nu → culture) n'est pas persistant. Les classes « agriculture » et « jachère » forment un seul groupe."),
         T("FALSE GREENING: on agricultural land a productivity increase can reflect intensified inputs (e.g. state support after 2010) or the conversion of natural rangeland to cropland; it is not land restoration. Report the improvement by group (table 'Where is the improvement?') and support the claim with yield statistics.", "FAUX VERDISSEMENT : sur les terres agricoles une hausse de productivité peut refléter l'intensification des intrants (ex. soutien de l'État après 2010) ou la conversion de parcours naturels en cultures ; ce n'est pas une restauration. Rapporter l'amélioration par groupe (tableau « Où se trouve l'amélioration ? ») et appuyer l'affirmation par des statistiques de rendement."),
         T("1OAO is very conservative: if each sub-indicator has a high error rate it overestimates degradation (GPG).", "Le 1OAO est très conservateur : si chaque sous-indicateur a un taux d'erreur élevé, il surestime la dégradation (GPG)."),
         T("The land-cover transition matrix is a national decision; the strict and robust variants bound the sensitivity to moisture-related misclassification.", "La matrice de transition est une décision nationale ; les variantes stricte et robuste encadrent la sensibilité aux erreurs de classification liées à l'humidité."),
         T("SOC is reconstructed from LULC change, not measured; the 'without SOC' scenario quantifies its contribution.", "Le SOC est reconstitué à partir du LULC, pas mesuré ; le scénario « sans SOC » quantifie sa contribution."),
         T("Mixed resolution: LULC 30 m; LPD 250 m and SOC ~230 m resampled by nearest neighbour.", "Résolution mixte : LULC 30 m ; LPD 250 m et SOC ~230 m rééchantillonnés au plus proche voisin.")]
    A = [T("Run stages 02, 03, 05B and 06 for the new area first: this stage only combines their outputs.", "Exécuter d'abord les étapes 02, 03, 05B et 06 pour la nouvelle zone : cette étape ne fait que combiner leurs sorties."),
         T("Write the national land-cover transition matrix (CSV, effect D/S/I per transition, strict and robust) with a justification for every D or I; the script writes an empty template if none is given.", "Rédiger la matrice nationale de transitions (CSV, effet D/S/I par transition, stricte et robuste) avec une justification pour chaque D ou I ; le script écrit un modèle vide si rien n'est fourni."),
         T("Baseline (t0) and monitoring periods follow the UNCCD calendar (baseline 2000–2015, then 4-year reporting periods): run the baseline first, keep its BaselineStatus raster and give it to the next run.", "Les périodes de base (t0) et de suivi suivent le calendrier UNCCD (base 2000–2015, puis périodes de 4 ans) : exécuter d'abord la base, conserver son raster BaselineStatus et le fournir à l'exécution suivante."),
         T("Choose whether open water is excluded from the land area (denominator) and report the choice.", "Choisir d'exclure ou non l'eau de la surface terrestre (dénominateur) et rapporter le choix.")]
    R = ["UNCCD. Good Practice Guidance for SDG Indicator 15.3.1 (version 2) and its Addendum.", "Sims, N.C. et al. (2017). Good Practice Guidance. SDG Indicator 15.3.1: Proportion of Land That Is Degraded Over Total Land Area, Version 1.0. UNCCD, Bonn.",
         "Olofsson, P. et al. (2014). Good practices for estimating area and assessing accuracy of land change. Remote Sensing of Environment 148, 42–57."]
    spec = {"stage": "07", "title": T("SDG 15.3.1 — integration (one-out, all-out)", "ODD 15.3.1 — intégration (un-sorti-tous-sortis)"), "subtitle": T("Land cover + productivity + SOC", "Couverture + productivité + SOC"), "lang": lang, "area": area_name, "started": t0, "out_dir": out_root,
            "params": params, "inputs": inputs, "summary": summary, "checks": checks, "sections": sections, "limits": L, "adapt": A, "references": R}
    path = os.path.join(out_root, "Stage_Report_07_Integration.html")
    write_stage_report(path, spec)
    log("[Rapport HTML] " + path)
    return path
def unccd_final_report(final_dir, res_b, res_m, params, inputs, area_name, lang="en", log=print):
    """
    Rapport FINAL des deux périodes (CNULCD, GPG 15.3.1) : base puis suivi calculés dans une seule exécution. Matrice des statuts (tableau 3 du GPG) pour le scénario principal ET pour chacun des scénarios
    (matrice de couverture × productivité × SOC), proportion de terres dégradées = dégradation persistante + nouvelle, et résumé de chaque période.
    """
    en = lang == "en"
    T = lambda a, b: a if en else b
    t0 = time.time()
    rows = lambda dirs, name: sr_dict_rows(sr_read_csv(os.path.join(dirs["stats"], name)))
    fin = rows(res_m["dirs"], "Final_Indicator_by_Scenario.csv")
    grid_b, grid_m = rows(res_b["dirs"], "Scenario_Grid.csv"), rows(res_m["dirs"], "Scenario_Grid.csv")
    key = lambda r: (r.get("land_cover_matrix"), r.get("productivity"), r.get("soc"))
    pk = res_m["primary_key"]
    pkey = (pk[0], "corrigée" if pk[1] else "non corrigée", "avec SOC" if pk[2] else "sans SOC")
    land = res_m["land_ha"]
    names5 = [T("Persistent degradation (degraded at the start of the monitoring period and not improved)", "Dégradation persistante (dégradé au début du suivi et non amélioré)"), T("New degradation", "Nouvelle dégradation"),
              T("Recovered (degraded at t0 and improved)", "Rétabli (dégradé à t0 et amélioré)"), T("Stable, not degraded", "Stable non dégradé"), T("Improved (not degraded at t0)", "Amélioré (non dégradé à t0)")]
    cols = ["persistent_degradation_ha", "new_degradation_ha", "recovered_ha", "stable_not_degraded_ha", "improved_ha"]
    prim = next((r for r in fin if key(r) == pkey), None)
    status_tab = None
    if prim:
        status_tab = [[T("UNCCD status (GPG table 3)", "Statut UNCCD (GPG tableau 3)"), T("Area (ha)", "Surface (ha)"), T("% of the land", "% des terres")]]
        for nm, c in zip(names5, cols):
            v = sr_num(prim[c])
            status_tab.append([nm, f"{v:,.0f}", f"{100 * v / land:.2f}"])
        deg = sr_num(prim["persistent_degradation_ha"]) + sr_num(prim["new_degradation_ha"])
        status_tab.append([T("PROPORTION OF DEGRADED LAND (persistent + new)", "PROPORTION DE TERRES DÉGRADÉES (persistante + nouvelle)"), f"{deg:,.0f}", f"{100 * deg / land:.2f}"])
    props = [sr_num(r["proportion_degraded_%_of_land"]) for r in fin]
    scen_tab = [[T("Land-cover matrix", "Matrice de couverture"), T("Productivity", "Productivité"), "SOC", T("Baseline degraded %", "Dégradé base %"), T("Monitoring degraded %", "Dégradé suivi %"), T("Persistent (ha)", "Persistante (ha)"), T("New (ha)", "Nouvelle (ha)"),
                 T("Recovered (ha)", "Rétabli (ha)"), T("Improved (ha)", "Amélioré (ha)"), T("PROPORTION DEGRADED %", "PROPORTION DÉGRADÉE %")]]
    gb, gm = {key(r): r for r in grid_b}, {key(r): r for r in grid_m}
    csv_rows = [["land_cover_matrix", "productivity", "soc", "baseline_degraded_pct", "monitoring_degraded_pct", "persistent_ha", "new_ha", "recovered_ha", "stable_ha", "improved_ha", "proportion_degraded_pct", "main_scenario"]]
    for r in fin:
        k = key(r)
        b_, m_ = gb.get(k, {}), gm.get(k, {})
        mark = " ★" if k == pkey else ""
        scen_tab.append([r["land_cover_matrix"] + mark, r["productivity"], r["soc"], b_.get("degraded_%_of_land", ""), m_.get("degraded_%_of_land", ""), f"{sr_num(r['persistent_degradation_ha']):,.0f}", f"{sr_num(r['new_degradation_ha']):,.0f}",
                         f"{sr_num(r['recovered_ha']):,.0f}", f"{sr_num(r['improved_ha']):,.0f}", r["proportion_degraded_%_of_land"]])
        csv_rows.append([r["land_cover_matrix"], r["productivity"], r["soc"], b_.get("degraded_%_of_land", ""), m_.get("degraded_%_of_land", ""), r["persistent_degradation_ha"], r["new_degradation_ha"], r["recovered_ha"], r["stable_not_degraded_ha"], r["improved_ha"], r["proportion_degraded_%_of_land"], "yes" if k == pkey else "no"])
    import csv as _csv
    with open(os.path.join(final_dir, "UNCCD_Final_Indicator.csv"), "w", newline="", encoding="utf-8-sig") as f:
        _csv.writer(f, delimiter=";").writerows(csv_rows)
    sub_b, sub_m = sr_read_csv(os.path.join(res_b["dirs"]["stats"], "SubIndicator_Areas.csv")), sr_read_csv(os.path.join(res_m["dirs"]["stats"], "SubIndicator_Areas.csv"))
    lo, hi = (min(props), max(props)) if props else (float("nan"), float("nan"))
    checks = []
    checks.append((T("The two periods follow each other", "Les deux périodes s'enchaînent"), "PASS" if res_b["y1"] == res_m["y0"] else "FAIL", T(f"baseline {res_b['y0']}–{res_b['y1']}, monitoring {res_m['y0']}–{res_m['y1']}: the baseline status is the status at the END of the baseline", f"base {res_b['y0']}–{res_b['y1']}, suivi {res_m['y0']}–{res_m['y1']} : le statut de base est celui de la FIN de la base")))
    if props:
        checks.append((T("Proportion of degraded land across the scenarios", "Proportion de terres dégradées selon les scénarios"), "PASS" if hi - lo <= 10 else "WARN",
                       T(f"{lo:.2f} % to {hi:.2f} % ({hi - lo:.1f} points); main scenario {sr_num(prim['proportion_degraded_%_of_land']):.2f} %: report the RANGE and justify the main scenario" if prim else f"{lo:.2f} % to {hi:.2f} %",
                         f"{lo:.2f} % à {hi:.2f} % ({hi - lo:.1f} points) ; scénario principal {sr_num(prim['proportion_degraded_%_of_land']):.2f} % : rapporter la FOURCHETTE et justifier le scénario principal" if prim else f"{lo:.2f} % à {hi:.2f} %")))
    if prim:
        per_, new_, rec_ = sr_num(prim["persistent_degradation_ha"]), sr_num(prim["new_degradation_ha"]), sr_num(prim["recovered_ha"])
        checks.append((T("Persistent, new and recovered land (main scenario)", "Terres persistantes, nouvelles et rétablies (scénario principal)"), "INFO", T(f"persistent {per_:,.0f} ha, new {new_:,.0f} ha, recovered {rec_:,.0f} ha", f"persistante {per_:,.0f} ha, nouvelle {new_:,.0f} ha, rétablie {rec_:,.0f} ha")))
    pm = {r["category"]: sr_num(r["area_ha"]) for r in rows(res_m["dirs"], "Primary_Area_Statistics.csv")}
    na_ = pm.get("not_assessed", 0.0)
    checks.append((T("Land not assessed in the monitoring period", "Terres non évaluées dans la période de suivi"), "PASS" if (land and na_ / land <= 0.2) else "WARN", f"{na_:,.0f} ha ({100 * na_ / land:.1f} %)" if land else ""))
    _diag = [str(d) for d in globals().get("DIAGNOSTIC_YEARS", [])]
    checks.append((T("Baseline year is not a diagnostic (drought) year", "L'année de début de la base n'est pas une année diagnostique (sécheresse)"), "WARN" if str(res_b["y0"]) in _diag else "PASS", f"{res_b['y0']} ; " + T("diagnostic years: ", "années diagnostiques : ") + (", ".join(_diag) or "–")))
    checks.append((T("Productivity of each period", "Productivité de chaque période"), "INFO", T("the LPD of each period must come from stage 02 run with LPD_PERIOD = \"baseline\" (trajectory over the baseline period) and \"monitoring\" (state against the baseline); check the parameters of both stage-02 reports",
                                                                                           "le LPD de chaque période doit venir de l'étape 02 lancée avec LPD_PERIOD = \"baseline\" (trajectoire sur la période de base) et \"monitoring\" (état par rapport à la base) ; vérifier les paramètres des deux rapports de l'étape 02")))
    summary = []
    if prim:
        summary.append(T(f"Main scenario: {100 * deg / land:.2f} % of the land is degraded in {res_m['y1']} (persistent {per_:,.0f} ha + new {new_:,.0f} ha); recovered {rec_:,.0f} ha", f"Scénario principal : {100 * deg / land:.2f} % des terres sont dégradées en {res_m['y1']} (persistante {per_:,.0f} ha + nouvelle {new_:,.0f} ha) ; rétabli {rec_:,.0f} ha"))
    if props:
        summary.append(T(f"Range over the {len(props)} scenarios: {lo:.2f} % – {hi:.2f} %", f"Fourchette sur les {len(props)} scénarios : {lo:.2f} % – {hi:.2f} %"))
    rel = lambda r_, f_: os.path.relpath(os.path.join(r_["out_root"], f_), final_dir).replace(os.sep, "/")
    links = f"{T('Baseline', 'Base')} {res_b['y0']}–{res_b['y1']}  ->  {rel(res_b, 'Stage_Report_07_Integration.html')}\n{T('Monitoring', 'Suivi')} {res_m['y0']}–{res_m['y1']}  ->  {rel(res_m, 'Stage_Report_07_Integration.html')}"
    sections = [{"id": "status", "title": T("UNCCD status matrix, main scenario", "Matrice des statuts UNCCD, scénario principal"), "intro": T("The baseline status of each pixel (degraded or not at the end of the baseline period) is combined with its status in the monitoring period.", "Le statut de base de chaque pixel (dégradé ou non à la fin de la période de base) est combiné à son statut dans la période de suivi."),
                 "tables": [("", status_tab)] if status_tab else []},
                {"id": "scen", "title": T("Final indicator for every scenario", "Indicateur final pour chaque scénario"), "intro": T("The baseline status is applied scenario by scenario: same land-cover matrix, same productivity and same SOC choice in both periods. ★ = main scenario.", "Le statut de base est appliqué scénario par scénario : même matrice de couverture, même productivité et même choix SOC dans les deux périodes. ★ = scénario principal."),
                 "tables": [("", scen_tab)]},
                {"id": "base", "title": T(f"Baseline period {res_b['y0']}–{res_b['y1']}: sub-indicators", f"Période de base {res_b['y0']}–{res_b['y1']} : sous-indicateurs"), "tables": [("", sub_b)]},
                {"id": "mon", "title": T(f"Monitoring period {res_m['y0']}–{res_m['y1']}: sub-indicators", f"Période de suivi {res_m['y0']}–{res_m['y1']} : sous-indicateurs"), "tables": [("", sub_m)]},
                {"id": "links", "title": T("Detailed report of each period", "Rapport détaillé de chaque période"), "pre": links}]
    L = [T("The land-cover matrix is a NATIONAL decision: the strict, robust and persistent variants frame it; report the range, not one figure.", "La matrice de couverture est une décision NATIONALE : les variantes stricte, robuste et persistante l'encadrent ; rapporter la fourchette, pas un seul chiffre."),
         T("1OAO is conservative: a pixel is degraded if one assessed sub-indicator is; the sub-indicators rarely agree on the same pixel (see the support classes of each period).", "Le 1OAO est conservateur : un pixel est dégradé si un sous-indicateur évalué l'est ; les sous-indicateurs concordent rarement sur le même pixel (voir les classes de soutien de chaque période)."),
         T("The proportion of degraded land counts persistent plus new degradation; land degraded in the baseline and recovered is reported apart. Historically degraded land that never recovered is not detected by the monitoring data alone.", "La proportion de terres dégradées compte la dégradation persistante et la nouvelle ; les terres dégradées à la base puis rétablies sont rapportées à part. Les terres dégradées de longue date et jamais rétablies ne sont pas détectées par les seules données du suivi."),
         T("Productivity gains on agricultural land or on converted land are not land recovery (see the false-greening table of each period).", "Les gains de productivité sur terres agricoles ou converties ne sont pas une restauration (voir le tableau du faux verdissement de chaque période).")]
    A = [T("Run stage 02 twice (LPD_PERIOD = baseline, then monitoring), stage 06 for both SOC periods, then this stage with the two windows.", "Lancer l'étape 02 deux fois (LPD_PERIOD = baseline puis monitoring), l'étape 06 pour les deux périodes de SOC, puis cette étape avec les deux fenêtres."),
         T("Choose the main scenario and justify it; keep the full table of scenarios in the paper.", "Choisir le scénario principal et le justifier ; garder le tableau complet des scénarios dans l'article.")]
    R = ["UNCCD. Good Practice Guidance for SDG Indicator 15.3.1 (version 2) and its Addendum (status matrix, table 3)."]
    spec = {"stage": "07", "title": T("SDG 15.3.1 — baseline and monitoring periods", "ODD 15.3.1 — périodes de base et de suivi"), "subtitle": T("One run, two periods, every scenario", "Une exécution, deux périodes, tous les scénarios"), "lang": lang, "area": area_name, "started": t0, "out_dir": final_dir,
            "params": params, "inputs": inputs, "summary": summary, "checks": checks, "sections": sections, "limits": L, "adapt": A, "references": R}
    path = os.path.join(final_dir, "Stage_Report_07_UNCCD_Final.html")
    write_stage_report(path, spec)
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


YEARS = list(LULC_YEARS)
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
# 2. PARAMÈTRES
# ============================================================================

NA8 = 127                                    # « non évalué » dans les rasters de classes (int8 / Int16)
LC_EFFECTS = {"D": -1, "S": 0, "I": 1}       # D = dégradation, S = stable, I = amélioration
PLACEHOLDER_TEXT = ("", "à décider", "a decider", "todo", "tbd", "?")
LPD_RAIN_GLOB = "LPD_3class_*RainAdjusted.tif"
LPD_MAIN_NAME = "LPD_3class_B_QA1_min5.tif"
WATER_CODE = 2
AGRI_CLASSES = (5, 6)           # Agriculture, Jachère : un verdissement peut venir de l'INTENSIFICATION (intrants, subventions) ou de la CONVERSION de terres naturelles, pas d'une restauration
NATURAL_CLASSES = (4, 7, 8)     # Sol nu, Forêt, Parcours : terres non cultivées (à adapter à la légende de la zone)


# ============================================================================
# 3. LOGIQUE PURE (NumPy) — matrice de transition, 1OAO, classes de soutien, statut de base
# ============================================================================

def write_lc_matrix_template(path):
    """Matrice de transition VIDE (sauf la diagonale) : la dégradation par transition est une décision NATIONALE (GPG)."""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["from_code", "from_class", "to_code", "to_class", "effect_strict", "effect_robust", "rationale", "confidence", "source"])
        for a in CLASS_CODES:
            for b in CLASS_CODES:
                if a == b:
                    w.writerow([a, DEFAULT_CLASSES[a], b, DEFAULT_CLASSES[b], "S", "S", "pas de transition", "", ""])
                else:
                    w.writerow([a, DEFAULT_CLASSES[a], b, DEFAULT_CLASSES[b], "", "", "", "", ""])      # confidence : high / medium / low ; source : référence locale, image HR, expertise de terrain... (définir « robust » AVANT de voir les résultats)
    return path


def dict_rows_any_delimiter(f):
    """Lignes d'un CSV en dictionnaires ; le séparateur (virgule ou point-virgule, selon la langue d'Excel) est reconnu sur la ligne d'en-tête."""
    text = f.read()
    first = text.split("\n", 1)[0]
    delim = ";" if first.count(";") > first.count(",") else ","
    return list(csv.DictReader(text.splitlines(), delimiter=delim))


def read_lc_matrix(path):
    """
    Lit la matrice de transition (D / S / I) en deux variantes : « strict » et « robust » (robuste aux erreurs de classification
    liées à l'humidité). Les cases vides restent « non évaluables » ; D et I EXIGENT une justification ; la diagonale = S.
    Renvoie (lut_strict, lut_robust) : tableaux int8 de taille 100 indexés par code_depart * 10 + code_arrivee.
    """
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = dict_rows_any_delimiter(f)
    need = {"from_code", "to_code", "effect_strict", "effect_robust"}
    if not rows or not need.issubset(rows[0].keys()):
        raise RuntimeError("La matrice doit contenir les colonnes : from_code, to_code, effect_strict, effect_robust (+ rationale).")
    lut = {"effect_strict": np.full(100, NA8, dtype=np.int8), "effect_robust": np.full(100, NA8, dtype=np.int8)}
    problems = []
    for r in rows:
        try:
            a, b = int(str(r["from_code"]).strip()), int(str(r["to_code"]).strip())
        except ValueError:
            continue
        if a not in CLASS_CODES or b not in CLASS_CODES:
            continue
        why = (r.get("rationale") or "").strip()
        for key in ("effect_strict", "effect_robust"):
            v = (r.get(key) or "").strip().upper()
            if a == b:
                lut[key][a * 10 + b] = 0
                continue
            if not v:
                continue
            if v not in LC_EFFECTS:
                problems.append("transition {}->{} : '{}' invalide (attendu D, S ou I)".format(a, b, v))
                continue
            if v in ("D", "I") and why.lower() in PLACEHOLDER_TEXT:
                problems.append("transition {}->{} : un effet {} exige une JUSTIFICATION (colonne rationale)".format(a, b, v))
                continue
            lut[key][a * 10 + b] = LC_EFFECTS[v]
    if problems:
        raise RuntimeError("MATRICE DE TRANSITION REFUSÉE :\n  - " + "\n  - ".join(dict.fromkeys(problems)))
    for key in lut:
        for a in CLASS_CODES:
            lut[key][a * 10 + a] = 0                       # pas de transition = stable, même si la diagonale n'est pas dans le fichier
    return lut["effect_strict"], lut["effect_robust"]


def read_lc_matrix_meta(path):
    """Justification, niveau de confiance (high / medium / low) et source de chaque règle de la matrice : {(de, vers): {...}}. Les colonnes confidence et source sont FACULTATIVES (absentes d'une ancienne matrice : vides)."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = dict_rows_any_delimiter(f)
    out = {}
    for r in rows:
        try:
            a, b = int(str(r["from_code"]).strip()), int(str(r["to_code"]).strip())
        except (KeyError, ValueError):
            continue
        out[(a, b)] = {"effect_strict": (r.get("effect_strict") or "").strip().upper(), "effect_robust": (r.get("effect_robust") or "").strip().upper(), "rationale": (r.get("rationale") or "").strip(),
                       "confidence": (r.get("confidence") or "").strip().lower(), "source": (r.get("source") or "").strip()}
    return out


def lc_effect(a_arr, b_arr, lut):
    """Effet de la transition pixel par pixel : -1 / 0 / +1, NA8 si une date est invalide ou si la transition n'est pas dans la matrice."""
    out = np.full(a_arr.shape, NA8, dtype=np.int8)
    ok = (a_arr > 0) & (a_arr <= 8) & (b_arr > 0) & (b_arr <= 8)
    code = a_arr.astype(np.int16) * 10 + b_arr.astype(np.int16)
    out[ok] = lut[code[ok]]
    return out


def to_class8(arr, valid=(-1, 0, 1)):
    """Convertit un raster de classes (Int16 avec NoData) en int8 : valeurs de `valid` conservées, tout le reste = NA8."""
    out = np.full(arr.shape, NA8, dtype=np.int8)
    for v in valid:
        out[arr == v] = v
    return out


def oneout_allout(layers):
    """
    Règle « un seul suffit » (1OAO, GPG UNCCD) : dégradé si AU MOINS un sous-indicateur évalué est dégradé ; amélioré si au moins un
    est amélioré et AUCUN n'est dégradé ; stable sinon ; NA8 si aucun n'est évalué. Renvoie (statut int8, nombre de sous-indicateurs évalués).
    """
    shape = layers[0].shape
    avail = np.zeros(shape, dtype=np.uint8)
    deg = np.zeros(shape, dtype=bool)
    imp = np.zeros(shape, dtype=bool)
    for l in layers:
        avail += (l != NA8)
        deg |= (l == -1)
        imp |= (l == 1)
    status = np.full(shape, NA8, dtype=np.int8)
    status[avail > 0] = 0
    status[imp] = 1
    status[deg] = -1
    return status, avail


def support_class(lc, pr, so):
    """Classes de soutien du GPG (tableau 4) : 1 = O,O,O ... 8 = N,N,N (O = dégradé). 0 si un sous-indicateur manque."""
    cls = np.zeros(lc.shape, dtype=np.uint8)
    ok = (lc != NA8) & (pr != NA8) & (so != NA8)
    cls[ok] = (1 + (lc[ok] != -1).astype(np.uint8) * 4 + (pr[ok] != -1).astype(np.uint8) * 2 + (so[ok] != -1).astype(np.uint8)).astype(np.uint8)
    return cls


def apply_baseline(status, base_deg):
    """
    Statut de référence t0 (GPG, tableau 3). base_deg : 1 = dégradé à t0, 0 = non dégradé, autre = inconnu.
    Catégories : 1 dégradation persistante (dégradé à t0 et non amélioré), 2 nouvelle dégradation, 3 rétabli (dégradé à t0, amélioré),
    4 stable non dégradé, 5 amélioré (non dégradé à t0), 0 non évalué. Dégradé au sens de l'indicateur = catégories 1 et 2.
    """
    cat = np.zeros(status.shape, dtype=np.uint8)
    av = (status != NA8) & np.isin(base_deg, (0, 1))
    b = (base_deg == 1)
    cat[av & b & ((status == -1) | (status == 0))] = 1
    cat[av & ~b & (status == -1)] = 2
    cat[av & b & (status == 1)] = 3
    cat[av & ~b & (status == 0)] = 4
    cat[av & ~b & (status == 1)] = 5
    return cat


PERSISTENCE_MIN_DATES = 2       # une conversion n'est comptée que si la nouvelle occupation du sol est observée à au moins ce nombre de dates (la dernière comprise) : une conversion vue à la seule dernière date peut être un aller-retour (rotation, humidité)


def persistent_change_mask(arrays, agri=AGRI_CLASSES, min_dates=PERSISTENCE_MIN_DATES):
    """
    Règle de PERSISTANCE. arrays : liste de cartes de classes (1-8) dans l'ordre chronologique (la première = début de période, la dernière = fin).
    Vrai là où l'occupation du sol a changé UNE SEULE FOIS et s'est maintenue : le groupe à la fin diffère du groupe au début (Agriculture et Jachère forment UN groupe : une alternance culture / jachère n'est pas un changement) ;
    toutes les dates intermédiaires sont soit le groupe de départ soit le groupe d'arrivée ; une fois le groupe d'arrivée atteint il n'est plus quitté ; il est observé à au moins `min_dates` dates.
    Un pixel invalide (classe 0 ou hors 1-8) à une date n'est jamais persistant.
    """
    agri = tuple(agri)
    def grp(a):
        a = np.asarray(a)
        return np.where(np.isin(a, agri), agri[0], a) if agri else a
    first, last = grp(arrays[0]), grp(arrays[-1])
    valid = np.ones(first.shape, bool)
    for a in arrays:
        a = np.asarray(a)
        valid &= (a > 0) & (a <= 8)
    changed = first != last
    ok = changed & valid
    reached = np.zeros(first.shape, bool)
    n_last = np.zeros(first.shape, np.int16)
    for a in arrays[1:]:
        g = grp(a)
        is_first, is_last = g == first, g == last
        ok &= is_first | is_last
        ok &= ~(reached & is_first)
        reached |= is_last
        n_last += is_last
    return ok & (n_last >= int(min_dates))


def lc_effect_persistent(a_arr, b_arr, lut, mask):
    """Effet de la matrice (D/S/I) pour les seules conversions PERSISTANTES ; toute autre conversion (aller-retour, changement à la seule dernière date) compte pour « stable » ; les pixels invalides ou hors matrice restent NA8."""
    eff = lc_effect(a_arr, b_arr, lut)
    changed = np.asarray(a_arr) != np.asarray(b_arr)
    return np.where(changed & ~mask & (eff != NA8), 0, eff).astype(np.int8)


def persistence_by_transition(a_arr, b_arr, mask, land, px_ha, lut):
    """Lignes (de, classe, vers, classe, surface ha, surface persistante ha, % persistant, effet de la matrice stricte) pour chaque conversion observée sur `land`."""
    sel = land & (a_arr > 0) & (b_arr > 0) & (a_arr <= 8) & (b_arr <= 8) & (a_arr != b_arr)
    code = a_arr.astype(np.int32) * 10 + b_arr.astype(np.int32)
    tot = np.bincount(code[sel], minlength=100)
    per = np.bincount(code[sel & mask], minlength=100)
    lab = {-1: "D", 0: "S", 1: "I", NA8: "NON ÉVALUABLE"}
    rows = []
    for a in CLASS_CODES:
        for b in CLASS_CODES:
            n = int(tot[a * 10 + b])
            if n:
                rows.append([a, DEFAULT_CLASSES[a], b, DEFAULT_CLASSES[b], n * px_ha, int(per[a * 10 + b]) * px_ha, 100.0 * per[a * 10 + b] / n, lab[int(lut[a * 10 + b])]])
    return rows


IMPROVEMENT_GROUPS = ("natural_stable", "agri_stable", "natural_to_agri", "agri_to_natural", "other")


def improvement_attribution(a0, a1, prod, st, land, px_ha, agri=AGRI_CLASSES, natural=NATURAL_CLASSES):
    """
    Où se trouve l'AMÉLIORATION ? Ventile la surface, l'amélioration de la productivité et celle de l'indicateur final selon ce qui est arrivé à l'occupation du sol (a0 -> a1) :
      natural_stable  : terre non cultivée restant non cultivée (restauration possible)
      agri_stable     : terre agricole restant agricole (verdissement possible par intensification : intrants, subventions)
      natural_to_agri : terre non cultivée devenue agricole (FAUX VERDISSEMENT par conversion : la productivité monte parce que le sol est cultivé)
      agri_to_natural : terre agricole redevenue non cultivée (abandon, recolonisation)
      other           : bâti, eau, sebkha
    Les groupes sont disjoints et couvrent tous les pixels de `land`.
    """
    a0, a1 = np.asarray(a0), np.asarray(a1)
    n0, n1, g0, g1 = np.isin(a0, natural), np.isin(a1, natural), np.isin(a0, agri), np.isin(a1, agri)
    masks = {"natural_stable": n0 & n1, "agri_stable": g0 & g1, "natural_to_agri": n0 & g1, "agri_to_natural": g0 & n1}
    masks["other"] = ~(masks["natural_stable"] | masks["agri_stable"] | masks["natural_to_agri"] | masks["agri_to_natural"])
    tot_imp = float(np.count_nonzero(land & (st == 1)))
    rows = []
    for g in IMPROVEMENT_GROUPS:
        m = land & masks[g]
        n = float(np.count_nonzero(m))
        pi, pd_, si, sd = (float(np.count_nonzero(m & (v == w))) for v, w in ((prod, 1), (prod, -1), (st, 1), (st, -1)))
        rows.append({"group": g, "area_ha": n * px_ha, "prod_improved_ha": pi * px_ha, "prod_improved_pct": (100 * pi / n) if n else float("nan"), "prod_degraded_ha": pd_ * px_ha,
                     "indicator_improved_ha": si * px_ha, "indicator_improved_share_pct": (100 * si / tot_imp) if tot_imp else float("nan"), "indicator_degraded_ha": sd * px_ha})
    return rows


def area_shares(status, mask, px_ha):
    """Surfaces (ha) dégradé / stable / amélioré / non évalué dans `mask`."""
    out = {}
    for name, v in (("degraded", -1), ("stable", 0), ("improved", 1), ("not_assessed", NA8)):
        out[name] = float(np.count_nonzero(mask & (status == v))) * px_ha
    out["total"] = float(np.count_nonzero(mask)) * px_ha
    return out


# ============================================================================
# 4. ENTRÉES / SORTIES RASTER
# ============================================================================

def read_first_band(path):
    """Lit la bande 1 en gardant le dataset référencé pendant la lecture (évite « Band_XSize_get » de GDAL)."""
    ds = open_ds(path)
    arr = ds.GetRasterBand(1).ReadAsArray()
    ds = None
    return arr


def assert_class_values(path, allowed, nodata_ok, label):
    """Refuse un raster qui n'est pas un raster de classes (ex. changement continu en t C/ha au lieu de SOC_Class_*.tif)."""
    arr = read_first_band(path)
    vals = np.unique(arr[np.isfinite(arr)]) if arr.dtype.kind == "f" else np.unique(arr)
    extra = [v for v in vals.tolist() if v not in allowed and v not in nodata_ok]
    if extra:
        raise RuntimeError("Le fichier choisi pour « {} » n'est pas un raster de classes valide.\n  Fichier : {}\n  Valeurs attendues : {} (+ NoData)\n  Valeurs trouvées : {}{}".format(
            label, os.path.basename(path), sorted(allowed), [round(v, 4) if isinstance(v, float) else v for v in extra[:8]], " ..." if len(extra) > 8 else ""))


def warp_nearest_to_grid(src_path, ref_path, dtype=None, nodata=-9999):
    """Rééchantillonne `src_path` sur la grille de `ref_path` par plus proche voisin (chaque pixel fin hérite de la cellule grossière)."""
    ref = open_ds(ref_path)
    gt, rows, cols, proj = ref.GetGeoTransform(), ref.RasterYSize, ref.RasterXSize, ref.GetProjection()
    bounds = (gt[0], gt[3] + rows * gt[5], gt[0] + cols * gt[1], gt[3])
    opts = gdal.WarpOptions(format="MEM", outputBounds=bounds, width=cols, height=rows, dstSRS=proj,
                            resampleAlg=gdal.GRA_NearestNeighbour, outputType=dtype if dtype is not None else gdal.GDT_Int16,
                            dstNodata=nodata)
    out = gdal.Warp("", src_path, options=opts)
    if out is None:
        raise RuntimeError("Échec du rééchantillonnage de : " + src_path)
    arr = out.GetRasterBand(1).ReadAsArray()
    out = None
    return arr


def write_class_raster(path, arr, ref_path, nodata=NA8):
    ref = open_ds(ref_path)
    write_geotiff(path, arr.astype(np.int16), ref.GetGeoTransform(), ref.GetProjection(), gdal.GDT_Int16, nodata)


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


def find_files_glob(folder, pattern):
    import fnmatch
    hits = []
    for root, _d, files in os.walk(folder):
        for fn in files:
            if fnmatch.fnmatch(fn, pattern):
                hits.append(os.path.join(root, fn))
    return sorted(hits)


# ============================================================================
# 5. PROGRAMME PRINCIPAL
# ============================================================================

def main(cfg=None):
    t0 = time.time()
    quiet = bool(cfg and cfg.get("quiet"))          # fenêtres : période lancée par run_two_periods, sans boîte de dialogue
    if cfg is None:
        QMessageBox.information(
            None, "Indicateur ODD 15.3.1 – intégration finale (1OAO)",
            "Combine : couverture terrestre (matrice de transition NATIONALE), productivité (LPD MODIS) et carbone organique du sol (SOC),\n"
            "selon la règle « un seul suffit » (one-out, all-out) du guide de bonnes pratiques de la CNULCD.\n\n"
            "Le calcul est fait sur la grille LULC 30 m ; LPD (250 m) et SOC (~230 m) sont rééchantillonnés au plus proche voisin.\n"
            "Rien n'est inventé : une transition absente de la matrice est déclarée « non évaluable ».")

    if cfg is None:
        lulc_dir = choose_directory("1/7 – Dossier des cartes LULC (1999 ... 2025)")
        lulc_files = resolve_lulc_files(lulc_dir)

        lpd_dir = choose_directory("2/7 – Dossier 03_LPD (sorties de MODIS_LPD_COMPLETE_QGIS)")
        rain = find_files_glob(lpd_dir, LPD_RAIN_GLOB)
        main_l = find_files_glob(lpd_dir, LPD_MAIN_NAME)
        if rain:
            lpd_rain = rain[0]
        else:
            lpd_rain, _f = QFileDialog.getOpenFileName(None, "LPD 3 classes CORRIGÉ DE LA PLUIE (LPD_3class_*_RainAdjusted.tif)", lpd_dir, "Raster (*.tif)")
        if main_l:
            lpd_main = main_l[0]
        else:
            lpd_main, _f = QFileDialog.getOpenFileName(None, "LPD 3 classes NON corrigé (LPD_3class_B_QA1_min5.tif)", lpd_dir, "Raster (*.tif)")
        if not lpd_rain or not lpd_main:
            raise RuntimeError("Les deux rasters LPD (corrigé de la pluie et non corrigé) sont nécessaires.")
        assert_class_values(lpd_rain, {-1, 0, 1}, {-9999, 255, 127}, "LPD corrigé de la pluie")
        assert_class_values(lpd_main, {-1, 0, 1}, {-9999, 255, 127}, "LPD non corrigé")

        soc_file, _f = QFileDialog.getOpenFileName(None, "3/7 – SOC_Class_<début>_<fin>.tif (sortie de UNCCD_SOC_FINAL_QGIS)", "", "Raster (*.tif)")
        if not soc_file:
            raise RuntimeError("Opération annulée.")
        if not os.path.basename(soc_file).startswith("SOC_Class_"):
            raise RuntimeError("Vous avez choisi « {} ». Il faut le raster de CLASSES SOC_Class_<début>_<fin>.tif (dossier 04_SOC_Change), "
                               "pas SOC_Change / SOC_ChangePct / SOC_ChangeAnnual (valeurs continues en t C/ha ou en %).".format(os.path.basename(soc_file)))
        assert_class_values(soc_file, {-1, 0, 1}, {127, -9999, 255}, "SOC")
        m = re.search(r"(\d{4})_(\d{4})", os.path.basename(soc_file))
        if not m or int(m.group(1)) not in YEARS or int(m.group(2)) not in YEARS:
            raise RuntimeError("Le nom du fichier SOC doit contenir deux années de LULC, ex. SOC_Class_2000_2025.tif.")
        y0, y1 = int(m.group(1)), int(m.group(2))

        matrix_file, _f = QFileDialog.getOpenFileName(None, "4/7 – Matrice de transition de la couverture terrestre (CSV D/S/I) – annuler pour un modèle", "", "CSV (*.csv)")
        out_root = choose_directory("5/7 – Dossier de sortie")
        if not matrix_file:
            tpl = write_lc_matrix_template(os.path.join(out_root, "LC_Transition_Matrix_TEMPLATE.csv"))
            QMessageBox.information(None, "Modèle de matrice créé",
                                    "Aucune matrice fournie : modèle écrit dans\n{}\n\nLa dégradation par transition est une DÉCISION NATIONALE : "
                                    "remplissez effect_strict / effect_robust (D, S ou I) et justifiez chaque D ou I.".format(tpl))
            return
        baseline_file, _f = QFileDialog.getOpenFileName(None, "6/7 (facultatif) – SDG1531_BaselineStatus_for_next_run_*.tif d'une exécution PRÉCÉDENTE (ex. 2000-2015) comme statut t0 – annuler = aucun", "", "Raster (*.tif)")

        lc_choice, ok = QInputDialog.getItem(None, "Variante LC principale", "Matrice de transition à utiliser pour le scénario PRINCIPAL :\n"
                                             "strict = toutes les transitions de la matrice ; robuste = transitions entre classes sensibles à l'humidité jugées stables ;\n"
                                             "persistent = matrice stricte, mais une transition ne compte que si elle est PERSISTANTE (changement unique qui se maintient à au moins 2 dates ; il faut au moins 3 cartes LULC ; les années diagnostiques sont ignorées).",
                                             ["robust", "strict", "persistent"], 0, False)
        if not ok:
            raise RuntimeError("Opération annulée.")
        prod_choice, ok = QInputDialog.getItem(None, "Productivité principale", "Le guide exige une productivité calibrée sur l'humidité :",
                                               ["corrigée de la pluie", "non corrigée"], 0, False)
        if not ok:
            raise RuntimeError("Opération annulée.")
        soc_choice, ok = QInputDialog.getItem(None, "SOC dans le scénario principal", "SOC estimé à partir des changements de LULC (confiance faible) :",
                                              ["inclure", "exclure"], 0, False)
        if not ok:
            raise RuntimeError("Opération annulée.")
        water_choice, ok = QInputDialog.getItem(None, "Eau dans la surface terrestre", "Surface terrestre totale (dénominateur) :",
                                                ["exclure l'eau", "inclure l'eau"], 0, False)
        if not ok:
            raise RuntimeError("Opération annulée.")
        primary_lc_variant, primary_rain, primary_soc, excl_water = lc_choice, prod_choice.startswith("corrig"), soc_choice == "inclure", water_choice.startswith("exclure")
    else:                                                     # période lancée par les deux fenêtres (base puis suivi) : toutes les réponses viennent de cfg
        lulc_dir, lulc_files = cfg["lulc_dir"], cfg["lulc_files"]
        lpd_rain, lpd_main = cfg["lpd_rain"], cfg["lpd_main"]
        soc_file, y0, y1 = cfg["soc_file"], cfg["y0"], cfg["y1"]
        matrix_file, out_root, baseline_file = cfg["matrix_file"], cfg["out_root"], cfg.get("baseline_file")
        primary_lc_variant, primary_rain, primary_soc, excl_water = cfg["primary_lc_variant"], cfg["primary_rain"], cfg["primary_soc"], cfg["excl_water"]

    dirs = {k: os.path.join(out_root, v) for k, v in (("qa", "00_QA"), ("sub", "01_SubIndicators"), ("ind", "02_Indicator"), ("stats", "03_Statistics"))}
    for d in dirs.values():
        ensure_dir(d)
    report = []

    def log(line=""):
        print(line)
        report.append(line)

    log("INDICATEUR ODD 15.3.1 – INTÉGRATION 1OAO (couverture + productivité + SOC)")
    log("=" * 78)
    ref_lulc = lulc_files[y1]
    px_ha = pixel_area_ha_path(ref_lulc)
    log("Période de suivi : LULC {} -> {} ; SOC : {} ; grille d'analyse = LULC ({:.0f} m, pixel {:.3f} ha)".format(y0, y1, os.path.basename(soc_file), raster_info(ref_lulc)["xres"], px_ha))

    # ---- matrice et couverture terrestre
    lut_s, lut_r = read_lc_matrix(matrix_file)
    a_arr, b_arr = read_first_band(lulc_files[y0]), read_first_band(lulc_files[y1])
    lc = {"strict": lc_effect(a_arr, b_arr, lut_s), "robust": lc_effect(a_arr, b_arr, lut_r)}
    # variante PERSISTANTE : matrice stricte filtrée par la persistance des conversions (cartes intermédiaires ; années diagnostiques ignorées)
    _diag = [str(d) for d in globals().get("DIAGNOSTIC_YEARS", [])]
    persist_years = [yy for yy in sorted(lulc_files) if y0 <= yy <= y1 and (yy in (y0, y1) or str(yy) not in _diag)]
    persist_mask = None
    if len(persist_years) >= 3:
        persist_mask = persistent_change_mask([a_arr if yy == y0 else (b_arr if yy == y1 else read_first_band(lulc_files[yy])) for yy in persist_years])
        lc["persistent"] = lc_effect_persistent(a_arr, b_arr, lut_s, persist_mask)
    LC_VARIANTS = [v for v in ("strict", "robust", "persistent") if v in lc]
    if primary_lc_variant not in lc:
        raise RuntimeError("Variante LC « {} » impossible : il faut au moins 3 cartes LULC entre {} et {} (hors années diagnostiques) pour tester la persistance ; trouvées : {}.".format(primary_lc_variant, y0, y1, ", ".join(map(str, persist_years))))
    land = (b_arr > 0) & ((b_arr != WATER_CODE) if excl_water else True)
    land_ha = float(np.count_nonzero(land)) * px_ha
    log("Surface terrestre totale (dénominateur) : {:,.0f} ha ({})".format(land_ha, "eau exclue" if excl_water else "eau incluse"))
    # couverture de la matrice : transitions observées
    codes = np.bincount((a_arr[(a_arr > 0) & (b_arr > 0)].astype(np.int32) * 10 + b_arr[(a_arr > 0) & (b_arr > 0)].astype(np.int32)), minlength=100)
    cov_rows, n_missing = [], 0.0
    for a in CLASS_CODES:
        for b in CLASS_CODES:
            n = int(codes[a * 10 + b])
            if n and a != b:
                es, er = int(lut_s[a * 10 + b]), int(lut_r[a * 10 + b])
                lab = lambda v: {-1: "D", 0: "S", 1: "I", NA8: "NON ÉVALUABLE"}[v]
                cov_rows.append([a, DEFAULT_CLASSES[a], b, DEFAULT_CLASSES[b], n, fmt(n * px_ha, 1), lab(es), lab(er)])
                if es == NA8:
                    n_missing += n * px_ha
    write_csv(os.path.join(dirs["qa"], "LC_Transitions_Observed.csv"), ["from", "from_class", "to", "to_class", "pixels", "area_ha", "effect_strict", "effect_robust"], cov_rows)
    meta = read_lc_matrix_meta(matrix_file)
    obs_ha = {(r[0], r[2]): float(r[5]) for r in cov_rows}
    rules = []
    for (a, b), mm in sorted(meta.items()):
        if a == b or (mm["effect_strict"] not in ("D", "I") and mm["effect_robust"] not in ("D", "I")):
            continue
        rules.append([a, DEFAULT_CLASSES.get(a, ""), b, DEFAULT_CLASSES.get(b, ""), mm["effect_strict"], mm["effect_robust"], mm["confidence"] or "not given", mm["source"], mm["rationale"], fmt(obs_ha.get((a, b), 0.0), 1)])
    write_csv(os.path.join(dirs["qa"], "LC_Matrix_Rules_Used.csv"), ["from", "from_class", "to", "to_class", "effect_strict", "effect_robust", "confidence", "source", "rationale", "observed_area_ha"], rules)
    n_nc = sum(1 for r in rules if r[6] == "not given")
    if rules:
        log("MATRICE : {} règles D ou I appliquées ; niveau de confiance non renseigné pour {} d'entre elles (colonnes confidence et source de la matrice).".format(len(rules), n_nc))
    if n_missing:
        log("ATTENTION : {:,.0f} ha de transitions observées ne figurent pas dans la matrice (variante stricte) : couverture terrestre NON ÉVALUABLE sur ces pixels.".format(n_missing))

    # ---- productivité et SOC sur la grille LULC
    pr_rain = to_class8(warp_nearest_to_grid(lpd_rain, ref_lulc, gdal.GDT_Int16, -9999))
    pr_main = to_class8(warp_nearest_to_grid(lpd_main, ref_lulc, gdal.GDT_Int16, -9999))
    so = to_class8(warp_nearest_to_grid(soc_file, ref_lulc, gdal.GDT_Int16, NA8))
    base, base_by = None, (cfg or {}).get("baseline_by")
    if baseline_file:
        assert_class_values(baseline_file, {0, 1}, {255, -9999, 127}, "statut de référence t0")
        base = warp_nearest_to_grid(baseline_file, ref_lulc, gdal.GDT_Int16, -9999)

    subs = (("Couverture (strict)", lc["strict"]), ("Couverture (robuste)", lc["robust"])) + ((("Couverture (persistante)", lc["persistent"]),) if "persistent" in lc else ()) + (("Productivité corrigée de la pluie", pr_rain),
            ("Productivité non corrigée", pr_main), ("SOC (changement de LULC, {}-{})".format(y0, y1), so))
    log("")
    log("SOUS-INDICATEURS SUR LA GRILLE LULC (surface terrestre)")
    sub_rows = []
    for name, arr in subs:
        s = area_shares(arr, land, px_ha)
        log("   {:<42s} dégradé {:>10,.0f} ha ({:4.1f} %) | stable {:>10,.0f} | amélioré {:>9,.0f} | non évalué {:>9,.0f} ha".format(
            name, s["degraded"], 100 * s["degraded"] / land_ha, s["stable"], s["improved"], s["not_assessed"]))
        sub_rows.append([name, fmt(s["degraded"], 1), fmt(100 * s["degraded"] / land_ha, 2), fmt(s["stable"], 1), fmt(s["improved"], 1), fmt(s["not_assessed"], 1)])
    write_csv(os.path.join(dirs["stats"], "SubIndicator_Areas.csv"), ["sub_indicator", "degraded_ha", "degraded_%_of_land", "stable_ha", "improved_ha", "not_assessed_ha"], sub_rows)

    # ---- grille de scénarios
    log("")
    log("INDICATEUR 15.3.1 PAR SCÉNARIO (% de la surface terrestre totale ; 1OAO)")
    scen_rows, status_by = [], {}
    for lcv in LC_VARIANTS:
        for rn in (True, False):
            for soc_in in (True, False):
                layers = [lc[lcv], pr_rain if rn else pr_main] + ([so] if soc_in else [])
                st, nav = oneout_allout(layers)
                status_by[(lcv, rn, soc_in)] = (st, nav)
                s = area_shares(st, land, px_ha)
                assessed = land_ha - s["not_assessed"]
                scen_rows.append([lcv, "corrigée" if rn else "non corrigée", "avec SOC" if soc_in else "sans SOC",
                                  fmt(s["degraded"], 1), fmt(100 * s["degraded"] / land_ha, 2), fmt(100 * s["degraded"] / assessed if assessed else float("nan"), 2),
                                  fmt(100 * s["improved"] / land_ha, 2), fmt(100 * s["not_assessed"] / land_ha, 2)])
                tag = "PRINCIPAL" if (lcv == primary_lc_variant and rn == primary_rain and soc_in == primary_soc) else ""
                log("   LC {:<7s} | productivité {:<13s} | {:<8s} : dégradé {:>6.2f} % ({:>10,.0f} ha) | amélioré {:>5.2f} % | non évalué {:>5.2f} %  {}".format(
                    lcv, "corrigée" if rn else "non corrigée", "avec SOC" if soc_in else "sans SOC", 100 * s["degraded"] / land_ha, s["degraded"],
                    100 * s["improved"] / land_ha, 100 * s["not_assessed"] / land_ha, tag))
    write_csv(os.path.join(dirs["stats"], "Scenario_Grid.csv"),
              ["land_cover_matrix", "productivity", "soc", "degraded_ha", "degraded_%_of_land", "degraded_%_of_assessed", "improved_%_of_land", "not_assessed_%_of_land"], scen_rows)
    # indicateur FINAL (GPG tableau 3) pour CHAQUE scénario : le statut de base de la période précédente est appliqué scénario par scénario (même matrice, même productivité, même SOC)
    final_rows = []
    if base_by:
        for (lcv, rn, soc_in), (st_k, _nav) in status_by.items():
            if (lcv, rn, soc_in) not in base_by:
                continue
            cat_k = apply_baseline(st_k, base_by[(lcv, rn, soc_in)])
            ha_k = [float(np.count_nonzero(land & (cat_k == k))) * px_ha for k in (1, 2, 3, 4, 5)]
            final_rows.append([lcv, "corrigée" if rn else "non corrigée", "avec SOC" if soc_in else "sans SOC"] + [fmt(v, 1) for v in ha_k] + [fmt(100 * (ha_k[0] + ha_k[1]) / land_ha, 2)])
        write_csv(os.path.join(dirs["stats"], "Final_Indicator_by_Scenario.csv"), ["land_cover_matrix", "productivity", "soc", "persistent_degradation_ha", "new_degradation_ha", "recovered_ha", "stable_not_degraded_ha", "improved_ha", "proportion_degraded_%_of_land"], final_rows)
        base = base_by.get((primary_lc_variant, primary_rain, primary_soc))

    # ---- scénario principal : rasters et statistiques détaillées
    st, nav = status_by[(primary_lc_variant, primary_rain, primary_soc)]
    sup = support_class(lc[primary_lc_variant], pr_rain if primary_rain else pr_main, so)
    write_class_raster(os.path.join(dirs["sub"], "LC_Class_{}_{}_strict.tif".format(y0, y1)), lc["strict"], ref_lulc)
    write_class_raster(os.path.join(dirs["sub"], "LC_Class_{}_{}_robust.tif".format(y0, y1)), lc["robust"], ref_lulc)
    if persist_mask is not None:
        write_class_raster(os.path.join(dirs["sub"], "LC_Class_{}_{}_persistent.tif".format(y0, y1)), lc["persistent"], ref_lulc)
        pr_rows = persistence_by_transition(a_arr, b_arr, persist_mask, land, px_ha, lut_s)
        write_csv(os.path.join(dirs["stats"], "LC_Persistence_by_Transition.csv"), ["from", "from_class", "to", "to_class", "area_ha", "persistent_ha", "persistent_%", "effect_strict"],
                  [[r[0], r[1], r[2], r[3], fmt(r[4], 1), fmt(r[5], 1), fmt(r[6], 1), r[7]] for r in pr_rows])
        log("")
        log("PERSISTANCE DES CONVERSIONS (dates : {} ; années diagnostiques ignorées : {}) : un changement ne compte que s'il est unique et se maintient à au moins {} dates".format(", ".join(map(str, persist_years)), ", ".join(_diag) or "aucune", PERSISTENCE_MIN_DATES))
        nat_agri = [r for r in pr_rows if r[0] in NATURAL_CLASSES and r[2] in AGRI_CLASSES]
        if nat_agri:
            log("   conversions naturel -> agricole : {:,.0f} ha, dont {:,.0f} ha persistantes ({:.0f} %)".format(sum(r[4] for r in nat_agri), sum(r[5] for r in nat_agri), 100 * sum(r[5] for r in nat_agri) / max(1e-9, sum(r[4] for r in nat_agri))))
        for r in sorted(pr_rows, key=lambda r: -r[4])[:6]:
            log("   {:<12s} -> {:<12s} : {:>9,.0f} ha, persistants {:>9,.0f} ha ({:4.0f} %)  matrice stricte : {}".format(r[1], r[3], r[4], r[5], r[6], r[7]))
    else:
        log("")
        log("PERSISTANCE : variante non calculée (il faut au moins 3 cartes LULC entre {} et {}, hors années diagnostiques ; trouvées : {})".format(y0, y1, ", ".join(map(str, persist_years))))
    write_class_raster(os.path.join(dirs["sub"], "Productivity_RainAdjusted_on_LULC_grid.tif"), pr_rain, ref_lulc)
    write_class_raster(os.path.join(dirs["sub"], "Productivity_Unadjusted_on_LULC_grid.tif"), pr_main, ref_lulc)
    write_class_raster(os.path.join(dirs["sub"], "SOC_Class_on_LULC_grid.tif"), so, ref_lulc)
    write_class_raster(os.path.join(dirs["ind"], "SDG1531_1OAO_primary.tif"), st, ref_lulc)
    write_class_raster(os.path.join(dirs["ind"], "SDG1531_NAvailable_primary.tif"), nav, ref_lulc, nodata=255)
    write_class_raster(os.path.join(dirs["ind"], "SDG1531_SupportClass_primary.tif"), sup, ref_lulc, nodata=0)
    # statut « dégradé / non dégradé » prêt à servir de statut de référence t0 pour une exécution ultérieure (ex. 2000-2015 -> 2015-2025)
    base_out = np.where(st == -1, 1, np.where((st == 0) | (st == 1), 0, 255)).astype(np.int16)
    write_class_raster(os.path.join(dirs["ind"], "SDG1531_BaselineStatus_for_next_run_{}_{}.tif".format(y0, y1)), base_out, ref_lulc, nodata=255)
    anomaly = ((pr_main == -1) & (pr_rain != -1) & (pr_rain != NA8)).astype(np.int8)
    write_class_raster(os.path.join(dirs["ind"], "Explainable_Anomaly_Productivity_Rain.tif"), np.where(land, anomaly, NA8), ref_lulc)
    n_anom = float(np.count_nonzero(land & (anomaly == 1))) * px_ha
    log("")
    log("ANOMALIES EXPLICABLES : productivité dégradée SANS correction de la pluie mais non dégradée une fois corrigée : {:,.0f} ha ({:.1f} % de la surface terrestre)".format(n_anom, 100 * n_anom / land_ha))

    sp = area_shares(st, land, px_ha)
    assessed = land_ha - sp["not_assessed"]
    log("")
    log("SCÉNARIO PRINCIPAL : LC {} + productivité {} + {}".format(primary_lc_variant, "corrigée de la pluie" if primary_rain else "non corrigée", "SOC" if primary_soc else "sans SOC"))
    log("   dégradé {:,.0f} ha = {:.2f} % de la surface terrestre ({:.2f} % de la surface évaluée) | amélioré {:.2f} % | non évalué {:.2f} %".format(
        sp["degraded"], 100 * sp["degraded"] / land_ha, 100 * sp["degraded"] / assessed if assessed else float("nan"),
        100 * sp["improved"] / land_ha, 100 * sp["not_assessed"] / land_ha))
    # ---- COUVERTURE (surface valide) de chaque sous-indicateur et du résultat : un NoData n'est JAMAIS transformé en « stable »
    prod_prim = pr_rain if primary_rain else pr_main
    cov_items = [("land", land), ("assessed_land_cover", land & (lc[primary_lc_variant] != NA8)), ("assessed_productivity", land & (prod_prim != NA8))]
    if primary_soc:
        cov_items.append(("assessed_soc", land & (so != NA8)))
    n_need = 2 + (1 if primary_soc else 0)
    for k in range(0, n_need + 1):
        cov_items.append(("assessed_by_{}_subindicators".format(k), land & (nav == k)))
    cov_items.append(("final_assessed_at_least_one", land & (nav > 0)))
    covg_rows = [[k, fmt(float(np.count_nonzero(v)) * px_ha, 1), fmt(100.0 * float(np.count_nonzero(v)) / max(1, np.count_nonzero(land)), 2)] for k, v in cov_items]
    sum_chk = sum(float(np.count_nonzero(land & (st == v))) for v in (-1, 0, 1, NA8)) * px_ha
    covg_rows.append(["sum_of_statuses_degraded_stable_improved_not_assessed", fmt(sum_chk, 1), fmt(100.0 * sum_chk / land_ha, 2)])
    write_csv(os.path.join(dirs["stats"], "Coverage_Table.csv"), ["item", "area_ha", "percent_of_land"], covg_rows)
    log("")
    log("COUVERTURE (scénario principal) : surface terrestre {:,.0f} ha ; évaluée par la couverture {:,.0f} | par la productivité {:,.0f}{} ; pixels évalués par 0 / 1 / 2{} sous-indicateurs : {}".format(
        land_ha, float(np.count_nonzero(cov_items[1][1])) * px_ha, float(np.count_nonzero(cov_items[2][1])) * px_ha, (" | par le SOC {:,.0f}".format(float(np.count_nonzero(cov_items[3][1])) * px_ha) if primary_soc else ""), " / 3" if primary_soc else "",
        " / ".join("{:,.0f} ha".format(float(np.count_nonzero(land & (nav == k))) * px_ha) for k in range(0, n_need + 1))))
    log("   Un pixel est « non évalué » seulement si AUCUN sous-indicateur n'est évaluable ; un pixel sans donnée pour un sous-indicateur est jugé par les autres (jamais compté comme stable par défaut). La somme des statuts = {:,.0f} ha.".format(sum_chk))
    # statut de référence t0 (GPG tableau 3)
    if base is not None:
        cat = apply_baseline(st, base)
        names = {1: "dégradation persistante", 2: "nouvelle dégradation", 3: "rétabli", 4: "stable non dégradé", 5: "amélioré (non dégradé à t0)"}
        write_class_raster(os.path.join(dirs["ind"], "SDG1531_StatusMatrix_primary.tif"), cat, ref_lulc, nodata=0)
        tot_deg = float(np.count_nonzero(land & np.isin(cat, (1, 2)))) * px_ha
        log("   AVEC statut de référence t0 : " + " | ".join("{} {:,.0f} ha".format(names[k], float(np.count_nonzero(land & (cat == k))) * px_ha) for k in names))
        log("   PROPORTION DE TERRES DÉGRADÉES (persistantes + nouvelles) : {:.2f} %".format(100 * tot_deg / land_ha))
    else:
        log("   Statut de référence t0 NON fourni : le résultat est la dégradation détectée sur la période de suivi (nouvelle dégradation) ; les terres dégradées")
        log("   avant la période et non rétablies ne sont pas comptées (GPG : « terres historiquement dégradées non rétablies » à ajouter).")
    # classes de soutien
    log("")
    log("CLASSES DE SOUTIEN (GPG tableau 4 ; O = dégradé) sur les pixels où les 3 sous-indicateurs sont évalués")
    lab = {1: "O,O,O", 2: "O,O,N", 3: "O,N,O", 4: "O,N,N", 5: "N,O,O", 6: "N,O,N", 7: "N,N,O", 8: "N,N,N"}
    sup_rows = []
    for k in range(1, 9):
        ar = float(np.count_nonzero(land & (sup == k))) * px_ha
        sup_rows.append([k, "couverture/productivité/SOC = " + lab[k], fmt(ar, 1), "oui" if k < 8 else "non"])
        log("   classe {} ({}) : {:>10,.0f} ha".format(k, lab[k], ar))
    write_csv(os.path.join(dirs["stats"], "SupportClass_Areas.csv"), ["support_class", "combination (couverture, productivité, SOC ; O=dégradé)", "area_ha", "degraded_at_indicator_level"], sup_rows)
    n_single = sum(float(np.count_nonzero(land & (sup == k))) * px_ha for k in (4, 6, 7))
    n_deg_all3 = sum(float(np.count_nonzero(land & (sup == k))) * px_ha for k in range(1, 8))
    if n_deg_all3:
        log("   dégradation signalée par UN SEUL sous-indicateur : {:,.0f} ha ({:.0f} % des pixels dégradés évalués sur les 3) -> la plus exposée aux faux positifs".format(n_single, 100 * n_single / n_deg_all3))
    # par classe d'occupation du sol à la date finale
    rows_l = []
    for c in CLASS_CODES:
        mk = land & (b_arr == c)
        n = int(np.count_nonzero(mk))
        if n:
            d = float(np.count_nonzero(mk & (st == -1)))
            i = float(np.count_nonzero(mk & (st == 1)))
            rows_l.append([c, DEFAULT_CLASSES[c], n, fmt(n * px_ha, 1), fmt(d * px_ha, 1), fmt(100 * d / n, 2), fmt(100 * i / n, 2)])
    write_csv(os.path.join(dirs["stats"], "Primary_by_LULC_{}.csv".format(y1)), ["class_code", "class", "pixels", "area_ha", "degraded_ha", "degraded_%", "improved_%"], rows_l)
    # où se trouve l'amélioration ? (faux verdissement : conversion de terres naturelles en terres agricoles ; intensification des intrants)
    prod_primary = pr_rain if primary_rain else pr_main
    ia = improvement_attribution(a_arr, b_arr, prod_primary, st, land, px_ha)
    write_csv(os.path.join(dirs["stats"], "Improved_by_Transition_Group.csv"), ["group", "area_ha", "productivity_improved_ha", "productivity_improved_%_of_group", "productivity_degraded_ha", "indicator_improved_ha", "indicator_improved_%_of_all_improved", "indicator_degraded_ha"],
              [[r["group"], fmt(r["area_ha"], 1), fmt(r["prod_improved_ha"], 1), fmt(r["prod_improved_pct"], 2), fmt(r["prod_degraded_ha"], 1), fmt(r["indicator_improved_ha"], 1), fmt(r["indicator_improved_share_pct"], 2), fmt(r["indicator_degraded_ha"], 1)] for r in ia])
    log("")
    log("OÙ SE TROUVE L'AMÉLIORATION (faux verdissement) : terres agricoles (intrants) ou converties de terres naturelles ne sont pas une restauration")
    for r in ia:
        log("   {:<16} {:>10,.0f} ha | productivité améliorée {:>9,.0f} ha ({:5.1f} %) | indicateur amélioré {:>9,.0f} ha ({:5.1f} % de l'amélioration totale)".format(
            r["group"], r["area_ha"], r["prod_improved_ha"], r["prod_improved_pct"], r["indicator_improved_ha"], r["indicator_improved_share_pct"]))
    sdg_rows = [[k, fmt(v, 1)] for k, v in sp.items()]
    write_csv(os.path.join(dirs["stats"], "Primary_Area_Statistics.csv"), ["category", "area_ha"], sdg_rows)

    log("")
    log("LIMITES (à reprendre dans la méthodologie)")
    log("  - 1OAO est très conservateur : si l'erreur de chaque sous-indicateur est élevée, il surestime la dégradation (GPG, §6.1). Voir les classes de soutien.")
    log("  - La matrice de transition est une décision NATIONALE ; les deux variantes (stricte / robuste) encadrent la sensibilité aux erreurs de classification liées à l'humidité.")
    log("  - Le SOC est reconstitué à partir des changements de LULC (pas une mesure) : il hérite de leurs erreurs ; le scénario « sans SOC » quantifie sa contribution.")
    log("  - La productivité doit être calibrée sur l'humidité (GPG) : le scénario principal par défaut utilise la variante corrigée de la pluie ; la variante non corrigée est la borne haute.")
    log("  - FAUX VERDISSEMENT : sur les terres agricoles l'augmentation de productivité peut venir de l'intensification (intrants, subventions) et, là où des terres naturelles sont devenues agricoles, de la conversion elle-même ; ce n'est pas une restauration. Voir Improved_by_Transition_Group.csv.")
    log("  - Résolution mixte : LULC 30 m ; LPD 250 m et SOC ~230 m rééchantillonnés au plus proche voisin (les cellules grossières sont réparties sur des pixels de 30 m).")
    log("")
    log("Durée : {:.1f} min | Sorties : {}".format((time.time() - t0) / 60.0, out_root))
    with open(os.path.join(dirs["qa"], "Integration_Report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    add_layer(os.path.join(dirs["ind"], "SDG1531_1OAO_primary.tif"), "ODD 15.3.1 – 1OAO (-1 dégradé, 0 stable, 1 amélioré ; 127 non évalué)")
    add_layer(os.path.join(dirs["ind"], "SDG1531_SupportClass_primary.tif"), "ODD 15.3.1 – classes de soutien (1 = O,O,O ... 8 = N,N,N)")
    try:
        _inp = [{"label": "Land productivity (rain-adjusted)", "path": lpd_rain}, {"label": "Land productivity (unadjusted)", "path": lpd_main}, {"label": "SOC class raster", "path": soc_file}, {"label": "Land-cover transition matrix", "path": matrix_file}]
        integration_stage_report(out_root, dirs, report, t0, {"Land-cover matrix variant (main)": primary_lc_variant, "Rain-adjusted productivity (main)": primary_rain, "SOC included (main)": primary_soc, "Open water excluded": excl_water, "Period": f"{y0}-{y1}"}, _inp, AREA_NAME, y0, y1, REPORT_LANG)
    except Exception as _exc:
        print("[Rapport HTML d'étape] échec (le traitement lui-même est terminé) : " + str(_exc))
    if not quiet:  # message final
        QMessageBox.information(None, "Intégration 15.3.1 terminée", "\n".join(report[:45]))
    out = {"y0": y0, "y1": y1, "out_root": out_root, "dirs": dirs, "report": report, "land_ha": land_ha, "px_ha": px_ha, "primary_key": (primary_lc_variant, primary_rain, primary_soc), "final_rows": final_rows, "t0": t0,
           "scenario_rows": scen_rows}
    if cfg and cfg.get("return_baseline"):               # statut de base de CHAQUE scénario, pour la période de suivi (1 dégradé, 0 non dégradé, 255 non évalué)
        out["baseline_by"] = {k: np.where(v[0] == -1, 1, np.where((v[0] == 0) | (v[0] == 1), 0, 255)).astype(np.int8) for k, v in status_by.items()}
    return out


# ============================================================================
# DEUX FEN\u00caTRES SUCCESSIVES (CNULCD, GPG 15.3.1) : p\u00e9riode de BASE puis p\u00e9riode de SUIVI, calcul\u00e9es dans UNE seule ex\u00e9cution
# ============================================================================
def parse_period_from_soc(soc_file):
    """(y0, y1) lus dans SOC_Class_<d\u00e9but>_<fin>.tif ; erreur claire sinon."""
    base = os.path.basename(soc_file)
    if not base.startswith("SOC_Class_"):
        raise RuntimeError("Vous avez choisi \u00ab {} \u00bb. Il faut le raster de CLASSES SOC_Class_<d\u00e9but>_<fin>.tif (dossier 04_SOC_Change), pas SOC_Change / SOC_ChangePct / SOC_ChangeAnnual.".format(base))
    m = re.search(r"(\d{4})_(\d{4})", base)
    if not m or int(m.group(1)) not in YEARS or int(m.group(2)) not in YEARS or int(m.group(1)) >= int(m.group(2)):
        raise RuntimeError("Le nom du fichier SOC doit contenir deux ann\u00e9es de LULC dans l'ordre, ex. SOC_Class_1999_2015.tif ({}).".format(base))
    return int(m.group(1)), int(m.group(2))


def find_lpd_pair(lpd_dir):
    """(LPD corrig\u00e9 de la pluie, LPD non corrig\u00e9) d'un dossier 03_LPD ; erreur claire si l'un manque ou n'est pas un raster de classes."""
    rain, main_l = find_files_glob(lpd_dir, LPD_RAIN_GLOB), find_files_glob(lpd_dir, LPD_MAIN_NAME)
    if not rain or not main_l:
        raise RuntimeError("Le dossier {} doit contenir LPD_3class_*_RainAdjusted.tif ET LPD_3class_B_QA1_min5.tif (sorties de l'\u00e9tape 02).".format(lpd_dir))
    assert_class_values(rain[0], {-1, 0, 1}, {-9999, 255, 127}, "LPD corrig\u00e9 de la pluie")
    assert_class_values(main_l[0], {-1, 0, 1}, {-9999, 255, 127}, "LPD non corrig\u00e9")
    return rain[0], main_l[0]


def validate_periods(base, mon):
    """base, mon : (y0, y1). La base finit l\u00e0 o\u00f9 le suivi commence (UNCCD : p\u00e9riode de base puis p\u00e9riode de suivi)."""
    if base[1] != mon[0]:
        raise RuntimeError("Les p\u00e9riodes ne s'encha\u00eenent pas : la base finit en {} mais le suivi commence en {}. Le statut de base doit \u00eatre celui de la FIN de la base.".format(base[1], mon[0]))
    if not (base[0] < base[1] < mon[1]):
        raise RuntimeError("P\u00e9riodes incoh\u00e9rentes : base {}-{}, suivi {}-{}.".format(base[0], base[1], mon[0], mon[1]))
    return True


def persist_dates(lulc_files, y0, y1):
    _diag = [str(d) for d in globals().get("DIAGNOSTIC_YEARS", [])]
    return [yy for yy in sorted(lulc_files) if y0 <= yy <= y1 and (yy in (y0, y1) or str(yy) not in _diag)]


def run_two_periods(common, base_in, mon_in, lang=None, log=print):
    """
    common : {lulc_dir, lulc_files, matrix_file, out_root, primary_lc_variant, primary_rain, primary_soc, excl_water} ; base_in, mon_in : {lpd_dir, soc_file}.
    1. p\u00e9riode de BASE (ex. 1999 -> 2015) -> statut de base de CHAQUE sc\u00e9nario ; 2. p\u00e9riode de SUIVI (ex. 2015 -> 2025) avec ce statut ; 3. rapport HTML FINAL (mati\u00e8re des statuts UNCCD, indicateur par sc\u00e9nario, p\u00e9riodes).
    """
    lang = lang or REPORT_LANG
    b = parse_period_from_soc(base_in["soc_file"])
    m = parse_period_from_soc(mon_in["soc_file"])
    validate_periods(b, m)
    if common["primary_lc_variant"] == "persistent":
        for nm, (y0_, y1_) in (("base", b), ("suivi", m)):
            if len(persist_dates(common["lulc_files"], y0_, y1_)) < 3:
                raise RuntimeError("Variante LC \u00ab persistent \u00bb impossible pour la p\u00e9riode de {} {}-{} : il faut au moins 3 cartes LULC (hors ann\u00e9es diagnostiques) ; trouv\u00e9es : {}.".format(nm, y0_, y1_, ", ".join(map(str, persist_dates(common["lulc_files"], y0_, y1_)))))
    root = common["out_root"]
    out_b, out_m, out_f = (os.path.join(root, d) for d in ("1_Baseline_{}_{}".format(*b), "2_Monitoring_{}_{}".format(*m), "3_UNCCD_Final"))
    for d in (out_b, out_m, out_f):
        ensure_dir(d)
    def cfg_for(period, inp, out, **extra):
        rain_f, main_f = find_lpd_pair(inp["lpd_dir"])
        c = {"lulc_dir": common["lulc_dir"], "lulc_files": common["lulc_files"], "lpd_rain": rain_f, "lpd_main": main_f, "soc_file": inp["soc_file"], "y0": period[0], "y1": period[1], "matrix_file": common["matrix_file"], "out_root": out,
             "primary_lc_variant": common["primary_lc_variant"], "primary_rain": common["primary_rain"], "primary_soc": common["primary_soc"], "excl_water": common["excl_water"], "quiet": True}
        c.update(extra)
        return c
    log("=" * 78 + "\nP\u00c9RIODE DE BASE {}-{}\n".format(*b) + "=" * 78)
    res_b = main(cfg_for(b, base_in, out_b, return_baseline=True))
    log("=" * 78 + "\nP\u00c9RIODE DE SUIVI {}-{}\n".format(*m) + "=" * 78)
    res_m = main(cfg_for(m, mon_in, out_m, baseline_by=res_b.pop("baseline_by")))
    params = {"Land-cover matrix variant (main)": common["primary_lc_variant"], "Rain-adjusted productivity (main)": common["primary_rain"], "SOC included (main)": common["primary_soc"], "Open water excluded": common["excl_water"],
              "Baseline period": "{}-{}".format(*b), "Monitoring period": "{}-{}".format(*m)}
    inputs = [{"label": "Baseline: LPD folder", "path": find_lpd_pair(base_in["lpd_dir"])[0]}, {"label": "Baseline: SOC class", "path": base_in["soc_file"]}, {"label": "Monitoring: LPD folder", "path": find_lpd_pair(mon_in["lpd_dir"])[0]},
              {"label": "Monitoring: SOC class", "path": mon_in["soc_file"]}, {"label": "Land-cover transition matrix", "path": common["matrix_file"]}]
    path = unccd_final_report(out_f, res_b, res_m, params, inputs, AREA_NAME, lang, log)
    return {"baseline": res_b, "monitoring": res_m, "final_dir": out_f, "report": path, "dirs": {"base": out_b, "mon": out_m, "final": out_f}}


def build_windows():
    """Les DEUX fen\u00eatres successives : (1) donn\u00e9es communes + p\u00e9riode de BASE ; (2) p\u00e9riode de SUIVI + options + calcul. PyQt est import\u00e9 ici pour que le reste reste importable sans QGIS."""
    from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog, QComboBox, QGroupBox

    def field(lay, owner, label, le, kind, flt="Raster (*.tif)"):
        box = QGroupBox(label)
        h = QHBoxLayout(box)
        h.addWidget(le, 1)
        b = QPushButton("Parcourir\u2026")
        def pick(_c=False, le_=le, k=kind):
            if k == "dir":
                p = QFileDialog.getExistingDirectory(owner, "Dossier", le_.text() or "")
            else:
                p, _f = QFileDialog.getOpenFileName(owner, "Fichier", le_.text() or "", flt)
            if p:
                le_.setText(p)
        b.clicked.connect(pick)
        h.addWidget(b)
        lay.addWidget(box)

    class Win1(QDialog):
        """FEN\u00caTRE 1/2 : donn\u00e9es communes et p\u00e9riode de BASE."""
        def __init__(self):
            super().__init__(None)
            self.setWindowTitle("ODD 15.3.1 \u2014 fen\u00eatre 1/2 : p\u00e9riode de BASE")
            self.resize(880, 640)
            lay = QVBoxLayout(self)
            lay.addWidget(QLabel("<b>Fen\u00eatre 1/2 \u2014 donn\u00e9es communes et p\u00e9riode de BASE</b> (UNCCD : p\u00e9riode de r\u00e9f\u00e9rence, ex. 1999 \u2192 2015). La fen\u00eatre 2 demandera la p\u00e9riode de SUIVI (ex. 2015 \u2192 2025)."))
            self.le_lulc, self.le_matrix, self.le_lpd, self.le_soc, self.le_out = QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit()
            field(lay, self, "1. Dossier des cartes LULC (LULC_<ZONE>_<ann\u00e9e>.tif) \u2014 communes aux deux p\u00e9riodes", self.le_lulc, "dir")
            field(lay, self, "2. Matrice de transition de la couverture (CSV D/S/I, d\u00e9cision NATIONALE) \u2014 commune aux deux p\u00e9riodes", self.le_matrix, "file", "CSV (*.csv)")
            field(lay, self, "3. LPD de la p\u00e9riode de BASE : dossier 03_LPD (\u00e9tape 02 avec LPD_PERIOD = \"baseline\")", self.le_lpd, "dir")
            field(lay, self, "4. SOC de la p\u00e9riode de BASE : SOC_Class_<d\u00e9but>_<fin>.tif (ex. SOC_Class_1999_2015.tif)", self.le_soc, "file")
            field(lay, self, "5. Dossier de SORTIE (trois sous-dossiers : 1_Baseline, 2_Monitoring, 3_UNCCD_Final)", self.le_out, "dir")
            self.lbl_err = QLabel("")
            self.lbl_err.setWordWrap(True)
            lay.addWidget(self.lbl_err)
            bt = QHBoxLayout()
            tp, nx, cn = QPushButton("Cr\u00e9er un mod\u00e8le de matrice"), QPushButton("Suivant \u2192"), QPushButton("Annuler")
            tp.clicked.connect(self.make_template)
            nx.clicked.connect(self.on_next)
            cn.clicked.connect(self.reject)
            bt.addWidget(tp)
            bt.addStretch(1)
            bt.addWidget(nx)
            bt.addWidget(cn)
            lay.addLayout(bt)
            self.settings = None

        def make_template(self):
            out = self.le_out.text().strip()
            if not out or not os.path.isdir(out):
                self.lbl_err.setText("Choisissez d'abord le dossier de sortie (5) : le mod\u00e8le y sera \u00e9crit.")
                return
            tpl = write_lc_matrix_template(os.path.join(out, "LC_Transition_Matrix_TEMPLATE.csv"))
            self.lbl_err.setText("Mod\u00e8le \u00e9crit : {} \u2014 remplissez effect_strict / effect_robust (D, S ou I), justifiez chaque D ou I, puis choisissez-le en (2).".format(tpl))

        def on_next(self):
            errs, files, per, lpd = [], None, None, None
            lulc, matrix_, lpd_d, soc, out = (w.text().strip() for w in (self.le_lulc, self.le_matrix, self.le_lpd, self.le_soc, self.le_out))
            if not lulc or not os.path.isdir(lulc):
                errs.append("Dossier des cartes LULC introuvable (1).")
            if not matrix_ or not os.path.exists(matrix_):
                errs.append("Matrice de transition introuvable (2) : la d\u00e9gradation par transition est une D\u00c9CISION NATIONALE, rien n'est invent\u00e9 (bouton \u00ab Cr\u00e9er un mod\u00e8le \u00bb).")
            if not out or not os.path.isdir(out):
                errs.append("Dossier de sortie introuvable (5).")
            try:
                lpd = find_lpd_pair(lpd_d) if (lpd_d and os.path.isdir(lpd_d)) else None
                if lpd is None:
                    errs.append("Dossier LPD de la base introuvable (3).")
            except RuntimeError as e:
                errs.append(str(e))
            try:
                per = parse_period_from_soc(soc) if (soc and os.path.exists(soc)) else None
                if per is None:
                    errs.append("SOC de la p\u00e9riode de base introuvable (4).")
                else:
                    assert_class_values(soc, {-1, 0, 1}, {127, -9999, 255}, "SOC (base)")
            except RuntimeError as e:
                errs.append(str(e))
            if lulc and os.path.isdir(lulc) and not errs:
                try:
                    files = resolve_lulc_files(lulc)
                except RuntimeError as e:
                    errs.append(str(e))
            if errs:
                self.lbl_err.setText("<span style='color:#c62828'>" + "<br>".join("\u2022 " + x for x in errs) + "</span>")
                return
            self.settings = {"lulc_dir": lulc, "lulc_files": files, "matrix_file": matrix_, "out_root": out, "base": {"lpd_dir": lpd_d, "soc_file": soc}, "base_period": per}
            self.accept()

    class Win2(QDialog):
        """FEN\u00caTRE 2/2 : p\u00e9riode de SUIVI, options, calcul."""
        def __init__(self, s1):
            super().__init__(None)
            self.s1 = s1
            self.setWindowTitle("ODD 15.3.1 \u2014 fen\u00eatre 2/2 : p\u00e9riode de SUIVI")
            self.resize(880, 640)
            lay = QVBoxLayout(self)
            lay.addWidget(QLabel("<b>Fen\u00eatre 2/2 \u2014 p\u00e9riode de SUIVI</b>. Base : {}\u2013{}. Le suivi doit COMMENCER en {}.".format(s1["base_period"][0], s1["base_period"][1], s1["base_period"][1])))
            self.le_lpd, self.le_soc = QLineEdit(), QLineEdit()
            field(lay, self, "6. LPD de la p\u00e9riode de SUIVI : dossier 03_LPD (\u00e9tape 02 avec LPD_PERIOD = \"monitoring\")", self.le_lpd, "dir")
            field(lay, self, "7. SOC de la p\u00e9riode de SUIVI : SOC_Class_<d\u00e9but>_<fin>.tif (ex. SOC_Class_2015_2025.tif)", self.le_soc, "file")
            self.cb_lc, self.cb_prod, self.cb_soc, self.cb_water, self.cb_lang = QComboBox(), QComboBox(), QComboBox(), QComboBox(), QComboBox()
            for cb, items, label in ((self.cb_lc, ["robust", "strict", "persistent"], "Matrice de couverture du sc\u00e9nario PRINCIPAL (persistent = matrice stricte filtr\u00e9e par la persistance, \u2265 3 cartes par p\u00e9riode)"),
                                     (self.cb_prod, ["corrig\u00e9e de la pluie", "non corrig\u00e9e"], "Productivit\u00e9 du sc\u00e9nario principal"), (self.cb_soc, ["inclure", "exclure"], "SOC dans le sc\u00e9nario principal"),
                                     (self.cb_water, ["exclure l'eau", "inclure l'eau"], "Eau dans la surface terrestre"), (self.cb_lang, ["English (publication)", "Fran\u00e7ais"], "Langue des rapports")):
                box = QGroupBox(label)
                hh = QHBoxLayout(box)
                cb.addItems(items)
                hh.addWidget(cb)
                lay.addWidget(box)
            self.lbl_err = QLabel("")
            self.lbl_err.setWordWrap(True)
            lay.addWidget(self.lbl_err)
            bt = QHBoxLayout()
            go, cn = QPushButton("\u25b6 Calculer base + suivi"), QPushButton("Annuler")
            go.clicked.connect(self.on_go)
            cn.clicked.connect(self.reject)
            bt.addStretch(1)
            bt.addWidget(go)
            bt.addWidget(cn)
            lay.addLayout(bt)
            self.settings = None

        def on_go(self):
            errs = []
            lpd_d, soc = self.le_lpd.text().strip(), self.le_soc.text().strip()
            mon = None
            try:
                if not (lpd_d and os.path.isdir(lpd_d)):
                    errs.append("Dossier LPD du suivi introuvable (6).")
                else:
                    find_lpd_pair(lpd_d)
                if not (soc and os.path.exists(soc)):
                    errs.append("SOC de la p\u00e9riode de suivi introuvable (7).")
                else:
                    mon = parse_period_from_soc(soc)
                    assert_class_values(soc, {-1, 0, 1}, {127, -9999, 255}, "SOC (suivi)")
                    validate_periods(self.s1["base_period"], mon)
            except RuntimeError as e:
                errs.append(str(e))
            variant = self.cb_lc.currentText()
            if variant == "persistent" and mon:
                for nm, (a, b2) in (("base", self.s1["base_period"]), ("suivi", mon)):
                    d = persist_dates(self.s1["lulc_files"], a, b2)
                    if len(d) < 3:
                        errs.append("Variante \u00ab persistent \u00bb impossible pour la p\u00e9riode de {} {}-{} : il faut au moins 3 cartes LULC (hors ann\u00e9es diagnostiques), trouv\u00e9es : {}.".format(nm, a, b2, ", ".join(map(str, d))))
            if errs:
                self.lbl_err.setText("<span style='color:#c62828'>" + "<br>".join("\u2022 " + x for x in errs) + "</span>")
                return
            s1 = self.s1
            self.settings = {"common": {"lulc_dir": s1["lulc_dir"], "lulc_files": s1["lulc_files"], "matrix_file": s1["matrix_file"], "out_root": s1["out_root"], "primary_lc_variant": variant,
                                        "primary_rain": self.cb_prod.currentText().startswith("corrig"), "primary_soc": self.cb_soc.currentText() == "inclure", "excl_water": self.cb_water.currentText().startswith("exclur")},
                             "base": s1["base"], "mon": {"lpd_dir": lpd_d, "soc_file": soc}, "lang": "en" if self.cb_lang.currentIndex() == 0 else "fr"}
            self.accept()

    return Win1, Win2


def run_all():
    """Point d'entr\u00e9e : les deux fen\u00eatres (TWO_WINDOW_MODE = True, d\u00e9faut) ou l'ancien mode \u00e0 bo\u00eetes de dialogue successives (False : une seule p\u00e9riode)."""
    if not TWO_WINDOW_MODE:
        return main()
    Win1, Win2 = build_windows()
    w1 = Win1()
    if not (w1.exec_() if hasattr(w1, "exec_") else w1.exec()) or not w1.settings:
        print("Annul\u00e9 : aucune sortie.")
        return None
    w2 = Win2(w1.settings)
    if not (w2.exec_() if hasattr(w2, "exec_") else w2.exec()) or not w2.settings:
        print("Annul\u00e9 : aucune sortie.")
        return None
    st = w2.settings
    res = run_two_periods(st["common"], st["base"], st["mon"], st["lang"])
    QMessageBox.information(None, "ODD 15.3.1 \u2014 base et suivi termin\u00e9s", "Rapport FINAL :\n{}\n\nBase : {}\nSuivi : {}".format(res["report"], res["dirs"]["base"], res["dirs"]["mon"]))
    try:
        from qgis.PyQt.QtCore import QUrl
        from qgis.PyQt.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(res["report"]))
    except Exception:
        pass
    return res


if AUTO_RUN:
    try:
        run_all()
    except Exception as exc:
        msg = "Int\u00e9gration 15.3.1 - \u00e9chec.\n\n" + str(exc) + "\n\n" + traceback.format_exc()
        print(msg)
        try:
            QMessageBox.critical(None, "Erreur int\u00e9gration 15.3.1", msg)
        except Exception:
            pass
