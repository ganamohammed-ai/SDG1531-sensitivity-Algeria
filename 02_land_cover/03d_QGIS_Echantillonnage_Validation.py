# -*- coding: utf-8 -*-
# SDG 15.3.1 REFERENCE PIPELINE — STAGE 05A / 08 : Validation sampling design — QGIS
"""
ÉTAPE 05A — ÉCHANTILLONNAGE STRATIFIÉ ALÉATOIRE POUR LA VALIDATION DES CARTES LULC   |   QGIS / PyQGIS
(à coller dans la Console Python de QGIS ou à exécuter depuis l'éditeur)

CE QUE FAIT LE SCRIPT
  1. Détecte les cartes LULC_<ZONE>_<année>.tif d'un dossier (toutes les années, sans liste codée en dur).
  2. Pour CHAQUE année : tirage STRATIFIÉ ALÉATOIRE de points, les strates étant les classes CARTOGRAPHIÉES (Olofsson et al. 2014) :
        - n total par année (400 par défaut) ; minimum par classe (30) ; le reste réparti proportionnellement à la surface (méthode du plus fort reste) ;
        - une classe plus petite que son minimum est échantillonnée en totalité (et signalée).
  3. Écrit, par année : les points (GeoPackage + CSV) avec le champ Reference_Class VIDE (à remplir par un interprète INDÉPENDANT, sans voir la classe cartographiée),
     le plan d'échantillonnage (surface, poids W_h, effectif par strate) — nécessaire à l'étape 05B —, le protocole d'interprétation, et un RAPPORT HTML d'étape.
  4. Vérifie la taille de l'échantillon avec la formule d'Olofsson (n requis pour une erreur-type cible sur l'exactitude globale).

REPRODUCTIBILITÉ : graine aléatoire fixée (graine de base + année) et inscrite dans le rapport ; mêmes cartes + même graine = mêmes points.
AUTRE ZONE D'ÉTUDE : changer AREA_TAG (nom dans LULC_<AREA_TAG>_<année>.tif) et, si besoin, les noms de classes ; aucune autre modification.
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

AREA_TAG = "Oum_El_Bouaghi"                 # <-- seul réglage à changer pour une autre zone : LULC_<AREA_TAG>_<année>.tif
AREA_NAME = "Oum El Bouaghi (Algeria)"
REPORT_LANG = "en"                          # langue du rapport HTML : "en" ou "fr"
N_POINTS = 400                              # points par année
MIN_PER_CLASS = 30                          # minimum par strate
BASE_SEED = 2026
SE_TARGET_OA = 0.01                         # erreur-type visée sur l'exactitude globale (Olofsson et al. 2014)
ASSUMED_USER_ACCURACY = {1: 0.9, 2: 0.9, 3: 0.9, 4: 0.7, 5: 0.8, 6: 0.7, 7: 0.8, 8: 0.7}   # exactitudes a priori pour dimensionner l'échantillon (à remplacer par celles d'une étude pilote)
CLASS_NAMES = {1: "Built-up", 2: "Water", 3: "Sebkha", 4: "Bareland / Rock", 5: "Cropland", 6: "Fallow", 7: "Forest", 8: "Rangeland"}
CLASS_COLORS = {1: "#dc3232", 2: "#648cd2", 3: "#d6e6f5", 4: "#b9c3cd", 5: "#ffe182", 6: "#f0af00", 7: "#87b978", 8: "#64f58c"}
MAP_RE = re.compile(r"^LULC_(.+?)_((?:19|20)\d{2})\.tif$", re.I)
SKIP_NAME_PARTS = ("_Original", "_Edited", "_Retro", "_Corrige")
LABEL_FIELDS = ["Point_ID", "Year", "X", "Y", "Map_Class", "Class_Name", "Reference_Class", "Confidence", "Interpreter", "Notes"]
# Shapefile : les noms de champs sont limités à 10 caractères -> « Reference_Class » devient « Ref_Class » (l'étape 05B accepte les deux)
SHP_FIELDS = [("Point_ID", "C", 20, 0, "Point_ID"), ("Year", "N", 10, 0, "Year"), ("X", "N", 19, 3, "X"), ("Y", "N", 19, 3, "Y"), ("Map_Class", "N", 10, 0, "Map_Class"), ("Class_Name", "C", 40, 0, "Class_Name"),
              ("Ref_Class", "N", 10, 0, "Reference_Class"), ("Confidence", "C", 10, 0, "Confidence"), ("Analyst", "C", 40, 0, "Interpreter"), ("Notes", "C", 100, 0, "Notes")]

# ============================================================================
# 1. LOGIQUE PURE (testée sans QGIS)
# ============================================================================
def find_lulc_maps(folder, area_tag=None):
    """{année: chemin} : cartes LULC_<ZONE>_<année>.tif du dossier (et de son sous-dossier LULC/) ; copies _Original / _Edited / _Retro / _Corrige ignorées."""
    out = {}
    for d in (os.path.join(folder, "LULC"), folder):
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            m = MAP_RE.match(fn)
            if m and not any(p in fn for p in SKIP_NAME_PARTS) and (area_tag is None or m.group(1) == area_tag):
                out[m.group(2)] = os.path.join(d, fn)
    return dict(sorted(out.items(), key=lambda kv: int(kv[0])))


def allocate_points(class_counts, n_total=N_POINTS, min_per_class=MIN_PER_CLASS):
    """
    Répartition des points entre strates : minimum par classe, puis le reste proportionnel à la surface (plus fort reste) ; jamais plus de points que de pixels disponibles (le déficit est redistribué).
    Si les minimums dépassent n_total, répartition proportionnelle (au moins 1 par classe). Retourne {classe: n}.
    """
    active = [c for c in CLASS_NAMES if class_counts.get(c, 0) > 0]
    if not active:
        raise RuntimeError("Aucune classe valide dans la zone : rien à échantillonner.")
    alloc = {c: min(min_per_class, class_counts[c]) for c in active}
    if sum(alloc.values()) > n_total:
        tot = sum(class_counts[c] for c in active)
        alloc = {c: max(1, int(np.floor(n_total * class_counts[c] / tot))) for c in active}
        while sum(alloc.values()) > n_total:
            c = max(alloc, key=lambda x: alloc[x])
            if alloc[c] > 1:
                alloc[c] -= 1
            else:
                break
    remaining = n_total - sum(alloc.values())
    if remaining > 0:
        tot = sum(class_counts[c] for c in active)
        raw = {c: remaining * class_counts[c] / tot for c in active}
        fl = {c: int(np.floor(raw[c])) for c in active}
        for c in active:
            alloc[c] += fl[c]
        left = n_total - sum(alloc.values())
        order = sorted(active, key=lambda c: raw[c] - fl[c], reverse=True)
        i = 0
        while left > 0:
            alloc[order[i % len(order)]] += 1
            left -= 1
            i += 1
    for c in list(alloc):
        if alloc[c] > class_counts[c]:
            deficit = alloc[c] - class_counts[c]
            alloc[c] = class_counts[c]
            for t in sorted(active, key=lambda x: class_counts[x] - alloc[x], reverse=True):
                add = min(deficit, max(0, class_counts[t] - alloc[t]))
                alloc[t] += add
                deficit -= add
                if deficit <= 0:
                    break
    return alloc


def class_pixel_counts(arr, domain=None):
    a = np.asarray(arr)
    if domain is not None:
        a = a[np.asarray(domain, bool)]
    cnt = np.bincount(a.ravel().astype(np.int64), minlength=max(CLASS_NAMES) + 2)
    return {c: int(cnt[c]) for c in CLASS_NAMES if c < len(cnt)}


def sample_stratified(arr, alloc, seed, domain=None):
    """Tire, dans chaque classe, `alloc[classe]` pixels au hasard SANS remise. Retourne [(ligne, colonne, classe)] (ordre : classe puis tirage)."""
    a = np.asarray(arr)
    ok = (np.asarray(domain, bool) if domain is not None else np.ones(a.shape, bool))
    rng = np.random.default_rng(seed)
    out = []
    for c in sorted(alloc):
        n = alloc[c]
        if n <= 0:
            continue
        idx = np.flatnonzero((a == c) & ok)
        take = rng.choice(idx.size, size=min(n, idx.size), replace=False)
        rr, cc = np.divmod(idx[take], a.shape[1])
        out += [(int(r), int(k), c) for r, k in zip(rr, cc)]
    return out


def pixel_center(gt, row, col):
    return gt[0] + (col + 0.5) * gt[1] + (row + 0.5) * gt[2], gt[3] + (col + 0.5) * gt[4] + (row + 0.5) * gt[5]


def design_rows(year, counts, alloc, px_ha):
    """Plan d'échantillonnage : une ligne par strate (poids W_h = N_h / N)."""
    N = sum(counts.values())
    return [{"year": year, "class": c, "name": CLASS_NAMES[c], "mapped_px": counts[c], "mapped_ha": counts[c] * px_ha, "weight": (counts[c] / N) if N else 0.0, "n_allocated": alloc.get(c, 0)} for c in CLASS_NAMES if counts.get(c, 0) > 0]


