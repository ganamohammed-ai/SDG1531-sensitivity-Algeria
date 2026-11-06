# -*- coding: utf-8 -*-
# QGIS : colle ce script dans l'editeur Python de QGIS puis Run.
# Telecharge, pour chacun des 410 points D04, une vignette (+-120 m) Wayback "debut" (2015-05-13) et "fin" (2025-05-29),
# puis construit DEUX fichiers HTML autonomes (images integrees, hors ligne), un par lecteur, avec un ordre aleatoire different.
# 1) Mets TEST_N = 3 pour un essai rapide, verifie le dossier chips, puis remets TEST_N = 0 pour tout faire.
# 2) Le script peut etre relance : les vignettes deja telechargees ne sont pas retelechargees.
import os, csv, io, math, json, base64, random, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from qgis.PyQt.QtGui import QImage, QPainter
from qgis.PyQt.QtCore import Qt, QBuffer, QByteArray, QIODevice

# ------------------------------------------------------------------ CONFIG
KIT_CSV = r"D:\Résultat finale\3_Results\10_Visual_Verification\D04_Blind_Kit\D04_Blind_Points_for_readers.csv"
OUT_DIR = r"D:\Résultat finale\3_Results\10_Visual_Verification\D04_Human_Reading"
TARGETS = ("2015-05-13", "2025-05-29")      # date de la release Wayback voulue : debut, fin
HALF_M = 120.0                              # demi-cote de la vignette au sol (m)
OUT_PX = 400                                # taille de la vignette (px)
JPG_Q = 80
READERS = [("Reader1", 2026), ("Reader2", 2027)]   # nom, graine de l'ordre aleatoire
TEST_N = 0                                  # 0 = tous les points ; 3 = essai
WB_CONFIG = "https://s3-us-west-2.amazonaws.com/config.maptiles.arcgis.com/waybackconfig.json"
UA = {"User-Agent": "Mozilla/5.0 (D04-verification)"}

def E(cls, name, scoped):
    return getattr(cls, name, None) or getattr(getattr(cls, scoped), name)

FMT = E(QImage, "Format_RGB32", "Format")
KEEP = E(Qt, "KeepAspectRatio", "AspectRatioMode")
SMOOTH = E(Qt, "SmoothTransformation", "TransformationMode")
WRITE = E(QIODevice, "WriteOnly", "OpenModeFlag")

# ------------------------------------------------------------------ RESEAU
def get(url, tries=3):
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
                return r.read()
        except Exception:
            time.sleep(0.6 * (k + 1))
    return None

def load_releases():
    j = json.loads(get(WB_CONFIG).decode("utf-8"))
    import re
    rel = []
    for k, v in j.items():
        m = re.search(r"(\d{4}-\d{2}-\d{2})", v.get("itemTitle", ""))
        if m:
            rel.append(dict(k=k, d=m.group(1), url=v["itemURL"].replace("{level}", "{z}").replace("{row}", "{y}").replace("{col}", "{x}")))
    rel.sort(key=lambda r: r["d"])
    return rel

def days(d):
    return time.mktime(time.strptime(d, "%Y-%m-%d")) / 86400.0

def tile_url(rel, z, x, y):
    return rel["url"].replace("{z}", str(z)).replace("{x}", str(x)).replace("{y}", str(y))

def decode(data):
    if not data:
        return None
    img = QImage()
    return img if img.loadFromData(data) else None

