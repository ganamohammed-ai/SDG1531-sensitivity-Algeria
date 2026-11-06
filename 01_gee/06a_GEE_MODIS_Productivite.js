// SDG 15.3.1 REFERENCE PIPELINE — STAGE 01 / 07 : MODIS annual productivity export (Google Earth Engine)
/* ============================================================================
   PRODUCTIVITÉ ANNUELLE MODIS TERRA (MOD13Q1 v061, 250 m)   2000-2025
   Oum El Bouaghi | Google Earth Engine (Code Editor)   |   TRÈS LÉGER

   POURQUOI MODIS
   La série Landsat 1985-2025 mélange cinq capteurs (L5, L7, L8, L9) dont le NDVI diffère
   systématiquement sur votre zone (L7 - L5 ~ +0,03 à +0,04 ; L8 - L7 ~ +0,02 à +0,03 ; mesure
   directe) : une dérive d'environ +0,05 NDVI (~ +25 %) qui masque tout signal de dégradation.
   MODIS Terra MOD13Q1 Collection 6.1 fournit un produit d'indice de végétation à capteur unique,
   temporellement cohérent, avec une calibration et un traitement améliorés par rapport aux
   collections précédentes (cela ne signifie pas que toute dérive possible est nulle : la
   robustesse est testée par les scénarios A / B / C dans QGIS). C'est la base usuelle des
   analyses de productivité UNCCD.

   PRODUIT : MODIS/061/MOD13Q1  (NDVI, composites de 16 jours, 250 m, échelle 0,0001)

   MÉTHODE (par année N)
     - composites dont le milieu tombe entre le 1er mars et le 30 juin (~ 8 composites) ;
     - pixel-composite retenu si SummaryQA <= QA_MAX (0 = bon, 1 = marginal ; 2 neige, 3 nuage rejetés) ;
     - productivité = MOYENNE du NDVI des composites retenus (pas de somme : la valeur ne dépend
       pas du NOMBRE de composites) ;
     - l'année est rejetée (NoData) si moins de MIN_VALID_COMPOSITES composites sont retenus.

   EXPORTS (onglet Tasks -> Run) :
     01_Annual_Productivity_MODIS_2000_2025<suffixe>    bandes productivity_AAAA (NoData = -9999)
     01b_Annual_ValidPeriods_MODIS_2000_2025<suffixe>   nombre de composites retenus par pixel et par année

   SCÉNARIOS DE SENSIBILITÉ (test de robustesse du QA)
     B (principal)  : QA_MAX = 1, EXPORT_SUFFIX = ''        (valeurs actuelles ; déjà exporté)
     A              : QA_MAX = 0, EXPORT_SUFFIX = '_QA0'    (bonnes données seulement) -> relancer et exporter
     C (>= 6 composites) n'a pas besoin d'export : il est dérivé dans QGIS à partir de 01b.
   Mettre les exports du scénario A dans un AUTRE dossier Drive (ou garder le suffixe _QA0 dans le nom).

   Nombre de composites : le milieu de chaque composite de 16 jours doit tomber entre le 1er mars et
   le 30 juin, soit 7 composites au maximum selon l'année (n_valid maximal observé = 7).

   Ensuite, dans QGIS : MODIS_LPD_COMPLETE_QGIS.py (qualité, scénarios, Trajectory, State, Performance, LPD, statistiques).
   ============================================================================ */

// ===================== CONFIGURATION (à adapter pour une autre zone d'étude) =====================
var AREA_TAG = 'Oum_El_Bouaghi';
var STUDY_AREA_ASSET = 'projects/my-project-6188225/assets/Study_Area_Final';   // limite de la zone d'étude téléversée comme asset GEE
// Saison de végétation (voir plus bas SEASON_START_MONTH / SEASON_END_MONTH) et fuseau UTM (EXPORT_CRS) : à régler pour la zone.
// =================================================================================================
var aoi = ee.FeatureCollection(STUDY_AREA_ASSET);
var AOI_GEOM = aoi.geometry();

var START_YEAR = 2000;               // Terra : composites disponibles depuis le 18 février 2000
var END_YEAR = 2025;

var SEASON_START_MONTH = 3;          // 1 mars
var SEASON_END_MONTH = 7;            // jusqu'au 1er juillet (exclu)
var QA_MAX = 1;                      // SummaryQA retenu : 0 = bon, 1 = marginal (scénario A : 0)
var MIN_VALID_COMPOSITES = 5;        // sur ~ 8 composites de la saison

