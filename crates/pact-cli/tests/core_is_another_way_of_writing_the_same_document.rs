//! PACT Core's forms are another way of WRITING a workspace, and nothing else
//! (`docs/100-PACT-CORE-A-WRITABLE-KERNEL-LANGUAGE.md` §4).
//!
//! Three forms are read by `crates/pact-lang`:
//!
//! * a **signature** on the line that names a flow, an agent or a program:
//!   `flow decide-all(orders: list of text) gives summary: text`;
//! * a **call in brackets**: `seen = orders/look(order: input.order)`;
//! * an **actor**: one name with several capabilities, each `by model` (an
//!   agent) or written out as statements (a workflow), called as
//!   `<actor>.<capability>`.
//!
//! None of them is a new thing in the document. The first test here is the
//! claim: a workspace written with them and the same workspace written the
//! way `.pact` files always were load to the IDENTICAL document, so every
//! rule `pact check` has holds for Core with no rule written for it. The rest
//! are what is refused, and that a refusal of the document underneath points
//! at the Core line the author wrote.

use serde_json::Value;
use std::process::Command;

const SHARED: &str = r#"workspace "Refund desk"
  description: A desk that decides refunds.
  allow-egress: []

resource office
  resource-kind: mcp-server
  endpoint: host/office
  description: Where the orders are reached.

tool orders
  description: The order book.
  connect: office
  actions:
    look:
      description: Read one order.
      reads-only: yes
      takes:
        order: text

"#;

const IN_CORE: &str = r#"actor desk
  description: Decides refund requests.
  uses orders
  at most 6 steps
  when it runs out: stop and say so

  can judge(order: text, facts: text) gives decision: one of approved, declined, reason: text
    by model
    instructions: Decide whether this order is refunded.

  can decide-one(order: text) gives decision: text
    seen = orders/look(order: input.order)
    ruled = desk.judge(order: input.order, facts: seen.facts)
    answer with decision: ruled.decision

flow decide-all(orders: list of text) gives verdicts: list of text
  description: Decide every order in a list.
  each = for each item in input.orders
    limits:
      items-at-most: 50
      when-it-runs-out: stop-and-say-so
    one = desk.decide-one(order: item)
  answer with verdicts: each.items
"#;

const IN_KEYWORDS: &str = r#"agent desk-judge
  description: Decides refund requests (desk can judge)
  uses orders
  at most 6 steps
  when it runs out: stop and say so
  takes order: text, facts: text
  gives decision: one of approved, declined, reason: text
  instructions: Decide whether this order is refunded.

workflow desk-decide-one
  description: Decides refund requests (desk can decide-one)
  takes order: text
  gives decision: text
  seen = call orders/look with order: input.order
  ruled = call desk-judge with order: input.order, facts: seen.facts
  answer with decision: ruled.decision

workflow decide-all
  description: Decide every order in a list.
  takes orders: list of text
  gives verdicts: list of text
  each = for each item in input.orders
    limits:
      items-at-most: 50
      when-it-runs-out: stop-and-say-so
    one = call desk-decide-one with order: item
  answer with verdicts: each.items
"#;

