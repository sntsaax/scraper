"""Aggregate existing per-run JSON logs and print full benchmark summary.

Usage: python scripts/aggregate_and_print_summary.py
This reads all JSON files in `data/results/`, extracts the `metadata` record
from each run log (or the top-level keys if metadata missing), rebuilds the
summary using functions from `src.runner`, saves benchmark_summary.json and
benchmark_summary.csv, and prints the summary report to stdout.
"""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data" / "results"

def collect_run_metadata():
    runs = []
    for p in sorted(RESULTS.glob("*.json")):
        if p.name == "benchmark_summary.json":
            continue
        try:
            with open(p, "r", encoding="utf-8") as f:
                obj = json.load(f)
        except Exception:
            continue

        # Prefer the 'metadata' field produced by the runner; otherwise, use top-level
        if isinstance(obj, dict) and "metadata" in obj and isinstance(obj["metadata"], dict):
            runs.append(obj["metadata"])
        elif isinstance(obj, dict):
            # Heuristic: if this JSON looks like a run record, use it
            candidate_keys = {"extracted_count", "latency_seconds", "estimated_cost_usd", "system", "site"}
            if candidate_keys & set(obj.keys()):
                runs.append(obj)

    return runs


def main():
    runs = collect_run_metadata()
    if not runs:
        print("No run metadata found in data/results/ to aggregate.")
        sys.exit(1)

    # Filter out records that lack both site and system to avoid 'unknown::' groups
    before = len(runs)
    runs = [r for r in runs if r.get("site") and r.get("system")]
    filtered = before - len(runs)
    if filtered:
        print(f"Filtered out {filtered} run(s) missing site/system metadata.")

    # Import runner utilities (ensure repo root is on path)
    sys.path.insert(0, str(ROOT))
    try:
        from src.runner import save_summary_json, save_summary_csv, print_summary_report
    except Exception as e:
        print(f"Failed to import runner utilities: {e}")
        sys.exit(1)

    # Save artifacts and print report
    save_summary_csv(runs)
    save_summary_json(runs)
    print_summary_report(runs)


if __name__ == "__main__":
    main()
