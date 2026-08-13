//! Every word an author may write as a `role:` is a word the egress rule knows.
//!
//! `crates/pact-cli/src/egress.rs` kept its own copy of the role words:
//!
//! ```text
//! pub(crate) const ROLES: &[&str] = &["llm", "stt", "tts", "embedder", "judge", "reflector"];
//! ```
//!
//! under a module header calling them *"the six"*, and `spec/schema.yaml`
//! declared seven choices for both `workspace.allow-egress` and
//! `learning-model.role`:
//!
//! ```text
//! choices: [llm, stt, tts, embedder, judge, reflector, tools]
//! ```
//!
//! Two lists that nothing held against each other, already a word apart. That
//! word is `tools`, and it reached an author on both lines.
//!
//! MEASURED before the fix, on a workspace whose `workspace.yaml` reads
//! `allow-egress: [tools]` and whose `learning.yaml` reads
//! `models: {execution: {role: tools, model: claude-opus-5}}` — both words
//! straight out of the specification's own `choices:`:
//!
//! ```text
//! error: `model: claude-opus-5` is only served off this machine, and this
//!   workspace says `allow-egress: [tools]` — nothing there lets the model doing
//!   the work talk to anything outside the box.
//!   fix: write `model: qwen2.5-7b-instruct`, which runs here; or add `llm` to
//!   `allow-egress:` in workspace.yaml — which is a change a person has to
//!   approve.
//!   rule: loader/leaves-the-box
//! ```
//!
//! Three wrongs in one message. The workspace is told the word it granted grants
//! nothing. The role it was invited to write was read as if it said `llm`,
//! silently, because the lookup fell through to a default. And the only typeable
//! fix offered is `llm`, which grants every other model role at the same time —
//! the over-grant this whole module exists to remove.
//!
//! ## The word that was in the wrong list
//!
//! `tools` is not a model role and the specification says so twice, in the
//! comment sitting directly above each of those two `choices:` lines: *"`tools`
//! is the seventh PART, not a seventh model role"*. It is the tool documents'
//! own outbound addresses, and `allow-egress: [tools]` is already read as
//! exactly that by `nothing_reaches_outside_the_box` in `main.rs`. It was on
//! `learning-model.role` because that whole comment block is a copy of the
//! `allow-egress:` one, and the copy brought the seventh word with it.
//!
//! So the repair is not to teach the checker a seventh model role — that would
//! make one person-approved word open two unrelated boundaries at once, which is
//! the "one boolean wearing several names" defect in a new direction. It is to
//! take `tools` off the line where no model can play it, and to read the words
//! that remain off the specification instead of copying them into Rust.
//! [`the_word_for_tool_documents_is_not_a_model_role_and_does_not_let_a_model_out`]
//! holds both halves of that.
//!
//! ## What is parameterised, and why
//!
//! The cases are the **shipped `spec/schema.yaml`'s own `choices:`**, read off
//! the file. Listing the words here would be the same hand-kept table one layer
//! further out, and it would go on passing on the day a seventh model role is
//! declared. Read this way, a new choice arrives here as a case by existing —
//! and it arrives in the checker the same way, which is the property under test.
//!
//! Each word runs three times, and the runs are what make each other mean
//! something:
//!
//! * granted by its own name, the binding must LOAD — this is what the six-word
//!   table got wrong;
//! * granted nothing, the same binding must be REFUSED, and the refusal must
//!   name that word as the grant that would work rather than the superset;
//! * bound to a model that runs here, it must load whatever was granted, so a
//!   tree refused for some unrelated missing setting cannot masquerade as a
//!   boundary refusal above.
//!
//! ## The second table in that file
//!
//! `egress.rs` holds one list the specification does not state: `WORDS`, the
//! roles a bare `allow-egress: [llm]` carries with it. That is a real decision —
//! `stt` and `tts` are deliberately outside it, because a grant for words is not
//! a grant for a recording of somebody's voice — but a decision written in Rust
//! and measured nowhere is how the first table got six words.
//! [`every_word_the_general_grant_carries_is_a_model_call_over_words`] measures
//! it, one tree per word.
//!
//! ## The fallback sentence is caught here, not shipped
//!
//! `egress.rs::part()` turns a role into the plain words a refusal uses — *"the
//! model that grades the checks"* — and ends in `_ => "this"`, which was a
//! comment claiming to be unreachable rather than a fact. A word declared in
//! `choices:` with no sentence written for it would really print *"nothing there
//! lets this talk to anything outside the box"*. The refusal run asserts that
//! sentence never appears, so a word added to the specification arrives as a red
//! test here instead of as a sentence about nothing in front of an author.
//!
//! ## Mutation
//!
//! Putting the shipped table back **on its own changes nothing today**, and
//! saying so is the honest way round: with `tools` off `learning-model.role`,
//! `const ROLES: &[&str] = &["llm", "stt", "tts", "embedder", "judge",
//! "reflector"]` and the specification's `choices:` agree word for word. A copy
//! is not wrong on the day it is made. It is wrong on the day the thing it
//! copies moves, and every mutation below was run and its output read.
//!
//! 1. **The copy stops tracking.** Declare a seventh model role — add `vision`
//!    to `learning-model.role`'s `choices:` and to `workspace.allow-egress`'s,
//!    and give `part()` a `"vision" =>` arm. With the derivation in place this
//!    whole file stays green: 7 passed, the new word joining every loop by
//!    existing, which is the property. Now replace the `role_words(group)` call
//!    in `plays` with the six-word `const ROLES` above. Red, 3 of 7:
//!    [`every_word_a_role_may_say_admits_the_binding_that_plays_it`] —
//!    `allow-egress: [vision]` refuses a binding that says `role: vision`;
//!    [`every_word_a_role_may_say_is_the_grant_its_own_refusal_asks_for`] — the
//!    refusal offers `llm` instead of the word the author wrote;
//!    [`every_word_the_general_grant_carries_is_a_model_call_over_words`] —
//!    `allow-egress: [llm]` silently admits it, because the unknown word fell
//!    through to the `llm` default. `cargo test --workspace --no-fail-fast`:
//!    those three and **nothing else**. That is exactly how six shipped against
//!    a specification saying seven.
//! 2. **The sentence nobody wrote.** Same `vision` in the specification,
//!    derivation restored, `part()`'s new arm removed. Red:
//!    [`every_word_a_role_may_say_is_the_grant_its_own_refusal_asks_for`], on
//!    the *"lets this talk"* assertion, quoting the shipped sentence *"nothing
//!    there lets this talk to anything outside the box"*. So the `_ => "this"`
//!    fallback is held by a test rather than by a comment claiming it cannot
//!    happen.
//! 3. **The word back in the wrong list.** Restore `tools` to
//!    `learning-model.role`'s `choices:`. Red, 2 of 7:
//!    [`the_word_for_tool_documents_is_not_a_model_role_and_does_not_let_a_model_out`]
//!    on the first assertion, and
//!    [`every_word_a_role_may_say_is_the_grant_its_own_refusal_asks_for`] on the
//!    fallback sentence — because there is no plain-words sentence for `tools`
//!    and there is not meant to be.
//! 4. **A word out of `WORDS`.** Drop `"embedder"`. Red:
//!    [`every_word_the_general_grant_carries_is_a_model_call_over_words`] here,
//!    and `one_grant_names_one_role` too.
//! 5. **The boundary rule guesses again.** In `plays`, replace
//!    `None if !words.is_empty() => return None` with `None if false => return
//!    None`, so an unoffered `role:` falls back to `llm` the way it used to.
//!    Red: [`the_word_for_tool_documents_is_not_a_model_role_and_does_not_let_a_model_out`]
//!    on the one-message assertion — `role: tools` draws two errors again, the
//!    second offering a grant for a role the first is telling the author to stop
//!    writing.
//! 6. **A word into `WORDS`.** Add `"stt"` — a grant for words carrying speech.
//!    Red: this file, plus
//!    `a_voice_recording_is_not_covered_by_permission_for_the_words` and
//!    `the_speech_roles_gate_speech_wherever_the_author_wrote_it`. The second
//!    table in `egress.rs` is the one the specification does not state, and
//!    these two runs are what hold it in both directions.

