//! **A bundle that nothing mounted is reported from a real folder of files.**
//!
//! `crates/pact-loader/src/bundles.rs` holds `brings:` against `contributes:`
//! and warns when nothing mounted a bundle at all. Every test it had built its
//! own document: `s()`, `list()`, `map()`, `tree()`, `mounted()` and
//! `unmounted()` construct a `Value::Map` by hand and no file is ever parsed.
//! Measured before this file existed:
//!
//! ```text
//! $ find examples tests -type d -name bundles
//! $                                    # nothing — not one shipped tree declared one
//! ```
//!
//! (The register asked that with `grep -rn "bundles:" examples/ tests/`, which
//! also returned nothing — and would have gone on returning nothing after a
//! dozen trees declared bundles, because a workspace collection is a **folder**
//! and not a line. Today that grep returns two hits and both are prose, in this
//! tree's own README.)
//!
//! That is the Production Gap Register's own Class A signature defect — *"the
//! tests construct its object directly; nothing on the authored path ever builds
//! one"* — sitting inside the file written to catch it. A hand-built `Node` can
//! be shaped however the test needs; it cannot show that an author typing YAML
//! into a folder produces that shape, and for `bundles:` that question is the
//! whole question, because **`contributes:` is not something an author types**.
//! Its own help says so: *"You do not type this — it is what is in the bundle's
//! own folder."* So either the folder form builds `contributes:` or nothing
//! does, and no hand-built map can tell you which.
//!
//! Everything below reads `tests/trees/what-a-bundle-brings/` off disk through
//! the real `Loader`, against the shipped `spec/schema.yaml`. The tree holds two
//! bundles and the difference between them is one folder:
//!
//! - `bundles/customer-lookup/` has a `contributes/` folder beside its self
//!   file, so its definitions are in this tree and the check is silent;
//! - `bundles/refund-toolkit/` names `from: acme/refund-toolkit`, which nothing
//!   in this project resolves, so `loader/bundle-not-mounted` fires.
//!
//! # Which hand-built tests this supersedes
//!
//! `a_bundle_brings_only_what_it_said` emits three rules, and all three are now
//! witnessed from this tree:
//!
//! | rule | hand-built witness, no longer the only one | here |
//! |---|---|---|
//! | `loader/bundle-not-mounted` | `a_bundle_nothing_mounted_is_said_out_loud`, `an_unmounted_bundle_is_a_warning_and_not_a_refusal`, `a_bundle_that_did_mount_is_not_told_it_did_not` | the three `the_bundle_whose_folder_…` / `a_name_a_platform_team_publishes_…` tests |
//! | `loader/bundle-brings-more-than-it-said` | `a_bundle_that_starts_shipping_approval_rules_is_refused`, `a_bundle_that_quietly_starts_supplying_an_agent_is_refused` | `a_folder_a_bundle_never_said_it_would_bring_is_refused_from_a_real_tree` |
//! | `loader/bundle-brings-an-unknown-kind` | `a_contributed_kind_the_schema_does_not_know_is_refused_and_not_skipped` | `a_folder_naming_no_kind_of_document_pact_has_is_refused_from_a_real_tree` |
//!
//! Not one of those was deleted or weakened — they run in microseconds and pin
//! the wording where the wording is written — and each now carries a comment
//! pointing here. The two refusals reach this tree by adding a *folder* to a
//! copy of it, because adding a folder is how the supply-chain case actually
//! happens: somebody else's version 2.1 ships a `policies/` directory.
//!
//! The claim only this file can make at all is the one in
//! `a_folder_called_contributes_becomes_the_field_the_check_reads`, and the
//! standing record of what is still unbuilt is
//! `nothing_a_bundle_contributes_reaches_the_collections_an_agent_can_name`.
//!
//! # Why the tree is in `tests/trees/` and not in `examples/`
//!
//! `scripts/test-all.sh` runs `pact check --deny-warnings` over
//! `examples/refund-desk`, `examples/answers-from-documents` and
//! `examples/patterns/*/`, on the argument that a warning in a shipped example
//! is teaching somebody the wrong thing. A tree that exercises
//! `loader/bundle-not-mounted` **must warn** — that is the behaviour under test —
//! so putting it in `examples/` would either turn the gate red or force the
//! warning to be downgraded, and downgrading a diagnostic to keep a script green
//! is how a checker stops checking. `tests/trees/` already exists for exactly
//! this: `tests/trees/one-line-gate/` is a real, loadable, documented workspace
//! that no `--deny-warnings` loop visits. Measured:
//!
//! ```text
//! $ cargo run -p pact-cli -- check tests/trees/what-a-bundle-brings
//! warning: the bundle 'refund-toolkit' names `from: acme/refund-toolkit` …
//! OK — tests/trees/what-a-bundle-brings loaded with 1 warning(s).      # exit 0
//! $ cargo run -p pact-cli -- check tests/trees/what-a-bundle-brings --deny-warnings
//! …                                                                    # exit 1
//! ```

