//! What each word in `allow-egress:` actually gates.
//!
//! `workspace.yaml` offers a closed list of them, and until this module existed
//! **one of them was read and the rest were not**. Every check anywhere asked
//! the same question, `"llm" in egress`, so a per-role list was one boolean
//! wearing several names.
//!
//! Two consequences, both measured before this file existed:
//!
//! 1. `allow-egress: [judge]` behaved exactly like `allow-egress: []`. A team
//!    that approved a grader talking to a hosted service, and nothing else, got
//!    a workspace where the grader still could not run and the refusal told
//!    them to add `llm` — which grants every other model role at the same time.
//!    The only typeable fix the tool offered was to over-grant.
//! 2. `stt`, `tts` and `embedder` named parts of the system that no check could
//!    distinguish, so `allow-egress:`'s own help — *"which parts of this system
//!    are allowed to talk to something outside this box"* — was a sentence
//!    about a list with one entry.
//!
//! ## The rule
//!
//! A binding is admitted when `allow-egress:` names **the role that binding
//! plays**. `llm` is the general grant for *words* leaving the box, so it also
//! admits the text roles that are particular kinds of model call — `judge`,
//! `reflector`, `embedder`.
//!
//! `stt` and `tts` are deliberately **not** covered by `llm`, and this is the
//! one asymmetry in the file. If a grant for words also carried speech, there
//! would be no reason for `stt` and `tts` to be separate choices at all — they
//! would be exactly the decoration this module exists to remove. A customer's
//! voice is not their words: D16 makes audio a first-class v1 modality, and the
//! author who wrote `allow-egress: [llm]` approved a model call, not a
//! recording of somebody speaking being posted to it.
//!
//! ## Which words there are
//!
//! Not decided here either. An author writes a role in one place — `role:`
//! beside a model binding — and `spec/schema.yaml`'s own `choices:` for that
//! field is the list of words it may say. [`role_words`] reads it off the file,
//! from the group the binding sits in, so it is the declaration of the field
//! actually being read.
//!
//! This module used to keep a `const` of them beside a header calling them "the
//! six". B15 for the second time in this one file, and it had already gone
//! wrong: `spec/schema.yaml` offered `tools` on that line too — copied there,
//! comment and all, from `allow-egress:` — so `role: tools` was a word the
//! specification accepted from the author and this module had never heard of.
//! It fell through to the `llm` default in silence, and the refusal it produced
//! told the author to grant a role wider than the one they had written.
//!
//! `tools` is now off that line, where it never belonged: it is a PART of the
//! system and not a kind of model, and it already means something in
//! `allow-egress:` — the tool documents' own outbound addresses, held by
//! `nothing_reaches_outside_the_box` on a different line. Making it a model role
//! instead would have made one person-approved word open two unrelated
//! boundaries, which is this module's own defect wearing a new hat. So the two
//! lists are related and not equal: every model role is also a word
//! `allow-egress:` offers, because a role nothing can grant is a role nothing
//! can run; not every part of a system is a model.
//!
//! A seventh model role joins by existing — the gate, the roles a refusal will
//! offer, and the cases in
//! `every_part_the_boundary_offers_is_one_the_checker_knows` all read the same
//! line of the specification. Its plain-words sentence in [`part`] is the one
//! thing it still needs written by hand, and that test fails on the word rather
//! than letting the fallback reach an author.
//!
//! ## Where the roles are read
//!
//! WHICH lines bind a model is not decided here. The specification says it —
//! every field carrying `names: pact:models`, in the place that field is
//! declared — and [`bindings`] walks the author's tree through the schema to
//! find them. This module used to walk four paths written out in Rust, and the
//! specification declared five: `agent.model-for-checking` was in the schema,
//! was not in the list, and so a hosted model bound on that line loaded cleanly
//! under `allow-egress: []` while the SAME id one line above it, under `model:`,
//! was refused. B15 again — a table of field names that nothing holds against
//! the schema comes to disagree with the schema. The sixth model binding joins
//! by existing.
//!
//! It is a walk THROUGH the schema and not a search for keys spelt like model
//! fields, which is the other way to read that set off the file and is wrong in
//! the opposite direction: `metric.with` and `case.with` are `map of anything`,
//! a `model:` inside one is an ordinary setting the author does not get to
//! rename, and refusing it would refuse a document the specification allows.
//! See [`bindings`] for the measurement.
//!
//! What is decided here is the ROLE each binding plays, which the schema does
//! not state:
//!
//! | written | role | why |
//! |---|---|---|
//! | `evals.graded-by` | `judge` or `llm` | AD-56: the judge sees strictly more than the reflector ever did |
//! | a binding with a `role:` beside it | whatever it says | the schema promises those two lines "can be read against each other" |
//! | anything else that binds a model | `llm` | a model call over words, which is what `llm` grants |
//! | an agent that `accepts:` audio | `stt` | the recording goes with the words, to every model the conversation passes through |
//! | an agent that `answers-with:` audio | `tts` | the spoken reply comes back from them |
//! | an agent whose `needs: audio: yes` | `stt` or `tts` | it has to hear or speak, and the author did not say which |
//!
//! Which models a conversation passes through is [`envelope`], and it is read
//! off the specification for the same reason [`bindings`] is: it was
//! `agent.model` alone, so the same recording crossed the boundary unremarked
//! under `model-for-checking:` and under a named context policy's
//! `summarised-by:`. The measurements are on [`envelope`].
//!
//! There is no `vision` role, so pictures cross under `llm` with nothing extra
//! asked. That is not an oversight here: this file enforces the list the schema
//! declares and invents no choice of its own, because a choice no author can
//! write in `allow-egress:` would be exactly the defect in reverse.
//!
//! ## The message quotes the file
//!
//! Ledger row R56 records the last time this went wrong: the diagnostic
//! hardcoded `allow-egress: []`, so a workspace saying `[judge]` was told its
//! own file said something it does not, and an author who opens the file and
//! sees otherwise stops believing the checker. Every message here renders the
//! roles as the author wrote them.