use std::process::Command;

fn pact() -> Command {
    Command::new(env!("CARGO_BIN_EXE_pact"))
}

/// The specification as it actually ships — the same file `pact-cli` embeds.
const SPEC: &str = include_str!("../../../spec/schema.yaml");

/// A row `models/catalog.yaml` serves over somebody's API and nowhere else.
const HOSTED: &str = "claude-opus-5";

/// A row `models/catalog.yaml` says runs on this machine.
const LOCAL: &str = "qwen2.5-7b-instruct";

/// The words `allow-egress:` carries for free when it says `llm`.
///
/// The one list here that is not read off the specification, because the
/// specification does not state it — see the module header. `stt` and `tts` are
/// outside it on purpose: a customer's voice is not their words.
const CARRIED_BY_LLM: &[&str] = &["llm", "embedder", "judge", "reflector"];

/// The `choices:` the shipped specification declares for `group.field`.
///
/// Read off the file rather than listed here. That is the whole subject of this
/// test: a copy of this list kept anywhere else is a copy that drifts.
fn choices(group: &str, field: &str) -> Vec<String> {
    let node = parsed();
    let declared = node
        .get("groups")
        .and_then(pact_doc::Node::as_map)
        .and_then(|groups| groups.get(group))
        .and_then(|g| g.node.get("fields"))
        .and_then(pact_doc::Node::as_map)
        .and_then(|fields| fields.get(field))
        .map(|f| f.node.clone())
        .unwrap_or_else(|| panic!("the specification declares `{group}.{field}`"));
    let listed = declared
        .get("choices")
        .and_then(|c| c.as_list().map(<[pact_doc::Node]>::to_vec))
        .unwrap_or_else(|| panic!("`{group}.{field}` is a closed list and says what is in it"));
    listed
        .iter()
        .filter_map(pact_doc::Node::as_str)
        .map(str::to_owned)
        .collect()
}

