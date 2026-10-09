//! Objective measurement of the authoring surface (bears on AC-1.5).
//!
//! **This is not a user study and cannot substitute for one.** AC-1.5 asks
//! whether a non-technical domain expert can build a multi-agent system unaided,
//! and only a person attempting it can answer that.
//!
//! What *can* be measured mechanically is the surface they would face, and
//! whether it behaves the way a format for non-coders has to:
//!
//! * how many concepts and files a complete system costs;
//! * whether the mistakes such an author actually makes each produce a
//!   diagnostic naming the file, the line and a typeable fix;
//! * whether any error message assumes programming knowledge.
//!
//! A format can fail these and still be unusable by a human. But it cannot pass
//! a human trial while failing these, so they are a necessary condition worth
//! holding under test rather than an argument for the sufficient one.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn example() -> String {
    format!("{}/../../examples/refund-desk", env!("CARGO_MANIFEST_DIR"))
}

/// Copy the example and apply one edit, returning the temp root.
fn broken(name: &str, file: &str, from: &str, to: &str) -> String {
    let dst = std::env::temp_dir().join(format!("pact-surface-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    copy(std::path::Path::new(&example()), &dst);
    let p = dst.join(file);
    let text = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
    assert!(
        text.contains(from),
        "fixture drifted: {from:?} not in {file}"
    );
    std::fs::write(&p, text.replace(from, to)).unwrap();
    dst.to_string_lossy().into_owned()
}

fn copy(src: &std::path::Path, dst: &std::path::Path) {
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

#[test]
fn the_no_code_bar_from_d14_stays_small() {
    // D14 names the bar precisely: a multi-agent system with custom tools, its
    // own eval cases, SLO limits and learning enabled. THAT is what a
    // non-technical author has to hold in their head, and it is what this
    // ceiling protects.
    //
    // Measured separately from the showcase directories below, because the
    // example also demonstrates constructs a typical system never uses. Letting
    // one number cover both would quietly let the bar drift upward every time a
    // new capability is added.
    const CORE: &[&str] = &["agents", "tools", "resources", "skills", "evals"];

    let root = example();
    // workspace.yaml + learning.yaml + redaction.yaml at the root. It was 2 for
    // a round, and the third file is not new work: what must never leave used to
    // sit in `redactions/`, a directory counted by neither this ceiling nor the
    // showcase one below (R61). A directory nobody counts is a directory that can
    // grow without anyone noticing — the argument the showcase list already makes
    // — so collapsing it to one root file is also the moment to start counting it.
    let mut files = 3usize;
    for dir in CORE {
        files += count_specs(&std::path::Path::new(&root).join(dir));
    }
    assert!(
        files <= 26,
        "the D14 core is {files} files — past what a non-coder holds in their head"
    );
    assert!(
        files >= 10,
        "the core must be a real multi-agent system, not a toy"
    );
}

#[test]
fn the_showcase_directories_stay_optional_and_bounded() {
    // Ports, schedules, context policies, interceptors, policies, questions and
    // loops are what a system grows into, not what it starts as. They are
    // counted, so their growth is visible, but they are not part of the
    // beginner's ceiling.
    //
    // `loops` belongs here and not in CORE because nobody writes the shape of
    // the thinking first. It is what a system grows into once its FIRST shape
    // turns out to be wrong — a refund desk answers a customer without reading
    // the decision back against the policy, somebody notices, and only then
    // does a stage get added in between. A beginner never types one, so D14's
    // count above must not move to pay for it.
    //
    // `questions` is counted here rather than left out. A directory nobody
    // counts is a directory that can grow without anyone noticing, and the
    // whole point of this ceiling is that adding a capability has to be visibly
    // paid for somewhere.
    const SHOWCASE: &[&str] = &[
        "ports",
        "schedules",
        "context-policies",
        "interceptors",
        "policies",
        "questions",
        "loops",
        // The observe half of the event lattice. Counted here and not in CORE
        // for the reason the others are: nobody writes down what a run did
        // before they have a run. It is counted at all because a directory
        // nobody counts is a directory that can grow without anyone noticing.
        "watch",
    ];

    let root = example();
    let extra: usize = SHOWCASE
        .iter()
        .map(|d| count_specs(&std::path::Path::new(&root).join(d)))
        .sum();
    // 13 -> 14 bought `interceptors/redact-card-numbers-in-tool-calls.yaml`,
    // and this number has since been REFUNDED: 14 -> 13. The comment that paid
    // for it said the duplication was "the thing to fix — not this number", and
    // it was fixed. `interceptor.when` takes a list of moments, so the rule that
    // catches what the customer typed and the rule that catches what the agent
    // is about to hand to `payments` are two lines in one file instead of two
    // files differing in `description:` and `when:` and nothing else. Both
    // moments are still covered, and the tree is one file smaller — which is the
    // only direction this ceiling should ever move on its own.
    //
    // 14 -> 15 bought `questions/may-we-connect.yaml`, and the same rule applies:
    // this comment is the payment.
    //
    // What it bought: `resources/payments-server.yaml` now says `asks-to-connect:`, so
    // the one Eve park kind PACT claims to have generalised — its scoped-OAuth
    // park — has an instance in the tree instead of only in a document a test
    // built inline. Before it, the field was in the schema, was one of the
    // checked references, had a test, and was written by nothing an author
    // could read; a mechanism whose only instance lives in its own test is one
    // edit away from being unreachable with nothing noticing, which is the
    // thing this worked example exists to prevent. The file is a question
    // rather than a new kind because a wait's wording, audience, deadline and
    // timeout are what a `question` already is (§7.14 WAIT-2) — so the count
    // moved by one and the concept count did not move at all.
    // 15 -> 16 buys `watch/tool-calls.yaml`, and this comment is the payment.
    //
    // What it bought: the OBSERVE half of the event lattice had no authoring
    // surface at all. Watching a run took a Python callable — `Bus.on(pattern,
    // fn)` — while CHANGING one already took a YAML file, so the safer power sat
    // behind the higher bar and D14's "no capability may require author code"
    // was untrue of exactly the capability a beginner reaches for first. The
    // file is a kind of its own rather than an interceptor with an empty `may:`
    // so that a watch needs nobody's review: there is nothing it may do.
    //
    // 16 -> 15 is the card-number refund above. The ceiling comes DOWN with it
    // rather than staying where it was: a ceiling left high after a file is
    // removed is a file's worth of room nobody argued for.
    assert!(
        extra <= 15,
        "{extra} showcase files is more than one screen"
    );
}

/// Count YAML/Markdown files under `dir`, recursively. Missing dir counts zero.
fn count_specs(dir: &std::path::Path) -> usize {
    let Ok(entries) = std::fs::read_dir(dir) else {
        return 0;
    };
    let mut n = 0;
    for e in entries.flatten() {
        let p = e.path();
        if p.is_dir() {
            n += count_specs(&p);
        } else if p.extension().is_some_and(|x| x == "yaml" || x == "md") {
            n += 1;
        }
    }
    n
}

#[test]
fn the_mistakes_a_non_coder_actually_makes_are_all_caught_with_a_fix() {
    // Each of these is a realistic slip, not a synthetic edge case: a typo, a
    // unit left off, a word that isn't one of the allowed ones, a missing
    // currency, an ambiguous percentage.
    let cases: &[(&str, &str, &str, &str)] = &[
        ("typo", "workspace.yaml", "description:", "descriptoin:"),
        (
            "no-unit",
            "agents/refund-desk/limits.yaml",
            "finishes-within: 30s",
            "finishes-within: soon",
        ),
        (
            "wrong-word",
            "agents/refund-desk/needs.yaml",
            "reasoning: careful",
            "reasoning: brilliant",
        ),
        (
            "no-currency",
            "agents/refund-desk/limits.yaml",
            "cost-per-request-under: 0.05 USD",
            "cost-per-request-under: 0.05",
        ),
        (
            "bad-feel",
            "agents/refund-desk/limits.yaml",
            "feel: interactive",
            "feel: snappy",
        ),
        // A ceiling with nothing saying what happens at it. The commonest way
        // to write one, and the one that costs most: stopping silently and
        // answering as if finished are different enough that the system must
        // not pick for you.
        (
            "ceiling-with-no-action",
            "agents/refund-desk/limits.yaml",
            "when-it-runs-out: ask-a-person",
            "",
        ),
    ];

    for (name, file, from, to) in cases {
        let root = broken(name, file, from, to);
        let out = pact().args(["check", &root]).output().expect("runs");
        let text = String::from_utf8_lossy(&out.stdout);

        assert!(
            !out.status.success(),
            "[{name}] must be caught, not accepted"
        );
        assert!(text.contains("  fix: "), "[{name}] no fix offered:\n{text}");
        assert!(
            text.contains(".yaml:"),
            "[{name}] no file:line given:\n{text}"
        );

        // A fix a non-coder can act on names something concrete — a value to
        // type or a spelling to use — not just a restatement of the rule.
        let fix_line = text
            .lines()
            .find(|l| l.trim_start().starts_with("fix:"))
            .unwrap();
        assert!(
            fix_line.contains('`') || fix_line.contains("Did you mean") || fix_line.contains(':'),
            "[{name}] fix is not actionable: {fix_line}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }
}

#[test]
fn a_ceiling_with_no_declared_action_is_refused_and_the_choices_are_offered() {
    // Eve has no ceiling of any kind to forget an action for; PACT has five, so
    // this is the mistake its own surface creates and therefore the one it owes
    // a diagnostic. The fix has to be a line the author can type, with all
    // three choices spelled out — picking one blind is how the wrong governance
    // decision gets made by accident.
    let root = broken(
        "no-action",
        "agents/refund-desk/limits.yaml",
        "when-it-runs-out: ask-a-person",
        "",
    );
    let out = pact().args(["check", &root]).output().unwrap();
    let text = String::from_utf8_lossy(&out.stdout);

    assert!(
        !out.status.success(),
        "a ceiling with no action must be refused:\n{text}"
    );
    assert!(
        text.contains("when-it-runs-out"),
        "must name the missing setting:\n{text}"
    );
    assert!(
        text.contains("limits.yaml:"),
        "must name the file and line:\n{text}"
    );
    for choice in ["stop-and-say-so", "ask-a-person", "answer-with-what-it-has"] {
        assert!(
            text.contains(choice),
            "the fix must offer '{choice}':\n{text}"
        );
    }
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn a_question_put_to_a_person_is_checked_like_everything_else() {
    // G7 makes "what a person is asked" authored data rather than a widget with
    // two options in it. The moment it is data, it is data that can be wrong —
    // so the mistakes an author makes writing one have to be caught here, not
    // discovered by an approver staring at a request with no wording in it.
    let cases: &[(&str, &str, &str, &str)] = &[
        // A word that is not one of the allowed ones. The three that are allowed
        // deliberately do not include approving, so a timeout can never be a yes.
        (
            "silence-approves",
            "questions/is-this-ok.yaml",
            "if-nobody-answers: escalate",
            "if-nobody-answers: approve",
        ),
        // A typo in the one line that says who reads it.
        (
            "asked-of-typo",
            "questions/is-this-ok.yaml",
            "asked-of:",
            "asked-off:",
        ),
        // The wording left off entirely — a request with nothing to read.
        (
            "no-wording",
            "questions/keep-going.yaml",
            "says: This is taking longer than it should. Keep going?",
            "# no wording",
        ),
    ];

    for (name, file, from, to) in cases {
        let root = broken(name, file, from, to);
        let out = pact().args(["check", &root]).output().expect("runs");
        let text = String::from_utf8_lossy(&out.stdout);

        assert!(
            !out.status.success(),
            "[{name}] must be caught, not accepted:\n{text}"
        );
        assert!(text.contains("  fix: "), "[{name}] no fix offered:\n{text}");
        assert!(
            text.contains(".yaml:"),
            "[{name}] no file:line given:\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }
}

#[test]
fn a_timeout_cannot_be_written_as_an_approval() {
    // The one property of G7 that has to hold in the FILE FORMAT and not only in
    // the runtime: there is no spelling of "when nobody answers, go ahead". If
    // the word existed here, every structural guarantee downstream would be one
    // YAML edit away from being turned off.
    let root = broken(
        "no-silent-yes",
        "questions/how-much-to-refund.yaml",
        "if-nobody-answers: decline",
        "if-nobody-answers: approve",
    );
    let out = pact().args(["check", &root]).output().unwrap();
    let text = String::from_utf8_lossy(&out.stdout);
    assert!(
        !out.status.success(),
        "silence must never be writable as a yes:\n{text}"
    );
    // And the fix has to name what CAN be written, or the author is stuck.
    assert!(
        text.contains("decline") && text.contains("escalate") && text.contains("stop-and-say-so"),
        "the fix must list the choices that exist:\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn no_diagnostic_assumes_programming_knowledge() {
    let root = broken(
        "jargon",
        "agents/refund-desk/needs.yaml",
        "reasoning: careful",
        "reasoning: brilliant",
    );
    let out = pact().args(["check", &root]).output().unwrap();
    let text = String::from_utf8_lossy(&out.stdout).to_lowercase();
    for word in [
        "enum",
        "variant",
        "deserialize",
        "serde",
        "unwrap",
        "panic",
        "trait",
        "struct",
        "vec<",
        "option<",
        "stack trace",
        "null pointer",
        "schema validation failed",
    ] {
        assert!(
            !text.contains(word),
            "diagnostic assumes programming knowledge ('{word}'):\n{text}"
        );
    }
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn every_field_in_the_specification_carries_help_and_surface_and_tier() {
    // `50-NOT-COPIED.md` §7 tells a reader that checking category (a) means
    // checking a field carries all three of `help:`, `surface:` and `tier:`, and
    // names this file as what holds it. For a round it held only `help:`, and
    // only as a whole-file substring ratio — `helped * 100 >= typed * 90` — which
    // cannot say WHICH field is missing WHAT, and which nothing anywhere read
    // `surface:` or `tier:` at all to make true.
    //
    // Each of the three is load-bearing somewhere different, which is why one
    // standing in for the others is not a smaller version of the check:
    //   help:     the only documentation the reader D13 names ever gets
    //   surface:  §8.2's governance zone and §8.3's blast-radius class are
    //             lookups into it — a field without one is CLASS-4 by default,
    //             so an omission tightens silently rather than failing loudly
    //   tier:     what makes the `no-code` badge (D14) checkable at all
    let text = std::fs::read_to_string(format!(
        "{}/../../spec/schema.yaml",
        env!("CARGO_MANIFEST_DIR")
    ))
    .unwrap();
    let doc = pact_doc::parse_yaml(&text, camino::Utf8Path::new("spec/schema.yaml"))
        .expect("the specification parses");
    let groups = doc
        .get("groups")
        .and_then(pact_doc::Node::as_map)
        .expect("groups:");

    let mut missing: Vec<String> = Vec::new();
    let mut checked = 0usize;
    for (group, entry) in groups {
        let Some(fields) = entry.node.get("fields").and_then(pact_doc::Node::as_map) else {
            continue;
        };
        for (field, f) in fields {
            checked += 1;
            for want in ["help", "surface", "tier"] {
                let present = f
                    .node
                    .get(want)
                    .and_then(pact_doc::Node::as_str)
                    .is_some_and(|s| !s.trim().is_empty());
                if !present {
                    missing.push(format!("{group}.{field} has no `{want}:`"));
                }
            }
        }
    }

    assert!(
        checked > 100,
        "only {checked} fields found — the walk is wrong, not the spec"
    );
    assert!(
        missing.is_empty(),
        "{} field(s) short:\n  {}",
        missing.len(),
        missing.join("\n  ")
    );
}

#[test]
fn every_command_the_specification_promises_is_a_command_that_exists() {
    // Help text is the only documentation D13's reader ever gets, so a verb
    // named in it reads as a verb that exists. Four did not: `agent.team` said
    // "`pact init` writes each member's instructions", `resource.endpoint` said
    // "`pact tools list` shows the ones this machine already knows about",
    // `tool.pinned` said it is "Written by `pact tools sync`; you never write it
    // by hand", and `evals.graded-by` said "`pact show models --can-judge` lists
    // the ones you can name here". The binary dispatches check, show, discover
    // and card, and falls through to `unknown command`.
    //
    // `tool.pinned` was the sharpest: the schema forbade writing it by hand and
    // named a tool to write it that has never existed, so the field had no path
    // at all. `pact show models --can-judge` was worse than absent — `show`
    // ignores extra positionals, so it silently printed the whole document.
    // EVERY author-facing document, not only `spec/schema.yaml`. The schema was
    // cleaned and the identical sentences survived one directory over: the
    // worked example — the only template a D13 reader opens — went on saying
    // "`pact init` writes each member's instructions.md", "written by `pact
    // tools sync`", "Written by `pact tools add payments --url ...`" and "`pact
    // show models --can-judge` lists what you can put here", all four of which
    // error. The test written to stop exactly this read one file.
    let repo = format!("{}/../..", env!("CARGO_MANIFEST_DIR"));
    let mut text = std::fs::read_to_string(format!("{repo}/spec/schema.yaml")).unwrap();
    let mut stack = vec![std::path::PathBuf::from(format!("{repo}/examples"))];
    while let Some(dir) = stack.pop() {
        let Ok(entries) = std::fs::read_dir(&dir) else {
            continue;
        };
        for e in entries.flatten() {
            let p = e.path();
            if p.is_dir() {
                stack.push(p);
            } else if matches!(
                p.extension().and_then(|x| x.to_str()),
                Some("yaml" | "yml" | "md")
            ) && let Ok(more) = std::fs::read_to_string(&p)
            {
                text.push('\n');
                text.push_str(&more);
            }
        }
    }
    let main =
        std::fs::read_to_string(format!("{}/src/main.rs", env!("CARGO_MANIFEST_DIR"))).unwrap();

    // The verbs the dispatch actually has, read from the `match` rather than
    // from a list here — a second copy would drift the first time one is added.
    let body = main
        .split_once("    match cmd {")
        .expect("main.rs dispatches on `cmd`")
        .1;
    let verbs: Vec<&str> = body
        .split("\n}")
        .next()
        .unwrap_or(body)
        .lines()
        .filter(|l| l.contains("=>"))
        .flat_map(|l| l.split('"').skip(1).step_by(2))
        .filter(|s| !s.is_empty() && !s.starts_with('-'))
        .collect();
    assert!(
        verbs.contains(&"check"),
        "no verbs parsed — the dispatch changed shape"
    );

    let mut promised: Vec<String> = Vec::new();
    for span in text.split('`').skip(1).step_by(2) {
        let Some(rest) = span.strip_prefix("pact ") else {
            continue;
        };
        let verb = rest.split_whitespace().next().unwrap_or("");
        if !verbs.contains(&verb) {
            promised.push(format!("`pact {verb}`"));
        }
    }
    promised.sort();
    promised.dedup();
    assert!(
        promised.is_empty(),
        "the specification and the worked example promise {} command(s) that do not \
         exist: {}. \
         Either ship the verb, or write help text naming only what does — a \
         non-coder reads help text as a description of the product.",
        promised.len(),
        promised.join(", ")
    );
}

#[test]
fn a_model_nobody_has_heard_of_is_caught_where_the_author_is_and_a_workspace_may_add_one() {
    // `model:` and `summarised-by:` name a model, and the list of models is a
    // file the author never writes — so for a round they resolved against
    // nothing at all. `model: qwen2.5-7b-instrukt` loaded clean and failed later
    // at run time in another language, which is verbatim the failure class
    // `names:` exists to end, on the two fields where the consequence is that a
    // tidying rule is measured against nothing and reported as unenforced.
    let typo = broken(
        "unknown-model",
        "agents/refund-desk/agent.yaml",
        "policy: approvals",
        "model: qwen2.5-7b-instrukt\npolicy: approvals",
    );
    let out = pact().args(["check", &typo]).output().unwrap();
    let said =
        String::from_utf8_lossy(&out.stdout).to_string() + &String::from_utf8_lossy(&out.stderr);
    assert!(said.contains("qwen2.5-7b-instrukt"), "{said}");
    assert!(said.contains("the model catalogue"), "{said}");
    assert!(
        said.contains("qwen2.5-7b-instruct"),
        "the fix must offer what to type:\n{said}"
    );
    assert!(
        said.contains("models/catalog.yaml"),
        "and where a new one goes:\n{said}"
    );

    // And the override layer, which is the whole reason this is not a closed
    // list: a machine serving a model this distribution has never heard of adds
    // a row, and the pin resolves. Without it an air-gapped author's only path
    // was editing a file inside the product, which is D14's "experts write code
    // for that" wearing a different hat.
    let own = broken(
        "own-model",
        "agents/refund-desk/agent.yaml",
        "policy: approvals",
        "model: our-own-7b\npolicy: approvals",
    );
    std::fs::create_dir_all(std::path::Path::new(&own).join("models")).unwrap();
    std::fs::write(
        std::path::Path::new(&own).join("models/catalog.yaml"),
        concat!(
            "version: 1\n",
            "models:\n",
            "  our-own-7b:\n",
            "    tier: small\n",
            "    served-by:\n",
            "      - { runtime: vllm, endpoint: local }\n",
            "    capabilities:\n",
            "      context-window:\n",
            "        value: 16384\n",
            "        provenance:\n",
            "          source: the max-model-len our platform team serves it with\n",
            "          as-of: 2026-07-28\n",
        ),
    )
    .unwrap();
    let ok = pact().args(["check", &own]).output().unwrap();
    assert!(
        ok.status.success(),
        "a workspace that says what its own model holds must load:\n{}{}",
        String::from_utf8_lossy(&ok.stdout),
        String::from_utf8_lossy(&ok.stderr)
    );
}

#[test]
fn a_model_that_only_answers_off_this_machine_is_refused_in_an_air_gapped_workspace() {
    // The schema tells the author, in help text a non-coder reads as a
    // description of the product, that `endpoint:` anything other than `local`
    // "means the call leaves the box — which a workspace with nothing in
    // `allow-egress:` will refuse to do". Nothing refused it. Measured before
    // this test existed: the worked example says `allow-egress: []`, and
    // pointing `summarised-by:` at a hosted-only row still reported
    // "OK — loaded cleanly (448 settings)", exit 0. The failure then arrived at
    // run time, in another language, in a process a support lead never starts.
    //
    // Both fields that bind a model are covered, because both went out the same
    // door and this round is what turned `summarised-by:` from an inert setting
    // into a call that really goes out.
    for (name, file, from, to, field) in [
        (
            "egress-summariser",
            "context-policies/long-threads.yaml",
            "summarised-by: qwen2.5-14b-instruct",
            "summarised-by: claude-opus-5",
            "summarised-by",
        ),
        (
            "egress-model",
            "agents/refund-desk/agent.yaml",
            "policy: approvals",
            "model: claude-opus-5\npolicy: approvals",
            "model",
        ),
    ] {
        let root = broken(name, file, from, to);
        let out = pact().args(["check", &root]).output().unwrap();
        let said = String::from_utf8_lossy(&out.stdout).to_string()
            + &String::from_utf8_lossy(&out.stderr);
        assert!(!out.status.success(), "{field} must be refused:\n{said}");
        assert!(
            said.contains("claude-opus-5"),
            "name what is wrong:\n{said}"
        );
        assert!(
            said.contains("allow-egress"),
            "name the rule that refused it:\n{said}"
        );
        assert!(
            said.contains("workspace.yaml"),
            "name where that rule lives:\n{said}"
        );
        assert!(
            said.contains(&format!("write `{field}: qwen2.5-7b-instruct`")),
            "the fix must be a line the author can type:\n{said}"
        );
    }

    // And the escape hatch really is one. A workspace that has decided to allow
    // model calls out loads — the rule is about the *binding*, per decision Y16,
    // and never about the model being unwelcome.
    let allowed = broken(
        "egress-allowed",
        "workspace.yaml",
        "allow-egress: []",
        "allow-egress: [llm]",
    );
    let p = std::path::Path::new(&allowed).join("context-policies/long-threads.yaml");
    let text = std::fs::read_to_string(&p).unwrap();
    std::fs::write(
        &p,
        text.replace(
            "summarised-by: qwen2.5-14b-instruct",
            "summarised-by: claude-opus-5",
        ),
    )
    .unwrap();
    let out = pact().args(["check", &allowed]).output().unwrap();
    assert!(
        out.status.success(),
        "a workspace that allows egress must load:\n{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
}

#[test]
fn a_reference_to_something_this_workspace_does_not_have_is_caught_where_the_author_is() {
    // For a round `pact check` resolved NO cross-file name, so every realistic
    // reference typo a non-coder makes loaded with zero diagnostics and failed
    // later — at run time, in another language, in a process a support lead
    // never starts. Two documents said otherwise (`50-NOT-COPIED.md` §1.2 and
    // the note atop `worked_example_loop.rs`) and both were wrong.
    //
    // Each case below is one edit to a copy of the worked example, and each one
    // is a name the workspace itself declares — which is exactly the set
    // `pact check` can be held to. What it cannot resolve is named in the
    // schema's own R6 note and in §7 of `50-NOT-COPIED.md`: anything the HOST
    // binds (`through:`), and narrowing `may-use:` to one agent's tools.
    let cases: &[(&str, &str, &str, &str, &str)] = &[
        (
            "loop",
            "agents/refund-desk/agent.yaml",
            "loop: careful",
            "loop: carefull",
            "careful",
        ),
        (
            "policy",
            "agents/refund-desk/agent.yaml",
            "policy: approvals",
            "policy: aproovals",
            "approvals",
        ),
        (
            "context-policy",
            "agents/refund-desk/agent.yaml",
            "context-policy: long-threads",
            "context-policy: long-thredz",
            "long-threads",
        ),
        (
            "interceptor",
            "agents/refund-desk/agent.yaml",
            "- stop-runaway-refunds",
            "- stop-runaway-refundz",
            "stop-runaway-refunds",
        ),
        (
            "skill-or-tool",
            "agents/refund-desk/agent.yaml",
            "  - zendesk",
            "  - zendsk",
            "zendesk",
        ),
        (
            "limits-asks",
            "agents/refund-desk/limits.yaml",
            "asks: keep-going",
            "asks: keep-goin",
            "keep-going",
        ),
        (
            "teamwork-asks",
            "agents/refund-desk/teamwork.yaml",
            "asks: carry-on-without-a-check",
            "asks: carry-on-without-a-chek",
            "carry-on-without-a-check",
        ),
        (
            "tidying-asks",
            "context-policies/long-threads.yaml",
            "asks: too-long-to-send",
            "asks: too-long",
            "too-long-to-send",
        ),
        (
            "approval-question",
            "policies/approvals.yaml",
            "question: is-this-ok",
            "question: is-this-okay",
            "is-this-ok",
        ),
        (
            "port-answers",
            "ports/slack.yaml",
            "answers: refund-desk",
            "answers: refnud-desk",
            "refund-desk",
        ),
        (
            "schedule-answers",
            "ports/weekly-review.yaml",
            "answers: refund-desk",
            "answers: nobody",
            "refund-desk",
        ),
        (
            "starts-at",
            "loops/careful.yaml",
            "starts-at: gather",
            "starts-at: gathr",
            "gather",
        ),
        (
            "then-target",
            "loops/careful.yaml",
            "answered: reply",
            "answered: repl",
            "reply",
        ),
        (
            "may-use",
            "loops/careful.yaml",
            "      - zendesk",
            "      - stripe",
            "zendesk",
        ),
    ];

    for (name, file, from, to, should_offer) in cases {
        let root = broken(name, file, from, to);
        let out = pact().args(["check", &root]).output().expect("runs");
        let text = String::from_utf8_lossy(&out.stdout);

        assert!(
            !out.status.success(),
            "[{name}] loaded clean with a name that is not there:\n{text}"
        );
        assert!(
            text.contains(".yaml:"),
            "[{name}] no file:line given:\n{text}"
        );
        assert!(text.contains("  fix: "), "[{name}] no fix offered:\n{text}");
        // The fix has to name what DOES exist. "No such loop" without the list
        // is a dead end for a reader who cannot grep the tree.
        assert!(
            text.contains(should_offer),
            "[{name}] the fix must offer '{should_offer}':\n{text}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }
}

#[test]
fn a_stage_that_may_never_run_and_an_outcome_that_cannot_happen_are_both_refused() {
    // Two more shapes of the same mistake, and neither is a name. `at-most: 0`
    // reads as a setting and means "this stage never runs"; `then: {finished:
    // ...}` reads as an outcome and is not one of the three that exist — the
    // schema said so in its own help text for a round while declaring the field
    // `map of text`, which is a field that contradicts itself.
    let cases: &[(&str, &str, &str, &str)] = &[
        (
            "never-runs",
            "loops/careful.yaml",
            "at-most: 2",
            "at-most: 0",
        ),
        (
            "no-such-outcome",
            "loops/careful.yaml",
            "answered: reply",
            "finished: reply",
        ),
    ];
    for (name, file, from, to) in cases {
        let root = broken(name, file, from, to);
        let out = pact().args(["check", &root]).output().expect("runs");
        let text = String::from_utf8_lossy(&out.stdout);
        assert!(!out.status.success(), "[{name}] must be refused:\n{text}");
        assert!(text.contains("  fix: "), "[{name}] no fix offered:\n{text}");
        let _ = std::fs::remove_dir_all(&root);
    }
    // And the outcome case names the three that do exist, in the author's own
    // words rather than in the group's internal name.
    let root = broken(
        "outcome-words",
        "loops/careful.yaml",
        "answered: reply",
        "finished: reply",
    );
    let ran = pact().args(["check", &root]).output().unwrap();
    let text = String::from_utf8_lossy(&ran.stdout);
    assert!(
        text.contains("is not an outcome a stage can end in"),
        "{text}"
    );
    for outcome in ["used-a-tool", "answered", "too-many-times"] {
        assert!(
            text.contains(outcome),
            "the fix must offer '{outcome}':\n{text}"
        );
    }
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_word_a_diagnostic_uses_for_a_stage_is_the_word_the_author_typed() {
    // The schema called the group `phase` for a round while its own help text
    // said "stage" eleven times, `loops/careful.yaml` said "stage", and every
    // run-time message said "stage". The only place the other word ever
    // surfaced was the diagnostic — `'thn' is not something a phase can have` —
    // which left D13's reader with two names for one thing and one of them
    // findable nowhere.
    let root = broken(
        "stage-word",
        "loops/careful.yaml",
        "    then:\n      answered: done",
        "    thn:\n      answered: done",
    );
    let out = pact().args(["check", &root]).output().unwrap();
    let text = String::from_utf8_lossy(&out.stdout);
    assert!(!out.status.success(), "{text}");
    assert!(text.contains("a stage can have"), "{text}");
    assert!(
        !text.contains("phase"),
        "the author never typed the word 'phase':\n{text}"
    );
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn the_address_vocabulary_in_the_architecture_is_the_one_the_schema_publishes() {
    // §7.13 says "The address vocabulary is INT-2's and is not repeated here",
    // which makes INT-2's table the single source an author reads — and for a
    // round its subject row said `phase` while the executed vocabulary said
    // `stage`. So the address the document published was one every tool
    // refuses, and the word `phase` was findable nowhere else in the authoring
    // surface. Prose and behaviour only stay in step when something fails.
    //
    // Held against `spec/schema.yaml` rather than against a Rust list, because
    // the schema is where the vocabulary now lives: `interceptor.when`'s
    // `parts:` block IS the three closed lists, and it carries the anchor every
    // other address field points at.
    let repo = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let schema = std::fs::read_to_string(repo.join("spec/schema.yaml")).unwrap();
    let arch = std::fs::read_to_string(repo.join("docs/20-ARCHITECTURE-DRAFT.md")).unwrap();

    // The three lists, read from the ANCHOR that defines them rather than from
    // the type name above it. This split on `type: event-address` for a round
    // and silently moved to a different field the day `interceptor.when` became
    // `type: list of event-address` — landing on `watch.when`, whose `parts:` is
    // the alias `*the-address-vocabulary` and holds no words at all. The anchor
    // is the definition site and cannot drift to a second one, because a YAML
    // document may declare it once.
    let block = schema
        .split("parts: &the-address-vocabulary")
        .nth(1)
        .and_then(|s| s.split("        reaches:").next())
        .expect("interceptor.when's `parts:` block anchors the address vocabulary");
    let words_of = |position: &str| -> Vec<String> {
        let after = block
            .split(&format!("          {position}:"))
            .nth(1)
            .unwrap();
        let mut out = Vec::new();
        for line in after.lines() {
            let t = line.trim();
            if let Some(rest) = t.strip_prefix("- ") {
                out.push(rest.to_string());
            } else if let Some(rest) = t.strip_prefix('[') {
                out.extend(
                    rest.trim_end_matches(']')
                        .split(',')
                        .map(|w| w.trim().to_string()),
                );
                break;
            } else if !out.is_empty() {
                break;
            }
        }
        out
    };

    // The three rows of INT-2's table.
    let row = |name: &str| -> String {
        arch.lines()
            .find(|l| l.starts_with(&format!("| {name} | ")))
            .unwrap_or_else(|| panic!("INT-2 has no '{name}' row"))
            .to_string()
    };
    for (position, table_row) in [("part", "scope"), ("thing", "subject"), ("moment", "phase")] {
        let published = row(table_row);
        for word in words_of(position) {
            assert!(
                published.contains(&format!("`{word}`")),
                "INT-2's {table_row} row does not list `{word}`, which the schema does:\n{published}"
            );
        }
    }
    // And nothing the table lists is absent from the schema — the direction the
    // `phase`/`stage` slip actually went. `x-` is the author's own prefix and is
    // prose in that row rather than a member of the list.
    let subjects = words_of("thing");
    for word in row("subject").split('`').skip(1).step_by(2) {
        assert!(
            word == "x-" || subjects.iter().any(|s| s == word),
            "INT-2's subject row lists `{word}`, which is not a thing that happens"
        );
    }
}

#[test]
fn a_long_instruction_may_be_split_across_files_and_nothing_else_changes() {
    // The headline rule of both READMEs — *"A directory is a field; a field may
    // be a directory"* — and `examples/refund-desk/README.md` uses this very
    // field as its example: *"Start with one file; split it up when it gets long.
    // Nothing else changes."* It was not true. `agents/<a>/instructions/01-tone.md`
    // plus `02-length.md` gave *"'instructions' should be some text, but it is a
    // set of settings. fix: Change it to some text"* — a fix whose whole content
    // is "undo what you did", on the field an author splits FIRST. Eve supports
    // `agent/instructions/` and PACT's own README promised it.
    let root = std::env::temp_dir().join(format!("pact-split-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    std::fs::create_dir_all(root.join("agents/helper/instructions")).unwrap();
    std::fs::write(
        root.join("workspace.yaml"),
        "name: split\ndescription: A workspace.\n",
    )
    .unwrap();
    std::fs::write(
        root.join("agents/helper/agent.yaml"),
        "description: Answers questions.\n",
    )
    .unwrap();
    std::fs::write(
        root.join("agents/helper/instructions/01-tone.md"),
        "Be brief.\n",
    )
    .unwrap();
    std::fs::write(
        root.join("agents/helper/instructions/02-length.md"),
        "Never exceed three sentences.\n",
    )
    .unwrap();

    let out = pact()
        .args(["check", root.to_str().unwrap()])
        .output()
        .expect("runs");
    let said = String::from_utf8_lossy(&out.stdout);
    assert!(
        out.status.success(),
        "a field split across files must load:\n{said}"
    );

    // And it must reach a reader IN ORDER — the ordinal prefix is what the author
    // numbered them with, and `serde_json` sorted the keys at the boundary, so
    // `01-tone` arrived after `02-length`.
    let shown = pact()
        .args(["show", root.to_str().unwrap()])
        .output()
        .expect("runs");
    let doc: serde_json::Value = serde_json::from_slice(&shown.stdout).expect("JSON");
    let parts = doc["agents"]["helper"]["instructions"]
        .as_object()
        .expect("a block");
    let keys: Vec<&str> = parts.keys().map(String::as_str).collect();
    assert_eq!(
        keys,
        vec!["tone", "length"],
        "the order the author numbered them"
    );
    let _ = std::fs::remove_dir_all(&root);
}
