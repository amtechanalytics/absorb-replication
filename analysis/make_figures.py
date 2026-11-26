"""Figures for the manuscript, drawn from numbers.json (which analyse.py writes from the run records).

Usage: python3 make_figures.py [numbers.json] [output folder]   (defaults: numbers.json next to this script, ../figures)
Requires matplotlib.
"""
import json
import os
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "numbers.json")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "figures")
os.makedirs(OUT, exist_ok=True)
N = json.load(open(SRC))
plt.rcParams.update({"font.size": 9, "font.family": "serif", "pdf.fonttype": 42, "axes.spines.top": False,
                     "axes.spines.right": False})
BLUE = ["#c6dbef", "#6baed6", "#08519c"]

# Figure: exact share by source format and arm
fmts = [("fhir_r4", "FHIR\nR4"), ("fhir_stu3", "FHIR\nSTU3"), ("claims", "Claims"), ("d1", "Dialect 1\nrenames"),
        ("d2", "Dialect 2\nstructure"), ("d3", "Dialect 3\nunits")]
fig, ax = plt.subplots(figsize=(4.7, 2.6))
w = 0.26
for j, arm in enumerate(("A1", "A2", "A3")):
    xs, ys, lo, hi = [], [], [], []
    for i, (f, _) in enumerate(fmts):
        d = N["format_arm"][f"{f}|{arm}"]
        p = 100 * d["exact"] / d["n"]
        xs.append(i + (j - 1) * w); ys.append(p); lo.append(p - d["lo"]); hi.append(d["hi"] - p)
    ax.bar(xs, ys, w, color=BLUE[j], edgecolor="black", linewidth=0.4,
           label={"A1": "A1 single call", "A2": "A2 + build feedback", "A3": "A3 + mapping hints"}[arm])
    ax.errorbar(xs, ys, yerr=[lo, hi], fmt="none", ecolor="black", elinewidth=0.5, capsize=1.2)
ax.set_xticks(range(len(fmts))); ax.set_xticklabels([l for _, l in fmts], fontsize=7.5)
ax.set_ylabel("Exact integrations (%)"); ax.set_ylim(0, 105)
ax.legend(frameon=False, fontsize=7.5, loc="lower center", ncol=3, bbox_to_anchor=(0.46, 1.0), columnspacing=0.9,
          handlelength=1.1, handletextpad=0.4)
fig.tight_layout(pad=0.3); fig.savefig(os.path.join(OUT, "fig_exact_by_format.pdf")); plt.close(fig)

# Figure: outcome of staging integrations by arm
fig, ax = plt.subplots(figsize=(4.7, 1.75))
cats = [("exact", "Exact", "#08519c"), ("silent", "Passes build and tests, wrong cells", "#de2d26"),
        ("testfail", "Builds, a test fails", "#fdae6b"), ("nobuild", "Does not build", "#bdbdbd")]
arms = ["A3", "A2", "A1"]
left = [0, 0, 0]
for key, lab, col in cats:
    vals = [N["arm_stg"][a].get(key, 0) for a in arms]
    ax.barh(range(3), vals, left=left, color=col, edgecolor="black", linewidth=0.4, label=lab)
    for i, v in enumerate(vals):
        if v >= 9:
            ax.text(left[i] + v / 2, i, str(v), ha="center", va="center", fontsize=7.5,
                    color="white" if key in ("exact", "silent") else "black")
    left = [l + v for l, v in zip(left, vals)]
ax.set_yticks(range(3)); ax.set_yticklabels(arms); ax.set_xlim(0, 222); ax.set_xlabel("Staging integrations (of 222 per arm)")
ax.legend(frameon=False, fontsize=7.5, ncol=2, loc="lower center", bbox_to_anchor=(0.45, 1.0), columnspacing=1.0,
          handlelength=1.2)
fig.tight_layout(pad=0.3); fig.savefig(os.path.join(OUT, "fig_outcomes_by_arm.pdf")); plt.close(fig)
print("figures written")
