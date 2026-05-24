import json
from pathlib import Path
import math
import matplotlib.pyplot as plt

SUMMARY = Path("data/results/benchmark_summary.json")
OUT_DIR = Path("data/results")

if not SUMMARY.exists():
    print("No summary found at data/results/benchmark_summary.json. Run the benchmark first.")
    raise SystemExit(1)

with open(SUMMARY, "r", encoding="utf-8") as f:
    data = json.load(f)

systems = data.get("systems", {})
labels = [f"{v.get('site')} {v.get('system')}" for k, v in systems.items()]

extracted = [v.get('extracted_avg', 0.0) for v in systems.values()]
latency = [v.get('latency_avg', 0.0) for v in systems.values()]
cost = [v.get('cost_avg', 0.0) for v in systems.values()]

OUT_DIR.mkdir(parents=True, exist_ok=True)

def save_bar_chart(values, title, ylabel, fmt, out_name, colors=None):
    fig, ax = plt.subplots(figsize=(12, 6))
    bars = ax.bar(labels, values, color=colors or "#4C78A8")
    ax.set_title(title, fontsize=14)
    ax.set_ylabel(ylabel, fontsize=12)
    ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=10)
    ax.set_xlabel("")
    # annotate
    for bar, val in zip(bars, values):
        h = bar.get_height()
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            txt = "N/A"
        else:
            txt = fmt.format(val)
        ax.annotate(txt, xy=(bar.get_x() + bar.get_width() / 2, h), xytext=(0, 3),
                    textcoords="offset points", ha='center', va='bottom', fontsize=9)
    plt.tight_layout()
    path = OUT_DIR / out_name
    plt.savefig(path, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved {path}")


save_bar_chart(extracted,
               title="Average Extracted Record Count per System",
               ylabel="Records (avg)",
               fmt="{:.1f}",
               out_name="avg_extracted_count.png",
               colors="#4C78A8")

save_bar_chart(latency,
               title="Average Latency per System",
               ylabel="Latency (seconds)",
               fmt="{:.2f} s",
               out_name="avg_latency_seconds.png",
               colors="#F58518")

save_bar_chart(cost,
               title="Average Cost per Run (USD) per System",
               ylabel="Cost (USD)",
               fmt="${:.4f}",
               out_name="avg_cost_usd.png",
               colors="#E45756")

print("All single-metric charts generated in data/results/")
