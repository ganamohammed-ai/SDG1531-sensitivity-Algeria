# -*- coding: utf-8 -*-
"""
Stage 4 - Accuracy of land-cover CHANGE: stratified sample design (Olofsson et al. 2014)
==========================================================================================
Reads the ENVI land-cover maps (uint8, classes 1-8, 0 = outside/unclassified), builds
change strata from the transition rules, draws a stratified random sample of 30 m pixels
for each period, and writes:

  <out>/Sample_<period>_for_labelling.csv   points WITHOUT the mapped class (blind labelling)
  <out>/Sample_<period>_for_labelling.shp   same points as a shapefile (EPSG:32632)
  <out>/Sample_<period>_KEY_do_not_open.csv mapped class and stratum of every point (analysis only)
  <out>/Strata_<period>.csv                 stratum sizes, weights, sample sizes
  <out>/Rules_Effects.csv                   transition -> effect (D/S/I) used for the strata

Needs only numpy and pandas (both ship with QGIS). No GDAL required.
Run from a terminal:  python Stage4_Make_Change_Sample.py
or from the QGIS Python console:  exec(open(r"<path>").read())
"""
import os, struct, math, csv
import numpy as np
import pandas as pd

# ------------------------------------------------------------------ settings
MAP_DIR   = os.environ.get("S4_MAP_DIR", r"C:\Users\User25\Desktop\Claude files\LULC BEST")          # folder with LULC_Oum_El_Bouaghi_<year>.dat
RULES_CSV = os.environ.get("S4_RULES_CSV", r"C:\Users\User25\Desktop\Claude files\SDG1531_OEB_FINAL_BUNDLE\FINAL_DELIVERABLES\03_LC_Transition_Matrix_OEB_FINAL_v2.csv")
OUT_DIR   = os.environ.get("S4_OUT_DIR", r"C:\Users\User25\Desktop\Claude files\LULC BEST\Validation LCLU\05C_Change_Accuracy")
PERIODS   = [(1999, 2015), (2015, 2025)]
ROWS, COLS = 2913, 5145                    # from the .hdr
X0, Y0, PIX = 243105.0, 4008255.0, 30.0    # upper-left corner of the upper-left pixel, UTM 32N
UTM_ZONE_CM = 9.0                          # central meridian of zone 32
N_STRATUM = {  # points per stratum and period
    "D1_Range_to_Crop": 28, "D2_Range_to_Bare_or_Fallow": 28, "D3_Crop_or_Fallow_to_Bare": 28,
    "D4_Forest_loss": 28, "D5_To_Built": 28,
    "I1_Bare_to_Range": 28, "I2_Bare_to_Crop_or_Fallow": 28, "I3_To_Forest": 28,
    "S1_Stable": 40, "S2_Other_change": 36}
MIN_DIST_M = 150.0                         # minimum distance between sample points
SEED_BASE  = 2026
CLASS = {1: "Built-up", 2: "Water", 3: "Sebkha", 4: "Bareland/Rock", 5: "Cropland", 6: "Fallow",
         7: "Forest", 8: "Rangeland"}

# ------------------------------------------------------------------ strata
def stratum_of(f, t, eff):
    """Stratum name for a mapped transition f -> t (eff = strict effect D/S/I)."""
    if f == t:
        return "S1_Stable"
    if (f, t) == (8, 5): return "D1_Range_to_Crop"
    if (f, t) in ((8, 4), (8, 6)): return "D2_Range_to_Bare_or_Fallow"
    if (f, t) in ((5, 4), (6, 4)): return "D3_Crop_or_Fallow_to_Bare"
    if f == 7 and eff == "D": return "D4_Forest_loss"
    if t == 1 and eff == "D": return "D5_To_Built"
    if (f, t) == (4, 8): return "I1_Bare_to_Range"
    if f == 4 and t in (5, 6): return "I2_Bare_to_Crop_or_Fallow"
    if t == 7 and eff == "I": return "I3_To_Forest"
    return "S2_Other_change"

def load_rules():
    r = pd.read_csv(RULES_CSV, encoding="utf-8-sig")
    eff = {(int(a), int(b)): (s, ro) for a, b, s, ro in
           zip(r.from_code, r.to_code, r.effect_strict, r.effect_robust)}
    return eff

