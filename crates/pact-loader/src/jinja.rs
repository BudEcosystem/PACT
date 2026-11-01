//! **`template-language: jinja`** (96 §C): an agent's words that choose and
//! repeat, held to a dialect both ports can render the same way.
//!
//! `holes` (`{{run-inputs.<name>}}` and nothing else) stays the default and
//! the no-code path. A workspace that writes `template-language: jinja` gets
//! `{% if %}`, `{% for %}`, comparisons, `and`/`or`/`not`, and a short list of
//! filters — and nothing that reaches outside the text:
//!
//! * **No includes, imports, `extends`, blocks or macros.** A template is one
//!   field's words; a second file pulled in at render time is a second thing
//!   the review did not read.
//! * **No function or method calls.** `range()`, `namespace()`, `.upper()` and
//!   friends are where Jinja2 (Python) and MiniJinja (Rust) differ, and where
//!   a sandbox escape starts.
//! * **Only the filters and tests both engines implement with one meaning**
//!   ([`FILTERS`], [`TESTS`]) — checked by name, so a filter one port lacks is
//!   refused here rather than failing at render time in one runtime only.
//! * **Names are what the agent declares**, written with `_` where PACT writes
//!   `-` — `run_inputs.brand_voice` — because `run-inputs.brand` is
//!   *subtraction* in Jinja. Two names that become the same with `_` are
//!   refused.
//! * **A picture is never put into words.** A run input that is an image, a
//!   recording or a document is attached to a turn; it cannot be printed.
//!
//! What a template is filled with is DATA. A runtime renders the authored text
//! once and never renders what it inserted — so a customer who types
//! `{{ 7*7 }}` into a run input gets those characters, not 49 (the template-
//! injection hole every Jinja deployment has to close).
//!
//! | Rule | Fires when |
//! |---|---|
//! | `loader/a-template-that-does-not-read` | the text is not a template MiniJinja can read |
//! | `loader/a-hole-written-for-the-other-language` | `{{run-inputs.x}}` in a `jinja` workspace |
//! | `loader/a-filter-only-one-port-has` | a filter or test outside the shared list |
//! | `loader/a-template-that-reaches-outside` | an include, import, block, macro, call or capture |
//! | `loader/a-name-a-template-cannot-reach` | a name that is not `run_inputs.<x>`, `remembers.<x>` or a loop's own |
//! | `loader/no-such-run-input`, `loader/no-such-remembered-fact` | the name after the dot is not declared |
//! | `loader/a-picture-in-the-words` | the name is a run input of a kind that cannot be printed |
//! | `loader/two-names-one-template-name` | two declared names become one with `_` for `-` |

use minijinja::machinery::{Instruction, get_compiled_template};
use pact_diag::{Diagnostic, Diagnostics, Span};
use std::collections::{BTreeMap, BTreeSet};

/// Filters Jinja2 3.1 and MiniJinja 2.21 both ship, with one meaning.
pub const FILTERS: &[&str] = &[
    "abs",
    "capitalize",
    "count",
    "d",
    "default",
    "first",
    "float",
    "indent",
    "int",
    "items",
    "join",
    "last",
    "length",
    "list",
    "lower",
    "max",
    "min",
    "replace",
    "reverse",
    "round",
    "sort",
    "string",
    "sum",
    "title",
    "trim",
    "unique",
    "upper",
];

/// Tests both engines ship, with one meaning.
pub const TESTS: &[&str] = &[
    "defined",
    "undefined",
    "none",
    "number",
    "string",
    "sequence",
    "mapping",
    "even",
    "odd",
];

/// Shapes whose value is a reference to a file, not words.
const UNPRINTABLE: &[&str] = &[
    "images",
    "a picture",
    "pictures",
    "an image",
    "list of images",
    "audio",
    "a recording",
    "a voice message",
    "list of audio",
    "documents",
    "a pdf",
    "list of documents",
    "video",
    "a video",
    "a clip",
    "list of videos",
    "file",
    "a file",
    "an attachment",
    "list of files",
];

/// Tags that reach another file or define code: refused by name.
const REACHING_TAGS: &[&str] = &[
    "include", "import", "from", "extends", "block", "macro", "call",
];

/// The text of the first `{% <tag>` in `text`, however it is spaced.
fn tagged(text: &str, tag: &str) -> Option<String> {
    let mut from = 0;
    while let Some(open) = text[from..].find("{%").map(|i| from + i) {
        let rest = text[open + 2..].trim_start_matches(['-', '+']).trim_start();
        let word: String = rest
            .chars()
            .take_while(|c| c.is_ascii_alphabetic())
            .collect();
        if word == tag {
            return Some(text[open..].chars().take(2 + tag.len() + 2).collect());
        }
        from = open + 2;
    }
    None
}

