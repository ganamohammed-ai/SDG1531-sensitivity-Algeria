# -*- coding: utf-8 -*-
"""
OUM EL BOUAGHI : TOUS LES PLANS (D01-D08) x 3 PRODUITS DE PLUIE (CHIRPS / ERA5-Land / TerraClimate)   |   QGIS / PyQGIS, script autonome

Suite de OEB_RainProducts_Test.py (meme methode, memes reglages, memes CSV de pluie ; seule difference : les 8 plans au lieu de D04 seul).
  1. CSV de pluie journaliere par produit (CHIRPS = fichier Climate Engine de D04 ; ERA5, TerraClimate = reconstruits et verifies) ; repris si deja faits.
  2. LPD (06e) : pour chaque produit, les 8 baselines (depart 2000/2003 x fenetre 09-06/12-04 x etat 2011-2015/2013-2015) et les 4 suivis.
  3. Integration 1OAO (08a) pour chacun des 8 plans : 12 scenarios par plan (3 regles de couverture x productivite corrigee/non corrigee x SOC avec/sans) = 96 scenarios par produit.
  4. Controle : le CHIRPS (Climate Engine) doit redonner le tableau maitre d'origine (Master_Final_Indicator_All_Designs.csv) ; ecarts affiches.
  5. Ecrit : OEB_RainProducts_AllDesigns_long.csv (96 lignes x 3 produits), OEB_RainProducts_Designs_Summary.csv (plan principal par plan et par produit) et OEB_RainProducts_Range.csv (minimum-maximum des scenarios corriges par produit et par fenetre).
UTILISATION : ouvrir dans l'editeur Python de QGIS, verifier les chemins (REGLAGES), Executer. Reprise automatique (RESUME = True) : relancer apres une interruption.
"""
import os, re, csv, json, time, html, math, calendar, datetime as dt, traceback

# ----------------------------------------------------------------------------- REGLAGES
DATA = r"C:\Users\User25\Desktop\DATA Oum El Bouaghi"
R = r"D:\Résultat finale\3_Results\27_OEB_CHIRPS_monthly_AllDesigns"               # dossier de sortie (cree)
S06E = r"D:\Résultat finale\2_Scripts\06_Productivity_LPD\06e_QGIS_LPD_Productivite.py"
S08A = r"D:\Résultat finale\2_Scripts\08_Integration_1OAO\08a_QGIS_Integration_ODD1531_1OAO.py"
LULC_DIR = r"D:\Résultat finale\Claude files\LULC BEST"
MATRIX = r"D:\Résultat finale\3_Results\05_Transition_Rules\03_LC_Transition_Matrix_OEB_FINAL_v3_expert.csv"
SOC_BASE = r"D:\Résultat finale\Claude files\SOC\Scenario_A_MAIN_central\04_SOC_Change\SOC_Class_1999_2015.tif"
SOC_MON = r"D:\Résultat finale\Claude files\SOC\Scenario_A_MAIN_central\04_SOC_Change\SOC_Class_2015_2025.tif"
MODIS_DIR = DATA + r"\04_MODIS_2000_2025"
AOI_UTM = DATA + r"\00_Boundary\AOI_OumElBouaghi_UTM.shp"             # limite pour le LPD (comme le plan D04)
AOI_WGS = DATA + r"\00_Boundary\AOI_OumElBouaghi_WGS84.shp"           # limite pour la pluie (grilles en lat/lon)
CHECK_ERA5_TC = r"D:\Résultat finale\3_Results\22_Rain_Source_Test\Regional_Monthly_Alt_Rain_OEB.csv"   # CSV mensuel deja valide
CHECK_CHIRPS = r"D:\Résultat finale\3_Results\22_Rain_Source_Test\Regional_Monthly_CHIRPS_OEB.csv"
CHIRPS_FILE = ""   # inutilise : le CSV CHIRPS (total mensuel valide reparti uniformement) est deja dans R\02_Rain
ENV_DIR = ""                       # dossier des couches Env_Rainfall / Env_Elevation si le plan D04 d'origine les utilisait (n'influence pas la classe « degrade »)
PRODUCTS = ["CHIRPS"]      # CHIRPS = controle de reproduction de D04
FIRST_YEAR, LAST_YEAR = 1999, 2025               # pluie journaliere : decembre 1999 est necessaire a la saison 2000 (fenetre dec-avril)
# les 8 plans du tableau maitre : (nom, annee de debut, fenetre de pluie, fenetre d'etat)
DESIGNS = [("D01", 2000, (9, 6), "2013-2015"), ("D02", 2000, (9, 6), "2011-2015"), ("D03", 2000, (12, 4), "2013-2015"), ("D04", 2000, (12, 4), "2011-2015"),
           ("D05", 2003, (9, 6), "2013-2015"), ("D06", 2003, (9, 6), "2011-2015"), ("D07", 2003, (12, 4), "2013-2015"), ("D08", 2003, (12, 4), "2011-2015")]
