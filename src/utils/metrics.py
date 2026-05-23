from typing import List, Dict, Any, Optional
import json
from src.schemas import JobListing


def normalize_text(text: Optional[str]) -> str:
    """Normalize text for comparison: lowercase, strip whitespace."""
    if not text:
        return ""
    return text.lower().strip()


def calculate_field_accuracy(
    ground_truth: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
) -> float:
    """
    Calculate field-level accuracy.
    Matches records by URL, then compares title, company, location, and url.
    Unsupported extra records and missing ground-truth records count as errors.
    Returns percentage of correctly extracted fields over all expected fields.
    """
    if not ground_truth:
        return 0.0

    # Build lookup from ground truth by URL and match results one-to-one.
    gt_by_url = {gt.get("url", ""): gt for gt in ground_truth}
    result_buckets: Dict[str, List[Dict[str, Any]]] = {}
    for result in results:
        result_url = result.get("url", "")
        result_buckets.setdefault(result_url, []).append(result)

    expected_fields_per_record = 4  # title, company, location, url
    matched_fields = 0
    unmatched_extra_results = 0

    for gt_record in ground_truth:
        gt_url = gt_record.get("url", "")
        candidate_bucket = result_buckets.get(gt_url, [])

        if candidate_bucket:
            result_record = candidate_bucket.pop(0)
            for field in ["title", "company", "location", "url"]:
                gt_value = normalize_text(gt_record.get(field, ""))
                result_value = normalize_text(result_record.get(field, ""))
                if gt_value == result_value:
                    matched_fields += 1

    # Any remaining result records are unsupported extras and should reduce accuracy.
    for remaining_bucket in result_buckets.values():
        unmatched_extra_results += len(remaining_bucket)

    total_fields = (len(ground_truth) + unmatched_extra_results) * expected_fields_per_record
    if total_fields == 0:
        return 0.0

    return (matched_fields / total_fields) * 100


def calculate_record_coverage(
    ground_truth: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
) -> float:
    """Return the share of ground-truth records that were recovered at least once."""
    if not ground_truth:
        return 0.0

    gt_urls = {normalize_text(item.get("url")) for item in ground_truth if item.get("url")}
    result_urls = {normalize_text(item.get("url")) for item in results if item.get("url")}
    matched = len(gt_urls.intersection(result_urls))
    return (matched / len(gt_urls)) * 100 if gt_urls else 0.0


def count_unsupported_records(
    ground_truth: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
) -> int:
    """Count records whose URLs do not appear in the ground-truth set."""
    gt_urls = {normalize_text(item.get("url")) for item in ground_truth if item.get("url")}
    unsupported = 0
    for record in results:
        result_url = normalize_text(record.get("url"))
        if result_url and result_url not in gt_urls:
            unsupported += 1
    return unsupported


def validate_schema(data: Any) -> tuple[bool, Optional[str]]:
    """
    Validate that data conforms to JobListing schema.
    Returns (is_valid, error_message).
    """
    try:
        if isinstance(data, list):
            for item in data:
                JobListing(**item)
        else:
            JobListing(**data)
        return (True, None)
    except Exception as e:
        return (False, str(e))


def categorize_failure(
    raw_output: Optional[str],
    parsed_data: Optional[Any],
    schema_valid: bool,
    extraction_success: bool,
) -> str:
    """
    Categorize the type of failure encountered.
    Returns failure type: navigation_failure, extraction_failure, 
    parsing_error, schema_error, or 'success' if no failure.
    """
    if not extraction_success:
        return "extraction_failure"
    
    if raw_output is None or raw_output.strip() == "":
        return "extraction_failure"
    
    if parsed_data is None:
        return "parsing_error"
    
    if not schema_valid:
        return "schema_error"
    
    # Check for common issues
    if isinstance(parsed_data, list):
        for record in parsed_data:
            if isinstance(record, dict):
                # Check for missing required fields
                for required_field in ["title", "company", "location", "url"]:
                    if required_field not in record or record[required_field] is None:
                        return "missing_field"
    
    return "success"


def detect_unsupported_records(
    ground_truth_urls: set,
    results: List[Dict[str, Any]],
) -> List[int]:
    """
    Detect hallucinated records (URLs not in ground truth).
    Returns list of indices of hallucinated records.
    """
    hallucinated_indices = []
    for idx, result in enumerate(results):
        result_url = result.get("url", "")
        if result_url and result_url not in ground_truth_urls:
            hallucinated_indices.append(idx)
    return hallucinated_indices


def detect_hallucinations(
    ground_truth_urls: set,
    results: List[Dict[str, Any]],
) -> List[int]:
    return detect_unsupported_records(ground_truth_urls, results)


def detect_duplicates(results: List[Dict[str, Any]]) -> List[int]:
    """
    Detect duplicate records (same URL appears multiple times).
    Returns list of duplicate indices (keeps first occurrence, flags duplicates).
    """
    seen_urls = set()
    duplicate_indices = []
    
    for idx, result in enumerate(results):
        result_url = result.get("url", "")
        if result_url:
            if result_url in seen_urls:
                duplicate_indices.append(idx)
            else:
                seen_urls.add(result_url)
    
    return duplicate_indices


def format_benchmark_results(name: str, metrics: Dict) -> str:
    """Format metrics for display."""
    return (
        f"[{name}] Extracted: {metrics.get('extracted_count', 0)} | "
        f"Accuracy: {metrics.get('accuracy', 0):.2f}% | "
        f"Coverage: {metrics.get('record_coverage', 0):.2f}% | "
        f"Schema Valid: {metrics.get('schema_valid', False)} | "
        f"Latency: {metrics.get('latency_seconds', 0):.2f}s | "
        f"Cost: ${metrics.get('estimated_cost_usd', 0):.4f} | "
        f"Failure: {metrics.get('failure_type', 'unknown')}"
    )

