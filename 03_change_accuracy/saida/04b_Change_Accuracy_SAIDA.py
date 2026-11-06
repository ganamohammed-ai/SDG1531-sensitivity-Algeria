# -*- coding: utf-8 -*-
# 04b: precision du changement (Olofsson et al. 2014) pour Saida. Usage: python 04b.py <tag> <dir_with_KEY_Strata_Rules> <LABELLED.csv> <out_prefix>
import sys, numpy as np, pandas as pd, importlib.util, os
tag, D, LAB, OUT = sys.argv[1:5]
spec = importlib.util.spec_from_file_location("s", os.path.join(D,"04a_Make_Change_Sample_SAIDA.py")); s = importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
rules = pd.read_csv(os.path.join(D,"Rules_Effects.csv"))
eff = {(a,b):(e1,e2) for a,b,e1,e2 in zip(rules.from_code,rules.to_code,rules.effect_strict,rules.effect_robust)}
key = pd.read_csv(os.path.join(D,"Sample_%s_KEY_do_not_open.csv"%tag), encoding="utf-8-sig")
st = pd.read_csv(os.path.join(D,"Strata_%s.csv"%tag), encoding="utf-8-sig").set_index("stratum")
_L = open(LAB, encoding="utf-8-sig").read().splitlines(); _k = next(i for i,l in enumerate(_L) if l.startswith("ID"))
import io; lab = pd.read_csv(io.StringIO("\n".join(_L[_k:])), sep=None, engine="python")
df = key.merge(lab[["ID","Ref_From","Ref_To","Confidence"]], on="ID")
df = df[(df.Ref_From>0)&(df.Ref_To>0)].copy(); print("points interpretes:", len(df))
df["ref_stratum"] = [s.stratum_of(int(f),int(t),eff[(int(f),int(t))][0]) for f,t in zip(df.Ref_From,df.Ref_To)]
df["ref_eff_strict"] = [eff[(int(f),int(t))][0] for f,t in zip(df.Ref_From,df.Ref_To)]
df["ref_eff_robust"] = [eff[(int(f),int(t))][1] for f,t in zip(df.Ref_From,df.Ref_To)]
W = st.weight_W; names = list(st.index); nh = df.groupby("stratum").size().reindex(names).fillna(0)
rows=[]
def analyse(mapcol, refcol, classes, label):
    # proportions p_ij = W_i n_ij / n_i  (i = classe carte/strate, j = reference)
    wi = df.groupby("stratum").size().reindex(names).fillna(0)
    P = pd.DataFrame(0.0,index=classes,columns=classes)
    cnt = pd.crosstab(df[mapcol],df[refcol]).reindex(index=classes,columns=classes).fillna(0)
    # poids de chaque classe de carte = somme des W des strates
    if mapcol=="stratum": Wc = W.reindex(classes)
    else:
        Wc = pd.Series({c: W[[n for n in names if df[df.stratum==n][mapcol].iloc[0:1].tolist() and True]].sum() for c in classes}) if False else None
    return cnt