DESIGNS_ONLY = []                  # [] = les 8 plans ; ex. ["D04", "D08"] pour limiter
STATE = {"2011-2015": {"BASELINE_STATE_END": 2010, "BASELINE_STATE_RECENT": (2011, 2015)},
         "2013-2015": {"BASELINE_STATE_END": 2012, "BASELINE_STATE_RECENT": (2013, 2015)}}
MASTER_ORIG = r"D:\Résultat finale\3_Results\08_Integration_1OAO\Master_Final_Indicator_All_Designs.csv"    # tableau maitre d'origine (controle)
MIN_PRODUCTIVITY_YEARS = 15
MAX_REL_DIFF_CHECK = 0.10          # ecart relatif annuel maximal tolere entre serie reconstruite et CSV deja valide
ALL_TOUCHED = True                 # True = toutes les cellules touchant la limite (c'etait 310 cellules dans le test valide) ; False = centre dans la limite (251)
RESUME = True
AUTO_RUN = True

# ----------------------------------------------------------------------------- PLUIE : CSV JOURNALIERS
def _gdal():
    from osgeo import gdal, ogr
    gdal.UseExceptions()
    return gdal, ogr


def aoi_mask(ds, aoi_path):
    """Masque booleen des cellules de la grille `ds` dont le centre est dans la limite (sinon toutes celles qui la touchent)."""
    import numpy as np
    gdal, ogr = _gdal()
    mem = gdal.GetDriverByName("MEM").Create("", ds.RasterXSize, ds.RasterYSize, 1, gdal.GDT_Byte)
    mem.SetGeoTransform(ds.GetGeoTransform())
    mem.SetProjection(ds.GetProjection())
    src = ogr.Open(aoi_path)          # garder une reference a la source, sinon la couche est detruite (erreur OGRLayerShadow)
    lyr = src.GetLayer(0)
    gdal.RasterizeLayer(mem, [1], lyr, burn_values=[1], options=["ALL_TOUCHED=TRUE" if ALL_TOUCHED else "ALL_TOUCHED=FALSE"])
    m = mem.GetRasterBand(1).ReadAsArray().astype(bool)
    if not m.any():
        gdal.RasterizeLayer(mem, [1], lyr, burn_values=[1], options=["ALL_TOUCHED=TRUE"])
        m = mem.GetRasterBand(1).ReadAsArray().astype(bool)
    return m


def band_means(ds, mask, nb=None):
    """Moyenne regionale de chaque bande (cellules valides du masque), echelle/decalage appliques."""
    import numpy as np
    out = []
    for i in range(1, (nb or ds.RasterCount) + 1):
        b = ds.GetRasterBand(i)
        a = b.ReadAsArray().astype("float64")
        nd = b.GetNoDataValue()
        sc, off = b.GetScale() or 1.0, b.GetOffset() or 0.0
        if nd is not None:
            a = np.where(a == nd, np.nan, a)
        a = a * sc + off
        v = a[mask]
        v = v[np.isfinite(v)]
        out.append(float(v.mean()) if v.size else float("nan"))
    return out


