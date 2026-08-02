//! `pact` — the command line for the Portable Agent Contract.
//!
//! Two commands exist so far, and both are deliberately read-only:
//!
//! - `pact check [path]` — load the tree and report every problem at once.
//! - `pact show  [path]` — print the loaded document as JSON.
//!
//! Neither ever executes author code. Validation that runs the thing being
//! validated is not validation, it is a supply-chain hazard (D17, D23) — and it
//! is precisely why Eve's build step cannot run air-gapped or unprivileged.

mod discover;
mod egress;
mod suites;

use anyhow::{Result, bail};
use camino::Utf8PathBuf;
use pact_diag::Diagnostics;
use pact_loader::Loader;


const USAGE: &str = "\
pact — Portable Agent Contract

USAGE:
    pact check    [PATH]  Load the agent tree and report any problems
    pact show     [PATH]  Print the loaded document as JSON
    pact waits    [PATH]  Print every wait this tree can produce, with the
                          deadline a runtime must set a timer for (§9.4 G14)
    pact discover [PATH]  Find every PACT workspace under PATH and print an
                          inventory a runtime can index (no build step)
    pact card <agent> [PATH]
                          Print one agent's A2A Agent Card
    pact help             Show this message (also written -h or --help)

PATH defaults to the current directory.

OPTIONS:
    --quiet               Only print problems, not the summary
    --deny-warnings       Fail the run on a warning as well as on a problem. For
                          a pipeline, where a run with warnings and a run
                          without them are the same green tick.
    --unsafe-spec         Validate against $PACT_SPEC instead of the specification
                          compiled into this binary. Development builds only, and
                          the source is named on every run that uses it.
";

/// Every option `pact` accepts, spelled the way it has to be typed.
///
/// One list, not two. [`unknown_options`] refuses anything absent from it and
/// names everything in it, so the refusal a reader sees and the set the parser
/// enforces cannot say different things. The test
/// `every_option_the_usage_advertises_is_one_the_parser_accepts` reads both back
/// out of the real binary and compares them, which is what keeps [`USAGE`]
/// honest about this list rather than merely adjacent to it.
const OPTIONS: &[&str] = &["--quiet", "--unsafe-spec", "--deny-warnings"];

/// What a diagnostic points at when the mistake is in the command rather than in
/// a file.
///
/// The renderer's shape is file, line, column — and a command line fits it
/// without pretending anything: it has exactly one line, and the column is where
/// the mistyped word starts, so the caret lands under it.
const COMMAND_LINE: &str = "the command line";

/// Write to stdout, and end quietly when the reader has gone away.
///
/// `pact show | head -1` used to end in a raw Rust panic — *"thread 'main'
/// panicked at ...: failed printing to stdout: Broken pipe"*, exit 101 — nine
/// times out of sixty on `discover` and intermittently on `show`, because it is
/// a race between the writer and the reader closing. Rust ignores SIGPIPE at
/// startup so that a write to a closed pipe returns an error rather than killing
/// the process, and `println!` then unwraps that error. `| head` is an ordinary
/// thing to type, and the word "panicked" is exactly the raw exception reaching a
/// user the diagnostic bar forbids — no file, no line, no fix.
///
/// Restoring the default signal disposition would need an `unsafe` block, which
/// this crate forbids at the lint level and should. So the write is checked
/// instead, and a closed pipe ends the process the way `cat` ends: silently,
/// successfully, at the moment the reader went away.
macro_rules! out {
    ($($arg:tt)*) => {{
        use std::io::Write;
        let stdout = std::io::stdout();
        let mut lock = stdout.lock();
        if let Err(e) = writeln!(lock, $($arg)*)
            && e.kind() == std::io::ErrorKind::BrokenPipe
        {
            std::process::exit(0);
        }
    }};
}

/// The same, without the newline — for `check`, which renders a block that
/// already ends in one.
macro_rules! out_raw {
    ($($arg:tt)*) => {{
        use std::io::Write;
        let stdout = std::io::stdout();
        let mut lock = stdout.lock();
        if let Err(e) = write!(lock, $($arg)*)
            && e.kind() == std::io::ErrorKind::BrokenPipe
        {
            std::process::exit(0);
        }
    }};
}

fn main() {
    match run() {
        Ok(code) => std::process::exit(code),
        Err(e) => {
            eprintln!("error: {e}");
            std::process::exit(2);
        }
    }
}

/// Whether this is somebody asking what the commands are — answered BEFORE the
/// positional filter below, which is the whole point of it living here.
///
/// The `"help" | "-h" | "--help"` arm used to sit in the `match cmd` further
/// down, and for the `--help` spelling it was dead code: the filter drops every
/// argument starting with a dash, so `pact --help` reached the parser as *no
/// arguments at all* and fell into the `[]` case, which is `check .`. From a
/// repository root holding other checkouts that walk never returns, so the first
/// command a new author types looked like a hang.
///
/// `help` counts only as the first word, so `pact card help .` can still ask for
/// an agent that happens to be called `help`. `-h` and `--help` count anywhere,
/// which is what makes `pact check --help` do the obvious thing.
fn asking_for_help(args: &[String]) -> bool {
    args.first().is_some_and(|a| a == "help") || args.iter().any(|a| a == "-h" || a == "--help")
}

/// An argument meant as an option rather than as a command or a path.
///
/// Any leading dash, not just two. `pact check -q some/path` used to read `-q`
/// as the path and report *"'-q' does not exist"*, which sends the reader
/// looking for a missing folder instead of at the word they mistyped.
fn looks_like_an_option(arg: &str) -> bool {
    arg.starts_with('-')
}

/// The command as the reader typed it, for the line the diagnostic shows back.
///
/// Rebuilt from the word `pact` rather than from the program's own path, which
/// is a build directory under test and an install directory in the wild, and is
/// never what anybody types.
fn as_typed(args: &[String]) -> String {
    std::iter::once("pact")
        .chain(args.iter().map(String::as_str))
        .collect::<Vec<_>>()
        .join(" ")
}

/// The same command with every unrecognised option put right: replaced by the
/// nearest real option where there is one, removed where there is not.
///
/// The fix has to be *typeable* (O7.3), and the most typeable form of "you meant
/// `--quiet`" is the whole line, ready to paste.
fn corrected(args: &[String]) -> String {
    let mut out = vec!["pact".to_string()];
    for a in args {
        if looks_like_an_option(a) && !OPTIONS.contains(&a.as_str()) {
            if let Some(near) = pact_schema::suggest::closest(a, OPTIONS) {
                out.push(near.to_string());
            }
        } else {
            out.push(a.clone());
        }
    }
    out.join(" ")
}

/// The options that do exist, named. "That is not an option" without the list is
/// a dead end for a reader who has no other way to find out what is.
fn options_sentence() -> String {
    match OPTIONS {
        [] => "`pact` takes no options at all.".to_string(),
        [only] => format!("The only option `pact` takes is `{only}`."),
        many => format!(
            "The options `pact` takes are {}.",
            many.iter().map(|o| format!("`{o}`")).collect::<Vec<_>>().join(", ")
        ),
    }
}

/// Refuse an option `pact` does not have, rather than dropping it on the floor.
///
/// Everything except `--quiet` was discarded by the positional filter, so
/// `pact check --quite examples/refund-desk` printed the summary it had just
/// been asked to suppress and never mentioned the typo. PACT refuses a misspelt
/// *field* by exact name and offers the nearest real one
/// (`schema/unknown-field`) — that is the bar the whole project is held to, and
/// the command line of the tool doing the refusing was the one surface exempt
/// from it.
///
/// Every unrecognised option is reported, not just the first, for the same
/// reason `check` reports every problem in a tree at once: a reader who fixes
/// one and is then told about the next learns to run the command twice.
fn unknown_options(args: &[String]) -> Diagnostics {
    let mut diags = Diagnostics::new();
    diags.add_source(COMMAND_LINE, as_typed(args));

    // Where each argument starts in the line above, counted rather than searched
    // for, so the caret still lands on the right word when one option is a
    // fragment of another.
    let mut at = "pact".len() + 1;
    for arg in args {
        let start = at;
        at += arg.len() + 1;
        if !looks_like_an_option(arg) || OPTIONS.contains(&arg.as_str()) {
            continue;
        }
        let span = pact_diag::Span::new(COMMAND_LINE, 1, start + 1, start, start + arg.len());
        let fix = match pact_schema::suggest::closest(arg, OPTIONS) {
            Some(real) => {
                format!("Did you mean `{real}`? Type this instead: `{}`", corrected(args))
            }
            None => format!(
                "{} Take `{arg}` off and type this instead: `{}`",
                options_sentence(),
                corrected(args)
            ),
        };
        diags.push(pact_diag::Diagnostic::error(
            "cli/unknown-option",
            span,
            format!("`{arg}` is not something `pact` takes, so nothing was run."),
            fix,
        ));
    }
    diags
}

/// One refusal about the command line itself, rendered the way every other
/// diagnostic is.
///
/// Four CLI errors used to reach the reader as a bare `error: <text>` — no fix,
/// no rule id, no span — which is the one shape `pact-diag`'s own module
/// invariant says is unconstructable: *"a diagnostic without a fix is
/// unconstructable"*. `pact chek` printed a usage dump and `unknown command
/// 'chek'` with no *"did you mean"*, two functions below the one that already
/// suggests the closest option.
fn refuse(rule: &'static str, message: String, fix: String) -> Diagnostics {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let typed = as_typed(&args);
    let mut diags = Diagnostics::new();
    diags.add_source(COMMAND_LINE, typed.clone());
    let span = pact_diag::Span::new(COMMAND_LINE, 1, 1, 0, typed.len());
    diags.push(pact_diag::Diagnostic::error(rule, span, message, fix));
    diags
}

