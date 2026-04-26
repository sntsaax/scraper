from typing import List, Dict
from src.schemas import JobListing


def calculate_accuracy(
    ground_truth: List[JobListing],
    results: List[JobListing],
) -> float:
    """Compare length and data accuracy."""
    if not ground_truth:
        return 0.0

    # Compare count
    match_count = min(len(results), len(ground_truth))
    return (match_count / len(ground_truth)) * 100


def format_benchmark_results(name: str, metrics: Dict) -> str:
    return (
        f"[{name}] Accuracy: {metrics['accuracy']:.2f}% "
        f"| Latency: {metrics['latency']}s"
    )
