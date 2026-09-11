#!/usr/bin/env bash
# Run the test suite in every .venv-* virtual environment of the project.
#
# Usage:
#   bash scripts/run_tests.sh            # every environment
#   bash scripts/run_tests.sh .venv-3.7  # only the given environment(s)
set -u

cd "$(dirname "$0")/.." || exit 1

if [ "$#" -gt 0 ]; then
    venvs="$*"
else
    venvs=$(ls -d .venv-*/ 2>/dev/null)
fi

if [ -z "$venvs" ]; then
    echo "没有找到 .venv-* 环境，请先创建，例如：" >&2
    echo "  C:/Python37/python.exe -m venv --without-pip .venv-3.7" >&2
    exit 1
fi

status=0
for venv in $venvs; do
    if [ -x "${venv}Scripts/python.exe" ]; then
        python="${venv}Scripts/python.exe"
    elif [ -x "${venv}bin/python" ]; then
        python="${venv}bin/python"
    else
        echo "跳过 ${venv}（找不到解释器）" >&2
        continue
    fi

    echo "=== $("$python" -V 2>&1) :: ${venv%/} ==="
    if ! "$python" scripts/run_tests.py; then
        status=1
    fi
    echo
done

exit $status