def open_nc_var(path, names):
    gdal, _ = _gdal()
    ds = gdal.Open(path)
    subs = ds.GetSubDatasets() or []
    if subs:
        for sname, _desc in subs:
            if sname.rsplit(":", 1)[-1].lower() in names:
                return gdal.Open(sname)
        raise RuntimeError("Variable %s introuvable dans %s ; sous-jeux : %s" % (names, path, [s[0].rsplit(":", 1)[-1] for s in subs]))
    return ds


def monthly_series(product):
    """{(annee, mois): valeur journaliere equivalente en mm/jour} pour ERA5 ou TerraClimate ; CHIRPS est traite en journalier."""
    res, ncells = {}, None
    for y in range(FIRST_YEAR, LAST_YEAR + 1):
        if product == "ERA5":
            p = os.path.join(DATA, "03_Climat", "08_Climate_ERA5Land_Monthly", "ERA5_Land_Monthly_OumElBouaghi_%d.nc" % y)
            ds = open_nc_var(p, ("tp", "total_precipitation"))
        else:
            p = os.path.join(DATA, "03_Climat", "14_Climate_TerraClimate", "TerraClimate_ppt_%d_OumElBouaghi.nc" % y)
            ds = open_nc_var(p, ("ppt",))
        if ds.RasterCount != 12:
            raise RuntimeError("%s : %d bandes au lieu de 12 (verifier la variable / les dimensions)" % (p, ds.RasterCount))
        mask = aoi_mask(ds, AOI_WGS)
        ncells = int(mask.sum())
        vals = band_means(ds, mask)
        for m in range(1, 13):
            v = vals[m - 1]
            res[(y, m)] = (v * 1000.0) if product == "ERA5" else (v / calendar.monthrange(y, m)[1])     # ERA5 : m/jour -> mm/jour ; TerraClimate : mm/mois -> mm/jour
    return res, ncells


def write_daily_csv(path, daily):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        f.write("date;chirps_mm\n")
        d = dt.date(FIRST_YEAR, 1, 1)
        while d <= dt.date(LAST_YEAR, 12, 31):
            v = daily.get(d)
            if v is not None:
                f.write("%s;%.5f\n" % (d.isoformat(), v))
            d += dt.timedelta(days=1)


def build_rain_csv(product, path, log=print):
    """Ecrit le CSV journalier du produit ; retourne {annee: total annuel} pour le controle."""
    daily = {}
    if product == "CHIRPS" and CHIRPS_FILE and os.path.exists(CHIRPS_FILE):
        for ln in open(CHIRPS_FILE, encoding="utf-8-sig").read().splitlines()[1:]:
            a, b = ln.replace('"', '').split(";")[:2]
            d0 = dt.date(int(a[:4]), int(a[5:7]), int(a[8:10]))
            if FIRST_YEAR <= d0.year <= LAST_YEAR:
                daily[d0] = max(0.0, float(b.replace(",", ".")))
        log("   CHIRPS : fichier Climate Engine utilise (%d jours)" % len(daily))
    elif product == "CHIRPS":
        for y in range(FIRST_YEAR, LAST_YEAR + 1):
            gdal, _ = _gdal()
            ds = gdal.Open(os.path.join(DATA, "03_Climat", "06_Climate_CHIRPS_Daily", "CHIRPS_OumElBouaghi_%d_365days.tif" % y))
            mask = aoi_mask(ds, AOI_WGS)
            vals = band_means(ds, mask)
            ndays = 366 if calendar.isleap(y) else 365
            if len(vals) != ndays:
                raise RuntimeError("CHIRPS %d : %d bandes, attendu %d (jours de l'annee)" % (y, len(vals), ndays))
            for i, v in enumerate(vals):
                daily[dt.date(y, 1, 1) + dt.timedelta(days=i)] = max(0.0, v) if v == v else None
        log("   CHIRPS : %d cellules dans la limite (attendu : 310)" % int(mask.sum()))
    else:
        series, nc = monthly_series(product)
        log("   %s : %d cellules dans la limite" % (product, nc))
        for (y, m), v in series.items():
            for d in range(1, calendar.monthrange(y, m)[1] + 1):
                daily[dt.date(y, m, d)] = v
    write_daily_csv(path, daily)
    return daily


