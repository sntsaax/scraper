import json
from pathlib import Path
import math
import matplotlib.pyplot as plt

SUMMARY = Path("data/results/benchmark_summary.json")
OUT = Path("data/results/metrics_overview.png")

if not SUMMARY.exists():
    print("No summary found at data/results/benchmark_summary.json. Run the benchmark first.")
    exit(1)

with open(SUMMARY, "r", encoding="utf-8") as f:
    data = json.load(f)

systems = data.get("systems", {})
keys = list(systems.keys())
labels = [f"{v.get('site')}\n{v.get('system')}" for k, v in systems.items()]

# gather metrics
extracted = [v.get('extracted_avg', 0.0) for v in systems.values()]
latency = [v.get('latency_avg', 0.0) for v in systems.values()]
cost = [v.get('cost_avg', 0.0) for v in systems.values()]
heuristic = [v.get('heuristic_quality_score', None) for v in systems.values()]
schema_valid_rate = [v.get('schema_valid_rate', 0.0) for v in systems.values()]
accuracy = [v.get('accuracy_avg', None) for v in systems.values()]

# Utility to plot bar with labels

def bar_labels(ax, bars, fmt="{:.2f}"):
    for bar in bars:
        h = bar.get_height()
        ax.annotate(fmt.format(h), xy=(bar.get_x() + bar.get_width() / 2, h),
                    xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=8)

# Prepare multi-plot
fig, axes = plt.subplots(2, 3, figsize=(18, 10))
plt.subplots_adjust(hspace=0.4, wspace=0.3)

# Extracted avg
ax = axes[0, 0]
bars = ax.bar(labels, extracted, color="#4C78A8")
ax.set_title("Avg Extracted Count")
ax.set_ylabel("Records")
ax.tick_params(axis='x', rotation=45)
bar_labels(ax, bars, "{:.1f}")

# Latency
ax = axes[0, 1]
bars = ax.bar(labels, latency, color="#F58518")
ax.set_title("Avg Latency (s)")
ax.set_ylabel("Seconds")
ax.tick_params(axis='x', rotation=45)
bar_labels(ax, bars, "{:.2f}")

# Cost per run
ax = axes[0, 2]
bars = ax.bar(labels, cost, color="#E45756")
ax.set_title("Avg Cost per Run (USD)")
ax.set_ylabel("USD")
ax.tick_params(axis='x', rotation=45)
bar_labels(ax, bars, "${:.4f}")

# Heuristic quality (N/A when absent)
ax = axes[1, 0]
heur_vals = [h if h is not None else 0.0 for h in heuristic]
bars = ax.bar(labels, heur_vals, color="#72B7B2")
ax.set_title("Heuristic Quality Score (unsupervised)")
ax.set_ylabel("Score (0-100)")
ax.tick_params(axis='x', rotation=45)
bar_labels(ax, bars, "{:.2f}")

# Schema valid rate
ax = axes[1, 1]
bars = ax.bar(labels, schema_valid_rate, color="#54A24B")
ax.set_title("Schema Valid Rate (%)")
ax.set_ylabel("Percent")
ax.tick_params(axis='x', rotation=45)
bar_labels(ax, bars, "{:.2f}%")

# Controlled accuracy (skip N/A)
ax = axes[1, 2]
acc_vals = [a if a is not None else math.nan for a in accuracy]
# For plotting, replace nan with 0 but mark ticks where nan
plot_vals = [0.0 if math.isnan(a) else a for a in acc_vals]
bars = ax.bar(labels, plot_vals, color=["#8A89A6" if not math.isnan(a) else "#CCCCCC" for a in acc_vals])
ax.set_title("Accuracy (controlled only)")
ax.set_ylabel("Percent")
ax.tick_params(axis='x', rotation=45)
for i, a in enumerate(acc_vals):
    if math.isnan(a):
        ax.annotate("N/A", xy=(i, 0.02), xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=8)
    else:
        ax.annotate(f"{a:.2f}%", xy=(i, a), xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=8)

plt.suptitle("Benchmark Metrics Overview")

OUT.parent.mkdir(parents=True, exist_ok=True)
plt.tight_layout(rect=[0, 0.03, 1, 0.95])
plt.savefig(OUT)
print(f"Saved overview chart to {OUT}")
