/**
 * GEE_01_Download_All_Data.js — ALL the Earth Engine layers needed to complete the study (stages 14–36 of the plan)
 * Oum El Bouaghi | Google Earth Engine Code Editor | exports GeoTIFF to Google Drive (folder SDG1531_GEE_Data)
 *
 * HOW TO USE
 *   1. Paste in the Code Editor, check STUDY_AREA_ASSET (taken from your Assets panel), choose what to export in RUN.
 *   2. Run. The console prints the number of tasks and a few quality checks (dates available, image counts).
 *   3. Tasks tab -> RUN every task (about 20). Download the folder from Google Drive.
 *
 * WHAT IT EXPORTS (name -> plan stage)
 *   Terrain_SRTM_30m                         elevation, slope, aspect, TPI 500 m            (19, 20)
 *   SoilGrids_0_30cm_250m                    sand, silt, clay, bulk density, SOC, pH, OCS    (22, 12)
 *   Fire_MCD64A1_Burned_By_Year_2001_2025_500m  burned (0/1) for every year                (28, 32, 35)
 *   Fire_MCD64A1_Summary_500m                number of burned years, first and last burn year (28, 32, 35)
 *   CHIRPS_WetSeason_SepJun_1986_2025_5km    wet-season rain per year                       (14, 17)
 *   CHIRPS_Annual_1985_2025_5km              annual rain per year                           (14, 18)
 *   TerraClimate_Tmean / PET / Pr / AI       annual stacks 1990–2024                        (15, 16, 18)
 *   Trend_*                                  Sen slope, Kendall tau and p per pixel (rain, temperature, PET)  (14, 15, 16, 33)
 *   WorldPop_2000_2020_100m                  population 2000, 2005, 2010, 2015, 2020 + change (26)
 *   GHSL_BuiltUp_2000_2020_100m              built-up surface per epoch                       (25)
 *   Erosivity_FournierIndex_mean_5km         relative rain-erosivity index (input of an OPTIONAL relative erosion risk) (21)
 *   Salinity_S2_2019_2025_30m (RUN.salinity) salinity indices, dry-season median (OFF by default) (29)
 *
 * NOT AVAILABLE HERE (download elsewhere): OSM roads (Geofabrik, plan 27), livestock statistics (DSA / FAO, plan 24),
 *   local fire records (forest service), census (ONS), field salinity (EC).
 *
 * CHECK IN THE CONSOLE: catalogue ids, band names and scale factors can change; TerraClimate is not always complete for the last year;
 *   MCD64A1 (500 m) maps only large burns (about 20 ha and more): it does NOT prove the absence of a small fire.
 */
var STUDY_AREA_ASSET = 'projects/ee-gana2014med/assets/Study_Area_Final';
var DRIVE_FOLDER = 'SDG1531_GEE_Data';
var CRS = 'EPSG:32632';                       // UTM 32N (Oum El Bouaghi, about 7 degrees E)
var RUN = {
  terrain: true, soil: true, fire: true,
  rain_chirps: true, terraclimate: true, climate_trends: true,
  population: true, builtup: true, erosivity_index: true,
  salinity: false
};
var CHIRPS_FIRST = 1986, CHIRPS_LAST = 2025;  // wet season Sep(N-1)–Jun(N)
var TC_FIRST = 1990, TC_LAST = 2024;          // TerraClimate: check the last complete year with the console output
var FIRE_FIRST = 2001, FIRE_LAST = 2025;
var EPOCHS = [2000, 2005, 2010, 2015, 2020];

var area = ee.FeatureCollection(STUDY_AREA_ASSET);
var geom = area.geometry();
var region = geom.bounds();
var tasks = [];

