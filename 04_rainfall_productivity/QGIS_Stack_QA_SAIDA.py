# -*- coding: utf-8 -*-
# فحص جودة مكدسات سعيدة (48 نطاقاً) للسنوات 1999-2025: القيم الناقصة، المدى، الاتساق الداخلي، المقارنة بين السنوات.
# الصق السكربت كاملاً في محرر Python في QGIS ثم شغّله. يقرأ كل مكدس بدقة مخفَّضة (كل 8 بكسلات) فيستغرق دقائق قليلة.
import os, csv
import numpy as np
from osgeo import gdal

ROOT  = r"C:\Users\User25\Desktop\SAIDA LC FINALE\03_Master_Stacks_48Bands"
YEARS = [1999, 2000, 2007, 2015, 2020, 2025]
STEP  = 8
OUT   = r"C:\Users\User25\Desktop\SAIDA LC FINALE\Stack_QA"
os.makedirs(OUT, exist_ok=True)

def read_stack(y):
    p = os.path.join(ROOT, "STACK_%d" % y, "%d_Stack_Master.dat" % y)
    ds = gdal.Open(p)
    if ds is None: raise RuntimeError("تعذّر فتح " + p)
    nx, ny = ds.RasterXSize // STEP, ds.RasterYSize // STEP
    names = [ds.GetRasterBand(i + 1).GetDescription() for i in range(ds.RasterCount)]
    arr = np.stack([ds.GetRasterBand(i + 1).ReadAsArray(buf_xsize=nx, buf_ysize=ny).astype("float64")
                    for i in range(ds.RasterCount)])
    arr[arr <= -9998] = np.nan
    return arr, names

rows, means = [], {}
for y in YEARS:
    a, names = read_stack(y)
    print("====", y, "| نطاقات:", a.shape[0], "| عينة:", a.shape[1:], "====")
    # اللقطة الأولى (Apr_*) ثم الثانية: مواضع الأدوار ثابتة 0..6 = أزرق،أخضر،أحمر،NIR،SWIR1،SWIR2،TIR، 7 = NDVI
    red, nir, ndvi = a[2], a[3], a[7]
    both = np.isfinite(red) & np.isfinite(nir) & (red + nir != 0)
    recomputed = (nir - red) / (nir + red)
    ok = both & np.isfinite(ndvi)
    corr = float(np.corrcoef(recomputed[ok], ndvi[ok])[0, 1]) if ok.sum() > 10 else float("nan")
    allnan = np.isnan(a).all(axis=0)
    print("  بكسلات بلا أي قيمة (خارج الولاية/فراغ): %.1f%%" % (100 * allnan.mean()))
    print("  ارتباط NDVI المخزَّن بالمحسوب من النطاقين الأحمر وNIR: %.3f" % corr)
    for i, n in enumerate(names):
        v = a[i][np.isfinite(a[i])]
        if v.size == 0:
            rows.append(dict(year=y, band=i + 1, name=n, valid_pct=0)); continue
        rows.append(dict(year=y, band=i + 1, name=n, valid_pct=round(100 * v.size / a[i].size, 1),
                         min=round(float(v.min()), 4), p1=round(float(np.percentile(v, 1)), 4),
                         median=round(float(np.median(v)), 4), p99=round(float(np.percentile(v, 99)), 4),
                         max=round(float(v.max()), 4)))
        means.setdefault(i + 1, {})[y] = float(np.median(v))
    print("  وسيط Apr_NDVI: %.3f | وسيط الصيفي NDVI: %.3f" % (np.nanmedian(a[7]), np.nanmedian(a[30])))
    print("  وسيط Apr_Red: %.4f | Apr_NIR: %.4f | Apr_SWIR1: %.4f" % (np.nanmedian(a[2]), np.nanmedian(a[3]), np.nanmedian(a[4])))
    print("  أسماء الصيفي: ", names[23], "|", names[30])

with open(os.path.join(OUT, "Stack_Band_Stats.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=["year", "band", "name", "valid_pct", "min", "p1", "median", "p99", "max"], restval="")
    w.writeheader(); w.writerows(rows)
with open(os.path.join(OUT, "Stack_Median_By_Year.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f); w.writerow(["band"] + YEARS)
    for b in sorted(means): w.writerow([b] + [round(means[b].get(y, float("nan")), 4) for y in YEARS])
print("\nالنتائج في:", OUT)