use pact_diag::Diagnostics;
use pact_doc::Node;
use std::collections::BTreeSet;

/// The words a `role:` written beside a model binding may say, read off the
/// specification's own `choices:` for that group's own `role` field.
///
/// This module used to keep a `const` of them, and the copy drifted from the
/// specification the way every copy in this file has — B15 again, in the file
/// that already lost this argument once over which fields bind a model (see
/// [`bindings`]). The measurement is in
/// `every_part_the_boundary_offers_is_one_the_checker_knows`: `role: tools` was
/// a word `spec/schema.yaml` accepted from the author and this list did not
/// have, so it fell through to the `llm` default and the author was told, in a
/// refusal, to grant a role wider than the one they had written. The seventh
/// model role joins by existing.
///
/// It is the `role` field of the group the binding SITS IN — the field actually
/// being read — and not `workspace.allow-egress`, which is a different
/// declaration for a different question: which parts of the system a person has
/// approved. Every model role is one of those parts, because a role nothing can
/// grant is a role nothing can run, and the specification says so where it
/// declares them. The reverse is false: `tools` is a part and not a model.
///
/// Empty for a group with no `role:` in it, which is every group but one today.
fn role_words(group: &pact_schema::Group) -> Vec<&str> {
    group
        .fields
        .iter()
        .find(|f| f.name == "role")
        .map(|f| choices(&f.ty))
        .unwrap_or_default()
}

/// The words a closed list accepts, through however many lists it is wrapped in.
///
/// `role:` is a plain `one-of`; a field that became `list of one-of` tomorrow —
/// which is what `allow-egress:` already is — is read here too.
fn choices(ty: &pact_schema::Ty) -> Vec<&str> {
    match ty {
        pact_schema::Ty::OneOf(words) => words.iter().map(String::as_str).collect(),
        pact_schema::Ty::ListOf(inner) => choices(inner),
        _ => Vec::new(),
    }
}

/// The roles that are a kind of model call over words, and so are also admitted
/// by the general `llm` grant.
///
/// A decision the specification does not state, unlike [`role_words`], which is
/// why this one is still written out here: the schema says which words exist,
/// and no line in it says which of them a grant for words carries with it.
/// `stt` and `tts` are the two it does not — see the module header for why that
/// asymmetry is the reason those two choices exist at all.
///
/// Written here, but not unheld:
/// `every_word_the_general_grant_carries_is_a_model_call_over_words` builds one
/// tree per word the specification offers and measures which of them
/// `allow-egress: [llm]` really admits. Dropping a word from this list, or
/// adding `stt` to it, fails there instead of shipping — which is what happened
/// to the last list in this file that nothing measured.
const WORDS: &[&str] = &["llm", "embedder", "judge", "reflector"];

/// Every spelling the schema's `answer-shape` vocabulary accepts for audio.
///
/// Taken from `spec/schema.yaml`'s own `shapes:` block rather than guessed —
/// `accepts:` and `answers-with:` are written in the author's words, and a check
/// that only recognised the word `audio` would miss `a voice message`, which is
/// the spelling the vocabulary was widened to accept in the first place.
const AUDIO_SPELLINGS: &[&str] = &["audio", "a recording", "a voice message", "list of audio"];

/// Plain words for a role, for the sentence saying what may not leave.
///
/// `llm` is "the model doing the work" and not "a model", because the message is
/// printed under lists like `[judge]` where several other things on the list are
/// also models — and a sentence that says "nothing there lets a model talk
/// outside the box" to a workspace that just granted the judge is the R56
/// mistake with different words.
fn part(role: &str) -> &'static str {
    match role {
        "llm" => "the model doing the work",
        "stt" => "the model that turns speech into words",
        "tts" => "the model that turns words into speech",
        "embedder" => "the model that turns text into numbers",
        "judge" => "the model that grades the checks",
        "reflector" => "the model that proposes improvements",
        // There is no `tools` arm, and there is not meant to be. `tools` is a
        // word `allow-egress:` offers and `role:` does not: it names the tool
        // documents' own outbound addresses, which
        // `nothing_reaches_outside_the_box` holds on a different line. Nothing
        // built here is ever about it, because every sentence built from here is
        // about a MODEL that may not be reached.
        //
        // Reached only if the specification grows a role word with no sentence
        // written for it. Honest rather than panicking, because a diagnostic is
        // not the place to discover a spec edit — and
        // `every_part_the_boundary_offers_is_one_the_checker_knows` fails on
        // that word rather than letting this reach an author, which is what the
        // comment that used to sit here merely asserted.
        _ => "this",
    }
}

