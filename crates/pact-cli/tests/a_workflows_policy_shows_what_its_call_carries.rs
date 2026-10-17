//! A question a WORKFLOW's `policy:` puts is held to the call it is about, as
//! an agent's is: a `shows:` name the gated action is not given is dropped in
//! silence at run time (`Question.about_call` keeps `k in args`), so the
//! loader says so. Only agents' parks were walked, and budflow's corpus #103
//! showed the incident commander `item.blast-radius`, a name no call carries,
//! with nothing said.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

/// A workflow that suspends a user once its policy's question is answered.
const TREE: &[(&str, &str)] = &[
    (
        "workspace.yaml",
        r#"name: containment
description: Suspends a user once the incident commander says yes.
allow-egress: []
"#,
    ),
    (
        "resources/okta-server.yaml",
        r#"resource-kind: mcp-server
endpoint: host/okta-server
description: Where Okta is served.
"#,
    ),
    (
        "tools/okta.yaml",
        r#"description: Okta administration.
connect: okta-server
actions:
  suspend-user:
    description: Suspend one user.
    takes:
      user: text
      blast-radius: text
    answers-with:
      said: text
"#,
    ),
    (
        "policies/approve-suspensions.yaml",
        r#"ask-a-person:
  - when:
      - { tool: okta/suspend-user }
    because: suspending a user locks them out
    question: approve-suspension
"#,
    ),
    (
        "questions/approve-suspension.yaml",
        r#"description: The incident commander approves one suspension.
says: Suspend this user?
answer:
  approved: yes or no
shows: [user, blast-radius]
asked-of: [incident-commander]
answer-within: 30m
if-nobody-answers: decline
"#,
    ),
    (
        "workflows/contain.yaml",
        r#"description: Suspends one user, after the incident commander's yes.
accepts:
  user: text
  blast-radius: text
answers-with:
  said: text
policy: approve-suspensions
starts-at: suspend
steps:
  suspend:
    does: call
    call: okta/suspend-user
    bind:
      user: input.user
      blast-radius: input.blast-radius
    then:
      answered: reply
  reply:
    does: answer
    bind:
      said: steps.suspend.said
"#,
    ),
];

fn tree(name: &str, shows: &str) -> String {
    let root = std::env::temp_dir().join(format!("pact-cli-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    for (file, text) in TREE {
        let path = root.join(file);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        let text = text.replace("shows: [user, blast-radius]", shows);
        std::fs::write(&path, text).unwrap();
    }
    root.to_string_lossy().into_owned()
}

fn checked(root: &str) -> String {
    let out = pact().args(["check", root]).output().unwrap();
    assert!(out.status.success(), "a warning, not a refusal");
    String::from_utf8_lossy(&out.stdout).into_owned()
}

#[test]
fn a_workflow_policys_question_that_shows_what_its_call_is_given_loads_clean() {
    let text = checked(&tree("wf-shows-ok", "shows: [user, blast-radius]"));
    assert!(!text.contains("loader/shows-nothing-can-supply"), "{text}");
}

#[test]
fn a_workflow_policys_question_that_shows_what_no_call_carries_is_reported() {
    let text = checked(&tree("wf-shows-item", "shows: [user, item.blast-radius]"));
    assert!(
        text.contains("rule: loader/shows-nothing-can-supply"),
        "the name is dropped in silence at run time: {text}"
    );
    assert!(text.contains("'item.blast-radius'"), "{text}");
    assert!(
        text.contains("Change it to one of: action, blast-radius, user."),
        "the fix names what the call is given: {text}"
    );
}
