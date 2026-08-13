// Emits the conformance trace for the Vercel AI transport as JSON on stdout,
// so the Python suite can compare it byte-for-byte against the reference.
// Cross-runtime agreement is the strongest form of the portability claim.

import {
  run, undeclaredIn, AGENT_SPEC_FIELDS, type AgentSpec, type ToolCall, type Transport,
} from "./harness.ts";
import { ceilings, ceilingsNothingCanReach, limitsFrom, sentence } from "./limits.ts";
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
  // And the third optional field, forwarded for the same reason and after the
  // same failure. `VercelAITransport` declares `pricesMoney = false`, and a
  // wrapper that dropped it put the harness back on its default — so a spend cap
  // driven through THIS file reported itself enforced against a money meter that
  // never left zero, while a bare `VercelAITransport` reported it as unmetered.
  // Measured both ways: with the field forwarded, `run-trace.ts` on a
  // `0.05 USD` cap answers `"unmetered":["cost-per-request-under"]`; without it,
  // `"unmetered":[]`. The Python cross-port suite reaches this port through no
  // other door, so anything this constructor forgets is invisible to every test
  // in the repository that compares the two ports.
  pricesMoney?: boolean;

  constructor(inner: Transport) {
    this.inner = inner;
    this.name = inner.name;
    if (typeof inner.usage === "function") {
      this.usage = () => inner.usage!();
    }
    if (typeof inner.pricesMoney === "boolean") {
      this.pricesMoney = inner.pricesMoney;
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
// argv[6] — `prices-money` makes this run declare that its calls CAN be priced.
//
// Not a convenience. `VercelAITransport` declares `pricesMoney = false` honestly
// (B6: it drives a scripted model bound to no catalogue row), and the
// consequence is that EVERY money ceiling this port runs lands on `unmetered`
// for that reason, whatever the figure was. So the shipped array cannot tell a
// cap nothing can reach from a cap nothing here can price, and the only field
// that could was `ceilingsNothingCanReach` — a projection computed in this file, for
// the Python suite, read by nothing an author sees. Measured: with the
// `!nothingCanReach(...)` guard deleted from `ceilings()` in `limits.ts` and this
// port driven on its own `NaN USD` fixture, every key of the output below was
// byte-identical to the unmutated run except `ceilingsNothingCanReach` — `unmetered`,
// `halted`, `stoppedBy`, `output`, `unenforced` all unchanged. A guard held only
// by the test driver's own projection is a guard held by nothing.
//
// With this flag the money finding has to come from the figure, because the
// transport reason is switched off: the same mutation then empties the SHIPPED
// `unmetered` array, and that is what
// `test_a_spend_cap_nothing_can_reach_holds_nothing_and_says_so.py` asserts on.
// It is a declaration about the transport and nothing else — `usage()` is
// untouched, so the money meter still never moves and no ceiling can be reached
// by it.
if (process.argv[6] === "prices-money") transport.pricesMoney = true;
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
    // The two reasons a ceiling lands on `unmetered`, told apart — a trace
    // field, not a second channel of the report.
    //
    // `harness.ts` merges them on purpose ("not a channel of its own":
    // *"cannot promise"* is exactly what is true of both) and that is right for
    // an author. It is wrong for the Python suite, which has to hold each
    // separately: a cap NO SPEND CAN REACH (`NaN USD`, `inf USD` — `ceilings()`
    // refuses to build the row) and a cap NOTHING HERE CAN PRICE
    // (`pricesMoney = false` — this port drives a scripted model bound to no
    // catalogue row) are different findings about different lines. Once
    // `VercelAITransport` declared the second honestly, every money ceiling was
    // on `unmetered` for that reason and the control assertions in
    // `test_a_spend_cap_nothing_can_reach_holds_nothing_and_says_so.py` — "a
    // real figure is not named as an unusable one" — could no longer see which
    // of the two had fired. Projected rather than inferred, because inferring it
    // from the transport is how a test comes to assert its own stand-in.
    ceilingsNothingCanReach: ceilingsNothingCanReach(limitsFrom(spec.limits ?? {})),
    // And the rows that WERE built, which is the other half of the same claim
    // and the half nothing projected.
    //
    // `ceilingsNothingCanReach` derives its answer off `ceilings()` precisely so
    // that the row refused and the name reported cannot come apart — and that
    // coupling was argued in a comment in `limits.ts` and held by nothing.
    // Measured: re-derive that function off the `nothingCanReach` predicate
    // instead (which reads as a simplification and removes a Set allocation)
    // AND delete a `ceilings()` guard, and the entire holding suite stays green
    // while this port builds a row `reached` can never satisfy. Either edit
    // ALONE is caught; the pair was not, because every assertion in the suite
    // read only the projection both edits agree about.
    //
    // With the built rows here, the assertion is on the thing the guard is
    // about — `cost-per-request-under` is absent from THIS list, however
    // `ceilingsNothingCanReach` happens to be written — so the second port's
    // guard stops depending on a comment.
    ceilingRows: ceilings(limitsFrom(spec.limits ?? {})).map((c) => c.field),
    // What a person would be shown had this port a person to ask. Beside
    // `output` and not inside it — `output` is compared byte-for-byte.
    waitingWords: result.waitingWords ?? null,
    // Authored lines this port reads and does not carry out. `unmetered` says
    // nobody could count something; this says the line is understood and this
    // runtime does not do it — and it did not exist here at all, so a spec
    // carrying `interceptors:` ran with none of them and said nothing.
    unenforced: result.unenforced,
    // Sets of documents this run never looked anything up in. A channel of its
    // own and not more of `unenforced`, because the two go to different people:
    // an unenforced line is one the author wrote and can take out, and there is
    // nothing to take out here — the document is right and this runtime cannot
    // read documents. Projected so the Python suite can hold the two ports to
    // one sentence about one absence; without it, a corpus with no `must-cite:`
    // ran here, answered out of the model's own memory, and said nothing.
    unretrieved: result.unretrieved,
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
