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
// There is deliberately NO `nothingCanReach` field here. It was one, set by
// `limitsFrom`, and a stored answer to a question about a value is a stored
// answer that outlives the value: measured, `{...limitsFrom({"cost-per-request-
// under": "NaN USD"}), costPerRequestUnder: 0.1}` came out carrying
// `nothingCanReach: ["cost-per-request-under"]` beside a perfectly good ten-pence
// ceiling. `ceilingsNothingCanReach` below derives it from the figure instead, and
// `ceilings()` refuses to build the row, so the answer cannot be stale and
// cannot be bypassed by building the object some other way. `limits.py` reaches
// the same place through `Limits.__post_init__`, which is the hook a frozen
// dataclass has and an object literal does not.

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
  // EVERY row is guarded, and for a round two of them were not. `at >= limit` is
  // one comparison, and `NaN` and `Infinity` defeat it identically whatever it
  // is counting — so a guard that names some of the fields is a guard on the
  // FIELD when the defect is a property of the FIGURE. Measured on this port
  // with only the money and wall-clock rows guarded:
  //
  //     {...limitsFrom({}), tokensAtMost: Infinity}
  //       -> rows=["tokens-at-most"]      reached@1e9=null  caps=[]
  //     {...limitsFrom({}), toolCallsAtMost: Infinity}
  //       -> rows=["tool-calls-at-most"]  reached@1e9=null  caps=[]
  //
  // a live row nothing can ever be at or above, reported nowhere, in a port
  // whose reference twin names both on `unmetered`. `whole()` refuses these
  // where an author writes one, so an object literal is the only door — which
  // is the door this whole guard exists for.
  if (l.toolCallsAtMost !== null && !nothingCanReach(l.toolCallsAtMost))
    rows.push({
      field: "tool-calls-at-most", reads: "toolCalls", limit: l.toolCallsAtMost,
      unit: "tool calls", halted: "tool-call-limit",
    });
  // Measured before this one, on a plain spread:
  //
  //     {...limitsFrom({}), wallClockS: Infinity} -> rows=['finishes-within']
  //                                                  ceilingsNothingCanReach=[]
  //
  // The Python port names it on `unmetered` (`Limits.__post_init__` walks every
  // ceiling field it carries), so without this the two ports answer differently
  // for one object — and `runs-for-at-most` / `finishes-within` are keys §7.28
  // list A says the byte-identical-trace claim COVERS.
  if (l.wallClockS !== null && !nothingCanReach(l.wallClockS))
    rows.push({
      field: l.wallClockField, reads: "seconds", limit: l.wallClockS,
      unit: "seconds", halted: "time-limit",
    });
  // A figure no spend can ever be at or above is not a loose ceiling — it is no
  // ceiling at all, so no row is built for it, WHOEVER built this object. That
  // is the port's equivalent of `Limits.__post_init__` dropping the amount:
  // there is no construction hook for an object literal, so the guard lives at
  // the read every ceiling in this file goes through. `reached`, `unmeterable`
  // and `harness.run` all come through here, so none of them can see a row the
  // comparison below could never satisfy.
  if (l.costPerRequestUnder !== null && !nothingCanReach(l.costPerRequestUnder))
    rows.push({
      field: "cost-per-request-under", reads: "money", limit: l.costPerRequestUnder,
      // The author's currency, not this file's favourite one — word for word the
      // comment on the line this mirrors in `limits.py`.
      unit: l.costCurrency, halted: "cost-limit",
    });
  if (l.tokensAtMost !== null && !nothingCanReach(l.tokensAtMost))
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
//
// The claim is now measured rather than asserted, because it was FALSE for
// ordinary money for a round while this comment said it was true. `significant`
// below decided a half by asking whether the p+1-digit rendering round-TRIPPED
// to the same double, which is not the same question as whether the double sits
// on the midpoint, and the two answers part on figures an author writes:
// `10.005 USD` and `0.12345 USD` both load through `pact check` (measured, rc=0)
// and came out `10.01` / `0.1235` in Python against `10` / `0.1234` here.
// Re-measured after the repair, through this exported `sentence()` against
// Python's `_round` — the two shipped formatters, not a re-spelling of either:
// 54 000 five-significant-digit decimals ending in `5` (mantissas 1000‥9999,
// exponents -5‥0 — the shape of an authored cap, and the only shape that
// reaches the tie at all) gave **8 439 divergences before and 0 after**, and
// 4 000 uniform random doubles gave 0 both times. That last figure is why a
// random fuzz never found this and why the fixtures naming the amounts are
// where the holding has to be: `ROUNDING` in
// `test_both_ports_read_every_way_a_spend_cap_is_written.py`.
function round(v: number): string {
  // C's `%g` — and so Python's `f"{v:.4g}"` — writes the three non-finite values
  // as `inf`, `-inf` and `nan`. `String(v)` writes `Infinity`, `-Infinity` and
  // `NaN`, and that was a live divergence rather than a hypothetical one: a cap
  // of `-inf USD` is reached by EVERY run, because `spent > -Infinity` is true of
  // any spend at all, so the two ports read the same cap identically and then
  // reported it as `(0 of -inf USD)` here and `(0 of -Infinity USD)` there.
  // (`inf` and `nan` never reach the sentence — nothing is greater than either —
  // but they are written out too, because which of the three can fire is a fact
  // about the comparison in `ceilings()` and not about this function.)
  if (Number.isNaN(v)) return "nan";
  if (!Number.isFinite(v)) return v > 0 ? "inf" : "-inf";
  // `String(1e21)` is `"1e+21"`; Python's `str(int(v))` writes it out.
  if (Number.isInteger(v)) return BigInt(v).toString();
  const P = 4;
  const sign = v < 0 ? "-" : "";
  const { digits, exp } = significant(Math.abs(v), P);
  // C's `%g` switches to exponential below 1e-4 and at or above 10^precision.
  if (exp < -4 || exp >= P) {
    const mant = digits.length > 1 ? `${digits[0]}.${digits.slice(1)}` : digits;
    return `${sign}${strip(mant)}e${exp < 0 ? "-" : "+"}${String(Math.abs(exp)).padStart(2, "0")}`;
  }
  // Fixed notation, written straight out of the digits rather than by feeding
  // them back through `Number(...).toFixed(...)`. That round trip was a SECOND
  // rounding of an already-rounded figure, and a second rounding is a second
  // chance to disagree with the port this function exists to match.
  const whole = exp >= 0 ? digits.slice(0, exp + 1) : "0";
  const frac = exp >= 0 ? digits.slice(exp + 1) : "0".repeat(-exp - 1) + digits;
  return `${sign}${strip(frac ? `${whole}.${frac}` : whole)}`;
}

