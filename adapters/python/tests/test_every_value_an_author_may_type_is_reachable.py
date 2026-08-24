"""A dead field name is inert. A dead choice value is *recommended*.

`test_every_field_has_a_reader.py` holds every field an author can write. It says
nothing about the values inside a closed choice, and that is the column that has
been growing fastest: 147 values across 45 lists.

The asymmetry is the whole argument. A field nothing reads is silent — an author
has to have typed it for it to matter. A VALUE nothing reads is *taught*: type a
near-miss and the checker prints the whole legal list back as its `fix:` line, so
a value nothing honours is offered to every author who makes a typo near it. That
is R24's defect — a setting nothing can use — arriving through the one construct
the field-level instrument cannot see.

**Why this is sequenced last.** Measured, it is dark on most of a plan's new
values on the day they land, because the value ships in the schema before the arm
that reads it. Run first it is a blocker with a test's name; run last it is a
guard.

**Values are matched as LITERALS only.** A choice is compared as a string —
`"durable-execution"`, `'p95'` — and never bound to an identifier, so the
identifier half of `reader_exists` would only add false positives. `max` and
`mean` are ordinary English words and `single`, `delete` and `get` are common
method names; matching them as bare identifiers would have reported every one of
them as read, including the two that were genuinely broken.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_every_field_has_a_reader import corpus  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
SCHEMA = yaml.safe_load((REPO / "spec/schema.yaml").read_text())["groups"]

#: Fields whose VALUES are honoured somewhere other than this repository, each
#: with the reason — the same register `DELEGATED` is one level up, and read the
#: same way: a line here is a claim that somebody else acts on the word, and it
#: is reviewable precisely because it is written down.
#:
#: Per FIELD and not per value, because the reason is a fact about the field. A
#: list of individually-excused values is a list nobody reads.
SOMEBODY_ELSE_ACTS_ON_THE_WORD: dict[str, str] = {
    # §4 — declared here, kept by the store the host supplies.
    "state.lasts": "the store decides how long a value survives",
    "state.never-from": "the store refuses a write from a source this names",
    "workspace.durability": "what the system running this keeps when a run stops part-way",
    "action.same-request-key-across": "a scope wider than one run is kept outside it",
    # §4 — a carried program (P6). PACT declares which kind of program this is
    # and which kinds a locked room can run; the HOST is what starts one, because
    # nothing in this distribution ever opens a body. The words are held against
    # EACH OTHER at check time (`crates/pact-loader/src/programs.rs`) — a program
    # written for a kind no room here hosts is refused where the author is — and
    # what no check can do is run it.
    "program.engine": "the host runs the program; PACT records which kind it is",
    "program.determinism": "the host decides whether an answer may be replayed",
    "resource.engines": "the locked room is the host's; PACT records what it says it can run",
    # §4 — the host makes the call and schedules the work.
    "tool.method": "the host makes the HTTP call; PACT records which verb it is",
    "port.if-still-running": "the scheduler decides what to do with an overlapping run",
    "learning.review": "the host schedules the review cycle",
    "learning.needs-a-person-to-approve": "the host routes each kind of change to a person",
    # HALF DELEGATED, and the row said "the host decides" of a field this port
    # branches on: `may_apply_without_a_person` reads
    # `keep-only-if: a-person-approves-it` and refuses to apply anything without
    # one (learning.py). What is the host's is the OTHER value —
    # `scores-higher-on-evals` names a bar that only a run with a live model can
    # clear, so nothing here can decide it either way.
    #
    # The distinction matters because a wrong excuse blinds the guard: registered
    # as wholly delegated, a THIRD choice added to this field would be exempted
    # in silence, while the code really does branch on the word.
    "learning.keep-only-if": (
        "`a-person-approves-it` is read here and refuses every automatic apply; "
        "`scores-higher-on-evals` is the host's, since only a run against a live "
        "model can clear that bar"
    ),
    # A7 — PACT does not retrieve, embed, index or chunk.
    "knowledge.split-by": "the retrieval runtime breaks a document up",
    "knowledge.looked-up-by": "the retrieval runtime finds the passages",
    # Read as DATA rather than as a literal, which is the point of B15: the
    # loader compares the author's word against `satisfied-by:` in the schema, so
    # the word appears in `spec/schema.yaml` and in no Rust source.
    "tool.available-when": "compared against `satisfied-by:` in the schema, not against a literal",
    "skill.available-when": "compared against `satisfied-by:` in the schema, not against a literal",
    "resource.available-when": "compared against `satisfied-by:` in the schema, not against a literal",
    # Published to a host that acts on them; PACT records the author's choice.
    "model.tier": "a label a host uses to pick between rows in its own price list",
    "model-can.tool-calling": "what a transport can do, compared against the model's own row",
    "resource.resource-kind": "the host connects to the thing this names",
    "settings.thinking": "the transport turns this into whatever its provider calls it",
    "case.split": "the learning loop's own split, honoured by whoever runs the cycle",
}


def closed_choices() -> dict[str, list[str]]:
    """Every closed-choice value, by the field that offers it."""
    out: dict[str, list[str]] = {}
    for kind, group in SCHEMA.items():
        for field, spec in (group.get("fields") or {}).items():
            if isinstance(spec, dict) and spec.get("choices"):
                out[f"{kind}.{field}"] = [str(c) for c in spec["choices"]]
    return out


def read_as_a_literal(value: str, body: str) -> bool:
    return f'"{value}"' in body or f"'{value}'" in body


def test_there_are_closed_choices_to_check() -> None:
    fields = closed_choices()
    assert len(fields) > 30, f"only {len(fields)} closed choices found — the schema did not load"
    assert sum(len(v) for v in fields.values()) > 120


def test_every_value_an_author_may_type_is_read_by_something_that_is_not_a_test() -> None:
    """The whole test.

    **Mutation:** delete the arm in `slo.py` that reads `max`. `max` stays in
    `spec/schema.yaml`, stays in every `fix:` line the checker prints, and this
    turns red — which is what it did not do for as long as `measured-at: max`
    silently reported the 95th percentile under the author's own word.
    """
    body, _ = corpus()
    orphans: list[str] = []
    for field, values in closed_choices().items():
        if field in SOMEBODY_ELSE_ACTS_ON_THE_WORD:
            continue
        for value in values:
            if not read_as_a_literal(value, body):
                orphans.append(f"{field}: {value!r}")
    assert not orphans, (
        f"{len(orphans)} value(s) an author can type are honoured by nothing, and the "
        f"checker offers every one of them in its own `fix:` line:\n  "
        + "\n  ".join(orphans)
        + "\n\nEither wire it, delete it, or add its FIELD to "
        "SOMEBODY_ELSE_ACTS_ON_THE_WORD with the reason somebody else acts on it."
    )


def test_the_delegation_register_is_not_a_dumping_ground() -> None:
    """Every excuse carries a reason and names a field that exists. A register
    that can hold anything records nothing."""
    fields = closed_choices()
    for field, reason in SOMEBODY_ELSE_ACTS_ON_THE_WORD.items():
        assert field in fields, f"`{field}` is excused and offers no closed choice"
        assert len(reason) > 20, f"`{field}` is excused with no real reason: {reason!r}"
    assert len(SOMEBODY_ELSE_ACTS_ON_THE_WORD) < 30, (
        f"{len(SOMEBODY_ELSE_ACTS_ON_THE_WORD)} delegations — this list is becoming the "
        f"exception that swallows the rule"
    )


def test_a_percentile_word_means_the_number_it_names() -> None:
    """The defect this test was written by finding. `mean` and `max` are two of
    the six values `measured-at:` accepts and neither is a percentile, so both
    fell to a dict default of 0.95 and were printed under the author's own word:
    over samples 1..100, `max` reported `95.00s` when the true maximum is 100.0.

    Somebody who writes `max` wants the worst case. They were shown a number
    that hides it, labelled with the word they chose."""
    from dataclasses import replace

    from pact_adapters.slo import Slo

    slo = Slo.from_mapping({"finishes-within": "200s", "measured-at": "p95"})
    samples = [float(i) for i in range(1, 101)]
    said = {
        at: replace(slo, measured_at=at).assess(samples, "e2e", min_samples=1)
        for at in ("p50", "p95", "p99", "mean", "max")
    }
    assert "max=100.00s" in said["max"], said["max"]
    assert "mean=50.50s" in said["mean"], said["mean"]
    assert "p95=95.00s" in said["p95"], said["p95"]
    assert len({s.split("=")[1] for s in said.values()}) == 5, (
        "five different statistics over one set of samples must not agree", said
    )