def check_against_validated(product, daily, log=print):
    """Compare les totaux mensuels reconstruits au CSV mensuel deja valide (22_Rain_Source_Test) ; retourne l'ecart relatif annuel maximal."""
    tot = {}
    for d, v in daily.items():
        if v is not None:
            tot[(d.year, d.month)] = tot.get((d.year, d.month), 0.0) + v
    if product == "CHIRPS":
        ref = {(int(r["year"]), int(r["month"])): float(r["chirps_mm"]) for r in csv.DictReader(open(CHECK_CHIRPS, encoding="utf-8-sig"))}
    else:
        col = "terraclimate_ppt_mm" if product == "TerraClimate" else "era5_mm_if_daily_mean"
        ref = {(int(r["year"]), int(r["month"])): float(r[col]) for r in csv.DictReader(open(CHECK_ERA5_TC, encoding="utf-8-sig"))}
    worst = 0.0
    for y in range(2001, 2026):
        a = sum(tot.get((y, m), float("nan")) for m in range(1, 13)); b = sum(ref.get((y, m), float("nan")) for m in range(1, 13))
        if b and a == a and b == b:
            worst = max(worst, abs(a - b) / b)
    log("   controle %s : ecart annuel maximal contre le CSV valide = %.1f %% (tolere %.0f %%)" % (product, 100 * worst, 100 * MAX_REL_DIFF_CHECK))
    return worst


# ----------------------------------------------------------------------------- LPD (script 06e execute avec des reglages imposes)
def set_const(text, name, value):
    m = re.search(r"^(" + re.escape(name) + r" = )(.*?)(\s+#.*)?$", text, re.M)
    if not m:
        raise RuntimeError("Constante %s introuvable dans 06e" % name)
    return text[:m.start()] + m.group(1) + (('"%s"' % value) if isinstance(value, str) else repr(value)) + (m.group(3) or "") + text[m.end():]


def configure_script(text, period, start, window, extra=None):
    text = set_const(text, "LPD_PERIOD", period)
    text = set_const(text, "TREND_START_YEAR", int(start))
    text = set_const(text, "RAIN_WINDOW_MONTHS", tuple(window))
    for k, v in (extra or {}).items():
        text = set_const(text, k, v)
    return text


def run_folder_name(period, start, window, extra=None):
    name = "LPD_%d_%s_%s" % (start, period, "%02d%02d" % tuple(window))
    if extra and "BASELINE_STATE_END" in extra:
        rec = extra.get("BASELINE_STATE_RECENT", ("", ""))
        name += "_s%s_r%s-%s" % (extra["BASELINE_STATE_END"], rec[0], rec[1])
    return name


def parse_key_results(report_html):
    txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<style>.*?</style>", "", report_html, flags=re.S))))
    out = {}
    for m in re.finditer(r"([A-Z]_QA\d_min\d(?:_RainAdjusted)?) : Degraded ([\d.]+) % \| Stable ([\d.]+) % \| Improved ([\d.]+) %", txt):
        out.setdefault(m.group(1), (float(m.group(2)), float(m.group(3)), float(m.group(4))))
    return out