# ------------------------------------------------------------------ geodesy (UTM 32N -> lon/lat, WGS84)
def utm_to_lonlat(x, y, cm=UTM_ZONE_CM):
    a, f = 6378137.0, 1 / 298.257223563
    k0, E0 = 0.9996, 500000.0
    n = f / (2 - f)
    A = a / (1 + n) * (1 + n**2 / 4 + n**4 / 64)
    b1 = n/2 - 2*n**2/3 + 37*n**3/96
    b2 = n**2/48 + n**3/15
    b3 = 17*n**3/480
    d1 = 2*n - 2*n**2/3 - 2*n**3
    d2 = 7*n**2/3 - 8*n**3/5
    d3 = 56*n**3/15
    xi = y / (k0 * A)
    eta = (x - E0) / (k0 * A)
    xi_p = xi - (b1*np.sin(2*xi)*np.cosh(2*eta) + b2*np.sin(4*xi)*np.cosh(4*eta) + b3*np.sin(6*xi)*np.cosh(6*eta))
    eta_p = eta - (b1*np.cos(2*xi)*np.sinh(2*eta) + b2*np.cos(4*xi)*np.sinh(4*eta) + b3*np.cos(6*xi)*np.sinh(6*eta))
    chi = np.arcsin(np.sin(xi_p) / np.cosh(eta_p))
    lat = chi + d1*np.sin(2*chi) + d2*np.sin(4*chi) + d3*np.sin(6*chi)
    lon = np.radians(cm) + np.arctan2(np.sinh(eta_p), np.cos(xi_p))
    return np.degrees(lon), np.degrees(lat)

# ------------------------------------------------------------------ minimal shapefile writer (points)
PRJ = ('PROJCS["WGS_1984_UTM_Zone_32N",GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],'
       'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],'
       'PARAMETER["False_Easting",500000.0],PARAMETER["False_Northing",0.0],PARAMETER["Central_Meridian",9.0],'
       'PARAMETER["Scale_Factor",0.9996],PARAMETER["Latitude_Of_Origin",0.0],UNIT["Meter",1.0]]')