/// A PACT name as a template writes it.
pub fn template_name(name: &str) -> String {
    name.replace('-', "_")
}

/// What one agent's templates may name: run inputs (with their shapes) and
/// remembered facts, each under the name a template writes.
pub struct Scope {
    inputs: BTreeMap<String, (String, String)>,
    remembered: BTreeMap<String, String>,
}

impl Scope {
    /// Build the scope, refusing two names that become one.
    pub fn of(
        agent: &str,
        inputs: &BTreeMap<String, String>,
        remembered: &BTreeSet<String>,
        at: &Span,
        diags: &mut Diagnostics,
    ) -> Self {
        let mut scope = Scope {
            inputs: BTreeMap::new(),
            remembered: BTreeMap::new(),
        };
        for (name, shape) in inputs {
            let written = template_name(name);
            if let Some((other, _)) = scope.inputs.get(&written) {
                collision(agent, "run input", other, name, &written, at, diags);
            }
            scope.inputs.insert(written, (name.clone(), shape.clone()));
        }
        for name in remembered {
            let written = template_name(name);
            if let Some(other) = scope.remembered.get(&written) {
                collision(agent, "remembered fact", other, name, &written, at, diags);
            }
            scope.remembered.insert(written, name.clone());
        }
        scope
    }
}

fn collision(
    agent: &str,
    noun: &str,
    one: &str,
    other: &str,
    written: &str,
    at: &Span,
    diags: &mut Diagnostics,
) {
    diags.push(Diagnostic::error(
        "loader/two-names-one-template-name",
        at.clone(),
        format!(
            "`{agent}` has a {noun} '{one}' and a {noun} '{other}', and a template writes both \
             as `{written}` — so it cannot say which it means."
        ),
        format!("Rename one of them in `{agent}`."),
    ));
}

/// The span of the first place `needle` appears in `text`, moved down from the
/// value's own position by the lines before it.
fn near(span: &Span, text: &str, needle: &str) -> Span {
    let Some(i) = text.find(needle) else {
        return span.clone();
    };
    let down = text[..i].matches('\n').count();
    Span::new(
        span.file.clone(),
        span.line + down,
        if down == 0 { span.col } else { 1 },
        span.byte_start,
        span.byte_end,
    )
}

fn on_line(span: &Span, line: Option<usize>) -> Span {
    match line {
        Some(n) if n > 0 => Span::new(
            span.file.clone(),
            span.line + n - 1,
            if n == 1 { span.col } else { 1 },
            span.byte_start,
            span.byte_end,
        ),
        _ => span.clone(),
    }
}

