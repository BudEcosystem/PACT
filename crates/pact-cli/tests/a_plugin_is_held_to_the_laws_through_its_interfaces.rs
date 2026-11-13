//! D29 under the eight laws (`docs/97-PRIMITIVES.md` §4): a plugin is code no
//! checker reads, so the laws hold for it through the interfaces it says it
//! implements. Every rule is driven through the real binary on a copy of
//! `examples/plugin-desk` that adds a customer-records interface and a plugin
//! whose code stands behind it; the unbroken copy is held to saying nothing.
//!
//! Law 8 for a plugin is a learning proposal held to `pact check` before it is
//! held for a person, which is the Python reference's to do and is driven by
//! `adapters/python/tests/test_a_plugin_a_cycle_proposes_is_checked_then_held.py`.

use std::path::{Path, PathBuf};
use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> PathBuf {
    PathBuf::from(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../examples/plugin-desk"
    ))
}

/// The interface: one action that looks things up, and one that cannot be
/// undone and so names the argument that makes two calls the same call.
const CRM: (&str, &str) = (
    "tools/crm.yaml",
    "description: The customer records the desk reads and closes.\n\
     interface: yes\n\
     actions:\n  \
       look-up:\n    \
         description: Finds a customer by email.\n    \
         takes:\n      email: text\n    \
         reads-only: yes\n  \
       close-account:\n    \
         description: Closes a customer's account.\n    \
         takes:\n      customer: text\n    \
         same-request-key: customer\n",
);

/// The plugin whose code stands behind it.
const PLUGIN: (&str, &str) = (
    "plugins/crm-tools.yaml",
    "description: The customer-records client the desk's runtime loads.\n\
     package: npm:@acme/crm-tools\n\
     version: ^1.4.0\n\
     if-it-cannot-be-loaded: run-without-it\n\
     implements: [crm]\n",
);

const AGENT: &str = "agents/research-desk/agent.yaml";
const LOADED: &str = "plugins:\n  - web-search\n  - crm-tools\nuses: [crm]\n";

fn copy(src: &Path, dst: &Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() {
            copy(&s, &d)
        } else {
            std::fs::copy(&s, &d).map(|_| ()).unwrap()
        }
    }
}

/// The example with the interface, the plugin and the agent that uses both,
/// then each `(file, from, to)` edit made.
fn desk(name: &str, edits: &[(&str, &str, &str)]) -> PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-plugin-laws-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&example(), &dst);
    for (file, text) in [CRM, PLUGIN] {
        let p = dst.join(file);
        std::fs::create_dir_all(p.parent().unwrap()).unwrap();
        std::fs::write(&p, text).unwrap();
    }
    let agent = dst.join(AGENT);
    let text = std::fs::read_to_string(&agent).unwrap();
    assert!(text.contains("plugins:\n  - web-search\n"), "fixture drifted: {AGENT}");
    std::fs::write(&agent, text.replacen("plugins:\n  - web-search\n", LOADED, 1)).unwrap();
    for (file, from, to) in edits {
        let p = dst.join(file);
        let text = std::fs::read_to_string(&p).unwrap_or_default();
        assert!(text.contains(from), "fixture drifted: {from:?} not in {file}");
        std::fs::write(&p, text.replacen(from, to, 1)).unwrap();
    }
    dst
}

/// `pact check --deny-warnings` on `root`: whether it passed, every
/// `(severity, rule)` it printed, and the whole text.
fn check(root: &Path) -> (bool, Vec<(String, String)>, String) {
    let out = pact()
        .args(["check", root.to_str().unwrap(), "--deny-warnings"])
        .output()
        .expect("runs");
    let text = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    let mut told = Vec::new();
    let mut severity = String::new();
    for line in text.lines() {
        for word in ["error", "warning", "note"] {
            if line.starts_with(&format!("{word}:")) {
                severity = word.to_string();
            }
        }
        if let Some(rule) = line.trim().strip_prefix("rule: ") {
            told.push((severity.clone(), rule.to_string()));
        }
    }
    (out.status.success(), told, text)
}

/// The rules `edits` makes `pact check` print, the tree removed afterwards.
fn checked(name: &str, edits: &[(&str, &str, &str)]) -> (bool, Vec<(String, String)>, String) {
    let root = desk(name, edits);
    let out = check(&root);
    let _ = std::fs::remove_dir_all(&root);
    out
}

fn has(told: &[(String, String)], severity: &str, rule: &str) -> bool {
    told.iter().any(|(s, r)| s == severity && r == rule)
}

/// What `pact discover` says the research desk does to the world.
fn effect_of_the_desk(name: &str, edits: &[(&str, &str, &str)]) -> (String, bool) {
    let root = desk(name, edits);
    let out = pact()
        .args(["discover", root.to_str().unwrap()])
        .output()
        .expect("runs");
    let _ = std::fs::remove_dir_all(&root);
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
    let inv: serde_json::Value = serde_json::from_slice(&out.stdout).expect("JSON");
    let desk = inv[0]["agents"]
        .as_array()
        .expect("agents")
        .iter()
        .find(|a| a["id"] == "pact:research-desk")
        .cloned()
        .expect("the research desk");
    (
        desk["effect"].as_str().expect("effect").to_string(),
        desk["moves-money"].as_bool().expect("moves-money"),
    )
}

