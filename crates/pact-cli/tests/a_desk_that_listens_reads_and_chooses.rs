//! Every field `docs/96-MODALITIES-INTERFACES-TEMPLATES-TURNS.md` adds, written
//! by one tree and read through the real binary — and each new rule broken
//! once, at a line of that tree, and named.
//!
//! Fixture: `tests/trees/a-desk-that-listens-reads-and-chooses/` — a voice
//! desk under `allow-egress: []` that hears, reads documents and speaks with
//! models served on the machine, looks things up by meaning with a local
//! embedder, reaches whichever mailbox the customer connected through an
//! `email` interface, and writes its words in Jinja.

use std::path::{Path, PathBuf};
use std::process::Command;

fn tree() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../tests/trees/a-desk-that-listens-reads-and-chooses")
}

fn pact(args: &[&str]) -> (Option<i32>, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(args)
        .output()
        .expect("runs");
    (
        out.status.code(),
        format!(
            "{}{}",
            String::from_utf8_lossy(&out.stdout),
            String::from_utf8_lossy(&out.stderr)
        ),
    )
}

#[test]
fn the_tree_is_clean_and_every_field_reaches_the_document() {
    let (code, said) = pact(&["check", tree().to_str().unwrap(), "--deny-warnings"]);
    assert_eq!(code, Some(0), "{said}");

    let (code, shown) = pact(&["show", tree().to_str().unwrap()]);
    assert_eq!(code, Some(0), "{shown}");
    let doc: serde_json::Value = serde_json::from_str(&shown).expect("`pact show` prints JSON");
    assert_eq!(doc["template-language"], "jinja");
    let desk = &doc["agents"]["front-desk"];
    assert_eq!(desk["voice"]["hears-with"], "whisper-large-v3");
    assert_eq!(desk["voice"]["speaks-as"], "af_heart");
    assert_eq!(desk["needs"]["prefer"], "fastest");
    assert_eq!(desk["turns"][0]["from"], "developer");
    assert_eq!(desk["turns"][2]["calls"], "email/search-messages");
    assert_eq!(desk["accepts"]["message"], "audio");
    assert_eq!(desk["run-inputs"]["receipt"], "documents, optional");
    assert!(
        desk["instructions"]
            .as_str()
            .unwrap()
            .contains("{% if run_inputs.tier == \"gold\" %}"),
        "a template is carried unrendered: its values arrive with a run"
    );

    // The interface's contract is written into each implementation, so a
    // runtime reads Gmail as though it were written out longhand.
    let send = &doc["tools"]["gmail"]["actions"]["send-message"];
    assert_eq!(send["calls"], "send_email");
    assert_eq!(send["passes"]["recipient"], "to");
    assert_eq!(send["takes"]["to"], "text");
    assert_eq!(send["needs-a-person"], "yes");
    assert_eq!(send["inspects"][0], "to");
    assert_eq!(doc["tools"]["outlook"]["category"], "email");
    assert_eq!(doc["tools"]["email"]["chosen-by"], "run-inputs.mailbox");

    let snapshot = &doc["resources"]["gmail-server"]["published"];
    assert_eq!(
        snapshot["tools"]["send_email"]["takes"]["required"][0],
        "recipient"
    );
    let policies = &doc["knowledge"]["acme-policies"];
    assert_eq!(policies["embedded-by"], "nomic-embed-text");
    assert_eq!(
        policies["use-when"],
        "somebody asks what the shop's rules are"
    );
    let case = &doc["evals"]["cases"]["the-second-call-about-a-kettle"];
    assert_eq!(case["turns"][2]["attaches"][0], "receipt");
    let row = &doc["models"]["models"]["qwen2.5-vl-7b-instruct"];
    assert_eq!(row["benchmarks"]["MMMU"]["value"], "58.6");
    assert_eq!(row["capabilities"]["modality-in"][2], "document");
    assert_eq!(row["speed"]["first-words-within"]["value"], "350ms");
}

/// One line of the tree changed, and the rule that has to say so.
struct Broken {
    file: &'static str,
    from: &'static str,
    to: &'static str,
    rule: &'static str,
}

