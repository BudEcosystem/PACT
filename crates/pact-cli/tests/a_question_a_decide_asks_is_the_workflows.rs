//! End-to-end: a workspace question that a `decide`'s person rung asks
//! (`by: [- asks: <question>]`) is a question the workflow asks
//! (`pact-loader/src/waits.rs`, `asked_by_workflows`). Before, only a stage's,
//! a limit's and a failure plan's `asks:` counted, so such a question was read
//! as an agent's: it had to say `if-nobody-answers:`, and what it said there
//! (`escalate`, say) loaded clean and was never read, since a decide's silence
//! stops the run (found by Bud Agent Flow's *Sort and route an inbox*
//! template). A question nothing asks yet (a tree begun from a template, its
//! `decide` not written) is held to neither reader's lines: the line an agent
//! would need is the one a workflow refuses. Driven against the shipped
//! `workflows-48-invoices` tree, its sorter's question moved out of the
//! workflow into `questions/`.

use std::path::{Path, PathBuf};
use std::process::Command;

const QUESTION: &str = "  what-is-this-attachment:
    description: An AP clerk sorts an attachment the classifier was unsure of.
    says: Is this attachment a supplier invoice?
    shows: [item.name]
    answer:
      label: one of invoice, other
    asked-of: [ap-clerks]
    answer-within: 1 day
";

fn copy(src: &Path, dst: &Path) {
    std::fs::create_dir_all(dst).unwrap();
    for entry in std::fs::read_dir(src).unwrap() {
        let entry = entry.unwrap();
        let to = dst.join(entry.file_name());
        if entry.file_type().unwrap().is_dir() {
            copy(&entry.path(), &to);
        } else {
            std::fs::copy(entry.path(), to).unwrap();
        }
    }
}

