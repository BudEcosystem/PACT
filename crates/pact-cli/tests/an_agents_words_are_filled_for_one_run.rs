//! **An agent's words are filled for one run** — `pact fill`, run against the
//! real binary: the words a model reads at the start of a run, filled by the
//! same renderer the shared cases (`tests/conformance/fill.json`) hold every
//! port to.

use std::process::Command;

fn run(args: &[&str]) -> (Option<i32>, String, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(args)
        .output()
        .expect("runs");
    (
        out.status.code(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
        String::from_utf8_lossy(&out.stderr).into_owned(),
    )
}

fn tree(name: &str) -> String {
    format!("{}/../../tests/trees/{name}", env!("CARGO_MANIFEST_DIR"))
}

#[test]
fn a_hole_is_filled_from_what_the_agent_remembers_and_nothing_is_added() {
    let memory = tree("an-agent-that-reads-the-workspace-memory");
    let (code, out, _) = run(&[
        "fill",
        "desk",
        &memory,
        "--remembered",
        r#"{"house-style": ["short", "kind"]}"#,
    ]);
    assert_eq!(code, Some(0));
    assert_eq!(
        out,
        "Look the order up and answer in this style: [\"short\", \"kind\"]."
    );
    let (code, out, _) = run(&["fill", "desk", &memory, "--field", "description"]);
    assert_eq!(
        (code, out.as_str()),
        (
            Some(0),
            "Answers questions about an order in the house style."
        )
    );
}

#[test]
fn a_jinja_desk_is_rendered_and_a_value_it_needs_is_asked_for_by_name() {
    let desk = tree("a-desk-that-listens-reads-and-chooses");
    let (code, out, _) = run(&[
        "fill",
        "front-desk",
        &desk,
        "--run-inputs",
        r#"{"shop-name": "Acme", "tier": "gold", "brand-voice": "warm"}"#,
        "--remembered",
        r#"{"caller-notes": ["rang about a kettle"]}"#,
    ]);
    assert_eq!(code, Some(0));
    assert!(out.contains("You answer the phone for Acme."), "{out}");
    assert!(
        out.contains("offer the free returns label") && out.contains("- rang about a kettle"),
        "{out}"
    );
    let (code, out, err) = run(&[
        "fill",
        "front-desk",
        &desk,
        "--run-inputs",
        r#"{"shop-name": "Acme"}"#,
    ]);
    assert_eq!((code, out.as_str()), (Some(1), ""));
    assert!(
        err.contains("{{run-inputs.tier}} has no value for this run")
            && err.contains("cli/a-hole-with-no-value"),
        "{err}"
    );
}

#[test]
fn the_command_is_refused_before_anything_is_printed() {
    let memory = tree("an-agent-that-reads-the-workspace-memory");
    for (args, rule, code) in [
        (vec!["fill"], "cli/no-agent-named", 2),
        (
            vec!["fill", "desk", &memory, "--run-inputs", "[1]"],
            "cli/not-a-json-object",
            2,
        ),
        (
            vec!["fill", "desk", &memory, "--field", "persona"],
            "cli/not-a-field-with-words",
            2,
        ),
        (vec!["fill", "nobody", &memory], "cli/no-such-agent", 2),
        (vec!["fill", "desk", &memory], "cli/a-hole-with-no-value", 1),
    ] {
        let (got, out, err) = run(&args);
        assert_eq!((got, out.as_str()), (Some(code), ""), "{args:?}: {err}");
        assert!(err.contains(rule), "{args:?}: {err}");
    }
    let (code, out, err) = run(&["fill", "writer", &tree("a-hole-in-folded-and-quoted-words")]);
    assert_eq!((code, out.as_str()), (Some(1), ""));
    assert!(err.contains("loader/no-such-run-input"), "{err}");
}
