# -*- coding: utf-8 -*-
"""
LANCEUR 00 — TOUS LES PLANS D'EXPÉRIENCE DE LA PRODUCTIVITÉ (ÉTAPE 02, LPD) EN UNE SEULE FOIS   |   QGIS / PyQGIS, SCRIPT AUTONOME

Il vous pose les questions UNE seule fois (fichiers et dossiers), puis lance 02_QGIS_LPD_Productivite.py autant de fois qu'il le faut pour couvrir TOUTES les combinaisons de :
    - année de début de la série            (DESIGN_AXES["start"]        : 2000 = convention UNCCD ; 2003 = après la sécheresse de début de série),
    - fenêtre de pluie de la correction     (DESIGN_AXES["rain_window"]  : (9, 6) sept.-juin ; (12, 4) déc.-avril),
    - fenêtre de l'ÉTAT de la période de base (DESIGN_AXES["state"]       : 3 ans 2013-2015 contre le début-2012 ; 5 ans 2011-2015 contre le début-2010).
Chaque exécution a son dossier ; la période de SUIVI ne dépend pas de la fenêtre de l'état de la base : elle n'est calculée qu'une fois par (début, fenêtre de pluie).
Il écrit LPD_Designs_Index.json (qui retrouve les dossiers de chaque plan : lu par 01_RUN_INTEGRATION_ALL_DESIGNS.py) et un tableau comparatif (LPD_Runs_Comparison.html + .csv).

CE QU'IL NE FAIT PAS : il ne décide pas quel plan est le principal (à fixer d'après le texte de l'indication UNCCD et l'étape 02B, AVANT de regarder les résultats) ;
ne remplace aucun contrôle des rapports ; n'exécute ni 06 (SOC) ni 07 (voir le lanceur 01).
UTILISATION : ouvrir ce fichier dans l'éditeur Python de QGIS, régler DESIGN_AXES (ou RUN_ALL_COMBINATIONS = False et RUNS), Exécuter, répondre aux questions.
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
AUTO_RUN = True


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


def main():
    from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox
    from qgis.PyQt.QtCore import QUrl
    Q = QFileDialog
    ask = lambda title, kind, flt="": (Q.getExistingDirectory(None, title, "") if kind == "dir" else Q.getOpenFileName(None, title, "", flt)[0])
    s02 = ask("0/8 — le script 02_QGIS_LPD_Productivite.py (version de scripts/)", "file", "Python (*.py)")
    if not s02:
        return print("Annulé.")
    modis = ask("1/8 — dossier des exports MODIS (01 + 01b)", "dir")
    qa0 = ask("2/8 — dossier du scénario A (_QA0) — Annuler si absent", "dir")
    lulc = ask("3/8 — dossier des cartes LULC", "dir")
    env = ask("4/8 — dossier des couches environnementales — Annuler si absent", "dir")
    aoi = ask("5/8 — limite de la zone Study_Area_Final.shp — Annuler si absente (déconseillé)", "file", "Vecteur (*.shp *.gpkg *.geojson)")
    rain = ask("6/8 — pluie journalière ClimateEngine.csv", "file", "CSV (*.csv *.txt)")
    root = ask("7/8 — dossier RACINE de sortie (un sous-dossier par exécution)", "dir")
    if not (modis and lulc and root and rain):
        return print("Annulé : MODIS, LULC, pluie et dossier de sortie sont requis.")
    inp = {"modis_dir": modis, "qa0_dir": qa0, "lulc_dir": lulc, "env_dir": env, "aoi_shp": aoi, "rain_csv": rain, "min_years": MIN_PRODUCTIVITY_YEARS}
    if RUN_ALL_COMBINATIONS:
        rows, path, _idx = run_all_designs(s02, inp, root)
    else:
        rows, path = run_lpd_runs(s02, inp, root)
    QMessageBox.information(None, "LPD — exécutions terminées", "\n".join("%s : %s" % (r["name"], r["status"]) for r in rows) + "\n\nComparatif : " + path)
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