fn run() -> Result<i32> {
    let args: Vec<String> = std::env::args().skip(1).collect();

    // Both of these come first because both decide whether the rest of the line
    // means anything at all.
    if asking_for_help(&args) {
        out_raw!("{USAGE}");
        return Ok(0);
    }
    let refused = unknown_options(&args);
    if !refused.is_empty() {
        // stderr, not stdout: `show`, `waits` and `discover` put machine-readable
        // JSON on stdout, and a command that was never understood must not put
        // anything there. Exit 2 for the same reason `unknown command` does —
        // 1 means the tree has problems, and here the tree was never read.
        eprint!("{}", refused.render());
        return Ok(2);
    }

    let quiet = args.iter().any(|a| a == "--quiet");
    // The only way to use a specification other than the compiled-in one, and it
    // has to be typed out. `$PACT_SPEC` alone used to be enough, so a variable
    // somebody else exported quietly decided what the governance columns said.
    let unsafe_spec = args.iter().any(|a| a == "--unsafe-spec");
    // For a pipeline, where "loaded with 3 warning(s)" and "loaded cleanly" are
    // the same green tick and nobody reads either. Sequenced a phase after the
    // warnings themselves were made FIXABLE, because a flag that turns an
    // unfixable warning into a build failure is worse than no flag: measured,
    // `loader/never-offered` used to offer a fix that was itself refused when
    // typed, and this would have made that a wall.
    let deny_warnings = args.iter().any(|a| a == "--deny-warnings");
    let positional: Vec<&String> = args.iter().filter(|a| !looks_like_an_option(a)).collect();

    // Typing just `pact` is the first thing a new author does, and it used to
    // mean `check .`. From a repository root holding other checkouts that walk
    // does not return — measured at four minutes and still going, descending
    // into `research/repos` — so the first command anybody types looked like a
    // hang. A reader who typed nothing has asked what the commands are.
    if positional.is_empty() {
        out_raw!("{USAGE}");
        return Ok(0);
    }
    let (cmd, path) = match positional.as_slice() {
        [] => unreachable!("handled above"),
        [c] => (c.as_str(), Utf8PathBuf::from(".")),
        [c, p, ..] => (c.as_str(), Utf8PathBuf::from(p.as_str())),
    };

    match cmd {
        "check" => check(&path, quiet, unsafe_spec, deny_warnings),
        "show" => show(&path, unsafe_spec),
        "waits" => waits_cmd(&path, unsafe_spec),
        "discover" => discover_cmd(&path, unsafe_spec),
        "card" => {
            let agent = positional.get(1).map(|s| s.as_str()).unwrap_or("");
            let root = positional.get(2).map(|s| Utf8PathBuf::from(s.as_str()))
                .unwrap_or_else(|| Utf8PathBuf::from("."));
            card_cmd(agent, &root, unsafe_spec)
        }
        other => {
            // Four command-line refusals used to reach the reader as a bare
            // `error: <text>` with no fix, no rule id and no span — which the
            // invariant at the top of `pact-diag` says is unconstructable. The
            // typo suggestion is the same `suggest::closest` the option refusal
            // two functions up already uses.
            let verbs = ["check", "show", "waits", "discover", "card", "help"];
            let fix = match pact_schema::suggest::closest(other, &verbs) {
                Some(near) => format!("Did you mean `pact {near}`?"),
                None => format!("The commands are: {}.", verbs.join(", ")),
            };
            eprint!(
                "{}",
                refuse(
                    "cli/unknown-command",
                    format!("there is no command called '{other}'."),
                    fix,
                )
                .render()
            );
            Ok(2)
        }
    }
}

fn load(path: &Utf8PathBuf) -> Result<(Option<pact_doc::Node>, Diagnostics)> {
    if !path.exists() {
        bail!("'{path}' does not exist");
    }
    let root = if path.is_dir() { path.clone() } else { path.parent().unwrap_or(path).to_owned() };
    let mut diags = Diagnostics::new();
    let node = Loader::new(root).load(path, &mut diags);
    diags.sort();
    Ok((node, diags))
}

/// The specification shipped with this binary — **the only core schema there
/// is.**
///
/// Embedding it is what makes the CLI work air-gapped and standalone (D17), and
/// compiling it in is also the whole of the governance partition. §8.2's safety
/// argument is that the classification of every field lives *"strictly further
/// outside the search space"* than anything the optimiser can reach, and LOAD-13
/// says the core schema *"is not discovered from the tree at all"*.
///
/// For a round it was discovered from the tree. `find_spec` walked UP from the
/// target to the filesystem root looking for `spec/schema.yaml`, so putting an
/// edited copy one directory above a workspace rewrote the governance class of
/// every field in it: flipping `agent.remembers` from `map of group:state`/S-GOV
/// to `map of anything`/S-GEN made a `remembers:` block with no `lasts:` and an
/// unknown field print *"OK — loaded cleanly"* and exit 0, where the same tree
/// without the parent file produced two errors. Anything with write access to
/// any ancestor directory could do it, and the output never named which
/// specification had been used.
const BUILTIN_SPEC: &str = include_str!("../../../spec/schema.yaml");

/// The digest of the specification actually in force, over its canonical form.
///
/// The schema's header says its sha256 is verified. What is worth verifying is
/// not that the binary agrees with itself — a constant compiled in beside the
/// file it hashes can only ever agree — but that the specification a run used is
/// one a reader can identify. So the digest is COMPUTED and REPORTED: `pact
/// check` prints it whenever the schema did not come from the built-in copy, and
/// [`governance_is_complete`] is the property §8.2 actually depends on.
fn spec_digest(text: &str) -> String {
    match pact_doc::parse_yaml(text, camino::Utf8Path::new("spec/schema.yaml")) {
        Ok(doc) => pact_doc::digest(&doc),
        Err(_) => "unreadable".to_string(),
    }
}

/// Every field of the specification in force carries a governance class.
///
/// This is the invariant §8.2's safety argument rests on: the zone a field lives
/// in is a lookup into `surface:` and `tier:`, and LOAD-12 says a field missing
/// either is BR-UNKNOWN → GOVERNED → CLASS-4. A specification with fields
/// carrying neither does not fail closed — it fails *silently*, because nothing
/// was ever asked. Checked at startup rather than in a test, because a
/// specification supplied from outside the binary is exactly the one no test ran
/// against.
fn governance_is_complete(text: &str) -> Vec<String> {
    let mut missing = Vec::new();
    let Ok(doc) = pact_doc::parse_yaml(text, camino::Utf8Path::new("spec/schema.yaml")) else {
        return missing;
    };
    let Some(groups) = doc.get("groups").and_then(pact_doc::Node::as_map) else {
        return missing;
    };
    for (kind, entry) in groups {
        let Some(fields) = entry.node.get("fields").and_then(pact_doc::Node::as_map) else {
            continue;
        };
        for (name, f) in fields {
            // The short form (`instructions: text`) is a field with no block at
            // all, so it carries neither — and there are none in the shipped
            // schema, which is what makes this checkable rather than aspirational.
            let has = |k: &str| f.node.get(k).and_then(pact_doc::Node::as_str).is_some();
            if !has("surface") || !has("tier") {
                missing.push(format!("{kind}.{name}"));
            }
        }
    }
    missing
}

/// The models this distribution knows about, compiled in beside the schema.
///
/// Embedded for the same reason the specification is: `pact check` must resolve
/// `model: qwen2.5-7b-instrukt` on a machine with no network and no PACT
/// checkout (D17). It is still *data* — a workspace's own `models/catalog.yaml`
/// is layered on top, so adding a model is a YAML edit and never a rebuild.
const BUILTIN_CATALOGUE: &str = include_str!("../../../models/catalog.yaml");

/// Every id the catalogue publishes, under its own name and every runtime alias.
///
/// Read straight out of the loaded document rather than through a typed record,
/// because the only question being asked is "is this a name somebody could
/// legitimately write?" — and a catalogue row with a mistake elsewhere in it
/// should still let a correct pin resolve.
fn catalogue_ids(text: &str, from: &str) -> std::collections::BTreeSet<String> {
    let mut ids = std::collections::BTreeSet::new();
    let path = camino::Utf8Path::new(from);
    let Ok(doc) = pact_doc::parse_yaml(text, path) else {
        return ids;
    };
    let Some(rows) = doc.get("models").and_then(pact_doc::Node::as_map) else {
        return ids;
    };
    for (name, entry) in rows {
        ids.insert(name.clone());
        if let Some(list) = entry.node.get("also-known-as").and_then(pact_doc::Node::as_list) {
            ids.extend(list.iter().filter_map(|n| n.as_str().map(str::to_string)));
        }
    }
    ids
}

/// The `pact:models` namespace: what PACT ships, plus what this workspace added.
///
/// Both layers, because the workspace copy is an *override layer* and never a
/// replacement — an author who adds one locally-served model must not thereby
/// un-name the eight the distribution already knows.
fn models_known_here(root: Option<&pact_doc::Node>) -> pact_schema::Known {
    let mut names = catalogue_ids(BUILTIN_CATALOGUE, "models/catalog.yaml");
    if let Some(node) = root.and_then(|r| r.get("models"))
        && let Some(rows) = node.get("models").and_then(pact_doc::Node::as_map)
    {
        for (name, entry) in rows {
            names.insert(name.clone());
            if let Some(list) = entry.node.get("also-known-as").and_then(pact_doc::Node::as_list) {
                names.extend(list.iter().filter_map(|n| n.as_str().map(str::to_string)));
            }
        }
    }
    pact_schema::Known {
        label: "the model catalogue".to_string(),
        add: "add a `{}:` row to `models/catalog.yaml` in this workspace, saying \
              how much it can hold and where that number came from"
            .to_string(),
        names,
    }
}

/// Which of the catalogue's ids are served on this machine.
///
/// Decision Y16 puts egress on the BINDING rather than on the model: a row is
/// air-gappable when some `served-by:` entry says `endpoint: local`. The rule is
/// stated in `models/catalog.yaml`'s own header and in the schema's help for
/// `served-by.endpoint` — *"Anything else means the call leaves the box — which
/// a workspace with nothing in `allow-egress:` will refuse to do"* — and until
/// [`egress_is_allowed`] existed nothing anywhere refused it. An air-gapped
/// workspace could name a hosted summariser and `pact check` said
/// *"OK — loaded cleanly"*.
fn locally_served(text: &str, from: &str) -> std::collections::BTreeSet<String> {
    let mut ids = std::collections::BTreeSet::new();
    let path = camino::Utf8Path::new(from);
    let Ok(doc) = pact_doc::parse_yaml(text, path) else {
        return ids;
    };
    let Some(rows) = doc.get("models").and_then(pact_doc::Node::as_map) else {
        return ids;
    };
    for (name, entry) in rows {
        let local = entry
            .node
            .get("served-by")
            .and_then(pact_doc::Node::as_list)
            .is_some_and(|ways| {
                ways.iter()
                    .any(|w| w.get("endpoint").and_then(pact_doc::Node::as_str) == Some("local"))
            });
        if !local {
            continue;
        }
        ids.insert(name.clone());
        if let Some(list) = entry.node.get("also-known-as").and_then(pact_doc::Node::as_list) {
            ids.extend(list.iter().filter_map(|n| n.as_str().map(str::to_string)));
        }
    }
    ids
}

