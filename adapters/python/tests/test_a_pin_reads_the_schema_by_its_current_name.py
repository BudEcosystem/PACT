"""A pinned server is read by the field name its SDK uses now.

MCP SDK v2 renamed a tool's `inputSchema` to `input_schema`, and FastMCP 4 keeps
the old name as a property that warns on every read. `digest_of` tried the old
name first, so every call to a pinned server printed a deprecation warning, and
the day the old name goes the digest would fall through to the next key. Both
spellings name the same schema, so the digest does not move.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.mcp_bridge import digest_of  # noqa: E402

SCHEMA = {"type": "object", "properties": {"ticket-id": {"type": "string"}}}


class _Renamed:
    """A tool as SDK v2 hands it back: the new name, and the old one that warns."""

    name = "read-ticket"
    description = "Read one ticket."
    input_schema = SCHEMA

    @property
    def inputSchema(self) -> dict:  # noqa: N802 - the SDK's own spelling
        warnings.warn("inputSchema is deprecated", DeprecationWarning, stacklevel=2)
        return SCHEMA


def test_the_new_name_is_read_and_the_digest_is_the_old_ones() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        renamed = digest_of([_Renamed()])
    old = digest_of([{"name": "read-ticket", "description": "Read one ticket.", "inputSchema": SCHEMA}])
    assert renamed == old
