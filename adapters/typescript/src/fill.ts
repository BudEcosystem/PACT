// An agent's words, filled for one run, in this process: `pact_loader::fill`
// through its WebAssembly build (`crates/pact-fill-wasm`), so a runtime written
// in TypeScript sends a model the same words `pact fill` prints and
// `pact_adapters.holes.fill` returns — one engine, the one `pact check` reads
// templates with, rather than a third renderer that drifts from the other two.
//
// `tests/conformance/fill.json` holds all three ports to the same answers
// (`test_words_are_filled_as_the_shared_cases_say.py`, through `read-fill.mts`).
//
// The module imports nothing and keeps nothing between calls, so one `Filler`
// serves any number of runs; a host that fills the same words often keys its
// own cache by the version's digest and the inputs.

/** One fill: the fields of a case in `tests/conformance/fill.json`. */
export interface FillRequest {
  /** The authored words, as the document holds them. */
  text: string;
  /** The workspace's `template-language:`; anything but `jinja` is `holes`. */
  language: string;
  /** The run's inputs, keyed by the names the agent declares (`brand-voice`). */
  "run-inputs"?: Record<string, unknown>;
  /** What the agent remembers at the start of the run, the same way. */
  remembers?: Record<string, unknown>;
}

/**
 * The words, or why there are none: `unfilled` for a value the run did not
 * give (the braces never reach a model), `not-rendered` for a template
 * `pact check` refuses.
 */
export type FillAnswer =
  | { said: string }
  | { refused: "unfilled" | "not-rendered"; message: string };

interface FillExports {
  memory: WebAssembly.Memory;
  pact_alloc(len: number): number;
  pact_free(at: number, len: number): void;
  pact_fill(at: number, len: number): bigint;
}

/** The WebAssembly renderer, loaded once. */
export class Filler {
  readonly #exports: FillExports;
  readonly #encoder = new TextEncoder();
  readonly #decoder = new TextDecoder();

  private constructor(exports: FillExports) {
    this.#exports = exports;
  }

  /**
   * Load the module from its bytes (`pact_fill_wasm.wasm`) or an already
   * compiled `WebAssembly.Module`.
   */
  static async load(module: BufferSource | WebAssembly.Module): Promise<Filler> {
    const compiled = module instanceof WebAssembly.Module ? module : await WebAssembly.compile(module);
    const instance = await WebAssembly.instantiate(compiled, {});
    const exports = instance.exports as unknown as FillExports;
    for (const name of ["memory", "pact_alloc", "pact_free", "pact_fill"] as const) {
      if (!(name in exports)) throw new Error(`this is not pact_fill_wasm: it exports no \`${name}\``);
    }
    return new Filler(exports);
  }

  /** `request.text` filled for one run. */
  fill(request: FillRequest): FillAnswer {
    const bytes = this.#encoder.encode(JSON.stringify(request));
    const { memory, pact_alloc, pact_free, pact_fill } = this.#exports;
    const at = pact_alloc(bytes.length);
    new Uint8Array(memory.buffer, at, bytes.length).set(bytes);
    // `pact_fill` frees the request and hands back `address << 32 | length`.
    const answer = pact_fill(at, bytes.length);
    const answerAt = Number(answer >> 32n);
    const answerLen = Number(answer & 0xffff_ffffn);
    const said = this.#decoder.decode(new Uint8Array(memory.buffer, answerAt, answerLen));
    pact_free(answerAt, answerLen);
    return JSON.parse(said) as FillAnswer;
  }
}
