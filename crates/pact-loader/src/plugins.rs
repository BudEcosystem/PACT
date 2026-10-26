//! **A plugin is named and never loaded** (D29).
//!
//! `plugins/<name>.yaml` asks whatever runs these agents to load a package for
//! them. PACT reads the request and nothing else: this pass never resolves,
//! downloads or opens a package (R5), and needs no network to say what it says
//! (D17). What it can hold is the request itself, because each half of it has a
//! grammar that is not PACT's and that a runtime will apply later, somewhere the
//! author is not watching:
//!
//! * **`package:` names its registry.** `npm:@acme/crm-tools`, `pypi:acme-crm`.
//!   The word in front is the portability fact — which runtimes can load the
//!   line at all — so a package with no registry, or with one no runtime here
//!   knows how to load from, is refused rather than guessed at.
//! * **`version:` is a range in that registry's own grammar.** npm ranges as
//!   `node-semver` reads them, pypi specifiers as PEP 440 writes them. A range
//!   that only the other registry understands is the commonest slip, and a
//!   runtime meeting it would refuse to install with the author long gone.
//! * **No secret is written in `config:`.** The settings are the plugin's own
//!   and the schema leaves them open, so this is the one rule held inside them:
//!   a key that names a token, a secret, a password or an API key carries
//!   `{by-reference: <name>}`, never the value, as `resource.auth` does.
//!
//! And one note, because a plugin that cannot be loaded and must be there is a
//! portability fact a reviewer should see before a run finds it: every agent
//! such a plugin applies to runs only where its package can be loaded.

use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::{Entry, Map, Node, Value};
use std::str::FromStr;

/// The registries a `package:` may name: the two any shipped runtime has a
/// loader for. A third is a spec change, not an author's choice.
pub const REGISTRIES: [&str; 2] = ["npm", "pypi"];

/// What `if-it-cannot-be-loaded:` means when it is left out.
pub const REFUSE_TO_START: &str = "refuse-to-start";

/// The words a `config:` key is a secret by. Compared against the key's words,
/// so `max-tokens` is a count and `access-token` is a secret.
const SECRET_WORDS: [&str; 3] = ["token", "secret", "password"];

/// The plugins `agent` needs, by name, in name order: the ones its own
/// `plugins:` line names and every one whose `applies-to:` is `every-agent`.
///
/// The one reading of `applies-to:` in the checker, shared with `pact
/// discover`, so the note below and the inventory a runtime indexes can never
/// disagree about which agent a plugin is loaded for.
pub fn needed_by<'a>(document: &'a Node, agent: &Node) -> Vec<(&'a str, &'a Node)> {
    let Some(plugins) = document.get("plugins").and_then(Node::as_map) else {
        return Vec::new();
    };
    let named = names_on(agent);
    let mut out: Vec<(&str, &Node)> = plugins
        .iter()
        .filter(|(name, entry)| named.contains(&name.as_str()) || for_every_agent(&entry.node))
        .map(|(name, entry)| (name.as_str(), &entry.node))
        .collect();
    out.sort_by_key(|(name, _)| *name);
    out
}

/// `if-it-cannot-be-loaded:` as written, or the default when it is not.
pub fn if_it_cannot_be_loaded(plugin: &Node) -> &str {
    plugin
        .get("if-it-cannot-be-loaded")
        .and_then(Node::as_str)
        .map_or(REFUSE_TO_START, str::trim)
}

/// Hold every plugin line to the grammar a runtime will apply to it, and say
/// which agents run only where a required plugin can be loaded.
pub fn check(document: &Node, diags: &mut Diagnostics) {
    let Some(plugins) = document.get("plugins").and_then(Node::as_map) else {
        return;
    };
    for (name, entry) in plugins {
        let Some(fields) = entry.node.as_map() else {
            continue;
        };
        if let Some(config) = fields.get("config") {
            no_secret_in(name, &config.node, diags);
        }
        // A package already refused for its registry has no portability fact to
        // note: the error says what to fix first.
        if let Some(registry) = registry_of(name, fields, diags) {
            version_is_a_range(name, registry, fields, diags);
            runs_only_where_loaded(document, name, entry, diags);
        }
    }
}

