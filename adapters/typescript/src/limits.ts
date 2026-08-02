// The termination algebra, ported to TypeScript.
//
// A deliberate second reading of the same specification, for the same reason
// the loop itself is ported: if the two ports disagree about when a run stops,
// that is an ambiguity in PACT rather than a bug in one language. The ceilings
// are read from the AUTHOR'S OWN field names — `steps-at-most`,
// `tool-calls-at-most` — not from a pre-digested payload, so this port has to
// understand `30s` and `0.05 USD` exactly as the other one does.
//
// Eve, which runs on this runtime, has none of it: no step limit, no turn
// limit, no wall-clock limit and no spend cap, and `stopWhen: isStepCount(1)`
// is the only stop condition in the package.

export type Action =
  | "stop-and-say-so"
  | "ask-a-person"
  | "answer-with-what-it-has";

export type Ceiling = {
  // Exactly what the author typed. Reports quote this, never an internal name.
  field: string;
  reads: "steps" | "toolCalls" | "seconds" | "money" | "tokens";
  limit: number;
  unit: string;
  halted: string;
};

export type Reached = { ceiling: Ceiling; at: number; action: Action };

export type Meter = {
  started: number;
  carried: number;
  steps: number;
  toolCalls: number;
  tokens: number;
  money: number;
};

export type Limits = {
  toolCallsAtMost: number | null;
  wallClockS: number | null;
  wallClockField: string;
  costPerRequestUnder: number | null;
  // Which currency the spend cap was written in. Kept beside the amount for the
  // reason `limits.py` gives: the two come off one authored line, and letting
  // them arrive from different places is how the report came to name `USD` for a
  // cap written in `JPY`.
  costCurrency: string;
  tokensAtMost: number | null;
  whenItRunsOut: Action;
};

export function newMeter(now: number): Meter {
  return { started: now, carried: 0, steps: 0, toolCalls: 0, tokens: 0, money: 0 };
}

export function reading(m: Meter, reads: Ceiling["reads"], now: number): number {
  return reads === "seconds" ? m.carried + (now - m.started) : (m[reads] as number);
}

export function stepCeiling(limit: number): Ceiling {
  return { field: "steps-at-most", reads: "steps", limit, unit: "steps", halted: "step-limit" };
}

// In a FIXED order, so two runs of the same trace name the same ceiling. An
// explanation that changes between identical runs is one nobody can act on.
export function ceilings(l: Limits, stepsAtMost: number | null = null): Ceiling[] {
  const rows: Ceiling[] = [];
  if (stepsAtMost !== null) rows.push(stepCeiling(stepsAtMost));
  if (l.toolCallsAtMost !== null)
    rows.push({
      field: "tool-calls-at-most", reads: "toolCalls", limit: l.toolCallsAtMost,
      unit: "tool calls", halted: "tool-call-limit",
    });
  if (l.wallClockS !== null)
    rows.push({
      field: l.wallClockField, reads: "seconds", limit: l.wallClockS,
      unit: "seconds", halted: "time-limit",
    });
  if (l.costPerRequestUnder !== null)
    rows.push({
      field: "cost-per-request-under", reads: "money", limit: l.costPerRequestUnder,
      // The author's currency, not this file's favourite one — word for word the
      // comment on the line this mirrors in `limits.py`.
      unit: l.costCurrency, halted: "cost-limit",
    });
  if (l.tokensAtMost !== null)
    rows.push({
      field: "tokens-at-most", reads: "tokens", limit: l.tokensAtMost,
      unit: "tokens", halted: "token-limit",
    });
  return rows;
}

export function reached(
  l: Limits,
  m: Meter,
  now: number,
  stepsAtMost: number | null = null,
): Reached | null {
  for (const c of ceilings(l, stepsAtMost)) {
    const at = reading(m, c.reads, now);
    if (at >= c.limit) return { ceiling: c, at, action: l.whenItRunsOut };
  }
  return null;
}

/** Ceilings that cannot be enforced against this transport.
 *
 *  **Two separate questions**, matching `Limits.unmeterable` in the Python port,
 *  which took the same shape after running them together cost an author a ceiling
 *  they had written:
 *
 *  * `countsTokens` — does this transport say how many tokens a call carried?
 *  * `pricesMoney` — does the catalogue publish a price for the bound model? A
 *    locally-served row may publish a window and no `cost:` block, which is
 *    exactly what a workspace on an air-gapped box writes.
 *
 *  This port asked ONE, so a model with a known window and no price lost
 *  `tokens-at-most` as a side effect — contradicting that field's own help, which
 *  promises it is *"the only ceiling that still bites when there is no price
 *  list"*. One argument here and two there also means the two ports report
 *  different `unmetered` lists for one document, which is what the portability
 *  claim is about.
 *
 *  `pricesMoney` omitted means "the same as `countsTokens`" — what a caller that
 *  only knows one thing about a transport is honestly saying. */