/// Every problem with one text written as a template.
pub fn check(
    agent: &str,
    field: &str,
    text: &str,
    span: &Span,
    scope: &Scope,
    diags: &mut Diagnostics,
) {
    // The other language's hole, which Jinja reads as `run - inputs.x`.
    if let Some(at) = text.find("run-inputs.") {
        let before = text[..at].trim_end();
        if before.ends_with("{{") || before.ends_with("{%") || before.contains("{{") {
            let name: String = text[at + "run-inputs.".len()..]
                .chars()
                .take_while(|c| c.is_ascii_alphanumeric() || matches!(c, '-' | '_'))
                .collect();
            diags.push(Diagnostic::error(
                "loader/a-hole-written-for-the-other-language",
                near(span, text, "run-inputs."),
                format!(
                    "`{agent}`'s `{field}:` writes `run-inputs.{name}`, and this workspace's \
                     templates are Jinja, where `run-inputs` reads as `run` minus `inputs`."
                ),
                format!(
                    "Write `{{{{ run_inputs.{} }}}}` — `_` where PACT writes `-`.",
                    template_name(&name)
                ),
            ));
            return;
        }
    }
    // The tags that pull in another file or define code. The checker is built
    // without MiniJinja's `multi_template` and `macros` features, so these do
    // not even parse — named here first, so the author is told what the tag
    // does rather than that the text is broken.
    for tag in REACHING_TAGS {
        if let Some(found) = tagged(text, tag) {
            diags.push(Diagnostic::error(
                "loader/a-template-that-reaches-outside",
                near(span, text, &found),
                format!(
                    "`{agent}`'s `{field}:` uses `{{% {tag} %}}`, which this workspace's \
                     templates do not have: a template is the words of one field, and pulls in \
                     nothing a review did not read."
                ),
                "Write the words out here, or move shared words into a skill the agent reads.",
            ));
            return;
        }
    }
    let env = minijinja::Environment::empty();
    let template = match env.template_from_str(text) {
        Ok(t) => t,
        Err(e) => {
            diags.push(Diagnostic::error(
                "loader/a-template-that-does-not-read",
                on_line(span, e.line()),
                format!(
                    "`{agent}`'s `{field}:` is not a template that can be read: {}.",
                    e.detail().unwrap_or("it stops part-way")
                ),
                "Close every `{% if %}` with `{% endif %}` and every `{% for %}` with \
                 `{% endfor %}`, and every `{{` with `}}`. For braces the model is meant to \
                 read, write `{% raw %}{{ ... }}{% endraw %}`.",
            ));
            return;
        }
    };
    let compiled = get_compiled_template(&template);
    let instructions = &compiled.instructions;
    // A function's name is also a name nobody declared; it is told once, as
    // the call it is.
    let mut called: BTreeSet<&str> = BTreeSet::new();
    for i in 0..instructions.len() as u32 {
        let Some(instruction) = instructions.get(i) else {
            continue;
        };
        let at = || on_line(span, instructions.get_line(i));
        let outside = |what: String| -> Diagnostic {
            Diagnostic::error(
                "loader/a-template-that-reaches-outside",
                at(),
                format!(
                    "`{agent}`'s `{field}:` uses {what}, which this workspace's templates do \
                     not have: a template is the words of one field, and fills in only what \
                     the agent declares."
                ),
                "Use `{% if %}`, `{% for %}`, `{% set %}`, comparisons and the filters \
                 PACT lists — or move shared words into a skill the agent reads.",
            )
        };
        match instruction {
            Instruction::ApplyFilter(name, ..) if !FILTERS.contains(name) => {
                diags.push(only_one_port(agent, field, "filter", name, FILTERS, at()));
            }
            Instruction::PerformTest(name, ..) if !TESTS.contains(name) => {
                diags.push(only_one_port(agent, field, "test", name, TESTS, at()));
            }
            Instruction::CallFunction(name, _) => {
                called.insert(name);
                diags.push(outside(format!("the function `{name}()`")));
            }
            Instruction::CallMethod(name, _) => {
                diags.push(outside(format!("the method `.{name}()`")));
            }
            Instruction::CallObject(_) => diags.push(outside("a call".to_string())),
            Instruction::BeginCapture(_) => {
                diags.push(outside(
                    "a `{% filter %}` or `{% set %}…{% endset %}` block".into(),
                ));
            }
            Instruction::PushAutoEscape => {
                diags.push(outside("`{% autoescape %}`".to_string()));
            }
            Instruction::FastRecurse => diags.push(outside("a recursive loop".to_string())),
            _ => {}
        }
    }
    let mut names: Vec<String> = template.undeclared_variables(true).into_iter().collect();
    names.sort();
    for name in names {
        let (root, rest) = name.split_once('.').unwrap_or((name.as_str(), ""));
        let first = rest.split('.').next().unwrap_or("");
        let at = near(span, text, root);
        match root {
            "loop" => {}
            _ if called.contains(root) => {}
            "run_inputs" | "remembers" if first.is_empty() => {
                diags.push(Diagnostic::error(
                    "loader/a-name-a-template-cannot-reach",
                    at,
                    format!(
                        "`{agent}`'s `{field}:` reads all of `{root}` at once, which prints \
                         every value it holds — including ones written for somebody else."
                    ),
                    format!("Name the one it needs: `{{{{ {root}.<name> }}}}`."),
                ));
            }
            "run_inputs" => match scope.inputs.get(first) {
                None => diags.push(missing(
                    agent,
                    field,
                    "run input",
                    root,
                    first,
                    at,
                    scope.inputs.keys(),
                    "loader/no-such-run-input",
                )),
                Some((declared, shape)) if unprintable(shape) => {
                    diags.push(Diagnostic::error(
                        "loader/a-picture-in-the-words",
                        at,
                        format!(
                            "`{agent}`'s `{field}:` prints `run_inputs.{first}`, and '{declared}' \
                             is `{shape}` — something to look at or listen to, which cannot be \
                             put into words."
                        ),
                        format!(
                            "Attach it to a turn instead: `attaches: [run-inputs.{declared}]`."
                        ),
                    ));
                }
                Some(_) => {}
            },
            "remembers" => {
                if !scope.remembered.contains_key(first) {
                    diags.push(missing(
                        agent,
                        field,
                        "remembered fact",
                        root,
                        first,
                        at,
                        scope.remembered.keys(),
                        "loader/no-such-remembered-fact",
                    ));
                }
            }
            _ => diags.push(Diagnostic::error(
                "loader/a-name-a-template-cannot-reach",
                at,
                format!(
                    "`{agent}`'s `{field}:` reads `{root}`, which is not something a template \
                     can be given — nothing would fill it when a run starts."
                ),
                "A template reads `run_inputs.<name>` and `remembers.<name>`, and the names its \
                 own `{% for %}` and `{% set %}` make."
                    .to_string(),
            )),
        }
    }
}

