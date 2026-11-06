# -*- coding: utf-8 -*-
# 5.4 Test fonctionnel NDVI : les pixels "degrades" de chaque produit pluie sont-ils vraiment moins verts ?
# Usage: python Phase5_Functional_NDVI_Test.py <DATA Saida> <resultat Saida> <sortie.csv>
import sys, os, numpy as np
from PIL import Image
D, R, OUT = sys.argv[1:4]
st = np.array(Image.open(os.path.join(D,'04_MODIS_2000_2025','01_Annual_Productivity_MODIS_2000_2025_Saida.tif'))) if False else None
import tifffile
st = tifffile.imread(os.path.join(D,'04_MODIS_2000_2025','01_Annual_Productivity_MODIS_2000_2025_Saida.tif')).astype('float64')
st[st<=-9990] = np.nan            # (H,W,26) annees 2000..2025
yrs = np.arange(2000,2026)
def rd(p): return np.array(Image.open(p)).astype(int)
paths = {'CHIRPS':os.path.join(R,'09_Designs_LPD'),'TerraClimate':os.path.join(R,'14_RainProducts','TerraClimate'),'ERA5':os.path.join(R,'14_RainProducts','ERA5')}
sub = {'baseline':'LPD_2000_baseline_0906_s2012_r2013-2015','monitoring':'LPD_2000_monitoring_0906'}
f = os.path.join('03_LPD','LPD_3class_B_QA1_min5_RainAdjusted.tif')
def metric(per):
    if per=='baseline':
        i = (yrs>=2000)&(yrs<=2015); x = yrs[i]-yrs[i].mean(); y = st[:,:,i]
        m = np.nanmean(y,axis=2); ok = np.isfinite(y).sum(2)>=12
        yc = np.where(np.isfinite(y), y-m[:,:,None], 0)
        s = (yc*x).sum(2)/((x**2)[None,None,:]*np.isfinite(y)).sum(2)
        return np.where(ok&(m>0), s/m*100, np.nan)   # %/an
    a = np.nanmean(st[:,:,(yrs>=2021)],axis=2); b = np.nanmean(st[:,:,yrs<=2012],axis=2)
    return np.where(b>0,(a-b)/b*100,np.nan)           # % changement
rows=[]; masks={}
for per in sub:
    met = metric(per)
    for p,base in paths.items():
        c = rd(os.path.join(base,sub[per],f)); valid=(c!=-9999)&np.isfinite(met)
        masks[(per,p)] = (c==-1)&valid
        n=valid.sum()
        for k,nm in [(-1,'degrade'),(0,'stable'),(1,'ameliore')]:
            v=met[valid&(c==k)]
            rows.append([per,p,nm,int((valid&(c==k)).sum()),round(100*(valid&(c==k)).sum()/n,2),round(float(np.mean(v)),3) if len(v) else '',round(float(np.median(v)),3) if len(v) else ''])
with open(OUT,'w',encoding='utf-8-sig') as fo:
    fo.write('periode;produit_pluie;classe;pixels;part_%;mean_metrique;median_metrique\n')
    for r in rows: fo.write(';'.join(str(x).replace('.',',') for x in r)+'\n')
    fo.write('\nmetrique: baseline=pente NDVI-productivite 2000-2015 en %/an ; monitoring=(moy2021-25 - moy2000-12)/moy2000-12 en %\n')
    fo.write('\nrecouvrement des masques degrade (Jaccard)\nperiode;A;B;Jaccard;pixels_communs\n')
    for per in sub:
        ps=list(paths)
        for i in range(3):
            for j in range(i+1,3):
                a,b=masks[(per,ps[i])],masks[(per,ps[j])]
                fo.write(f'{per};{ps[i]};{ps[j]};{(a&b).sum()/max((a|b).sum(),1):.3f};{(a&b).sum()}\n'.replace('.',','))
print(open(OUT,encoding='utf-8-sig').read())