/** `a` (finite, positive) to `p` significant decimal digits, ties to EVEN.
 *
 *  Returned as the digits and the decimal exponent, so the caller places the
 *  point: `{digits: "1235", exp: -1}` is `0.1235`.
 *
 *  **Rounded off the double's EXACT value, in `BigInt`, and this is the whole
 *  point of the function.** JavaScript rounds a half away from zero where C —
 *  and so Python's `f"{v:.4g}"` — rounds it to the even digit, so `1234.5` came
 *  out `1235` here and `1234` there. The first repair asked
 *  `Number(a.toExponential(p)) === a && mant.endsWith("5")`, which is a
 *  ROUND-TRIP test and not a midpoint test, and the two are different questions.
 *  `10.005` is the double `10.0050000000000007815970093361102044582366943359375`
 *  — measured, `Decimal(10.005)` — which is strictly ABOVE the decimal midpoint,
 *  so C rounds it UP to `10.01` with the tie rule never consulted. But
 *  `(10.005).toExponential(4)` is `1.0005e+1` and that string parses back to the
 *  same double, so the round-trip test believed it had a tie, applied
 *  half-to-even, and rounded DOWN to `10.00`. A round trip says the p+1-digit
 *  rendering identifies the double; it says nothing about where in its interval
 *  the double sits. Measured through the two shipped formatters, that parted the
 *  ports on 8 439 of 54 000 five-significant-digit amounts — 15.6% — and
 *  `cost-per-request-under: 10.005 USD` passes `pact check` (rc=0).
 *
 *  A double is a dyadic rational, so its exact value is a terminating decimal
 *  and `num / den` below is that value with nothing thrown away. A tie is then
 *  `2 * remainder === den` — an exact equality on integers, which is the only
 *  form of "exactly a half" that is not an approximation of one. */
