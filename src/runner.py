import argparse
import json
import time
import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Sequence
import uuid

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv()

from src.scrapers.rule_follower import RuleFollowerScraper
from src.scrapers.semantic_reader import SemanticReaderScraper
from src.scrapers.autonomous import AutonomousScraper
from src.benchmark_profile import SiteProfile, load_site_profiles
from src.utils.metrics import (
    calculate_field_accuracy,
    calculate_record_coverage,
    calculate_record_match_summary,
    calculate_reliability_summary,
    validate_schema,
    categorize_failure,
    count_unsupported_records,
    detect_unsupported_records,
    detect_duplicates,
    format_benchmark_results,
)
from src.utils.logger import get_logger

logger = get_logger("Runner")


# Ensure results directory exists
RESULTS_DIR = Path("data/results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Initialize scrapers
_scrapers_dict = {}
for name, scraper_class in [
    ("rule_follower", RuleFollowerScraper),
    ("semantic_reader", SemanticReaderScraper),
    ("autonomous", AutonomousScraper),
]:
    try:
        scraper = scraper_class()
        # Check if it's available (relevant for optional scrapers)
        if hasattr(scraper, 'available') and not scraper.available:
            logger.warning(f"Scraper '{name}' is not available, skipping")
        else:
            _scrapers_dict[name] = scraper
    except Exception as e:
        logger.warning(f"Failed to initialize scraper '{name}': {e}")

SCRAPERS = _scrapers_dict

NUM_RUNS = int(os.getenv("NUM_RUNS", "5"))


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the thesis benchmark suite.")
    parser.add_argument(
        "--runs",
        type=int,
        default=NUM_RUNS,
        help="Number of runs per scraper and site.",
    )
    parser.add_argument(
        "--sites",
        nargs="*",
        default=[],
        help="Optional subset of site profile names to benchmark.",
    )
    parser.add_argument(
        "--scrapers",
        nargs="*",
        default=[],
        help="Optional subset of scraper names to benchmark.",
    )
    return parser.parse_args(argv)


def load_ground_truth(ground_truth_file: str) -> List[Dict[str, Any]]:
    """Load and return the reference ground truth dataset for one site."""
    try:
        with open(ground_truth_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except Exception as e:
        logger.error(f"Failed to load ground truth from {ground_truth_file}: {e}")
        return []


def estimate_cost_usd(scraper_name: str, run_metrics: Dict[str, Any], latency_seconds: float) -> Dict[str, Any]:
    """Estimate run cost using environment-configured rates."""
    browser_rate = float(os.getenv("BROWSER_RUNTIME_COST_PER_HOUR_USD", "0"))
    input_rate = float(os.getenv("ANTHROPIC_INPUT_COST_PER_1K_TOKENS", "0"))
    output_rate = float(os.getenv("ANTHROPIC_OUTPUT_COST_PER_1K_TOKENS", "0"))

    input_tokens = int(run_metrics.get("input_tokens", 0) or 0)
    output_tokens = int(run_metrics.get("output_tokens", 0) or 0)

    token_cost = ((input_tokens / 1000.0) * input_rate) + ((output_tokens / 1000.0) * output_rate)
    browser_cost = (max(latency_seconds, 0.0) / 3600.0) * browser_rate
    estimated_cost = token_cost + browser_cost

    return {
        "estimated_cost_usd": round(estimated_cost, 6),
        "cost_model": "env_rate" if (browser_rate or input_rate or output_rate) else "unconfigured",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "scraper_cost_profile": scraper_name,
    }


def select_site_profiles(site_profiles: List[SiteProfile], allowed_names: Sequence[str]) -> List[SiteProfile]:
    if not allowed_names:
        return site_profiles
    allowed = {name.strip() for name in allowed_names if name.strip()}
    return [profile for profile in site_profiles if profile.name in allowed]


def select_scrapers(scrapers: Dict[str, Any], allowed_names: Sequence[str]) -> Dict[str, Any]:
    if not allowed_names:
        return scrapers
    allowed = {name.strip() for name in allowed_names if name.strip()}
    return {name: scraper for name, scraper in scrapers.items() if name in allowed}


def run_single_extraction(
    scraper_name: str,
    scraper,
    site: SiteProfile,
    run_id: int,
    ground_truth: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Execute a single extraction run and collect metrics.
    Returns a dictionary with all metrics for this run.
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"[{site.name} | {scraper_name}] Run {run_id}/{NUM_RUNS}")
    logger.info(f"{'='*60}")

    run_uuid = str(uuid.uuid4())[:8]
    result_record = {
        "system": scraper_name,
        "site": site.name,
        "site_url": site.url,
        "benchmark_url": site.benchmark_url(),
        "run_id": run_id,
        "uuid": run_uuid,
        "timestamp": datetime.now().isoformat(),
    }

    # Track extraction success
    extraction_success = False
    raw_output = None
    parsed_data = None
    results_list = []

    try:
        start_time = time.time()
        results_list = scraper.extract(site)
        latency = time.time() - start_time

        extraction_success = True
        result_record["latency_seconds"] = round(latency, 3)

        results_dicts = [job.model_dump(exclude_none=False) for job in results_list]
        parsed_data = results_dicts
        raw_output = json.dumps(results_dicts, indent=2, ensure_ascii=False)

        logger.info(f"Extraction succeeded in {latency:.2f}s")

    except Exception as e:
        logger.error(f"Extraction failed with exception: {e}")
        result_record["latency_seconds"] = -1.0
        extraction_success = False
        run_metrics = {}

    run_metrics = getattr(scraper, "get_run_metrics", lambda: {})()
    cost_metrics = estimate_cost_usd(scraper_name, run_metrics, result_record.get("latency_seconds", 0.0))
    result_record.update(cost_metrics)
    result_record["site_expected_records"] = site.expected_record_count if site.expected_record_count is not None else ""
    result_record["site_ground_truth_file"] = site.ground_truth_file

    schema_valid = False
    if parsed_data is not None:
        schema_valid, schema_error = validate_schema(parsed_data)
        if not schema_valid:
            logger.warning(f"Schema validation failed: {schema_error}")
    result_record["schema_valid"] = schema_valid

    extracted_count = len(results_list) if results_list else 0
    result_record["extracted_count"] = extracted_count
    logger.info(f"Extracted count: {extracted_count}")

    if parsed_data and ground_truth:
        accuracy = calculate_field_accuracy(ground_truth, parsed_data)
        record_summary = calculate_record_match_summary(ground_truth, parsed_data)
        result_record["accuracy"] = round(accuracy, 2)
        result_record["record_coverage"] = round(calculate_record_coverage(ground_truth, parsed_data), 2)
        result_record.update(record_summary)
        logger.info(f"Field-level accuracy: {accuracy:.2f}%")
    else:
        result_record["accuracy"] = 0.0
        result_record["record_coverage"] = 0.0
        result_record["record_precision"] = 0.0
        result_record["record_recall"] = 0.0
        result_record["record_f1"] = 0.0
        result_record["exact_record_matches"] = 0.0

    unsupported_indices = []
    duplicate_indices = []

    if parsed_data and ground_truth:
        gt_urls = {gt.get("url", "") for gt in ground_truth if gt.get("url")}
        unsupported_indices = detect_unsupported_records(gt_urls, parsed_data)
        duplicate_indices = detect_duplicates(parsed_data)

        if unsupported_indices:
            logger.warning(
                f"Unsupported records (URLs not in ground truth): {len(unsupported_indices)}"
            )
        if duplicate_indices:
            logger.warning(f"Duplicate records detected: {len(duplicate_indices)}")

    result_record["unsupported_record_count"] = len(unsupported_indices)
    result_record["duplicate_count"] = len(duplicate_indices)
    result_record["unsupported_record_count_from_gt"] = count_unsupported_records(
        ground_truth, parsed_data or []
    )

    failure_type = categorize_failure(
        raw_output, parsed_data, schema_valid, extraction_success
    )
    result_record["failure_type"] = failure_type
    logger.info(f"Failure type: {failure_type}")

    display_metrics = {
        "extracted_count": extracted_count,
        "accuracy": result_record["accuracy"],
        "record_f1": result_record["record_f1"],
        "record_coverage": result_record["record_coverage"],
        "schema_valid": schema_valid,
        "latency_seconds": result_record["latency_seconds"],
        "estimated_cost_usd": result_record["estimated_cost_usd"],
        "failure_type": failure_type,
    }
    logger.info(format_benchmark_results(scraper_name, display_metrics))

    run_file = RESULTS_DIR / f"{site.name}_{scraper_name}_run_{run_id:02d}_{run_uuid}.json"
    try:
        detailed_log = {
            "metadata": result_record,
            "raw_output": parsed_data,
            "scraper_metrics": run_metrics,
            "ground_truth_sample": ground_truth[:3] if ground_truth else [],
        }
        with open(run_file, "w", encoding="utf-8") as f:
            json.dump(detailed_log, f, indent=2, ensure_ascii=False)
        logger.info(f"Run log saved to {run_file.name}")
    except Exception as e:
        logger.error(f"Failed to save run log: {e}")

    return result_record


def run_all_benchmarks() -> List[Dict[str, Any]]:
    """
    Execute the complete benchmark: all sites, all scrapers, all runs.
    Returns list of all run records.
    """
    logger.info("\n" + "=" * 80)
    logger.info("THESIS BENCHMARK: Comparing Extraction Approaches")
    logger.info("=" * 80)
    site_profiles = load_site_profiles()
    logger.info(f"Sites: {[site.name for site in site_profiles]}")
    logger.info(f"Scrapers: {list(SCRAPERS.keys())}")
    logger.info(f"Runs per scraper: {NUM_RUNS}")
    logger.info("=" * 80 + "\n")

    all_results = []

    for site in site_profiles:
        ground_truth = load_ground_truth(site.ground_truth_file)
        logger.info(f"\n{'#'*80}")
        logger.info(f"# SITE: {site.name.upper()}")
        logger.info(f"# GROUND TRUTH RECORDS: {len(ground_truth)}")
        logger.info(f"{'#'*80}\n")

        for scraper_name, scraper in SCRAPERS.items():
            logger.info(f"\n{'#'*80}")
            logger.info(f"# SCRAPER: {scraper_name.upper()}")
            logger.info(f"{'#'*80}\n")

            for run_id in range(1, NUM_RUNS + 1):
                try:
                    run_record = run_single_extraction(
                        scraper_name, scraper, site, run_id, ground_truth
                    )
                    all_results.append(run_record)
                except Exception as e:
                    logger.error(f"Run {run_id} crashed for {scraper_name}: {e}")
                    all_results.append(
                        {
                            "system": scraper_name,
                            "site": site.name,
                            "site_url": site.url,
                            "benchmark_url": site.benchmark_url(),
                            "run_id": run_id,
                            "timestamp": datetime.now().isoformat(),
                            "extracted_count": 0,
                            "accuracy": 0.0,
                            "record_coverage": 0.0,
                            "schema_valid": False,
                            "latency_seconds": -1.0,
                            "estimated_cost_usd": 0.0,
                            "cost_model": "unconfigured",
                            "failure_type": "extraction_failure",
                            "error": str(e),
                        }
                    )

    return all_results


def build_summary(all_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for result in all_results:
        key = f"{result.get('site', 'unknown')}::{result.get('system', 'unknown')}"
        grouped.setdefault(
            key,
            {
                "site": result.get("site", "unknown"),
                "system": result.get("system", "unknown"),
                "runs": 0,
                "accuracy_avg": 0.0,
                "record_precision_avg": 0.0,
                "record_recall_avg": 0.0,
                "record_f1_avg": 0.0,
                "coverage_avg": 0.0,
                "latency_avg": 0.0,
                "cost_avg": 0.0,
                "schema_valid_rate": 0.0,
                "extracted_avg": 0.0,
                "reliability_score": 0.0,
                "success_rate": 0.0,
                "count_stability": 0.0,
                "coverage_stability": 0.0,
                "latency_stability": 0.0,
            },
        )

    for key, payload in grouped.items():
        runs = [result for result in all_results if f"{result.get('site', 'unknown')}::{result.get('system', 'unknown')}" == key]
        payload["runs"] = len(runs)
        payload["accuracy_avg"] = round(sum(item.get("accuracy", 0.0) for item in runs) / len(runs), 2) if runs else 0.0
        payload["record_precision_avg"] = round(sum(item.get("record_precision", 0.0) for item in runs) / len(runs), 2) if runs else 0.0
        payload["record_recall_avg"] = round(sum(item.get("record_recall", 0.0) for item in runs) / len(runs), 2) if runs else 0.0
        payload["record_f1_avg"] = round(sum(item.get("record_f1", 0.0) for item in runs) / len(runs), 2) if runs else 0.0
        payload["coverage_avg"] = round(sum(item.get("record_coverage", 0.0) for item in runs) / len(runs), 2) if runs else 0.0
        positive_latencies = [item.get("latency_seconds", 0.0) for item in runs if item.get("latency_seconds", -1) > 0]
        payload["latency_avg"] = round(sum(positive_latencies) / len(positive_latencies), 2) if positive_latencies else 0.0
        payload["cost_avg"] = round(sum(item.get("estimated_cost_usd", 0.0) for item in runs) / len(runs), 6) if runs else 0.0
        payload["schema_valid_rate"] = round(sum(1 for item in runs if item.get("schema_valid", False)) / len(runs) * 100, 2) if runs else 0.0
        payload["extracted_avg"] = round(sum(item.get("extracted_count", 0) for item in runs) / len(runs), 2) if runs else 0.0
        reliability = calculate_reliability_summary(runs)
        payload["reliability_score"] = reliability["reliability_score"]
        payload["success_rate"] = reliability["success_rate"]
        payload["count_stability"] = reliability["count_stability"]
        payload["coverage_stability"] = reliability["coverage_stability"]
        payload["latency_stability"] = reliability["latency_stability"]

    return {
        "generated_at": datetime.now().isoformat(),
        "results_count": len(all_results),
        "systems": grouped,
    }


def save_summary_csv(all_results: List[Dict[str, Any]]) -> str:
    """
    Generate summary CSV with aggregated statistics.
    Returns path to CSV file.
    """
    csv_path = RESULTS_DIR / "benchmark_summary.csv"

    # CSV columns (matching thesis requirements)
    csv_columns = [
        "system",
        "site",
        "site_url",
        "benchmark_url",
        "run_id",
        "extracted_count",
        "accuracy",
        "record_precision",
        "record_recall",
        "record_f1",
        "record_coverage",
        "schema_valid",
        "latency_seconds",
        "estimated_cost_usd",
        "cost_model",
        "failure_type",
        "unsupported_record_count",
        "unsupported_record_count_from_gt",
        "duplicate_count",
        "timestamp",
    ]

    try:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=csv_columns)
            writer.writeheader()

            for result in all_results:
                # Filter to only CSV columns, use defaults for missing
                row = {col: result.get(col, "") for col in csv_columns}
                writer.writerow(row)

        logger.info(f"\nSummary CSV saved to {csv_path}")
        return str(csv_path)

    except Exception as e:
        logger.error(f"Failed to save summary CSV: {e}")
        return ""


def save_summary_json(all_results: List[Dict[str, Any]]) -> str:
    """Write a compact aggregated summary for thesis tables and plots."""
    json_path = RESULTS_DIR / "benchmark_summary.json"
    try:
        with open(json_path, "w", encoding="utf-8") as handle:
            json.dump(build_summary(all_results), handle, indent=2, ensure_ascii=False)
        logger.info(f"Summary JSON saved to {json_path}")
        return str(json_path)
    except Exception as e:
        logger.error(f"Failed to save summary JSON: {e}")
        return ""


def print_summary_report(all_results: List[Dict[str, Any]]) -> None:
    """Print a formatted summary report of the benchmark."""
    logger.info("\n" + "=" * 80)
    logger.info("BENCHMARK SUMMARY")
    logger.info("=" * 80)

    # Group by site and system
    by_system = {}
    for result in all_results:
        system = f"{result.get('site', 'unknown')}::{result.get('system')}"
        if system not in by_system:
            by_system[system] = []
        by_system[system].append(result)

    # Print stats per system
    for system in sorted(by_system.keys()):
        runs = by_system[system]
        logger.info(f"\n{system.upper()}:")
        logger.info("-" * 40)

        extracted_counts = [r.get("extracted_count", 0) for r in runs]
        accuracies = [r.get("accuracy", 0.0) for r in runs]
        precisions = [r.get("record_precision", 0.0) for r in runs]
        recalls = [r.get("record_recall", 0.0) for r in runs]
        f1_scores = [r.get("record_f1", 0.0) for r in runs]
        coverages = [r.get("record_coverage", 0.0) for r in runs]
        latencies = [r.get("latency_seconds", -1.0) for r in runs if r.get("latency_seconds", -1) > 0]
        schema_valids = [r.get("schema_valid", False) for r in runs]
        costs = [r.get("estimated_cost_usd", 0.0) for r in runs]

        logger.info(f"  Runs: {len(runs)}")
        logger.info(f"  Extracted (avg/min/max): {sum(extracted_counts)/len(extracted_counts):.1f} / "
                   f"{min(extracted_counts)}/{max(extracted_counts)}")
        logger.info(f"  Accuracy (avg): {sum(accuracies)/len(accuracies):.2f}%")
        logger.info(f"  Precision (avg): {sum(precisions)/len(precisions):.2f}%")
        logger.info(f"  Recall (avg): {sum(recalls)/len(recalls):.2f}%")
        logger.info(f"  F1 (avg): {sum(f1_scores)/len(f1_scores):.2f}%")
        logger.info(f"  Coverage (avg): {sum(coverages)/len(coverages):.2f}%")
        logger.info(f"  Schema Valid: {sum(schema_valids)}/{len(schema_valids)}")
        reliability = calculate_reliability_summary(runs)
        logger.info(f"  Reliability: {reliability['reliability_score']:.2f}%")
        logger.info(f"  Success Rate: {reliability['success_rate']:.2f}%")
        logger.info(f"  Cost (avg): ${sum(costs)/len(costs):.4f}")
        if latencies:
            logger.info(f"  Latency (avg/min/max): {sum(latencies)/len(latencies):.2f}s / "
                       f"{min(latencies):.2f}s / {max(latencies):.2f}s")

    logger.info("\n" + "=" * 80)


def main(argv: Optional[Sequence[str]] = None):
    """Main entry point for the benchmark runner."""
    args = parse_args(argv)
    logger.info(f"Starting benchmark at {datetime.now()}")

    site_profiles = select_site_profiles(load_site_profiles(), args.sites)
    scrapers = select_scrapers(SCRAPERS, args.scrapers)

    global NUM_RUNS
    NUM_RUNS = max(1, args.runs)

    all_results = []
    logger.info(f"Selected sites: {[site.name for site in site_profiles]}")
    logger.info(f"Selected scrapers: {list(scrapers.keys())}")
    logger.info(f"Selected runs: {NUM_RUNS}")

    for site in site_profiles:
        ground_truth = load_ground_truth(site.ground_truth_file)
        logger.info(f"Loaded {len(ground_truth)} ground truth records for {site.name}")

        for scraper_name, scraper in scrapers.items():
            for run_id in range(1, NUM_RUNS + 1):
                try:
                    all_results.append(
                        run_single_extraction(scraper_name, scraper, site, run_id, ground_truth)
                    )
                except Exception as e:
                    logger.error(f"Run {run_id} crashed for {scraper_name}: {e}")
                    all_results.append(
                        {
                            "system": scraper_name,
                            "site": site.name,
                            "site_url": site.url,
                            "run_id": run_id,
                            "timestamp": datetime.now().isoformat(),
                            "extracted_count": 0,
                            "accuracy": 0.0,
                            "record_coverage": 0.0,
                            "schema_valid": False,
                            "latency_seconds": -1.0,
                            "estimated_cost_usd": 0.0,
                            "cost_model": "unconfigured",
                            "failure_type": "extraction_failure",
                            "error": str(e),
                        }
                    )

    save_summary_csv(all_results)
    save_summary_json(all_results)

    print_summary_report(all_results)

    logger.info(f"\nBenchmark completed at {datetime.now()}")
    logger.info(f"Results saved to {RESULTS_DIR}")


if __name__ == "__main__":
    main()
