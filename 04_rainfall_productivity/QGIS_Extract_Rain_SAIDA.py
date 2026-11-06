# -*- coding: utf-8 -*-
# استخراج السلاسل الشهرية لولاية سعيدة من CHIRPS وERA5-Land وTerraClimate (ppt وsoil) للفترة 1999-2025
# الصق السكربت كاملاً في محرر Python في QGIS ثم شغّله.
import os, csv, calendar, unicodedata
import numpy as np
from osgeo import gdal
from qgis.core import QgsVectorLayer
import processing

DATA   = r"D:\DATA ALG_CLIP"
SHP    = DATA + r"\0_Decoupage\Nord_Comm_Wilaya.shp"
CHIRPS = DATA + r"\06_Climate_CHIRPS\chirps-v3.0.{y}.{m:02d}_NordALG.tif"
ERA5   = DATA + r"\08_Climate_ERA5Land_Monthly\ERA5_Land_Monthly_NordALG_{y}.nc"
TCPPT  = DATA + r"\14_Climate_TerraClimate\TerraClimate_ppt_{y}_NordALG.nc"
TCSOIL = DATA + r"\14_Climate_TerraClimate\TerraClimate_soil_{y}_NordALG.nc"
OUTDIR = r"D:\Résultat finale\3_Results\23_Saida_Rain_Test"
FIELD  = "name_fr_1"
WILAYA = "saida"            # يُقارَن بعد حذف الحركات وتجاهل حالة الأحرف (Saïda = saida)
YEARS  = range(1999, 2026)
os.makedirs(OUTDIR, exist_ok=True)

def norm(s):
    return "".join(c for c in unicodedata.normalize("NFD", str(s)) if unicodedata.category(c) != "Mn").strip().lower()

# 1) حدود الولاية (دمج بلدياتها في مضلع واحد)
lyr = QgsVectorLayer(SHP, "w", "ogr")
vals = sorted({f[FIELD] for f in lyr.getFeatures() if f[FIELD] is not None})
match = [v for v in vals if norm(v) == WILAYA]
if not match:
    print("لم أجد الولاية. القيم المتاحة في الحقل", FIELD, ":", vals)
    raise SystemExit
sel = match[0].replace("'", "''")
lyr.setSubsetString("\"%s\" = '%s'" % (FIELD, sel))
print("الولاية:", match[0], "| عدد البلديات:", lyr.featureCount())
cut = OUTDIR + r"\saida_dissolved.gpkg"
if os.path.exists(cut): os.remove(cut)
processing.run("native:dissolve", {"INPUT": lyr, "FIELD": [], "OUTPUT": cut})

def open_var(path, want):
    ds = gdal.Open(path)
    if ds is None: raise RuntimeError("تعذّر فتح " + path)
    subs = ds.GetSubDatasets()
    if not subs: return ds, [ds.GetDescription()]
    names = [s[0] for s in subs]
    pick = [s for s in names if s.split(":")[-1].lower() in want]
    if not pick: raise RuntimeError("لم أجد المتغير %s. المتغيرات: %s" % (want, names))
    return gdal.Open(pick[0]), names

def warp_arr(ds, nd=None):
    kw = dict(format="MEM", cutlineDSName=cut, cropToCutline=True, outputType=gdal.GDT_Float32,
              dstNodata=-9999, warpOptions=["CUTLINE_ALL_TOUCHED=TRUE"])
    if nd is not None: kw["srcNodata"] = nd
    w = gdal.Warp("", ds, **kw)
    a = w.ReadAsArray().astype("float64")
    if a.ndim == 2: a = a[None]
    a[a == -9999] = np.nan
    return a

def regional_means(path, want):
    ds, names = open_var(path, want)
    b1 = ds.GetRasterBand(1)
    sc = b1.GetScale() or 1.0; off = b1.GetOffset() or 0.0; nd = b1.GetNoDataValue()
    a = warp_arr(ds, nd) * sc + off
    return [float(np.nanmean(x)) for x in a], int(np.isfinite(a[0]).sum())

rows = []
for y in YEARS:
    e = p = s = []
    if os.path.exists(ERA5.format(y=y)):
        e, nc_e = regional_means(ERA5.format(y=y), ("tp", "total_precipitation"))
    if os.path.exists(TCPPT.format(y=y)):
        p, nc_p = regional_means(TCPPT.format(y=y), ("ppt",))
        s, _ = regional_means(TCSOIL.format(y=y), ("soil",))
    for m in range(1, 13):
        d = calendar.monthrange(y, m)[1]
        ch, ncc = "", ""
        cp = CHIRPS.format(y=y, m=m)
        if os.path.exists(cp) and not (y == 1999 and m < 9):
            a = warp_arr(gdal.Open(cp), -9999)
            ch = round(float(np.nanmean(a)), 3); ncc = int(np.isfinite(a[0]).sum())
        ei = e[m - 1] if m - 1 < len(e) else None
        rows.append(dict(year=y, month=m, days=d,
                         chirps_mm=ch, n_cells_chirps=ncc,
                         era5_mm_daily_mean=round(ei * 1000 * d, 3) if ei is not None else "",
                         era5_tp_raw=round(ei, 8) if ei is not None else "",
                         terraclimate_ppt_mm=round(p[m - 1], 3) if m - 1 < len(p) else "",
                         terraclimate_soil_mm=round(s[m - 1], 3) if m - 1 < len(s) else ""))
    print(y, "تم")

path = OUTDIR + r"\Regional_Monthly_Rain_SAIDA.csv"
with open(path, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
by = {}
for r in rows:
    d = by.setdefault(r["year"], [0.0, 0.0, 0.0])
    for i, k in enumerate(("chirps_mm", "era5_mm_daily_mean", "terraclimate_ppt_mm")):
        d[i] += float(r[k] or 0)
print("\nالسنة | CHIRPS | ERA5 | TerraClimate (مجموع سنوي ملم؛ المتوقع لسعيدة نحو 300-450)")
for y in (2001, 2010, 2020):
    print(y, [round(v) for v in by[y]])
print("النتائج في:", path)