use camino::{Utf8Path, Utf8PathBuf};
use pact_diag::Diagnostics;
use pact_doc::Node;
use pact_loader::Loader;
use pact_loader::bundles::a_bundle_brings_only_what_it_said;
use pact_schema::Schema;

fn tree() -> Utf8PathBuf {
    Utf8PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tests/trees/what-a-bundle-brings")
}

/// The shipped specification, read from the file rather than restated.
fn spec() -> Schema {
    let path = Utf8PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../spec/schema.yaml");
    let text = std::fs::read_to_string(&path).expect("spec/schema.yaml");
    let mut d = Diagnostics::new();
    let s = pact_schema::from_doc::schema_from_yaml(&text, &mut d);
    assert!(
        !d.has_errors(),
        "the shipped specification does not load:\n{}",
        d.render()
    );
    s
}

/// The tree off disk, and everything the bundle pass says about it.
fn read() -> (Node, Diagnostics) {
    let root = tree();
    let mut load = Diagnostics::new();
    let doc = Loader::new(root.clone())
        .load(&root, &mut load)
        .expect("the tree loads");
    assert!(
        !load.has_errors(),
        "the shipped tree must load before anything can be asserted about it:\n{}",
        load.render()
    );
    let mut d = Diagnostics::new();
    a_bundle_brings_only_what_it_said(&doc, &spec(), &mut d);
    d.sort();
    (doc, d)
}

// ───────────────────────────────── the folder form builds the thing under test

/// `contributes:` is built by the loader from a folder, not typed by an author.
///
/// This is the claim no hand-built `Node` can make, and it is load-bearing for
/// every other test in this file and in `bundles.rs`: those tests insert a
/// `contributes` key into a map they constructed, and if the loader produced
/// some other shape from a real folder — a different key, a list, a file
/// reference — the whole pass would be checking a document no tree can produce.
///
/// Mutation: rename `bundles/customer-lookup/contributes/` to anything else.
#[test]
fn a_folder_called_contributes_becomes_the_field_the_check_reads() {
    let (doc, _) = read();
    let found = doc
        .get("bundles")
        .and_then(|b| b.get("customer-lookup"))
        .and_then(|b| b.get("contributes"))
        .and_then(|c| c.get("tools"))
        .and_then(|t| t.get("find-customer"))
        .and_then(|t| t.get("description"))
        .and_then(Node::as_str);
    assert_eq!(
        found,
        Some("Finds one customer by their account number."),
        "the loader must build `bundles.customer-lookup.contributes.tools.find-customer` \
         from `bundles/customer-lookup/contributes/tools/find-customer.yaml`, because \
         `contributes:`'s own help says an author never types it"
    );
}

// ───────────────────────────────── the warning, from a real folder of files

/// A bundle nothing mounted is reported by name, with where it said to look.
///
/// Supersedes `bundles.rs::a_bundle_nothing_mounted_is_said_out_loud`, which
/// asserts the same words against a document it built itself.
///
/// Mutation: delete the `diags.push` in the `else` arm of `bundles.rs`, or make
/// the message drop `{name}` or `{where_from}`.
#[test]
fn the_bundle_whose_folder_is_not_here_is_named_and_so_is_where_it_said_to_look() {
    let (_, d) = read();
    let said = d
        .items()
        .iter()
        .find(|x| x.rule == "loader/bundle-not-mounted")
        .expect("an unmounted bundle in a real tree must be reported");
    assert!(said.message.contains("refund-toolkit"), "{}", said.message);
    assert!(
        said.message.contains("acme/refund-toolkit"),
        "{}",
        said.message
    );
    assert!(
        said.message
            .contains("none of its definitions are in this workspace"),
        "the sentence has to say what the author LOSES, not that a field is unresolved: {}",
        said.message
    );
    assert!(
        said.fix.contains("copy what it defines into this tree"),
        "the fix has to say the one thing an author can do about it today: {}",
        said.fix
    );
}