def run_one(script_text, period, start, window, rain_csv, out_dir, log=print, extra=None):
    text = configure_script(script_text, period, start, window, extra)
    head = text.split("\ntry:\n    main()\nexcept Exception as exc:")[0]
    if head == text:
        raise RuntimeError("Point d'entree de 06e non reconnu (utiliser la version de 2_Scripts).")
    ns = {"__name__": "lpd_run"}
    exec(compile(head, "06e (%s %s)" % (period, start), "exec"), ns)
    dirs = {"1/6": MODIS_DIR, "2/6": "", "3/6": LULC_DIR, "4/6": ENV_DIR, "6/6": out_dir}
    yes = {"Scénario A": False, "LULC": True, "Stratification": bool(ENV_DIR), "Limite": True, "Pluie": True}

    def choose_directory(title, start_=""):
        return dirs[title[:3]]

    def ask_yes_no(title, text_):
        for k, v in yes.items():
            if title.startswith(k):
                return v
        return False

    class FD:
        @staticmethod
        def getOpenFileName(parent, title, start_="", flt=""):
            return ((AOI_UTM if "Limite" in title else rain_csv), "")
        getExistingDirectory = staticmethod(lambda parent, title, start_="": "")

    class ID:
        getInt = staticmethod(lambda parent, title, label, value=0, lo=0, hi=100, *a, **k: (MIN_PRODUCTIVITY_YEARS, True))
        getItem = staticmethod(lambda parent, title, label, items, cur=0, editable=False, *a, **k: (items[cur], True))

    class MB:
        information = staticmethod(lambda *a, **k: None)
        critical = staticmethod(lambda parent, title, msg, *a, **k: log("[ERREUR] " + str(msg)[:600]))
        question = staticmethod(lambda *a, **k: ns.get("_QMB_YES"))
        warning = staticmethod(lambda *a, **k: None)
    ns["choose_directory"], ns["ask_yes_no"], ns["QFileDialog"], ns["QInputDialog"], ns["QMessageBox"] = choose_directory, ask_yes_no, FD, ID, MB
    ns["main"]()
    return os.path.join(out_dir, "Stage_Report_02_LPD.html")


def design_list():
    return [d for d in DESIGNS if not DESIGNS_ONLY or d[0] in DESIGNS_ONLY]


def lpd_run_list():
    """Les calculs LPD distincts : une baseline par plan, un suivi par (debut, fenetre)."""
    out, seen = [], set()
    for _n, start, window, st in design_list():
        for run in (("baseline", start, window, STATE[st]), ("monitoring", start, window)):
            k = run_folder_name(*run[:3], run[3] if len(run) > 3 else None)
            if k not in seen:
                seen.add(k)
                out.append(run)
    return out


def run_lpd(product, rain_csv, log=print):
    script_text = open(S06E, encoding="utf-8").read()
    root = os.path.join(R, product)
    for run in lpd_run_list():
        period, start, window = run[0], run[1], run[2]
        extra = run[3] if len(run) > 3 else None
        name = run_folder_name(period, start, window, extra)
        out_dir = os.path.join(root, name)
        os.makedirs(out_dir, exist_ok=True)
        rep = os.path.join(out_dir, "Stage_Report_02_LPD.html")
        if RESUME and os.path.exists(rep) and os.path.isdir(os.path.join(out_dir, "03_LPD")):
            log("   [reprise] %s" % name)
        else:
            log("   LPD %s / %s ..." % (product, name))
            t0 = time.time()
            run_one(script_text, period, start, window, rain_csv, out_dir, log, extra)
            log("   -> %d s" % round(time.time() - t0))
    return root


# ----------------------------------------------------------------------------- INTEGRATION 1OAO (script 08a charge sans lancement automatique)
def load_08a():
    text = open(S08A, encoding="utf-8").read()
    if "AUTO_RUN = True" not in text:
        raise RuntimeError("08a : constante AUTO_RUN introuvable (version differente ?)")
    ns = {"__name__": "integ08a"}
    exec(compile(text.replace("AUTO_RUN = True", "AUTO_RUN = False", 1), "08a", "exec"), ns)
    return ns


