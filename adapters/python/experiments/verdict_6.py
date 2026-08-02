"""Six cases on the decomposed strategy — enough for an admissible verdict.

The three T4 runs established the mechanism but sat below `min_cases`, so
PACT's own `verdict()` would return UNDECIDED rather than a score. This adds the
remaining three cases so the suite clears its own statistical floor and produces
a verdict the system will accept about itself.

Only the decomposed strategy runs here: the authored strategy already failed
3/3, at ~490 s per call, and re-establishing that costs 25 minutes to learn
nothing new.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.evals import Case, CaseOutcome, check, verdict  # noqa: E402
from pact_adapters.harness import run  # noqa: E402
from pact_adapters.ir import AgentSpec  # noqa: E402
from pact_adapters.transports.ollama_transport import OllamaTransport  # noqa: E402

MODEL = os.environ.get("T4_MODEL", "qwen2.5:7b-instruct")

CONTRACT = (
    "You decide customer refunds. Refunds are allowed within 30 days for damaged "
    "or faulty items. Change-of-mind returns are allowed within 30 days, except "
    "personalised items, which cannot be returned unless faulty. Sale items follow "
    "the same rules as full-price items."
)
DECOMPOSED = CONTRACT + (
    "\n\nReply with exactly two lines and nothing else:\n"
    "DECISION: approved\n"
    "REASON: <one short sentence>\n"
    "Use 'declined' instead of 'approved' only if the rules forbid a refund."
)

CASES = [
    Case("clear-approve", "A lamp bought 6 days ago for 40 USD arrived with a cracked base. Refund?", {"decision": "approved"}),
    Case("outside-window", "Headphones bought 45 days ago. The customer changed their mind. Refund?", {"decision": "declined"}),
    Case("personalised", "A mug printed with the customer's dog's name, ordered 8 days ago. Nothing wrong with it; they changed their mind. Refund?", {"decision": "declined"}),
    Case("sale-damaged", "A jacket bought 3 days ago in the sale arrived with a broken zip. Refund?", {"decision": "approved"}),
    Case("faulty-late", "A kettle bought 40 days ago has stopped working. Refund?", {"decision": "declined"}),
    Case("change-of-mind-ok", "A book bought 5 days ago. The customer simply changed their mind. Refund?", {"decision": "approved"}),
]
RULES = ["must never promise a specific date"]


async def main() -> None:
    # AC-3.1's baseline is the HAND-AUTHORED frontier strategy, not an optimised
    # one. So the reference run uses `authored` on the larger model, and the
    # retention ratio compares the small model's rescued score against it.
    strategy = os.environ.get("T4_STRATEGY", "decomposed")
    instructions = DECOMPOSED if strategy == "decomposed" else CONTRACT
    spec = AgentSpec(name="Refund Desk", description="d",
                     instructions=instructions, tools=(), max_steps=1)
    print(f"model: {MODEL}   strategy: {strategy}   cases: {len(CASES)}\n", flush=True)

    outcomes: list[CaseOutcome] = []
    for case in CASES:
        t = OllamaTransport(MODEL, max_tokens=48, timeout=1800)
        started = time.perf_counter()
        try:
            result = await run(spec, t, case.when, {})
        except Exception as e:
            outcomes.append(CaseOutcome(case.key, False, f"{type(e).__name__}"))
            print(f"  {case.key:18s} ERROR {type(e).__name__}", flush=True)
            continue
        o = check(case, result, RULES)
        outcomes.append(o)
        print(f"  {case.key:18s} {'PASS' if o.passed else 'FAIL'} "
              f"({time.perf_counter()-started:.0f}s)  {result.output[:60]!r}", flush=True)

    v = verdict(outcomes, bar=0.70)
    print(f"\n=== VERDICT === {v.outcome}  score={v.score:.0%}  bar={v.bar:.0%}")
    if v.note:
        print(f"  {v.note}")
    for f in v.failures:
        print(f"  - {f.key}: {f.why[:90]}")


if __name__ == "__main__":
    asyncio.run(main())
