//! An agent somewhere else, reached over A2A, is a resource like an MCP server
//! (N1): `resource-kind: a2a-agent`, reached by a tool's `connect:`, consented
//! to by `asks-to-connect:`, its card pinned by `tool-snapshot-digest:`. The
//! tool's `actions:` are the skills it may ask; what comes back is words, so no
//! action promises values; and an endpoint off this machine is held to
//! `allow-egress: [tools]` like every other outbound address.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

/// A desk that books through a remote agent at `endpoint`, under `egress`, with
/// `actions` as the tool file's `actions:` block (empty for none).
fn desk(name: &str, egress: &str, endpoint: &str, actions: &str) -> std::path::PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-a2a-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    for dir in ["agents/desk", "tools", "resources", "questions"] {
        std::fs::create_dir_all(dst.join(dir)).unwrap();
    }
    let files = [
        (
            "workspace.yaml",
            format!("name: Bookings\ndescription: Books slots.\nallow-egress: {egress}\n"),
        ),
        (
            "agents/desk/agent.yaml",
            "name: Desk\ndescription: Books slots.\ninstructions: Book what is asked.\n\
             uses: [bookings]\n"
                .to_string(),
        ),
        (
            "tools/bookings.yaml",
            format!("description: The booking agent.\nconnect: booker\n{actions}"),
        ),
        (
            "resources/booker.yaml",
            format!(
                "resource-kind: a2a-agent\nendpoint: {endpoint}\ndescription: Books slots.\n\
                 asks-to-connect: may-we-ask-booker\n\
                 tool-snapshot-digest: sha256:0000\ntool-snapshot-taken-at: \"2026-10-12\"\n"
            ),
        ),
        (
            "questions/may-we-ask-booker.yaml",
            "description: Consent to ask the booking agent.\nsays: May the desk ask the booking agent?\n\
             answer:\n  approved: yes or no\nasked-of: [leads]\nanswer-within: 1h\n\
             if-nobody-answers: decline\n"
                .to_string(),
        ),
    ];
    for (file, text) in files {
        std::fs::write(dst.join(file), text).unwrap();
    }
    dst
}

const SKILL: &str = "actions:\n  book-slot:\n    description: Book one slot.\n    takes:\n      \
                     request: text\n";

fn check(root: &std::path::Path) -> (bool, String) {
    let out = pact()
        .args(["check", root.to_str().unwrap()])
        .output()
        .expect("runs");
    let text = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    (out.status.success(), text)
}

#[test]
fn a_remote_agent_asked_for_a_skill_in_words_loads() {
    let root = desk("clean", "[]", "host/booker", SKILL);
    let (ok, text) = check(&root);
    assert!(ok, "{text}");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_remote_agent_asked_for_no_skill_is_refused() {
    let root = desk("none", "[]", "host/booker", "");
    let (ok, text) = check(&root);
    assert!(
        !ok && text.contains("loader/a-remote-agent-asked-for-no-skill"),
        "{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_skill_of_a_remote_agent_that_promises_values_is_refused() {
    let root = desk(
        "values",
        "[]",
        "host/booker",
        &format!("{SKILL}    answers-with:\n      slot: text\n"),
    );
    let (ok, text) = check(&root);
    assert!(
        !ok && text.contains("loader/a-remote-agent-answers-in-words"),
        "{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_remote_agent_off_this_machine_needs_tools_in_allow_egress() {
    let closed = desk("closed", "[]", "https://booker.example.com", SKILL);
    let (ok, text) = check(&closed);
    assert!(
        !ok && text.contains("loader/reaches-outside-the-box"),
        "{text}"
    );
    assert!(text.contains("booker.example.com"), "{text}");

    let open = desk("open", "[tools]", "https://booker.example.com", SKILL);
    let (ok, text) = check(&open);
    assert!(ok, "{text}");
    for p in [closed, open] {
        let _ = std::fs::remove_dir_all(&p);
    }
}
