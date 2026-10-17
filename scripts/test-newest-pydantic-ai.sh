#!/usr/bin/env bash
# The importer and the exporter on the newest Pydantic AI 2.x, beside the locked one
# `test-all.sh` runs. Runs offline once installed (D17): the install is the only network.
#
# The lock holds Pydantic AI at the release the code was written against; a user may have
# any 2.x. So the parity suite (S4 finds every name a release adds that the registry has
# no row for, printing the row to write), the live reader's tests (a public read a release
# moves) and the private-name checks run again on the newest 2.x and harness. The `test`
# extra pins `pydantic-ai-harness` to the lock's release, so an override lifts both pins
# together, in a venv of its own: the lock is never touched.
set -euo pipefail
cd "$(dirname "$0")/.."
cargo build --quiet -p pact-cli
cd adapters/python
newest="${PACT_NEWEST_VENV:-.newest}"
uv venv --quiet --allow-existing "$newest"
printf 'pydantic-ai-slim>=2.54,<3\npydantic-ai-harness>=0.54,<1\n' > "$newest/overrides.txt"
uv pip install --quiet --python "$newest" -e ".[all,test]" --override "$newest/overrides.txt" --upgrade
"$newest/bin/python" -c "import importlib.metadata as m; print('── Pydantic AI', m.version('pydantic-ai-slim'), 'and pydantic-ai-harness', m.version('pydantic-ai-harness'), '──')"
"$newest/bin/python" -m pytest -q tests/test_parity.py \
  tests/test_a_live_agent_is_read_through_public_names_only.py \
  tests/test_the_loader_is_found_one_way.py
