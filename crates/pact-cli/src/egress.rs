//! What each of the six `allow-egress:` roles actually gates.
//!
//! `workspace.yaml` offers six choices — `llm`, `stt`, `tts`, `embedder`,
//! `judge`, `reflector` — and until this module existed **one of them was read
//! and five were not**. Every check anywhere asked the same question,
//! `"llm" in egress`, so a per-role list was one boolean wearing six names.
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
//! ## Where the roles are read
//!
//! | written | role | why |
//! |---|---|---|
//! | `agents.<a>.model` | `llm` | the model doing the work |
//! | `context-policies.<p>.summarised-by` | `llm` | a model call that writes a summary |
//! | `evals.graded-by` | `judge` or `llm` | AD-56: the judge sees strictly more than the reflector ever did |
//! | `learning.models.<m>.model` | whatever its own `role:` says | the schema promises those two lines "can be read against each other" |
//! | an agent that `accepts:` audio | `stt` | the recording goes to the model with the words |
//! | an agent that `answers-with:` audio | `tts` | the spoken reply comes back from it |
//! | an agent whose `needs: audio: yes` | `stt` or `tts` | it has to hear or speak, and the author did not say which |
//!
//! There is no `vision` role, so pictures cross under `llm` with nothing extra
//! asked. That is not an oversight here: this file enforces the list the schema
//! declares and does not invent a seventh choice, because a choice no author can
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

/// The six roles `allow-egress:` offers, in the order `spec/schema.yaml` lists
/// them. Named here so the day a seventh is added, the compiler has one place
/// to bring anybody who has to think about it.
pub(crate) const ROLES: &[&str] = &["llm", "stt", "tts", "embedder", "judge", "reflector"];

/// The roles that are a kind of model call over words, and so are also admitted
/// by the general `llm` grant.
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
        // Unreachable while `allow-egress:` and `role:` share one closed list,
        // which the schema enforces. Honest rather than panicking, because a
        // diagnostic is not the place to discover a spec edit.
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
    /// asks for the least grant that works, never the superset.
    roles: Vec<&'static str>,
    /// What travels besides the words, in the author's own words. `None` for a
    /// plain model call.
    carries: Option<String>,
}

fn yes(node: &Node) -> bool {
    match &node.value {
        pact_doc::Value::Bool(b) => *b,
        pact_doc::Value::Str(s) => matches!(s.trim().to_ascii_lowercase().as_str(), "yes" | "true" | "on" | "y"),
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

/// Everything in this tree that would leave the box, with the roles that allow it.
///
/// One mistake gets one message: when an agent's own `model:` is already refused
/// for `llm`, its audio is not reported as well. The author has one line to
/// change and telling them about three grants at once buries it.
fn reaches<'a>(root: &'a Node, off_box: &dyn Fn(&Node) -> bool) -> Vec<Reach<'a>> {
    let mut out: Vec<Reach<'a>> = Vec::new();

    if let Some(agents) = root.get("agents").and_then(Node::as_map) {
        for (_, entry) in agents {
            let agent = &entry.node;
            let Some(model) = agent.get("model") else { continue };
            if !off_box(model) {
                // Nothing leaves, so nothing is gated. An agent that pins no
                // model at all lands here too: PACT then binds the catalogue's
                // `default:`, which D17 keeps locally servable by construction.
                continue;
            }
            if !admits(root, "llm") {
                out.push(Reach { field: "model", id: model, roles: vec!["llm"], carries: None });
                continue;
            }
            // The words are allowed out. What else is in the envelope?
            if let Some(written) = audio_entry(agent, "accepts") {
                out.push(Reach {
                    field: "model",
                    id: model,
                    roles: vec!["stt"],
                    carries: Some(written),
                });
            }
            if let Some(written) = audio_entry(agent, "answers-with") {
                out.push(Reach {
                    field: "model",
                    id: model,
                    roles: vec!["tts"],
                    carries: Some(written),
                });
            }
            // `needs: audio: yes` says it has to "hear or speak" and does not say
            // which, so either grant satisfies the sentence the author wrote.
            // Demanding both would refuse a transcription agent for a reply it
            // never speaks, which is a worse answer than the one this replaces.
            let needs_audio = agent.get("needs").and_then(|n| n.get("audio")).is_some_and(yes);
            if needs_audio
                && audio_entry(agent, "accepts").is_none()
                && audio_entry(agent, "answers-with").is_none()
            {
                out.push(Reach {
                    field: "model",
                    id: model,
                    roles: vec!["stt", "tts"],
                    carries: Some("needs: audio: yes".to_string()),
                });
            }
        }
    }

    if let Some(policies) = root.get("context-policies").and_then(Node::as_map) {
        for (_, entry) in policies {
            if let Some(m) = entry.node.get("summarised-by") {
                out.push(Reach { field: "summarised-by", id: m, roles: vec!["llm"], carries: None });
            }
        }
    }

    // AD-56: the judge reads every eval case, which is strictly more than the
    // reflector ever sees. `judge` is the least grant that covers it, and `llm`
    // covers it too — so a workspace that has already decided model calls may
    // leave is not asked to decide again.
    if let Some(m) = root.get("evals").and_then(|e| e.get("graded-by")) {
        out.push(Reach { field: "graded-by", id: m, roles: vec!["judge", "llm"], carries: None });
    }

    // The one place an author can write any of the six roles by hand. The
    // schema's help for `learning-model.role` promises it uses "the same words
    // `allow-egress:` uses, so the two lines can be read against each other" —
    // and nothing read them against each other until here, so `role: reflector`
    // was gated on `llm` and `allow-egress: [reflector]` gated nothing.
    if let Some(rows) = root.get("learning").and_then(|l| l.get("models")).and_then(Node::as_map) {
        for (_, entry) in rows {
            let Some(m) = entry.node.get("model") else { continue };
            let written = entry.node.get("role").and_then(Node::as_str).unwrap_or("llm");
            let role = ROLES.iter().find(|r| **r == written).copied().unwrap_or("llm");
            let mut roles = vec![role];
            if WORDS.contains(&role) && role != "llm" {
                roles.push("llm");
            }
            out.push(Reach { field: "model", id: m, roles, carries: None });
        }
    }

    out
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
/// `local` is every model id served on this machine, `offer` a locally-served id
/// to write instead, and `known` every id this tree could possibly mean — an id
/// in none of them is a TYPO, and `schema/no-such-name` reports it with the right
/// message and the right fix. Saying it "is only served off this machine" as
/// well is a confident false statement about a model that exists nowhere.
pub fn refusals(
    root: &Node,
    local: &BTreeSet<String>,
    offer: &str,
    known: &BTreeSet<String>,
    diags: &mut Diagnostics,
) {
    let written = listed(root);
    let off_box = |node: &Node| {
        node.as_str()
            .is_some_and(|id| !id.is_empty() && !local.contains(id) && known.contains(id))
    };

    for reach in reaches(root, &off_box) {
        let Some(id) = reach.id.as_str() else { continue };
        if !off_box(reach.id) {
            continue;
        }
        if reach.roles.iter().any(|r| admits(root, r)) {
            continue;
        }
        let Reach { field, roles, carries, .. } = &reach;
        let message = match carries {
            None => format!(
                "`{field}: {id}` is only served off this machine, and this workspace \
                 says `allow-egress: {written}` — nothing there lets {} talk to \
                 anything outside the box.",
                part(roles[0])
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