def write_point_shapefile(path_noext, xs, ys, fields, records):
    """fields: list of (name, type 'C'|'N', length, decimals); records: list of tuples."""
    n = len(xs)
    # .shp
    rec_len = 4 + 20  # record header (8) counted separately; content 20 bytes for a point
    shp_len_words = (100 + n * (8 + 20)) // 2
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    with open(path_noext + ".shp", "wb") as shp, open(path_noext + ".shx", "wb") as shx:
        hdr = struct.pack(">7i", 9994, 0, 0, 0, 0, 0, shp_len_words) + struct.pack("<2i4d4d", 1000, 1, xmin, ymin, xmax, ymax, 0, 0, 0, 0)
        shp.write(hdr)
        shx.write(struct.pack(">7i", 9994, 0, 0, 0, 0, 0, (100 + n * 8) // 2) + struct.pack("<2i4d4d", 1000, 1, xmin, ymin, xmax, ymax, 0, 0, 0, 0))
        off = 50
        for i, (x, y) in enumerate(zip(xs, ys), start=1):
            shp.write(struct.pack(">2i", i, 10) + struct.pack("<i2d", 1, x, y))
            shx.write(struct.pack(">2i", off, 10))
            off += 14
    # .dbf
    rec_size = 1 + sum(f[2] for f in fields)
    with open(path_noext + ".dbf", "wb") as dbf:
        dbf.write(struct.pack("<4BIHH20x", 3, 126, 1, 1, n, 32 + 32 * len(fields) + 1, rec_size))
        for name, typ, ln, dec in fields:
            dbf.write(struct.pack("<11sc4xBB14x", name.encode("ascii")[:10], typ.encode("ascii"), ln, dec))
        dbf.write(b"\r")
        for rec in records:
            dbf.write(b" ")
            for (name, typ, ln, dec), v in zip(fields, rec):
                if typ == "N":
                    s = ("%*.*f" % (ln, dec, v)) if dec else ("%*d" % (ln, int(v)))
                    dbf.write(s[-ln:].encode("ascii"))
                else:
                    dbf.write(str(v).encode("ascii", "replace")[:ln].ljust(ln))
        dbf.write(b"\x1a")
    with open(path_noext + ".prj", "w") as f:
        f.write(PRJ)
    with open(path_noext + ".cpg", "w") as f:
        f.write("UTF-8")

# ------------------------------------------------------------------ main
def interior(valid):
    """True where the pixel and its 8 neighbours are all inside the mapped area."""
    m = valid.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0: continue
            sh = np.zeros_like(valid)
            ys = slice(max(dy, 0), ROWS + min(dy, 0)); yd = slice(max(-dy, 0), ROWS + min(-dy, 0))
            xs_ = slice(max(dx, 0), COLS + min(dx, 0)); xd = slice(max(-dx, 0), COLS + min(-dx, 0))
            sh[yd, xd] = valid[ys, xs_]
            m &= sh
    return m

def draw_sample(cand_flat, n, rng, min_px):
    """Random points from candidate flat indices keeping a minimum spacing (grid-hash rejection)."""
    order = rng.permutation(cand_flat)
    cell = max(1, int(min_px))
    taken, grid = [], {}
    for idx in order:
        r, c = divmod(int(idx), COLS)
        gr, gc = r // cell, c // cell
        ok = True
        for a in (gr - 1, gr, gr + 1):
            for b in (gc - 1, gc, gc + 1):
                for (r2, c2) in grid.get((a, b), ()):
                    if (r - r2) ** 2 + (c - c2) ** 2 < min_px ** 2:
                        ok = False; break
                if not ok: break
            if not ok: break
        if ok:
            taken.append(int(idx)); grid.setdefault((gr, gc), []).append((r, c))
            if len(taken) == n: break
    return taken

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    eff = load_rules()
    pd.DataFrame([(f, t, CLASS[f], CLASS[t], s, r, stratum_of(f, t, s)) for (f, t), (s, r) in sorted(eff.items())],
                 columns=["from_code", "to_code", "from", "to", "effect_strict", "effect_robust", "stratum"]
                 ).to_csv(os.path.join(OUT_DIR, "Rules_Effects.csv"), index=False, encoding="utf-8-sig")
    # lookup table: code f*10+t -> stratum index
    names = list(N_STRATUM.keys())
    lut = np.full(100, -1, dtype=np.int16)
    for (f, t), (s, r) in eff.items():
        lut[f * 10 + t] = names.index(stratum_of(f, t, s))
    for pi, (y1, y2) in enumerate(PERIODS):
        tag = "%d_%d" % (y1, y2)
        A = np.fromfile(os.path.join(MAP_DIR, "LULC_Oum_El_Bouaghi_%d.dat" % y1), dtype=np.uint8).reshape(ROWS, COLS)
        B = np.fromfile(os.path.join(MAP_DIR, "LULC_Oum_El_Bouaghi_%d.dat" % y2), dtype=np.uint8).reshape(ROWS, COLS)
        valid = (A > 0) & (B > 0) & (A <= 8) & (B <= 8)
        frame = interior(valid)
        code = A.astype(np.int16) * 10 + B
        strat = np.where(frame, lut[np.clip(code, 0, 99)], -1)
        N_tot = int(frame.sum())
        rng = np.random.default_rng(SEED_BASE + pi)
        rows_key, rows_lab, strata_rows = [], [], []
        for si, name in enumerate(names):
            cand = np.flatnonzero((strat == si).ravel())
            n = N_STRATUM[name]
            pts = draw_sample(cand, n, rng, MIN_DIST_M / PIX) if len(cand) else []
            strata_rows.append((name, int(len(cand)), len(cand) / N_tot, len(cand) * 0.09, n, len(pts)))
            for idx in pts:
                r, c = divmod(idx, COLS)
                rows_key.append((name, int(A[r, c]), int(B[r, c]), r, c))
        # shuffle so strata are not recognisable from the point order
        perm = rng.permutation(len(rows_key))
        rows_key = [rows_key[i] for i in perm]
        recs, key_out, xs, ys = [], [], [], []
        for k, (name, f, t, r, c) in enumerate(rows_key, start=1):
            pid = "C%s_%03d" % (tag[2:4] + tag[7:9], k)      # e.g. C0015_001
            x = X0 + (c + 0.5) * PIX; y = Y0 - (r + 0.5) * PIX
            lon, lat = utm_to_lonlat(x, y)
            xs.append(x); ys.append(y)
            recs.append((pid, tag, round(x, 1), round(y, 1), round(float(lon), 6), round(float(lat), 6), y1, y2, 0, 0, 0, "", "", ""))
            key_out.append((pid, name, f, t, CLASS[f], CLASS[t], eff[(f, t)][0], eff[(f, t)][1]))
        cols = ["ID", "Period", "X_utm32", "Y_utm32", "Lon", "Lat", "Date1_year", "Date2_year", "Ref_From", "Ref_To",
                "Confidence", "Source1", "Source2", "Notes"]
        pd.DataFrame(recs, columns=cols).to_csv(os.path.join(OUT_DIR, "Sample_%s_for_labelling.csv" % tag), index=False, encoding="utf-8-sig")
        pd.DataFrame(key_out, columns=["ID", "stratum", "map_from", "map_to", "map_from_name", "map_to_name", "effect_strict", "effect_robust"]
                     ).to_csv(os.path.join(OUT_DIR, "Sample_%s_KEY_do_not_open.csv" % tag), index=False, encoding="utf-8-sig")
        pd.DataFrame(strata_rows, columns=["stratum", "N_pixels", "weight_W", "area_ha", "n_planned", "n_drawn"]
                     ).to_csv(os.path.join(OUT_DIR, "Strata_%s.csv" % tag), index=False, encoding="utf-8-sig")
        fields = [("ID", "C", 12, 0), ("Period", "C", 12, 0), ("X_utm32", "N", 12, 1), ("Y_utm32", "N", 12, 1),
                  ("Lon", "N", 11, 6), ("Lat", "N", 11, 6), ("Date1", "N", 4, 0), ("Date2", "N", 4, 0),
                  ("Ref_From", "N", 2, 0), ("Ref_To", "N", 2, 0), ("Conf", "N", 1, 0),
                  ("Source1", "C", 40, 0), ("Source2", "C", 40, 0), ("Notes", "C", 80, 0)]
        write_point_shapefile(os.path.join(OUT_DIR, "Sample_%s_for_labelling" % tag), xs, ys, fields, recs)
        print(tag, "frame px:", N_tot, "points:", len(rows_key))
        for row in strata_rows: print("   %-30s N=%9d  W=%.5f  n=%d/%d" % (row[0], row[1], row[2], row[5], row[4]))

if __name__ == "__main__":
    main()
