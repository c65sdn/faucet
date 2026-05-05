#!/bin/bash

set -euo pipefail

# Faucet's own code still depends on eventlet semantics (see faucet/faucet.py
# eventlet.monkey_patch and the .dead checks in valve_ryuapp/test_gauge), and
# os-ken 4.0 flipped the default hub from eventlet to native. Pin the hub
# back to eventlet for tests until those eventlet assumptions are removed.
export OSKEN_HUB_TYPE=eventlet

MINCOVERAGE=91

SCRIPTPATH=$(readlink -f "$0")
TESTDIR=$(dirname "${SCRIPTPATH}")
BASEDIR=$(readlink -f "${TESTDIR}/..")
PYTHONPATH=${BASEDIR}:${BASEDIR}/clib

unit_test_files=(${TESTDIR}/unit/*/test_*.py)

test_cmd="PYTHONPATH=${PYTHONPATH} coverage run --parallel-mode --source ${BASEDIR}/faucet/ -m unittest --verbose"

coverage erase
printf '%s\n' "${unit_test_files[@]}" | shuf | parallel --verbose --timeout 600 --delay 1 --halt now,fail=1 -j 4 "${test_cmd}"
coverage combine
coverage xml
coverage report -m --fail-under=${MINCOVERAGE}
