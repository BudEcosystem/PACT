//! Topics, events and reactions (`docs/99-THE-PACT-LANGUAGE.md` §3.3): the laws
//! `pact check` holds, each driven against `examples/kernel/finance-first` with
//! one line changed.

use std::path::{Path, PathBuf};
use std::process::Command;

fn copy(from: &Path, to: &Path) {
    std::fs::create_dir_all(to).unwrap();
    for entry in std::fs::read_dir(from).unwrap() {
        let entry = entry.unwrap();
        let target = to.join(entry.file_name());
        if entry.file_type().unwrap().is_dir() {
            copy(&entry.path(), &target);
        } else {
            std::fs::copy(entry.path(), target).unwrap();
        }
    }
}

/// The shipped example with `file` replaced by `text` (or added).
fn tree(name: &str, file: &str, text: &str) -> PathBuf {
    let src = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../examples/kernel/finance-first");
    let dst = std::env::temp_dir().join(format!("pact-react-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&src, &dst);
    let at = dst.join(file);
    std::fs::create_dir_all(at.parent().unwrap()).unwrap();
    std::fs::write(at, text).unwrap();
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

fn refused(name: &str, file: &str, text: &str, rule: &str) -> String {
    let (ok, said) = check(&tree(name, file, text));
    assert!(!ok, "{name} loaded, and `{rule}` should have refused it:\n{said}");
    assert!(said.contains(&format!("rule: {rule}")), "{name}: no `{rule}` in:\n{said}");
    said
}

const WRAP_UP: &str = "reactions/wrap-up.yaml";

#[test]
fn the_shipped_example_loads_with_no_warnings() {
    let src = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../examples/kernel/finance-first");
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(["check", src.to_str().unwrap(), "--deny-warnings"])
        .output()
        .unwrap();
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stdout));
}

#[test]
fn a_reaction_that_waits_for_nothing_is_refused() {
    let said = refused(
        "nothing",
        WRAP_UP,
        "description: Nudge.\nthen:\n  - remind: Finish.\n",
        "loader/a-signal-says-one-thing",
    );
    assert!(said.contains("does not say what it waits for"), "{said}");
}

#[test]
fn a_reaction_that_waits_for_two_things_is_refused() {
    refused(
        "two",
        WRAP_UP,
        "description: Nudge.\nat: step.run.started\ntopic: finance\nthen:\n  - remind: Finish.\n",
        "loader/a-signal-says-one-thing",
    );
    // An event named, and something else said here as well.
    refused(
        "event-and-more",
        WRAP_UP,
        "description: Nudge.\nevent: refund-issued\nat: step.run.started\nthen:\n  - remind: Finish.\n",
        "loader/a-signal-says-one-thing",
    );
}

#[test]
fn a_narrowing_needs_a_moment_about_a_call() {
    let said = refused(
        "no-call",
        WRAP_UP,
        "description: Nudge.\nat: step.run.started\nwhen-this:\n  - { tool: billing/issue-refund }\nthen:\n  - remind: Finish.\n",
        "loader/a-narrowing-with-nothing-to-narrow",
    );
    assert!(said.contains("`step.run.started` is not a moment that is about a call"), "{said}");
    refused(
        "beside-a-topic",
        WRAP_UP,
        "description: Nudge.\ntopic: finance\nmore-than: 2\nthen:\n  - remind: Finish.\n",
        "loader/a-narrowing-with-nothing-to-narrow",
    );
    refused(
        "a-value",
        WRAP_UP,
        "description: Nudge.\nat: step.tool.before\nwhen-this:\n  - { value: input.x, is: y }\nthen:\n  - remind: Finish.\n",
        "loader/a-narrowing-with-nothing-to-narrow",
    );
}

#[test]
fn a_signal_names_a_call_that_is_there() {
    let said = refused(
        "no-tool",
        WRAP_UP,
        "description: Nudge.\nat: step.tool.before\nwhen-this:\n  - { tool: biling/issue-refund }\nthen:\n  - remind: Finish.\n",
        "loader/a-signal-names-no-such-call",
    );
    assert!(said.contains("Did you mean `billing`?"), "{said}");
    let said = refused(
        "no-action",
        WRAP_UP,
        "description: Nudge.\nat: step.tool.before\nwhen-this:\n  - { tool: billing/refund }\nthen:\n  - remind: Finish.\n",
        "loader/a-signal-names-no-such-call",
    );
    assert!(said.contains("The actions of 'billing' are"), "{said}");
    // The whole tool, with no action, is every call to it — and that loads.
    let (ok, said) = check(&tree(
        "whole-tool",
        WRAP_UP,
        "description: Nudge.\nat: step.tool.before\nwhen-this:\n  - { tool: billing }\nthen:\n  - remind: Careful.\n",
    ));
    assert!(ok, "{said}");
}

#[test]
fn a_judge_reads_words() {
    refused(
        "judged-at-a-call",
        "reactions/upset-customer.yaml",
        "description: The customer is upset.\njudged: yes\nat: step.tool.before\nthen:\n  - remind: Apologise.\n",
        "loader/a-judge-reads-words",
    );
}

#[test]
fn a_guess_does_not_stop_a_run() {
    let said = refused(
        "judged-stop",
        "reactions/upset-customer.yaml",
        "description: The customer is upset.\njudged: yes\nat: turn.run.started\nthen:\n  - stop: Goodbye.\n",
        "loader/a-guess-cannot-stop",
    );
    assert!(said.contains("it is judged, and a judge can be wrong"), "{said}");
    // The topic `finance` is noticed by tags AND by the agent, so it can be a guess.
    let said = refused(
        "topic-stop",
        WRAP_UP,
        "description: No finance here.\ntopic: finance\nthen:\n  - stop: Not here.\n",
        "loader/a-guess-cannot-stop",
    );
    assert!(said.contains("noticed by the agent"), "{said}");
    // On an exact moment, stopping is what it says.
    let (ok, said) = check(&tree(
        "exact-stop",
        WRAP_UP,
        "description: One refund a request.\nat: step.tool.before\nwhen-this:\n  - { tool: billing/issue-refund }\nmore-than: 1\nthen:\n  - stop: A second refund needs a person.\n",
    ));
    assert!(ok, "{said}");
}

#[test]
fn a_step_does_one_thing() {
    refused(
        "two-verbs",
        WRAP_UP,
        "description: Nudge.\nat: step.run.started\nthen:\n  - { remind: Finish., tell: auditor }\n",
        "loader/a-step-does-one-thing",
    );
}

#[test]
fn a_reaction_that_only_wakes_the_agent_naming_it_is_refused() {
    let said = refused(
        "itself",
        WRAP_UP,
        "description: Ask support.\nat: step.run.started\nthen:\n  - consult: support\n",
        "loader/asks-only-itself",
    );
    assert!(said.contains("never woken by its own work"), "{said}");
}

#[test]
fn a_topic_nothing_carries_and_a_tag_nobody_reads() {
    let (ok, said) = check(&tree(
        "untagged",
        "topics/legal.yaml",
        "description: Legal questions.\n",
    ));
    assert!(ok, "a warning, not a refusal:\n{said}");
    assert!(said.contains("rule: loader/a-topic-nothing-carries"), "{said}");

    let said = refused(
        "unread-tag",
        "topics/finance.yaml",
        "description: Money.\nnoticed-by: [the-agent]\n",
        "loader/a-tag-nobody-reads",
    );
    assert!(said.contains("leaves out `tags`"), "{said}");
}

#[test]
fn a_reaction_an_event_and_a_topic_nothing_names_are_told() {
    let (ok, said) = check(&tree(
        "unnamed",
        "reactions/spare.yaml",
        "description: Spare.\nat: step.run.started\nthen:\n  - remind: x\n",
    ));
    assert!(ok, "{said}");
    assert!(said.contains("'spare' is a reaction that nothing here names"), "{said}");
    let (_, said) = check(&tree(
        "unnamed-event",
        "events/spare.yaml",
        "description: Spare.\nat: step.run.started\n",
    ));
    assert!(said.contains("'spare' is a event that nothing here names")
        || said.contains("'spare' is an event that nothing here names"), "{said}");
}

#[test]
fn a_listens_for_line_names_a_topic_or_an_event() {
    refused(
        "both",
        "agents/auditor/agent.yaml",
        "description: Keeps a note.\ninstructions: Note it.\nlistens-for:\n  - { topic: finance, event: refund-issued, how: told-after }\n",
        "loader/a-signal-says-one-thing",
    );
    refused(
        "no-such-event",
        "agents/auditor/agent.yaml",
        "description: Keeps a note.\ninstructions: Note it.\nlistens-for:\n  - { event: refund-isued, how: told-after }\n",
        "schema/no-such-name",
    );
}

#[test]
fn a_moment_nothing_stops_at_is_refused_by_the_address_list() {
    let (ok, said) = check(&tree(
        "unreachable",
        WRAP_UP,
        "description: Nudge.\nat: turn.message.after\nthen:\n  - remind: Finish.\n",
    ));
    assert!(!ok, "{said}");
    assert!(said.contains("rule: schema/nothing-happens-there"), "{said}");
}

#[test]
fn an_agent_that_is_told_is_reached_for_a_leak_the_way_a_teammate_is() {
    // `reader` reaches records and the open web, and has no way out. `mailer`
    // has the way out and asks to be told about everything `reader` looks up —
    // so what a stranger wrote on a web page is put in front of an agent that
    // can send mail, and nobody stands at the door. Nothing in `reader`'s own
    // file names `mailer`; the edge is the subscription.
    let dir = std::env::temp_dir().join(format!("pact-react-leak-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    let workspace = |told: &str| {
        format!(
            "name: Leak\n\
             resources:\n  office: {{ resource-kind: mcp-server, endpoint: host/office, description: Office. }}\n\
             tools:\n\
             \x20 crm: {{ description: Records., connect: office, carries: [private-data], actions: {{ look-up: {{ description: Look., reads-only: yes }} }} }}\n\
             \x20 web: {{ description: The web., connect: office, carries: [untrusted-content], actions: {{ fetch: {{ description: Fetch., reads-only: yes }} }} }}\n\
             \x20 mail: {{ description: Mail., connect: office, carries: [a-way-out], actions: {{ send: {{ description: Send. }} }} }}\n\
             events:\n  looked-up: {{ description: A record was read., at: step.tool.completed, when-this: [{{ tool: crm/look-up }}] }}\n\
             agents:\n\
             \x20 reader: {{ description: Reads., instructions: Read., uses: [crm, web] }}\n\
             \x20 mailer: {{ description: Mails., instructions: Mail., uses: [mail]{told} }}\n"
        )
    };
    std::fs::write(
        dir.join("workspace.yaml"),
        workspace(", listens-for: [{ event: looked-up, how: told-after }]"),
    )
    .unwrap();
    let (ok, said) = check(&dir);
    assert!(!ok, "{said}");
    assert!(said.contains("rule: loader/three-things-that-make-a-leak"), "{said}");
    assert!(said.contains("'reader' can reach"), "{said}");

    // Without the subscription the two agents are strangers, and it loads.
    std::fs::write(dir.join("workspace.yaml"), workspace("")).unwrap();
    let (_, said) = check(&dir);
    assert!(!said.contains("three-things-that-make-a-leak"), "{said}");
}