/// What actually travels, for the sentence about content rather than about a
/// model. Two vocabularies because the two sentences are about different things:
/// a `role: stt` binding is a *model* that may not be reached, and an agent that
/// `accepts:` a voice message is a *recording* that may not be sent. Reusing one
/// wording gave "nothing there lets a recording talk to anything outside the
/// box", which is not a sentence about anything.
fn travels(roles: &[&str]) -> &'static str {
    match roles {
        ["stt"] => "a recording",
        ["tts"] => "a spoken reply",
        // `needs: audio: yes` — the author said it has to hear or speak and did
        // not say which, so neither does this.
        _ => "a recording or a spoken reply",
    }
}

/// The roles `allow-egress:` names, as written.
fn granted(root: &Node) -> Vec<&str> {
    root.get("allow-egress")
        .and_then(Node::as_list)
        .map(|roles| roles.iter().filter_map(Node::as_str).collect())
        .unwrap_or_default()
}

/// The author's own `allow-egress:` line, rendered the way they wrote it.
///
/// R56. A message that quotes a line the author did not write is a message they
/// stop believing.
pub fn listed(root: &Node) -> String {
    format!("[{}]", granted(root).join(", "))
}

/// Does this workspace let a binding playing `role` talk outside the box?
fn admits(root: &Node, role: &str) -> bool {
    let listed = granted(root);
    listed.contains(&role) || (WORDS.contains(&role) && listed.contains(&"llm"))
}

/// One thing this tree would send off this machine, and what would allow it.
struct Reach<'a> {
    /// The field the author wrote, so the fix is a line they can find.
    field: &'a str,
    /// The model id and where it is written — the caret lands here.
    id: &'a Node,
    /// Any ONE of these in `allow-egress:` admits it, narrowest first: the fix
    /// asks for the least grant that works, never the superset. Borrowed from
    /// the specification, because that is where the words come from — see
    /// [`role_words`].
    roles: Vec<&'a str>,
    /// What to call the model that may not be reached — see [`noun`].
    noun: &'static str,
    /// What travels besides the words, in the author's own words. `None` for a
    /// plain model call.
    carries: Option<String>,
}

fn yes(node: &Node) -> bool {
    match &node.value {
        pact_doc::Value::Bool(b) => *b,
        pact_doc::Value::Str(s) => matches!(
            s.trim().to_ascii_lowercase().as_str(),
            "yes" | "true" | "on" | "y"
        ),
        _ => false,
    }
}

fn is_audio(node: &Node) -> bool {
    node.as_str()
        .map(|s| s.trim().to_ascii_lowercase())
        .is_some_and(|s| AUDIO_SPELLINGS.contains(&s.as_str()))
}

/// The first `accepts:`/`answers-with:` entry naming audio, as `key: shape`.
fn audio_entry(agent: &Node, block: &str) -> Option<String> {
    let rows = agent.get(block)?.as_map()?;
    rows.iter()
        .find(|(_, e)| is_audio(&e.node))
        .map(|(k, e)| format!("{block}: {k}: {}", e.node.as_str().unwrap_or("audio")))
}

/// The namespace a field's `names:` writes when its value is a model id.
const MODELS: &str = "pact:models";

/// One model binding the specification declares, found in the author's tree.
struct Bound<'a> {
    /// The field as the author spelt it — an alias is what they typed and what
    /// the message has to quote for them to find the line.
    written: &'a str,
    /// The id, and where it is written.
    id: &'a Node,
    /// The roles that admit it, narrowest first.
    roles: Vec<&'a str>,
    /// What a refusal calls the model this line binds.
    noun: &'static str,
}

