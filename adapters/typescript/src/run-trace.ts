// Emits the conformance trace for the Vercel AI transport as JSON on stdout,
// so the Python suite can compare it byte-for-byte against the reference.
// Cross-runtime agreement is the strongest form of the portability claim.

import {
  run, undeclaredIn, AGENT_SPEC_FIELDS, type AgentSpec, type ToolCall, type Transport,
} from "./harness.ts";
import { sentence } from "./limits.ts";
import { VercelAITransport } from "./vercel-transport.ts";

const payload = JSON.parse(process.argv[2]);
// A key no `AgentSpec` field declares used to vanish in the cast, so an authored
// setting this port has not ported was neither honoured nor reported — the T7
// breach `notDoneHere` exists to prevent, arriving one layer earlier.
// The SAME function `run` refuses with, rather than a second copy of the rule.
// Kept here as well so the driver can exit 2 with a bare message instead of a
// stack trace — the check is the library's, the exit code is this file's.
const undeclared = undeclaredIn(payload);
if (undeclared.length > 0) {
  process.stderr.write(
    `this port does not know the field(s) ${undeclared.join(", ")}. ` +
      `It reads: ${AGENT_SPEC_FIELDS.join(", ")}.\n`,
  );
  process.exit(2);
}
const spec: AgentSpec = payload;
const script = JSON.parse(process.argv[3]);
const userInput = process.argv[4];

// The tool answers. Given on argv when the caller supplies them — as a map of
// name to the literal string that tool returns — and otherwise the same two the
// Python suite gives, because the claim under test is which stage may reach
// which tool rather than what the tool says back.
// (`tests/test_worked_example_loop.py::TOOLS`.)
//
// Hardcoding them meant NO OTHER FIXTURE could be driven through this script, so
// the cross-runtime claim was pinned to one shape of agent for ever.
//
// ABSENT and EMPTY are different: `'{}'` means this fixture implements no tools
// at all, which is the one case that exercises the unknown-tool path, and
// falling back to the defaults for it made Python answer
// `error: no tool named 'zendesk'` where this port answered a ticket.
const DEFAULT_ANSWERS: Record<string, (a: Record<string, unknown>) => string> = {
  zendesk: (a) => `ticket ${a.ticket}: lamp, 6 days ago, broken`,
  payments: () => "refunded",
};
const tools: Record<string, (a: Record<string, unknown>) => string> =
  process.argv[5]
    ? Object.fromEntries(
        Object.entries(JSON.parse(process.argv[5]) as Record<string, string>).map(
          ([name, said]) => [name, () => said],
        ),
      )
    : DEFAULT_ANSWERS;

// What each stage actually put in front of the model. `may-use:` is a claim
// about what the model can see and `says:` is a claim about what it was told, so
// the only honest way to check either across runtimes is to record what arrived.
// The idiom is borrowed from the `Watching` transport in
// `tests/test_worked_example_loop.py`, which does this job on the Python side.
class Watching implements Transport {
  name: string;
  told: string[] = [];
  offered: string[][] = [];

  private inner: Transport;
  // Forwarded when the inner transport has one. It was not, so the seventh
  // target enforced no token or cost ceiling through the only path the Python
  // suite has to it: the same spec that halted `token-limit` in one step on a
  // bare `VercelAITransport` ran twenty steps to `step-limit` through this
  // wrapper and reported `tokens-at-most` as unmetered.
  usage?: () => [number, number];

  constructor(inner: Transport) {
    this.inner = inner;
    this.name = inner.name;
    if (typeof inner.usage === "function") {
      this.usage = () => inner.usage!();
    }
  }

  lattice(): Record<string, string> {
    return this.inner.lattice();
  }

  async modelCall(
    system: string,
    history: Array<Record<string, unknown>>,
    toolDefs: Array<Record<string, unknown>>,
  ): Promise<[string, ToolCall[]]> {
    this.told.push(system);
    this.offered.push(toolDefs.map((t) => String(t.name)));
    return this.inner.modelCall(system, history, toolDefs);
  }
}

const transport = new Watching(new VercelAITransport(script));
const result = await run(spec, transport, userInput, tools);

process.stdout.write(
  JSON.stringify({
    trace: result.steps.map((s) => ({
      index: s.index,
      text: s.text,
      tools: s.tools.map((c) => ({ name: c.name, args: c.args })),
      results: s.results,
    })),
    output: result.output,
    halted: result.halted,
    // Which ceiling ended it, if one did. Reported so the Python suite can
    // check that both ports stop for the same reason and say the same thing —
    // agreeing about every step and then ending on different rules would be
    // agreeing about nothing that matters.
    stoppedBy: result.stoppedBy && {
      limit: result.stoppedBy.ceiling.field,
      ceiling: result.stoppedBy.ceiling.limit,
      at: result.stoppedBy.at,
      action: result.stoppedBy.action,
      // The UNIT and the SENTENCE. `limits.ts`' own comment says the sentence is
      // *"the compared contract"* — and neither was projected here, so it could
      // not be compared. That is how `unit: "USD"` survived on a cap written
      // `500 JPY`: the figure was checked, the noun beside it was invisible.
      unit: result.stoppedBy.ceiling.unit,
      sentence: sentence(result.stoppedBy),
    },
    unmetered: result.unmetered,
    // What a person would be shown had this port a person to ask. Beside
    // `output` and not inside it — `output` is compared byte-for-byte.
    waitingWords: result.waitingWords ?? null,
    // Authored lines this port reads and does not carry out. `unmetered` says
    // nobody could count something; this says the line is understood and this
    // runtime does not do it — and it did not exist here at all, so a spec
    // carrying `interceptors:` ran with none of them and said nothing.
    unenforced: result.unenforced,
    // The stage path, and what each stage was handed (G1). Outside `trace` on
    // purpose — the trace is what seven transports are held to byte-for-byte —
    // but reported, because a loop document that changed nothing about the run
    // would otherwise be indistinguishable from one that changed everything.
    phases: result.phases,
    told: transport.told,
    offered: transport.offered,
    lattice: transport.lattice(),
  }),
);