fn parsed() -> pact_doc::Node {
    pact_doc::parse_yaml(SPEC, camino::Utf8Path::new("spec/schema.yaml")).expect("parses")
}

/// Every word an author may write as a `role:`, off the specification.
fn role_words() -> Vec<String> {
    choices("learning-model", "role")
}

/// A workspace granting `granted`, whose one model binding plays `role`.
///
/// `learning.yaml` is used because `learning-model.role` is the one place in the
/// whole specification an author writes a role by hand — the other end of the
/// promise `allow-egress:` makes. `enabled:` is required of the file and
/// `agents/` has to hold something, or the tree is refused for that instead and
/// the boundary is never reached.
fn tree(granted: &str, role: &str, id: &str) -> Vec<(&'static str, String)> {
    vec![
        (
            "workspace.yaml",
            format!("name: probe\nallow-egress: [{granted}]\n"),
        ),
        (
            "agents/desk/agent.yaml",
            "name: Desk\ndescription: A desk.\ninstructions: Do it.\n".to_string(),
        ),
        (
            "learning.yaml",
            format!(
                "enabled: propose-only\nmodels:\n  execution: {{ role: {role}, model: {id} }}\n"
            ),
        ),
    ]
}

fn written(name: &str, files: &[(&'static str, String)]) -> String {
    let dst = std::env::temp_dir().join(format!("pact-parts-{name}-{}", std::process::id()));
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

/// The specification offers more than nobody, and says so in one place.
///
/// A guard on every loop below: if `choices:` ever came back empty they would
/// all iterate nothing and pass while measuring nothing at all.
#[test]
fn the_specification_says_which_parts_may_talk_outside_the_box() {
    let parts = choices("workspace", "allow-egress");
    assert!(
        parts.len() >= 7,
        "`allow-egress:` declared seven choices when this was written, and declares {} now \
         — a shrunken list silently shrinks this file: {parts:?}",
        parts.len()
    );
    let roles = role_words();
    assert!(
        roles.len() >= 6,
        "`learning-model.role` declared six choices when this was written, and declares {} \
         now — every case below is one of them, so a shrunken list silently shrinks the \
         test: {roles:?}",
        roles.len()
    );
}

/// Every word a `role:` may say is a word `allow-egress:` can grant.
///
/// `learning-model.role`'s help is *"one of the model roles `allow-egress:`
/// names, so the two lines can be read against each other"*, and the egress rule
/// reads them against each other literally: a binding's `role:` is looked up,
/// and the same word is what `allow-egress:` has to name for that binding to
/// reach a hosted service. A role word that `allow-egress:` does not offer is
/// therefore a role nothing can ever grant — a model bound to it could never
/// run, and the refusal would ask the author to type a word their own
/// `workspace.yaml` refuses.
///
/// A SUBSET and not an equality, which is the whole shape of the thing. The two
/// lines answer different questions: one says what a model is for, the other
/// says which parts of the system a person has approved. Not every part is a
/// model — `tools` is the standing example. Asserting them equal would freeze
/// both lists together, so that a new PART could not be declared without also
/// declaring a model role nobody can play.
#[test]
fn every_word_a_role_may_say_is_a_word_the_boundary_can_grant() {
    let parts = choices("workspace", "allow-egress");
    for role in role_words() {
        assert!(
            parts.contains(&role),
            "`role: {role}` is a word the specification invites an author to write, and \
             `allow-egress:` offers {parts:?} — so a model bound on that line could never \
             be granted, whatever anybody typed."
        );
    }
}

/// A word this workspace granted admits the binding that plays it.
///
/// One run per word the specification offers, so a word added to `choices:`
/// arrives here as a case rather than as an edit somebody has to remember.
#[test]
fn every_word_a_role_may_say_admits_the_binding_that_plays_it() {
    for role in role_words() {
        let root = written(&format!("granted-{role}"), &tree(&role, &role, HOSTED));
        let (ok, out) = check(&root);
        assert!(
            ok && out.contains("loaded cleanly"),
            "this workspace says `allow-egress: [{role}]` and its one model says \
             `role: {role}`, which are the two lines the specification's own help says can \
             be read against each other — and `pact check` said:\n{out}"
        );
    }
}

/// Granted nothing, the same binding is refused — and told the word it needs.
///
/// The control for the run above: without it a tree that loaded because the
/// boundary was never consulted would pass there for the wrong reason. It also
/// carries the two things a refusal has to get right — the word it asks for is
/// the narrowest one that works and not the superset, and the model it names is
/// named in words rather than in the `_ => "this"` fallback.
#[test]
fn every_word_a_role_may_say_is_the_grant_its_own_refusal_asks_for() {
    for role in role_words() {
        let root = written(&format!("refused-{role}"), &tree("", &role, HOSTED));
        let (ok, out) = check(&root);
        assert!(!ok, "this workspace says `allow-egress: []`:\n{out}");
        assert!(
            out.contains("loader/leaves-the-box"),
            "`role: {role}` binds `{HOSTED}`, which is served off this machine, in a \
             workspace that says nothing may leave — and it was refused for something \
             else:\n{out}"
        );
        assert!(
            out.contains(&format!("`{role}`")),
            "the refusal for `role: {role}` never names `{role}` as a grant that would \
             work, so the only thing the author can type is a wider one:\n{out}"
        );
        assert!(
            !out.contains("lets this talk"),
            "`{role}` is a word the specification offers and no plain-words sentence was \
             written for it, so the refusal says \"nothing there lets this talk to \
             anything outside the box\" — which is a sentence about nothing:\n{out}"
        );
    }
}

/// The control: the same workspaces, a model that runs here — all load clean.
///
/// Without this, a tree refused for a missing required setting would look like a
/// boundary refusal above and the whole file would pass on trees the rule never
/// reached.
#[test]
fn the_same_workspaces_with_a_model_that_runs_here_load_cleanly() {
    for role in role_words() {
        let root = written(&format!("control-{role}"), &tree("", &role, LOCAL));
        let (ok, out) = check(&root);
        assert!(
            ok && out.contains("loaded cleanly"),
            "`role: {role}` binds `{LOCAL}`, which runs on this machine, so nothing in this \
             workspace reaches outside the box whatever it granted — and `pact check` \
             said:\n{out}"
        );
    }
}

/// What a bare `allow-egress: [llm]` carries with it, measured word by word.
///
/// `llm` is the general grant for *words* leaving the box, so it also admits the
/// roles that are particular kinds of model call. It does not admit `stt` or
/// `tts`: a recording of a customer speaking is not their words, and if a grant
/// for words carried speech there would be no reason for those two choices to
/// exist at all.
///
/// That is a decision `spec/schema.yaml` does not state, so `egress.rs` states
/// it, in a `const WORDS` — the second hand-kept list in the same file, and the
/// first one drifted. Held here rather than trusted: every word the
/// specification offers is run under `allow-egress: [llm]` and the answer is
/// asserted in both directions.
#[test]
fn every_word_the_general_grant_carries_is_a_model_call_over_words() {
    for role in role_words() {
        let carried = CARRIED_BY_LLM.contains(&role.as_str());
        let root = written(&format!("llm-carries-{role}"), &tree("llm", &role, HOSTED));
        let (ok, out) = check(&root);
        if carried {
            assert!(
                ok && out.contains("loaded cleanly"),
                "`role: {role}` is a model call over words, and this workspace granted \
                 `llm` — the general grant for words leaving the box. A workspace that has \
                 already approved model calls must not be asked to approve them again, and \
                 `pact check` said:\n{out}"
            );
        } else {
            assert!(
                !ok && out.contains("loader/leaves-the-box"),
                "`role: {role}` sends a recording or a spoken reply, not words, and the \
                 author who wrote `allow-egress: [llm]` approved a model call — not a \
                 recording of somebody speaking being posted to one. If `llm` carried \
                 speech there would be no reason for `{role}` to be a choice at all, and \
                 `pact check` said:\n{out}"
            );
            assert!(
                out.contains(&format!("`{role}`")),
                "and the refusal has to name `{role}`, which is the one grant that \
                 works:\n{out}"
            );
        }
    }
}

/// `tools` is a part of the system, not a kind of model — and grants only that.
///
/// The word an author writes in `allow-egress: [tools]` releases one thing: the
/// outbound addresses tool documents hold, which `nothing_reaches_outside_the_box`
/// enforces on a different line. It is a PART and not a model role, and
/// `spec/schema.yaml` says so in the comment above both `choices:` lines that
/// mention it.
///
/// It was in `learning-model.role`'s `choices:` all the same, copied there with
/// that comment, and the two halves of this test are the two ways that could
/// have been left standing:
///
/// * accepting `role: tools` and reading it as `llm`, which is what shipped —
///   the specification invites a word and the checker quietly means another;
/// * accepting `role: tools` and teaching the checker to admit it, which would
///   be worse: one person-approved word would then release tool addresses AND
///   hosted model inference, two unrelated boundaries under two different rules.
///   That is the "one boolean wearing several names" defect the egress rule
///   exists to remove, pointing the other way.
///
/// So three things are held: the word is not a role an author can write;
/// writing it anyway draws one message, from the rule that can name the words a
/// `role:` may say, and not a second one guessing at a grant; and granting the
/// word does not let a model out, while still granting the thing it is for.
#[test]
fn the_word_for_tool_documents_is_not_a_model_role_and_does_not_let_a_model_out() {
    assert!(
        !role_words().contains(&"tools".to_string()),
        "`tools` names the addresses tool documents may reach, which is not something a \
         model can be for. Offering it on `role:` invites an author to write a word the \
         checker has to mean something else by: {:?}",
        role_words()
    );

    // Writing it draws ONE message, from the rule that can name the words a
    // `role:` may say. The boundary rule stays quiet on that line rather than
    // adding a second error whose fix — *"add `llm`"* — would be advice about a
    // role the first error is telling the author to stop writing. Nothing gets
    // through: the document does not load either way.
    let root = written("tools-is-not-a-role", &tree("tools", "tools", HOSTED));
    let (ok, out) = check(&root);
    assert!(
        !ok,
        "`role: tools` is not a word the specification offers:\n{out}"
    );
    assert!(
        out.contains("1 problem(s)") && out.contains("schema/wrong-type"),
        "a `role:` the specification does not offer is one mistake, and the message that \
         can list the words it may say is the only one that can be right about it:\n{out}"
    );
    assert!(
        !out.contains("loader/leaves-the-box"),
        "the boundary rule guessed at a role the author is being told to change, and \
         offered a grant for the guess:\n{out}"
    );
    let offered = role_words().join(", ");
    assert!(
        out.contains(&offered),
        "and it has to say which words a `role:` may be — `{offered}`, off the \
         specification — or the author has nowhere to go:\n{out}"
    );

    // Granting it does not let a model out. An ordinary agent `model:`, which
    // needs `llm` and nothing else, under a workspace that granted `tools` and
    // nothing else.
    let root = written(
        "tools-grants-no-model",
        &[
            (
                "workspace.yaml",
                "name: probe\nallow-egress: [tools]\n".to_string(),
            ),
            (
                "agents/desk/agent.yaml",
                format!(
                    "name: Desk\ndescription: A desk.\ninstructions: Do it.\nmodel: {HOSTED}\n"
                ),
            ),
        ],
    );
    let (ok, out) = check(&root);
    assert!(
        !ok && out.contains("loader/leaves-the-box"),
        "`allow-egress: [tools]` approved the addresses tool documents may reach. It is \
         not an approval for sending this workspace's work to a model on somebody else's \
         machine, and `pact check` said:\n{out}"
    );

    // And it still grants the thing it is for: a tool document holding an
    // address outside this box, which is refused without the word.
    let with_a_tool =
        |granted: &str| {
            vec![
            ("workspace.yaml", format!("name: probe\nallow-egress: [{granted}]\n")),
            (
                "agents/desk/agent.yaml",
                "name: Desk\ndescription: A desk.\ninstructions: Do it.\n".to_string(),
            ),
            (
                "tools/upload.yaml",
                "description: Send a file.\nurl: https://vendor.example.com/upload\nmethod: post\n"
                    .to_string(),
            ),
        ]
        };
    let (ok, out) = check(&written("tools-granted", &with_a_tool("tools")));
    assert!(
        ok && out.contains("loaded cleanly"),
        "`allow-egress: [tools]` is the approval a tool document's own outbound address \
         needs, and `pact check` said:\n{out}"
    );
    let (ok, out) = check(&written("tools-not-granted", &with_a_tool("llm")));
    assert!(
        !ok,
        "and without it that address is refused, or the run above proved nothing:\n{out}"
    );
}