def read_final(final_csv):
    txt = open(final_csv, encoding="utf-8-sig").read()
    delim = ";" if txt.split("\n")[0].count(";") > txt.split("\n")[0].count(",") else ","
    out = {}
    for r in csv.DictReader(txt.splitlines(), delimiter=delim):
        f = lambda k: float(str(r[k]).replace(",", "."))
        out[(r["land_cover_matrix"], r["productivity"], r["soc"])] = (f("proportion_degraded_pct"), f("baseline_degraded_pct"), f("monitoring_degraded_pct"))
    return out


def run_integration(product, root, design, ns, log=print):
    name, start, window, st = design
    base_dir = os.path.join(root, run_folder_name("baseline", start, window, STATE[st]), "03_LPD")
    mon_dir = os.path.join(root, run_folder_name("monitoring", start, window), "03_LPD")
    out_root = os.path.join(root, "Integration", name)
    final_csv = os.path.join(out_root, "3_UNCCD_Final", "UNCCD_Final_Indicator.csv")
    if not (RESUME and os.path.exists(final_csv)):
        ns["ensure_dir"](out_root)
        lulc_files = ns["resolve_lulc_files"](LULC_DIR)
        common = {"lulc_dir": LULC_DIR, "lulc_files": lulc_files, "matrix_file": MATRIX, "out_root": out_root,
                  "primary_lc_variant": "robust", "primary_rain": True, "primary_soc": True, "excl_water": True}
        log("   integration %s / %s ..." % (product, name))
        t0 = time.time()
        res = ns["run_two_periods"](common, {"lpd_dir": base_dir, "soc_file": SOC_BASE}, {"lpd_dir": mon_dir, "soc_file": SOC_MON}, "en")
        final_csv = os.path.join(res["dirs"]["final"], "UNCCD_Final_Indicator.csv")
        log("   -> %d s" % round(time.time() - t0))
    else:
        log("   [reprise] integration %s / %s" % (product, name))
    return read_final(final_csv)


# ----------------------------------------------------------------------------- PRINCIPAL
LC_EN = {"strict": "strict", "robust": "robust", "persistent": "persistent"}