/// Refuse a model that only answers off this machine, in a workspace that says
/// nothing may leave it.
///
/// Two fields bind a model — `agents.<name>.model` and
/// `context-policies.<name>.summarised-by` — and both went out the same
/// unguarded door. Reproduced before this existed: `examples/refund-desk` says
/// `allow-egress: []`, and changing `summarised-by: qwen2.5-14b-instruct` to a
/// hosted row still reported *"OK — loaded cleanly (448 settings)"*, exit 0.
/// The failure then arrived at run time, in another language, in a process a
/// support lead never starts.
///
/// The egress rule lives in the Python resolver too (`must-stay-on-this-machine`
/// in `resolve.py`), where it is applied to the `needs:`-driven recommendation.
/// This is the same rule at check time, over the fields an author writes by
/// hand, which is the only place it can reach an author *where they are*.
///
/// **Which of the six roles admits which binding lives in [`egress`]**, along
/// with the walk that finds them. It used to live here and asked one question of
/// all four — `"llm" in allow-egress:` — so five of the six choices a workspace
/// can write were read by nothing at all. This function's job is the three
/// things only the CLI knows: what is served on this machine, what to offer
/// instead, and which ids exist at all.
/// An address that leaves the box, in a workspace that says nothing may (B9).
///
/// `allow-egress:`'s own help promises *"which parts of this system are allowed
/// to talk to something outside this box. Empty means nothing is."* Its six
/// choices were all MODEL roles, because a model was the only reacher anything
/// checked. MEASURED under `allow-egress: []`:
///
/// ```text
/// tool.url: https://vendor.example.com/upload + method: post + an upload action
///   → OK — loaded cleanly (19 settings)
/// ```
///
/// That door needs no resource file at all, which is why it is the one an
/// attacker writes: a single tool document, and the workspace's whole stated
/// boundary is silent.
///
/// # Two decisions worth stating
///
/// **One setting, not two.** A sibling hostname allow-list would be R61 (*"two
/// settings for what must never leave a workspace"*) and R20 (a name only the
/// host can resolve) at once, and `resource.endpoint`'s own help already says
/// the address is *"a name your platform team publishes… it is their list, not a
/// file in here"*. So `tools` is a seventh PART of the system, not a seventh
/// model role, on the field that already promises the whole boundary.
///
/// **An address the runtime resolves is not leaving the box.** `host/payments-mcp`
/// in the worked example has no `scheme://`, so it stays clean under
/// `allow-egress: []` and the flagship does not move. That is the difference
/// between a boundary and a ban on the letter `h`.
///
/// The set of fields that carry an outbound address is COMPUTED from
/// `reaches-outside:` in the schema. A hand-written list here would be B15 in a
/// new file.
/// A set of documents with no documents in it.
///
/// `knowledge.documents` is a folder, not a glob, so whether it holds anything
/// is a fact the loader already has: the payload walker either found files or it
/// did not. An empty one is the shape that looks most like success and is not —
/// the agent answers from what the model already knew, cites nothing, and
/// nobody is told the corpus was never there.
///
/// An ERROR and not a warning, unlike most cross-document judgements here. There
/// is no half-written state this describes: an author who has written
/// `knowledge/x/x.yaml` and no `documents/` folder has not started the thing
/// they are declaring, and every question the agent is asked in the meantime is
/// answered from nothing.
fn a_set_of_documents_has_documents_in_it(root: &pact_doc::Node, diags: &mut Diagnostics) {
    let Some(sets) = root.get("knowledge").and_then(pact_doc::Node::as_map) else { return };
    for (name, entry) in sets {
        // A payload is `Value::Payload`, not a map — `pact show` renders it
        // with `$payload` and `files` keys, and reading it back through those
        // names finds nothing. A folder of files is also a legitimate `Map` when
        // the walker did not treat it as a payload, so both shapes count.
        let files = match entry.node.get("documents").map(|d| &d.value) {
            Some(pact_doc::Value::Payload(p)) => p.files.len(),
            Some(pact_doc::Value::Map(m)) => m.len(),
            Some(pact_doc::Value::List(items)) => items.len(),
            _ => 0,
        };
        if files > 0 {
            continue;
        }
        diags.push(pact_diag::Diagnostic::error(
            "loader/knowledge-with-no-documents",
            entry.key_span.clone(),
            format!(
                "'{name}' is a set of documents with no documents in it, so nothing \
                 would ever come back and the agent would answer from what the model \
                 already knew."
            ),
            format!(
                "Put the files in a `documents/` folder beside `knowledge/{name}/`, or \
                 take '{name}' out until there is something to look things up in."
            ),
        ));
    }
}

/// `looked-up-by: meaning` in a workspace where nothing may leave.
///
/// Matching what a question is ABOUT rather than the words in it needs an
/// embedder, and an embedder is a model outside this box. `embedder` was the one
/// role in `allow-egress:` with no producer anywhere in the tree — `egress.rs`
/// says so in its own docstring — so this is its first, and it is the one that
/// matters: a hosted embedder is called on every question a customer asks, with
/// the question in it.
fn looking_up_by_meaning_needs_an_embedder(root: &pact_doc::Node, diags: &mut Diagnostics) {
    let Some(sets) = root.get("knowledge").and_then(pact_doc::Node::as_map) else { return };
    let allowed: Vec<String> = match root.get("allow-egress") {
        None => return,
        Some(n) => match &n.value {
            pact_doc::Value::List(items) => {
                items.iter().filter_map(|x| x.as_str().map(str::trim).map(str::to_owned)).collect()
            }
            pact_doc::Value::Str(s) => vec![s.trim().to_owned()],
            _ => Vec::new(),
        },
    };
    if allowed.iter().any(|a| a == "embedder") {
        return;
    }
    for (name, entry) in sets {
        let Some(how) = entry.node.get("looked-up-by").and_then(pact_doc::Node::as_str) else {
            continue;
        };
        if !matches!(how.trim(), "meaning" | "meaning-and-words") {
            continue;
        }
        let span = entry
            .node
            .as_map()
            .and_then(|m| m.get("looked-up-by"))
            .map(|e| e.node.span.clone())
            .unwrap_or_else(|| entry.key_span.clone());
        diags.push(pact_diag::Diagnostic::error(
            "loader/reaches-outside-the-box",
            span,
            format!(
                "'{name}' is looked up by `{}`, which needs a model to work out what a \
                 question is about — and nothing in this workspace may talk to something \
                 outside this box.",
                how.trim()
            ),
            "Add `embedder` to `allow-egress:` in workspace.yaml — that needs somebody to \
             approve it, because the question a customer typed goes to that model — or \
             write `looked-up-by: words`, which matches the words themselves and needs \
             nothing outside."
                .to_string(),
        ));
    }
}

fn nothing_reaches_outside_the_box(
    root: &pact_doc::Node,
    schema: &pact_schema::Schema,
    diags: &mut Diagnostics,
) {
    let allowed: Vec<String> = match root.get("allow-egress") {
        // The field is absent: this workspace has not drawn a boundary, and
        // inventing one would refuse trees that never opted in.
        None => return,
        Some(n) => match &n.value {
            pact_doc::Value::List(items) => {
                items.iter().filter_map(|x| x.as_str().map(str::trim).map(str::to_owned)).collect()
            }
            pact_doc::Value::Str(s) => vec![s.trim().to_owned()],
            _ => Vec::new(),
        },
    };
    if allowed.iter().any(|a| a == "tools") {
        return;
    }

    let outbound: std::collections::BTreeSet<&str> = schema
        .groups()
        .flat_map(|g| g.fields.iter())
        .filter(|f| f.reaches_outside)
        .map(|f| f.name.as_str())
        .collect();
    if outbound.is_empty() {
        return;
    }

    let mut found: Vec<(String, String, pact_diag::Span)> = Vec::new();
    walk_for_outbound(root, "", &outbound, &mut found);
    for (owner, address, span) in found {
        diags.push(pact_diag::Diagnostic::error(
            "loader/reaches-outside-the-box",
            span,
            format!(
                "nothing in this workspace may talk to something outside this box, and \
                 {owner} reaches `{address}`."
            ),
            "Add `tools` to `allow-egress:` in workspace.yaml — that needs somebody to \
             approve it — or use an address your runtime resolves, written without \
             `https://`, like `host/vendor-upload`."
                .to_string(),
        ));
    }
}

/// Every value of an outbound-address field anywhere in the tree, with the name
/// of the entry that owns it.
fn walk_for_outbound(
    node: &pact_doc::Node,
    owner: &str,
    outbound: &std::collections::BTreeSet<&str>,
    found: &mut Vec<(String, String, pact_diag::Span)>,
) {
    let Some(map) = node.as_map() else {
        if let pact_doc::Value::List(items) = &node.value {
            for item in items {
                walk_for_outbound(item, owner, outbound, found);
            }
        }
        return;
    };
    for (key, entry) in map.iter() {
        if outbound.contains(key.as_str())
            && let Some(written) = entry.node.as_str().map(str::trim)
            && leaves_the_box(written)
        {
            let named = if owner.is_empty() { key.clone() } else { format!("'{owner}'") };
            found.push((named, written.to_owned(), entry.node.span.clone()));
            continue;
        }
        // The name of the thing that owns the address is the key one level up
        // — `vendor` in `tools: { vendor: { url: … } }` — because that is what
        // an author looks for, not the field name.
        let next = if node_is_collection(key) { owner } else { key.as_str() };
        walk_for_outbound(&entry.node, if next.is_empty() { key } else { next }, outbound, found);
    }
}