function significant(a: number, p: number): { digits: string; exp: number } {
  const view = new DataView(new ArrayBuffer(8));
  view.setFloat64(0, a);
  const bits = view.getBigUint64(0);
  const rawExp = Number((bits >> 52n) & 0x7ffn);
  const fraction = bits & 0xf_ffff_ffff_ffffn;
  // Subnormals carry no implicit leading 1 and share the smallest exponent.
  const mantissa = rawExp === 0 ? fraction : fraction | (1n << 52n);
  const e2 = (rawExp === 0 ? 1 : rawExp) - 1075;
  let num = e2 >= 0 ? mantissa << BigInt(e2) : mantissa;
  let den = e2 >= 0 ? 1n : 1n << BigInt(-e2);

  // The decimal exponent: the `n` with `10^n <= a < 10^(n+1)`. `Math.log10` is
  // the guess and the two loops are the proof, because a floating-point log of
  // a power of ten is exactly the place it is allowed to be off by one.
  let exp = Math.floor(Math.log10(a));
  const atLeast = (k: number): boolean =>
    k >= 0 ? num >= den * 10n ** BigInt(k) : num * 10n ** BigInt(-k) >= den;
  while (!atLeast(exp)) exp--;
  while (atLeast(exp + 1)) exp++;

  const shift = p - 1 - exp;
  if (shift >= 0) num *= 10n ** BigInt(shift);
  else den *= 10n ** BigInt(-shift);
  let q = num / den;
  const twiceRemainder = (num - q * den) * 2n;
  if (twiceRemainder > den || (twiceRemainder === den && q % 2n === 1n)) q += 1n;
  // `9.9995` rounds to `10.00`, which is one digit too many and one power of
  // ten further up.
  if (q === 10n ** BigInt(p)) {
    q /= 10n;
    exp += 1;
  }
  return { digits: q.toString(), exp };
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
  // The figure the author wrote is passed straight through, INCLUDING one no
  // spend can ever be at or above. That is not the guard going missing — the
  // guard moved to `ceilings()` and `ceilingsNothingCanReach`, which is where every
  // reader of this value already goes. Guarding it here instead made the answer
  // a property of THIS FUNCTION rather than of the cap, and the cap has other
  // ways of coming into existence; see the note on the `Limits` type for the
  // spread that carried a stale `nothingCanReach` beside a real ceiling.
  //
  // Measured before either guard, on the authored route:
  //
  //     "NaN USD" -> costPerRequestUnder=NaN currency="USD"
  //         reached at 1000                    -> null
  //         reached at 1.7976931348623157e+308 -> null
  //         unmeterable(countsTokens=true, pricesMoney=true) -> []
  //
  // That is a spec BUILT IN CODE — the one route `pact check` never sees, since
  // `Schema::check_floor` refuses `NaN USD` and `inf USD` in a file — running
  // fully metered under no cap at all, in both ports.
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

/** The ceilings on THIS `Limits` that no reading can ever be at or above.
 *
 *  By FIELD NAME, and never as a ceiling: `ceilings()` has already refused to
 *  build the row, because a row `reached` can never satisfy is not a loose
 *  ceiling — it is no ceiling at all. What replaces it is a NAME on
 *  `RunResult.unmetered`, whose own wording is *"cannot promise"* rather than
 *  *"did not enforce"*.
 *
 *  ALL FOUR ceilings, and it was called `ceilingsNothingCanReach` while it answered
 *  about two. `tokensAtMost` and `toolCallsAtMost` are compared by the same
 *  `at >= limit`, and were measured building live rows nothing could satisfy
 *  with this function silent — the guard was on a hand-kept list of FIELDS when
 *  the defect is a property of the FIGURE. `ceilings()` above carries that
 *  measurement, and `Limits._CEILING_FIELDS` in the reference port is the same
 *  table.
 *
 *  Not a channel of its own, and not `never_reached`: that field is a fact
 *  about the BINDING, built out of the bound model's catalogue price, and it
 *  exists in the Python port only — so carrying this there would mean inventing
 *  a third channel here to receive it. `limits.py` makes the same choice and
 *  gives the same reasons, at `Limits.__post_init__` and `_nothing_can_reach`.
 *
 *  DERIVED on every call rather than stored on the object, for the reason the
 *  `Limits` type gives: a stored answer survives the value it was an answer
 *  about.
 *
 *  And derived off `ceilings()` rather than off `nothingCanReach` a second
 *  time, so the row that is NOT built and the name that IS reported cannot come
 *  apart. Asking the predicate twice would make it possible to drop a guard in
 *  `ceilings()` — putting a row nothing can satisfy back into the comparison —
 *  while this function went on cheerfully reporting the field. **That coupling
 *  used to be argued in this comment and held by nothing**, which is the same
 *  category of claim as the docstrings that said a record could not be handed
 *  in: re-deriving here off the predicate AND deleting the `ceilings()` money
 *  guard left the whole suite green with the port building a row no spend could
 *  satisfy. It is held now, by `run-trace.ts` projecting the BUILT ROWS beside
 *  this list and the Python suite asserting on both — an assertion that bites
 *  the `ceilings()` guard however this function is written. */
export function ceilingsNothingCanReach(l: Limits): string[] {
  const built = new Set(ceilings(l).map((c) => c.field));
  const named: string[] = [];
  // In `ceilings()` order, so the names arrive in the sequence the rows would
  // have — tool calls, then the clock, then money, then tokens — and the two
  // ports do not report one document in two orders.
  if (l.toolCallsAtMost !== null && !built.has("tool-calls-at-most"))
    named.push("tool-calls-at-most");
  if (l.wallClockS !== null && !built.has(l.wallClockField)) named.push(l.wallClockField);
  if (l.costPerRequestUnder !== null && !built.has("cost-per-request-under"))
    named.push("cost-per-request-under");
  if (l.tokensAtMost !== null && !built.has("tokens-at-most"))
    named.push("tokens-at-most");
  return named;
}

/** Is this a money cap NO spend can ever be at or above?
 *
 *  Every ceiling is compared as `spent >= limit`, so there are exactly two such
 *  figures and they fail for different arithmetic reasons:
 *
 *  * `NaN` — every comparison against a NaN is false, so the row is skipped at
 *    every spend there is, including `Infinity`;
 *  * `Infinity` — the comparison works perfectly and nothing can be larger.
 *
 *  **`-Infinity` is deliberately not one of them, and this is a test rather
 *  than `!Number.isFinite`.** `spent >= -Infinity` is true of every spend, so a
 *  cap of `-inf USD` fires on the FIRST step and stops the run loudly at
 *  `(0 of -inf USD)`. That is a wrong ceiling, not an absent one, and
 *  `test_both_ports_read_every_way_a_spend_cap_is_written.py` pins it as *"the
 *  one non-finite cap a run can reach"* and compares that sentence across the
 *  two ports byte for byte — it is the only value that exercises the
 *  non-finite arm of `round()` above. All three are refused where an author
 *  writes one: `Schema::check_floor` puts a floor under money. */
export function nothingCanReach(cap: number): boolean {
  return Number.isNaN(cap) || cap === Infinity;
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
  const chars = text + " ";
  for (let i = 0; i < chars.length; i += 1) {
    const ch = chars[i];
    if ((ch >= "0" && ch <= "9") || ch === ".") {
      if (unit) {
        const part = piece(num, unit);
        if (part === null) return null;
        total += part; num = ""; unit = ""; any = true;
      }
      num += ch;
    } else if (exponentAt(chars, i, num, unit)) {
      // `1e6s` — the `e` belongs to the figure and not to a unit called `e`.
      // The Rust coercer accepts this spelling, so a reader that refused it
      // would hold no ceiling at all on a line `pact check` had passed.
      num += "e";
      if (chars[i + 1] === "+" || chars[i + 1] === "-") { i += 1; num += chars[i]; }
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

// Whether `chars[i]` is the `e` of an exponent rather than a unit's first
// letter: a figure has been written, no unit has started, and digits (with an
// optional sign) follow. No unit here begins with `e`, so `2 seconds` keeps
// starting its unit at the `s`.
function exponentAt(chars: string, i: number, num: string, unit: string): boolean {
  if (chars[i] !== "e" || !num || unit) return false;
  let j = i + 1;
  if (chars[j] === "+" || chars[j] === "-") j += 1;
  return chars[j] !== undefined && chars[j] >= "0" && chars[j] <= "9";
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
 *  **And then it was fixed for ONE spelling of the cap out of the six that
 *  reach it.** The reader below used to take the currency positionally, so it
 *  read `0.05 USD` and nothing else: `USD 0.05` and `$0.05` — the other two
 *  spellings `coerce::money` accepts and `schema.yaml`'s own help offers — both
 *  arrived with no noun to print, `0.05 usd` was reported in `usd` where the
 *  loader stores `USD`, and `0.05 DOLLARS` was reported in a currency no
 *  document can carry. It survived because the money figure was never SENT in a
 *  divergent spelling: every money fixture in `test_termination.py` is written
 *  `<number> <CUR>`, the one order both readers already agreed about, and
 *  `test_portability.py` sends no `limits:` block at all. Held now by
 *  `test_both_ports_read_every_way_a_spend_cap_is_written.py`, which sends each
 *  spelling through both ports and compares the sentence byte for byte.
 *
 *  Empty currency for a bare number: nothing was written, so there is no noun to
 *  print, and inventing one is the whole defect.
 *
 *  **What this reads is `coerce::money`'s language, with two named widenings.**
 *  The comment on `FIGURE` below used to claim the reader took *"exactly what
 *  the gate lets through"*; measured, it took a good deal more and a little
 *  less, and the two were argued in opposite directions thirty lines apart. The
 *  rule is now one rule: the same separators, the same number grammar, at most
 *  two tokens, and `$` as a PREFIX. The two widenings both cost the currency
 *  and never invent one — a bare number is a cap with no noun, and a second
 *  token that is not three ASCII letters is dropped rather than refusing the
 *  line. `limits.py` states the same rule in the same words, because a rule
 *  stated twice differently is how this file and that one came to disagree. */
export function spend(raw: unknown): [number | null, string] {
  if (raw === null || raw === undefined || typeof raw === "boolean") return [null, ""];
  if (typeof raw === "number") return [raw, ""];
  let amount: number | null = null;
  let currency = "";
  // Python's bare `.split()` drops empty fields; splitting on a regex keeps
  // them, and an empty token is neither an amount nor a currency.
  const tokens = String(raw).split(SEPARATOR).filter((t) => t);
  // `$` is a PREFIX and the rest of the line must be one whole number —
  // `s.strip_prefix('$')` then `rest.trim().parse::<f64>().ok()?`, mirrored.
  // A global `.replace(/\$/g, " USD ")` was here instead, and it invented a
  // currency out of a dollar sign ANYWHERE in the string: measured through this
  // function, `0.05$` and `5 U$D` both came back `[…, "USD"]` and `$0.05 USD`
  // came back `[0.05, "USD"]`, while `pact check` gives `schema/wrong-type` for
  // all three. That is the invention this pair exists to have stopped, arriving
  // through the mechanism chosen to stop it. Reading the prefix off the first
  // token is enough, because the first token starts at the first character
  // `trim()` would have kept.
  if (tokens.length > 0 && tokens[0].startsWith("$")) {
    const rest = [tokens[0].slice(1), ...tokens.slice(1)].filter((t) => t);
    if (rest.length !== 1) return [null, ""];
    const only = figure(rest[0]);
    return only === null ? [null, ""] : [only, "USD"];
  }
  // Two tokens at most: `coerce::money` returns `None` on a third, and a reader
  // that dropped the surplus in silence enforced a ceiling the gate had already
  // refused — `5 USD 7` was five dollars in both ports, with nothing said.
  if (tokens.length === 0 || tokens.length > 2) return [null, ""];
  for (const part of tokens) {
    if (amount === null) {
      const v = figure(part);
      if (v !== null) {
        amount = v;
        continue;
      }
    }
    // Three ASCII letters is what the validator accepts as a currency
    // (`coerce::money` refuses anything else), so it is what is looked for
    // here — word for word the rule `limits.py` states. Reading it LEXICALLY
    // rather than positionally is what lets one reader take `0.05 USD`,
    // `USD 0.05` and `$0.05` without three branches; requiring the amount
    // first meant a currency written before its number could never be taken,
    // so `500 JPY` reported in JPY and `JPY 500` reported in nothing. The
    // upper-casing is `coerce::money`'s too: it stores `12 eur` as `EUR`, and a
    // report that echoed `eur` would disagree with the loader about one line.
    // `0.05 DOLLARS` yields no currency in BOTH ports for the same reason —
    // naming a currency no document can carry is the invention this pair
    // exists to have stopped, one word further on.
    if (!currency && /^[a-z]{3}$/i.test(part)) currency = part.toUpperCase();
  }
  return [amount, amount === null ? "" : currency];
}

// What separates the amount from the currency, spelled out rather than left as
// `\s+`, because the three readers do not agree on what a space is and JS has
// the ODD ONE OUT in both directions. This is `char::is_whitespace` — the
// Unicode `White_Space` property, which is what `split_whitespace` in
// `coerce::money` uses — and `limits.py` spells out the same set beside this
// one instead of calling `str.split()`. The three differences that had to be
// settled, each measured through the shipped binary on a real workspace:
//
//   * `U+0085` NEL, which JS `\s` does not split on and the other two do, so
//     `5<NEL>USD` was a cap the validator loads, a cap in Python, and NO CAP AT
//     ALL here. `cost-per-request-under: 0.05<NEL>USD` gives `pact check` rc=0
//     — the least believable row in the set is one an author can write.
//   * `U+001C`–`U+001F`, which Python's `str.split()` splits on and
//     `char::is_whitespace` does not. They were taken here for a round *"so the
//     two readers agree rather than agreeing only where a document can reach"*
//     — the opposite of the rule `FIGURE` below was arguing thirty lines
//     further on, in the same file, about the same trade-off. There is one rule
//     now and it is the gate's: `0.05<US>USD` gives rc=1 `schema/wrong-type`,
//     so no document can carry one and neither reader takes one.
//   * `U+FEFF`, which `\s` splits on and neither of the other two does. It was
//     the loose direction: `5<BOM>USD` is one token — and so not a number — to
//     `parse::<f64>()`, and was two tokens here. `0.05<BOM>USD` is rc=1 too.
const SEPARATOR =
  /[\t\n\v\f\r\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+/;

// A whole token that `coerce::money`'s `parse::<f64>()` reads as a number, and
// nothing else.
//
// `/^[0-9.]+$/` was neither that nor Python's `float()`: it refused `-5` and
// `1e2`, which both of the others take, so a cap written either way loaded as no
// cap at all here while binding on the other side. `Number.parseFloat` is not
// the fix — it takes the `0.05` out of `0.05USD`, a token `float()` refuses
// outright, which would load a typo as five pence of nothing. `Number()` is not
// either: it reads `0x10` as sixteen, and neither of the other two reads hex.
//
// The grammar is deliberately RUST'S and not Python's. `float()` takes two
// things `parse::<f64>()` does not:
//
//   * digit-group underscores — `1_0` is ten, `1_000.5` is a thousand and a
//     half;
//   * any Unicode decimal digit — Arabic-Indic `١٢` and fullwidth `１２` are
//     both twelve.
//
// `coerce::money` refuses every one of them — measured: `1_0 USD`, `０.05 USD`
// and `٠.05 USD` are all `pact check` rc=1 `schema/wrong-type` — so no CHECKED
// document can carry one, and taking them here would be inventing a cap out of
// a string the validator has already refused.
//
// **That argument only became a defence once `limits.py` made the same
// parting.** For a round it did not, and "no checked document can carry one"
// was not a defence available on the route this file is compared over: the
// fixtures in `test_both_ports_read_every_way_a_spend_cap_is_written.py` are
// specs built in code, and `run-trace.ts` takes a payload straight off argv
// without a gate anywhere. Measured through that door, `0_0 USD`, `０ USD` and
// `٠ USD` each halted the reference port on `cost-limit` and ran the second one
// to `final` — a ceiling in one port and no ceiling in the other, which the
// holding file's own message calls worse than a wrong noun. `float()` is gone
// from `money()` there; the pattern below is character for character the
// pattern in `limits.py`, `[0-9]` rather than `\d` in both because Python's
// `\d` is every Unicode decimal digit and that is one of the two widenings.
const FIGURE = /^[+-]?(?:(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:e[+-]?[0-9]+)?|inf(?:inity)?|nan)$/i;

function figure(token: string): number | null {
  if (!FIGURE.test(token)) return null;
  // `Number("inf")` is `NaN` where `float("inf")` is infinity, so the three
  // word forms — which both of the other readers accept — are spelled out.
  const word = token.replace(/^[+-]/, "").toLowerCase();
  if (word === "nan") return NaN;
  if (word === "inf" || word === "infinity") {
    return token.startsWith("-") ? -Infinity : Infinity;
  }
  return Number(token);
}
