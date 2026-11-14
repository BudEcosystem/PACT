"""Whether an agent's answer is what the agent says it gives.

`answers-with:` is a promise to whoever calls the agent. The harness put the
shape to the model and then took whatever came back: `decision: maybe` from an
agent that gives `one of approved, declined` was handed on as its answer, and
the caller found out when it read the field. `checked-by:`, the author's own
rules for an answer, was read by nothing in this loop at all. This is the
reader that holds an answer to both, and the one place its refusal is worded,
so a model that is asked again is told what was wrong in the author's own
words and two runtimes tell it the same thing.

What is fixed (ruled with Bud Agent Flow, whose engine checked the answer and
asked again without limit; the owner's ruling, 14 November: "if there is a
promised shape, it must be honored"):

* **A field left out** does not fit, unless its shape says `, optional`.
* **A value its shape refuses** does not fit: outside a `one of`, not a number
  where a number is written.
* **A field that streams** (`reply: stream of text`) is the reply itself, as it
  arrives: it is not looked for on a line of its own, and its value is the
  reply's words. Only an empty reply leaves it out.
* **A field the shape does not have** is not a reason to ask again. It breaks
  nothing that was promised; it is not handed back (`fields_of`).
* **Asked for at most `checks-at-most:` times in all**, 2 when unwritten. An
  attempt that does not fit and an attempt that breaks a `checked-by:` rule
  spend from the same count, and so does the closing answer of a run that
  reached a limit.
* **An empty reply that arrived is an attempt.** A call that failed is not: it
  never produced an answer to hold.
* **Still not fitting, the run ends `checks-failed` and hands back no answer.**
  What it says is why. The answer that did not fit is in the steps.
* **An agent that promises no shape and has no rules is held to nothing**, an
  empty reply included.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from .questions import Rejected, Shape

#: How a run that could not get a fitting answer ended (`RunResult.halted`).
CHECKS_FAILED = "checks-failed"

#: How a failed `checked-by:` check opens what the model is told. The words
#: `pydantic_ai_interop` already sent for the same thing.
CHECK_FAILED = "Your answer breaks a rule it must keep: "
#: How a reply that does not fit `answers-with:` opens what the model is told.
DID_NOT_FIT = "Your last answer did not fit what your answer must contain:"

#: `name: value` on a line of its own, as the model is asked to end its reply:
#: `- decision: approved`. A bullet or bold in front is the model's habit.
_LINE = re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?([A-Za-z0-9][A-Za-z0-9_-]*)(?:\*\*)?\s*:\s*(.*?)\s*$")


def _streams(written: Any) -> bool:
    """Whether a field is written as a stream: the reply itself, arriving."""
    return str(written).lstrip().startswith("stream of ")


def fields_of(said: str, shape: Mapping[str, str]) -> dict[str, Any]:
    """The declared fields a reply carries, and no others. A reply that is one
    JSON record is read as that; otherwise each declared name is read off its
    own line, the last such line winning, because the model is told to END
    with them. A value written as JSON (a list, a record) is read as JSON. A
    field that streams is the reply's own words, unless a line of its own
    says otherwise."""
    try:
        read = json.loads(said)
    except (TypeError, ValueError):
        read = None
    if isinstance(read, Mapping):
        return {k: v for k, v in read.items() if k in shape}
    found: dict[str, Any] = {
        name: str(said) for name, written in shape.items() if _streams(written) and str(said).strip()
    }
    for line in str(said).splitlines():
        m = _LINE.match(line)
        if not m or m.group(1) not in shape:
            continue
        value: Any = m.group(2)
        if value[:1] in "[{":
            try:
                value = json.loads(value)
            except ValueError:
                pass
        found[m.group(1)] = value
    return found


def does_not_fit(
    said: str, shape: Mapping[str, str], shapes: Mapping[str, Mapping[str, str]] | None = None
) -> tuple[str, ...]:
    """Why `said` is not what `shape` promises: one line for each field, in the
    order the shape writes them. Empty when it fits."""
    fields = fields_of(said, shape)
    problems: list[str] = []
    for name, written in shape.items():
        if name not in fields or (isinstance(fields[name], str) and not fields[name].strip()):
            if not str(written).rstrip().endswith(", optional"):
                problems.append(f"`{name}` is missing. It should be: {written}.")
            continue
        try:
            Shape.parse(written, dict(shapes or {})).read(fields[name])
        except Rejected as no:
            # The shape reader's own words: what it should be, and what it is.
            problems.append(f"`{name}` {no}.")
    return tuple(problems)


def ask_again(problems: tuple[str, ...]) -> str:
    """What a model is told when its answer did not fit and it is asked again."""
    return (
        DID_NOT_FIT
        + "\n"
        + "\n".join(f"- {p}" for p in problems)
        + "\nAnswer again, with every field as it is asked for."
    )


def rule_broken(broken: str) -> str:
    """What a model is told when its answer broke a `checked-by:` rule."""
    return f"{CHECK_FAILED}{broken}. Answer again so that it keeps every rule."


@dataclass
class Held:
    """One run's hold on its answer: what the answer is held to, and how many
    times it has been asked for.

    `wrong` is the one question, asked of every reply that would be the
    answer. It counts the attempt. The shape is read first: a reply with a
    field missing is told that, and its `checked-by:` rules are read only of a
    reply that fits, because a rule about what an answer says is not usefully
    decided on one that is not an answer yet."""

    shape: Mapping[str, str] = field(default_factory=dict)
    shapes: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    #: `evals.first_broken`, already bound to the agent's rules: given the
    #: reply, why it breaks one, or `""`.
    rules: "Callable[[str], str] | None" = None
    at_most: int = 2
    #: How many replies have been held so far.
    asked: int = 0
    #: Why the last reply held did not fit, as the model was (or would be) told.
    last: str = ""
    #: The same, as its parts: the fields that did not fit, or the rule broken.
    problems: tuple[str, ...] = ()
    broken: str = ""

    @property
    def holds_anything(self) -> bool:
        return bool(self.shape) or self.rules is not None

    @property
    def may_ask_again(self) -> bool:
        return self.asked < self.at_most

    def wrong(self, said: str) -> str:
        """Why `said` is not the answer, in the words a model is told, or `""`
        when it is. Counts one attempt either way."""
        if not self.holds_anything:
            return ""
        self.asked += 1
        self.last, self.broken = "", ""
        self.problems = does_not_fit(said, self.shape, self.shapes) if self.shape else ()
        if self.problems:
            self.last = ask_again(self.problems)
        elif self.rules is not None and (broken := self.rules(said)):
            self.broken = broken
            self.last = rule_broken(broken)
        return self.last

    def gave_up(self) -> str:
        """What a run says when it ends `checks-failed`: how many times it was
        asked, and what was wrong with the last reply. Said to a person, so in
        the third person: the words the MODEL was told (`last`) begin "Your
        last answer", and whoever reads a run's ending is not the model."""
        times = "once" if self.asked == 1 else f"{self.asked} times"
        if self.broken:
            kept = "it did not keep" if self.asked == 1 else "none kept"
            return (
                f"Stopped without an answer: it was asked for its answer {times} and {kept} "
                f"its `checked-by:` rules. The last one {self.broken}."
            )
        fit = "it did not fit" if self.asked == 1 else "none fit"
        return (
            f"Stopped without an answer: it was asked for its answer {times} and {fit} "
            f"`answers-with:`. In the last one:\n" + "\n".join(f"- {p}" for p in self.problems)
        )
