//! Every field the specification binds a model with is held to `allow-egress:`.
//!
//! `allow-egress:`'s own help promises *"which parts of this system are allowed
//! to talk to something outside this box. Empty means nothing is."* Six fields
//! in `spec/schema.yaml` carry `names: pact:models`, and the egress rule walked
//! four of them by hand. The fifth — `agent.model-for-checking` — was a hosted
//! model an air-gapped workspace could bind with nothing said.
//!
//! The sixth is `catalog.default`, and it is the same defect one layer out: the
//! first fix moved the table from Rust into `spec/schema.yaml`, where the table
//! was ALSO incomplete. `default:` is what every agent that pins no `model:`
//! actually runs, it carried no `names:` line, so `bindings` never walked it.
//! MEASURED on that fix, a workspace saying `allow-egress: []` with one agent
//! pinning nothing and `models/catalog.yaml` reading
//! `version: 1` / `default: claude-opus-5`:
//!
//! ```text
//! OK — /tmp/probe loaded cleanly (11 settings).
//! ```
//!
//! — while the same id moved one file over onto `model:` was refused. It broke
//! an invariant the fix's own comment asserted, that `default:` is "locally
//! servable by construction"; a workspace-supplied catalogue is not.
//!
//! MEASURED before the fix, on a workspace whose `workspace.yaml` reads
//! `allow-egress: []` and whose one agent writes `model-for-checking:
//! claude-opus-5` — a row `models/catalog.yaml` serves over somebody's API and
//! nowhere else:
//!
//! ```text
//! OK — /tmp/probe loaded cleanly (11 settings).
//! ```
//!
//! The same id on the line above it, under `model:`, was refused correctly:
//!
//! ```text
//! error: `model: claude-opus-5` is only served off this machine, and this
//!   workspace says `allow-egress: []` — nothing there lets the model doing the
//!   work talk to anything outside the box.
//!   rule: loader/leaves-the-box
//! ```
//!
//! So the boundary held or did not hold depending on which of two adjacent
//! lines the author wrote the same name on. That is the hand-written-table
//! failure this repository has already removed twice: a list of field names in
//! Rust that nothing holds against the specification comes to disagree with the
//! specification.
//!
//! ## What is parameterised, and why
//!
//! The cases here are **read off the shipped `spec/schema.yaml`** — every field
//! of every group declaring `names: pact:models` — rather than listed in this
//! file. A test that named the five fields would be the same table one layer
//! further out, and would go on passing on the day a sixth is added. Instead a
//! sixth field arrives here as a case with no tree to run it in, and
//! [`every_field_the_specification_binds_a_model_with_has_a_tree_here`] fails by
//! name until somebody writes one.
//!
//! Each field gets a CONTROL run as well: the same tree with a locally-served
//! id, which must load cleanly. Without it, a tree missing a required setting
//! would be refused for that instead and the refusal test would pass for the
//! wrong reason.
//!
//! Both runs go through the real `pact check` binary over real files on disk,
//! so what is under test is the author's own line reaching the check.
//!
//! ## The other direction: what must NOT be refused
//!
//! `names: pact:models` says which FIELDS bind a model. It does not say that
//! every key spelt like one is a binding, and the first fix for the hole above
//! read it that way — every key in the tree, at any depth. `metric.with` and
//! `case.with` are `type: map of anything`, whose own help is *"any settings
//! that score takes, written exactly as its own documentation names them.
//! Nothing is renamed"*, and one of those scores takes a setting called `model`.
//! MEASURED on that fix, on a suite carrying
//! `metrics: [{uri: deepeval:faithfulness, with: {model: claude-opus-5}}]`:
//!
//! ```text
//! error: `model: claude-opus-5` is only served off this machine, and this
//!   workspace says `allow-egress: []` …
//!   fix: write `model: qwen2.5-7b-instruct`, which runs here; …
//!   rule: loader/leaves-the-box
//! ```
//!
//! — against `OK — loaded cleanly (17 settings)` before it, and with a fix line
//! telling the author to rewrite a key whose name is not theirs to choose. So
//! half the cases here are trees that must go on loading, each with a CONTROL
//! putting the same hosted id in a real binding in the same tree, so a tree that
//! passes because the rule never ran cannot pass quietly.
//!
//! ## Mutations
//!
//! 1. **The hole this file was written for.** In
//!    `crates/pact-cli/src/egress.rs::bindings`, replace
//!    `if f.names.iter().any(|n| n == MODELS)` with
//!    `if ["model", "summarised-by", "graded-by"].contains(&f.name.as_str())` —
//!    exactly the set the four hardcoded paths reached (`agents.<a>.model`,
//!    `context-policies.<p>.summarised-by`, `evals.graded-by`,
//!    `learning.models.<m>.model`). Without it, the `agent.model-for-checking`
//!    case of
//!    [`a_model_served_only_off_this_machine_is_refused_wherever_the_specification_binds_one`]
//!    goes red and everything else stays green: that field was not walked at
//!    all, so a hosted model bound on it loaded cleanly under
//!    `allow-egress: []`.
//! 2. **The over-refusal.** Put the key-name walk back — collect every field
//!    with `names: pact:models` into a set of names and recurse over every key
//!    in the tree, matching on the key. Without it,
//!    [`a_model_named_inside_a_block_the_specification_leaves_open_is_left_alone`]
//!    and [`a_model_under_a_key_evals_does_not_have_is_not_a_second_problem`]
//!    both go red, and every refusal test in this file stays green — which is
//!    how that walk shipped.
//! 3. **The boundary a document cannot draw.** Delete the `allow-egress`
//!    guard at the top of `egress::refusals`. Without it,
//!    [`an_agent_with_no_workspace_around_it_is_not_told_what_its_workspace_says`]
//!    goes red: a lone `agent.yaml` is refused with *"this workspace says
//!    `allow-egress: []`"* and a fix in a `workspace.yaml` that does not exist.
//! 4. **The role, which nothing held.** Every tree in [`tree`] says
//!    `allow-egress: []`, under which every role refuses identically — so those
//!    cases cannot tell `llm` from `stt` from `judge`. Insert
//!    `if field == "model-for-checking" { return Some(vec!["stt"]); }` at the
//!    top of `egress::plays`. Measured before
//!    [`the_same_workspaces_load_cleanly_when_the_workspace_grants_the_role_they_play`]
//!    existed: 60 test binaries, all 60 green, and an author with
//!    `allow-egress: [llm]` told to *"add `stt`"* — the defect the egress module
//!    exists to remove, inverted.
//! 5. **The noun.** Delete both arms of `egress::noun`, leaving the
//!    `part(roles[0])` fallback. Measured before
//!    [`noun_in_the_refusal`] existed: 60 test binaries green, and
//!    `model-for-checking:` refused with *"the model doing the work"* — which
//!    the field's own help contradicts one line down. Now
//!    [`a_model_served_only_off_this_machine_is_refused_wherever_the_specification_binds_one`]
//!    fails by name.
//! 6. **The table one layer out.** Delete `names: pact:models` from
//!    `catalog.default` in `spec/schema.yaml`.
//!    [`every_field_the_specification_binds_a_model_with_has_a_tree_here`] goes
//!    red on the count — which is what the count is for, since without it the
//!    field simply stops being a case and every other test in this file goes on
//!    passing over five.
//! 7. **The list.** `egress::ids` reads a list of ids only where the
//!    specification declares a list. Make it read every list and
//!    [`a_model_binding_written_as_a_list_is_one_problem_and_not_one_per_item`]
//!    goes red with three messages about one line; make it ignore every list and
//!    [`a_model_binding_the_specification_declares_as_a_list_is_read_as_one`]
//!    goes red instead.
//! 8. **The role nobody has written yet.** Delete the `required: yes` check at
//!    the end of `egress::plays`. Without it,
//!    [`a_model_row_that_has_not_said_what_it_is_for_is_not_told_to_grant_everything`]
//!    goes red: a `learning.yaml` row with no `role:` draws a second message
//!    advising `llm`, the widest grant there is, on a line whose whole point is
//!    that nobody has said what it is for.
//! 9. **The other half of the boundary.** Make `egress::envelope` return the
//!    agent's own `model:` and nothing else. Without it,
//!    [`a_recording_is_held_against_every_model_the_conversation_passes_through`]
//!    goes red on five of its six cases: a hosted `model-for-checking:`, a named
//!    context policy's hosted `summarised-by:`, and a hosted catalogue
//!    `default:` each carried a recording out of the box under
//!    `allow-egress: [llm]`.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

