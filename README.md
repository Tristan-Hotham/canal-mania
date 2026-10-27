# Canal Mania

Did the towns on England's canals of 1760 to 1830 boom, and do they still lead today? A dated canal network, England's largest towns from 1801, and Census 2021 and ONS income figures.

**Interactive version:** https://tristan-hotham.github.io/canal-mania/

**Paper:** https://doi.org/10.5281/zenodo.23689966

This repository holds the interactive page, the datasets, the computed results and the analysis code for a data study by Dr Tristan Hotham (Independent researcher).

## Headline results

- I dated 77% (by length) of 3,884 km of OpenStreetMap canal in the UK. The busiest decade was the 1790s, with 586 km finished.
- Of the 29 largest towns in England in 1801 (London left out), 14 were canal towns by 1830 (within 2 km of a canal dated 1830 or earlier).
- From 1801 to 1861 the canal towns grew by a median of 4.0 times; the others by at most 2.7 times (several dropped out of the 1861 top 30, so their growth is an upper bound). England grew about 2.0 times from 1801 to 1851.
- The canal towns were already rising before the canals: only 3 of the 14 were among the 30 largest towns of 1662, against 11 of the 15 others (Fisher's exact p = 0.009).
- By 2021 the canal towns of 1801 had grown a median 10.2 times to their built-up areas, against 6.9 times for the others, but their household income (ONS, FYE2023) is about 6.9% lower, other things equal.
- Across 884 built-up areas in England and Wales with 10,000 or more people, canal places are about 54% bigger than others in the same region, and about 2.7% lower in household income after allowing for size, region and the coast.
- 26 of the 30 towns of 10,000 or more on the Leeds and Liverpool Canal are below the England and Wales median for household income.

These are associations, not causes. Railways arrived from 1830 and are not in the data.

## Files

- `index.html`: the interactive page (animated canal map, charts, tables). Data embedded; works as a single file.
- `header.png`: social card (1200 by 630).
- `data/canal_network.geojson`: 8,356 OSM canal ways (simplified), each with the matched canal, its opening year (`year`, the latest year in the list's cell), the earliest year in the cell (`year_first`), the source of the year and the matching method.
- `data/canals_list.csv`: the 195 rows of Wikipedia's List of canals in the United Kingdom, parsed, with the length of OSM canal matched to each.
- `data/towns_historic.csv`: every town in the ranking tables of Wikipedia's List of towns and cities in England by historical population (1377 to 1991), with its OS Open Names point, its 2021 built-up area, 2021 residents and mean household income, and distances to the nearest dated canal.
- `data/bua_2021.csv`: built-up areas (BUA22) in England and Wales with at least one MSOA: 2021 residents, income, region, and distance from the area's edge to a canal of 1830 or earlier.
- `data/results.json`: every number quoted on the page, in the paper, the blog post and the collage.
- `code/01_canals.py`: parses the canal list, matches it to OSM ways, writes the network.
- `code/02_towns.py`: parses the town tables, places towns, adds Census 2021 and income, measures canal distances.
- `code/03_analyse.py`: comparisons, tests and regressions; writes `results.json` and a temporary page data file.
- `code/04_build_page.py`: fills `code/page_template.html` from `results.json` to make `index.html`.
- `code/05_header.py`: renders `header.png` with Playwright.
- `release/`: the paper (PDF, LaTeX source and figures), the blog post and figures, and the Zenodo files. Rebuild with `python3 release/paper/figures.py [font_dir]`, `python3 release/paper/build_paper.py`, `python3 release/blog/build_post.py` and `python3 release/build_release_meta.py`.
- `reddit/`: the collage and its script.

## How to rerun

The scripts read the source files in place (paths at the top of each script): the Wikipedia and Wikidata/OSM bundles retrieved on 27 October 2026, OS Open Names, ONS geography lookups, Census 2021 TS001 and the ONS small area income estimates for FYE2023, and the Natural Earth coastline.

```
python3 code/01_canals.py
python3 code/02_towns.py
python3 code/03_analyse.py
python3 code/04_build_page.py
python3 code/05_header.py [font_dir]
```

It needs Python 3 with pandas, numpy, scipy, statsmodels, openpyxl and playwright.

## Method in brief

- Canal dates: the latest year in the "Year opened" cell of the Wikipedia list (usually when the whole line was finished), matched to OSM ways by name. OSM's Grand Union Canal is split by position into its older constituent canals. Unnamed pieces take the year of a dated canal within 300 m. Wikidata fills a few gaps.
- Canal town: OS Open Names town point within 2 km of a canal dated 1830 or earlier. Checks with 1 km, canal-age canals only, the earliest year, and any canal today.
- 1861 growth for towns missing from the 1861 top 30 is an upper bound (they had fewer than 40,400 people).
- Built-up areas: canal place if the area's edge (centroid distance minus the radius of a circle of equal area) is within 1 km of a canal dated 1830 or earlier. Income is the population-weighted mean of the MSOA estimates that best fit each area.

## Known limits

- Only the top 30 or 40 towns of each year are listed in the source tables, and there is no 1851 table, so 1861 stands in for it.
- Undated or lost canals (for example branches at Stockport, Bolton and Oldham, and the Derby and Bradford canals) make some canal towns count as "other".
- One year per canal: long canals opened in stages, so sections were often open earlier than the year shown.
- Boundaries differ across 1801, 1861 and 2021; growth to 2021 is a rough guide.
- No railway data; railways arrived from 1830.
- Canals were dug to places already growing (coalfields, ports, the new industrial towns), so the comparisons describe association, not the effect of canals.

## Sources and licences

- Canal lines: OpenStreetMap contributors, Open Database Licence (ODbL), https://www.openstreetmap.org/copyright
- Canal list and town tables: Wikipedia, "List of canals in the United Kingdom" and "List of towns and cities in England by historical population", CC BY-SA 4.0, retrieved 27 October 2026.
- Wikidata (canal dates, England population series): CC0.
- Census 2021 (TS001) and Income estimates for small areas, England and Wales, financial year ending 2023: Office for National Statistics, Open Government Licence v3.0.
- OS Open Names and ONS geography (BUA22, MSOA and LSOA lookups): contains OS data © Crown copyright and database right 2026; Open Government Licence v3.0.
- Coastline: Natural Earth, public domain.
- Base map tiles: Esri.

The data in `data/` and the text of the page are released under CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/), because they derive from Wikipedia tables; `data/canal_network.geojson` is derived from OpenStreetMap and is available under the ODbL. The code (`code/`) is released under the MIT licence (see `LICENSE`).

## Citation

Hotham, T. (2026). Canal Mania: Did England's Canal Towns Boom, and Do They Still Lead? Zenodo. https://doi.org/10.5281/zenodo.23689966

I wrote the text, with drafting and editing assistance from Claude (Anthropic), which also helped prepare the analysis code. I reviewed and checked all text and results.
