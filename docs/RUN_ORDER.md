# Run order

Run each script in the QGIS Python editor (Plugins → Python Console → Show Editor → open or paste → Run),
after editing its settings block. Oum El Bouaghi (OEB) and Saïda use the same core scripts; the Saïda copies in
`08_all_designs/saida_settings` differ only by the area tag (`AREA_TAG = "Saida"`), the area name and the
rainfall window.

| Step | Script | Output |
|---|---|---|
| 1 | `01_gee/01a_GEE_01_Download_All_Data.js`, `02a_GEE_CLIMATE_MONTHLY.js`, `06a_GEE_MODIS_Productivite.js` (Earth Engine) | Landsat composites, climate grids, annual MODIS productivity and valid-period rasters |
| 2 | `02_land_cover/03a` → `03b` (optional) → `03c` → `03d` → `03e` | Land-cover maps 1999–2025, transition matrices, validation sample, area-adjusted accuracy |
| 3 | `03_change_accuracy/<province>/04a` → interpretation of the sample → `04b` | Change accuracy by stratum and under strict / robust rules |
| 4 | `04_rainfall_productivity/QGIS_Extract_*` and `06b` | Regional rainfall series, annual productivity index |
| 5 | `05_lpd/06d` | Start-year and rainfall-window sensitivity |
| 6 | `06_soc/07a` | SOC classes 1999–2015 and 2015–2025 (main parameterisation and alternatives) |
| 7 | `08_all_designs/OEB_CHIRPS_Monthly_AllDesigns.py` and `Saida_CHIRPS_Monthly_AllDesigns.py` | LPD for 12 runs and 1OAO integration for 8 designs × 12 scenarios; master table of 96 scenarios. These launchers call `05_lpd/06e` and `07_integration_1oao/08a` (OEB) or their Saïda settings copies |
| 8 | `08_all_designs/saida_settings/06f_DIRECT_RAINPRODUCTS_SAIDA.py`, `08a_DIRECT_RAINPRODUCTS_SAIDA.py`; for OEB set `PRODUCTS` in `OEB_CHIRPS_Monthly_AllDesigns.py` | Runs with ERA5-Land and TerraClimate |
| 9 | `09_checks/*` | Block, functional and Pettitt tests (Saïda); blind reading of the OEB main-design map |
| 10 | `10_tables/*` | Supplementary tables S1, S3, S7, S9 |

## Input formats

- Daily rainfall CSV (`config/CHIRPS_FromMonthly_Daily_*.csv`): header `date;chirps_mm`, one row per day; each
  monthly CHIRPS total (regional mean) is spread evenly over the days of the month. Used for the rainfall
  adjustment of productivity.
- Transition matrices (`config/*Transition_Matrix*.csv`): degradation / stable / improvement label (`effect_strict`, `effect_robust`)
  for each pair of land-cover classes, with the rationale and source of each rule (1 built-up, 2 water, 3 sebkha, 4 bare land, 5 cropland, 6 fallow, 7 forest, 8 rangeland).
- SOC factor tables (`config/SOC_Factors_*.csv`): stock-change factor and its range for each class (IPCC 2019, warm temperate dry).
