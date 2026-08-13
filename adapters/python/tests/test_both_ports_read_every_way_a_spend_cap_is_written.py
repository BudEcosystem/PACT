"""One `cost-per-request-under:` line, every way it is written, two runtimes, one sentence.

`coerce::money` accepts the amount and the currency in either order and takes
`$` as USD — its own unit test names `0.05 USD`, `USD 0.05` and `$0.05` as the
three spellings, and `schema.yaml`'s help offers them to the author. So a
document may legitimately carry any of them, and `Reached.sentence()` is the
string the two ports are compared on.

Measured before the fix, over `spend()` in `adapters/typescript/src/limits.ts`
against `money()` in `adapters/python/src/pact_adapters/limits.py`::

    '0.05 USD' -> py (0.05, 'USD')   ts [0.05, "USD"]        agree
    'USD 0.05' -> py (0.05, 'USD')   ts [0.05, ""]           DIVERGE
    '$0.05'    -> py (0.05, 'USD')   ts [0.05, ""]           DIVERGE
    '0.05 usd' -> py (0.05, 'USD')   ts [0.05, "usd"]        DIVERGE
    'JPY 500'  -> py (500.0, 'JPY')  ts [500, ""]            DIVERGE
    '0.05 DOLLARS' -> py (0.05, '')  ts [0.05, "DOLLARS"]    DIVERGE

Four of the six documented ways to write one cap produced a different noun in
the report, and the fifth invented a currency out of a word `coerce::money`
refuses outright. The currency bug this pair was introduced for — *"reported
(501 of 500 USD), a currency the author never wrote"*, quoted in `spend()`'s own
docstring — was fixed for `0.05 USD` and for no other spelling of it.

**Every divergent spelling but one is a line an author can write and the gate
accepts.** Measured through the shipped binary, on throwaway copies of
`examples/refund-desk` with `agents/refund-desk/limits.yaml:11` rewritten and
nothing else touched::

    cost-per-request-under: 0.05 USD    rc=0  loaded cleanly (498 settings)
    cost-per-request-under: USD 0.05    rc=0  loaded cleanly (498 settings)
    cost-per-request-under: $0.05       rc=0  loaded cleanly (498 settings)
    cost-per-request-under: 0.05 usd    rc=0  loaded cleanly (498 settings)
    cost-per-request-under: 0.05<NEL>USD rc=0 loaded cleanly (498 settings)
    cost-per-request-under: 0.05 DOLLARS rc=1 '…should be an amount of money,
                                              like `0.05 USD`, but it is some text.'

So this was an authorable defect and not a synthetic one — including the NEL
row, the least believable of the set. Only the degenerate ZERO in `SPELLINGS`
below is code-built; see the note on that dict for why the amount has to be.

**Why this survived a suite that already compares the two ports.** The money
figure was never *sent* in a divergent spelling. `test_portability.py`'s
`_payload_for` sends no `limits` key at all — only `maxSteps`, and its own
coverage table accounted for the whole block as ``"limits": ("maxSteps",)`` — and
all three money fixtures in `test_termination.py` are written `<number> <CUR>`
or as a bare number, the one order both readers already agreed about. A
spelling that is never sent is outside the comparison by construction, which is
why a unit test on `spend()` alone would be the wrong test here as well: it
would prove the reader and not the report.

Mutation. Each behaviour restored ON ITS OWN in an isolated copy of the tree —
`adapters/typescript/src` and `pact_adapters/limits.py` byte-identical to the
working tree before each one, `diff -rq` clean — the whole file run, and the
count and the red rows taken FROM THE RUN rather than reasoned about. Baseline
**19 passed**::

    no `$` arm at all                            1 failed   $0
    global " USD " for the `$` PREFIX arm        1 failed   0$
    amount !== null before the currency          1 failed   JPY 0
    currency = part           for .toUpperCase() 1 failed   0 jpy
    String(v)                 for inf/-inf/nan   1 failed   -inf USD
    .split(/\\s+/)             for SEPARATOR      1 failed   0<NEL>JPY
    no `tokens.length > 2` guard                 1 failed   0 USD 0
    round-TRIP tie test       for the midpoint   3 failed   -0.12345, -10.005, -100.45
    float(token)              for _FIGURE (py)   3 failed   0_0, ０, ٠ USD
    ties away from zero       for ties to even   1 failed   -1234.5
    /^[0-9.]+$/               for FIGURE.test    7 failed   -5 JPY, 0e0 JPY,
                                                            -inf USD, all 4 ROUNDING

Three are worth reading twice. `/^[0-9.]+$/` fails `-5 JPY` and `0e0 JPY` with
*"is a ceiling in one port and not in the other: python stopped on 'cost-limit',
node on 'final'"* — a cap that binds on one side and does not exist on the other,
which is worse than a wrong noun — and it takes every `ROUNDING` row with it,
because those amounts are signed too. The round-TRIP tie test and the
ties-away-from-zero rule are the two halves of C's `%g` half-to-even rule, and
they redden DISJOINT rows: the first three `ROUNDING` amounts are not exact
binary midpoints and `-1234.5` is, so a fixture set with only one kind in it
would have held only one half. And the `$` arm is pinned in both directions —
`$0` must be a cap in USD, `0$` must be no cap at all — because the defect and
the mechanism chosen to fix it are the same invention pointing opposite ways.

With the whole pre-B5 `spend()` restored (`git show HEAD:` — the global `$`
substitution, `.split(/\\s+/)`, `/^[0-9.]+$/`, positional currency, no
upper-casing): **15 failed, 4 passed**. Restoring the pre-B5 `round()` and
`significant()` with it changes nothing — still 15 failed — because the four
`ROUNDING` rows are already red on the reader. The four passes are the `0 JPY`
control and the three `REFUSED` digit-grammar rows, which that reader happens to
refuse as well. `0 JPY` is the only spelling `test_termination.py` sends, which
is precisely why every one of these survived it.

The environment is mutated too, because the skip in `_probe` is itself a way for
this file to stay green while broken — and the record kept here of that was
FALSE for a round. It claimed a `throw` at the top of `spend()` gave
``8 passed, 1 skipped`` before the probe and ``1 failed`` after; that is nine
outcomes for a file `pytest --collect-only` reports 19 tests in, and the
mechanism it described did not exist. Re-measured, all four in the same isolated
copy::

    node not on PATH at all                 19 skipped   pytest exit 0
    node_modules absent                     19 skipped   pytest exit 0
    throw at the top of spend()             19 failed    pytest exit 1
      — the same, against the old probe     19 skipped   pytest exit 0

The last two lines are the repair: an exit-code probe cannot tell a port that is
not here from a port that is broken, because the control document reaches
`spend()` too. `_probe` now separates them by SIGNATURE, and says which
signatures and why.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.harness import run  # noqa: E402
from pact_adapters.ir import AgentSpec, ToolSpec  # noqa: E402
from pact_adapters.limits import Limits  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402
from pact_adapters.transports.mock import ReferenceTransport  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
TS_DIR = REPO / "adapters" / "typescript"

SPEC = AgentSpec(
    name="Refund Desk",
    description="Decides refunds",
    instructions="Decide, then issue the refund.",
    tools=(ToolSpec("zendesk", "read the ticket"),),
)

#: `written` -> the currency both ports must name for it.
#:
#: **The SPELLINGS are authorable; only the AMOUNT is not.** Each of these six
#: written with `0.05` in place of the `0` was put through the shipped binary on
#: a throwaway copy of `examples/refund-desk`: `0.05 USD`, `USD 0.05`, `$0.05`,
#: `0.05 usd` and `0.05<NEL>USD` all load cleanly, and `0.05 DOLLARS` is refused
#: with *"should be an amount of money, like `0.05 USD`, but it is some text"*.
#: The full table is in this module's docstring. So five of the six rows below
#: are lines a person can write and `pact check` accepts, and the defect they
#: caught was reachable from a real file.
#:
#: The AMOUNT is `0` for the reason
#: `test_a_cap_the_validator_can_read_is_a_cap_in_both_ports` gives at length: a
#: cap of zero is the only NON-NEGATIVE one a transport that spends nothing can
#: actually reach (`Limits.reached` compares `at >= c.limit`), and a ceiling that
#: never fires puts no noun in the report. `Schema::check_floor` refuses it —
#: measured, `cost-per-request-under: 0 USD` is rc=1 *"is 0 USD, which is no
#: money at all"* — so THAT much of each row is built in code. The figure is
#: degenerate on purpose; the NOUN is what is under test.
#:
#: `0 DOLLARS` is here as the row that must name NOTHING in both ports.
#: `coerce::money` refuses a currency that is not three ASCII letters, so a
#: reader that took `DOLLARS` would be naming a currency no document can carry —
#: the same defect as inventing `USD`, one word further on.
#:
#: `0<NEL>JPY` is the row that pins WHAT A SPACE IS. The three readers disagreed:
#: `split_whitespace` in `coerce::money` uses the Unicode `White_Space`
#: property, `str.split()` uses its own slightly wider set, and JavaScript `\s`
#: is narrower than both — it does not include `U+0085` NEL. So that one
#: separator was a cap the validator loads, a cap in Python, and no cap at all in
#: a port that splits on `\s`. It is written here as an escape rather than a
#: literal because a test that turns on an invisible character should say so.
SPELLINGS = {
    "0 JPY": "JPY",       # the control: the one order both ports already read
    "JPY 0": "JPY",       # currency first — `coerce::money`'s second branch
    "$0": "USD",          # the dollar sign IS the currency
    "0 jpy": "JPY",       # upper-cased, as `coerce::money` upper-cases it
    "0 DOLLARS": "",      # not three ASCII letters, so there is no noun at all
    "0\u0085JPY": "JPY",  # NEL: whitespace to Rust and Python, not to JS `\s`
}


def _drive(spec_payload: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["node", "--experimental-strip-types", "src/run-trace.ts",
         spec_payload, json.dumps({"turns": [{"text": "done"}]}), "hello"],
        cwd=TS_DIR, capture_output=True, text=True,
    )


def _payload(written: dict[str, object] | None) -> str:
    spec: dict[str, object] = {
        "name": "Refund Desk",
        "instructions": "Decide, then issue the refund.",
        "tools": [{"name": "zendesk", "description": "read the ticket"}],
        "maxSteps": 8,
    }
    if written is not None:
        spec["limits"] = written
    return json.dumps(spec)


def _probe() -> "tuple[str, str] | None":
    """`None` if the second port RUNS here, otherwise `(kind, why)`.

    The idiom every cross-port test in this suite uses is
    ``if out.returncode != 0: pytest.skip(...)`` — which reports a REGRESSION in
    the port under test as a skip. The first repair settled "node is not
    installed here" ONCE, against a document with no `limits:` block, on the
    stated ground that such a document is *"nothing this file is about"*.

    **That ground was false, and the record kept of it was false with it.**
    `harness.ts:467-468` is ``const written = spec.limits ?? {}`` followed by an
    unconditional ``limitsFrom(written)``, and `limits.ts:332` then calls
    ``spend(m["cost-per-request-under"])`` on `undefined` — so the control
    document reaches the very function this file exists to hold, and a crash
    there was reported as an absent runtime. Measured in an isolated copy of the
    tree, with `throw new Error(...)` as the FIRST statement of `spend()` and
    the probe as it was: ``19 skipped in 0.14s``, pytest exit 0. The same throw
    with the probe as it is now: ``19 failed``, exit 1. A test that cannot go red
    when the thing it is testing crashes is not holding it.

    So the question is no longer *"did it exit non-zero"* — every breakage does
    — but *"is this the signature of a runtime that is not here"*. There are
    exactly two such signatures and both were measured in that copy:

    * `node` not on PATH at all raises `OSError` out of `subprocess.run` before
      any exit code exists (`FileNotFoundError: [Errno 2] No such file or
      directory: 'node'`, with `PATH` emptied);
    * the TypeScript dependencies not installed gives rc=1 and
      ``Error [ERR_MODULE_NOT_FOUND]: Cannot find package 'ai' imported from
      …/src/vercel-transport.ts`` — measured by removing the `node_modules`
      link, which took the file from ``19 passed`` to ``19 skipped``.

    **What this does not close.** `19 skipped, exit 0` is still a green gate
    with zero cross-port money comparison in it, and `scripts/test-all.sh:39-42`
    skips the second port's typecheck under exactly the same condition. The
    probe closes the per-file half — a BROKEN port now fails — and nothing in
    this repository yet asserts at gate level that the second port is RUNNABLE.
    The idiom is systemic rather than local: ``grep -rn "node/AI SDK
    unavailable" adapters/python/tests/*.py`` returns 10 sites across 6 other
    files. It is recorded in `docs/remediation/B5-ts-money-divergence.md` as the
    residual hole, with the missing artifact named.

    Anything else is this port breaking, and `_both_ports` fails on it. The cost
    of the choice is stated rather than hidden: a `node` too old for
    `--experimental-strip-types` will now fail this file rather than skip it.
    That is the right way round — a runtime that cannot run the port at all is
    a fact the gate should say out loud — and it is why the message names the
    return code and the stderr instead of a category.
    """
    try:
        out = _drive(_payload(None))
    except OSError as exc:                      # no `node` on PATH at all
        return ("absent", f"node is not runnable here: {exc}")
    if out.returncode == 0:
        return None
    if "ERR_MODULE_NOT_FOUND" in out.stderr:
        return (
            "absent",
            f"the TypeScript port's dependencies are not installed "
            f"(`npm install` in {TS_DIR}): {out.stderr[-300:]}",
        )
    return (
        "broken",
        f"the second port exited {out.returncode} on a document with NO "
        f"`limits:` block. That is not a missing runtime — `run-trace.ts` "
        f"resolved its imports and then failed — and this file cannot compare "
        f"two ports when one of them does not run.\n{out.stderr[-2000:]}",
    )


UNAVAILABLE = _probe()


def _both_ports(written: dict[str, object]) -> tuple[dict, object]:
    """Run one authored `limits:` block through the TypeScript port and the
    reference port, and hand back both endings."""
    if UNAVAILABLE is not None:
        kind, why = UNAVAILABLE
        if kind == "absent":
            pytest.skip(why)
        pytest.fail(why)
    spec_payload = _payload(written)
    out = _drive(spec_payload)
    if out.returncode != 0:
        pytest.fail(
            f"the second port ran a document with no `limits:` block and then "
            f"exited {out.returncode} on `cost-per-request-under: "
            f"{written.get('cost-per-request-under')!r}`. That is this input "
            f"crashing it, not a missing runtime.\n{out.stderr[-2000:]}"
        )
    ts = json.loads(out.stdout)

    spec = replace(
        SPEC, max_steps=8, limits=Limits.from_mapping(written),
    )
    mine = asyncio.run(
        run(spec, ReferenceTransport(Script([Turn("done")])), "hello", {})
    )
    return ts, mine


def _block(written: str) -> dict[str, object]:
    return {"steps-at-most": 8, "cost-per-request-under": written,
            "when-it-runs-out": "stop-and-say-so"}


@pytest.mark.parametrize("written,currency", sorted(SPELLINGS.items()))
def test_both_ports_say_the_same_sentence_however_the_cap_was_written(
    written: str, currency: str,
) -> None:
    """The sentence a person reads, BYTE FOR BYTE, for each spelling."""
    ts, mine = _both_ports(_block(written))

    assert mine.halted == "cost-limit", f"`{written}` did not reach the cost ceiling: {mine.halted}"
    assert ts["halted"] == mine.halted, (written, ts["halted"], mine.halted)
    assert mine.stopped_by is not None
    said = mine.stopped_by.sentence()

    # The reference port is pinned first, so a divergence below is always a
    # statement about the SECOND port and never about a fixture that was wrong
    # all along.
    assert mine.stopped_by.ceiling.unit == currency, (
        f"the reference port read `{written}` as "
        f"{mine.stopped_by.ceiling.unit!r}, not {currency!r}"
    )
    assert said == ts["stoppedBy"]["sentence"], (
        f"`cost-per-request-under: {written}` is read differently by the two "
        f"ports, and the sentence is the contract.\n"
        f"  python: {said}\n"
        f"  node:   {ts['stoppedBy']['sentence']}"
    )
    if currency:
        assert f" {currency})" in said, (
            f"`{written}` should be reported in {currency}: {said}"
        )
    else:
        # No currency written, so no noun — and no stray space where one would go.
        assert said.endswith("(0 of 0)."), said


#: A cap whose AMOUNT is written in a form the second port's number test threw
#: out. `/^[0-9.]+$/` has no room for a sign and no room for an exponent, and
#: `float()` and `coerce::money`'s `parse::<f64>()` take both — so each of these
#: bound a run on one side and loaded as no cap at all on the other.
#:
#: `-inf USD` is here because widening the number test to the three non-finite
#: WORDS — which `float()` and `parse::<f64>()` both read — put a value through
#: the reporter that the reporter also disagreed about. `inf` and `nan` never
#: reach the sentence (nothing is `>=` either — `inf` is, but a meter never
#: reads it), but every spend is `>= -Infinity`, so a negative-infinity cap fires
#: on the first step and prints. Python's `f"{v:.4g}"` writes `-inf`; `String(v)`
#: in the second port wrote `-Infinity`. Reading the same cap and then naming it
#: differently is the same defect as reading it differently, one layer further on.
GRAMMAR = {
    "-5 JPY": "JPY",    # a sign. The typo `check_floor` calls "less than nothing".
    "0e0 JPY": "JPY",   # an exponent, pinned at a figure that binds.
    "-inf USD": "USD",  # a word, and the one non-finite cap a run can reach.
}


@pytest.mark.parametrize("written,currency", sorted(GRAMMAR.items()))
def test_a_cap_the_validator_can_read_is_a_cap_in_both_ports(
    written: str, currency: str,
) -> None:
    """A spend cap that binds on one side and vanishes on the other is worse
    than a currency named wrongly: the run does not stop at all.

    `coerce::money` parses these — it hands `Schema::check_floor` a
    `Coerced::Money` and *that* is where they are refused, by name, as *"less
    than nothing"* and *"which is no money at all"*. So the reader's job is to
    read what the validator reads, and the refusing is done one layer up.
    Measured through the shipped binary: `-5 JPY` and `0e0 JPY` are rc=1 on the
    currency rule and `-inf USD` is rc=1 *"is -inf USD, which is not an amount of
    money"*.

    They are therefore specs BUILT IN CODE, and that is a licence about the
    FIGURE and not about the reader: `Limits.reached` compares `at >= c.limit`,
    a scripted transport that spends nothing reads `0`, and so a cap at or below
    zero is the only one that puts a sentence in the report at all. The reader
    under test is the same reader either way — `10.005 USD` and `USD 10.005` are
    both `pact check` rc=0 — and the sentence is what is being compared.
    """
    ts, mine = _both_ports(_block(written))

    assert mine.halted == "cost-limit", (written, mine.halted)
    assert ts["halted"] == mine.halted, (
        f"`cost-per-request-under: {written}` is a ceiling in one port and not "
        f"in the other: python stopped on {mine.halted!r}, node on "
        f"{ts['halted']!r}"
    )
    assert mine.stopped_by is not None
    said = mine.stopped_by.sentence()
    assert said == ts["stoppedBy"]["sentence"], (
        f"`cost-per-request-under: {written}`\n  python: {said}\n"
        f"  node:   {ts['stoppedBy']['sentence']}"
    )
    assert f" {currency})" in said, said


#: A cap the two ports READ identically and then WROTE differently.
#:
#: Every fixture above this line is an integer or a non-finite word, so every one
#: of them takes `round()`'s `Number.isInteger` branch or its `inf`/`nan` branch
#: and NONE of them reaches the significant-digit code — which is why the
#: rounding half of `sentence()` was unheld while this file claimed to compare
#: the sentence. Python writes `f"{v:.4g}"`, which is C's `%g`: four significant
#: digits, ties to EVEN, and the tie is the double's EXACT value against the
#: decimal midpoint. The second port asked instead whether the p+1-digit
#: rendering round-TRIPPED to the same double, which is a different question and
#: parts from `%g` on ordinary money. Measured through the exported `sentence()`
#: against `Reached.sentence()`, with the old test restored::
#:
#:     -10.005   py '-10.01'   node '-10'
#:     -100.45   py '-100.5'   node '-100.4'
#:     -0.12345  py '-0.1235'  node '-0.1234'
#:     -1234.5   py '-1234'    node '-1234'   <- an exact tie, so it agreed
#:
#: `-1234.5` is kept as the row that must stay agreed: it is the case the
#: half-to-even rule exists FOR, and it is the only one of the four that IS an
#: exact binary midpoint. Measured — replacing the tie rule with
#: ``twiceRemainder >= den`` (half away from zero, what JavaScript does) reddens
#: `-1234.5` and nothing else, while the round-TRIP tie test reddens the other
#: three and not `-1234.5`. Two disjoint mutations, so a fixture set with only
#: one kind of amount in it would have held only one half of the rule.
#:
#: The amounts are negative for the reason `GRAMMAR` gives — a zero-spend
#: transport reaches no positive cap — and the ROUNDING they exercise is
#: reachable from a checked file: `cost-per-request-under: 10.005 USD`,
#: `0.12345 USD` and `1234.5 USD` are all `pact check` rc=0 on a copy of
#: `examples/refund-desk`, and `10.005 usd`, `USD 10.005` and `$10.005` are rc=0
#: too. The sign is what `check_floor` refuses; the digits are not.
ROUNDING = {
    "-10.005 USD": "-10.01",
    "-100.45 USD": "-100.5",
    "-0.12345 USD": "-0.1235",
    "-1234.5 USD": "-1234",
}


@pytest.mark.parametrize("written,figure", sorted(ROUNDING.items()))
def test_both_ports_write_the_same_figure_for_a_cap_that_is_not_a_whole_number(
    written: str, figure: str,
) -> None:
    """Reading one cap the same way and then printing it differently is the
    same defect as reading it differently, one layer further on — and it is the
    defect `-inf USD` caught for the non-finite arm of the same function while
    the finite arm went on diverging.
    """
    ts, mine = _both_ports(_block(written))

    assert mine.halted == "cost-limit", (written, mine.halted)
    assert ts["halted"] == mine.halted, (written, ts["halted"], mine.halted)
    assert mine.stopped_by is not None
    said = mine.stopped_by.sentence()

    # The reference port is pinned to C's `%g` first, so a divergence below is a
    # statement about the second port and not about a fixture that was guessed.
    assert f"(0 of {figure} USD)" in said, (
        f"the reference port wrote `{written}` as {said!r}, not {figure!r} — "
        f"`f\"{{v:.4g}}\"` is the standard here"
    )
    assert said == ts["stoppedBy"]["sentence"], (
        f"`cost-per-request-under: {written}` is READ the same by both ports "
        f"and WRITTEN differently, and the sentence is the contract.\n"
        f"  python: {said}\n"
        f"  node:   {ts['stoppedBy']['sentence']}"
    )


def test_no_port_invents_a_currency_out_of_a_word_the_validator_refuses() -> None:
    """`0 DOLLARS` names NOTHING, in both ports.

    `coerce::money` refuses a currency that is not exactly three ASCII letters,
    so `cost-per-request-under: 0.05 DOLLARS` cannot reach a run from a file at
    all — measured, rc=1 *"should be an amount of money, like `0.05 USD`, but it
    is some text"*. A reader that took `DOLLARS` anyway would print a currency no
    document can carry, and would then have to be un-invented in the report —
    which is the defect `spend()` exists to have fixed, one word further on.
    """
    ts, mine = _both_ports(_block("0 DOLLARS"))
    assert mine.stopped_by is not None
    said = mine.stopped_by.sentence()
    assert "DOLLARS" not in said, said
    assert "DOLLARS" not in json.dumps(ts), json.dumps(ts)[:400]
    assert said == ts["stoppedBy"]["sentence"], (said, ts["stoppedBy"]["sentence"])


#: Written amounts the VALIDATOR refuses, which therefore must be no ceiling in
#: EITHER port.
#:
#: These are the other half of the claim, and the half that was argued in two
#: directions in one file. `FIGURE`'s comment defended being narrower than
#: `float()` as *"exactly what the gate lets through"*; `SEPARATOR`'s comment
#: thirty lines earlier defended being WIDER than the gate *"so the two readers
#: agree rather than agreeing only where a document can reach"*. One trade-off,
#: two resolutions, and the `FIGURE` side left a measured divergence: `0_0 USD`,
#: `０ USD` and `٠ USD` each halted the reference port on `cost-limit` and ran
#: the second one to `final`.
#:
#: The rule is now the gate's, in both ports and in both comments, and every row
#: here is `pact check` rc=1 `schema/wrong-type` on a copy of
#: `examples/refund-desk` — measured, written with `0.05` in place of the `0`
#: where the floor would otherwise be the thing refusing it:
#:
#:   * `1_0 USD`, `０.05 USD`, `٠.05 USD` — the two things `float()` takes and
#:     `parse::<f64>()` does not: digit-group underscores and Unicode decimal
#:     digits that are not ASCII;
#:   * `0.05$` — `$` is a PREFIX and the remainder must be one whole number,
#:     which is `s.strip_prefix('$')` then `parse::<f64>().ok()?`. A global
#:     substitution invented `USD` out of a dollar sign ANYWHERE in the line;
#:   * `0.05 USD 0.05` — `coerce::money` returns `None` on a third token, and a
#:     reader that dropped the surplus in silence enforced a ceiling the gate
#:     had already refused, with nothing said on any honesty channel.
#:
#: **Every row here is one a single mutation reddens, and the AMOUNT is zero for
#: a reason.** A refused string with a POSITIVE amount cannot tell the two
#: readers apart on this route: a zero-spend transport never reaches `0.05`, so a
#: port that wrongly read `0.05$` as a cap would still run to `final` and the two
#: endings would agree. Measured — with the global `$` substitution restored and
#: `0.05$` as the fixture, this file stayed **20 passed**; with `0$` it goes red.
#: A row that cannot fail is the thing this file exists to have stopped.
#:
#: `$0.05 USD` is refused by the gate and by both readers as well, and is
#: deliberately NOT a row here under the same rule: the anchored arm and the
#: global substitution BOTH give no cap for it (three tokens either way), so no
#: single mutation parts them on it.
#:
#: `pact check` is not what makes these safe HERE, and that is the point: this
#: file's own fixtures never pass it, and `run-trace.ts` takes a payload straight
#: off argv with no gate anywhere. What makes them safe is that both readers
#: refuse them, so no route can produce a cap in one port and none in the other.
REFUSED = (
    "0_0 USD",
    "\uff10 USD",  # FULLWIDTH DIGIT ZERO, written as an escape for the
    "\u0660 USD",  # ARABIC-INDIC DIGIT ZERO, same reason the NEL row is
    "0$",
    "0 USD 0",
)


@pytest.mark.parametrize("written", REFUSED)
def test_an_amount_the_gate_refuses_is_no_ceiling_in_either_port(written: str) -> None:
    """A ceiling in one port and none in the other, on a line no document can
    carry — the failure the `GRAMMAR` test's own message calls worse than a
    wrong noun, reached through the route that has no gate on it.

    Both readers refuse these, so the run finishes normally in both. The
    assertion is on BOTH halves: that the reference port did not build a cost
    ceiling out of it, and that the two ports ended the same way. Checking only
    the second would pass if both ports started reading it.
    """
    ts, mine = _both_ports(_block(written))

    assert mine.halted != "cost-limit", (
        f"the reference port built a spend ceiling out of "
        f"`cost-per-request-under: {written}`, which `pact check` refuses as "
        f"`schema/wrong-type`. Enforcing a cap the gate would not accept is a "
        f"silent degradation, and no channel reports it."
    )
    assert ts["halted"] == mine.halted, (
        f"`cost-per-request-under: {written}` is a ceiling in one port and not "
        f"in the other: python stopped on {mine.halted!r}, node on "
        f"{ts['halted']!r}"
    )
    assert mine.stopped_by is None or mine.stopped_by.ceiling.reads != "money"
    assert ts["stoppedBy"] is None or ts["stoppedBy"]["limit"] != "cost-per-request-under"