var EXPORT_SUFFIX = '';             // '' pour le scénario B ; '_QA0' pour le scénario A (QA_MAX = 0)
var EXPORT_FOLDER = 'UNCCD_' + AREA_TAG + '_MODIS' + EXPORT_SUFFIX;
var EXPORT_CRS = 'EPSG:32632';
var EXPORT_SCALE = 250;
var PRINT_COVERAGE = true;           // imprime la part de la zone valide pour chaque année (26 petites requêtes)

var modis = ee.ImageCollection('MODIS/061/MOD13Q1');


/* ============================================================================
   1. PRODUCTIVITÉ ANNUELLE
   ============================================================================ */

function annualImage(year) {
  year = ee.Number(year);

  // composites dont le MILIEU (début + 8 jours) tombe dans [1 mars, 1 juillet[
  var start = ee.Date.fromYMD(year, SEASON_START_MONTH, 1).advance(-8, 'day');
  var end = ee.Date.fromYMD(year, SEASON_END_MONTH, 1).advance(-8, 'day');

  var good = modis
    .filterDate(start, end)
    .map(function (img) {
      var ok = img.select('SummaryQA').lte(QA_MAX);
      var ndvi = img.select('NDVI').multiply(0.0001).updateMask(ok);
      return ndvi.rename('ndvi');
    });

  var count = good.count().rename('n_valid');
  var mean = good.mean().rename('productivity');
  var keep = count.gte(MIN_VALID_COMPOSITES);

  return mean.updateMask(keep)
    .addBands(count)
    .set('year', year)
    .set('system:time_start', ee.Date.fromYMD(year, 1, 1).millis());
}

var years = ee.List.sequence(START_YEAR, END_YEAR);
var annual = ee.ImageCollection(years.map(annualImage));

var productivityStack = annual
  .map(function (img) {
    var y = ee.Number(img.get('year')).format('%d');
    return img.select('productivity').rename(ee.String('productivity_').cat(y)).toFloat();
  })
  .toBands()
  .toFloat();

var validStack = annual
  .map(function (img) {
    var y = ee.Number(img.get('year')).format('%d');
    return img.select('n_valid').rename(ee.String('nvalid_').cat(y)).toFloat();
  })
  .toBands()
  .toFloat();


/* ============================================================================
   2. EXPORTS (NoData déclaré = -9999)
   ============================================================================ */

function exportStack(image, description) {
  Export.image.toDrive({
    // découpage au contour de la zone d'étude : sans clip, l'export contient tout le RECTANGLE englobant
    image: image.clip(AOI_GEOM).unmask({value: -9999, sameFootprint: false}),
    description: description,
    folder: EXPORT_FOLDER,
    region: AOI_GEOM,
    scale: EXPORT_SCALE,
    crs: EXPORT_CRS,
    maxPixels: 1e10,
    fileFormat: 'GeoTIFF',
    formatOptions: {noData: -9999}
  });
  print('Export cree : ' + description);
}

exportStack(productivityStack, '01_Annual_Productivity_MODIS_' + START_YEAR + '_' + END_YEAR + EXPORT_SUFFIX);
exportStack(validStack, '01b_Annual_ValidPeriods_MODIS_' + START_YEAR + '_' + END_YEAR + EXPORT_SUFFIX);


/* ============================================================================
   3. COUVERTURE VALIDE PAR ANNÉE (contrôle, requêtes séquentielles légères)
   ============================================================================ */

var coverage = [];

function checkYear(i) {
  var y = START_YEAR + i;
  if (y > END_YEAR) {
    var lines = ['year,valid_percent,mean_valid_composites'];
    coverage.forEach(function (r) {
      lines.push([r.year, r.valid.toFixed(1), r.mean.toFixed(2)].join(','));
    });
    print('COUVERTURE (part de la zone avec une productivite valide, et nombre moyen de composites) :');
    print(lines.join('\n'));
    var weak = coverage.filter(function (r) { return r.valid < 90; }).map(function (r) { return r.year; });
    print('Annees avec moins de 90 % de la zone valide : ' + (weak.length ? weak.join(', ') : 'aucune'));
    return;
  }
  var img = annualImage(y);
  var valid = img.select('productivity').mask().rename('valid').toFloat();
  valid.addBands(img.select('n_valid')).reduceRegion({
    reducer: ee.Reducer.mean(),
    geometry: AOI_GEOM,
    scale: EXPORT_SCALE,
    crs: EXPORT_CRS,
    maxPixels: 1e10,
    tileScale: 2
  }).evaluate(function (res, err) {
    if (err || !res) {
      print('ERREUR couverture ' + y + ' : ' + err);
      coverage.push({year: y, valid: NaN, mean: NaN});
    } else {
      coverage.push({year: y, valid: 100 * res.valid, mean: res.n_valid});
    }
    checkYear(i + 1);
  });
}

if (PRINT_COVERAGE) {
  checkYear(0);
}