export function unmeterable(
  l: Limits,
  countsTokens: boolean,
  pricesMoney: boolean | null = null,
): string[] {
  const priced = pricesMoney === null ? countsTokens : pricesMoney;
  return ceilings(l)
    .filter(
      (c) =>
        (c.reads === "tokens" && !countsTokens) || (c.reads === "money" && !priced),
    )
    .map((c) => c.field);
}

// What a person is told. Word for word what the Python port says, because two
// ports that stop at the same moment and explain it differently have still
// diverged for whoever reads the report.
export function sentence(r: Reached): string {
  // The unit is APPENDED rather than interpolated, word for word the reason
  // `Reached.which` gives in `limits.py`: a money row whose currency nobody wrote
  // has no noun to print, and `"(0.06 of 0.05 )"` would be a stray space where a
  // currency should be. This mattered the moment `unit` stopped being the
  // hardcoded `"USD"` it used to be.
  let figures = `${round(r.at)} of ${round(r.ceiling.limit)}`;
  if (r.ceiling.unit) figures = `${figures} ${r.ceiling.unit}`;
  const what = `\`${r.ceiling.field}\` (${figures})`;
  if (r.action === "ask-a-person")
    return `Waiting for a person: this run reached the limit you set with ${what}.`;
  if (r.action === "answer-with-what-it-has")
    return `This run reached the limit you set with ${what}, so it answered with what it had rather than finishing the work.`;
  return `Stopped before finishing: this run reached the limit you set with ${what}.`;
}

// Python writes `f"{v:.4g}"`. This is that, digit for digit, because the
// sentence above is the compared contract: measured over ten values, five of
// them came out differently — `2.914e-05` against `0.00002914`, `1234` against
// `1235`, `1e-07` against `1e-7`, `1.235e+05` against `123500`, and `1e21`
// printed in full against `1e+21`. The sub-millisecond one is the ordinary
// case: every wall-clock ceiling reports elapsed seconds.
function round(v: number): string {
  if (!Number.isFinite(v)) return String(v);
  // `String(1e21)` is `"1e+21"`; Python's `str(int(v))` writes it out.
  if (Number.isInteger(v)) return BigInt(v).toString();
  const P = 4;
  const [mantissa, exponent] = significant(v, P).split("e");
  const exp = Number(exponent);
  // C's `%g` switches to exponential below 1e-4 and at or above 10^precision.
  if (exp < -4 || exp >= P) {
    const sign = exp < 0 ? "-" : "+";
    return `${strip(mantissa)}e${sign}${String(Math.abs(exp)).padStart(2, "0")}`;
  }
  return strip(Number(`${mantissa}e${exponent}`).toFixed(Math.max(0, P - 1 - exp)));
}

// `v` to `p` significant digits, in exponential form, rounding a HALF to the
// even digit the way C does. JavaScript rounds a half away from zero, so
// `1234.5` came out `1235` here and `1234` in Python.
function significant(v: number, p: number): string {
  const wider = v.toExponential(p); // p + 1 significant digits
  const [mant, exp] = wider.split("e");
  if (Number(wider) === v && mant.endsWith("5")) {
    const digits = mant.replace("-", "").replace(".", "");
    if (Number(digits[p - 1]) % 2 === 0) {
      const kept = digits.slice(0, p);
      const head = p > 1 ? `${kept[0]}.${kept.slice(1)}` : kept;
      return `${v < 0 ? "-" : ""}${head}e${exp}`;
    }
  }
  return v.toExponential(p - 1);
}

function strip(s: string): string {
  return s.includes(".") ? s.replace(/0+$/, "").replace(/\.$/, "") : s;
}

//: Every key `limitsFrom` and `stepsAtMost` actually read. The rest of a
//: `limits:` block arriving here is DROPPED, and until this list existed it was
//: dropped in silence — `feel`, `first-reply-within`, `per-word-under`,
//: `measured-at` and `asks` all vanished with nothing said, while the
//: architecture's own §7.28 accounted for them under `slo.*`. They do not arrive
//: under `slo:`: `pact show` nests them inside `limits:`, so that branch was dead
//: against every real document and the row read as covered.
export const LIMITS_FIELDS = [
  "steps-at-most",
  "tool-calls-at-most",
  "runs-for-at-most",
  "finishes-within",
  "cost-per-request-under",
  "tokens-at-most",
  "when-it-runs-out",
] as const;

/** Keys in an authored `limits:` block this port does not read. */
export function limitsNotRead(m: Record<string, unknown>): string[] {
  const reads = LIMITS_FIELDS as readonly string[];
  return Object.keys(m).filter((k) => !reads.includes(k)).sort();
}

// ------------------------------------------------------------- from the file

