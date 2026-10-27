"""r/dataisbeautiful collage for Canal Mania. Reads only ../data/ and the Natural Earth land polygons.
Usage (from reddit/): python3 collage.py [font_dir]
"""
import json
import os
import sys

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "..", "data")
F = sys.argv[1] if len(sys.argv) > 1 else "/tmp/claude-0/-home-claude/c232619d-81e0-53f3-9de6-41e973630753/scratchpad/fonts"
for f in ["FrauncesVar.ttf", "IBMPlexMono-Regular.ttf", "IBMPlexMono-Medium.ttf", "SourceSerif4-Regular.ttf", "SourceSerif4-Semibold.ttf", "SourceSerif4-It.ttf"]:
    fm.fontManager.addfont(os.path.join(F, f))
DISP = fm.FontProperties(fname=os.path.join(F, "FrauncesVar.ttf"), weight=900)
SER, MONO = "Source Serif 4", "IBM Plex Mono"
BG, FG, MUT = "#DCEAE6", "#16201C", "#4E5F58"
LANDC, LANDE = "#F1F6F3", "#BCCCC5"
RED, BLUE, GREEN, DGREEN, OLD, UND = "#B3322A", "#2F68A8", "#1F7A4D", "#0F3D27", "#8A9690", "#B4C3BC"
R = json.load(open(os.path.join(D, "results.json")))
T = pd.read_csv(os.path.join(D, "towns_historic.csv"))
NET = json.load(open(os.path.join(D, "canal_network.geojson")))["features"]
K = np.cos(np.radians(52.8))

land = []
for ft in json.load(open("/home/claude/hist/_data3/ne/geojson/ne_10m_land.geojson"))["features"]:
    g = ft["geometry"]
    for p in (g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]):
        r = np.array(p[0])
        if ((r[:, 0] > -11) & (r[:, 0] < 3) & (r[:, 1] > 49) & (r[:, 1] < 61)).any():
            land.append(r)


def base(ax, xlim=(-5.75, 1.85), ylim=(50.0, 55.15)):
    for r in land:
        ax.fill(r[:, 0] * K, r[:, 1], color=LANDC, ec=LANDE, lw=0.6, zorder=0)
    ax.set_xlim(xlim[0] * K, xlim[1] * K)
    ax.set_ylim(*ylim)
    ax.set_aspect("equal")
    ax.axis("off")


def lines(ax, upto=None, lw=1.6, recent=None):
    segs, cols, lws = [], [], []
    for f in sorted(NET, key=lambda f: f["properties"]["year"] or 0):
        y = f["properties"]["year"]
        if upto is not None and (y is None or y > upto):
            continue
        c = np.array(f["geometry"]["coordinates"])
        segs.append(np.c_[c[:, 0] * K, c[:, 1]])
        if recent is not None:
            cols.append(RED if y > upto - recent else GREEN)
            lws.append(lw * (1.5 if y > upto - recent else 1))
        else:
            cols.append(UND if y is None else OLD if y < 1760 else GREEN if y <= 1830 else DGREEN)
            lws.append(lw * (0.5 if y is None else 1))
    ax.add_collection(LineCollection(segs, colors=cols, linewidths=lws, capstyle="round", zorder=2))


fig = plt.figure(figsize=(12, 15), dpi=200, facecolor=BG)
fig.text(0.04, 0.968, "Did canals make", fontproperties=DISP, fontsize=50, color=FG, va="top")
fig.text(0.04, 0.918, "the boom towns?", fontproperties=DISP, fontsize=50, color=RED, va="top")
P = R["panel"]
fig.text(0.04, 0.862, f"England dug most of its canals between 1760 and 1830. I dated {R['net']['dated_share']*100:.0f}% of today's mapped\n"
         f"network and followed the {P['n']} largest towns of 1801 (London aside) to 2021.",
         family=SER, fontsize=15, color=FG, va="top", linespacing=1.4)

# hero map
ax = fig.add_axes([-0.01, 0.30, 0.60, 0.495])
base(ax, ylim=(50.0, 55.05))
lines(ax, lw=2.0)
Pn = T[T.pop1801.notna() & (T.town != "London")]
for r in Pn.sort_values("pop1801", ascending=False).itertuples():
    canal = r.km_canal_by1830 <= 2
    ax.scatter(r.lon * K, r.lat, s=np.sqrt(r.pop1801) * 2.6, color=RED if canal else BLUE, alpha=0.88, edgecolor="white", lw=1.2, zorder=3)
