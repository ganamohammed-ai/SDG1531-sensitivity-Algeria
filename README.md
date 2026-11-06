# SDG 15.3.1 sensitivity analysis — Oum El Bouaghi and Saïda (Algeria)

Code for the article:

> {{Authors}} ({{Year}}). How much does the analyst decide? Sensitivity of the SDG 15.3.1 land degradation
> indicator to rainfall adjustment and design choices in two semi-arid Algerian provinces.
> *Arid Land Research and Management*, {{volume, pages, DOI}}.

Data (processed layers and result tables): Zenodo, https://doi.org/10.5281/zenodo.{{XXXXXXX}}
Archived version of this code: https://doi.org/10.5281/zenodo.{{YYYYYYY}}

The workflow computes the three SDG 15.3.1 sub-indicators (land cover, land productivity, soil organic carbon),
integrates them with the one-out-all-out rule and repeats the computation for 96 scenarios per province
(8 designs × 3 land-cover rule sets × rainfall-adjusted / unadjusted productivity × with / without soil carbon).

## Software

| Part | Environment |
|---|---|
| Data download | Google Earth Engine (JavaScript Code Editor) |
| Processing (folders 02–09) | QGIS 3.44 with its bundled Python 3.12, GDAL 3.13 and NumPy 1.26; scripts are run in the QGIS Python editor |
| Tables (folder 10) | Python 3 with the packages in `requirements.txt` |

Comments and report texts inside the processing scripts are mostly in French.

## Repository structure

| Folder | Content | Article section |
|---|---|---|
| `01_gee` | Download of Landsat, MODIS, CHIRPS, ERA5-Land, TerraClimate and auxiliary layers; monthly climate; MODIS productivity series | 2.2 |
| `02_land_cover` | Random-forest classification, review of improbable transitions, transition matrices, validation sample, area-adjusted accuracy (Olofsson et al. 2014) | 2.3 |
| `03_change_accuracy` | Stratified change sample and change accuracy recoded to strict / robust rules (`oeb`, `saida`) | 2.3–2.4, 3.1 |
| `04_rainfall_productivity` | Annual productivity index, extraction of the regional rainfall series, stack quality checks | 2.2, 2.5 |
| `05_lpd` | Land productivity dynamics (trajectory, state, performance; RESTREND rainfall adjustment); start-year sensitivity; launcher of all LPD runs | 2.5 |
| `06_soc` | Soil organic carbon sub-indicator (IPCC factors, 20-year relaxation, Monte Carlo) | 2.6 |
| `07_integration_1oao` | One-out-all-out integration; launcher of all designs; base-year sensitivity; combined report | 2.4, 2.7 |
| `08_all_designs` | Final runs of the 8 designs × 12 scenarios with the CHIRPS monthly series (`OEB_…`, `Saida_…`); Saïda settings of the core scripts and rainfall-product runs (`saida_settings`) | 2.7–2.8, 3.3–3.5 |
| `09_checks` | Saïda block, functional and Pettitt tests; factorial audit; blind reading of the Oum El Bouaghi main-design map (reading pages and analysis) | 2.9, 3.6 |
| `10_tables` | Variance decomposition (Supplementary S1, S3), forest-loss scenarios (S7), change-accuracy matrices (S9) | 2.8, 3.1, 3.4, 3.6 |
| `config` | Land-cover transition matrices, SOC factor tables, daily-equivalent CHIRPS series built from monthly totals | 2.2, 2.4–2.6 |
| `docs` | Run order and input formats | — |

## Reproducing the tables from the Zenodo data

```bash
pip install -r requirements.txt
# unzip the Zenodo deposit into ./data  (so that ./data/00_Tables, ./data/05_Integration_1OAO ... exist)
python 10_tables/Variance_Decomposition.py data/00_Tables      # Supplementary S1 and S3
python 10_tables/S10_forest_loss_scenarios.py data             # Supplementary S7
python 10_tables/S12_build_change_accuracy_matrices.py data    # Supplementary S9
```

`Variance_Decomposition.py` reproduces Supplementary S1 exactly, for example a rainfall-adjustment main effect
of 77.0% (Oum El Bouaghi) and 41.0% (Saïda) and a rainfall-window share including interactions of 1.0% and 57.5%.

## Re-running the processing chain

See `docs/RUN_ORDER.md`. Each processing script starts with a settings block (`REGLAGES` / paths) that must be
edited to point to local folders before running it in the QGIS Python editor. Inputs are the layers downloaded
with the scripts in `01_gee` and the processed layers of the Zenodo deposit.

## Licence

MIT (see `LICENSE`). Please cite the article and the archived code (see `CITATION.cff`).
