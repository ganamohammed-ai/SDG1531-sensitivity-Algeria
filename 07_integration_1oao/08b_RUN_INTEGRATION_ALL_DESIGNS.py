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

MAIN_DESIGN = None            # ex. "D03" : marque ce plan comme principal dans le tableau (à décider AVANT de voir les résultats)
AUTO_RUN = True


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


def main():
    from qgis.PyQt.QtWidgets import QFileDialog, QInputDialog, QMessageBox
    from qgis.PyQt.QtCore import QUrl
    ask = lambda title, kind, flt="": (QFileDialog.getExistingDirectory(None, title, "") if kind == "dir" else QFileDialog.getOpenFileName(None, title, "", flt)[0])
    s07 = ask("0/9 — le script 07_QGIS_Integration_ODD1531_1OAO.py (version de scripts/)", "file", "Python (*.py)")
    lulc = ask("1/9 — dossier des cartes LULC (les six dates)", "dir")
    matrix = ask("2/9 — matrice de transition (LC_Transition_Matrix_OEB_v1.csv)", "file", "CSV (*.csv)")
    soc_b = ask("3/9 — SOC de la BASE : SOC_Class_1999_2015.tif", "file", "Raster (*.tif)")
    soc_m = ask("4/9 — SOC du SUIVI : SOC_Class_2015_2025.tif", "file", "Raster (*.tif)")
    lpd_root = ask("5/9 — dossier RACINE des LPD (celui qui contient LPD_Designs_Index.json)", "dir")
    out_root = ask("6/9 — dossier RACINE de sortie (un sous-dossier par plan)", "dir")
    if not all((s07, lulc, matrix, soc_b, soc_m, lpd_root, out_root)):
        return print("Annulé : tous les fichiers et dossiers sont requis.")
    variant, ok1 = QInputDialog.getItem(None, "7/9", "Matrice du scénario PRINCIPAL de chaque plan :", ["robust", "strict", "persistent"], 0, False)
    prod, ok2 = QInputDialog.getItem(None, "8/9", "Productivité du scénario principal :", ["corrigée de la pluie", "non corrigée"], 0, False)
    soc, ok3 = QInputDialog.getItem(None, "9/9", "SOC dans le scénario principal :", ["inclure", "exclure"], 0, False)
    if not (ok1 and ok2 and ok3):
        return print("Annulé.")
    ns07 = load_script07(s07)
    common = {"lulc_dir": lulc, "lulc_files": ns07["resolve_lulc_files"](lulc), "matrix_file": matrix, "soc_base": soc_b, "soc_mon": soc_m, "primary_lc_variant": variant,
              "primary_rain": prod.startswith("corrig"), "primary_soc": soc == "inclure", "excl_water": True}
    results, path = run_integration_designs(ns07, common, lpd_root, out_root, "en", MAIN_DESIGN)
    QMessageBox.information(None, "Indicateur final — tous les plans", "\n".join("%s : %s" % (design_title(r["design"]), r["status"]) for r in results) + "\n\nTableau maître : " + path)
    try:
        from qgis.PyQt.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    except Exception:
        pass


if AUTO_RUN:
    try:
        main()
    except Exception:
        print(traceback.format_exc())
