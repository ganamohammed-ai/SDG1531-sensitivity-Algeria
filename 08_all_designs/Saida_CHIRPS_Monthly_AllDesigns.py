# -*- coding: utf-8 -*-
r"""
SAIDA : TOUS LES PLANS D01-D08 AVEC UN CHIRPS UNIQUE (total mensuel valide reparti uniformement)   |   QGIS / PyQGIS, script autonome
Etape 1 : LPD (06e) pour les 8 plans avec 02_Rain\CHIRPS_FromMonthly_Daily_SAIDA.csv  -> 20_CHIRPS_monthly\09_Designs_LPD
Etape 2 : integration 1OAO (08a) pour les 8 plans (12 scenarios chacun = 96) -> 20_CHIRPS_monthly\10_Designs_Integration\Master_Final_Indicator_All_Designs.csv
Tout le reste est identique aux scripts 06f_DIRECT_SAIDA.py et 08b_DIRECT_SAIDA.py (memes LULC, matrice, SOC, limite). Les anciens dossiers 09/10 ne sont pas touches.
UTILISATION : coller dans l'editeur Python de QGIS, Executer (long : plusieurs heures possibles).
"""
import os
import re
import csv
import html
import time
import traceback

# ----------------------------------------------------------------------------- RÉGLAGES (à adapter)
RUNS = [                       # (période, année de début, fenêtre de pluie[, réglages supplémentaires]) ; la 1re et la 2e sont les exécutions PRINCIPALES
                               # 4e élément facultatif : dict de constantes du script 02, ex. {"BASELINE_STATE_END": 2010, "BASELINE_STATE_RECENT": (2011, 2015)} (fenêtre de l'ÉTAT de la base plus large)
    ("baseline", 2000, (12, 4)),
    ("monitoring", 2000, (12, 4)),
    ("baseline", 2003, (12, 4)),       # robustesse : série commençant après la sécheresse 2000-2002
    ("monitoring", 2003, (12, 4)),
]
RUN_ALL_COMBINATIONS = True      # True : tous les plans de DESIGN_AXES ; False : seulement la liste RUNS ci-dessus
DESIGN_AXES = {
    "start": [2000, 2003],
    "rain_window": [(9, 6), (12, 4)],
    "state": [("state3y", 2012, (2013, 2015)), ("state5y", 2010, (2011, 2015))],     # (étiquette, fin de la moyenne de référence, fenêtre récente) de la période de BASE
}
MIN_PRODUCTIVITY_YEARS = 15      # années minimales de productivité pour Performance (réponse à la dernière question de 02)
AUTO_RUN = False


# ----------------------------------------------------------------------------- LOGIQUE (testée sans QGIS)
def set_const(text, name, value):
    """Remplace la valeur d'une constante de configuration en colonne 0 (première occurrence), le commentaire est conservé."""
    m = re.search(r"^(" + re.escape(name) + r" = )(.*?)(\s+#.*)?$", text, re.M)
    if not m:
        raise RuntimeError("Constante %s introuvable dans le script 02 : version trop ancienne ? (recharger le script de scripts/)" % name)
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


def extra_label(extra):
    return ", ".join("%s=%s" % (k, v) for k, v in (extra or {}).items())


def parse_key_results(report_html):
    """Lignes « Key results » d'un rapport 02 : {nom: (dégradé, stable, amélioré)} en %."""
    txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<style>.*?</style>", "", report_html, flags=re.S))))
    out = {}
    for m in re.finditer(r"([A-Z]_QA\d_min\d(?:_RainAdjusted)?) : Degraded ([\d.]+) % \| Stable ([\d.]+) % \| Improved ([\d.]+) %", txt):
        out.setdefault(m.group(1), (float(m.group(2)), float(m.group(3)), float(m.group(4))))
    return out