/// Every model id in this tree, walked **through the specification**.
///
/// WHICH lines bind a model is `names: pact:models` in `spec/schema.yaml`, for
/// the reason `Field::reaches_outside` gives about outbound addresses: a table
/// of field names kept in Rust is a table that comes to name a different set
/// from the one the specification declares. It did. Four paths were walked here
/// and five fields carried `names: pact:models`, so `model-for-checking:` — a
/// whole model binding — was outside the boundary.
///
/// # Why the walk is guided by the schema and not by key names
///
/// The first fix for that read every key in the tree spelt like a model field,
/// which is what `nothing_reaches_outside_the_box` does with addresses. It
/// refuses documents the specification allows. `metric.with` and `case.with` are
/// `type: map of anything` — *"any settings that score takes, written exactly as
/// its own documentation names them. Nothing is renamed"* — and one of those
/// scores takes a setting called `model`. Measured: an eval suite with
///
/// ```text
/// metrics:
///   - uri: deepeval:faithfulness
///     with: { model: claude-opus-5 }
/// ```
///
/// went from *"OK — loaded cleanly (17 settings)"* to a hard
/// `loader/leaves-the-box` whose fix told the author to rename a key whose name
/// is not theirs to choose. The address walk is safe from this only because
/// `leaves_the_box` demands a `scheme://`; a model id is an ordinary word, so
/// there is no such shape to lean on. A key spelt `model:` inside a block the
/// specification deliberately leaves open is not a binding, and the only thing
/// that knows the difference is the specification.
///
/// So this descends the way [`pact_schema::Schema::validate`] descends: from the
/// group the root IS, into the groups its fields declare. A block typed
/// `anything` is where the walk stops, which is the same sentence as "the
/// specification says nothing about what is in here". Two things follow for
/// free: a `model:` under an unrecognised key is not reported a second time on a
/// line the author is already being told to delete, and the group a binding sits
/// in is known, so [`plays`] can be told which field of which group it is
/// looking at.
fn bindings<'a>(
    node: &'a Node,
    group: &'a pact_schema::Group,
    schema: &'a pact_schema::Schema,
    found: &mut Vec<Bound<'a>>,
) {
    let Some(map) = node.as_map() else { return };
    for f in &group.fields {
        // Every spelling of the field the author could have used. `check_group`
        // reads aliases the same way; taking only the canonical name would let
        // an import-compatible spelling bind a hosted model unseen.
        for spelling in std::iter::once(&f.name).chain(f.aliases.iter()) {
            let Some((written, entry)) = map.get_key_value(spelling) else {
                continue;
            };
            if f.names.iter().any(|n| n == MODELS) {
                // `None` is a `role:` the specification does not offer, already
                // being refused on this line by the message that can name the
                // words it may say. See [`plays`].
                let Some(played) = plays(group, &f.name, node) else {
                    continue;
                };
                for id in ids(&entry.node, &f.ty) {
                    found.push(Bound {
                        written,
                        id,
                        noun: noun(&f.name, &played),
                        roles: played.clone(),
                    });
                }
                continue;
            }
            // The one open block that is not open. A bundle's `contributes:` is
            // `map of anything` because it holds the same kinds a workspace
            // does — *"what it defines, read exactly as if you had written it
            // here"*, in the schema's own words — so it is read exactly that
            // way here. `brings:`'s own comment says why it matters: a bundle
            // that quietly adds an agent adds something that can act, and that
            // agent pins a model like any other.
            if group.name == "bundle" && f.name == "contributes" {
                if let Some(workspace) = schema.group("workspace") {
                    bindings(&entry.node, workspace, schema, found);
                }
                continue;
            }
            descend(&entry.node, &f.ty, schema, found);
        }
    }
}

/// Follow a value into whatever groups its declared type contains.
///
/// Every arm that is not a group is a stop, `Ty::Anything` among them — see
/// [`bindings`] for why that stop is the whole point.
fn descend<'a>(
    value: &'a Node,
    ty: &'a pact_schema::Ty,
    schema: &'a pact_schema::Schema,
    found: &mut Vec<Bound<'a>>,
) {
    match ty {
        pact_schema::Ty::Group(name) => {
            if let Some(g) = schema.group(name) {
                bindings(value, g, schema, found);
            }
        }
        pact_schema::Ty::MapOf(inner) => {
            if let Some(map) = value.as_map() {
                for entry in map.values() {
                    descend(&entry.node, inner, schema, found);
                }
            }
        }
        pact_schema::Ty::ListOf(inner) => match &value.value {
            pact_doc::Value::List(items) => {
                for item in items {
                    descend(item, inner, schema, found);
                }
            }
            // One value where a list is expected is accepted everywhere else
            // (`Schema::check_value` says why), so it is followed here too:
            // a tree that loads must be a tree this rule saw all of.
            _ => descend(value, inner, schema, found),
        },
        _ => {}
    }
}

/// The ids written under a model binding, read against the shape the
/// specification declares for it.
///
/// A model id is a name, so a binding holding a BLOCK is not a binding — it is a
/// mistake some other rule reports, and inventing a refusal for it here would be
/// a second message about one line.
///
/// # Why the declared type is asked, rather than reading any list
///
/// A list was once read as a list of ids on every field, on the argument that a
/// field which grows into one is then held to the boundary on the day it does.
/// It is the right instinct and it was the wrong reading, because every field
/// carrying `names: pact:models` is `type: text` today — so on the documents
/// that actually exist the arm could only ever fire on a line
/// `schema/wrong-type` is already refusing. MEASURED on the version that read
/// every list, `graded-by: [claude-opus-5, gpt-5.4]` under `allow-egress: []`:
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
/// document that cannot load whichever way the author resolves them — the
/// "one mistake gets one message" rule in [`reaches`] broken by the rule that
/// was meant to future-proof it.
///
/// So the instinct is kept and the reading is asked of the specification: a
/// `list of text` field's items are ids, a `text` field's list is somebody
/// else's error. The day a model binding is declared `list of text`, this reads
/// it, and nothing here has to be edited for that —
/// `a_model_binding_the_specification_declares_as_a_list_is_read_as_one` holds
/// both directions against a specification that declares each shape.
fn ids<'a>(node: &'a Node, ty: &pact_schema::Ty) -> Vec<&'a Node> {
    if let pact_doc::Value::List(items) = &node.value {
        return match ty {
            pact_schema::Ty::ListOf(_) => items.iter().filter(|i| i.as_str().is_some()).collect(),
            _ => Vec::new(),
        };
    }
    if node.as_str().is_some() {
        vec![node]
    } else {
        Vec::new()
    }
}

