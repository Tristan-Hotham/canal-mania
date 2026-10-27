"""Step 3. Analysis. Writes data/results.json (every number used in the page, paper, blog and collage)
and data/_site_data.json (compact map and chart data for the page; removed by step 4).

Definitions
  Canal town (historic towns): the town's OS Open Names point lies within 2 km of a canal that the list dates to
  1830 or earlier (THRESH). Sensitivity checks: 1 km; canals of the canal age only (1760 to 1830); any canal on the
  map today regardless of date; earliest year in the list's cell instead of the latest.
  Canal place (2021 built-up areas): the area's edge (centroid distance minus the radius of a circle of the same
  area) lies within 1 km of a canal dated 1830 or earlier.
"""
import json
import math
import os
from collections import Counter, defaultdict

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")
R = {}
THRESH = 2.0
THRESH_BUA = 1.0
NORTH = {"North West", "North East", "Yorkshire and the Humber"}
MID = {"West Midlands", "East Midlands"}


def zone(r):
    return "North" if r in NORTH else "Midlands" if r in MID else "South and East"


# ---------------- network
cs = json.load(open(os.path.join(D, "_canal_stats.json")))
R["net"] = {k: cs[k] for k in ["osm_ways_total", "osm_ways_kept", "network_km", "named_km", "dated_km", "dated_share",
                               "named_dated_share", "dated_km_1760_1830", "dated_km_by_1830", "list_rows", "list_with_year",
                               "list_opened_1760_1830", "list_matched_to_osm"]}
R["net"]["km_by_method"] = cs["km_by_method"]
R["net"]["undated_km"] = cs["network_km"] - cs["dated_km"]
R["net"]["share_dated_by_1830_of_dated"] = cs["dated_km_by_1830"] / cs["dated_km"]
R["net"]["share_dated_1760_1830_of_dated"] = cs["dated_km_1760_1830"] / cs["dated_km"]
dec = {int(k): v for k, v in cs["km_by_decade"].items()}
R["net"]["km_by_decade"] = [{"decade": k, "km": v} for k, v in sorted(dec.items()) if 1700 <= k <= 1900 or True]
peak = max((k for k in dec if 1700 <= k < 1900), key=lambda k: dec[k])
R["net"]["peak_decade"] = peak
R["net"]["peak_decade_km"] = dec[peak]
cum = 0
cumd = {}
for k in sorted(dec):
    cum += dec[k]
    cumd[k] = cum
