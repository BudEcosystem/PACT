//! A workflow's stages written as statements (`read/flow.rs`): each held to
//! the stages it stands for, and to coming back out of `pact_lang::write` as
//! the statements it went in as.

use camino::Utf8Path;
use serde_json::{Value, json};

fn read(text: &str) -> Value {
    let parsed = pact_lang::read(text, Utf8Path::new("t.pact"));
    let said: Vec<String> = parsed.diagnostics.iter().map(|d| d.message.clone()).collect();
    assert!(said.is_empty(), "{text}\n{said:?}");
    parsed.node.to_json()
}

fn refused(text: &str) -> Vec<(&'static str, usize)> {
    pact_lang::read(text, Utf8Path::new("t.pact"))
        .diagnostics
        .iter()
        .map(|d| (d.rule, d.span.line))
        .collect()
}

/// Read `text`, write what was read, and read that: the same document — and
/// the same text, so a statement comes back as the statement it was.
fn comes_back_as_written(text: &str) {
    let parsed = pact_lang::read(text, Utf8Path::new("t.pact"));
    assert!(parsed.diagnostics.is_empty(), "{text}");
    let written = pact_lang::write(&parsed.node).unwrap();
    assert_eq!(read(&written.text), parsed.node.to_json(), "{}", written.text);
    assert_eq!(written.text.trim(), text.trim());
}

#[test]
fn one_statement_after_another_and_a_name_is_a_variable() {
    let text = "\
workflow deliver
  description: Research a brief, plan from the findings, then build from the plan.
  takes brief: text
  gives result: text
  research = call researcher with brief: input.brief
  plan = call planner with brief: input.brief, findings: research.findings
  make = call builder with plan: plan.plan
  reply = answer with result: make.result
";
    assert_eq!(
        read(text),
        json!({"workflows": {"deliver": {
            "description": "Research a brief, plan from the findings, then build from the plan.",
            "accepts": {"brief": "text"},
            "answers-with": {"result": "text"},
            "starts-at": "research",
            "steps": {
                "research": {
                    "does": "call", "call": "researcher",
                    "bind": {"brief": "input.brief"},
                    "then": {"answered": "plan"},
                },
                "plan": {
                    "does": "call", "call": "planner",
                    "bind": {"brief": "input.brief", "findings": "steps.research.findings"},
                    "then": {"answered": "make"},
                },
                "make": {
                    "does": "call", "call": "builder",
                    "bind": {"plan": "steps.plan.plan"},
                    "then": {"answered": "reply"},
                },
                "reply": {"does": "answer", "bind": {"result": "steps.make.result"}},
            },
        }}})
    );
    comes_back_as_written(text);
}

#[test]
fn a_step_with_no_name_is_called_after_what_it_does() {
    let text = "\
workflow hello
  description: Ask one agent and hand back what it said.
  call greeter with message: input.message
  answer with reply: greeter.reply
";
    let doc = read(text);
    let steps = &doc["workflows"]["hello"]["steps"];
    assert_eq!(doc["workflows"]["hello"]["starts-at"], "greeter");
    assert_eq!(steps["greeter"]["then"], json!({"answered": "answer"}));
    assert_eq!(steps["answer"], json!({"does": "answer", "bind": {"reply": "steps.greeter.reply"}}));
    comes_back_as_written(text);
}