/// Whether an address points outside, or is one the host resolves.
///
/// A `scheme://` is the whole test. `host/payments-mcp` is a name a platform
/// team publishes and the runtime looks up, and refusing it would make
/// `allow-egress: []` mean "no tools at all" rather than "nothing leaves".
fn leaves_the_box(address: &str) -> bool {
    let a = address.trim();
    if a.is_empty() {
        return false;
    }
    match a.split_once("://") {
        // `file://` is this machine, and `local` is the catalogue's own word for
        // a model served here — neither is somewhere outside the box.
        Some((scheme, _)) => !matches!(scheme, "file"),
        None => false,
    }
}

/// Whether a key is one of the workspace's collections rather than an entry.
fn node_is_collection(key: &str) -> bool {
    matches!(
        key,
        "agents" | "tools" | "resources" | "skills" | "policies" | "questions" | "ports"
            | "loops" | "context-policies" | "bundles" | "interceptors" | "watch" | "models"
            | "actions" | "served-by"
    )
}

fn egress_is_allowed(root: &pact_doc::Node, diags: &mut Diagnostics) {
    let mut local = locally_served(BUILTIN_CATALOGUE, "models/catalog.yaml");
    if let Some(rows) = root.get("models") {
        local.extend(locally_served_from(rows));
    }
    // The suggestion has to be a model that exists AND is served here, or the
    // fix is not typeable. The catalogue's own `default:` is what PACT binds
    // when nobody pins one and is locally servable by construction (D17), so it
    // is the one to offer; anything else would be an arbitrary pick out of a
    // sorted set.
    let offer = catalogue_default()
        .filter(|d| local.contains(d))
        .or_else(|| local.iter().next().cloned())
        .unwrap_or_else(|| "a locally-served model".to_string());
    // Every model id this tree could possibly mean — the shipped catalogue plus
    // the workspace's own rows. An id in NONE of them is a TYPO, and
    // `schema/no-such-name` already reports it with the right message and the
    // right fix; saying it "is only served off this machine" as well is a
    // confident false statement about a model that exists nowhere, printed
    // first, whose fix tells the author to bind a different model rather than to
    // correct the spelling.
    let known = models_known_here(Some(root));

    egress::refusals(root, &local, &offer, &known.names, diags);
}

/// Warn when the model grading the eval suite is a model under test.
///
/// `graded-by:`'s own help says *"Point it at a different model from the one
/// doing the work"*, and nothing anywhere compared the two — so a workspace
/// could pin `model: qwen2.5-14b-instruct` on its agent, write
/// `graded-by: qwen2.5-14b-instruct` in `evals/suite.yaml`, and get a score
/// where the model marks its own homework, printed as *"OK — loaded cleanly"*.
/// A promise in help text that nothing keeps is the silent degradation T7 names,
/// and this is the one place it can be caught before a number is quoted.
///
/// # A warning, not an error
///
/// The same call `money.rs` and `unnamed.rs` make. On a one-model air-gapped box
/// there may be nothing else to point at, and refusing to load would leave that
/// workspace with no judge at all — which is worse than a judge somebody has
/// been warned about. PACT's job here is that nobody quotes a self-graded score
/// *without having been told*.
///
/// # What it deliberately stays quiet about
///
/// **An agent that pins no `model:` at all.** PACT then binds the catalogue's
/// `default:`, which may well be the same weights, but that is a fact about this
/// distribution rather than a line the author wrote — and the only fix would be
/// advice about a field they deliberately left blank. `examples/refund-desk` is
/// exactly that workspace, and telling it to pin a model so it can pin a
/// different one is not a line anybody would type.
///
/// Aliases are resolved through both catalogue layers, because
/// `qwen2.5:14b-instruct` and `qwen2.5-14b-instruct` are one row's two spellings
/// and a check that compared the strings would miss the case it exists for.
/// `profile:` is written, `tier: core`, and read by nothing.
///
/// AC-7.2 asks that all defaults resolve from profiles. No profile mechanism
/// exists — `workspace.profile` has zero readers in the loader, in either
/// adapter, and in the second port — so an author writing `profile: production`
/// gets exactly what an author writing nothing gets, and believes otherwise.
///
/// A WARNING, for the same reason `bundle-not-mounted` is one: a host may resolve
/// it, and refusing outright would break a workspace whose runtime does. What
/// must not happen is silence, which is what happened until this.
fn a_profile_selects_nothing_yet(root: &pact_doc::Node, diags: &mut Diagnostics) {
    let Some(named) = root.get("profile") else { return };
    let Some(said) = named.as_str().map(str::trim).filter(|s| !s.is_empty()) else {
        return;
    };
    diags.push(pact_diag::Diagnostic::warning(
        "loader/profile-selects-nothing",
        named.span.clone(),
        format!(
            "`profile: {said}` chooses a set of defaults, and nothing in PACT \
             reads it — so this workspace behaves exactly as one with no \
             `profile:` line."
        ),
        "Nothing to type if the system running this resolves profiles itself. \
         Otherwise write the settings you meant explicitly — `limits:`, \
         `settings:` and `loop:` are where the defaults a profile would have \
         chosen actually live."
            .to_string(),
    ));
}

/// A case that asserts nothing is not a case.
///
/// `expect:` is `type: anything`, so `expect: {}` loaded cleanly — and a suite
/// carrying it reported one more case than it could grade. That matters most for
/// the case shape a person did NOT type: `--from-trace` promotes a run into a
/// file with an empty `expect:` on purpose, so that somebody has to say what
/// should have happened. Without this rule the promoted file passed `check`, the
/// suite's count went up, and the number it produced was about one case fewer
/// than it claimed.
///
/// `must-also:` counts as an assertion. A case whose whole point is *"it must
/// call `look-up-order` before `issue-refund`"* has nothing to put in `expect:`
/// and is complete without it.
fn every_case_asserts_something(root: &pact_doc::Node, diags: &mut Diagnostics) {
    let Some(cases) = root.get("evals").and_then(|e| e.get("cases")) else { return };
    let Some(cases) = cases.as_map() else { return };
    for (name, entry) in cases {
        let says_what = entry
            .node
            .get("expect")
            .is_some_and(|e| e.as_map().is_some_and(|m| !m.is_empty()) || e.as_str().is_some());
        let has_rules = entry
            .node
            .get("must-also")
            .is_some_and(|r| r.as_list().is_some_and(|l| !l.is_empty()));
        if says_what || has_rules {
            continue;
        }
        diags.push(pact_diag::Diagnostic::error(
            "evals/case-asserts-nothing",
            entry.key_span.clone(),
            format!(
                "The case '{name}' says what to send and nothing about what should \
                 come back, so running it can neither pass nor fail."
            ),
            "Fill in `expect:` with what the answer should contain — for example \
             `decision: approved` — or add a `must-also:` rule. A case promoted \
             from a run with `--from-trace` arrives empty on purpose: the answer \
             that run gave is the wrong one, and this is where you write the right \
             one."
                .to_string(),
        ));
    }
}

/// A metric that does not say who provides the score.
///
/// Port parity, the second half. `spec/schema.yaml` makes `uri:` required, so a
/// metric with none is already refused; what was not refused is a `uri:` with no
/// provider in front of it. `uri: faithfulness` printed `OK — loaded cleanly`
/// and then, at run time in another language, produced *"does not say who
/// provides that score, so nothing measured it"*.
///
/// The third thing `providers.py` decides — whether this machine HAS that
/// provider — is deliberately not checked here and belongs where it is: the
/// answer depends on what is installed, and a portable folder must not refuse
/// on one machine and load on another. Only the half that is a fact about the
/// document is a fact `pact check` can hold.
///
/// The wording is `providers.py`'s, to the word. Two ports refusing one thing in
/// two vocabularies is how an author learns that the checker and the runtime are
/// different products.
fn every_metric_says_who_provides_it(root: &pact_doc::Node, diags: &mut Diagnostics) {
    let Some(metrics) = root.get("evals").and_then(|e| e.get("metrics")) else { return };
    let Some(metrics) = metrics.as_list() else { return };
    for metric in metrics {
        let Some(uri) = metric.get("uri") else { continue };
        let Some(written) = uri.as_str().map(str::trim).filter(|s| !s.is_empty()) else { continue };
        if written.contains(':') {
            continue;
        }
        diags.push(pact_diag::Diagnostic::error(
            "evals/metric-without-a-provider",
            uri.span.clone(),
            format!(
                "`uri: {written}` does not say who provides that score, so nothing \
                 would measure it."
            ),
            format!(
                "Put the provider in front of it with a colon — `uri: deepeval:{written}` \
                 for a DeepEval score, or `uri: pact:at_most_words` for one that needs \
                 nothing installed."
            ),
        ));
    }
}

/// A rule graded by reading the answer, in a suite with nobody to read it.
///
/// Port parity. `judged:` is decided by a model, and which model is
/// `graded-by:`. With no `graded-by:` the Python runtime reaches
/// `providers.py`'s judge-is-`None` arm and reports the rule on
/// `RunResult.unenforced` — *"nothing was grading this run, so it was not
/// measured"* — while `pact check` printed `OK — loaded cleanly`. Everything
/// needed to decide it is in the documents: a rule that says `judged:` and a
/// suite with no grader. Deciding it at run time, in a process the author never
/// starts, is the split this check closes.
///
/// A WARNING and not an error, for the reason `available.rs` gives: a suite
/// under construction legitimately has the rule before it has the grader, and a
/// build that fails on a half-written tree teaches people to turn checking off.
/// What it may never be is silent, because the failure is the dangerous
/// direction — the author believes the rule is being enforced.
fn a_judged_rule_has_somebody_to_grade_it(root: &pact_doc::Node, diags: &mut Diagnostics) {
    let Some(evals) = root.get("evals") else { return };
    let graded_by = evals
        .get("graded-by")
        .and_then(|n| n.as_str())
        .map(str::trim)
        .filter(|s| !s.is_empty());
    if graded_by.is_some() {
        return;
    }

    // Both places a judged rule can be written: the suite's own `rules:`, and a
    // case's `must-also:`. One reader for both, so the two cannot come to mean
    // different things — which is how `must-match-shape:` drifted.
    let mut wheres: Vec<(pact_diag::Span, String)> = Vec::new();
    if let Some(rules) = evals.get("rules").and_then(pact_doc::Node::as_list) {
        for rule in rules {
            if let Some(j) = rule.get("judged") {
                wheres.push((j.span.clone(), "this suite's `rules:`".to_owned()));
            }
        }
    }
    if let Some(cases) = evals.get("cases").and_then(pact_doc::Node::as_map) {
        for (name, entry) in cases {
            let Some(also) = entry.node.get("must-also").and_then(pact_doc::Node::as_list) else {
                continue;
            };
            for rule in also {
                if let Some(j) = rule.get("judged") {
                    wheres.push((j.span.clone(), format!("the case '{name}'")));
                }
            }
        }
    }

    for (span, where_) in wheres {
        diags.push(pact_diag::Diagnostic::warning(
            "evals/judged-with-nobody-grading",
            span,
            format!(
                "a rule in {where_} is decided by reading the answer, and this suite \
                 says nothing about who grades it — so running the checks measures \
                 everything except this."
            ),
            "Add `graded-by:` to the suite, naming a model this machine serves — \
             `graded-by: qwen2.5-14b-instruct` is what the worked example uses. Its \
             own help asks for a different model from the one being checked, so a \
             score is not something a model gave itself."
                .to_string(),
        ));
    }
}

