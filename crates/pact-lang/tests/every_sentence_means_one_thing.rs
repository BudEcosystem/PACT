//! Each sentence of the PACT language, held to the fields it stands for
//! (`docs/99-THE-PACT-LANGUAGE.md` §4.3) — and to coming back out of
//! `pact_lang::write` as the sentence it went in as.

use camino::Utf8Path;
use serde_json::{Value, json};

fn read(text: &str) -> Value {
    let parsed = pact_lang::read(text, Utf8Path::new("t.pact"));
    let said: Vec<String> = parsed.diagnostics.iter().map(|d| d.message.clone()).collect();
    assert!(said.is_empty(), "{text}\n{said:?}");
    parsed.node.to_json()
}

fn refused(text: &str) -> Vec<&'static str> {
    pact_lang::read(text, Utf8Path::new("t.pact")).diagnostics.iter().map(|d| d.rule).collect()
}

/// Read `text`, write what was read, and read that: the same document, twice.
fn there_and_back(text: &str) -> String {
    let parsed = pact_lang::read(text, Utf8Path::new("t.pact"));
    assert!(parsed.diagnostics.is_empty(), "{text}");
    let written = pact_lang::write(&parsed.node).unwrap();
    assert_eq!(read(&written.text), parsed.node.to_json(), "{}", written.text);
    written.text
}

#[test]
fn an_agent_s_sentences() {
    let text = "\
agent desk \"The Desk\"
  description: Decides refunds.
  takes message: text, photos: list of images
  gives decision: one of approved, declined, reason: text
  uses zendesk, payments
  asks checker: Checks the request against the policy.
  asks finder: Looks for the order.
  at most 8 steps
  at most 20 tool calls
  spends under 0.50 USD a request
  when it runs out: stop and say so
  listens for topic finance: asked first
  listens for event refund-issued: told after
  remembers what-was-said
    description: What the customer said.
    lasts: one-conversation
  instructions
    Read the ticket.

    # Then decide
      and say why.
";
    assert_eq!(
        read(text),
        json!({"agents": {"desk": {
            "name": "The Desk",
            "description": "Decides refunds.",
            "accepts": {"message": "text", "photos": "list of images"},
            "answers-with": {"decision": "one of approved, declined", "reason": "text"},
            "uses": ["zendesk", "payments"],
            "team": {
                "checker": "Checks the request against the policy.",
                "finder": "Looks for the order.",
            },
            "limits": {
                "steps-at-most": 8,
                "tool-calls-at-most": 20,
                "cost-per-request-under": "0.50 USD",
                "when-it-runs-out": "stop-and-say-so",
            },
            "listens-for": [
                {"topic": "finance", "how": "asked-first"},
                {"event": "refund-issued", "how": "told-after"},
            ],
            "remembers": {"what-was-said": {
                "description": "What the customer said.",
                "lasts": "one-conversation",
            }},
            "instructions": "Read the ticket.\n\n# Then decide\n  and say why.",
        }}})
    );
    // And every one of those lines is written back as the sentence it was.
    let back = there_and_back(text);
    for line in text.lines().filter(|l| !l.trim().is_empty()) {
        assert!(back.contains(line.trim_end()), "`{line}` did not come back in:\n{back}");
    }
}

#[test]
fn a_sentence_and_a_setting_add_to_the_same_limits() {
    let doc = read(
        "agent desk\n  at most 8 steps\n  limits:\n    feel: interactive\n    asks: keep-going\n",
    );
    assert_eq!(
        doc["agents"]["desk"]["limits"],
        json!({"steps-at-most": 8, "feel": "interactive", "asks": "keep-going"})
    );
    assert_eq!(
        refused("agent desk\n  at most 8 steps\n  limits:\n    steps-at-most: 9\n"),
        ["lang/said-twice"]
    );
    assert_eq!(refused("agent desk\n  uses a\n  uses: [b]\n"), ["lang/said-twice"]);
    assert_eq!(refused("agent desk\n  description: a\n\nagent desk\n  description: b\n"), ["lang/said-twice"]);
}

#[test]
fn what_a_tool_is_about_and_when_a_person_is_asked() {
    let text = "\
tool billing
  description: Invoices.
  about finance, tax

policy approvals
  applies-to: every-agent
  before billing/send: ask is-this-ok, because nothing is sent unread
  before billing/refund, when amount is more than 200 USD: ask is-this-ok, because a refund over 200 USD is a management decision
  before leads/score, when score is less than 80: ask review, because low scores are read
  before crm/update, when tier is enterprise: ask review, because enterprise accounts are handled by hand
";
    let doc = read(text);
    assert_eq!(doc["tools"]["billing"]["topics"], json!(["finance", "tax"]));
    assert_eq!(
        doc["policies"]["approvals"]["ask-a-person"],
        json!([
            {"when": [{"tool": "billing/send"}], "because": "nothing is sent unread", "question": "is-this-ok"},
            {"when": [{"tool": "billing/refund", "arg": "amount", "more-than": "200 USD"}],
             "because": "a refund over 200 USD is a management decision", "question": "is-this-ok"},
            {"when": [{"tool": "leads/score", "arg": "score", "less-than": 80}],
             "because": "low scores are read", "question": "review"},
            {"when": [{"tool": "crm/update", "arg": "tier", "is": "enterprise"}],
             "because": "enterprise accounts are handled by hand", "question": "review"},
        ])
    );
    let back = there_and_back(text);
    for line in text.lines().filter(|l| l.contains("before ") || l.contains("about ")) {
        assert!(back.contains(line.trim_end()), "`{line}` did not come back in:\n{back}");
    }
}