#[test]
fn a_loop_over_a_list_and_two_things_at_once() {
    let text = "\
workflow review-all
  description: Review every document, then summarise two ways.
  takes documents: text
  gives verdict: text, optional
  each-document = for each item in input.documents
    identified-by: [content-hash]
    combines-by:
      verdict: vote
    limits:
      items-at-most: 50
      when-it-runs-out: stop-and-say-so
    review = call reviewer with document: item.content-hash
  both = together
    short = call summariser with verdicts: each-document.verdict
    long = call summariser with verdicts: each-document.reason
  reply = answer
";
    assert_eq!(
        read(text)["workflows"]["review-all"],
        json!({
            "description": "Review every document, then summarise two ways.",
            "accepts": {"documents": "text"},
            "answers-with": {"verdict": "text, optional"},
            "starts-at": "each-document",
            "steps": {
                "each-document": {
                    "does": "each",
                    "over": "input.documents",
                    "identified-by": ["content-hash"],
                    "combines-by": {"verdict": "vote"},
                    "limits": {"items-at-most": 50, "when-it-runs-out": "stop-and-say-so"},
                    "starts-at": "review",
                    "steps": {"review": {
                        "does": "call", "call": "reviewer",
                        "bind": {"document": "item.content-hash"},
                    }},
                    "then": {"answered": "both"},
                },
                "both": {
                    "does": "together",
                    "steps": {
                        "short": {
                            "does": "call", "call": "summariser",
                            "bind": {"verdicts": "steps.each-document.verdict"},
                        },
                        "long": {
                            "does": "call", "call": "summariser",
                            "bind": {"verdicts": "steps.each-document.reason"},
                        },
                    },
                    "then": {"answered": "reply"},
                },
                "reply": {"does": "answer"},
            },
        })
    );
    comes_back_as_written(text);
}

#[test]
fn a_loop_that_goes_round_until_something_holds() {
    let text = "\
workflow search
  description: Search over ideas until one scores 0.9 or four rounds have run.
  takes problem: text
  rounds = repeat at most 4 times
    forks: yes
    until:
      - value: steps.score.best
        more-than: 0.9
    then:
      too-many-times: reply
    propose = call proposer with frontier: remembers.frontier
    score = call scorer with ideas: propose.ideas
  reply = answer with ideas: rounds.frontier
";
    let doc = read(text);
    let rounds = &doc["workflows"]["search"]["steps"]["rounds"];
    assert_eq!(rounds["does"], "repeat");
    assert_eq!(rounds["at-most"], 4);
    // What is written beneath the statement and what the order says are one
    // `then:` — the order adds `answered`, and does not take the other away.
    assert_eq!(rounds["then"], json!({"too-many-times": "reply", "answered": "reply"}));
    assert_eq!(rounds["starts-at"], "propose");
    assert_eq!(rounds["steps"]["propose"]["then"], json!({"answered": "score"}));
    assert_eq!(rounds["steps"]["propose"]["bind"], json!({"frontier": "remembers.frontier"}));
    assert_eq!(rounds["steps"]["score"]["bind"], json!({"ideas": "steps.propose.ideas"}));
    assert!(rounds["steps"]["score"].get("then").is_none(), "the last of a round ends the round");
    comes_back_as_written(text);
}

#[test]
fn a_decision_and_where_its_branches_come_back_together() {
    let text = "\
workflow route
  description: Send one message to the right desk.
  takes message: text, channel: text
  where = decide
    by:
      - { agent: sorter }
    if billing
      bill = call billing-desk with message: input.message
    if tech
      fix = call tech-desk with message: input.message
      note = call note-taker with what: fix.reply
    if out-of-scope: decline
  thanks = call thanker
  reply = answer
  decline = answer
";
    let doc = read(text);
    let steps = &doc["workflows"]["route"]["steps"];
    assert_eq!(
        steps["where"],
        json!({
            "does": "decide",
            "by": [{"agent": "sorter"}],
            "chooses-between": {"billing": "bill", "tech": "fix", "out-of-scope": "decline"},
        })
    );
    // The statements beneath an `if` are stages beside the decision, and the
    // last of each goes on to what is written after the `decide`.
    assert_eq!(steps["bill"]["then"], json!({"answered": "thanks"}));
    assert_eq!(steps["fix"]["then"], json!({"answered": "note"}));
    assert_eq!(steps["note"]["then"], json!({"answered": "thanks"}));
    assert_eq!(steps["thanks"]["then"], json!({"answered": "reply"}));
    assert!(steps["reply"].get("then").is_none(), "an answer goes nowhere");
    assert!(steps["decline"].get("then").is_none());
    assert_eq!(doc["workflows"]["route"]["starts-at"], "where");
}

