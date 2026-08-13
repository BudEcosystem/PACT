//! The PACT document model: a spanned value tree plus the parsers that build it.
//!
//! Decision D2 makes the file tree the **native, authoritative** form of a PACT
//! agent. `canonical.json` is derived. Everything in this crate therefore
//! optimises for the tree direction: preserve order, preserve provenance, and
//! never lose the information needed to write an edit back to the right line of
//! the right file.

pub mod canonical;
pub mod markdown;
pub mod value;
pub mod yaml;

pub use canonical::{canonical_string, digest};
pub use markdown::{Folded, Markdown, parse_markdown};
pub use value::{Entry, FileRef, Map, Node, Payload, Value};
pub use yaml::{
    Offset, parse_yaml, parse_yaml_at, whole_number_past_holding, whole_number_written,
};

/// The version of the PACT format this build reads and writes.
///
/// **One string, in one place.** `pact.dev/v1` was a bare literal inside
/// `discover.rs` — so the only versioned thing in the system was the discovery
/// index, and a workspace had no way to say which format it was written against.
/// A format that cannot version cannot evolve without breaking every consumer
/// silently, which is register row C1.
///
/// The shape is `pact.dev/vN`. It changes when a document valid under the old
/// version stops being valid, or changes meaning — not when a field is added,
/// because an added field is what `pact check`'s unknown-key refusal already
/// covers.
pub const SPEC_VERSION: &str = "pact.dev/v1";

/// The key a placeholder for an unreadable file carries.
///
/// The loader records a file it could not parse as an empty block wearing this,
/// rather than dropping the name entirely, so that every reference to that
/// document still resolves — one YAML typo used to produce four diagnostics,
/// three of them false and one of them advising the author to create a second
/// copy of the file they had open. The schema reads it as *"say nothing about
/// what is inside this"*, because nothing is known about what is inside it.
///
/// An `x-` prefix so it can never collide with a field somebody writes, and a
/// constant so the two crates cannot spell it differently.
pub const UNLOADED: &str = "x-pact-unloaded";