fn judge_is_not_the_model_under_test(root: &pact_doc::Node, diags: &mut Diagnostics) {
    let Some(judge) = root.get("evals").and_then(|e| e.get("graded-by")) else { return };
    let Some(grader) = judge.as_str().map(str::trim).filter(|s| !s.is_empty()) else { return };
    let Some(agents) = root.get("agents").and_then(pact_doc::Node::as_map) else { return };

    let mut rows = alias_groups(BUILTIN_CATALOGUE, "models/catalog.yaml");
    if let Some(node) = root.get("models") {
        rows.extend(alias_groups_from(node));
    }
    // The set of spellings that mean the grader — itself, plus every row that
    // publishes it as an alias, plus that row's other names.
    let same_as_grader: std::collections::BTreeSet<String> = rows
        .iter()
        .filter(|names| names.contains(grader))
        .flatten()
        .cloned()
        .chain(std::iter::once(grader.to_string()))
        .collect();

    for (name, entry) in agents {
        let Some(pinned) = entry.node.get("model") else { continue };
        let Some(id) = pinned.as_str().map(str::trim).filter(|s| !s.is_empty()) else { continue };
        if !same_as_grader.contains(id) {
            continue;
        }
        // Underlined at the AGENT's `model:` rather than at `graded-by:`. One
        // suite grades every agent, so the line to change is usually the one
        // that differs — and the message names both, so a reader who wants to
        // change the other one knows where it is.
        diags.push(pact_diag::Diagnostic::warning(
            "loader/judge-is-the-model-under-test",
            pinned.span.clone(),
            format!(
                "`{name}` runs on `{id}` and `graded-by: {grader}` in this workspace's \
                 checks is the same model, so it grades its own answers — a model \
                 grading its own work marks its own homework."
            ),
            format!(
                "Point `graded-by:` at a different row in `models/catalog.yaml`; or, \
                 if `{name}` is the one to move, write a different `model:` for it."
            ),
        ));
    }
}

/// Every catalogue row's names, one set per row: its own, plus `also-known-as`.
fn alias_groups(text: &str, from: &str) -> Vec<std::collections::BTreeSet<String>> {
    let path = camino::Utf8Path::new(from);
    let Ok(doc) = pact_doc::parse_yaml(text, path) else {
        return Vec::new();
    };
    alias_groups_from(&doc)
}

/// The same, for a `models:` block that arrives already parsed as part of the
/// loaded document rather than as text — the split [`locally_served_from`] makes,
/// for the same reason.
fn alias_groups_from(models: &pact_doc::Node) -> Vec<std::collections::BTreeSet<String>> {
    let Some(rows) = models.get("models").and_then(pact_doc::Node::as_map) else {
        return Vec::new();
    };
    rows.iter()
        .map(|(name, entry)| {
            let mut names = std::collections::BTreeSet::from([name.clone()]);
            if let Some(list) = entry.node.get("also-known-as").and_then(pact_doc::Node::as_list) {
                names.extend(list.iter().filter_map(|n| n.as_str().map(str::to_string)));
            }
            names
        })
        .collect()
}

/// What PACT binds when the author pins nothing — the catalogue's own `default:`.
fn catalogue_default() -> Option<String> {
    let path = camino::Utf8Path::new("models/catalog.yaml");
    let doc = pact_doc::parse_yaml(BUILTIN_CATALOGUE, path).ok()?;
    doc.get("default").and_then(pact_doc::Node::as_str).map(str::to_string)
}

/// The locally-served ids a workspace added in its own `models/catalog.yaml`.
///
/// Separate from [`locally_served`] only because the workspace copy arrives
/// already parsed, as a node of the loaded document, rather than as text.
fn locally_served_from(models: &pact_doc::Node) -> std::collections::BTreeSet<String> {
    let mut ids = std::collections::BTreeSet::new();
    let Some(rows) = models.get("models").and_then(pact_doc::Node::as_map) else {
        return ids;
    };
    for (name, entry) in rows {
        let local = entry
            .node
            .get("served-by")
            .and_then(pact_doc::Node::as_list)
            .is_some_and(|ways| {
                ways.iter()
                    .any(|w| w.get("endpoint").and_then(pact_doc::Node::as_str) == Some("local"))
            });
        if !local {
            continue;
        }
        ids.insert(name.clone());
        if let Some(list) = entry.node.get("also-known-as").and_then(pact_doc::Node::as_list) {
            ids.extend(list.iter().filter_map(|n| n.as_str().map(str::to_string)));
        }
    }
    ids
}

/// Where the specification came from. Reported, never assumed.
///
/// There is no `Workspace` arm any more and there must not be one. It walked UP
/// from the target to the filesystem root, so a `spec/schema.yaml` in any
/// ancestor directory replaced the core schema for everything under it — see
/// [`BUILTIN_SPEC`] for the reproduction. LOAD-13: *"the core schema is not
/// discovered from the tree at all."*
enum SpecSource {
    /// `$PACT_SPEC`, and only in a debug build, and only with `--unsafe-spec`
    /// typed out. It exists so the specification can be edited and tried without
    /// a rebuild; it is not a supported way to run.
    // NEVER CONSTRUCTIBLE IN A RELEASE BINARY, which is the point: the only
    // arm that builds one is `#[cfg(debug_assertions)]`, so `PACT_SPEC` cannot
    // decide what the governance columns say in anything somebody installed.
    // The compiler notices and warns `dead_code` — correctly — so the warning is
    // silenced HERE, where the reason is, rather than by deleting the variant or
    // by widening a lint somewhere central.
    //
    // `cargo clippy --all-targets` never saw it: tests build with debug
    // assertions on, so the variant is live there. It appeared the first time
    // anybody ran `cargo install`, which is register row C6's whole subject.
    #[cfg_attr(not(debug_assertions), allow(dead_code))]
    Unsafe(Utf8PathBuf),
    Builtin,
}

impl SpecSource {
    fn text(&self) -> Result<String> {
        match self {
            SpecSource::Unsafe(p) => {
                Ok(std::fs::read_to_string(p).map_err(|e| anyhow::anyhow!("reading {p}: {e}"))?)
            }
            SpecSource::Builtin => Ok(BUILTIN_SPEC.to_string()),
        }
    }

    fn describe(&self) -> String {
        match self {
            SpecSource::Unsafe(p) => format!("{p} (from PACT_SPEC, with --unsafe-spec)"),
            SpecSource::Builtin => "the built-in specification".to_string(),
        }
    }
}

/// The specification: the compiled-in copy, unless a developer has explicitly
/// asked for another one in a build that allows it.
///
/// This never returns "none". Silently skipping validation because a file was
/// not found is how a broken tree reports itself as fine — the exact failure
/// this project exists to eliminate.
fn find_spec(unsafe_spec: bool) -> SpecSource {
    // Two gates, and both have to be open. `#[cfg(debug_assertions)]` keeps it
    // out of a release binary entirely; `--unsafe-spec` keeps an environment
    // variable somebody else set from taking effect silently. It was one gate
    // and neither, so `PACT_SPEC` in an inherited environment quietly decided
    // what the governance columns said.
    #[cfg(debug_assertions)]
    if unsafe_spec && let Ok(p) = std::env::var("PACT_SPEC") {
        return SpecSource::Unsafe(Utf8PathBuf::from(p));
    }
    let _ = unsafe_spec;
    SpecSource::Builtin
}

/// Load a tree and run every check over it, returning what they found.
///
/// Split out from [`check`] so that checking ONE AGENT can load the workspace
/// that holds its tools and then show only what is wrong inside the folder the
/// reader named. Before that split, `pact check examples/refund-desk/agents/refund-desk`
/// printed fourteen errors on the shipped, correct example — every one false and
/// every fix harmful (*"'uses' names 'zendesk', and there is no such entry in
/// `tools:`"*, offering to create a file that exists two directories up).
/// C1: refuse a tree written for a version of the format this build cannot read.
///
/// Absent is the ordinary case and is never a problem: a no-code author writes no
/// version line, and `pact-version:`'s own help says PACT then reads it as the
/// version this build understands. The field exists for the other direction — a
/// tree that wants to be refused **loudly** by a runtime too old for it, rather
/// than misread quietly, which is what happens today to every consumer of a format
/// with no version at all.
fn version_is_one_we_read(root: &pact_doc::Node, diags: &mut Diagnostics) {
    let Some(written) = root.get("pact-version") else { return };
    let Some(said) = written.as_str() else { return };
    let said = said.trim();
    if said.is_empty() || said == pact_doc::SPEC_VERSION {
        return;
    }
    diags.push(pact_diag::Diagnostic::error(
        "loader/unreadable-spec-version",
        written.span.clone(),
        format!(
            "This workspace says it is written for `{said}`, and this build reads \
             `{}`.",
            pact_doc::SPEC_VERSION
        ),
        format!(
            "Either upgrade PACT to one that reads `{said}`, or change \
             `pact-version:` to `{}` and check the tree still means what you \
             intended. Refusing is the point of the line: a document read under \
             the wrong version of a format is worse than one that would not load.",
            pact_doc::SPEC_VERSION
        ),
    ));
}

