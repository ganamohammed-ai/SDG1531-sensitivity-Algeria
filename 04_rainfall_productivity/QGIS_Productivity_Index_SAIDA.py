# -*- coding: utf-8 -*-
# المؤشر الإقليمي السنوي للإنتاجية (index_tous) لولاية سعيدة من MODIS 2000-2025، بنفس تعريف 06b:
# مؤشر البكسل = قيمته / متوسط البكسل في سنواته الصالحة؛ مؤشر السنة = متوسط النسب على البكسلات المستقرة (صالحة في 80% فأكثر من السنوات).
# الصق السكربت كاملاً في محرر Python في QGIS ثم شغّله.
import os, csv, math, unicodedata
import numpy as np
from osgeo import gdal
from qgis.core import QgsVectorLayer
import processing

DATA    = r"D:\DATA ALG_CLIP"
SHP     = DATA + r"\0_Decoupage\Nord_Comm_Wilaya.shp"
PROD    = DATA + r"\10_MODIS_2000_2025\01_Annual_Productivity_MODIS_2000_2025_NordALG.tif"
NVALID  = DATA + r"\10_MODIS_2000_2025\01b_Annual_ValidPeriods_MODIS_2000_2025_NordALG.tif"
OUTDIR  = r"D:\Résultat finale\3_Results\23_Saida_Rain_Test"
FIELD, WILAYA = "name_fr_1", "saida"
START_YEAR = 2000
MIN_NVALID = 5                  # نفس عتبة السيناريو B (n_valid >= 5)
MIN_VALID_YEAR_FRACTION = 0.80
MIN_COVERAGE_PCT = 50.0
os.makedirs(OUTDIR, exist_ok=True)

def norm(s):
    return "".join(c for c in unicodedata.normalize("NFD", str(s)) if unicodedata.category(c) != "Mn").strip().lower()

# 1) حدود الولاية
lyr = QgsVectorLayer(SHP, "w", "ogr")
vals = sorted({f[FIELD] for f in lyr.getFeatures() if f[FIELD] is not None})
match = [v for v in vals if norm(v) == WILAYA]
if not match:
    print("لم أجد الولاية. القيم المتاحة:", vals); raise SystemExit
lyr.setSubsetString("\"%s\" = '%s'" % (FIELD, match[0].replace("'", "''")))
cut = OUTDIR + r"\saida_dissolved.gpkg"
if not os.path.exists(cut):
    processing.run("native:dissolve", {"INPUT": lyr, "FIELD": [], "OUTPUT": cut})

def crop(path):
    ds = gdal.Open(path)
    if ds is None: raise RuntimeError("تعذّر فتح " + path)
    nd = ds.GetRasterBand(1).GetNoDataValue()
    kw = dict(format="MEM", cutlineDSName=cut, cropToCutline=True, outputType=gdal.GDT_Float32,
              dstNodata=-9999, warpOptions=["CUTLINE_ALL_TOUCHED=FALSE"])
    if nd is not None: kw["srcNodata"] = nd
    w = gdal.Warp("", ds, **kw)
    a = w.ReadAsArray().astype("float64")
    if a.ndim == 2: a = a[None]
    a[a == -9999] = np.nan
    desc = [ds.GetRasterBand(i + 1).GetDescription() for i in range(ds.RasterCount)]
    return a, desc

P, desc = crop(PROD)
print("نطاقات الإنتاجية:", P.shape, "| أول الأوصاف:", desc[:3])
try:
    N, _ = crop(NVALID)
    if N.shape == P.shape:
        P[N < MIN_NVALID] = np.nan
        print("طُبّق قناع n_valid >=", MIN_NVALID)
    else:
        print("تحذير: أبعاد n_valid مختلفة، لم يُطبَّق القناع", N.shape)
except Exception as e:
    print("لم يُطبَّق قناع n_valid:", e)

ny = P.shape[0]
years = []
for i, d in enumerate(desc):
    digits = "".join(ch for ch in d if ch.isdigit())[-4:]
    years.append(int(digits) if len(digits) == 4 and 1990 < int(digits) < 2100 else START_YEAR + i)
if len(set(years)) != ny:
    years = [START_YEAR + i for i in range(ny)]
print("السنوات:", years[0], "-", years[-1], "| عدد السنوات:", ny)

valid = np.isfinite(P)
nv = valid.sum(0)
inc = nv >= math.ceil(MIN_VALID_YEAR_FRACTION * ny)
mean_px = np.where(inc, np.nanmean(np.where(valid, P, np.nan), axis=0), np.nan)
with np.errstate(invalid="ignore", divide="ignore"):
    ratio = P / mean_px[None]
n_stable = int(inc.sum())
print("بكسلات الإنتاجية المستقرة:", n_stable)

rows = []
for i, y in enumerate(years):
    ok = np.isfinite(ratio[i]) & inc
    cov = 100.0 * ok.sum() / max(n_stable, 1)
    idx = float(np.nanmean(ratio[i][ok])) if ok.any() else float("nan")
    rows.append(dict(year=y, index_tous=round(idx, 4) if cov >= MIN_COVERAGE_PCT else "",
                     n_tous=int(ok.sum()), coverage_pct=round(cov, 1),
                     mean_value=round(float(np.nanmean(P[i][ok])), 4) if ok.any() else "",
                     index_all=round(idx, 4)))
path = OUTDIR + r"\Productivity_Index_By_Year_SAIDA.csv"
with open(path, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
for r in rows: print(r["year"], r["index_tous"], r["coverage_pct"])
print("النتائج في:", path)
