"""`redaction.yaml` can name a social security number, and a bank account in
lower case is a bank account.

Two gaps Bud Flow's corpus hit (use cases #23, #50, #55, #75 and #77 ask for the
first; complex live scenario 42 found the second):

* `anything that looks like a social security number` was refused at load —
  the recognisable things were card number, bank account, email address and
  phone number, and nothing else could be named;
* `gb82west12345698765432` went through a `bank account` rule untouched, because
  the IBAN pattern read capital letters only.

Both are held through the real loader (the schema's closed list) and through
the sentence a run carries out.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pact_adapters.interceptors import Chain  # noqa: E402
from trees import pact, write  # noqa: E402

SSN_FORMS = ["123-45-6789", "123 45 6789", "123456789"]


def _hidden(*hide: str) -> Chain:
    return Chain.from_document({"agents": {"a": {}}, "redaction": {"hide": list(hide)}}, "a")


def _said(chain: Chain, text: str) -> str:
    seen, _ = chain.run("step.message.before", {"content": text})
    return seen["content"]


def test_a_redaction_naming_a_social_security_number_loads(tmp_path: Path) -> None:
    root = write(
        tmp_path / "w",
        {
            "workspace.yaml": "name: w\nallow-egress: []\n",
            "agents/desk.yaml": "description: Answers HR questions.\ninstructions: Answer briefly.\n",
            "redaction.yaml": (
                "description: Nothing that identifies a person leaves.\n"
                "hide:\n  - anything that looks like a social security number\n"
            ),
        },
    )
    checked = pact("check", "--deny-warnings", str(root))
    assert checked.returncode == 0, checked.stdout + checked.stderr


@pytest.mark.parametrize("ssn", SSN_FORMS)
def test_a_social_security_number_is_hidden_in_every_way_it_is_written(ssn: str) -> None:
    said = _said(_hidden("anything that looks like a social security number"), f"my ssn is {ssn}.")
    assert ssn not in said and "[removed]" in said, said


def test_a_number_split_some_other_way_is_not_read_as_one() -> None:
    said = _said(_hidden("anything that looks like a social security number"), "call 12-345-6789")
    assert said == "call 12-345-6789"


@pytest.mark.parametrize(
    "iban", ["gb82west12345698765432", "gb29 nwbk 6016 1331 9268 19", "GB82WEST12345698765432"]
)
def test_a_bank_account_is_hidden_in_either_case(iban: str) -> None:
    said = _said(_hidden("anything that looks like a bank account"), f"refund to {iban} please")
    assert said == "refund to [removed] please", said


def test_the_new_thing_works_beside_the_others_in_one_file() -> None:
    chain = _hidden(
        "anything that looks like a card number",
        "do the same for anything that looks like a social security number",
    )
    said = _said(chain, "card 4111 1111 1111 1111, ssn 123-45-6789")
    assert "4111" not in said and "6789" not in said, said


@pytest.mark.parametrize(
    "kept",
    [
        "ab12f9e8d7c6b5a4e3d2c1b0a9f8e7d6",  # a UUID written without its dashes
        "de34a1b2c3d4e5f6a7b8",  # a commit hash
        "ab12cdefgh1234",  # a URL segment
        "GB82WEST12345698765431",  # an IBAN's shape whose check digits are wrong
    ],
)
def test_an_id_that_only_starts_like_an_iban_stays(kept: str) -> None:
    """Either case, run together, also fits a hex digest: a candidate is hidden
    only when it passes the ISO 13616 check, so the ids a run needs survive."""
    chain = _hidden("anything that looks like a bank account")
    text = f"look up {kept} and refund to gb82west12345698765432 please"
    assert _said(chain, text) == f"look up {kept} and refund to [removed] please"


def test_an_iban_in_fours_followed_by_a_number_is_hidden_and_the_number_kept() -> None:
    chain = _hidden("anything that looks like a bank account")
    said = _said(chain, "pay GB29 NWBK 6016 1331 9268 19 1234 now")
    assert said == "pay [removed] 1234 now", said
