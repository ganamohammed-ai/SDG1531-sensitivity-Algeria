# Phase 5.3 - block out-of-sample tests of the rain-productivity relation, by rain product and window (Saida)
import csv,numpy as np,sys,os
from scipy import stats
R=sys.argv[1] if len(sys.argv)>1 else r"C:\Users\User25\Desktop\résultat Saida"
prod={int(r['year']):float(r['index_tous']) for r in csv.DictReader(open(os.path.join(R,'03_Productivity','Productivity_Index_By_Year_SAIDA.csv'),encoding='utf-8-sig'))}
rows=list(csv.DictReader(open(os.path.join(R,'02_Rain','Regional_Monthly_Rain_SAIDA_CHIRPSdaily.csv'),encoding='utf-8-sig')))
cols={'CHIRPS':'chirps_mm','TerraClimate':'terraclimate_ppt_mm','ERA5':'era5_mm_daily_mean'}
def ser(col,win):
    d={(int(r['year']),int(r['month'])):float(r[col]) for r in rows if r[col]!=''}
    m0,m1=win; out={}
    for y in range(2000,2026):
        ms=([(y-1,m) for m in range(m0,13)]+[(y,m) for m in range(1,m1+1)]) if m0>m1 else [(y,m) for m in range(m0,m1+1)]
        if all(k in d for k in ms): out[y]=sum(d[k] for k in ms)
    return out
Y=np.array(sorted(prod)); P=np.array([prod[y] for y in Y]); sd=P.std(ddof=1)
out=[["window","product","R2_in_sample","block","skill","bias_pred_minus_obs_in_sd"]]
for win,wn in (((9,6),'Sep-Jun'),((12,4),'Dec-Apr')):
    for name,col in cols.items():
        s=ser(col,win); x=np.array([s[y] for y in Y]); r2=stats.linregress(x,P).rvalue**2
        for bn,te,tr in (("2013-15, train all other years",(Y>=2013)&(Y<=2015),None),("2016-25, train 2000-15",Y>=2016,Y<2016),("2021-25, train 2000-20",Y>=2021,Y<2021)):
            if tr is None: tr=~te
            sl,ic,*_=stats.linregress(x[tr],P[tr]); pr=ic+sl*x[te]; ob=P[te]
            sk=1-np.sqrt(np.mean((pr-ob)**2))/np.sqrt(np.mean((P[tr].mean()-ob)**2))
            out.append([wn,name,round(r2,3),bn,round(sk,3),round(float(np.mean(pr-ob)/sd),3)])
with open(os.path.join(R,'15_Phase5','Rain_Product_BlockTests_SAIDA.csv'),'w',newline='',encoding='utf-8-sig') as f: csv.writer(f,delimiter=';').writerows(out)
print("ok")
