"""Questions — what a person is asked, carrying the shape of the answer.

Eve defines a request to a human **structurally**: it is exactly two options,
named approve and deny. Everything else a person might be asked has to borrow
that widget, which is why Eve's own session-token-limit prompt ships as an
Approve/Stop pair rather than as the question it actually is — nothing is being
approved there, someone is being asked whether to keep spending. A question
needing a number, a choice of three, or a sentence has nowhere to go at all.

Here a question carries its own answer schema:

    asks                the fixed wording the person reads
    answer              what a valid answer looks like     <- the schema
    shows               which values to put in front of them
    asked-of            who is asked
    answer-within       how long they have
    if-nobody-answers   what happens when they don't

**Approval is not a concept in this module.** It is `Question.approval(...)`,
whose answer schema is one yes-or-no field, built from the same class as every
other question. The four HITL decision kinds the architecture names (HARN-3:
approve, approve-with-override-args, deny, respond-on-behalf) stop being four
kinds of *request* and become four shapes of one typed *answer*:

    {approved: yes}                  approve
    {approved: yes, amount: 25 USD}  approve, with the person's figure
    {approved: no}                   deny
    {instead: "..."}                 answer on the agent's behalf

`Shape` is the piece [`suspension.Expect`] uses, so a suspension asks for the
same typed thing a question does — there is one vocabulary for "what may come
back", not one per subsystem.

Two properties here are structural rather than checked:

* **Silence can never approve.** `when_nobody_answers` has no branch able to
  produce `approved: True`, and the schema's `if-nobody-answers` has no such
  word in its list, so a timeout cannot be configured into a yes.
* **Model text cannot forge a section of what an approver reads.** Values are
  rendered as quoted, length-capped, control-stripped data in their own labelled
  region and are never folded into the author's sentence — architecture Y18/AD-46,
  where every structural control held and the last hop into the only human
  control in the system was still string concatenation.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

#: One diagnostic shape for the whole adapter — see `diagnostics`. A rule this
#: vocabulary cannot decide names the real file and the real line, exactly as a
#: mistake in a context policy or an interceptor does.
from .diagnostics import locate
from .yes_no import said_yes


class Rejected(ValueError):
    """An answer that does not fit its question, or a question that cannot be asked.

    Carries one line per problem, each naming what is wrong and a fix that can
    be typed — the same bar the file-level diagnostics hold.
    """

    def __init__(self, problems: list[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


# ───────────────────────────────────────────────────────────────────── shapes


#: Every way a person says yes, and every way they say no. `approve`, `granted`
#: and `carry-on` are here because they are what somebody answering an approval,
#: a permission request or a budget question actually types — they used to be a
#: table in `suspension`, one row per kind of wait, which is the shape Eve is
#: stuck in. One vocabulary means a new kind of wait needs no new word.
_YES = {"yes", "y", "true", "on", "enabled", "approve", "approved", "granted",
        "carry-on", "carry on", "keep-going", "keep going"}
_NO = {"no", "n", "false", "off", "disabled", "decline", "declined", "deny",
       "denied", "refused", "stop"}
_MONEY = re.compile(
    r"^\s*(?:(?P<sym>\$)\s*(?P<a1>-?[\d.]+)"
    r"|(?P<a2>-?[\d.]+)\s+(?P<c2>[A-Za-z]{3})"
    r"|(?P<c3>[A-Za-z]{3})\s+(?P<a3>-?[\d.]+))\s*$"
)

#: Every spelling of every shape, including the shape's own name so that a
#: question which has crossed a process boundary parses back into what it left
#: as. Deliberately the words an author already met in `answers-with:` — a
#: second vocabulary would be a second thing to learn for no gain.
#: NINE, matching `&the-answer-shapes` in spec/schema.yaml:308 exactly. Five for
#: a round, which meant a question asking a person for a photo, a voice note or
#: an attachment passed `pact check` — the schema's own help for `question.answer`
#: lists all nine and promises *"anything else is refused here rather than at the
#: moment a person is waiting"* — and then raised `Rejected` when the agent
#: started. That is the "loads clean, fails later, in another language, in a
#: process the author never starts" failure the `shapes:` attribute exists to end,
#: and it blocked D16's stated v1 modalities at the one surface where a person is
#: asked. `test_typed_questions.py` holds this list against the specification's.
_SPELLINGS: Mapping[str, frozenset[str]] = {
    "yes-or-no": frozenset({"yes-or-no", "yes or no", "yes-no", "yes/no", "boolean"}),
    "text": frozenset({"text", "some text", "a sentence", "a note"}),
    "money": frozenset({"money", "an amount of money", "an amount"}),
    "number": frozenset({"number", "a number"}),
    "whole-number": frozenset({"whole-number", "whole number", "a whole number", "integer"}),
    "images": frozenset({"images", "a picture", "pictures", "list of images", "an image"}),
    "audio": frozenset({"audio", "a recording", "a voice message", "list of audio"}),
    "file": frozenset({"file", "a file", "an attachment", "list of files"}),
    "agent": frozenset({"agent", "an agent", "which agent", "the name of an agent"}),
}

_DESCRIBED: Mapping[str, str] = {
    "yes-or-no": "yes or no",
    "text": "some text",
    "money": "an amount of money, like `25.00 USD`",
    "number": "a number",
    "whole-number": "a whole number",
    "images": "one or more pictures",
    "audio": "a recording",
    "file": "a file",
    "agent": "the name of one of this workspace's agents",
}

#: The three shapes whose value is a path to a file in this workspace.
#:
#: One name for one wire form. `images`, `audio` and `file` differ in what the
#: model is told the file IS, not in how it is written down, and giving them
#: three spellings is how `B19`'s currency divergence happened one type over.
_A_PATH: frozenset[str] = frozenset({"images", "audio", "file"})


def _a_path_inside_the_workspace(value: Any, described: str) -> str:
    """`evals/attachments/receipt.png` — and nothing that climbs out of the tree.

    The same rule `file-name` already makes one level down, one level up: no
    leading `/`, no `..`, no `~`. A portable folder whose answer names
    `/etc/passwd` or `../../secrets` is not portable and not safe, and the
    refusal says what to type instead rather than that the value is bad.
    """
    written = str(value).strip()
    if not written:
        raise Rejected([f"should be {described}, and it is empty"])
    if written.startswith(("/", "~")) or "://" in written:
        raise Rejected([
            f"should be {described} inside this workspace, and `{written}` is "
            f"somewhere else. Write it relative to the workspace root, like "
            f"`evals/attachments/receipt.png`."
        ])
    parts = written.replace("\\", "/").split("/")
    if any(p == ".." for p in parts):
        raise Rejected([
            f"should be {described} inside this workspace, and `{written}` climbs "
            f"out of it. Write it relative to the workspace root, like "
            f"`evals/attachments/receipt.png`."
        ])
    return "/".join(p for p in parts if p not in ("", "."))


_EXAMPLE: Mapping[str, str] = {
    "yes-or-no": "yes",
    "text": "a sentence",
    "money": "25.00 USD",
    "number": "1.5",
    "whole-number": "3",
    "images": "a picture",
    "audio": "a recording",
    "file": "a file",
    # A KIND, not a name, and it is the only row here that has to be.
    #
    # `25.00 USD`, `3` and `yes` are literals anybody can type in any workspace;
    # `a sentence`, `a picture` and `a recording` read as descriptions of a kind.
    # This row said `refund-desk` — the flagship example's own agent — and
    # `Shape.example()` is the line a person is told to type, word for word. So a
    # hospital workspace holding `triage` and `x-ray` told a clinician with a
    # patient waiting to `Add \`who: refund-desk\``, which resolves to nothing.
    #
    # That is R56 one layer worse: there the AUTHOR was told their file said
    # something it does not; here the reader is not the author and cannot go and
    # look. An answer shape whose values are names from THIS tree cannot have a
    # correct literal here, so it does not pretend to.
    "agent": "the name of an agent in this workspace",
}


@dataclass(frozen=True)
class Shape:
    """One line of an answer's schema: `yes or no`, `money`, `one of a, b`.

    This is the whole of G7 in one class. Eve's equivalent is not a class at
    all: approval is two literal option objects, so there is no place a shape
    could be written down even if someone wanted to.
    """

    kind: str
    choices: tuple[str, ...] = ()

    @staticmethod
    def parse(written: Any) -> "Shape":
        s = " ".join(str(written).strip().lower().split())
        for prefix in ("one of ", "one-of ", "either "):
            if s.startswith(prefix):
                rest = s[len(prefix):].replace(" or ", ", ")
                choices = tuple(c.strip() for c in rest.split(",") if c.strip())
                if not choices:
                    raise Rejected([
                        f"'{written}' does not say what to choose between. "
                        "Write it like `one of approved, declined`."
                    ])
                return Shape("one-of", choices)
        for kind, spellings in _SPELLINGS.items():
            if s in spellings:
                return Shape(kind)
        raise Rejected([
            f"'{written}' is not a shape an answer can have. Use one of: "
            + ", ".join(_DESCRIBED[k] for k in _SPELLINGS)
            + " — or `one of a, b, c`."
        ])

    def written(self) -> str:
        """The spelling that parses back to this — what `to_json` writes."""
        return "one of " + ", ".join(self.choices) if self.kind == "one-of" else self.kind

    def describe(self) -> str:
        if self.kind == "one-of":
            return "one of: " + ", ".join(self.choices)
        return _DESCRIBED[self.kind]

    def example(self) -> str:
        if self.kind == "one-of":
            return self.choices[0]
        return _EXAMPLE[self.kind]

    def read(self, value: Any) -> Any:
        """Coerce `value` into this shape, or raise `Rejected`.

        Accepts the spellings a person naturally types (`y`, `Yes`, `$25`,
        `approve`), because refusing them teaches nothing and costs a round
        trip — the bargain `pact-schema::coerce` already strikes for files.
        """
        if self.kind == "yes-or-no":
            if isinstance(value, bool):
                return value
            word = str(value).strip().lower()
            if word in _YES:
                return True
            if word in _NO:
                return False
        elif self.kind == "text":
            if isinstance(value, str):
                return value
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return str(value)
        elif self.kind == "money":
            m = _MONEY.match(str(value))
            if m:
                amount = m.group("a1") or m.group("a2") or m.group("a3")
                currency = "USD" if m.group("sym") else (m.group("c2") or m.group("c3"))
                try:
                    return f"{float(amount):.2f} {currency.upper()}"
                except ValueError:
                    pass
        elif self.kind == "number":
            if isinstance(value, bool):
                raise Rejected([f"should be {self.describe()}, but it is '{value}'"])
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
        elif self.kind == "whole-number":
            if not isinstance(value, bool):
                try:
                    return int(str(value).strip())
                except (TypeError, ValueError):
                    pass
        elif self.kind == "one-of":
            word = str(value).strip().lower()
            for c in self.choices:
                if c.lower() == word:
                    return c
        elif self.kind in _A_PATH:
            # A12. `_SPELLINGS` accepted `images`, `audio` and `file` and this
            # branch did not exist, so every one of them fell to the raise below
            # — and `examples/refund-desk/agents/refund-desk/agent.yaml` declares
            # `photos: list of images`, which means the flagship could not read
            # its own declared input. Two hand-maintained lists in one class,
            # held to each other by nothing; `every_shape_the_spellings_accept_can_be_read`
            # is what now holds them.
            #
            # The wire form is a WORKSPACE PATH: a file inside this workspace,
            # written relative to its root. Deciding that here rather than
            # accepting any string is the whole content of the fix — B19 is the
            # same modality question answered four different ways in two ports,
            # and a picture has to mean the same thing on either side.
            return _a_path_inside_the_workspace(value, self.describe())
        if self.kind == "agent":
            written = str(value).strip()
            plain = bool(written) and all(
                ch.isascii() and (ch.isalnum() or ch == "-") for ch in written
            )
            if plain and not written.startswith("-") and not written.endswith("-"):
                # Whether an agent by this name EXISTS is the checker's
                # question, asked where the document is in scope — the same
                # division `file` makes for paths.
                return written
            raise Rejected([
                f"should be {_DESCRIBED['agent']}, written as its key — like "
                f"`refund-desk` — and `{value}` is not one"
            ])
        raise Rejected([f"should be {self.describe()}, but it is '{value}'"])


#: Free text, for a wait that has no closed answer — a teammate's reply.
ANYTHING = Shape("text")

#: The name of one of this workspace's agents. Beside `ANYTHING`, and for the
#: same reason it is here rather than at its reader: a `Shape` a caller builds
#: for itself is the closed vocabulary copied out, and `_SPELLINGS` above is the
#: one place that decides what `an agent` and `which agent` both mean.
#:
#: Its reader is `harness.run`'s admission pass (P4), which turns a supplied
#: `run-inputs:` value of this shape into a delegate the model may hand work to.
#: `read` is what says a value is a plain key and not a path, an address or a
#: sentence — the same division `file` makes, one shape over: whether an agent
#: by this name EXISTS stays the checker's question, asked where the document is
#: in scope.
AN_AGENT = Shape("agent")


# ─────────────────────────────────────────────────────────────────── questions


#: The three answer names the loop itself reads. Everything else in an answer
#: that names an argument of the pending action REPLACES that argument, which is
#: the symmetric partner of `action.inspects:` — the arguments a gate may look at
#: are the ones a person may set.
APPROVED = "approved"
BECAUSE = "because"
INSTEAD = "instead"

#: Longest a shown value may be before it is cut. A page of model prose pasted
#: into an approval screen is a way to hide the number that matters.
SHOW_LIMIT = 200


#: The question the ONE-LINE gate puts — `needs-a-person: yes` on an action (F17).
#:
#: Gating one action used to cost three files and thirteen lines: a question, a
#: policy file, and a rule inside it. Eve charges one file and two lines
#: (`approval: 'always'` beside the tool), and a measured first-time author needed
#: four rounds of diagnostics — and four concepts — before their first gate held.
#: That was the one surface where this format was harder to author in than the
#: system it has to beat.
#:
#: The `pact:` prefix is the one `loop:` already uses for a shipped shape
#: (`pact:loop/standard`), so an author who has met one has met this. It cannot
#: collide with anything in `questions/`: `pact:question/is-this-ok.yaml` is not
#: a filename.
SHIPPED_QUESTION = "pact:question/is-this-ok"

#: The questions PACT ships, mirroring `spec/questions/*.yaml` byte for byte in
#: meaning — the same arrangement `loops.LIBRARY` has, for the same reason. An
#: adapter reads the loaded document and never the author's tree (invariant P-1),
#: and `spec/` is not the author's tree either, so the shipped wording lives here
#: as well as there and `test_a_gate_written_in_one_line.py` reads the YAML
#: through `Question.from_document` — the same door an author's own question goes
#: through — and refuses to let the two drift.
#:
#: `shows:` and `because:` are deliberately absent and are filled in from the
#: ACTION being gated (see [`gated_actions`]), so a person reads which tool is
#: about to do what and the values it was called with, rather than a placeholder.
LIBRARY: Mapping[str, Mapping[str, Any]] = {
    SHIPPED_QUESTION: {
        "description": (
            "The yes-or-no PACT puts when an action says it needs a person and "
            "nothing else is written."
        ),
        "says": "Somebody has to say yes before this runs.",
        "answer": {"approved": "yes or no", "because": "text"},
        # Not a team name: this file does not know your teams. Whoever is
        # running the agent is the one party that certainly exists, and naming
        # somebody else is the one thing that needs the longer form.
        "asked-of": ["whoever-is-running-this"],
        "answer-within": "30m",
        # Never `escalate` — there is nobody here to escalate TO, so the deadline
        # would dead-end. Never `decline` either: a run that carries on having
        # been refused by nobody looks, from the outside, exactly like a run a
        # person turned down.
        "if-nobody-answers": "stop-and-say-so",
    }
}


@dataclass(frozen=True)
class Question:
    """Something a person is asked, carrying the shape of the answer it expects."""

    name: str
    asks: str
    #: The schema. One entry per thing wanted back.
    answer: Mapping[str, Shape]
    #: What this is about — the pending action, once it is bound to one.
    about: str = ""
    #: Why a person is needed. Comes from the rule that fired, and is shown.
    because: str = ""
    #: Which of the action's values to put in front of the person.
    shows: tuple[str, ...] = ()
    #: Those values once pulled out of the action, kept apart from `shows` so
    #: that what to show survives being asked about a different action.
    showing: Mapping[str, Any] = field(default_factory=dict)
    asked_of: tuple[str, ...] = ()
    answer_within: str = ""
    if_nobody_answers: str = "decline"
    escalates_to: tuple[str, ...] = ()
    #: A carried program that looks at the answer before the run goes on with it
    #: (P8 wave 4) — the check a SHAPE cannot make. Empty for almost every
    #: question, which is why nothing about the ordinary path changes.
    checked_by: str = ""

    # -- approval is one of these, not a kind of its own --------------------

    @staticmethod
    def approval(about: str = "", **kw: Any) -> "Question":
        """The boolean-schema case. Note there is no second class for it.

        Its schema is one yes-or-no field and nothing else, so the shorthand a
        caller may already be using — "these tool names are approved" — is a
        complete, valid answer to it.
        """
        return Question(
            name=kw.pop("name", "is-this-ok"),
            asks=kw.pop("asks", "Please check this before it happens."),
            answer={APPROVED: Shape("yes-or-no")},
            about=about,
            **kw,
        )

    def about_call(self, name: str, args: Mapping[str, Any], because: str = "") -> "Question":
        """Point this question at one pending action, pulling `shows` out of it."""
        return replace(
            self,
            about=name,
            because=because or self.because,
            showing={k: args[k] for k in self.shows if k in args},
        )

    # -- what a person sees -------------------------------------------------

    def for_person(self) -> str:
        """One canonical rendering, in labelled regions.

        There is deliberately no way to interpolate a value into `asks`: the
        wording is the author's and the values are data, and they are printed in
        different places. A caller rendering this cannot accidentally
        concatenate them, which is the failure Y18 records.
        """
        lines = [self.asks]
        if self.because:
            lines.append(f"why: {self.because}")
        for label, value in self.showing.items():
            lines.append(f"{label}: {quoted(value)}")
        if self.asked_of:
            lines.append("asked of: " + ", ".join(self.asked_of))
        if self.answer_within:
            lines.append(f"answer within: {self.answer_within}")
        lines.append(
            "answer with: "
            + ", ".join(f"{k} ({s.describe()})" for k, s in self.answer.items())
        )
        return "\n".join(lines)

    # -- answers ------------------------------------------------------------

    def validate(
        self,
        raw: Mapping[str, Any],
        run_program: "Callable[[str, dict[str, Any]], str] | None" = None,
    ) -> "Answer":
        """Read an answer, or raise `Rejected` saying exactly what to type.

        Every field the schema declares must be present. There is no optional
        marker on purpose: a schema with a field the author did not want
        answered is a schema with a field too many, and a hidden marker is one
        more thing a non-technical author would have to know about.
        """
        problems: list[str] = []
        values: dict[str, Any] = {}

        for key in raw:
            if key not in self.answer:
                problems.append(
                    f"'{self.name}' does not ask for '{key}'. Remove that line, "
                    f"or use one of: {', '.join(self.answer)}."
                )

        for key, shape in self.answer.items():
            if key not in raw:
                problems.append(
                    f"'{self.name}' has not been answered: '{key}' is missing. "
                    f"Add `{key}: {shape.example()}`."
                )
                continue
            try:
                values[key] = shape.read(raw[key])
            except Rejected as e:
                problems.append(
                    f"'{key}' {e.problems[0]}. Write it like `{key}: {shape.example()}`."
                )

        if problems:
            raise Rejected(problems)

        # The check a shape cannot make (P8 wave 4). LAST, so the program is
        # handed values that are already the kind the author declared and never
        # has to re-implement the shape vocabulary.
        if self.checked_by:
            if run_program is None:
                # Refused, not passed. An author who wrote a check, watched it
                # load and never had it run is the failure this line exists to
                # remove, arriving one level up — and a person told nothing is a
                # person who believes they were checked.
                raise Rejected([
                    f"'{self.name}' is checked by the program '{self.checked_by}', and "
                    f"nothing here can run a carried program — so this answer could not "
                    f"be checked and has not been accepted. Whatever runs your agents "
                    f"has to supply a locked room for programs."
                ])
            try:
                said = run_program(self.checked_by, dict(values))
            except Exception as e:  # noqa: BLE001 — a grader's failure is data
                raise Rejected([
                    f"'{self.name}' is checked by the program '{self.checked_by}', and it "
                    f"could not run: {e}. The answer has not been accepted."
                ]) from e
            # An empty answer, or the word `ok`, is the program saying nothing is
            # wrong. Anything else is what it wants the person to read — its own
            # sentence, because it is the thing that knows why.
            objection = str(said).strip()
            if objection and objection.lower() not in {"ok", "yes", "true"}:
                raise Rejected([objection])

        return Answer(question=self.name, about=self.about, values=values)

    # -- the deadline -------------------------------------------------------

    def when_nobody_answers(self) -> "Unanswered":
        """What happens at the deadline. It can never be an approval.

        The result is not validated against the schema, because it is not an
        answer — it is what happens when there isn't one. That is why it is a
        separate method rather than a default value: a default satisfying the
        schema would be indistinguishable from a person having typed it.
        """
        if self.if_nobody_answers == "escalate":
            if not self.escalates_to:
                raise Rejected([
                    f"question '{self.name}' escalates when nobody answers, but "
                    "names nobody to escalate to. Add a line: "
                    "`escalates-to: [a team]`."
                ])
            # The next people are asked the very same question, once. If they
            # stay silent too the run stops and says so — exactly what
            # `suspension.Suspension.escalate` does to the wait — because an
            # escalation that could escalate again would re-ask the same
            # `escalates-to:` audience for ever.
            return Unanswered(
                self, "escalate",
                ask_instead=replace(
                    self, asked_of=self.escalates_to,
                    if_nobody_answers="stop-and-say-so", escalates_to=(),
                ),
            )
        if self.if_nobody_answers == "stop-and-say-so":
            return Unanswered(
                self, "stop-and-say-so",
                stop_because=f"nobody answered '{self.name}'{self._in_time()}",
            )
        return Unanswered(
            self, "decline",
            answer=Answer(
                question=self.name,
                about=self.about,
                values={APPROVED: False, BECAUSE: f"nobody answered{self._in_time()}"},
                from_silence=True,
            ),
        )

    def _in_time(self) -> str:
        return f" within {self.answer_within}" if self.answer_within else ""

    # -- crossing a process boundary ---------------------------------------

    def to_json(self) -> dict[str, Any]:
        """Everything needed to ask this again in another process.

        A parked run outlives the process that parked it (D23), so the question
        travels with it. Re-deriving it on the far side would let a person be
        shown wording that no longer matches what was asked.
        """
        return {
            "name": self.name,
            "asks": self.asks,
            "answer": {k: s.written() for k, s in self.answer.items()},
            "about": self.about,
            "because": self.because,
            "shows": list(self.shows),
            "showing": dict(self.showing),
            "asked-of": list(self.asked_of),
            "answer-within": self.answer_within,
            "if-nobody-answers": self.if_nobody_answers,
            "escalates-to": list(self.escalates_to),
            "checked-by": self.checked_by,
        }

    @staticmethod
    def from_json(d: Mapping[str, Any]) -> "Question":
        return Question(
            name=str(d.get("name", "")),
            asks=str(d.get("asks", "")),
            answer={k: Shape.parse(v) for k, v in (d.get("answer") or {}).items()},
            about=str(d.get("about", "")),
            because=str(d.get("because", "")),
            shows=tuple(d.get("shows") or ()),
            showing=dict(d.get("showing") or {}),
            asked_of=tuple(d.get("asked-of") or ()),
            answer_within=str(d.get("answer-within", "")),
            if_nobody_answers=str(d.get("if-nobody-answers", "decline")),
            escalates_to=tuple(d.get("escalates-to") or ()),
            checked_by=str(d.get("checked-by", "")),
        )

    # -- from the authored document ----------------------------------------

    @staticmethod
    def from_document(doc: Mapping[str, Any], name: str) -> "Question":
        """Build one from the loaded PACT document. No author code (D14).

        A `pact:question/...` name resolves against [`LIBRARY`] instead of the
        workspace, which is the same fallback `Loop.resolve` makes for
        `pact:loop/standard`. The shipped question then goes through EXACTLY this
        constructor — the answer shapes are parsed here, the `escalate`-with-
        nobody-to-escalate-to rule is applied here — so a gate written in one
        line cannot end up built by a quieter code path than one written in
        thirteen.
        """
        questions = doc.get("questions") or {}
        if name not in questions and name in LIBRARY:
            questions = {**questions, name: LIBRARY[name]}
        if name not in questions:
            known = ", ".join(sorted(questions)) or "none"
            raise Rejected([
                f"no question named '{name}'. This workspace has: {known}. "
                f"Add a file `questions/{name}.yaml`, or correct the name."
            ])
        q = questions[name] or {}
        shapes: dict[str, Shape] = {}
        problems: list[str] = []
        for key, written in (q.get("answer") or {}).items():
            try:
                shapes[key] = Shape.parse(written)
            except Rejected as e:
                problems.append(f"question '{name}', answer line '{key}': {e.problems[0]}")
        if not shapes and not problems:
            problems.append(
                f"question '{name}' does not say what an answer looks like. Add an "
                "`answer:` section, for example a line `approved: yes or no`."
            )

        escalates = tuple(_as_list(q.get("escalates-to")))
        if str(q.get("if-nobody-answers", "")).strip() == "escalate" and not escalates:
            # The schema cannot say "required when another field has this value"
            # without growing a conditional language, so it is checked here
            # rather than left to fail silently at the deadline.
            problems.append(
                f"question '{name}' escalates when nobody answers, but names nobody "
                "to escalate to. Add a line: `escalates-to: [a team]`."
            )
        if problems:
            raise Rejected(problems)

        return Question(
            name=name,
            asks=str(q.get("says", "")).strip(),
            answer=shapes,
            shows=tuple(_as_list(q.get("shows"))),
            asked_of=tuple(_as_list(q.get("asked-of"))),
            answer_within=str(q.get("answer-within", "")).strip(),
            if_nobody_answers=str(q.get("if-nobody-answers", "decline")).strip(),
            escalates_to=escalates,
            checked_by=str(q.get("checked-by", "")).strip(),
        )

    @staticmethod
    def all_from_document(doc: Mapping[str, Any]) -> dict[str, "Question"]:
        """Every question in the workspace, so a bad one is reported at load."""
        return {n: Question.from_document(doc, n) for n in sorted(doc.get("questions") or {})}


#: The two reasons to wait that ONE call can carry at the same time. Spelled out
#: rather than imported because `suspension` imports this module and not the
#: other way round; `test_connection_consent.py` pins both strings to
#: `suspension.NEEDS_PERMISSION` and `suspension.NEEDS_APPROVAL` so the two files
#: cannot drift apart in silence.
NEEDS_PERMISSION = "needs-permission"
NEEDS_APPROVAL = "needs-approval"

#: **Consent before approval.** This line is the decision, not a consequence of
#: one — it is the thing §7.14 gap (1) says nobody had made.
#:
#: `payments` carries rules from two of the author's files: a threshold in
#: `policies/approvals.yaml` and an `asks-to-connect:` in
#: `resources/payments-server.yaml`. A 300 USD refund needs both, and until this
#: line existed which one a person met first fell out of declaration order — a
#: `setdefault` on the harness's `gated` map, which is not a choice anybody made.
#:
#: Consent first, because the two questions are not the same size. *May we use
#: the payments connection at all?* is asked once and governs every refund that
#: will ever go over it; *is THIS refund right?* is about one call. Asking the
#: second first spends a person's attention on a payment that may turn out to be
#: unmakeable, and puts an approval on record for a refund a later *no* on the
#: connection silently voids — a yes in the audit trail for something that never
#: happened. The other order has no such hole: a no on the connection ends it
#: before anybody is asked about the money.
#:
#: A reason not named here is asked after both, in its own name's order, so an
#: author's `x-` reason needs no row and no edit.
ASKED_IN_ORDER: tuple[str, ...] = (NEEDS_PERMISSION, NEEDS_APPROVAL)


def _asked_in_order(reason: str) -> tuple[int, str]:
    """Where one reason comes in the order a person is asked them."""
    place = ASKED_IN_ORDER.index(reason) if reason in ASKED_IN_ORDER else len(ASKED_IN_ORDER)
    return (place, reason)


@dataclass(frozen=True)
class Wait:
    """One reason one call has to stop, and the name its answer goes under.

    The second field is why this is a pair rather than a bare string. A call can
    have two reasons at once, and if both answers were named after the call they
    would be the same name: `questions/may-we-connect.yaml` and
    `questions/is-this-ok.yaml` both ask for `approved` and `because`, and a
    person allowing the connection would have approved the refund they were never
    shown. So each wait is named after the thing whose file said to wait —
    consent after the CONNECTION (`payments-server`, the file the author wrote
    `asks-to-connect:` in), approval after the CALL.

    Empty means the call's own name, which is every wait a host seeds through
    `run(gates=)`: the host named a tool, so the wait is about that tool.
    """

    reason: str
    asked_as: str = ""


@dataclass(frozen=True)
class Gate(MappingABC):
    """Which question to put about which thing — one entry per RULE, not per tool.

    It used to be a plain `dict[str, Question]` keyed by the tool's head name,
    filled in rule order. Two rules over one tool therefore collapsed to one and
    the last won: `examples/refund-desk/policies/approvals.yaml` asks
    `is-this-ok` above 200 USD and `how-much-to-refund` above 500, and a 210 USD
    refund was put to a person as the 500 USD question — with the lower rule's
    `because:` never shown and nothing anywhere reporting the loss. That is the
    silent degradation of a governance setting T7 forbids.

    So a thing maps to the rules about it, in the author's order, and
    [`for_call`] picks between them from the arguments the model actually chose.
    It still behaves as a mapping, because most things have exactly one rule and
    a caller that has no arguments to hand — a teammate, a budget — should not
    have to know that.
    """

    rules: Mapping[str, tuple["Rule", ...]]
    #: Rules this vocabulary cannot decide before the run starts, each already a
    #: sentence naming the file, the line, what could not be decided and a line
    #: to type. Carried rather than dropped for the reason `RunResult.unmetered`
    #: exists one subsystem over: a governance rule that quietly does nothing is
    #: the silent degradation T7 forbids, and it is worse here than for a ceiling
    #: because the author's own comment calls it "enforcement, not a note in the
    #: instructions".
    #:
    #: An action-scoped rule used to be listed here, at load, for every run. It
    #: is not any more: whether `zendesk/reply` can be applied is a fact about a
    #: CALL — the one that says `action: reply` is stopped — so that half is said
    #: per call by [`undecided_on`] and only about calls it really could not
    #: decide.
    unenforced: tuple[str, ...] = ()
    #: What each tool's `actions:` block declares. Read for one thing only:
    #: deciding a call that does not say which action it is, when the author has
    #: written a rule about every action it could be. Empty for a gate built by
    #: hand from `{thing: question}`, which describes no tool at all.
    actions_of: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    # -- the mapping face, for the things that have one rule ----------------

    def __getitem__(self, key: str) -> Question:
        return self.rules[key][0].question

    def __iter__(self) -> Iterator[str]:
        return iter(self.rules)

    def __len__(self) -> int:
        return len(self.rules)

    @staticmethod
    def of(source: "Gate | Mapping[str, Question] | None") -> "Gate":
        """Accept either face. A caller with a plain `{thing: question}` map —
        a test, a host wiring one question by hand — is describing one rule per
        thing, so that is what it becomes."""
        if isinstance(source, Gate):
            return source
        return Gate({k: (Rule(q),) for k, q in dict(source or {}).items()})

    # -- the rule face ------------------------------------------------------

    def for_call(
        self, name: str, args: Mapping[str, Any], reason: str = ""
    ) -> "Question | None":
        """The question this call actually deserves.

        Among the rules whose `when:` this call satisfies, the **narrowest**
        wins — the one with the highest threshold. That is what the author's two
        lines mean read together: over 200 a person approves the figure, over
        500 a person sets it, and 600 is both.

        An atom PACT cannot evaluate counts as satisfied. Failing to ask is the
        dangerous direction, so an unrecognised condition widens the gate rather
        than closing it.

        `reason` is why the run stopped, and it narrows before anything else
        does. One name can carry rules for two reasons — `payments` is guarded
        by an approval policy AND by `resources/payments-server.yaml`'s
        `asks-to-connect:` — and a gate that is not told which one stopped the
        run puts the first rule it has. Measured on the worked example: a
        `needs-permission` park on `payments` rendered *"Please check this
        before it happens."* with a 30-minute deadline, which is `is-this-ok`,
        the refund-approval question. The person was asked to approve a refund
        when what was actually waiting was whether this desk may use the
        payments connection at all. Empty means "any", so every caller that has
        no reason to give behaves exactly as it did before.
        """
        candidates = self.rules.get(name) or ()
        # A rule written for THIS reason answers it, and it answers it alone. A
        # rule written for no particular reason answers any wait, and is reached
        # only when no rule was written for this one. Falling back to the whole
        # list when neither exists is deliberate: a park with the wrong wording is
        # bad, and a park with no wording at all is worse.
        #
        # The two used to be one bucket — "not written for a DIFFERENT reason" —
        # and `narrowness` then chose between them, so the rule with a threshold
        # beat the rule written for the wait. Measured: a `needs-permission` park
        # on a 300 USD refund rendered *"Please check this before it happens. why:
        # a refund over 200 USD is a management decision"* while asking for
        # `payments-server`, so a person was shown the refund question and their
        # answer went to the connection. It held at 40 USD only because no
        # approval rule fired there — the fix was passing on an amount, not on a
        # reason.
        fitting = tuple(r for r in candidates if r.for_reason == reason)
        candidates = fitting or tuple(r for r in candidates if not r.for_reason) or candidates
        if not candidates:
            return None
        fired = [r for r in candidates if r.fires_on(args)]
        if not fired:
            # Nothing matched: the run is parked about this thing anyway (the
            # gate is what parked it), so it is asked the author's first rule
            # rather than nothing at all.
            return candidates[0].question
        return max(fired, key=lambda r: r.narrowness).question

    def _stops(self, name: str, args: Mapping[str, Any]) -> bool:
        """Does anything this gate holds stop this call?

        [`for_call`] says *which* question; this says *whether there is a wait at
        all*, and the two are different questions. For a round only a host could
        answer the second: `run()` seeded its gate from the `needs_approval=`
        argument, so `examples/refund-desk/policies/approvals.yaml` — whose first
        line reads "This is enforcement, not a note in the instructions" — was,
        as shipped, a note in the instructions. A 300 USD refund ran and the run
        reported `final`. D14 rules out "a host writes code for that" for every
        capability in the core.

        Only rules the gate holds, and only ones PACT can decide from the call
        itself (see [`Rule.decidable`]). A rule that names one ACTION of a tool
        is decided by the action the call carries: a call saying `action: reply`
        waits, and the read-only `read-ticket` lookup the author wrote no rule
        about does not. A call that says which action it is NOT is neither gated
        nor silently ignored — see [`undecided_on`].

        Answers for whichever rules the gate is holding, which is what lets
        [`waits_for`] ask it once per reason over [`only_for`] rather than
        growing a second copy of the same predicate per reason. There used to be
        a `must_ask` above this that pinned it to `needs-approval` and returned a
        bare bool; a caller told "yes, stop" had to invent WHY, and inventing
        `needs-approval` is how a connection-consent park came to be keyed and
        rendered as a refund approval (§7.14 gap (1) item 2). It went the moment
        its last caller could act on a reason.
        """
        if any(
            r.gates and r.decidable(args) and r.stops_on(args)
            for r in self.rules.get(name) or ()
        ):
            return True
        return self._whatever_action_this_is(name, args)

    def _whatever_action_this_is(self, name: str, args: Mapping[str, Any]) -> bool:
        """A call that names no action, where every action it could be is ruled on.

        This is the case where the author HAS answered the question a silent call
        leaves open. `zendesk/reply` alone cannot decide a bare `zendesk` call,
        because that call might be the read-only lookup. Add a rule about
        `zendesk/read-ticket` and there is no longer a call to that tool the
        author wrote no rule about, so whichever action this one turns out to be
        it is stopped — and stopping it is what they wrote, not a guess.

        Asked action by action rather than tool-wide on purpose, so a threshold
        keeps governing: `payments` covered by a rule on `look-up-order` and one
        on `issue-refund` above 200 USD still lets a 40 USD call with no action
        through, because the `issue-refund` rule does not stop that call either.
        It is also the only spelling `pact check` accepts — a bare `tool:
        payments` is refused there as `loader/rule-names-no-action`.
        """
        if _action_of(args):
            return False
        declared = tuple(self.actions_of.get(name) or ())
        gating = [r for r in self.rules.get(name) or () if r.gates]
        if not declared or not gating:
            return False
        return all(
            any(r.stops_on(args, as_action=action) for r in gating)
            for action in declared
        )

    def undecided_on(self, name: str, args: Mapping[str, Any]) -> tuple[str, ...]:
        """What this gate could not decide about ONE call, ready to be said.

        The other half of [`_stops`]. A rule naming one action of a tool, met
        by a call that does not say which action it is, is neither gated nor
        dropped: the sentence names the file, the line, what could not be
        decided and a line to type, and the run carries it on
        `RunResult.unenforced` beside every other authored line this runtime
        could not apply.

        Nothing is said when [`_whatever_action_this_is`] settled the call, since
        the rule was applied.

        Over the approval rules alone, for the reason [`waits_for`] asks per
        reason: a
        connection consent stops every call to the tool it guards, so counting it
        here would report that every action of `payments` is now ruled on and
        take the sentence about the threshold rule off the run. The consent is a
        different wait, not an answer to this one.
        """
        approvals = self.only_for(NEEDS_APPROVAL)
        if approvals._whatever_action_this_is(name, args):
            return ()
        return tuple(
            dict.fromkeys(
                r.undecided_says
                for r in approvals.rules.get(name) or ()
                if r.gates and r.undecided_says and not r.decidable(args)
            )
        )

    def only_for(self, reason: str) -> "Gate":
        """The same gate, holding only the rules written for ONE kind of wait.

        A rule that names no reason answers any of them (see [`for_call`]), but
        the only rules that name none AND stop a call are the approval policy's,
        so for gating "no reason" means `needs-approval`.

        It exists so the predicate that decides whether to stop a call is written
        once and asked once per reason, rather than once per reason and drifting.
        """
        return replace(
            self,
            rules={
                k: tuple(r for r in v if (r.for_reason or NEEDS_APPROVAL) == reason)
                for k, v in self.rules.items()
            },
        )

    def waits_for(
        self, name: str, args: Mapping[str, Any], seeded: str = ""
    ) -> tuple[Wait, ...]:
        """Every reason this call must stop, in the order a person is asked them.

        The predicate under it says *whether*; this says *why*, and the
        difference is the whole of §7.14 gap (1) item 1. One name can carry rules
        for two reasons —
        `payments` has a threshold in `policies/approvals.yaml` and a connection
        consent in `resources/payments-server.yaml` — and a caller told only "yes,
        stop" has to invent which one, which is how a consent park came to be
        keyed and rendered as a refund approval.

        One entry per REASON, not per rule. Two approval rules over one call are
        one wait — which of their questions is put is [`for_call`]'s decision, and
        a person who has approved the refund has approved it once.

        `seeded` is the reason a HOST gave for this name (`run(gates=)` and
        `needs_approval=`). It is kept whatever the author's files say — a host
        with its own reason to stop a call is not overruled by a document — and
        it takes its place in the same order as the rest, under the call's own
        name because a host names tools rather than connections.

        Empty is the answer for every call nothing stops, and it is also what
        [`asking_only`] leaves: turning the gate off turns the consent off with
        it, which is the property the eval runner needs and could not have while
        the wait lived in a map beside the gate.
        """
        found: dict[str, Wait] = {}
        if seeded:
            found[seeded] = Wait(seeded)
        for rule in self.rules.get(name) or ():
            reason = rule.for_reason or NEEDS_APPROVAL
            if not rule.gates or reason in found:
                continue
            if self.only_for(reason)._stops(name, args):
                found[reason] = Wait(reason, rule.asked_as)
        return tuple(found[r] for r in sorted(found, key=_asked_in_order))

    def asking_only(self) -> "Gate":
        """The same questions, none of them stopping a call.

        Exactly one caller needs this and it has to say so out loud: the eval
        runner. A run that parks cannot be scored, so an eval that inherited the
        gate would score every governed case as a failure to answer — but a
        governance setting that is silently off in the runner producing the
        numbers is the defect this whole area exists to prevent, so it is a named
        method called from one place rather than an argument nobody passes.

        It clears `gates` on EVERY rule, so a connection consent goes off with the
        approvals. That is why the consent had to be a rule here rather than a
        fourth seeding of the harness's `gated` map: a wait seeded there is one
        this method cannot reach, so every scored case that touches `payments`
        would come back "did not answer" and the model under test would be blamed
        for a connection nobody had granted (§7.14 gap (1), measured).
        """
        return Gate(
            {k: tuple(replace(r, gates=False) for r in v) for k, v in self.rules.items()},
            self.unenforced,
            self.actions_of,
        )


@dataclass(frozen=True)
class Rule:
    """One `ask-a-person` line: when it applies, and what is asked."""

    question: Question
    when: tuple[Mapping[str, Any], ...] = ()
    #: True when this rule is what MAKES a call wait, rather than only what is
    #: asked once something else has stopped it. Only `policy.ask-a-person` sets
    #: it: the rules read off `limits.asks`, a context policy and a `teamwork`
    #: block supply wording for a wait the run has already entered for another
    #: reason, and turning those into gates would park a run on the mere
    #: existence of a question.
    gates: bool = False
    #: The reason to wait this rule's question answers; "" means any of them.
    #: Only one kind of rule needs it today — a connection nobody has allowed —
    #: and it needs it because `payments` is the same name in two of the
    #: author's files: a threshold in `policies/approvals.yaml` and an
    #: `asks-to-connect:` in `resources/payments-server.yaml`. Without this the gate
    #: chose between them by declaration order, which is not a choice anybody
    #: made.
    for_reason: str = ""
    #: The name a person answers this rule's wait under, when the wait is not
    #: about the thing the rule is attached to. Empty means it is.
    #:
    #: Exactly one rule needs it, and it needs it because two waits on one call
    #: would otherwise share an answer key. `questions/may-we-connect.yaml` and
    #: `questions/is-this-ok.yaml` both ask for `approved` and `because`, and a
    #: wait is named after what it is about, so both would be answered
    #: `payments: yes` — one person's consent to the connection would release a
    #: 300 USD refund they were never shown. Consent is granted for the
    #: CONNECTION (the question's own file says so: *"This is asked once, not
    #: once per customer"*) and approval for the CALL, so the consent wait is
    #: named for the connection — `payments-server`, the file the author wrote
    #: `asks-to-connect:` in.
    asked_as: str = ""
    #: What to say when this rule meets a call it cannot be decided against.
    #: Built where the file and the line are known — at load, in
    #: [`questions_for`] — and said only if such a call actually happens, which
    #: is why it is carried rather than reported there and then.
    undecided_says: str = ""
    #: Which arguments each action this rule names will let a rule look at —
    #: `<tool>/<action>` to that action's own `inspects:`, read off the tool
    #: document at load by [`_inspects_of`].
    #:
    #: `inspects:` was a field with a help line, a check, and no reader. Its help
    #: says it names *"the arguments an approval rule is allowed to look at"*, and
    #: measured before this: with `inspects: [order-number]` and with
    #: `inspects: [amount]`, the very same 300 USD refund produced the identical
    #: `Question` — the word "allowed" governed nothing, in either language. This
    #: is the field arriving where it is enforced; see
    #: [`_reads_something_it_may_not`].
    #:
    #: Empty means "nothing declared", not "nothing permitted". A tool file with
    #: no `inspects:` line is most tool files, and a rule over one is exactly as
    #: free as it was — the check follows the author's line, and where there is no
    #: line there is nothing to enforce.
    may_read: Mapping[str, frozenset[str]] = field(default_factory=dict)

    def decidable(self, args: Mapping[str, Any]) -> bool:
        """Can PACT tell, from THIS call, whether this rule applies?

        It used to be a property, and it answered for the rule rather than for
        the call because it believed *"every shipped transport calls a tool by
        its name and carries no action"*. That stopped being true when
        `ir._takes` began declaring `action:` on every multi-action tool: the
        model is shown `one of read-ticket, reply`, picks one, and the call
        carries it — which is already how `evals._calls` builds
        `<tool>/<action>` for `must-call-before:`. So a rule naming one action of
        a tool is decidable whenever the call says which action it is, and
        `zendesk/reply` — a rule whose `because:` reads *"nothing goes to a
        customer without a person seeing it first"* — is enforced rather than
        reported.

        Three shapes say yes. A threshold over an argument the model chose is
        read straight off the call (`more-than: 200 USD` on `amount`), a `when:`
        that names the whole tool applies to every call to it, and a `when:` that
        names one action is settled by the action the call carries.

        What remains undecidable is narrow: a call to a multi-action tool that
        carries NO `action` argument at all, against a rule that names one
        action and tests nothing else. PACT would have to stop every such call
        (including the read-only lookup the author wrote no rule about) or none
        of them. Both are answers the author did not give, so neither is taken
        silently — see [`Gate.undecided_on`], and [`Gate._stops`] for the one
        case where the author HAS given the answer.
        """
        if not self.when:
            return True
        if any("more-than" in atom for atom in self.when):
            return True
        return _action_of(args) != "" or not any(_action_named(a) for a in self.when)

    @property
    def narrowness(self) -> float:
        """How high this rule's threshold is; 0 for a rule with none.

        Used only to choose between rules that both apply, so it does not need
        to be a total order over conditions — just over the one kind of
        condition that can overlap.
        """
        return max((_amount(a.get("more-than")) or 0.0 for a in self.when), default=0.0)

    def fires_on(self, args: Mapping[str, Any]) -> bool:
        return all(_atom_holds(a, args, self.may_read) for a in self.when)

    def stops_on(self, args: Mapping[str, Any], as_action: str = "") -> bool:
        """Does this rule STOP the call — as opposed to merely being about it?

        Read strictly, which is the one place this file reads a condition
        strictly, and the difference is worth stating. [`fires_on`] chooses
        between questions for a run that is *already* parked, so an atom it
        cannot evaluate counts as holding: widening there costs nothing but a
        better-worded question. This decides whether to park at all, and
        widening here stops calls the author wrote no rule about — a
        `more-than: 200 USD` rule on `amount` would park `payments` calls that
        carry no amount, which are the read-only lookups.

        `as_action` reads the call as if it had said which action it is. Exactly
        one caller passes it — [`Gate._whatever_action_this_is`], asking "would
        the author's rules stop this call if it turned out to be `read-ticket`?"
        — and it is a named argument rather than a second method because it
        changes one clause of one atom, not what strict means.
        """
        return all(_atom_stops(a, args, as_action, self.may_read) for a in self.when)


#: The argument that says which of a tool's actions a call is. `ir._takes`
#: declares it on every tool with an `actions:` block (`action: one of
#: read-ticket, reply`), so the model is shown it and the call carries it;
#: `evals._calls` reads the same key to build `<tool>/<action>`. One spelling,
#: read in both places, rather than one mechanism believing the call carries an
#: action and the other believing it cannot.
ACTION = "action"


def _action_named(atom: Mapping[str, Any]) -> str:
    """The action half of an atom's `tool:` cell — `reply` in `zendesk/reply`.

    Empty when the rule names the whole tool, which is a rule about every action
    of it. The head half is read by [`_things_named`], which is what attaches the
    rule to a tool; this is the half that says WHICH call to that tool it is
    about, and for a round nothing read it at all.
    """
    return str(atom.get("tool") or atom.get("name") or "").partition("/")[2].strip()


def _action_of(args: Mapping[str, Any]) -> str:
    """Which action a call says it is, or "" when it does not say."""
    value = args.get(ACTION)
    return value.strip() if isinstance(value, str) else ""


def _reads_something_it_may_not(
    atom: Mapping[str, Any], may_read: Mapping[str, frozenset[str]]
) -> bool:
    """Is this condition looking at an argument its action does not offer?

    `action.inspects:` — *"the arguments an approval rule is allowed to look
    at"* — held against the `arg:` of the rule that is looking. The whole of the
    word "allowed", and until this function nothing in either language read the
    line: `inspects: [amount]` and `inspects: [order-number]` produced byte-identical
    gate output on the same 300 USD refund.

    False when the action declares no `inspects:` at all, which is most actions.
    The permission is the author's line; where there is no line there is nothing
    to enforce, and inventing one would refuse rules that are correct today.

    The architecture (§Y9's argument roles) is what this makes true: an
    `inspected` argument is *"the only role a `policy.ask-a-person` predicate may
    read"*. The other roles are the ones the surrounding system binds — a
    customer id, an account — and a gate that compares against those is a gate
    that reads a value the model never chose.
    """
    arg = str(atom.get("arg") or "").strip()
    if not arg:
        return False  # a rule about the whole action reads nothing
    offered = may_read.get(str(atom.get("tool") or atom.get("name") or "").strip())
    return bool(offered) and arg not in offered


def _equality_holds(atom: Mapping[str, Any], args: Mapping[str, Any]) -> "bool | None":
    """`is:` / `is-one-of:` against the argument, or `None` when neither is written.

    A3. `more-than:` compares a MAGNITUDE, and a customer tier, a country or a
    reason code has none — so an approval gate could ask about money and about
    nothing else. `when-this.arg` even carried `needs-also: [more-than]`, which
    refused `{tool: t/go, arg: reason, is: fraud}` outright: a rule the author
    had written correctly.

    Compared as text, folded, because the value comes off a model's tool call and
    `Enterprise` and `enterprise` are the same tier. The same bargain
    `Shape.read` already strikes for the answers a person types.

    `None` means this atom says nothing about equality, so the caller falls
    through to whatever else it carries.
    """
    if "is" in atom:
        wanted = [atom.get("is")]
    elif "is-one-of" in atom:
        one_of = atom.get("is-one-of")
        wanted = list(one_of) if isinstance(one_of, (list, tuple)) else [one_of]
    else:
        return None
    named = str(atom.get("arg") or "")
    if named not in args:
        # The rule is about a value this call does not carry, so it is not the
        # call the rule is about — the same reading `more-than:` takes one
        # function down when its argument is absent.
        return False
    got = str(args.get(named)).strip().lower()
    return any(str(w).strip().lower() == got for w in wanted if w is not None)


def _atom_holds(
    atom: Mapping[str, Any],
    args: Mapping[str, Any],
    may_read: Mapping[str, frozenset[str]] = {},
) -> bool:
    """Does one condition hold for these arguments?

    The vocabulary is closed and small on purpose: `more-than` over an argument
    the action declared under `inspects:`, and which action of the tool the rule
    is about. Anything else is unevaluable here and counts as holding — see
    [`Gate.for_call`].

    The action half only ever narrows, and only on a KNOWN mismatch: a call
    saying `action: read-ticket` is not the call a `zendesk/reply` rule is about,
    so that rule's wording is not put in front of a person about it. A call that
    says nothing still holds, because this side chooses wording for a run already
    parked and guessing wide there costs nothing.

    A condition reading an argument `inspects:` does not offer is unevaluable in
    the same way and holds for the same reason: this side is choosing the wording
    for a run something else already stopped, and the run that stopped it is
    [`_atom_stops`] one function down, where the permission bites.
    """
    called = _action_of(args)
    action = _action_named(atom)
    if action and called and called != action:
        return False
    if _reads_something_it_may_not(atom, may_read):
        return True
    equal = _equality_holds(atom, args)
    if equal is not None:
        return equal
    if "more-than" not in atom:
        return True
    threshold = _amount(atom.get("more-than"))
    value = _amount(args.get(str(atom.get("arg") or "")))
    if threshold is None or value is None:
        return True
    return value > threshold


def _atom_stops(
    atom: Mapping[str, Any],
    args: Mapping[str, Any],
    as_action: str = "",
    may_read: Mapping[str, frozenset[str]] = {},
) -> bool:
    """Does one condition stop this call? See [`Rule.stops_on`].

    A threshold PACT cannot read still stops — a malformed `more-than:` is a
    mistake, and refusing to ask because of one would turn a typo into a
    disabled gate. A threshold whose ARGUMENT is absent does not: the rule is
    about a figure, and a call carrying no figure is not the call it is about.

    A threshold PACT may not read stops for exactly the first of those reasons.
    `inspects:` names the arguments a rule is allowed to look at, so a rule
    looking outside it has no figure it can legitimately compare — and the choice
    is between stopping the call and letting the gate go quiet. It stops. That is
    the direction the malformed-threshold rule above already settled, and it is
    the direction `pact check` now refuses the tree in, so the author hears about
    it before a customer is waiting rather than by watching every call park.

    The action half reads the same way round, and it is why `zendesk/reply` now
    stops a reply. A call saying `action: reply` is the call the rule is about
    and is stopped; one saying `action: read-ticket` is not and goes through; one
    that says NOTHING is not identifiably either, so this clause stays out of the
    way and [`Rule.decidable`] withholds the gate — the run reports the rule
    through [`Gate.undecided_on`] instead of gating on a guess. Silence must fall
    through rather than refuse: `payments/issue-refund` carries a threshold as
    well, and refusing here would have taken the 300 USD gate off every call the
    model wrote without an `action:`.
    """
    called = _action_of(args) or as_action
    action = _action_named(atom)
    if action and called and called != action:
        return False
    if _reads_something_it_may_not(atom, may_read):
        return True
    equal = _equality_holds(atom, args)
    if equal is not None:
        return equal
    if "more-than" not in atom:
        return True
    threshold = _amount(atom.get("more-than"))
    if threshold is None:
        return True
    value = _amount(args.get(str(atom.get("arg") or "")))
    return value is not None and value > threshold


#: Every way a figure is written, INCLUDING the ones with nothing before the
#: decimal point.
#:
#: The first version was `-?\d+(?:\.\d+)?`, which requires a digit in front of
#: the dot — and because [`_GROUPING`] strips the space first, `'.50 USD'`
#: became `'.50USD'` and the first thing that matched was `50`. So a gate an
#: author wrote at fifty cents was read at fifty dollars and did not fire on a
#: 40 USD refund. MEASURED, before this:
#:
#:     '$.50'    -> 50.0        '$0.50'    -> 0.5
#:     '.50 USD' -> 50.0        '0.50 USD' -> 0.5
#:     '-.5 USD' -> 5.0         '-5 USD'   -> -5.0
#:     '1e5 USD' -> 1.0
#:
#: with `pact check` and `pact show` passing every one of them cleanly. Three
#: separate wrong figures out of one missing alternative: off by 100x, sign
#: flipped (the `-?` cannot start at a `-` it is not allowed to reach), and an
#: exponent dropped. The sign one is the sharpest, because
#: `a_gate_that_stops_for_a_person_on_any_spend_at_all_is_left_alone` DECIDES
#: that a negative threshold is legal — "a gate is not a ceiling" — so
#: `more-than: -.5 USD` is a gate deliberately written to stop on every refund
#: there is, and it stopped none under five dollars.
#:
#: This is the half `crates/pact-loader/src/money.rs` cannot reach: those are
#: all figures, so no "that is not a figure" refusal could ever have caught
#: them. The two grammars are held together by
#: `tests/test_a_spend_cap_that_can_never_be_reached.py`, which asserts that for
#: every threshold the checker lets through, the figure read back here is the
#: figure that was written.
_NUMBER = re.compile(r"-?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?")

#: Every way a person or a model writes a thousands separator. Stripped before
#: the number is read, because the pattern above stops at one — so
#: `'1,500.00 USD'` read as **1.0** and slipped under a 200 USD approval
#: threshold. Measured end to end on the worked example: the payments call ran,
#: the tool was invoked, and `RunResult.halted == 'final'` — money moved with
#: nobody asked, on an argument the MODEL chooses. Both sides of every comparison
#: come through here, so one strip covers rule thresholds and call arguments.
_GROUPING = str.maketrans("", "", ",_ ")


def _amount(value: Any) -> float | None:
    """The number inside `200 USD`, `$25`, `40.00 USD`, `1,500.00 USD` or `12`.

    One reader for both sides of the comparison, so a rule written `200 USD` and
    an argument the model wrote as `$210` are compared as numbers rather than as
    strings — which is how `"210.00 USD" > "200 USD"` would quietly be false.

    A number that is not a finite one is not a figure, and is read as no figure
    at all. THE TWO SPELLINGS USED TO LAND ON OPPOSITE SIDES OF THE GATE, which
    was the one genuinely fail-OPEN path in this whole area: `'NaN USD'` is text,
    finds no digits, returns `None`, and `_atom_stops` then stops the call — but
    a float `nan` arriving from a spec built in code went through the branch
    above and came back as `nan`, and `nan > anything` is `False`, so the gate
    silently never fired. Measured:

        _atom_stops({..., 'more-than': float('nan')}, {'amount': '999999 USD'})
        -> False
        _atom_stops({..., 'more-than': float('inf')}, {'amount': '999999 USD'})
        -> False

    A gate that lets a 999,999 USD refund past with nobody asked, and no report
    entry anywhere — FR-8.1.1 (T7): *"No lossy operation anywhere may proceed
    silently; each MUST emit a report entry and be fail-closed by default."* The
    guard is on the VALUE and not on any one reader, which is where B3's record
    says it belongs (`docs/70-PRODUCTION-GAP-REGISTER.md`, *"The guard is on the
    VALUE, not on a reader"*), and it costs one line: both spellings now return
    `None`, and `None` is the case `_atom_stops` already handles by stopping.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    m = _NUMBER.search(str(value).translate(_GROUPING))
    return float(m.group()) if m else None


def policies_over(
    doc: Mapping[str, Any], agent: Mapping[str, Any]
) -> list[tuple[str, Mapping[str, Any]]]:
    """Every approval policy that covers this agent, in name order.

    Two ways in, and the second is the one that was missing: the policy the agent
    NAMES, and any policy that says `applies-to: every-agent`. Approval bound
    per-agent and opt-in, which is the polarity `interceptor.applies-to` was
    added to fix one surface over — and here the consequence is money. Measured
    on the shipped example: `fraud-checker` uses `zendesk`, `zendesk` exposes
    `reply`, `policies/approvals.yaml` gates `zendesk/reply`, and `pact waits`
    listed seven waits of which every one said `"agent": "refund-desk"`.

    Name order, so two runs of two ports gate in the same sequence.
    """
    named = str(agent.get("policy") or "").strip()
    out: list[tuple[str, Mapping[str, Any]]] = []
    for key, policy in sorted((doc.get("policies") or {}).items()):
        if not isinstance(policy, Mapping):
            continue
        covers = str(policy.get("applies-to") or "the-agents-that-name-it").strip()
        if key == named or covers == "every-agent":
            out.append((key, policy))
    return out


@dataclass(frozen=True)
class Gated:
    """One action gated by `needs-a-person: yes`, expanded into what a rule says.

    The short line is a SHORTHAND, not a second mechanism: everything below is a
    field of the ordinary approval `Rule` the author would otherwise have typed
    out, and it is put through the same [`Gate`] by the same [`questions_for`].
    Nothing downstream of here can tell the two apart, which is the property
    that makes the shorthand safe to offer — a gate written in one line stops a
    call, parks the run, waits, times out and refuses in exactly the way a gate
    written in thirteen lines does.
    """

    tool: str
    action: str
    #: Why a person is being asked, in the ACTION's own words. The shipped
    #: question's wording is fixed and cannot name an action, so this is where
    #: the action gets named — and it is what the approver reads under `why:`.
    #: Without it the screen says "Somebody has to say yes before this runs" and
    #: nothing else, which is a placeholder wearing a question's clothes.
    because: str
    #: The values to put in front of the person: every argument the action
    #: declares under `takes:`. The long form makes the author list these; the
    #: short form reads them off the action, which already says what it is given.
    shows: tuple[str, ...]

    @property
    def named(self) -> str:
        """`payments/issue-refund` — the spelling a written rule's `when:` uses."""
        return f"{self.tool}/{self.action}"


def gated_actions(doc: Mapping[str, Any], agent_key: str) -> list[Gated]:
    """Every action THIS agent can reach whose own file says it needs a person.

    Bound through `uses:` rather than through `policies:` and `applies-to:`. An
    agent that cannot reach `payments` never waits for a person about it, and
    that needs no line from the author to say so — which is one of the four
    concepts the long form charges for.

    An action a written rule already decides is left out. That is the whole of
    "the expert path wins": a rule says who is asked, how long they have and
    what shape the answer takes, and a second wait quietly appearing beside it
    would put two screens in front of one person for one call.
    `pact-loader::approvals` reports the overlap where the author is, so the
    line they wrote is never merely ignored.
    """
    agent = (doc.get("agents") or {}).get(agent_key) or {}
    tools = doc.get("tools") or {}
    ruled = {
        str(atom.get("tool") or atom.get("name") or "").strip()
        for _, policy in policies_over(doc, agent)
        for raw in policy.get("ask-a-person") or []
        if isinstance(raw, Mapping)
        for atom in raw.get("when") or []
        if isinstance(atom, Mapping)
    }
    out: list[Gated] = []
    for used in sorted(_as_list(agent.get("uses"))):
        settings = tools.get(used)
        if not isinstance(settings, MappingABC):
            continue  # a skill or a teammate — it has no actions
        actions = settings.get("actions")
        if not isinstance(actions, MappingABC):
            continue
        for action, written in sorted(actions.items()):
            if not isinstance(written, MappingABC) or not _needs_a_person(written):
                continue
            if f"{used}/{action}" in ruled or used in ruled:
                continue
            takes = written.get("takes")
            out.append(Gated(
                tool=str(used),
                action=str(action),
                because=_because_of(str(used), str(action), written),
                shows=tuple(str(k) for k in takes) if isinstance(takes, MappingABC) else (),
            ))
    return out


def _needs_a_person(action: Mapping[str, Any]) -> bool:
    """Does this action's own file say a person has to say yes?

    Every spelling the schema's `yes-no` accepts, because a tick this did not
    recognise would be an authored gate that loads clean and stops nothing —
    the same argument `pact-loader::money::moves_money` makes for
    `spends-money:`, on the same kind of line.

    This was the only one of six readers in the port whose word-list was right,
    and it held it privately: `facts`, `egress`, `resolve`, `ir` and `scoring`
    each kept their own and three of those took neither `y` nor `enabled`. It now
    reads `yes_no.said_yes` like the rest — being correct in a copy is how the
    other five came to look correct too.

    NOT `_YES` above, which is a wider list on purpose: that one is what a PERSON
    types at an approval prompt (`approve`, `granted`, `ok`), and this is what an
    AUTHOR writes on a line `pact check` reads. `needs-a-person: approve` is
    refused at the door, so honouring it here would be this port inventing a
    spelling the format does not have.
    """
    return said_yes(action.get("needs-a-person"))


def _because_of(tool: str, action: str, written: Mapping[str, Any]) -> str:
    """`why:` on the approver's screen, in the action's own words."""
    described = str(written.get("description") or "").strip().rstrip(".")
    if not described:
        return f"`{action}` on `{tool}` needs a person before it runs."
    return (
        f"`{action}` on `{tool}` needs a person before it runs — "
        f"it does this: {described}."
    )


def questions_for(
    doc: Mapping[str, Any], agent_key: str, source: "Path | None" = None
) -> Gate:
    """Which question to put about which thing, for one agent.

    Read from what the author already wrote — `policy.ask-a-person` says which
    question guards which tool, `limits.asks` says which one to put when a
    ceiling is reached, and a `does: ask-someone` stage of the loop says which
    one that stage asks. Nothing here is registered in code, which is D14's bar:
    a support lead adds `questions/how-much-to-refund.yaml`, names it in a rule,
    and the run asks it.

    A rule naming a question nobody wrote is refused here rather than at the
    moment money moves, which is the only time the mistake would otherwise show.

    `source` is the workspace root and is optional, exactly as it is for a
    context policy and an interceptor: given one, a rule this vocabulary cannot
    decide names the real file and the real line rather than a path built from
    the policy's name.
    """
    agent = (doc.get("agents") or {}).get(agent_key) or {}
    out: dict[str, list[Rule]] = {}
    problems: list[str] = []

    def named(name: str, where: str) -> Question | None:
        try:
            return Question.from_document(doc, name)
        except Rejected as e:
            problems.append(f"{where} names a question that is not there: {e.problems[0]}")
            return None

    def add(about: str, rule: Rule) -> None:
        out.setdefault(about, []).append(rule)

    for policy_name, policy in policies_over(doc, agent):
        for raw in policy.get("ask-a-person") or []:
          if not isinstance(raw, dict):
              continue
          q = named(str(raw.get("question") or ""), f"the {agent_key} approval rules")
          if q is None:
              continue
          because = str(raw.get("because") or "").strip()
          atoms = tuple(a for a in (raw.get("when") or []) if isinstance(a, dict))
          # `gates=True` is the whole difference between this block and the three
          # below it: an approval rule is what STOPS a call, the others only say
          # what to ask once something else already stopped the run.
          #
          # The sentence for a call this rule cannot be decided against is built
          # HERE, where the policy's file and line are in hand, and carried on the
          # rule. Saying it here as well would report `zendesk/reply` as unapplied
          # on every run — including the ones where the call said `action: reply`
          # and a person was asked, which is the untruth this round removes.
          rule = Rule(
              replace(q, because=because), atoms, gates=True,
              undecided_says=(
                  _cannot_decide(raw, policy_name, source, doc)
                  if any(_action_named(a) for a in atoms)
                  else ""
              ),
              # `inspects:` arriving where it is enforced. This is the ONLY line
              # that carries the author's permission out of their tool file and
              # into the predicate that reads an argument; delete it and
              # `test_a_gate_reads_only_what_it_may.py` fails, because the field
              # goes back to being a help string with a check behind it and no
              # reader.
              may_read=_inspects_of(doc),
          )
          for about in dict.fromkeys(_things_named(raw.get("when"))):
              add(about, rule)

    # `needs-a-person: yes` on an action — the same rule, written in one line
    # (F17). It is built HERE, beside the long form and out of the same `Rule`,
    # rather than anywhere later: a shorthand assembled by a second path is a
    # shorthand that will one day stop a call the long form would have stopped,
    # or stop one it would not. `gates=True` for the same reason the block above
    # has it — this is what MAKES a call wait, not wording for a wait something
    # else began.
    for gate in gated_actions(doc, agent_key):
        q = named(SHIPPED_QUESTION, f"the {agent_key} tools")
        if q is None:
            continue
        add(gate.tool, Rule(
            replace(q, because=gate.because, shows=gate.shows),
            ({"tool": gate.named},),
            gates=True,
            undecided_says=_cannot_decide_short(gate, source, doc),
        ))

    limits = agent.get("limits") or {}
    if str(limits.get("when-it-runs-out") or "") == "ask-a-person" and limits.get("asks"):
        # Eve's session-limit continuation, asked as what it is. `decision` is
        # the name the loop waits on when a ceiling is reached.
        q = named(str(limits["asks"]), f"the {agent_key} limits")
        if q is not None:
            add("decision", Rule(q))

    tidying = (doc.get("context-policies") or {}).get(
        str(agent.get("context-policy") or "")
    ) or {}
    if str(tidying.get("if-it-still-does-not-fit") or "") == "ask-a-person" and tidying.get(
        "asks"
    ):
        # A conversation nobody can shrink enough. Eve reaches this point too and
        # has nothing to ask with — it sends the oversized history and says
        # nothing. Waited on under `conversation` rather than `decision`, because
        # `decision` is already what a ceiling waits on and one agent can hit
        # both in the same run.
        q = named(str(tidying["asks"]), f"the {agent_key} context policy")
        if q is not None:
            add("conversation", Rule(q))

    teamwork = agent.get("teamwork") or {}
    if str(teamwork.get("if-someone-fails") or "") == "ask-a-person" and teamwork.get("asks"):
        # A teammate that could not answer is waited on under its own name, the
        # same way a tool call is, so the question attaches per member: "carry
        # on without the fraud check?" is a different decision per specialist.
        q = named(str(teamwork["asks"]), f"the {agent_key} teamwork")
        if q is not None:
            for member in agent.get("team") or {}:
                if member not in out:
                    add(member, Rule(q))

    # A stage of the loop that stops to ask (G1 meeting G7). Waited on under the
    # stage's own name, so a person answering reads the wording the author wrote
    # rather than only the stage's `says:` line.
    for stage_name, asks in asking_stages(doc, agent):
        if not asks:
            continue  # refused where the waiting rules are read — see `suspension`
        q = named(asks, f"the {agent_key} loop, stage {stage_name!r}")
        if q is not None and stage_name not in out:
            add(stage_name, Rule(q))

    # A connection nobody has allowed yet. Registered LAST on purpose: `payments`
    # already has the approval rules above it, `Gate.__getitem__` returns the
    # first rule's question, and a caller with no reason to give must keep
    # getting the approval question it has always got. What `for_reason` buys is
    # the other direction — a run parked because the connection is not allowed
    # now reads `may-we-connect` instead of `is-this-ok`, which was measured on
    # the worked example and is the defect §11.6a records.
    #
    # `gates=True`, so this is a STOP and not only wording. It was `False` for a
    # round while a decision was outstanding, and for that round
    # `asks-to-connect:` stopped nothing: a run of the worked example reached
    # `payments` with `{'order-number': 'A-1182', 'amount': '40.00 USD'}` and
    # reported `final`, so money moved over a connection nobody had consented to
    # while `pact check` passed the file that says otherwise. The decision the
    # gap was waiting on is `ASKED_IN_ORDER` (consent before approval) and the
    # answer key is `asked_as` (the connection, not the call); with both written
    # down the wait belongs here, in the gate, where `asking_only()` can turn it
    # off with everything else.
    #
    # NO `when:`, so it stops every call to the tool including the read-only
    # `look-up-order` — which is the line's own meaning. `asks-to-connect`'s help
    # says *"when this connection has not been allowed yet"*, and a lookup goes
    # over the connection exactly as a refund does.
    #
    # Imported inside the function because `suspension` imports this module and
    # not the other way round. `asking_stages` below does the same for `loops`
    # and for the same reason. `NEEDS_PERMISSION` is this module's own — see the
    # constant.
    from .suspension import connections_needing_permission

    tools = doc.get("tools") or {}
    for tool, asks in connections_needing_permission(doc, agent_key).items():
        q = named(asks, f"the {agent_key} connection to {tool!r}")
        if q is not None:
            # The SERVER, not the tool. `connections_needing_permission` walked
            # `uses:` -> `tools.<t>.connect` -> `resources.<server>` to find this
            # rule at all, so the name at the end of that walk is the name the
            # consent is about, and it is what a person answers under.
            server = str(((tools.get(tool) or {}).get("connect") or "")).strip()
            add(tool, Rule(q, gates=True, for_reason=NEEDS_PERMISSION,
                           asked_as=server or f"{tool}-connection"))

    if problems:
        raise Rejected(problems)
    # Nothing is left for the load-time half to say. The one thing it used to
    # carry — a rule naming one action — is a fact about a CALL now, so it goes
    # out per call through `Gate.undecided_on`; the field stays because a host
    # that assembles a gate itself may still have something to report before a
    # run starts, and because the run reads both through one channel.
    return Gate({k: tuple(v) for k, v in out.items()}, (), _actions_of(doc))


def _actions_of(doc: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    """What each tool's `actions:` block declares, by tool name.

    The same block `ir._takes` turns into the `action:` argument the model is
    shown, read here so the gate knows what a silent call could have been.
    """
    out: dict[str, tuple[str, ...]] = {}
    for tool, settings in (doc.get("tools") or {}).items():
        actions = (settings or {}).get("actions") if isinstance(settings, Mapping) else None
        if isinstance(actions, Mapping) and actions:
            out[str(tool)] = tuple(sorted(str(a) for a in actions))
    return out


def _inspects_of(doc: Mapping[str, Any]) -> dict[str, frozenset[str]]:
    """Every action's `inspects:` line, keyed the way a rule's `when:` spells it.

    `payments/issue-refund` -> `{'amount'}`, straight off `tools/payments.yaml`.
    The key is `<tool>/<action>` because that is the string an approval rule
    writes, so [`_reads_something_it_may_not`] can look a permission up with the
    rule's own words and nothing has to be re-derived at call time.

    Actions with no `inspects:` line are absent rather than present-and-empty,
    and the difference is the whole safety of this: absent means "the author said
    nothing", which is most tool files and must go on behaving exactly as it did.
    An empty frozenset would mean "no argument may be looked at", which would
    turn every gate in every workspace that has not written the line into a gate
    that stops everything.
    """
    out: dict[str, frozenset[str]] = {}
    for tool, settings in (doc.get("tools") or {}).items():
        actions = (settings or {}).get("actions") if isinstance(settings, Mapping) else None
        if not isinstance(actions, Mapping):
            continue
        for action, written in actions.items():
            if not isinstance(written, Mapping):
                continue
            offered = written.get("inspects")
            if isinstance(offered, str):
                offered = [offered]
            if not isinstance(offered, list):
                continue
            names = frozenset(str(a).strip() for a in offered if str(a).strip())
            if names:
                out[f"{tool}/{action}"] = names
    return out


def _cannot_decide(
    raw: Mapping[str, Any], policy_name: str, source: "Path | None",
    doc: Mapping[str, Any],
) -> str:
    """One sentence about a CALL this rule cannot be decided against.

    Four parts, the same four every diagnostic in this project carries: where,
    what, why, and something the author can type. It is a sentence rather than a
    `Problem` because it is not a mistake — the file is valid and `pact check`
    passes it. It is a rule that this runtime could not apply to one call, which
    is the fact `RunResult.unmetered` reports for a ceiling nobody can measure.

    It used to say the rule *"was not applied"* full stop, because the runtime
    believed a call never carried an action; it does now, so the sentence is
    about the calls that still do not. Its two old fixes are gone with the
    premise. *"Write `zendesk` instead of `zendesk/reply`"* would have gated the
    read-only lookup the author wrote no rule about — and `pact check` refuses
    that spelling outright as `loader/rule-names-no-action`, so it was a line
    that could not be typed. *"Move `reply` into a tool file of its own"* was
    surgery on a tool to fix a policy, and it does not even help: the new file
    would declare `reply` under its own `actions:`, so a call that named no
    action would be exactly as silent as before.
    """
    named = ""
    for atom in raw.get("when") or []:
        if isinstance(atom, Mapping):
            candidate = str(atom.get("tool") or atom.get("name") or "")
            if "/" in candidate:
                named = candidate
                break
    tool, _, action = named.partition("/")
    others = [a for a in _actions_of(doc).get(tool, ()) if a != action]
    file, line = locate(source, "policies", "policy", policy_name, named)
    # A rule for every action is the one spelling that both fixes this and passes
    # `pact check`; see `Gate._whatever_action_this_is`, which is what makes the
    # promise in the last clause true.
    write = ", ".join(f"`{tool}/{a}`" for a in others) or f"every other action of `{tool}`"
    contrast = (
        f"A call saying `action: {action}` is stopped for a person and one saying "
        f"`action: {others[0]}` is not, and this one said neither. "
        if others
        else ""
    )
    return (
        f"{file}:{line} — the rule about `{named}` was not applied to a `{tool}` call "
        f"that did not say which of its actions it was. {contrast}"
        f"fix: write a rule for {write} as well — once every action of a tool has a "
        f"rule, a call that names none of them is stopped too, because whichever one "
        f"it turns out to be you have written a rule about it."
    )


def _cannot_decide_short(
    gate: Gated, source: "Path | None", doc: Mapping[str, Any]
) -> str:
    """The same sentence, for a gate written in one line.

    The one-line form buys shorter typing and not a quieter runtime, so the call
    it cannot decide is reported exactly as the long form's is: a `payments` call
    that does not say which of its actions it is, against a line about one of
    them. What differs is the fix, and only because the line to type is shorter
    — `needs-a-person: yes` on the other actions rather than a rule apiece.
    """
    others = [a for a in _actions_of(doc).get(gate.tool, ()) if a != gate.action]
    file, line = locate(source, "tools", "tool", gate.tool, "needs-a-person")
    write = ", ".join(f"`{a}`" for a in others) or f"every other action of `{gate.tool}`"
    contrast = (
        f"A call saying `action: {gate.action}` is stopped for a person and one saying "
        f"`action: {others[0]}` is not, and this one said neither. "
        if others
        else ""
    )
    return (
        f"{file}:{line} — `needs-a-person: yes` on `{gate.named}` was not applied to a "
        f"`{gate.tool}` call that did not say which of its actions it was. {contrast}"
        f"fix: write `needs-a-person: yes` under {write} as well — once every action of "
        f"a tool needs a person, a call that names none of them is stopped too, because "
        f"whichever one it turns out to be you have said it needs a person."
    )


def asking_stages(doc: Mapping[str, Any], agent: Mapping[str, Any]) -> list[tuple[str, str]]:
    """`(stage, the question it names)` for every `does: ask-someone` stage.

    Stages that name nothing are included, with an empty second value: refusing
    them belongs to `suspension`, where the other four places that can stop and
    ask are refused in the same words. One enumeration for both callers —
    `suspension` may import this module and not the other way round, so this is
    the side it lives on.

    Read through `Loop.resolve` rather than off the raw mapping so a stage
    inherited through `based-on:` counts. A loop that does not resolve yields
    nothing: the same resolution runs a line later in `AgentSpec.from_document`
    and reports it once, under a heading about loops rather than about questions.
    """
    from .loops import Does, Loop, LoopError

    try:
        loop = Loop.resolve(doc, str(agent.get("loop", "")).strip())
    except LoopError:
        return []
    return [(p.name, p.asks.strip()) for p in loop.steps.values() if p.does is Does.ASK]


def _things_named(when: Any) -> list[str]:
    """The tools a rule's `when:` is about, so a question attaches to them.

    Only the tool name is taken. WHICH argument crossed which threshold is read
    later, by [`Gate.for_call`], from the arguments the model actually chose —
    the rule's own atoms travel with it rather than being discarded here.
    """
    out: list[str] = []
    for atom in when or []:
        if not isinstance(atom, dict):
            continue
        named = atom.get("tool") or atom.get("name") or ""
        head = str(named).split("/")[0].strip()
        if head:
            out.append(head)
    return out


@dataclass(frozen=True)
class Answer:
    """A validated answer. Everything the loop acts on is read from here."""

    question: str
    about: str
    values: Mapping[str, Any]
    answered_by: str = ""
    #: True when this stands in for an answer nobody gave. Never approving.
    from_silence: bool = False

    def _verdict(self) -> bool | None:
        """The yes-or-no this answer carries, or `None` when it carries none.

        The MEANING FOLLOWS THE SHAPE, not the spelling. Reading only a field
        literally called `approved` meant that a support lead writing
        `answer: {ok: yes or no}` built a gate that could not be refused: with no
        `approved` key the answer was cleared by having been given at all, so a
        person typing `ok: no` released the call. Measured — renaming that one
        word in `questions/may-we-connect.yaml`, the consent gate for the
        payments connection, printed "OK — loaded cleanly". A `yes or no` reaches
        here as a real `bool`, so the shape is readable without the schema.

        `approved` still wins when it is there, so a question carrying both a
        gate and an ordinary yes-or-no fact behaves exactly as before; when it is
        NOT there, any yes-or-no is the gate. `pact check` refuses that spelling
        where the author is, so the two never have to disagree in silence.
        """
        if APPROVED in self.values:
            return self.values[APPROVED] is True
        flags = [
            v for k, v in self.values.items()
            if isinstance(v, bool) and k not in (BECAUSE, INSTEAD)
        ]
        if not flags:
            return None
        return all(flags)

    @property
    def approved(self) -> bool:
        """A schema with no yes-or-no field at all is not a gate.

        Answering "how much should we refund?" at all IS the go-ahead; there is
        nothing further to say yes to, and inventing a second confirmation would
        be Eve's approve/deny reappearing under the answer.
        """
        verdict = self._verdict()
        return True if verdict is None else verdict

    @property
    def declined(self) -> bool:
        return self._verdict() is False

    @property
    def instead(self) -> str | None:
        """Text the person supplied in place of doing the action at all."""
        value = self.values.get(INSTEAD)
        return str(value) if isinstance(value, str) and value.strip() else None

    @property
    def because(self) -> str:
        return str(self.values.get(BECAUSE, "")).strip()

    def applied_to(self, args: Mapping[str, Any]) -> dict[str, Any]:
        """Replace the arguments the person set, and only those.

        An answer field that does not name an existing argument cannot invent
        one: a question is a way to correct a value the model chose, never a way
        to reach parameters the action never had.
        """
        out = dict(args)
        for key, value in self.values.items():
            if key not in (APPROVED, BECAUSE, INSTEAD) and key in out:
                out[key] = value
        return out


@dataclass(frozen=True)
class Unanswered:
    """What the deadline produced. Exactly one of the last three is set."""

    question: Question
    then: str
    ask_instead: "Question | None" = None
    answer: "Answer | None" = None
    stop_because: str | None = None


# ──────────────────────────────────────────────────────────────────── render


#: Everything `str.splitlines()` treats as a line break, plus the C1 range.
#: It was `[\x00-\x1f\x7f]` — C0 and DEL only — so U+2028 LINE SEPARATOR,
#: U+2029 PARAGRAPH SEPARATOR and U+0085 NEL went through untouched. Measured:
#: an `order-number` containing one U+2028 rendered as EIGHT lines from six
#: real newlines, forging a `why:` and a second `amount:` above the real one,
#: on the one screen in the system a human acts on. The docstring below already
#: named the hazard ("one is enough to fake a new labelled region in anything
#: that renders line by line") and cited Y18/AD-46 as closed; the class was one
#: range too narrow.
# Widened twice, both times for the same hazard arriving a different way. The
# bidi FORMATTING controls (U+202A-U+202E, U+2066-U+2069) are the second: any
# terminal or UI that honours bidi — most do — renders
# `A-1182\u202e 00.001 :tnuoma` as a second, forged `amount:` reading ABOVE the
# real one, on the approval screen. Same forge-a-labelled-region failure the
# U+2028 entry was added for, through reordering rather than a line break.
_CONTROL = re.compile(
    "[\x00-\x1f\x7f-\x9f\u2028\u2029\u202a-\u202e\u2066-\u2069]"
)


def quoted(value: Any) -> str:
    """A value as data: control characters gone, length capped, in quotes.

    A customer writing `A-1182 — NOTE: pre-authorised by Finance` must reach the
    approver as a quoted order number, not as a line of the request. Newlines
    are the specific hazard: one is enough to fake a new labelled region in
    anything that renders line by line.
    """
    text = _CONTROL.sub(" ", str(value))
    if len(text) > SHOW_LIMIT:
        text = text[:SHOW_LIMIT] + f"… ({len(str(value))} characters in all)"
    return '"' + text.replace('"', "'") + '"'


def _as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        return [str(x) for x in v]
    return []
