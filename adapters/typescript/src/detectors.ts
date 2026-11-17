// Detectors in TypeScript: the five recognisers every rule can name and the
// ones a workspace declares under `detectors:`, as `detectors.declared_in` and
// `interceptors.RECOGNISES` read them, compiled to JavaScript regular
// expressions that find what Python's `re` finds.
//
// A declared pattern is written in the detector dialect (spec/schema.yaml,
// `detectors`; `crates/pact-loader/src/dialect.rs`): the syntax both Python's
// `re` and the Rust `regex` crate read, with Python's meaning, so one document
// detects the same values on every runtime. `pact check` refuses a pattern
// outside it (`loader/looks-like-outside-the-dialect`), and
// `translateDetectorPattern` refuses the same patterns with the same reasons,
// among them a pattern that can match an empty value, whose matches Python's
// `re` and JavaScript would step past differently.
// The built-in patterns are the reference's own and are translated with
// lookahead allowed, since the card number's dotted form needs it.
//
// Each detector's `examples:` are held to its own pattern when it is compiled,
// so a pattern that misses the example its author wrote stops the run before
// it starts.
//
// `tests/conformance/detectors.json` holds this port and Python's `re` to the
// same matches (`test_every_port_reads_one_detector_dialect.py`, through
// `read-detectors.mts`).
/** One entry of a workspace's `detectors:`, as `pact show` prints it. */
export interface Detector {
  /** The patterns the thing looks like: one line, or several, each in the detector dialect. */
  "looks-like"?: string | readonly string[];
  /** Values the patterns must find. */
  examples?: string | readonly string[];
  /** What the thing is, for a person. */
  description?: string;
}

/**
 * The five built-in recognisers, by name, exactly as the reference adapter writes them
 * (`interceptors.RECOGNISES`, Python syntax).
 */
export const PACT_BUILT_IN_DETECTOR_PATTERNS: Readonly<Record<string, string>> = Object.freeze({
  "card number": String.raw`\b(?:\d[ \u00a0\u2007\u2009\u202f-]*?){12,}\d\b|\b(?=(?:\d\.?){13,}\b)\d+(?:\.\d+){2,}\b`,
  "bank account": String.raw`(?i:\b[A-Z]{2}\d{2}(?:[ ][A-Z0-9]{4}){2,7}(?:[ ][A-Z0-9]{1,3})?\b)|(?i:\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b)|\b\d{2}[- ]\d{2}[- ]\d{2}\b|\b\d{8,17}\b`,
  "email address": String.raw`\b[\w.+-]+@[\w-]+\.[\w.-]+\b`,
  "phone number": String.raw`\+?\d(?:[ ()-]*\d){9,}`,
  "social security number": String.raw`\b(?:\d{3}-\d{2}-\d{4}|\d{3} \d{2} \d{4}|\d{9})\b`,
});

/**
 * Why a detector cannot be compiled:
 * - `outside-dialect`: a `looks-like:` line writes syntax outside the detector dialect, or is not a pattern.
 * - `misses-example`: the detector's pattern does not find one of its own `examples:`.
 */
export type PactDetectorErrorCode = "outside-dialect" | "misses-example";

/** A detector that cannot be compiled; callers switch on {@link PactDetectorError.code}. */
export class PactDetectorError extends Error {
  /** Which failure this is. */
  readonly code: PactDetectorErrorCode;
  /** The detector's name as the workspace writes it. */
  readonly detector: string;

  /**
   * @param code - which failure this is.
   * @param detector - the detector's name.
   * @param message - the sentence naming the detector, what is wrong and what to change.
   */
  constructor(code: PactDetectorErrorCode, detector: string, message: string) {
    super(message);
    this.name = "PactDetectorError";
    this.code = code;
    this.detector = detector;
  }
}

/** A translated pattern: the JavaScript source (compiled with the `u` flag), or why it is outside the dialect. */
export type PactDetectorTranslation =
  | { readonly ok: true; readonly source: string; }
  | { readonly ok: false; readonly reason: string; readonly at: number; };

