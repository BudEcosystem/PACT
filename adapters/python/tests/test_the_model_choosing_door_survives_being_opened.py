"""`--choose-model` is the door onto D11 — fail, then recommend — and opening it
raised a `TypeError` out of the middle of the search.

Measured, before the fix, from the repository root:

```text
$ env -i PYTHONPATH=adapters/python/src PATH=/usr/bin:/bin python3 -c \
    "from pact_adapters.scoring import main; raise SystemExit(main( \
     ['examples/refund-desk','--choose-model','--serving-at','http://127.0.0.1:9/v1']))"
Traceback (most recent call last):
  ...
  File ".../pact_adapters/resolve.py", line 1012, in evaluate
    transport = transport_for(model, strategy_name)
TypeError: _choose.<locals>.<lambda>() takes 1 positional argument but 2 were given
```

Three separate things had to be true for that, and this file holds all three:

* `_choose` built a ONE-argument factory for the two-argument `TransportFactory`
  protocol `resolve.evaluate` calls (`(model_name, strategy_name)`). The flag
  parsed, the help text advertised it, and the capability behind it could not be
  reached even once;
* with the arity fixed the door STILL ended in a stack, because the search walks
  the catalogue and on a machine serving nothing every candidate refuses the
  connection. A refusal is a sentence, not a traceback (D13), so an unreachable
  model is now a caught non-result inside `evaluate` — the same reading
  `scoring._run_every_case` already gives one;
* and the refusal has to say WHICH thing happened. A row that answered badly and
  a row that never answered are two different facts with two different things for
  the author to go and do — edit the suite, or start a runtime — and the first
  version of this fix printed the second as the first whenever any other row
  answered. That is the ordinary shape on a real box: one model pulled, the rest
  of the catalogue not.

The existing reachability test for this flag asserted the STRING `resolve(`
appeared after `def _choose(` in the source. It did, throughout, while the call
it named could not complete — which is how this shipped. It has been replaced by
the executions here; `test_what_the_author_wrote_reaches_the_run.py` names this
file so that deleting it is visible from there.

AND OPENING THE DOOR TURNED OUT TO OPEN MORE THAN THE DOOR. Everything from
`test_a_teammate_the_agent_asks_is_run_rather_than_parked` down was written
against the LANDED fix rather than against the original crash, because a search
that could not connect could not be wrong about anything either. Once it really
dials:

* the search sent the agent's system prompt and the author's eval cases to an
  off-box `--serving-at` out of a workspace whose `allow-egress:` is `[]` —
  measured at 36 requests to a listener on this machine's LAN address — because
  the egress guard lives in `_bind`, which `score()` calls AFTER `_choose`. A
  guard-ordering defect that was unreachable while the arity crash held it shut;
* `resolve.evaluate` built no `ask_member`, so every delegation of an agent with
  a `team:` parked instead of asking and came back as an empty answer. The
  worked example this file runs against has a `team:` of two, and the measured
  effect was every case failing with `expected decision 'approved', got ''`;
* `except Exception` filed a defect in our own program, and `harness`'s own
  deliberate `RuntimeError`s, as "the model did not answer" — and the sentence
  one level up turned that into "this machine is not serving them. Start the
  model runtime", which is a remedy for a machine that is already running;
* a row that answered three of six cases and then stopped was indistinguishable
  from one that never opened a socket, so an author whose runtime was serving
  the model perfectly well was told it was not;
* and the flag could only ever bind the model the agent already named. Its help
  said it would "bind the first that passes the bar"; the search ran every case
  against a row that passed at 83% and then refused with an error.

ELEVEN MUTATIONS, each applied by hand, observed red, reverted, and observed
green again. One per thing this change claims, because a fix with five parts and
one mutation has four parts nobody checked.

1. Restore `transport_for=lambda name: _transport_for(name, serving_at, root)()`
   in `scoring._choose` in place of the two-parameter `transport_for`. FIVE of
   the seven tests here go red on
   `TypeError: _choose.<locals>.<lambda>() takes 1 positional argument but 2
   were given`, in a traceback on stderr. Without it they are green.

2. Make the `except` around `asyncio.run(run(...))` in `resolve.evaluate`
   unreachable, so the connection error propagates. Four go red with
   `httpx.ConnectError: All connection attempts failed` in a traceback. This is
   recorded separately because the arity fix ALONE leaves the door crashing, so
   mutation 1 does not cover it.

3. In `resolve._cheapest_passing`, fold the quiet rows back into the count —
   `len(tried)` for `len(measured)` — and drop the sentence that names them.
   Only `test_a_row_that_never_answered_is_not_reported_as_one_that_missed_the_bar`
   goes red: the refusal reports a model as having missed a bar it was never
   measured against.

4. Seed `heard = False` instead of `heard = not strategies` in the same
   function. Only `test_a_caller_who_asked_for_no_strategies_is_not_told_the_box_
   is_silent` goes red — a search that opened no socket claiming the machine
   serves nothing.

5. Disable the `UNDECIDED and not results` branch in `PortabilityReport.render`.
   Only `test_a_model_that_never_answered_is_not_given_a_score` goes red, on
   `score 0%` being printed for a model nobody reached.

6. Disable the `transport_for is None` guard at the top of `resolve`. Only
   `test_the_search_refuses_without_a_way_to_run_anything` goes red. That guard
   had no coverage at all when it was first written, which is the same fault as
   the source-grep it was written next to.

7. Drop `ask_member=ask_member` from the `run(...)` call in `resolve.evaluate`.
   Only `test_a_teammate_the_agent_asks_is_run_rather_than_parked` goes red, on
   a case that came back `got ''` — the parked delegation, scored as the model's
   answer.

8. Widen `except Exception as stopped:` in `resolve.evaluate` back to swallowing
   everything — i.e. delete the `if reading is None: raise`. TWO go red:
   `test_a_defect_in_our_own_program_is_never_reported_as_a_machine_that_is_not_
   serving` and, once the transport build is also moved inside the `try`,
   `test_a_factory_with_the_wrong_arity_is_a_defect_and_not_a_model_that_did_not_
   answer`. That second pair is the one the previous round of this file got
   wrong: it named `"none of them answered"` in test 1 as its arity witness, and
   that assertion is reachable through `evaluate` whatever the factory's arity —
   with the pre-fix one-argument lambda restored AND the build moved one line
   into the `try`, tests 1, 2, 5, 6 and 7 were GREEN against the arity bug. The
   arity is witnessed by the two socket tests and by the library-level test
   named above, and by nothing else.

9. Return `Verdict(..., results, silence)` instead of `Verdict(..., [], silence)`
   in `resolve.evaluate`. Only `test_a_suite_that_stopped_half_way_publishes_no_
   score_and_says_how_far_it_got` goes red, on a figure computed off a shorter
   suite than the author wrote (AC-3.1) — which until this test was written was
   an argued decision with no witness anywhere in the tree.

10. Drop `unenforced=` from the `Silence(...)` built in `resolve.evaluate`. Only
   `test_a_rule_nothing_could_grade_is_still_reported_when_the_suite_stopped`
   goes red: the run threw away a "nothing applied this rule of yours" report on
   its way to throwing away the score, which is the silent degradation T7
   forbids by name.

11. Return the `scoring/no-model-passes` refusal from `_choose` instead of
   binding `found.model`. Only `test_the_door_binds_the_model_that_passed_when_
   the_agent_s_own_did_not` goes red, on a command that exits non-zero over a
   model it had just measured passing.

12. Restore `if self.verdict.outcome == "UNDECIDED" and not self.verdict.results:`
   in `PortabilityReport.render`, in place of `if not self.verdict.results:`.
   Only `test_something_listening_that_is_not_a_model_runtime_is_named_as_that`
   goes red, on `score 0% vs bar 70%` printed for a row that was refused on
   `needs:` before a case was run — the same false number the UNDECIDED branch
   was written to stop, one outcome over.

AND THREE MORE that are about ordering and spelling rather than about a line,
all measured with a real listener rather than a monkeypatch:

* move the `_egress_refusal` call in `scoring._choose` to after the `resolve()`
  call — `test_the_search_never_dials_off_this_machine_before_the_workspace_
  allows_it` goes red with real requests recorded at an off-box address;
* classify `json.JSONDecodeError` as `NOT_SERVING` in `resolve._why_it_stopped`
  — `test_something_listening_that_is_not_a_model_runtime_is_named_as_that` goes
  red on a report telling the author to start a runtime that is already running;
* drop the `_served` lookup from `_choose`'s `transport_for`, so the search posts
  the catalogue id instead of the tag the runtime has on disk —
  `test_the_door_binds_the_model_that_passed_when_the_agent_s_own_did_not` goes
  red, which is what a real Ollama box would have done to every locally-served
  candidate.

AND THE WHOLE ORIGINAL DEFECT, re-measured rather than recalled. With the
pre-fix `transport_for = lambda name: _transport_for(name, serving_at, root)()`
restored in `scoring._choose`, the shipped command still ends in a stack —

    TypeError: _choose.<locals>.<lambda>() takes 1 positional argument but 2
    were given                          (resolve.py:1200, inside `evaluate`)

— and SEVEN of the fifteen tests here go red. The two that do not need a socket,
`test_a_factory_with_the_wrong_arity...` and
`test_the_search_never_dials_off_this_machine...`, stay green under it, which is
correct: the first is about the protocol rather than about this caller, and the
second is about a refusal that now happens before any factory is built.
"""

