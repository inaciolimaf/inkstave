#!/usr/bin/env bash
# Run a test stage and publish its wall clock as the `seconds` step output, and the
# budget job gates the slowest stage (`make budget`). Outside GitHub Actions it only prints the time.
#
#   scripts/measure_stage.sh make test-unit web-coverage
set -euo pipefail

start=$(date +%s)
"$@"
seconds=$(($(date +%s) - start))
echo "stage took ${seconds}s"
echo "seconds=${seconds}" >>"${GITHUB_OUTPUT:-/dev/null}"
