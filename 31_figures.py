"""A8: paper figures (static PNG, light mode, print) from results tables only (no recomputation).

Palette: dataviz reference categorical slots 1-3 (blue #2a78d6, orange #eb6834, aqua #1baf7a), which pass
the all-pairs CVD and normal-vision checks; neutral greys for context. One y-axis per panel; legends plus
selective direct labels.
  fig1_regret_vs_K.png          regret share vs budget K, cov60 and isolation objectives (base config)
  fig2_regret_by_config.png     regret of x_A (cov60, K20) across the 14 pre-registered configurations
  fig3_bias_ratios.png          A/B ratios of three outcomes across configurations (H2), log scale
  fig4_traveltime_curves.png    population-weighted CDF of normal travel time: A, B, ensemble mean
  fig5_a6_aucpr.png             A6 AUC-PR with 95 % intervals by model and evaluation
  fig6_map_categories_2022.png  village flood categories, 2022 base, layer B, 1 km rule
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _common import DATA, TABLES, FIGS, VID, log_env

log_env(__file__)
FIGS.mkdir(parents=True, exist_ok=True)
C = {"A": "#2a78d6", "B": "#eb6834", "ens": "#1baf7a"}
LAB = {"A": "Open data (A)", "B": "Open data + PPHI (B)", "ens": "Ensemble (truth proxy)"}
LS = {"A": ("-", "o"), "B": ("--", "s"), "ens": (":", "^")}     # pattern + colour (accessibility)
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({"font.size": 9, "font.family": "Arial", "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2,
                     "ytick.color": INK2, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
                     "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 150, "savefig.dpi": 600,
                     "savefig.bbox": "tight", "legend.frameon": False})
BASE = "2022_D3_T0.6_N200_K50"

# fig 1 ---------------------------------------------------------------------------------
R = pd.read_csv(TABLES / f"a7_{BASE}_regret.csv")
fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.9), sharey=True)
for ax, obj, title in zip(axes, ("cov60", "iso"), ("(a)", "(b)")):
    for a in ("A", "B", "ens"):
        d = R[(R.objective == obj) & (R.alloc == a)].sort_values("K")
        xpos = np.arange(len(d))                       # K = 5, 10, 20, 50 at even spacing
        ax.plot(xpos, d.regret_share, color=C[a], lw=2, ls=LS[a][0], marker=LS[a][1], ms=4)
        ax.fill_between(xpos, d.regret_lo95, d.regret_hi95, color=C[a], alpha=0.15, lw=0)
        if a == "A":                                   # only A is direct-labelled (B and ensemble overlap near 0)
            ax.annotate("Open data (A)", (xpos[-1], d.regret_share.iloc[-1]), xytext=(0, 8),
                        textcoords="offset points", color=INK2, fontsize=7.5, ha="center")
    ax.set_title(title, fontsize=9, color=INK, loc="left", fontweight="bold"); ax.set_xlabel("Budget K (protected road links)")
    ax.set_xticks(np.arange(len(d))); ax.set_xticklabels(d.K.astype(int).astype(str))
axes[0].set_ylabel("Regret (share of achievable benefit)")
axes[0].set_ylim(-0.02, 1.0)
fig.legend([plt.Line2D([], [], color=C[a], lw=2, ls=LS[a][0], marker=LS[a][1]) for a in C], [LAB[a] for a in C], loc="upper center",
           ncol=3, bbox_to_anchor=(0.5, 1.08), fontsize=8)
fig.savefig(FIGS / "fig1_regret_vs_K.png"); plt.close(fig)

# fig 2 ---------------------------------------------------------------------------------
Sx = pd.read_csv(TABLES / "a7_sensitivity_regret.csv")
d = Sx[(Sx.objective.isin(["cov60", "iso"])) & (Sx.alloc == "A") & (Sx.K.astype(str).isin(["20", "length"]))].copy()
order = d[d.objective == "cov60"].sort_values("regret_share")["cfg"].tolist()
nice = lambda c: (c.replace("_N200_K50", "").replace("2022_", "").replace("_", " ").replace("N1000 K100", "N=1000")
                  .replace("L27.975", "length budget").replace("D3 T0.6", "base").replace("emb", "embankment"))
fig, ax = plt.subplots(figsize=(6.4, 4.2))
for k, (obj, mk, col) in enumerate((("cov60", "o", C["A"]), ("iso", "s", INK2))):
    dd = d[d.objective == obj].set_index("cfg").loc[order]
    y = np.arange(len(order)) + (0.15 if k else -0.15)
    err = np.vstack([dd.regret_share - dd.regret_lo95, dd.regret_hi95 - dd.regret_share]).clip(min=0)
    ax.errorbar(dd.regret_share, y, xerr=np.nan_to_num(err), fmt=mk, color=col, ms=5, lw=1.5, capsize=0,
                label="Coverage within 60 min" if obj == "cov60" else "Isolation")
ax.set_yticks(np.arange(len(order))); ax.set_yticklabels([nice(c) for c in order], fontsize=8)
ax.set_xlabel("Regret of open-data targeting $x_A$ (share of achievable benefit, K = 20)")
ax.set_xlim(-0.02, 0.7); ax.legend(loc="lower right", fontsize=8)
fig.savefig(FIGS / "fig2_regret_by_config.png"); plt.close(fig)

# fig 3 ---------------------------------------------------------------------------------
H = pd.read_csv(TABLES / "a7_h2_by_config.csv")
H = H[~H.cfg.str.contains("_L|_N1000")]
names = {"cov60_shortfall": "Share not within 60 min", "added_ph_dedup": "Added person-hours",
         "isolated_dedup": "Isolated people"}
fig, ax = plt.subplots(figsize=(6.0, 2.6))
for i, (o, lab) in enumerate(names.items()):
    v = H[H.outcome == o]["ratio_A_B"]
    ax.scatter(v, np.full(len(v), i) + np.random.default_rng(1).uniform(-0.12, 0.12, len(v)), s=22,
               color=C["A"], alpha=0.8, linewidths=0)
    b = H[(H.outcome == o) & (H.cfg == BASE)]["ratio_A_B"].iloc[0]
    ax.scatter([b], [i], s=60, facecolors="none", edgecolors=INK, linewidths=1.2)
ax.axvline(1, color=INK2, lw=1)
ax.set_xscale("log"); ax.set_xticks([1, 2, 5, 10, 20]); ax.set_xticklabels(["1", "2", "5", "10", "20"])
ax.minorticks_off(); ax.set_yticks(range(3)); ax.set_yticklabels(names.values())
ax.set_xlabel("Open-data bias: ratio A / B (log scale; ring = base configuration)")
fig.savefig(FIGS / "fig3_bias_ratios.png"); plt.close(fig)

# fig 4 ---------------------------------------------------------------------------------
pop = pd.read_parquet(DATA / "village_population_alt.parquet", columns=[VID, "population"]).set_index(VID)["population"]
nt = pd.read_parquet(DATA / "a2_normal_times.parquet").set_index(VID)
VD = pd.read_parquet(DATA / "a4_village_distributions.parquet").query("config == 'normal'").set_index(VID)
fig, ax = plt.subplots(figsize=(5.2, 3.0))
for a, t in (("A", nt.min_any_A), ("B", nt.min_any_B), ("ens", VD.mean_min)):
    t = t.dropna(); w = pop.loc[t.index]; o = np.argsort(t.to_numpy())
    ax.plot(t.to_numpy()[o], np.cumsum(w.to_numpy()[o]) / w.sum(), color=C[a], lw=2, ls=LS[a][0], label=LAB[a])
ax.set_xlim(0, 120); ax.set_ylim(0, 1)
ax.set_xlabel("Travel time to nearest facility, normal roads (min)"); ax.set_ylabel("Share of population (RHAI weights)")
ax.legend(loc="lower right", fontsize=8)
fig.savefig(FIGS / "fig4_traveltime_curves.png"); plt.close(fig)

# fig 5 ---------------------------------------------------------------------------------
M = pd.read_csv(TABLES / "a6_metrics.csv")
fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.6), sharey=True)
mods = {"gbm": "Gradient boosting", "base_fac": "Distance to facility", "base_river": "Distance to river"}
for ax, sub, ttl in zip(axes, ("all", "excl_fringe"), ("(a)", "(b)")):
    for j, (ev, col) in enumerate((("2022_LODO_CV", INK2), ("2025_out_of_event", C["A"]))):
        dd = M[(M.subset == sub) & (M["eval"] == ev)].set_index("model").loc[list(mods)]
        y = np.arange(3) + (0.15 if j else -0.15)
        ax.errorbar(dd.auc_pr, y, xerr=np.vstack([dd.auc_pr - dd.auc_pr_lo95, dd.auc_pr_hi95 - dd.auc_pr]),
                    fmt="o" if j == 0 else "D", color=col, ms=5, lw=1.5, label="2022 (leave-district-out)" if j == 0 else "2025 (out-of-event)")
    ax.set_title(ttl, fontsize=9, loc="left", color=INK, fontweight="bold"); ax.set_xlabel("AUC-PR")
axes[0].set_yticks(range(3)); axes[0].set_yticklabels(mods.values())
fig.legend(*axes[0].get_legend_handles_labels(), loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.1), fontsize=8)
fig.savefig(FIGS / "fig5_a6_aucpr.png"); plt.close(fig)

# fig 6 ---------------------------------------------------------------------------------
import geopandas as gpd
import _routing as Rt
vm = pd.read_parquet(DATA / "village_master.parquet", columns=[VID, "lon", "lat"]).set_index(VID)
cat = pd.read_parquet(DATA / "a2_flood").query("event == '2022' and D == 3 and T == 0.6 and scenario == 'B'").set_index(VID)
nrm = pd.read_parquet(DATA / "a2_flood").query("event == 'normal' and scenario == 'B'").set_index(VID)["min_any_r1000"]
c = np.select([cat.no_road_r1000, cat.min_any_r1000.isna() & nrm.loc[cat.index].notna(),
               cat.min_any_r1000 - nrm.loc[cat.index] > 0.01], ["no_road", "isolated", "delayed"], "unaffected")
cat["cat"] = c
fig, ax = plt.subplots(figsize=(5.0, 5.6))
Rt.districts().boundary.plot(ax=ax, color=GRID, lw=0.6)
sty = {"unaffected": ("#c9c7c0", 3, "Unaffected"), "no_road": ("#8d8b84", 3, "No road within 1 km"),
       "delayed": (C["B"], 9, "Delayed"), "isolated": (C["A"], 12, "Newly isolated")}
for k, (col, s, lab) in sty.items():
    ids = cat.index[cat.cat == k]
    ax.scatter(vm.loc[ids, "lon"], vm.loc[ids, "lat"], s=s, color=col, linewidths=0, label=f"{lab} ({len(ids):,})")
ax.set_aspect("equal"); ax.grid(False); ax.set_xticks([]); ax.set_yticks([])
for s in ax.spines.values():
    s.set_visible(False)
ax.legend(loc="lower left", fontsize=7.5, markerscale=1.5)
fig.savefig(FIGS / "fig6_map_categories_2022.png"); plt.close(fig)
print("figures written:", sorted(p.name for p in FIGS.glob("fig*.png")))
