//! `gaia-ai-runtime` must find and run a PACT tree with no build step (D2, AC-6.1).

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

fn examples() -> String {
    format!("{}/../../examples", env!("CARGO_MANIFEST_DIR"))
}

fn inventory() -> serde_json::Value {
    let out = pact()
        .args(["discover", &examples()])
        .output()
        .expect("runs");
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
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
        .map(|w| {
            w["root"]
                .as_str()
                .unwrap()
                .rsplit('/')
                .next()
                .unwrap()
                .to_string()
        })
        .collect();
    on_disk.sort();
    found.sort();
    assert_eq!(
        found, on_disk,
        "discovery must find every workspace under examples/"
    );
    assert!(
        on_disk.len() > 1,
        "this stops meaning anything with one workspace"
    );
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
    for expected in [
        "pact:refund-desk",
        "pact:policy-checker",
        "pact:fraud-checker",
    ] {
        assert!(ids.contains(&expected), "{expected} missing from {ids:?}");
    }

    let desk = agents
        .iter()
        .find(|a| a["id"] == "pact:refund-desk")
        .unwrap();
    // The runtime already owns models, tools and skills. Discovery tells it
    // which ones this agent needs, so it can refuse cleanly rather than fail
    // part-way through a run.
    let caps: Vec<&str> = desk["capabilities"]
        .as_array()
        .unwrap()
        .iter()
        .map(|c| c.as_str().unwrap())
        .collect();
    assert!(caps.contains(&"reasoning:careful"), "{caps:?}");
    assert!(caps.contains(&"images"), "{caps:?}");
    assert!(desk["uses"].as_array().unwrap().len() >= 2);
    assert_eq!(desk["team"].as_array().unwrap().len(), 2);
    // `slo` and `limits` are two different questions, and this assertion used to
    // be `desk["slo"].is_object()` alone — which was true while the key `slo`
    // carried the WHOLE `limits` block, so a runtime reading it for a latency
    // promise was handed `steps-at-most: 12` as a service level. An assertion
    // about a value's TYPE cannot catch a value that is the wrong thing.
    let slo = desk["slo"]
        .as_object()
        .expect("the latency promise must reach the runtime");
    let limits = desk["limits"]
        .as_object()
        .expect("and the ceilings must too");
    assert_eq!(slo["finishes-within"], "30s", "{slo:?}");
    assert_eq!(slo["feel"], "interactive", "{slo:?}");
    for ceiling in [
        "steps-at-most",
        "tool-calls-at-most",
        "when-it-runs-out",
        "asks",
    ] {
        assert!(
            !slo.contains_key(ceiling),
            "`{ceiling}` stops a run; it is not a latency promise, and a runtime \
             reading `slo` to decide how long to wait would read it as one: {slo:?}"
        );
        assert!(
            limits.contains_key(ceiling),
            "`{ceiling}` is missing from `limits`: {limits:?}"
        );
    }
    // `finishes-within` is in both on purpose — the author's own file says it is
    // "both the promise and, with no `runs-for-at-most` written, the wall-clock
    // stop", so dropping it from either side loses half of what it means.
    assert_eq!(limits["finishes-within"], "30s", "{limits:?}");

    // WHETHER IT IS GOVERNED, and by what. The inventory carried none of this, so
    // a runtime routing work could not tell an agent that stops to ask a person
    // before moving money from one that does not.
    let gov = desk["governance"]
        .as_object()
        .expect("governance must reach the runtime");
    assert_eq!(gov["policy"], "approvals", "{gov:?}");
    assert_eq!(gov["context-policy"], "long-threads", "{gov:?}");
    assert_eq!(gov["teamwork"], true, "{gov:?}");
    let rules: Vec<&str> = gov["interceptors"]
        .as_array()
        .unwrap()
        .iter()
        .map(|c| c.as_str().unwrap())
        .collect();
    assert!(rules.contains(&"stop-runaway-refunds"), "{rules:?}");
    // `remembers:` is a MAP in the file and a list of names here, so a consumer
    // needs one shape for "which ones" rather than two.
    let facts: Vec<&str> = gov["remembers"]
        .as_array()
        .unwrap()
        .iter()
        .map(|c| c.as_str().unwrap())
        .collect();
    assert!(facts.contains(&"payments-was-approved"), "{facts:?}");

    // And an agent that is governed by nothing says so, rather than being absent
    // from the answer — a missing key and "no policy" read the same to a consumer
    // and mean different things.
    let checker = agents
        .iter()
        .find(|a| a["id"] == "pact:policy-checker")
        .expect("the example ships three agents");
    let none = checker["governance"].as_object().unwrap();
    assert!(none["policy"].is_null(), "{none:?}");
    assert_eq!(none["teamwork"], false, "{none:?}");
    assert!(
        none["interceptors"].as_array().unwrap().is_empty(),
        "{none:?}"
    );
    // THIS agent's own `evals:` line, and the suite it names — not a boolean read
    // off the workspace. Reading the workspace reported `evals: true` for all
    // three agents while only this one carries the line, so a runtime indexing
    // the inventory to decide which agents are verified got a false positive on
    // two of three.
    assert_eq!(desk["evals"], "/evals/suite.yaml");
    let unchecked = agents
        .iter()
        .find(|a| a["id"] == "pact:fraud-checker")
        .unwrap();
    assert!(
        unchecked["evals"].is_null(),
        "an agent with no checks must not claim any"
    );
    assert_eq!(desk["runnable"], true);
}