R["net"]["km_open_by_1760"] = sum(v for k, v in dec.items() if k < 1760)
R["net"]["km_open_by_1800"] = sum(v for k, v in dec.items() if k < 1800)
R["net"]["km_1790s"] = dec.get(1790, 0)
R["net"]["km_1770s"] = dec.get(1770, 0)
R["net"]["km_1810s"] = dec.get(1810, 0)
R["net"]["km_after_1830"] = sum(v for k, v in dec.items() if k >= 1830)
lst = pd.read_csv(os.path.join(D, "canals_list.csv"))
lst_d = lst.dropna(subset=["year_opened"]).drop_duplicates("name")
R["net"]["list_unique"] = int(lst.drop_duplicates("name").shape[0])
R["net"]["list_unique_dated"] = int(lst_d.shape[0])
R["net"]["list_unique_1760_1830"] = int(((lst_d.year_opened >= 1760) & (lst_d.year_opened <= 1830)).sum())
R["net"]["list_by_decade"] = {str(int(k)): int(v) for k, v in (lst_d.year_opened // 10 * 10).value_counts().sort_index().items()}
R["net"]["list_1790s"] = int(((lst_d.year_opened >= 1790) & (lst_d.year_opened < 1800)).sum())

# ---------------- historic towns
T = pd.read_csv(os.path.join(D, "towns_historic.csv"))
T["zone"] = T.region.map(zone)
T["coastal"] = T.dist_coast_km <= 5
for k, col, th in [("canal", "km_canal_by1830", THRESH), ("canal_1km", "km_canal_by1830", 1.0),
                   ("canal_age", "km_canal_age1760_1830", THRESH), ("canal_any", "km_canal_any", THRESH),
                   ("canal_first", "km_canal_first_by1830", THRESH), ("canal_1800", "km_canal_by1800", THRESH)]:
    T[k] = T[col] <= th
P = T[(T.pop1801.notna()) & (T.town != "London")].copy()
CUT61 = 40400   # the 30th town in the 1861 table (York); towns not in the table had fewer people
CUT00 = 100900  # the 40th town in the 1900 table (South Shields)
P["in1861"] = P.pop1861.notna()
P["in1900"] = P.pop1900.notna()
P["g61"] = np.where(P.in1861, P.pop1861 / P.pop1801, CUT61 / P.pop1801)  # upper bound when not in the table
P["g2021"] = P.pop2021 / P.pop1801
P["lg2021"] = np.log(P.g2021)
P["lp1801"] = np.log(P.pop1801)
P["north"] = P.zone == "North"
P["big"] = P.pop1801 >= P.pop1801.median()
R["panel"] = {"n": int(len(P)), "n_canal": int(P.canal.sum()), "n_other": int((~P.canal).sum()),
              "median_pop1801": float(P.pop1801.median()), "cut1861": CUT61, "cut1900": CUT00,
              "canal_towns": P[P.canal].town.tolist(), "other_towns": P[~P.canal].town.tolist()}


def grp(df, flag):
    out = {}
    for lab, g in [("canal", df[df[flag]]), ("other", df[~df[flag]])]:
        out[lab] = {
            "n": int(len(g)),
            "in1861": int(g.in1861.sum()), "in1861_share": float(g.in1861.mean()) if len(g) else None,
            "in1900": int(g.in1900.sum()), "in1900_share": float(g.in1900.mean()) if len(g) else None,
            "median_g61_bound": float(g.g61.median()) if len(g) else None,
            "median_g61_known": float(g[g.in1861].g61.median()) if g.in1861.any() else None,
            "n_censored_1861": int((~g.in1861).sum()),
            "median_g2021": float(g.g2021.median()) if len(g) else None,
            "median_income": float(g.income_fye2023.median()) if len(g) else None,
            "median_pop1801": float(g.pop1801.median()) if len(g) else None,
            "median_pop2021": float(g.pop2021.median()) if len(g) else None,
            "towns": g.town.tolist(),
        }
    return out


R["panel"]["main"] = grp(P, "canal")
R["panel"]["sens"] = {k: grp(P, k) for k in ["canal_1km", "canal_age", "canal_any", "canal_first", "canal_1800"]}
R["panel"]["by_zone"] = {z: grp(P[P.zone == z], "canal") for z in ["North", "Midlands", "South and East"]}
R["panel"]["by_size"] = {"bigger": grp(P[P.big], "canal"), "smaller": grp(P[~P.big], "canal")}
R["panel"]["by_coast"] = {"coastal": grp(P[P.coastal], "canal"), "inland": grp(P[~P.coastal], "canal")}
R["panel"]["n_coastal"] = int(P.coastal.sum())
R["panel"]["canal_coastal"] = int((P.canal & P.coastal).sum())
R["panel"]["other_coastal"] = int((~P.canal & P.coastal).sum())
R["panel"]["canal_north"] = int((P.canal & P.north).sum())
R["panel"]["other_north"] = int((~P.canal & P.north).sum())
# Mann-Whitney on bounded growth (conservative for the group with more censoring) and Fisher on staying in the table
R["panel"]["fisher_in1861"] = float(stats.fisher_exact([[P[P.canal].in1861.sum(), (~P[P.canal].in1861).sum()],
                                                         [P[~P.canal].in1861.sum(), (~P[~P.canal].in1861).sum()]])[1])
R["panel"]["mw_g2021_p"] = float(stats.mannwhitneyu(P[P.canal].g2021, P[~P.canal].g2021).pvalue)
R["panel"]["mw_income_p"] = float(stats.mannwhitneyu(P[P.canal].income_fye2023, P[~P.canal].income_fye2023).pvalue)
m = smf.ols("lg2021 ~ canal + lp1801 + coastal + north", data=P.assign(canal=P.canal.astype(int), coastal=P.coastal.astype(int), north=P.north.astype(int))).fit(cov_type="HC1")
R["panel"]["ols_g2021"] = {"coef_canal": float(m.params["canal"]), "lo": float(m.conf_int().loc["canal", 0]), "hi": float(m.conf_int().loc["canal", 1]),
                           "p": float(m.pvalues["canal"]), "ratio": float(math.exp(m.params["canal"])),
                           "ratio_lo": float(math.exp(m.conf_int().loc["canal", 0])), "ratio_hi": float(math.exp(m.conf_int().loc["canal", 1])), "n": int(m.nobs), "r2": float(m.rsquared),
                           "coef_north": float(m.params["north"]), "coef_coastal": float(m.params["coastal"])}
m2 = smf.ols("np.log(income_fye2023) ~ canal + lp1801 + coastal + north", data=P.assign(canal=P.canal.astype(int), coastal=P.coastal.astype(int), north=P.north.astype(int))).fit(cov_type="HC1")
R["panel"]["ols_income"] = {"coef_canal": float(m2.params["canal"]), "lo": float(m2.conf_int().loc["canal", 0]), "hi": float(m2.conf_int().loc["canal", 1]),
                            "p": float(m2.pvalues["canal"]), "pct": float(math.exp(m2.params["canal"]) - 1),
                            "pct_lo": float(math.exp(m2.conf_int().loc["canal", 0]) - 1), "pct_hi": float(math.exp(m2.conf_int().loc["canal", 1]) - 1), "n": int(m2.nobs),
                            "coef_north_pct": float(math.exp(m2.params["north"]) - 1), "p_north": float(m2.pvalues["north"])}
R["panel"]["spearman_1801_2021"] = float(stats.spearmanr(P.pop1801, P.pop2021)[0])
# rank tables for the page
P["rank2021"] = P.pop2021.rank(ascending=False).astype(int)
P["rank1801p"] = P.pop1801.rank(ascending=False, method="first").astype(int)
R["panel"]["table"] = [
    {"town": r.town, "region": r.region, "canal": bool(r.canal), "km": round(r.km_canal_by1830, 1), "canal_name": r.nearest_canal_by1830,
     "canal_year": int(r.nearest_canal_by1830_year), "pop1801": int(r.pop1801), "pop1861": None if pd.isna(r.pop1861) else int(r.pop1861),
     "pop1900": None if pd.isna(r.pop1900) else int(r.pop1900), "pop2021": int(r.pop2021), "income": int(r.income_fye2023),
     "g61": round(r.g61, 2), "in1861": bool(r.in1861), "g2021": round(r.g2021, 2), "rank1801": int(r.rank1801p), "rank2021": int(r.rank2021),
     "coastal": bool(r.coastal), "bua": r.bua22}
    for r in P.sort_values("pop1801", ascending=False).itertuples()]
best61 = P[P.in1861].sort_values("g61", ascending=False)
R["panel"]["fastest_1861"] = [{"town": r.town, "g": float(r.g61), "canal": bool(r.canal), "pop1801": int(r.pop1801), "pop1861": int(r.pop1861)} for r in best61.head(6).itertuples()]
R["panel"]["dropped_1861"] = [{"town": r.town, "canal": bool(r.canal), "pop1801": int(r.pop1801)} for r in P[~P.in1861].itertuples()]

# England benchmark (Wikidata Q21)
R["england"] = {"pop1801": 8331434, "pop1851": 16921972, "pop1901": 32544685}
R["england"]["g1851"] = R["england"]["pop1851"] / R["england"]["pop1801"]
R["england"]["g1901"] = R["england"]["pop1901"] / R["england"]["pop1801"]

# newcomers: towns in the 1861, 1881 or 1900 tables that were not among the 30 largest in 1801
N = T[(T.pop1801.isna()) & (T.pop1861.notna() | T.pop1881.notna() | T.pop1900.notna()) & (T.town != "London")]
R["newcomers"] = {"n": int(len(N)), "n_canal": int(N.canal.sum()), "share_canal": float(N.canal.mean()),
                  "towns": [{"town": r.town, "canal": bool(r.canal), "km": round(r.km_canal_by1830, 1), "canal_name": r.nearest_canal_by1830,
                             "first": int(1861 if not pd.isna(r.pop1861) else 1881 if not pd.isna(r.pop1881) else 1900),
                             "pop": int(r.pop1861 if not pd.isna(r.pop1861) else r.pop1881 if not pd.isna(r.pop1881) else r.pop1900),
                             "pop1900": None if pd.isna(r.pop1900) else int(r.pop1900), "region": r.region, "coastal": bool(r.coastal)}
                            for r in N.itertuples()],
                  "panel_share_canal": float(P.canal.mean())}
R["newcomers"]["n_coastal_other"] = int((~N.canal & N.coastal).sum())
R["newcomers"]["n_other"] = int((~N.canal).sum())

# pre-canal: older tables
pre = {}
for lab, g in [("canal", P[P.canal]), ("other", P[~P.canal])]:
    pre[lab] = {"n": int(len(g)), "in1377": int(g.pop1377.notna().sum()), "in1523": int(g.rank1523.notna().sum()),
                "in1662": int(g.rank1662.notna().sum()), "in1750": int(g.pop1750.notna().sum())}
    pre[lab]["share1377"] = pre[lab]["in1377"] / len(g)
    pre[lab]["share1662"] = pre[lab]["in1662"] / len(g)
R["pre"] = pre
R["pre"]["fisher_1662_p"] = float(stats.fisher_exact([[pre["canal"]["in1662"], pre["canal"]["n"] - pre["canal"]["in1662"]],
                                                      [pre["other"]["in1662"], pre["other"]["n"] - pre["other"]["in1662"]]])[1])
c1750 = T[T.pop1750.notna() & (T.town != "London")]
R["pre"]["y1750"] = [{"town": r.town, "pop1750": int(r.pop1750), "pop1801": int(r.pop1801), "g": float(r.pop1801 / r.pop1750),
                      "canal": bool(r.canal), "in1662": bool(not pd.isna(r.rank1662)), "in1377": bool(not pd.isna(r.pop1377))}
                     for r in c1750.sort_values("pop1750", ascending=False).itertuples()]
R["pre"]["canal_new_since_1662"] = [r.town for r in P[P.canal & P.rank1662.isna()].itertuples()]
R["pre"]["other_new_since_1662"] = [r.town for r in P[~P.canal & P.rank1662.isna()].itertuples()]

# ---------------- 2021 built-up areas
B = pd.read_csv(os.path.join(D, "bua_2021.csv"))
B = B[(B.pop2021 >= 10000) & B.income_fye2023.notna()].copy()
B["canal"] = B.km_edge_canal_by1830 <= THRESH_BUA
B["canal_age"] = B.km_edge_canal_age <= THRESH_BUA
B["canal_1800"] = B.km_edge_canal_by1800 <= THRESH_BUA
B["coastal"] = B.dist_coast_km <= 5
B["lp"] = np.log(B.pop2021)
B["li"] = np.log(B.income_fye2023)
B["zone"] = B.region.map(lambda r: "Wales" if r == "Wales" else zone(r))
R["bua"] = {"n": int(len(B)), "n_canal": int(B.canal.sum()), "share_canal": float(B.canal.mean()),
            "median_income_canal": float(B[B.canal].income_fye2023.median()), "median_income_other": float(B[~B.canal].income_fye2023.median()),
            "median_pop_canal": float(B[B.canal].pop2021.median()), "median_pop_other": float(B[~B.canal].pop2021.median()),
            "median_income_all": float(B.income_fye2023.median())}
R["bua"]["raw_income_gap_pct"] = R["bua"]["median_income_canal"] / R["bua"]["median_income_other"] - 1


def fit(formula, df, term="canal"):
    mm = smf.ols(formula, data=df.assign(canal=df.canal.astype(int), canal_age=df.canal_age.astype(int), canal_1800=df.canal_1800.astype(int),
                                          coastal=df.coastal.astype(int))).fit(cov_type="HC1")
    return {"coef": float(mm.params[term]), "lo": float(mm.conf_int().loc[term, 0]), "hi": float(mm.conf_int().loc[term, 1]),
            "p": float(mm.pvalues[term]), "pct": float(math.exp(mm.params[term]) - 1), "pct_lo": float(math.exp(mm.conf_int().loc[term, 0]) - 1),
            "pct_hi": float(math.exp(mm.conf_int().loc[term, 1]) - 1), "n": int(mm.nobs), "r2": float(mm.rsquared)}


R["bua"]["income_region"] = fit("li ~ canal + C(region)", B)
R["bua"]["income_full"] = fit("li ~ canal + lp + coastal + C(region)", B)
R["bua"]["size_region"] = fit("lp ~ canal + coastal + C(region)", B)
R["bua"]["income_age"] = fit("li ~ canal_age + lp + coastal + C(region)", B, "canal_age")
R["bua"]["income_1800"] = fit("li ~ canal_1800 + lp + coastal + C(region)", B, "canal_1800")
R["bua"]["income_england"] = fit("li ~ canal + lp + coastal + C(region)", B[B.region != "Wales"])
R["bua"]["size_england"] = fit("lp ~ canal + coastal + C(region)", B[B.region != "Wales"])
byr = []
for rg, g in B.groupby("region"):
    c, o = g[g.canal], g[~g.canal]
    byr.append({"region": rg, "n": int(len(g)), "n_canal": int(len(c)),
                "inc_canal": float(c.income_fye2023.median()) if len(c) else None, "inc_other": float(o.income_fye2023.median()) if len(o) else None,
                "pop_canal": float(c.pop2021.median()) if len(c) else None, "pop_other": float(o.pop2021.median()) if len(o) else None})
for r in byr:
    r["gap_pct"] = (r["inc_canal"] / r["inc_other"] - 1) if r["inc_canal"] and r["inc_other"] else None
R["bua"]["by_region"] = sorted(byr, key=lambda r: -(r["gap_pct"] if r["gap_pct"] is not None else -9))
R["bua"]["regions_canal_poorer"] = sum(1 for r in byr if r["gap_pct"] is not None and r["gap_pct"] < 0)
R["bua"]["regions_with_both"] = sum(1 for r in byr if r["gap_pct"] is not None)
# size bands
bands = [(10000, 25000), (25000, 75000), (75000, 10 ** 8)]
R["bua"]["by_size"] = []
for lo, hi in bands:
    g = B[(B.pop2021 >= lo) & (B.pop2021 < hi)]
    R["bua"]["by_size"].append({"lo": lo, "hi": hi, "n": int(len(g)), "share_canal": float(g.canal.mean()),
                                "inc_canal": float(g[g.canal].income_fye2023.median()), "inc_other": float(g[~g.canal].income_fye2023.median())})

# ---------------- Lancashire
LANCS = {"Burnley", "Chorley", "Fylde", "Hyndburn", "Lancaster", "Pendle", "Preston", "Ribble Valley", "Rossendale", "South Ribble",
         "West Lancashire", "Wyre", "Blackburn with Darwen", "Blackpool"}
L = B[B.lad.isin(LANCS) | (B.lad == "Wigan")].copy()
R["lancs"] = {"n": int(len(L)), "n_canal": int(L.canal.sum()),
              "inc_canal": float(L[L.canal].income_fye2023.median()), "inc_other": float(L[~L.canal].income_fye2023.median()),
              "pop_canal": float(L[L.canal].pop2021.median()), "pop_other": float(L[~L.canal].pop2021.median()),
              "rows": [{"bua": r.bua22, "lad": r.lad, "pop2021": int(r.pop2021), "income": int(r.income_fye2023), "canal": bool(r.canal),
                        "canal_name": r.nearest_canal_by1830 if r.canal else "", "km_edge": round(r.km_edge_canal_by1830, 2), "coastal": bool(r.coastal)}
                       for r in L.sort_values("pop2021", ascending=False).itertuples()]}
LL = B[(B.nearest_canal_by1830 == "Leeds and Liverpool Canal") & B.canal]
R["lancs"]["ll_n"] = int(len(LL))
R["lancs"]["ll_median_income"] = float(LL.income_fye2023.median())
R["lancs"]["ll_towns"] = [{"bua": r.bua22, "pop2021": int(r.pop2021), "income": int(r.income_fye2023), "region": r.region} for r in LL.sort_values("pop2021", ascending=False).itertuples()]
nw = B[B.region == "North West"]
R["lancs"]["nw_median_income"] = float(nw.income_fye2023.median())
BW = B[B.canal & (B.nearest_canal_by1830 == "Bridgewater Canal")]
R["lancs"]["bw_towns"] = [{"bua": r.bua22, "pop2021": int(r.pop2021), "income": int(r.income_fye2023)} for r in BW.sort_values("pop2021", ascending=False).itertuples()]
B["inc_rank"] = B.income_fye2023.rank(ascending=False).astype(int)
spot = {}
for nm, key in [("Burnley", "Burnley"), ("Blackburn (Blackburn with Darwen)", "Blackburn"), ("Wigan", "Wigan")]:
    r = B[B.bua22 == nm].iloc[0]
    t = T[T.bua22 == nm]
    spot[key] = {"pop2021": int(r.pop2021), "income": int(r.income_fye2023), "inc_rank": int(r.inc_rank), "of": int(len(B)),
                 "canal": r.nearest_canal_by1830, "canal_year": int(r.nearest_canal_year), "km_edge": float(r.km_edge_canal_by1830),
                 "pop1801": None if t.empty or pd.isna(t.iloc[0].pop1801) else int(t.iloc[0].pop1801),
                 "pop1861": None if t.empty or pd.isna(t.iloc[0].pop1861) else int(t.iloc[0].pop1861),
                 "pop1900": None if t.empty or pd.isna(t.iloc[0].pop1900) else int(t.iloc[0].pop1900),
                 "pop1921": None if t.empty or pd.isna(t.iloc[0].pop1921) else int(t.iloc[0].pop1921)}
R["lancs"]["spot"] = spot
R["lancs"]["share_below_median"] = float((LL.income_fye2023 < R["bua"]["median_income_all"]).mean())

# Wikidata historic populations: why not used
import re
b9 = json.load(open("/home/claude/hist/_data9/wd_osm_bundle.json"))
rows = [l.split("\t") for l in b9["wd_historic_populations_tsv"].splitlines()[1:]]
by = defaultdict(dict)
co = {}
for r in rows:
    by[r[0]][r[4][:4]] = float(r[3])
    co[r[0]] = r[2]
both = [k for k, d in by.items() if "1801" in d and "1851" in d]
fen = 0
for k in both:
    mm = re.match(r"POINT\(([-\d.]+) ([-\d.]+)\)", co[k] or "")
    if mm and 51.9 < float(mm.group(2)) < 52.8 and -0.6 < float(mm.group(1)) < 0.6:
        fen += 1
R["wd_hist"] = {"items": len(by), "with_1801_1851": len(both), "in_cambs_hunts_box": fen, "share_box": fen / len(both)}

R["panel"]["inland_canal"] = int((P.canal & ~P.coastal).sum())
R["panel"]["inland_other"] = int((~P.canal & ~P.coastal).sum())
R["panel"]["growth_gap_1861"] = R["panel"]["main"]["canal"]["median_g61_bound"] / R["panel"]["main"]["other"]["median_g61_bound"]
R["panel"]["growth_gap_2021"] = R["panel"]["main"]["canal"]["median_g2021"] / R["panel"]["main"]["other"]["median_g2021"]
R["panel"]["income_gap"] = R["panel"]["main"]["canal"]["median_income"] / R["panel"]["main"]["other"]["median_income"] - 1
R["lancs"]["ll_below_n"] = int((LL.income_fye2023 < R["bua"]["median_income_all"]).sum())
R["lancs"]["ll_gap_nw"] = R["lancs"]["ll_median_income"] / R["lancs"]["nw_median_income"] - 1
R["lancs"]["gap"] = R["lancs"]["inc_canal"] / R["lancs"]["inc_other"] - 1
R["bua"]["n_regions"] = len(byr)
R["thresholds"] = {"town_km": THRESH, "bua_km": THRESH_BUA, "bua_min_pop": 10000, "coastal_km": 5}
json.dump(R, open(os.path.join(D, "results.json"), "w"), indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))

# ---------------- site data
net = json.load(open(os.path.join(D, "canal_network.geojson")))["features"]
lines = []
names = []
nidx = {}
for f in net:
    p = f["properties"]
    nm = p["canal"] or p["osm_name"] or ""
    if nm not in nidx:
        nidx[nm] = len(names)
        names.append(nm)
    cc = f["geometry"]["coordinates"]
    flat = []
    px = py = None
    for x, y in cc:
        xi, yi = round(x * 1000), round(y * 1000)
        if (xi, yi) == (px, py):
            continue
        flat += [xi, yi]
        px, py = xi, yi
    if len(flat) >= 4:
        lines.append([p["year"] if p["year"] is not None else 0, nidx[nm], flat])
towns = []
for r in T.itertuples():
    if pd.isna(r.lat):
        continue
    g = lambda v: None if pd.isna(v) else int(v)
    towns.append([round(r.lat, 4), round(r.lon, 4), r.town, r.region, g(r.pop1377), g(r.pop1801), g(r.pop1861), g(r.pop1881), g(r.pop1900),
                  g(r.pop2021), g(r.income_fye2023), round(r.km_canal_by1830, 2), r.nearest_canal_by1830, g(r.nearest_canal_by1830_year),
                  g(r.rank1662), g(r.pop1750), bool(r.canal), g(r.pop1921), g(r.pop1951), g(r.pop1971), g(r.pop1991)])
buas = [[round(r.lat, 4), round(r.lon, 4), r.bua22, int(r.pop2021), int(r.income_fye2023), int(r.canal), r.region] for r in B.itertuples()]
scat = [[r.town, int(r.pop1801), int(r.pop2021), int(r.income_fye2023), int(r.canal), round(float(r.g61), 3), int(r.in1861)] for r in P.itertuples()]
json.dump({"lines": lines, "names": names, "towns": towns, "buas": buas, "panel": scat}, open(os.path.join(ROOT, "_site_data.json"), "w"), separators=(",", ":"))
print(json.dumps({k: R[k] for k in ["panel", "newcomers", "pre", "bua", "lancs"]}, indent=1, default=str)[:12000])