def required_sample_size(weights, user_acc, se_target=SE_TARGET_OA):
    """
    Taille d'échantillon d'Olofsson et al. (2014, éq. 13) pour une erreur-type cible sur l'exactitude globale, en allocation proportionnelle :
    n = ( somme W_h S_h / S(O) )^2 avec S_h = sqrt(U_h (1 - U_h)). weights = {classe: W_h}, user_acc = {classe: U_h a priori}.
    """
    s = sum(w * math.sqrt(max(user_acc.get(c, 0.8) * (1 - user_acc.get(c, 0.8)), 1e-9)) for c, w in weights.items())
    return int(math.ceil((s / se_target) ** 2))


def points_records(year, sample, gt):
    """Enregistrements des points (Reference_Class vide)."""
    recs = []
    for i, (r, c, cl) in enumerate(sample, start=1):
        x, y = pixel_center(gt, r, c)
        recs.append({"Point_ID": f"{year}_{i:03d}", "Year": int(year), "X": round(x, 3), "Y": round(y, 3), "Map_Class": cl, "Class_Name": CLASS_NAMES[cl], "Reference_Class": "", "Confidence": "", "Interpreter": "", "Notes": ""})
    return recs


def dbf_bytes(fields, records):
    """Table dBASE III : fields = [(nom ≤ 10 car., type 'C'|'N', longueur, décimales, clé)], records = liste de dict. Valeur vide -> champ vide (NULL). Texte en UTF-8 (fichier .cpg)."""
    for nm, *_r in fields:
        if len(nm) > 10:
            raise ValueError(f"Nom de champ Shapefile trop long (max 10) : {nm}")
    hdr_len = 32 + 32 * len(fields) + 1
    rec_len = 1 + sum(f[2] for f in fields)
    t = time.localtime()
    head = bytes([3, t.tm_year - 1900, t.tm_mon, t.tm_mday]) + len(records).to_bytes(4, "little") + hdr_len.to_bytes(2, "little") + rec_len.to_bytes(2, "little") + bytes(20)
    desc = b""
    for nm, typ, ln, dec, _k in fields:
        desc += nm.encode("ascii").ljust(11, b"\x00") + typ.encode("ascii") + bytes(4) + bytes([ln, dec]) + bytes(14)
    body = b""
    for r in records:
        row = b" "
        for nm, typ, ln, dec, key in fields:
            v = r.get(key, "")
            if v is None or v == "":
                row += b" " * ln
            elif typ == "N":
                row += (f"{float(v):.{dec}f}" if dec else f"{int(round(float(v)))}").rjust(ln).encode("ascii")[-ln:]
            else:
                b = str(v).encode("utf-8")[:ln]
                row += b.ljust(ln, b" ")
        body += row
    return head + desc + b"\x0d" + body + b"\x1a"


