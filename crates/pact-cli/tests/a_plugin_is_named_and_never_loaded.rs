//! D29: a plugin is a request for code the runtime loads, and `pact check`
//! holds the request without ever touching the code. Every rule is driven here
//! through the real binary on a broken copy of `examples/plugin-desk`, and the
//! unbroken example is held to saying nothing at all; `pact discover` publishes
//! what each agent needs; and an edit to a plugin moves the digests a run pins
//! exactly as an edit to anything else the run relies on does.

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

const PLUGIN: &str = "plugins/web-search.yaml";
const AGENT: &str = "agents/research-desk/agent.yaml";

/// A workflow that calls the research desk, and the two lines the desk needs to
/// be called with a question and to hand an answer back, written above its
/// `plugins:` line.
const WORKFLOW: (&str, &str) = (
    "workflows/ask-the-desk.yaml",
    "description: Asks the research desk one question and hands back its answer.\n\
     accepts:\n  question: text\nanswers-with:\n  answer: text\nstarts-at: ask\nsteps:\n  \
     ask:\n    does: call\n    call: research-desk\n    bind: { question: input.question }\n    \
     then: { answered: reply }\n  reply:\n    does: answer\n    bind: { answer: steps.ask.answer }\n",
);
const CALLABLE: &str = "accepts:\n  question: text\nanswers-with:\n  answer: text\nplugins:";

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