fn only_one_port(
    agent: &str,
    field: &str,
    noun: &str,
    name: &str,
    allowed: &[&str],
    at: Span,
) -> Diagnostic {
    Diagnostic::error(
        "loader/a-filter-only-one-port-has",
        at,
        format!(
            "`{agent}`'s `{field}:` uses the {noun} `{name}`, which is not one both runtimes \
             render the same way — the same words could come out differently, or not at all, \
             depending on which one runs them."
        ),
        format!("Use one of: {}.", allowed.join(", ")),
    )
}

#[allow(clippy::too_many_arguments)]
fn missing<'a>(
    agent: &str,
    field: &str,
    noun: &str,
    root: &str,
    name: &str,
    at: Span,
    known: impl Iterator<Item = &'a String>,
    rule: &'static str,
) -> Diagnostic {
    let known: Vec<String> = known.map(|k| format!("`{root}.{k}`")).collect();
    Diagnostic::error(
        rule,
        at,
        format!(
            "`{agent}`'s `{field}:` reads `{root}.{name}`, and `{agent}` declares no {noun} \
             called that — so there is nothing to fill it with when a run starts."
        ),
        if known.is_empty() {
            format!("Declare it in `{agent}`, or take it out.")
        } else {
            format!("Change it to one of: {}.", known.join(", "))
        },
    )
}

fn unprintable(shape: &str) -> bool {
    let s = shape.trim().to_ascii_lowercase();
    let s = s.strip_suffix(", optional").unwrap_or(&s).trim();
    UNPRINTABLE.contains(&s)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn run(text: &str) -> Vec<String> {
        let mut diags = Diagnostics::new();
        let span = Span::new("t.yaml", 1, 1, 0, 0);
        let inputs: BTreeMap<String, String> = [
            ("brand-voice".to_string(), "text".to_string()),
            ("tier".to_string(), "one of gold, silver".to_string()),
            ("photo".to_string(), "images".to_string()),
        ]
        .into_iter()
        .collect();
        let remembered: BTreeSet<String> = ["notes".to_string()].into_iter().collect();
        let scope = Scope::of("desk", &inputs, &remembered, &span, &mut diags);
        check("desk", "instructions", text, &span, &scope, &mut diags);
        diags.items().iter().map(|d| d.rule.to_string()).collect()
    }

    #[test]
    fn the_shared_dialect_reads_clean() {
        let ok = "{% if run_inputs.tier == 'gold' %}Be generous.{% endif %}\n\
                  Speak as {{ run_inputs.brand_voice | default('us') | upper }}.\n\
                  {% for n in remembers.notes %}- {{ loop.index }}. {{ n }}\n{% endfor %}";
        assert_eq!(run(ok), Vec::<String>::new());
    }

    #[test]
    fn each_way_out_of_the_dialect_is_named() {
        assert_eq!(
            run("{{ run_inputs.tier | tojson }}"),
            ["loader/a-filter-only-one-port-has"]
        );
        assert_eq!(
            run("{% include 'x' %}"),
            ["loader/a-template-that-reaches-outside"]
        );
        assert_eq!(
            run("{{ range(3) }}"),
            ["loader/a-template-that-reaches-outside"]
        );
        assert_eq!(run("{{ run_inputs.nope }}"), ["loader/no-such-run-input"]);
        assert_eq!(
            run("{{ run_inputs.photo }}"),
            ["loader/a-picture-in-the-words"]
        );
        assert_eq!(
            run("{{ run_inputs }}"),
            ["loader/a-name-a-template-cannot-reach"]
        );
        assert_eq!(
            run("{{ secrets.key }}"),
            ["loader/a-name-a-template-cannot-reach"]
        );
        assert_eq!(run("{% if x %}"), ["loader/a-template-that-does-not-read"]);
        assert_eq!(
            run("{{run-inputs.tier}}"),
            ["loader/a-hole-written-for-the-other-language"]
        );
    }
}