#[test]
fn a_plugin_behind_an_interface_says_nothing_at_all() {
    let (ok, told, text) = checked("clean", &[]);
    assert!(ok, "{text}");
    assert!(told.is_empty(), "{text}");
}

#[test]
fn law_4_a_plugin_implements_only_an_interface() {
    let (ok, told, text) = checked("not-an-interface", &[("tools/crm.yaml", "interface: yes\n", "")]);
    assert!(!ok, "{text}");
    assert!(
        has(&told, "error", "loader/plugin-implements-what-is-not-an-interface"),
        "{text}"
    );
    assert!(text.contains("'crm-tools' says its code implements 'crm'"), "{text}");
}

#[test]
fn law_4_an_interface_a_plugin_implements_is_implemented() {
    // Without the plugin's `implements:` the interface has nothing behind it.
    let (_, told, text) = checked("no-implements", &[("plugins/crm-tools.yaml", "implements: [crm]\n", "")]);
    assert!(has(&told, "warning", "loader/an-interface-nothing-implements"), "{text}");
}

#[test]
fn law_4_an_agent_using_an_interface_only_an_absent_plugin_implements_is_warned() {
    let (ok, told, text) = checked(
        "absent",
        &[(AGENT, "  - crm-tools\n", "")],
    );
    assert!(!ok, "{text}");
    assert!(
        has(&told, "warning", "loader/an-interface-only-an-absent-plugin-implements"),
        "{text}"
    );
    assert!(text.contains("Add 'crm-tools' to `plugins:` in 'research-desk'"), "{text}");
    // Loaded for every agent, the plugin is behind the interface again.
    let (_, told, text) = checked(
        "every-agent",
        &[
            (AGENT, "  - crm-tools\n", ""),
            ("plugins/crm-tools.yaml", "implements: [crm]\n", "implements: [crm]\napplies-to: every-agent\n"),
        ],
    );
    assert!(
        !has(&told, "warning", "loader/an-interface-only-an-absent-plugin-implements"),
        "{text}"
    );
}

#[test]
fn law_4_a_run_input_may_choose_the_plugin() {
    let (ok, told, text) = checked(
        "chosen",
        &[
            ("tools/crm.yaml", "interface: yes\n", "interface: yes\nchosen-by: run-inputs.records\n"),
            (AGENT, "uses: [crm]\n", "uses: [crm]\nrun-inputs:\n  records: one of crm-tools\n"),
        ],
    );
    assert!(ok, "{text}");
    assert!(told.is_empty(), "{text}");
    let (_, told, text) = checked(
        "chosen-wrong",
        &[
            ("tools/crm.yaml", "interface: yes\n", "interface: yes\nchosen-by: run-inputs.records\n"),
            (AGENT, "uses: [crm]\n", "uses: [crm]\nrun-inputs:\n  records: one of web-search\n"),
        ],
    );
    assert!(has(&told, "error", "loader/a-choice-that-implements-nothing"), "{text}");
}

#[test]
fn law_3_an_action_a_plugin_cannot_undo_names_its_key() {
    let (ok, told, text) = checked(
        "no-key",
        &[("tools/crm.yaml", "    same-request-key: customer\n", "")],
    );
    assert!(!ok, "{text}");
    assert!(has(&told, "error", "loader/a-plugin-action-with-no-claim"), "{text}");
    assert!(text.contains("'crm/close-account' cannot be undone"), "{text}");
    // An action that looks things up needs no claim, and neither does one the
    // tree can take back.
    let (ok, told, text) = checked(
        "undone",
        &[(
            "tools/crm.yaml",
            "    same-request-key: customer\n",
            "    undone-by: crm/reopen-account\n  reopen-account:\n    description: Reopens it.\n    takes:\n      customer: text\n    same-request-key: customer\n",
        )],
    );
    assert!(ok, "{text}");
    assert!(!has(&told, "error", "loader/a-plugin-action-with-no-claim"), "{text}");
}

#[test]
fn law_1_an_agent_loaded_with_a_plugin_reports_what_its_interface_does() {
    // The desk names the interface: it can close an account.
    assert_eq!(effect_of_the_desk("uses", &[]), ("cannot-be-undone".into(), false));
    // It no longer names it and is still loaded with the code that does it.
    assert_eq!(
        effect_of_the_desk("loaded", &[(AGENT, "uses: [crm]\n", "")]),
        ("cannot-be-undone".into(), false)
    );
    // A plugin that implements nothing gives the agent nothing to report.
    assert_eq!(
        effect_of_the_desk(
            "nothing",
            &[(AGENT, "uses: [crm]\n", ""), ("plugins/crm-tools.yaml", "implements: [crm]\n", "")]
        ),
        ("nothing".into(), false)
    );
    // Money is carried the same way.
    assert_eq!(
        effect_of_the_desk(
            "money",
            &[
                (AGENT, "uses: [crm]\n", ""),
                ("tools/crm.yaml", "    same-request-key: customer\n", "    same-request-key: customer\n    spends-money: yes\n    needs-a-person: yes\n"),
            ]
        ),
        ("cannot-be-undone".into(), true)
    );
}