const BROKEN: &[Broken] = &[
    // 96 §A2: a model of the wrong kind, in both directions.
    Broken {
        file: "agents/front-desk/agent.yaml",
        from: "model: qwen2.5-vl-7b-instruct",
        to: "model: nomic-embed-text",
        rule: "loader/the-wrong-kind-of-model",
    },
    Broken {
        file: "knowledge/acme-policies/acme-policies.yaml",
        from: "embedded-by: nomic-embed-text",
        to: "embedded-by: kokoro-82m",
        rule: "loader/the-wrong-kind-of-model",
    },
    // 96 §A6: voice lines that disagree with each other or the catalogue.
    Broken {
        file: "agents/front-desk/agent.yaml",
        from: "talking: takes-turns",
        to: "talking: both-at-once",
        rule: "loader/talking-over-a-pipeline",
    },
    Broken {
        file: "agents/front-desk/agent.yaml",
        from: "pipeline: transcribe-think-speak",
        to: "pipeline: one-speech-model",
        rule: "loader/one-model-and-three",
    },
    Broken {
        file: "agents/front-desk/agent.yaml",
        from: "speaks-as: af_heart",
        to: "speaks-as: alloy",
        rule: "loader/a-voice-the-speaker-does-not-have",
    },
    Broken {
        file: "agents/front-desk/agent.yaml",
        from: "languages: [en-GB]",
        to: "languages: [en-GB, fr]",
        rule: "loader/a-language-it-cannot-handle",
    },
    Broken {
        file: "agents/front-desk/agent.yaml",
        from: "accepts:\n  message: audio\nanswers-with:\n  reply: audio",
        to: "accepts:\n  message: text\nanswers-with:\n  reply: text",
        rule: "loader/a-voice-nobody-hears",
    },
    // 96 §A7: a hosted embedder is a binding, held to `allow-egress:` like any.
    Broken {
        file: "models/catalog.yaml",
        from: "  nomic-embed-text:\n    kind: embedding\n    served-by: [{runtime: ollama, endpoint: local}]",
        to: "  nomic-embed-text:\n    kind: embedding\n    served-by: [{runtime: openai, endpoint: https://api.example.com/v1}]",
        rule: "loader/leaves-the-box",
    },
    // 96 §B1: an implementation says how, never what.
    Broken {
        file: "tools/gmail.yaml",
        from: "    calls: send_email\n",
        to: "    calls: send_email\n    needs-a-person: no\n",
        rule: "loader/an-implementation-restates-the-interface",
    },
    Broken {
        file: "tools/gmail.yaml",
        from: "    calls: search_threads\n",
        to: "    calls: search_threads\n    reads-only: no\n",
        rule: "loader/an-implementation-restates-the-interface",
    },
    Broken {
        file: "tools/gmail.yaml",
        from: "html_body: body",
        to: "html_body: bdy",
        rule: "loader/passes-an-argument-the-interface-does-not-take",
    },
    Broken {
        file: "tools/outlook.yaml",
        from: "  send-message:\n    calls: sendMail\n    passes: {toRecipients: to}\n",
        to: "",
        rule: "loader/an-implementation-missing-an-action",
    },
    Broken {
        file: "tools/outlook.yaml",
        from: "  search-messages:",
        to: "  delete-everything:\n    calls: purge\n  search-messages:",
        rule: "loader/an-action-the-interface-does-not-have",
    },
    Broken {
        file: "agents/front-desk/agent.yaml",
        from: "mailbox: one of gmail, outlook",
        to: "mailbox: one of gmail, yahoo",
        rule: "loader/a-choice-that-implements-nothing",
    },
    Broken {
        file: "agents/front-desk/agent.yaml",
        from: "  mailbox: one of gmail, outlook\n",
        to: "",
        rule: "loader/chosen-by-an-input-the-agent-lacks",
    },
    Broken {
        file: "tools/email.yaml",
        from: "chosen-by: run-inputs.mailbox",
        to: "chosen-by: the-customer",
        rule: "loader/chosen-by-what",
    },
    Broken {
        file: "tools/email.yaml",
        from: "category: email",
        to: "category: email\nconnect: gmail-server",
        rule: "loader/an-interface-that-does-the-work",
    },
    Broken {
        file: "tools/outlook.yaml",
        from: "implements: email",
        to: "implements: gmail",
        rule: "loader/implements-what-is-not-an-interface",
    },
    Broken {
        file: "agents/front-desk/agent.yaml",
        from: "uses: [email, shop-policies, refund-policy]",
        to: "uses: [email, gmail, shop-policies, refund-policy]",
        rule: "loader/the-interface-and-one-of-its-own",
    },
    // 96 §C: the Jinja dialect.
    Broken {
        file: "agents/front-desk/agent.yaml",
        from: "{{ run_inputs.shop_name }}",
        to: "{{ run_inputs.shop_nam }}",
        rule: "loader/no-such-run-input",
    },
    Broken {
        file: "agents/front-desk/agent.yaml",
        from: "{{ run_inputs.shop_name }}",
        to: "{{run-inputs.shop-name}}",
        rule: "loader/a-hole-written-for-the-other-language",
    },
    Broken {
        file: "agents/front-desk/agent.yaml",
        from: "| default(\"a friendly shop assistant\")",
        to: "| truncate(20)",
        rule: "loader/a-filter-only-one-port-has",
    },
    Broken {
        file: "agents/front-desk/agent.yaml",
        from: "You answer the phone",
        to: "{% include \"tone.md\" %}You answer the phone",
        rule: "loader/a-template-that-reaches-outside",
    },
    Broken {
        file: "agents/front-desk/agent.yaml",
        from: "{{ run_inputs.shop_name }}",
        to: "{{ run_inputs.receipt }}",
        rule: "loader/a-picture-in-the-words",
    },
    Broken {
        file: "agents/front-desk/agent.yaml",
        from: "{% endif %}",
        to: "",
        rule: "loader/a-template-that-does-not-read",
    },
    // 96 §D: written conversations.
    Broken {
        file: "agents/front-desk/agent.yaml",
        from: "  - from: agent\n    says: Yes",
        to: "  - from: system\n    says: Yes",
        rule: "loader/a-standing-instruction-in-the-middle",
    },
    Broken {
        file: "agents/front-desk/agent.yaml",
        from: "  - from: tool\n",
        to: "  - from: user\n",
        rule: "loader/a-call-nobody-answers",
    },
    Broken {
        file: "agents/front-desk/agent.yaml",
        from: "calls: email/search-messages",
        to: "calls: email/delete-everything",
        rule: "loader/a-call-to-something-it-cannot-use",
    },
    Broken {
        file: "agents/front-desk/agent.yaml",
        from: "attaches: [run-inputs.receipt]",
        to: "attaches: [run-inputs.brand-voice]",
        rule: "loader/an-attachment-that-is-not-there",
    },
    Broken {
        file: "evals/suite.yaml",
        from: "      - from: user\n        says: I emailed",
        to: "      - from: agent\n        says: I emailed",
        rule: "loader/a-case-that-ends-with-the-agent",
    },
    // 96 §B4: which models the agent accepts, figure by figure.
    Broken {
        file: "agents/front-desk/agent.yaml",
        from: "    - cost < 0.05 USD",
        to: "    - cost > 0.050",
        rule: "loader/a-comparison-in-the-wrong-unit",
    },
    Broken {
        file: "agents/front-desk/agent.yaml",
        from: "    - pass-rate >= 90%",
        to: "    - pass-rate >= 90",
        rule: "loader/a-comparison-in-the-wrong-unit",
    },
    Broken {
        file: "agents/front-desk/agent.yaml",
        from: "    - refund-tone.score >= 0.8",
        to: "    - refund-tones.score >= 0.8",
        rule: "loader/no-such-measure",
    },
    Broken {
        file: "agents/front-desk/agent.yaml",
        from: "    - mmmu.score > 50",
        to: "    - mmmu.pass-rate > 50",
        rule: "loader/a-part-a-measure-does-not-have",
    },
    Broken {
        file: "agents/front-desk/agent.yaml",
        from: "    - mmmu.score > 50",
        to: "    - mmmu.score is high",
        rule: "loader/not-a-comparison",
    },
    Broken {
        file: "agents/front-desk/agent.yaml",
        from: "    - mmmu.score > 50",
        to: "    - terminal-bench.score >= 40",
        rule: "loader/a-benchmark-nobody-has-measured",
    },
    Broken {
        file: "agents/front-desk/agent.yaml",
        from: "  prefer: fastest\n",
        to: "  prefer: fastest\n  scores:\n    MMMU: \"> 40\"\n",
        rule: "loader/a-benchmark-held-twice",
    },
    Broken {
        file: "models/catalog.yaml",
        from: "      MMMU:",
        to: "      MMMMU:",
        rule: "loader/a-score-for-no-benchmark",
    },
    Broken {
        file: "evals/suite.yaml",
        from: "    name: refund-tone\n",
        to: "    name: mmlu\n",
        rule: "loader/a-metric-named-like-a-figure",
    },
    Broken {
        file: "evals/suite.yaml",
        from: "metrics:\n",
        to: "metrics:\n  - {uri: deepeval:geval, name: refund-tone, with: {criteria: Short.}}\n",
        rule: "loader/two-metrics-one-name",
    },
    // 96 §E: what the server says, recorded and held.
    Broken {
        file: "tools/gmail.yaml",
        from: "calls: send_email",
        to: "calls: send_mail",
        rule: "loader/an-action-the-server-does-not-publish",
    },
    Broken {
        file: "tools/gmail.yaml",
        from: "recipient: to",
        to: "to_address: to",
        rule: "loader/an-argument-the-server-does-not-take",
    },
    Broken {
        file: "tools/outlook.yaml",
        from: "connect: outlook-server",
        to: "connect: outlook-server\nschemas-from: the-snapshot",
        rule: "loader/a-snapshot-nobody-took",
    },
    Broken {
        file: "tools/outlook.yaml",
        from: "connect: outlook-server",
        to: "connect: outlook-server\nunlisted-actions: each-call-asks-a-person",
        rule: "loader/unlisted-actions-nobody-can-describe",
    },
    Broken {
        file: "resources/outlook-server.yaml",
        from: "resource-kind: mcp-server",
        to: "resource-kind: mcp-server\nif-it-changes: stop-and-say-so",
        rule: "loader/a-change-to-nothing-recorded",
    },
    Broken {
        file: "resources/gmail-server.yaml",
        from: "if-it-changes: use-what-was-reviewed",
        to: "if-it-changes: use-what-was-reviewed\ntool-snapshot-digest: sha256:00\ntool-snapshot-taken-at: 2026-10-01",
        rule: "loader/two-pins-on-one-server",
    },
];