/// The registry `package:` names, or `None` after saying why it names none.
fn registry_of<'a>(name: &str, fields: &'a Map, diags: &mut Diagnostics) -> Option<&'a str> {
    let package = fields.get("package")?;
    let written = package.node.as_str()?.trim();
    let registry = written.split_once(':').map(|(r, _)| r.trim());
    if let Some(r) = registry.filter(|r| REGISTRIES.contains(r)) {
        return Some(r);
    }
    let what = match registry {
        Some(r) if !r.is_empty() => {
            format!("names the registry '{r}', which no runtime loads from")
        }
        _ => "names no registry".to_string(),
    };
    diags.push(Diagnostic::error(
        "loader/plugin-package-has-no-registry",
        at(package),
        format!(
            "'{name}' asks for the package '{written}', which {what} — so no runtime can \
             say whether it is one it can load."
        ),
        format!(
            "Write one of the registries a runtime loads from — {} — in front of the name: \
             `npm:{bare}` for an npm package, `pypi:{bare}` for a Python one.",
            REGISTRIES
                .iter()
                .map(|r| format!("`{r}`"))
                .collect::<Vec<_>>()
                .join(" or "),
            bare = written.rsplit_once(':').map_or(written, |(_, n)| n).trim(),
        ),
    ));
    None
}

/// Refuse a `version:` its registry would not read as a range.
fn version_is_a_range(name: &str, registry: &str, fields: &Map, diags: &mut Diagnostics) {
    let Some(version) = fields.get("version") else {
        return;
    };
    let written = match &version.node.value {
        Value::Str(s) => s.trim().to_string(),
        // `version: 1.4` arrives as a number; the schema reports the type, and
        // this pass has nothing further to say about a line that is not text.
        _ => return,
    };
    let (reads, example) = match registry {
        "npm" => (
            nodejs_semver::Range::parse(&written).is_ok(),
            "`^1.4.0` (1.4.0 or any later 1.x), `~1.4.0` (any 1.4.x) or `>=1.4.0 <2.0.0`",
        ),
        _ => (
            pep440_rs::VersionSpecifiers::from_str(&written).is_ok(),
            "`>=1.4,<2` (1.4 or any later 1.x), `~=1.4` or `==1.4.2`",
        ),
    };
    if reads {
        return;
    }
    diags.push(Diagnostic::error(
        "loader/plugin-version-is-not-a-range",
        at(version),
        format!(
            "'{name}' asks for versions '{written}', which {registry} does not read as a \
             range of versions — so a runtime cannot tell which versions will do."
        ),
        format!("Write the range the way {registry} does, for example {example}."),
    ));
}

/// Refuse a secret written into a plugin's own settings, at any depth.
fn no_secret_in(name: &str, node: &Node, diags: &mut Diagnostics) {
    match &node.value {
        Value::Map(map) => {
            for (key, entry) in map {
                if names_a_secret(key) && !by_reference(&entry.node) {
                    diags.push(Diagnostic::error(
                        "loader/plugin-secret-written-in-the-file",
                        entry.key_span.clone().merge(&entry.node.span),
                        format!(
                            "'{name}' writes its `{key}` into the file, and a file in a \
                             workspace is read by everyone who reviews, copies or checks it out."
                        ),
                        format!(
                            "Replace the value with where it is kept: `{key}: {{by-reference: \
                             <the name your platform team publishes for it>}}`."
                        ),
                    ));
                    continue;
                }
                no_secret_in(name, &entry.node, diags);
            }
        }
        Value::List(items) => items.iter().for_each(|i| no_secret_in(name, i, diags)),
        _ => {}
    }
}

/// Whether a settings key names a secret: one of its words is `token`,
/// `secret` or `password`, or two of them are `api` then `key`.
///
/// Words and not substrings, because a plugin's settings are full of counts
/// named after tokens (`max-tokens`), and a rule that refused those would be
/// switched off by the first author it annoyed.
fn names_a_secret(key: &str) -> bool {
    let words = words_of(key);
    words.iter().any(|w| SECRET_WORDS.contains(&w.as_str()))
        || words.windows(2).any(|p| p[0] == "api" && p[1] == "key")
        || words.iter().any(|w| w == "apikey")
}