lab = {"Manchester": (0.0, -0.3, "center"), "Liverpool": (-0.22, 0.13, "right"), "Birmingham": (-0.2, -0.24, "right"), "Bristol": (-0.22, -0.1, "right"),
       "Leeds": (0.2, -0.14, "left"), "Blackburn": (-0.16, 0.14, "right"), "Norwich": (-0.15, 0.18, "right"), "Plymouth": (0.17, -0.12, "left"),
       "Hull": (0.17, 0.1, "left"), "Newcastle": (0.17, 0.05, "left"), "Sheffield": (0.2, -0.08, "left"), "Exeter": (0.16, 0.05, "left")}
for r in Pn.itertuples():
    if r.town in lab:
        dx, dy, ha = lab[r.town]
        ax.text(r.lon * K + dx, r.lat + dy, r.town, family=MONO, fontsize=10.5, color=FG, ha=ha, va="center", zorder=4,
                path_effects=[pe.withStroke(linewidth=3.5, foreground=LANDC)])
hs = [Line2D([], [], color=OLD, lw=3, label="canal finished before 1760"), Line2D([], [], color=GREEN, lw=3, label="1760 to 1830, the canal age"),
      Line2D([], [], color=DGREEN, lw=3, label="after 1830"), Line2D([], [], color=UND, lw=2, label="no date in my sources"),
      Line2D([], [], marker="o", ls="", color=RED, ms=11, label="canal town of 1801 (within 2 km)"), Line2D([], [], marker="o", ls="", color=BLUE, ms=11, label="other large town of 1801")]
fig.legend(handles=hs, loc="upper left", bbox_to_anchor=(0.04, 0.305), frameon=False, prop={"family": MONO, "size": 10.5}, labelcolor=FG, ncol=2,
           columnspacing=1.6, handlelength=1.8)

# right column numbers
tx = fig.add_axes([0.60, 0.33, 0.38, 0.49])
tx.axis("off")
pre = R["pre"]
notes = [(f"{P['main']['canal']['median_g61_bound']:.1f}× vs {P['main']['other']['median_g61_bound']:.1f}×",
          f"median growth 1801 to 1861: canal towns\nagainst the other big towns of 1801 (at most).\nEngland as a whole: about {R['england']['g1851']:.1f}× from 1801 to 1851."),
         (f"{pre['canal']['in1662']} of {pre['canal']['n']}",
          f"canal towns were already among the 30\nbiggest towns in 1662. Other towns: {pre['other']['in1662']} of {pre['other']['n']}.\nCanals were dug to towns already booming."),
         (f"+{R['bua']['size_region']['pct']*100:.0f}%",
          f"bigger today: the {R['bua']['n_canal']} towns of 10,000+ within 1 km\nof a canal of 1830 or earlier, against others\nin the same region ({R['bua']['n']} towns in all)."),
         (f"{abs(R['bua']['income_full']['pct'])*100:.1f}% poorer",
          "mean household income in canal towns\ntoday, allowing for size, region and coast.\nSize outlasted the boom; wealth did not.")]
for (big, small), y in zip(notes, [1.0, 0.74, 0.48, 0.22]):
    tx.text(0, y, big, fontproperties=DISP, fontsize=32, color=RED, va="top", transform=tx.transAxes)
    tx.text(0, y - 0.082, small, family=SER, fontsize=12.5, color=FG, va="top", transform=tx.transAxes, linespacing=1.3)

# small multiples: the network growing
fig.text(0.04, 0.232, "THE NETWORK GROWS  ·  canals open at the end of each decade; red = opened in that decade", family=MONO, fontsize=11, color=MUT)
for i, yr in enumerate([1769, 1789, 1799, 1809, 1829]):
    a = fig.add_axes([0.01 + i * 0.198, 0.088, 0.19, 0.115])
    base(a, xlim=(-3.6, 0.6), ylim=(50.7, 54.3))
    lines(a, upto=yr, lw=1.3, recent=10)
    km = sum(d["km"] for d in R["net"]["km_by_decade"] if d["decade"] <= yr - 9)
    a.set_title(f"by {yr}: {km:,.0f} km", family=MONO, fontsize=11, color=FG, pad=3)

fig.text(0.04, 0.018, "Data: OpenStreetMap canals (ODbL); opening years and town populations from Wikipedia's List of canals in the UK and List of towns\n"
         "and cities in England by historical population (CC BY-SA 4.0); Wikidata (CC0); ONS Census 2021 and income estimates FYE2023, OS Open Names\n"
         "(OGL v3, contains OS data © Crown copyright 2026); Natural Earth. Association, not cause; railways from 1830 not included.\n"
         "Analysis and chart: Tristan Hotham, with Python and matplotlib.", family=MONO, fontsize=9, color=MUT, linespacing=1.45)
fig.savefig(os.path.join(HERE, "did_canals_make_the_boom_towns.png"), facecolor=BG, dpi=200)
print("ok")
