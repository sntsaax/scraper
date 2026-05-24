import json
from pathlib import Path
import matplotlib.pyplot as plt

SUMMARY = Path("data/results/benchmark_summary.json")
OUT = Path("data/results/monthly_costs.png")

if not SUMMARY.exists():
    print("No summary found at data/results/benchmark_summary.json. Run the benchmark first.")
    exit(1)

with open(SUMMARY, "r", encoding="utf-8") as f:
    data = json.load(f)

systems = data.get("systems", {})
site_order = ["mellby_gaard_careers", "datadog_all_jobs", "webflow_jobs", "fixture_marketing_jobs"]
site_labels = {
    "mellby_gaard_careers": "Mellby Gård",
    "datadog_all_jobs": "Datadog",
    "webflow_jobs": "Webflow",
    "fixture_marketing_jobs": "Fixture benchmark",
}

ordered_items = sorted(
    systems.items(),
    key=lambda item: (
        site_order.index(item[1].get("site")) if item[1].get("site") in site_order else len(site_order),
        item[1].get("site", ""),
        item[1].get("system", ""),
    ),
)

labels = [f"{site_labels.get(info.get('site'), info.get('site'))}::{info.get('system')}" for _, info in ordered_items]
costs = [info.get("monthly_operational_cost_estimate_usd", 0.0) for _, info in ordered_items]

if not labels:
    print("No systems found in summary.")
    exit(1)

plt.figure(figsize=(10, 6))
bars = plt.bar(labels, costs, color="#4C78A8")
plt.xticks(rotation=45, ha="right")
plt.ylabel("Monthly operational cost (USD)")
plt.title("Estimated Monthly Operational Cost per System")

# annotate
for bar in bars:
    h = bar.get_height()
    plt.annotate(f"${h:.2f}", xy=(bar.get_x() + bar.get_width() / 2, h),
                 xytext=(0, 3), textcoords="offset points", ha='center', va='bottom')

plt.tight_layout()
OUT.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(OUT)
print(f"Saved monthly cost chart to {OUT}")
