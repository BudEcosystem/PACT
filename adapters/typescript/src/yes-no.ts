// One reading of a tick in a document, for this port — the twin of
// `adapters/python/src/pact_adapters/yes_no.py`, and here for the same reason.
//
// `spec/schema.yaml` has one type for a tick, `yes-no`, and one piece of code
// decides what an author may write on such a line:
// `crates/pact-schema/src/coerce.rs::yes_no`, which takes `yes`, `y`, `true`,
// `on` and `enabled`, and their five negatives, in any capitalisation. That
// function is the DOOR. A word it refuses never becomes a document; a word it
// accepts is a line the author has been told, by the checker, is fine.
//
// This port read one such line — `must-cite:` — with its own two-word list:
//
//     .filter((k) => k["must-cite"] === true || String(k["must-cite"]).trim() === "yes")
//
// Two spellings, case-sensitive, against the checker's five. Measured on
// `examples/answers-from-documents` with the authored word carried through to
// `run-trace.ts` unparsed, both ports over the same script:
//
//     must-cite: yes      PY halted=no-sources   NODE halted=no-sources
//     must-cite: enabled  PY halted=no-sources   NODE halted=final  "25 days."
//     must-cite: y        PY halted=no-sources   NODE halted=final  "25 days."
//     must-cite: on       PY halted=no-sources   NODE halted=final  "25 days."
//     must-cite: Yes      PY halted=no-sources   NODE halted=final  "25 days."
//
// `must-cite:` is in §7.28's list A — the things both ports are claimed to carry
// out IDENTICALLY — and four spellings out of five did the opposite. What the
// second port did on those four is the outcome `harness.ts` names in its own
// comment as *"the worst outcome available and the one that looks most like
// success"*: it answered out of the model's own memory, citing a corpus it never
// opened, on an agent whose author had written the line that forbids exactly
// that.
//
// It went unseen because the cross-port driver
// (`tests/test_a_corpus_the_second_port_never_looked_in_is_not_silent.py`) sends
// `"must-cite": k.must_cite` — the Python side's ALREADY-PARSED boolean — so the
// string arm was never exercised with anything but `yes`. Two ports compared
// through a value one of them has already normalised cannot disagree about how
// to normalise it.
//
// The vocabulary is held to `coerce.rs` from the Python suite, in
// `test_one_word_for_yes_means_one_thing_to_every_reader.py`, which reads all
// three lists — the Rust match, `yes_no.TICKS`, and `TICKS` below — and fails if
// any of them moves without the others. There is no test runner in this package,
// so a guard that lived here would be a guard nothing runs.

/** The five spellings of a tick, exactly as `coerce.rs::yes_no` holds them. */
export const TICKS: readonly string[] = ["yes", "y", "true", "on", "enabled"];

/**
 * Did the author tick this line?
 *
 * `false` for an absent line, for a crossed one, and for anything else. A real
 * boolean is answered as itself: `must-cite: true` is the one spelling the YAML
 * core schema resolves, so it arrives as `true` and never as text — and a caller
 * that has already parsed the value (the conformance driver used to be one) is
 * answered the same way.
 *
 * Deliberately NOT a list of the negatives as well. `no`, `n`, `false`, `off`
 * and `disabled` are the other five words the checker takes, and this answers a
 * crossed line and an absent one alike, so a second list here would decide
 * nothing and go stale unwatched.
 */
export function saidYes(written: unknown): boolean {
  if (typeof written === "boolean") return written;
  if (written === null || written === undefined) return false;
  return TICKS.includes(String(written).trim().toLowerCase());
}
