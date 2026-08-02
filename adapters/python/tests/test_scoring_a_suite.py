"""Getting a verdict out of a suite, with no code (D14).

A non-coder could WRITE an eval suite and could not RUN one. `evals.py` was a
library with no entry point — no `main`, no `argparse`, no console script — and
`pact --help` offered `check`, `show`, `waits`, `discover`, `card` and nothing
that produces a score. So the author of `examples/refund-desk/evals/suite.yaml`,
who wrote six cases, a 70% bar, a `population:` line and four rules, had to write
Python to learn whether their agent passes. D14 rules that out for every
capability in the core, and it is worse here than elsewhere: this is the
mechanism the model-portability figure and the learning gate are computed from,
so the one number nobody could reproduce by hand was the number everything
downstream inherited.

**Nothing here is injected.** Every test below runs the real command line against
the real worked example, loaded by the real Rust loader, bound to a real model
row out of `models/catalog.yaml`, over the real Ollama transport. The only thing
that is not the real thing is the *weights*, and they are stood in for by an HTTP
server on a loopback port that speaks the same OpenAI-compatible wire format —
reached with the same `--serving-at` option an author on an air-gapped box types
when their runtime is not on the default port. That is deliberate: a test that
built an `AgentSpec` and called `score()` with a hand-made transport would prove
the object works and say nothing about whether the author's files reach it, which
is the defect this project has shipped five rounds running.

Offline throughout (D17): one loopback socket, no network, no judge unless the
stand-in runtime says it is serving one.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

REPO = Path(__file__).resolve().parents[3]
EXAMPLE = REPO / "examples" / "refund-desk"
PACT_BIN = REPO / "target" / "debug" / "pact"
LAUNCHER = REPO / "scripts" / "pact-eval"

#: The catalogue row the worked example's own `needs.yaml` admits — it is the
#: only one that can see the photos the cases attach. Named here rather than
#: hard-coded into an assertion, because the point is that the command picks it
#: from the files; the tests that pass `--model` pass this one so the stand-in
#: runtime and the command are talking about the same weights.
MODEL = "qwen2.5-vl-7b-instruct"

#: What Ollama calls those weights — the row's own `also-known-as:`. The stand-in
#: runtime advertises this, because that is what a real one advertises.
TAG = "qwen2.5vl:7b"

#: The model the suite's `graded-by:` line names. Served by the stand-in only in
#: the one test about judged rules, so every other test exercises the path where
#: a rule is read and not applied.
GRADER_TAG = "qwen2.5:14b-instruct"


# ─────────────────────────────────────────────────── a runtime, in ninety lines


class _Runtime:
    """An OpenAI-compatible model server that decides refunds from the ticket.

    Deterministic on purpose. This suite is about whether the author's files
    reach a verdict, not about how well any model decides — a live model here
    would measure sampling noise, would need weights nobody can assume, and would
    take ten minutes per run on CPU.

    It answers in two turns, the way a real one does on this agent: look the
    order up, then decide. The tool calls matter — the worked example's own
    suite-level rule is `must-call-before: { call: payments/issue-refund, first:
    payments/look-up-order }`, and a stand-in that never called anything would
    make that rule vacuous exactly where it is load-bearing.
    """

    def __init__(
        self, serves: "tuple[str, ...]" = (TAG,), wrong: str = "", hasty: str = ""
    ) -> None:
        self.serves = serves
        #: Which case key to answer badly, so a suite can be made to miss its
        #: bar without changing anything the author wrote.
        self.wrong = wrong
        #: Which case key to pay out on without looking the order up first. The
        #: author's own suite-level rule forbids exactly that, and it is the one
        #: failure that has to be fatal however good the average is (AD-58a).
        self.hasty = hasty
        self.asked: list[str] = []
        handler = _handler(self)
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/v1"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    # ------------------------------------------------------------- the answers

    def reply(self, model: str, messages: list[dict]) -> dict:
        # Only what came from the customer's side. The system prompt carries the
        # agent's instructions, which mention sums of money of their own, and a
        # stand-in that read the amount out of those would answer every case with
        # the same figure.
        said = " ".join(
            str(m.get("content") or "") for m in messages if m.get("role") == "user"
        )
        self.asked.append(said)
        if model == GRADER_TAG:
            # The judge: two lines, the first a single word. `judge.RUBRIC` says
            # so, and answering in that shape is what makes this a stand-in for a
            # grader rather than a second decision-maker.
            return _text("PASS\nthe reason is one sentence a customer could read")
        if "[result of payments]" not in said:
            # One `payments` call per run and no more. The worked example's own
            # `interceptors/stop-runaway-refunds.yaml` ends any run that calls
            # that tool twice — it counts calls to the tool, not refunds — so a
            # stand-in that looked the order up AND paid out would be stopped by
            # the agent's own rules before it ever answered.
            if _case_of(said) == self.hasty:
                return _tool_call(
                    "payments",
                    {"action": "issue-refund", "order-number": "A-1", "amount": "40 USD"},
                )
            return _tool_call("payments", {"action": "look-up-order", "order-number": "A-1"})
        return _text(_decides_from(said, self.wrong))


def _decides_from(ticket: str, wrong: str) -> str:
    """One refund decision, from the words of the ticket alone.

    Written to satisfy the author's OWN suite — every `expect:`, every
    `must-also:` and every rule under `evals.rules:` — because the thing being
    measured is whether their file decides the verdict, and answers that only
    half-satisfy it would make a PASS mean something else.
    """
    said = ticket.lower()
    key = _case_of(said)
    money = ", ".join(re.findall(r"\d+(?:\.\d+)?\s*(?:USD|GBP|EUR)", ticket))
    if key == wrong:
        # Right on the decision and on the amount, and it breaks exactly one
        # thing: `must-not-contain: ["refund by", "arrive on"]`, the author's own
        # rule about never promising a date they do not control. One case wrong
        # is what puts the suite between the 70% bar they typed and a higher one.
        return (
            f"DECISION: approved. Refunding {money}. Your refund by Friday, and "
            f"the money will arrive on Monday."
        )
    if key == "personalised-item":
        return (
            "DECISION: declined. This is a personalised item made to order, and "
            "personalised items cannot be returned unless they are faulty."
        )
    if key == "fraud-signal":
        return (
            "DECISION: declined. A person will review this request before anything "
            "is paid, because several details do not line up."
        )
    if key == "outside-window":
        return (
            "DECISION: declined. More than 30 days have passed since the purchase, "
            "and a change of mind is only covered inside that window."
        )
    if key == "partial-gift-card":
        return (
            "DECISION: approved. The kettle arrived faulty inside 30 days, so the "
            "60 USD goes back the way it was paid — 20 USD to the gift card and "
            "the rest to the card."
        )
    # `money` is every sum the ticket named, because `01-clear-approve.yaml`
    # expects an `amount:` as well as a decision — a stand-in that answered
    # without one would fail a case for a reason none of these tests is about.
    return (
        "DECISION: approved. The item arrived damaged inside 30 days."
        + (f" Refunding {money}." if money else "")
    )


def _case_of(said: str) -> str:
    """Which of the author's six examples this ticket is, by its own words."""
    if "personalised" in said or "printed with" in said or "dog's name" in said:
        return "personalised-item"
    if "fourth refund" in said or "different from all their previous" in said:
        return "fraud-signal"
    if "45 days" in said:
        return "outside-window"
    if "gift card" in said:
        return "partial-gift-card"
    if "sale" in said or "discounted" in said:
        return "sale-item-damaged"
    return "clear-approve"


