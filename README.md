# Thesis Benchmark

This project benchmarks three extraction strategies for dynamic job listings:

* a fixed-selector Playwright scraper,
* a semantic LLM-based extractor,
* an autonomous browser-agent style scraper.

The benchmark is profile-driven, so it can scale from the current Mellby Gård careers page to additional zero-shot site profiles without rewriting the runner.

Site profiles are loaded from `data/site_profiles.json` by default. Set `BENCHMARK_SITE_PROFILES` if you want to point to another profile file.

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

## Environment

The semantic scraper only runs when `ANTHROPIC_API_KEY` is set. Cost estimates can be enabled with optional environment variables:

* `BROWSER_RUNTIME_COST_PER_HOUR_USD`
* `ANTHROPIC_INPUT_COST_PER_1K_TOKENS`
* `ANTHROPIC_OUTPUT_COST_PER_1K_TOKENS`