/// A workspace that says nothing survives a stop, and stops.
///
/// `pact waits` already walks every place this tree can park — thirteen of them
/// in the worked example, out to four hours. So `durability: none` is not an
/// opinion PACT has to take on trust: the tree says whether it parks, and the
/// two lines can be read against each other.
///
/// That is what makes the field worth having. The shape it replaces —
/// `requires-of-the-runtime: {durable-resume: yes}` — could only ever be
/// confirmed by a host, never contradicted by the document, so it would have
/// been a line that validates and means nothing.
///
/// A WARNING and not an error: a workspace may genuinely intend to lose a
/// parked run and start again, and refusing outright would make `durability:`
/// unwritable for the case it describes. What must not happen is silence.
fn durability_matches_what_this_tree_does(
    root: &pact_doc::Node,
    report: &pact_loader::report::LoadReport,
    diags: &mut Diagnostics,
) {
    let Some(said) = root.get("durability").and_then(pact_doc::Node::as_str) else { return };
    if said.trim() != "none" || report.waits.is_empty() {
        return;
    }
    let span = root
        .as_map()
        .and_then(|m| m.get("durability"))
        .map(|e| e.key_span.clone())
        .unwrap_or_else(|| root.span.clone());
    let n = report.waits.len();
    diags.push(pact_diag::Diagnostic::warning(
        "loader/parks-with-nothing-to-resume-it",
        span,
        format!(
            "this workspace says `durability: none`, and it can stop and wait for a \
             person in {n} place(s). With nothing kept, each of those starts again from \
             the beginning — including the work already paid for."
        ),
        "Write `durability: checkpoint` if the system running this picks a run back \
         up, or take the waits out if it really does start again. `pact waits` lists \
         every one of them."
            .to_string(),
    ));
}

fn validate(path: &Utf8PathBuf, unsafe_spec: bool) -> Result<(Option<pact_doc::Node>, Diagnostics)> {
    let (mut node, mut diags) = load(path)?;

    // `based-on:` is resolved BEFORE the schema sees anything (G11). A derived
    // entry has to be validated as the thing it becomes: validating it as
    // written would demand every required field on a document whose whole point
    // is that it restates only what differs, and would then check the merged
    // fields never at all. Resolving first means one document reaches the
    // schema, the digest, `show` and both adapters — the alternative is four
    // places that each have to remember to merge.
    // The specification is built BEFORE the tree is touched, because
    // `based-on:` resolution has to know which top-level maps are collections of
    // definitions and which are not — and that is a fact the specification
    // states. It used to be a list of fourteen names in `derive.rs`, four of
    // which (`watches`, `schedules`, `evals`, `redactions`) name nothing a
    // workspace has, while `watch:` and `bundles:` were missing, so a `based-on:`
    // inside either was silently never resolved.
    //
    // Built under the same condition as before, and no earlier: a tree that did
    // not load must not start reporting a problem with the specification
    // instead of the problem it has.
    let source = find_spec(unsafe_spec);
    let mut sd = Diagnostics::new();
    let (text, spec) = if node.is_some() {
        let text = source.text()?;
        let spec = pact_schema::from_doc::schema_from_yaml(&text, &mut sd);
        (text, spec)
    } else {
        (String::new(), pact_schema::Schema::new())
    };

    if let Some(root) = node.as_mut() {
        pact_loader::derive::resolve(root, &spec, &mut diags);
    }

    if let Some(root) = node.as_ref() {
        let schema = spec
            .knowing("models", models_known_here(node.as_ref()))
            // The suites this tree really has, so `evals:` on an agent is held
            // against them the way `policy:` is held against `policies:`. It is
            // supplied here rather than resolved as a map in the document
            // because the suite is a set of settings, not a map of suites: a
            // plain `names: evals` would have accepted `evals: cases`, which is
            // a field inside the suite and not a suite. See `suites`.
            .knowing("evals", suites::known_here(node.as_ref()));

        if sd.has_errors() {
            eprintln!("The specification itself has problems ({}):", source.describe());
            eprint!("{}", sd.render());
            bail!("cannot validate against a broken specification");
        }
        // Which specification decided this, whenever it was not the compiled-in
        // one. A run that classifies fields differently from every other run must
        // say so; for a round nothing in the output ever named the source.
        if let SpecSource::Unsafe(_) = source {
            eprintln!(
                "note: validated against {} (sha256 {}), not the built-in specification.",
                source.describe(),
                spec_digest(&text)
            );
        }
        let ungoverned = governance_is_complete(&text);
        if !ungoverned.is_empty() {
            bail!(
                "the specification at {} leaves {} field(s) with no `surface:` or `tier:` — \
                 {} — so nothing could say which changes to them need a person. Refusing to \
                 validate against it.",
                source.describe(),
                ungoverned.len(),
                ungoverned.join(", ")
            );
        }

        // A tree with `agents:` is a workspace; anything else is a single agent.
        let kind = if root.get("agents").is_some() { "workspace" } else { "agent" };
        // ...and a folder that is neither is neither, which nothing said. A
        // directory holding only `agent.yaml` and `instructions.md` — Eve's
        // documented flat layout — printed "OK — loaded cleanly (3 settings)"
        // and exit 0, while `pact show` emitted no `agents:` key, `pact
        // discover` printed `[]`, `pact card hello` failed, and the adapter
        // raised `KeyError: no agent named 'hello'`. The only affirmative signal
        // an author got was a success message for something no runtime can load.
        // An EMPTY folder was worse: it was validated as an agent and told to
        // add `description:` to a file that does not exist.
        let mut nothing_to_validate = false;
        if kind == "agent" && enclosing_workspace(path).is_none() {
            nothing_to_validate = not_a_workspace(path, root, &mut diags);
        }
        // One mistake gets one message. Validating a folder that is not a PACT
        // folder as if it were an agent produced a second error telling the
        // reader to add `description:` to a file that does not exist.
        if nothing_to_validate {
            diags.sort();
            return Ok((node, diags));
        }
        match schema.group(kind) {
            Some(_) => schema.validate(root, kind, &mut diags),
            None => bail!(
                "the specification at {} describes no '{kind}' kind",
                source.describe()
            ),
        }
        // WHICH VERSION OF THE FORMAT THIS TREE IS WRITTEN FOR — asked before any
        // other cross-document rule, because every one of them is a rule of a
        // particular version. A tree written for a version this build does not
        // read must be refused rather than misread; that is what the field is for
        // and it is the only reason to write one.
        version_is_one_we_read(root, &mut diags);
        // The one rule the schema cannot state about itself: `names: pact:models`
        // asks whether an id EXISTS, and this asks whether binding it would leave
        // a workspace that says nothing may (D17, Y16).
        egress_is_allowed(root, &mut diags);
        // B9: the seventh part of the system — every address a tool or a server
        // it connects to reaches. See `nothing_reaches_outside_the_box`.
        nothing_reaches_outside_the_box(root, &schema, &mut diags);
        // A7: the two things only a whole-tree walk can say about a corpus.
        a_set_of_documents_has_documents_in_it(root, &mut diags);
        looking_up_by_meaning_needs_an_embedder(root, &mut diags);
        // And the other thing only this walk can see about `graded-by:`: whether
        // the model grading the checks is a model being checked. Its own help
        // promises they are different and nothing compared them, so a score a
        // model gave itself printed "OK — loaded cleanly".
        judge_is_not_the_model_under_test(root, &mut diags);
        every_case_asserts_something(root, &mut diags);
        // Port parity: what the Python runtime decides from the document alone,
        //  decides too — see .
        a_judged_rule_has_somebody_to_grade_it(root, &mut diags);
        every_metric_says_who_provides_it(root, &mut diags);
        a_profile_selects_nothing_yet(root, &mut diags);
        // What the load found about the waits this tree can produce — and the
        // two diagnostics only it can emit: a `if-nobody-answers:` with no
        // `answer-within:` beside it, and a `shows:` naming a value the park it
        // is put at cannot supply.
        //
        // Until this line, `LoadReport::of` was called from exactly one place in
        // the repository: its own test. So a question that said what to do when
        // nobody answers and never said how long they had printed
        // *"OK — loaded cleanly"* and exited 0, and the warning reached a Rust
        // caller and nobody else. D13's reader runs `pact check` and nothing
        // else, so a diagnostic that does not arrive here does not arrive.
        let report = pact_loader::report::LoadReport::of(root, &mut diags);
        // A8. `durability: none` on a tree that parks is a claim the tree itself
        // disproves — and being CONTRADICTABLE is the whole reason this field is
        // worth writing. `allow-egress: []` has the same property;
        // `durable-resume: yes` could only ever be confirmed.
        durability_matches_what_this_tree_does(root, &report, &mut diags);
        // The other rule the schema cannot state about itself: it can hold each
        // stage name in a loop against `steps:`, and it cannot walk the arrows.
        // §7.6 rule 7 states this for the graph half ("a `join` with
        // `waits-for: everyone` is reachable from every member of its group");
        // this is the loop half. It runs HERE, beside the two above, because
        // D13's reader runs `pact check` and nothing else — a diagnostic that
        // does not arrive here does not arrive.
        pact_loader::reachability::every_stage_is_reachable(root, &mut diags);
        // And the third: the schema can say each share is a percentage and
        // cannot add them up, nor compare the names under `shares:` against the
        // names under `team:`. Both rules already existed in
        // `delegation.py`'s `Teamwork.check`, which raises — but only once a run
        // starts, in another language, in a process D13's author never starts.
        // Reproduced before this line: `shares:` reading 60% and 90% — 150% of
        // one pot — printed `OK — … loaded cleanly (468 settings).` and exited 0.
        pact_loader::teamwork::check(root, &mut diags);
        // And the fourth: the tool an approval rule guards. `names:` resolves a
        // value against the keys of a map, and the name here is `<tool>/<action>`
        // — two names in one string, the second a level down — so nothing the
        // schema can say reaches it. Reproduced before this line: misspelling
        // `payments/issue-refund` in the shipped example printed
        // `OK — … loaded cleanly (468 settings).` and a 300 USD refund went
        // through with nobody asked and nothing reported.
        pact_loader::approvals::check(root, &mut diags);
        // And the fifth: a `team:` that comes back to where it started.
        // `key-names: agents` holds each name against the agents that exist and
        // cannot see the shape of the graph, so `team: {helper: I ask myself.}`
        // inside `agents/helper/` printed "OK — loaded cleanly (11 settings)".
        pact_loader::teams::no_team_calls_itself(root, &mut diags);
        // And the sixth, which runs the other way round from every check above:
        // `names:` asks whether a name RESOLVES, and never whether anything names
        // a document. A fully-written approval policy that no agent points at
        // loaded cleanly and gated nothing, which is the commonest way to author
        // a gate that does not exist.
        pact_loader::unnamed::nothing_points_at_it(root, &mut diags);
        // G12. The schema holds `available-when:` against its closed list and
        // cannot hold it against the agent that names the capability — whether
        // this agent has a `team:` is a fact about a different document. A
        // condition that can never hold makes a capability load, read as
        // configured, and never once be offered, which is the hardest kind of
        // nothing to debug.
        pact_loader::available::nothing_waits_on_a_condition_that_cannot_hold(
            root, &schema, &mut diags,
        );
        // G10. `brings:` is a declaration of scope, and a declaration nobody
        // checks is a comment. The hazard is a supply-chain one: a bundle's next
        // version starts shipping `interceptors/`, and a third party's rule can
        // now stop this run — with nothing in this workspace changed and nobody
        // here having approved it.
        pact_loader::bundles::a_bundle_brings_only_what_it_said(root, &schema, &mut diags);
        // And the seventh, which was decided only by RUNNING the agent.
        // `spends-money:`'s own help promises the call is routed through the
        // author's approval policy; whether it is, is a fact about a different
        // document — the policy `policy:` points at, naming `<tool>/<action>` —
        // so `needed-when:` cannot reach it and the schema said nothing. It was
        // reported instead on `RunResult.money_moving`, which is a field on a
        // result object in another language, in a process D13's reader never
        // starts. Reproduced before this line: deleting the two
        // `payments/issue-refund` rules from the shipped example printed
        // `OK — … loaded cleanly (489 settings).` while a Python run of the same
        // tree said money moves without anybody being asked.
        pact_loader::money::check(root, &mut diags);
        // And the eighth, which runs one direction further round than
        // `needed-when:` can reach. `kind: schedule` already demanded `every:`;
        // nothing asked the reverse question — whether the settings a port
        // carries agree with the kind it says it is. Reproduced before this
        // line: `ports/weekly-review.yaml` changed from `kind: schedule` to
        // `kind: event`, with `every: Friday at 4pm`, `says:` and
        // `if-still-running: skip` left in place, printed
        // `OK — … loaded cleanly (492 settings).` and exited 0 — a timer that
        // can never fire, and the first person to know would have been whoever
        // expected the weekly summary on a Friday. This is also what reads the
        // derivation that let `kind:` stop being required: a port carrying
        // `every:` is a timer whether or not it says so.
        pact_loader::ports::check(root, &schema, &mut diags);
        // And the ninth, which is a set question rather than a pair question, so
        // no field attribute can reach it: a tool says where it reaches on
        // exactly one of `connect:`, `url:` and `says:`, and `needs-also:` and
        // `needed-when:` both fire on ONE field being set. `runs-as:` used to
        // stand in front of the three as a word naming which applied, and was
        // read by nothing at all — two of its four choices named ways of running
        // nothing here carries out, so the tool was offered to the model anyway
        // and came back `error: no tool named ...` on the first call. Reproduced
        // before this line: deleting `connect: payments-server` from the shipped
        // `tools/payments.yaml` printed `OK — … loaded cleanly (491 settings).`
        // and exited 0, and adding a second transport line beside it printed the
        // same, with nothing written down anywhere deciding which one a runtime
        // would use.
        pact_loader::reach::check(root, &mut diags);
        // And the tenth, which is about the NAME rather than about anything
        // written under it, so no field attribute can see it: `names:` and
        // `key-names:` ask whether a name resolves inside this tree, and every
        // model provider asks a different question — whether the name matches
        // `^[a-zA-Z0-9_-]{1,64}$` — before it will accept the request at all. A
        // tool key and a teammate key are the two names that go onto that wire
        // verbatim (`harness.py` builds the model's tool list from `spec.tools`
        // and `spec.team`). Reproduced before this line: `tools/Get Weather.yaml`
        // plus `- Get Weather` under `uses:` in the shipped example printed
        // `OK — … loaded cleanly (497 settings).` and exited 0, while the lowered
        // payload read `{"name": "Get Weather"}` — a workspace whose first model
        // call is a guaranteed refusal, passed by the only command D13's reader
        // runs.
        pact_loader::callable::check(root, &mut diags);
        // And the eleventh, which no `one-of:` can reach because the list it
        // would have to hold is not in the specification at all — it is whatever
        // `models/catalog.yaml` charges in, here, after this workspace's own
        // override layer. `Ty::Money` keeps its currency and FR-1.4.5 forbids
        // converting one, and then every reader of a money value threw the
        // currency away. Reproduced before this line: `cost-per-request-under:
        // 500 JPY` in the shipped example's `limits.yaml` printed
        // `OK — … loaded cleanly (492 settings).` and exited 0, while the meter
        // that ceiling is compared against is priced in USD and the sentence the
        // author got back at 501 read `(501 of 500 USD)`.
        pact_loader::currency::check(root, &schema, BUILTIN_CATALOGUE, &mut diags);
        // And the twelfth, which is the line that READS `redaction:`. Collapsing
        // `redaction:`/`redactions:` into one field (R61) fixed a shape and left
        // the field consulted by nothing: an author could write `redaction.yaml`,
        // have every sentence in it checked, and change no outcome anywhere. This
        // is AD-88 rule 4 — `enabled: yes` plus a reflector allowed off this
        // machine plus no redaction is a load-time error — stated in the
        // architecture for a round and implemented by nothing. Reproduced before
        // this line: the shipped example with `enabled: yes` and
        // `allow-egress: [reflector]` and `redaction.yaml` deleted printed
        // `OK — … loaded cleanly` and exited 0, and the failing conversations the
        // improving cycle learns from — the customer's own words — went to a
        // model outside the box with nothing saying what to hold back.
        pact_loader::redaction::improving_with_nothing_held_back(root, &mut diags);
        // And the thirteenth, which is the line that READS `learning.review:`.
        // That field's own help text promised *"`pact check` tells you if
        // nothing runs this"* for a round, and the promise was withdrawn from
        // the help rather than kept — measured on the shipped example, `review:
        // weekly` with `ports/weekly-review.yaml` deleted printed
        // `OK — … loaded cleanly` and exited 0, so a workspace could promise the
        // team a weekly review of what its agent wants to change and have
        // nothing anywhere able to reach a Friday. It is a pair question across
        // two files (`learning.yaml` and `ports/`), which no field attribute can
        // ask.
        pact_loader::review::check(root, &schema, &mut diags);
        diags.sort();
    }
    Ok((node, diags))
}