def expand_designs(axes=None):
    """Tous les plans (produit cartésien des trois axes) et la liste dédupliquée des exécutions du script 02 qu'ils exigent."""
    axes = axes or DESIGN_AXES
    designs, runs, seen = [], [], set()
    n = 0
    for start in axes["start"]:
        for window in axes["rain_window"]:
            for label, st_end, st_recent in axes["state"]:
                n += 1
                d = {"id": "D%02d" % n, "start": int(start), "rain_window": tuple(window), "state": label, "state_end": st_end, "state_recent": tuple(st_recent)}
                extra = {"BASELINE_STATE_END": st_end, "BASELINE_STATE_RECENT": tuple(st_recent)}
                d["baseline_run"] = run_folder_name("baseline", start, window, extra)
                d["monitoring_run"] = run_folder_name("monitoring", start, window)
                designs.append(d)
                if d["baseline_run"] not in seen:
                    seen.add(d["baseline_run"]); runs.append(("baseline", start, tuple(window), extra))
                if d["monitoring_run"] not in seen:
                    seen.add(d["monitoring_run"]); runs.append(("monitoring", start, tuple(window)))
    return designs, runs


def write_index(root, designs, rows):
    import json
    status = {r["name"]: r["status"] for r in rows}
    out = []
    for d in designs:
        ok_b, ok_m = status.get(d["baseline_run"], "").startswith("OK"), status.get(d["monitoring_run"], "").startswith("OK")
        e = dict(d); e["rain_window"] = list(d["rain_window"]); e["state_recent"] = list(d["state_recent"])
        e["baseline_dir"] = os.path.join(root, d["baseline_run"]); e["monitoring_dir"] = os.path.join(root, d["monitoring_run"]); e["complete"] = bool(ok_b and ok_m)
        out.append(e)
    path = os.path.join(root, "LPD_Designs_Index.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"designs": out}, f, ensure_ascii=False, indent=2)
    return path


def run_all_designs(script02_path, inputs, root, axes=None, log=print):
    """Lance tous les plans ; retourne (lignes, chemin du comparatif, chemin de l'index)."""
    designs, runs = expand_designs(axes)
    rows, cmp_path = run_lpd_runs(script02_path, inputs, root, runs=runs, log=log)
    return rows, cmp_path, write_index(root, designs, rows)


def run_one(script_text, period, start, window, inputs, out_dir, log=print, extra=None):
    """Exécute l'étape 02 UNE fois avec les réglages donnés, en lui fournissant les réponses aux dialogues."""
    text = configure_script(script_text, period, start, window, extra)
    head = text.split("\ntry:\n    main()\nexcept Exception as exc:")[0]
    if head == text:
        raise RuntimeError("Point d'entrée du script 02 non reconnu : utilisez la version livrée dans scripts/.")
    ns = {"__name__": "lpd_run"}
    exec(compile(head, "02_QGIS_LPD_Productivite.py (%s %s)" % (period, start), "exec"), ns)
    dirs_by_prefix = {"1/6": inputs["modis_dir"], "2/6": inputs.get("qa0_dir") or "", "3/6": inputs["lulc_dir"], "4/6": inputs.get("env_dir") or "", "6/6": out_dir}
    yes = {"Scénario A": bool(inputs.get("qa0_dir")), "LULC": True, "Stratification": bool(inputs.get("env_dir")), "Limite": bool(inputs.get("aoi_shp")), "Pluie": bool(inputs.get("rain_csv"))}

    def choose_directory(title, start_=""):
        return dirs_by_prefix[title[:3]]

    def ask_yes_no(title, text_):
        for k, v in yes.items():
            if title.startswith(k):
                return v
        return False

    class FD:
        @staticmethod
        def getOpenFileName(parent, title, start_="", flt=""):
            return ((inputs.get("aoi_shp") or "") if "Limite" in title else (inputs.get("rain_csv") or ""), "")
        getExistingDirectory = staticmethod(lambda parent, title, start_="": "")

    class ID:
        getInt = staticmethod(lambda parent, title, label, value=0, lo=0, hi=100, *a, **k: (inputs.get("min_years", MIN_PRODUCTIVITY_YEARS), True))
        getItem = staticmethod(lambda parent, title, label, items, cur=0, editable=False, *a, **k: (items[cur], True))

    class MB:
        information = staticmethod(lambda *a, **k: None)
        critical = staticmethod(lambda parent, title, msg, *a, **k: log("[ERREUR] " + str(msg)[:600]))
        question = staticmethod(lambda *a, **k: ns.get("_QMB_YES"))
        warning = staticmethod(lambda *a, **k: None)
    ns["choose_directory"], ns["ask_yes_no"], ns["QFileDialog"], ns["QInputDialog"], ns["QMessageBox"] = choose_directory, ask_yes_no, FD, ID, MB
    ns["main"]()
    return os.path.join(out_dir, "Stage_Report_02_LPD.html")


def comparison_html(rows, area_name="", started=None):
    esc = html.escape
    th = "".join("<th>%s</th>" % esc(h) for h in ["Exécution", "Période", "Début de série", "Fenêtre de pluie", "Réglages supplémentaires", "Brut dégradé %", "Brut stable %", "Brut amélioré %", "Corrigé pluie dégradé %", "Corrigé stable %", "Corrigé amélioré %", "Statut"])
    tr = []
    for r in rows:
        main_ = r.get("raw") or ("", "", ""); adj = r.get("adj") or ("", "", "")
        tr.append("<tr><td><a href='%s'>%s</a></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>%s%s<td>%s</td></tr>" % (esc(r["report"]), esc(r["name"]), esc(r["period"]), r["start"], esc("%02d–%02d" % tuple(r["window"])), esc(r.get("extra_label", "")),
                  "".join("<td align='right'>%s</td>" % x for x in main_), "".join("<td align='right'>%s</td>" % x for x in adj), esc(r["status"])))
    return ("<!DOCTYPE html><html lang='fr'><head><meta charset='utf-8'><title>Comparaison des exécutions LPD</title><style>body{font-family:Segoe UI,Arial,sans-serif;margin:24px}table{border-collapse:collapse}th,td{border:1px solid #9aa7b5;padding:5px 8px;font-size:13px}th{background:#d6e4f0}.n{color:#555;font-size:12px;max-width:900px}</style></head><body>"
            "<h1>Comparaison des exécutions LPD — %s</h1><p class='n'>Pourcentages de la surface évaluée par l'étape 02 (scénario B pour le brut, variante corrigée de la pluie). Les exécutions « baseline » alimentent la fenêtre 1 de l'étape 07, les « monitoring » la fenêtre 2. "
            "Ne pas présenter une « amélioration » qui disparaît quand la série commence en 2003 comme une restauration (voir le rapport 02B). Lire les contrôles de chaque rapport avant d'utiliser ces chiffres.</p><table><tr>%s</tr>%s</table></body></html>" % (esc(area_name), th, "".join(tr)))


def run_lpd_runs(script02_path, inputs, root, runs=None, log=print):
    """Lance les exécutions de `runs` ; une exécution en échec n'arrête pas les autres. Retourne (lignes, chemin du comparatif)."""
    runs = runs or RUNS
    script_text = open(script02_path, encoding="utf-8").read()
    os.makedirs(root, exist_ok=True)
    rows = []
    for k, run in enumerate(runs, 1):
        period, start, window = run[0], run[1], run[2]
        extra = run[3] if len(run) > 3 else None
        name = run_folder_name(period, start, window, extra)
        out_dir = os.path.join(root, name)
        os.makedirs(out_dir, exist_ok=True)
        log("=" * 70 + "\n[%d/%d] %s : période %s, début %s, pluie %s\n" % (k, len(runs), name, period, start, window) + "=" * 70)
        t0 = time.time()
        row = {"name": name, "period": period, "start": start, "window": window, "extra_label": extra_label(extra), "report": os.path.join(name, "Stage_Report_02_LPD.html"), "status": "?"}
        try:
            run_one(script_text, period, start, window, inputs, out_dir, log, extra)
            rep = os.path.join(out_dir, "Stage_Report_02_LPD.html")
            if os.path.exists(rep):
                kr = parse_key_results(open(rep, encoding="utf-8").read())
                row["raw"] = tuple("%.1f" % v for v in kr.get("B_QA1_min5", ())) or None
                row["adj"] = tuple("%.1f" % v for v in kr.get("B_QA1_min5_RainAdjusted", ())) or None
                row["status"] = "OK (%d s)" % round(time.time() - t0)
            else:
                row["status"] = "ÉCHEC : rapport absent"
        except Exception as exc:
            row["status"] = "ÉCHEC : %s" % str(exc)[:150]
            log(traceback.format_exc())
        rows.append(row)
    path = os.path.join(root, "LPD_Runs_Comparison.html")
    open(path, "w", encoding="utf-8").write(comparison_html(rows, os.environ.get("AREA_NAME", "")))
    with open(os.path.join(root, "LPD_Runs_Comparison.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["run", "period", "start_year", "rain_window", "extra_settings", "raw_degraded", "raw_stable", "raw_improved", "adj_degraded", "adj_stable", "adj_improved", "status"])
        for r in rows:
            w.writerow([r["name"], r["period"], r["start"], "%02d-%02d" % tuple(r["window"]), r.get("extra_label", "")] + list(r.get("raw") or ["", "", ""]) + list(r.get("adj") or ["", "", ""]) + [r["status"]])
    return rows, path


def main_lpd():
    from qgis.PyQt.QtWidgets import QMessageBox
    from qgis.PyQt.QtCore import QUrl
    R = r"C:\Users\User25\Desktop\résultat Saida"
    D = r"C:\Users\User25\Desktop\DATA Saida"
    s02 = R + r"\Scripts_Saida\06e_QGIS_LPD_Productivite.py"
    inp = {"modis_dir": D + r"\04_MODIS_2000_2025", "qa0_dir": "", "lulc_dir": R + r"\lulc 2", "env_dir": "",
           "aoi_shp": D + r"\00_Boundary\AOI_Saida_UTM.shp", "rain_csv": R + r"\02_Rain\CHIRPS_FromMonthly_Daily_SAIDA.csv", "min_years": MIN_PRODUCTIVITY_YEARS}
    root = R + r"\20_CHIRPS_monthly\09_Designs_LPD"
    os.makedirs(root, exist_ok=True)
    for k in ("modis_dir", "lulc_dir", "aoi_shp", "rain_csv"):
        if not os.path.exists(inp[k]):
            return print("INTROUVABLE :", k, inp[k])
    if not os.path.exists(s02):
        return print("INTROUVABLE :", s02)
    if RUN_ALL_COMBINATIONS:
        rows, path, _idx = run_all_designs(s02, inp, root)
    else:
        rows, path = run_lpd_runs(s02, inp, root)
    print("\n".join("%s : %s" % (r["name"], r["status"]) for r in rows))
    print("Comparatif :", path)
    try:
        from qgis.PyQt.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    except Exception:
        pass




# ===================== (08b) =====================
# -*- coding: utf-8 -*-
"""
LANCEUR 01 — L'INDICATEUR FINAL (ÉTAPE 07) POUR TOUS LES PLANS DE LA PRODUCTIVITÉ   |   QGIS / PyQGIS, SCRIPT AUTONOME

Lit LPD_Designs_Index.json (écrit par 00_RUN_LPD_ALL_DESIGNS.py) et lance l'étape 07 (DEUX périodes : base puis suivi) POUR CHAQUE PLAN, avec les MÊMES cartes LULC, la MÊME matrice
de transition et les MÊMES SOC (que vous gardez comme terminés). Chaque plan donne son propre dossier (<plan>/1_Baseline…, 2_Monitoring…, 3_UNCCD_Final) et ses 12 scénarios
(matrice stricte / robuste / persistante × productivité corrigée ou non × avec ou sans SOC).
Il écrit ensuite UN SEUL tableau maître (Master_Final_Indicator_All_Designs.html + .csv) : les plans en colonnes, les 12 scénarios en lignes, la proportion de terres dégradées dans chaque case.

RÈGLE DE LECTURE : le plan principal et le scénario principal se fixent d'après le TEXTE de l'indication UNCCD et l'étape 02B, AVANT de regarder ce tableau ; le tableau sert à montrer la
fourchette, pas à choisir le plus petit chiffre. MAIN_DESIGN (ci-dessous) ne fait que marquer votre choix dans le tableau.
CE QU'IL NE FAIT PAS : il ne relance ni 02 ni 06 ; ne valide pas la matrice (décision nationale).
UTILISATION : éditer MAIN_DESIGN si besoin, Exécuter dans l'éditeur Python de QGIS, répondre aux questions.
"""
import os
import re
import csv
import json
import html
import time
import gc
import traceback

MAIN_DESIGN = "D01"           # ex. "D03" : marque ce plan comme principal dans le tableau (à décider AVANT de voir les résultats)
AUTO_RUN = False


# ----------------------------------------------------------------------------- LOGIQUE (testée sans QGIS)
def load_index(lpd_root):
    path = os.path.join(lpd_root, "LPD_Designs_Index.json")
    if not os.path.exists(path):
        raise RuntimeError("LPD_Designs_Index.json introuvable dans %s : lancer d'abord 00_RUN_LPD_ALL_DESIGNS.py (même dossier racine)." % lpd_root)
    with open(path, encoding="utf-8") as f:
        return json.load(f)["designs"]


def design_title(d):
    return "%s : début %s, pluie %02d–%02d, état %s (%s–%s)" % (d["id"], d["start"], d["rain_window"][0], d["rain_window"][1], d["state"], d["state_recent"][0], d["state_recent"][1])


def read_final_csv(out_dir):
    path = os.path.join(out_dir, "3_UNCCD_Final", "UNCCD_Final_Indicator.csv")
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def scenario_key(r):
    return "%s | %s | %s" % (r["land_cover_matrix"], r["productivity"], r["soc"])


def run_integration_designs(ns07, common_in, lpd_root, out_root, lang="en", main_design=None, log=print):
    """
    ns07 : espace de noms du script 07 chargé avec AUTO_RUN = False. common_in : lulc_dir, lulc_files, matrix_file, soc_base, soc_mon, primary_lc_variant, primary_rain, primary_soc, excl_water.
    Retourne (résultats par plan, chemin du tableau maître).
    """
    designs = load_index(lpd_root)
    os.makedirs(out_root, exist_ok=True)
    results = []
    for k, d in enumerate(designs, 1):
        row = {"design": d, "status": "?", "rows": []}
        log("=" * 72 + "\n[%d/%d] %s\n" % (k, len(designs), design_title(d)) + "=" * 72)
        if not d.get("complete"):
            row["status"] = "IGNORÉ : exécutions 02 incomplètes (voir le comparatif LPD)"
            results.append(row)
            continue
        t0 = time.time()
        out_d = os.path.join(out_root, "%s_start%s_rain%02d%02d_%s" % (d["id"], d["start"], d["rain_window"][0], d["rain_window"][1], d["state"]))
        common = {"lulc_dir": common_in["lulc_dir"], "lulc_files": common_in["lulc_files"], "matrix_file": common_in["matrix_file"], "out_root": out_d,
                  "primary_lc_variant": common_in["primary_lc_variant"], "primary_rain": common_in["primary_rain"], "primary_soc": common_in["primary_soc"], "excl_water": common_in["excl_water"]}
        try:
            os.makedirs(out_d, exist_ok=True)
            ns07["run_two_periods"](common, {"lpd_dir": d["baseline_dir"], "soc_file": common_in["soc_base"]}, {"lpd_dir": d["monitoring_dir"], "soc_file": common_in["soc_mon"]}, lang, log)
            row["rows"] = read_final_csv(out_d)
            row["out_dir"] = out_d
            row["status"] = "OK (%d s)" % round(time.time() - t0)
        except Exception as exc:
            row["status"] = "ÉCHEC : %s" % str(exc)[:200]
            log(traceback.format_exc())
        results.append(row)
        gc.collect()
    return results, write_master(results, out_root, main_design)


def write_master(results, out_root, main_design=None):
    esc = html.escape
    ok_res = [r for r in results if r["rows"]]
    scen = []
    for r in ok_res:
        for x in r["rows"]:
            if scenario_key(x) not in scen:
                scen.append(scenario_key(x))
    # CSV long
    with open(os.path.join(out_root, "Master_Final_Indicator_All_Designs.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["design", "start_year", "rain_window", "state_window", "land_cover_matrix", "productivity", "soc", "baseline_degraded_pct", "monitoring_degraded_pct", "persistent_ha", "new_ha", "recovered_ha", "improved_ha", "proportion_degraded_pct", "design_main_scenario"])
        for r in ok_res:
            d = r["design"]
            for x in r["rows"]:
                w.writerow([d["id"], d["start"], "%02d-%02d" % tuple(d["rain_window"]), "%s-%s" % tuple(d["state_recent"]), x["land_cover_matrix"], x["productivity"], x["soc"], x["baseline_degraded_pct"], x["monitoring_degraded_pct"],
                            x["persistent_ha"], x["new_ha"], x["recovered_ha"], x["improved_ha"], x["proportion_degraded_pct"], x["main_scenario"]])
    # pivot
    head = "<th>Scénario (matrice | productivité | SOC)</th>" + "".join("<th>%s%s<br><span class='s'>début %s · pluie %02d–%02d<br>état %s–%s</span></th>" % (esc(r["design"]["id"]), " ★ PRINCIPAL" if r["design"]["id"] == main_design else "", r["design"]["start"], r["design"]["rain_window"][0], r["design"]["rain_window"][1], r["design"]["state_recent"][0], r["design"]["state_recent"][1]) for r in ok_res)
    body = []
    for sc in scen:
        cells = []
        for r in ok_res:
            x = next((y for y in r["rows"] if scenario_key(y) == sc), None)
            cells.append("<td class='n%s'>%s</td>" % (" m" if (x and x["main_scenario"] == "yes") else "", esc(x["proportion_degraded_pct"]) if x else ""))
        body.append("<tr><td>%s</td>%s</tr>" % (esc(sc), "".join(cells)))
    def col(r, fn):
        vals = [float(x["proportion_degraded_pct"]) for x in r["rows"]]
        return fn(vals)
    rng = "<tr class='r'><td><b>Minimum du plan</b></td>%s</tr><tr class='r'><td><b>Maximum du plan</b></td>%s</tr><tr class='r'><td><b>Scénario principal du plan (★ dans le script 07)</b></td>%s</tr>" % (
        "".join("<td class='n'>%.2f</td>" % col(r, min) for r in ok_res), "".join("<td class='n'>%.2f</td>" % col(r, max) for r in ok_res),
        "".join("<td class='n'>%s</td>" % esc(next((x["proportion_degraded_pct"] for x in r["rows"] if x["main_scenario"] == "yes"), "")) for r in ok_res))
    st = "".join("<tr><td>%s</td><td>%s</td></tr>" % (esc(design_title(r["design"])), esc(r["status"])) for r in results)
    allv = [float(x["proportion_degraded_pct"]) for r in ok_res for x in r["rows"]]
    summ = ("Sur %d plans et %d scénarios, la proportion de terres dégradées va de %.2f %% à %.2f %%." % (len(ok_res), len(allv), min(allv), max(allv))) if allv else "Aucun plan terminé."
    page = ("<!DOCTYPE html><html lang='fr'><head><meta charset='utf-8'><title>Indicateur final — tous les plans</title><style>body{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#1f2933}h1{color:#0b3d5c}table{border-collapse:collapse;margin:10px 0}th,td{border:1px solid #9aa7b5;padding:5px 9px;font-size:13px;vertical-align:top}th{background:#d6e4f0}.n{text-align:right}.m{background:#fff3cd;font-weight:700}.r td{background:#eef3f8}.s{font-weight:400;font-size:11px;color:#444}.box{background:#f0f7ff;border-left:4px solid #0b3d5c;padding:8px 14px;max-width:1000px}</style></head><body>"
            "<h1>Proportion de terres dégradées — tous les plans de la productivité</h1><div class='box'><p><b>%s</b></p><p>Mêmes LULC, même matrice de transition, mêmes SOC dans tous les plans : seules changent les productivités (année de début, fenêtre de pluie, fenêtre de l'état de la base). "
            "Cases jaunes = scénario principal de chaque plan. Fixer le plan principal d'après le texte de l'indication UNCCD et l'étape 02B <u>avant</u> de lire ce tableau ; rapporter la FOURCHETTE et justifier le choix ; "
            "ne pas retenir un plan parce qu'il donne le plus petit chiffre. Lire les contrôles du rapport 07 final de chaque plan.</p></div><h2>Proportion dégradée (%% des terres)</h2><table><tr>%s</tr>%s%s</table><h2>Plans et exécutions</h2><table><tr><th>Plan</th><th>Statut</th></tr>%s</table></body></html>"
            % (esc(summ), head, "".join(body), rng, st))
    path = os.path.join(out_root, "Master_Final_Indicator_All_Designs.html")
    open(path, "w", encoding="utf-8").write(page)
    return path


def load_script07(path):
    text = open(path, encoding="utf-8").read()
    text2 = re.sub(r"^AUTO_RUN = True", "AUTO_RUN = False", text, count=1, flags=re.M)
    if text2 == text:
        raise RuntimeError("Le script 07 choisi ne contient pas « AUTO_RUN = True » : utiliser la version de scripts/ (07_QGIS_Integration_ODD1531_1OAO.py).")
    ns = {"__name__": "lanceur07"}
    exec(compile(text2, "07_QGIS_Integration_ODD1531_1OAO.py", "exec"), ns)
    return ns


def main_int():
    from qgis.PyQt.QtWidgets import QMessageBox
    from qgis.PyQt.QtCore import QUrl
    R = r"C:\Users\User25\Desktop\résultat Saida"
    s07 = R + r"\Scripts_Saida\08a_QGIS_Integration_ODD1531_1OAO.py"
    lulc = R + r"\lulc 2"
    matrix = R + r"\05_Integration_1OAO\LC_Transition_Matrix_SAIDA_v1_same_as_OEB.csv"
    soc_b = R + r"\soc\04_SOC_Change\SOC_Class_1999_2015.tif"
    soc_m = R + r"\soc\04_SOC_Change\SOC_Class_2015_2025.tif"
    lpd_root = R + r"\20_CHIRPS_monthly\09_Designs_LPD"
    out_root = R + r"\20_CHIRPS_monthly\10_Designs_Integration"
    for p in (s07, lulc, matrix, soc_b, soc_m, os.path.join(lpd_root, "LPD_Designs_Index.json")):
        if not os.path.exists(p):
            return print("INTROUVABLE :", p)
    os.makedirs(out_root, exist_ok=True)
    ns07 = load_script07(s07)
    common = {"lulc_dir": lulc, "lulc_files": ns07["resolve_lulc_files"](lulc), "matrix_file": matrix, "soc_base": soc_b, "soc_mon": soc_m,
              "primary_lc_variant": "robust", "primary_rain": True, "primary_soc": True, "excl_water": True}
    results, path = run_integration_designs(ns07, common, lpd_root, out_root, "en", MAIN_DESIGN)
    print("\n".join("%s : %s" % (design_title(r["design"]), r["status"]) for r in results))
    print("Tableau maitre :", path)
    try:
        from qgis.PyQt.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    except Exception:
        pass




# ----------------------------------------------------------------------------- LANCEMENT
if __name__ != "__never__":
    try:
        print("#" * 70 + "\nETAPE 1/2 : LPD des 8 plans\n" + "#" * 70)
        main_lpd()
        print("#" * 70 + "\nETAPE 2/2 : integration 1OAO des 8 plans\n" + "#" * 70)
        main_int()
        print("TERMINE : voir R\\20_CHIRPS_monthly\\10_Designs_Integration\\Master_Final_Indicator_All_Designs.csv")
    except Exception:
        print(traceback.format_exc())
