//! The worked example is an executable acceptance test for D14/D20:
//! a non-technical author's multi-agent system, with evals and learning,
//! containing no code at all.

use camino::Utf8PathBuf;
use pact_diag::Diagnostics;
use pact_loader::Loader;

fn example() -> Utf8PathBuf {
    Utf8PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../examples/refund-desk")
}

fn load() -> (pact_doc::Node, Diagnostics) {
    let root = example();
    let mut d = Diagnostics::new();
    let n = Loader::new(root.clone()).load(&root, &mut d).expect("example loads");
    d.sort();
    (n, d)
}

#[test]
fn the_example_loads_without_a_single_problem() {
    let (_, d) = load();
    assert!(!d.has_errors(), "{}", d.render());
    assert_eq!(d.warning_count(), 0, "{}", d.render());
}

#[test]
fn the_agent_definition_contains_no_code() {
    // D14: every capability must have a no-code expression.
    //
    // The boundary is precise, and worth stating because it is easy to erode:
    // the *definition* of the system — agents, tools, policies, evals, learning
    // — must be YAML and Markdown only. A payload directory (`scripts/`,
    // `references/`, `assets/`) is different in kind: those are files a skill
    // POINTS AT, carried verbatim, the same way a policy document is. A skill
    // that ships a script is not a no-code skill, and that is a property of
    // that skill rather than of the format.
    //
    // If this test ever needs relaxing beyond payload directories, the format
    // has failed its own definition of success.
    const PAYLOAD_DIRS: &[&str] = &["scripts", "references", "assets", "workspace"];

    let root = example();
    let mut offenders = Vec::new();
    let mut stack = vec![root.clone()];
    while let Some(dir) = stack.pop() {
        for e in std::fs::read_dir(&dir).unwrap().flatten() {
            let p = Utf8PathBuf::from_path_buf(e.path()).unwrap();
            if p.is_dir() {
                // Dot-directories are skipped for the same reason `Policy::is_ignored`
                // skips them at load: `.pact/` is DERIVED (D2), not authored. A
                // `watch:` document writes its record there, so a workspace that has
                // actually been RUN has a `.pact/watch/*.jsonl` in it — and a
                // workspace that has been run is still a no-code workspace. Before
                // this line the whole Rust suite went red the first time anybody
                // executed the example, which is a test that punishes using the
                // thing it is testing.
                let name = p.file_name().unwrap_or_default();
                if !name.starts_with('.') && !PAYLOAD_DIRS.contains(&name) {
                    stack.push(p);
                }
            } else if !matches!(p.extension(), Some("yaml" | "yml" | "md")) {
                offenders.push(p.to_string());
            }
        }
    }
    assert!(offenders.is_empty(), "code in the agent definition: {offenders:?}");
}

#[test]
fn the_supervisor_and_both_specialists_are_present() {
    let (n, _) = load();
    let agents = n.get("agents").expect("agents/ became a field");
    for who in ["refund-desk", "policy-checker", "fraud-checker"] {
        let a = agents.get(who).unwrap_or_else(|| panic!("missing agent {who}"));
        assert!(a.get("name").is_some(), "{who} has a name");
        assert!(a.get("instructions").is_some(), "{who}'s instructions.md became a field");
    }
}

#[test]
fn separate_files_became_fields_of_the_agent_that_owns_them() {
    // The Expansion Rule: needs.yaml and limits.yaml sit beside agent.yaml and
    // are indistinguishable from having been written inside it.
    let (n, _) = load();
    let desk = n.get("agents").and_then(|a| a.get("refund-desk")).unwrap();
    assert_eq!(desk.get("needs").unwrap().get("reasoning").unwrap().as_str(), Some("careful"));
    assert_eq!(desk.get("limits").unwrap().get("feel").unwrap().as_str(), Some("interactive"));
    // `yes` stays text so a model-scores field like "NO" is never mangled;
    // the schema layer coerces where a yes/no is actually expected.
    assert_eq!(desk.get("needs").unwrap().get("tool-calling").unwrap().as_str(), Some("yes"));
    // The core spellings expand to an ENFORCED budget as well as a reported
    // objective, so a support lead's few lines are a real spend cap. They are
    // one flat family now: `stop-after: {tool-calls, turns}` is gone, because
    // `turns` and `steps-at-most` were two names for one counter — the mistake
    // the `same-setting-twice` rule exists to catch, sitting in the
    // specification itself — and `turn` already means something else in the
    // event lattice, where a turn contains steps.
    let limits = desk.get("limits").unwrap();
    assert!(limits.get("steps-at-most").is_some(), "the one loop counter");
    assert!(limits.get("tool-calls-at-most").is_some());
    // And a ceiling always says what happens when it is reached.
    assert!(limits.get("when-it-runs-out").is_some());
}

