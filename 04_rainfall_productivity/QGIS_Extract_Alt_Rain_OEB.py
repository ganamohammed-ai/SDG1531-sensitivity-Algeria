# -*- coding: utf-8 -*-
# استخراج سلاسل شهرية 2000-2025 لولاية أم البواقي من ERA5-Land وTerraClimate (ppt و soil)
# الصق السكربت كاملاً في محرر Python في QGIS ثم شغّله.
import os, csv, calendar
import numpy as np
from osgeo import gdal, ogr, osr
from qgis.core import QgsVectorLayer, QgsVectorFileWriter, QgsProject
import processing

DATA   = r"D:\DATA ALG_CLIP"
SHP    = DATA + r"\0_Decoupage\Nord_Comm_Wilaya.shp"
ERA5   = DATA + r"\08_Climate_ERA5Land_Monthly\ERA5_Land_Monthly_NordALG_{y}.nc"
TCPPT  = DATA + r"\14_Climate_TerraClimate\TerraClimate_ppt_{y}_NordALG.nc"
TCSOIL = DATA + r"\14_Climate_TerraClimate\TerraClimate_soil_{y}_NordALG.nc"
OUTDIR = r"D:\Résultat finale\3_Results\22_Rain_Source_Test"
WILAYA = "Oum El Bouaghi"
YEARS  = range(2000, 2026)
os.makedirs(OUTDIR, exist_ok=True)

# 1) حدود الولاية (ذوبان البلديات الثلاثين في مضلع واحد)
lyr = QgsVectorLayer(SHP, "w", "ogr")
lyr.setSubsetString("\"name_fr_1\" = '%s'" % WILAYA)
print("عدد البلديات:", lyr.featureCount())
cut = OUTDIR + r"\oeb_dissolved.gpkg"
if os.path.exists(cut): os.remove(cut)
processing.run("native:dissolve", {"INPUT": lyr, "FIELD": [], "OUTPUT": cut})

def open_var(path, want):
    ds = gdal.Open(path)
    if ds is None: raise RuntimeError("تعذّر فتح " + path)
    subs = ds.GetSubDatasets()
    if not subs: return ds, [ds.GetDescription()]
    names = [s[0] for s in subs]
    pick = [s for s in names if s.split(":")[-1].lower() in want]
    if not pick:
        raise RuntimeError("لم أجد المتغير %s. المتغيرات: %s" % (want, names))
    return gdal.Open(pick[0]), names

def regional_means(path, want):
    ds, names = open_var(path, want)
    b1 = ds.GetRasterBand(1)
    sc = b1.GetScale() or 1.0; off = b1.GetOffset() or 0.0; nd = b1.GetNoDataValue()
    kw = dict(format="MEM", cutlineDSName=cut, cropToCutline=True, outputType=gdal.GDT_Float32,
              dstNodata=-9999, warpOptions=["CUTLINE_ALL_TOUCHED=TRUE"])
    if nd is not None: kw["srcNodata"] = nd
    w = gdal.Warp("", ds, **kw)
    arr = w.ReadAsArray().astype("float64")
    if arr.ndim == 2: arr = arr[None]
    arr[arr == -9999] = np.nan
    arr = arr * sc + off
    means = [float(np.nanmean(a)) for a in arr]
    ncell = int(np.isfinite(arr[0]).sum())
    return means, ncell, names, ds.GetMetadata()

rows = []
first = True
for y in YEARS:
    e, nc_e, names_e, md = regional_means(ERA5.format(y=y), ("tp", "total_precipitation"))
    p, nc_p, _, _ = regional_means(TCPPT.format(y=y), ("ppt",))
    s, nc_s, _, _ = regional_means(TCSOIL.format(y=y), ("soil",))
    if first:
        print("متغيرات ERA5:", names_e)
        print("وحدات ERA5:", {k: v for k, v in md.items() if "units" in k.lower() or "long_name" in k.lower()})
        print("خلايا داخل الحدود: ERA5=%d  TerraClimate=%d" % (nc_e, nc_p))
        print("عدد أشهر ERA5=%d  ppt=%d  soil=%d" % (len(e), len(p), len(s)))
        first = False
    for m in range(1, 13):
        ei = e[m - 1] if m - 1 < len(e) else float("nan")
        rows.append(dict(year=y, month=m, days=calendar.monthrange(y, m)[1],
                         era5_tp_raw=round(ei, 8),
                         era5_mm_if_daily_mean=round(ei * 1000 * calendar.monthrange(y, m)[1], 3),
                         era5_mm_if_monthly_sum=round(ei * 1000, 3),
                         terraclimate_ppt_mm=round(p[m - 1], 3) if m - 1 < len(p) else "",
                         terraclimate_soil_mm=round(s[m - 1], 3) if m - 1 < len(s) else ""))
    print(y, "تم")

path = OUTDIR + r"\Regional_Monthly_Alt_Rain_OEB.csv"
with open(path, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

# فحص سريع للوحدات: المجموع السنوي المتوقع لمطر أم البواقي نحو 300-500 ملم
by = {}
for r in rows:
    d = by.setdefault(r["year"], [0, 0, 0])
    d[0] += r["era5_mm_if_daily_mean"]; d[1] += r["era5_mm_if_monthly_sum"]; d[2] += float(r["terraclimate_ppt_mm"] or 0)
print("\nالسنة | ERA5 (متوسط يومي×أيام) | ERA5 (مجموع شهري) | TerraClimate ppt")
for y in list(by)[:5]:
    print(y, "|", round(by[y][0]), "|", round(by[y][1]), "|", round(by[y][2]))
print("\nالنتائج في:", path)
