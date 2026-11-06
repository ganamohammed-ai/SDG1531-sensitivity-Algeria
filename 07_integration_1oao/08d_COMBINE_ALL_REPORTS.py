# -*- coding: utf-8 -*-
"""
OUTIL 04 — TOUS LES RAPPORTS HTML DE LA CHAÎNE EN UN SEUL FICHIER   |   QGIS / PyQGIS (ou Python), SCRIPT AUTONOME

Parcourt un ou plusieurs dossiers (productivité, LULC, SOC, intégration, sensibilité…), retrouve TOUS les rapports HTML des scripts
(Stage_Report_*.html, Transition_Report*.html, Master_Final_Indicator_All_Designs*.html, LPD_Runs_Comparison*.html) et les range dans UN SEUL fichier :
All_Reports_Combined.html  (+ All_Reports_Index.csv).
Le fichier combiné contient :
  - une vue d'ensemble (un tableau : étape, dossier d'origine, date de génération, statut global, nombre de contrôles PASS / WARN / FAIL / INFO),
  - un menu à gauche (par étape, avec filtre de texte) et le rapport sélectionné à droite, avec ses images et ses tableaux intacts,
  - les rapports tels quels (aucune modification), un bouton pour ouvrir le rapport seul dans un onglet ou l'imprimer.
Les doublons exacts (même contenu) ne sont gardés qu'une fois. Le fichier est autonome (pas de lien vers vos dossiers) : il peut être envoyé tel quel.

CE QU'IL NE FAIT PAS : il ne relit ni ne corrige les rapports ; il n'efface rien ; il ne remplace pas la lecture des contrôles de chaque rapport.
UTILISATION : exécuter dans l'éditeur Python de QGIS (ou « python 04_COMBINE_ALL_REPORTS.py <dossier> [<dossier>…] <sortie.html> »), choisir les dossiers racine, choisir le fichier de sortie.
"""
import os
import re
import sys
import csv
import json
import html
import base64
import hashlib
import datetime as dt
import traceback

AUTO_RUN = True
REPORT_LANG = "en"
MAX_WARN_MB = 400                     # avertissement si le fichier combiné dépasse cette taille

STAGE_ORDER = ["01B", "02B", "02", "02C", "03", "04A", "04B", "05A", "05B", "06", "07", "07F", "07M", "08", "other"]
STAGE_LABEL = {"01B": "01B · Productivity index", "02B": "02B · Start-year / rain-window sensitivity", "02": "02 · Land productivity (LPD)", "02C": "02 · LPD runs comparison", "03": "03 · Land-cover classification",
               "04A": "04A · Review of implausible transitions", "04B": "04B · Transition matrices and choice of dates", "05A": "05A · Validation sampling", "05B": "05B · Accuracy (Olofsson)",
               "06": "06 · Soil organic carbon", "07": "07 · Integration (one period)", "07F": "07 · FINAL baseline + monitoring", "07M": "07 · Master table, all designs", "08": "08 · Baseline-year sensitivity", "other": "Other reports"}
STAGE_LABEL_FR = {"01B": "01B · Indice de productivité", "02B": "02B · Sensibilité année de début / fenêtre de pluie", "02": "02 · Productivité des terres (LPD)", "02C": "02 · Comparatif des exécutions LPD", "03": "03 · Classification de la couverture",
                  "04A": "04A · Revue des transitions improbables", "04B": "04B · Matrices de transition et choix des dates", "05A": "05A · Échantillonnage de validation", "05B": "05B · Exactitude (Olofsson)", "06": "06 · Carbone organique du sol",
                  "07": "07 · Intégration (une période)", "07F": "07 · FINAL base + suivi", "07M": "07 · Tableau maître, tous les plans", "08": "08 · Sensibilité à l'année de base", "other": "Autres rapports"}


# ----------------------------------------------------------------------------- LOGIQUE (testée sans QGIS)
def classify(filename):
    """Étape d'un rapport d'après son nom (les copies « (1) », « _a1b2c3 »… sont reconnues)."""
    n = os.path.basename(filename)
    low = n.lower()
    if re.match(r"^master_final_indicator_all_designs", low):
        return "07M"
    if re.match(r"^lpd_runs_comparison", low):
        return "02C"
    if re.match(r"^transition_report", low):
        return "04B"
    m = re.match(r"^stage_report_(\d{2}[ab]?)_", low)
    if m:
        st = m.group(1).upper()
        if st == "07" and "unccd_final" in low:
            return "07F"
        return st if st in STAGE_ORDER else "other"
    return "other"


