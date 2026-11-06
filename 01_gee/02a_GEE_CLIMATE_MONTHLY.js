/**
 * 05_GEE_CLIMATE_MONTHLY.js — température et ETP MENSUELLES moyennes sur la zone d'étude (pour l'outil 05_CLIMATE_BLOCK_14_18.py)
 *
 * Produit un CSV  Climate_Monthly.csv  : Year, Month, Tmax_C, Tmin_C, Tmean_C, PET_mm
 * Source par défaut : TerraClimate (IDAHO_EPSCOR/TERRACLIMATE, ~4 km, mensuel) : tmmx, tmmn (°C x 0.1), pet (mm x 0.1).
 * Alternative commentée : ERA5-Land mensuel (ECMWF/ERA5_LAND/MONTHLY_AGGR, ~9 km).
 *
 * À VÉRIFIER dans la console de GEE : les identifiants de collections, les noms de bandes et les facteurs d'échelle peuvent changer ; la dernière année disponible s'imprime ci-dessous
 * (TerraClimate n'est pas toujours à jour jusqu'à l'année en cours : les mois absents donnent des années incomplètes, que l'outil ignore).
 * L'ETP de TerraClimate et celle d'ERA5-Land diffèrent (parfois de plusieurs dizaines de %) : citer la source et, si possible, comparer à des stations.
 *
 * UTILISATION : coller dans l'éditeur de code de Google Earth Engine, mettre le chemin de l'asset de la zone d'étude, exécuter, lancer la tâche « Climate_Monthly » dans l'onglet Tasks.
 */
var STUDY_AREA_ASSET = 'users/VOTRE_COMPTE/Study_Area_Final';      // <-- à remplacer
var START_YEAR = 1990;
var END_YEAR = 2025;
var SOURCE = 'TERRACLIMATE';                                         // 'TERRACLIMATE' ou 'ERA5LAND'

var area = ee.FeatureCollection(STUDY_AREA_ASSET).geometry();
var start = ee.Date.fromYMD(START_YEAR, 1, 1), end = ee.Date.fromYMD(END_YEAR + 1, 1, 1);
var scale = SOURCE === 'TERRACLIMATE' ? 4638.3 : 11132;

var col, feat;
if (SOURCE === 'TERRACLIMATE') {
  col = ee.ImageCollection('IDAHO_EPSCOR/TERRACLIMATE').filterDate(start, end);
  feat = function (img) {
    var tmax = img.select('tmmx').multiply(0.1), tmin = img.select('tmmn').multiply(0.1), pet = img.select('pet').multiply(0.1);
    var v = tmax.rename('Tmax_C').addBands(tmin.rename('Tmin_C')).addBands(tmax.add(tmin).divide(2).rename('Tmean_C')).addBands(pet.rename('PET_mm'))
      .reduceRegion({reducer: ee.Reducer.mean(), geometry: area, scale: scale, maxPixels: 1e10, bestEffort: true});
    var d = ee.Date(img.get('system:time_start'));
    return ee.Feature(null, v).set({Year: d.get('year'), Month: d.get('month')});
  };
} else {
  // ERA5-Land : températures en kelvin, évaporation potentielle cumulée en mètres (valeur négative = convention ECMWF)
  col = ee.ImageCollection('ECMWF/ERA5_LAND/MONTHLY_AGGR').filterDate(start, end);
  feat = function (img) {
    var tmax = img.select('temperature_2m_max').subtract(273.15), tmin = img.select('temperature_2m_min').subtract(273.15), tm = img.select('temperature_2m').subtract(273.15);
    var pet = img.select('potential_evaporation_sum').multiply(-1000);
    var v = tmax.rename('Tmax_C').addBands(tmin.rename('Tmin_C')).addBands(tm.rename('Tmean_C')).addBands(pet.rename('PET_mm'))
      .reduceRegion({reducer: ee.Reducer.mean(), geometry: area, scale: scale, maxPixels: 1e10, bestEffort: true});
    var d = ee.Date(img.get('system:time_start'));
    return ee.Feature(null, v).set({Year: d.get('year'), Month: d.get('month')});
  };
}
var table = ee.FeatureCollection(col.map(feat));
print('Mois exportés :', table.size());
print('Dernier mois disponible :', ee.Date(col.sort('system:time_start', false).first().get('system:time_start')).format('YYYY-MM'));
print(table.limit(5));
Export.table.toDrive({collection: table, description: 'Climate_Monthly', fileNamePrefix: 'Climate_Monthly', fileFormat: 'CSV', selectors: ['Year', 'Month', 'Tmax_C', 'Tmin_C', 'Tmean_C', 'PET_mm']});
