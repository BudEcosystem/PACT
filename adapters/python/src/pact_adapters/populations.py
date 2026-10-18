"""Which runs a suite is a score of (02W §2.13): its population and the lines
beside it, which runs a sample takes, and the score broken down by group.

`evals.py` grades one answer; this says what the answers were answers TO. A
suite of written cases scores the situations somebody thought of. Once real
runs exist a team wants three more things, and PACT says what each one means so
that every runtime that keeps runs means the same:

- **`past-runs`**: real runs from `from-the-last:` (every finished one when it
  is left out), each replayed with its own inputs and every write stubbed by its
  declared effect. The runtime replays; PACT reads the window.
- **`sampled-frame`**: a `sample:` share of finished live runs is put in front
  of `reviewed-by:`. Which runs is decided by each run's own id (`in_sample`),
  never by a draw: the same run is always in the sample or always out of it, on
  any machine, however many runs there are and in whatever order they are
  listed — so a sample can be taken as runs finish, twice over, and still be
  one sample.
- **`sliced-by:`**: the score broken down by what each run was given
  (`slices`), each group with the verdict `evals.verdict` gives a suite of that
  size, so a group too small to support the bar says UNDECIDED rather than a
  share that reads as evidence.

`runs-every:` is read by the grammar a port's `every:` is (`schedules.py`); the
clock is the serving runtime's.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .evals import CaseOutcome, Verdict, verdict
from .limits import seconds
from .providers import share

#: The four populations, in the order `spec/schema.yaml` lists them.
AUTHORED, PROMOTED, SAMPLED, PAST_RUNS = (
    "authored-enumeration",
    "promoted-traces",
    "sampled-frame",
    "past-runs",
)

#: What a slice is called for a run that was not given the field at all.
NOT_GIVEN = "(not given)"


@dataclass(frozen=True)
class Population:
    """A suite's `population:` and the lines that say which runs it scores."""

    kind: str = AUTHORED
    #: `from-the-last:` in seconds; None is every finished run there is.
    from_the_last: float | None = None
    #: `sample:` as a share from 0 to 1; None when the suite samples nothing.
    sample: float | None = None
    reviewed_by: tuple[str, ...] = ()
    sliced_by: tuple[str, ...] = ()
    #: `runs-every:` as written; "" when the checks run only when asked.
    runs_every: str = ""

    @staticmethod
    def of(doc: Mapping[str, Any]) -> "Population":
        """The suite's population lines, as `pact check` let them through."""
        suite = doc.get("evals") or {}
        sample = suite.get("sample")
        return Population(
            kind=str(suite.get("population") or AUTHORED).strip(),
            from_the_last=seconds(suite.get("from-the-last")),
            sample=None if sample is None else share(sample, 0.0),
            reviewed_by=_texts(suite.get("reviewed-by")),
            sliced_by=_texts(suite.get("sliced-by")),
            runs_every=str(suite.get("runs-every") or "").strip(),
        )

    @property
    def schedule(self) -> Any:
        """`runs-every:` as a `schedules.Schedule`, or None when it is not written.
        Raises `schedules.Unreadable` with the forms that work."""
        from .schedules import Schedule

        return Schedule.parse(self.runs_every) if self.runs_every else None


def _texts(raw: Any) -> tuple[str, ...]:
    items = [raw] if isinstance(raw, str) else list(raw or ())
    return tuple(str(i).strip() for i in items if str(i).strip())


def in_sample(run_id: str, share_of_runs: float) -> bool:
    """Whether the run `run_id` is in a sample of `share_of_runs` (0 to 1).

    The first eight bytes of the SHA-256 of the run's id, read as a fraction of
    2^64, below the share. A pure function of the id: the same run is in or out
    whatever else ran, and over many runs the share taken is the share written.
    """
    if share_of_runs <= 0:
        return False
    if share_of_runs >= 1:
        return True
    point = int.from_bytes(hashlib.sha256(run_id.encode("utf-8")).digest()[:8], "big")
    return point / 2**64 < share_of_runs


def slices(
    results: Sequence[CaseOutcome],
    given: Mapping[str, Mapping[str, Any]],
    fields: Sequence[str],
    bar: float,
) -> dict[str, dict[str, Verdict]]:
    """Each `fields` entry's groups, each group's verdict at `bar`.

    `given` is what each case's run was given, by the case's key. A value is
    grouped as it reads (`True` is `yes`), and a run not given the field falls in
    `NOT_GIVEN`, so every case is counted once in every field's breakdown.
    """
    out: dict[str, dict[str, Verdict]] = {}
    for name in fields:
        groups: dict[str, list[CaseOutcome]] = {}
        for result in results:
            value = (given.get(result.key) or {}).get(name)
            groups.setdefault(_group(value), []).append(result)
        out[name] = {g: verdict(rs, bar) for g, rs in sorted(groups.items())}
    return out


def _group(value: Any) -> str:
    if value is None:
        return NOT_GIVEN
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value).strip() or NOT_GIVEN
