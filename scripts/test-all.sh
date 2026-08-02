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
for tree in examples/refund-desk examples/answers-from-documents examples/patterns/*/; do
  [ -d "$tree" ] || continue
  cargo run --quiet -p pact-cli -- check "$tree" --deny-warnings
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
# The CLI has to be BUILT, not merely buildable. Forty-two adapter test files
# load the worked example through the real loader and skip themselves when the
# binary is absent — measured, nineteen tests skip — so a gate that ran them
# without it would report green over a suite that had quietly stopped checking
# the thing invariant P-1 is about. The `cargo run` above builds it; this is the
# assertion that it did.
if [ ! -x target/debug/pact ]; then
  echo "error: target/debug/pact is missing, and 44 test files read the worked" >&2
  echo "  example through it. Running the suite now would skip them silently." >&2
  echo "  fix: cargo build -p pact-cli" >&2
  exit 1
fi
cd adapters/python && uv run pytest tests/ -q