def main(log=print):
    os.makedirs(R, exist_ok=True)
    for p in (S06E, S08A, MATRIX, SOC_BASE, SOC_MON, MODIS_DIR, AOI_UTM, AOI_WGS, LULC_DIR, CHECK_CHIRPS, CHECK_ERA5_TC):
        if not os.path.exists(p):
            raise RuntimeError("INTROUVABLE : " + p)
    log("=" * 70 + "\n1. PLUIE JOURNALIERE PAR PRODUIT\n" + "=" * 70)
    csv_paths = {}
    for pr in PRODUCTS:
        path = os.path.join(R, "02_Rain", "%s_Daily_OEB.csv" % pr)
        csv_paths[pr] = path
        if RESUME and os.path.exists(path):
            log("   [reprise] %s" % path)
            continue
        log("   construction %s ..." % pr)
        daily = build_rain_csv(pr, path, log)
        worst = check_against_validated(pr, daily, log)
        if worst > MAX_REL_DIFF_CHECK:
            os.remove(path)
            raise RuntimeError("%s : ecart %.0f %% avec le CSV valide ; arreter et verifier." % (pr, 100 * worst))
    log("\n" + "=" * 70 + "\n2. LPD (06e) : %d calculs par produit\n" % len(lpd_run_list()) + "=" * 70)
    roots = {pr: run_lpd(pr, csv_paths[pr], log) for pr in PRODUCTS}
    log("\n" + "=" * 70 + "\n3. INTEGRATION 1OAO (08a) : %d plans par produit\n" % len(design_list()) + "=" * 70)
    ns = load_08a()
    res = {}                       # (produit, plan) -> {(lc, prod, soc): (proportion, base, suivi)}
    for pr in PRODUCTS:
        for d in design_list():
            res[(pr, d[0])] = run_integration(pr, roots[pr], d, ns, log)
    # --- fichier long
    head = ["product", "design", "start_year", "rain_window", "state_window", "land_cover_matrix", "productivity", "soc", "baseline_degraded_pct", "monitoring_degraded_pct", "proportion_degraded_pct"]
    long_rows = []
    for pr in PRODUCTS:
        for (n, start, window, st) in design_list():
            for (lc, prod, soc), (pp, b, m) in sorted(res[(pr, n)].items()):
                long_rows.append([pr, n, start, "%02d-%02d" % tuple(window), st, lc, prod, soc, b, m, pp])
    with open(os.path.join(R, "OEB_RainProducts_AllDesigns_long.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";"); w.writerow(head); w.writerows(long_rows)
    # --- controle contre le tableau maitre d'origine (produit de reference = premier produit, CHIRPS)
    if os.path.exists(MASTER_ORIG) and "CHIRPS" in PRODUCTS:
        orig = {}
        for r in csv.DictReader(open(MASTER_ORIG, encoding="utf-8-sig"), delimiter=";"):
            orig[(r["design"], r["land_cover_matrix"], r["productivity"], r["soc"])] = float(r["proportion_degraded_pct"].replace(",", "."))
        diffs = []
        for (n, start, window, st) in design_list():
            for (lc, prod, soc), (pp, b, m) in res[("CHIRPS", n)].items():
                k = (n, lc, prod, soc)
                if k in orig:
                    diffs.append((abs(pp - orig[k]), k, pp, orig[k]))
        diffs.sort(reverse=True)
        bad = [d for d in diffs if d[0] > 0.3]
        log("\nCONTROLE CHIRPS contre le tableau maitre d'origine : %d scenarios compares, ecart maximal %.2f point, %d scenarios au-dela de 0,3 point" % (len(diffs), diffs[0][0] if diffs else float("nan"), len(bad)))
        for d in diffs[:5]:
            log("   %s : nouveau %.2f | origine %.2f" % (d[1], d[2], d[3]))
    # --- resume par plan : scenario principal (robust, corrigee, avec SOC)
    main_key = ("robust", "corrigée", "avec SOC")
    sh = ["design", "start_year", "rain_window", "state_window"] + ["%s_robust_adj_withSOC_%%" % p for p in PRODUCTS]
    srows = [[n, start, "%02d-%02d" % tuple(window), st] + ["%.2f" % res[(pr, n)][main_key][0] for pr in PRODUCTS] for (n, start, window, st) in design_list()]
    with open(os.path.join(R, "OEB_RainProducts_Designs_Summary.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";"); w.writerow(sh); w.writerows(srows)
    # --- fourchettes : scenarios corriges (3 regles x SOC) des plans de chaque fenetre
    rh = ["product", "rain_window", "n_scenarios", "min_%", "max_%"]
    rrows = []
    for pr in PRODUCTS:
        for wname in ("12-04", "09-06"):
            vals = [pp for (n, start, window, st) in design_list() if "%02d-%02d" % tuple(window) == wname
                    for (lc, prod, soc), (pp, b, m) in res[(pr, n)].items() if prod == "corrigée"]
            if vals:
                rrows.append([pr, wname, len(vals), "%.1f" % min(vals), "%.1f" % max(vals)])
    with open(os.path.join(R, "OEB_RainProducts_Range.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";"); w.writerow(rh); w.writerows(rrows)
    log("\n" + "=" * 70 + "\nRESULTAT 1 : scenario principal (robust, corrigee, avec SOC) par plan et par produit\n" + "=" * 70)
    log("  ; ".join(sh))
    for r in srows:
        log("  ; ".join(str(x) for x in r))
    log("\n" + "=" * 70 + "\nRESULTAT 2 : fourchette des scenarios corriges (3 regles x SOC x plans de la fenetre)\n" + "=" * 70)
    log("  ; ".join(rh))
    for r in rrows:
        log("  ; ".join(str(x) for x in r))
    log("\nFichiers dans : " + R)
    return srows


if AUTO_RUN:
    try:
        main()
    except Exception:
        print(traceback.format_exc())
