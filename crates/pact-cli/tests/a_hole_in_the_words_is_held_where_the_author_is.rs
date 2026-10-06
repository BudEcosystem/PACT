//! `{{run-inputs.<n>}}` and `{{remembers.<n>}}` in an agent's words, held by
//! `pact check` itself (02P §3.2 A1).
//!
//! `pact_loader::holes::check` had ten unit tests and one call site, and the
//! call site was held by nothing in this workspace: commenting the line out of
//! `main.rs` left `cargo test` green, because every Rust test called the
//! function and none ran the command. D13's reader runs `pact check` and
//! nothing else, so a check that does not arrive there does not arrive.
//!
//! Four fixture trees under `tests/trees/`, each read through the real binary:
//!
//! * braces a model is meant to read load, with a warning, and the one escape
//!   is quiet;
//! * braces that are nearly a hole are warned about, each of the three ways;
//! * a variant's hole naming nothing is refused, like the agent's own;
//! * a hole in folded or quoted words is reported at the line it is written on.

use std::process::Command;

struct Checked {
    code: Option<i32>,
    said: String,
}

fn check(tree: &str, more: &[&str]) -> Checked {
    let root = format!("{}/../../tests/trees/{tree}", env!("CARGO_MANIFEST_DIR"));
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .arg("check")
        .arg(&root)
        .args(more)
        .output()
        .expect("runs");
    Checked {
        code: out.status.code(),
        said: format!(
            "{}{}",
            String::from_utf8_lossy(&out.stdout),
            String::from_utf8_lossy(&out.stderr)
        ),
    }
}

fn times(said: &str, what: &str) -> usize {
    said.matches(what).count()
}

#[test]
fn braces_the_model_is_meant_to_read_load_with_one_warning() {
    let c = check("braces-the-model-is-meant-to-read", &[]);
    assert_eq!(c.code, Some(0), "a template's own braces are not an error:\n{}", c.said);
    assert_eq!(times(&c.said, "rule: loader/not-a-hole"), 1, "{}", c.said);
    assert!(c.said.contains("mailer.yaml:6:23"), "at the braces themselves:\n{}", c.said);
    assert!(c.said.contains(r"`\{{first_name}}`"), "the escape is offered:\n{}", c.said);
    // The escaped pairs on the next line are said on purpose: nothing about them.
    assert!(!c.said.contains("order_id"), "{}", c.said);
    assert_eq!(times(&c.said, "rule: "), 1, "and nothing else:\n{}", c.said);

    // A warning is still a warning: the flag that refuses them refuses this.
    let strict = check("braces-the-model-is-meant-to-read", &["--deny-warnings"]);
    assert_ne!(strict.code, Some(0), "{}", strict.said);
}

#[test]
fn braces_that_are_nearly_a_hole_are_each_warned_about() {
    let c = check("braces-that-are-nearly-a-hole", &[]);
    assert_eq!(c.code, Some(0), "{}", c.said);
    assert_eq!(times(&c.said, "rule: loader/almost-a-hole"), 3, "{}", c.said);
    for (nearly, at) in [
        ("`{{{run-inputs.brand}}}`", "writer.yaml:5:17"),
        ("`{{run-inputs.brand | upper}}`", "writer.yaml:6:13"),
        ("`{{ run-inputs. brand }}`", "writer.yaml:7:24"),
    ] {
        assert!(c.said.contains(nearly), "{nearly} is named:\n{}", c.said);
        assert!(c.said.contains(at), "{nearly} is at {at}:\n{}", c.said);
    }
    assert_eq!(times(&c.said, "rule: "), 3, "the real hole on line 8 is quiet:\n{}", c.said);
}

#[test]
fn a_variants_hole_naming_nothing_is_refused() {
    let c = check("a-variant-with-a-hole-nothing-fills", &[]);
    assert_eq!(c.code, Some(1), "{}", c.said);
    assert!(c.said.contains("rule: loader/no-such-run-input"), "{}", c.said);
    assert!(c.said.contains("`variants.small.says:`"), "{}", c.said);
    assert!(c.said.contains("writer.yaml:11:29"), "{}", c.said);
    assert!(c.said.contains("rule: loader/no-such-remembered-fact"), "{}", c.said);
    assert!(c.said.contains("`variants.terse.instructions:`"), "{}", c.said);
    assert_eq!(times(&c.said, "rule: "), 2, "`plain` names a declared input:\n{}", c.said);
}

#[test]
fn a_hole_in_folded_or_quoted_words_is_reported_at_its_own_line() {
    let c = check("a-hole-in-folded-and-quoted-words", &[]);
    assert_eq!(c.code, Some(1), "{}", c.said);
    assert!(c.said.contains("writer.yaml:6:12"), "the quoted description:\n{}", c.said);
    assert!(c.said.contains("writer.yaml:11:17"), "the folded instructions:\n{}", c.said);
}

#[test]
fn a_card_says_when_it_publishes_a_description_nobody_will_fill() {
    // `mailer`'s description is `... a campaign for {{run-inputs.brand}} ...`.
    // A card is read with no run, so the braces go out as written; that is
    // said on stderr rather than left for whoever reads the card to find.
    let root = format!(
        "{}/../../tests/trees/braces-the-model-is-meant-to-read",
        env!("CARGO_MANIFEST_DIR")
    );
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(["card", "mailer", &root])
        .output()
        .expect("runs");
    let (card, said) =
        (String::from_utf8_lossy(&out.stdout), String::from_utf8_lossy(&out.stderr));
    assert_eq!(out.status.code(), Some(0), "{said}");
    assert!(card.contains("{{run-inputs.brand}}"), "carried as written:\n{card}");
    assert!(
        said.contains("rule: card/a-description-filled-when-a-run-starts"),
        "and said:\n{said}"
    );
    assert!(said.contains("`{{run-inputs.brand}}`"), "{said}");
}

#[test]
fn an_inventory_says_so_too() {
    // `pact discover` publishes the same description to the same kind of
    // reader, one with no run, and said nothing about the braces.
    let root = format!(
        "{}/../../tests/trees/braces-the-model-is-meant-to-read",
        env!("CARGO_MANIFEST_DIR")
    );
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(["discover", &root])
        .output()
        .expect("runs");
    let (found, said) =
        (String::from_utf8_lossy(&out.stdout), String::from_utf8_lossy(&out.stderr));
    assert_eq!(out.status.code(), Some(0), "{said}");
    assert!(found.contains("{{run-inputs.brand}}"), "carried as written:\n{found}");
    assert!(
        said.contains("rule: discover/a-description-filled-when-a-run-starts"),
        "and said:\n{said}"
    );
    assert!(said.contains("An inventory is read with no run"), "{said}");
}
