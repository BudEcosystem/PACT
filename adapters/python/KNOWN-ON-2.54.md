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
| `test_both_directions_…::test_instructions_that_only_exist_during_a_run_are_reported_not_invented` and three more that load the tree it writes | `Agent._instructions` entries were now `SourcedInstruction` wrappers (`_instructions.py:46`), so no instruction read as text | then `pydantic_ai_interop._authored_instructions` read both shapes; since WP-38 no private attribute is read: `pydantic_ai_reading` takes the instructions from a probe request's `instruction_parts` |
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

`tests/parity/<row>/` holds one folder per agent-level 02P row (138, since
WP-38): a fixture (a PACT tree, an `AgentSpec` file, or an `agent.py` that builds
an `Agent`) and an `expect.yaml`, or, for a row with nothing on an agent to
import, `import: none` and why (a run's, a host's or an export's), or `later:`
and the package whose importer reads it. The same test imports each fixture
back (S1), checks the plain-words report (S5), exports each tree row and names
what its export cannot carry (S2), round-trips each agent a spec file holds whole
to the same `pact show` digest (S3), and runs each tree's agent through
`build_agent` on a scripted `FunctionModel`. `pydantic-ai-harness` 0.54 is a
test dependency so its 62 capabilities are in S4 and the harness rows have
fixtures; each is a named loss naming the PACT construct to write.

## No private Pydantic AI name is read

No module imports one (`tests/test_the_loader_is_found_one_way.py::
test_no_module_imports_a_private_name_from_pydantic_ai`), and since WP-38 none
reads one either (`test_no_module_reads_a_private_attribute_of_pydantic_ai`: an
underscored attribute no PACT module defines, read in a module that imports
Pydantic AI). The two that were imported are gone: `pact_agent.py` enters a run
from sync code with its own helper over public `asyncio` (it was
`pydantic_ai._utils.run_until_complete`), and the capabilities the SDK injects
are read off a bare `Agent`'s public `root_capability` (it was
`pydantic_ai.agent._AUTO_INJECT_CAPABILITY_TYPES`).

The live importer reads an `Agent` the way any caller can
(`pact_adapters/pydantic_ai_reading.py`):

- instructions and system prompts from a probe request: the agent run, as it
  is and bare (no capabilities, toolsets or tools), under
  `Agent.override(model=FunctionModel(...))` with model requests off, the
  function recording `ModelRequestParameters.instruction_parts` (each marked
  `dynamic` or not) and the request's `SystemPromptPart`s (`dynamic_ref`), then
  stopping the run before anything answers, so no tool runs. Deps are `None`,
  `deps_type()`, or a stand-in that answers everything with nothing; a part made
  from it is dynamic. A dynamic part is counted and named, never carried; so is
  a part only the full run has, which a capability or a toolset added (an
  `AskUser`'s instructions, an MCP server's, a `FunctionToolset`'s). When the
  full run fails, its capabilities and its tools are run apart; a capability
  that fails makes what they add a named loss, and a tool's `prepare=` or a
  filter that fails does not (it adds no instruction; the walk names it): each
  toolset is then asked for its instructions (`get_instructions`);
- tools from `agent.toolsets` and each toolset's `get_tools`, walking every
  wrapper through its public attributes (`prefix`, `name_map`, `filter_func`,
  `approval_required_func`, `wrapped`, `toolsets`); an MCP server is opened to
  list its tools, as every run opens it;
- the output from `output_type` and `output_json_schema()`; a tool's timeout
  and retry budget from `Tool.timeout`, `Tool.max_retries` and its
  `FunctionToolset`'s.

What has no public read is one named loss on every live import, `not_shown`:
output validators, the agent's retry budgets, its metadata, `max_concurrency`,
a `FallbackModel`'s `fallback_on`, and an instruction function that wrote
nothing for the deps the importer built. A `@agent.system_prompt` function not
marked dynamic cannot be told from a written string either, so system prompts
are carried as one run wrote them and named (`system_prompts.maybe-made-by-code`).
`pact_agent.py` builds an
`AgentRunResult` from its public serialized shape, and names an unnamed agent
from the caller's frame itself.
