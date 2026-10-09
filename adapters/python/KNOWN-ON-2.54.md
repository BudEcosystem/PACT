# Known on Pydantic AI 2.54

`pydantic-ai-slim` moved from 2.21.0 to 2.54.0 (`pydantic-graph` with it).
`uv run --extra all --extra test pytest tests/ -q`: 2140 passed, 8 skipped at
the move (the opt-in live and absent-runtime skips that existed on 2.21). The
Phase 1 work added one skip, the opt-in live test (`PACT_LIVE_BASE_URL`,
`PACT_LIVE_MODEL`, and `PACT_LIVE_API_KEY` when the server wants a key).
**No test fails on 2.54.**

The count today is not repeated here. It was, and it went stale as soon as a
test was added. It is on `README.md`'s status line, which
`tests/test_the_headline_test_count_is_the_count.py` holds to what pytest
collects.

What the move broke, and how each was fixed:

| Test | Cause on 2.54 | Fix |
|---|---|---|
| `test_a_conversation_crosses_between_the_two_message_dialects.py` (collection) | `UserPromptPart.__post_init__` now refuses an item that is not `UserContent` (messages.py) | the fixture uses a real `ImageUrl` |
| `test_both_directions_…::test_instructions_that_only_exist_during_a_run_are_reported_not_invented` and three more that load the tree it writes | `Agent._instructions` entries are now `SourcedInstruction` wrappers (`_instructions.py:46`), so no instruction read as text | `pydantic_ai_interop._authored_instructions` reads both shapes |
| `test_both_directions_…::test_the_skills_the_author_wrote_reach_the_model` | the test read `agent._instructions` | it reads what a `FunctionModel` is sent |
| `test_the_mcp_export_says_which_shape_it_speaks.py::test_the_pin_the_report_names_is_the_pin_that_is_installed` | the `mcp` extra now pins `fastmcp-slim[client]>=3.3.0,<5`, admitting FastMCP 4 (MCP SDK v2, `2026-07-28`, no `initialize` handshake) | `_MCP_SHAPE` says the shape is the host's install, naming both eras |

## The parity suite holds the pin

`tests/test_parity.py` is 02P §6's suite. Its completeness check (S4) reads
public names only: every capability class anywhere in the installed
`pydantic_ai` (read from its source, so a capability in a provider module whose
optional dependency is not installed is found too, such as
`models.openai.OpenAICompaction`, `models.anthropic.AnthropicCompaction` and
`durable_exec.*Durability`), every `pydantic_ai.capabilities` member and
`CAPABILITY_TYPES` entry, every `AgentSpec` field, every
`ModelSettings` key, every message part (`ModelRequestPart`,
`ModelResponsePart`), every `AgentStreamEvent` member, every `ToolDefinition`
field and every public `GraphBuilder` member, and fails on any name
`pydantic_ai_registry.yaml` has no row for. On 2.54 that is 19 message parts, 23
stream events, 17 `ToolDefinition` fields and 16 `GraphBuilder` members beside
the doors that were already held; each has its outcome and its 02P row. Moving
the pin is a run of that one test: a name it prints is a row to write, never
code.

`tests/parity/<row>/` holds one folder per 02P row Phase 1 compiles (23 rows),
each a fixture and an `expect.yaml`; the same test imports each back (S1), checks
the plain-words report (S5), and runs each tree's agent through `build_agent` on
a scripted `FunctionModel`.

## Private Pydantic AI names PACT still reads

No module imports one: `tests/test_the_loader_is_found_one_way.py::
test_no_module_imports_a_private_name_from_pydantic_ai` walks every module
under `src/pact_adapters`. The two that were imported are gone:
`pact_agent.py` enters a run from sync code with its own helper over public
`asyncio` (it was `pydantic_ai._utils.run_until_complete`), and the
capabilities the SDK injects are read off a bare `Agent`'s public
`root_capability` (it was `pydantic_ai.agent._AUTO_INJECT_CAPABILITY_TYPES`).

What is left is attributes of a live `Agent` object, read by the live importer
(`from_pydantic_ai_agent`) because Pydantic AI has no public read for them.
None is on the run path (`harness.run`); the next pin move should check each
first.

- `pydantic_ai_interop.py`, live importer, on `Agent`: `_instructions`,
  `_system_prompts`, `_system_prompt_functions`,
  `_system_prompt_dynamic_functions`, `_tool_timeout`, `_metadata`,
  `_output_validators`, `_max_tool_retries`, `_max_output_retries`