#[test]
fn the_join_policy_is_a_field_of_the_agent_that_owns_the_team() {
    // G8. Eve takes these three decisions in code — all-or-nothing barrier,
    // serial starts, even token split — and an author can say none of them.
    // Here they are three lines in `teamwork.yaml`, sitting beside the `team:`
    // they govern, and the Expansion Rule makes that indistinguishable from
    // having been written inside `agent.yaml`.
    let (n, _) = load();
    let tw = n
        .get("agents")
        .and_then(|a| a.get("refund-desk"))
        .and_then(|d| d.get("teamwork"))
        .expect("teamwork.yaml became a field of the agent");
    assert_eq!(tw.get("waits-for").unwrap().as_str(), Some("everyone"));
    assert_eq!(tw.get("starts").unwrap().as_str(), Some("all-at-once"));
    assert_eq!(tw.get("divides-the-budget").unwrap().as_str(), Some("by-share"));
    assert_eq!(tw.get("if-someone-fails").unwrap().as_str(), Some("ask-a-person"));

    // A share is declared for every member of the team, or the budget policy
    // names somebody who gets nothing.
    let team = n.get("agents").and_then(|a| a.get("refund-desk")).and_then(|d| d.get("team"));
    let shares = tw.get("shares").and_then(pact_doc::Node::as_map).expect("shares");
    for member in team.and_then(pact_doc::Node::as_map).expect("team").keys() {
        assert!(shares.contains_key(member), "no share declared for {member}");
    }
}

#[test]
fn eval_cases_keep_their_authored_order_and_lose_the_number_prefix() {
    let (n, _) = load();
    let cases = n.get("evals").and_then(|e| e.get("cases")).expect("evals/cases/ became a field");
    let keys: Vec<&str> = cases.as_map().unwrap().keys().map(String::as_str).collect();
    assert_eq!(
        keys,
        vec![
            "clear-approve",
            "outside-window",
            "fraud-signal",
            "partial-gift-card",
            "personalised-item",
            "sale-item-damaged",
        ],
        "cases must keep the order their filenames give them, with NN- stripped"
    );
}

#[test]
fn the_learning_rules_distinguish_safe_changes_from_ones_needing_a_person() {
    // D23: blast-radius classification has to be expressible by the author.
    let (n, _) = load();
    let l = n.get("learning").expect("learning.yaml became a field");
    assert!(l.get("may-improve-on-its-own").unwrap().as_list().unwrap().len() >= 2);
    assert!(l.get("needs-a-person-to-approve").unwrap().as_list().unwrap().len() >= 3);
}

#[test]
fn loading_is_deterministic() {
    // Reproducible digests depend on this. Load twice; require identical JSON.
    let (a, _) = load();
    let (b, _) = load();
    assert_eq!(a.to_json(), b.to_json());
}

#[test]
fn the_flat_and_expanded_forms_have_the_same_digest() {
    // AC-1.4 at the level that actually matters: a beginner's single file and
    // an expert's tree are the same artifact, so they cache, sign and lock the
    // same. If this ever fails, the Expansion Rule is not an equivalence.
    use camino::Utf8PathBuf;
    use std::fs;

    let base = Utf8PathBuf::from(std::env::temp_dir().to_string_lossy().to_string())
        .join(format!("pact-digest-eq-{}", std::process::id()));
    let _ = fs::remove_dir_all(&base);

    let flat = base.join("flat");
    fs::create_dir_all(&flat).unwrap();
    fs::write(
        flat.join("agent.yaml"),
        "name: Refund Desk\ndescription: Decides refunds\ninstructions: Be precise.\nneeds:\n  reasoning: careful\n",
    )
    .unwrap();

    let tree = base.join("tree");
    fs::create_dir_all(&tree).unwrap();
    fs::write(tree.join("agent.yaml"), "name: Refund Desk\ndescription: Decides refunds\n").unwrap();
    fs::write(tree.join("instructions.md"), "Be precise.").unwrap();
    fs::write(tree.join("needs.yaml"), "reasoning: careful\n").unwrap();

    let load = |p: &Utf8PathBuf| {
        let mut d = Diagnostics::new();
        let n = Loader::new(p.clone()).load(p, &mut d).expect("loads");
        assert!(!d.has_errors(), "{}", d.render());
        n
    };

    let a = load(&flat);
    let b = load(&tree);
    // NOT normalised. This used to rewrite the `instructions` node on both sides
    // before taking the digest, which meant the headline claim — *"both produce
    // the identical document"* — was held by a test that made them identical.
    // `pact_doc::prose` takes the trailing newline off at LOAD instead, so the
    // digests below are of what a runtime actually receives.

    assert_eq!(
        pact_doc::digest(&a),
        pact_doc::digest(&b),
        "a field and its file form must be the same artifact"
    );
    let _ = fs::remove_dir_all(&base);
}
