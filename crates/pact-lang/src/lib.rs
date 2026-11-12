//! **The PACT language** (`docs/99-THE-PACT-LANGUAGE.md` §4): one `.pact` file
//! that says what a workspace folder says.
//!
//! This crate is a second way of WRITING a workspace and nothing else. It has
//! no rules of its own about what a workspace may contain: [`read`] turns text
//! into the same spanned [`pact_doc::Node`] the YAML reader produces, and every
//! check `pact check` makes is made on that document afterwards — by the same
//! code, pointing at the line of the `.pact` file the author wrote.
//!
//! # The shape of a file
//!
//! A file is a list of **blocks**: a header at the left margin and an indented
//! body. A body line is one of three things.
//!
//! - A **setting**, `key: value`, with anything YAML allows beneath it. It is
//!   handed to the YAML reader as it stands, so every field of the
//!   specification is writable and nothing here has to know its name.
//! - A **sentence**, starting with one of a short list of words — `uses
//!   zendesk, payments`, `asks finance-desk: …`, `when the work touches
//!   finance`. Each stands for a fixed field or two (see [`read`]).
//! - A **text block**, a field's name alone on a line with text indented
//!   beneath it, for writing that runs to several lines.
//!
//! # The two directions agree by construction
//!
//! [`write()`] prints any document as a `.pact` file, and reading what it
//! printed gives the document back. That is not held by a table of fields. The
//! printer writes each block, reads its own text back, and compares; a block
//! that does not come back identical is written again more plainly, ending at
//! settings with every string quoted — a form that can say anything. So a
//! field this crate has never heard of round-trips on the day it is added to
//! `spec/schema.yaml`.

mod emit;
pub mod read;
pub mod write;

pub use read::{Parsed, read};
pub use write::{Written, write};

/// The file extension a PACT-language file has.
pub const EXTENSION: &str = "pact";

/// Every collection of a workspace, as `(header word, workspace field)`.
///
/// `agent refund-desk` is one entry of `agents:`. Written down here, and held
/// against `spec/schema.yaml` by `every_collection_has_a_header_word` in
/// `crates/pact-cli/tests`, so a collection added to the specification cannot
/// be left without a way to write it as a block — it would still be writable
/// as a setting of the workspace, which is why a missing row is a test failure
/// and not a parse failure.
pub const COLLECTIONS: &[(&str, &str)] = &[
    ("agent", "agents"),
    ("workflow", "workflows"),
    ("shape", "shapes"),
    ("remembers", "remembers"),
    ("detector", "detectors"),
    ("owner", "owners"),
    ("tool", "tools"),
    ("resource", "resources"),
    ("knowledge", "knowledge"),
    ("skill", "skills"),
    ("program", "programs"),
    ("value", "values"),
    ("policy", "policies"),
    ("question", "questions"),
    ("port", "ports"),
    ("loop", "loops"),
    ("context-policy", "context-policies"),
    ("bundle", "bundles"),
    ("interceptor", "interceptors"),
    ("watch", "watch"),
    ("topic", "topics"),
    ("event", "events"),
    ("reaction", "reactions"),
];

/// The workspace fields that are one document each, written as a header with
/// no name: `redaction`, then its settings.
pub const SINGLES: &[&str] = &["release", "redaction", "evals", "learning", "models"];

/// The field a header word stands for.
pub fn collection_of(word: &str) -> Option<&'static str> {
    COLLECTIONS.iter().find(|(w, _)| *w == word).map(|(_, c)| *c)
}

/// The header word a workspace field is written with.
pub fn word_for(collection: &str) -> Option<&'static str> {
    COLLECTIONS
        .iter()
        .find(|(_, c)| *c == collection)
        .map(|(w, _)| *w)
}

/// A name made from a sentence: lower-case words joined by `-`.
///
/// `when the work touches finance` is the reaction
/// `the-work-touches-finance` unless it says `called` something else.
pub fn slug(sentence: &str) -> String {
    let mut out = String::new();
    for c in sentence.chars() {
        if c.is_alphanumeric() {
            out.extend(c.to_lowercase());
        } else if !out.ends_with('-') && !out.is_empty() {
            out.push('-');
        }
    }
    out.trim_end_matches('-').to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_slug_is_the_words_of_the_sentence() {
        assert_eq!(slug("the work touches finance"), "the-work-touches-finance");
        assert_eq!(
            slug("the agent is about to call invoices/send"),
            "the-agent-is-about-to-call-invoices-send"
        );
        assert_eq!(slug("  It's 5 o'clock!  "), "it-s-5-o-clock");
    }

    #[test]
    fn every_header_word_is_written_once() {
        let mut words: Vec<&str> = COLLECTIONS.iter().map(|(w, _)| *w).collect();
        words.extend(SINGLES);
        words.extend(["workspace", "when"]);
        let n = words.len();
        words.sort_unstable();
        words.dedup();
        assert_eq!(n, words.len(), "two headers share a word");
    }
}