/// The specification as it actually ships — the same file `pact-cli` embeds.
const SPEC: &str = include_str!("../../../spec/schema.yaml");

/// The namespace a field writes to say its value is a model id.
const MODELS: &str = "pact:models";

/// A row `models/catalog.yaml` serves over somebody's API and nowhere else.
const HOSTED: &str = "claude-opus-5";

/// A row `models/catalog.yaml` says runs on this machine.
const LOCAL: &str = "qwen2.5-7b-instruct";

/// Every `(group, field)` the shipped specification declares with
/// `names: pact:models`.
///
/// Read off the file rather than listed here. A schema edit that adds a sixth
/// model binding adds a case to this test by existing, which is the whole point:
/// the defect being held is a list of these written out in Rust.
fn model_binding_fields() -> Vec<(String, String)> {
    let node =
        pact_doc::parse_yaml(SPEC, camino::Utf8Path::new("spec/schema.yaml")).expect("parses");
    let groups = node
        .get("groups")
        .and_then(pact_doc::Node::as_map)
        .expect("the specification has groups");
    let mut out = Vec::new();
    for (group, entry) in groups {
        let Some(fields) = entry.node.get("fields").and_then(pact_doc::Node::as_map) else {
            continue;
        };
        for (field, f) in fields {
            let Some(names) = f.node.get("names") else {
                continue;
            };
            // `names:` is written as a bare word on every field that has one
            // today, but the schema loader accepts a list, so both are read
            // here rather than assuming the spelling in front of us.
            let written: Vec<&str> = match names.as_list() {
                Some(items) => items.iter().filter_map(pact_doc::Node::as_str).collect(),
                None => names.as_str().into_iter().collect(),
            };
            if written.iter().any(|n| n.trim() == MODELS) {
                out.push((group.clone(), field.clone()));
            }
        }
    }
    out
}