/// What a refusal calls the model a particular field binds.
///
/// Keyed off the FIELD, because two fields play the same role and do not name
/// the same model: `model-for-checking:`'s own help says it is *"a different
/// model for the stages that check work … Everything else uses `model:`"*, and
/// a refusal quoting that line while saying "the model doing the work" tells the
/// author something their file contradicts one line down. R56 again.
///
/// A field with no entry here falls back to the noun for its role, which is what
/// every field did before — so this table cannot rot into a wrong answer, only
/// into a general one.
fn noun(field: &str, roles: &[&str]) -> &'static str {
    match field {
        "model-for-checking" => "the model that checks the work",
        "summarised-by" => "the model that writes the summary",
        _ => part(roles[0]),
    }
}

/// Which role a binding plays — the one thing the schema does not state.
///
/// Any ONE of the returned roles in `allow-egress:` admits it, narrowest first.
/// `group` is the group the binding sits in, so the words an author's `role:`
/// may say are read off that group's own declaration — see [`role_words`].
///
/// `None` when the author wrote a `role:` the specification does not offer. That
/// is the same judgement `refusals`' caller already makes about a model id in no
/// catalogue at all: `Schema::validate` is refusing that very line and naming
/// the words it may say, the document cannot load, and a second message here
/// could only offer a grant for a role the author is being told to stop writing.
fn plays<'a>(group: &'a pact_schema::Group, field: &str, owner: &Node) -> Option<Vec<&'a str>> {
    // AD-56: the judge reads every eval case, which is strictly more than the
    // reflector ever sees. `judge` is the least grant that covers it, and `llm`
    // covers it too — so a workspace that has already decided model calls may
    // leave is not asked to decide again. Named here rather than derived,
    // because it is a decision about what a grader sees and no line in the
    // specification says it. Group AND field, because it is a decision about
    // the model an eval suite grades with and not about a word.
    if (group.name.as_str(), field) == ("evals", "graded-by") {
        return Some(vec!["judge", "llm"]);
    }
    // The one place an author can write a role by hand. The schema's help for
    // `learning-model.role` promises it names "one of the model roles
    // `allow-egress:` names, so the two lines can be read against each other" —
    // and nothing read them against each other until this module, so
    // `role: reflector` was gated on `llm` and `allow-egress: [reflector]` gated
    // nothing.
    //
    // Read off the SIBLING rather than off the group, even though the group is
    // now known. That is a shape assumption and not a fact the specification
    // states: `^ *role:` occurs exactly once in `spec/schema.yaml`
    // (learning-model), so today "a `role:` beside a model id" and "a learning
    // model" are the same set. It is written this way on purpose — a second
    // group growing a `role:` field beside a model binding is read here the day
    // it does, which is the reading the schema's own help asks for. Nothing
    // enforces that, so it is said here rather than assumed.
    //
    // The words it may say come from that group's own `role:` declaration, so
    // this lookup asks the specification about the field it is reading.
    if let Some(written) = owner.get("role").and_then(Node::as_str) {
        let words = role_words(group);
        let role = match words.iter().find(|r| **r == written) {
            Some(found) => *found,
            // A word the specification does not offer. MEASURED with `tools`
            // still on that line: two errors on one line, and the second one's
            // advice — *"add `llm`"* — was advice about a role the first one was
            // telling the author to stop writing. The schema's message names
            // every word `role:` may say and is the only one that can be right,
            // so this rule says nothing and nothing gets through: the document
            // does not load either way.
            None if !words.is_empty() => return None,
            // Unless the field is not a closed list at all, and no other message
            // is coming. A role nobody constrained is read the way every other
            // binding without a `role:` is read.
            None => "llm",
        };
        let mut played = vec![role];
        if WORDS.contains(&role) && role != "llm" {
            played.push("llm");
        }
        return Some(played);
    }
    // A `role:` the group REQUIRES and the author has not written yet. The role
    // this binding plays is exactly as unknown as it is one line up, where the
    // author wrote a word the specification does not offer — so this answers the
    // same way, and for the same reason.
    //
    // It did not, and the fall-through was the module header's own consequence
    // #1 shipped back. MEASURED, `models: { execution: { model: claude-opus-5 } }`
    // in `learning.yaml` under `allow-egress: []`:
    //
    // ```text
    // error: A model binding must have a 'role'.
    //   rule: schema/missing-field
    // error: `model: claude-opus-5` is only served off this machine … nothing
    //   there lets the model doing the work talk to anything outside the box.
    //   fix: … or add `llm` to `allow-egress:` …
    //   rule: loader/leaves-the-box
    // 2 problem(s) found
    // ```
    //
    // Two messages on one authored row, the second guessing `llm` for a line
    // whose whole point is that nobody has said what it is for — so an author
    // who meant `role: judge` was advised, in writing, to make the widest grant
    // there is. *"The only typeable fix the tool offered was to over-grant."*
    //
    // Asked of the specification rather than of the group's name: `required: yes`
    // on that `role:` is what guarantees `schema/missing-field` is already on
    // this row, which is what makes saying nothing here safe. A group with an
    // OPTIONAL `role:` gets no such guarantee, so it keeps the reading below —
    // a role nobody constrained is read the way every binding without one is.
    if group.fields.iter().any(|f| f.name == "role" && f.required) {
        return None;
    }
    // Everything else that binds a model is a plain model call over words —
    // `agent.model`, `agent.model-for-checking`, `context-policy.summarised-by`,
    // `catalog.default` — and `llm` is the grant for words leaving the box.
    Some(vec!["llm"])
}

