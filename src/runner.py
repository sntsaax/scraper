import json
import time
import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import uuid

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv()

from src.scrapers.rule_follower import RuleFollowerScraper
from src.scrapers.semantic_reader import SemanticReaderScraper
from src.scrapers.autonomous import AutonomousScraper
from src.utils.metrics import (
    calculate_field_accuracy,
    validate_schema,
    categorize_failure,
    detect_hallucinations,
    detect_duplicates,
    format_benchmark_results,
)
from src.utils.logger import get_logger

logger = get_logger("Runner")


# Ensure results directory exists
RESULTS_DIR = Path("data/results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Ground truth is read-only
GROUND_TRUTH_FILE = "data/ground_truth.json"

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

NUM_RUNS = 5


def load_ground_truth() -> List[Dict[str, Any]]:
    """Load and return the reference ground truth dataset."""
    try:
        with open(GROUND_TRUTH_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except Exception as e:
        logger.error(f"Failed to load ground truth: {e}")
        return []


def run_single_extraction(
    scraper_name: str,
    scraper,
    run_id: int,
    ground_truth: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Execute a single extraction run and collect metrics.
    Returns a dictionary with all metrics for this run.
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"[{scraper_name}] Run {run_id}/{NUM_RUNS}")
    logger.info(f"{'='*60}")

    run_uuid = str(uuid.uuid4())[:8]
    result_record = {
        "system": scraper_name,
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
        # Execute extraction and measure latency
        start_time = time.time()
        results_list = scraper.extract()
        latency = time.time() - start_time

        extraction_success = True
        result_record["latency_seconds"] = round(latency, 3)

        # Convert to dictionaries for metrics
        results_dicts = [job.model_dump(exclude_none=False) for job in results_list]
        parsed_data = results_dicts
        raw_output = json.dumps(results_dicts, indent=2, ensure_ascii=False)

        logger.info(f"Extraction succeeded in {latency:.2f}s")

    except Exception as e:
        logger.error(f"Extraction failed with exception: {e}")
        result_record["latency_seconds"] = -1.0
        extraction_success = False

    # Validate schema
    schema_valid = False
    if parsed_data is not None:
        schema_valid, schema_error = validate_schema(parsed_data)
        if not schema_valid:
            logger.warning(f"Schema validation failed: {schema_error}")
    result_record["schema_valid"] = schema_valid

    # Count extracted records
    extracted_count = len(results_list) if results_list else 0
    result_record["extracted_count"] = extracted_count
    logger.info(f"Extracted count: {extracted_count}")

    # Calculate field-level accuracy against ground truth
    if parsed_data and ground_truth:
        accuracy = calculate_field_accuracy(ground_truth, parsed_data)
        result_record["accuracy"] = round(accuracy, 2)
        logger.info(f"Field-level accuracy: {accuracy:.2f}%")
    else:
        result_record["accuracy"] = 0.0

    # Detect anomalies
    hallucinated_indices = []
    duplicate_indices = []

    if parsed_data and ground_truth:
        gt_urls = {gt.get("url", "") for gt in ground_truth if gt.get("url")}
        hallucinated_indices = detect_hallucinations(gt_urls, parsed_data)
        duplicate_indices = detect_duplicates(parsed_data)

        if hallucinated_indices:
            logger.warning(
                f"Hallucinated records (URLs not in ground truth): {len(hallucinated_indices)}"
            )
        if duplicate_indices:
            logger.warning(f"Duplicate records detected: {len(duplicate_indices)}")

    result_record["hallucinated_count"] = len(hallucinated_indices)
    result_record["duplicate_count"] = len(duplicate_indices)

    # Categorize failure type
    failure_type = categorize_failure(
        raw_output, parsed_data, schema_valid, extraction_success
    )
    result_record["failure_type"] = failure_type
    logger.info(f"Failure type: {failure_type}")

    # Log comprehensive metrics
    display_metrics = {
        "extracted_count": extracted_count,
        "accuracy": result_record["accuracy"],
        "schema_valid": schema_valid,
        "latency_seconds": result_record["latency_seconds"],
        "failure_type": failure_type,
    }
    logger.info(format_benchmark_results(scraper_name, display_metrics))

    # Save raw output and detailed log
    run_file = RESULTS_DIR / f"{scraper_name}_run_{run_id:02d}_{run_uuid}.json"
    try:
        detailed_log = {
            "metadata": result_record,
            "raw_output": parsed_data,
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
    Execute the complete benchmark: all scrapers, all runs.
    Returns list of all run records.
    """
    logger.info("\n" + "=" * 80)
    logger.info("THESIS BENCHMARK: Comparing Extraction Approaches")
    logger.info("=" * 80)
    logger.info(f"Ground truth records: {len(load_ground_truth())}")
    logger.info(f"Scrapers: {list(SCRAPERS.keys())}")
    logger.info(f"Runs per scraper: {NUM_RUNS}")
    logger.info("=" * 80 + "\n")

    ground_truth = load_ground_truth()
    all_results = []

    # Run each scraper NUM_RUNS times
    for scraper_name, scraper in SCRAPERS.items():
        logger.info(f"\n{'#'*80}")
        logger.info(f"# SCRAPER: {scraper_name.upper()}")
        logger.info(f"{'#'*80}\n")

        for run_id in range(1, NUM_RUNS + 1):
            try:
                run_record = run_single_extraction(
                    scraper_name, scraper, run_id, ground_truth
                )
                all_results.append(run_record)
            except Exception as e:
                logger.error(f"Run {run_id} crashed for {scraper_name}: {e}")
                all_results.append(
                    {
                        "system": scraper_name,
                        "run_id": run_id,
                        "timestamp": datetime.now().isoformat(),
                        "extracted_count": 0,
                        "accuracy": 0.0,
                        "schema_valid": False,
                        "latency_seconds": -1.0,
                        "failure_type": "extraction_failure",
                        "error": str(e),
                    }
                )

    return all_results


def save_summary_csv(all_results: List[Dict[str, Any]]) -> str:
    """
    Generate summary CSV with aggregated statistics.
    Returns path to CSV file.
    """
    csv_path = RESULTS_DIR / "benchmark_summary.csv"

    # CSV columns (matching thesis requirements)
    csv_columns = [
        "system",
        "run_id",
        "extracted_count",
        "accuracy",
        "schema_valid",
        "latency_seconds",
        "failure_type",
        "hallucinated_count",
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


def print_summary_report(all_results: List[Dict[str, Any]]) -> None:
    """Print a formatted summary report of the benchmark."""
    logger.info("\n" + "=" * 80)
    logger.info("BENCHMARK SUMMARY")
    logger.info("=" * 80)

    # Group by system
    by_system = {}
    for result in all_results:
        system = result.get("system")
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
        latencies = [r.get("latency_seconds", -1.0) for r in runs if r.get("latency_seconds", -1) > 0]
        schema_valids = [r.get("schema_valid", False) for r in runs]

        logger.info(f"  Runs: {len(runs)}")
        logger.info(f"  Extracted (avg/min/max): {sum(extracted_counts)/len(extracted_counts):.1f} / "
                   f"{min(extracted_counts)}/{max(extracted_counts)}")
        logger.info(f"  Accuracy (avg): {sum(accuracies)/len(accuracies):.2f}%")
        logger.info(f"  Schema Valid: {sum(schema_valids)}/{len(schema_valids)}")
        if latencies:
            logger.info(f"  Latency (avg/min/max): {sum(latencies)/len(latencies):.2f}s / "
                       f"{min(latencies):.2f}s / {max(latencies):.2f}s")

    logger.info("\n" + "=" * 80)


def main():
    """Main entry point for the benchmark runner."""
    logger.info(f"Starting benchmark at {datetime.now()}")

    # Run all benchmarks
    all_results = run_all_benchmarks()

    # Save results
    save_summary_csv(all_results)

    # Print summary
    print_summary_report(all_results)

    logger.info(f"\nBenchmark completed at {datetime.now()}")
    logger.info(f"Results saved to {RESULTS_DIR}")


if __name__ == "__main__":
    main()