/// The tree with the rung's question in `questions/`, `more` written under it.
fn moved(name: &str, more: &str) -> PathBuf {
    let src = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/trees/workflows-48-invoices");
    let dst =
        std::env::temp_dir().join(format!("pact-rung-question-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&src, &dst);
    let flow = dst.join("workflows/ap-inbox.yaml");
    let text = std::fs::read_to_string(&flow).unwrap();
    assert!(text.contains(QUESTION), "the shipped question changed");
    std::fs::write(&flow, text.replacen(QUESTION, "", 1)).unwrap();
    let body: String = QUESTION
        .lines()
        .skip(1)
        .map(|l| format!("{}\n", l.strip_prefix("    ").unwrap_or(l)))
        .collect();
    std::fs::create_dir_all(dst.join("questions")).unwrap();
    std::fs::write(
        dst.join("questions/what-is-this-attachment.yaml"),
        format!("{body}{more}"),
    )
    .unwrap();
    dst
}

fn check(tree: &Path) -> (bool, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .arg("check")
        .arg(tree)
        .output()
        .unwrap();
    let said =
        String::from_utf8_lossy(&out.stdout).to_string() + &String::from_utf8_lossy(&out.stderr);
    (out.status.success(), said)
}

#[test]
fn a_rungs_workspace_question_is_written_as_a_workflows_is() {
    let (ok, said) = check(&moved("as-a-workflows", ""));
    assert!(ok, "{said}");
}

#[test]
fn what_a_rungs_question_says_of_silence_is_refused_as_nothing_reads_it() {
    let more = "if-nobody-answers: escalate\nescalates-to: [ap-leads]\n";
    let (ok, said) = check(&moved("escalates", more));
    assert!(!ok, "{said}");
    assert!(said.contains("loader/an-agent-only-spelling"), "{said}");
    assert!(
        said.contains("a `decide`'s person rung, which has no exit, stops the run"),
        "{said}"
    );
    assert!(said.contains("hands-over-to:"), "{said}");
}

#[test]
fn a_question_nothing_asks_yet_is_only_said_to_take_no_effect() {
    let tree = moved("unasked", "");
    let body =
        std::fs::read_to_string(tree.join("questions/what-is-this-attachment.yaml")).unwrap();
    std::fs::write(tree.join("questions/a-spare-question.yaml"), body).unwrap();
    let (ok, said) = check(&tree);
    assert!(ok, "{said}");
    assert!(
        said.contains("'a-spare-question' is a question that nothing here names"),
        "{said}"
    );
    assert!(!said.contains("if-nobody-answers"), "{said}");
}

/// A question only a workflow's `policy:` asks, through an `ask-a-person`
/// rule on one of its calls: the gate's runtime reads `if-nobody-answers:`
/// (Bud Agent Flow's `gates`), so it is held to it as an agent's question is,
/// not let through as a question nothing asks.
fn gated(name: &str, more: &str) -> PathBuf {
    let tree = moved(name, "");
    let body =
        std::fs::read_to_string(tree.join("questions/what-is-this-attachment.yaml")).unwrap();
    std::fs::write(
        tree.join("questions/sign-off-payment.yaml"),
        format!("{body}{more}"),
    )
    .unwrap();
    std::fs::create_dir_all(tree.join("policies")).unwrap();
    std::fs::write(
        tree.join("policies/payment-sign-off.yaml"),
        "ask-a-person:\n  - when:\n      - { tool: bill-com/schedule-payment }\n    \
         because: a clerk signs off each payment\n    question: sign-off-payment\n",
    )
    .unwrap();
    let flow = tree.join("workflows/one-invoice.yaml");
    let text = std::fs::read_to_string(&flow).unwrap();
    std::fs::write(&flow, format!("policy: payment-sign-off\n{text}")).unwrap();
    tree
}

#[test]
fn a_question_a_workflows_policy_asks_must_say_what_silence_does() {
    let (ok, said) = check(&gated("policy-silent", ""));
    assert!(!ok, "{said}");
    assert!(
        said.contains("A question must have an 'if-nobody-answers'"),
        "{said}"
    );
    let (ok, said) = check(&gated("policy-says", "if-nobody-answers: decline\n"));
    assert!(ok, "{said}");
}

/// A question only a resource's `asks-to-connect:` names, the resource reached
/// through a tool only a workflow calls (Pattern AP10 with its agent swapped
/// for a workflow). The consent gate reads `if-nobody-answers:` whoever's call
/// opens the connection, so the question is held to it: it was let through as
/// one nothing asks, because only an agent's or a policy's asking counted.
fn consent(name: &str, more: &str) -> PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-consent-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    for (path, text) in [
        (
            "workspace.yaml",
            "name: consent\nworkspace-id: 01K6PACTCONSENTWORKFLOW0000\n\
             description: Reads incidents once somebody allowed the connection.\n\
             owner: tests\nallow-egress: []\n",
        ),
        (
            "resources/incident-server.yaml",
            "resource-kind: mcp-server\nendpoint: host/incidents-mcp\n\
             description: The incident system.\nasks-to-connect: may-we-connect\n",
        ),
        (
            "tools/incidents.yaml",
            "description: Incident records.\nconnect: incident-server\nactions:\n  \
             read-incident:\n    description: Read one incident.\n    takes:\n      \
             incident-id: text\n    reads-only: yes\n",
        ),
        (
            "workflows/read-one.yaml",
            "description: Reads one incident.\naccepts:\n  incident-id: text\n\
             answers-with:\n  status: text\nstarts-at: look\nsteps:\n  look:\n    \
             does: call\n    call: incidents/read-incident\n    bind:\n      \
             incident-id: input.incident-id\n    then:\n      answered: reply\n  \
             reply:\n    does: answer\n    bind:\n      status: steps.look.status\n",
        ),
    ] {
        let to = dst.join(path);
        std::fs::create_dir_all(to.parent().unwrap()).unwrap();
        std::fs::write(to, text).unwrap();
    }
    std::fs::create_dir_all(dst.join("questions")).unwrap();
    std::fs::write(
        dst.join("questions/may-we-connect.yaml"),
        format!(
            "description: Asks whether we may connect.\nsays: May we read incidents?\n\
             answer:\n  approved: yes or no\nasked-of: [platform-operations]\n\
             answer-within: 1h\n{more}"
        ),
    )
    .unwrap();
    dst
}

#[test]
fn a_question_a_workflows_connection_asks_must_say_what_silence_does() {
    let (ok, said) = check(&consent("silent", ""));
    assert!(!ok, "{said}");
    assert!(
        said.contains("A question must have an 'if-nobody-answers'"),
        "{said}"
    );
    let (ok, said) = check(&consent("says", "if-nobody-answers: stop-and-say-so\n"));
    assert!(ok, "{said}");
}
