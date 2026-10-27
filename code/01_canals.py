"""Step 1. Build a dated canal network.

Reads (in place, never copied):
  /home/claude/hist/_data9/wikipedia_wikitext.json  "List of canals in the United Kingdom" (CC BY-SA 4.0)
  /home/claude/hist/_data9/wd_osm_bundle.json       "wd_canals_tsv" (Wikidata, CC0) and "osm_canals_uk" (OSM, ODbL)

Writes:
  data/canals_list.csv         one row per canal in the Wikipedia list (name, country table, length, year opened)
  data/canal_network.geojson   OSM canal ways (simplified) with the matched canal name, opening year and match method
  data/_canal_stats.json       coverage figures, read by step 3

Matching, in order:
  1. exact match of the normalised OSM name to a Wikipedia list name (link target or display text);
  2. the OSM name starts with, or contains, a list name (longest list name wins), e.g. "Birmingham Canal
     Navigations Main Line" -> "Birmingham Canal Navigations";
  3. a small table of aliases written by hand (ALIASES below), each checked against the list;
  4. a Wikidata canal item with the same normalised label and an opening (P1619) or inception (P571) date,
     used only where the list has no year.
Unnamed ways take the year of the nearest dated way if it is within 300 m (method "nearest"), which mostly
fills short unnamed pieces (locks, basins, arms) of dated canals. Ways tagged as spillways, mill races,
irrigation or drains are dropped.

The year used is the latest year in the list's "Year opened" cell (for example "1727, 1810" gives 1810 for the
Kennet and Avon). For long canals built in stages this is usually the year the whole line was finished, so many
sections were open earlier than the year shown; the earliest year in the cell is kept as year_first and used in a
sensitivity check.

"Grand Union Canal" in OSM is the 1929 amalgamation of older canals, and the list dates it 1927. OSM ways with
that name are therefore given to their older constituent canals by position (GRAND_UNION below): south of
latitude 52.27 (Braunston and Norton Junction) the Grand Junction Canal; the Leicester line north of 52.27 and
east of longitude -1.2 the Grand Union Canal (old) up to latitude 52.47 and the Leicestershire and
Northamptonshire Union Canal beyond; the Birmingham line west of -1.2 the Warwick and Napton Canal east of
-1.55 and the Warwick and Birmingham Canal west of it. Each takes that canal's year from the list.
OSM waterway relations are dropped because they repeat their member ways.
"""
import json
import math
import os
import re
from collections import Counter, defaultdict

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D9 = "/home/claude/hist/_data9"
OUT = os.path.join(ROOT, "data")

wiki = json.load(open(os.path.join(D9, "wikipedia_wikitext.json"), encoding="utf-8"))
bundle = json.load(open(os.path.join(D9, "wd_osm_bundle.json"), encoding="utf-8"))
text = wiki["List of canals in the United Kingdom"]["text"]


def norm(s):
    s = s.lower().replace("&", " and ").replace("'", "").replace("’", "")
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\b(the|of)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ---------- 1. Wikipedia list tables
SECTIONS = [("England", "==Canals in England==", 6), ("Northern Ireland", "==Canals in Northern Ireland==", 3),
            ("Scotland", "==Canals in Scotland==", 5), ("Wales", "==Canals in Wales==", 5)]
