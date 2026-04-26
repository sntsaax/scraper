import json
import time
from src.scrapers.rule_follower import RuleFollowerScraper
from src.utils.metrics import calculate_accuracy, format_benchmark_results
from src.utils.logger import get_logger

logger = get_logger("Runner")


def run_benchmarks():
    scraper = RuleFollowerScraper()
    logger.info("Starting Rule-Follower benchmark...")

    # Load ground truth
    with open("data/ground_truth.json", "r", encoding="utf-8") as f:
        ground_truth_dicts = json.load(f)

    # Execute and time
    start = time.time()
    results = scraper.extract()
    latency = round(time.time() - start, 2)

    # Calculate metrics
    results_dicts = [job.model_dump() for job in results]
    accuracy = calculate_accuracy(ground_truth_dicts, results_dicts)

    # Log results
    metrics = {"accuracy": accuracy, "latency": latency}
    logger.info(format_benchmark_results("RuleFollower", metrics))

    # Save current run as ground truth (if refreshing)
    with open("data/ground_truth.json", "w", encoding="utf-8") as f:
        json.dump(results_dicts, f, indent=4, ensure_ascii=False)


if __name__ == "__main__":
    run_benchmarks()