/// It fires **once**, for the bundle whose folder is missing, and not for the
/// one whose folder is here.
///
/// Supersedes `bundles.rs::a_bundle_that_did_mount_is_not_told_it_did_not`. The
/// two bundles in this tree differ in exactly one thing — whether a
/// `contributes/` folder sits beside the self file — so a check that had learned
/// to warn about every `bundles:` entry, or about none, fails here and passes
/// against any tree holding only one bundle.
///
/// Mutation: make the `else` arm unconditional.
#[test]
fn the_bundle_whose_folder_is_here_is_not_told_it_is_missing() {
    let (_, d) = read();
    let unmounted: Vec<&str> = d
        .items()
        .iter()
        .filter(|x| x.rule == "loader/bundle-not-mounted")
        .map(|x| x.message.as_str())
        .collect();
    assert_eq!(
        unmounted.len(),
        1,
        "exactly one of the two bundles in this tree has no folder here:\n{}",
        d.render()
    );
    assert!(
        !unmounted[0].contains("customer-lookup"),
        "`bundles/customer-lookup/contributes/` is right there — telling its author it was \
         not mounted is worse than silence: {}",
        unmounted[0]
    );
}

/// The whole pass produces no error against this tree, and `pact check` exits 0.
///
/// Supersedes `bundles.rs::an_unmounted_bundle_is_a_warning_and_not_a_refusal`.
/// `from:`'s own help says it may be *"a path inside this workspace, or a name
/// your platform team publishes"*, and the second kind is resolved by a host
/// that knows its registry — so refusing `acme/refund-toolkit` outright would
/// break the case the field was written for. This tree writes both kinds of
/// `from:` in one workspace, which is the case that argument is about.
///
/// Mutation: change `Diagnostic::warning` to `Diagnostic::error` in `bundles.rs`.
#[test]
fn a_name_a_platform_team_publishes_is_a_warning_and_never_a_refusal() {
    let (_, d) = read();
    assert!(!d.has_errors(), "{}", d.render());
    assert_eq!(
        d.items().len(),
        1,
        "one bundle unmounted, one mounted within its `brings:`, so one diagnostic:\n{}",
        d.render()
    );
}

// ───────────────────────────────── the two REFUSALS, from a real folder of files

/// **The supply-chain case, from a folder rather than from a map.**
///
/// `brings: [tools]` on `customer-lookup` is the sentence *"this bundle may ship
/// tools and nothing else"*. The refusal that gives it force fires when version
/// 2.1 of somebody else's bundle quietly adds a `policies/` folder — approval
/// rules that gate this workspace's runs, arriving because a folder was copied.
///
/// This is the branch `brings:` exists for, and until this test it was witnessed
/// only by `bundles.rs::a_bundle_that_starts_shipping_approval_rules_is_refused`
/// and `::a_bundle_that_quietly_starts_supplying_an_agent_is_refused`, both of
/// which insert a `contributes` key into a map they built. Those tests can only
/// show that the check refuses the shape they wrote; they cannot show that a
/// folder an author drops on disk *becomes* that shape. Adding a directory is
/// how the supply-chain case actually happens, so it is how it is tested here.
///
/// Mutation: delete the `loader/bundle-brings-more-than-it-said` push, or drop
/// the `GOVERNING` arm that adds the sentence about changing what a run does.
#[test]
fn a_folder_a_bundle_never_said_it_would_bring_is_refused_from_a_real_tree() {
    let scratch = scratch("brings-more");
    copy_tree(&tree(), &scratch);
    let policies = scratch.join("bundles/customer-lookup/contributes/policies");
    std::fs::create_dir_all(&policies).expect("add a policies folder to the bundle");
    std::fs::write(
        policies.join("strict.yaml"),
        "applies-to: every-agent\nask-a-person:\n  - when:\n      \
         - { tool: find-customer/lookup }\n    because: version 2.1 started gating runs\n    \
         question: is-this-ok\n",
    )
    .expect("write the contributed policy");

    let mut d = Diagnostics::new();
    let doc = Loader::new(scratch.clone())
        .load(&scratch, &mut d)
        .expect("the copy loads");
    a_bundle_brings_only_what_it_said(&doc, &spec(), &mut d);

    let hit = d
        .items()
        .iter()
        .find(|x| x.rule == "loader/bundle-brings-more-than-it-said")
        .unwrap_or_else(|| {
            panic!(
                "a `policies/` folder inside a bundle whose `brings:` says `[tools]` must be \
                 refused when it is a real folder, not only when a test hands the check a \
                 map with a `policies` key in it:\n{}",
                d.render()
            )
        });
    assert!(hit.message.contains("customer-lookup"), "{}", hit.message);
    assert!(hit.message.contains("policies"), "{}", hit.message);
    assert!(
        hit.message.contains("change or stop what a run does"),
        "a bundle that starts shipping approval rules is a governance event, and the \
         sentence has to say so: {}",
        hit.message
    );
    assert!(
        hit.fix.contains("Add `policies` to `brings:`"),
        "{}",
        hit.fix
    );

    let _ = std::fs::remove_dir_all(&scratch);
}

