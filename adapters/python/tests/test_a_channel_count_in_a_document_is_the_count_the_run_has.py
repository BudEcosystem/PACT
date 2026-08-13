"""A document that counts the honesty channels counts the ones the run has.

The honesty channels are the thing this project says about itself most often:
`unmetered` (nobody could measure it), `unenforced` (nobody could evaluate it),
`unwatched` (nowhere to write it), `never_reached` (the meter is right and always
zero) and `unretrieved` (the documents were never opened, so the answer is what
the model already knew). Three shipped documents put a NUMBER in front of them,
and a number in prose is the one kind of claim that decays without anybody
touching it — the code grew a fifth channel and the documents went on saying
four for as long as it took a reader to notice:

```text
docs/90-REVIEW.md:30   on the evidence of its diagnostics and its four honesty channels
docs/90-REVIEW.md:97   3. **Four honesty channels** — `unmetered` … `never_reached`.
docs/93-GAPS.md:229    - **Four honesty channels** — `unmetered` / … / `never_reached`.
$ git show HEAD:adapters/python/src/pact_adapters/harness.py | grep -c unretrieved
4
```

So the reference port had carried the fifth since A7 and the two documents that
count them had never been moved. This is the same job
`crates/pact-cli/tests/the_subset_the_second_port_runs.rs` does for §7.28's three
lists and `deliberate_refusals.rs` does for `50-NOT-COPIED.md`: `pact check`
never reads a document about the code, so without a test a document about the
code says whatever it likes.

Two drifts are held, and they are two different mistakes:

* a channel added to or taken off `RunResult` and the documents left behind —
  which is what happened;
* a document writing a count the run does not have, in either direction.

WHICH channel a report lands on is not held here. That is
`test_the_subset_the_second_port_runs.py` (which runs a port and reads
`unenforced`) and
`test_a_corpus_the_second_port_never_looked_in_is_not_silent.py` (which runs both
and compares the sentence). This file holds the arithmetic.

Mutation: write `five` back to `four` in `docs/93-GAPS.md`. Without the count
check, the whole suite stays green — nothing else in it reads that line — and
a reader is told the port has one fewer way of admitting what it did not do than
it has. Second mutation: add `unbudgeted: tuple[str, ...] = ()` to `RunResult`.
Without the negation check, a sixth channel lands with three documents still
saying five and no test notices.
"""

from __future__ import annotations

import dataclasses
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # noqa: E402

from pact_adapters.harness import RunResult  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

#: The channels, in the order `RunResult` declares them as a group. Written out
#: rather than derived, because this list IS the claim the documents make — a
#: list derived from the fields would agree with the code by construction and
#: could never catch the code growing a channel nobody wrote down.
CHANNELS = ("unretrieved", "unmetered", "unenforced", "unwatched", "never_reached")

#: How a channel is named apart from every other field on a run: it is a
#: negation. `output`, `steps`, `retrieved` and `phases` say what happened;
#: these say what did not. A new field spelt this way is a new channel.
NEGATIONS = ("un", "never_")

#: The documents that describe the system as it is. `95-FIX-PLAN.md` is in here
#: too: it writes *"prints all five honesty channels"* about a verb that does not
#: exist yet, and a plan that plans for the wrong number of channels is exactly
#: as wrong as a review that reviews the wrong number.
PROSE = [REPO / "README.md", *sorted((REPO / "docs").rglob("*.md")),
         *sorted((REPO / "site-docs").rglob("*.md"))]

WORDS = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
}

#: `four honesty channels`, `Five honesty channels`, `5 honesty channels`. The
#: plural is required: *"the fifth honesty channel"* is an ordinal naming one of
#: them, not a count of all of them, and `**1**` in a diff summary is a count of
#: what a change ADDS. Only counting words match, so *"printing the honesty
#: channels"* — prose that deliberately carries no number, which is the other
#: honest way to write the sentence — is left alone rather than read as a count.
COUNTED = re.compile(
    r"\b(" + "|".join(WORDS.values()) + r"|\d+) honesty channels\b", re.IGNORECASE
)


def lines_with(path: Path, pattern: re.Pattern[str]) -> list[tuple[int, str, str]]:
    """`(line number, the word matched, the line)` for a document a person reads."""
    found = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for m in pattern.finditer(line):
            found.append((n, m.group(1), line.strip()))
    return found


# ------------------------------------------------------------------ the channels


def test_every_channel_the_documents_name_is_a_channel_the_run_carries() -> None:
    """The list in prose against the fields on the result, in both directions.

    A channel renamed on `RunResult` and left alone in the documents sends a
    reader to a field that is not there; a channel added and not written down is
    a report nobody knows to read, which is the same defect the fifth channel
    itself was.
    """
    declared = [f.name for f in dataclasses.fields(RunResult)]

    missing = [c for c in CHANNELS if c not in declared]
    assert not missing, (
        f"the documents count {len(CHANNELS)} honesty channels and `RunResult` has "
        f"no {missing} on it.\n"
        f"  what it does declare: {declared}\n"
        "  fix: if a channel was renamed, rename it in CHANNELS here and in every "
        "document that names it; if it was withdrawn, take it out of both and drop "
        "the count by one."
    )

    negations = [
        f.name for f in dataclasses.fields(RunResult)
        if f.name.startswith(NEGATIONS)
    ]
    extra = [n for n in negations if n not in CHANNELS]
    assert not extra, (
        f"`RunResult` carries {extra}, which no document counts.\n"
        "  fix: a field that says what the run did NOT do is an honesty channel. "
        "Add it to CHANNELS here, and move the count in docs/90-REVIEW.md and "
        "docs/93-GAPS.md with it — a channel nobody was told about is a report "
        "nobody reads, which is the defect the channels exist to prevent."
    )


def test_a_document_that_counts_the_channels_counts_all_of_them() -> None:
    """The number in the prose, against the number on the run.

    Held on the word and the digit both, because the sentence is written for a
    person: *"its five honesty channels"* is the form these documents use, and a
    reader who trusts it and goes looking for the fifth must find it.
    """
    want = {WORDS[len(CHANNELS)], str(len(CHANNELS))}
    wrong = []
    counted = 0
    for doc in PROSE:
        for n, word, line in lines_with(doc, COUNTED):
            counted += 1
            if word.lower() not in want:
                wrong.append(
                    f"{doc.relative_to(REPO)}:{n} says {word!r}\n      {line}"
                )
    assert not wrong, (
        f"a document counts the honesty channels and the run has {len(CHANNELS)} "
        f"({', '.join(CHANNELS)}):\n    " + "\n    ".join(wrong) + "\n"
        f"  fix: write `{WORDS[len(CHANNELS)]} honesty channels` and name the ones "
        "the sentence enumerates — a count that has drifted tells a reader the port "
        "admits less than it does, and they stop looking for the rest."
    )
    assert counted >= 3, (
        "no shipped document counts the honesty channels any more.\n"
        "  fix: either restore the sentence in docs/90-REVIEW.md and docs/93-GAPS.md, "
        "or delete this test with it — a drift guard over nothing is worse than none, "
        "because it reads green forever."
    )
