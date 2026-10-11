"""A US bank account number is a bank account.

`anything that looks like a bank account` read an IBAN, a UK sort code and a UK
account number of exactly eight digits, so the account a US employee typed for
their pay (`000123456789`, twelve digits) reached the model whole: Bud Flow's
corpus case #77, an HR helpdesk whose employee wrote "change my bank account to
000123456789". An account number written as one run of digits has eight to
seventeen of them; a shorter number is still left as written.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.interceptors import Chain  # noqa: E402


def _said(text: str) -> str:
    chain = Chain.from_document(
        {"agents": {"a": {}}, "redaction": {"hide": ["anything that looks like a bank account"]}}, "a"
    )
    seen, _ = chain.run("step.message.before", {"content": text})
    return seen["content"]


@pytest.mark.parametrize("account", ["000123456789", "12345678", "98765432101234567", "4400123456"])
def test_an_account_number_of_eight_to_seventeen_digits_is_hidden(account: str) -> None:
    said = _said(f"please change my bank account to {account} from next payday")
    assert account not in said and "[removed]" in said, said


@pytest.mark.parametrize(
    "text",
    ["order 4471 of 2026, room 12", "employee E-20417 moves on 2026-11-01", "a seven digit ticket 1234567"],
)
def test_a_shorter_number_or_a_date_is_left_as_written(text: str) -> None:
    assert _said(text) == text