/// `pact <command>` over one `.pact` file holding `SHARED` and `rest`:
/// whether it succeeded, stdout, and stdout with stderr.
fn pact(name: &str, command: &[&str], rest: &str) -> (bool, String, String) {
    let dir = std::env::temp_dir().join(format!("pact-core-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("desk.pact"), format!("{SHARED}{rest}")).unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(command)
        .arg(dir.to_str().unwrap())
        .output()
        .expect("runs");
    let _ = std::fs::remove_dir_all(&dir);
    let stdout = String::from_utf8_lossy(&out.stdout).into_owned();
    let all = format!("{stdout}{}", String::from_utf8_lossy(&out.stderr));
    (out.status.success(), stdout, all)
}

fn shown(name: &str, rest: &str) -> Value {
    let (ok, out, all) = pact(name, &["show"], rest);
    assert!(ok, "{all}");
    serde_json::from_str(&out).expect("JSON")
}

#[test]
fn core_and_keywords_load_to_the_identical_document() {
    let core = shown("core", IN_CORE);
    let keywords = shown("keywords", IN_KEYWORDS);
    // The same settings with the same values. (The order an entry's own
    // settings are listed in follows the order they were written, which is
    // not something a document means: a signature is written on the first
    // line and `takes` further down.)
    assert_eq!(core, keywords, "the two ways of writing one workspace are two documents");
    // And the same fingerprint, which is what a waiting run is pinned to: a
    // workspace rewritten in Core is the same workspace to every run.
    let digests = |name: &str, rest: &str| -> (Value, Value) {
        let (ok, out, all) = pact(name, &["discover"], rest);
        assert!(ok, "{all}");
        let found: Value = serde_json::from_str(&out).expect("JSON");
        (found[0]["digest"].clone(), found[0]["workflows"].clone())
    };
    let (core_digest, core_flows) = digests("core-digest", IN_CORE);
    let (keyword_digest, keyword_flows) = digests("keyword-digest", IN_KEYWORDS);
    assert!(core_digest.as_str().is_some_and(|d| d.starts_with("sha256:")), "{core_digest}");
    assert_eq!(core_digest, keyword_digest);
    assert_eq!(core_flows, keyword_flows);
    // And it is a workspace the checker passes with nothing to say.
    let (ok, _, all) = pact("clean", &["check", "--deny-warnings"], IN_CORE);
    assert!(ok, "{all}");
}

#[test]
fn an_actor_is_an_agent_for_what_a_model_decides_and_a_workflow_for_what_is_written_out() {
    let doc = shown("actor", IN_CORE);
    let agents: Vec<&String> = doc["agents"].as_object().unwrap().keys().collect();
    let flows: Vec<&String> = doc["workflows"].as_object().unwrap().keys().collect();
    assert_eq!(agents, ["desk-judge"]);
    assert_eq!(flows, ["desk-decide-one", "decide-all"]);
    // What the actor shares reaches the capability a model carries out.
    assert_eq!(doc["agents"]["desk-judge"]["uses"][0], "orders");
    assert_eq!(doc["agents"]["desk-judge"]["limits"]["steps-at-most"], 6);
    // `desk.judge` in a statement is that agent.
    assert_eq!(doc["workflows"]["desk-decide-one"]["steps"]["ruled"]["call"], "desk-judge");
}

#[test]
fn a_binding_that_starts_as_a_path_is_not_taken_for_a_capability() {
    // `call item.worker` is a call by value, as it always was.
    let doc = shown(
        "by-value",
        "agent a\n  description: A.\n  instructions: Do it.\n\n\
         flow f(workers: list of text) gives done: list of text\n  description: F.\n  \
         each = for each item in input.workers\n    limits:\n      items-at-most: 3\n      \
         when-it-runs-out: stop-and-say-so\n    one = call item.worker\n      may-call: [a]\n  \
         answer with done: each.items\n",
    );
    assert_eq!(doc["workflows"]["f"]["steps"]["each"]["steps"]["one"]["call"], "item.worker");
}

#[test]
fn a_rule_of_the_checker_points_at_the_core_line_that_broke_it() {
    // A `for each` with no ceiling is refused by a rule written long before
    // Core, at the line the author wrote in Core.
    let (ok, _, all) = pact(
        "no-ceiling",
        &["check"],
        "agent a(order: text) gives ok: text\n  description: A.\n  instructions: Do it.\n\n\
         flow f(orders: list of text) gives done: list of text\n  description: F.\n  \
         each = for each item in input.orders\n    one = a(order: item)\n  \
         answer with done: each.items\n",
    );
    assert!(!ok, "{all}");
    assert!(all.contains("rule: loader/for-each-with-no-ceiling"), "{all}");
    assert!(all.contains("each = for each item in input.orders"), "{all}");
}

#[test]
fn a_call_to_what_is_not_there_is_refused_whichever_way_it_is_written() {
    for call in ["nobody(order: input.order)", "call nobody with order: input.order"] {
        let (ok, _, all) = pact(
            "nobody",
            &["check"],
            &format!(
                "flow f(order: text) gives done: text\n  description: F.\n  one = {call}\n  \
                 answer with done: one.x\n"
            ),
        );
        assert!(!ok, "{call}: {all}");
        assert!(all.contains("nobody"), "{call}: {all}");
    }
}

#[test]
fn what_cannot_be_read_is_said_where_it_is_written() {
    for (name, rest, says) in [
        (
            "unclosed",
            "flow f(order: text gives done: text\n  description: F.\n  answer\n",
            "'f(' is opened and never closed.",
        ),
        (
            "after-the-bracket",
            "flow f(order: text) returns done: text\n  description: F.\n  answer\n",
            "After what 'f' takes, the only thing this line can say is what it gives.",
        ),
        (
            "an-actor-with-no-can",
            "actor desk\n  description: Does nothing.\n",
            "The actor 'desk' has no `can` line, so there is nothing to ask it.",
        ),
        (
            "said-twice",
            "flow f(order: text) gives done: text\n  description: F.\n  takes order: text\n  answer\n",
            "rule: lang/said-twice",
        ),
    ] {
        let (ok, _, all) = pact(name, &["check"], rest);
        assert!(!ok, "{name}: {all}");
        assert!(all.contains(says), "{name}: {all}");
    }
}

#[test]
fn the_shipped_core_example_loads_clean() {
    let root = concat!(env!("CARGO_MANIFEST_DIR"), "/../../examples/core/refund-desk");
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(["check", root, "--deny-warnings"])
        .output()
        .expect("runs");
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stdout));
}
