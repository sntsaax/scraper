# Run full benchmark (PowerShell)
# Usage: open PowerShell in the repo root and run: .\scripts\run_benchmark.ps1

# Optional environment vars (uncomment and edit if needed):
# $env:ANTHROPIC_API_KEY = "your_key_here"
# $env:MAINTENANCE_HOURLY_SEK = "875"
# $env:MAINTENANCE_HOURS_PER_MONTH = "40"
# $env:EXCHANGE_RATE_SEK_TO_USD = "0.093"

python -m src.runner --runs 5 --monthly-runs 40 --sites mellby_gaard_careers datadog_all_jobs webflow_jobs fixture_marketing_jobs --scrapers autonomous semantic_reader rule_follower

# regenerate charts after the run finishes
python scripts/plot_benchmark_metrics.py
python scripts/plot_monthly_costs.py