def _text(said: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": said}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20}}


def _tool_call(name: str, args: dict) -> dict:
    return {
        "choices": [{"message": {
            "role": "assistant", "content": "Looking the order up.",
            "tool_calls": [{"type": "function", "function": {
                "name": name, "arguments": json.dumps(args)}}],
        }}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20},
    }


def _handler(runtime: "_Runtime"):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args) -> None:  # keep pytest output readable
            pass

        def _send(self, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            # What `judge.served_here` asks, and therefore what the scorer asks
            # to find out whether these weights are on this disk.
            if self.path.rstrip("/").endswith("/api/tags"):
                self._send({"models": [{"name": t} for t in runtime.serves]})
                return
            self.send_error(404)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            asked = json.loads(self.rfile.read(length) or b"{}")
            self._send(runtime.reply(asked.get("model") or "", asked.get("messages") or []))

    return Handler


@pytest.fixture
def runtime():
    served = _Runtime()
    yield served
    served.close()


# ─────────────────────────────────────────────────────────── running the thing


def _scored(where: Path, *options: str, serving_at: str = "") -> tuple[int, str]:
    """Run the command a support lead runs, and hand back what they see."""
    if not PACT_BIN.exists():
        pytest.skip("build the CLI first: cargo build -p pact-cli")
    args = [str(LAUNCHER), str(where), *options]
    if serving_at:
        args += ["--serving-at", serving_at]
    done = subprocess.run(args, capture_output=True, text=True, cwd=REPO, timeout=300)
    return done.returncode, done.stdout + done.stderr


def _percent(report: str, label: str) -> "int | None":
    found = re.search(rf"{label}\s*\((\d+)%\)", report)
    return int(found.group(1)) if found else None


# ───────────────────────────────────────────────────────────── the guarantees


def test_the_command_scores_the_worked_examples_six_cases_against_the_bar_its_author_typed(
    runtime,
) -> None:
    """The whole of the gap, in one line a support lead types.

    Six cases, the 70% bar out of their own `must-pass:` line, and a verdict that
    is PASS, FAIL or UNDECIDED — never two of the three collapsed into one. The
    score and the outcome have to agree with the bar the file carries: a report
    that says PASS under its own bar, or prints a number and an UNDECIDED, is a
    report that cannot be used to decide anything.
    """
    code, report = _scored(EXAMPLE, "--model", MODEL, serving_at=runtime.base_url)

    assert "6 examples" in report, report
    assert "70% of them must come out right" in report, report

    outcome = re.search(r"VERDICT: (PASS|FAIL|UNDECIDED)", report)
    assert outcome, report
    said = outcome.group(1)
    assert code == {"PASS": 0, "FAIL": 1, "UNDECIDED": 2}[said], report

    if said == "UNDECIDED":
        # Allowed, and only with a reason. A suite that could not be scored must
        # say why in words with something to type; a bare UNDECIDED is the same
        # dead end as a number nobody can reproduce.
        assert "fix:" in report, report
        return

    # Every one of the six was run and reported by name, so "83%" can be checked
    # against something rather than believed.
    for case in ("clear-approve", "outside-window", "fraud-signal",
                 "partial-gift-card", "personalised-item", "sale-item-damaged"):
        assert re.search(rf"(PASS|FAIL)  {case}", report), (case, report)

    score = _percent(report, "came out right")
    assert score is not None, report
    assert (said == "PASS") == (score >= 70), report


def test_a_rule_nothing_applied_is_printed_even_when_the_suite_passes(runtime) -> None:
    """The half a green number hides.

    The worked example's fourth rule is `judged: gives the reason in one sentence
    a customer can understand`, and deciding it needs a grading model. The
    stand-in runtime below is not serving the one `graded-by:` names, so that rule
    is read and not applied — and the author has to be told so on the same page as
    the score, not left to infer it from a PASS.
    """
    code, report = _scored(EXAMPLE, "--model", MODEL, serving_at=runtime.base_url)

    assert "VERDICT: PASS" in report, report
    assert code == 0, report
    assert "NOT CHECKED" in report, report
    assert "judged" in report, report
    assert "gives the reason in one sentence" in report, report
    # And with a line to type, like every other diagnostic in this project.
    assert "fix:" in report, report


def test_raising_the_bar_in_the_authors_own_file_turns_the_same_answers_into_a_refusal(
    tmp_path, runtime
) -> None:
    """`must-pass:` REFUSES something, and this is the something.

    Two runs, identical in every respect but one line of one file: the same six
    cases, the same stand-in giving the same answers, the same model row. One
    case answers badly — it promises a date, which the author's own
    `must-not-contain: ["refund by", "arrive on"]` forbids — so five of six come
    out right. At the 70% the author typed that passes; at 95% the same evidence
    is refused, and the command's exit code changes with it.

    Written this way because `bar_of(doc)` reaching a `Verdict` object proves
    nothing on its own: a value can reach an object and still constrain no
    behaviour. What is asserted here is a behaviour that changes when, and only
    when, the author edits their file.
    """
    tree = tmp_path / "refund-desk"
    shutil.copytree(EXAMPLE, tree)
    served = _Runtime(wrong="clear-approve")
    try:
        lenient_code, lenient = _scored(tree, "--model", MODEL, serving_at=served.base_url)

        suite = tree / "evals" / "suite.yaml"
        raised = suite.read_text().replace("must-pass: 70%", "must-pass: 95%")
        assert raised != suite.read_text(), "the bar to raise is not where it was"
        suite.write_text(raised)

        strict_code, strict = _scored(tree, "--model", MODEL, serving_at=served.base_url)
    finally:
        served.close()

    assert "VERDICT: PASS" in lenient, lenient
    assert lenient_code == 0, lenient
    assert "VERDICT: FAIL" in strict, strict
    assert strict_code == 1, strict
    # The same evidence under both bars — so the flip is the author's line and
    # not a different run.
    assert _percent(lenient, "came out right") == _percent(strict, "came out right")
    assert "95%" in strict and "70%" in lenient
    # And the failing case is named with the reason `CaseOutcome.why` carries,
    # because "you are at 83%" without "and here is which one" is not actionable.
    assert "clear-approve" in strict
    assert "'refund by'" in strict and "which it must not" in strict, strict
    assert "we must never promise a date we do not control" in strict, strict


def test_an_example_that_moved_money_and_came_out_wrong_is_fatal_to_a_passing_suite(
) -> None:
    """AD-58a, through the command a support lead types.

    One case pays out without looking the order up first, which is precisely what
    the author's own suite-level `must-call-before:` forbids and what their
    `because:` calls "the expensive mistake". Five of six still come out right, so
    the suite clears the 70% bar they typed — and the command must not report that
    as shippable, because a wrongly-issued refund is not offset by five correct
    decisions.

    Which cases count as money-moving is read off `spends-money: yes` in
    `tools/payments.yaml`, not listed here: an author who marks a second action
    moves this line without touching any code.
    """
    served = _Runtime(hasty="clear-approve")
    try:
        code, report = _scored(EXAMPLE, "--model", MODEL, serving_at=served.base_url)
    finally:
        served.close()

    assert "VERDICT: PASS" in report, report
    assert "MONEY: FAIL" in report, report
    assert "clear-approve" in report, report
    assert "payments/look-up-order" in report, report
    assert "average cannot excuse" in report, report
    # And the exit code follows the money, not the average. A command that
    # printed this and exited 0 would be the same hiding-inside-an-average one
    # layer up from where AD-58a fixed it.
    assert code == 1, report


def test_a_suite_that_never_moved_money_says_so_rather_than_implying_it_checked(
    runtime,
) -> None:
    """`MONEY: nothing to check` is a different fact from `MONEY: PASS`.

    None of these runs reaches a paying action, so nothing about the money path
    was verified — and reporting that as a pass would be a green line covering a
    thing nobody looked at.
    """
    _code, report = _scored(EXAMPLE, "--model", MODEL, serving_at=runtime.base_url)

    assert "MONEY: nothing to check" in report, report
    assert "spends-money" in report, report


def test_a_tool_with_nothing_behind_it_is_named_rather_than_quietly_stubbed(
    runtime,
) -> None:
    """What a score does NOT cover has to be on the same page as the score.

    Scoring connects no tools: an MCP server is a runtime resource, and inventing
    a reply for one would fabricate the evidence the number is built on. What the
    agent DID is still graded — `must-call-before:` is decided off the run's own
    steps — but what `payments` would have answered is not part of this, and an
    author reading a green score is told so.
    """
    _code, report = _scored(EXAMPLE, "--model", MODEL, serving_at=runtime.base_url)

    assert "HOW THIS RUN DIFFERED FROM A REAL ONE" in report, report
    assert "`payments` was called and nothing was connected to it" in report, report
    # And the approval policy, which is switched off for scoring because a run
    # that parks for a person cannot be scored. A governance setting that is
    # silently off in the thing producing the numbers is the defect this whole
    # area exists to prevent.
    assert "approvals did not stop anything" in report, report


def test_the_score_says_which_model_produced_it_and_why_that_one(runtime) -> None:
    """A score is a claim about one model (T4), so the report names it.

    And names how it was chosen, because the worked example pins none: the
    command picks the cheapest row in `models/catalog.yaml` that meets the
    author's own `needs.yaml`, which is the same ranking D11 recommends by. The
    six other locally-served rows are all cheaper and all refused, because they
    cannot see the photos the cases attach.
    """
    _code, report = _scored(EXAMPLE, serving_at=runtime.base_url)

    assert MODEL in report, report
    assert "needs.yaml" in report, report
    assert "nothing pins a model" in report, report


def test_a_model_the_authors_needs_refuse_is_refused_and_a_better_one_named(
    runtime,
) -> None:
    """D11 through this command: refuse, then recommend.

    `--model qwen2.5-7b-instruct` names weights this machine really does serve,
    and `agents/refund-desk/needs.yaml` says the model has to be able to read
    images. Scoring on it anyway would produce a number about a different agent,
    so it is refused — with the name of one that does qualify, which is a line the
    author can type.
    """
    code, report = _scored(
        EXAMPLE, "--model", "qwen2.5-7b-instruct", serving_at=runtime.base_url
    )

    assert code == 2, report
    assert "VERDICT: UNDECIDED" in report, report
    assert "cannot handle images" in report, report
    assert "needs.yaml" in report, report
    assert f"--model {MODEL}" in report, report


def test_scoring_against_a_model_off_the_box_is_refused_where_the_author_wrote_it(
    runtime,
) -> None:
    """`allow-egress: []` is one line and it has to mean something here too.

    The workspace says nothing may talk to anything outside this box. A suite
    scored against a model somewhere else has quietly turned that line off, and
    the number would be a claim about weights this workspace is not allowed to
    use. Refused, naming the file the line is in and both ways out.
    """
    code, report = _scored(
        EXAMPLE, "--model", MODEL, serving_at="http://models.example.com/v1"
    )

    assert code == 3, report
    assert "workspace.yaml" in report, report
    assert "allow-egress" in report, report
    assert "fix:" in report, report


def test_nothing_serving_the_model_is_undecided_and_never_a_score(runtime) -> None:
    """No answers is not the same as wrong answers.

    A box where the model is not running produces UNDECIDED with the line to
    type, never a FAIL — a FAIL would put a model's name against six results it
    never produced, and `verdict()` has three outcomes precisely so that this one
    does not have to be flattened into either of the others.
    """
    empty = _Runtime(serves=())
    try:
        code, report = _scored(EXAMPLE, "--model", MODEL, serving_at=empty.base_url)
    finally:
        empty.close()

    assert code == 2, report
    assert "VERDICT: UNDECIDED" in report, report
    assert TAG in report, report
    assert "fix:" in report, report
    # Every rule the FILES already say nothing will apply is still reported, even
    # though not one case ran. An author whose suite could not be scored still
    # learns which of their rules were never going to be applied.
    assert "6 examples" in report and "70%" in report, report


def test_the_grader_the_author_named_decides_the_judged_rule_when_it_is_running(
    tmp_path,
) -> None:
    """`graded-by:` reaches this command, at the address this command was given.

    `judge_of` binds the default runtime when it is handed no route, so a suite
    scored on `--serving-at X` whose judge quietly ran somewhere else would put
    two models under one number. Here the stand-in serves both, and the judged
    rule stops being reported as unapplied — which is the only observable
    difference between the two arms.
    """
    quiet = _Runtime(serves=(TAG,))
    both = _Runtime(serves=(TAG, GRADER_TAG))
    try:
        _c1, without = _scored(EXAMPLE, "--model", MODEL, serving_at=quiet.base_url)
        _c2, with_judge = _scored(EXAMPLE, "--model", MODEL, serving_at=both.base_url)
    finally:
        quiet.close()
        both.close()

    assert "gives the reason in one sentence" in without, without
    assert "gives the reason in one sentence" not in with_judge, with_judge
    assert "VERDICT: PASS" in with_judge, with_judge


def test_the_report_says_out_loud_what_the_population_line_says_it_covers(
    tmp_path, runtime
) -> None:
    """`population:` is a required, `tier: core` field whose own help ends
    *"Reports say so out loud"* — and for a round no report said anything,
    because the word appeared in zero source files across `crates/*/src` and both
    adapters. A behavioural claim in the schema that nothing kept.

    Two arms, differing by that one line in the author's file, so the sentence is
    demonstrably read rather than printed from a constant.
    """
    _code, authored = _scored(EXAMPLE, "--model", MODEL, serving_at=runtime.base_url)
    assert "the situations you wrote down yourself" in authored, authored
    assert "not everything a customer might send" in authored

    tree = tmp_path / "refund-desk"
    shutil.copytree(EXAMPLE, tree)
    suite = tree / "evals" / "suite.yaml"
    suite.write_text(
        suite.read_text().replace(
            "population: authored-enumeration", "population: promoted-traces"
        )
    )
    _code2, promoted = _scored(tree, "--model", MODEL, serving_at=runtime.base_url)

    assert "real conversations somebody promoted into examples" in promoted, promoted
    assert "the situations you wrote down yourself" not in promoted


def test_the_agent_scored_is_the_one_whose_own_file_points_at_the_checks(
    runtime,
) -> None:
    """`evals: /evals/suite.yaml` in `agent.yaml` decides whose score this is.

    Three agents live in this workspace and one of them names the suite. Nothing
    in either adapter had ever read that line — the Rust side checks the file it
    names exists, and no runtime ever asked whose checks they were — so a
    workspace with more than one agent had no no-code way to say which one a
    score is about.
    """
    _code, report = _scored(EXAMPLE, "--model", MODEL, serving_at=runtime.base_url)

    assert "--agent refund-desk" in report, report
    assert "Refund Desk" in report, report
    # And an agent that does not exist is refused by name, with the real ones.
    code, refused = _scored(EXAMPLE, "--agent", "refund-dest")
    assert code == 3 and "refund-dest" in refused and "fraud-checker" in refused
    # An agent scored against checks its own file does not name gets a number
    # and a sentence saying whose checks they were. "fraud-checker passes" and
    # "fraud-checker passes the refund desk's suite" are different claims, and a
    # reader takes the first unless told the second.
    _code, borrowed = _scored(
        EXAMPLE, "--agent", "fraud-checker", "--model", MODEL,
        serving_at=runtime.base_url,
    )
    assert "does not name any checks of its own" in borrowed, borrowed
    assert "evals/suite.yaml" in borrowed


def test_a_model_pinned_in_the_agents_own_file_is_the_one_scored(
    tmp_path, runtime
) -> None:
    """`model:` is the author's pin and this is a caller that obeys it.

    The shipped example pins none, so the command picks; pinning one in the
    agent's own file has to change which model the report names and says why.
    Asserted through the file rather than through an option, because an option is
    a thing a person types once and a pin is a thing that travels with the folder.
    """
    tree = tmp_path / "refund-desk"
    shutil.copytree(EXAMPLE, tree)
    agent = tree / "agents" / "refund-desk" / "agent.yaml"
    agent.write_text(agent.read_text().replace("name: Refund Desk", f"name: Refund Desk\nmodel: {MODEL}"))

    _code, report = _scored(tree, serving_at=runtime.base_url)

    assert f"model    {MODEL}" in report, report
    assert "pins it" in report, report
    assert "nothing pins a model" not in report, report


def test_a_mistyped_option_is_refused_by_name_with_the_real_ones_listed() -> None:
    """The command line is held to the bar every file is held to.

    `argparse` would answer this with "unrecognized arguments" and a usage dump,
    which names nothing to type. PACT's whole argument to a non-technical author
    is that nothing they type is quietly ignored and every refusal comes with a
    line — the first thing anybody runs is not exempt from it.
    """
    code, report = _scored(EXAMPLE, "--modle", MODEL)

    assert code == 3, report
    assert "--modle" in report, report
    assert "--model" in report, report
    assert "fix:" in report, report


def test_the_report_ends_with_the_line_that_reproduces_it(runtime) -> None:
    """The complaint this whole mechanism answers is a number nobody can
    reproduce by hand. A report that does not say how it was produced is a number
    of that kind however it was computed — so the last line is the command,
    spelled the way the reader typed it rather than the way the module is
    imported."""
    _code, report = _scored(EXAMPLE, "--model", MODEL, serving_at=runtime.base_url)

    assert "Run this again with:" in report, report
    assert "./scripts/pact-eval" in report, report
    assert "--serving-at" in report, report


def test_the_worked_examples_readme_tells_a_support_lead_how_to_get_a_score() -> None:
    """The command is only reachable if somebody is told it exists.

    Held here rather than left to prose review for the reason
    `the_worked_example_readme_matches_the_tree.rs` gives about the table beside
    it: a document that describes a capability decays silently, and the only
    thing that stops it is a test that fails.
    """
    readme = (EXAMPLE / "README.md").read_text()

    assert "scripts/pact-eval" in readme, "the README does not say how to get a score"
    assert "python -m pact_adapters.evals" in readme, (
        "the README names the wrapper and not what it runs, so a reader on a "
        "machine without this checkout has nothing to type"
    )


def test_the_module_form_of_the_command_is_the_one_the_readme_documents() -> None:
    """`python -m pact_adapters.evals` is the entry point, not just the wrapper.

    The wrapper is a convenience that finds an interpreter; the entry point has to
    be the module the README names, or the documented command is a fiction that
    only works from one checkout.
    """
    done = subprocess.run(
        [sys.executable, "-m", "pact_adapters.evals", "--help"],
        capture_output=True, text=True, cwd=REPO,
        env={**os.environ, "PYTHONPATH": str(REPO / "adapters/python/src")},
    )
    assert done.returncode == 0, done.stderr
    assert "python -m pact_adapters.evals" in done.stdout, done.stdout
    assert "--model" in done.stdout and "--serving-at" in done.stdout


# ───────────────────────────────────────── a suite too small to mean anything


def test_a_suite_too_small_to_support_its_own_bar_is_undecided_rather_than_scored(
) -> None:
    """`verdict()`'s five-case floor, which nothing asserted.

    Deleting the floor — `if len(results) < min_cases:` for `if False:` — left
    the whole suite green, so the one line standing between an author and a 100%
    printed off two examples was held by nothing.

    Three arms, because a floor that only fires on failing suites is not a floor:
    a small suite that came out perfect is exactly the one somebody quotes. What
    it must never do is round to FAIL either — a suite nobody could decide has
    produced no evidence, and reporting no evidence as a failure is the same
    flattening in the other direction.

    Imported here rather than at the top of this file on purpose: everything
    above runs the real command against the real tree, and a module-level import
    would make it look as though something in here is injected. This one test is
    about the grading rule itself, and the end-to-end arm below it is about the
    same rule reached through the command.
    """
    from pact_adapters.evals import CaseOutcome, verdict

    def outcomes(n: int, right: int) -> list:
        return [CaseOutcome(f"case-{i}", i < right, "") for i in range(n)]

    perfect = verdict(outcomes(2, 2), 0.7)
    assert perfect.outcome == "UNDECIDED", perfect
    assert "too few" in perfect.note, perfect.note
    assert "needs at least 5" in perfect.note, perfect.note

    poor = verdict(outcomes(3, 0), 0.7)
    assert poor.outcome == "UNDECIDED", "a small suite is not a FAIL either"

    # And one case over the floor is decided, so the floor is a floor and not a
    # refusal to score anything.
    assert verdict(outcomes(5, 5), 0.7).outcome == "PASS"
    assert verdict(outcomes(5, 1), 0.7).outcome == "FAIL"


def test_a_suite_the_author_shrank_below_the_floor_is_undecided_through_the_command(
    tmp_path, runtime
) -> None:
    """The same floor, reached the way an author reaches it: by writing fewer
    examples than the bar they typed can support.

    Two of the six cases are kept and the other four deleted — nothing else in
    the tree changes, so the bar is still the 70% they wrote and the model is
    still the one their `needs.yaml` admits. Both survivors are answered
    correctly, which is the dangerous shape: without the floor this prints
    `VERDICT: PASS` off two examples and exits 0, and 100% of two is the number
    somebody puts in a slide.

    The exit code is asserted beside the words because the words are what a
    person reads and the code is what a pipeline reads, and a gate that says
    UNDECIDED on screen while exiting 0 has told the pipeline it passed.
    """
    tree = tmp_path / "refund-desk"
    shutil.copytree(EXAMPLE, tree)
    cases = tree / "evals" / "cases"
    kept = {"01-clear-approve.yaml", "02-outside-window.yaml"}
    for case in sorted(cases.iterdir()):
        if case.name not in kept:
            case.unlink()
    assert sorted(p.name for p in cases.iterdir()) == sorted(kept)

    code, report = _scored(tree, "--model", MODEL, serving_at=runtime.base_url)

    assert "VERDICT: UNDECIDED" in report, report
    assert code == 2, report
    assert "2 examples" in report, "the report still says how many there were:\n" + report
    assert "too few" in report, report
    # No score is printed beside it. A percentage under an UNDECIDED is a number
    # a reader will quote, and the whole point of the third outcome is that there
    # is nothing here to quote.
    assert "came out right" not in report, report