function clipImg(img) { return img.clip(geom); }
function exp(img, name, scale) {
  Export.image.toDrive({ image: img.toFloat(), description: name, folder: DRIVE_FOLDER, fileNamePrefix: name, region: region, scale: scale, crs: CRS, maxPixels: 1e10, fileFormat: 'GeoTIFF' });
  tasks.push(name + '  (' + scale + ' m)');
}
function trendMap(imgs, years) {
  var col = ee.ImageCollection.fromImages(imgs.map(function (im, i) {
    return ee.Image.constant(years[i]).float().rename('year').addBands(im.rename('v')).toFloat();
  }));
  var xy = col.select(['year', 'v']);
  var sen = xy.reduce(ee.Reducer.sensSlope());
  var kt = xy.reduce(ee.Reducer.kendallsCorrelation());
  return sen.select('slope').rename('sen_slope_per_year').addBands(kt.select('tau').rename('mk_tau')).addBands(kt.select('p-value').rename('mk_p'));
}
function sliceFrom(arr, years, y0) { var i = years.indexOf(y0); return { imgs: arr.slice(i), years: years.slice(i) }; }

print('Study area (features):', area.size());

// ---------------------------------------------------------------- 19, 20 terrain
if (RUN.terrain) {
  var srtm = ee.Image('USGS/SRTMGL1_003').select('elevation');
  var slope = ee.Terrain.slope(srtm).rename('slope_deg');
  var aspect = ee.Terrain.aspect(srtm).rename('aspect_deg');
  var tpi = srtm.subtract(srtm.focalMean(500, 'circle', 'meters')).rename('tpi_500m');
  exp(clipImg(srtm.rename('elevation_m').addBands(slope).addBands(aspect).addBands(tpi)), 'Terrain_SRTM_30m', 30);
}

// ---------------------------------------------------------------- 22, 12 soil (SoilGrids 2.0, weighted mean of 0–30 cm)
if (RUN.soil) {
  var SOIL_PROPS = ['sand', 'silt', 'clay', 'bdod', 'soc', 'phh2o'];   // g/kg, g/kg, g/kg, cg/cm3, dg/kg, pH x 10
  var soil030 = function (p) {
    var img = ee.Image('projects/soilgrids-isric/' + p + '_mean');
    var b1 = img.select(p + '_0-5cm_mean'), b2 = img.select(p + '_5-15cm_mean'), b3 = img.select(p + '_15-30cm_mean');
    return b1.multiply(5).add(b2.multiply(10)).add(b3.multiply(15)).divide(30).rename(p + '_0_30cm');
  };
  var soil = ee.Image.cat(SOIL_PROPS.map(soil030));
  soil = soil.addBands(ee.Image('projects/soilgrids-isric/ocs_mean').select('ocs_0-30cm_mean').rename('ocs_0_30cm_tha'));
  exp(clipImg(soil), 'SoilGrids_0_30cm_250m', 250);
}

// ---------------------------------------------------------------- 28 fires (MODIS MCD64A1 burned area, 500 m)
if (RUN.fire) {
  var ba = ee.ImageCollection('MODIS/061/MCD64A1');
  var burnedList = [], yearImgs = [];
  for (var fy = FIRE_FIRST; fy <= FIRE_LAST; fy++) {
    var by = ba.filterDate(fy + '-01-01', (fy + 1) + '-01-01').select('BurnDate').max().gt(0).unmask(0).rename('burned_' + fy);
    burnedList.push(by);
    yearImgs.push(by.multiply(fy).selfMask().rename('yr'));
  }
  var burned = ee.Image.cat(burnedList);
  var nBurn = burned.reduce(ee.Reducer.sum()).rename('n_burn_years');
  var yrs = ee.ImageCollection.fromImages(yearImgs);
  var lastB = yrs.max().unmask(0).rename('last_burn_year');
  var firstB = yrs.min().unmask(0).rename('first_burn_year');
  exp(clipImg(burned), 'Fire_MCD64A1_Burned_By_Year_' + FIRE_FIRST + '_' + FIRE_LAST + '_500m', 500);
  exp(clipImg(nBurn.addBands(firstB).addBands(lastB)), 'Fire_MCD64A1_Summary_500m', 500);
  print('MCD64A1 images in the period:', ba.filterDate(FIRE_FIRST + '-01-01', (FIRE_LAST + 1) + '-01-01').size());
}