/** Python's whitespace (`str.isspace()`), the meaning of `\s`, as class members. */
const SPACE_MEMBERS = String.raw`\t-\r\u{1c}-\u{20}\u{85}\u{a0}\u{1680}\u{2000}-\u{200a}\u{2028}\u{2029}\u{202f}\u{205f}\u{3000}`;
/** Python's word characters (`str.isalnum()` or `_`), the meaning of `\w`, as class members. */
const WORD_MEMBERS = String.raw`\p{L}\p{N}_`;
/** Python's decimal digits, the meaning of `\d`, as class members. */
const DIGIT_MEMBERS = String.raw`\p{Nd}`;
const WORD = `[${WORD_MEMBERS}]`;
const ANY = String.raw`[\s\S]`;

/** The class escapes, each with its members and whether it is the complement of them. */
const CLASS_ESCAPES: Readonly<Record<string, { readonly members: string; readonly negated: boolean; }>> = {
  d: { members: DIGIT_MEMBERS, negated: false },
  D: { members: DIGIT_MEMBERS, negated: true },
  w: { members: WORD_MEMBERS, negated: false },
  W: { members: WORD_MEMBERS, negated: true },
  s: { members: SPACE_MEMBERS, negated: false },
  S: { members: SPACE_MEMBERS, negated: true },
};

/** The single-character escapes both readers share, by letter. */
const CHARACTER_ESCAPES: Readonly<Record<string, number>> = { n: 0x0a, t: 0x09, r: 0x0d, f: 0x0c, v: 0x0b, a: 0x07 };

/** Python's `re` refuses a repetition count from this one up (`sre_constants.MAXREPEAT`). */
const PYTHON_MAX_REPEAT = 4_294_967_295;

/** Characters JavaScript's `u` mode reads as syntax outside a class. */
const SYNTAX = new Set("^$\\.*+?()[]{}|/");
/** Characters escaped inside a class. */
const CLASS_SYNTAX = new Set("\\]-[^");

/** Flags a group may set. */
interface Flags {
  readonly i: boolean;
  readonly m: boolean;
  readonly s: boolean;
}

class OutsideDialect extends Error {
  readonly reason: string;
  readonly at: number;

  constructor(reason: string, at: number) {
    super(reason);
    this.reason = reason;
    this.at = at;
  }
}

function hexOf(code: number): string {
  return `\\u{${code.toString(16)}}`;
}

/** One code point as a literal outside a class. */
function literal(code: number): string {
  const char = String.fromCodePoint(code);
  if (SYNTAX.has(char)) return `\\${char}`;
  return code < 0x20 || code > 0x7e ? hexOf(code) : char;
}

/** One code point as a class member. */
function member(code: number): string {
  const char = String.fromCodePoint(code);
  if (CLASS_SYNTAX.has(char)) return `\\${char}`;
  return code < 0x20 || code > 0x7e ? hexOf(code) : char;
}

/**
 * The pairs Python's `re` treats as one letter under `(?i:...)` beyond lower-casing (`sre_compile._equivalences`):
 * dotless i, long s, micro sign, the Greek symbol variants, final sigma and two ligatures.
 */
const PYTHON_CASE_EQUIVALENCES: readonly (readonly number[])[] = [
  [0x69, 0x131], [0x73, 0x17f], [0xb5, 0x3bc], [0x345, 0x3b9, 0x1fbe], [0x390, 0x1fd3], [0x3b0, 0x1fe3], [0x3b2, 0x3d0],
  [0x3b5, 0x3f5], [0x3b8, 0x3d1], [0x3ba, 0x3f0], [0x3c0, 0x3d6], [0x3c1, 0x3f1], [0x3c2, 0x3c3], [0x3c6, 0x3d5],
  [0x1e61, 0x1e9b], [0xfb05, 0xfb06],
];

/** The highest code point with a lower-case form; every cased letter of Unicode sits below it. */
const LAST_CASED = 0x1e943;

/** One code point's lower-case form, when that is one code point; otherwise the code point itself. */
function lowerOf(code: number): number {
  const lower = String.fromCodePoint(code).toLowerCase();
  const first = lower.codePointAt(0) as number;
  return lower.length === (first > 0xffff ? 2 : 1) ? first : code;
}

let byLower: ReadonlyMap<number, readonly number[]> | undefined;

/** Every code point by its lower-case form, built on first use. */
function codesByLower(): ReadonlyMap<number, readonly number[]> {
  if (byLower !== undefined) return byLower;
  const map = new Map<number, number[]>();
  for (let code = 0; code <= LAST_CASED; code += 1) {
    const lower = lowerOf(code);
    if (lower === code) continue;
    const list = map.get(lower) ?? [lower];
    list.push(code);
    map.set(lower, list);
  }
  byLower = map;
  return map;
}

