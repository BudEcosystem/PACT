"""Hidden values that travel as placeholders (docs/98 WP-11).

The Origin primitive's `placeholder` operation (`docs/97-PRIMITIVES.md` §5.4).
`redaction.hide` and `hide-values` replace what they recognise, and until this
module the replacement was one-way: `[removed]`, with nothing kept. That is
right for a value nothing downstream needs, and wrong for one a tool does — a
card number the payments tool must charge, an email the mailer must send to.
The patterns this serves are PII tokenisation and the credential broker: the
model, the logs and the person approving never see the value, and the one
action that needs it gets it.

How it works: while a run has an action marked `gets-hidden-values: yes`, each
hidden value becomes a numbered placeholder — `⟦card-number-1⟧` — and the run
keeps the original in its `Vault`. The same value always gets the same
placeholder, so a model that mentions it twice is talking about one thing. The
real value is put back only in the arguments the harness sends to such an
action, after every rule has run, so the trace and any approval show the
placeholder. A run with no such action masks exactly as it always has.
"""

from __future__ import annotations

import re
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

#: The vault the chain currently masking belongs to (`Chain.run` sets it for its
#: own duration), or `None`: mask one-way, as before.
VAULT: "ContextVar[Vault | None]" = ContextVar("pact_vault", default=None)

_TOKEN = re.compile(r"⟦[a-z0-9-]+-\d+⟧")


def _slug(text: str) -> str:
    words = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return words or "hidden"


@dataclass
class Vault:
    """One run's hidden values, by placeholder."""

    held: dict[str, str] = field(default_factory=dict)
    _by_value: dict[str, str] = field(default_factory=dict)
    _counts: dict[str, int] = field(default_factory=dict)

    def token(self, kind: str, original: str) -> str:
        """The placeholder for `original`, which a rule says is a `kind`."""
        if original in self._by_value:
            return self._by_value[original]
        slug = _slug(kind.strip("[]").replace("removed", "").strip())
        n = self._counts.get(slug, 0) + 1
        self._counts[slug] = n
        placeholder = f"⟦{slug}-{n}⟧"
        self.held[placeholder] = original
        self._by_value[original] = placeholder
        return placeholder

    def restored(self, value: Any) -> Any:
        """`value` with every placeholder this vault holds put back."""
        if isinstance(value, str):
            return _TOKEN.sub(lambda m: self.held.get(m.group(), m.group()), value)
        if isinstance(value, dict):
            return {k: self.restored(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.restored(v) for v in value]
        if isinstance(value, tuple):
            return tuple(self.restored(v) for v in value)
        return value
