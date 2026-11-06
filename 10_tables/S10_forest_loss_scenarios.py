"""S7 (Saida forest-loss scenarios): recomputes the main Saida design after weighting the mapped 2015-2025 forest loss by the share confirmed in the image sample.
Usage: python S10_forest_loss_scenarios.py <unzipped Zenodo folder>  (needs numpy, tifffile)."""
import os, sys
DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")   # unzipped Zenodo deposit
import tifffile, numpy as np, math, json
M=os.path.join(DATA,"05_Integration_1OAO","Saida","D01_start2000_rain0906_state3y")+os.sep
LC=os.path.join(DATA,"01_LandCover","Saida")+os.sep
S=M+"2_Monitoring_2015_2025"+os.sep+"01_SubIndicators"+os.sep
rd=tifffile.imread
NA=127
lc={k:rd(S+"LC_Class_2015_2025_%s.tif"%k) for k in("strict","robust","persistent")}
prod={"adj":rd(S+"Productivity_RainAdjusted_on_LULC_grid.tif"),"unadj":rd(S+"Productivity_Unadjusted_on_LULC_grid.tif")}
soc=rd(S+"SOC_Class_on_LULC_grid.tif")
base=rd(M+"1_Baseline_1999_2015/02_Indicator/SDG1531_BaselineStatus_for_next_run_1999_2015.tif")
l15=rd(LC+"LULC_Saida_2015.tif"); l25=rd(LC+"LULC_Saida_2025.tif")
land=(l15>0)&(l15!=2)&(l15<=8)&(l25>0)&(l25<=8)&(l25!=2)
PX=0.09
fl=(l15==7)&(l25!=7)&(l25>0)&(l25<=8)
print("forest loss ha",fl.sum()*PX)
total=(l25!=2)&(l25>0)  # land
def final(lcl,pr,so):
    avail=(lcl!=NA).astype(int)+(pr!=NA)+(so!=NA)
    deg=(lcl==-1)|(pr==-1)|(so==-1); imp=((lcl==1)|(pr==1)|(so==1))
    st=np.full(lcl.shape,NA,np.int16); st[avail>0]=0; st[imp]=1; st[deg]=-1
    av=(st!=NA)&np.isin(base,(0,1)); b=base==1
    c1=av&b&((st==-1)|(st==0)); c2=av&~b&(st==-1)
    return c1|c2
def share(d,mask): return 100*(d&mask).sum()/mask.sum()
# denominateur : terre (eau exclue) selon rapport 676,276 ha
den=total
print("den ha",den.sum()*PX)
n,k=30,20
p=k/n; z=1.96
wl=(p+z*z/(2*n)-z*math.sqrt(p*(1-p)/n+z*z/(4*n*n)))/(1+z*z/n)
wu=(p+z*z/(2*n)+z*math.sqrt(p*(1-p)/n+z*z/(4*n*n)))/(1+z*z/n)
out=[]
for rule in("strict","robust","persistent"):
  for pk in("adj","unadj"):
    lA=lc[rule]; lB=lA.copy(); lB[fl&(lB!=NA)]=0
    dA=final(lA,prod[pk],soc); dB=final(lB,prod[pk],soc)
    sA,sB=share(dA,den),share(dB,den)
    row=dict(rule=rule,prod=pk,all_pct=sA,excl_pct=sB,diff_pts=sA-sB,fl_only_ha=(dA&~dB).sum()*PX,
             fl_in_deg_ha=(dA&fl).sum()*PX,
             corr_pct=sB+p*(sA-sB),corr_lo=sB+wl*(sA-sB),corr_hi=sB+wu*(sA-sB))
    out.append(row); print({a:(round(b,2) if isinstance(b,float) else b) for a,b in row.items()})
print("p",p,"wilson",wl,wu)
json.dump(out,open("/tmp/o/fl/res.json","w"))