def shp_shx_bytes(points):
    """(shp, shx) d'une couche de POINTS [(x, y), ...] au format ESRI Shapefile."""
    import struct
    n = len(points)
    xs, ys = [p[0] for p in points] or [0.0], [p[1] for p in points] or [0.0]
    bbox = struct.pack("<4d", min(xs), min(ys), max(xs), max(ys)) + struct.pack("<4d", 0, 0, 0, 0)
    def header(length_words):
        return struct.pack(">i", 9994) + bytes(20) + struct.pack(">i", length_words) + struct.pack("<ii", 1000, 1) + bbox
    shp_body, shx_body = b"", b""
    for i, (x, y) in enumerate(points):
        content = struct.pack("<i2d", 1, x, y)
        shx_body += struct.pack(">ii", (100 + len(shp_body)) // 2, len(content) // 2)
        shp_body += struct.pack(">ii", i + 1, len(content) // 2) + content
    return header((100 + len(shp_body)) // 2) + shp_body, header((100 + len(shx_body)) // 2) + shx_body


def write_point_shapefile(base_path, records, prj_wkt=None):
    """Écrit <base>.shp / .shx / .dbf / .cpg (et .prj si prj_wkt est fourni) : Shapefile de points directement lisible par ArcGIS Pro et QGIS, sans GDAL. Retourne la liste des fichiers."""
    os.makedirs(os.path.dirname(base_path) or ".", exist_ok=True)
    shp, shx = shp_shx_bytes([(float(r["X"]), float(r["Y"])) for r in records])
    out = {".shp": shp, ".shx": shx, ".dbf": dbf_bytes(SHP_FIELDS, records), ".cpg": b"UTF-8"}
    if prj_wkt:
        out[".prj"] = prj_wkt.encode("utf-8")
    for ext, data in out.items():
        with open(base_path + ext, "wb") as f:
            f.write(data)
    return [base_path + e for e in out]


def labeling_protocol(area_name, n_total, min_pc, seed):
    """Protocole d'interprétation (à joindre au rapport : une validation sans protocole n'est pas reproductible)."""
    return f"""# Reference-data protocol — {area_name}

1. **Blind interpretation.** The interpreter does NOT see the mapped class (hide Map_Class and Class_Name before labelling) and fills Reference_Class (1–8) for each point.
2. **Reference sources**: very-high-resolution imagery of the same year or the closest date (Google Earth / Bing / Planet), Sentinel-2 or Landsat time series (NDVI profile of the pixel), field data when available. State the source in Notes.
3. **Response design**: the reference label describes the dominant cover of the 30 m x 30 m pixel centred on the point (not the point itself). Mixed pixels: choose the majority cover; record Confidence = low.
4. **Classes** (same legend as the map): {', '.join(f'{k} {v}' for k, v in CLASS_NAMES.items())}.
5. **Drought / wet years**: label what is on the ground (e.g. a failed crop is 'Fallow' or 'Bareland' only if no crop is visible in the imagery), not what the map shows.
6. **Quality control**: a second interpreter re-labels at least 10 % of the points; disagreements are resolved by a third opinion; report the inter-interpreter agreement.
7. **Sample design**: {n_total} points per year, stratified by mapped class, minimum {min_pc} per class, random seed base {seed} + year.

8. **ArcGIS Pro / QGIS**: open `Shapefiles_ArcGIS/Validation_Points_<year>.shp`, fill the field `Ref_Class` (1–8; the field is `Reference_Class` in the GeoPackage and the CSV), and hide `Map_Class` and `Class_Name` while labelling (ArcGIS Pro: Fields view of the attribute table, untick them; QGIS: layer properties > Attributes Form). Save the edits; stage 05B reads the shapefiles directly.

After labelling, run stage 05B (accuracy assessment, Olofsson et al. 2014).
"""


# ============================================================================
# 2. RAPPORT HTML D'ÉTAPE (bloc partagé : voir tools/sdg_stage_report.py)
# ============================================================================
PIPELINE_BUILD = "2026.10-b71fa71eaf82"
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


def sampling_stage_report(out_dir, designs, sample_info, t0, params, inputs, area_name, lang="en", log=print):
    """Rapport HTML de l'étape 05A : plan d'échantillonnage par année, justification de la taille, protocole d'interprétation, carte des points."""
    en = lang == "en"
    T = lambda a, b: a if en else b
    summary, checks, sections = [], [], []
    hdr = [T("Class", "Classe"), T("Mapped area (ha)", "Surface cartographiée (ha)"), "W_h", T("Points allocated", "Points alloués"), T("Sampling fraction (px)", "Fraction d'échantillonnage (px)")]
    for y in sorted(designs):
        rows = designs[y]
        n_tot = sum(r["n_allocated"] for r in rows)
        W = {r["class"]: r["weight"] for r in rows}
        n_req = required_sample_size(W, ASSUMED_USER_ACCURACY, SE_TARGET_OA)
        small = [r["name"] for r in rows if r["mapped_px"] < MIN_PER_CLASS]
        summary.append(T(f"{y}: {n_tot} points in {len(rows)} strata; Olofsson sample size for SE(OA) = {SE_TARGET_OA:g}: n = {n_req}", f"{y} : {n_tot} points dans {len(rows)} strates ; taille d'Olofsson pour ET(exactitude globale) = {SE_TARGET_OA:g} : n = {n_req}"))
        checks.append((T(f"Sample size {y}", f"Taille d'échantillon {y}"), "PASS" if n_tot >= n_req else "WARN", T(f"{n_tot} points vs {n_req} required for SE(OA) = {SE_TARGET_OA:g} with the assumed accuracies", f"{n_tot} points contre {n_req} requis pour ET(OA) = {SE_TARGET_OA:g} avec les exactitudes supposées")))
        checks.append((T(f"Minimum per stratum {y}", f"Minimum par strate {y}"), "PASS" if not small else "WARN", T("every stratum has at least the minimum", "chaque strate atteint le minimum") if not small else T("whole stratum sampled for: ", "strate échantillonnée en totalité pour : ") + ", ".join(small)))
        tb = [hdr] + [[f"{r['class']} — {r['name']}", f"{r['mapped_ha']:,.1f}", f"{r['weight']:.5f}", r["n_allocated"], f"{(r['n_allocated'] / r['mapped_px']) if r['mapped_px'] else 0:.2e}"] for r in rows]
        imgs = [(T(f"Sampled points {y}", f"Points échantillonnés {y}"), sample_info[y]["png"])] if sample_info.get(y, {}).get("png") else []
        sections.append({"id": f"y{y}", "title": T(f"Sampling design {y}", f"Plan d'échantillonnage {y}"), "tables": [(T("Strata (mapped classes)", "Strates (classes cartographiées)"), tb)], "images": imgs,
                         "notes": [T(f"Random seed: {sample_info[y]['seed']}", f"Graine aléatoire : {sample_info[y]['seed']}")]})
    sections.append({"id": "protocol", "title": T("Reference-data protocol", "Protocole des données de référence"), "pre": labeling_protocol(area_name, N_POINTS, MIN_PER_CLASS, BASE_SEED)})
    L = [T("Stratifying by the MAPPED class is the standard design (Olofsson et al. 2014); it guarantees points in rare classes but the estimates must be weighted by W_h (done in stage 05B).", "Stratifier par la classe CARTOGRAPHIÉE est le plan standard (Olofsson et al. 2014) ; il garantit des points dans les classes rares mais les estimations doivent être pondérées par W_h (fait à l'étape 05B)."),
         T("The a-priori accuracies used to size the sample are assumptions; replace them with the values of a pilot study.", "Les exactitudes a priori utilisées pour dimensionner l'échantillon sont des hypothèses ; les remplacer par celles d'une étude pilote."),
         T("This design validates each year's MAP; estimating the area of CHANGE with confidence intervals needs a sample stratified by change class (Olofsson et al. 2014, section 5).", "Ce plan valide la CARTE de chaque année ; estimer la surface du CHANGEMENT avec intervalles de confiance exige un échantillon stratifié par classe de changement (Olofsson et al. 2014, section 5).")]
    A = [T("Set AREA_TAG (and AREA_NAME) at the top of the script to the tag used in LULC_<AREA_TAG>_<year>.tif.", "Régler AREA_TAG (et AREA_NAME) en tête de script sur l'étiquette utilisée dans LULC_<AREA_TAG>_<année>.tif."),
         T("Adapt CLASS_NAMES if the legend differs; keep the same legend in stages 03, 05B, 06 and 07.", "Adapter CLASS_NAMES si la légende diffère ; garder la même légende aux étapes 03, 05B, 06 et 07."),
         T("Choose N_POINTS and MIN_PER_CLASS from the sample-size check of this report (rare classes drive the cost).", "Choisir N_POINTS et MIN_PER_CLASS d'après le contrôle de taille de ce rapport (les classes rares font le coût).")]
    R = ["Olofsson, P., Foody, G.M., Herold, M., Stehman, S.V., Woodcock, C.E., Wulder, M.A. (2014). Good practices for estimating area and assessing accuracy of land change. Remote Sensing of Environment 148, 42–57.",
         "Stehman, S.V. (2009). Sampling designs for accuracy assessment of land cover. International Journal of Remote Sensing 30, 5243–5272."]
    spec = {"stage": "05A", "title": T("Validation sampling design", "Plan d'échantillonnage de validation"), "subtitle": T("Stratified random sampling by mapped class", "Échantillonnage aléatoire stratifié par classe cartographiée"), "lang": lang, "area": area_name, "started": t0, "out_dir": out_dir,
            "params": params, "inputs": inputs, "summary": summary, "checks": checks, "sections": sections, "limits": L, "adapt": A, "references": R}
    path = os.path.join(out_dir, "Stage_Report_05A_Sampling.html")
    write_stage_report(path, spec)
    log("[Rapport HTML] " + path)
    return path


# ============================================================================
# 3. COUCHE GDAL / QGIS (relue, non exécutable hors QGIS)
# ============================================================================
def write_csv(path, rows, fields):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def write_gpkg(path, layers, wkt):
    """GeoPackage de points : une couche par année (champs longs autorisés, contrairement au shapefile)."""
    from osgeo import ogr, osr
    drv = ogr.GetDriverByName("GPKG")
    if os.path.exists(path):
        drv.DeleteDataSource(path)
    ds = drv.CreateDataSource(path)
    srs = osr.SpatialReference()
    srs.ImportFromWkt(wkt)
    for year, recs in layers.items():
        lyr = ds.CreateLayer(f"points_{year}", srs, ogr.wkbPoint)
        for name, typ, width in (("Point_ID", ogr.OFTString, 20), ("Year", ogr.OFTInteger, 0), ("X", ogr.OFTReal, 0), ("Y", ogr.OFTReal, 0), ("Map_Class", ogr.OFTInteger, 0), ("Class_Name", ogr.OFTString, 40),
                                  ("Reference_Class", ogr.OFTInteger, 0), ("Confidence", ogr.OFTString, 10), ("Interpreter", ogr.OFTString, 40), ("Notes", ogr.OFTString, 200)):
            fd = ogr.FieldDefn(name, typ)
            if width:
                fd.SetWidth(width)
            lyr.CreateField(fd)
        for r in recs:
            ft = ogr.Feature(lyr.GetLayerDefn())
            for k in ("Point_ID", "Year", "X", "Y", "Map_Class", "Class_Name", "Confidence", "Interpreter", "Notes"):
                v = r[k]
                if v != "":
                    ft.SetField(k, v)
            pt = ogr.Geometry(ogr.wkbPoint)
            pt.AddPoint_2D(float(r["X"]), float(r["Y"]))
            ft.SetGeometry(pt)
            lyr.CreateFeature(ft)
    ds = None


def read_map(path):
    from osgeo import gdal
    ds = gdal.Open(path, gdal.GA_ReadOnly)
    if ds is None:
        raise RuntimeError(f"Carte illisible : {path}")
    arr = ds.GetRasterBand(1).ReadAsArray()
    return arr, ds.GetGeoTransform(), ds.GetProjection()


def admin_mask(shp_path, rows, cols, gt, wkt):
    from osgeo import gdal, ogr
    ds = ogr.Open(shp_path)
    if ds is None:
        raise RuntimeError(f"Zone d'étude illisible : {shp_path}")
    mem = gdal.GetDriverByName("MEM").Create("", cols, rows, 1, gdal.GDT_Byte)
    mem.SetGeoTransform(gt)
    mem.SetProjection(wkt)
    gdal.RasterizeLayer(mem, [1], ds.GetLayer(), burn_values=[1])
    return mem.GetRasterBand(1).ReadAsArray() == 1


def points_overview_png(arr, sample, png_path, title, max_px=1200):
    """Carte des classes avec les points tirés (contrôle visuel de la répartition spatiale)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.colors import ListedColormap
        from matplotlib.patches import Patch
    except Exception:
        return None
    a = np.asarray(arr)
    s = max(1, int(math.ceil(max(a.shape) / float(max_px))))
    cmap = ListedColormap(["#f7f7f7"] + [CLASS_COLORS[k] for k in sorted(CLASS_COLORS)])
    fig, ax = plt.subplots(figsize=(10, 7.5))
    ax.imshow(a[::s, ::s], cmap=cmap, vmin=0, vmax=len(CLASS_COLORS), interpolation="nearest")
    ax.scatter([c / s for _r, c, _k in sample], [r / s for r, _c, _k in sample], s=9, c="black", marker="o", edgecolors="white", linewidths=0.4)
    ax.legend(handles=[Patch(facecolor=CLASS_COLORS[k], label=f"{k} — {CLASS_NAMES[k]}") for k in sorted(CLASS_COLORS)], loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False, fontsize=8)
    ax.set_title(title)
    ax.set_xticks([])
    ax.set_yticks([])
    os.makedirs(os.path.dirname(png_path), exist_ok=True)
    fig.savefig(png_path, dpi=110, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return png_path


def run_sampling(maps, out_dir, n_points=N_POINTS, min_pc=MIN_PER_CLASS, base_seed=BASE_SEED, study=None, lang=REPORT_LANG, log=print):
    """Calcule et écrit tout (points, plan, protocole, rapport). maps = {année: chemin}."""
    t0 = time.time()
    os.makedirs(out_dir, exist_ok=True)
    layers, designs, info, all_rows = {}, {}, {}, []
    wkt = gt0 = None
    for y, p in maps.items():
        arr, gt, w = read_map(p)
        wkt, gt0 = wkt or w, gt0 or gt
        dom = admin_mask(study, arr.shape[0], arr.shape[1], gt, w) if study else None
        counts = class_pixel_counts(arr, dom)
        alloc = allocate_points(counts, n_points, min_pc)
        seed = base_seed + int(y)
        sample = sample_stratified(arr, alloc, seed, dom)
        recs = points_records(y, sample, gt)
        layers[y] = recs
        all_rows += recs
        px_ha = abs(gt[1] * gt[5] - gt[2] * gt[4]) / 10000.0
        designs[y] = design_rows(y, counts, alloc, px_ha)
        png = points_overview_png(arr, sample, os.path.join(out_dir, "_temp", f"points_{y}.png"), f"{y} — {len(sample)} points")
        info[y] = {"seed": seed, "png": png}
        log(f"[05A] {y} : {len(sample)} points ; " + ", ".join(f"{c}:{n}" for c, n in alloc.items()))
    write_gpkg(os.path.join(out_dir, "Validation_Points.gpkg"), layers, wkt)
    prj = None
    try:
        from osgeo import osr
        srs = osr.SpatialReference()
        srs.ImportFromWkt(wkt)
        srs.MorphToESRI()                                          # WKT « ESRI » : celui que ArcGIS Pro attend dans un .prj
        prj = srs.ExportToWkt()
    except Exception:
        prj = wkt
    shp_files = []
    for y, recs in layers.items():
        shp_files += write_point_shapefile(os.path.join(out_dir, "Shapefiles_ArcGIS", f"Validation_Points_{y}"), recs, prj)
    write_csv(os.path.join(out_dir, "Validation_Points_all.csv"), all_rows, LABEL_FIELDS)
    write_csv(os.path.join(out_dir, "Sampling_Design.csv"), [r for y in designs for r in designs[y]], ["year", "class", "name", "mapped_px", "mapped_ha", "weight", "n_allocated"])
    with open(os.path.join(out_dir, "Labeling_Protocol.md"), "w", encoding="utf-8") as f:
        f.write(labeling_protocol(AREA_NAME, n_points, min_pc, base_seed))
    params = {"Points per year": n_points, "Minimum per class": min_pc, "Base seed": base_seed, "SE target (OA)": SE_TARGET_OA, "Years": ", ".join(maps), "Study-area mask": study or "(whole map)"}
    inputs = [{"label": f"LULC {y}", "path": p} for y, p in maps.items()]
    rep = sampling_stage_report(out_dir, designs, info, t0, params, inputs, AREA_NAME, lang, log)
    import shutil
    shutil.rmtree(os.path.join(out_dir, "_temp"), ignore_errors=True)
    return rep


def _stop(msg):
    print("[Arrêt] " + msg)
    try:
        from qgis.PyQt.QtWidgets import QMessageBox
        QMessageBox.information(None, "05A", msg)
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
            QMessageBox.critical(None, "05A — erreur", tb[-1500:])
        except Exception:
            pass


def _main():
    from qgis.PyQt.QtWidgets import QFileDialog, QInputDialog, QMessageBox
    from qgis.PyQt.QtCore import QUrl
    folder = QFileDialog.getExistingDirectory(None, f"05A — dossier des cartes LULC_{AREA_TAG}_<année>.tif")
    if not folder:
        return _stop("Annulé : aucun fichier produit.")
    maps = find_lulc_maps(folder, AREA_TAG)
    if not maps:
        return _stop(f"Aucune carte LULC_{AREA_TAG}_<année>.tif dans ce dossier (vérifiez AREA_TAG en tête de script).")
    out = QFileDialog.getExistingDirectory(None, "05A — dossier de SORTIE (différent du dossier des cartes)")
    if not out or os.path.normpath(out) == os.path.normpath(folder):
        return _stop("Dossier de sortie absent ou identique au dossier des cartes : annulé.")
    n, ok = QInputDialog.getInt(None, "05A", "Nombre de points par année :", N_POINTS, 50, 5000)
    if not ok:
        return _stop("Annulé.")
    study, _f = QFileDialog.getOpenFileName(None, "05A — zone d'étude (shp) : facultatif, Annuler pour toute la carte", "", "Shapefile (*.shp)")
    rep = run_sampling(maps, os.path.join(out, "05A_Validation_Sampling"), n, MIN_PER_CLASS, BASE_SEED, study or None, REPORT_LANG)
    try:
        from qgis.core import QgsVectorLayer, QgsProject
        for y in maps:
            lyr = QgsVectorLayer(os.path.join(out, "05A_Validation_Sampling", "Validation_Points.gpkg") + f"|layername=points_{y}", f"Validation {y}", "ogr")
            if lyr.isValid():
                QgsProject.instance().addMapLayer(lyr)
    except Exception:
        pass
    QMessageBox.information(None, "05A terminé", f"Points, plan d'échantillonnage, protocole et rapport écrits dans :\n{out}\n\nShapefiles pour ArcGIS Pro : 05A_Validation_Sampling/Shapefiles_ArcGIS/\nRapport : {rep}\n\nRemplissez Ref_Class SANS voir Map_Class, puis lancez 05B.")
    try:
        from qgis.PyQt.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(rep))
    except Exception:
        pass


# ====================== MAIN ======================
main()