/// A copy of the example with each `(file, from, to)` edit made. A file that is
/// not there is written, from "".
fn desk(name: &str, edits: &[(&str, &str, &str)]) -> PathBuf {
    let dst = std::env::temp_dir().join(format!("pact-plugin-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(&example(), &dst);
    for (file, from, to) in edits {
        let p = dst.join(file);
        std::fs::create_dir_all(p.parent().unwrap()).unwrap();
        let text = std::fs::read_to_string(&p).unwrap_or_default();
        assert!(
            text.contains(from),
            "fixture drifted: {from:?} not in {file}"
        );
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

/// The one rule a broken copy is refused by, at the severity given.
fn refused_by(name: &str, edits: &[(&str, &str, &str)], severity: &str, rule: &str) -> String {
    let root = desk(name, edits);
    let (ok, told, text) = check(&root);
    let _ = std::fs::remove_dir_all(&root);
    assert_eq!(told, [(severity.to_string(), rule.to_string())], "{text}");
    assert_eq!(ok, severity == "note", "{text}");
    text
}

fn discover(root: &Path) -> serde_json::Value {
    let out = pact()
        .args(["discover", root.to_str().unwrap()])
        .output()
        .expect("runs");
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let inv: serde_json::Value = serde_json::from_slice(&out.stdout).expect("JSON");
    inv.as_array()
        .and_then(|a| a.first())
        .cloned()
        .expect("one workspace")
}

#[test]
fn the_example_says_nothing_at_all() {
    let (ok, told, text) = check(&example());
    assert!(ok, "{text}");
    assert!(told.is_empty(), "{text}");
}

#[test]
fn a_package_that_names_no_registry_or_one_nobody_loads_from_is_refused() {
    let text = refused_by(
        "no-registry",
        &[(PLUGIN, "npm:@budmh/tool-web", "\"@budmh/tool-web\"")],
        "error",
        "loader/plugin-package-has-no-registry",
    );
    assert!(
        text.contains("`npm:@budmh/tool-web`"),
        "the fix spells the line: {text}"
    );
    refused_by(
        "unknown-registry",
        &[(PLUGIN, "npm:@budmh/tool-web", "cargo:tool-web")],
        "error",
        "loader/plugin-package-has-no-registry",
    );
}

#[test]
fn a_range_its_registry_would_not_read_is_refused() {
    let text = refused_by(
        "pypi-range-under-npm",
        &[(PLUGIN, "^0.2.1-rc.3", "\">=0.2,<1\"")],
        "error",
        "loader/plugin-version-is-not-a-range",
    );
    assert!(
        text.contains("^1.4.0"),
        "the fix shows an npm range: {text}"
    );
    refused_by(
        "npm-range-under-pypi",
        &[(PLUGIN, "npm:@budmh/tool-web", "pypi:budmh-tool-web")],
        "error",
        "loader/plugin-version-is-not-a-range",
    );
}

#[test]
fn a_secret_in_the_plugins_settings_is_refused_and_a_reference_is_not() {
    refused_by(
        "secret",
        &[(
            PLUGIN,
            "  searchMaxResults: 5\n",
            "  searchMaxResults: 5\n  apiKey: sk-live-2f9c41\n",
        )],
        "error",
        "loader/plugin-secret-written-in-the-file",
    );
    let root = desk(
        "reference",
        &[(
            PLUGIN,
            "  searchMaxResults: 5\n",
            "  searchMaxResults: 5\n  apiKey: { by-reference: host/search-key }\n",
        )],
    );
    let (ok, told, text) = check(&root);
    let _ = std::fs::remove_dir_all(&root);
    assert!(ok && told.is_empty(), "{text}");
}

#[test]
fn a_plugin_the_agent_cannot_start_without_is_a_note_and_not_a_failure() {
    let text = refused_by(
        "required",
        &[(PLUGIN, "if-it-cannot-be-loaded: run-without-it\n", "")],
        "note",
        "loader/plugin-runs-only-where-loaded",
    );
    assert!(
        text.contains("'research-desk' runs only where `npm:@budmh/tool-web` can be loaded"),
        "{text}"
    );
}

#[test]
fn a_plugin_name_nothing_defines_is_refused_where_it_is_written() {
    // And the plugin the author meant is then named by nobody, which is the
    // second thing they are told.
    let root = desk("misspelt", &[(AGENT, "  - web-search", "  - web-serch")]);
    let (ok, told, text) = check(&root);
    let _ = std::fs::remove_dir_all(&root);
    assert!(!ok, "{text}");
    assert_eq!(
        told,
        [
            ("error".to_string(), "schema/no-such-name".to_string()),
            (
                "warning".to_string(),
                "loader/nothing-points-at-it".to_string()
            ),
        ],
        "{text}"
    );
    assert!(text.contains("Change it to one of: web-search"), "{text}");
}

#[test]
fn a_plugin_nothing_names_is_loaded_for_nobody_and_says_so() {
    let text = refused_by(
        "unnamed",
        &[(AGENT, "plugins:\n  - web-search\n", "")],
        "warning",
        "loader/nothing-points-at-it",
    );
    assert!(text.contains("applies-to: every-agent"), "{text}");
    let root = desk(
        "every-agent",
        &[
            (AGENT, "plugins:\n  - web-search\n", ""),
            (PLUGIN, "config:", "applies-to: every-agent\nconfig:"),
        ],
    );
    let (ok, told, text) = check(&root);
    assert!(ok && told.is_empty(), "{text}");
    let inv = discover(&root);
    let _ = std::fs::remove_dir_all(&root);
    assert_eq!(
        inv["agents"][0]["plugins"][0]["name"], "web-search",
        "a plugin for every agent is listed for an agent that does not name it"
    );
}

#[test]
fn the_folder_form_is_the_same_plugin() {
    let flat = discover(&example());
    let root = desk("folder", &[]);
    let file = root.join(PLUGIN);
    let folder = root.join("plugins/web-search");
    std::fs::create_dir_all(&folder).unwrap();
    std::fs::rename(&file, folder.join("plugin.yaml")).unwrap();
    let (ok, told, text) = check(&root);
    let folded = discover(&root);
    let _ = std::fs::remove_dir_all(&root);
    assert!(ok && told.is_empty(), "{text}");
    assert_eq!(folded["digest"], flat["digest"]);
}

#[test]
fn discover_says_what_each_agent_asks_its_runtime_to_load() {
    let inv = discover(&example());
    assert_eq!(
        inv["agents"][0]["plugins"],
        serde_json::json!([{
            "name": "web-search",
            "package": "npm:@budmh/tool-web",
            "version": "^0.2.1-rc.3",
            "if-it-cannot-be-loaded": "run-without-it",
        }])
    );
    let root = desk(
        "default",
        &[(PLUGIN, "if-it-cannot-be-loaded: run-without-it\n", "")],
    );
    let inv = discover(&root);
    let _ = std::fs::remove_dir_all(&root);
    assert_eq!(
        inv["agents"][0]["plugins"][0]["if-it-cannot-be-loaded"], "refuse-to-start",
        "the default is written out, so a runtime never has to know it"
    );
}

/// The workspace digest and `ask-the-desk`'s two digests, with the workflow and
/// the desk's two lines added, plus `edits`.
fn digests(name: &str, edits: &[(&str, &str, &str)]) -> (String, String, String) {
    let mut all = vec![(WORKFLOW.0, "", WORKFLOW.1), (AGENT, "plugins:", CALLABLE)];
    all.extend_from_slice(edits);
    let root = desk(name, &all);
    let inv = discover(&root);
    let _ = std::fs::remove_dir_all(&root);
    let flow = &inv["workflows"][0];
    assert_eq!(flow["name"], "ask-the-desk");
    let text = |v: &serde_json::Value| v.as_str().expect("a digest").to_string();
    (
        text(&inv["digest"]),
        text(&flow["doc-digest"]),
        text(&flow["contract-digest"]),
    )
}

#[test]
fn a_settings_edit_moves_what_a_run_relies_on_and_not_what_its_callers_do() {
    let (workspace, document, contract) = digests("before", &[]);
    let after = digests(
        "after",
        &[(PLUGIN, "searchMaxResults: 5", "searchMaxResults: 8")],
    );
    assert_ne!(workspace, after.0, "the workspace digest moves");
    assert_ne!(
        document, after.1,
        "the doc-digest of a workflow that reaches the agent moves"
    );
    assert_eq!(
        contract, after.2,
        "the contract-digest does not: a caller hands the same question and gets the same shape back"
    );
}

fn tree(name: &str) -> PathBuf {
    PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../../tests/trees")).join(name)
}

#[test]
fn the_two_trees_say_what_their_readmes_say() {
    let (ok, told, text) = check(&tree("a-desk-that-needs-a-plugin"));
    assert!(ok, "{text}");
    assert_eq!(
        told,
        [(
            "note".to_string(),
            "loader/plugin-runs-only-where-loaded".to_string()
        )],
        "{text}"
    );
    let (ok, told, text) = check(&tree("a-plugin-with-no-registry"));
    assert!(!ok, "{text}");
    assert_eq!(
        told,
        [(
            "error".to_string(),
            "loader/plugin-package-has-no-registry".to_string()
        )],
        "the note waits until the registry is known: {text}"
    );
}