#[test]
fn every_signal_a_when_can_say() {
    for (sentence, fields) in [
        ("the agent is about to call invoices/send",
         json!({"at": "step.tool.before", "when-this": [{"tool": "invoices/send"}]})),
        ("the agent has called payments more than 1 times",
         json!({"at": "step.tool.before", "when-this": [{"tool": "payments"}], "more-than": 1})),
        ("billing/issue-refund has answered",
         json!({"at": "step.tool.completed", "when-this": [{"tool": "billing/issue-refund"}]})),
        ("the agent has taken more than 5 steps", json!({"at": "step.run.started", "more-than": 5})),
        ("a turn starts", json!({"at": "turn.run.started"})),
        ("the agent is about to ask a teammate", json!({"at": "step.delegate.before"})),
        ("the agent has written a step", json!({"at": "step.message.after"})),
        ("the work touches finance", json!({"topic": "finance"})),
        ("refund-issued happens", json!({"event": "refund-issued"})),
    ] {
        let text = format!("when {sentence}\n  remind it: Take care.\n");
        let id = pact_lang::slug(sentence);
        let mut want = fields.clone();
        want["description"] = json!(format!("When {sentence}."));
        want["applies-to"] = json!("every-agent");
        want["then"] = json!([{"remind": "Take care."}]);
        assert_eq!(read(&text), json!({"reactions": {id: want}}), "{sentence}");
        assert_eq!(there_and_back(&text), text, "{sentence}");
    }
}

#[test]
fn a_judgement_s_sentence_is_the_question_the_judge_answers() {
    let text = "when it looks like the customer is angry or upset\n  remind it: Apologise once.\n";
    assert_eq!(
        read(text),
        json!({"reactions": {"it-looks-like-the-customer-is-angry-or-upset": {
            "judged": "yes",
            "description": "The customer is angry or upset.",
            "applies-to": "every-agent",
            "then": [{"remind": "Apologise once."}],
        }}})
    );
    assert_eq!(there_and_back(text), text);
    // A description of its own wins, and where the judge reads is a setting.
    let text = "\
when it looks like the customer is rude
  called rude
  description: Is the customer being abusive to staff?
  at: turn.run.started
  remind it: Stay polite.
";
    let doc = read(text);
    assert_eq!(doc["reactions"]["rude"]["description"], "Is the customer being abusive to staff?");
    assert_eq!(doc["reactions"]["rude"]["at"], "turn.run.started");
    there_and_back(text);
}

#[test]
fn what_a_reaction_does_and_what_it_is_called() {
    let text = "\
when the work touches finance
  called finance-first
  every time
  consult finance-desk
  tell auditor
  remind it: Keep the order number.
  stop and say: This needs a person.
";
    assert_eq!(
        read(text)["reactions"]["finance-first"],
        json!({
            "topic": "finance",
            "fires": "every-time",
            "then": [
                {"consult": "finance-desk"},
                {"tell": "auditor"},
                {"remind": "Keep the order number."},
                {"stop": "This needs a person."},
            ],
            "description": "When the work touches finance.",
            "applies-to": "every-agent",
        })
    );
    assert_eq!(there_and_back(text), text);
}

#[test]
fn a_when_inside_an_agent_is_one_that_agent_names() {
    let text = "\
agent desk
  description: Helps.
  when the agent has taken more than 5 steps
    remind it: Finish.
  when the work touches finance
    called finance-first
    consult finance-desk
";
    assert_eq!(
        read(text),
        json!({
            "agents": {"desk": {
                "description": "Helps.",
                "reactions": ["the-agent-has-taken-more-than-5-steps", "finance-first"],
            }},
            "reactions": {
                "the-agent-has-taken-more-than-5-steps": {
                    "at": "step.run.started", "more-than": 5,
                    "description": "When the agent has taken more than 5 steps.",
                    "then": [{"remind": "Finish."}],
                },
                "finance-first": {
                    "topic": "finance",
                    "description": "When the work touches finance.",
                    "then": [{"consult": "finance-desk"}],
                },
            },
        })
    );
    assert_eq!(there_and_back(text), text);
}