from __future__ import annotations

import functools
import json
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

REPO = Path(__file__).resolve().parents[3]
PACT_BIN = REPO / "target" / "debug" / "pact"
EXAMPLE = "examples/refund-desk"
#: Port 9 is `discard`, and nothing on this machine listens on it. The point of
#: the address is that connecting to it fails at once rather than hanging.
NOWHERE = "http://127.0.0.1:9/v1"
#: The one distribution row `examples/refund-desk` admits: it needs `images: yes`
#: and `reasoning: careful`, which rules out every other locally-served row, and
#: `allow-egress:` without `llm` rules out all the hosted ones.
THE_SERVED_ROW = "qwen2.5-vl-7b-instruct"


def open_the_door(
    serving_at: str, workspace: str = EXAMPLE, timeout: int = 300
) -> subprocess.CompletedProcess:
    """Run `--choose-model` the way the console script does, in its own process.

    Through `main`, not `python -m`: `scoring`'s `__main__` guard refuses and
    points at `pact_adapters.evals` rather than scoring anything, which is
    deliberate and documented there. Copied rather than imported from the other
    door test, because this suite keeps no shared test helper.

    The loader has to be built, because `scoring` reads the tree through it
    (invariant P-1) and refuses with "the `pact` command is not on this machine"
    otherwise — which is a different refusal from the one under test here.
    """
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    return subprocess.run(
        [
            sys.executable, "-c",
            "from pact_adapters.scoring import main; raise SystemExit(main("
            f"[{workspace!r}, '--choose-model', '--serving-at', {serving_at!r}]))",
        ],
        capture_output=True, text=True, cwd=REPO, timeout=timeout,
        env={
            "PYTHONPATH": str(REPO / "adapters/python/src"),
            "PATH": "/usr/bin:/bin",
        },
    )


def test_the_door_refuses_and_does_not_raise_when_nothing_is_served() -> None:
    """The ordinary state of an air-gapped box the first time anyone scores on
    it: the flag is asked for a model, the catalogue is walked, and nothing on
    the other end of `--serving-at` answers.

    That is a refusal, and a refusal is four lines of English. It was a stack.
    """
    out = open_the_door(NOWHERE)
    said = out.stdout + out.stderr

    assert "Traceback" not in out.stderr, (
        f"`--choose-model` raised instead of refusing:\n{out.stderr[-2000:]}"
    )
    assert said.strip(), "`--choose-model` did its work and said nothing at all"
    # UNCONDITIONALLY, both halves. `if out.returncode != 0:` around the second
    # assertion would assert nothing at all on the regression path, where the
    # process dies with a traceback and a non-zero code.
    assert out.returncode != 0, (
        f"nothing was served, so nothing could be chosen, and that must not "
        f"exit 0:\n{said}"
    )
    assert "error" in said.lower(), (
        f"it failed and did not say why — every diagnostic here opens with "
        f"`error:`:\n{said}"
    )
    # The refusal came out of the portability search and not from something in
    # front of it. This is the assertion that used to be a grep of `scoring.py`
    # for the string `resolve(`.
    assert "PORTABILITY" in said, (
        f"the refusal did not come from the portability search, so `_choose` is "
        f"not reaching `resolve`:\n{said}"
    )

    # AND THE SEARCH MUST HAVE ACTUALLY RUN. This sentence is only reachable
    # through `evaluate`, so it covers "the search was reached and every
    # candidate was run" rather than a short-circuit in front of it.
    #
    # IT DOES NOT WITNESS THE ARITY, and this comment said it did. Measured: with
    # the pre-fix one-argument lambda restored in `scoring._choose` AND the
    # transport build moved one line into the `try` in `resolve.evaluate` — a
    # refactor that source's own comment anticipates — this test PASSES against
    # the arity bug, and the refusal reads "2 model(s) met the requirements and
    # none of them answered", i.e. a `TypeError` in our own program reported to
    # the author as a missing runtime. What witnesses the arity is this test and
    # the next one only through a real socket, plus
    # `test_a_factory_with_the_wrong_arity_is_a_defect_and_not_a_model_that_did_not_answer`
    # below, which needs no socket at all. If the catalogue ever stops holding a
    # row this workspace's `needs:` admits, this assertion fails loudly instead
    # of leaving the search quietly untested.
    assert "none of them answered" in said, (
        f"no candidate was ever run, so `resolve()` was never reached with the "
        f"transport factory and this test no longer covers what it says it "
        f"does:\n{said}"
    )
    # And the refusal names what to do about it, which is the whole of D11.
    assert "--serving-at" in said, f"the refusal is a dead end:\n{said}"


def test_the_door_names_hosted_models_it_could_not_use() -> None:
    """The refusal TEXT is part of D11, not decoration.

    Filtering the catalogue down to rows the local runtime reports would also
    stop the crash — and it would permanently blind this flag to every hosted
    model, because `judge.served_here` asks Ollama's `/api/tags` and no
    `claude-*` row can ever appear there. The author would be told nothing about
    the models they cannot reach, or why.
    """
    out = open_the_door(NOWHERE)
    said = out.stdout + out.stderr

    assert "claude" in said, (
        f"not one hosted row survived into the refusal, which is what happens "
        f"when the catalogue is filtered to what is served here:\n{said}"
    )
    assert "leave the box" in said, (
        f"a hosted row was ruled out and the reason was not printed:\n{said}"
    )