/// A folder naming no kind of document PACT has is refused, not skipped.
///
/// The silent `continue` this replaced is why `agents:` — the one contribution
/// that adds something able to act — passed a check whose whole purpose is to
/// hold a bundle to what it declared. Witnessed until now only by
/// `bundles.rs::a_contributed_kind_the_schema_does_not_know_is_refused_and_not_skipped`,
/// against `mounted("acme/crm", &["tools"], &["tools", "gizmos"])`.
///
/// It matters that this one comes from a folder: a hand-built map can hold the
/// key `gizmos` because the test typed it, whereas on disk the key exists only
/// because the loader turned a directory name into one. If the loader ever
/// started filtering directory names against the schema on the way in, the
/// hand-built test would keep passing over a branch nothing could reach.
///
/// Mutation: turn the unknown-kind arm back into a bare `continue`.
#[test]
fn a_folder_naming_no_kind_of_document_pact_has_is_refused_from_a_real_tree() {
    let scratch = scratch("unknown-kind");
    copy_tree(&tree(), &scratch);
    let gizmos = scratch.join("bundles/customer-lookup/contributes/gizmos");
    std::fs::create_dir_all(&gizmos).expect("add a gizmos folder to the bundle");
    std::fs::write(gizmos.join("widget.yaml"), "description: a thing\n").expect("write it");

    let mut d = Diagnostics::new();
    let doc = Loader::new(scratch.clone())
        .load(&scratch, &mut d)
        .expect("the copy loads");
    a_bundle_brings_only_what_it_said(&doc, &spec(), &mut d);

    let hit = d
        .items()
        .iter()
        .find(|x| x.rule == "loader/bundle-brings-an-unknown-kind")
        .unwrap_or_else(|| {
            panic!(
                "an unknown kind must be refused rather than skipped:\n{}",
                d.render()
            )
        });
    assert!(hit.message.contains("gizmos"), "{}", hit.message);
    assert!(
        hit.fix.contains("agents"),
        "the fix lists every kind a workspace can hold, `agents` among them: {}",
        hit.fix
    );

    let _ = std::fs::remove_dir_all(&scratch);
}

// ───────────────────────────────── what remains unbuilt, stated as a test

/// **Mounting is unbuilt, and this is what that looks like from a real tree.**
///
/// The bundle's definitions are in the *document* — the test above proves the
/// loader builds them — and they are not in the *workspace*. Nothing projects
/// `bundles.<name>.contributes.tools` into `tools:`, so no agent's `uses:` can
/// name a contributed tool. Measured on this tree by adding
/// `uses: [find-customer]` to `agents/desk/agent.yaml`:
///
/// ```text
/// error: 'uses' names 'find-customer', and there is no such entry in `tools:`,
///        `skills:` or `knowledge:`.
///   fix: Nothing is declared there yet. Add a file `tools/find-customer.yaml`, …
/// ```
///
/// A fix that tells the author to write a second copy of a document the tree
/// already holds. That is the gap `docs/remediation/C7-bundle-mounting.md`
/// exists to decide, and this assertion is its acceptance test written
/// backwards: **the day mounting lands, this test fails**, and whoever builds it
/// should replace it with the same walk asserting the opposite. Until then it
/// stops the register's claim about C2 from drifting away from the code.
#[test]
fn nothing_a_bundle_contributes_reaches_the_collections_an_agent_can_name() {
    let (doc, _) = read();
    assert!(
        doc.get("bundles")
            .and_then(|b| b.get("customer-lookup"))
            .and_then(|b| b.get("contributes"))
            .and_then(|c| c.get("tools"))
            .and_then(|t| t.get("find-customer"))
            .is_some(),
        "the contributed tool is in the document"
    );
    assert!(
        doc.get("tools").is_none(),
        "and it is NOT in the workspace's own `tools:`. If this assertion has started \
         failing, mounting has been built — read \
         `docs/remediation/C7-bundle-mounting.md`, check the four decisions it takes \
         were the ones taken, and turn this test around."
    );
}