#[test]
fn the_inventory_carries_a_digest_so_the_runtime_can_cache_safely() {
    let inv = inventory();
    let digest = refund_desk(&inv)["digest"].as_str().unwrap().to_string();
    assert!(digest.starts_with("sha256:"));
    let again = inventory();
    assert_eq!(
        refund_desk(&again)["digest"].as_str().unwrap(),
        digest,
        "must be stable"
    );
    // And every workspace gets its OWN digest. Indexing position 0 twice would
    // have compared one workspace with itself however many there were, so this
    // said nothing about the other eight.
    let all: Vec<&str> = inv
        .as_array()
        .unwrap()
        .iter()
        .map(|w| w["digest"].as_str().unwrap())
        .collect();
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
        .args([
            "card",
            "refund-desk",
            &format!("{}/refund-desk", examples()),
        ])
        .output()
        .expect("runs");
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let card: serde_json::Value = serde_json::from_slice(&out.stdout).unwrap();
    assert_eq!(card["protocolVersion"], "1.0");
    assert_eq!(card["name"], "Refund Desk");
    let skills = card["skills"].as_array().unwrap();
    assert!(
        skills.iter().any(|s| s["id"] == "handoff:policy-checker"),
        "team members must be discoverable as handoffs"
    );
}

#[test]
fn the_card_is_a_facade_not_an_internal_dump() {
    // Instructions, filesystem paths and credentials must not be projected —
    // the same rule the runtime's existing card projection follows.
    let out = pact()
        .args([
            "card",
            "refund-desk",
            &format!("{}/refund-desk", examples()),
        ])
        .output()
        .unwrap();
    let text = String::from_utf8_lossy(&out.stdout);
    assert!(!text.contains("You decide whether"), "instructions leaked");
    assert!(!text.contains("/home/"), "filesystem path leaked");
    assert!(!text.contains("instructions"), "instructions key leaked");
}

#[test]
fn asking_for_an_unknown_agent_fails_loudly() {
    let out = pact()
        .args([
            "card",
            "nosuchagent",
            &format!("{}/refund-desk", examples()),
        ])
        .output()
        .unwrap();
    assert!(!out.status.success());
    assert!(String::from_utf8_lossy(&out.stderr).contains("nosuchagent"));
}