/// Everything in this tree that would leave the box, with the roles that allow it.
///
/// One mistake gets one message: when a line's own words are already refused,
/// the audio that would travel with them is not reported on that line as well.
/// The author has one line to change and telling them about three grants at once
/// buries it.
///
/// # One message per LINE, not per agent
///
/// An agent with a hosted `model:` and a hosted `model-for-checking:` under
/// `allow-egress: []` draws two refusals. That is deliberate, and it is what the
/// rule above already means. The audio case stacks a SECOND grant onto a line
/// that is already refused — the author fixes `model:` and both messages go, so
/// printing them together buries the one edit under three. Two model bindings
/// are two lines the author has to edit separately, and changing one leaves the
/// other reaching outside the box. Reporting only the first would mean fixing
/// `model:` and being told about `model-for-checking:` on the next run, which is
/// the failure a checker exists to prevent.
///
/// So the "already refused" test is per BINDING and not per agent: under
/// `allow-egress: [llm]` an agent whose `model:` is local and whose
/// `model-for-checking:` is hosted has nothing said about its words, and the
/// recording it `accepts:` is refused on the line that would carry it.
///
/// The other way this rule could stack a message onto a line already being
/// reported is a model bound inside a block the schema does not recognise, and
/// it cannot: [`bindings`] never enters one.
fn reaches<'a>(
    root: &'a Node,
    kind: &str,
    schema: &'a pact_schema::Schema,
    off_box: &dyn Fn(&Node) -> bool,
) -> Vec<Reach<'a>> {
    let mut out: Vec<Reach<'a>> = Vec::new();

    if let Some(group) = schema.group(kind) {
        let mut found: Vec<Bound<'a>> = Vec::new();
        bindings(root, group, schema, &mut found);
        for b in found {
            out.push(Reach {
                field: b.written,
                id: b.id,
                roles: b.roles,
                noun: b.noun,
                carries: None,
            });
        }
    }

    // What else is in the envelope besides the words. Per AGENT, because the
    // recording enters at the agent that `accepts:` it — and then against every
    // model that agent's conversation passes through, which is [`envelope`].
    if let Some(agents) = root.get("agents").and_then(Node::as_map) {
        for (_, entry) in agents {
            let agent = &entry.node;
            let carries = carried(agent);
            if carries.is_empty() {
                continue;
            }
            for b in envelope(agent, root, schema) {
                if !off_box(b.id) {
                    // Nothing leaves on this line, so nothing about it is gated.
                    continue;
                }
                if !b.roles.iter().any(|r| admits(root, r)) {
                    // The words on THIS line are already refused above. One
                    // mistake gets one message.
                    continue;
                }
                for (roles, written) in &carries {
                    out.push(Reach {
                        field: b.written,
                        id: b.id,
                        roles: roles.clone(),
                        noun: b.noun,
                        carries: Some(written.clone()),
                    });
                }
            }
        }
    }

    // Two agents naming one context policy send their recordings through one
    // summariser, and the second pass over it says the same sentence about the
    // same line — one mistake, one message.
    let mut seen = std::collections::HashSet::new();
    out.retain(|r| {
        seen.insert((
            r.id.span.file.to_string(),
            r.id.span.byte_start,
            r.roles.join(","),
            r.carries.clone(),
        ))
    });

    out
}