def is_report(filename):
    low = os.path.basename(filename).lower()
    return low.endswith(".html") and (low.startswith("stage_report_") or low.startswith("transition_report") or low.startswith("master_final_indicator_all_designs") or low.startswith("lpd_runs_comparison"))


def find_reports(roots):
    out = []
    for root in roots:
        for d, _dirs, files in os.walk(root):
            for f in sorted(files):
                if is_report(f):
                    out.append(os.path.join(d, f))
    return sorted(set(out))


def parse_report(path, raw=None):
    """Métadonnées d'un rapport : titre, étape, dossier d'origine, date, statut global, comptage des contrôles."""
    raw = raw if raw is not None else open(path, "rb").read()
    text = raw.decode("utf-8", errors="replace")
    t = re.search(r"<title>(.*?)</title>", text, re.S)
    title = html.unescape(re.sub(r"\s+", " ", t.group(1))).strip() if t else os.path.basename(path)
    gen = re.search(r"<th>Generated</th><td>([^<]+)</td>", text)
    st = re.search(r"<header>.*?<span class='badge (PASS|WARN|FAIL|INFO)'>", text, re.S)
    sec = re.search(r"<h2 id='checks'>(.*?)(?=<h2 id=|</main>|$)", text, re.S)
    counts = {k: 0 for k in ("PASS", "WARN", "FAIL", "INFO")}
    if sec:
        for k in re.findall(r"<span class='badge (PASS|WARN|FAIL|INFO)'>", sec.group(1)):
            counts[k] += 1
    parts = os.path.normpath(os.path.dirname(path)).split(os.sep)
    ctx = "/".join(parts[-2:]) if len(parts) >= 2 else (parts[-1] if parts else "")
    return {"path": path, "file": os.path.basename(path), "title": title, "stage": classify(path), "context": ctx, "generated": gen.group(1).strip() if gen else "", "status": st.group(1) if st else "",
            "counts": counts, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def collect(roots, log=print):
    """Rapports uniques (doublons exacts écartés), triés par étape puis par date."""
    seen, items, dup = {}, [], 0
    for p in find_reports(roots):
        raw = open(p, "rb").read()
        meta = parse_report(p, raw)
        if meta["sha256"] in seen:
            dup += 1
            seen[meta["sha256"]]["duplicates"].append(p)
            continue
        meta["raw"] = raw
        meta["duplicates"] = []
        seen[meta["sha256"]] = meta
        items.append(meta)
    items.sort(key=lambda m: (STAGE_ORDER.index(m["stage"]) if m["stage"] in STAGE_ORDER else 99, m["generated"], m["context"], m["file"]))
    log("Rapports trouvés : %d uniques, %d doublon(s) exact(s) écarté(s)." % (len(items), dup))
    return items


def build_combined(items, lang=None, title="SDG 15.3.1 — all stage reports"):
    lang = lang or REPORT_LANG
    labels = STAGE_LABEL if lang == "en" else STAGE_LABEL_FR
    T = lambda a, b: a if lang == "en" else b
    esc = html.escape
    data = []
    for i, m in enumerate(items):
        data.append({"id": i, "stage": m["stage"], "title": m["title"], "context": m["context"], "file": m["file"], "generated": m["generated"], "status": m["status"], "counts": m["counts"],
                     "b64": base64.b64encode(m["raw"]).decode("ascii")})
    # vue d'ensemble : un tableau (sans les rapports)
    rows = []
    for i, m in enumerate(items):
        c = m["counts"]
        rows.append("<tr><td><a href='#' onclick='show(%d);return false'>%s</a></td><td>%s</td><td>%s</td><td>%s</td><td><span class='b %s'>%s</span></td><td class='n'>%d</td><td class='n'>%d</td><td class='n'>%d</td><td class='n'>%d</td></tr>" % (
            i, esc(labels.get(m["stage"], m["stage"])), esc(m["context"]), esc(m["file"]), esc(m["generated"]), esc(m["status"] or "—"), esc(m["status"] or "—"), c["PASS"], c["WARN"], c["FAIL"], c["INFO"]))
    tot = {k: sum(m["counts"][k] for m in items) for k in ("PASS", "WARN", "FAIL", "INFO")}
    menu, last = [], None
    for i, m in enumerate(items):
        if m["stage"] != last:
            menu.append("<div class='g'>%s</div>" % esc(labels.get(m["stage"], m["stage"])))
            last = m["stage"]
        menu.append("<a href='#' class='it' id='m%d' data-t='%s' onclick='show(%d);return false'><span class='b %s'>%s</span> %s<br><span class='s'>%s</span></a>" % (
            i, esc((m["context"] + " " + m["file"] + " " + m["title"]).lower(), quote=True), i, esc(m["status"] or "—"), esc((m["status"] or "—")[:4]), esc(m["context"]), esc(m["generated"] or m["file"])))
    css = ("body{margin:0;font-family:Segoe UI,Arial,sans-serif;color:#1f2933}#side{position:fixed;left:0;top:0;bottom:0;width:340px;overflow:auto;background:#f4f6f8;border-right:1px solid #cbd2d9}"
           "#side h1{font-size:15px;margin:0;padding:12px;background:#0b3d5c;color:#fff}#q{width:92%;margin:8px 4%;padding:5px}.g{font-weight:700;font-size:12px;background:#d6e4f0;padding:5px 10px;margin-top:6px}"
           ".it{display:block;padding:6px 10px;font-size:12px;color:#1f2933;text-decoration:none;border-bottom:1px solid #e4e7eb}.it:hover,.it.on{background:#fff3cd}.s{color:#616e7c}"
           "#main{margin-left:340px;height:100vh;display:flex;flex-direction:column}#bar{padding:6px 12px;background:#eef3f8;border-bottom:1px solid #cbd2d9;font-size:13px}#bar button{margin-left:8px}"
           "#view{flex:1;border:0;width:100%}#ov{overflow:auto;padding:18px 24px}table{border-collapse:collapse;font-size:12.5px}th,td{border:1px solid #cbd2d9;padding:3px 8px;text-align:left}th{background:#eef3f8}td.n{text-align:right}"
           ".b{display:inline-block;padding:1px 7px;border-radius:9px;color:#fff;font-size:11px;font-weight:600;background:#546e7a}.PASS{background:#2e7d32}.WARN{background:#ef6c00}.FAIL{background:#c62828}.INFO{background:#546e7a}")
    js = ("var R=JSON.parse(document.getElementById('data').textContent);var cur=-1;"
          "function dec(i){var bin=atob(R[i].b64);var u=new Uint8Array(bin.length);for(var k=0;k<bin.length;k++)u[k]=bin.charCodeAt(k);return u;}"
          "function show(i){var v=document.getElementById('view');document.getElementById('ov').style.display='none';v.style.display='block';cur=i;v.srcdoc=new TextDecoder('utf-8').decode(dec(i));"
          "document.getElementById('cap').textContent=R[i].context+' — '+R[i].file;var a=document.querySelectorAll('.it');for(var k=0;k<a.length;k++)a[k].classList.remove('on');var m=document.getElementById('m'+i);if(m){m.classList.add('on');}}"
          "function home(){document.getElementById('view').style.display='none';document.getElementById('ov').style.display='block';document.getElementById('cap').textContent='';cur=-1;}"
          "function tab(){if(cur<0)return;var b=new Blob([dec(cur)],{type:'text/html;charset=utf-8'});window.open(URL.createObjectURL(b),'_blank');}"
          "function prt(){if(cur<0)return;var v=document.getElementById('view');v.contentWindow.focus();v.contentWindow.print();}"
          "function flt(){var q=document.getElementById('q').value.toLowerCase();var a=document.querySelectorAll('.it');for(var k=0;k<a.length;k++){a[k].style.display=(a[k].getAttribute('data-t').indexOf(q)>=0)?'block':'none';}}")
    page = ("<!DOCTYPE html><html lang='%s'><head><meta charset='utf-8'><title>%s</title><style>%s</style></head><body>"
            "<div id='side'><h1>%s</h1><input id='q' placeholder='%s' oninput='flt()'><div class='g' style='cursor:pointer' onclick='home()'>%s</div>%s</div>"
            "<div id='main'><div id='bar'><b id='cap'></b><button onclick='home()'>%s</button><button onclick='tab()'>%s</button><button onclick='prt()'>%s</button></div>"
            "<div id='ov'><h2>%s</h2><p>%s</p><p><b>%s</b> %d &nbsp; <span class='b PASS'>PASS %d</span> <span class='b WARN'>WARN %d</span> <span class='b FAIL'>FAIL %d</span> <span class='b INFO'>INFO %d</span></p>"
            "<table><tr><th>%s</th><th>%s</th><th>%s</th><th>%s</th><th>%s</th><th>PASS</th><th>WARN</th><th>FAIL</th><th>INFO</th></tr>%s</table></div>"
            "<iframe id='view' style='display:none' sandbox='allow-same-origin allow-modals allow-popups'></iframe></div>"
            "<script id='data' type='application/json'>%s</script><script>%s</script></body></html>") % (
        lang, esc(title), css, esc(title), T("filter (folder, file, title)…", "filtre (dossier, fichier, titre)…"), T("▶ Overview", "▶ Vue d'ensemble"), "".join(menu),
        T("Overview", "Vue d'ensemble"), T("Print", "Imprimer"), T("Open alone", "Ouvrir seul"),
        T("All the reports of the chain in one file", "Tous les rapports de la chaîne dans un fichier"),
        T("Each report is shown as produced by its script (nothing is modified). Read the checks (WARN, FAIL) of each report before using its figures; 'Overall status' is the badge of the report header.",
          "Chaque rapport est montré tel que produit par son script (rien n'est modifié). Lire les contrôles (WARN, FAIL) de chaque rapport avant d'utiliser ses chiffres ; « Statut global » est le badge de l'en-tête du rapport."),
        T("Reports:", "Rapports :"), len(items), tot["PASS"], tot["WARN"], tot["FAIL"], tot["INFO"],
        T("Stage", "Étape"), T("Folder", "Dossier"), T("File", "Fichier"), T("Generated", "Généré"), T("Overall status", "Statut global"), "".join(rows),
        json.dumps(data, ensure_ascii=False).replace("</", "<\\/"), js)
    return page


def write_index(items, path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["stage", "folder", "file", "generated", "overall_status", "PASS", "WARN", "FAIL", "INFO", "bytes", "sha256", "path", "exact_duplicates_skipped"])
        for m in items:
            c = m["counts"]
            w.writerow([m["stage"], m["context"], m["file"], m["generated"], m["status"], c["PASS"], c["WARN"], c["FAIL"], c["INFO"], m["bytes"], m["sha256"], m["path"], " | ".join(m["duplicates"])])
    return path


def combine(roots, out_html, lang=None, log=print):
    items = collect(roots, log)
    if not items:
        raise RuntimeError("Aucun rapport HTML trouvé dans : %s" % ", ".join(roots))
    page = build_combined(items, lang)
    os.makedirs(os.path.dirname(os.path.abspath(out_html)), exist_ok=True)
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(page)
    base = os.path.splitext(os.path.basename(out_html))[0]
    idx = write_index(items, os.path.join(os.path.dirname(os.path.abspath(out_html)), (base.replace("Combined", "Index") if "Combined" in base else base + "_Index") + ".csv"))
    mb = os.path.getsize(out_html) / 1e6
    log("Fichier combiné : %s (%.1f Mo)" % (out_html, mb))
    if mb > MAX_WARN_MB:
        log("ATTENTION : fichier très volumineux ; réduire les dossiers analysés ou ne garder que les rapports utiles.")
    return out_html, idx, items


def main():
    from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox
    from qgis.PyQt.QtCore import QUrl
    roots = []
    while True:
        d = QFileDialog.getExistingDirectory(None, "04 — dossier à parcourir pour trouver les rapports HTML (%d choisi(s)) — Annuler pour terminer" % len(roots), roots[-1] if roots else "")
        if not d:
            break
        roots.append(d)
        if QMessageBox.question(None, "04", "Dossiers choisis : %d\n\nAjouter un autre dossier ?" % len(roots), QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            break
    if not roots:
        return print("Annulé : aucun dossier.")
    out = QFileDialog.getSaveFileName(None, "04 — fichier de SORTIE", os.path.join(roots[0], "All_Reports_Combined.html"), "HTML (*.html)")[0]
    if not out:
        return print("Annulé.")
    out_html, idx, items = combine(roots, out)
    QMessageBox.information(None, "Rapports combinés", "%d rapports\n\n%s\n%s" % (len(items), out_html, idx))
    try:
        from qgis.PyQt.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(out_html))
    except Exception:
        pass


if AUTO_RUN:
    try:
        if len(sys.argv) >= 3 and not any("qgis" in a.lower() for a in sys.argv[:1]):
            combine(sys.argv[1:-1], sys.argv[-1])
        else:
            main()
    except Exception:
        print(traceback.format_exc())