#[test]
fn a_decision_whose_branches_each_end_comes_back_as_written() {
    comes_back_as_written(
        "\
workflow route
  description: Send one message to the right desk.
  where = decide
    by:
      - { agent: sorter }
    if billing
      bill = call billing-desk with message: input.message
      reply-bill = answer with reply: bill.reply
    if tech
      fix = call tech-desk with message: input.message
      reply-fix = answer with reply: fix.reply
    if out-of-scope: done
",
    );
    comes_back_as_written(
        "\
workflow route
  description: Two desks, one thank-you.
  where = decide
    by:
      - { agent: sorter }
    if billing
      bill = call billing-desk
    if tech
      fix = call tech-desk
      note = call note-taker with what: fix.reply
  thanks = call thanker
  answer
",
    );
}

#[test]
fn a_decision_says_what_its_agents_are_given_with_the_word_a_call_uses() {
    let text = "\
workflow fix-item
  description: Classify a defect and pick the team that takes it.
  takes report: text
  triage = call triager with report: input.report
  assign = decide with kind: triage.kind, summary: triage.summary, urgency: input.urgency
    by:
      - { agent: assigner }
    if powerplant: done
    if interiors: done
";
    let doc = read(text);
    let assign = &doc["workflows"]["fix-item"]["steps"]["assign"];
    assert_eq!(assign["does"], json!("decide"));
    // A step's name is read as `steps.<name>`, as after a `call … with`.
    assert_eq!(
        assign["bind"],
        json!({
            "kind": "steps.triage.kind",
            "summary": "steps.triage.summary",
            "urgency": "input.urgency",
        })
    );
    assert_eq!(
        assign["chooses-between"],
        json!({"powerplant": "done", "interiors": "done"})
    );
    comes_back_as_written(text);
    // With no name of its own, and an item given under the name the agent uses.
    comes_back_as_written(
        "\
workflow shelve
  description: Put every note on a shelf.
  takes notes: list of text
  for each item in input.notes
    decide with note: item
      by:
        - { agent: shelver }
      if bills: done
      if other: done
",
    );
    // `with` and nothing after it is not a line.
    let rules: Vec<&str> = refused(
        "\
workflow shelve
  description: Put every note on a shelf.
  decide with note
    if bills: done
",
    )
    .into_iter()
    .map(|(rule, _)| rule)
    .collect();
    assert!(rules.contains(&"lang/not-a-line"), "{rules:?}");
}

#[test]
fn starting_something_and_stopping_it_and_asking_a_person() {
    let text = "\
workflow work
  description: Work every task on the queue.
  watch = call queue/watch with queue: input.queue
    waits-for-result: no
  work = for each item in input.tasks
    keeps-taking: yes
    do = call queue/do with task: item.id
  halt-watch = stop watch.run
  ask is-it-done
  answer
";
    let doc = read(text);
    let steps = &doc["workflows"]["work"]["steps"];
    assert_eq!(steps["watch"]["waits-for-result"], "no");
    assert_eq!(steps["work"]["keeps-taking"], "yes");
    assert_eq!(steps["halt-watch"], json!({
        "does": "stop", "stops": "steps.watch.run", "then": {"answered": "ask-is-it-done"},
    }));
    assert_eq!(steps["ask-is-it-done"], json!({
        "does": "ask-someone", "asks": "is-it-done", "then": {"answered": "answer"},
    }));
    comes_back_as_written(text);
}

