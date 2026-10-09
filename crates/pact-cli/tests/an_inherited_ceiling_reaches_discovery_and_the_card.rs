//! **An inherited ceiling reaches discovery and the card** — C8 §7 D-5's own
//! name for its acceptance test, run against the real binary.
//!
//! D-5's measured defect: `pact discover` and `pact card` re-loaded the tree
//! bare, so every derived agent was published with `model: null` and
//! `limits: null` — the document `validate` had already resolved was thrown
//! away and the underived one projected instead. Both commands now keep
//! validate's node, and this file is where that shows: the spend cap `refunds`
//! never typed is in its inventory row, the description it never typed is on
//! its card, and the base it derives from is offered by neither command.
//!
//! Everything runs `CARGO_BIN_EXE_pact` against
//! `tests/trees/an-agent-built-on-another/` — a base with a hole, a descendant
//! that fills it, a budgeted self-team and a budgeted two-ring.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn tree() -> String {
    format!(
        "{}/../../tests/trees/an-agent-built-on-another",
        env!("CARGO_MANIFEST_DIR")
    )
}

fn run(args: &[&str]) -> (Option<i32>, String, String) {
    let out = pact().args(args).output().expect("runs");
    (
        out.status.code(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
        String::from_utf8_lossy(&out.stderr).into_owned(),
    )
}

/// The whole tree — the base's hole, the self-team, the two-ring — is clean
/// under the strictest gate the CLI has.
///
/// This is the grant side of two refusals: a circle every member budgets is
/// allowed, and a base may leave `instructions:` unwritten. Either exemption
/// gone and this exits 1.
#[test]
fn check_allows_a_budgeted_circle() {
    let (code, out, err) = run(&["check", &tree(), "--deny-warnings"]);
    assert_eq!(
        code,
        Some(0),
        "a budgeted circle and a base with a hole must check clean:\n{out}{err}"
    );
}

/// The inventory publishes each agent as the thing it BECOMES.
///
/// `refunds` writes two lines; its row carries the pattern's spend cap,
/// non-null, and no `based-on` seam survives anywhere in the output. The
/// pattern itself — `base: yes`, nothing can run it — has no row at all.
///
/// Mutation: put the bare re-load back in discover_cmd (limits go null), or
/// drop the `is_base` skip in inventory() (desk-pattern comes back).
#[test]
fn discover_reports_the_derived_agent_whole() {
    let (code, out, err) = run(&["discover", &tree()]);
    assert_eq!(code, Some(0), "{err}");
    let json: serde_json::Value = serde_json::from_str(&out).expect("discover emits JSON");
    let agents = json[0]["agents"].as_array().expect("a list of agents");

    let refunds = agents
        .iter()
        .find(|a| a["id"] == "pact:refunds")
        .expect("the derived agent is in the inventory");
    assert!(
        !refunds["limits"].is_null(),
        "the inherited limits must be published, not the underived null: {out}"
    );
    assert_eq!(
        refunds["limits"]["cost-per-request-under"], "0.05 USD",
        "the ceiling is the one the pattern declared: {out}"
    );

    assert!(
        !out.contains("based-on"),
        "a resolved inventory has no seam to show: {out}"
    );
    assert!(
        !agents.iter().any(|a| a["id"] == "pact:desk-pattern"),
        "a base exists only to be based on — publishing it was C8 §6 price 6's defect: {out}"
    );
}

/// The card another system reads INSTEAD of the tree carries what the agent
/// inherited — the pattern's own sentence, word for word.
#[test]
fn the_card_carries_the_inherited_description() {
    let (code, out, err) = run(&["card", "refunds", &tree()]);
    assert_eq!(code, Some(0), "{err}");
    let card: serde_json::Value = serde_json::from_str(&out).expect("card emits JSON");
    assert_eq!(
        card["description"],
        "The shape of a desk — a spend cap and a stop rule — for real desks to be based on.",
        "refunds writes no `description:` — the card must carry the inherited one: {out}"
    );
}

/// A card for a base is refused, and the fix never suggests one.
///
/// `agent_card` returns None for `base: yes`, and the no-such-agent fix list
/// filters bases — suggesting `desk-pattern` would send the reader straight
/// back into the refusal they just read.
#[test]
fn a_card_for_a_base_is_refused() {
    let (code, out, err) = run(&["card", "desk-pattern", &tree()]);
    assert_eq!(code, Some(2), "a base has no card to publish:\n{out}{err}");
    let fix = err
        .lines()
        .find(|l| l.contains("Change it to one of:"))
        .unwrap_or_else(|| panic!("the refusal offers the agents that CAN be carded:\n{err}"));
    for runnable in ["refunds", "second-look", "drafter", "checker"] {
        assert!(
            fix.contains(runnable),
            "'{runnable}' is missing from: {fix}"
        );
    }
    assert!(
        !fix.contains("desk-pattern"),
        "the fix must not offer the base back: {fix}"
    );
}

/// A card does not publish an address nobody can reach.
///
/// `agent_card` takes a `base_url` — it was always meant to be supplied — and
/// the CLI passed the literal `"https://agents.local"`, with no way to give it
/// anything else. Every card this repository has ever printed therefore carried
///
/// ```text
/// "url": "https://agents.local/pact/refund-desk"
/// ```
///
/// which resolves to nothing, anywhere, for anybody. And the card is the one
/// artefact here that is *meant* to leave the machine: an A2A consumer reads
/// that field to decide where to send work.
///
/// The same system already answers this question, and answers it the other way.
/// `exporting.py` leaves `invocation.url` EMPTY on purpose and says why: *"where
/// this deployment answers. A PACT tree is not deployed anywhere — that is what
/// makes the same tree runnable in two places."* Two halves of one system, two
/// answers, and the one that travels was the invented one.
///
/// `agent_card`'s own comment already knows the shape of the mistake — it
/// refuses to print a card for a `base: yes` agent because that would be *"a lie
/// with a URL on it"*. A URL that goes nowhere is the same lie with the subject
/// changed.
///
/// So the operator supplies the host, and where they have not, the card
/// publishes a RELATIVE reference: the path under it is PACT's to know, since it
/// derives from the agent's own name, and the host is not. That resolves against
/// whatever really serves the agent, and invents nothing.
#[test]
fn a_card_does_not_invent_a_host_nobody_can_reach() {
    let (code, out, err) = run(&["card", "refunds", &tree()]);
    assert_eq!(code, Some(0), "{out}{err}");
    let card: serde_json::Value = serde_json::from_str(&out).expect("a card is JSON");
    let url = card["url"].as_str().unwrap_or_default();
    assert!(
        !url.contains("agents.local"),
        "the card publishes an address nobody can reach: {url:?}"
    );
    // A RELATIVE reference, which is the most informative true answer. The path
    // under the host is PACT's to know — it derives from the agent's own name —
    // and the host is not. Emitting the path without a host says exactly that,
    // and resolves correctly against whatever really serves the agent; emitting
    // nothing at all would throw away a fact this side does know.
    assert_eq!(
        url, "/pact/refunds",
        "with no address given, the card publishes the path and no host: {url:?}"
    );
}

/// And when the operator says where their agents answer, that is what it prints.
#[test]
fn a_card_publishes_the_address_the_operator_gave_it() {
    let (code, out, err) = run(&[
        "card",
        "refunds",
        &tree(),
        "--base-url",
        "https://desks.acme.example",
    ]);
    assert_eq!(code, Some(0), "{out}{err}");
    let card: serde_json::Value = serde_json::from_str(&out).expect("a card is JSON");
    assert_eq!(
        card["url"].as_str(),
        Some("https://desks.acme.example/pact/refunds"),
        "the address the operator gave, with the agent's own path under it"
    );
}
