// Vercel AI SDK as a transport (harness lowering).
//
// The seam is a `LanguageModelV2` provider — the interface every real provider
// implements. `generateText` is called with `stopWhen` disabled so the SDK
// performs exactly one model call and its own step loop never engages. That is
// the same trick Eve uses (`stopWhen: isStepCount(1)`), arrived at independently
// by the strongest prior art in this space.

import { generateText, stepCountIs } from "ai";
import type { ToolCall, Transport } from "./harness.ts";

export type Script = { turns: { text: string; toolCalls?: ToolCall[] }[] };

function scriptedModel(script: Script, historyRef: { value: any[] }) {
  return {
    specificationVersion: "v2" as const,
    provider: "pact",
    modelId: "scripted",
    supportedUrls: {},
    async doGenerate() {
      const turned = historyRef.value.filter(
        (m: any) => m.role === "assistant",
      ).length;
      const turn = script.turns[Math.min(turned, script.turns.length - 1)];
      const content: any[] = [];
      if (turn.text) content.push({ type: "text", text: turn.text });
      for (const [i, c] of (turn.toolCalls ?? []).entries()) {
        content.push({
          type: "tool-call",
          toolCallId: `c${i}`,
          toolName: c.name,
          input: JSON.stringify(c.args ?? {}),
        });
      }
      return {
        content,
        finishReason: (turn.toolCalls?.length ? "tool-calls" : "stop") as any,
        // Counted, not zeroed. `harness.run` only meters when `usage()` exists,
        // and it did not exist on this transport at all — so `tokens-at-most`
        // and `cost-per-request-under` were unenforceable on the seventh target
        // while README said "SLOs are enforced during the run" without
        // qualification. Measured, same spec and script:
        // PydanticAI/LangGraph `halted='token-limit'`, Node `halted='step-limit'`
        // with both ceilings on `unmetered`.
        usage: {
          inputTokens: countTokens(historyRef.value),
          outputTokens: countTokens(content),
          totalTokens: countTokens(historyRef.value) + countTokens(content),
        },
        warnings: [],
      };
    },
    async doStream() {
      throw new Error("PACT does not stream through this seam");
    },
  };
}

//: The same rough count `pact_adapters.transports._metering` uses on the Python
//: side: four characters to a token. A scripted seam has no tokeniser and a real
//: provider returns its own numbers, so this is what makes a scripted run
//: METERABLE rather than accurate — which is what a ceiling needs.
function countTokens(v: unknown): number {
  return Math.ceil(JSON.stringify(v ?? "").length / 4);
}

export class VercelAITransport implements Transport {
  name = "vercel-ai";
  //: Whether ANYTHING can put a price on what a call here carried. Nothing can:
  //: this drives a scripted model bound to no catalogue row, so the money half
  //: of `usage()` below is a placeholder and not a bill.
  //:
  //: Declared rather than left to the default, and the default is `false` for
  //: the reason B6 records: reading the money answer off the TOKEN answer told
  //: an author their spend cap was enforced against a meter that never left
  //: zero. This port shipped the `pricesMoney` MECHANISM and no transport that
  //: assigned it, so the false branch was unreachable and
  //: `cost-per-request-under` could never appear on `unmetered` for any document
  //: this port ran. Measured through `run-trace.ts` with a `0.05 USD` cap:
  //: `"unmetered":[]`.
  pricesMoney = false;
  private historyRef = { value: [] as any[] };
  private counted: [number, number] = [0, 0];

  private script: Script;

  constructor(script: Script) {
    this.script = script;
  }

  lattice(): Record<string, string> {
    return {
      model_call: "native",
      tool_calls: "native",
      text_with_tool_calls: "native",
      parallel_tool_calls: "native",
      streaming: "emulated",
      durable_resume: "unsupported",
      // Whether a tool's `connect:` line — the reach kind that names a SYSTEM
      // in `resources:` — becomes a call that leaves this process.
      //
      // `unsupported`, and it is the sharpest thing this column records. Every
      // harness-driven PYTHON target says `emulated`, because PACT's own MCP
      // client (`pact_adapters/mcp/`) reaches the server through the tool-impl
      // seam the loop already has. That client is Python and this port is Node,
      // so there is nothing here for a `connect:` line to become: the tool
      // arrives at the model as a name and reaches the system never. The AI SDK
      // does ship an MCP client of its own, and binding it would mean binding
      // the SDK's loop, which PACT owns.
      //
      // This is the second thing this port is smaller by, beside the ten
      // governance keys on `unenforced` — declared here rather than discovered
      // by whoever ships a refund desk on Node. The key must be present at all
      // or the two ports cannot be compared (P-2), which is what
      // `test_all_seven_targets_publish_the_same_lattice_features` holds.
      connected_tools: "unsupported",
    };
  }

  async modelCall(
    system: string,
    history: Array<Record<string, unknown>>,
    _tools: Array<Record<string, unknown>>,
  ): Promise<[string, ToolCall[]]> {
    this.historyRef.value = history as any[];
    const messages = history.flatMap((m: any) => {
      if (m.role === "user") return [{ role: "user", content: m.content }];
      if (m.role === "assistant")
        return [{ role: "assistant", content: m.content || "." }];
      return [{ role: "user", content: `[tool ${m.name}] ${m.content}` }];
    });

    const result = await generateText({
      model: scriptedModel(this.script, this.historyRef) as any,
      system: system || undefined,
      messages: messages as any,
      // Disable the SDK's own loop: PACT owns it.
      stopWhen: stepCountIs(1),
    });

    const u: any = result.usage ?? {};
    this.counted = [
      Number(u.totalTokens ?? (u.inputTokens ?? 0) + (u.outputTokens ?? 0)) || 0,
      0,
    ];

    const calls: ToolCall[] = (result.toolCalls ?? []).map((c: any) => ({
      name: c.toolName,
      args: c.input ?? {},
    }));
    return [result.text ?? "", calls];
  }

  //: What the last call carried. The TOKEN half is real — counted off the
  //: SDK's own usage block — and the money half is a placeholder, which is why
  //: `pricesMoney` above is `false` and not why it could be omitted.
  //:
  //: The comment here used to say the `0` was "the same honesty every Python
  //: transport keeps". It was the opposite of it:
  //: `pact_adapters.transports._metering` states the rule as *"An unpriced row
  //: yields `None`, never zero"*, and a `0` that reaches a money meter is
  //: exactly the *"spend cap that can never be reached"* it opens by forbidding.
  //: The tuple type is `[number, number]` in both ports' wire shape, so the
  //: honesty is carried by `pricesMoney` rather than by a third value — and
  //: `unmeterable` then keeps `tokens-at-most` and drops only the money cap,
  //: which is the whole reason it asks two questions rather than one.
  usage(): [number, number] {
    return this.counted;
  }
}
