import csv, itertools, numpy as np
f="/mnt/user-data/uploads/Desktop/résultat Saida/10_Designs_Integration/Master_Final_Indicator_All_Designs.csv"
rows=list(csv.DictReader(open(f,encoding='utf-8-sig'),delimiter=';'))
print(len(rows), rows[0].keys())
def num(x): return float(str(x).replace(',','.'))
data=[]
for r in rows:
    data.append(dict(start=r['start_year'],win=r['rain_window'],state=r['state_window'],mat=r['land_cover_matrix'],prod=r['productivity'],soc=r['soc'],y=num(r['proportion_degraded_pct'])))
factors=['start','win','state','mat','prod','soc']
y=np.array([d['y'] for d in data]); gm=y.mean(); sst=((y-gm)**2).sum()
def main_ss(sub,fs):
    ys=np.array([d['y'] for d in sub]); gm=ys.mean(); tot=((ys-gm)**2).sum(); out={}
    for fct in fs:
        lv={}
        for d in sub: lv.setdefault(d[fct],[]).append(d['y'])
        out[fct]=(sum(len(v)*(np.mean(v)-gm)**2 for v in lv.values()), {k:round(float(np.mean(v)),2) for k,v in lv.items()})
    return tot,out
for name,sub in (("ALL 96",data),("corrigee only",[d for d in data if d['prod']=='corrigée']),("corrigee, Sep-Jun only",[d for d in data if d['prod']=='corrigée' and d['win']=='09-06'])):
    fs=[f for f in factors if len({d[f] for d in sub})>1]
    tot,out=main_ss(sub,fs)
    print("\n==",name,len(sub),"cells; total SS %.1f"%tot)
    tsum=0
    for k,(ss,lv) in out.items():
        tsum+=ss; print("  %-6s share %5.1f%%  means %s"%(k,100*ss/tot,lv))
    print("  interactions/residual %.1f%%"%(100*(tot-tsum)/tot))