/**
 * The code points one character is matched as under `(?i:...)`, as Python's `re` matches them: every code point
 * with the same lower-case form, and the members of its equivalence pair.
 */
function caseForms(code: number): number[] {
  const forms = new Set<number>([code]);
  const lowers = new Set<number>([lowerOf(code)]);
  for (const group of PYTHON_CASE_EQUIVALENCES) {
    if (group.includes(lowerOf(code))) for (const member of group) lowers.add(member);
  }
  for (const lower of lowers) {
    forms.add(lower);
    for (const form of codesByLower().get(lower) ?? []) forms.add(form);
  }
  return [...forms].sort((a, b) => a - b);
}

/** One parsed class item. */
type ClassItem =
  | { readonly kind: "char"; readonly code: number; }
  | { readonly kind: "range"; readonly from: number; readonly to: number; }
  | { readonly kind: "escape"; readonly members: string; readonly negated: boolean; };

/** Translated JavaScript, and whether it can match an empty value. */
interface Piece {
  readonly source: string;
  readonly empty: boolean;
}

/** One translated atom: whether a quantifier may follow it, and whether it can match an empty value. */
interface Atom extends Piece {
  readonly repeatable: boolean;
}

/** A reader of one pattern, emitting JavaScript as it goes. */
class Translator {
  private at = 0;
  private readonly names = new Set<string>();

  private readonly pattern: string;
  private readonly lookaround: boolean;

  constructor(pattern: string, lookaround: boolean) {
    this.pattern = pattern;
    this.lookaround = lookaround;
  }

  translate(): string {
    const whole = this.alternation({ i: false, m: false, s: false });
    if (this.at < this.pattern.length) this.refuse("a `)` that closes no group; write `\\)` for the character");
    if (whole.empty) this.refuse("a pattern that can match an empty value, so it finds something in every text and runtimes disagree on what; make every branch need at least one character", 0);
    return whole.source;
  }

  private refuse(reason: string, at = this.at): never {
    throw new OutsideDialect(reason, at);
  }

  private peek(offset = 0): string | undefined {
    return this.pattern[this.at + offset];
  }

  private startsWith(text: string): boolean {
    return this.pattern.startsWith(text, this.at);
  }

  /** Alternatives: empty when one of them can match an empty value. */
  private alternation(flags: Flags): Piece {
    const branches = [this.sequence(flags)];
    while (this.peek() === "|") {
      this.at += 1;
      branches.push(this.sequence(flags));
    }
    return { source: branches.map((branch) => branch.source).join("|"), empty: branches.some((branch) => branch.empty) };
  }

  /** Atoms in a row: empty when all of them can match an empty value. */
  private sequence(flags: Flags): Piece {
    let source = "";
    let empty = true;
    for (;;) {
      const char = this.peek();
      if (char === undefined || char === "|" || char === ")") return { source, empty };
      const start = this.at;
      const atom = this.atom(flags);
      if (atom.repeatable) {
        const quantifier = this.quantifier();
        source += atom.source + quantifier.text;
        empty &&= atom.empty || quantifier.none;
      } else {
        source += atom.source;
        empty &&= atom.empty;
        if (this.quantifierAhead()) this.refuse("a quantifier after something that is no character or group", start);
      }
    }
  }

  private quantifierAhead(): boolean {
    const char = this.peek();
    return char === "*" || char === "+" || char === "?" || (char === "{" && this.braceQuantifier() !== undefined);
  }

  /** A `{n}`, `{n,}` or `{n,m}` at the cursor: its text, or undefined when the brace is no quantifier. */
  private braceQuantifier(): string | undefined {
    const match = /^\{(\d*)(,?)(\d*)\}/.exec(this.pattern.slice(this.at));
    if (match === null) return undefined;
    const [text, low = "", comma = "", high = ""] = match;
    if (low === "" && comma === "") return undefined;
    if (low === "") this.refuse("a `{,m}` quantifier with no lower bound, which the Rust regex crate does not read; write `{0,m}`");
    if (high !== "" && Number(high) < Number(low)) this.refuse(`a quantifier \`${text}\` whose upper bound is below its lower bound`);
    if (Number(low) >= PYTHON_MAX_REPEAT || (high !== "" && Number(high) >= PYTHON_MAX_REPEAT)) this.refuse(`a quantifier \`${text}\` above the largest repetition count Python's re reads`);
    return text;
  }