# --- (1) precision des strates de changement ---
cnt = pd.crosstab(df.stratum, df.ref_stratum).reindex(index=names, columns=names).fillna(0)
ni = cnt.sum(axis=1); P = cnt.div(ni.replace(0,np.nan),axis=0).fillna(0).mul(W,axis=0)
OA = np.trace(P.values); 
V_oa = sum(W[i]**2*(cnt.loc[i,i]/ni[i])*(1-cnt.loc[i,i]/ni[i])/(ni[i]-1) for i in names if ni[i]>1)
UA = pd.Series({i: cnt.loc[i,i]/ni[i] if ni[i]>0 else np.nan for i in names})
PA = pd.Series({j: P.loc[j,j]/P[j].sum() if P[j].sum()>0 else np.nan for j in names})
res1 = pd.DataFrame({"n_interpretes":ni,"poids_W":W,"UA_precision_utilisateur":UA,"PA_precision_producteur":PA}).round(3)
res1.to_csv(OUT+"_strata_accuracy.csv", encoding="utf-8-sig", sep=";", decimal=",")
# --- (2) precision de l'effet D/S/I (strict et robust) ---
eff_map = {n: None for n in names}
key["emap"]=key.effect_strict; key["emap_r"]=key.effect_robust
def eff_acc(mapc, refc, label):
    d = df.merge(key[["ID","emap","emap_r"]],on="ID")
    mc = "emap" if mapc=="strict" else "emap_r"
    cl = ["D","S","I"]
    # Wi par strate -> proportions p[strate, ref effect]
    out=[]; Pm = pd.DataFrame(0.0,index=cl,columns=cl); V=0
    # estimation par strate puis agregation par classe-carte d'effet
    cc = pd.DataFrame(0.0,index=cl,columns=cl)
    for h in names:
        dh = d[d.stratum==h]
        if len(dh)==0: continue
        for _,r in dh.iterrows(): cc.loc[r[mc], r[refc]] += W[h]/len(dh)   # contribution p_hj ventilee
    OAe = np.trace(cc.values)
    Wm = cc.sum(axis=1); Wr = cc.sum(axis=0)
    UAe = pd.Series({c: cc.loc[c,c]/Wm[c] if Wm[c]>0 else np.nan for c in cl}); PAe = pd.Series({c: cc.loc[c,c]/Wr[c] if Wr[c]>0 else np.nan for c in cl})
    # variance approchee (bootstrap stratifie)
    rng = np.random.default_rng(1); oas=[]
    for _ in range(2000):
        a=0.0
        for h in names:
            dh = d[d.stratum==h]
            if len(dh)==0: continue
            sm = dh.sample(len(dh),replace=True,random_state=int(rng.integers(1e9)))
            a += W[h]*(sm[mc]==sm[refc]).mean()
        oas.append(a)
    ci=np.percentile(oas,[2.5,97.5])
    return cc, OAe, ci, UAe, PAe, d
lines=[]
for mapc,refc,lab_ in (("strict","ref_eff_strict","strict"),("robust","ref_eff_robust","robust")):
    cc,OAe,ci,UAe,PAe,d = eff_acc(mapc,refc,lab_)
    lines.append("EFFET %s : precision globale (aire ponderee) %.3f  IC95%% bootstrap [%.3f ; %.3f]"%(lab_,OAe,ci[0],ci[1]))
    lines.append("  UA (D,S,I): "+", ".join("%s=%.2f"%(k,v) for k,v in UAe.items())+" | PA: "+", ".join("%s=%.2f"%(k,v) for k,v in PAe.items()))
    lines.append("  surface estimee corrigee (part du territoire) D/S/I d'apres la reference: "+", ".join("%s=%.2f%%"%(k,100*v) for k,v in cc.sum(axis=0).items())+" ; d'apres la carte: "+", ".join("%s=%.2f%%"%(k,100*v) for k,v in cc.sum(axis=1).items()))
    cc.round(5).to_csv(OUT+"_effect_%s_matrix.csv"%lab_, encoding="utf-8-sig", sep=";", decimal=",")
# --- (3) precision des classes LULC aux deux dates ---
fa = (df.map_from==df.Ref_From); ta = (df.map_to==df.Ref_To)
wt = df.stratum.map(W)/df.stratum.map(ni.rename(lambda x:x))
wt = df.stratum.map(lambda h: W[h]/nh[h])
lines.append("PRECISION DES CLASSES : date 1 (ponderee) %.3f ; date 2 (ponderee) %.3f ; (non ponderee %.3f / %.3f)"%((wt*fa).sum(),(wt*ta).sum(),fa.mean(),ta.mean()))
lines.append("PRECISION DES STRATES DE CHANGEMENT (OA ponderee) %.3f  (+-%.3f IC95%%)"%(OA,1.96*np.sqrt(V_oa)))
lines.append("Par confiance (non ponderee, effet strict correct): "+", ".join("conf %d: %.2f (n=%d)"%(c,(g.effect_strict==g.ref_eff_strict).mean(),len(g)) for c,g in df.groupby("Confidence")))
open(OUT+"_summary.txt","w",encoding="utf-8").write("\n".join(lines)); print("\n".join(lines)); print(res1.to_string())
df.to_csv(OUT+"_joined.csv",index=False,encoding="utf-8-sig",sep=";",decimal=",")
