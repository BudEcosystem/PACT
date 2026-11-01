//! **An agent people talk to out loud** (96 §A6).
//!
//! `voice:` is the strategy half of a voice agent; the contract half —
//! `accepts: audio`, `answers-with: audio`, `limits.feel: voice` — was already
//! writable. What only a check can say is whether the lines of the strategy
//! agree with each other and with the catalogue rows of the models they name.
//! The kind of each model is `modelkinds.rs`'s; everything else is here.
//!
//! | Rule | Fires when |
//! |---|---|
//! | `loader/talking-over-a-pipeline` | `talking: both-at-once` with `pipeline: transcribe-think-speak` — three models in a row cannot listen while they speak |
//! | `loader/one-model-and-three` | `pipeline: one-speech-model` beside `hears-with:` or `speaks-with:`, which name the other pipeline's models |
//! | `loader/a-voice-the-speaker-does-not-have` | `speaks-as:` is not one of the `voices:` the speaking model's row lists |
//! | `loader/a-language-it-cannot-handle` | a `languages:` tag the listening or speaking model's row does not list |
//! | `loader/a-voice-nobody-hears` (warning) | `voice:` on an agent that neither takes nor gives audio |
//!
//! A catalogue row that lists no voices or no languages is not judged: an
//! unrecorded figure is unknown, never "none" (Y12), and refusing on it would
//! empty the choice the author is about to make.

use crate::modelkinds::{self, Row};
use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::Node;
use std::collections::BTreeMap;

/// The spellings of the `audio` answer shape (`workspace.shapes` in the
/// specification), as `egress.rs` reads them.
const AUDIO: &[&str] = &["audio", "a recording", "a voice message", "list of audio"];

pub fn check(document: &Node, builtin: &str, diags: &mut Diagnostics) {
    let Some(agents) = document.get("agents").and_then(Node::as_map) else {
        return;
    };
    let rows = modelkinds::catalogue(builtin, document);
    for (name, entry) in agents {
        let Some(voice) = entry.node.get("voice") else {
            continue;
        };
        if voice.as_map().is_none() {
            continue;
        }
        one_agent(name, &entry.node, voice, &rows, diags);
    }
}

fn word<'a>(voice: &'a Node, field: &str) -> Option<&'a str> {
    voice.get(field).and_then(Node::as_str).map(str::trim)
}

fn at(voice: &Node, field: &str) -> Span {
    voice
        .as_map()
        .and_then(|m| m.get(field))
        .map(|e| e.key_span.clone().merge(&e.node.span))
        .unwrap_or_else(|| voice.span.clone())
}

fn one_agent(
    name: &str,
    agent: &Node,
    voice: &Node,
    rows: &BTreeMap<String, Row>,
    diags: &mut Diagnostics,
) {
    let pipeline = word(voice, "pipeline");
    if word(voice, "talking") == Some("both-at-once") && pipeline == Some("transcribe-think-speak")
    {
        diags.push(Diagnostic::error(
            "loader/talking-over-a-pipeline",
            at(voice, "talking"),
            format!(
                "'{name}' is to talk while it is being talked to, and it listens, thinks and \
                 speaks with three models in a row — none of them hears anything while the \
                 last one is speaking."
            ),
            "Write `pipeline: one-speech-model`, or `talking: takes-turns`.",
        ));
    }
    if pipeline == Some("one-speech-model") {
        for field in ["hears-with", "speaks-with"] {
            if voice.get(field).is_some() {
                diags.push(Diagnostic::error(
                    "loader/one-model-and-three",
                    at(voice, field),
                    format!(
                        "'{name}' hears and speaks with one model, and `{field}:` names a \
                         separate model for one half of that — which only the other \
                         pipeline uses."
                    ),
                    format!(
                        "Take the `{field}:` line out, or write `pipeline: \
                         transcribe-think-speak`."
                    ),
                ));
            }
        }
    }
    let speaker = word(voice, "speaks-with").and_then(|id| rows.get(id));
    if let (Some(said), Some(row)) = (word(voice, "speaks-as"), speaker)
        && !row.voices.is_empty()
        && !row.voices.iter().any(|v| v == said)
    {
        diags.push(Diagnostic::error(
            "loader/a-voice-the-speaker-does-not-have",
            at(voice, "speaks-as"),
            format!(
                "'{name}' speaks as '{said}', and '{}' has no voice by that name.",
                row.name
            ),
            format!("Use one of its voices: {}.", row.voices.join(", ")),
        ));
    }
    let tags: Vec<&str> = voice
        .get("languages")
        .map(crate::workflows::list)
        .into_iter()
        .flatten()
        .filter_map(Node::as_str)
        .map(str::trim)
        .collect();
    for field in ["hears-with", "speaks-with"] {
        let Some(row) = word(voice, field).and_then(|id| rows.get(id)) else {
            continue;
        };
        if row.languages.is_empty() {
            continue;
        }
        for tag in &tags {
            if !row.languages.iter().any(|l| covers(l, tag)) {
                diags.push(Diagnostic::error(
                    "loader/a-language-it-cannot-handle",
                    at(voice, "languages"),
                    format!(
                        "'{name}' is spoken to in '{tag}', and '{}', which `{field}:` names, \
                         does not handle it.",
                        row.name
                    ),
                    format!(
                        "Name a model that handles '{tag}', or take it off `languages:`. \
                         '{}' handles: {}.",
                        row.name,
                        row.languages.join(", ")
                    ),
                ));
            }
        }
    }
    let takes_audio = ["accepts", "answers-with", "run-inputs"]
        .iter()
        .filter_map(|block| agent.get(block).and_then(Node::as_map))
        .flat_map(|m| m.values())
        .filter_map(|e| e.node.as_str())
        .any(is_audio);
    if !takes_audio {
        diags.push(Diagnostic::warning(
            "loader/a-voice-nobody-hears",
            at(voice, "pipeline").merge(&voice.span),
            format!(
                "'{name}' says how it listens and speaks, and nothing it `accepts:` or \
                 `answers-with:` is audio — so nothing ever reaches it to be heard."
            ),
            "Write `accepts: {message: audio}` and `answers-with: {reply: audio}`, or take \
             the `voice:` block out.",
        ));
    }
}

/// `en` covers `en-GB`; `en-GB` covers only itself.
fn covers(listed: &str, asked: &str) -> bool {
    let (listed, asked) = (listed.to_ascii_lowercase(), asked.to_ascii_lowercase());
    asked == listed || asked.starts_with(&format!("{listed}-"))
}

fn is_audio(shape: &str) -> bool {
    let s = shape.trim().to_ascii_lowercase();
    let s = s.strip_suffix(", optional").unwrap_or(&s).trim();
    AUDIO.contains(&s)
        || s.strip_prefix("list of ")
            .is_some_and(|r| AUDIO.contains(&r.trim()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_language_covers_its_regions_and_not_the_other_way_round() {
        assert!(covers("en", "en-GB"));
        assert!(covers("en-GB", "en-gb"));
        assert!(!covers("en-GB", "en"));
        assert!(!covers("en", "eng"));
    }

    #[test]
    fn every_spelling_of_audio_is_audio() {
        assert!(is_audio("audio"));
        assert!(is_audio("a voice message, optional"));
        assert!(is_audio("list of audio"));
        assert!(!is_audio("text"));
    }
}