export function limitsFrom(m: Record<string, unknown>): Limits {
  // `finishes-within` is a promise to whoever waits. With no `runs-for-at-most`
  // written it is also the stop, so a promise is never left unenforced.
  let wall = seconds(m["runs-for-at-most"]);
  let wallField = "runs-for-at-most";
  if (wall === null) {
    wall = seconds(m["finishes-within"]);
    wallField = "finishes-within";
  }
  const [cap, currency] = spend(m["cost-per-request-under"]);
  return {
    toolCallsAtMost: whole(m["tool-calls-at-most"]),
    wallClockS: wall,
    wallClockField: wallField,
    costPerRequestUnder: cap,
    costCurrency: currency,
    tokensAtMost: whole(m["tokens-at-most"]),
    whenItRunsOut: action(m["when-it-runs-out"]),
  };
}

export function stepsAtMost(m: Record<string, unknown>, fallback: number): number {
  const written = whole(m["steps-at-most"]);
  return written === null ? fallback : written;
}

function action(raw: unknown): Action {
  const s = typeof raw === "string" ? raw.trim().toLowerCase() : "";
  if (s === "ask-a-person" || s === "answer-with-what-it-has") return s;
  // The safe one: the only action that neither invents an answer nor spends
  // anything further. Reached only for a file `pact check` has already refused.
  return "stop-and-say-so";
}

function whole(raw: unknown): number | null {
  if (raw === null || raw === undefined || typeof raw === "boolean") return null;
  const n = Number.parseInt(String(raw).trim(), 10);
  return Number.isNaN(n) ? null : n;
}

const UNITS: Record<string, number> = {
  ms: 0.001, millisecond: 0.001, milliseconds: 0.001,
  s: 1, sec: 1, secs: 1, second: 1, seconds: 1, "": 1,
  m: 60, min: 60, mins: 60, minute: 60, minutes: 60,
  h: 3600, hr: 3600, hrs: 3600, hour: 3600, hours: 3600,
  d: 86400, day: 86400, days: 86400,
};

// `30s`, `500ms`, `1m30s`, `2 minutes`, or a bare number of seconds. Compound
// spellings are handled rather than approximated: reading `1m30s` as one second
// would be a ceiling ninety times tighter than the one written.
export function seconds(raw: unknown): number | null {
  if (raw === null || raw === undefined || typeof raw === "boolean") return null;
  if (typeof raw === "number") return raw;
  const text = String(raw).trim().toLowerCase();
  if (!text) return null;
  let total = 0, num = "", unit = "", any = false;
  for (const ch of text + " ") {
    if ((ch >= "0" && ch <= "9") || ch === ".") {
      if (unit) {
        const part = piece(num, unit);
        if (part === null) return null;
        total += part; num = ""; unit = ""; any = true;
      }
      num += ch;
    } else if (/[a-z]/.test(ch)) {
      unit += ch;
    } else if (/\s/.test(ch)) {
      continue;
    } else {
      return null;
    }
  }
  if (num) {
    const part = piece(num, unit);
    if (part === null) return null;
    total += part; any = true;
  } else if (unit) {
    return null;
  }
  return any ? total : null;
}

function piece(num: string, unit: string): number | null {
  const mult = UNITS[unit];
  if (mult === undefined) return null;
  const v = Number.parseFloat(num);
  return Number.isNaN(v) ? null : v * mult;
}

// `0.05 USD`, `USD 0.05`, `$0.05`. The currency is never converted.
export function money(raw: unknown): number | null {
  return spend(raw)[0];
}

/** `[amount, currency]` — the pair, because they come off ONE authored line.
 *
 *  `money()` returned the amount and threw the currency away, and `ceilings()`
 *  printed a hardcoded `"USD"`, so `cost-per-request-under: 500 JPY` loaded, ran
 *  and reported *"(501 of 500 USD)"* — a currency the author never wrote. The
 *  Python port fixed this and says so in `limits.py`: *"reporting a spend cap in
 *  the wrong currency is a correctness bug and FR-1.4.5 says it normatively"*.
 *  This port kept the bug, and the sentence IS the contract, so the two ports
 *  disagreed about what the same file means.
 *
 *  Empty currency for a bare number: nothing was written, so there is no noun to
 *  print, and inventing one is the whole defect. */
export function spend(raw: unknown): [number | null, string] {
  if (raw === null || raw === undefined || typeof raw === "boolean") return [null, ""];
  if (typeof raw === "number") return [raw, ""];
  let amount: number | null = null;
  let currency = "";
  for (const part of String(raw).replace(/\$/g, " ").split(/\s+/)) {
    if (/^[0-9.]+$/.test(part)) {
      const v = Number.parseFloat(part);
      if (!Number.isNaN(v) && amount === null) amount = v;
    } else if (part && amount !== null && !currency) {
      currency = part;
    }
  }
  return [amount, amount === null ? "" : currency];
}
