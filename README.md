# Thesis Benchmark

<div align="center">

**A benchmark harness for dynamic job-site extraction, measured as a system rather than a script.**

Fixed selectors, semantic extraction, and autonomous browsing are evaluated side by side across fixture and live sites.

</div>

---

## Signal Board

| extracted count | latency | cost |
| --- | --- | --- |
| ![Average extracted count](data/results/avg_extracted_count.png) | ![Average latency](data/results/avg_latency_seconds.png) | ![Average cost](data/results/avg_cost_usd.png) |

These are the three final figures generated for the thesis version of the benchmark. They are the core visual summary of the current results set.

## What This Project Does

This repository benchmarks three extraction strategies for dynamic job listings:

* a fixed-selector Playwright scraper,
* a semantic LLM-based extractor,
* an autonomous browser-agent style scraper.

The runner is profile-driven, so the same code path can evaluate a deterministic fixture baseline and multiple live sites without changing the scraper implementation. The current profile set includes fixture data plus live sites such as Datadog, Webflow, and Mellby Gård.

## Visual Readout

The benchmark is designed to produce both raw run logs and compact thesis figures. The charts below are the primary visual layer of the final analysis.

```text
Extraction volume  ->  how much each strategy found on average
Latency            ->  how expensive each strategy is in time
Cost               ->  how expensive each strategy is in dollars
```

## How To Run

Run the full benchmark:

```bash
python -m src.runner
```

Run a focused subset:

```bash
python -m src.runner --runs 5 --sites mellby_gaard_careers --scrapers semantic_reader rule_follower autonomous
```

Use single-URL mode when you want to point the benchmark at a live site without editing profile JSON:

```bash
python -m src.runner --site-url https://careers.datadoghq.com/all-jobs/ --site-name datadog_all_jobs --company-name Datadog
```

If a site needs custom selectors, add `--item-selector`, `--title-selector`, and `--location-selector`.

## Outputs

Results are written to `data/results/`:

* `benchmark_summary.csv`
* `benchmark_summary.json`
* per-run JSON logs
* `avg_extracted_count.png`
* `avg_latency_seconds.png`
* `avg_cost_usd.png`

The JSON summary includes reliability, success rate, coverage stability, and latency stability for each site and scraper pair. The per-run logs preserve the detailed metadata behind each figure so the thesis narrative can be reproduced exactly.

## How To Read The Benchmark

Use two evaluation modes when interpreting the numbers:

* `controlled` means the site has manually validated ground truth, so accuracy, precision, recall, and F1 are meaningful.
* `live_analysis` means the site is a production target without labels, so the benchmark should be read as an operational robustness test rather than supervised scoring.

Reliability and stability become meaningful only when a scraper is run repeatedly. `--runs 1` is a smoke test; `--runs 5` or `--runs 10` is the right range for consistency claims.

## Environment

The semantic scraper runs when `ANTHROPIC_API_KEY` is set. Cost estimates can be enabled with optional environment variables:

* `BROWSER_RUNTIME_COST_PER_HOUR_USD`
* `ANTHROPIC_INPUT_COST_PER_1K_TOKENS`
* `ANTHROPIC_OUTPUT_COST_PER_1K_TOKENS`

## Notes

Site profiles are loaded from `data/site_profiles.json` by default. Set `BENCHMARK_SITE_PROFILES` if you want to point the runner at another profile file.

The final thesis workflow also includes helper scripts for generating the plots and rebuilding the summary from saved run logs. If you regenerate the benchmark, re-run the plot scripts so the figures stay aligned with the summary JSON.