/// What besides the words is in this agent's envelope: the grant each thing
/// needs, and the line the author wrote that put it there.
///
/// `needs: audio: yes` says it has to "hear or speak" and does not say which, so
/// either grant satisfies the sentence the author wrote. Demanding both would
/// refuse a transcription agent for a reply it never speaks, which is a worse
/// answer than the one this replaces — and it is only consulted when neither
/// `accepts:` nor `answers-with:` has already said which way the audio goes.
fn carried(agent: &Node) -> Vec<(Vec<&'static str>, String)> {
    let mut out: Vec<(Vec<&'static str>, String)> = Vec::new();
    if let Some(written) = audio_entry(agent, "accepts") {
        out.push((vec!["stt"], written));
    }
    if let Some(written) = audio_entry(agent, "answers-with") {
        out.push((vec!["tts"], written));
    }
    if out.is_empty()
        && agent
            .get("needs")
            .and_then(|n| n.get("audio"))
            .is_some_and(yes)
    {
        out.push((vec!["stt", "tts"], "needs: audio: yes".to_string()));
    }
    out
}

/// Every model this agent's conversation passes through.
///
/// # Why this is not `agent.model`
///
/// It was, and the module's own asymmetry — *"the author who wrote
/// `allow-egress: [llm]` approved a model call, not a recording of somebody
/// speaking being posted to it"* — held on one of the fields that reads the
/// conversation and not on the others. MEASURED on the version scoped to
/// `model:`, each tree with `allow-egress: [llm]`, a locally-served `model:`,
/// and a hosted second model:
///
/// | tree | said |
/// |---|---|
/// | `model:` hosted, `accepts: clip: audio` | refused, and named `stt` |
/// | `model-for-checking:` hosted, `accepts: clip: audio` | `OK — loaded cleanly (14 settings)` |
/// | `model-for-checking:` hosted, `answers-with: reply: a voice message` | `OK — loaded cleanly (14 settings)` |
/// | `model-for-checking:` hosted, `needs: audio: yes` | `OK — loaded cleanly (15 settings)` |
/// | `summarised-by:` hosted, `accepts: clip: audio` | `OK — loaded cleanly (17 settings)` |
///
/// The justification for the narrow scope was that "an agent hears and speaks
/// with the model doing its work". `model-for-checking:`'s own help refutes it —
/// *"Expect the conversation to be read again from the start each time it
/// switches"* — and so does `context-policy:`'s, which is the rules for
/// *"when the conversation gets too long"*: the model that summarises a
/// conversation reads the conversation, recording included. A recording that may
/// not go to one of them may not go to the others.
///
/// # What is in it, and how that set is decided
///
/// Not by a list of field names here — that is B15, which this file has now lost
/// twice. Three sources, each read off the specification:
///
/// 1. Every model binding the schema declares ON THE AGENT, through the same
///    [`bindings`] walk the words half uses. A seventh field on the `agent`
///    group joins by existing.
/// 2. Every model binding in the documents the agent NAMES, followed through the
///    `names:` edges the schema declares on the agent's own fields into the
///    workspace collection each one points at. Today that is exactly
///    `context-policy:` → `context-policies.<name>.summarised-by`.
/// 3. The catalogue's `default:`, for an agent that pins no `model:` — because
///    that is the model it runs. The comment that used to sit here asserted the
///    opposite in prose, that `default:` is "locally servable by construction";
///    a workspace-supplied `models/catalog.yaml` is not, and `spec/schema.yaml`
///    now carries `names: pact:models` on that line so the words half holds it
///    too.
///
/// # What is deliberately NOT in it
///
/// `evals.graded-by` and `learning-model.model`, and this is a position rather
/// than an oversight — `an_eval_judge_is_not_in_an_agents_audio_envelope` holds
/// it, so it is a line somebody can argue with instead of a silence.
///
/// A judge sees eval CASES, not the conversation: whether one of those holds a
/// recording depends on `population:`, which the author writes per suite —
/// `authored-enumeration` means "you wrote down the situations you thought of",
/// and refusing every such suite for a recording it cannot contain is the
/// over-refusal [`bindings`] measured and rejected on the words half. A learning
/// model is bound in `learning.yaml`, which belongs to the workspace and to no
/// one agent, so there is no agent whose `accepts:` line a message could quote.
/// Neither is reachable by rule 2: `agent.evals` writes `names: pact:evals`, a
/// supplied namespace rather than a workspace collection, and `workspace.evals`
/// is a `group:` and not a map — so the walk finds nothing to enter, which is
/// the answer this paragraph argues for and not merely the one it happens to
/// give.
fn envelope<'a>(
    agent: &'a Node,
    root: &'a Node,
    schema: &'a pact_schema::Schema,
) -> Vec<Bound<'a>> {
    let mut found: Vec<Bound<'a>> = Vec::new();
    if let Some(group) = schema.group("agent") {
        bindings(agent, group, schema, &mut found);
        named(agent, group, root, schema, &mut found);
    }
    if agent.get("model").is_none()
        && let Some(default) = root.get("models").and_then(|m| m.get("default"))
        && default.as_str().is_some()
    {
        found.push(Bound {
            written: "default",
            id: default,
            roles: vec!["llm"],
            noun: part("llm"),
        });
    }
    found
}

