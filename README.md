# Thesis Benchmark

This project benchmarks three extraction strategies for dynamic job listings:

* a fixed-selector Playwright scraper,
* a semantic LLM-based extractor,
* an autonomous browser-agent style scraper.

The benchmark is profile-driven, so it can scale from the current Mellby Gård careers page to additional zero-shot site profiles without rewriting the runner. The default profile set now points at three live public job boards: Mellby Gård, Datadog, and Webflow.

Site profiles are loaded from `data/site_profiles.json` by default. Set `BENCHMARK_SITE_PROFILES` if you want to point to another profile file.

If you want to analyze a different live site without editing profile JSON, use the new single-URL mode:

```bash
python -m src.runner --site-url https://careers.datadoghq.com/all-jobs/ --site-name datadog_all_jobs --company-name Datadog
```

Pass `--item-selector`, `--title-selector`, and `--location-selector` when a site needs custom card selectors.

## Run

```bash
python -m src.runner
```

Optional CLI arguments:

```bash
python -m src.runner --runs 3 --sites mellby_gaard_careers --scrapers rule_follower autonomous
```

## Outputs

Results are written to `data/results/`:

* `benchmark_summary.csv`
* `benchmark_summary.json`
* per-run JSON logs

The JSON summary includes reliability, success rate, coverage stability, and latency stability for each site and scraper pair.

For correctness, the benchmark now reports field-level accuracy plus record-level precision, recall, and F1. A 100% score is still possible on a small deterministic fixture, but it only means that site was matched exactly. It should not be interpreted as generalization across sites.

## Environment

The semantic scraper only runs when `ANTHROPIC_API_KEY` is set. Cost estimates can be enabled with optional environment variables:

* `BROWSER_RUNTIME_COST_PER_HOUR_USD`
* `ANTHROPIC_INPUT_COST_PER_1K_TOKENS`
* `ANTHROPIC_OUTPUT_COST_PER_1K_TOKENS`

