# -*- coding: utf-8 -*-
# SDG 15.3.1 REFERENCE PIPELINE — STAGE 01B / 08 : Annual productivity index for the drought decision — QGIS
"""
ÉTAPE 01B — INDICE DE PRODUCTIVITÉ ANNUEL (Productivity_Index_By_Year.csv) À PARTIR D'UN RASTER MULTI-BANDES   |   QGIS / PyQGIS
(à coller dans la Console Python de QGIS ou à exécuter depuis l'éditeur)

À QUOI SERT LE FICHIER PRODUIT
  Il alimente l'étape 04B (champ « Indice de productivité par année ») : il permet de distinguer une SÉCHERESSE CONFIRMÉE PAR LA VÉGÉTATION (année parmi les 25 % les plus basses) d'un simple DÉFICIT DE PLUIE.
  Il n'entre dans AUCUN calcul de LPD ni de matrice : c'est un indicateur de contexte pour décider d'exclure ou non une année.

ENTRÉE : le raster d'export Google Earth Engine d'une série annuelle (une bande par année : Annual_Productivity_1985_2025-....tif). Si l'export a été découpé en dalles
         (suffixes -0000000000-0000000000, -0000000000-0000010240 ...), choisissez UNE dalle : les autres du même dossier et du même préfixe sont lues automatiquement.
         Les années sont lues dans le nom des bandes (productivity_1999) ; à défaut, la première bande = ANNÉE DE DÉPART demandée.

MÉTHODE (documentée, reproductible)
  1. Échantillon STABLE de pixels : ceux qui ont une valeur valide dans au moins 80 % des années (même population chaque année : on ne compare pas des années calculées sur des surfaces différentes).
  2. Indice d'un pixel et d'une année = valeur / moyenne de ce pixel sur ses années valides (ratio à la normale du pixel).
  3. Indice de l'année = moyenne spatiale de ces ratios sur les pixels valides cette année-là ; COUVERTURE = part de l'échantillon stable valide cette année-là. Une année couverte à moins de 50 % reçoit un indice VIDE
     (non classée) au lieu d'un indice biaisé par une surface partielle.
  4. Si le CSV de pluie journalière (ClimateEngine / CHIRPS) est fourni : pluie de la saison sept(a-1)–mai(a), droite de régression indice ~ pluie, RÉSIDU = indice - valeur prédite.

LIMITES (à lire)
  - Une série multi-capteurs (Landsat 5, 7, 8, 9) contient des écarts systématiques de NDVI entre capteurs : le rang d'une année peut refléter le capteur autant que le climat. Le rapport signale les sauts brusques entre années consécutives.
  - Ce n'est PAS identique à un ancien fichier du même nom (définition d'origine non documentée) : seul l'ordre des années compte pour l'étape 04B.
  - Une série MODIS (étape 01) ne commence qu'en 2000 : elle ne couvre pas 1999.
"""
import os
import re
import csv
import json
import time
import math
import datetime
import calendar
import platform
import traceback
import numpy as np

AREA_NAME = "Oum El Bouaghi (Algeria)"
REPORT_LANG = "en"
MIN_VALID_YEAR_FRACTION = 0.80      # un pixel est retenu s'il est valide dans au moins cette part des années
MIN_COVERAGE_PCT = 50.0             # sous cette couverture (% de l'échantillon stable), l'indice de l'année est laissé vide
JUMP_FLAG = 0.15                    # saut entre deux années consécutives au-delà duquel un changement de capteur est suspecté
BLOCK = 512                         # taille des blocs de lecture (pixels)
RAIN_WINDOW = (9, 5)                # pluie de septembre (année a-1) à mai (année a)