/// Every shape an agent's location can take, laid down as sibling workspaces.
///
/// The Expansion Rule's whole claim is that the authoring forms are ONE
/// document, so anything the inventory says about an agent has to be true
/// whichever way it was written. The last two are not authoring forms but they
/// are trees an author can produce, and each one used to break the field in its
/// own way. Returns the parent directory holding the six workspaces.
fn every_form(name: &str) -> std::path::PathBuf {
    let root =
        std::env::temp_dir().join(format!("pact-discover-path-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    let agent = "name: Desk\ndescription: Handles things.\ninstructions: Do it.\n";

    // The folder form: `agents/desk/agent.yaml`.
    std::fs::create_dir_all(root.join("folder/agents/desk")).unwrap();
    std::fs::write(root.join("folder/workspace.yaml"), "name: folder-form\n").unwrap();
    std::fs::write(root.join("folder/agents/desk/agent.yaml"), agent).unwrap();

    // The flat form: `agents/desk.yaml`, one file and no folder.
    std::fs::create_dir_all(root.join("flat/agents")).unwrap();
    std::fs::write(root.join("flat/workspace.yaml"), "name: flat-form\n").unwrap();
    std::fs::write(root.join("flat/agents/desk.yaml"), agent).unwrap();

    // The inline form: written into `workspace.yaml` itself, no `agents/` at all.
    std::fs::create_dir_all(root.join("inline")).unwrap();
    std::fs::write(
        root.join("inline/workspace.yaml"),
        "name: inline-form\nagents:\n  desk:\n    name: Desk\n    \
         description: Handles things.\n    instructions: Do it.\n",
    )
    .unwrap();

    // A folder whose settings have no file of their own: every field is carried
    // by a sibling, and there is no `agent.yaml` to name.
    std::fs::create_dir_all(root.join("siblings/agents/desk")).unwrap();
    std::fs::write(root.join("siblings/workspace.yaml"), "name: sibling-form\n").unwrap();
    std::fs::write(root.join("siblings/agents/desk/name.md"), "Desk\n").unwrap();
    std::fs::write(
        root.join("siblings/agents/desk/description.md"),
        "Handles things.\n",
    )
    .unwrap();
    std::fs::write(
        root.join("siblings/agents/desk/instructions.md"),
        "Do it.\n",
    )
    .unwrap();

    // A shortcut pointing OUTSIDE the workspace. The loader refuses to follow it
    // (`loader/symlink-skipped`), so PACT reads nothing from the target.
    std::fs::create_dir_all(root.join("outside")).unwrap();
    std::fs::write(root.join("outside/desk.yaml"), agent).unwrap();
    std::fs::create_dir_all(root.join("shortcut/agents")).unwrap();
    std::fs::write(
        root.join("shortcut/workspace.yaml"),
        "name: shortcut-form\n",
    )
    .unwrap();
    symlink(
        &root.join("outside/desk.yaml"),
        &root.join("shortcut/agents/desk.yaml"),
    );

    // A shortcut with nothing on the other end.
    std::fs::create_dir_all(root.join("dangling/agents")).unwrap();
    std::fs::write(
        root.join("dangling/workspace.yaml"),
        "name: dangling-form\n",
    )
    .unwrap();
    symlink(
        std::path::Path::new("/no/such/file/anywhere.yaml"),
        &root.join("dangling/agents/desk.yaml"),
    );

    root
}

#[cfg(unix)]
fn symlink(target: &std::path::Path, link: &std::path::Path) {
    std::os::unix::fs::symlink(target, link).unwrap();
}
#[cfg(windows)]
fn symlink(target: &std::path::Path, link: &std::path::Path) {
    std::os::windows::fs::symlink_file(target, link).unwrap();
}

fn discover_at(dir: &std::path::Path, arg: &str) -> serde_json::Value {
    let out = pact()
        .current_dir(dir)
        .args(["discover", arg])
        .output()
        .expect("runs");
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    serde_json::from_slice(&out.stdout).expect("discover emits JSON")
}

/// One agent of one workspace, by the workspace's own name.
fn agent_of<'a>(inv: &'a serde_json::Value, workspace: &str) -> &'a serde_json::Value {
    &inv.as_array()
        .unwrap()
        .iter()
        .find(|w| w["workspace"] == workspace)
        .unwrap_or_else(|| panic!("'{workspace}' must be discovered: {inv}"))["agents"]
        .as_array()
        .unwrap()[0]
}

