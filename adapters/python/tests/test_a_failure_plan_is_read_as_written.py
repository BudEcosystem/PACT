"""What happens after a failure, read off the document `pact show` prints
(02W §2.7): a stage's `if-it-fails:` as one typed `FailurePlan` on the
`StageSpec` a runtime is handed. (An action's `undone-by:` and `status-check:`
are held by the loader, `failures.rs`; the workflow runtime that undoes reads
them where it runs the undo.)

Over #60's tree (`tests/trees/workflows-60-interconnection/`, 02W §5.5) and
#48's (`workflows-48-invoices/`), copied and given the lines each test reads,
then loaded through the real loader.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pact_adapters.ir import WorkflowSpec  # noqa: E402
from pact_adapters.moments import FailurePlan, Moment  # noqa: E402
from trees import REPO, shown  # noqa: E402

INTERCONNECTION = REPO / "tests/trees/workflows-60-interconnection"
INVOICES = REPO / "tests/trees/workflows-48-invoices"


def _copy(src: Path, dst: Path, edits: dict[str, tuple[str, str]], extra: dict[str, str] | None = None) -> Path:
    shutil.copytree(src, dst)
    for name, (old, new) in edits.items():
        path = dst / name
        text = path.read_text()
        assert old in text, f"fixture drifted: {old!r} not in {name}"
        path.write_text(text.replace(old, new, 1))
    for name, text in (extra or {}).items():
        (dst / name).parent.mkdir(parents=True, exist_ok=True)
        (dst / name).write_text(text)
    return dst


ENVELOPE = "    bind: { agreement: steps.contract.agreement, signers: steps.contract.signers }\n"


def test_a_stage_with_no_failure_plan_stops_and_says_so() -> None:
    flow = WorkflowSpec.from_workflow(shown(INTERCONNECTION), "interconnection")
    assert flow.stage_named("envelope").if_it_fails is None
    assert FailurePlan.from_written(None) is None


def test_an_undo_plan_is_read_with_its_stage_and_its_deadline(tmp_path: Path) -> None:
    root = _copy(
        INTERCONNECTION,
        tmp_path / "tree",
        {
            "workflows/interconnection.yaml": (
                ENVELOPE,
                ENVELOPE + "    if-it-fails:\n      after-that: undo\n      undo: reserve\n      gives-up-after: 2 days\n",
            )
        },
    )
    plan = WorkflowSpec.from_workflow(shown(root), "interconnection").stage_named("envelope").if_it_fails
    assert plan == FailurePlan(after_that="undo", undo="reserve", gives_up_after=Moment(after="2 days"))


def test_carrying_on_is_read_with_the_answer_it_goes_on_with(tmp_path: Path) -> None:
    root = _copy(
        INVOICES,
        tmp_path / "tree",
        {
            "workflows/ap-inbox.yaml": (
                "        bind: { file: item.file }\n",
                "        bind: { file: item.file }\n        if-it-fails:\n          after-that: carry-on\n"
                "          carry-on-with: { invoice: values.unread-invoice }\n",
            )
        },
        {"values/unread-invoice.yaml": "description: d\nshape: text\nvalue: unread\n"},
    )
    flow = WorkflowSpec.from_workflow(shown(root), "ap-inbox")
    (each,) = [s for s in flow.steps if s.name == "each-attachment"]
    (read,) = [s for s in each.steps if s.name == "read"]
    assert read.if_it_fails == FailurePlan(after_that="carry-on", carry_on_with={"invoice": "values.unread-invoice"})