# ============================================================================
# 1. LOGIQUE PURE (testée sans QGIS)
# ============================================================================
def accumulate_block(stack, min_valid_years):
    """
    stack : tableau (années, h, w) avec NaN pour les valeurs invalides. Retourne les cumuls ADDITIFS d'un bloc :
      sum_ratio[année], count[année] (pixels retenus et valides cette année-là), sum_value[année], n_included (pixels de l'échantillon stable).
    Le ratio d'un pixel ne dépend que de ses propres années : les blocs et les dalles s'additionnent sans erreur.
    """
    S = np.asarray(stack, np.float64)
    valid = np.isfinite(S)
    nv = valid.sum(axis=0)
    inc = nv >= min_valid_years
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(inc, np.nanmean(np.where(valid, S, np.nan), axis=0), np.nan)
        ok = valid & inc[None, :, :] & (mean[None, :, :] > 0)
        ratio = np.where(ok, S / mean[None, :, :], 0.0)
    return {"sum_ratio": ratio.sum(axis=(1, 2)), "count": ok.sum(axis=(1, 2)).astype(np.int64), "sum_value": np.where(ok, S, 0.0).sum(axis=(1, 2)), "n_included": int(inc.sum())}


def merge_acc(a, b):
    if a is None:
        return b
    return {"sum_ratio": a["sum_ratio"] + b["sum_ratio"], "count": a["count"] + b["count"], "sum_value": a["sum_value"] + b["sum_value"], "n_included": a["n_included"] + b["n_included"]}


def ols_residuals(x, y):
    """Droite y ~ x sur les paires finies ; retourne (pente, ordonnée, R², résidus alignés sur y ; NaN là où x ou y manque)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    res = np.full(y.shape, np.nan)
    if m.sum() < 3 or np.ptp(x[m]) == 0:
        return float("nan"), float("nan"), float("nan"), res
    b, a = np.polyfit(x[m], y[m], 1)
    pred = a + b * x[m]
    res[m] = y[m] - pred
    ss_res, ss_tot = float(np.sum((y[m] - pred) ** 2)), float(np.sum((y[m] - y[m].mean()) ** 2))
    return float(b), float(a), (1 - ss_res / ss_tot) if ss_tot > 0 else float("nan"), res


def finalize(acc, years, rain=None, min_coverage=MIN_COVERAGE_PCT):
    """Lignes par année : year, rain_mm, index_tous (vide sous la couverture minimale), n_tous, residual_tous, coverage_pct, mean_value."""
    n_inc = max(acc["n_included"], 1)
    cnt = acc["count"].astype(float)
    cov = 100.0 * cnt / n_inc
    idx = np.where(cnt > 0, acc["sum_ratio"] / np.maximum(cnt, 1), np.nan)
    mean_v = np.where(cnt > 0, acc["sum_value"] / np.maximum(cnt, 1), np.nan)
    idx_ok = np.where(cov >= min_coverage, idx, np.nan)
    rain_arr = np.array([(rain or {}).get(y, np.nan) for y in years], float)
    slope, icpt, r2, res = ols_residuals(rain_arr, idx_ok)
    rows = [{"year": int(y), "rain_mm": rain_arr[i], "index_tous": idx_ok[i], "n_tous": int(cnt[i]), "residual_tous": res[i], "coverage_pct": cov[i], "mean_value": mean_v[i], "index_all": idx[i]} for i, y in enumerate(years)]
    return rows, {"slope": slope, "intercept": icpt, "r2": r2, "n_included": acc["n_included"]}


def sensor_jumps(rows, flag=JUMP_FLAG):
    """Sauts brusques d'indice entre années consécutives (ratios proches de 1) : [(année précédente, année, écart)] ; indice de changement possible de capteur ou de couverture."""
    out = []
    ok = [r for r in rows if r["index_tous"] == r["index_tous"]]
    for a, b in zip(ok, ok[1:]):
        if b["year"] - a["year"] == 1 and abs(b["index_tous"] - a["index_tous"]) >= flag:
            out.append((a["year"], b["year"], b["index_tous"] - a["index_tous"]))
    return out


