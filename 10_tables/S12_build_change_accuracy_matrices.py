"""S9 (change accuracy matrices, both provinces) from the change-accuracy tables of the Zenodo deposit.
Usage: python S12_build_change_accuracy_matrices.py <unzipped Zenodo folder>  (needs pandas, xlsxwriter)."""
import os, sys
DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")   # unzipped Zenodo deposit
import pandas as pd, numpy as np
S=os.path.join(DATA,"07_Accuracy_Samples","Saida","Change_Accuracy")+os.sep
O=os.path.join(DATA,"07_Accuracy_Samples","OEB","Change_Accuracy")+os.sep
names=["D1_Range_to_Crop","D2_Range_to_Bare_or_Fallow","D3_Crop_or_Fallow_to_Bare","D4_Forest_loss","D5_To_Built","I1_Bare_to_Range","I2_Bare_to_Crop_or_Fallow","I3_To_Forest","S1_Stable","S2_Other_change"]
def rd(p,**k): return pd.read_csv(p,sep=None,engine="python",encoding="utf-8-sig",**k)
def num(s): return pd.to_numeric(s.astype(str).str.replace(",","."),errors="coerce")
sheets={}
for per in("1999_2015","2015_2025"):
    j=rd(S+f"Change_Accuracy_{per}_joined.csv")
    cnt=pd.crosstab(j["stratum"],j["ref_stratum"]).reindex(index=names,columns=names).fillna(0).astype(int)
    cnt["total"]=cnt.sum(axis=1)
    sa=rd(S+f"Change_Accuracy_{per}_strata_accuracy.csv",index_col=0)
    for c in sa.columns: sa[c]=num(sa[c])
    cnt["weight_W"]=sa["poids_W"]; cnt["UA"]=sa["UA_precision_utilisateur"]; cnt["PA"]=sa["PA_precision_producteur"]
    sheets[f"Saida_{per}_strata"]=cnt.rename_axis("map stratum (rows) / reference stratum (cols)").reset_index()
    for rule in("strict","robust"):
        m=rd(S+f"Change_Accuracy_{per}_effect_{rule}_matrix.csv",index_col=0)
        for c in m.columns: m[c]=num(m[c])
        m=m.reindex(index=["D","S","I"],columns=["D","S","I"])
        t=m.copy(); t["map total"]=m.sum(axis=1)
        t["UA"]=[m.loc[c,c]/m.loc[c].sum() for c in m.index]
        t.loc["ref total"]=list(m.sum(axis=0))+[m.values.sum(),np.nan]
        t.loc["PA"]=[m.loc[c,c]/m[c].sum() for c in m.columns]+[np.nan,np.nan]
        t.insert(0,"rules",rule)
        sheets[f"Saida_{per}_effect_{rule}"]=t.rename_axis("map effect (rows) / ref effect (cols), area proportions").reset_index().round(4)
for per in("1999_2015","2015_2025"):
    sm=rd(O+f"Result_{per}_stratum_matrix.csv"); sm=sm.rename(columns={sm.columns[0]:"map stratum (rows) / reference (cols), counts"})
    me=rd(O+f"Result_{per}_metrics.csv")[["level","cls","n","UA_or_OA","UA_se","PA","PA_se"]].round(3)
    sheets[f"OEB_{per}_strata_counts"]=sm; sheets[f"OEB_{per}_UA_PA"]=me
readme=pd.DataFrame({"S12 - Change accuracy: confusion matrices and user's/producer's accuracy":[
 "Saida 'strata' sheets: confusion matrix of the 10 change strata (map in rows, reference in columns, interpreted points) with stratum weight W, user's accuracy (UA) and area-weighted producer's accuracy (PA).",
 "Saida 'effect' sheets: degradation (D) / stable (S) / improvement (I) label under strict and robust rules, as area proportions of the territory (rows map, columns reference), with UA, PA and totals.",
 "Oum El Bouaghi sheets: stratum confusion matrix (counts) and UA/PA with standard errors for strata and effects (level 'stratum' / 'effect'; OVERALL = overall accuracy).",
 "Strata: D1 range to crop, D2 range to bare/fallow, D3 crop/fallow to bare, D4 forest loss, D5 to built-up, I1 bare to range, I2 bare to crop/fallow, I3 to forest, S1 stable, S2 other change.",
 "Strata with very few interpreted points (e.g. Saida D1 in 2015-2025, n=1) give unstable UA/PA and should not be interpreted alone."]})
with pd.ExcelWriter("Supplementary_S9_Change_Accuracy_Matrices.xlsx") as w:
    readme.to_excel(w,sheet_name="README",index=False)
    for k,v in sheets.items(): v.to_excel(w,sheet_name=k[:31],index=False)
    for ws in w.book.worksheets(): ws.set_column(0,0,55)
print(sheets["Saida_2015_2025_strata"].to_string()); print(sheets["Saida_2015_2025_effect_robust"].to_string()); print(sheets["OEB_1999_2015_UA_PA"].tail(6).to_string())
