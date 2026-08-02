//! `gaia-ai-runtime` must find and run a PACT tree with no build step (D2, AC-6.1).

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn examples() -> String {
    format!("{}/../../examples", env!("CARGO_MANIFEST_DIR"))
}

fn inventory() -> serde_json::Value {
    let out = pact().args(["discover", &examples()]).output().expect("runs");
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
    serde_json::from_slice(&out.stdout).expect("discover emits JSON")
}

/// The worked example's entry in the inventory, found BY NAME.
///
/// It was `inv[0]`, which meant "the first workspace discovery happened to
/// return" — true while `examples/` held one workspace and wrong the moment
/// `examples/patterns/` landed beside it, when index 0 became `debate`. An
/// index into a walk of the filesystem is not an identifier.
fn refund_desk(inv: &serde_json::Value) -> &serde_json::Value {
    inv.as_array()
        .expect("an array of workspaces")
        .iter()
        .find(|w| w["workspace"] == "refund-desk")
        .expect("examples/refund-desk must be discovered")
}

#[test]
fn a_workspace_is_found_by_walking_the_tree() {
    let inv = inventory();
    // EVERY workspace under `examples/`, compared against the directories that
    // actually hold one. The assertion was `len() == 1`, which stopped being
    // about walking the tree the moment there was more than one thing to walk —
    // it passed for eight rounds and then failed for the right reason.
    let mut on_disk: Vec<String> = Vec::new();
    let mut stack = vec![std::path::PathBuf::from(examples())];
    while let Some(dir) = stack.pop() {
        for e in std::fs::read_dir(&dir).unwrap().flatten() {
            let p = e.path();
            if p.is_dir() && !p.file_name().unwrap().to_string_lossy().starts_with('.') {
                if p.join("workspace.yaml").exists() {
                    on_disk.push(p.file_name().unwrap().to_string_lossy().into_owned());
                } else {
                    stack.push(p);
                }
            }
        }
    }
    let mut found: Vec<String> = inv
        .as_array()
        .unwrap()
        .iter()
        .map(|w| w["root"].as_str().unwrap().rsplit('/').next().unwrap().to_string())
        .collect();
    on_disk.sort();
    found.sort();
    assert_eq!(found, on_disk, "discovery must find every workspace under examples/");
    assert!(on_disk.len() > 1, "this stops meaning anything with one workspace");
    assert_eq!(refund_desk(&inv)["workspace"], "refund-desk");
}

#[test]
fn discovery_needs_no_build_artifact() {
    // D2: `.pact/` is a cache. Deleting it must cost time, never correctness.
    let cache = format!("{}/refund-desk/.pact", examples());
    let _ = std::fs::remove_dir_all(&cache);
    assert!(!std::path::Path::new(&cache).exists());
    let inv = inventory();
    assert!(!refund_desk(&inv)["agents"].as_array().unwrap().is_empty());
}