  /** The quantifier at the cursor, if any, and whether it allows no repeat. */
  private quantifier(): { readonly text: string; readonly none: boolean } {
    let out = "";
    let none: boolean;
    const char = this.peek();
    if (char === "*" || char === "+" || char === "?") {
      out = char;
      none = char !== "+";
      this.at += 1;
    } else if (char === "{") {
      const brace = this.braceQuantifier();
      if (brace === undefined) return { text: "", none: false };
      out = brace;
      none = Number(/^\{(\d*)/.exec(brace)?.[1]) === 0;
      this.at += brace.length;
    } else {
      return { text: "", none: false };
    }
    if (this.peek() === "?") {
      out += "?";
      this.at += 1;
    } else if (this.peek() === "+") {
      this.refuse("a possessive quantifier, which the Rust regex crate does not read");
    }
    if (this.quantifierAhead()) this.refuse("two quantifiers in a row; put the first in a group `(?:...)`");
    return { text: out, none };
  }

  private atom(flags: Flags): Atom {
    const char = this.peek() as string;
    if (char === "(") return this.group(flags);
    if (char === "[") return { source: this.characterClass(flags), repeatable: true, empty: false };
    if (char === "*" || char === "+" || char === "?") this.refuse("a quantifier with nothing before it to repeat");
    if (char === "{") {
      if (this.braceQuantifier() !== undefined) this.refuse("a quantifier with nothing before it to repeat");
      this.refuse("a `{` that is no quantifier; write `\\{` for the character");
    }
    this.at += 1;
    switch (char) {
      case ".": return { source: flags.s ? ANY : String.raw`[^\n]`, repeatable: true, empty: false };
      case "^": return { source: flags.m ? String.raw`(?<![^\n])` : String.raw`(?<![\s\S])`, repeatable: false, empty: true };
      case "$": return { source: flags.m ? String.raw`(?=\n|(?![\s\S]))` : String.raw`(?=\n?(?![\s\S]))`, repeatable: false, empty: true };
      case "\\": return this.escape(flags);
      default: {
        const code = this.pattern.codePointAt(this.at - 1) as number;
        if (code > 0xffff) this.at += 1;
        return { source: this.character(code, flags), repeatable: true, empty: false };
      }
    }
  }

  private character(code: number, flags: Flags): string {
    if (!flags.i) return literal(code);
    const forms = caseForms(code);
    return forms.length === 1 ? literal(code) : `[${forms.map(member).join("")}]`;
  }

  private group(flags: Flags): Atom {
    const start = this.at;
    if (this.startsWith("(?P<")) {
      const match = /^\(\?P<([A-Za-z_][A-Za-z0-9_]*)>/.exec(this.pattern.slice(this.at));
      if (match === null) this.refuse("a group name that is not a letter or `_` followed by letters, digits or `_`");
      const name = match[1] as string;
      if (this.names.has(name)) this.refuse(`the group name \`${name}\` written twice`);
      this.names.add(name);
      this.at += match[0].length;
      const inner = this.closed(flags, start);
      return { source: `(?<${name}>${inner.source})`, repeatable: true, empty: inner.empty };
    }
    for (const opener of ["(?=", "(?!", "(?<=", "(?<!"]) {
      if (!this.startsWith(opener)) continue;
      if (!this.lookaround) this.refuse("a lookaround `" + opener + "...)`, which the Rust regex crate does not read");
      this.at += opener.length;
      return { source: `${opener}${this.closed(flags, start).source})`, repeatable: false, empty: true };
    }
    if (this.startsWith("(?P=") || this.startsWith("(?P>")) this.refuse("a back-reference to a named group, which the Rust regex crate does not read");
    if (this.startsWith("(?#")) this.refuse("a comment group, which the Rust regex crate does not read");
    if (this.startsWith("(?>")) this.refuse("an atomic group, which the Rust regex crate does not read");
    if (this.startsWith("(?(")) this.refuse("a conditional group, which neither the Rust regex crate nor the PACT dialect reads");
    if (this.startsWith("(?<")) this.refuse("a named group written `(?<name>...)`, which Python's re refuses; write `(?P<name>...)`");
    if (this.startsWith("(?:")) {
      this.at += 3;
      const inner = this.closed(flags, start);
      return { source: `(?:${inner.source})`, repeatable: true, empty: inner.empty };
    }
    if (this.startsWith("(?")) {
      const match = /^\(\?([a-zA-Z-]*)([:)])/.exec(this.pattern.slice(this.at));
      if (match === null) this.refuse("a `(?` that opens no group the dialect reads");
      const [, letters = "", end = ""] = match;
      if (end === ")") this.refuse("a flag for the whole pattern, which the reference adapter cannot read inside a detector; write `(?i:...)` around the part it applies to");
      if (letters.includes("-")) this.refuse("a group that turns a flag off, which the PACT dialect does not read");
      for (const letter of letters) {
        if (letter !== "i" && letter !== "m" && letter !== "s") this.refuse(`the flag \`${letter}\`, which the PACT dialect does not read; it reads \`i\`, \`m\` and \`s\``);
      }
      this.at += match[0].length;
      const scoped = { i: flags.i || letters.includes("i"), m: flags.m || letters.includes("m"), s: flags.s || letters.includes("s") };
      const inner = this.closed(scoped, start);
      return { source: `(?:${inner.source})`, repeatable: true, empty: inner.empty };
    }
    this.at += 1;
    const inner = this.closed(flags, start);
    return { source: `(${inner.source})`, repeatable: true, empty: inner.empty };
  }

  private closed(flags: Flags, start: number): Piece {
    const inner = this.alternation(flags);
    if (this.peek() !== ")") this.refuse("a group that is never closed", start);
    this.at += 1;
    return inner;
  }

  /** The code point a character escape names, or undefined when the escape is no character. */
  private escapedCode(letter: string): number | undefined {
    const fixed = CHARACTER_ESCAPES[letter];
    if (fixed !== undefined) {
      this.at += 1;
      return fixed;
    }
    const digits = letter === "x" ? 2 : letter === "u" ? 4 : letter === "U" ? 8 : 0;
    if (digits > 0) {
      const hex = this.pattern.slice(this.at + 1, this.at + 1 + digits);
      if (!new RegExp(`^[0-9A-Fa-f]{${String(digits)}}$`).test(hex)) this.refuse(`\`\\${letter}\` followed by other than ${String(digits)} hexadecimal digits`);
      const code = Number.parseInt(hex, 16);
      if (code > 0x10ffff) this.refuse(`\`\\${letter}${hex}\`, which is no character`);
      this.at += 1 + digits;
      return code;
    }
    if (/^[\x21-\x2f\x3a-\x40\x5b-\x60\x7b-\x7e]$/.test(letter)) {
      this.at += 1;
      return letter.codePointAt(0);
    }
    return undefined;
  }

  private refuseEscape(letter: string | undefined): never {
    if (letter === undefined) this.refuse("a `\\` that ends the pattern");
    if (/^[0-9]$/.test(letter)) this.refuse(`\`\\${letter}\`, a back-reference or an octal escape, which the Rust regex crate does not read`);
    this.refuse(`the escape \`\\${letter}\`, which Python's re and the Rust regex crate do not read alike`);
  }

  private escape(flags: Flags): Atom {
    const letter = this.peek();
    const assertion: Readonly<Record<string, string>> = {
      b: `(?:(?<=${WORD})(?!${WORD})|(?<!${WORD})(?=${WORD}))`,
      B: `(?:(?<=${WORD})(?=${WORD})|(?<!${WORD})(?!${WORD}))`,
      A: String.raw`(?<![\s\S])`,
      Z: String.raw`(?![\s\S])`,
    };
    if (letter !== undefined && Object.hasOwn(assertion, letter)) {
      this.at += 1;
      return { source: assertion[letter] as string, repeatable: false, empty: true };
    }
    const set = letter === undefined ? undefined : CLASS_ESCAPES[letter];
    if (set !== undefined) {
      this.at += 1;
      return { source: `[${set.negated ? "^" : ""}${set.members}]`, repeatable: true, empty: false };
    }
    const code = letter === undefined ? undefined : this.escapedCode(letter);
    if (code === undefined) this.refuseEscape(letter);
    return { source: this.character(code, flags), repeatable: true, empty: false };
  }

  private classItem(): ClassItem {
    const char = this.peek() as string;
    if (char === "[") this.refuse("a `[` inside a class, which the Rust regex crate reads as a nested class; write `\\[`");
    if (char === "\\") {
      this.at += 1;
      const letter = this.peek();
      const set = letter === undefined ? undefined : CLASS_ESCAPES[letter];
      if (set !== undefined) {
        this.at += 1;
        return { kind: "escape", members: set.members, negated: set.negated };
      }
      if (letter === "b") this.refuse("`\\b` inside a class, which Python reads as a backspace and the Rust regex crate refuses");
      const code = letter === undefined ? undefined : this.escapedCode(letter);
      if (code === undefined) this.refuseEscape(letter);
      return { kind: "char", code };
    }
    for (const operation of ["&&", "--", "~~"]) {
      if (this.startsWith(operation)) this.refuse(`\`${operation}\` inside a class, which the Rust regex crate reads as a set operation; escape one of the two`);
    }
    const code = this.pattern.codePointAt(this.at) as number;
    this.at += code > 0xffff ? 2 : 1;
    return { kind: "char", code };
  }

  private characterClass(flags: Flags): string {
    const start = this.at;
    this.at += 1;
    const negated = this.peek() === "^";
    if (negated) this.at += 1;
    const items: ClassItem[] = [];
    let first = true;
    for (;;) {
      const char = this.peek();
      if (char === undefined) this.refuse("a class `[` that is never closed", start);
      if (char === "]" && !first) break;
      first = false;
      if (char === "]") {
        this.at += 1;
        items.push({ kind: "char", code: 0x5d });
        continue;
      }
      const item = this.classItem();
      if (this.startsWith("--")) this.refuse("`--` inside a class, which the Rust regex crate reads as a set operation; escape one of the two");
      const dash = this.peek() === "-" && this.peek(1) !== "]" && this.peek(1) !== undefined;
      if (!dash) {
        items.push(item);
        continue;
      }
      const dashAt = this.at;
      this.at += 1;
      const end = this.classItem();
      if (item.kind !== "char" || end.kind !== "char") this.refuse("a range whose end is a class such as `\\d`", dashAt);
      if (end.code < item.code) this.refuse("a range whose end comes before its start", dashAt);
      items.push({ kind: "range", from: item.code, to: end.code });
    }
    this.at += 1;
    return this.emitClass(items, negated, flags);
  }

  private rangeMembers(from: number, to: number, ignoreCase: boolean): string[] {
    const out = [from === to ? member(from) : `${member(from)}-${member(to)}`];
    if (!ignoreCase) return out;
    if (to > 0x7f) this.refuse("a range of letters beyond ASCII inside `(?i:...)`, which the PACT dialect does not read; list the letters");
    const forms = new Set<number>();
    for (let code = from; code <= to; code += 1) {
      for (const form of caseForms(code)) if (form < from || form > to) forms.add(form);
    }
    return [...out, ...[...forms].sort((a, b) => a - b).map(member)];
  }

  private emitClass(items: readonly ClassItem[], negated: boolean, flags: Flags): string {
    const members: string[] = [];
    const complements: string[] = [];
    for (const item of items) {
      if (item.kind === "escape") {
        if (item.negated) complements.push(item.members);
        else members.push(item.members);
      } else if (item.kind === "range") {
        members.push(...this.rangeMembers(item.from, item.to, flags.i));
      } else {
        members.push(...(flags.i ? caseForms(item.code) : [item.code]).map(member));
      }
    }
    const own = members.join("");
    if (complements.length === 0) return `[${negated ? "^" : ""}${own}]`;
    if (!negated) return `(?:${[...own === "" ? [] : [`[${own}]`], ...complements.map(set => `[^${set}]`)].join("|")})`;
    const [last, ...rest] = complements as [string, ...string[]];
    return `(?:${own === "" ? "" : `(?![${own}])`}${rest.map(set => `(?=[${set}])`).join("")}[${last}])`;
  }
}

/**
 * Translate one pattern of the detector dialect to JavaScript.
 * @param pattern - the pattern in Python syntax.
 * @param options - `lookaround: true` reads lookahead and lookbehind too, as the built-in patterns need.
 * @returns the JavaScript source to compile with the `u` flag, or the reason and position the pattern is outside the
 * dialect.
 * @example
 * translateDetectorPattern("ORD-[0-9]{8}") // { ok: true, source: "ORD-[0-9]{8}" }
 * translateDetectorPattern("(?<=x)y") // { ok: false, reason: "a lookaround …", at: 0 }
 */
export function translateDetectorPattern(pattern: string, options: { readonly lookaround?: boolean; } = {}): PactDetectorTranslation {
  try {
    return { ok: true, source: new Translator(pattern, options.lookaround === true).translate() };
  } catch (error: unknown) {
    if (!(error instanceof OutsideDialect)) throw error;
    return { ok: false, reason: error.reason, at: error.at };
  }
}

function compiled(source: string): RegExp {
  return new RegExp(source, "u");
}

/** The built-in recognisers, compiled once. */
const BUILT_IN: ReadonlyMap<string, RegExp> = new Map(Object.entries(PACT_BUILT_IN_DETECTOR_PATTERNS).map(([name, pattern]) => {
  const translation = translateDetectorPattern(pattern, { lookaround: true });
  if (!translation.ok) throw new Error(`the built-in detector '${name}' is outside the dialect: ${translation.reason}`);
  return [name, compiled(translation.source)];
}));

/** The detectors one workspace can name: its declared ones, then the built-in ones. */
export interface PactDetectorSet {
  /**
   * The compiled pattern of a detector by name, compared as the reference compares it: trimmed and lower-cased,
   * a declared detector before a built-in one of the same name.
   * @param name - the name a `looks-like:` writes.
   * @returns the pattern, or undefined when nothing here knows the name.
   */
  pattern(name: string): RegExp | undefined;
  /** The names the workspace declares, trimmed and lower-cased, in written order. */
  readonly declared: readonly string[];
}

/** The set with no declared detectors: the five built-in ones. */
export const PACT_BUILT_IN_DETECTORS: PactDetectorSet = Object.freeze({
  pattern: (name: string) => BUILT_IN.get(name.trim().toLowerCase()),
  declared: Object.freeze([]),
});

function texts(value: string | readonly string[] | undefined): string[] {
  if (value === undefined) return [];
  return (Array.isArray(value) ? value : [value]).map(item => String(item));
}

/**
 * Compile a workspace's `detectors:` as `detectors.declared_in` reads them: each detector's non-blank `looks-like:`
 * lines joined into one pattern (`(?:a)|(?:b)`), held to the dialect and to its own `examples:`. A detector that
 * writes no non-blank pattern is skipped, as the reference skips it.
 * @param detectors - the workspace's `detectors:`, or undefined.
 * @returns the set that answers the declared names and the built-in ones.
 * @throws {PactDetectorError} `outside-dialect` for a line outside the dialect, `misses-example` for an example the
 * pattern does not find.
 * @example
 * const set = compileDetectors({
 *   "order reference": { description: "An order", "looks-like": ["ORD-[0-9]{8}"], examples: ["ORD-12345678"] },
 * })
 * set.pattern("Order Reference")?.test("see ORD-12345678") // true
 */
export function compileDetectors(detectors: Readonly<Record<string, Detector>> | undefined): PactDetectorSet {
  const declared = new Map<string, RegExp>();
  for (const [name, body] of Object.entries(detectors ?? {})) {
    const lines = texts(body["looks-like"]).filter(line => line.trim() !== "");
    if (lines.length === 0) continue;
    const joined = lines.map(line => `(?:${line})`).join("|");
    const translation = translateDetectorPattern(joined);
    if (!translation.ok) {
      throw new PactDetectorError("outside-dialect", name, `the detector '${name}' looks like a pattern outside the detector dialect: ${translation.reason} (at character ${String(translation.at + 1)} of \`${joined}\`). Fix its \`looks-like:\` lines.`);
    }
    // The translation is valid JavaScript for every pattern the dialect reads, so compiling it cannot fail.
    const pattern = compiled(translation.source);
    for (const example of texts(body.examples)) {
      if (!pattern.test(example)) {
        throw new PactDetectorError("misses-example", name, `the detector '${name}' does not recognise its own example '${example}', so it would let that value through. Fix its \`looks-like:\` lines, or the example.`);
      }
    }
    declared.set(name.trim().toLowerCase(), pattern);
  }
  return Object.freeze({
    pattern: (name: string) => {
      const key = name.trim().toLowerCase();
      return declared.get(key) ?? BUILT_IN.get(key);
    },
    declared: Object.freeze([...declared.keys()]),
  });
}
