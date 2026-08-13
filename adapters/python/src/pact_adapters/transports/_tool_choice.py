"""Whether ONE model call can carry the author's `tool-choice:`.

`settings.tool-choice`'s help says *"auto, required, none, or one tool name"*.
Three of those four are answers about the tools **this call offers**, and the
harness makes calls that offer none:

* `harness.run`'s closing call is `transport.model_call(spec.instructions,
  history, [])` — no tools at all, deliberately, so a run that hit a ceiling
  answers from what it already has instead of starting more work.
* a stage narrows the set: `step_tools = [d for d in tool_defs if d["name"] in
  offered]`, and a stage may offer nothing or may not offer the tool the author
  named.

So `apply_settings` — which is asked ONCE, before the loop, and knows nothing
about either — cannot be the place this is decided. It is decided per call, and
what it decides is whether to SEND the key, never how to approximate it.

What sending it anyway costs, measured on the installed SDKs:

* Pydantic AI raises. `models/_tool_choice.resolve_tool_choice` is called by
  every provider model in the tree (openai, anthropic, google, groq, mistral,
  cohere, bedrock, xai, huggingface) and with `function_tools=[]` it gives
  `UserError: `tool_choice` was set to "required", but no function tools are
  defined` and `UserError: Invalid tool names in `tool_choice`: {'payments'}`.
  A `settings:` key that was merely unhonoured before would now kill the run.
* LangChain does not raise, which is worse. A `tool_choice` that misses
  `bind_tools` — the only place an integration translates it — reaches the
  provider payload as the bare word: `any` is a value no OpenAI-compatible
  endpoint accepts, and a bare tool name is one it accepts and silently ignores.
  That is the translate-or-nothing line exactly.

Both spellings are understood here because both exist in the tree: PACT's own
`required`, and the `any` LangChain's `bind_tools` uses for the same idea. A
helper that knew only one would be right on one transport and quietly wrong on
the other, which is the failure it is here to prevent.
"""

from __future__ import annotations

from typing import Any, Iterable


def can_choose(chose: Any, offered: "Iterable[str]") -> bool:
    """Whether a call offering `offered` can carry `chose` truthfully.

    `auto` and `none` are answers a call with no tools can still give — "pick
    for yourself" and "do not call one" are both satisfiable by a call that has
    nothing to pick from, and `resolve_tool_choice` returns them unchanged in
    that state. `required` (and LangChain's `any`, the same word) needs at least
    one tool to be required OF. A NAME needs THAT tool, on THIS call.

    Returning `False` means the key is not sent for this call. It is not an
    approximation and it is not a substitution: nothing goes in its place.
    """
    said = str(chose).strip()
    names = {str(n) for n in offered}
    if said in ("auto", "none"):
        return True
    if said in ("required", "any"):
        return bool(names)
    return said in names