canals = []
for i, (country, head, ycol) in enumerate(SECTIONS):
    a = text.index(head)
    b = text.index(SECTIONS[i + 1][1]) if i + 1 < len(SECTIONS) else text.index("==Proposed canal routes==")
    sec = text[a:b]
    for row in sec.split("\n|-"):
        row = row.strip()
        if not row.startswith("|") or row.startswith("|}") or row.startswith("|+"):
            continue
        row = re.sub(r"<ref[^>]*/>", "", row)
        row = re.sub(r"<ref[^>]*>.*?</ref>", "", row, flags=re.S)
        cells = [c.strip() for c in row[1:].split("||")]
        if len(cells) <= ycol:
            continue
        m = re.search(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", cells[0])
        if not m:
            name = re.sub(r"[\[\]']", "", cells[0]).strip()
            target = name
        else:
            target = m.group(1).strip()
            name = (m.group(2) or m.group(1)).strip()
        ycell = cells[ycol]
        sortm = re.search(r"\{\{sort\|(\d{3,4})", ycell)
        yrs = [int(y) for y in re.findall(r"(?<!\d)(1[0-9]{3}|[0-9]{3})(?!\d)", re.sub(r"\{\{sort\|\d+\|", "", ycell))]
        allyrs = yrs + ([int(sortm.group(1))] if sortm else [])
        year = max(allyrs) if allyrs else None  # completion: the latest year the cell gives
        first = min(allyrs) if allyrs else None
        approx = "appr" in ycell or "c." in ycell
        lm = re.search(r"\{\{convert\|([\d.]+)\|mi", cells[1])
        miles = float(lm.group(1)) if lm else None
        if miles is None:
            lm2 = re.match(r"\s*([\d.]+)", re.sub(r"<.*?>", "", cells[1]))
            miles = float(lm2.group(1)) if lm2 else None
        canals.append({"name": name, "wiki_title": target, "country": country, "miles": miles,
                       "year_opened": year, "year_first": first, "year_text": re.sub(r"\{\{sort\|\d+\|([^}]*)\}\}", r"\1", ycell).strip(),
                       "years_mentioned": ";".join(str(y) for y in yrs), "approx": approx})
print("list rows", len(canals), Counter(c["country"] for c in canals))

# ---------- 2. Wikidata canals
wd = {}
for line in bundle["wd_canals_tsv"].splitlines()[1:]:
    r = line.split("\t")
    while len(r) < 7:
        r.append("")
    lab = r[1].split('"')[1] if '"' in r[1] else r[1]
    cls = r[2].split('"')[1] if '"' in r[2] else r[2]
    if cls not in ("canal", "navigation", "section of a canal", "ship canal", "navigation channel"):
        continue
    yr = None
    src = None
    if r[5]:
        yr, src = int(r[5][:4]), "Wikidata P1619 opened"
    elif r[4]:
        yr, src = int(r[4][:4]), "Wikidata P571 inception"
    k = norm(lab)
    if k not in wd or (wd[k]["year"] is None and yr):
        wd[k] = {"label": lab, "item": r[0].strip("<>").split("/")[-1], "year": yr, "src": src}

# lookup of list names
keys = {}
for c in canals:
    for nm in {c["name"], c["wiki_title"]}:
        k = norm(nm)
        if k and k not in keys:
            keys[k] = c
# fill list years from Wikidata where the list has none
for c in canals:
    c["year_source"] = "Wikipedia list" if c["year_opened"] is not None else ""
    c["wikidata"] = ""
    w = wd.get(norm(c["wiki_title"])) or wd.get(norm(c["name"]))
    if w:
        c["wikidata"] = w["item"]
        if c["year_opened"] is None and w["year"]:
            c["year_opened"], c["year_source"] = w["year"], w["src"]

# hand aliases: OSM name (normalised) -> list name. Only where the OSM name is a well-known variant.
ALIASES = {
    "grand union canal": "Grand Union Canal",
    "staffs and worcs canal": "Staffordshire and Worcestershire Canal",
    "kennet and avon": "Kennet and Avon Canal",
    "regents canal": "Regent's Canal",
    "manchester bolton and bury canal": "Manchester Bolton & Bury Canal",
    "caledonian": "Caledonian Canal",
    "monmouthshire and brecon canal": "Monmouthshire, Brecon and Abergavenny Canal",
    "monmouthshire canal": "Monmouthshire, Brecon and Abergavenny Canal",
    "brecon and abergavenny canal": "Monmouthshire, Brecon and Abergavenny Canal",
    "hereford and gloucester canal": "Herefordshire and Gloucestershire Canal",
    "neath canal": "Neath and Tennant Canal",
    "tennant canal": "Neath and Tennant Canal",
    "birmingham old main line canal": "Birmingham Canal Navigations",
    "dudley no 2 canal": "Dudley Canal",
    "dudley no 1 canal": "Dudley Canal",
    "fossdyke navigation": "Foss Dyke",
}


def grand_union(lon, lat):
    if lat < 52.27:
        return "Grand Junction Canal"
    if lon > -1.2:
        return "Grand Union Canal (old)" if lat < 52.47 else "Leicestershire and Northamptonshire Union Canal"
    return "Warwick and Napton Canal" if lon > -1.55 else "Warwick and Birmingham Canal"
akeys = {}
for a, target in ALIASES.items():
    t = norm(target)
    if t in keys:
        akeys[a] = keys[t]

skeys = sorted(keys, key=len, reverse=True)


def match(osm_name, pts):
    n = norm(osm_name)
    if not n:
        return None, None
    if n.startswith("grand union canal"):
        mid = pts[len(pts) // 2]
        return keys[norm(grand_union(mid[0], mid[1]))], "grand union split"
    if n in keys:
        return keys[n], "exact"
    if n in akeys:
        return akeys[n], "alias"
    for k in skeys:
        if len(k) >= 8 and (n.startswith(k + " ") or (" " + k + " ") in (" " + n + " ")):
            return keys[k], "contains"
    for a in sorted(akeys, key=len, reverse=True):
        if n.startswith(a + " ") or (" " + a + " ") in (" " + n + " "):
            return akeys[a], "alias"
    if n in wd and wd[n]["year"]:
        return {"name": wd[n]["label"], "year_opened": wd[n]["year"], "year_source": wd[n]["src"],
                "wikidata": wd[n]["item"], "country": ""}, "wikidata"
    return None, None


# ---------- 3. OSM ways
DROP = {"spillway", "irrigation", "headrace", "tailrace", "drain", "intake", "watershed_management", "transmission"}
LAT0 = 53.0
KX, KY = 111.32 * math.cos(math.radians(LAT0)), 110.57


def length_km(pts):
    return sum(math.hypot((pts[i + 1][0] - pts[i][0]) * KX, (pts[i + 1][1] - pts[i][1]) * KY) for i in range(len(pts) - 1))


ways = []
dropped = Counter()
for w in bundle["osm_canals_uk"]:
    if w.get("usage") in DROP:
        dropped[w["usage"]] += 1
        continue
    if w["osm"].startswith("relation"):
        dropped["relation (repeats member ways)"] += 1
        continue
    if len(w["pts"]) < 2:
        dropped["single point"] += 1
        continue
    c, how = match(w.get("name") or "", w["pts"])
    ways.append({"osm": w["osm"], "osm_name": w.get("name") or "", "disused": w.get("disused") or "",
                 "pts": w["pts"], "km": length_km(w["pts"]), "canal": c["name"] if c else "",
                 "year": c["year_opened"] if c else None, "year_first": c.get("year_first") if c else None, "year_source": c.get("year_source", "") if c else "",
                 "method": how or ""})
print("ways kept", len(ways), "dropped", dict(dropped))

# nearest dated way for unnamed ways (within 300 m)
dated_pts = []
for i, w in enumerate(ways):
    if w["year"] is not None:
        for p in w["pts"]:
            dated_pts.append((p[0] * KX, p[1] * KY, i))
from scipy.spatial import cKDTree

arr = np.array([(a, b) for a, b, _ in dated_pts])
idx = np.array([i for _, _, i in dated_pts])
tree = cKDTree(arr)
for w in ways:
    if w["year"] is None and not w["osm_name"]:
        q = np.array([(p[0] * KX, p[1] * KY) for p in w["pts"]])
        d, j = tree.query(q)
        k = int(np.argmin(d))
        if d[k] <= 0.3:
            src = ways[idx[j[k]]]
            w.update(canal=src["canal"], year=src["year"], year_first=src["year_first"], year_source=src["year_source"], method="nearest")

# ---------- 4. stats and outputs
tot = sum(w["km"] for w in ways)
dated = sum(w["km"] for w in ways if w["year"] is not None)
named = sum(w["km"] for w in ways if w["osm_name"])
named_dated = sum(w["km"] for w in ways if w["osm_name"] and w["year"] is not None)
by_method = defaultdict(float)
for w in ways:
    by_method[w["method"] or "none"] += w["km"]
unmatched = Counter()
for w in ways:
    if w["year"] is None and w["osm_name"]:
        unmatched[w["osm_name"]] += w["km"]
by_decade = defaultdict(float)
for w in ways:
    if w["year"] is not None:
        by_decade[(w["year"] // 10) * 10] += w["km"]
canal_age = sum(w["km"] for w in ways if w["year"] is not None and 1760 <= w["year"] <= 1830)
pre1830 = sum(w["km"] for w in ways if w["year"] is not None and w["year"] <= 1830)
stats = {
    "osm_ways_total": len(bundle["osm_canals_uk"]), "osm_ways_kept": len(ways), "osm_ways_dropped": sum(dropped.values()),
    "network_km": tot, "named_km": named, "dated_km": dated, "dated_share": dated / tot,
    "named_dated_share": named_dated / named, "km_by_method": dict(by_method),
    "dated_km_1760_1830": canal_age, "dated_km_by_1830": pre1830,
    "km_by_decade": {str(k): v for k, v in sorted(by_decade.items())},
    "unmatched_named_top": [[n, round(v, 1)] for n, v in unmatched.most_common(25)],
    "list_rows": len(canals), "list_with_year": sum(1 for c in canals if c["year_opened"] is not None),
    "list_years_from_wikidata": sum(1 for c in canals if c["year_source"].startswith("Wikidata")),
    "list_rows_by_country": dict(Counter(c["country"] for c in canals)),
    "list_opened_1760_1830": sum(1 for c in canals if c["year_opened"] and 1760 <= c["year_opened"] <= 1830),
    "list_matched_to_osm": len({w["canal"] for w in ways if w["canal"]} & {c["name"] for c in canals}),
}
json.dump(stats, open(os.path.join(OUT, "_canal_stats.json"), "w"), indent=1)

import csv

with open(os.path.join(OUT, "canals_list.csv"), "w", newline="", encoding="utf-8") as f:
    cols = ["name", "wiki_title", "country", "miles", "year_opened", "year_first", "year_source", "year_text", "years_mentioned", "approx", "wikidata",
            "osm_km_matched"]
    km = defaultdict(float)
    for w in ways:
        if w["canal"]:
            km[w["canal"]] += w["km"]
    wr = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
    wr.writeheader()
    for c in canals:
        c["osm_km_matched"] = round(km.get(c["name"], 0), 2)
        wr.writerow(c)

feats = []
for w in ways:
    feats.append({"type": "Feature", "properties": {"osm": w["osm"], "osm_name": w["osm_name"], "canal": w["canal"],
                                                    "year": w["year"], "year_first": w["year_first"], "year_source": w["year_source"], "match": w["method"],
                                                    "disused": w["disused"], "km": round(w["km"], 3)},
                  "geometry": {"type": "LineString", "coordinates": [[round(x, 5), round(y, 5)] for x, y in w["pts"]]}})
json.dump({"type": "FeatureCollection", "features": feats}, open(os.path.join(OUT, "canal_network.geojson"), "w"),
          separators=(",", ":"))
print(json.dumps({k: v for k, v in stats.items() if k != "unmatched_named_top"}, indent=1))
print(stats["unmatched_named_top"])