#[test]
fn each_new_rule_is_broken_once_and_named() {
    let mut failed = Vec::new();
    for (i, broken) in BROKEN.iter().enumerate() {
        let dst = std::env::temp_dir().join(format!("pact-96-{}-{i}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dst);
        copy_dir(&tree(), &dst);
        let file = dst.join(broken.file);
        let text = std::fs::read_to_string(&file).unwrap();
        assert!(
            text.contains(broken.from),
            "fixture drifted: {} no longer says {:?}",
            broken.file,
            broken.from
        );
        std::fs::write(&file, text.replacen(broken.from, broken.to, 1)).unwrap();
        let (code, said) = pact(&["check", dst.to_str().unwrap(), "--deny-warnings"]);
        if code == Some(0) || !said.contains(&format!("rule: {}", broken.rule)) {
            failed.push(format!(
                "{} -> {:?} in {}: expected {}\n{said}",
                broken.from, broken.to, broken.file, broken.rule
            ));
        }
        let _ = std::fs::remove_dir_all(&dst);
    }
    assert!(failed.is_empty(), "{}", failed.join("\n\n"));
}

fn copy_dir(src: &Path, dst: &Path) {
    std::fs::create_dir_all(dst).unwrap();
    for e in std::fs::read_dir(src).unwrap().flatten() {
        let (s, d) = (e.path(), dst.join(e.file_name()));
        if s.is_dir() {
            copy_dir(&s, &d);
        } else {
            std::fs::copy(&s, &d).unwrap();
        }
    }
}

/// 96 §A6: a transcriber and a speaker on this machine keep the caller's voice
/// here, so a hosted language model behind them is sent words and needs the
/// grant for words alone. Take the transcriber away and the recording goes to
/// the hosted model, which `stt` has to allow.
#[test]
fn a_voice_heard_here_needs_only_the_grant_for_words() {
    let dst = std::env::temp_dir().join(format!("pact-96-voice-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy_dir(&tree(), &dst);
    let edit = |file: &str, from: &str, to: &str| {
        let p = dst.join(file);
        let text = std::fs::read_to_string(&p).unwrap();
        assert!(
            text.contains(from),
            "fixture drifted: {file} no longer says {from:?}"
        );
        std::fs::write(&p, text.replacen(from, to, 1)).unwrap();
    };
    edit("workspace.yaml", "allow-egress: []", "allow-egress: [llm]");
    edit(
        "agents/front-desk/agent.yaml",
        "model: qwen2.5-vl-7b-instruct",
        "model: claude-opus-5",
    );
    let (code, said) = pact(&["check", dst.to_str().unwrap(), "--deny-warnings"]);
    assert_eq!(code, Some(0), "{said}");

    edit(
        "agents/front-desk/agent.yaml",
        "  hears-with: whisper-large-v3\n",
        "",
    );
    let (code, said) = pact(&["check", dst.to_str().unwrap()]);
    assert_eq!(code, Some(1), "{said}");
    assert!(
        said.contains("rule: loader/leaves-the-box") && said.contains("`stt`"),
        "{said}"
    );
    let _ = std::fs::remove_dir_all(&dst);
}