/// The smallest workspace in which `group.field` is the ONE model binding.
///
/// `None` means this test has no tree for that field — see
/// [`every_field_the_specification_binds_a_model_with_has_a_tree_here`].
///
/// Every tree says `allow-egress: []`, and every tree has an `agents/` folder:
/// a workspace with no agents in it loads, but warns that nothing in it can run
/// (`loader/nothing-can-run-this`), and these trees are about the boundary
/// rather than about that. It used to be worse — such a folder was read as a
/// lone AGENT and refused with `loader/not-a-pact-folder` before any of this was
/// reached; see `a_workspace_with_no_agents_in_it_yet_is_still_a_workspace`.
fn tree(group: &str, field: &str, id: &str) -> Option<Vec<(&'static str, String)>> {
    const WORKSPACE: &str = "name: probe\nallow-egress: []\n";
    const AGENT: &str = "name: Desk\ndescription: A desk.\ninstructions: Do it.\n";
    let files: Vec<(&'static str, String)> = match (group, field) {
        ("agent", "model") => vec![
            ("workspace.yaml", WORKSPACE.to_string()),
            ("agents/desk/agent.yaml", format!("{AGENT}model: {id}\n")),
        ],
        ("agent", "model-for-checking") => vec![
            ("workspace.yaml", WORKSPACE.to_string()),
            // `model-for-checking:` carries `needs-also: [loop]` — a stage is
            // where the difference applies — so without a `loop:` this tree
            // would be refused for the missing companion instead.
            (
                "agents/desk/agent.yaml",
                format!("{AGENT}model-for-checking: {id}\nloop: pact:loop/standard\n"),
            ),
        ],
        ("evals", "graded-by") => vec![
            ("workspace.yaml", WORKSPACE.to_string()),
            ("agents/desk/agent.yaml", AGENT.to_string()),
            // `population:` is required of every eval suite.
            (
                "evals/suite.yaml",
                format!(
                    "description: Checks.\npopulation: authored-enumeration\ngraded-by: {id}\n"
                ),
            ),
        ],
        ("learning-model", "model") => vec![
            ("workspace.yaml", WORKSPACE.to_string()),
            ("agents/desk/agent.yaml", AGENT.to_string()),
            // `enabled:` is required of `learning.yaml`, and `role:` is
            // required of every model row in it.
            (
                "learning.yaml",
                format!(
                    "enabled: propose-only\nmodels:\n  execution: {{ role: llm, model: {id} }}\n"
                ),
            ),
        ],
        ("context-policy", "summarised-by") => vec![
            ("workspace.yaml", WORKSPACE.to_string()),
            // A tidying policy nothing names loads with a warning about never
            // taking effect, so the agent names it and the control run is clean.
            (
                "agents/desk/agent.yaml",
                format!("{AGENT}context-policy: tidy\n"),
            ),
            (
                "context-policies/tidy.yaml",
                format!("description: Keeps it short.\nsummarised-by: {id}\n"),
            ),
        ],
        // The model every agent that pins nothing actually runs. The agent here
        // deliberately writes no `model:` line, so the only model this workspace
        // binds is the one in its own catalogue.
        ("catalog", "default") => vec![
            ("workspace.yaml", WORKSPACE.to_string()),
            ("agents/desk/agent.yaml", AGENT.to_string()),
            (
                "models/catalog.yaml",
                format!("version: 1\ndefault: {id}\n"),
            ),
        ],
        _ => return None,
    };
    Some(files)
}

/// The same files, with the workspace granting `llm` instead of granting nothing.
///
/// `llm` admits every binding in [`tree`] as the specification declares them
/// today — `agent.model`, `agent.model-for-checking`, `context-policy.summarised-by`
/// and `catalog.default` play `llm`; `evals.graded-by` plays `judge` or `llm`;
/// the `learning.yaml` row writes `role: llm`. So one uniform grant serves every
/// case, and a binding that stops being admitted by it has had its ROLE changed.
fn granting_llm(files: Vec<(&'static str, String)>) -> Vec<(&'static str, String)> {
    files
        .into_iter()
        .map(|(path, body)| {
            if path != "workspace.yaml" {
                return (path, body);
            }
            assert!(
                body.contains("allow-egress: []"),
                "every tree in this file says `allow-egress: []`, and this one says:\n{body}"
            );
            (
                path,
                body.replace("allow-egress: []", "allow-egress: [llm]"),
            )
        })
        .collect()
}

/// What the refusal must call the model each field binds.
///
/// `egress::noun` is a two-row hand-written table sitting eight lines below that
/// module's own account of losing the hand-written-table argument, and until
/// this function existed nothing in the repository held either row: a repo-wide
/// grep for both sentences returned exactly the two source lines that write
/// them. MEASURED with both arms deleted and only the `part(role)` fallback
/// left — `cargo test -p pact-cli` printed 60 test binaries green, and the
/// shipped binary said
///
/// ```text
/// error: `model-for-checking: claude-opus-5` is only served off this machine …
///   nothing there lets the model doing the work talk to anything outside the box.
/// ```
///
/// while `model-for-checking:`'s own help one line down says *"Everything else
/// uses `model:`"*. R56: a message that contradicts the author's own file is a
/// message they stop believing.
///
/// `None` for a field this file has no expectation for, which
/// [`every_field_the_specification_binds_a_model_with_has_a_tree_here`] refuses
/// — a sixth binding must arrive with a decision about what to call it, not with
/// a fallback nobody chose.
fn noun_in_the_refusal(group: &str, field: &str) -> Option<&'static str> {
    Some(match (group, field) {
        ("agent", "model") => "the model doing the work",
        ("agent", "model-for-checking") => "the model that checks the work",
        ("evals", "graded-by") => "the model that grades the checks",
        ("learning-model", "model") => "the model doing the work",
        ("context-policy", "summarised-by") => "the model that writes the summary",
        // Every agent that pins nothing runs it, so it IS the model doing the
        // work — the general noun is the right one here rather than a missing one.
        ("catalog", "default") => "the model doing the work",
        _ => return None,
    })
}