#[test]
fn every_agent_is_listed_with_what_the_runtime_must_supply() {
    let inv = inventory();
    let agents = refund_desk(&inv)["agents"].as_array().unwrap();
    let ids: Vec<&str> = agents.iter().map(|a| a["id"].as_str().unwrap()).collect();
    for expected in ["pact:refund-desk", "pact:policy-checker", "pact:fraud-checker"] {
        assert!(ids.contains(&expected), "{expected} missing from {ids:?}");
    }

    let desk = agents.iter().find(|a| a["id"] == "pact:refund-desk").unwrap();
    // The runtime already owns models, tools and skills. Discovery tells it
    // which ones this agent needs, so it can refuse cleanly rather than fail
    // part-way through a run.
    let caps: Vec<&str> = desk["capabilities"].as_array().unwrap()
        .iter().map(|c| c.as_str().unwrap()).collect();
    assert!(caps.contains(&"reasoning:careful"), "{caps:?}");
    assert!(caps.contains(&"images"), "{caps:?}");
    assert!(desk["uses"].as_array().unwrap().len() >= 2);
    assert_eq!(desk["team"].as_array().unwrap().len(), 2);
    // `slo` and `limits` are two different questions, and this assertion used to
    // be `desk["slo"].is_object()` alone — which was true while the key `slo`
    // carried the WHOLE `limits` block, so a runtime reading it for a latency
    // promise was handed `steps-at-most: 12` as a service level. An assertion
    // about a value's TYPE cannot catch a value that is the wrong thing.
    let slo = desk["slo"].as_object().expect("the latency promise must reach the runtime");
    let limits = desk["limits"].as_object().expect("and the ceilings must too");
    assert_eq!(slo["finishes-within"], "30s", "{slo:?}");
    assert_eq!(slo["feel"], "interactive", "{slo:?}");
    for ceiling in ["steps-at-most", "tool-calls-at-most", "when-it-runs-out", "asks"] {
        assert!(
            !slo.contains_key(ceiling),
            "`{ceiling}` stops a run; it is not a latency promise, and a runtime \
             reading `slo` to decide how long to wait would read it as one: {slo:?}"
        );
        assert!(limits.contains_key(ceiling), "`{ceiling}` is missing from `limits`: {limits:?}");
    }
    // `finishes-within` is in both on purpose — the author's own file says it is
    // "both the promise and, with no `runs-for-at-most` written, the wall-clock
    // stop", so dropping it from either side loses half of what it means.
    assert_eq!(limits["finishes-within"], "30s", "{limits:?}");

    // WHETHER IT IS GOVERNED, and by what. The inventory carried none of this, so
    // a runtime routing work could not tell an agent that stops to ask a person
    // before moving money from one that does not.
    let gov = desk["governance"].as_object().expect("governance must reach the runtime");
    assert_eq!(gov["policy"], "approvals", "{gov:?}");
    assert_eq!(gov["context-policy"], "long-threads", "{gov:?}");
    assert_eq!(gov["teamwork"], true, "{gov:?}");
    let rules: Vec<&str> = gov["interceptors"].as_array().unwrap()
        .iter().map(|c| c.as_str().unwrap()).collect();
    assert!(rules.contains(&"stop-runaway-refunds"), "{rules:?}");
    // `remembers:` is a MAP in the file and a list of names here, so a consumer
    // needs one shape for "which ones" rather than two.
    let facts: Vec<&str> = gov["remembers"].as_array().unwrap()
        .iter().map(|c| c.as_str().unwrap()).collect();
    assert!(facts.contains(&"payments-was-approved"), "{facts:?}");

    // And an agent that is governed by nothing says so, rather than being absent
    // from the answer — a missing key and "no policy" read the same to a consumer
    // and mean different things.
    let checker = agents.iter()
        .find(|a| a["id"] == "pact:policy-checker")
        .expect("the example ships three agents");
    let none = checker["governance"].as_object().unwrap();
    assert!(none["policy"].is_null(), "{none:?}");
    assert_eq!(none["teamwork"], false, "{none:?}");
    assert!(none["interceptors"].as_array().unwrap().is_empty(), "{none:?}");
    // THIS agent's own `evals:` line, and the suite it names — not a boolean read
    // off the workspace. Reading the workspace reported `evals: true` for all
    // three agents while only this one carries the line, so a runtime indexing
    // the inventory to decide which agents are verified got a false positive on
    // two of three.
    assert_eq!(desk["evals"], "/evals/suite.yaml");
    let unchecked = agents.iter().find(|a| a["id"] == "pact:fraud-checker").unwrap();
    assert!(unchecked["evals"].is_null(), "an agent with no checks must not claim any");
    assert_eq!(desk["runnable"], true);
}

#[test]
fn the_inventory_carries_a_digest_so_the_runtime_can_cache_safely() {
    let inv = inventory();
    let digest = refund_desk(&inv)["digest"].as_str().unwrap().to_string();
    assert!(digest.starts_with("sha256:"));
    let again = inventory();
    assert_eq!(refund_desk(&again)["digest"].as_str().unwrap(), digest, "must be stable");
    // And every workspace gets its OWN digest. Indexing position 0 twice would
    // have compared one workspace with itself however many there were, so this
    // said nothing about the other eight.
    let all: Vec<&str> = inv.as_array().unwrap()
        .iter().map(|w| w["digest"].as_str().unwrap()).collect();
    assert_eq!(
        all.len(),
        all.iter().collect::<std::collections::BTreeSet<_>>().len(),
        "two workspaces share a digest, so a runtime caching on it would serve \
         one workspace's agents for another: {all:?}"
    );
}

#[test]
fn an_agent_projects_to_an_a2a_card() {
    // AC-6.3: agents are discoverable through the facade the runtime already
    // publishes, not a second catalogue.
    let out = pact()
        .args(["card", "refund-desk", &format!("{}/refund-desk", examples())])
        .output().expect("runs");
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
    let card: serde_json::Value = serde_json::from_slice(&out.stdout).unwrap();
    assert_eq!(card["protocolVersion"], "1.0");
    assert_eq!(card["name"], "Refund Desk");
    let skills = card["skills"].as_array().unwrap();
    assert!(skills.iter().any(|s| s["id"] == "handoff:policy-checker"),
            "team members must be discoverable as handoffs");
}

#[test]
fn the_card_is_a_facade_not_an_internal_dump() {
    // Instructions, filesystem paths and credentials must not be projected —
    // the same rule the runtime's existing card projection follows.
    let out = pact()
        .args(["card", "refund-desk", &format!("{}/refund-desk", examples())])
        .output().unwrap();
    let text = String::from_utf8_lossy(&out.stdout);
    assert!(!text.contains("You decide whether"), "instructions leaked");
    assert!(!text.contains("/home/"), "filesystem path leaked");
    assert!(!text.contains("instructions"), "instructions key leaked");
}

#[test]
fn asking_for_an_unknown_agent_fails_loudly() {
    let out = pact()
        .args(["card", "nosuchagent", &format!("{}/refund-desk", examples())])
        .output().unwrap();
    assert!(!out.status.success());
    assert!(String::from_utf8_lossy(&out.stderr).contains("nosuchagent"));
}
