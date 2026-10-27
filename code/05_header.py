"""Step 5. Make header.png (1200x630 social card) by rendering a small HTML card with Playwright.

Usage:
    python3 code/05_header.py [font_dir]

Fonts come from Google Fonts. Where Google Fonts is unreachable, pass a folder holding
FrauncesVar.ttf, IBMPlexMono-Regular.ttf, IBMPlexMono-Medium.ttf and SourceSerif4-Regular.ttf.
"""
import asyncio
import json
import os
import sys

from playwright.async_api import async_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = json.load(open(os.path.join(ROOT, "data", "results.json")))
FONTS = sys.argv[1] if len(sys.argv) > 1 else None
net = json.load(open(os.path.join(ROOT, "data", "canal_network.geojson")))["features"]
lines = [[f["properties"]["year"] or 0, [[round(x, 3), round(y, 3)] for x, y in f["geometry"]["coordinates"]]] for f in net]
import csv
towns = [[float(r["lat"]), float(r["lon"]), int(r["pop1801"]), float(r["km_canal_by1830"]) <= 2]
         for r in csv.DictReader(open(os.path.join(ROOT, "data", "towns_historic.csv"))) if r["pop1801"] and r["town"] != "London"]
dek = (f"The typical canal town grew {R['panel']['main']['canal']['median_g61_bound']:.1f} times over from 1801 to 1861. "
       f"Today they are bigger, but not richer.")

HTML = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,900&family=IBM+Plex+Mono:wght@400;500&family=Source+Serif+4:opsz,wght@8..60,400&display=swap">
<style>
body{margin:0;width:1200px;height:630px;background:#E9F0EC;color:#1A211E;overflow:hidden;position:relative;font-family:'Source Serif 4',Georgia,serif}
.l{position:absolute;left:72px;top:64px;width:600px}
.k{font:500 17px/1 'IBM Plex Mono',monospace;letter-spacing:.14em;text-transform:uppercase;color:#56635D;display:flex;gap:14px;align-items:center}
.k b{background:#B3322A;color:#fff;padding:8px 10px;font-weight:500}
h1{font:900 124px/.86 'Fraunces',Georgia,serif;letter-spacing:-.02em;margin:26px 0 0}
h1 em{font-style:normal;color:#B3322A}
p{font-size:28px;line-height:1.34;margin:26px 0 0;color:#2A332E;max-width:540px}
.f{position:absolute;left:72px;bottom:36px;font:400 15px/1 'IBM Plex Mono',monospace;letter-spacing:.12em;text-transform:uppercase;color:#56635D}
canvas{position:absolute;right:20px;top:10px}
</style></head><body>
<div class="l"><div class="k"><b>Data study</b><span>History × data</span></div>
<h1>Canal<br><em>mania</em></h1>
<p>__DEK__</p></div>
<div class="f">Dr Tristan Hotham · Independent researcher</div>
<canvas id="c" width="1060" height="1220" style="width:530px;height:610px"></canvas>
<script>
const L = __LINES__, T = __TOWNS__;
const cv = document.getElementById("c"), x = cv.getContext("2d"); x.scale(2, 2);
const lat0 = 52.8, k = Math.cos(lat0 * Math.PI / 180), lo0 = -4.4, lo1 = 1.0, la0 = 50.6, la1 = 54.4;
const sc = Math.min(530 / ((lo1 - lo0) * k), 610 / (la1 - la0));
const X = l => (l - lo0) * k * sc + (530 - (lo1 - lo0) * k * sc) / 2, Y = l => (la1 - l) * sc;
const col = y => !y ? "#B9C5BF" : y < 1760 ? "#7E8F86" : y < 1790 ? "#6FB08A" : y < 1800 ? "#B3322A" : y <= 1830 ? "#1B6B40" : "#0F4A2B";
L.sort((a, b) => (a[0] === 0 ? -1 : 0) - (b[0] === 0 ? -1 : 0));
L.forEach(([y, pts]) => { x.beginPath(); pts.forEach((p, i) => i ? x.lineTo(X(p[0]), Y(p[1])) : x.moveTo(X(p[0]), Y(p[1]))); x.strokeStyle = col(y); x.lineWidth = y >= 1790 && y < 1800 ? 2.4 : 1.6; x.lineCap = "round"; x.stroke(); });
T.forEach(([la, lo, p, c]) => { x.beginPath(); x.arc(X(lo), Y(la), Math.sqrt(p) / 22, 0, 7); x.fillStyle = c ? "rgba(179,50,42,.85)" : "rgba(47,104,168,.8)"; x.fill(); x.lineWidth = 1.5; x.strokeStyle = "#E9F0EC"; x.stroke(); });
</script></body></html>"""
html = HTML.replace("__DEK__", dek).replace("__LINES__", json.dumps(lines, separators=(",", ":"))).replace("__TOWNS__", json.dumps(towns))
if FONTS:
    css = "".join(f"@font-face{{font-family:'{fam}';src:url(file://{FONTS}/{f});font-weight:{w}}}" for fam, f, w in
                  [("Fraunces", "FrauncesVar.ttf", "100 900"), ("IBM Plex Mono", "IBMPlexMono-Regular.ttf", "400"),
                   ("IBM Plex Mono", "IBMPlexMono-Medium.ttf", "500"), ("Source Serif 4", "SourceSerif4-Regular.ttf", "400")])
    html = html.replace('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,900&family=IBM+Plex+Mono:wght@400;500&family=Source+Serif+4:opsz,wght@8..60,400&display=swap">', f"<style>{css}</style>")


async def main():
    tmp = os.path.join(ROOT, "_header.html")
    open(tmp, "w", encoding="utf-8").write(html)
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--allow-file-access-from-files"])
        pg = await b.new_page(viewport={"width": 1200, "height": 630})
        await pg.goto("file://" + tmp)
        await pg.wait_for_timeout(1500)
        await pg.screenshot(path=os.path.join(ROOT, "header.png"))
        await b.close()
    os.remove(tmp)


asyncio.run(main())
print("header.png written")