// ---------------------------------------------------------------- 14, 17, 18 rainfall (CHIRPS)
var wetList = [], wetYears = [];
if (RUN.rain_chirps || RUN.climate_trends) {
  var chirps = ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY').select('precipitation');
  var annList = [], annYears = [];
  for (var cy = CHIRPS_FIRST; cy <= CHIRPS_LAST; cy++) {
    wetList.push(chirps.filterDate((cy - 1) + '-09-01', cy + '-07-01').sum().rename('wet_' + cy));
    wetYears.push(cy);
  }
  for (var ay = CHIRPS_FIRST - 1; ay <= CHIRPS_LAST; ay++) {
    annList.push(chirps.filterDate(ay + '-01-01', (ay + 1) + '-01-01').sum().rename('annual_' + ay));
    annYears.push(ay);
  }
  if (RUN.rain_chirps) {
    exp(clipImg(ee.Image.cat(wetList)), 'CHIRPS_WetSeason_SepJun_' + CHIRPS_FIRST + '_' + CHIRPS_LAST + '_5km', 5566);
    exp(clipImg(ee.Image.cat(annList)), 'CHIRPS_Annual_' + (CHIRPS_FIRST - 1) + '_' + CHIRPS_LAST + '_5km', 5566);
  }
}

// ---------------------------------------------------------------- 15, 16, 18 temperature, PET, aridity (TerraClimate)
var tmList = [], peList = [], tcYears = [];
if (RUN.terraclimate || RUN.climate_trends) {
  var tc = ee.ImageCollection('IDAHO_EPSCOR/TERRACLIMATE');
  var prList = [], aiList = [];
  for (var ty = TC_FIRST; ty <= TC_LAST; ty++) {
    var c = tc.filterDate(ty + '-01-01', (ty + 1) + '-01-01');
    var tmean = c.select('tmmx').mean().add(c.select('tmmn').mean()).multiply(0.05).rename('tmean_' + ty);       // (tmmx + tmmn) / 2, scale 0.1
    var pet = c.select('pet').sum().multiply(0.1).rename('pet_' + ty);
    var pr = c.select('pr').sum().rename('pr_' + ty);
    tmList.push(tmean); peList.push(pet); prList.push(pr); aiList.push(pr.divide(pet).rename('ai_' + ty)); tcYears.push(ty);
  }
  if (RUN.terraclimate) {
    exp(clipImg(ee.Image.cat(tmList)), 'TerraClimate_Tmean_' + TC_FIRST + '_' + TC_LAST + '_4km', 4638);
    exp(clipImg(ee.Image.cat(peList)), 'TerraClimate_PET_' + TC_FIRST + '_' + TC_LAST + '_4km', 4638);
    exp(clipImg(ee.Image.cat(prList)), 'TerraClimate_Pr_' + TC_FIRST + '_' + TC_LAST + '_4km', 4638);
    exp(clipImg(ee.Image.cat(aiList)), 'TerraClimate_AI_' + TC_FIRST + '_' + TC_LAST + '_4km', 4638);
  }
  print('TerraClimate: last month available =', ee.Date(tc.sort('system:time_start', false).first().get('system:time_start')).format('YYYY-MM'));
}

// ---------------------------------------------------------------- 14, 15, 16, 33 trends per pixel (Sen slope + Kendall)
if (RUN.climate_trends) {
  var w2000 = sliceFrom(wetList, wetYears, 2000), w2003 = sliceFrom(wetList, wetYears, 2003);
  exp(clipImg(trendMap(w2000.imgs, w2000.years)), 'Trend_WetSeasonRain_2000_2025_5km', 5566);
  exp(clipImg(trendMap(w2003.imgs, w2003.years)), 'Trend_WetSeasonRain_2003_2025_5km', 5566);
  var t2000 = sliceFrom(tmList, tcYears, 2000), p2000 = sliceFrom(peList, tcYears, 2000);
  exp(clipImg(trendMap(t2000.imgs, t2000.years)), 'Trend_Tmean_2000_' + TC_LAST + '_4km', 4638);
  exp(clipImg(trendMap(p2000.imgs, p2000.years)), 'Trend_PET_2000_' + TC_LAST + '_4km', 4638);
}

