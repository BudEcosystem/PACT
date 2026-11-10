"""Two lines the primitives round added, and the second port's honesty about them.

`docs/98-PRIMITIVES-ENGINEERING-PLAN.md` WP-16: every new agent key is either
honoured by the TypeScript port or reported on `RunResult.unenforced`. Two reach
it inside blocks it already reads, so neither is caught by the undeclared-key
check at the front door:

- `forks: yes` on a loop stage (WP-10). The Python harness starts each attempt
  from a copy of the conversation; this port runs every attempt on one
  conversation, so the attempts are not independent. Saying nothing would let
  three votes that are really one pass as three.
- `limits.unbounded: yes` (WP-3, law 2 option A). The Python harness sets no
  step ceiling for an owner who wrote it; this port still stops at its default.
  The generic "`limits.<key>` holds nothing on this run" sentence would be false
  of it — the port holds MORE than was written, not less — so it has its own.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

TS_DIR = Path(__file__).resolve().parents[3] / "adapters" / "typescript"


def _run(spec: dict) -> dict:
    out = subprocess.run(
        [
            "node",
            "--experimental-strip-types",
            "src/run-trace.ts",
            json.dumps(spec),
            json.dumps({"turns": [{"text": "done"}]}),
            "hello",
        ],
        cwd=TS_DIR,
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        pytest.skip(f"node/AI SDK unavailable: {out.stderr[-300:]}")
    return json.loads(out.stdout)


def _spec(**extra: object) -> dict:
    return {"name": "Desk", "instructions": "Answer.", "tools": [], "maxSteps": 3, **extra}


FORKING_LOOP = {
    "loop": "vote",
    "loops": {
        "vote": {
            "starts-at": "attempt",
            "steps": {
                "attempt": {"does": "answer", "forks": "yes", "then": {"answered": "done"}},
            },
        },
    },
}


def test_a_stage_that_forks_is_named_as_not_forked_here() -> None:
    said = _run(_spec(**FORKING_LOOP))["unenforced"]
    lines = [s for s in said if s.startswith("forks: yes")]
    assert len(lines) == 1, said
    assert "'attempt'" in lines[0] and "one conversation" in lines[0], lines[0]


def test_an_owners_unbounded_line_is_named_with_the_ceiling_still_held() -> None:
    said = _run(_spec(limits={"unbounded": "yes"}))["unenforced"]
    lines = [s for s in said if s.startswith("limits.unbounded")]
    assert len(lines) == 1, said
    assert "stops at 3 steps" in lines[0], lines[0]
    assert not any("limits.unbounded — read and not applied" in s for s in said), (
        "the generic sentence says the line holds nothing; this port holds more than written"
    )


def test_neither_line_is_reported_when_neither_is_written() -> None:
    said = _run(_spec())["unenforced"]
    assert not any(s.startswith(("forks:", "limits.unbounded")) for s in said), said


def test_a_shared_board_is_offered_refused_and_reported() -> None:
    """docs/98 WP-8. Python offers a team's shared memory as a tool named after it;
    this port offers the same name (so the model is shown the same tools on both),
    keeps no board, refuses a call to it, and says so."""
    out = subprocess.run(
        [
            "node", "--experimental-strip-types", "src/run-trace.ts",
            json.dumps(_spec(boards=[{"name": "findings", "description": "findings"}])),
            json.dumps({"turns": [
                {"text": "", "toolCalls": [{"name": "findings", "args": {"action": "read"}}]},
                {"text": "done"},
            ]}),
            "hello",
        ],
        cwd=TS_DIR, capture_output=True, text=True,
    )
    if out.returncode != 0:
        pytest.skip(f"node/AI SDK unavailable: {out.stderr[-300:]}")
    got = json.loads(out.stdout)
    assert any(s.startswith("remembers.findings: shared-with: the-team") for s in got["unenforced"]), got
    results = [r for step in got["trace"] for r in step.get("results", [])]
    assert any("is not kept on this runtime" in r for r in results), got["trace"]
