"""Step 2. Towns: historical populations, places on the map, 2021 size and income, and distance to dated canals.

Reads (in place):
  _data9/wikipedia_wikitext.json  "List of towns and cities in England by historical population" (CC BY-SA 4.0)
  osnames_gb.tsv                  OS Open Names, City and Town points (OGL v3)
  _data8/ons_geo.json             BUA22 centroids and areas, MSOA21 to BUA22 lookup (OGL v3)
  _data8/lsoa21_bua22_lookup.json LSOA21 to BUA22 lookup (OGL v3)
  _data8/census/census2021-ts001-{lsoa,msoa}.csv  Census 2021 usual residents (OGL v3)
  _data8/ons_msoa_income_fye2023.xlsx  ONS small area income estimates FYE2023 (OGL v3)
  _data3/ne/geojson/ne_10m_coastline.geojson  Natural Earth coastline (public domain)
  data/canal_network.geojson      from step 1

Writes:
  data/towns_historic.csv  every town in the article's ranking tables (1377 to 1991), with its figures, its OS point,
                           its 2021 built-up area (BUA22), that area's 2021 residents and mean household income, and
                           its distance to the nearest canal open by 1800 and by 1830
  data/bua_2021.csv        every built-up area in England and Wales with at least one MSOA (2021 residents,
                           income, region, distance from its edge to a canal open by 1830)
"""
import csv
import json
import math
import os
import re
from collections import Counter, defaultdict

import numpy as np
import openpyxl
from scipy.spatial import cKDTree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H = "/home/claude/hist"
OUT = os.path.join(ROOT, "data")
LAT0 = 53.0
KX, KY = 111.32 * math.cos(math.radians(LAT0)), 110.57

# ---------------- 1. ranking tables
text = json.load(open(f"{H}/_data9/wikipedia_wikitext.json", encoding="utf-8"))[
    "List of towns and cities in England by historical population"]["text"]
tabs = re.findall(r"\{\|(.*?)\n\|\}", text, re.S)
YEARS = {"1377": "pop1377", "1523": "rank1523", "1662": "rank1662", "1750": "pop1750", "1801": "pop1801",
         "1861": "pop1861", "1881": "pop1881", "1900": "pop1900", "1921": "pop1921", "1951": "pop1951",
         "1971": "pop1971", "1981": "pop1981", "1991": "pop1991"}
