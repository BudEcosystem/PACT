"""docs/96 §D: `turns:` lowered to Pydantic AI's own messages, by §D's table."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pydantic_ai.messages import (  # noqa: E402
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from pact_adapters.pydantic_ai_turns import messages_of  # noqa: E402

KETTLE = [  # docs/96 §D's own example
    {"from": "developer", "says": "Every caller has been told the call may be recorded."},
    {"from": "user", "says": "Did you get my email about the broken kettle?"},
    {"from": "agent", "calls": "email/search-messages", "with": {"query": "broken kettle"}},
    {"from": "tool", "answer": 'One message, sent yesterday, subject "Kettle arrived cracked".'},
    {"from": "agent", "says": "Yes — I have it here."},
]


def test_the_kettle_conversation_is_five_messages_in_order() -> None:
    messages = messages_of(KETTLE, tool_name=lambda call: call.replace("/", "_"))
    assert [type(m) for m in messages] == [ModelRequest, ModelResponse, ModelRequest, ModelResponse]
    first = messages[0].parts
    assert isinstance(first[0], SystemPromptPart) and isinstance(first[1], UserPromptPart)
    [call] = messages[1].parts
    assert isinstance(call, ToolCallPart) and call.tool_name == "email_search-messages"
    assert call.args == {"query": "broken kettle"}
    [back] = messages[2].parts
    assert isinstance(back, ToolReturnPart) and back.tool_call_id == call.tool_call_id
    assert back.tool_name == call.tool_name and "Kettle arrived cracked" in back.content
    [said] = messages[3].parts
    assert isinstance(said, TextPart) and said.content == "Yes — I have it here."


def test_an_agents_words_are_filled_and_a_cases_are_not() -> None:
    turns = [{"from": "user", "says": "Hello {{run-inputs.name}}"}]
    filled = messages_of(turns, fill=lambda s: s.replace("{{run-inputs.name}}", "Ada"))
    assert filled[0].parts[0].content == "Hello Ada"
    assert messages_of(turns)[0].parts[0].content == "Hello {{run-inputs.name}}"


def test_an_attachment_follows_the_words_of_its_turn() -> None:
    turns = [{"from": "user", "says": "Here is the receipt.", "attaches": ["run-inputs.receipt"]}]
    [request] = messages_of(turns, attached=lambda name: f"<{name}>")
    assert request.parts[0].content == ["Here is the receipt.", "<run-inputs.receipt>"]


def test_a_conversation_may_end_with_the_persons_turn() -> None:
    """A case's turns end with the person's (or a tool's): the last message is a request."""
    messages = messages_of([{"from": "agent", "says": "Hi."}, {"from": "user", "says": "Refund me."}])
    assert isinstance(messages[-1], ModelRequest)