/// `apiKey`, `api_key`, `API-Key` and `api key` as the same four words.
fn words_of(key: &str) -> Vec<String> {
    let mut words = Vec::new();
    let mut word = String::new();
    let mut previous_lower = false;
    for c in key.chars() {
        if !c.is_alphanumeric() {
            if !word.is_empty() {
                words.push(std::mem::take(&mut word));
            }
            previous_lower = false;
            continue;
        }
        if c.is_uppercase() && previous_lower && !word.is_empty() {
            words.push(std::mem::take(&mut word));
        }
        previous_lower = c.is_lowercase();
        word.extend(c.to_lowercase());
    }
    if !word.is_empty() {
        words.push(word);
    }
    words
}

/// `{by-reference: <name>}` and nothing else: the one shape a secret may take.
fn by_reference(node: &Node) -> bool {
    node.as_map().is_some_and(|m| {
        m.len() == 1
            && m.get("by-reference")
                .and_then(|r| r.node.as_str())
                .is_some_and(|r| !r.trim().is_empty())
    })
}

/// Say which agents a `refuse-to-start` plugin keeps to the runtimes that can
/// load its package. A note, so `--deny-warnings` stays usable on a shipped tree
/// that means it.
fn runs_only_where_loaded(document: &Node, name: &str, entry: &Entry, diags: &mut Diagnostics) {
    if if_it_cannot_be_loaded(&entry.node) != REFUSE_TO_START {
        return;
    }
    let Some(package) = entry.node.get("package").and_then(Node::as_str) else {
        return;
    };
    let agents: Vec<&str> = document
        .get("agents")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
        .filter(|(_, a)| !a.node.get("base").is_some_and(crate::workflows::said_yes))
        .filter(|(_, a)| needed_by(document, &a.node).iter().any(|(n, _)| *n == name))
        .map(|(key, _)| key.as_str())
        .collect();
    if agents.is_empty() {
        return;
    }
    diags.push(Diagnostic::note(
        "loader/plugin-runs-only-where-loaded",
        entry.key_span.clone(),
        format!(
            "{} only where `{}` can be loaded: '{name}' says `refuse-to-start`, so on a \
             runtime that cannot load it {} before the first step.",
            if agents.len() == 1 {
                format!("{} runs", quoted(&agents))
            } else {
                format!("{} run", quoted(&agents))
            },
            package.trim(),
            if agents.len() == 1 {
                "the agent stops"
            } else {
                "each of them stops"
            },
        ),
        format!(
            "Nothing to do if that is what you mean. Write `if-it-cannot-be-loaded: \
             run-without-it` in `plugins/{name}.yaml` for an agent that can do its job \
             without it — every run then says the plugin was not there."
        ),
    ));
}

/// The names an agent's own `plugins:` line writes.
fn names_on(agent: &Node) -> Vec<&str> {
    match agent.get("plugins").map(|p| &p.value) {
        Some(Value::List(items)) => items
            .iter()
            .filter_map(Node::as_str)
            .map(str::trim)
            .collect(),
        Some(Value::Str(s)) => vec![s.trim()],
        _ => Vec::new(),
    }
}

/// Whether a plugin says, on its own line, that it is loaded for every agent.
fn for_every_agent(plugin: &Node) -> bool {
    plugin
        .get("applies-to")
        .and_then(Node::as_str)
        .map(str::trim)
        == Some("every-agent")
}

/// The line the author typed: the key and its value.
fn at(entry: &Entry) -> Span {
    entry.key_span.clone().merge(&entry.node.span)
}