def csv_text(rows):
    """CSV lu par l'étape 04B (séparateur virgule, point décimal, UTF-8 avec BOM) : year, rain_mm, index_tous, n_tous, residual_tous + couverture et valeur moyenne."""
    def f(v, nd):
        return "" if (v is None or (isinstance(v, float) and v != v)) else f"{v:.{nd}f}"
    lines = ["year,rain_mm,index_tous,n_tous,residual_tous,coverage_pct,mean_value,index_all_years"]
    for r in rows:
        lines.append(",".join([str(r["year"]), f(r["rain_mm"], 1), f(r["index_tous"], 4), str(r["n_tous"]), f(r["residual_tous"], 4), f(r["coverage_pct"], 1), f(r["mean_value"], 4), f(r["index_all"], 4)]))
    return "\r\n".join(lines) + "\r\n"


def band_year_list(descriptions, start_year=None):
    """Années des bandes : lues dans les descriptions (productivity_1999 ...) ; sinon start_year + rang. ValueError si impossible."""
    ys = []
    for i, d in enumerate(descriptions):
        m = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", str(d or ""))
        ys.append(int(m.group(1)) if m else None)
    if all(y is not None for y in ys) and len(set(ys)) == len(ys):
        return ys
    if start_year is None:
        raise ValueError("Les bandes n'ont pas d'année dans leur nom : indiquez l'année de la première bande.")
    return [int(start_year) + i for i in range(len(descriptions))]


def tile_family(path):
    """Dalles d'un même export GEE : mêmes dossier et préfixe (avant le premier « -000… »)."""
    folder, base = os.path.split(path)
    m = re.match(r"^(.*?)-\d{10}-\d{10}\.tif$", base, re.I)
    if not m:
        return [path]
    pre = m.group(1)
    return sorted(os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".tif") and re.match(re.escape(pre) + r"-\d{10}-\d{10}\.tif$", f, re.I))


def parse_chirps_csv(path):
    """Pluie journalière {date: mm} depuis un CSV ClimateEngine (« ; », virgule décimale, une ligne d'en-tête)."""
    daily = {}
    with open(path, encoding="utf-8-sig") as f:
        for ln in f.read().splitlines()[1:]:
            ln = ln.strip().replace('"', "")
            if not ln:
                continue
            p = ln.split(";")
            if len(p) < 2:
                raise ValueError(f"Format CSV pluie non reconnu (ligne « {ln[:40]} »).")
            try:
                daily[datetime.date.fromisoformat(p[0].strip())] = float(p[1].strip().replace(",", "."))
            except ValueError:
                raise ValueError(f"Format CSV pluie non reconnu (ligne « {ln[:40]} »).")
    if len(daily) < 365 * 10:
        raise ValueError("Le CSV de pluie contient moins de 10 ans de données journalières.")
    return daily


def window_total(daily, year, m0, m1, min_cover=0.95):
    start = datetime.date(year - 1 if m0 > m1 else year, m0, 1)
    end = datetime.date(year, m1, calendar.monthrange(year, m1)[1])
    n = (end - start).days + 1
    vals = [daily[d] for d in (start + datetime.timedelta(days=i) for i in range(n)) if d in daily]
    return sum(vals) if len(vals) >= min_cover * n else None


def rain_by_year(daily, years, window=RAIN_WINDOW):
    return {y: v for y, v in ((y, window_total(daily, y, *window)) for y in years) if v is not None}


# ============================================================================
# 2. RAPPORT HTML D'ÉTAPE (bloc partagé : voir tools/sdg_stage_report.py)
# ============================================================================
PIPELINE_BUILD = "2026.10-74e07a6eec71"
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


