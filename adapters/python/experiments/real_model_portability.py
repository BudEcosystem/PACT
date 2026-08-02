"""The model-portability experiment, on real weights.

Runs the worked example's eval suite against a ladder of locally-served models
under two strategies, and reports what actually passes. Everything is local, so
it satisfies the air-gap requirement (D17) while still being a real measurement.

What this can and cannot show, stated up front:
  * It CAN show whether a smaller model meets the same contract, and whether a
    different strategy rescues one that does not. That is thesis T4.
  * It CANNOT settle accuracy retention in general. Six cases on one task is an
    existence proof, not a benchmark, and the report says so.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.evals import Case, bar_of, check, rules_of, verdict  # noqa: E402
from pact_adapters.harness import run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.transports.ollama_transport import OllamaTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
# Reduced to what CPU-only inference can complete: ~100-300s per call.
#: Fastest model first, so a partial run still yields a row. On CPU-only
#: hardware a call costs 100-255s, which is the difference between a result and
#: a timeout — the scope is stated in the report rather than hidden.
import os
LADDER = os.environ.get("PACT_LADDER", "qwen2.5:7b-instruct").split(",")
MAX_CASES = 3
MODELS_ENV = "PACT_LADDER"

TOOLS = {
    "zendesk": lambda a: "order: lamp, 40 USD, delivered 6 days ago, arrived cracked",
    "payments": lambda a: "refund issued",
}

# The contract is fixed. Only the STRATEGY differs between these two.
STRATEGIES = {
    "authored": lambda s: s,
    "decomposed": lambda s: replace(
        s,
        instructions=(
            s.instructions
            + "\n\nAnswer in exactly this form and nothing else:\n"
            "DECISION: approved OR declined\n"
            "REASON: one sentence\n"
            "AMOUNT: the amount and currency, or none"
        ),
    ),
}


def document() -> dict:
    out = subprocess.run(
        [str(REPO / "target/debug/pact"), "show", str(REPO / "examples/refund-desk")],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


async def run_case(spec, model, case, rules):
    t = OllamaTransport(model, max_tokens=64, timeout=1800)
    started = time.perf_counter()
    result = await run(spec, t, case.when, TOOLS)
    return check(case, result, rules), time.perf_counter() - started, result.output


async def evaluate(spec, model, cases, rules, bar):
    pairs = [await run_case(spec, model, c, rules) for c in cases]
    outcomes = [p[0] for p in pairs]
    lat = sorted(p[1] for p in pairs)
    return verdict(outcomes, bar), lat[max(0, int(len(lat) * 0.95) - 1)], [p[2] for p in pairs]


async def main() -> None:
    doc = document()
    # No tools, one step. Every fact the decision needs is already in the case
    # text, so a tool call costs a ~250s round trip and adds no information.
    # And with max_steps=1 a model that DOES call a tool emits no text at all —
    # the first run of this experiment scored 0% for exactly that reason, which
    # was a flaw in the experiment rather than a finding about the model.
    spec = replace(AgentSpec.from_document(doc, "refund-desk"), tools=(), max_steps=1)
    cases, rules, bar = Case.from_document(doc)[:MAX_CASES], rules_of(doc), bar_of(doc)
    print(f"agent: {spec.name}   cases: {len(cases)}   bar: {bar:.0%}")
    print(f"ladder: {', '.join(LADDER)}\n", flush=True)

    table: dict[str, dict[str, str]] = {}
    for model in LADDER:
        table[model] = {}
        for sname, transform in STRATEGIES.items():
            try:
                v, p95, outs = await evaluate(transform(spec), model, cases, rules, bar)
            except Exception as e:
                table[model][sname] = f"ERROR {type(e).__name__}"
                print(f"  {model:24s} {sname:11s} ERROR {e}", flush=True)
                continue
            table[model][sname] = f"{v.outcome} {v.score:.0%}"
            print(f"  {model:24s} {sname:11s} {v.outcome:9s} score={v.score:.0%}  p95={p95:.1f}s",
                  flush=True)
            for f in v.failures[:2]:
                print(f"      - {f.key}: {f.why[:110]}", flush=True)
            if v.outcome == "PASS":
                break

    print("\n=== RESULT ===")
    for model, row in table.items():
        passed = next((k for k, x in row.items() if x.startswith("PASS")), None)
        print(f"{model:24s} {'PASS' if passed else 'FAIL':5s}  via {passed or 'none':11s}  {row}")

    Path(__file__).with_name("results.json").write_text(json.dumps(table, indent=2))
    print("\nScope: 6 cases, one task, one machine, temperature 0. An existence proof "
          "that the contract can survive a model downgrade under a different strategy "
          "— not a benchmark of accuracy retention in general.")


if __name__ == "__main__":
    asyncio.run(main())