def good_tile(img):
    """Tuile utile : au moins 200 px et pas un aplat (« donnees non disponibles »)."""
    if img is None or img.width() < 200:
        return False
    vals = [img.pixelColor(x, y).red() for x in range(8, img.width(), 24) for y in range(8, img.height(), 24)]
    m = sum(vals) / len(vals)
    sd = (sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5
    return sd > 6

def frac_tile(lat, lon, z):
    n = 2 ** z
    return (lon + 180.0) / 360.0 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n

def make_chip(lat, lon, rel, z):
    n = 2 ** z
    fx, fy = frac_tile(lat, lon, z)
    tx, ty = int(fx), int(fy)
    u, v = (fx - (tx - 1)) * 256.0, (fy - (ty - 1)) * 256.0      # position du point dans la mosaique 3x3 (768 px)
    mpp = 156543.03392 * math.cos(math.radians(lat)) / n
    half = min(int(round(HALF_M / mpp)), int(u), int(768 - u), int(v), int(768 - v))
    jobs = [(i, j) for i in range(3) for j in range(3)]
    with ThreadPoolExecutor(max_workers=9) as ex:
        res = list(ex.map(lambda ij: get(tile_url(rel, z, tx - 1 + ij[0], ty - 1 + ij[1])), jobs))
    canvas = QImage(768, 768, FMT)
    canvas.fill(0xFF808080)
    p = QPainter(canvas)
    for (i, j), data in zip(jobs, res):
        t = decode(data)
        if t is not None:
            p.drawImage(i * 256, j * 256, t)
    p.end()
    crop = canvas.copy(int(u) - half, int(v) - half, 2 * half, 2 * half).scaled(OUT_PX, OUT_PX, KEEP, SMOOTH)
    ba = QByteArray(); buf = QBuffer(ba); buf.open(WRITE)
    crop.save(buf, "JPG", JPG_Q); buf.close()
    return bytes(ba.data())

def find_chip(lat, lon, rels, target, hint):
    """Release la plus proche de la date voulue qui a vraiment une image a cet endroit."""
    c = sorted(rels, key=lambda r: abs(days(r["d"]) - days(target)))[:30]
    if hint is not None:
        c = [hint] + [r for r in c if r is not hint]
    for r in c:
        for z in (18, 17):
            fx, fy = frac_tile(lat, lon, z)
            if good_tile(decode(get(tile_url(r, z, int(fx), int(fy))))):
                return r, z, make_chip(lat, lon, r, z)
    return None, None, None

# ------------------------------------------------------------------ HTML
TEMPLATE = r"""<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>قراءة D04 العمياء - __READER__</title>
<style>
:root{--bg:#fbfaf7;--fg:#1f2328;--mu:#5b6470;--ac:#1f6f4a;--bd:#ddd9cf;--card:#fff;--D:#b8372b;--N:#1f6f4a;--U:#8a6d00}
@media(prefers-color-scheme:dark){:root{--bg:#15181b;--fg:#e8e6e1;--mu:#9aa3ad;--ac:#5fc08f;--bd:#33383e;--card:#1d2125;--D:#e5786d;--N:#5fc08f;--U:#d9b84a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,"Segoe UI",Tahoma,Arial,sans-serif}
header{display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:8px 12px;border-bottom:1px solid var(--bd);background:var(--card)}
header h1{font-size:16px;margin:0}.sp{flex:1}.mu{color:var(--mu)}
.bar{height:6px;background:var(--bd)}.bar i{display:block;height:100%;background:var(--ac);width:0}
.panes{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:8px 12px}
.pane{background:var(--card);border:1px solid var(--bd);border-radius:8px;overflow:hidden}
.pane h2{margin:0;padding:4px 8px;font-size:13px;border-bottom:1px solid var(--bd);display:flex;justify-content:space-between}
.vp{position:relative;width:100%;aspect-ratio:1/1;max-height:62vh;margin:0 auto;overflow:hidden;background:#222}
.zw{position:absolute;inset:0;transform-origin:center;transition:transform .08s}
.zw img{width:100%;height:100%;display:block}
.sq{position:absolute;left:50%;top:50%;width:__SQ__%;height:__SQ__%;transform:translate(-50%,-50%);border:2px solid #ffeb3b;pointer-events:none}
.noimg{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#ddd;text-align:center;padding:20px}
.form{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:6px 12px 14px}
button,select,input,textarea{font:inherit;color:var(--fg);background:var(--card);border:1px solid var(--bd);border-radius:6px;padding:5px 9px}
button{cursor:pointer}button.v{font-weight:600;min-width:104px}
button.v.D.on{background:var(--D);color:#fff}button.v.N.on{background:var(--N);color:#fff}button.v.U.on{background:var(--U);color:#fff}
textarea{width:min(520px,100%);height:44px}
@media(max-width:800px){.panes{grid-template-columns:1fr}}
</style></head><body>
<header><h1>قراءة D04 العمياء</h1><label>القارئ <input id="who" value="__READER__" style="width:110px"></label>
<b id="cur"></b><span class="sp"></span><span class="mu" id="cnt"></span>
<button id="exp">حفظ النتائج (CSV)</button><label class="mu" style="cursor:pointer">استعادة <input id="imp" type="file" accept=".csv" hidden></label></header>
<div class="bar"><i id="barf"></i></div>
<div class="panes">
<div class="pane"><h2><span>البداية</span><span class="mu" id="l1"></span></h2><div class="vp"><div class="zw" id="z1"><img id="i1"><div class="sq"></div></div></div></div>
<div class="pane"><h2><span>النهاية</span><span class="mu" id="l2"></span></h2><div class="vp"><div class="zw" id="z2"><img id="i2"><div class="sq"></div></div></div></div>
</div>
<div class="form">
<button id="prev">&rarr; السابق (→)</button><button id="next">التالي (←) &larr;</button><button id="nextu">أول غير مقروءة</button>
<label>اذهب إلى # <input id="goto" type="number" min="1" max="410" style="width:76px"></label>
<label>تكبير <input id="zoom" type="range" min="1" max="3" step="0.25" value="1"></label>
<span style="width:10px"></span>
<button class="v D" data-v="Degraded">Degraded (D)</button><button class="v N" data-v="NotDeg">NotDeg (N)</button><button class="v U" data-v="Unclear">Unclear (U)</button>
<select id="ct"><option value="">نوع التغير (1-8)</option></select>
<select id="cf"><option value="">الثقة (H/M/L)</option><option>H</option><option>M</option><option>L</option></select>
<textarea id="nt" placeholder="ملاحظات قصيرة تبرر الحكم"></textarea></div>
<p class="mu" style="padding:0 12px 16px">المربع الأصفر = بكسل 30 م الذي تحكم عليه. الحكم على ما تراه في الصورتين فقط. Degraded = دليل بنيوي على التدهور (فقدان غطاء وتربة عارية، بناء، تحويل مرعى إلى حقل، تعرية)؛ اختلاف اللون وحده = NotDeg؛ صورة لا تسمح بالمقارنة = Unclear. الصورتان من Wayback: تاريخ الإصدار وليس بالضرورة تاريخ الالتقاط. لا تفتح مفتاح الطبقات قبل أن ينتهي القارئان.</p>
<script>
const PTS=__DATA__;
const CT=["COVER_LOSS","TO_BUILT","TO_CROP","SOIL_EROSION","NO_CHANGE","SEASONAL","RECOVERY","OTHER"];
const KEY="D04_reading___READER__";
const $=id=>document.getElementById(id);
let A={},idx=0;
try{A=JSON.parse(localStorage.getItem(KEY)||"{}")}catch(e){A={}}
function save(){try{localStorage.setItem(KEY,JSON.stringify(A))}catch(e){}}
CT.forEach((c,i)=>{const o=document.createElement("option");o.value=c;o.textContent=(i+1)+" "+c;$("ct").appendChild(o)});
function show(){
 const p=PTS[idx];$("cur").textContent="#"+p[0]+"  ("+(idx+1)+"/"+PTS.length+")";
 [1,2].forEach(k=>{const im=$("i"+k),src=p[2+k];im.style.display=src?"block":"none";if(src)im.src=src;
  const w=$("z"+k);let n=w.querySelector(".noimg");if(!src){if(!n){n=document.createElement("div");n.className="noimg";w.appendChild(n)}n.textContent="لا توجد صورة هنا: احكم Unclear أو افتح Google Earth"}else if(n)n.remove();
  $("l"+k).textContent=p[4+k]||""});
 const a=A[p[0]]||{};
 document.querySelectorAll("button.v").forEach(b=>b.classList.toggle("on",a.v===b.dataset.v));
 $("ct").value=a.ct||"";$("cf").value=a.cf||"";$("nt").value=a.nt||"";
 let n=0;for(const k in A)if(A[k].v)n++;$("cnt").textContent="مقروء "+n+" / "+PTS.length;$("barf").style.width=(100*n/PTS.length)+"%";
}
function rec(){const p=PTS[idx];return A[p[0]]=A[p[0]]||{}}
function setV(v){rec().v=v;save();show()}
function go(i){idx=Math.max(0,Math.min(PTS.length-1,i));show()}
document.querySelectorAll("button.v").forEach(b=>b.onclick=()=>setV(b.dataset.v));
$("ct").onchange=()=>{rec().ct=$("ct").value;save()};$("cf").onchange=()=>{rec().cf=$("cf").value;save()};
$("nt").oninput=()=>{rec().nt=$("nt").value;save()};
$("nt").onkeydown=e=>{if(e.key==="Escape"){$("nt").blur()}else if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();$("nt").blur();go(idx+1)}};
$("prev").onclick=()=>go(idx-1);$("next").onclick=()=>go(idx+1);
$("nextu").onclick=()=>{for(let i=0;i<PTS.length;i++){if(!(A[PTS[i][0]]||{}).v){go(i);return}}};
$("goto").onchange=()=>{const t=+$("goto").value;const i=PTS.findIndex(p=>p[0]===t);if(i>=0)go(i)};
$("zoom").oninput=()=>{[1,2].forEach(k=>$("z"+k).style.transform="scale("+$("zoom").value+")")};
document.addEventListener("keydown",e=>{
 if(["TEXTAREA","INPUT"].includes(e.target.tagName)&&e.target.type!=="range")return;
 const k=e.key.toLowerCase();
 if(k==="d")setV("Degraded");else if(k==="n")setV("NotDeg");else if(k==="u")setV("Unclear");
 else if(k==="h"||k==="m"||k==="l"){rec().cf=k.toUpperCase();save();show()}
 else if(/^[1-8]$/.test(k)){rec().ct=CT[+k-1];save();show()}
 else if(e.key==="ArrowLeft"||e.key==="Enter")go(idx+1);else if(e.key==="ArrowRight")go(idx-1)});
function q(s){s=String(s==null?"":s);return /[",\n\r]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s}
$("exp").onclick=()=>{
 const byId={};PTS.forEach(p=>byId[p[0]]=p);
 const ids=PTS.map(p=>p[0]).sort((a,b)=>a-b);
 let out="BlindID,Lat,Lon,Verdict_Reader,ChangeType,ImgStart,ImgEnd,Conf,Notes,Analyst\n";
 ids.forEach(i=>{const p=byId[i],a=A[i]||{};out+=[i,p[1][0],p[1][1],a.v||"",a.ct||"",p[5]||"",p[6]||"",a.cf||"",a.nt||"",$("who").value].map(q).join(",")+"\n"});
 const b=new Blob(["\ufeff"+out],{type:"text/csv;charset=utf-8"}),u=URL.createObjectURL(b),l=document.createElement("a");
 l.href=u;l.download="__READER___D04.csv";l.click();setTimeout(()=>URL.revokeObjectURL(u),2000)};
function parse(t){const rows=[];let r=[],f="",inq=false;for(let i=0;i<t.length;i++){const c=t[i];
 if(inq){if(c==='"'){if(t[i+1]==='"'){f+='"';i++}else inq=false}else f+=c}
 else if(c==='"')inq=true;else if(c===","){r.push(f);f=""}else if(c==="\n"){r.push(f);rows.push(r);r=[];f=""}else if(c!=="\r")f+=c}
 if(f!==""||r.length){r.push(f);rows.push(r)}return rows}
$("imp").onchange=e=>{const fl=e.target.files[0];if(!fl)return;const rd=new FileReader();rd.onload=()=>{
 const rows=parse(String(rd.result).replace(/^\ufeff/,""));const h=rows[0];const ix=n=>h.indexOf(n);
 rows.slice(1).forEach(r=>{const id=+r[ix("BlindID")];if(!id)return;const v=r[ix("Verdict_Reader")];if(v||r[ix("Notes")])A[id]={v:v,ct:r[ix("ChangeType")],cf:r[ix("Conf")],nt:r[ix("Notes")]}});
 save();show()};rd.readAsText(fl,"utf-8")};
window.addEventListener("beforeunload",e=>{let n=0;for(const k in A)if(A[k].v)n++;if(n>0){e.preventDefault();e.returnValue=""}});
show();
</script></body></html>"""

def build_html(reader, seed, pts, chips_dir, meta):
    order = list(pts)
    random.Random(seed).shuffle(order)
    data = []
    for bid, lat, lon in order:
        m = meta.get(str(bid), {})
        imgs = []
        for k in ("s", "e"):
            fp = os.path.join(chips_dir, "%d_%s.jpg" % (bid, k))
            imgs.append("data:image/jpeg;base64," + base64.b64encode(open(fp, "rb").read()).decode("ascii") if os.path.exists(fp) else "")
        # layout used by the page: [id, [lat, lon], unused, image start, image end, label start, label end]
        data.append([bid, [lat, lon], 0, imgs[0], imgs[1], m.get("ls", ""), m.get("le", "")])
    return (TEMPLATE.replace("__READER__", reader)
            .replace("__SQ__", "%.3f" % (100.0 * 30.0 / (2 * HALF_M)))
            .replace("__DATA__", json.dumps(data, ensure_ascii=False)))

# ------------------------------------------------------------------ MAIN
def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    chips = os.path.join(OUT_DIR, "chips"); os.makedirs(chips, exist_ok=True)
    pts = []
    for r in csv.DictReader(open(KIT_CSV, encoding="utf-8-sig")):
        pts.append((int(r["BlindID"]), float(r["Lat"]), float(r["Lon"])))
    if TEST_N:
        pts = pts[:TEST_N]
    mp = os.path.join(OUT_DIR, "chips_meta.json")
    meta = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {}
    rels = load_releases()
    print("releases Wayback:", len(rels))
    hint = [None, None]
    t0 = time.time()
    for n, (bid, lat, lon) in enumerate(pts, 1):
        m = meta.setdefault(str(bid), {})
        for i, (k, lab) in enumerate((("s", "ls"), ("e", "le"))):
            fp = os.path.join(chips, "%d_%s.jpg" % (bid, k))
            if os.path.exists(fp) and lab in m:
                continue
            rel, z, jpg = find_chip(lat, lon, rels, TARGETS[i], hint[i])
            if jpg is None:
                m[lab] = "لا توجد صورة"
                continue
            hint[i] = rel
            open(fp, "wb").write(jpg)
            m[lab] = "Wayback %s (z%d)" % (rel["d"], z)
        if n % 10 == 0 or n == len(pts):
            json.dump(meta, open(mp, "w", encoding="utf-8"), ensure_ascii=False)
            print("%d/%d  (%.0f s)" % (n, len(pts), time.time() - t0))
    json.dump(meta, open(mp, "w", encoding="utf-8"), ensure_ascii=False)
    miss = [b for b, _, _ in pts if not (os.path.exists(os.path.join(chips, "%d_s.jpg" % b)) and os.path.exists(os.path.join(chips, "%d_e.jpg" % b)))]
    print("points sans image complete:", len(miss), miss[:20])
    for name, seed in READERS:
        fn = os.path.join(OUT_DIR, "%s_D04_Reading.html" % name)
        open(fn, "w", encoding="utf-8").write(build_html(name, seed, pts, chips, meta))
        print("ecrit:", fn, "(%.1f Mo)" % (os.path.getsize(fn) / 1e6))

if not os.environ.get("D04_NO_RUN"):
    main()