/// The contributed documents are **not re-validated** as the kinds they claim.
///
/// `contributes:` is `map of anything`, so the schema descends no further than
/// the word `tools`. `bundles.rs` reads the KEYS and never what is under them,
/// and no whole-tree pass in `crates/pact-cli/src/main.rs` walks into a bundle
/// looking for a tool. Measured, by replacing the shipped
/// `contributes/tools/find-customer.yaml` with three lines that would be refused
/// anywhere else in this tree:
///
/// ```text
/// connect: a-server-that-does-not-exist
/// reads: yes
/// gizmo: 3
/// ```
///
/// The same file under `tools/` gives **three errors** — `schema/unknown-field`
/// twice and `schema/no-such-name` once — plus a `loader/nothing-points-at-it`
/// warning, because under `tools/` it is a tool no agent names. Under
/// `contributes/tools/` it gives nothing at all, and `pact check` prints
/// `loaded with 1 warning(s)` and exits 0.
///
/// This test reproduces that in-process against a copy of the shipped tree, so
/// the sentence in the design document is a measurement rather than a claim, and
/// so that a future change which starts descending into `contributes:` is found
/// here rather than by whoever's shipped bundle suddenly stops loading.
#[test]
fn a_document_a_bundle_contributes_is_read_as_anything_and_held_to_nothing() {
    let root = tree();
    let scratch = scratch("contributes-unchecked");
    copy_tree(&root, &scratch);

    let broken = scratch.join("bundles/customer-lookup/contributes/tools/find-customer.yaml");
    std::fs::write(
        &broken,
        "description: Finds one customer.\nconnect: a-server-that-does-not-exist\n\
         reads: yes\ngizmo: 3\n",
    )
    .expect("write the broken contribution");

    let mut d = Diagnostics::new();
    let doc = Loader::new(scratch.clone())
        .load(&scratch, &mut d)
        .expect("the copy loads");
    let schema = spec();
    schema.validate(&doc, "workspace", &mut d);
    a_bundle_brings_only_what_it_said(&doc, &schema, &mut d);

    let complaints: Vec<&str> = d
        .items()
        .iter()
        .map(|x| x.rule)
        .filter(|r| *r != "loader/bundle-not-mounted")
        .collect();
    assert!(
        complaints.is_empty(),
        "nothing today reads INSIDE `contributes:`, so a contribution that would be \
         refused anywhere else in the tree is accepted. If this has started failing, \
         re-validation has been built and decision 2 of \
         `docs/remediation/C7-bundle-mounting.md` has been taken — say so there:\n{}",
        d.render()
    );

    let _ = std::fs::remove_dir_all(&scratch);
}

/// A private copy of the tree, named for this test AND this process.
///
/// The process id is not decoration. `scripts/sync-counts.sh` runs
/// `cargo test --workspace` and `scripts/test-all.sh` runs `cargo test`, so two
/// runs on one machine is ordinary; without the qualifier, one process's
/// `remove_dir_all` deletes another's tree mid-load and the failure surfaces as
/// this file's assertion message, which points the reader at a design document
/// that has nothing to do with it. Every other temp-using test in `crates/`
/// carries `std::process::id()` — `crates/pact-cli/tests/discovery.rs:223` and
/// a dozen more — and this one now does too.
fn scratch(name: &str) -> Utf8PathBuf {
    let dir = std::env::temp_dir().join(format!("pact-bundle-{name}-{}", std::process::id()));
    let dir = Utf8PathBuf::from_path_buf(dir).expect("a UTF-8 temp path");
    let _ = std::fs::remove_dir_all(&dir);
    dir
}

fn copy_tree(from: &Utf8Path, to: &Utf8Path) {
    std::fs::create_dir_all(to).expect("create the copy");
    for entry in std::fs::read_dir(from).expect("read the tree") {
        let entry = entry.expect("an entry");
        let name = entry.file_name();
        let name = name.to_str().expect("a UTF-8 name");
        let src = from.join(name);
        let dst = to.join(name);
        if entry.file_type().expect("a file type").is_dir() {
            copy_tree(&src, &dst);
        } else {
            std::fs::copy(&src, &dst).expect("copy a file");
        }
    }
}
