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

// ── names, values, programs and patterns ─────────────────────────────────────

const TILL: &str = r#"program add-up(amounts: list of number) gives total: number
  description: Adds a list of numbers.
  engine: wasm
  determinism: pure
  fuel:
    runs-for-at-most: 1s
    when-it-runs-out: stop-and-say-so

"#;

#[test]
fn what_a_flow_takes_is_read_by_its_name_and_a_value_can_be_given_one() {
    let core = shown(
        "names",
        "flow look(order: text) gives facts: text\n  description: Looks one order up.\n  \
         seen = orders/look(order: order)\n  found = seen.facts\n  answer with facts: found\n",
    );
    let keywords = shown(
        "names-keywords",
        "workflow look\n  description: Looks one order up.\n  takes order: text\n  gives facts: text\n  \
         seen = call orders/look with order: input.order\n  answer with facts: seen.facts\n",
    );
    // `found = seen.facts` is no stage: it is a name, and the document has none of it.
    assert_eq!(core, keywords);
    let steps: Vec<&String> = core["workflows"]["look"]["steps"].as_object().unwrap().keys().collect();
    assert_eq!(steps, ["seen", "answer"]);
}

#[test]
fn a_statement_named_like_an_input_is_the_statement_from_then_on() {
    let doc = shown(
        "shadow",
        "flow look(order: text) gives facts: text\n  description: Looks one order up.\n  \
         order = orders/look(order: order)\n  answer with facts: order.facts\n",
    );
    let steps = &doc["workflows"]["look"]["steps"];
    assert_eq!(steps["order"]["bind"]["order"], "input.order", "before it: what was given");
    assert_eq!(steps["answer"]["bind"]["facts"], "steps.order.facts", "after it: the statement");
}

#[test]
fn a_fixed_value_in_a_statement_is_a_named_value_and_the_same_one_is_filed_once() {
    let doc = shown(
        "said",
        "flow tag(order: text) gives note: text, again: text, most: money\n  description: Tags.\n  \
         answer with note: \"checked, and filed\", again: \"checked, and filed\", most: 200 USD\n",
    );
    let bind = &doc["workflows"]["tag"]["steps"]["answer"]["bind"];
    assert_eq!(bind["note"], "values.said-checked-and-filed");
    assert_eq!(bind["again"], "values.said-checked-and-filed", "a comma inside quotes is part of the words");
    assert_eq!(bind["most"], "values.said-200-usd");
    let values = doc["values"].as_object().unwrap();
    assert_eq!(values.len(), 2);
    assert_eq!(values["said-checked-and-filed"]["value"], "checked, and filed");
    assert_eq!(values["said-200-usd"]["value"], "200 USD");
    // It is the document a `let` and `values.<name>` have always made.
    let by_let = shown(
        "said-let",
        "let said-checked-and-filed = \"checked, and filed\"\nlet said-200-usd = 200 USD\n\n\
         flow tag(order: text) gives note: text, again: text, most: money\n  description: Tags.\n  \
         answer with note: values.said-checked-and-filed, again: values.said-checked-and-filed, \
         most: values.said-200-usd\n",
    );
    assert_eq!(doc, by_let);
}

#[test]
fn a_fixed_value_is_held_to_the_shape_it_fills() {
    // `"perhaps"` where the flow gives `one of approved, declined`.
    let (ok, _, all) = pact(
        "said-wrong",
        &["check"],
        "flow rule(order: text) gives decision: one of approved, declined\n  description: Rules.\n  \
         answer with decision: \"perhaps\"\n",
    );
    assert!(!ok, "{all}");
    assert!(all.contains("rule: loader/a-call-that-does-not-fit"), "{all}");
    assert!(
        all.contains("which is `perhaps`") && all.contains("fix: Write one of: `approved`, `declined`."),
        "{all}"
    );
    let (ok, _, all) = pact(
        "said-right",
        &["check"],
        "flow rule(order: text) gives decision: one of approved, declined\n  description: Rules.\n  \
         answer with decision: \"approved\"\n",
    );
    assert!(ok, "{all}");
}

#[test]
fn a_capability_carried_out_by_a_program_hands_it_the_same_inputs_and_hands_back_its_answer() {
    let core = shown(
        "by-program",
        &format!(
            "{TILL}actor till\n  description: Works out what an order comes to.\n\n  \
             can total(amounts: list of number) gives total: number\n    by program add-up\n"
        ),
    );
    let keywords = shown(
        "by-program-keywords",
        &format!(
            "{TILL}workflow till-total\n  description: Works out what an order comes to (till can total)\n  \
             takes amounts: list of number\n  gives total: number\n  \
             run = call add-up with amounts: input.amounts\n  answer with total: run.total\n"
        ),
    );
    assert_eq!(core, keywords);
}

#[test]
fn a_pattern_is_defined_on_one_line_and_what_is_made_from_it_fills_its_blanks() {
    let core = shown(
        "define",
        "define desk-for(domain: text, cap: money) as agent\n  \
         description: A desk that answers questions about <domain>.\n  \
         spends under <cap> a request\n  when it runs out: stop and say so\n  \
         instructions: Answer questions about <domain>, briefly.\n\n\
         agent billing-desk is desk-for(domain: billing, cap: 0.10 USD)\n",
    );
    let keywords = shown(
        "define-keywords",
        "agent desk-for\n  description: A desk that answers questions about <domain>.\n  \
         spends under <cap> a request\n  when it runs out: stop and say so\n  \
         instructions: Answer questions about <domain>, briefly.\n  base: yes\n  expects:\n    \
         domain:\n      shape: text\n    cap:\n      shape: money\n\n\
         agent billing-desk\n  based on desk-for with domain: billing, cap: 0.10 USD\n",
    );
    assert_eq!(core, keywords);
    // The pattern never runs; what is made from it is whole.
    let agents: Vec<&String> = core["agents"].as_object().unwrap().keys().collect();
    assert_eq!(agents, ["billing-desk"]);
    assert_eq!(
        core["agents"]["billing-desk"]["instructions"],
        "Answer questions about billing, briefly."
    );
    assert_eq!(core["agents"]["billing-desk"]["limits"]["cost-per-request-under"], "0.10 USD");
}

#[test]
fn a_blank_left_unfilled_or_a_pattern_that_is_not_there_is_refused_by_the_rules_patterns_always_had() {
    let pattern = "define desk-for(domain: text) as agent\n  description: About <domain>.\n  \
                   instructions: Answer about <domain>.\n\n";
    let (ok, _, all) = pact("unfilled", &["check"], &format!("{pattern}agent billing-desk is desk-for()\n"));
    assert!(!ok, "{all}");
    assert!(all.contains("domain"), "{all}");
    let (ok, _, all) = pact("no-pattern", &["check"], "agent billing-desk is nobody(domain: billing)\n");
    assert!(!ok, "{all}");
    assert!(all.contains("nobody"), "{all}");
    let (ok, _, all) = pact("no-kind", &["check"], "define desk-for(domain: text)\n  description: D.\n");
    assert!(!ok, "{all}");
    assert!(all.contains("A `define` says what kind of thing the pattern is."), "{all}");
}

#[test]
fn the_second_shipped_core_example_loads_clean() {
    let root = concat!(env!("CARGO_MANIFEST_DIR"), "/../../examples/core/shop");
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(["check", root, "--deny-warnings"])
        .output()
        .expect("runs");
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stdout));
}
