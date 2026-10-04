# Known on Pydantic AI 2.54

`pydantic-ai-slim` moved from 2.21.0 to 2.54.0 (`pydantic-graph` with it).
`uv run --extra all --extra test pytest tests/ -q`: 2140 passed, 8 skipped at
the move (the opt-in live and absent-runtime skips that existed on 2.21); 2150
passed, 9 skipped at the end of the Phase 1 work (the ninth is the opt-in live
test, `PACT_LIVE_BASE_URL`/`PACT_LIVE_MODEL`, which passes against gpt-oss-20b).
**No test fails on 2.54.**

What the move broke, and how each was fixed:

| Test | Cause on 2.54 | Fix |
|---|---|---|
| `test_a_conversation_crosses_between_the_two_message_dialects.py` (collection) | `UserPromptPart.__post_init__` now refuses an item that is not `UserContent` (messages.py) | the fixture uses a real `ImageUrl` |
| `test_both_directions_…::test_instructions_that_only_exist_during_a_run_are_reported_not_invented` and three more that load the tree it writes | `Agent._instructions` entries are now `SourcedInstruction` wrappers (`_instructions.py:46`), so no instruction read as text | `pydantic_ai_interop._authored_instructions` reads both shapes |
| `test_both_directions_…::test_the_skills_the_author_wrote_reach_the_model` | the test read `agent._instructions` | it reads what a `FunctionModel` is sent |
| `test_the_mcp_export_says_which_shape_it_speaks.py::test_the_pin_the_report_names_is_the_pin_that_is_installed` | the `mcp` extra now pins `fastmcp-slim[client]>=3.3.0,<5`, admitting FastMCP 4 (MCP SDK v2, `2026-07-28`, no `initialize` handshake) | `_MCP_SHAPE` says the shape is the host's install, naming both eras |

## Private Pydantic AI names PACT still reads

None of these is on the run path (`harness.run`). They are what the live
importer (`from_pydantic_ai_agent`) and the facade read because Pydantic AI has
no public read for them; the next pin move should check each first.

- `pact_agent.py`: `pydantic_ai._utils.run_until_complete`
- `pydantic_ai_interop.py`, live importer: `pydantic_ai.agent._AUTO_INJECT_CAPABILITY_TYPES`,
  and on `Agent`: `_instructions`, `_system_prompts`, `_system_prompt_functions`,
  `_system_prompt_dynamic_functions`, `_tool_timeout`, `_metadata`,
  `_output_validators`, `_max_tool_retries`, `_max_output_retries`
