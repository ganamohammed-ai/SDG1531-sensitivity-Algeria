# -*- coding: utf-8 -*-
# سلسلة CHIRPS الشهرية لولاية أم البواقي (1999-09 إلى 2025-12) لاختبار نافذتي ديسمبر–أبريل وسبتمبر–يونيو على CHIRPS نفسه
# الصق السكربت كاملاً في محرر Python في QGIS ثم شغّله (يعيد استخدام حدود الولاية من الخطوة السابقة).
import os, csv
import numpy as np
from osgeo import gdal
from qgis.core import QgsVectorLayer
import processing

DATA   = r"D:\DATA ALG_CLIP"
SHP    = DATA + r"\0_Decoupage\Nord_Comm_Wilaya.shp"
CHIRPS = DATA + r"\06_Climate_CHIRPS\chirps-v3.0.{y}.{m:02d}_NordALG.tif"
OUTDIR = r"D:\Résultat finale\3_Results\22_Rain_Source_Test"
WILAYA = "Oum El Bouaghi"
os.makedirs(OUTDIR, exist_ok=True)

cut = OUTDIR + r"\oeb_dissolved.gpkg"
if not os.path.exists(cut):
    lyr = QgsVectorLayer(SHP, "w", "ogr")
    lyr.setSubsetString("\"name_fr_1\" = '%s'" % WILAYA)
    processing.run("native:dissolve", {"INPUT": lyr, "FIELD": [], "OUTPUT": cut})

rows = []
for y in range(1999, 2026):
    for m in range(1, 13):
        if y == 1999 and m < 9: continue
        p = CHIRPS.format(y=y, m=m)
        if not os.path.exists(p): continue
        ds = gdal.Open(p)
        w = gdal.Warp("", ds, format="MEM", cutlineDSName=cut, cropToCutline=True, outputType=gdal.GDT_Float32,
                      srcNodata=-9999, dstNodata=-9999, warpOptions=["CUTLINE_ALL_TOUCHED=TRUE"])
        a = w.ReadAsArray().astype("float64"); a[a == -9999] = np.nan
        rows.append((y, m, round(float(np.nanmean(a)), 3), int(np.isfinite(a).sum())))
    print(y, "تم")
path = OUTDIR + r"\Regional_Monthly_CHIRPS_OEB.csv"
with open(path, "w", newline="", encoding="utf-8-sig") as f:
    wr = csv.writer(f); wr.writerow(["year", "month", "chirps_mm", "n_cells"]); wr.writerows(rows)
print("خلايا داخل الحدود (آخر شهر):", rows[-1][3], "| النتائج في:", path)
