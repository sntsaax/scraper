"""Read data/results/benchmark_summary.json and print a human-readable summary to stdout.

Usage:
  python scripts/dump_summary_text.py > data/results/full_benchmark_report.txt
"""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "data" / "results" / "benchmark_summary.json"

def fmt_pct(v):
    try:
        return f"{v:.2f}%"
    except Exception:
        return str(v)

def main():
    if not SUMMARY.exists():
        print(f"Summary file not found: {SUMMARY}")
        sys.exit(1)

    with open(SUMMARY, "r", encoding="utf-8") as f:
        data = json.load(f)

    print("="*80)
    print("BENCHMARK SUMMARY")
    print("="*80)
    print(f"Generated at: {data.get('generated_at')}")
    print(f"Total run records aggregated: {data.get('results_count')}")
    print()

    systems = data.get("systems", {})
    for key in sorted(systems.keys()):
        s = systems[key]
        print(f"{key.upper()}:")
        print("-"*40)
        print(f"  Runs: {s.get('runs')}")
        print(f"  Evaluation mode: {s.get('evaluation_mode')}")
        print(f"  Ground truth labels: {s.get('ground_truth_count')}")
        print(f"  Extracted (avg): {s.get('extracted_avg')}")
        print(f"  Accuracy (avg): {s.get('accuracy_avg')}")
        print(f"  Latency (avg): {s.get('latency_avg')}s")
        print(f"  Cost (avg): ${s.get('cost_avg')}")
        print(f"  Schema valid rate: {fmt_pct(s.get('schema_valid_rate'))}")
        print(f"  Reliability: {s.get('reliability_score')}% (n={s.get('reliability_sample_size')}; {s.get('reliability_note')})")
        print()

    print("="*80)


if __name__ == '__main__':
    main()