def index_figure(rows, png_path, lang="en"):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None
    ys = [r["year"] for r in rows]
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ax.bar(ys, [r["index_all"] if r["index_all"] == r["index_all"] else 0 for r in rows], color=["#b0bec5" if not (r["index_tous"] == r["index_tous"]) else "#1565c0" for r in rows])
    ax.axhline(1.0, color="black", linewidth=0.8, linestyle=":")
    ax.set_ylabel("productivity index (ratio to the pixel's own mean)" if lang == "en" else "indice de productivité (ratio à la moyenne du pixel)")
    ax.set_title(("Annual productivity index (grey = coverage below the minimum: not ranked)" if lang == "en" else "Indice annuel de productivité (gris = couverture sous le minimum : non classé)"))
    rn = [r["rain_mm"] for r in rows]
    if any(v == v for v in rn):
        ax2 = ax.twinx()
        ax2.plot(ys, rn, color="#ef6c00", marker="o", linewidth=1.2)
        ax2.set_ylabel("rain (mm)" if lang == "en" else "pluie (mm)")
    os.makedirs(os.path.dirname(png_path), exist_ok=True)
    fig.savefig(png_path, dpi=110, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return png_path


def index_stage_report(out_dir, rows, fit, jumps, t0, params, inputs, area_name, lang="en", log=print):
    T = lambda a, b: a if lang == "en" else b
    ranked = [r for r in rows if r["index_tous"] == r["index_tous"]]
    low = [r["year"] for r in rows if not (r["index_tous"] == r["index_tous"])]
    order = sorted(ranked, key=lambda r: r["index_tous"])
    summary = [T(f"{len(ranked)} of {len(rows)} years ranked ({rows[0]['year']}–{rows[-1]['year']}); stable sample: {fit['n_included']:,} pixels", f"{len(ranked)} années sur {len(rows)} classées ({rows[0]['year']}–{rows[-1]['year']}) ; échantillon stable : {fit['n_included']:,} pixels"),
               T("Lowest productivity: " + ", ".join(f"{r['year']} ({r['index_tous']:.3f})" for r in order[:5]), "Productivité la plus basse : " + ", ".join(f"{r['year']} ({r['index_tous']:.3f})" for r in order[:5]))]
    checks = [(T("Years with enough coverage to be ranked", "Années assez couvertes pour être classées"), "PASS" if not low else "WARN", T("all years ranked", "toutes les années classées") if not low else T(f"not ranked (coverage below {MIN_COVERAGE_PCT:.0f} %): ", f"non classées (couverture sous {MIN_COVERAGE_PCT:.0f} %) : ") + ", ".join(map(str, low))),
              (T("Stable pixel sample", "Échantillon stable de pixels"), "PASS" if fit["n_included"] > 0 else "FAIL", f"{fit['n_included']:,} px (≥ {100 * MIN_VALID_YEAR_FRACTION:.0f} % valid years)")]
    if fit["r2"] == fit["r2"]:
        checks.append((T("Relationship with rainfall", "Relation avec la pluie"), "PASS" if fit["r2"] >= 0.2 else "WARN", T(f"R² = {fit['r2']:.2f} (slope {fit['slope']:.5f} per mm): a weak link means the index reflects sensors or land use more than rainfall", f"R² = {fit['r2']:.2f} (pente {fit['slope']:.5f} par mm) : un lien faible signifie que l'indice reflète les capteurs ou l'usage du sol plus que la pluie")))
    else:
        checks.append((T("Relationship with rainfall", "Relation avec la pluie"), "INFO", T("no rainfall file: no residual", "pas de fichier de pluie : pas de résidu")))
    checks.append((T("Abrupt jumps between consecutive years (possible sensor change)", "Sauts brusques entre années consécutives (changement de capteur possible)"), "PASS" if not jumps else "WARN",
                   T("none", "aucun") if not jumps else ", ".join(f"{a}→{b} ({d:+.2f})" for a, b, d in jumps)))
    tb = [["year", "rain_mm", "index", "coverage_%", "n px", "residual", T("rank (1 = lowest)", "rang (1 = le plus bas)")]]
    rk = {r["year"]: i + 1 for i, r in enumerate(order)}
    for r in rows:
        f = lambda v, nd: "" if v != v else f"{v:.{nd}f}"
        tb.append([r["year"], f(r["rain_mm"], 0), f(r["index_tous"], 4), f(r["coverage_pct"], 1), f"{r['n_tous']:,}", f(r["residual_tous"], 4), rk.get(r["year"], T("not ranked", "non classée"))])
    png = index_figure(rows, os.path.join(out_dir, "_temp", "index.png"), lang)
    sections = [{"id": "idx", "title": T("Annual productivity index", "Indice annuel de productivité"), "intro": T("Index = mean over the stable pixels of (value / the pixel's own mean). Years covered below the minimum are left blank so that they are not ranked on a partial area.", "Indice = moyenne, sur les pixels de l'échantillon stable, de (valeur / moyenne propre du pixel). Les années sous la couverture minimale sont laissées vides pour ne pas être classées sur une surface partielle."),
                 "tables": [(T("Index by year", "Indice par année"), tb)], "images": [(T("Index and rainfall", "Indice et pluie"), png)]}]
    L = [T("A multi-sensor series (Landsat 5/7/8/9) has systematic NDVI differences between sensors: the rank of a year can reflect the sensor as much as the climate.", "Une série multi-capteurs (Landsat 5/7/8/9) a des écarts systématiques de NDVI entre capteurs : le rang d'une année peut refléter le capteur autant que le climat."),
         T("The index is not identical to any older file of the same name; only the order of the years matters for stage 04B.", "L'indice n'est identique à aucun ancien fichier du même nom ; seul l'ordre des années compte pour l'étape 04B."),
         T("A MODIS series (stage 01) only starts in 2000 and cannot give 1999.", "Une série MODIS (étape 01) ne commence qu'en 2000 et ne peut donner 1999.")]
    A = [T("Export the annual productivity stack of the new area from Google Earth Engine (one band per year, band names containing the year).", "Exporter depuis Google Earth Engine la pile de productivité annuelle de la nouvelle zone (une bande par année, nom de bande contenant l'année)."),
         T("Provide the daily rainfall CSV of the area to obtain the rainfall and residual columns.", "Fournir le CSV de pluie journalière de la zone pour obtenir les colonnes pluie et résidu."), T("Give the CSV to stage 04B (field 5).", "Donner le CSV à l'étape 04B (champ 5).")]
    R = ["Funk, C. et al. (2015). The climate hazards infrared precipitation with stations — a new environmental record for monitoring extremes. Scientific Data 2, 150066.", "UNCCD. Good Practice Guidance for SDG Indicator 15.3.1 (version 2) and its Addendum."]
    spec = {"stage": "01B", "title": T("Annual productivity index", "Indice de productivité annuel"), "subtitle": T("Context for the drought decision (stage 04B)", "Contexte de la décision sur la sécheresse (étape 04B)"), "lang": lang, "area": area_name, "started": t0, "out_dir": out_dir,
            "params": params, "inputs": inputs, "summary": summary, "checks": checks, "sections": sections, "limits": L, "adapt": A, "references": R}
    path = os.path.join(out_dir, "Stage_Report_01B_Productivity_Index.html")
    write_stage_report(path, spec)
    import shutil
    shutil.rmtree(os.path.join(out_dir, "_temp"), ignore_errors=True)
    log("[Rapport HTML] " + path)
    return path


# ============================================================================
# 3. COUCHE GDAL / QGIS (relue, non exécutable hors QGIS)
# ============================================================================
def read_tile_blocks(path, start_year, block=BLOCK):
    """Itère (années, tableau (années, h, w) avec NaN pour les valeurs invalides) sur les blocs d'une dalle."""
    from osgeo import gdal
    ds = gdal.Open(path, gdal.GA_ReadOnly)
    if ds is None:
        raise RuntimeError(f"Raster illisible : {path}")
    years = band_year_list([ds.GetRasterBand(i + 1).GetDescription() for i in range(ds.RasterCount)], start_year)
    nds = [ds.GetRasterBand(i + 1).GetNoDataValue() for i in range(ds.RasterCount)]
    for yoff in range(0, ds.RasterYSize, block):
        h = min(block, ds.RasterYSize - yoff)
        for xoff in range(0, ds.RasterXSize, block):
            w = min(block, ds.RasterXSize - xoff)
            arr = np.empty((ds.RasterCount, h, w), np.float32)
            for i in range(ds.RasterCount):
                a = ds.GetRasterBand(i + 1).ReadAsArray(xoff, yoff, w, h).astype(np.float32)
                if nds[i] is not None:
                    a[a == nds[i]] = np.nan
                arr[i] = a
            yield years, arr


def compute_index(raster, start_year=None, rain_csv=None, out_dir=None, lang=REPORT_LANG, log=print, reader=None):
    t0 = time.time()
    reader = reader or read_tile_blocks
    tiles = tile_family(raster)
    acc, years = None, None
    for tpath in tiles:
        for yrs, arr in reader(tpath, start_year):
            years = years or yrs
            if yrs != years:
                raise RuntimeError("Les dalles n'ont pas les mêmes années en bandes.")
            acc = merge_acc(acc, accumulate_block(arr, math.ceil(MIN_VALID_YEAR_FRACTION * len(yrs))))
        log(f"[01B] dalle lue : {os.path.basename(tpath)}")
    if acc is None:
        raise RuntimeError("Aucun pixel lu.")
    rain = rain_by_year(parse_chirps_csv(rain_csv), years) if rain_csv else None
    rows, fit = finalize(acc, years, rain)
    out_dir = out_dir or os.path.dirname(raster)
    os.makedirs(out_dir, exist_ok=True)
    cpath = os.path.join(out_dir, "Productivity_Index_By_Year.csv")
    with open(cpath, "w", encoding="utf-8-sig", newline="") as f:
        f.write(csv_text(rows))
    jumps = sensor_jumps(rows)
    params = {"Minimum valid years per pixel": f"{100 * MIN_VALID_YEAR_FRACTION:.0f} %", "Minimum coverage to rank a year": f"{MIN_COVERAGE_PCT:.0f} %", "Rain window": "Sep(a-1)–May(a)" if rain else "(no rainfall file)", "Tiles read": len(tiles)}
    rep = index_stage_report(out_dir, rows, fit, jumps, t0, params, [{"label": "Annual productivity raster", "path": raster}] + ([{"label": "Daily rainfall", "path": rain_csv}] if rain_csv else []), AREA_NAME, lang, log)
    return cpath, rep


def _stop(msg):
    print("[Arrêt] " + msg)
    try:
        from qgis.PyQt.QtWidgets import QMessageBox
        QMessageBox.information(None, "01B", msg)
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
            QMessageBox.critical(None, "01B — erreur", tb[-1500:])
        except Exception:
            pass


def _main():
    from qgis.PyQt.QtWidgets import QFileDialog, QInputDialog, QMessageBox
    from qgis.PyQt.QtCore import QUrl
    ras, _f = QFileDialog.getOpenFileName(None, "01B — raster de productivité annuelle (Annual_Productivity_…tif ; une dalle suffit)", "", "GeoTIFF (*.tif *.tiff)")
    if not ras:
        return _stop("Annulé : aucun fichier produit.")
    start, ok = QInputDialog.getInt(None, "01B", "Année de la PREMIÈRE bande (utilisée seulement si les bandes n'ont pas d'année dans leur nom) :", 1985, 1972, 2100)
    if not ok:
        return _stop("Annulé.")
    rain, _f = QFileDialog.getOpenFileName(None, "01B — pluie journalière ClimateEngine.csv (facultatif : Annuler pour passer)", os.path.dirname(ras), "CSV (*.csv)")
    out = QFileDialog.getExistingDirectory(None, "01B — dossier de SORTIE", os.path.dirname(ras))
    if not out:
        return _stop("Annulé : aucun fichier produit.")
    cpath, rep = compute_index(ras, start, rain or None, out, REPORT_LANG)
    QMessageBox.information(None, "01B terminé", f"CSV : {cpath}\nRapport : {rep}\n\nDonnez ce CSV à l'étape 04B (champ 5).")
    try:
        from qgis.PyQt.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(rep))
    except Exception:
        pass


# ====================== MAIN ======================
main()