/// `'a'`, `'a' and 'b'`, `'a', 'b' and 'c'`.
fn quoted(names: &[&str]) -> String {
    let q: Vec<String> = names.iter().map(|n| format!("'{n}'")).collect();
    match q.split_last() {
        Some((last, rest)) if !rest.is_empty() => format!("{} and {last}", rest.join(", ")),
        Some((last, _)) => last.clone(),
        None => String::new(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pact_doc::parse_yaml;

    const WORKSPACE: &str = "
agents:
  desk:
    description: Answers.
    instructions: Answer.
    plugins: [web-search]
  clerk:
    description: Files.
    instructions: File.
plugins:
  web-search:
    description: Searches the web.
    package: npm:@acme/web-search
    version: ^0.2.0
    if-it-cannot-be-loaded: run-without-it
    config:
      results-at-most: 5
      max-tokens: 400
      api-key: { by-reference: host/search-key }
";

    fn check_text(text: &str) -> Diagnostics {
        let node = parse_yaml(text, camino::Utf8Path::new("workspace.yaml")).expect("parses");
        let mut d = Diagnostics::new();
        d.add_source("workspace.yaml", text);
        check(&node, &mut d);
        d
    }

    fn rules(d: &Diagnostics) -> Vec<String> {
        d.items().iter().map(|x| x.rule.to_string()).collect()
    }

    #[test]
    fn a_plugin_written_the_way_its_registry_reads_it_is_left_alone() {
        let d = check_text(WORKSPACE);
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn a_package_with_no_registry_or_an_unknown_one_is_refused() {
        for (written, says) in [
            ("\"@acme/web-search\"", "names no registry"),
            ("cargo:web-search", "names the registry 'cargo'"),
        ] {
            let d = check_text(&WORKSPACE.replace("npm:@acme/web-search", written));
            assert_eq!(
                rules(&d),
                ["loader/plugin-package-has-no-registry"],
                "{}",
                d.render()
            );
            let hit = &d.items()[0];
            assert!(hit.message.contains(says), "{}", hit.message);
            assert!(
                hit.fix.contains("`npm:") && hit.fix.contains("`pypi:"),
                "{}",
                hit.fix
            );
        }
    }

    #[test]
    fn a_range_only_the_other_registry_reads_is_refused() {
        let d = check_text(&WORKSPACE.replace("^0.2.0", "\">=0.2,<1\""));
        assert_eq!(
            rules(&d),
            ["loader/plugin-version-is-not-a-range"],
            "{}",
            d.render()
        );
        let pypi = WORKSPACE.replace("npm:@acme/web-search", "pypi:acme-web-search");
        let d = check_text(&pypi);
        assert_eq!(
            rules(&d),
            ["loader/plugin-version-is-not-a-range"],
            "{}",
            d.render()
        );
        assert!(
            d.items()[0].fix.contains(">=1.4,<2"),
            "{}",
            d.items()[0].fix
        );
        let d = check_text(&pypi.replace("^0.2.0", "\">=0.2,<1\""));
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn a_secret_written_into_the_settings_is_refused_wherever_it_sits() {
        for (key, value) in [
            ("api-key", "sk-live-2f9c"),
            ("apiKey", "sk-live-2f9c"),
            ("access-token", "abc"),
            ("client_secret", "abc"),
            ("password", "{ value: hunter2 }"),
        ] {
            let text = WORKSPACE.replace(
                "      api-key: { by-reference: host/search-key }",
                &format!("      nested:\n        {key}: {value}"),
            );
            let d = check_text(&text);
            assert_eq!(
                rules(&d),
                ["loader/plugin-secret-written-in-the-file"],
                "{key}: {}",
                d.render()
            );
        }
    }

    #[test]
    fn a_count_named_after_tokens_is_not_a_secret() {
        assert!(!names_a_secret("max-tokens"));
        assert!(!names_a_secret("keyboard-layout"));
        assert!(names_a_secret("API_KEY"));
        assert!(names_a_secret("bearerToken"));
    }

    #[test]
    fn a_plugin_an_agent_cannot_start_without_is_a_note_naming_it() {
        let d = check_text(&WORKSPACE.replace("    if-it-cannot-be-loaded: run-without-it\n", ""));
        assert_eq!(
            rules(&d),
            ["loader/plugin-runs-only-where-loaded"],
            "{}",
            d.render()
        );
        let hit = &d.items()[0];
        assert!(
            hit.message.contains("'desk'") && !hit.message.contains("'clerk'"),
            "{}",
            hit.message
        );
        assert!(
            !d.has_errors()
                && d.items()
                    .iter()
                    .all(|x| x.severity == pact_diag::Severity::Note)
        );
    }

    #[test]
    fn every_agent_means_every_agent_that_runs() {
        let text = WORKSPACE
            .replace(
                "    if-it-cannot-be-loaded: run-without-it\n",
                "    applies-to: every-agent\n",
            )
            .replace("    plugins: [web-search]\n", "")
            .replace("  clerk:\n", "  house:\n    base: yes\n  clerk:\n");
        let d = check_text(&text);
        let hit = &d.items()[0];
        assert!(
            hit.message.contains("'desk' and 'clerk'"),
            "{}",
            hit.message
        );
        assert!(!hit.message.contains("'house'"), "{}", hit.message);
    }
}
