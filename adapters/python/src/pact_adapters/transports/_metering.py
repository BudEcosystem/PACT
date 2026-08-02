"""What one model call cost, for the transports whose wire format carries it.

This is the shared half of `usage()` and `summary_usage()` — the two optional
methods `harness.Transport` asks for and never requires, and the two that no
shipped transport implemented for a round. `harness._meter_usage` probed for
`usage()`, found nothing on all seven, and `Limits.unmeterable` therefore put
**both** `cost-per-request-under` and `tokens-at-most` on `RunResult.unmetered`
on every real run. The mechanism was honest and inert — exactly the state
`context_window()` was in before `models/catalog.yaml` landed — and it is closed
the same way: **from the catalogue, not hardcoded per transport.**

Three rules, each already argued somewhere a reader can check:

* **Tokens and money are two questions, and they are asked separately.**
  A token count is knowable whenever a call is made — a live provider returns
  it, a scripted seam counts what it built — and a price is knowable only if the
  catalogue publishes one. For a round they were one question: `can_price`
  decided whether `usage()` existed AT ALL, so a locally-served model with a
  window and no `cost:` block lost `tokens-at-most` as a side effect of having
  no price. That contradicts that field's own help text — *"This is the only
  ceiling that still bites when there is no price list: a model running on your
  own machine costs nothing per word, so a money cap cannot bound it and this
  can"* — and it landed on exactly the D17 author the workspace override layer
  was built for. So [`priced`] answers `(tokens, None)` on an unpriced row: the
  count is real, the bill is unknown, and only the money ceiling goes out on
  `RunResult.unmetered`.
* **An unpriced row yields `None`, never zero.** `ModelEntry.cost`'s own
  comment: an unpriced row used to sort first as the cheapest model and print
  `at 0.0/1k tokens`, a price nobody published. Metering a ceiling at 0.0 USD is
  the same mistake one hop along — a spend cap that can never be reached, under
  an author who believes they capped their spend. The same rule reaches one
  further hop in [`what_the_summariser_cost`], which used to answer `(0, 0.0)`
  for a summarising model nobody could price.
* **`transports/mock.py` stays honest-and-inert on purpose.** It is bound to no
  model, so it has nothing to count and nothing to price, and it is the one
  transport that keeps the `unmetered` route exercised. A failure route nothing
  reaches is a route nobody has checked.

**A workspace's own catalogue reaches all of this.** Every function here takes
`workspace=` and hands it to `resolve.price_of`, which layers a workspace-local
`models/catalog.yaml` over the distribution's. Without it the documented no-code
escape hatch for an air-gapped box — architecture §4.2's override layer — reached
the *window* lookup and not the *money* one, so an author who added a row for
their locally-served model still had both money ceilings on `unmetered` with no
no-code way out. `load_catalogue`'s own docstring names that shape: *a file the
checker accepts but the harness never opens is the same defect one hop along.*

**Where the token counts come from.** A live provider returns them and the
transport reads them off the response: `ollama_transport.py` takes
`usage.prompt_tokens` / `usage.completion_tokens` straight off the wire. The
scripted seams have no tokeniser, so they count the text they actually built —
`CHARS_PER_TOKEN`, the same declared approximation the context policy is
measured with, so a run cannot be tidied against one estimate and billed against
another. That is a stand-in's estimate of a stand-in's call, and it is written
into the SDK's own usage object (`anthropic.types.Usage`,
`autogen_core.models.RequestUsage`, `agents.usage.Usage`) rather than kept
beside it — those three seams already constructed one and hardcoded it to zero,
which is where the figure a live call fills in belongs.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from ..context_policy import CHARS_PER_TOKEN
from ..resolve import price_of


def can_price(model: str, workspace: str = "") -> bool:
    """Whether the catalogue publishes both halves of this model's price.

    Asked once, in a transport's `__init__`, and published as
    `Transport.prices_money` — which is the signal `harness.run` reads before
    deciding whether the MONEY ceilings can be enforced. It no longer decides
    whether `usage()` exists: a transport that can count tokens and cannot price
    them says so, rather than falling silent about both.

    `workspace` is the override layer. A machine serving a model this
    distribution has never heard of writes a row for it in its own
    `models/catalog.yaml`, and until that reached here the row was accepted by
    `pact check` and never opened by the thing that meters.
    """
    return price_of(model, 0, 0, workspace=workspace or None) is not None


def tokens_in(text: Any) -> int:
    """How many tokens a piece of text is, by this distribution's own rule.

    `CHARS_PER_TOKEN` and nothing cleverer, because it is what
    `context_policy.estimate` already measures a conversation with: a run that
    tidied at 85% of a window counted one way and was billed counted another
    would produce two token figures for one call, and the author would have no
    way to tell which one their ceiling was compared against.

    A real provider never comes through here — `ollama_transport.py` reads the
    counts the server returned. This is for the scripted seams, which have no
    tokeniser and would otherwise have to invent one.
    """
    return len(str(text or "")) // CHARS_PER_TOKEN


def tokens_sent(system: str, history: Iterable[Mapping[str, Any]]) -> int:
    """What one request carried in, counted over the messages actually built.

    The system prompt is counted with the history because the provider bills it:
    a stage that swaps a long instruction in is a cost the author can act on, and
    dropping it here would hide the one part of the prompt a `loop:` changes
    per step.
    """
    body = "".join(str(m.get("content") or "") for m in history)
    return tokens_in(system) + tokens_in(body)


def priced(
    model: str, input_tokens: int, output_tokens: int, workspace: str = ""
) -> tuple[int, "float | None"]:
    """One call as `usage()` reports it: total tokens, and what they cost.

    Tokens are the SUM of both directions, because `tokens-at-most` is help-texted
    as the tokens a request may use and a ceiling that counted only the prompt
    would let a runaway answer past it. Money comes from `resolve.price_of`, the
    one place a price is looked up.

    **`None` for the money half is a real answer and not a failure.** The count
    is knowable whenever a call is made; the price is knowable only if somebody
    published one. Answering `None` is what lets `tokens-at-most` keep biting on
    an unpriced row while `cost-per-request-under` goes out on
    `RunResult.unmetered` — two ceilings, two facts, one tuple. Answering `0.0`
    here instead would be the `at 0.0/1k tokens` defect `ModelEntry.cost`
    records, spending real money.
    """
    return (
        int(input_tokens) + int(output_tokens),
        price_of(model, input_tokens, output_tokens, workspace=workspace or None),
    )


def what_the_summariser_cost(other: Any) -> "tuple[int, float] | None":
    """What the SECOND transport's one call cost, read off that transport.

    `context-policy.summarised-by:` names a different model, so `write_summary`
    builds a second instance bound to it and that instance is the only thing
    that knows what its own call carried — `usage()` on the first one never sees
    it, which is the whole reason `summary_usage()` is a separate method
    (`harness.Transport`: *"a different transport instance … so its bill never
    reaches `usage()` on this one"*). Asking the second instance rather than
    re-deriving the figure keeps one arithmetic, priced on the summarising
    model's own row and not on the working model's.

    **`None` when nobody can price that call**, which for a round was `(0, 0.0)`
    — handed straight to `charge(0, 0.0)`, so a `summarised-by:` model the
    catalogue cannot price was billed as nothing at all against the author's
    spend cap, silently. That is exactly the mistake this module's own opening
    forbids one hop along, and it was reachable from the shipped distribution
    with one line: `models/catalog.yaml` publishes `gpt-5.4` with
    `cost: unknown`, so `summarised-by: gpt-5.4` under a priced working model
    produced a cap that never counted the summariser. `harness._summariser`
    reads the `None` and puts `summarised-by-cost` on `RunResult.unmetered`,
    which is the door every other unmeasurable thing already leaves by.
    """
    reports = getattr(other, "usage", None)
    if not callable(reports):
        return None
    tokens, money = reports()
    return None if money is None else (int(tokens), float(money))