/// Say so when the folder being checked is not something a runtime can load.
///
/// Two shapes, and they need different words. A folder with an agent in it but
/// no workspace around it is an author one file away from working; a folder with
/// neither is somebody who pointed the command at the wrong place, and telling
/// them to add `description:` to a file that does not exist helps nobody.
fn not_a_workspace(path: &Utf8PathBuf, root: &pact_doc::Node, diags: &mut Diagnostics) -> bool {
    let has_agent_settings = root.get("description").is_some() || root.get("instructions").is_some();

    // The folder that has to become a workspace. `pact check` also accepts a
    // single file, and the workspace a lone `agent.yaml` is missing goes BESIDE
    // it, never inside it — `agent.yaml/workspace.yaml` is not a path anybody
    // can create.
    let folder = if path.is_dir() {
        path.clone()
    } else {
        path.parent().map_or_else(|| path.clone(), Utf8PathBuf::from)
    };
    // Which file to make is asked of the one component that answers that
    // question, so this can never name a spelling the loader would go on to read
    // as an ordinary setting. `folder` is its own root here, so rule 1 fires and
    // the answer is `workspace.yaml` — the only name `pact discover` reads.
    let start = pact_loader::firstfile::to_start(&folder, &pact_loader::policy::Policy::default(), &folder);

    // ...and the span says FOLDER, which is what stops the arrow printing a line
    // and a column against a directory.
    //
    // `pact check <an empty folder>` — the very first thing anybody types, one
    // step EARLIER than the tree that has an `agents/` in it — opened with
    // `--> /tmp/hello:1:1`, sending a first-time reader to line 1 column 1 of
    // something no editor will open. `schema/missing-field` was taught this
    // (see `Span::in_folder` and `firstfile`); these two, which fire before it
    // and are therefore the FIRST sentence PACT ever says to anybody, were not.
    //
    // A file keeps its line and column, because a file really has them.
    let span = if path.is_dir() {
        pact_diag::Span::in_folder(path.as_str(), start.as_str())
    } else {
        pact_diag::Span::whole_file(path.as_str())
    };

    // Both fixes quote the line to type the one way the rest of the tool quotes
    // it: `name: ...` for the shape, then the words after the dash for what to
    // put there. It used to read `` `name: <what this whole system is called>` ``
    // — the whole instruction inside the backticks, so a reader who takes
    // "put this line in it" literally, which is the only safe way to read it
    // when you cannot write code (D13), ends up with a workspace actually called
    // `<what this whole system is called>`. Two spellings of one instruction,
    // and the ambiguous one was on the message that comes first.
    let make_the_workspace =
        format!("Create `{start}` and put one line in it: `name: ...` — what this whole system is called.");

    if has_agent_settings {
        diags.push(pact_diag::Diagnostic::warning(
            "loader/nothing-can-run-this",
            span,
            format!(
                "'{path}' has an agent in it and no workspace around it, so nothing \
                 can find it: `pact discover` returns none and `pact card` cannot \
                 publish it."
            ),
            format!(
                "{make_the_workspace} Then move this agent into a folder beside it: \
                 `{folder}/agents/<a short name for it>/agent.yaml`."
            ),
        ));
        return false;
    } else {
        diags.push(pact_diag::Diagnostic::error(
            "loader/not-a-pact-folder",
            span,
            format!(
                "'{path}' is not a PACT folder — there is no `workspace.yaml` in it \
                 and no `agents/` folder either."
            ),
            format!(
                "{make_the_workspace} Or point the command at the folder that already \
                 has one."
            ),
        ));
    }
    true
}

