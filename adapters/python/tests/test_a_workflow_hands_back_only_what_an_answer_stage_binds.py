"""A workflow hands back what an `answer` stage bound, and nothing where it reached none.

`run_workflow` handed back the last stage's own record when no `answer` stage
ran: a called agent's whole answer, or a `decide`'s `{label, by}`. That is what
a BODY hands the stage that holds it — one item of a `for each`, one round of a
`repeat` — and it is not what a workflow said it gives. The rule already
written down (CHANGELOG, 12 November) is that a workflow which hands back
nothing answers with an empty record; a shared case that ended on a `decide`
is how the reference was found not to keep it.

Beside it, what a `decide` records of itself: `.label`, `.decided-by` and
`.answered-by` — the names the specification gives a stage — and a written
rule's `because:` in the run's "why this path", not in the record a binding
reads.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters.ir import WorkflowSpec  # noqa: E402
from pact_adapters.workflow_runtime import Callers, run_workflow  # noqa: E402
from trees import shown  # noqa: E402

WORKSPACE = """\
workspace "Notes"
  description: A note is looked at, and sometimes filed.

agent looker
  description: Says what a note is about.
  takes note: text
  gives about: text
  instructions: Say what the note is about.

workflow look
  description: Look at a note, and hand nothing back.
  takes note: text
  see = call looker with note: input.note

workflow file
  description: File a note by the folder it came in.
  takes note: text, folder: text
  where = decide
    by:
      - rules:
          - when:
              - { value: input.folder, is: invoices }
            choose: bills
            because: Everything in the invoices folder is a bill.
          - choose: other
    if bills: done
    if other: done

workflow each-look
  description: Look at every note, and hand back what each was about.
  takes notes: list of text
  gives about: list of text
  every = for each item in input.notes
    limits:
      items-at-most: 5
      when-it-runs-out: stop-and-say-so
    combines-by:
      about: keep-all
    see = call looker with note: item
  reply = answer with about: every.about
"""


def go(tmp_path: Path, name: str, inputs: dict[str, Any]):
    (tmp_path / "notes.pact").write_text(WORKSPACE, encoding="utf-8")
    doc = shown(tmp_path)
    spec = WorkflowSpec.from_workflow(doc, name)

    def agent(_name: str, given: dict[str, Any]) -> dict[str, Any]:
        return {"about": f"about {given['note']}"}

    return asyncio.run(run_workflow(spec, inputs, Callers(agent=agent), document=doc))


def test_a_workflow_that_reaches_no_answer_stage_hands_back_an_empty_record(tmp_path: Path) -> None:
    out = go(tmp_path, "look", {"note": "rent"})
    assert out.halted == "final", out.said
    assert out.answer == {}
    # What the stage answered is still there to read, under its name.
    assert out.steps["see"] == {"about": "about rent"}


def test_a_workflow_that_ends_on_a_decision_hands_back_nothing_either(tmp_path: Path) -> None:
    out = go(tmp_path, "file", {"note": "rent", "folder": "invoices"})
    assert out.answer == {}
    assert out.steps["where"] == {"label": "bills", "decided-by": "rules"}
    # The rule's reason is the run's "why this path"; it is not a field of the
    # stage, which has no `because` for a binding to read.
    assert out.because == {"where": "Everything in the invoices folder is a bill."}
    out = go(tmp_path, "file", {"note": "rent", "folder": "inbox"})
    assert out.steps["where"] == {"label": "other", "decided-by": "rules"}
    assert out.because == {}


def test_a_body_still_hands_its_last_stages_answer_to_the_stage_that_holds_it(tmp_path: Path) -> None:
    out = go(tmp_path, "each-look", {"notes": ["rent", "gas"]})
    assert out.halted == "final", out.said
    assert sorted(out.answer["about"]) == ["about gas", "about rent"]