towns = {}
table_sizes = {}
for tb in tabs:
    cap = re.search(r"\|\+\s*([^<\n]*)", tb)
    cap = cap.group(1).strip() if cap else ""
    key = YEARS.get(cap[:4]) if cap[:4] in YEARS and len(cap.strip()) <= 6 or cap.startswith(("1377", "1523", "1662", "1750", "1801", "1861", "1881")) else None
    if cap[:4] in YEARS:
        key = YEARS[cap[:4]]
    if not key:
        continue
    body = re.sub(r"<ref[^>]*/>", "", tb)
    body = re.sub(r"<ref.*?</ref>", "", body, flags=re.S)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    rows = body.split("\n|-")
    n = 0
    rank = None
    for r in rows:
        r = r.strip()
        m = re.search(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", r)
        if not m or r.startswith(("!", "|+")):
            continue
        rk = re.match(r"\|\s*(?:rowspan=\d+\|)?\s*(\d+)\s*\|\|", r)
        if rk:
            rank = int(rk.group(1))
        tail = r[m.end():]
        num = re.search(r"\|\|\s*([\d,]+)", tail)
        val = int(num.group(1).replace(",", "")) if num else None
        title = m.group(1).strip()
        t = towns.setdefault(title, {"wiki_title": title, "town": (m.group(2) or m.group(1)).split(",")[0].strip()})
        if key.startswith("rank"):
            t[key] = rank
        else:
            if val is not None and (t.get(key) is None or val > t[key]):
                t[key] = val  # Plymouth has two 1900 rows (with and without Devonport): keep the larger
                t["rank" + key[3:]] = rank
            elif key not in t:
                t["rank" + key[3:]] = rank
        n += 1
    table_sizes[key] = n
print("tables", table_sizes, "towns", len(towns))

# merge Stoke-upon-Trent (1801 to 1881) with Stoke-on-Trent (1900 onwards): the same place under the article's two links
if "Stoke-upon-Trent" in towns and "Stoke-on-Trent" in towns:
    a, b = towns.pop("Stoke-upon-Trent"), towns["Stoke-on-Trent"]
    for k, v in a.items():
        if k not in b:
            b[k] = v
# Plymouth appears twice in the 1900 table (the article's note: one row includes Devonport); keep the larger, as in 1861 and 1881.
# The article links both Preston rows to two titles; merge them.
for alt, main in [("City of Preston, Lancashire", "Preston, Lancashire"), ("County Borough of Salford", "Salford")]:
    if alt in towns:
        a = towns.pop(alt)
        b = towns.setdefault(main, {"wiki_title": main, "town": a["town"]})
        for k, v in a.items():
            if k not in b or k == "town":
                b[k] = v if k != "town" else b.get("town", v)

# Deptford and East Greenwich (1662 table only) are now parts of London: dropped, as London is kept whole.
for k in ("Deptford", "Greenwich"):
    towns.pop(k, None)

# ---------------- 2. OS Open Names points
OSNAME = {"Kingston upon Hull": "Kingston upon Hull", "Stoke-on-Trent": "Stoke-on-Trent", "Salford": "Salford",
          "Preston, Lancashire": "Preston", "St Helens, Merseyside": "St Helens", "Bath, Somerset": "Bath",
          "Ely, Cambridgeshire": "Ely", "Southend-on-Sea": "Southend-on-Sea", "Brighton": "Brighton and Hove"}
HINT = {"Boston, Lincolnshire": "Lincolnshire", "Reading, Berkshire": "Reading", "Newbury, Berkshire": "West Berkshire",
        "Wells, Somerset": "Somerset", "Stamford, Lincolnshire": "Lincolnshire", "Hythe, Kent": "Kent",
        "Sandwich, Kent": "Kent", "Wilton, Wiltshire": "Wiltshire", "Wallingford, Oxfordshire": "Oxfordshire",
        "Scarborough, North Yorkshire": "North Yorkshire", "Hadleigh, Suffolk": "Suffolk", "Halifax, West Yorkshire": "Calderdale",
        "Rochester, Kent": "Medway", "Worcester, England": "Worcestershire", "Lincoln, England": "Lincolnshire",
        "Sunderland, Tyne and Wear": "Sunderland", "St Helens, Merseyside": "St. Helens", "Preston, Lancashire": "Lancashire",
        "Newcastle upon Tyne": "Newcastle", "Dudley": "Dudley", "Swindon": "Swindon", "Bolton": "Bolton",
        "Blackburn": "Blackburn", "Cambridge": "Cambridgeshire", "Brighton": "Brighton", "Richmond": "", "Greenwich": "Greenwich",
        "Deptford": "Lewisham", "Plymouth": "Plymouth", "Huntingdon": "Cambridgeshire"}
osn = defaultdict(list)
with open(f"{H}/osnames_gb.tsv", encoding="utf-8") as f:
    for r in csv.DictReader(f, delimiter="\t"):
        if r["type"] == "populatedPlace" and r["local_type"] in ("City", "Town", "Suburban Area", "Village") and r["country"] == "England":
            osn[r["name1"]].append(r)
ORDER = {"City": 0, "Town": 1, "Suburban Area": 2, "Village": 3}
for title, t in towns.items():
    name = OSNAME.get(title, title.split(",")[0].strip())
    cands = osn.get(name, []) or osn.get(name.replace("St ", "St. "), [])
    hint = HINT.get(title)
    if hint:
        c2 = [c for c in cands if hint in (c["district"] + " " + c["county"] + " " + c["populated_place"])]
        cands = c2 or cands
    cands = sorted(cands, key=lambda c: ORDER[c["local_type"]])
    if title == "London":
        t.update(lat=51.50735, lon=-0.12776, os_name="(London: Charing Cross area, set by hand)", region="London")
        continue
    if cands:
        c = cands[0]
        t.update(lat=float(c["lat"]), lon=float(c["lon"]), os_name=f'{c["name1"]} ({c["local_type"]}, {c["district"] or c["county"]})',
                 region=c["region"], n_os_candidates=len(cands))
    else:
        t.update(lat=None, lon=None, os_name="", region="")
print("towns without an OS point:", [k for k, t in towns.items() if t.get("lat") is None])

# ---------------- 3. 2021 built-up areas: residents and income
geo = json.load(open(f"{H}/_data8/ons_geo.json", encoding="utf-8"))
bua = {b["BUA22CD"]: b for b in geo["bua22_gb"]}
lsoa_pop = {}
with open(f"{H}/_data8/census/census2021-ts001-lsoa.csv", encoding="utf-8") as f:
    for r in csv.reader(f):
        if r[0] == "2021":
            lsoa_pop[r[2]] = int(r[3])
msoa_pop = {}
with open(f"{H}/_data8/census/census2021-ts001-msoa.csv", encoding="utf-8") as f:
    for r in csv.reader(f):
        if r[0] == "2021":
            msoa_pop[r[2]] = int(r[3])
bua_pop = Counter()
lad_of = defaultdict(Counter)
for r in json.load(open(f"{H}/_data8/lsoa21_bua22_lookup.json", encoding="utf-8")):
    if r["BUA22CD"] and r["LSOA21CD"] in lsoa_pop:
        bua_pop[r["BUA22CD"]] += lsoa_pop[r["LSOA21CD"]]
inc = {}
ws = openpyxl.load_workbook(f"{H}/_data8/ons_msoa_income_fye2023.xlsx", read_only=True)["Total annual income"]
for i, r in enumerate(ws.iter_rows(values_only=True)):
    if i >= 4 and r[0] and isinstance(r[6], (int, float)):
        inc[r[0]] = (r[6], r[5], r[3])
bua_inc_w = defaultdict(float)
bua_inc_p = defaultdict(float)
bua_rgn = defaultdict(Counter)
bua_lad = defaultdict(Counter)
bua_nmsoa = Counter()
for r in geo["msoa21_bua22_lookup"]:
    b = r["BUA22CD"]
    if not b:
        continue
    p = msoa_pop.get(r["MSOA21CD"], 0)
    bua_nmsoa[b] += 1
    bua_rgn[b][r["RGN22NM"] or "Wales"] += p
    bua_lad[b][r["LAD22NM"]] += p
    if r["MSOA21CD"] in inc:
        bua_inc_w[b] += inc[r["MSOA21CD"]][0] * p
        bua_inc_p[b] += p
# London as a whole (Greater London) for the London row
london_msoas = [r for r in geo["msoa21_bua22_lookup"] if r["RGN22NM"] == "London"]
london_pop = sum(msoa_pop.get(r["MSOA21CD"], 0) for r in london_msoas)
london_inc = sum(inc[r["MSOA21CD"]][0] * msoa_pop.get(r["MSOA21CD"], 0) for r in london_msoas if r["MSOA21CD"] in inc) / london_pop

# ---------------- 4. canal distances
net = json.load(open(os.path.join(OUT, "canal_network.geojson"), encoding="utf-8"))["features"]


def densify(coords, step=0.1):
    out = []
    for i in range(len(coords) - 1):
        (x0, y0), (x1, y1) = coords[i], coords[i + 1]
        d = math.hypot((x1 - x0) * KX, (y1 - y0) * KY)
        n = max(1, int(d / step))
        for k in range(n):
            out.append((x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n))
    out.append(tuple(coords[-1]))
    return out


def tree_for(cond, key="year"):
    P, meta = [], []
    for ft in net:
        y = ft["properties"][key]
        if y is None or not cond(y):
            continue
        for x, yy in densify(ft["geometry"]["coordinates"]):
            P.append((x * KX, yy * KY))
            meta.append(ft["properties"])
    return cKDTree(np.array(P)), meta


TREES = {"by1800": tree_for(lambda y: y <= 1800), "by1830": tree_for(lambda y: y <= 1830),
         "age1760_1830": tree_for(lambda y: 1760 <= y <= 1830), "first_by1830": tree_for(lambda y: y <= 1830, "year_first"),
         "any": tree_for(lambda y: True)}


def near(lon, lat, which):
    tr, meta = TREES[which]
    d, j = tr.query((lon * KX, lat * KY))
    return float(d), meta[j]


coast = []
for ft in json.load(open(f"{H}/_data3/ne/geojson/ne_10m_coastline.geojson", encoding="utf-8"))["features"]:
    g = ft["geometry"]
    lines = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
    for ln in lines:
        if any(-8 < x < 2.5 and 49.5 < y < 59 for x, y in ln):
            coast.extend(densify(ln, 0.5))
ctree = cKDTree(np.array([(x * KX, y * KY) for x, y in coast]))

# ---------------- 5. towns: BUA match and output
bua_by_name = defaultdict(list)
for b in bua.values():
    bua_by_name[b["BUA22NM"].split(" (")[0]].append(b)
BUANAME = {"Stoke-on-Trent": "Stoke-on-Trent", "Brighton": "Brighton and Hove", "Kingston upon Hull": "Kingston upon Hull",
           "Newcastle upon Tyne": "Newcastle upon Tyne"}
rows = []
for title, t in towns.items():
    r = dict(t)
    if t.get("lat") is not None:
        r["dist_coast_km"] = round(float(ctree.query((t["lon"] * KX, t["lat"] * KY))[0]), 2)
        for w in TREES:
            d, m = near(t["lon"], t["lat"], w)
            r[f"km_canal_{w}"] = round(d, 3)
            if w == "by1830":
                r["nearest_canal_by1830"] = m["canal"]
                r["nearest_canal_by1830_year"] = m["year"]
            if w == "any":
                r["nearest_canal_any"] = m["canal"]
                r["nearest_canal_any_year"] = m["year"]
    if title == "London":
        r.update(bua22="Greater London (all London MSOAs)", pop2021=london_pop, income_fye2023=round(london_inc))
    elif t.get("lat") is not None:
        nm = BUANAME.get(title, OSNAME.get(title, title.split(",")[0].strip()))
        c = bua_by_name.get(nm, [])
        if c:
            b = min(c, key=lambda b: math.hypot((b["LONG"] - t["lon"]) * KX, (b["LAT"] - t["lat"]) * KY))
            dd = math.hypot((b["LONG"] - t["lon"]) * KX, (b["LAT"] - t["lat"]) * KY)
            if dd < 15:
                r.update(bua22cd=b["BUA22CD"], bua22=b["BUA22NM"], pop2021=bua_pop.get(b["BUA22CD"]),
                         income_fye2023=round(bua_inc_w[b["BUA22CD"]] / bua_inc_p[b["BUA22CD"]]) if bua_inc_p[b["BUA22CD"]] else None,
                         bua_lad=bua_lad[b["BUA22CD"]].most_common(1)[0][0] if bua_lad[b["BUA22CD"]] else "")
    rows.append(r)
cols = ["town", "wiki_title", "os_name", "lat", "lon", "region", "pop1377", "rank1377", "rank1523", "rank1662", "pop1750",
        "pop1801", "rank1801", "pop1861", "rank1861", "pop1881", "rank1881", "pop1900", "rank1900", "pop1921", "pop1951", "pop1971",
        "pop1981", "pop1991", "bua22cd", "bua22", "bua_lad", "pop2021", "income_fye2023", "dist_coast_km",
        "km_canal_by1800", "km_canal_by1830", "km_canal_age1760_1830", "km_canal_first_by1830", "km_canal_any",
        "nearest_canal_by1830", "nearest_canal_by1830_year", "nearest_canal_any", "nearest_canal_any_year"]
rows.sort(key=lambda r: -(r.get("pop1801") or 0))
with open(os.path.join(OUT, "towns_historic.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
print("towns written", len(rows), "with BUA", sum(1 for r in rows if r.get("pop2021")))
print("no BUA:", [r["wiki_title"] for r in rows if not r.get("pop2021")])

# ---------------- 6. all built-up areas, England and Wales
out = []
for code, b in bua.items():
    if not code.startswith(("E", "W")) or bua_nmsoa[code] == 0 or not bua_pop.get(code):
        continue
    req = math.sqrt(b["Shape__Area"] / math.pi) / 1000
    d30, m30 = near(b["LONG"], b["LAT"], "by1830")
    d00, _ = near(b["LONG"], b["LAT"], "by1800")
    dag, _ = near(b["LONG"], b["LAT"], "age1760_1830")
    out.append({"bua22cd": code, "bua22": b["BUA22NM"], "lat": round(b["LAT"], 5), "lon": round(b["LONG"], 5),
                "region": bua_rgn[code].most_common(1)[0][0], "lad": bua_lad[code].most_common(1)[0][0],
                "pop2021": bua_pop[code], "n_msoa": bua_nmsoa[code],
                "income_fye2023": round(bua_inc_w[code] / bua_inc_p[code]) if bua_inc_p[code] else "",
                "radius_km": round(req, 3), "km_centre_canal_by1830": round(d30, 3), "km_edge_canal_by1830": round(max(0, d30 - req), 3),
                "km_edge_canal_by1800": round(max(0, d00 - req), 3), "km_edge_canal_age": round(max(0, dag - req), 3),
                "nearest_canal_by1830": m30["canal"], "nearest_canal_year": m30["year"],
                "dist_coast_km": round(float(ctree.query((b["LONG"] * KX, b["LAT"] * KY))[0]), 2)})
out.sort(key=lambda r: -r["pop2021"])
with open(os.path.join(OUT, "bua_2021.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
    w.writeheader()
    w.writerows(out)
print("BUAs", len(out))
