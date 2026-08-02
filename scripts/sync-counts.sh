#!/usr/bin/env bash
# Write the test counts into the four documents that state them.
#
# `test_the_headline_test_count_is_the_count.py` fails when README and the site
# disagree with what the suites actually run, and it is right to. But its fix
# line asks for the same two numbers to be typed into four files by hand, and a
# number copied by hand into four places is MAINTAINED — which is the thing this
# repository keeps finding to be wrong everywhere else. It was hand-synced five
# times in one day before this existed.
#
# The check still decides. This only computes what it asks for.
#
#     ./scripts/sync-counts.sh          # write them
#     ./scripts/sync-counts.sh --check  # print them, change nothing
set -euo pipefail
cd "$(dirname "$0")/.."

rust=$(cargo test --workspace -q 2>/dev/null \
  | grep -oE '^test result: ok\. [0-9]+' | grep -oE '[0-9]+' \
  | awk '{s+=$1} END {print s+0}')
adapter=$(cd adapters/python && uv run pytest tests/ -q --collect-only 2>/dev/null \
  | grep -oE '^[0-9]+ tests collected' | grep -oE '^[0-9]+' | head -1)
: "${adapter:=0}"
total=$((rust + adapter))

echo "rust=$rust adapter=$adapter total=$total"
[ "${1:-}" = "--check" ] && exit 0
[ "$total" -lt 100 ] && { echo "refusing: counted $total, which means a suite did not run" >&2; exit 1; }

python3 - "$rust" "$adapter" <<'PY'
import re, sys
rust, adapter = int(sys.argv[1]), int(sys.argv[2])
total = rust + adapter
edits = {
    "README.md": [
        (r"\*\*\d+ tests \(\d+ Rust \+ \d+ adapter\)",
         f"**{total} tests ({rust} Rust + {adapter} adapter)"),
        (r"# \d+ tests", f"# {total} tests"),
    ],
    "site-docs/status/verified.md": [
        (r"\| Rust tests \| \*\*\d+\*\* \|", f"| Rust tests | **{rust}** |"),
        (r"\| Adapter tests \| \*\*\d+\*\* \|", f"| Adapter tests | **{adapter}** |"),
        (r"\| Total \| \*\*[\d,]+\*\* \|", f"| Total | **{total:,}** |"),
    ],
    "site-docs/index.md": [
        (r"\| Tests \| \*\*[\d,]+\*\* — \d+ Rust, \d+ adapter \|",
         f"| Tests | **{total:,}** — {rust} Rust, {adapter} adapter |"),
    ],
}
for path, pairs in edits.items():
    text = open(path).read()
    for pattern, replacement in pairs:
        text, n = re.subn(pattern, replacement, text)
        if not n:
            raise SystemExit(f"error: {path} no longer contains {pattern!r}")
    open(path, "w").write(text)
print(f"wrote {total} into {len(edits)} documents")
PY
