#!/bin/sh
set -eu
mkdir -p /var/lib/strategylab/db /var/lib/strategylab/runs /var/lib/strategylab/data
chown appuser:appuser /var/lib/strategylab /var/lib/strategylab/db /var/lib/strategylab/runs /var/lib/strategylab/data
exec gosu appuser "$@"