fn written(name: &str, files: &[(&'static str, String)]) -> String {
    let dst = std::env::temp_dir().join(format!("pact-boundary-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dst);
    for (path, body) in files {
        let p = dst.join(path);
        std::fs::create_dir_all(p.parent().expect("every file is under the root")).unwrap();
        std::fs::write(&p, body).unwrap();
    }
    dst.to_string_lossy().into_owned()
}

fn check(root: &str) -> (bool, String) {
    let out = pact().args(["check", root]).output().unwrap();
    let said =
        String::from_utf8_lossy(&out.stdout).to_string() + &String::from_utf8_lossy(&out.stderr);
    (out.status.success(), said)
}

/// A filename-safe name for a case, so two cases never share a temp folder.
fn slug(group: &str, field: &str) -> String {
    format!("{group}-{field}")
}

#[test]
fn every_field_the_specification_binds_a_model_with_has_a_tree_here() {
    let fields = model_binding_fields();
    assert!(
        fields.len() >= 6,
        "the specification declares {} fields with `names: {MODELS}`, and there were six \
         when this was written — a field losing its `names:` line silently shrinks every \
         other test in this file, which is exactly how `catalog.default` was outside the \
         boundary: {fields:?}",
        fields.len()
    );
    let missing: Vec<String> = fields
        .iter()
        .filter(|(g, f)| tree(g, f, LOCAL).is_none())
        .map(|(g, f)| format!("{g}.{f}"))
        .collect();
    assert!(
        missing.is_empty(),
        "the specification binds a model with {missing:?}, and this file has no workspace \
         to check them in. Add one to `tree()` — a `workspace.yaml` saying \
         `allow-egress: []`, an `agents/` folder, and the field itself — so the boundary \
         is measured on that field too."
    );
    let unnamed: Vec<String> = fields
        .iter()
        .filter(|(g, f)| noun_in_the_refusal(g, f).is_none())
        .map(|(g, f)| format!("{g}.{f}"))
        .collect();
    assert!(
        unnamed.is_empty(),
        "the specification binds a model with {unnamed:?}, and nothing here says what a \
         refusal should CALL it. Add it to `noun_in_the_refusal()` — and if the general \
         noun for its role is the right answer, say so there rather than letting \
         `egress::noun`'s fallback decide it by accident: {fields:?}"
    );
}

#[test]
fn a_model_served_only_off_this_machine_is_refused_wherever_the_specification_binds_one() {
    for (group, field) in model_binding_fields() {
        let Some(files) = tree(&group, &field, HOSTED) else {
            continue;
        };
        let root = written(&slug(&group, &field), &files);
        let (ok, out) = check(&root);
        assert!(
            !ok,
            "`{group}.{field}: {HOSTED}` is served off this machine and this workspace says \
             `allow-egress: []`, so nothing may reach it — and `pact check` said:\n{out}"
        );
        assert!(
            out.contains("loader/leaves-the-box"),
            "`{group}.{field}` was refused for something other than leaving the box:\n{out}"
        );
        assert!(
            out.contains(&format!("`{field}: {HOSTED}`")),
            "the refusal for `{group}.{field}` does not quote the line the author wrote, so \
             they cannot find it:\n{out}"
        );
        let expected = noun_in_the_refusal(&group, &field).expect("held by the test above");
        assert!(
            out.contains(&format!("lets {expected} talk to anything outside the box")),
            "the refusal for `{group}.{field}` does not call the model it binds \
             {expected:?}, so it either says nothing about which model, or says \
             something the author's own file contradicts one line down:\n{out}"
        );
    }
}

/// The same trees, with the workspace granting `llm` — every one must load.
///
/// This holds the ROLE the walk assigns, which nothing held: every tree in
/// [`tree`] says `allow-egress: []`, and under that grant every role refuses
/// identically, so the refusal test above cannot tell `llm` from `stt` from
/// `judge`. MUTATION: insert at the top of `egress::plays`
///
/// ```rust,ignore
/// if field == "model-for-checking" { return Some(vec!["stt"]); }
/// ```
///
/// Measured before this test existed: `cargo test -p pact-cli --no-fail-fast`
/// ran 60 test binaries and all 60 printed `test result: ok`, while the shipped
/// binary told an author with `allow-egress: [llm]` to
///
/// ```text
/// fix: … or add `stt` to `allow-egress:` in workspace.yaml
/// ```
///
/// — the module header's own consequence #1, inverted and shipping green. With
/// this test the `agent.model-for-checking` case goes red by name.
#[test]
fn the_same_workspaces_load_cleanly_when_the_workspace_grants_the_role_they_play() {
    for (group, field) in model_binding_fields() {
        let Some(files) = tree(&group, &field, HOSTED) else {
            continue;
        };
        let root = written(
            &format!("granted-{}", slug(&group, &field)),
            &granting_llm(files),
        );
        let (ok, out) = check(&root);
        assert!(
            ok && out.contains("loaded cleanly"),
            "`{group}.{field}: {HOSTED}` is a model call over words, and this workspace says \
             `allow-egress: [llm]` — which is the grant for words leaving the box. Either \
             the role this binding is read as has changed, or a grant that admits it no \
             longer does:\n{out}"
        );
    }
}

/// A workspace that says nothing may leave, with one agent and an `evals/`.
///
/// The suite is written by the caller, so one shape of tree serves both the
/// "must not be refused" cases and their controls.
fn a_suite(name: &str, suite: &str) -> String {
    written(
        name,
        &[
            (
                "workspace.yaml",
                "name: probe\nallow-egress: []\n".to_string(),
            ),
            (
                "agents/desk/agent.yaml",
                "name: Desk\ndescription: A desk.\ninstructions: Do it.\n".to_string(),
            ),
            ("evals/suite.yaml", suite.to_string()),
        ],
    )
}

/// A `model:` the specification never said was a model binding is not one.
///
/// `metric.with` and `case.with` are `type: map of anything`. The metric one is
/// the case with no escape: its help says the settings are written *"exactly as
/// its own documentation names them. Nothing is renamed"*, and the score's own
/// parameter is spelt `model`. An author who cannot rename the key and does not
/// want to grant `llm` egress has only the option of abandoning the metric.
#[test]
fn a_model_named_inside_a_block_the_specification_leaves_open_is_left_alone() {
    let open = [
        (
            "metric-with",
            format!(
                "description: Checks.\npopulation: authored-enumeration\nmetrics:\n  \
                 - uri: deepeval:faithfulness\n    threshold: 80%\n    with:\n      \
                 model: {HOSTED}\n"
            ),
        ),
        (
            "case-with",
            format!(
                "description: Checks.\npopulation: authored-enumeration\ncases:\n  one:\n    \
                 when: a refund is asked for\n    with:\n      model: {HOSTED}\n    \
                 expect: approved\n"
            ),
        ),
    ];
    for (name, suite) in open {
        let (ok, out) = check(&a_suite(name, &suite));
        assert!(
            ok && out.contains("loaded cleanly"),
            "`with:` is a block the specification leaves open — `{HOSTED}` under it is a \
             setting a score takes, not a model this workspace binds — and `pact check` \
             said:\n{out}"
        );

        // The control: the SAME tree, with the same id on a line that really is
        // a model binding. Without it a fixture the rule never looked at would
        // pass here for the wrong reason.
        let graded = suite.replace(
            "population: authored-enumeration\n",
            &format!("population: authored-enumeration\ngraded-by: {HOSTED}\n"),
        );
        let (ok, out) = check(&a_suite(&format!("control-{name}"), &graded));
        assert!(
            !ok && out.contains("loader/leaves-the-box")
                && out.contains(&format!("`graded-by: {HOSTED}`")),
            "the boundary was never consulted on this tree at all, so the run above proves \
             nothing:\n{out}"
        );
        assert!(
            !out.contains(&format!("`model: {HOSTED}`")),
            "the `with:` block was refused alongside the binding that really is one:\n{out}"
        );
    }
}

/// A block `evals` does not have is one problem, not two.
///
/// The author's one edit — deleting or renaming the key — removes both messages,
/// so a second error under it buries the first. A walk that reads the tree by
/// key name descends into blocks the schema has already rejected; a walk that
/// reads it through the schema cannot.
#[test]
fn a_model_under_a_key_evals_does_not_have_is_not_a_second_problem() {
    let root = a_suite(
        "unknown-block",
        &format!(
            "description: Checks.\npopulation: authored-enumeration\nscores:\n  faith:\n    \
             uri: deepeval:faithfulness\n    with:\n      model: {HOSTED}\n"
        ),
    );
    let (ok, out) = check(&root);
    assert!(!ok && out.contains("schema/unknown-field"), "{out}");
    assert!(
        !out.contains("loader/leaves-the-box"),
        "`scores:` is not something evals can have, and the author is being told to take \
         the whole block out — so a model inside it is a second message about one line:\n{out}"
    );
    assert!(out.contains("1 problem(s)"), "{out}");
}

/// A bundle's `contributes:` is a workspace, and is read as one.
///
/// It is `map of anything` because it holds the same kinds a workspace does —
/// *"what it defines, read exactly as if you had written it here"*. `brings:`'s
/// own comment says why it matters: a bundle that quietly adds an agent adds
/// something that can act, and that agent pins a model like any other.
#[test]
fn an_agent_a_bundle_contributes_is_held_to_the_boundary_like_any_other() {
    let bundle = |id: &str| {
        format!(
            "name: probe\nallow-egress: []\nbundles:\n  extra:\n    description: Extra bits.\n    \
             from: bundles/extra\n    brings: [agents]\n    contributes:\n      agents:\n        \
             helper:\n          name: Helper\n          description: Helps.\n          \
             instructions: Help.\n          model: {id}\n"
        )
    };
    let agent = "name: Desk\ndescription: A desk.\ninstructions: Do it.\n".to_string();
    let root = written(
        "bundle-contributes",
        &[
            ("workspace.yaml", bundle(HOSTED)),
            ("agents/desk/agent.yaml", agent.clone()),
        ],
    );
    let (ok, out) = check(&root);
    assert!(
        !ok && out.contains("loader/leaves-the-box"),
        "a bundle contributed an agent pinned to `{HOSTED}`, which is served off this \
         machine, into a workspace that says nothing may leave — and `pact check` \
         said:\n{out}"
    );

    let root = written(
        "control-bundle-contributes",
        &[
            ("workspace.yaml", bundle(LOCAL)),
            ("agents/desk/agent.yaml", agent),
        ],
    );
    let (ok, out) = check(&root);
    assert!(
        ok && out.contains("loaded cleanly"),
        "the same bundle with `{LOCAL}`:\n{out}"
    );
}

/// A lone `agent.yaml` is not told what a workspace it does not have says.
///
/// `allow-egress:` is a `workspace` setting. A folder holding one agent and no
/// workspace has nowhere to write one — `pact check` already warns that nothing
/// can find it — so refusing its `model:` says *"this workspace says
/// `allow-egress: []`"* about a file that does not exist, and offers a fix in
/// another one. R56: a message that quotes a line the author did not write is a
/// message they stop believing.
#[test]
fn an_agent_with_no_workspace_around_it_is_not_told_what_its_workspace_says() {
    let root = written(
        "lone-agent",
        &[(
            "agent.yaml",
            format!("name: Desk\ndescription: A desk.\ninstructions: Do it.\nmodel: {HOSTED}\n"),
        )],
    );
    let (_, out) = check(&root);
    assert!(
        !out.contains("loader/leaves-the-box"),
        "this folder has no workspace in it, so it says nothing about egress and cannot be \
         quoted as saying something:\n{out}"
    );
    assert!(
        out.contains("loader/nothing-can-run-this"),
        "the thing actually wrong with this folder is that nothing can find it, and that \
         is what should be said:\n{out}"
    );
}

/// The control. Same trees, a model that runs here — every one must load clean.
///
/// Without this, a tree missing a required setting would be refused for that
/// instead, and the test above would pass on a workspace where the boundary was
/// never consulted at all.
#[test]
fn the_same_workspaces_with_a_model_that_runs_here_load_cleanly() {
    for (group, field) in model_binding_fields() {
        let Some(files) = tree(&group, &field, LOCAL) else {
            continue;
        };
        let root = written(&format!("control-{}", slug(&group, &field)), &files);
        let (ok, out) = check(&root);
        assert!(
            ok && out.contains("loaded cleanly"),
            "the workspace for `{group}.{field}` binds `{LOCAL}`, which runs on this machine, \
             so nothing in it reaches outside the box — but `pact check` said:\n{out}"
        );
    }
}

/// A `default:` that names no model is a typo, and is reported as one.
///
/// The other half of the same hole: `catalog.default` carried no
/// `names: pact:models`, so it was resolved against nothing at all. MEASURED
/// before the schema line was added, on this exact tree:
///
/// ```text
/// OK — /tmp/probe loaded cleanly (11 settings).
/// ```
///
/// — a `pact check` printing "loaded cleanly" for a workspace whose every
/// unpinned agent binds a model that exists nowhere, and for which the second
/// port already has a named problem code
/// (`adapters/python/src/pact_adapters/resolve.py`, `catalog/unknown-default`).
#[test]
fn a_catalogue_default_naming_no_model_at_all_is_a_typo_and_is_reported_as_one() {
    let Some(files) = tree("catalog", "default", "claude-opus-99-nonexistent") else {
        panic!("`tree()` has no catalogue fixture")
    };
    let root = written("unknown-default", &files);
    let (ok, out) = check(&root);
    assert!(
        !ok && out.contains("schema/no-such-name"),
        "`default: claude-opus-99-nonexistent` names no row in any catalogue this workspace \
         can see, and every agent that pins nothing binds it — so it is the same typo \
         `model:` is refused for:\n{out}"
    );
    assert!(
        !out.contains("loader/leaves-the-box"),
        "a model that exists nowhere is not a model served off this machine, and saying so \
         is a confident false statement whose fix is about the wrong line:\n{out}"
    );
}

/// A model binding written as a list is ONE problem, not one per item.
///
/// `graded-by:` is `type: text`. A list under it is refused by
/// `schema/wrong-type`, and the egress rule reading each item as an id stacked
/// a second and third message onto the same line. MEASURED on the version whose
/// `ids()` read every list:
///
/// ```text
/// error: 'graded-by' should be some text, but it is a list.
///   rule: schema/wrong-type
/// error: `graded-by: claude-opus-5` is only served off this machine …
///   rule: loader/leaves-the-box
/// error: `graded-by: gpt-5.4` is only served off this machine …
///   rule: loader/leaves-the-box
/// 3 problem(s) found
/// ```
///
/// Three messages about one line, and two of them advising a grant for a
/// document that cannot load whichever way the author resolves them. It is the
/// same rule [`a_model_under_a_key_evals_does_not_have_is_not_a_second_problem`]
/// holds one layer over, and nothing in the repository held it here: the file
/// had no case whose value was a list.
#[test]
fn a_model_binding_written_as_a_list_is_one_problem_and_not_one_per_item() {
    let root = a_suite(
        "list-graded-by",
        &format!(
            "description: Checks.\npopulation: authored-enumeration\n\
             graded-by: [{HOSTED}, gpt-5.4]\n"
        ),
    );
    let (ok, out) = check(&root);
    assert!(!ok && out.contains("schema/wrong-type"), "{out}");
    assert!(
        !out.contains("loader/leaves-the-box"),
        "`graded-by:` should be some text, and the author is being told to write one — so a \
         boundary refusal per item is two more messages about one line, each advising a \
         grant for a document that cannot load either way:\n{out}"
    );
    assert!(out.contains("1 problem(s)"), "{out}");
}

/// The repository root, for the tests that need their own specification.
fn repo() -> std::path::PathBuf {
    std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

/// A model binding the specification declares AS a list is read as a list.
///
/// The other direction of the test above, and the reason `egress::ids` asks the
/// specification for the shape rather than simply ignoring every list: the day a
/// model binding is declared `list of text`, each item is a binding and the
/// boundary has to hold all of them. No field is declared that way today, so the
/// question is asked of a specification that declares one — through `$PACT_SPEC`
/// and `--unsafe-spec`, which is the only route there is.
///
/// MUTATION: replace `egress::ids`'s list arm with `Vec::new()` — the reading
/// that makes the test above pass on its own. This goes red: both hosted ids
/// load cleanly under `allow-egress: []`, with no `schema/wrong-type` to catch
/// them, because under this specification a list is exactly what the author was
/// asked for.
#[test]
fn a_model_binding_the_specification_declares_as_a_list_is_read_as_one() {
    // `graded-by:` is the only `names: pact:models` field that is `surface: S-GOV`,
    // so this anchor names one line of the shipped specification and no other.
    const ANCHOR: &str = "        type: text\n        names: pact:models\n        surface: S-GOV\n";
    let spec = std::fs::read_to_string(repo().join("spec/schema.yaml")).unwrap();
    assert_eq!(
        spec.matches(ANCHOR).count(),
        1,
        "the specification drifted: this test edits `evals.graded-by` by finding the one \
         `names: pact:models` field declared `surface: S-GOV`, and that is no longer unique"
    );
    let listed = spec.replace(ANCHOR, &ANCHOR.replace("type: text", "type: list of text"));

    let root = std::env::temp_dir().join(format!("pact-boundary-listed-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    std::fs::create_dir_all(root.join("spec")).unwrap();
    std::fs::write(root.join("spec/schema.yaml"), &listed).unwrap();
    for (path, body) in [
        (
            "tree/workspace.yaml",
            "name: probe\nallow-egress: []\n".to_string(),
        ),
        (
            "tree/agents/desk/agent.yaml",
            "name: Desk\ndescription: A desk.\ninstructions: Do it.\n".to_string(),
        ),
        (
            "tree/evals/suite.yaml",
            format!(
                "description: Checks.\npopulation: authored-enumeration\n\
                 graded-by: [{HOSTED}, gpt-5.4]\n"
            ),
        ),
    ] {
        let p = root.join(path);
        std::fs::create_dir_all(p.parent().unwrap()).unwrap();
        std::fs::write(&p, body).unwrap();
    }

    let out = pact()
        .args([
            "check",
            "--unsafe-spec",
            root.join("tree").to_str().unwrap(),
        ])
        .env("PACT_SPEC", root.join("spec/schema.yaml"))
        .output()
        .unwrap();
    let said =
        String::from_utf8_lossy(&out.stdout).to_string() + &String::from_utf8_lossy(&out.stderr);
    assert!(
        !said.contains("schema/wrong-type"),
        "under this specification `graded-by:` IS a list, so the shape is not the \
         problem:\n{said}"
    );
    for id in [HOSTED, "gpt-5.4"] {
        assert!(
            said.contains(&format!("`graded-by: {id}`")),
            "`{id}` is served off this machine and this workspace says `allow-egress: []`, \
             and it is one of the ids the author bound on a line the specification declares \
             as a list of them:\n{said}"
        );
    }
}

/// A model row that has not said what it is for yet is not advised to over-grant.
///
/// `learning-model.role` is `required: yes`. When the author has not written it,
/// `schema/missing-field` is already refusing that row with the only message
/// that can be right — and the egress rule used to guess `llm` for it anyway.
/// MEASURED before the fix, `models: { execution: { model: claude-opus-5 } }`
/// under `allow-egress: []`:
///
/// ```text
/// error: A model binding must have a 'role'.
///   rule: schema/missing-field
/// error: `model: claude-opus-5` is only served off this machine …
///   fix: … or add `llm` to `allow-egress:` …
///   rule: loader/leaves-the-box
/// 2 problem(s) found
/// ```
///
/// An author who meant `role: judge` was advised, in writing, to make the widest
/// grant there is — the module header's own consequence #1. The invalid-word
/// case one line over already answered correctly, which is what made the two
/// readings worth measuring against each other: `role: tools` gave exactly one
/// problem, and an absent `role:` gave two.
#[test]
fn a_model_row_that_has_not_said_what_it_is_for_is_not_told_to_grant_everything() {
    let files = |row: &str| {
        vec![
            (
                "workspace.yaml",
                "name: probe\nallow-egress: []\n".to_string(),
            ),
            (
                "agents/desk/agent.yaml",
                "name: Desk\ndescription: A desk.\ninstructions: Do it.\n".to_string(),
            ),
            (
                "learning.yaml",
                format!("enabled: propose-only\nmodels:\n  execution: {row}\n"),
            ),
        ]
    };

    let root = written("role-absent", &files(&format!("{{ model: {HOSTED} }}")));
    let (ok, out) = check(&root);
    assert!(!ok && out.contains("schema/missing-field"), "{out}");
    assert!(
        !out.contains("loader/leaves-the-box"),
        "nobody has said what this model is for, so no grant can be the right advice — and \
         `llm` is the widest one there is:\n{out}"
    );
    assert!(out.contains("1 problem(s)"), "{out}");

    // The word the specification does not offer, which already answered this way
    // and is the reading the case above was made to match.
    let root = written(
        "role-unknown",
        &files(&format!("{{ role: tools, model: {HOSTED} }}")),
    );
    let (ok, out) = check(&root);
    assert!(!ok && out.contains("schema/wrong-type"), "{out}");
    assert!(out.contains("1 problem(s)"), "{out}");

    // The control: the same row, with a role written. The boundary really is
    // consulted on this tree.
    let root = written(
        "role-written",
        &files(&format!("{{ role: judge, model: {HOSTED} }}")),
    );
    let (ok, out) = check(&root);
    assert!(
        !ok && out.contains("loader/leaves-the-box") && out.contains("`judge`"),
        "with the role written, this row binds a hosted judge in a workspace that says \
         nothing may leave — and the fix should offer `judge`, not `llm`:\n{out}"
    );
}

/// A workspace granting `llm`, one agent, and whatever else the caller writes.
fn voice(name: &str, agent: &str, extra: &[(&'static str, String)]) -> String {
    let mut files = vec![
        (
            "workspace.yaml",
            "name: probe\nallow-egress: [llm]\n".to_string(),
        ),
        (
            "agents/desk/agent.yaml",
            format!("name: Desk\ndescription: A desk.\ninstructions: Do it.\n{agent}"),
        ),
    ];
    files.extend(extra.iter().cloned());
    written(name, &files)
}

/// A recording is held against every model the conversation passes through.
///
/// `stt` and `tts` are deliberately not covered by `llm` — the one asymmetry the
/// egress module states — because *"the author who wrote `allow-egress: [llm]`
/// approved a model call, not a recording of somebody speaking being posted to
/// it"*. That half of the boundary was keyed to `agent.model` alone while the
/// words half had been widened to every field the specification binds a model
/// with, so the same recording crossed the boundary unremarked one line down.
///
/// MEASURED before the fix, each tree with `allow-egress: [llm]` and a
/// locally-served `model:`:
///
/// ```text
/// model-for-checking hosted + accepts: clip: audio            → OK — loaded cleanly (14 settings)
/// model-for-checking hosted + answers-with: a voice message   → OK — loaded cleanly (14 settings)
/// model-for-checking hosted + needs: audio: yes               → OK — loaded cleanly (15 settings)
/// summarised-by hosted (named policy) + accepts: clip: audio  → OK — loaded cleanly (17 settings)
/// ```
///
/// against the control on the line above, `model:` hosted with the same
/// `accepts:`, which was refused and named `stt`. The walk already saw all four
/// lines — the same trees under `allow-egress: []` drew a words refusal quoting
/// `summarised-by:` by name — so the silence was a scoping choice.
///
/// MUTATION: put `envelope` back to the agent's own `model:` — return only
/// `agent.get("model")`. All four cases here go red and the control stays green.
#[test]
fn a_recording_is_held_against_every_model_the_conversation_passes_through() {
    for case in audio_cases() {
        let agent = format!("{}{}", case.binds, case.audio);
        let (ok, out) = check(&voice(case.name, &agent, &case.extra));
        let (field, grant) = (case.field, case.grant);
        assert!(
            !ok && out.contains("loader/leaves-the-box"),
            "this agent handles audio and `{field}: {HOSTED}` is served off this machine, so \
             a recording leaves the box — and this workspace granted `llm`, which is words \
             and not speech:\n{out}"
        );
        assert!(
            out.contains(&format!("`{field}: {HOSTED}`")),
            "the refusal does not quote the line carrying the recording:\n{out}"
        );
        assert!(
            out.contains(&format!("`{grant}`")),
            "the fix does not name `{grant}`, which is the grant this workspace is missing:\n{out}"
        );
    }
}

/// The control for the test above: the same trees, with the audio line taken out.
///
/// Every one of those refusals must be about the recording and not about the
/// words. Without this, a tree refused for its `model-for-checking:` under a
/// grant that never admitted it would pass there for the wrong reason. It is the
/// same `binds:` text in both, so a case cannot drift between them.
#[test]
fn the_same_agents_without_audio_load_cleanly_under_a_grant_for_words() {
    for case in audio_cases() {
        let (ok, out) = check(&voice(
            &format!("quiet-{}", case.name),
            &case.binds,
            &case.extra,
        ));
        assert!(
            ok && out.contains("loaded cleanly"),
            "`{HOSTED}` is a model call over words here and this workspace says \
             `allow-egress: [llm]`, which is the grant for words leaving the box:\n{out}"
        );
    }
}

/// One agent whose conversation carries a recording, and where it reaches.
struct Audio {
    /// A filename-safe name, so two cases never share a temp folder.
    name: &'static str,
    /// The model bindings the agent writes. On its own it is the control.
    binds: String,
    /// The line that puts a recording or a spoken reply in the envelope.
    audio: &'static str,
    /// Any other file the workspace needs.
    extra: Vec<(&'static str, String)>,
    /// The field the refusal must quote, so the author can find the line.
    field: &'static str,
    /// The grant the fix must name — the narrowest one that would work.
    grant: &'static str,
}

fn audio_cases() -> Vec<Audio> {
    let checking =
        format!("model: {LOCAL}\nmodel-for-checking: {HOSTED}\nloop: pact:loop/standard\n");
    vec![
        // The control case: the one field the audio half always held.
        Audio {
            name: "audio-model",
            binds: format!("model: {HOSTED}\n"),
            audio: "accepts:\n  clip: audio\n",
            extra: vec![],
            field: "model",
            grant: "stt",
        },
        Audio {
            name: "audio-checking-accepts",
            binds: checking.clone(),
            audio: "accepts:\n  clip: audio\n",
            extra: vec![],
            field: "model-for-checking",
            grant: "stt",
        },
        Audio {
            name: "audio-checking-answers",
            binds: checking.clone(),
            audio: "answers-with:\n  reply: a voice message\n",
            extra: vec![],
            field: "model-for-checking",
            grant: "tts",
        },
        Audio {
            name: "audio-checking-needs",
            binds: checking,
            audio: "needs:\n  audio: yes\n  because: It listens.\n",
            extra: vec![],
            field: "model-for-checking",
            grant: "stt",
        },
        Audio {
            name: "audio-summariser",
            binds: format!("model: {LOCAL}\ncontext-policy: tidy\n"),
            audio: "accepts:\n  clip: audio\n",
            extra: vec![(
                "context-policies/tidy.yaml",
                format!("description: Keeps it short.\nsummarised-by: {HOSTED}\n"),
            )],
            field: "summarised-by",
            grant: "stt",
        },
        // The agent pins no model at all, so it runs the catalogue's `default:`
        // — which a workspace-supplied `models/catalog.yaml` can point anywhere.
        Audio {
            name: "audio-default",
            binds: String::new(),
            audio: "accepts:\n  clip: audio\n",
            extra: vec![(
                "models/catalog.yaml",
                format!("version: 1\ndefault: {HOSTED}\n"),
            )],
            field: "default",
            grant: "stt",
        },
    ]
}

/// An eval judge is not in an agent's audio envelope, and that is a position.
///
/// It is the one place the envelope stops short of a `names: pact:models` field
/// that a recording could conceivably reach, so it is written down here rather
/// than left as a silence somebody has to discover. A judge reads eval CASES,
/// and whether a case holds a recording depends on `population:` — which the
/// author writes per suite, and whose first choice, `authored-enumeration`,
/// means *"you wrote down the situations you thought of"*. Refusing every such
/// suite for a recording it cannot contain is the over-refusal
/// [`a_model_named_inside_a_block_the_specification_leaves_open_is_left_alone`]
/// measured and rejected on the words half of the same boundary.
///
/// If that position changes, this test is the line to change with it — and the
/// control below is why the change would be visible: the judge IS held to the
/// words half of the boundary, on the same tree.
#[test]
fn an_eval_judge_is_not_in_an_agents_audio_envelope() {
    let suite =
        format!("description: Checks.\npopulation: authored-enumeration\ngraded-by: {HOSTED}\n");
    let agent = format!("model: {LOCAL}\nevals: evals\naccepts:\n  clip: audio\n");
    let (ok, out) = check(&voice(
        "judge-audio",
        &agent,
        &[("evals/suite.yaml", suite.clone())],
    ));
    assert!(
        ok && out.contains("loaded cleanly"),
        "a judge sees eval cases, not this agent's conversation, and this suite says its \
         cases are ones the author wrote down. If that is no longer the position, change \
         this test and `egress::envelope`'s account of it together:\n{out}"
    );

    // The control: the same judge under a workspace that grants nothing. The
    // words half holds it, so the run above is silence about the recording and
    // not silence about the field.
    let quiet = written(
        "judge-audio-control",
        &[
            (
                "workspace.yaml",
                "name: probe\nallow-egress: []\n".to_string(),
            ),
            (
                "agents/desk/agent.yaml",
                format!("name: Desk\ndescription: A desk.\ninstructions: Do it.\n{agent}"),
            ),
            ("evals/suite.yaml", suite),
        ],
    );
    let (ok, out) = check(&quiet);
    assert!(
        !ok && out.contains(&format!("`graded-by: {HOSTED}`")),
        "the boundary was never consulted on this field at all, so the run above proves \
         nothing:\n{out}"
    );
}