fn check(
    path: &Utf8PathBuf,
    quiet: bool,
    unsafe_spec: bool,
    deny_warnings: bool,
) -> Result<i32> {
    // Checking ONE AGENT is the obvious thing to type while working on one. Its
    // tools and policies live in the workspace above it, so the workspace is what
    // gets loaded and only what is wrong inside the folder the reader named is
    // printed.
    if let Some(root) = enclosing_workspace(path) {
        return check_in_context(path, &root, quiet, unsafe_spec);
    }
    let (node, diags) = validate(path, unsafe_spec)?;

    if !diags.is_empty() {
        out_raw!("{}", diags.render());
    }

    let errors = diags.error_count();
    let warnings = diags.warning_count();

    if !quiet {
        match (errors, warnings) {
            (0, 0) => {
                let n = node.as_ref().map_or(0, pact_doc::Node::node_count);
                out!("OK — {path} loaded cleanly ({n} settings).");
            }
            (0, w) => out!("OK — {path} loaded with {w} warning(s)."),
            (e, 0) => out!("{e} problem(s) found in {path}. Nothing was run."),
            (e, w) => out!("{e} problem(s) and {w} warning(s) found in {path}."),
        }
    }

    // A warning is a heuristic cross-document judgement, and what makes those
    // safe to ADD is that a false positive costs a line of noise rather than a
    // broken build. `--deny-warnings` gives that up on purpose, per run, where
    // somebody has decided the trade — never by default.
    Ok(if errors > 0 || (deny_warnings && warnings > 0) { 1 } else { 0 })
}

/// The workspace `path` is an agent inside, if it is one.
///
/// A workspace has `workspace.yaml` or an `agents/` folder. Walking up stops at
/// the first one, so an agent inside an agent's own subfolder still resolves to
/// the tree that holds its tools. `None` means `path` is the whole thing being
/// looked at, which is the ordinary case.
fn enclosing_workspace(path: &Utf8PathBuf) -> Option<Utf8PathBuf> {
    let start = path.canonicalize_utf8().ok()?;
    let mut dir = start.parent().map(Utf8PathBuf::from);
    while let Some(d) = dir {
        if d.join("workspace.yaml").exists() || d.join("agents").is_dir() {
            return Some(d);
        }
        dir = d.parent().map(Utf8PathBuf::from);
    }
    None
}

/// Check one agent against the workspace it lives in.
///
/// The whole tree is loaded, so `uses:`, `policy:`, `team:` and `evals:` resolve
/// against the tools and policies that really exist — and then only the problems
/// inside the folder the reader named are printed, because they asked about that
/// folder. Checking the whole workspace and printing all of it would answer a
/// question they did not ask; refusing would be the fourteen false errors again
/// in a politer voice.
fn check_in_context(
    agent: &Utf8PathBuf,
    root: &Utf8PathBuf,
    quiet: bool,
    unsafe_spec: bool,
) -> Result<i32> {
    let here = agent.canonicalize_utf8().unwrap_or_else(|_| agent.clone());
    let (_, whole) = validate(root, unsafe_spec)?;
    let mut mine = Diagnostics::new();
    for d in whole.items() {
        let inside = camino::Utf8Path::new(d.span.file.as_str())
            .canonicalize_utf8()
            .map(|p| p.starts_with(&here))
            .unwrap_or(false);
        if inside {
            mine.push(d.clone());
        }
    }
    mine.borrow_sources_from(&whole);
    mine.sort();

    let errors = mine.error_count();
    let warnings = mine.warning_count();
    if !mine.is_empty() {
        out_raw!("{}", mine.render());
    }
    if !quiet {
        match (errors, warnings) {
            (0, 0) => out!(
                "OK — {agent} loaded cleanly, checked inside {root} so its tools and \
                 policies could be found."
            ),
            (0, w) => out!("OK — {agent} loaded with {w} warning(s)."),
            (e, 0) => out!("{e} problem(s) found in {agent}. Nothing was run."),
            (e, w) => out!("{e} problem(s) and {w} warning(s) found in {agent}."),
        }
    }
    Ok(if errors > 0 { 1 } else { 0 })
}

/// `pact waits` — every wait this tree can produce, as data.
///
/// §9.4 G14 tells a runtime author how to comply: *"read every outstanding
/// wait's deadline and act on the timeout action the question names, without the
/// person coming back"*, and it names `LoadReport.waits` as the list to comply
/// against. That list existed as a Rust type and nothing else — no command, no
/// emitted file, no JSON field — so a runtime not written in Rust had literally
/// no way to obtain the thing it was obliged to walk. `LoadReport::to_json`'s own
/// doc comment says it is there *"for a runtime that is not written in Rust"*;
/// this is the one hop that makes that true.
///
/// Deliberately its own command rather than a key on `pact show`. `show` prints
/// the loaded DOCUMENT — what the author wrote, expanded — and a derived list
/// mixed into it would be indistinguishable from a field somebody typed.
fn waits_cmd(path: &Utf8PathBuf, unsafe_spec: bool) -> Result<i32> {
    // VALIDATE, not merely load. Every command below `check` ran the loader
    // alone, so a tree `pact check` refuses was served as valid interop output
    // at exit 0: with `throuh: slack` in a port, `check` printed
    // *"'throuh' is not something a port can have."* and exited 1 while `waits`,
    // `show`, `card` and `discover` all exited 0 with full output. Worse, with
    // `asked-of:` deleted from a question — which `check` calls an ERROR,
    // *"names nobody to ask, so the run stops"* — `waits` handed a scheduler a
    // human-approval gate on money that nobody can answer.
    let (node, mut diags) = validate(path, unsafe_spec)?;
    let Some(root) = node.as_ref() else {
        bail!("nothing loadable found at '{path}'");
    };
    if diags.has_errors() {
        // stderr: stdout is the machine-readable list the runtime asked for, and
        // a refusal must not arrive there looking like data.
        eprint!("{}", diags.render());
        return Ok(1);
    }
    let report = pact_loader::report::LoadReport::of(root, &mut diags);
    // Warnings the report itself found go to stderr, so the JSON on stdout stays
    // machine-readable for the runtime that asked for it.
    diags.sort();
    if !diags.is_empty() {
        eprint!("{}", diags.render());
    }
    out!("{}", serde_json::to_string_pretty(&report.to_json())?);
    Ok(0)
}

/// D2/AC-6.1: the runtime finds agents by walking the tree. No registration
/// step, no build artifact, no `.pact/` dependency.
fn discover_cmd(path: &Utf8PathBuf, unsafe_spec: bool) -> Result<i32> {
    let roots = discover::find_workspaces(path, 6);
    let mut out = Vec::new();
    for root in &roots {
        // Validated as well as loaded. `discover` publishes `"runnable": true`
        // for a tree, and it said so for trees `pact check` refuses.
        if let Ok((_, d)) = &validate(root, unsafe_spec)
            && d.has_errors()
        {
            eprintln!("skipping {root}: {} problem(s)", d.error_count());
            continue;
        }
        let mut diags = Diagnostics::new();
        if let Some(found) = discover::load(root, &mut diags) {
            if diags.has_errors() {
                eprintln!("skipping {root}: {} problem(s)", diags.error_count());
                continue;
            }
            out.push(discover::inventory(&found));
        }
    }
    out!("{}", serde_json::to_string_pretty(&serde_json::Value::Array(out))?);
    Ok(0)
}

fn card_cmd(agent: &str, root: &Utf8PathBuf, unsafe_spec: bool) -> Result<i32> {
    if agent.is_empty() {
        eprint!(
            "{}",
            refuse(
                "cli/no-agent-named",
                "`pact card` was not told which agent to publish a card for.".into(),
                "Write it as `pact card <agent> [PATH]` — for example \
                 `pact card refund-desk examples/refund-desk`."
                    .into(),
            )
            .render()
        );
        return Ok(2);
    }
    // The card is what another system reads INSTEAD of the tree. It built a
    // `Diagnostics` and threw it away unrendered, so a tree `pact check` refuses
    // was published as a valid A2A card at exit 0.
    let (_, diags) = validate(root, unsafe_spec)?;
    if diags.has_errors() {
        eprint!("{}", diags.render());
        return Ok(1);
    }
    let mut load_diags = Diagnostics::new();
    let Some(found) = discover::load(root, &mut load_diags) else {
        bail!("nothing loadable at '{root}'");
    };
    match discover::agent_card(&found, agent, "https://agents.local") {
        Some(card) => {
            out!("{}", serde_json::to_string_pretty(&card)?);
            Ok(0)
        }
        None => {
            let mut known: Vec<String> = found
                .document
                .get("agents")
                .and_then(pact_doc::Node::as_map)
                .map(|m| m.keys().cloned().collect())
                .unwrap_or_default();
            known.sort();
            let fix = if known.is_empty() {
                format!(
                    "This tree has no agents at all — add one at \
                     `{root}/agents/<name>/agent.yaml`."
                )
            } else {
                format!("Change it to one of: {}.", known.join(", "))
            };
            eprint!(
                "{}",
                refuse(
                    "cli/no-such-agent",
                    format!("there is no agent named '{agent}' in {root}."),
                    fix,
                )
                .render()
            );
            Ok(2)
        }
    }
}

fn show(path: &Utf8PathBuf, unsafe_spec: bool) -> Result<i32> {
    // Validated, for the reason `waits_cmd` gives: every adapter in this
    // repository reads its document through `pact show`, so a tree that only
    // `check` refuses is a tree every adapter accepts.
    let (node, diags) = validate(path, unsafe_spec)?;
    if diags.has_errors() {
        eprint!("{}", diags.render());
        return Ok(1);
    }
    match node {
        Some(n) => {
            out!("{}", serde_json::to_string_pretty(&n.to_json())?);
            Ok(0)
        }
        None => bail!("nothing loadable found at '{path}'"),
    }
}
