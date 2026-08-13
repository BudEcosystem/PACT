//! A count of tokens too big to hold is refused where the author is, instead of
//! being quietly turned into a different number.
//!
//! `needs.context-at-least` exists because `type: text` let `context-at-least:
//! quite a lot really` load clean and reach the resolver verbatim, where it was
//! compared against a real context window. `type: size` closed that — and left
//! the far end open. `k` and `m` are multiplied in floating point and the
//! product is cast to a whole number, and a float-to-integer cast in Rust
//! SATURATES rather than wrapping, so a number past the end comes out as the
//! largest number there is with nothing said:
//!
//! ```text
//! $ cat agents/refund-desk/needs.yaml
//! context-at-least: 99999999999999999999m
//!
//! $ pact check .
//! OK — examples/refund-desk loaded cleanly (498 settings).
//! $ echo $?
//! 0
//! ```
//!
//! That is the same shape of defect `schema/too-long-to-count` was added for on
//! the duration side, one function away in the same file, and the same answer:
//! the line is spelled exactly the way the help says to spell it, so it is not
//! "not a size" — it is a size this cannot count, refused by name, with the
//! field, the line, and something to type.
//!
//! **THE SPELLING THIS FILE CERTIFIED NOTHING ABOUT FOR A ROUND.** Every case
//! above carries a unit — `…m` — which is what makes the scalar a `Value::Str`
//! and what lets it reach `coerce::size` at all. The same figure WITHOUT the
//! unit, which is the form this field's own `fix:` prescribes (`200000`), used
//! to arrive as a `Value::Float` and fall out of `size` at its
//! `_ => return None`, so the author was told:
//!
//! ```text
//! error: 'context-at-least' should be a size, like `32k` or `200000`, but it is a number.
//!   fix: Write it like `32k`, `128k`, `1m` or `200000` — …
//!   rule: schema/wrong-type
//! ```
//!
//! — a sentence contradicted by its own example, about a correctly-spelled
//! line, with the right answer sitting one branch below and unreachable.
//! `1e999` fell out one branch later, at `!v.is_finite()`, as *"but it is some
//! text"*. Both were measured through this binary; the unit test in
//! `coerce.rs` could not have caught either, because it wraps its input in
//! quotes before calling `check` and so exercises a `Value::Str` the document
//! layer never produced for those spellings. Two edits close them —
//! `yaml::resolve_scalar` keeps a digit run `i64` refuses, and `size` hands a
//! non-finite parse that carries a digit up as `SizeTooBig` — and
//! `the_spelling_the_help_prescribes_is_covered_too` is the test that runs the
//! unquoted forms through the real command.
//!
//! Mutation, measured: put `!v.is_finite() => None` back in `coerce::size` and
//! that test alone goes red, `3 passed; 1 failed`, with `coerce.rs`'s own
//! `a_size_accepts_the_spellings_a_model_card_prints` red beside it; drop the
//! digits-only arm from `resolve_scalar` and it goes red on the unquoted
//! `99999999999999999999` while the quoted twin stays green, which is exactly
//! the gap that survived.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
}