#[test]
fn how_an_agent_thinks_is_written_the_same_way() {
    let text = "\
loop careful
  description: Look things up, then read the decision back before answering.
  gather = use tools
    then:
      used-a-tool: gather
  re-read = check its work
    may-use: [zendesk, refund-policy]
    at-most: 2
    then:
      used-a-tool: re-read
  reply = answer
    then:
      answered: done
";
    let doc = read(text);
    let steps = &doc["loops"]["careful"]["steps"];
    assert_eq!(doc["loops"]["careful"]["starts-at"], "gather");
    assert_eq!(steps["gather"], json!({
        "does": "use-tools", "then": {"used-a-tool": "gather", "answered": "re-read"},
    }));
    assert_eq!(steps["re-read"]["then"], json!({"used-a-tool": "re-read", "answered": "reply"}));
    assert_eq!(steps["reply"], json!({"does": "answer", "then": {"answered": "done"}}));
    comes_back_as_written(text);
}

#[test]
fn a_then_written_beneath_a_statement_is_kept_over_the_order() {
    let doc = read(
        "\
workflow w
  description: The first step says where it goes.
  a = call one
    then: { answered: c }
  b = call two
  c = answer
",
    );
    let steps = &doc["workflows"]["w"]["steps"];
    assert_eq!(steps["a"]["then"], json!({"answered": "c"}));
    assert_eq!(steps["b"]["then"], json!({"answered": "c"}));
}

#[test]
fn a_figure_with_a_name_and_a_block_based_on_another() {
    let text = "\
let refund-limit = 200 USD

let rounds = 4

agent desk
  description: A desk.
  base: yes

agent refunds
  based on desk
  description: Decides refunds.

loop careful
  based on \"pact:loop/standard\"
  description: The standard shape.
";
    assert_eq!(
        read(text),
        json!({
            "values": {"refund-limit": {"value": "200 USD"}, "rounds": {"value": 4}},
            "agents": {
                "desk": {"description": "A desk.", "base": "yes"},
                "refunds": {"based-on": "desk", "description": "Decides refunds."},
            },
            "loops": {"careful": {
                "based-on": "pact:loop/standard",
                "description": "The standard shape.",
            }},
        })
    );
    let parsed = pact_lang::read(text, Utf8Path::new("t.pact"));
    let written = pact_lang::write(&parsed.node).unwrap().text;
    assert_eq!(read(&written), parsed.node.to_json(), "{written}");
    for line in ["let refund-limit = 200 USD", "let rounds = 4", "  based on desk", "  based on \"pact:loop/standard\""] {
        assert!(written.lines().any(|l| l == line), "no `{line}` in:\n{written}");
    }
    // A figure with more said about it is a block, and the two are one list.
    let both = read("let a = 1\n\nvalue b\n  description: The second.\n  value: 2\n");
    assert_eq!(both["values"], json!({"a": {"value": 1}, "b": {"description": "The second.", "value": 2}}));
}

#[test]
fn a_pattern_is_filled_in_on_the_line_that_names_it() {
    let text = "\
agent desk-pattern
  description: A desk that answers questions about <domain>.
  base: yes
  expects:
    domain:
      shape: text
    daily-cap:
      shape: money

agent refunds
  based on desk-pattern with domain: refunds, daily-cap: 0.05 USD, tries: 3
";
    assert_eq!(
        read(text)["agents"]["refunds"],
        json!({
            "based-on": "desk-pattern",
            "with": {"domain": "refunds", "daily-cap": "0.05 USD", "tries": 3},
        })
    );
    comes_back_as_written(text);
    // A figure with a comma in it is not said on the line, and still comes back.
    let awkward = "agent a\n  based-on: p\n  with:\n    words: one, two\n";
    let parsed = pact_lang::read(awkward, Utf8Path::new("t.pact"));
    let written = pact_lang::write(&parsed.node).unwrap().text;
    assert_eq!(read(&written), parsed.node.to_json(), "{written}");
    assert!(written.contains("  based on p\n  with:\n"), "{written}");
    assert_eq!(refused("agent a\n  based on p with refunds\n"), [("lang/not-a-line", 2)]);
}