/// The model bindings in the documents this agent names.
///
/// A `names:` edge on an agent field says which workspace collection its value
/// is a key in — `context-policy:` writes `names: context-policies`, and
/// `workspace.context-policies` is `map of group:context-policy`. So the entry
/// is found and walked the way [`bindings`] walks anything else, and the set of
/// edges followed is the set the specification declares rather than one written
/// out here.
///
/// A collection that is not a `map of` is skipped, which is not an accident of
/// implementation: `workspace.evals` is a `group:`, one suite and not a map of
/// them, and `agent.evals` names it through the supplied `pact:evals` namespace
/// rather than through a collection at all. See [`envelope`] for why an eval
/// judge staying out is the intended answer.
fn named<'a>(
    agent: &'a Node,
    agent_group: &'a pact_schema::Group,
    root: &'a Node,
    schema: &'a pact_schema::Schema,
    found: &mut Vec<Bound<'a>>,
) {
    let Some(workspace) = schema.group("workspace") else {
        return;
    };
    for f in &agent_group.fields {
        let Some(written) = std::iter::once(&f.name)
            .chain(f.aliases.iter())
            .find_map(|spelling| agent.get(spelling))
        else {
            continue;
        };
        for collection in &f.names {
            let Some(holder) = workspace.fields.iter().find(|w| w.name == *collection) else {
                continue;
            };
            let pact_schema::Ty::MapOf(inner) = &holder.ty else {
                continue;
            };
            let Some(rows) = root.get(collection).and_then(Node::as_map) else {
                continue;
            };
            for name in ids(written, &f.ty) {
                let Some(named) = name.as_str().and_then(|n| rows.get(n)) else {
                    continue;
                };
                descend(&named.node, inner, schema, found);
            }
        }
    }
}

/// How the fix names the grants that would work: the narrowest first, and the
/// alternative when there really is one. Never a bare "add `llm`" for a binding
/// `llm` is merely the superset of.
fn grants(roles: &[&str]) -> String {
    match roles {
        [one] => format!("`{one}`"),
        [first, rest @ ..] => {
            let others: Vec<String> = rest.iter().map(|r| format!("`{r}`")).collect();
            format!("`{first}` or {}", others.join(" or "))
        }
        [] => "a role".to_string(),
    }
}

/// Refuse every binding whose role this workspace has not granted.
///
/// `kind` is the group this document IS — `workspace` or `agent`, decided once
/// by the caller — and `schema` says both which lines bind a model and where in
/// a document of that kind they can be written. See [`bindings`]. `local` is
/// every model id served on this machine, `offer` a locally-served id to write
/// instead, and `known` every id this tree could possibly mean — an id in none
/// of them is a TYPO, and `schema/no-such-name` reports it with the right
/// message and the right fix. Saying it "is only served off this machine" as
/// well is a confident false statement about a model that exists nowhere.
///
/// # A document that cannot draw the boundary is not held to one
///
/// `allow-egress:` is a `workspace` setting. A lone `agent.yaml` with no
/// workspace around it has nowhere to write one, so a refusal there says *"this
/// workspace says `allow-egress: []`"* about a file that does not exist and
/// offers a fix in another one — R56, in a document the author is already being
/// told to put a workspace around. Asked of the schema rather than by comparing
/// `kind` to a literal, so a second kind of document that can draw a boundary is
/// held to it the day it declares the field. An absent `allow-egress:` in a
/// document that COULD have one still means nothing may leave: that is the
/// air-gapped default (D17), and it is the answer this has always given.
pub fn refusals(
    root: &Node,
    kind: &str,
    schema: &pact_schema::Schema,
    local: &BTreeSet<String>,
    offer: &str,
    known: &BTreeSet<String>,
    diags: &mut Diagnostics,
) {
    if !schema
        .group(kind)
        .is_some_and(|g| g.fields.iter().any(|f| f.name == "allow-egress"))
    {
        return;
    }
    let written = listed(root);
    let off_box = |node: &Node| {
        node.as_str()
            .is_some_and(|id| !id.is_empty() && !local.contains(id) && known.contains(id))
    };

    for reach in reaches(root, kind, schema, &off_box) {
        let Some(id) = reach.id.as_str() else {
            continue;
        };
        if !off_box(reach.id) {
            continue;
        }
        if reach.roles.iter().any(|r| admits(root, r)) {
            continue;
        }
        let Reach {
            field,
            roles,
            noun,
            carries,
            ..
        } = &reach;
        let message = match carries {
            None => format!(
                "`{field}: {id}` is only served off this machine, and this workspace \
                 says `allow-egress: {written}` — nothing there lets {noun} talk to \
                 anything outside the box."
            ),
            Some(carried) => format!(
                "`{field}: {id}` is only served off this machine, and `{carried}` means \
                 {} goes there with the words. This workspace says \
                 `allow-egress: {written}`, which lets the words out and does not name \
                 {}.",
                travels(roles),
                grants(roles)
            ),
        };
        diags.push(pact_diag::Diagnostic::error(
            "loader/leaves-the-box",
            reach.id.span.clone(),
            message,
            format!(
                "write `{field}: {offer}`, which runs here; or add {} to \
                 `allow-egress:` in workspace.yaml — which is a change a person has \
                 to approve.",
                grants(roles)
            ),
        ));
    }
}