// ---------------------------------------------------------------- 26 population (WorldPop)
if (RUN.population) {
  var wp = ee.ImageCollection('WorldPop/GP/100m/pop').filter(ee.Filter.eq('country', 'DZA'));
  var popList = EPOCHS.map(function (y) { return wp.filter(ee.Filter.eq('year', y)).mosaic().rename('pop_' + y); });
  var pop = ee.Image.cat(popList);
  pop = pop.addBands(pop.select('pop_2020').subtract(pop.select('pop_2000')).rename('pop_change_2000_2020'));
  exp(clipImg(pop), 'WorldPop_2000_2020_100m', 100);
  print('WorldPop images for Algeria:', wp.size());
}

// ---------------------------------------------------------------- 25 built-up surface (GHSL)
if (RUN.builtup) {
  var gh = ee.ImageCollection('JRC/GHSL/P2023A/GHS_BUILT_S');
  var bList = EPOCHS.map(function (y) { return gh.filter(ee.Filter.calendarRange(y, y, 'year')).first().select('built_surface').rename('built_m2_' + y); });
  exp(clipImg(ee.Image.cat(bList)), 'GHSL_BuiltUp_2000_2020_100m', 100);
  print('GHSL epochs:', gh.aggregate_array('system:time_start').map(function (t) { return ee.Date(t).format('YYYY'); }));
}

// ---------------------------------------------------------------- 21 relative rain erosivity (Fournier index) — optional input of a RELATIVE erosion risk
if (RUN.erosivity_index) {
  var fiList = [];
  for (var ey = 2001; ey <= CHIRPS_LAST; ey++) {
    var monthly = [];
    for (var m = 1; m <= 12; m++) {
      var s = ee.Date.fromYMD(ey, m, 1);
      monthly.push(ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY').select('precipitation').filterDate(s, s.advance(1, 'month')).sum());
    }
    var mcol = ee.ImageCollection.fromImages(monthly);
    var psum = mcol.sum();
    fiList.push(mcol.map(function (im) { return im.pow(2); }).sum().divide(psum).rename('fi'));
  }
  var fi = ee.ImageCollection.fromImages(fiList).mean().rename('fournier_index_mean');
  exp(clipImg(fi), 'Erosivity_FournierIndex_mean_5km', 5566);
}

// ---------------------------------------------------------------- 29 salinity indices (Sentinel-2, dry-season median) — OFF by default
if (RUN.salinity) {
  var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(geom).filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
    .filter(ee.Filter.calendarRange(5, 9, 'month')).filterDate('2019-01-01', '2026-01-01')
    .map(function (im) { return im.divide(10000).copyProperties(im, ['system:time_start']); });
  var med = s2.median();
  var si1 = med.select('B3').multiply(med.select('B4')).sqrt().rename('SI1');
  var ndsi = med.select('B4').subtract(med.select('B8')).divide(med.select('B4').add(med.select('B8'))).rename('NDSI');
  var bsi = med.select('B11').add(med.select('B4')).subtract(med.select('B8').add(med.select('B2'))).divide(med.select('B11').add(med.select('B4')).add(med.select('B8')).add(med.select('B2'))).rename('BSI');
  exp(clipImg(si1.addBands(ndsi).addBands(bsi)), 'Salinity_S2_2019_2025_30m', 30);
}

print('Export tasks created (' + tasks.length + ') — open the Tasks tab and RUN each one:', tasks);
