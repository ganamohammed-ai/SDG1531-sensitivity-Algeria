# -*- coding: utf-8 -*-
"""
Decomposition of the variation among scenarios (SDG 15.3.1 sensitivity study).  Two analyses, same method.

A. 96 scenarios of each province (Master_Final_Indicator_All_Designs.csv; 2 x 2 x 2 x 2 x 3 x 2 factors)      -> Supplementary S1
B. Oum El Bouaghi, rain-adjusted scenarios of the three rainfall products (OEB_RainProducts_AllDesigns_long.csv;
   product x rain window x start year x state window x land-cover rules x soil carbon = 3 x 2 x 2 x 2 x 3 x 2 = 144)  -> Supplementary S3
   (input file = Supplementary S2; only rows with productivity == "corrigée" are used, because unadjusted productivity does not depend on the rainfall product)

Method (balanced full factorial, one run per cell):
    y_c  = degraded share (% of land) of scenario c ; ybar = mean of all values ; SS_total = sum_c (y_c - ybar)^2           (1)
    For every non-empty subset S of the factors, with m_S(c) = mean of y over the scenarios sharing the levels of S with c:
        SS_S = sum_c (m_S(c) - ybar)^2 - sum over proper non-empty subsets T of S of SS_T                                  (2)
    (main effect if |S| = 1, interaction of the factors in S otherwise.)  Because the design is balanced and fully crossed the terms
    are orthogonal and  sum_S SS_S = SS_total                                                                               (3)
    Share of a term = 100 * SS_S / SS_total  (descriptive: one run per cell, no error term, no significance test).
Usage : set TABLES to the 00_Tables folder of the Zenodo deposit (default: ../data/00_Tables), run with Python 3 (pandas). Outputs : Variance_Decomposition_Terms.csv (A) and Variance_Decomposition_OEB_Products.csv (B).
"""
import itertools, os, sys, pandas as pd

TABLES = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "00_Tables")
ADJUSTED = ("corrigée", "rain_adjusted")   # label of rain-adjusted productivity (French in the original run tables, English in the Zenodo tables)

Y = "proportion_degraded_pct"


def decompose(d, factors, label):
    assert (d.groupby(factors).size() == 1).all(), label + ": design is not a balanced full factorial with one run per cell"
    y = d[Y]; gm = y.mean(); sst = ((y - gm) ** 2).sum(); ss = {}
    for r in range(1, len(factors) + 1):
        for S in itertools.combinations(factors, r):
            m = d.groupby(list(S))[Y].transform("mean")
            ss[S] = ((m - gm) ** 2).sum() - sum(ss[T] for q in range(1, r) for T in itertools.combinations(S, q))
    assert abs(sum(ss.values()) - sst) < 1e-6 * sst
    print("%s : n = %d, mean %.2f, SS_total %.1f, sum of shares %.3f%%" % (label, len(d), gm, sst, 100 * sum(ss.values()) / sst))
    return [{"analysis": label, "order": len(S), "term": " x ".join(S), "SS": round(v, 4), "share_of_SS_total_%": round(100 * v / sst, 3)} for S, v in ss.items()]


# ---- A. 96 scenarios per province
PATHS = {"Oum El Bouaghi": os.path.join(TABLES, "Master_Table_96_Scenarios_OEB.csv"), "Saida": os.path.join(TABLES, "Master_Table_96_Scenarios_Saida.csv")}
F6 = ["productivity", "rain_window", "start_year", "state_window", "land_cover_matrix", "soc"]
rows = []
for prov, path in PATHS.items():
    rows += decompose(pd.read_csv(path, sep=";", encoding="utf-8-sig"), F6, prov)
a = pd.DataFrame(rows); a.to_csv("Variance_Decomposition_Terms.csv", sep=";", index=False, encoding="utf-8-sig")
print(a[a.order == 1].to_string(index=False))

# ---- B. Oum El Bouaghi, rain-adjusted scenarios x 3 rainfall products
PATH_B = os.path.join(TABLES, "Supplementary_S2_OEB_RainProducts_AllDesigns.csv")
F6B = ["product", "rain_window", "start_year", "state_window", "land_cover_matrix", "soc"]
d = pd.read_csv(PATH_B, sep=";", encoding="utf-8-sig"); d = d[d["productivity"].isin(ADJUSTED)]
b = pd.DataFrame(decompose(d, F6B, "OEB rain-adjusted, 3 products"))
b.to_csv("Variance_Decomposition_OEB_Products.csv", sep=";", index=False, encoding="utf-8-sig")
print(b[b.order == 1].to_string(index=False))
print("terms that include the rainfall product: %.1f%%" % b[b.term.str.contains("product")]["share_of_SS_total_%"].sum())
