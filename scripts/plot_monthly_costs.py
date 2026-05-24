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
labels = []
costs = []
for key, info in systems.items():
    labels.append(f"{info.get('site')}::{info.get('system')}")
    costs.append(info.get("monthly_operational_cost_estimate_usd", 0.0))

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