/// Copy the worked example, apply one edit, return the temp root.
fn edited(name: &str, file: &str, from: &str, to: &str) -> String {
    let dst = std::env::temp_dir().join(format!("pact-size-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(std::path::Path::new(&example()), &dst);
    let p = dst.join(file);
    let text = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
    assert!(
        text.contains(from),
        "fixture drifted: {from:?} not in {file}"
    );
    std::fs::write(&p, text.replace(from, to)).unwrap();
    dst.to_string_lossy().into_owned()
}

fn copy(src: &std::path::Path, dst: &std::path::Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() {
            copy(&s, &d)
        } else {
            std::fs::copy(&s, &d).map(|_| ()).unwrap()
        }
    }
}

#[test]
fn a_number_of_tokens_nobody_can_count_is_refused_at_check_time() {
    // Mutation: put `Some((v * mult) as u64)` back at the end of
    // `coerce::size`. Measured with it back: `OK — loaded cleanly (498
    // settings)`, exit 0, and the line travels on to a resolver that compares
    // it against a real model's context window.
    let root = edited(
        "too-big",
        "agents/refund-desk/needs.yaml",
        "context-at-least: 32k",
        "context-at-least: 99999999999999999999m",
    );
    let out = pact().args(["check", &root]).output().expect("runs");
    let text = String::from_utf8_lossy(&out.stdout);

    assert!(
        !out.status.success(),
        "a size nobody can count must be refused:\n{text}"
    );
    assert!(
        text.contains("schema/too-big-to-count"),
        "wrong rule:\n{text}"
    );
    assert!(
        text.contains("'context-at-least' is 99999999999999999999m"),
        "must name the setting and quote what was written:\n{text}"
    );
    assert!(
        text.contains("needs.yaml:7"),
        "must name the file and the line:\n{text}"
    );
    assert!(
        text.contains("fix: Write `context-at-least: 32k`"),
        "the fix must be a line they can type:\n{text}"
    );
    // `32k` and `99999999999999999999m` are spelled the same way. Telling the
    // author the second is not a size would send them hunting for a typo that
    // is not there.
    assert!(
        !text.contains("schema/wrong-type"),
        "the line is spelled correctly:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_spelling_the_help_prescribes_is_covered_too() {
    // THE GAP THAT MADE THE TEST ABOVE CERTIFY LESS THAN IT LOOKED LIKE.
    // `99999999999999999999m` carries a unit, so the document layer hands it up
    // as text and `coerce::size` sees it. The same figure WITHOUT the unit — the
    // form this field's own `fix:` prescribes, `200000` — used to arrive as a
    // `Value::Float(1e20)` and fall through `size`'s `_ => return None`, so the
    // author of a correctly-spelled line was told *"should be a size, like
    // `32k` or `200000`, but it is a number"*: a sentence that contradicts its
    // own example. `1e999` fell out the same door one branch later, as *"but it
    // is some text"*.
    //
    // The unit test at `coerce.rs`'s `mod tests` could not have caught either:
    // it wraps its input in quotes before calling `check`, so it exercises a
    // `Value::Str` that the document layer never produced for these spellings.
    // Only a run through the real binary reaches them.
    for written in ["99999999999999999999", "1e999", "1e999k"] {
        let root = edited(
            "bare-too-big",
            "agents/refund-desk/needs.yaml",
            "context-at-least: 32k",
            &format!("context-at-least: {written}"),
        );
        let out = pact().args(["check", &root]).output().expect("runs");
        let text = String::from_utf8_lossy(&out.stdout);

        assert!(!out.status.success(), "`{written}` must be refused:\n{text}");
        assert!(
            text.contains("schema/too-big-to-count"),
            "wrong rule for `{written}`:\n{text}"
        );
        assert!(
            !text.contains("schema/wrong-type"),
            "`{written}` is spelled the way this field's own fix says to spell \
             it; sending its author hunting for a typo is what this rule exists \
             to stop:\n{text}"
        );
        assert!(
            text.contains(&format!(
                "'context-at-least' is {written}, which is more than this can keep track of."
            )),
            "the sentence must quote what was written:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    // Quoted and unquoted must not be two different rules for one figure. That
    // they WERE is how the gap survived a green suite.
    let root = edited(
        "quoted-too-big",
        "agents/refund-desk/needs.yaml",
        "context-at-least: 32k",
        "context-at-least: \"99999999999999999999\"",
    );
    let out = pact().args(["check", &root]).output().expect("runs");
    let text = String::from_utf8_lossy(&out.stdout);
    assert!(
        text.contains("schema/too-big-to-count"),
        "the quoted form answers the same as the bare one:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_word_where_a_size_goes_is_still_a_word() {
    // The line the "too big" answer must not cross. `inf` and `nan` carry no
    // digit and never overflowed anything — they are words spelled where a
    // count goes, and *"not a size"* is the true sentence about them. A count
    // below zero is not a count either, whatever its size, so `-1e999` gets the
    // answer `-5` gets rather than a ranking of how far below zero it is.
    for written in ["inf", "nan", "-1e999"] {
        let root = edited(
            "size-word",
            "agents/refund-desk/needs.yaml",
            "context-at-least: 32k",
            &format!("context-at-least: {written}"),
        );
        let out = pact().args(["check", &root]).output().expect("runs");
        let text = String::from_utf8_lossy(&out.stdout);
        assert!(!out.status.success(), "`{written}` is not a size:\n{text}");
        assert!(
            text.contains("schema/wrong-type"),
            "`{written}` is a typo or a nonsense, not a size over a ceiling:\n{text}"
        );
        assert!(
            !text.contains("too-big-to-count"),
            "`{written}` never overflowed anything:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }
}

#[test]
fn every_size_the_help_advertises_still_loads() {
    // The refusal must not have taken the ordinary sizes with it. These four
    // are the ones `Ty::Size` names in its own fix — `32k`, `128k`, `1m`,
    // `200000` — plus the biggest number a model card has any business
    // printing, which is nowhere near the end.
    for (name, written) in [
        ("k", "32k"),
        ("bigger-k", "128k"),
        ("m", "1m"),
        ("bare", "200000"),
        ("huge", "9999999999k"),
    ] {
        let root = edited(
            name,
            "agents/refund-desk/needs.yaml",
            "context-at-least: 32k",
            &format!("context-at-least: {written}"),
        );
        let out = pact().args(["check", &root]).output().expect("runs");
        let text = String::from_utf8_lossy(&out.stdout);
        assert!(
            out.status.success(),
            "`{written}` is a size and must load:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }
}
