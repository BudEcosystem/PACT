"""Every tick `pact check` accepts is a tick every reader in this port acts on.

`crates/pact-schema/src/coerce.rs::yes_no` is the door an author's `yes-no` line
comes through, and it takes five spellings: `yes`, `y`, `true`, `on`, `enabled`.
Whatever it lets past is a line the author has written and the checker has told
them is fine. This port then read that line back FIVE separate times, with five
private word-lists, and three of them were different from the checker's:

    facts._yes                  yes true on 1        `survives-shortening:`
    egress._yes                 yes true on y        `needs: audio:`
    resolve._yes                yes true on y        `needs: images/audio/computer-use:`
    ir.py (must_cite)           yes true on y        `must-cite:`
    scoring.py (spends-money)   yes true on          `spends-money:`
    questions._needs_a_person   yes y true on enabled  `needs-a-person:`   <- the only one right

Measured on the shipped tree, on copies of `examples/refund-desk` with one word
changed and driven through the real `pact check` / `pact show`:

    spelling   pact check   fact survives   needs images   spends-money seen
    yes        OK           True            True           True
    y          OK           FALSE           True           FALSE
    enabled    OK           FALSE           FALSE          FALSE
    1          REFUSED      -               -              -

So `enabled` — a word the checker prints `OK` for — silently switched off every
one of these guarantees, and `y` switched off two of them. That is the live
defect. `1` is the other direction and is LATENT, not live: `facts._yes` alone
took it, and `pact check` refuses `images: 1` with `schema/wrong-type` before
this port is handed anything, so no document that ever passed the checker could
reach that arm. The fix removes it anyway — a reader more generous than the
checker is a second, unwritten specification.

What each of those falses costs, in the author's terms:

* `survives-shortening: enabled` — the approval a `policy:` gate reads is
  destroyed by the next summary, and the gate then decides on nothing. The
  schema's own help says *"say yes for anything a rule later checks"*.
* `needs: images: enabled` — the model filter drops the requirement, and an
  agent that has to look at a photo of a damaged item is recommended a model
  that cannot see.
* `spends-money: enabled` — worse than a silent Python bug, because the RUST
  half reads this field through `coerce::check` (`pact-loader::money::moves_money`,
  whose own comment says *"a tick the checker does not recognise is an ungated
  spend it reports as fine"*). So `pact check` calls the action money-moving and
  demands a gate on it, and this port's money-moving subset comes back empty:
  the two halves disagree about which actions spend money.

The fix is one predicate, `pact_adapters.yes_no.said_yes`, holding exactly the
words `coerce.rs::yes_no` holds. This test does not call it. It writes documents,
runs the shipped checker over them, and asserts the guarantee the author bought
actually holds — because call sites agreeing is only worth something if what they
agree on is what the checker accepted.

TWO MORE READERS, and one more PORT, found by a review of the first version of
this file, which had enumerated five and asserted completeness:

* `settings.parallel-tool-calls:` reached nothing. `ir.py` carried the author's
  `settings:` block through raw, so `enabled` raised a pydantic
  `ValidationError` out of `agents.model_settings.ModelSettings` — killing a run
  over a line `pact check` printed `OK` for — and `no` went on the wire to
  `chat.completions.create(parallel_tool_calls="no")`, a truthy string and the
  opposite of what the author wrote. Nothing caught it because the two settings
  tests set `"parallel-tool-calls": False`, a Python bool constructed straight
  into an `AgentSpec` and a value no author can type.
* `needs-a-person:` was asserted by calling `_needs_a_person` on a hand-built
  dict — the exact shape the paragraph above disclaims. It is written into the
  tree now and read back through `gated_actions`.
* `must-cite:` in the TypeScript port kept a two-word, case-sensitive list
  (`=== true || String(...) === "yes"`) against the checker's five. Four
  spellings out of five made the second port ANSWER a turn the reference port
  refused, citing a corpus it never opened, on a field §7.28 lists as carried
  out identically. The cross-port driver could not see it: it sends the Python
  side's already-parsed boolean, so the second port's own reading of the line
  was never exercised. The raw authored word crosses in this file instead.

Mutations, all four confirmed:

* Restore any one of the divergent copies — e.g. put `return
  str(v).strip().lower() in {"yes", "true", "on", "1"}` back in `facts.py`, or
  drop `"enabled"` from the set in `yes_no.py`. Without it,
  `..._is_one_every_reader_acts_on` goes red naming the reader that dropped it.
* Put `settings={k: v for k, v in ...}` back in `ir.py`. Without it, seven cases
  go red, one of them inside pydantic's own validator.
* Put `k["must-cite"] === true || String(...) === "yes"` back in `harness.ts`.
  Without it, six `..._the_second_port_reads_a_tick...` cases go red.
* Add a second true arm to `coerce.rs::yes_no` (`"ok" | "tick" => Some(true),`).
  Without the whole-body parse in `_rust_vocabulary`, the drift guard read only
  the FIRST matching line and stayed green while `pact check` accepted
  `spends-money: ok` and `_money_moving_actions` returned an empty set.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters import egress  # noqa: E402
from pact_adapters.ir import TICKS_IN_SETTINGS, AgentSpec  # noqa: E402
from pact_adapters.questions import _needs_a_person, gated_actions  # noqa: E402
from pact_adapters.resolve import TOOL_CALLING, needs_of  # noqa: E402
from pact_adapters.scoring import _money_moving_actions  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
REFUND_DESK = REPO / "examples" / "refund-desk"
DOCUMENTS = REPO / "examples" / "answers-from-documents"
PACT_BIN = REPO / "target" / "debug" / "pact"

#: Every spelling `coerce.rs::yes_no` reads as a yes, plus two capitalisations,
#: because that reader lowercases and so must this port. Held to the Rust list by
#: `test_the_words_this_port_takes_are_the_words_the_checker_takes` below.
TICKS = ("yes", "y", "true", "on", "enabled", "Yes", "ENABLED")

#: And the other half of the same door. None of these may switch anything on.
CROSSES = ("no", "n", "false", "off", "disabled", "No")


def _built() -> None:
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")


def _tree(tmp: Path, source: Path, edits: dict[str, list[tuple[str, str]]]) -> Path:
    """A copy of a worked example with some words changed, on disk.

    `edits` is `relative file -> [(the line as shipped, the line to write)]`. The
    whole line is matched so a substitution cannot land in a comment that happens
    to quote the same word.
    """
    root = tmp / source.name
    shutil.copytree(source, root, dirs_exist_ok=True)
    for relative, swaps in edits.items():
        path = root / relative
        text = path.read_text()
        for before, after in swaps:
            assert before in text, (
                f"{relative} no longer contains `{before.strip()}` — this test "
                f"edits the worked example and the example has moved on"
            )
            text = text.replace(before, after)
        path.write_text(text)
    return root


def _checked(root: Path) -> dict[str, Any]:
    """`pact check` must pass, then `pact show` is what this port is handed.

    The check is an assertion, not a formality: the whole claim is about lines the
    author was TOLD were fine, so a spelling the checker refuses proves nothing
    about a reader downstream.
    """
    checked = subprocess.run(
        [str(PACT_BIN), "check", str(root)], capture_output=True, text=True
    )
    assert checked.returncode == 0, (
        f"`pact check` refused this document, so it says nothing about what the "
        f"readers do with it:\n{checked.stdout}{checked.stderr}"
    )
    shown = subprocess.run(
        [str(PACT_BIN), "show", str(root)], capture_output=True, text=True, check=True
    )
    return json.loads(shown.stdout)


def _every_reader(tmp: Path, spelling: str) -> dict[str, bool]:
    """One word, written on every `yes-no` line this port reads, read back.

    SEVEN lines now, not five. `needs-a-person:` and `settings.parallel-tool-
    calls:` were added after a reviewer showed that neither was driven through a
    document — the first was asserted by calling `_needs_a_person` on a
    hand-built dict, which is the shape this file's own headline docstring
    disclaims, and the second was not asserted at all and was broken.
    """
    _built()
    desk = _tree(
        tmp / spelling.lower() / "a",
        REFUND_DESK,
        {
            "agents/refund-desk/agent.yaml": [
                ("    survives-shortening: yes", f"    survives-shortening: {spelling}"),
                # `settings:` is not in the worked example. `parallel-tool-calls`
                # is the group's one `yes-no` key and it reaches the SDKs, so the
                # block has to be added to reach that reader at all.
                (
                    "\npolicy: approvals",
                    f"\nsettings:\n  parallel-tool-calls: {spelling}\n"
                    f"\npolicy: approvals",
                ),
            ],
            "agents/refund-desk/needs.yaml": [
                ("images: yes ", f"images: {spelling} "),
                # `audio:` is not in the worked example, and `egress.carried` is
                # the only reader of it — so the line has to be added to reach
                # that reader at all.
                ("context-at-least: 32k", f"audio: {spelling}\ncontext-at-least: 32k"),
            ],
            "tools/payments.yaml": [
                ("    spends-money: yes", f"    spends-money: {spelling}"),
                # On `look-up-order`, NOT on `issue-refund`: a written rule in
                # `policies/approvals.yaml` already gates the refund, and
                # `gated_actions` leaves a ruled action out on purpose ("the
                # expert path wins"). Written on the gated one this would assert
                # nothing, and `pact check` says so — `loader/asked-for-twice`.
                ("    reads-only: yes", f"    reads-only: yes\n    needs-a-person: {spelling}"),
            ],
        },
    )
    doc = _checked(desk)
    spec = AgentSpec.from_document(doc, "refund-desk")
    agent = (doc.get("agents") or {})["refund-desk"]

    handbook = _tree(
        tmp / spelling.lower() / "b",
        DOCUMENTS,
        {"knowledge/staff-handbook/staff-handbook.yaml": [
            ("must-cite: yes", f"must-cite: {spelling}")
        ]},
    )
    desk_spec = AgentSpec.from_document(_checked(handbook), "helpdesk")

    return {
        # facts.py — the approval a `policy:` reads outlives the summary.
        #
        # Read off the FLAG, not off membership. Every declared `remembers:`
        # entry is held now, because `bind: remembers.<n>` and `remember-as:`
        # read and write the agent's memory and there has to be a memory for them
        # to reach; what this word decides, and always decided, is whether a
        # shortening puts the fact back.
        "survives-shortening": any(
            f.name == "payments-was-approved" and f.survives
            for f in spec.facts.declared.values()
        ),
        # resolve.py — the model filter keeps the requirement.
        "needs.images": "images" in needs_of(doc, "refund-desk")["capabilities"],
        # egress.py — speech is recognised as crossing the boundary.
        "needs.audio": any(
            roles == ("stt", "tts") for roles, _line in egress.carried(agent)
        ),
        # scoring.py — the action is in the money-moving subset.
        "spends-money": "payments/issue-refund" in _money_moving_actions(doc, spec),
        # questions.py — a person is actually asked before the action runs.
        # Through `gated_actions` and the document, not through `_needs_a_person`
        # and a dict: a hand-built mapping proves the predicate agrees with
        # itself, which is what six agreeing predicates already proved.
        "needs-a-person": "payments/look-up-order" in {
            g.named for g in gated_actions(doc, "refund-desk")
        },
        # ir.py — the author's `settings:` block becomes a real boolean before
        # any SDK is handed it. `is True`, not truthiness: `"enabled"` is truthy
        # and is what crashed `agents.model_settings.ModelSettings`, and `"no"`
        # is truthy and is the OPPOSITE of what the author wrote.
        "settings.parallel-tool-calls": spec.settings.get("parallel-tool-calls") is True,
        # ir.py — the corpus that must be cited says so.
        "must-cite": any(k.must_cite for k in desk_spec.knowledge),
    }


@pytest.mark.parametrize("spelling", TICKS)
def test_every_tick_the_checker_accepts_is_one_every_reader_acts_on(
    tmp_path: Path, spelling: str
) -> None:
    """`enabled` was `OK` at the checker and off at all five readers.

    One word per run, written on all five lines, and every guarantee it buys
    asserted through the thing that grants it — not by calling a predicate five
    times, which is what five agreeing predicates would prove and is not the
    question. A reader that stops honouring a spelling the checker prints `OK`
    for has taken a guarantee away from an author who was told they had it.
    """
    read = _every_reader(tmp_path, spelling)
    dropped = sorted(field for field, honoured in read.items() if not honoured)
    assert not dropped, (
        f"`pact check` accepted `{spelling}` and printed OK, and then "
        f"{dropped} was read as though the author had never written the line. "
        f"The five readers must hold exactly the words "
        f"`crates/pact-schema/src/coerce.rs::yes_no` holds."
    )


@pytest.mark.parametrize("spelling", CROSSES)
def test_no_word_the_checker_reads_as_a_no_switches_anything_on(
    tmp_path: Path, spelling: str
) -> None:
    """The control arm, and the half that would make a shared predicate dangerous.

    One predicate is only an improvement if it is the RIGHT one. A reader that
    said yes to `disabled` would be the same defect with the sign flipped —
    `spends-money: no` becoming a money-moving action, `needs-a-person: off`
    becoming a gate. `coerce.rs::yes_no` reads all six of these as a no, so every
    reader here must too.
    """
    read = _every_reader(tmp_path, spelling)
    switched = sorted(field for field, honoured in read.items() if honoured)
    assert not switched, (
        f"`{spelling}` is a NO to `coerce.rs::yes_no`, and {switched} treated it "
        f"as a yes"
    )


def test_a_word_the_checker_refuses_never_reaches_a_reader_at_all(
    tmp_path: Path,
) -> None:
    """`1` is where the drift pointed the other way, and it is LATENT, not live.

    `facts._yes` was the one copy that took `1`, so `survives-shortening: 1` read
    as a yes there while `needs: images: 1` read as a no two modules over. Neither
    was reachable: `1` is not a `yes-no` to the checker, so a document containing
    one never becomes a document this port is handed. This test is what stops that
    being rediscovered as a defect, and what stops a reader being made generous
    again on the grounds that "an author might write it" — if they write it, they
    are told, at their own line, before anything runs.
    """
    _built()
    root = _tree(
        tmp_path,
        REFUND_DESK,
        {"agents/refund-desk/needs.yaml": [("images: yes ", "images: 1 ")]},
    )
    refused = subprocess.run(
        [str(PACT_BIN), "check", str(root)], capture_output=True, text=True
    )
    assert refused.returncode != 0, "`images: 1` must not load"
    assert "schema/wrong-type" in refused.stdout, refused.stdout
    assert "Write `yes` or `no`." in refused.stdout, (
        "and the fix line must show the author what to type instead"
    )


def _rust_vocabulary() -> dict[str, set[str]]:
    """The WHOLE of `coerce.rs::yes_no`, both arms, sliced out of the source.

    The first version of this helper was one line — `next(raw for raw in
    source.splitlines() if "=> Some(true)" in raw and '"yes"' in raw)` — and a
    reviewer killed it in the obvious way: they added a SECOND true arm
    (`"ok" | "tick" => Some(true),`) below the first, rebuilt, and `pact check`
    accepted `spends-money: ok` while `_money_moving_actions` returned an empty
    set. Sixteen tests in this file passed. That is the D6 defect back, whole,
    with the guard against it green — because a guard that reads one line of a
    match only ever guards that line.

    So the function BODY is sliced, from `fn yes_no(` to its closing brace, and
    every arm mapping to `Some(true)` and to `Some(false)` is collected. Both
    directions, because a word MOVED from the true list to the false list is the
    same drift with the sign flipped: `spends-money: on` becoming a no would
    take the gate off a payment rather than putting one where none was wanted.
    """
    source = (REPO / "crates" / "pact-schema" / "src" / "coerce.rs").read_text()
    start = source.index("fn yes_no(")
    opened = source.index("{", start)
    depth, end = 0, opened
    for i in range(opened, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    body = source[opened : end + 1]
    said: dict[str, set[str]] = {"true": set(), "false": set()}
    for arm in re.finditer(r'((?:\s*"[a-z0-9]+"\s*\|)*\s*"[a-z0-9]+")\s*=>\s*Some\((true|false)\)', body):
        said[arm.group(2)] |= {w.strip().strip('"') for w in arm.group(1).split("|")}
    return said


def test_the_words_this_port_takes_are_the_words_the_checker_takes() -> None:
    """One list, read off the Rust source that is the authority for it.

    The six readers now share `said_yes`, so they cannot disagree with each
    other. That is half the defect. The other half is disagreeing with the
    CHECKER, which no amount of sharing inside this port would catch — all six
    were wrong about `enabled` together. So the words are read out of
    `coerce.rs` itself and compared, and a spelling added on either side without
    the other fails here.

    Read `_rust_vocabulary` for why this parses the whole match and not the one
    line it used to.
    """
    from pact_adapters.yes_no import TICKS, said_yes

    rust = _rust_vocabulary()
    assert rust["true"] == {"yes", "y", "true", "on", "enabled"}, (
        f"`coerce.rs::yes_no` now reads {sorted(rust['true'])} as a yes; this "
        f"port's `said_yes` has to be changed with it"
    )
    assert rust["false"] == {"no", "n", "false", "off", "disabled"}, (
        f"`coerce.rs::yes_no` now reads {sorted(rust['false'])} as a no"
    )
    # Equality, not membership. A sixth word added HERE and not there would make
    # this port honour a line `pact check` refuses — the generosity the fix
    # removed from `facts._yes` — and a one-way `for word in rust` check would
    # let it through.
    assert set(TICKS) == rust["true"], (
        f"`yes_no.TICKS` is {sorted(TICKS)} and `coerce.rs::yes_no` takes "
        f"{sorted(rust['true'])}; the checker is the authority for this list"
    )
    for word in rust["true"]:
        assert said_yes(word), f"the checker takes `{word}` and this port does not"
    for word in rust["false"]:
        assert not said_yes(word), f"`{word}` is a no at the checker and a yes here"


def test_the_settings_keys_this_port_ticks_are_the_ones_the_schema_types_yes_no() -> None:
    """A one-entry table is the kind that goes stale, so it is pinned.

    `ir.TICKS_IN_SETTINGS` holds `parallel-tool-calls` because that is the one
    key of the `settings:` group `spec/schema.yaml` types `yes-no`. A second one
    added to the schema and not to that frozenset would arrive at the SDKs as the
    author's raw word again — which is the defect this file exists about, exactly
    once removed.
    """
    yaml = pytest.importorskip("yaml")
    fields = yaml.safe_load((REPO / "spec" / "schema.yaml").read_text())
    ticks = {
        name
        for name, written in fields["groups"]["settings"]["fields"].items()
        if isinstance(written, dict) and written.get("type") == "yes-no"
    }
    assert ticks == set(TICKS_IN_SETTINGS), (
        f"`spec/schema.yaml`'s `settings:` group types {sorted(ticks)} as "
        f"`yes-no` and `ir.TICKS_IN_SETTINGS` holds "
        f"{sorted(TICKS_IN_SETTINGS)}; a key in the first and not the second "
        f"reaches the SDKs as the author's raw word"
    )


def test_the_one_of_beside_the_ticks_is_no_wider_than_the_schema(tmp_path: Path) -> None:
    """The word-list next door, which the same argument covers.

    `resolve.needs_of` reads `needs.tool-calling:` two lines above the ticks, and
    it is deliberately NOT a `yes-no` — `spec/schema.yaml` types it
    `one-of: [no, yes, parallel]`, because `parallel` is a third answer and not a
    stronger tick. It held a FOURTH word, `true`, left behind when this file's
    `_yes` was removed from around it, and `pact check` refuses that word at the
    author's own line. So the reader was more generous than the checker in
    exactly the way `yes_no.py`'s docstring says a reader must never be.

    Both halves asserted: the checker really does refuse it (otherwise removing
    it would be taking a spelling away from an author who can write it), and the
    list this port holds is the list the schema publishes.
    """
    _built()
    yaml = pytest.importorskip("yaml")
    fields = yaml.safe_load((REPO / "spec" / "schema.yaml").read_text())
    # The `needs` group, not `model-can` — a different `tool-calling:` with
    # `choices: [none, single, parallel]`, which this line does not read.
    #
    # And read through PyYAML's core schema, which turns the schema file's own
    # `no` and `yes` into `False` and `True`. The Rust loader keeps the author's
    # text, so the words are put back: comparing against `{False, True,
    # 'parallel'}` would pin this port to a quirk of the test's YAML reader
    # rather than to what the checker offers the author.
    choices = {
        {False: "no", True: "yes"}.get(c, c)
        for c in fields["groups"]["needs"]["fields"]["tool-calling"]["choices"]
    }
    assert choices == set(TOOL_CALLING), (
        f"`spec/schema.yaml` offers {sorted(choices)} and `resolve.TOOL_CALLING` "
        f"holds {sorted(TOOL_CALLING)}. If a fourth choice was added, decide "
        f"whether it means the model must be able to call tools — `needs_of` "
        f"reads everything but `no` as though it does."
    )

    root = _tree(
        tmp_path,
        REFUND_DESK,
        {"agents/refund-desk/needs.yaml": [("tool-calling: yes", "tool-calling: true")]},
    )
    refused = subprocess.run(
        [str(PACT_BIN), "check", str(root)], capture_output=True, text=True
    )
    assert refused.returncode != 0, "`tool-calling: true` must not load"
    assert "should be one of: no, yes, parallel" in refused.stdout, refused.stdout


def test_the_authored_word_reaches_the_agents_sdk_as_a_boolean(tmp_path: Path) -> None:
    """The blocking half of this defect, driven to the seam that crashed.

    `agents.model_settings.ModelSettings` is a *pydantic* dataclass whose
    `parallel_tool_calls` field is typed `bool | None`. Before the fix,
    `settings_for` copied the author's word onto it verbatim
    (`openai_agents_transport.py`, `_FIELDS[k]: v`) and the measurement was:

        'yes' -> True   'y' -> True   'true' -> True   'on' -> True
        'enabled' -> ValidationError
        'no' -> False   'n' -> False  'false' -> False 'off' -> False
        'disabled' -> ValidationError

    The eight that worked worked by pydantic's own `bool_parsing`, and the two
    that did not took down a run over a line `pact check` had printed `OK` for.

    Driven from a YAML file through the real `pact check` and `pact show`, not
    from a bool literal: `test_what_the_author_asked_for_reaches_the_agents_sdks
    _settings.py` sets `"parallel-tool-calls": False` straight into an
    `AgentSpec`, which is a value no author can type, and that is precisely why
    nothing caught this.
    """
    _built()
    pytest.importorskip("agents", reason="the OpenAI Agents SDK is not installed here")
    from agents.model_settings import ModelSettings

    from pact_adapters.script import Script, Turn
    from pact_adapters.transports.openai_agents_transport import OpenAIAgentsTransport

    for spelling, meant in (("enabled", True), ("y", True), ("disabled", False),
                            ("off", False), ("Yes", True)):
        root = _tree(
            tmp_path / spelling,
            REFUND_DESK,
            {"agents/refund-desk/agent.yaml": [(
                "\npolicy: approvals",
                f"\nsettings:\n  parallel-tool-calls: {spelling}\n\npolicy: approvals",
            )]},
        )
        spec = AgentSpec.from_document(_checked(root), "refund-desk")
        transport = OpenAIAgentsTransport(Script([Turn("Decision: approved.")]))
        transport.apply_settings(spec.settings)
        got = transport.settings_for(("payments",))
        assert isinstance(got, ModelSettings)
        assert got.parallel_tool_calls is meant, (
            f"the author wrote `parallel-tool-calls: {spelling}`, `pact check` "
            f"said OK, and the SDK was handed "
            f"{got.parallel_tool_calls!r} rather than {meant}"
        )


TS_DIR = REPO / "adapters" / "typescript"


def _node_halted(must_cite: Any) -> str:
    """`must-cite:` as the AUTHOR wrote it, through the second port, unparsed.

    The load-bearing word is *unparsed*. The existing cross-port driver
    (`test_a_corpus_the_second_port_never_looked_in_is_not_silent.py`) sends
    `"must-cite": k.must_cite` — the reference port's already-decided boolean —
    so the only thing the second port's own reading of the line was ever shown
    was `true` and `false`. Two ports compared through a value one of them has
    normalised cannot disagree about how to normalise it, which is why the
    divergence below survived a conformance suite that names this exact field.
    """
    payload = json.dumps({
        "name": "helpdesk",
        "instructions": "Answer from the handbook.",
        "tools": [],
        "maxSteps": 4,
        "knowledge": [{
            "name": "staff-handbook", "description": "the staff handbook",
            "must-cite": must_cite,
        }],
    })
    out = subprocess.run(
        ["node", "--experimental-strip-types", "src/run-trace.ts",
         payload, json.dumps({"turns": [{"text": "25 days."}]}),
         "how long is the notice period?", "{}"],
        cwd=TS_DIR, capture_output=True, text=True,
    )
    if out.returncode != 0:
        pytest.skip(f"node/AI SDK unavailable: {out.stderr[-300:]}")
    return str(json.loads(out.stdout)["halted"])


@pytest.mark.parametrize("spelling", TICKS)
def test_the_second_port_reads_a_tick_the_way_the_checker_wrote_it(spelling: str) -> None:
    """The sixth private copy, and the only one outside this port.

    `harness.ts` filtered on `k["must-cite"] === true || String(...) === "yes"` —
    two spellings, case-sensitive, against the checker's five. Measured on
    `examples/answers-from-documents` with the authored word carried across raw:

        yes      PY no-sources   NODE no-sources
        enabled  PY no-sources   NODE final  "25 days."
        y        PY no-sources   NODE final  "25 days."
        on       PY no-sources   NODE final  "25 days."
        Yes      PY no-sources   NODE final  "25 days."

    `must-cite:` is in §7.28's list A — carried out IDENTICALLY by both ports —
    and on four spellings out of five the second port did the opposite: it
    answered from the model's own memory, citing a corpus it never opened, which
    `harness.ts`'s own comment calls *"the worst outcome available and the one
    that looks most like success"*.

    Asserted against `no-sources` literally rather than against a Python run of
    the same spelling, because the reference port's answer here is not in doubt
    — `TICKS` is the checker's own list — and a second subprocess per spelling
    would buy nothing but time.
    """
    assert _node_halted(spelling) == "no-sources", (
        f"`pact check` accepts `must-cite: {spelling}` and the reference port "
        f"refuses the turn; the second port answered anyway, out of what the "
        f"model already knew, citing documents it never opened"
    )


@pytest.mark.parametrize("spelling", CROSSES)
def test_the_second_port_reads_a_crossed_line_the_way_the_checker_wrote_it(
    spelling: str,
) -> None:
    """The control arm on the other port. A `no` must not refuse the turn.

    A `saidYes` that said yes to `disabled` would fail every run over an
    ordinary corpus — declared, never retrieved, and not required to be cited,
    which is the ordinary enterprise shape.
    """
    assert _node_halted(spelling) == "final", (
        f"`must-cite: {spelling}` is a NO to `coerce.rs::yes_no`, and the second "
        f"port refused the turn as though a citation had been demanded"
    )


def test_both_ports_hold_the_same_five_words_as_the_checker() -> None:
    """Three lists, one authority. The Rust match is the authority.

    The TypeScript port has no test runner of its own — `package.json` has
    `typecheck` and `trace` and nothing else — so a guard living beside
    `yes-no.ts` would be a guard nothing runs. It lives here, where the Python
    suite already reads `coerce.rs`, and reads the TS list the same way it reads
    the Rust one: out of the source that is the authority for it.
    """
    rust = _rust_vocabulary()["true"]

    from pact_adapters.yes_no import TICKS as PY_TICKS

    source = (TS_DIR / "src" / "yes-no.ts").read_text()
    written = re.search(r"export const TICKS[^=]*=\s*\[([^\]]*)\]", source)
    assert written is not None, "`yes-no.ts` no longer exports a TICKS array"
    ts = {word.strip().strip('"').strip("'") for word in written.group(1).split(",") if word.strip()}

    assert ts == rust == set(PY_TICKS), (
        f"the checker takes {sorted(rust)}, the reference port takes "
        f"{sorted(PY_TICKS)} and the second port takes {sorted(ts)}; a word in "
        f"one and not another is a document that means two things"
    )


def test_the_reader_a_person_types_at_is_deliberately_not_this_one() -> None:
    """`questions._YES` is a different question and keeps its own wider list.

    An APPROVER typing into a prompt writes `approve`, `granted`, `ok`. An
    AUTHOR writing `spends-money:` in a file writes what `pact check` accepts and
    is refused at their own line otherwise. Folding the two together would make
    `spends-money: approve` a money-moving action that the checker refuses — one
    predicate for two questions is the same defect this file removes, arrived at
    from the other side.
    """
    from pact_adapters.questions import _YES
    from pact_adapters.yes_no import said_yes

    assert "approve" in _YES and "granted" in _YES
    assert not said_yes("approve"), (
        "a person's word of consent is not a word an author may write in a file"
    )
    # `needs-a-person:` is an AUTHORED line, so it goes through the shared reader.
    assert _needs_a_person({"needs-a-person": "enabled"}) is True
    assert _needs_a_person({"needs-a-person": "approve"}) is False