#[test]
fn a_step_named_like_the_start_of_a_binding_keeps_its_steps() {
    let text = "\
workflow w
  description: A step called input.
  input = call reader
  answer with reply: steps.input.reply, asked: input.question
";
    let doc = read(text);
    assert_eq!(
        doc["workflows"]["w"]["steps"]["answer"]["bind"],
        json!({"reply": "steps.input.reply", "asked": "input.question"})
    );
    comes_back_as_written(text);
}

#[test]
fn stages_reached_another_way_are_written_after_the_ones_the_order_reaches() {
    // `a` goes on to `b`, as the order says. `b` goes BACK to `a`, which no
    // order can say, so it says so itself — and `c`, reached only when `a` has
    // run too many times, is written after them.
    comes_back_as_written(
        "\
workflow w
  description: Round and round.
  a = call one
    then:
      too-many-times: c
  b = call two
    then:
      answered: a
  c = answer
",
    );
}

#[test]
fn stages_no_statement_can_name_are_written_as_settings_and_still_come_back() {
    // A statement names its stage with one bare word. A stage called `my step`
    // cannot be written as one, so the whole workflow is written the long way.
    let text = "\
workflow w
  description: A stage with a space in its name.
  starts-at: my step
  steps:
    my step:
      does: call
      call: one
      then: { answered: c }
    c:
      does: answer
";
    let parsed = pact_lang::read(text, Utf8Path::new("t.pact"));
    assert!(parsed.diagnostics.is_empty());
    let written = pact_lang::write(&parsed.node).unwrap().text;
    assert_eq!(read(&written), parsed.node.to_json(), "{written}");
    assert!(written.contains("  steps:\n"), "{written}");
    assert!(!written.contains(" = call"), "{written}");
}

#[test]
fn statements_and_stages_written_as_settings_are_one_set_of_steps() {
    let doc = read(
        "\
workflow w
  description: One stage is written the long way.
  a = call one
    then: { answered: odd }
  steps:
    odd:
      does: answer
",
    );
    let steps = doc["workflows"]["w"]["steps"].as_object().unwrap();
    assert_eq!(steps.keys().collect::<Vec<_>>(), ["odd", "a"]);
}

#[test]
fn what_is_refused_and_on_which_line() {
    for (text, rule, line) in [
        // Two steps with one name.
        ("workflow w\n  call one\n  call one\n", "lang/said-twice", 3),
        // A loop that does not say what it goes through.
        ("workflow w\n  for each document in input.documents\n    call one\n", "lang/not-a-line", 2),
        // A name and nothing it names.
        ("workflow w\n  plan = something else\n", "lang/not-a-line", 2),
        // A repeat that does not say how many.
        ("workflow w\n  repeat forever\n    call one\n", "lang/not-a-line", 2),
        // An `if` with nothing to do.
        ("workflow w\n  decide\n    if billing\n", "lang/not-a-line", 3),
        // An `if` that says where it leads, twice.
        ("workflow w\n  decide\n    if billing: bill\n      call one\n", "lang/nothing-goes-under-this", 4),
        // A setting that belongs to no step.
        ("workflow w\n  decide\n    if billing\n      at-most: 2\n      call one\n", "lang/not-a-line", 4),
        // A call given something with no name.
        ("workflow w\n  call one with input.brief\n", "lang/not-a-line", 2),
        // A `let` that is not one figure.
        ("let limits = [1, 2]\n", "lang/not-a-line", 1),
        ("let limit\n", "lang/not-a-line", 1),
        ("let limit = 5\n  description: Five.\n", "lang/nothing-goes-under-this", 2),
        // A line a workflow does not know: the fix names the statements.
        ("workflow w\n  cal one\n", "lang/not-a-line", 2),
    ] {
        assert_eq!(refused(text), [(rule, line)], "{text}");
    }
}

#[test]
fn the_fix_for_a_line_a_workflow_does_not_know_names_the_nearest_statement() {
    let parsed = pact_lang::read("workflow w\n  cal one\n", Utf8Path::new("t.pact"));
    assert_eq!(parsed.diagnostics[0].fix, "Did you mean a line starting `call`?");
}
