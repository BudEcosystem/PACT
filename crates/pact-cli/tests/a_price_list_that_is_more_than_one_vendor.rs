//! The catalogue grew four hosted rows. Both consequences, from the tool an
//! author runs.
//!
//! `models/catalog.yaml` priced exactly one vendor until this round: the three
//! Anthropic rows carried both halves of a price and every other hosted row
//! carried none, so `cost-per-request-under:` could only ever be enforced
//! against a model an Anthropic key reaches. Four rows fixed that — OpenAI,
//! Google and xAI models the shipped transports can name — and a distribution
//! whose flagship claim is that it runs air-gapped does not get to add four
//! hosted models without saying what happens to them in a workspace that has
//! nothing in `allow-egress:`.
//!
//! So both directions are held here, from `pact check` rather than from the
//! loader, for the reason `shares_are_checked_where_the_author_is` gives: a
//! Rust caller is not where the author is. The catalogue is compiled into this
//! binary (`include_str!`), which is what makes the first test a real question —
//! a row that the Python resolver reads and this binary does not would be a row
//! an author is told does not exist.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
}

/// Copy the worked example, apply `edits` as (file, from, to), return the root.
fn edited(name: &str, edits: &[(&str, &str, &str)]) -> String {
    let dst = std::env::temp_dir().join(format!("pact-vendors-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(std::path::Path::new(&example()), &dst);
    for (file, from, to) in edits {
        let p = dst.join(file);
        let text = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
        assert!(
            text.contains(from),
            "fixture drifted: {from:?} not found in {file}"
        );
        std::fs::write(&p, text.replace(from, to)).unwrap();
    }
    dst.to_string_lossy().into_owned()
}

fn copy_dir(src: &std::path::Path, dst: &std::path::Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() {
            copy_dir(&s, &d);
        } else {
            std::fs::copy(&s, &d).unwrap();
        }
    }
}

const AGENT: &str = "agents/refund-desk/agent.yaml";
const WORKSPACE: &str = "workspace.yaml";

/// A row added this round: priced at 0.75 USD per million tokens in and 4.50
/// out, holding 400,000, served over `openai-api`. Named once so the day it
/// moves, one line moves with it.
const PRICED_ELSEWHERE: &str = "gpt-5.4-mini";

#[test]
fn a_hosted_model_this_distribution_prices_can_be_named_by_the_author() {
    // The question the compiled-in catalogue answers: is this a name somebody
    // could legitimately write? A priced row the Python resolver meters and
    // this binary has never heard of would be refused here as a typo, and the
    // author would have no way to reach the model whose price was just added.
    let root = edited(
        "named",
        &[
            (WORKSPACE, "allow-egress: []", "allow-egress: [llm]"),
            (
                AGENT,
                "policy: approvals",
                &format!("model: {PRICED_ELSEWHERE}\npolicy: approvals"),
            ),
        ],
    );
    let out = pact().args(["check", &root]).output().unwrap();
    let said =
        String::from_utf8_lossy(&out.stdout).to_string() + &String::from_utf8_lossy(&out.stderr);
    assert!(
        out.status.success(),
        "a model this distribution publishes a price for must be nameable:\n{said}"
    );
}

#[test]
fn the_hosted_rows_added_for_price_are_still_refused_where_nothing_may_leave_the_box() {
    // D17 does not bend because the price list got wider. The shipped example
    // says `allow-egress: []` — nothing here talks outside the box — and every
    // row added this round is served over somebody's API. The refusal has to
    // name the model, say why, and give a line to type; anything less and the
    // four new rows are four new ways to leave an air-gapped site silently.
    let root = edited(
        "air-gapped",
        &[(
            AGENT,
            "policy: approvals",
            &format!("model: {PRICED_ELSEWHERE}\npolicy: approvals"),
        )],
    );
    let out = pact().args(["check", &root]).output().unwrap();
    let said =
        String::from_utf8_lossy(&out.stdout).to_string() + &String::from_utf8_lossy(&out.stderr);
    assert!(!out.status.success(), "it loaded clean:\n{said}");
    assert!(said.contains(PRICED_ELSEWHERE), "name the model:\n{said}");
    assert!(
        said.contains("allow-egress"),
        "name the line to change:\n{said}"
    );
    assert!(
        said.contains("qwen2.5-7b-instruct"),
        "and offer a model that runs here:\n{said}"
    );
}