#[test]
fn a_reaction_two_agents_name_is_a_block_of_its_own() {
    let text = "\
agent a
  description: A.
  reactions: [wrap-up]

agent b
  description: B.
  reactions: [wrap-up]

reaction wrap-up
  when the agent has taken more than 5 steps
  description: Long runs are told to finish.
  remind it: Finish.

event refund-issued
  when billing/issue-refund has answered
  description: A refund has gone out.
";
    let doc = read(text);
    assert_eq!(doc["reactions"]["wrap-up"]["at"], "step.run.started");
    assert!(doc["reactions"]["wrap-up"].get("applies-to").is_none());
    assert_eq!(doc["events"]["refund-issued"]["when-this"], json!([{"tool": "billing/issue-refund"}]));
    assert_eq!(there_and_back(text), text);
}

#[test]
fn a_signal_no_sentence_says_is_written_as_settings_and_still_comes_back() {
    let text = "\
reaction big-refund
  description: A large refund is about to go out.
  at: step.tool.before
  when-this:
    - { tool: billing/issue-refund, arg: amount, more-than: 200 USD }
  consult finance-desk
";
    assert_eq!(
        read(text)["reactions"]["big-refund"]["when-this"],
        json!([{"tool": "billing/issue-refund", "arg": "amount", "more-than": "200 USD"}])
    );
    assert_eq!(there_and_back(text), text);
}

#[test]
fn the_workspace_its_single_documents_and_anything_else_as_settings() {
    let text = "\
workspace \"Refund Desk\"
  description: Decides refunds.
  allow-egress: []

redaction
  hides: [card number]

watch tool-calls
  description: Records every tool call.
  when: step.tool.completed
  writes-to: tool-calls.jsonl
";
    assert_eq!(
        read(text),
        json!({
            "name": "Refund Desk",
            "description": "Decides refunds.",
            "allow-egress": [],
            "redaction": {"hides": ["card number"]},
            "watch": {"tool-calls": {
                "description": "Records every tool call.",
                "when": "step.tool.completed",
                "writes-to": "tool-calls.jsonl",
            }},
        })
    );
    assert_eq!(there_and_back(text), text);
}

#[test]
fn text_no_bare_line_could_hold_is_quoted_and_comes_back() {
    // Values a sentence or a bare setting would misread: each must survive.
    let mut agent = serde_json::Map::new();
    agent.insert("description".into(), json!("ends with a colon:"));
    agent.insert("instructions".into(), json!("trailing newline\n"));
    agent.insert("accepts".into(), json!({"note": "a: b, c: d"}));
    agent.insert("uses".into(), json!(["has, comma"]));
    agent.insert("team".into(), json!({"helper": " leading space"}));
    agent.insert("limits".into(), json!({"steps-at-most": "eight", "when-it-runs-out": "has space"}));
    let text = format!(
        "agent \"odd name\"\n{}",
        agent
            .iter()
            .map(|(k, v)| format!("  {k}: {v}\n"))
            .collect::<String>()
    );
    let doc = read(&text);
    assert_eq!(doc["agents"]["odd name"], Value::Object(agent));
    there_and_back(&text);
}

#[test]
fn a_comment_ends_a_header_or_a_sentence_and_is_text_inside_a_text_block() {
    let doc = read(
        "# The desk.\n\
         agent desk \"The Desk\"   # who answers\n\
         \x20 uses zendesk, payments  # the two systems\n\
         \x20 description: Helps.     # a setting's comment is YAML's\n\
         \x20 when the work touches finance   # exact: a tagged tool\n\
         \x20   remind it: Quote \"order #12\" exactly. # and this is a comment\n\
         \x20 instructions\n\
         \x20   # A heading\n\
         \x20   Read ticket #4 first.  # not a comment\n",
    );
    let desk = &doc["agents"]["desk"];
    assert_eq!(desk["name"], "The Desk");
    assert_eq!(desk["uses"], json!(["zendesk", "payments"]));
    assert_eq!(desk["description"], "Helps.");
    assert_eq!(desk["instructions"], "# A heading\nRead ticket #4 first.  # not a comment");
    assert_eq!(
        doc["reactions"]["the-work-touches-finance"]["then"],
        json!([{"remind": "Quote \"order #12\" exactly."}])
    );
    // Text that a comment would cut is written as a setting, and comes back whole.
    let text = "reaction r\n  description: d\n  at: step.run.started\n  then:\n    - remind: \"see ticket #9\"\n";
    assert_eq!(read(text)["reactions"]["r"]["then"], json!([{"remind": "see ticket #9"}]));
    let back = there_and_back(text);
    assert!(!back.contains("remind it:"), "{back}");
}

#[test]
fn a_name_with_a_space_in_it_is_written_in_quotes() {
    let text = "agent \"night desk\" \"The Night Desk\"\n  description: Answers at night.\n";
    assert_eq!(
        read(text),
        json!({"agents": {"night desk": {"name": "The Night Desk", "description": "Answers at night."}}})
    );
    assert_eq!(there_and_back(text), text);
    assert_eq!(refused("agent \"night desk\n  description: x\n"), ["lang/a-quote-left-open"]);
    assert_eq!(refused("tool billing \"Billing\"\n  description: x\n"), ["lang/a-second-name"]);
}