/// Every `path` the inventory publishes names a place that is on disk, and that
/// place is inside the workspace being described.
///
/// The path was assembled from the map key — `root/agents/<key>` — and handed
/// out for all three authoring forms, while only the first of them has that
/// directory. Measured on one agent written three ways:
///
/// ```text
/// === folder (agents/desk/agent.yaml) ===
///     "path": "/tmp/repro/folder/agents/desk",     <- exists
/// === flat (agents/desk.yaml) ===
///     "path": "/tmp/repro/flat/agents/desk",       <- NO SUCH DIRECTORY
/// === inline (in workspace.yaml) ===
///     "path": "/tmp/repro/inline/agents/desk",     <- NO SUCH DIRECTORY
/// ```
///
/// Reading it off the span fixed that but, resolved with `std::fs::canonicalize`,
/// opened a second hole in the other direction: a shortcut the loader had
/// REFUSED was followed anyway, so the inventory named a readable file outside
/// the project that PACT never opened —
///
/// ```text
/// $ pact check symws
/// warning: '…/symws/agents/desk.yaml' is a shortcut to somewhere else, so it was skipped.
///   rule: loader/symlink-skipped
/// $ pact discover symws
///     "path": "/…/repro/shared/desk.yaml",   <- OUTSIDE the workspace
///     "description": null,                   <- because nothing was read from it
///     "runnable": false
/// ```
///
/// Mutation A: restore
/// `o.insert("path".into(), J::String(found.root.join("agents").join(key).to_string()));`
/// in `crates/pact-cli/src/discover.rs`. Without the fix every other assertion
/// in this file stayed green — nothing anywhere read `path`.
///
/// Mutation B: put `std::fs::canonicalize` back in `observed_path` in place of
/// `absolutise`. The existence assertions all stay green; only the `shortcut`
/// containment assertion catches it.
#[test]
fn every_path_the_inventory_publishes_is_a_place_inside_the_workspace_that_is_there() {
    let root = every_form("exists");
    let inv = discover_at(&root, root.to_str().unwrap());

    let workspaces = inv.as_array().expect("an array of workspaces");
    assert_eq!(workspaces.len(), 6, "six workspaces, one per shape: {inv}");

    for w in workspaces {
        let ws_root = w["root"].as_str().expect("a root");
        for a in w["agents"].as_array().unwrap() {
            let Some(path) = a["path"].as_str() else {
                continue;
            }; // null is a legal answer
            // THE assertion. A constructed string cannot satisfy it.
            assert!(
                std::path::Path::new(path).exists(),
                "{} in workspace '{}' is published at '{path}', which is not on disk",
                a["id"],
                w["workspace"]
            );
            // And the projection never names a place outside what it describes.
            assert!(
                std::path::Path::new(path).starts_with(ws_root),
                "{} in workspace '{}' is published at '{path}', which is outside its root \
                 '{ws_root}'",
                a["id"],
                w["workspace"]
            );
        }
    }

    let path_of = |name: &str| agent_of(&inv, name)["path"].clone();
    let ends = |name: &str, tail: &str| {
        let p = path_of(name);
        assert!(
            p.as_str().is_some_and(|s| s.ends_with(tail)),
            "'{name}' should be located at …{tail}, got {p}"
        );
    };

    // The file the author really wrote the agent in, per form.
    ends("folder-form", "/folder/agents/desk/agent.yaml");
    ends("flat-form", "/flat/agents/desk.yaml");
    // Inline: the workspace file itself. A present-and-true path beats an absent
    // one — the single-file form is the most portable way to write an agent, and
    // it would otherwise be the one form discovery could not locate.
    ends("inline-form", "/inline/workspace.yaml");
    // A folder with no settings file of its own gives THE FOLDER. The published
    // contract is "a place that is there", not "a file", precisely because this
    // shape exists; a consumer that needs a file asks the filesystem which it got.
    ends("sibling-form", "/siblings/agents/desk");
    assert!(
        std::path::Path::new(path_of("sibling-form").as_str().unwrap()).is_dir(),
        "the sibling form's place is a directory, and the contract says so"
    );
    // The shortcut: its OWN in-workspace path, never the target it points at.
    // That is the place the author must go and fix, and it is the path
    // `loader/symlink-skipped` already names.
    ends("shortcut-form", "/shortcut/agents/desk.yaml");
    assert_eq!(
        agent_of(&inv, "shortcut-form")["runnable"],
        serde_json::Value::Bool(false),
        "PACT read nothing from a refused shortcut, and the inventory still says so"
    );
    // Nothing on the other end of the link, so there is no place to name. This is
    // the `null` branch of the contract, exercised rather than merely described.
    assert_eq!(
        path_of("dangling-form"),
        serde_json::Value::Null,
        "a shortcut to nothing has no place to publish"
    );

    let _ = std::fs::remove_dir_all(&root);
}

/// The whole inventory is the same document however the workspace was named on
/// the command line.
///
/// `root` was emitted verbatim as typed and `path` was absolute, so one tree
/// produced two different inventories, and the two location keys in one object
/// were in different coordinate systems — `path.strip_prefix(root)`, the obvious
/// way for a consumer to ask where in the workspace an agent lives, failed on
/// every invocation that was not already absolute:
///
/// ```text
/// $ pact discover examples/refund-desk
///     "root": "examples/refund-desk",
///     "path": "/home/…/examples/refund-desk/agents/fraud-checker/agent.yaml",
/// ```
///
/// Mutation: restore `J::String(found.root.to_string())` for the `root` key in
/// `crates/pact-cli/src/discover.rs`, or the constructed `path` line. Either
/// makes the whole-document comparison fail; comparing only the `path` list, as
/// this test first did, missed the `root` half entirely.
#[test]
fn the_whole_inventory_is_the_same_whatever_directory_it_was_asked_from() {
    let root = every_form("stable");

    let absolute = discover_at(&root, root.to_str().unwrap());
    let relative = discover_at(&root, ".");

    assert_eq!(
        absolute, relative,
        "one tree, two inventories: naming it absolutely gave {absolute:#}, naming it `.` gave \
         {relative:#}"
    );

    for w in relative.as_array().unwrap() {
        let ws_root = w["root"].as_str().expect("a root");
        assert!(
            std::path::Path::new(ws_root).is_absolute(),
            "a root only a particular working directory can resolve is not an address: {ws_root}"
        );
        for a in w["agents"].as_array().unwrap() {
            let Some(path) = a["path"].as_str() else {
                continue;
            };
            assert!(
                std::path::Path::new(path).is_absolute(),
                "a path only a particular working directory can resolve is not an address: {path}"
            );
            // The two location keys are joinable, which is the point of settling
            // them in one coordinate system.
            assert!(
                std::path::Path::new(path).strip_prefix(ws_root).is_ok(),
                "'{path}' does not sit under the root '{ws_root}' published beside it"
            );
        }
    }

    let _ = std::fs::remove_dir_all(&root);
}
