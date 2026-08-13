#!/usr/bin/env bash
# Everything, in one command. Runs fully offline (D17).
set -euo pipefail
cd "$(dirname "$0")/.."
echo "── Rust ──"
cargo test --quiet
cargo clippy --all-targets --quiet
# The RELEASE build too, and not for speed. `--all-targets` above builds with
# debug assertions ON, so anything `#[cfg(debug_assertions)]` gates is live there
# and its warnings never appear — `SpecSource::Unsafe` is deliberately
# unconstructible in a release binary, and the `dead_code` warning that follows
# from that was invisible to the gate until somebody ran `cargo install`. A
# warning nobody sees until they install the thing is register row C6's subject.
cargo clippy --release -p pact-cli --quiet -- -D warnings
echo "── CLI on every shipped tree ──"
# Every workspace this repository ships, under `--deny-warnings`. It was one
# tree, and the eight orchestration patterns beside it were checked by nothing —
# so a change that made `examples/patterns/quorum/` warn was found by whoever
# next opened it.
#
# `--deny-warnings` because a warning here means a shipped example is teaching
# somebody a shape the checker disagrees with, which is a different thing from a
# warning in a workspace somebody is halfway through writing.
#
# FOUND, not listed. This line spelled the trees out —
# `refund-desk answers-from-documents patterns/*/` — so a workspace added beside
# them was checked by nothing until somebody remembered to extend it, and the
# success criterion for that workspace was asserted by nothing at all. The golden
# set derives its agents from the tree for the same reason; a hand-written list
# is a scope somebody has to remember.
for spec in $(find examples -name workspace.yaml | sort); do
  cargo run --quiet -p pact-cli -- check "$(dirname "$spec")" --deny-warnings
done
echo "── TypeScript ──"
# 1238 lines of the "second, independent port" were never type-checked: there was
# no tsconfig, `typescript` was not a dependency, and `--experimental-strip-types`
# erases annotations without checking them. A type error survived everywhere
# except the two paths the two fixtures walk.
#
# `|| echo` neutralised `set -e`: any type error printed the install hint and
# exited 0, so the gate that exists to close TS-1 could not fail the build.
# Measured — `const _audit_probe: number = "not a number";` in harness.ts printed
# `error TS2322`, then `(skipped: ...)`, then exit 0. Gate on the TOOLCHAIN being
# there instead, so a missing install skips and a type error fails.
if [ -d adapters/typescript/node_modules ]; then
  (cd adapters/typescript && npx --no-install tsc --noEmit)
else
  echo "  (skipped: run \`npm install\` in adapters/typescript)"
fi
echo "── Adapters (7 targets: Pydantic AI, LangGraph, LangChain, AutoGen, OpenAI Agents, Anthropic, Vercel AI) ──"
# The CLI has to be BUILT, not merely buildable. Dozens of adapter test files
# load the worked example through the real loader and skip themselves when the
# binary is absent — the count is stated once, in the error below, because it is
# a measurement and two copies of it drift — so a gate that ran them
# without it would report green over a suite that had quietly stopped checking
# the thing invariant P-1 is about. The `cargo run` above builds it; this is the
# assertion that it did.
if [ ! -x target/debug/pact ]; then
  echo "error: target/debug/pact is missing, and 62 test files read the worked" >&2
  echo "  example through it. Running the suite now would skip them silently." >&2
  echo "  fix: cargo build -p pact-cli" >&2
  exit 1
fi
# And `node`, for exactly the reason above. The cross-port claim is the strongest
# thing this repository asserts, and every test that makes it drives
# `adapters/typescript/src/run-trace.ts` in a subprocess and SKIPS itself when
# that subprocess cannot start. Measured, with a `node` on PATH that exits 127:
# `1857 passed, 75 skipped` against `1945 passed, 7 skipped` — 68 tests stopped
# running and said so only in the skip list. Among them is the only assertion
# holding the second port's guard against a spend cap nothing can reach.
#
# The typecheck above gates on `node_modules` and this does not, deliberately:
# `--experimental-strip-types` needs no install, so a missing `node` is a missing
# runtime and not a missing dependency.
if ! command -v node >/dev/null 2>&1; then
  echo "error: node is not on PATH, and 68 adapter tests drive the second port" >&2
  echo "  through it. Running the suite now would skip them silently — including" >&2
  echo "  every cross-port comparison the portability claim rests on." >&2
  echo "  fix: install Node (>= 22, for --experimental-strip-types)" >&2
  exit 1
fi
cd adapters/python && uv run pytest tests/ -q
