"""The `settings:` block reaches the model call inside the graph, and is saved.

Third of the three, and the one where the honest answer takes the most saying.
Measured on this transport before the fix, on a spec carrying all twelve:

```text
    settings.frequency-penalty, settings.max-tokens,
    settings.parallel-tool-calls, settings.presence-penalty, settings.seed,
    settings.service-tier, settings.stop-sequences, settings.temperature,
    settings.thinking, settings.tool-choice, settings.top-k, settings.top-p
```

**LangGraph has no generation parameters at all.** It is an orchestration layer:
`@entrypoint` and `@task` take a payload and hand it to the function inside. So
there is no `ModelSettings` here as there is on Pydantic AI, and no `bind()` as
there is on LangChain. What LangGraph HAS is a model layer, and that layer is
`langchain_core` — LangGraph depends on it and a `@task` that calls a model calls
a `BaseChatModel`. So the vocabulary this transport can honestly speak is exactly
LangChain's, and it is the same four keys for the same checked reasons: `stop` is
a parameter of `_generate`, `tool_choice` a parameter of `bind_tools`, and
`temperature`/`max_tokens` `langchain_core`'s own SPELLING for two parameters an
integration's `_generate(**kwargs)` is what actually delivers — the weakest of
the three claims, and
`test_what_the_author_asked_for_reaches_langchains_model.py` says at length why.
The other eight have no name in `langchain_core` 1.5.3, which is the only `lang*`
package installed here, and are reported rather than guessed.

**A transport with no model honours nothing, and this one had none.** The first
version of this file was the defect it was written to close, moved one level in.
`model_call` put the four translated keys into the `@entrypoint` payload; the
`@task` called `Script.next_turn` directly; the transport constructed no
`BaseChatModel` at all, and `payload["settings"]` was read by nothing anywhere in
`src/`. Every test below passed. Four keys came off `RunResult.unmetered` — the
author told they were honoured — on runs that dropped all four. The `@task` now
calls a `BaseChatModel` (the transport's own docstring already said it should:
*"a `@task` that calls a model calls a `BaseChatModel`"*), the settings are
attached with `bind`/`bind_tools`, and the assertions are made at `_generate`.

**What is LangGraph's own is that the settings are CHECKPOINTED on the way.** The
transport carries them in the payload the `@entrypoint` is invoked with, so they
are written to the `InMemorySaver` with everything else and a resumed graph
resumes with the run's own settings rather than with a host's defaults. This
transport is the one whose lattice says `durable_resume: native`, and a setting
that did not survive a resume would make that claim false in a way nothing else
here would catch. That is a real property and it is asserted in its own test with
its own name, because on its own it honours nothing.

Mutation: drop the `"settings"` key from the payload dict `model_call` invokes
the graph with. Measured: `5 failed, 7 passed` —
`test_the_settings_reach_the_model_the_task_calls`,
`test_the_payload_the_task_was_handed_carries_them_too`,
`test_a_resumed_graph_resumes_with_the_runs_own_settings`,
`test_a_tool_choice_naming_a_tool_this_call_does_not_offer_is_not_sent` and
`test_the_run_still_works_when_the_author_wrote_no_settings`.

Second mutation, and the one that matters, because it is the one the first
version of this file could not survive: leave the payload alone and make
`_answer` ignore it — back to `turn = self.script.next_turn(history)`, no model
call, exactly as this transport shipped for a round. Measured: `2 failed, 10
passed`, and both failures are the assertions made at the model —
`test_the_settings_reach_the_model_the_task_calls` and
`test_a_tool_choice_naming_a_tool_this_call_does_not_offer_is_not_sent`. Under
the OLD tests that same edit was invisible: all six passed, because every one of
them read the payload back rather than the request.

Tests that CANNOT catch either mutation, kept and named rather than deleted:
`test_the_eight_langgraph_has_no_name_for_are_reported_not_guessed`,
`test_a_tool_choice_a_call_cannot_carry_is_not_bound_to_it` and
`test_the_run_still_works_when_the_author_wrote_no_settings` under the second
edit — all three assert an ABSENCE, which a transport that sends nothing at all
satisfies. They pin the honesty half; the two above pin the delivery half.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # noqa: E402

from pact_adapters.harness import run  # noqa: E402
from pact_adapters.ir import AgentSpec, ToolSpec  # noqa: E402
from pact_adapters.script import Script, Turn  # noqa: E402

pytest.importorskip(
    "langgraph", reason="LangGraph is not installed in this environment"
)

from pact_adapters.transports.langgraph_transport import (  # noqa: E402
    LangGraphTransport,
    _settings_for_the_task,
)


ALL_TWELVE = {
    "max-tokens": 512,
    "thinking": "high",
    "temperature": 0.2,
    "top-p": 0.9,
    "top-k": 40,
    "stop-sequences": ["END"],
    "seed": 7,
    "presence-penalty": 0.5,
    "frequency-penalty": 0.1,
    "tool-choice": "payments",
    "parallel-tool-calls": False,
    "service-tier": "flex",
}

#: The eight with no name in `langchain_core`, which is LangGraph's model layer.
NO_NAME_IN_CORE = (
    "thinking", "top-p", "top-k", "seed", "presence-penalty",
    "frequency-penalty", "parallel-tool-calls", "service-tier",
)


def _spec(settings: dict) -> AgentSpec:
    return AgentSpec(
        name="refund-desk",
        description="decides refunds",
        instructions="Be brief.",
        tools=(ToolSpec(name="payments", description="pays"),),
        settings=dict(settings),
    )


class Recording(LangGraphTransport):
    """The shipped transport, keeping what the MODEL inside the task was handed.

    Two things are recorded and they are not the same thing, which is the whole
    lesson of this file's first version.

    `seen` is the payload the `@task` was invoked with. That is a fact about
    LangGraph — it arrived by being serialised through the graph — and it is
    worth pinning, because it is what the checkpointer writes down. It is NOT
    evidence that any setting was honoured: for a round the payload carried a
    `settings` entry that nothing in the transport read, and every test here
    passed while the run dropped all four keys on the floor.

    `saw_stop` and `saw_kwargs` are what `langchain_core` delivered to
    `_generate` after `bind`/`bind_tools` — the model layer LangGraph orchestrates
    through, and the same delivery path a real `ChatOpenAI` takes. That is the
    effect. The mutation that severs the settings from the request has to turn
    those red or the file has proved nothing.
    """

    def __init__(self, *a, **kw) -> None:
        self.seen: list[dict] = []
        self.saw_stop: list | None = None
        self.saw_kwargs: dict = {}
        super().__init__(*a, **kw)
        transport = self
        inner = self._model._generate

        def _generate(messages, stop=None, run_manager=None, **kwargs):
            transport.saw_stop = stop
            transport.saw_kwargs = dict(kwargs)
            return inner(messages, stop=stop, run_manager=run_manager, **kwargs)

        object.__setattr__(self._model, "_generate", _generate)

    def _answer(self, payload: dict) -> dict:
        self.seen.append(dict(payload))
        return super()._answer(payload)


def _ran(transport: LangGraphTransport, settings: dict):
    return asyncio.run(run(_spec(settings), transport, "hello"))


def test_the_settings_reach_the_model_the_task_calls() -> None:
    """The model's own request, not the payload and not the mapping table.

    The register records the trap in its own words: *"A test of mine failed its
    own mutation here. The first version asserted `_WIRE` membership and what
    `apply_settings` returned — both true of a transport that then drops every
    setting on the floor."* This file's first version found a third way to fall
    into it: it asserted a key in a dict PACT built and handed to a PACT method,
    and the payload's `settings` entry had no reader anywhere in the tree.
    `grep -rn '\\["settings"\\]' src/pact_adapters/` found one hit and it was a
    docstring. So four keys came off `RunResult.unmetered` — the author told they
    were honoured — on a run that delivered none of them.

    They are read here where `langchain_core` delivers them, inside `_generate`,
    which is where a real integration builds its request.
    """
    t = Recording(Script([Turn("Decision: approved.")]))
    _ran(t, ALL_TWELVE)

    # `stop` is first-class on `_generate` — its own parameter in the signature,
    # which is what makes it the one PACT key `BaseChatModel` itself is
    # guaranteed to honour.
    assert t.saw_stop == ["END"], t.saw_stop
    assert t.saw_kwargs.get("temperature") == 0.2, t.saw_kwargs
    assert t.saw_kwargs.get("max_tokens") == 512, t.saw_kwargs
    assert t.saw_kwargs.get("tool_choice") == "payments", t.saw_kwargs
    # And the tools went with it, because a tool choice without them is a
    # setting about nothing.
    assert [d["name"] for d in t.saw_kwargs.get("tools") or []] == ["payments"]


def test_the_payload_the_task_was_handed_carries_them_too() -> None:
    """What is LangGraph's own, kept separate from the delivery claim above.

    The settings travel to the model INSIDE the `@entrypoint` payload rather than
    beside the graph, so they are checkpointed on the way. That is a real
    property and it is this transport's alone — but on its own it honours
    nothing, which is why it is asserted in its own test with its own name
    instead of standing in for one.
    """
    t = Recording(Script([Turn("Decision: approved.")]))
    _ran(t, ALL_TWELVE)

    assert t.seen, "the task was never reached"
    said = t.seen[0].get("settings")
    assert said == {
        "max_tokens": 512,
        "temperature": 0.2,
        "stop": ["END"],
        "tool_choice": "payments",
    }, said


@pytest.mark.parametrize("chose", ["required", "payments", "none", "auto"])
def test_a_tool_choice_a_call_cannot_carry_is_not_bound_to_it(chose: str) -> None:
    """The closing call, which offers NO tools.

    `harness.run` makes one on every ceiling-terminated run — "one closing call
    with NO tools offered". A tool choice attached to it has nothing to be about,
    and on this model layer attaching it anyway means `bind()` rather than
    `bind_tools()`, which is the one route on which no integration translates it:
    the provider then gets the bare word `any` (which no OpenAI-compatible
    endpoint accepts) or a bare tool name (which such an endpoint accepts and
    silently ignores).
    """
    t = Recording(Script([Turn("Decision: approved.")]))
    spec = AgentSpec(
        name="advisor",
        description="answers",
        instructions="Be brief.",
        settings={"tool-choice": chose},
    )
    asyncio.run(run(spec, t, "hello"))
    assert "tool_choice" not in t.saw_kwargs, t.saw_kwargs
    assert "tools" not in t.saw_kwargs, t.saw_kwargs


def test_a_tool_choice_naming_a_tool_this_call_does_not_offer_is_not_sent() -> None:
    """A stage narrows the tools; the author's choice narrows with it.

    Same rule as the LangChain transport, because it is the same model layer:
    a `tool_choice` naming a tool that is not in THIS call's list becomes a
    `{"type": "function", ...}` the provider rejects.
    """
    t = Recording(Script([Turn("Decision: approved.")]))
    spec = AgentSpec(
        name="refund-desk",
        description="decides refunds",
        instructions="Be brief.",
        tools=(ToolSpec(name="lookup", description="looks up"),),
        settings={"tool-choice": "payments"},
    )
    asyncio.run(run(spec, t, "hello"))
    assert [d["name"] for d in t.saw_kwargs.get("tools") or []] == ["lookup"]
    assert "tool_choice" not in t.saw_kwargs, t.saw_kwargs

    ok = Recording(Script([Turn("Decision: approved.")]))
    _ran(ok, {"tool-choice": "required"})
    assert ok.saw_kwargs.get("tool_choice") == "any", ok.saw_kwargs


def test_a_resumed_graph_resumes_with_the_runs_own_settings() -> None:
    """LangGraph's own half, and the reason this file is not a copy of the
    LangChain one.

    The lattice here says `durable_resume: native`. A run that is killed and
    resumed reads its state back out of the checkpointer — so a `settings:`
    block that lived beside the graph rather than inside its payload would come
    back as whatever the host had configured at resume time, silently, on the
    one transport whose whole claim is that a resume is faithful.
    """
    t = Recording(Script([Turn("Decision: approved.")]))
    _ran(t, {"max-tokens": 64, "temperature": 0.5})

    saved = [
        tup.checkpoint.get("channel_values", {}).get("__start__")
        for tup in t._saver.list(None)
    ]
    kept = [s.get("settings") for s in saved if isinstance(s, dict) and "settings" in s]
    assert kept, f"nothing the checkpointer saved carried the settings: {saved}"
    assert kept[0] == {"max_tokens": 64, "temperature": 0.5}, kept


def test_the_eight_langgraph_has_no_name_for_are_reported_not_guessed() -> None:
    """LangGraph takes no generation parameters of its own, and its model layer
    is `langchain_core`, which names four. The other eight are reported.

    Sending a guessed `top_k` into the payload would put it on whatever model
    the task calls, where an integration that has no such parameter forwards it
    to the provider or swallows it into `model_kwargs` — a setting in a shape
    the provider ignores, with nothing saying it did not happen.
    """
    t = Recording(Script([Turn("Decision: approved.")]))
    out = _ran(t, ALL_TWELVE)

    left = sorted(u for u in out.unmetered if u.startswith("settings."))
    assert left == sorted(f"settings.{k}" for k in NO_NAME_IN_CORE), left
    said = t.seen[0].get("settings") or {}
    for guessed in ("top_p", "top_k", "seed", "presence_penalty",
                    "frequency_penalty", "parallel_tool_calls", "service_tier",
                    "thinking", "reasoning_effort"):
        assert guessed not in said, f"{guessed} was guessed into the payload"
        assert guessed not in t.saw_kwargs, f"{guessed} was guessed onto the call"


def test_one_authored_word_becomes_the_model_layers_own_word() -> None:
    """`required` is `any` in `BaseChatModel.bind_tools`' vocabulary, which is
    the vocabulary a LangGraph task's model call speaks. Same authored word, and
    the graph carries the translated one — translating at the last hop instead
    would put the author's spelling in the checkpoint and translate it again on
    every resume.
    """
    assert _settings_for_the_task({"tool-choice": "required"}) == {"tool_choice": "any"}
    assert _settings_for_the_task({"tool-choice": "payments"}) == {"tool_choice": "payments"}
    # "list of text" written as one line is still a list, because a bare string
    # is a sequence of CHARACTERS to anything that iterates it.
    assert _settings_for_the_task({"stop-sequences": "END"}) == {"stop": ["END"]}
    assert _settings_for_the_task({"thinking": "high"}) == {}


def test_the_run_still_works_when_the_author_wrote_no_settings() -> None:
    """A transport that only works with a `settings:` block is worse than the
    one it replaced. Nothing carried, nothing bound, nothing reported, and no
    `stop` invented."""
    t = Recording(Script([Turn("Decision: approved.")]))
    out = _ran(t, {})
    assert t.seen[0].get("settings") == {}, t.seen[0]
    assert t.saw_stop is None, t.saw_stop
    assert not [k for k in t.saw_kwargs if k in ("temperature", "max_tokens")]
    assert [u for u in out.unmetered if u.startswith("settings.")] == []


def test_the_transport_still_counts_what_the_call_carried() -> None:
    """The metering already in the task must survive a wider payload — both money
    ceilings read `usage()`, and losing it would put them back on `unmetered`
    without failing anything above."""
    t = Recording(Script([Turn("Decision: approved.")]))
    _ran(t, ALL_TWELVE)
    tokens, _money = t.usage()
    assert tokens > 0, "the call carried nothing the meter could see"