class _Answering(BaseHTTPRequestHandler):
    """The smallest thing that looks like a served model.

    `/v1/chat/completions` in the OpenAI-compatible shape `OllamaTransport`
    posts to, and `/api/tags` because `judge.served_here` asks it.

    `serves` is the allowlist of model ids this server has pulled. Empty means
    "anything asked for". Anything outside it gets a 404, which is what a real
    runtime says about a model nobody pulled — and that is how the mixed case
    below is built: one row on this port answers, another on the same port does
    not. An allowlist rather than a denylist so that a catalogue which later
    admits a third row makes that test fail loudly instead of quietly measuring
    something it does not describe.
    """

    serves: tuple[str, ...] = ()

    def log_message(self, *args: object) -> None:  # noqa: D102 — quiet under pytest
        return

    def _send(self, body: dict, code: int = 200) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's spelling
        self._send({"models": [{"name": "llama3.1:8b"}]})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        try:
            asked = json.loads(raw or b"{}").get("model", "")
        except ValueError:
            asked = ""
        if self.serves and asked not in self.serves:
            self._send({"error": {"message": f"model {asked!r} not found"}}, code=404)
            return
        self._send({
            "choices": [{
                "message": {"content": "Refund approved for the order."},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 12, "completion_tokens": 8},
        })


def _serving(serves: tuple[str, ...] = ()):
    """A real HTTP server on a real port, in a thread, for the duration.

    Not a monkeypatch of the transport: the defect being covered lives in how
    `_choose` hands `resolve` a way to BUILD transports, so a test that replaces
    the transport replaces the thing under test.
    """
    handler = type("_Handler", (_Answering,), {"serves": serves})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture()
def a_model_that_answers():
    server = _serving()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    finally:
        server.shutdown()
        server.server_close()


def test_the_door_runs_the_authors_cases_against_a_model_that_does_answer(
    a_model_that_answers: str,
) -> None:
    """The other side of the same door, and the one the dead address cannot show:
    a candidate that answers is actually RUN — every case, through the factory,
    with the strategy name the protocol carries.

    The canned answer is wrong for the author's suite, so the honest outcome is
    still a refusal. What matters is which refusal: the models were measured and
    missed the bar, not "nothing answered".
    """
    out = open_the_door(a_model_that_answers)
    said = out.stdout + out.stderr

    assert "Traceback" not in out.stderr, (
        f"a model answered and the search still raised:\n{out.stderr[-2000:]}"
    )
    assert said.strip(), "the door said nothing at all"
    assert "none of them answered" not in said, (
        f"a model was answering on this port and the search reported silence, "
        f"so the cases never reached it:\n{said}"
    )
    assert "never answered" not in said, (
        f"the one qualifying row answered every case, so nothing may be reported "
        f"as silent:\n{said}"
    )
    # A run happened, so the report is a report: it names the agent and the bar
    # the author wrote rather than a connection problem.
    assert "PORTABILITY" in said, f"no portability report was produced:\n{said}"


#: A second locally-served row this workspace's `needs:` admits — same shape as
#: the distribution's vision row, and `unknown` in both figures for the reason
#: that row gives: Y12 makes UNKNOWN bind and rank last, which is what puts this
#: one second and leaves the served row first.
#:
#: The NAME decides which test it serves, because `_choose` asks for
#: `entries[0].name` when the author named no model and the catalogue is sorted:
#: a name sorting before `claude-haiku-4-5` becomes the REQUESTED model, and one
#: sorting after it is a candidate the search meets inside `_cheapest_passing`.
A_SECOND_ROW = "vision-8b-nobody-pulled"
A_REQUESTED_ROW = "a-vision-model-nobody-pulled"


def an_override_layer(name: str) -> str:
    """A workspace-local `models/catalog.yaml` adding one locally-served row.

    The override layer `resolve.load_catalogue` documents, written the way an
    author on an air-gapped box would write it, so these tests add a candidate
    without touching the distribution's file.
    """
    return f"""
models:
  {name}:
    family: local-vision
    tier: small
    served-by:
      - {{ runtime: ollama, endpoint: local }}
    capabilities:
      tool-calling: parallel
      modality-in: [text, image]
      modality-out: [text]
      context-window:
        value: unknown
        provenance:
          source: >
            Written by this test. The row exists to stand for a model the
            author's own machine could serve and is not serving right now.
          date: 2026-08-05
          as-of: 2026-08-05
          recorded-by: jithinvg@bud.studio
    reasoning:
      value: unknown
      provenance:
        source: >
          Written by this test; no positioning statement is being claimed.
        harness: none
        as-of: 2026-08-05
        recorded-by: jithinvg@bud.studio
    cost: {{ input-per-mtok: 0 USD, output-per-mtok: 0 USD }}
"""


def test_a_row_that_never_answered_is_not_reported_as_one_that_missed_the_bar(
    tmp_path: Path,
) -> None:
    """THE MIXED CASE, which is the ordinary one rather than a corner.

    A real box serves the model somebody pulled and does not serve the rest of
    the catalogue. So the search meets both facts in the same run: one row that
    answered and failed the author's checks, and one row that was never there.

    Those are different sentences because they are different jobs. "Met the
    requirements and none reached the bar" sends the author to edit their suite;
    the row it is said about was never asked a question. The first version of
    this fix collected the silent rows and then printed them that way whenever
    any other row answered, which is every run on a box with one model pulled.

    Built with a workspace-local `models/catalog.yaml` — the override layer
    `resolve.load_catalogue` documents — so the extra row is added the way an
    author on an air-gapped box would add one, and one HTTP server that answers
    for the served id and 404s for the other, which is what a real runtime says
    about a model nobody pulled.
    """
    root = tmp_path / "refund-desk"
    shutil.copytree(REPO / EXAMPLE, root)
    (root / "models").mkdir(exist_ok=True)
    (root / "models" / "catalog.yaml").write_text(an_override_layer(A_SECOND_ROW))

    # This port has pulled exactly one of the two qualifying rows. Stated as an
    # allowlist so that the "1 model(s)" assertion below is a claim this fixture
    # actually enforces rather than one it happens to satisfy today.
    server = _serving(serves=(THE_SERVED_ROW,))
    try:
        out = open_the_door(
            f"http://127.0.0.1:{server.server_address[1]}/v1", workspace=str(root)
        )
    finally:
        server.shutdown()
        server.server_close()
    said = out.stdout + out.stderr

    assert "Traceback" not in out.stderr, (
        f"one row went quiet and the search raised:\n{out.stderr[-2000:]}"
    )
    assert "PORTABILITY" in said, f"no portability report was produced:\n{said}"

    # BOTH FACTS, SEPARATELY. The row that answered is counted against the bar.
    assert "1 model(s) met the requirements and none reached the bar" in said, (
        f"the row that answered and failed is not being reported as measured, "
        f"or the silent row has been counted in with it:\n{said}"
    )
    # And the row that never answered is named, with the thing to go and do.
    assert A_SECOND_ROW in said, (
        f"a model that qualified and was never reachable is not named anywhere "
        f"in the refusal:\n{said}"
    )
    assert "never answered" in said, (
        f"the silent row was folded into the count of models that missed the "
        f"bar, which tells the author to edit a suite that was never run "
        f"against it:\n{said}"
    )
    assert "--serving-at" in said, (
        f"the author is told a model went quiet and not what to do about "
        f"it:\n{said}"
    )
    # The whole-catalogue sentence must NOT be used: something WAS measured.
    assert "none of them answered" not in said, (
        f"one row answered every case, so this is not the nothing-was-measured "
        f"refusal:\n{said}"
    )


def test_a_model_that_never_answered_is_not_given_a_score(tmp_path: Path) -> None:
    """`score 0% vs bar 70%` printed beside "did not answer, so nothing was
    measured on it" is a self-contradicting report, and the half a reader
    believes is the number.

    Nought per cent is what a model scores when it answers every case wrongly.
    It is not what a model scores when nobody could ask it anything, and the
    whole argument for returning no results rather than a figure off the cases
    that happened to answer is that a portability number is a claim about a
    measurement. `render()` then printed the number anyway.

    Reached by making the requested model a locally-served row and pointing
    `--serving-at` at nothing: the row qualifies on `needs:`, so the search runs
    it rather than ruling it out, and it is the head verdict of the report — the
    one place an unmeasured `Verdict` is actually rendered.
    """
    root = tmp_path / "refund-desk"
    shutil.copytree(REPO / EXAMPLE, root)
    (root / "models").mkdir(exist_ok=True)
    (root / "models" / "catalog.yaml").write_text(an_override_layer(A_REQUESTED_ROW))

    out = open_the_door(NOWHERE, workspace=str(root))
    said = out.stdout + out.stderr

    assert "Traceback" not in out.stderr, out.stderr[-2000:]
    # The head of the report is the row that could not be reached, which is the
    # verdict this test is about. If this fails the workspace no longer puts that
    # row first and the rest of the test is asserting about something else.
    assert f"PORTABILITY: UNDECIDED for {A_REQUESTED_ROW}" in said, (
        f"the unmeasured row is not the head verdict, so nothing here is "
        f"exercising how one is rendered:\n{said}"
    )
    assert "did not answer" in said, f"and it must say so in words:\n{said}"
    assert "score 0%" not in said, (
        f"a model nobody could reach was reported as having scored nought — a "
        f"measurement claim about a run that never happened:\n{said}"
    )
    assert "not measured" in said, (
        f"the score line was dropped rather than replaced, so the bar the author "
        f"wrote went unmentioned:\n{said}"
    )


def test_the_search_refuses_without_a_way_to_run_anything() -> None:
    """`resolve(transport_for=...)` defaults to `None`, and that default is the
    enabler behind this whole file.

    WHERE THIS GUARD CAN BE REACHED FROM, measured rather than assumed, because
    it decides what this test is worth. `grep -rn "resolve(" adapters/python/src`
    finds exactly ONE production call to this resolver — `scoring.py:1005`, the
    `--choose-model` path — and it passes `transport_for=` by keyword with a
    two-argument closure built four lines above it, so it can never reach the
    refusal. No shipped command can. This guard protects LIBRARY and EMBEDDER
    callers only, and a seam test is therefore the only door onto it that exists.
    That is a reason to keep this test, not to mistake it for product coverage.

    WHY THE DOCUMENT IS THE WORKED EXAMPLE AND NOT A ONE-LINE DICT. An earlier
    round of this test used `{"agents": {"a": {"instructions": ..., "model":
    "m"}}}` and asked for `"m"`. Measured with the guard deleted, that scenario
    returns a perfectly honest `PORTABILITY: FAIL ... 'm' is not in the
    catalogue` — the early return fires first and the `None` is never touched. So
    the only red a mutation could produce was `DID NOT RAISE`: the test witnessed
    the guard's PRESENCE and never its CONSEQUENCE. Asking for a row that IS in
    the catalogue walks past that early return into the search, where the `None`
    is called.

    MUTATION: delete the `if not callable(transport_for): raise TypeError(...)`
    block from `resolve`. Measured red with it gone, on this scenario:
    `TypeError: 'NoneType' object is not callable`, raised at `resolve.py` in
    `evaluate` on the `transport = transport_for(model, strategy_name)` line —
    the unnamed crash six frames from the caller that the guard converts into the
    sentence asserted below. That traceback is the harm; `DID NOT RAISE` was not.
    """
    from pact_adapters.resolve import resolve

    document, spec = the_worked_example()

    with pytest.raises(TypeError) as raised:
        resolve(spec, document, THE_SERVED_ROW, agent_key="refund-desk")

    said = str(raised.value)
    assert "transport_for" in said, said
    assert "RUNNING" in said or "run them on" in said, (
        f"the refusal does not say why a factory is needed:\n{said}"
    )
    assert "NoneType" not in said, (
        f"this is Python's message from the call site inside the search, not the "
        f"door's — the guard was removed or moved below the search:\n{said}"
    )


def test_the_door_refuses_a_factory_it_cannot_call_with_two_arguments() -> None:
    """The guard checks CALLABILITY and ARITY, not identity against `None`.

    For a round it was `if transport_for is None:`, and the comment beside it
    said the arity "CANNOT" be seen at runtime and handed the job to a test file.
    Both halves were measured false. Six wrong shapes were run through the public
    `resolve()` against the worked example with that guard in place, and five of
    them sailed through it to `TypeError` four frames down with a message naming
    neither `resolve` nor `transport_for`:

        zero-arg lambda    -> TypeError: <lambda>() takes 0 positional arguments
        one-arg lambda     -> TypeError: <lambda>() takes 1 positional argument
        three-arg lambda   -> TypeError: <lambda>() missing 1 required ...: 'c'
        transport INSTANCE -> TypeError: 'ATransport' object is not callable
        a bare string      -> TypeError: 'str' object is not callable
        False              -> TypeError: 'bool' object is not callable

    `False` is the sharpest: falsy, not callable, not `None`, and admitted. The
    one-argument lambda is sharper still — it is sibling issue A1's entire
    subject, the shape `_choose` actually shipped.

    AND IT MUST NOT OVER-REFUSE. `inspect.signature(f).bind("m", "s")` admits
    every real caller in this tree: `scoring._choose`'s
    `def transport_for(model_name, _strategy_name)`, a `*args` forwarder, a
    callable object, a `functools.partial`, and a builtin whose signature cannot
    be read at all (admitted deliberately — refusing on "I could not look" is a
    gate firing on the wrong evidence). Those are asserted below alongside the
    refusals, because a guard that rejects good callers is worse than none.

    MUTATION: narrow the guard back to `if transport_for is None:`. Measured red
    on the first parametrised shape — `AttributeError: 'bool' object has no
    attribute ...` out of the search instead of the door's sentence, and for the
    lambdas a `TypeError` whose text contains neither `transport_for` nor the
    expected `(model_name, strategy_name)` shape.
    """
    from pact_adapters.resolve import resolve

    document, spec = the_worked_example()

    class NotAFactory:
        """A transport INSTANCE where the factory belongs — the confusion the
        two seams in `scoring._choose` invite, `_transport_for` returning a
        factory and `transport_for` being one."""

    refused = {
        "a zero-argument factory": lambda: _Answers(),
        "a one-argument factory (A1's own shape)": lambda _model: _Answers(),
        "a three-argument factory": lambda _m, _s, _extra: _Answers(),
        "a transport instance rather than a factory": NotAFactory(),
        "a bare string": "qwen2.5-vl-7b-instruct",
        "False, which is falsy but is not None": False,
    }
    for what, shape in refused.items():
        with pytest.raises(TypeError) as raised:
            resolve(spec, document, THE_SERVED_ROW, None, shape, {},
                    agent_key="refund-desk")
        said = str(raised.value)
        assert "transport_for(model_name, strategy_name)" in said, (
            f"{what} reached the search and crashed there instead of being "
            f"refused at the door, so the author reads a message that names "
            f"neither the parameter nor its shape:\n{said}"
        )

    #: Callers that are FINE and must still get in. Every one of these is a shape
    #: something in this repository or an embedder actually uses.
    class CallableObject:
        def __call__(self, model: str, strategy: str):
            return _Answers()

    admitted = {
        "the shipped two-argument closure": lambda model, strategy: _Answers(),
        "a *args forwarder, as a decorator leaves behind": lambda *a: _Answers(),
        "a callable object": CallableObject(),
        "a factory with defaults": lambda model="", strategy="": _Answers(),
        "functools.partial with one bound": functools.partial(
            lambda _bound, model, strategy: _Answers(), object()
        ),
    }
    for what, shape in admitted.items():
        report = resolve(spec, document, THE_SERVED_ROW, None, shape, {},
                         agent_key="refund-desk")
        assert report is not None, what
        # The point is that the DOOR let it through. What the search then makes
        # of it is other tests' business.



def test_a_caller_who_asked_for_no_strategies_is_not_told_the_box_is_silent() -> None:
    """`strategies={}` is a supported input, and `resolve`'s own docstring says
    what it means: an author who wrote no `variants:` gets `{"authored": ...}`,
    and a caller who deliberately passed `{}` gets nothing. Different facts.

    Nothing is tried, so no socket is opened and nothing goes quiet. The first
    version of the silence tracking seeded its flag `False` before a loop that
    never runs, so every row was filed as having failed to answer and the author
    was told to start a model runtime over a search that never dialled.

    AND NOT TOLD THEY WERE MEASURED EITHER, which is the half this test did not
    have for a round and is the more dangerous half. Fixing the sentence above by
    seeding the flag `scored_it = not strategies` recorded a true fact — these
    rows did not go silent — in the wrong place: it marked them SCORED, they
    landed in `measured`, and `_cheapest_passing` printed "5 model(s) met the
    requirements and none reached the bar" off a search that built zero
    transports and ran zero cases. Measured on this exact document with the
    factory below, before the fix:

        factory calls: []
        results ran: 0
        NO ALTERNATIVE: nothing in the catalogue passed: 5 model(s) met the
        requirements and none reached the bar, ...

    A row nobody tried is not scored and not silent. It is UNRUN, and the two
    assertions this test used to carry both pass on a report that says it was
    measured — which is why the third and fourth are here.

    Not reachable from `--choose-model`, which always passes strategies — so this
    is a library-level test, and it lives beside the door because it is the same
    edit. The factory RAISES if anything calls it: that is the assertion that no
    connection was attempted, made where a string match on the refusal could not
    make it.

    MUTATION: restore `scored_it = not strategies` at the head of the candidate
    loop in `_cheapest_passing` and delete the `if not strategies:` branch below
    it. Measured red on the "none reached the bar" assertion, with the rendered
    recommendation quoted above.
    """
    from pact_adapters.ir import AgentSpec
    from pact_adapters.resolve import resolve

    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    shown = subprocess.run(
        [str(PACT_BIN), "show", str(REPO / EXAMPLE)],
        capture_output=True, text=True, check=True,
    )
    document = json.loads(shown.stdout)
    spec = AgentSpec.from_document(document, "refund-desk")

    def never_called(model: str, strategy: str):
        raise AssertionError(
            f"no strategies were given, so nothing should have been run — "
            f"something asked for a transport for {model}/{strategy}"
        )

    report = resolve(
        spec, document, "claude-haiku-4-5", {}, never_called, {},
    )

    # THE PRECONDITION THIS TEST TURNS ON. If no catalogue row qualifies, the
    # search returns "nothing in the catalogue meets what this agent needs" and
    # every assertion below passes for a reason that has nothing to do with the
    # defect. The false sentence only exists where rows DID qualify.
    assert report.instead is not None and "met the requirements" in (
        report.recommendation
    ), (
        f"no catalogue row qualified on this document, so the branch that "
        f"produced the false measurement claim was never reached and this test "
        f"is asserting about nothing:\n{report.recommendation}"
    )
    assert not report.verdict.results, (
        f"a case was run, so this is no longer the zero-run scenario: "
        f"{len(report.verdict.results)} results"
    )

    said = report.recommendation
    assert said, "a refusal with no recommendation is the dead end D11 closes"
    assert "never answered" not in said, (
        f"nothing was asked, so nothing can have failed to answer:\n{said}"
    )
    assert "none of them answered" not in said, (
        f"the search opened no connection and reported the machine as serving "
        f"nothing, which sends the author to start a runtime they do not "
        f"need:\n{said}"
    )
    assert "none reached the bar" not in said, (
        f"zero transports were built and zero cases ran, and the author is being "
        f"told models were measured against their bar and missed it — a "
        f"measurement claim about a search that took no measurement, and it "
        f"sends them to edit a suite that was never scored:\n{said}"
    )
    assert "met the requirements and none" not in said, (
        f"the same claim by its other spelling:\n{said}"
    )


def test_a_row_nothing_was_run_against_is_not_reported_as_having_failed() -> None:
    """The HEAD verdict, where the test above holds the recommendation.

    Same input, `strategies={}`, but asking for the one row this workspace does
    serve, so the search walks past the `needs:` refusal into the strategy loop —
    which then runs zero times. `last` stays `None` and the report used to be
    built as `last or Verdict("FAIL", 0.0, bar, [])` with the strategy named
    `"exhausted"`. Measured, with a factory that raises if it is called:

        factory calls: []
        results ran: 0
        PORTABILITY: FAIL for qwen2.5-vl-7b-instruct (agent Refund Desk,
                                                      strategy exhausted)

    Nothing was exhausted and nothing failed. `render` was already honest about
    the figure — it prints "score: not measured" whenever there are no results —
    so the false half was the outcome word and the strategy name beside it, which
    is what an author reads first and what a script greps for. UNDECIDED is what
    this module already returns for "no score could be taken", and the note says
    which of the reasons it is.

    MUTATION: put back `last or Verdict("FAIL", 0.0, bar, [])` with `"exhausted"`
    as the strategy. Measured red on the outcome assertion — `PORTABILITY: FAIL`
    for a model that was never run.
    """
    from pact_adapters.resolve import resolve

    document, spec = the_worked_example()

    def never_called(model: str, strategy: str):
        raise AssertionError(f"nothing should have been run: {model}/{strategy}")

    report = resolve(spec, document, THE_SERVED_ROW, {}, never_called, {},
                     agent_key="refund-desk")

    assert not report.verdict.results, "this is meant to be the zero-run scenario"
    assert report.verdict.outcome == "UNDECIDED", (
        f"nothing was run against {THE_SERVED_ROW} and it is being reported as "
        f"{report.verdict.outcome} — a verdict about a run that did not "
        f"happen:\n{report.render()}"
    )
    assert report.strategy != "exhausted", (
        f"no strategy was supplied, so none can have been exhausted:\n"
        f"{report.render()}"
    )
    assert "never run" in report.verdict.note, (
        f"the report does not say why there is no verdict:\n{report.render()}"
    )
    assert "score 0%" not in report.render(), (
        f"a model nothing was run against was given a figure:\n{report.render()}"
    )


# ─────────────────────────────────────── what opening the door made reachable
#
# Everything below is about the search AS IT NOW RUNS. None of it was reachable
# while `--choose-model` died on the line that builds the transport, which is why
# it is in this file and not in one of its own: it is the same door.


def the_worked_example() -> tuple[dict, "AgentSpec"]:
    """`examples/refund-desk` as the loader hands it over, and its supervisor.

    Through the real `pact show` rather than a dict written here, because the
    facts these tests turn on — that this agent has a `team:` of two, that its
    suite has six cases and a `judged:` rule nothing on this machine can grade —
    are facts about the shipped example. A hand-written document would let the
    example change out from under the assertions.
    """
    from pact_adapters.ir import AgentSpec

    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    shown = subprocess.run(
        [str(PACT_BIN), "show", str(REPO / EXAMPLE)],
        capture_output=True, text=True, check=True,
    )
    document = json.loads(shown.stdout)
    return document, AgentSpec.from_document(document, "refund-desk")


class _Answers:
    """A transport that answers with whatever it is told to, in order.

    Not `ReferenceTransport`: these tests need the SHAPE of a stopping run — a
    call that raises on the third case, a teammate call, a missing method — and
    scripting that through a recorded conversation would hide the thing under
    test behind the recording.
    """

    prices_money = False

    def __init__(self, name: str = "stub") -> None:
        self.name = name
        self.calls = 0

    def lattice(self) -> dict[str, str]:
        return {}

    async def model_call(self, system, history, tools):
        self.calls += 1
        return "Approved. The lamp arrived damaged within 30 days, refund 40 USD.", []


def test_a_teammate_the_agent_asks_is_run_rather_than_parked() -> None:
    """An agent with a `team:` scored by the search: the delegation has to RUN.

    `harness.run` only offers a teammate for real when it is given an
    `ask_member` — without one, `delegates` is empty, the call parks as
    WAITING_FOR_ANOTHER_AGENT, and the case comes back with an empty answer that
    is then scored as the model's. `scoring._run_every_case` builds one and says
    in its own comment why: omitting it "measured a suspension and blamed the
    model for it". `resolve.evaluate` had no `ask_member` anywhere in the file.

    Measured on the shipped worked example, whose supervisor names two members,
    with a transport that calls `policy-checker` once and then answers:

        without ask_member: score 0.0, every case `expected decision
                            'approved', got ''`
        with    ask_member: score 0.33, the delegating case answers

    The score itself is not the assertion — the stub gives one answer to six
    different questions, so most cases SHOULD fail. The assertion is that no case
    came back empty, which is what a parked run produces.

    MUTATION: drop `ask_member=ask_member` from the `run(...)` call in
    `resolve.evaluate` — every case comes back `got ''` and this goes red.
    """
    from pact_adapters.evals import Case, bar_of, rules_of
    from pact_adapters.harness import ToolCall
    from pact_adapters.resolve import evaluate

    document, spec = the_worked_example()
    assert spec.team, (
        "this test is about an agent with a `team:`, and the worked example no "
        "longer has one — it is measuring nothing"
    )

    class Delegating(_Answers):
        async def model_call(self, system, history, tools):
            self.calls += 1
            if self.calls == 1:
                return "", [ToolCall(name="policy-checker", args={"ask": "may we?"})]
            return await super().model_call(system, history, tools)

    v = evaluate(
        spec, Case.from_document(document), rules_of(document), bar_of(document),
        lambda model, strategy: Delegating(), "a-model-that-delegates", "authored",
        {}, document=document,
    )

    assert v.results, f"nothing was scored at all: {v.note}"
    empty = [r.key for r in v.results if "got ''" in r.why]
    assert not empty, (
        f"{len(empty)} case(s) came back with an empty answer — the delegation "
        f"parked instead of running, and the model was scored for it: {empty}"
    )
    assert v.score > 0, (
        f"every case failed, which is what a suspension scored as an answer "
        f"looks like: {[r.why for r in v.results]}"
    )


def test_a_factory_with_the_wrong_arity_is_a_defect_and_not_a_model_that_did_not_answer() -> None:
    """The arity, witnessed without a socket.

    This is the assertion the previous round of this file thought it had. A
    one-argument factory handed to the two-argument `TransportFactory` protocol
    is a mistake in the PROGRAM. It must arrive as a `TypeError` out of the
    call, and must never be turned into "the model did not answer" — which
    `_cheapest_passing` then prints as "this machine is not serving them. Start
    the model runtime", sending the author to fix a machine that is fine.

    Two things have to hold for that and this covers both: the transport is built
    outside the `try`, AND `_why_it_stopped` returns `None` for a `TypeError` so
    the narrowed `except` re-raises it. Either one alone is enough today, which
    is deliberate — the belt-and-braces is stated at the source line.

    THE FACTORY GOES THROUGH A `*args` FORWARDER ON PURPOSE, and that is not
    contrivance. `resolve`'s door now rejects a bare one-argument factory before
    the search starts (see the door test above), so handing one straight in would
    make this a test of the door and stop it exercising `evaluate` at all — the
    thing it is named for. `inspect.signature` cannot see through `*args`, which
    is the ordinary shape of a decorator or a forwarding wrapper, so this is both
    the realistic residue the door cannot decide AND the input that still reaches
    the line under test. The door admitting it is measured by this test passing:
    if the door started refusing `*args`, `asked_for` would be `[]` for the wrong
    reason and the message assertion below would fail.

    MUTATION: widen the `except` in `resolve.evaluate` back to swallowing
    everything (delete `if reading is None: raise`) AND move the
    `transport = transport_for(...)` line inside the `try`. This goes red with a
    `PortabilityReport` whose verdict says the model did not answer.
    """
    from pact_adapters.resolve import resolve

    document, spec = the_worked_example()
    asked_for = []

    def one_argument(model_name: str):
        asked_for.append(model_name)
        return _Answers()

    def forwards(*args):
        return one_argument(*args)

    with pytest.raises(TypeError) as raised:
        resolve(spec, document, THE_SERVED_ROW, None, forwards, {})

    said = str(raised.value)
    assert "positional argument" in said, (
        f"something else raised, so this test is no longer about the arity:\n{said}"
    )
    assert "resolve() needs a transport_for" not in said, (
        f"the DOOR refused this, so `evaluate`'s handling of a TypeError out of "
        f"the factory was never reached and this test is now asserting about the "
        f"guard one function up:\n{said}"
    )
    assert asked_for == [], (
        f"the factory was CALLED with one argument and returned a transport, so "
        f"the protocol is no longer two-argument: {asked_for}"
    )


def _stops_after(cases: int, raises: Exception):
    """A factory whose transports answer `cases` whole CASES per (model,
    strategy) and then raise — the shape of a runtime that goes away mid-suite.

    Counted per transport BUILT and not per model call, because `evaluate` builds
    one transport per case and one case is three calls on this example — a count
    of calls stops in the middle of the first case, which is a different fact
    from the one under test.
    """
    built: dict[tuple[str, str], int] = {}

    def factory(model: str, strategy: str):
        key = (model, strategy)
        built[key] = built.get(key, 0) + 1
        gone = built[key] > cases

        class Stopping(_Answers):
            async def model_call(self, system, history, tools):
                if gone:
                    raise raises
                return await super().model_call(system, history, tools)

        return Stopping(f"{model}/{strategy}")

    return factory


def test_a_suite_that_stopped_half_way_publishes_no_score_and_says_how_far_it_got() -> None:
    """AC-3.1 — a figure off a shorter suite is a claim about a different suite —
    and the fact that decision was throwing away with it.

    `evaluate` keeps NO results when a run stops, and that is argued: four cases
    out of six is not the author's suite. Nothing anywhere tested it. Every
    silence in this file happened with `results` already empty, so keeping them
    or discarding them was a no-op under the whole test set — measured by
    changing `Verdict(..., [], ...)` to `Verdict(..., results, ...)` and watching
    all seven tests here, and 64 more across the portability suites, stay green.

    What must NOT be thrown away with the score is that it answered at all.
    "Answered three of six then the runtime went away" and "never opened a
    socket" were one state downstream, and `_cheapest_passing` turned that state
    into "none of them answered — this machine is not serving them", which is a
    false statement of fact about a machine that was serving it.

    MUTATION: return `Verdict("UNDECIDED", 0.0, bar, results, ...)` from
    `resolve.evaluate` — the `results == []` assertion goes red.
    """
    import httpx

    from pact_adapters.evals import Case, bar_of, rules_of
    from pact_adapters.resolve import PortabilityReport, evaluate

    document, spec = the_worked_example()
    cases = Case.from_document(document)
    assert len(cases) > 1, "a suite of one case cannot stop half way"

    v = evaluate(
        spec, cases, rules_of(document), bar_of(document),
        _stops_after(1, httpx.ConnectError("All connection attempts failed")),
        "half-a-box", "authored", {}, document=document,
    )

    assert v.outcome == "UNDECIDED", v.note
    assert v.results == [], (
        f"a score was kept off {len(v.results)} of {len(cases)} cases, which is a "
        f"claim about a suite the author did not write"
    )
    assert v.silence is not None, "a run that stopped kept no reason for stopping"
    assert (v.silence.answered, v.silence.of) == (1, len(cases)), (
        f"how far it got was not recorded: {v.silence}"
    )
    assert f"answered 1 of {len(cases)}" in v.note, (
        f"the note does not say it answered anything:\n{v.note}"
    )
    assert "did not answer" not in v.note, (
        f"it answered a case and is reported as a model that did not:\n{v.note}"
    )
    # And the report still refuses to publish a number for it.
    said = PortabilityReport("Refund Desk", "half-a-box", "b", v, "authored").render()
    assert "not measured" in said and "score 0%" not in said, said

    # THE SENTENCE THE AUTHOR ACTUALLY READS, which is one function further on.
    # `_cheapest_passing` turned "UNDECIDED with no results" into "none of them
    # answered — this machine is not serving them. Start the model runtime", and
    # that is the false statement of fact this whole distinction exists to stop:
    # the machine was serving them and every row had answered a case.
    from pact_adapters.resolve import resolve

    # Asked for a row this workspace's `needs:` rules out, so the search moves
    # straight to the alternatives and THE_SERVED_ROW is one of them rather than
    # the excluded requested model.
    told = resolve(
        spec, document, "llama3.2-1b-instruct", None,
        _stops_after(1, httpx.ConnectError("All connection attempts failed")),
        {}, agent_key="refund-desk",
    ).recommendation
    assert "is not serving" not in told, (
        f"every row answered a case and the author is being told this machine "
        f"serves none of them:\n{told}"
    )
    assert "Start the model runtime" not in told, (
        f"the remedy is to start a runtime that is already running:\n{told}"
    )
    assert f"answered 1 of {len(cases)} cases and then stopped" in told, (
        f"how far each row got is not in the sentence the author reads:\n{told}"
    )


def test_a_rule_nothing_could_grade_is_still_reported_when_the_suite_stopped() -> None:
    """T7: "there is no silent degradation anywhere in the system".

    The cases that DID answer each met the suite's `judged:` rule, and nothing on
    this machine could grade it — which is a report the author is owed, in the
    same words `render` prints beside any other score. Throwing away
    `Verdict.results` threw those away too, silently, and that half of the loss
    was argued nowhere: dropping the SCORE is AC-3.1, dropping "a rule of yours
    was never applied" is the one thing T7 forbids by name.

    MUTATION: drop `unenforced=` from the `Silence(...)` built in
    `resolve.evaluate` — the `NOT APPLIED` assertion goes red while every other
    test in this file stays green.
    """
    import httpx

    from pact_adapters.evals import Case, bar_of, rules_of
    from pact_adapters.resolve import PortabilityReport, evaluate

    document, spec = the_worked_example()
    cases = Case.from_document(document)

    ran_out = evaluate(
        spec, cases, rules_of(document), bar_of(document),
        _stops_after(1, httpx.ConnectError("All connection attempts failed")),
        "half-a-box", "authored", {}, document=document,
    )
    whole = evaluate(
        spec, cases, rules_of(document), bar_of(document),
        _stops_after(len(cases), httpx.ConnectError("never reached")),
        "a-whole-box", "authored", {}, document=document,
    )

    assert whole.unenforced, (
        "the control run reports no ungraded rule, so this machine is grading "
        "the suite's `judged:` rule and the test cannot see the loss"
    )
    assert ran_out.unenforced == whole.unenforced, (
        f"the case that answered carried an ungraded-rule report and the stopped "
        f"suite dropped it:\n  kept: {ran_out.unenforced}\n  control: "
        f"{whole.unenforced}"
    )
    said = PortabilityReport("Refund Desk", "half-a-box", "b", ran_out, "authored").render()
    assert "NOT APPLIED" in said, (
        f"the hole was carried on the verdict and never printed, which is the "
        f"same silence one object further along:\n{said}"
    )


def test_a_defect_in_our_own_program_is_never_reported_as_a_machine_that_is_not_serving() -> None:
    """`except Exception` around the run, with "did not answer" written under it.

    A missing attribute in our own code is not a model that did not answer, and
    telling a support lead to "start the model runtime" over it is a right field
    name with a wrong diagnosis and a remedy that cannot help — the shape row C9
    of `docs/70-PRODUCTION-GAP-REGISTER.md` already names as a defect in this
    repository.

    Measured before the narrowing, with a transport object that has no
    `model_call`: `nothing could be measured: 1 model(s) met the requirements and
    none of them answered — this machine is not serving them. Start the model
    runtime`, with `'Broken' object has no attribute 'model_call'` dropped
    entirely by the time the author read it.

    MUTATION: delete `if reading is None: raise` in `resolve.evaluate` — this
    goes red with a `Verdict` in place of the exception.
    """
    from pact_adapters.evals import Case, bar_of, rules_of
    from pact_adapters.resolve import evaluate

    document, spec = the_worked_example()

    class Broken:
        name = "broken"

        def lattice(self) -> dict[str, str]:
            return {}

    with pytest.raises(AttributeError) as raised:
        evaluate(
            spec, Case.from_document(document), rules_of(document), bar_of(document),
            lambda model, strategy: Broken(), "some-model", "authored", {},
            document=document,
        )

    assert "model_call" in str(raised.value), str(raised.value)


class _NotARuntime(BaseHTTPRequestHandler):
    """A real HTTP server that is not a model runtime.

    The ordinary author mistake: `--serving-at` pointed at a port something else
    is on. It listens, it accepts, it answers 200 — and what it sends back is
    HTML.
    """

    def log_message(self, *args: object) -> None:  # noqa: D102 — quiet under pytest
        return

    def _html(self) -> None:
        body = b"<html><body>nginx</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = _html
    do_POST = _html


def test_something_listening_that_is_not_a_model_runtime_is_named_as_that() -> None:
    """A machine that is listening, accepting and answering 200 was reported to
    its author as one that is not serving anything, with "Start the model
    runtime" as the remedy.

    The cause the author WAS shown, one line up, was `Expecting value: line 1
    column 1 (char 0)` — a traceback with the frames taken off, in a module whose
    own docstring promises "a file, a line and something to type instead of a
    traceback" (D13).

    MUTATION: classify `json.JSONDecodeError` as `NOT_SERVING` in
    `resolve._why_it_stopped` — this goes red on the remedy.
    """
    server = ThreadingHTTPServer(("127.0.0.1", 0), _NotARuntime)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        out = open_the_door(f"http://127.0.0.1:{server.server_address[1]}/v1")
    finally:
        server.shutdown()
        server.server_close()
    said = out.stdout + out.stderr

    assert "Traceback" not in out.stderr, out.stderr[-2000:]
    assert "not a model runtime" in said, (
        f"something answered every request with HTML and the report does not say "
        f"so:\n{said}"
    )
    assert "Start the model runtime" not in said, (
        f"the machine is up, listening and answering, and the author is being "
        f"told to start it:\n{said}"
    )
    assert "Expecting value" not in said, (
        f"a raw Python exception string reached the author:\n{said}"
    )
    # AND THE HEAD OF THE REPORT, which on this run is a row refused on `needs:`
    # before any eval was run. It has no results either, and it printed
    # `score 0% vs bar 70%` beside "thinks at the 'steady' rung and this needs at
    # least 'careful'" — the same measurement claim about a run that never
    # happened that `render` already refuses to make for a model nobody reached.
    #
    # MUTATION: restore `if self.verdict.outcome == "UNDECIDED" and not
    # self.verdict.results:` in `PortabilityReport.render` — this goes red.
    assert "score 0%" not in said, (
        f"a model that was refused before any case was run is reported as having "
        f"scored nought:\n{said}"
    )


def _somewhere_else() -> str:
    """This machine's own non-loopback address, or a skip.

    The egress rule is about the HOST in `--serving-at`, not about which machine
    the packets end up on, so binding a listener to this box's LAN address is a
    real off-box `--serving-at` from `scoring.ON_THIS_MACHINE`'s point of view
    and needs no second computer.
    """
    import socket

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No packet is sent by connecting a UDP socket; this only asks the
        # routing table which local address would be used.
        probe.connect(("192.0.2.1", 9))
        here = probe.getsockname()[0]
    except OSError:  # pragma: no cover — a box with no route at all
        here = "127.0.0.1"
    finally:
        probe.close()
    if here in {"127.0.0.1", "::1", "0.0.0.0", ""}:
        pytest.skip("this machine has no non-loopback address to stand off the box")
    return here


def test_the_search_never_dials_off_this_machine_before_the_workspace_allows_it(
) -> None:
    """`allow-egress: []` in `workspace.yaml` means the model call may not leave
    the box, and `--choose-model` sent it anyway.

    The guard is real and it is in `_bind`, which `score()` calls AFTER
    `_choose`. While the arity crash held the search shut nothing left the box,
    because it died on the line that builds the transport. Opening the door made
    the guard-ordering defect live: measured at 36 requests carrying the agent's
    system prompt and the author's eval cases to a listener on this machine's LAN
    address, in a run whose own report said "this workspace does not let the
    model call leave the box". The same command with `--model` sent nothing.

    A recording server rather than a monkeypatch, and an address that is really
    off the box by `ON_THIS_MACHINE`'s reckoning, because what is being asserted
    is that no packet was sent.

    MUTATION: move the `_egress_refusal` call in `scoring._choose` to after the
    `resolve()` call — this goes red with requests recorded.
    """
    arrived: list[str] = []

    class _Recording(_Answering):
        def do_GET(self) -> None:  # noqa: N802
            arrived.append(self.path)
            super().do_GET()

        def do_POST(self) -> None:  # noqa: N802
            arrived.append(self.path)
            super().do_POST()

    off_box = _somewhere_else()
    server = ThreadingHTTPServer((off_box, 0), _Recording)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        out = open_the_door(f"http://{off_box}:{server.server_address[1]}/v1")
    finally:
        server.shutdown()
        server.server_close()
    said = out.stdout + out.stderr

    assert arrived == [], (
        f"{len(arrived)} request(s) left this box out of a workspace whose "
        f"`allow-egress:` is `[]`, before anything decided whether they may: "
        f"{arrived[:3]}"
    )
    assert "scoring/egress-refused" in said, (
        f"the search dialled off the box and the refusal that exists for it was "
        f"never reached:\n{said}"
    )
    assert "a change a person has to approve" in said, (
        f"the refusal does not say that widening `allow-egress:` is a person's "
        f"decision:\n{said}"
    )


#: What the distribution's served row is called BY THE RUNTIME, from its
#: `also-known-as:` line. A person types `qwen2.5-vl-7b-instruct`; Ollama has
#: `qwen2.5vl:7b` on disk. The two spellings are the point of the test below.
THE_RUNTIME_TAG = "qwen2.5vl:7b"


class _AnswersTheSuite(_Answering):
    """A runtime that gets the author's cases RIGHT — for one model tag only.

    `right_for` decides which tag gets the right answers; every other one gets a
    wrong answer rather than a 404, because the point of the run below is a row
    that ANSWERED and failed beside a row that answered and passed.

    `/api/tags` publishes the RUNTIME spelling and nothing else, which is what
    makes this a real runtime rather than one that answers to anything: a search
    that asks for the catalogue id gets the wrong answers and reports a model
    this machine is serving as one it is not.
    """

    right_for: str = THE_RUNTIME_TAG
    #: Every model id that was posted here, in order, so the test can assert
    #: which spelling the search used rather than infer it from the score.
    asked_for: list = []

    def do_GET(self) -> None:  # noqa: N802
        self._send({"models": [{"name": self.right_for}]})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        try:
            sent = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            sent = {}
        self.asked_for.append(str(sent.get("model") or ""))
        asked = " ".join(
            str(m.get("content") or "") for m in sent.get("messages") or []
        ).lower()
        if sent.get("model") != self.right_for:
            answer = "It depends on the circumstances."
        elif "lamp" in asked:
            answer = "Approved. The lamp arrived damaged within 30 days, refund 40 USD."
        elif "headphones" in asked:
            answer = "Declined. More than 30 days have passed since the purchase."
        elif "fourth refund" in asked:
            answer = "Declined. A person will review this before any refund is issued."
        elif "kettle" in asked:
            answer = (
                "Approved. Refund 60 USD, with the gift card portion returned to "
                "a gift card."
            )
        elif "mug" in asked:
            answer = (
                "Declined. It was a personalised item made to order, so it cannot "
                "be returned unless faulty."
            )
        else:
            answer = "Approved. Sale items follow the same rules and this one was faulty."
        self._send({
            "choices": [{"message": {"content": answer}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 8},
        })


def test_the_door_binds_the_model_that_passed_when_the_agent_s_own_did_not(
    tmp_path: Path,
) -> None:
    """The one branch of this door nobody opened: something PASSES.

    Five of the seven tests this file shipped with assert a refusal, and the two
    that reach a live socket assert which refusal. So the sentence in `--choose-
    model`'s own help — "bind the first that passes the bar" — described a path
    with no coverage, and the path did not exist: `_choose` returned
    `report.model`, which is always the model the agent already named, or an
    error. Measured against the scripted transports the portability suite ships:
    requested `llama3.2-1b-instruct` FAILs, `claude-haiku-4-5 — passes at 83%
    using the 'decomposed' strategy` is found and named, and the command exits
    non-zero with an error over a model that passed.

    Built the same way as the mixed-case test above: an override row that sorts
    first becomes the REQUESTED model, and one HTTP server that answers the
    author's six cases correctly for the distribution's served row and wrongly
    for the override.

    AND THE SERVER ONLY ANSWERS TO THE RUNTIME'S OWN SPELLING, which caught a
    second defect of the same family: the search posted the CATALOGUE id while
    the scoring path one screen up asks `_served` for the tag the runtime has on
    disk. On a real Ollama box every locally-served candidate would have come
    back 404 and been reported as a model this machine is not serving, in the
    same run that then scores it perfectly happily.

    MUTATION: return the `scoring/no-model-passes` refusal from `_choose`
    instead of binding `found.model` — this goes red on the exit code. And
    reverting the `_served` lookup in `_choose`'s `transport_for` turns the
    spelling assertion red.
    """
    root = tmp_path / "refund-desk"
    shutil.copytree(REPO / EXAMPLE, root)
    (root / "models").mkdir(exist_ok=True)
    (root / "models" / "catalog.yaml").write_text(an_override_layer(A_REQUESTED_ROW))

    posted: list = []
    handler = type("_Handler", (_AnswersTheSuite,), {"asked_for": posted})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        out = open_the_door(
            f"http://127.0.0.1:{server.server_address[1]}/v1", workspace=str(root)
        )
    finally:
        server.shutdown()
        server.server_close()
    said = out.stdout + out.stderr

    assert "Traceback" not in out.stderr, out.stderr[-2000:]
    assert out.returncode == 0, (
        f"a model passed the author's own cases and the command still refused:\n"
        f"{said}"
    )
    assert THE_SERVED_ROW in said, (
        f"the model that passed is not named in the report, so the author cannot "
        f"tell what was scored:\n{said}"
    )
    assert A_REQUESTED_ROW in said, (
        f"the report does not say which model was asked for first, so a bound "
        f"model nobody typed arrives unexplained:\n{said}"
    )
    assert "bound" in said, (
        f"the report does not say the model was CHOSEN by measurement:\n{said}"
    )
    assert THE_RUNTIME_TAG in posted, (
        f"the search never asked this runtime for the spelling it actually "
        f"serves, so a model that is on this disk would have come back 404: "
        f"{sorted(set(posted))}"
    )
    assert THE_SERVED_ROW not in posted, (
        f"a catalogue id was posted to the runtime as though it were a tag: "
        f"{sorted(set(posted))}"
    )
