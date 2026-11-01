//! 96 §B5: an agent that pins a model and writes `settings:` is held to what that
//! model takes, as its catalogue row records it — read from the Pydantic AI code
//! this repository pins. A line the model would throw away is refused at the line.

use std::process::Command;
use std::sync::atomic::{AtomicUsize, Ordering};

/// One folder per tree: the tests run at once, and two sharing a folder overwrite each other.
static NEXT: AtomicUsize = AtomicUsize::new(0);

fn check(model: &str, settings: &str) -> (bool, String) {
    let dst = std::env::temp_dir().join(format!(
        "pact-settings-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::SeqCst)
    ));
    let _ = std::fs::remove_dir_all(&dst);
    std::fs::create_dir_all(dst.join("agents/desk")).unwrap();
    std::fs::write(
        dst.join("workspace.yaml"),
        "name: pinned\ndescription: One exact model.\nallow-egress: [llm]\n",
    )
    .unwrap();
    std::fs::write(
        dst.join("agents/desk/agent.yaml"),
        format!(
            "description: Answers.\ninstructions: Answer briefly.\nmodel: {model}\nsettings:\n{settings}"
        ),
    )
    .unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(["check", dst.to_str().unwrap()])
        .output()
        .unwrap();
    let _ = std::fs::remove_dir_all(&dst);
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stdout).to_string() + &String::from_utf8_lossy(&out.stderr),
    )
}

#[test]
fn a_reasoning_model_keeps_its_sampling_only_with_thinking_turned_off() {
    let (ok, said) = check("gpt-5.5", "  temperature: 0.2\n  top-p: 0.9\n");
    assert!(
        !ok && said.contains("rule: loader/a-setting-ignored-while-it-thinks"),
        "{said}"
    );
    assert!(said.contains("`thinking: none`"), "{said}");
    let (ok, said) = check(
        "gpt-5.5",
        "  thinking: none\n  temperature: 0.2\n  top-p: 0.9\n  max-tokens: 2048\n",
    );
    assert!(ok, "{said}");
    // GPT-5.4 does not think unless told to, so the same lines hold with nothing else written…
    let (ok, said) = check("gpt-5.4", "  temperature: 0.2\n");
    assert!(ok, "{said}");
    // …and asking it to think puts them out of reach again.
    let (ok, said) = check("gpt-5.4", "  thinking: high\n  temperature: 0.2\n");
    assert!(
        !ok && said.contains("rule: loader/a-setting-ignored-while-it-thinks"),
        "{said}"
    );
}

#[test]
fn a_setting_a_model_never_takes_is_refused_however_it_thinks() {
    let (ok, said) = check("gpt-5.5", "  thinking: none\n  top-k: 40\n");
    assert!(
        !ok && said.contains("rule: loader/a-setting-the-model-ignores"),
        "{said}"
    );
    let (ok, said) = check("claude-opus-5", "  temperature: 0.2\n");
    assert!(
        !ok && said.contains("rule: loader/a-setting-the-model-ignores"),
        "{said}"
    );
    // A model whose row records nothing about its settings is not judged.
    let (ok, said) = check("qwen2.5-7b-instruct", "  temperature: 0.2\n  top-k: 40\n");
    assert!(ok, "{said}");
}
