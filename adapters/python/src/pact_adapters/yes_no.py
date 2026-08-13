"""One reading of a tick in a document, for the readers listed below.

`spec/schema.yaml` has one type for a tick — `yes-no` — and one piece of code
decides what an author may write on such a line:
`crates/pact-schema/src/coerce.rs::yes_no`, which takes `yes`, `y`, `true`, `on`
and `enabled`, and their five negatives, in any capitalisation. That function is
the DOOR. A word it refuses never becomes a document; a word it accepts is a line
the author has been told, by the checker, is fine.

This port read those lines back five separate times with five private word-lists,
and three of the five disagreed with the door as well as with each other:

    facts._yes                  yes true on 1          `survives-shortening:`
    egress._yes                 yes true on y          `needs: audio:`
    resolve._yes                yes true on y          `needs: images/audio/computer-use:`
    ir.py, inline               yes true on y          `must-cite:`
    scoring.py, inline          yes true on            `spends-money:`

Not one of them took `enabled`. So an author writing `spends-money: enabled` was
told `OK — loaded cleanly`, and then the money-moving subset this port scores came
back empty — while the RUST half of the same question
(`pact-loader::money::moves_money`) read the line correctly through
`coerce::check` and demanded a gate on it. Two halves of one checker disagreeing
about which actions move money. Its comment already said why:

    a tick the checker does not recognise is an ungated spend it reports as fine

`facts._yes` diverged the other way, taking `1` where nothing else did. That arm
was never reachable — `images: 1` is `schema/wrong-type` at the door, with
*"Write `yes` or `no`."* under it — and it is gone anyway, because a reader more
generous than the checker is a second, unwritten specification, and the next
person to read `facts.py` has no way to tell which of the two is the rule.

**Two more readers were found after the first version of this file claimed to
have them all, and the claim in this docstring's first line is now narrower for
it.** Enumerating the callers and calling the list complete is a promise this
module cannot keep on its own — nothing here can see a `yes-no` field it was
never pointed at:

* `questions._needs_a_person` (`needs-a-person:`) was the sixth, and it was
  already correct. It calls this anyway, because being correct in a copy is how
  the other five came to look correct too.
* `settings.parallel-tool-calls:` was the seventh and was reached by nothing at
  all. `ir.py` carried the author's `settings:` block through verbatim, so the
  WORD reached the installed SDKs: `enabled` raised a pydantic `ValidationError`
  out of `agents.model_settings.ModelSettings`, and `no` went on the wire to
  `chat.completions.create(parallel_tool_calls="no")` — a truthy string, the
  opposite of what the author wrote. See `ir.TICKS_IN_SETTINGS`.
* A SIXTH private copy lives in the other port, on `must-cite:`
  (`adapters/typescript/src/harness.ts`), and is now
  `adapters/typescript/src/yes-no.ts`. It is not importable from here and is
  held to the same list by the same test.

`resolve.TOOL_CALLING` is deliberately NOT one of these: `needs.tool-calling:` is
`one-of: [no, yes, parallel]`, and `parallel` is a third answer rather than a
stronger tick.

**This module has no imports from the rest of the package, and must not acquire
any.** Its callers sit at every level of the port — `facts` and `egress` are
leaves, `ir` is built from both, `resolve`, `scoring` and `questions` sit on or
beside `ir` — so anything it reached for would close a cycle behind it.

The Rust side does not need a twin of this file: it already reads every tick
through `coerce::check(&node, &Ty::YesNo)` rather than keeping a list, which is
the pattern this file brings to the Python side. What the two DO have to keep in
step is the vocabulary itself, and
`adapters/python/tests/test_one_word_for_yes_means_one_thing_to_every_reader.py`
reads it out of `coerce.rs` — the whole `fn yes_no` body, both arms — and
compares it against this file and against the TypeScript one.
"""

from __future__ import annotations

from typing import Any

#: The five spellings of a tick, exactly as `coerce.rs::yes_no` holds them.
#:
#: Not a list this port chose. Adding a sixth here without adding it there makes
#: a line an author may write in one half and not the other; removing one takes a
#: guarantee away from a document the checker still calls clean.
TICKS = frozenset({"yes", "y", "true", "on", "enabled"})

#: There is deliberately NO list of the negatives here. `no`, `n`, `false`, `off`
#: and `disabled` are the other five words `coerce.rs::yes_no` takes, and a copy
#: of them in this file would be read by nothing — :func:`said_yes` answers a
#: crossed line and an absent one the same way, so the list would decide nothing
#: and go stale unwatched. That is the shape
#: `tests/test_a_table_nothing_reads_is_not_a_source_of_truth.py` exists to catch,
#: and it caught this one. The five are held instead by the `CROSSES` rows of
#: `tests/test_one_word_for_yes_means_one_thing_to_every_reader.py`, which drive
#: each of them through `pact check` and assert nothing downstream switches on.


def said_yes(written: Any) -> bool:
    """Did the author tick this line?

    `False` for an absent line, for a crossed one, and for anything else — with
    the deliberate consequence that a word neither list holds reads as a no. That
    is safe HERE and would not be safe in the checker, and the difference is
    worth stating: on a call site reading a CHECKED DOCUMENT, invariant P-1 says
    an adapter is handed `pact show` output, so every value arriving has already
    been through `coerce.rs::yes_no` and is one of the ten words or a real
    boolean. There is no eleventh word to be wrong about. If one ever arrives,
    the mistake is upstream of here and a `False` is what the schema's own
    default already means for a line that is not there.

    **One call site is not that, and the exception is named rather than left to
    be discovered.** `resolve.py`'s `computer-use` reads a CAPABILITY BLOCK off
    `models/catalog.yaml` — the override layer §4.2 makes normative for an
    air-gapped box, hand-written, and not put through the schema. There, `y`,
    `on` and `enabled` are honoured exactly as they are in a document, and a
    TYPO (`computer-use: ues`) reads as a silent no: a model that can drive a
    computer is quietly dropped from what an author may be recommended. That is
    no worse than it was — the `_yes` this replaced was strictly narrower, and
    read `y` and `enabled` as typos too — but it is not covered by the argument
    above and does not pretend to be. Closing it means checking the catalogue
    against a schema, which is a larger piece of work than this file.

    A real `bool` is answered as itself. `true` is the one spelling the YAML core
    schema resolves, so `survives-shortening: true` arrives as `True` and never as
    text — and a hand-written catalogue row saying `computer-use: true` is the same
    value by a different route.
    """
    if isinstance(written, bool):
        return written
    return str(written or "").strip().lower() in TICKS
