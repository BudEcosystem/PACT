//! The table in `examples/refund-desk/README.md` is a map of the worked
//! example's tree, and it is the first thing a new author reads to learn what
//! shape a PACT system has. Nothing was checking that it described the tree it
//! sits in, and it had drifted in both directions at once:
//!
//! * it named `skills/refund-policy.md`, a file that has not existed since
//!   skills became packages — so the one row about the written policy pointed at
//!   nothing, and hid the fact that a skill is a FOLDER with `references/` and
//!   `scripts/` beside its `SKILL.md`;
//! * it had no row at all for `context-policies/`, `interceptors/`, `ports/`,
//!   `resources/`, `schedules/`, `watch/`, `policies/redaction.yaml`,
//!   `agents/refund-desk/teamwork.yaml` or `agents/refund-desk/run-inputs.yaml`
//!   — several of which the README's own later prose discusses, so the reader
//!   met a folder in a sentence that the map said was not there.
//!
//! Both halves are the same failure and neither is caught by anything else:
//! `pact check` reads the tree and never reads the README, so prose about the
//! tree can say whatever it likes. Hence both directions are held here. A row
//! naming a path that is not there is a dead end for a reader who cannot grep;
//! a file with no row is a capability nobody is ever shown.
//!
//! Held for the same reason `deliberate_refusals.rs` holds `50-NOT-COPIED.md`:
//! a prose document decays silently, and the only thing that stops it is a test
//! that fails.
//!
//! **The same tree is drawn a second time**, in `docs/20-ARCHITECTURE-DRAFT.md`
//! §11.1, above a headline file count. §12.1's own gate table said of it:
//! *"NOTHING asserts it … the block is regenerated from `find
//! examples/refund-desk -type f` by hand; `the_worked_example_readme_matches_
//! the_tree.rs` walks the tree in both directions for the example's OWN README,
//! and extending it to this fence is the open work."* That is this file, and
//! the four tests at the bottom are that extension. The fence had already
//! drifted: it printed a count one higher than the tree it draws.

use std::path::{Path, PathBuf};

fn repo() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn example_root() -> PathBuf {
    repo().join("examples/refund-desk")
}

fn readme() -> String {
    let p = example_root().join("README.md");
    std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()))
}

/// Every file in the worked example, as a path relative to its root.
///
/// `.pact/` is skipped. It is derived, it is in `.gitignore`, and D2 says
/// deleting it must be harmless — so it is not part of the tree an author is
/// shown, and a row describing it would be a row describing an output.
fn files() -> Vec<String> {
    let root = example_root();
    let mut out = Vec::new();
    walk(&root, &root, &mut out);
    out.sort();
    assert!(
        out.len() > 30,
        "only {} files found — the walk is wrong, not the tree",
        out.len()
    );
    out
}

fn walk(root: &Path, dir: &Path, out: &mut Vec<String>) {
    for entry in std::fs::read_dir(dir).unwrap().flatten() {
        let path = entry.path();
        let name = entry.file_name();
        if name == ".pact" {
            continue;
        }
        if path.is_dir() {
            walk(root, &path, out);
        } else {
            out.push(
                path.strip_prefix(root)
                    .unwrap()
                    .to_string_lossy()
                    .replace('\\', "/"),
            );
        }
    }
}

/// The backticked spans in the left-hand cell of every row of the table under
/// `## What each file is for`, in the order the reader meets them.
fn table_patterns() -> Vec<String> {
    let text = readme();
    let mut inside = false;
    let mut out = Vec::new();
    for line in text.lines() {
        if line.starts_with("## What each file is for") {
            inside = true;
            continue;
        }
        if inside && line.starts_with("## ") {
            break;
        }
        if !inside || !line.starts_with('|') {
            continue;
        }
        let Some(cell) = line.split('|').nth(1) else {
            continue;
        };
        out.extend(backticked(cell));
    }
    // Deliberately low. This guard exists for one thing only — a parser that has
    // stopped finding rows at all, which would make both tests below pass
    // vacuously. It must NEVER be the assertion that fires when the table is
    // merely incomplete: set at a plausible row count it swallows the finding
    // and reports "the parser is wrong" at an author who typed nothing wrong,
    // which is a diagnostic that names no file, no line and no fix. Held at 20
    // for one run, it did exactly that against the table this test was written
    // to catch.
    assert!(
        out.len() >= 5,
        "only {} paths parsed out of the table — the parser is broken, not the table",
        out.len()
    );
    out
}

fn backticked(text: &str) -> Vec<String> {
    text.split('`')
        .skip(1)
        .step_by(2)
        .map(str::to_string)
        .collect()
}

/// Does `pattern`, as an author would read it, describe `path`?
///
/// Three spellings, all of which the table already used before this test
/// existed, so none of them is a new notation an author has to learn:
/// `evals/` is everything under a folder, `tools/*.yaml` is every file of one
/// sort directly inside one, and anything else is one exact file.
fn describes(pattern: &str, path: &str) -> bool {
    if let Some(dir) = pattern.strip_suffix('/') {
        return path.starts_with(&format!("{dir}/"));
    }
    if let Some((pre, post)) = pattern.split_once('*') {
        return path.len() >= pre.len() + post.len()
            && path.starts_with(pre)
            && path.ends_with(post)
            && !path[pre.len()..path.len() - post.len()].contains('/');
    }
    pattern == path
}

/// Is `span` a path the tree really has, allowing a sentence to name the tail
/// of one? `references/` is the folder the row above it spells in full as
/// `skills/refund-policy/references/`, and repeating the prefix mid-sentence
/// would read like a different folder rather than the same one.
fn somewhere_in_the_tree(span: &str, files: &[String]) -> bool {
    let want = span.trim_end_matches('/');
    files.iter().any(|f| {
        f.as_str() == want
            || f.starts_with(&format!("{want}/"))
            || f.ends_with(&format!("/{want}"))
            || f.contains(&format!("/{want}/"))
    })
}

/// What to tell an author whose row points at nothing — a path that IS there
/// and is plainly the one they meant, so the fix is a line they can type.
fn nearest(missing: &str, files: &[String]) -> Option<String> {
    let stem = missing.rsplit_once('.').map_or(missing, |(s, _)| s);
    if let Some(hit) = files.iter().find(|f| f.starts_with(&format!("{stem}/"))) {
        return Some(hit.clone());
    }
    let base = Path::new(missing).file_name()?.to_str()?.to_string();
    files
        .iter()
        .find(|f| f.ends_with(&format!("/{base}")))
        .cloned()
}

#[test]
fn every_path_the_worked_examples_table_names_is_a_path_that_is_really_there() {
    // The half that was wrong: `skills/refund-policy.md` was a row about the
    // written refund policy pointing at a file the tree has not had since
    // skills became packages.
    let files = files();
    let mut dead = Vec::new();
    for pattern in table_patterns() {
        if files.iter().any(|f| describes(&pattern, f)) {
            continue;
        }
        let fix = match nearest(&pattern, &files) {
            Some(real) => format!("write `{real}` instead"),
            None => "delete the row, or add the file it describes".to_string(),
        };
        dead.push(format!(
            "`{pattern}` is named by the table and is not in the tree\n    fix: {fix}"
        ));
    }
    assert!(
        dead.is_empty(),
        "examples/refund-desk/README.md, the table under `## What each file is for`, \
         sends the reader to {} path(s) that do not exist:\n  {}",
        dead.len(),
        dead.join("\n  ")
    );
}

#[test]
fn every_file_in_the_worked_example_is_named_by_a_row_in_its_table() {
    // The other half, and the one that cost more: the table had no row for six
    // whole folders — `context-policies/`, `interceptors/`, `ports/`,
    // `resources/`, `schedules/`, `watch/` — nor for `teamwork.yaml`,
    // `run-inputs.yaml` or `policies/redaction.yaml`. A reader learning the
    // shape of a PACT system from this table came away believing most of it did
    // not exist, while the README's own later prose talked about it.
    //
    // `README.md` is the map and not a thing on it, so it is the one exclusion.
    let patterns = table_patterns();
    let mut unmapped = Vec::new();
    for file in files() {
        if file == "README.md" || patterns.iter().any(|p| describes(p, &file)) {
            continue;
        }
        unmapped.push(format!(
            "`{file}` is in the tree and in no row\n    fix: add a row to \
             examples/refund-desk/README.md:  | `{file}` | one plain sentence saying \
             what it says |"
        ));
    }
    assert!(
        unmapped.is_empty(),
        "examples/refund-desk/README.md says it lists what each file is for, and {} \
         file(s) are missing from it:\n  {}",
        unmapped.len(),
        unmapped.join("\n  ")
    );
}

#[test]
fn every_path_the_worked_examples_prose_names_is_a_path_that_is_really_there() {
    // The table is not the only place the README points at the tree — the
    // sections after it name `questions/`, `references/`, `scripts/` and
    // `agents/refund-desk/instructions.md` in ordinary sentences, and those rot
    // exactly the same way a row does.
    //
    // Fenced blocks are skipped: they are commands run from the repository root
    // and their paths are relative to somewhere else. Table rows are skipped
    // because the two tests above already hold them, to a stricter rule.
    let files = files();
    let mut fenced = false;
    let mut dead = Vec::new();
    for (n, line) in readme().lines().enumerate() {
        if line.starts_with("```") {
            fenced = !fenced;
            continue;
        }
        if fenced || line.starts_with('|') {
            continue;
        }
        for span in backticked(line) {
            // Only spans that are plainly a path. `instructions:` is a setting
            // and `Refund Desk` is a name; neither is one of these.
            if !span.contains('/') || span.ends_with(':') {
                continue;
            }
            if !somewhere_in_the_tree(&span, &files) {
                dead.push(format!("line {}: `{span}`", n + 1));
            }
        }
    }
    assert!(
        dead.is_empty(),
        "examples/refund-desk/README.md points its reader at {} path(s) that are not in \
         the tree:\n  {}\n  fix: name a path that exists, or add the file",
        dead.len(),
        dead.join("\n  ")
    );
}

// ---------------------------------------------------------------------------
// `docs/20-ARCHITECTURE-DRAFT.md` §11.1 — the same tree, drawn a second time
// ---------------------------------------------------------------------------

fn architecture_draft() -> String {
    let p = repo().join("docs/20-ARCHITECTURE-DRAFT.md");
    std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()))
}

/// The lines of the fenced block under `### 11.1` that draws the tree, with the
/// line number each is on, so a diagnostic can send an editor straight there.
///
/// §11.1 opens with a `$ pact check` fence and then the tree; the tree is the
/// fence whose header line ends `<n> files`, which is also the number this
/// file's first test recomputes, so one property identifies the block.
fn tree_block() -> Vec<(usize, String)> {
    let text = architecture_draft();
    let mut inside_section = false;
    let mut fenced = false;
    let mut block: Vec<(usize, String)> = Vec::new();
    for (n, line) in text.lines().enumerate() {
        if line.starts_with("### 11.1") {
            inside_section = true;
            continue;
        }
        if !inside_section {
            continue;
        }
        if line.starts_with("## ") {
            break;
        }
        if line.starts_with("```") {
            if fenced && block.iter().any(|(_, l)| l.trim_end().ends_with("files")) {
                return block;
            }
            fenced = !fenced;
            block.clear();
            continue;
        }
        if fenced {
            block.push((n + 1, line.to_string()));
        }
    }
    panic!(
        "docs/20-ARCHITECTURE-DRAFT.md §11.1 has no fenced block opening with a line ending \
         `<n> files`, so this gate cannot find the tree it holds. Restore that header line — \
         §12.1 lists the count as a CI gate and a gate that cannot find its subject is worse \
         than no gate."
    )
}

/// One leaf of the drawn tree, or a whole directory the drawing covers without
/// naming every file in it.
enum Drawn {
    /// A path the block spells out. It has to be in the tree.
    File(String),
    /// `cases/01…06.yaml` — an ellipsis stands for "and the rest of them", so
    /// the folder is covered and the *count* line is what holds its size.
    Folder(String),
}

/// The drawn tree, resolved into paths relative to `examples/refund-desk`.
///
/// The block is a box-drawing tree, so depth is the prefix width — four columns
/// per level, `│   ` or four spaces — and a label ending in `/` opens the level
/// below it. Three shorthands the block already used are honoured, because they
/// are what makes it readable and none is a notation invented here:
/// `tools/{a, b}` (siblings under one folder), `a.yaml, b.yaml` (siblings in
/// the folder above), and `…` (the rest of a folder).
fn drawn_paths() -> Vec<(usize, Drawn)> {
    let mut stack: Vec<String> = Vec::new();
    let mut out = Vec::new();
    for (n, raw) in tree_block() {
        let line = raw.split('←').next().unwrap_or(&raw).trim_end();
        if line.trim().is_empty() || line.trim_start().starts_with('#') {
            continue;
        }
        let Some(cut) = line.find("├── ").or_else(|| line.find("└── ")) else {
            continue;
        };
        let depth = line[..cut].chars().count() / 4;
        let label = line[cut + "├── ".len()..].trim();
        if let Some(dir) = label.strip_suffix('/') {
            stack.truncate(depth);
            stack.push(dir.to_string());
            continue;
        }
        assert!(
            depth <= stack.len(),
            "docs/20-ARCHITECTURE-DRAFT.md line {n}: `{label}` is drawn {depth} level(s) in and \
             only {} folder(s) are open above it. Indent it under the folder it belongs to, four \
             columns per level.",
            stack.len()
        );
        let prefix = if depth == 0 {
            String::new()
        } else {
            format!("{}/", stack[..depth].join("/"))
        };
        for leaf in expand(label) {
            let path = format!("{prefix}{leaf}");
            if path.contains('…') || path.contains("...") {
                let folder = path
                    .rsplit_once('/')
                    .map_or(String::new(), |(d, _)| d.to_string());
                out.push((n, Drawn::Folder(folder)));
            } else {
                out.push((n, Drawn::File(path)));
            }
        }
    }
    assert!(
        out.len() >= 20,
        "only {} paths parsed out of §11.1's tree — the parser is broken, not the block. A guard, \
         not the assertion: set at a plausible file count it would swallow the finding and blame \
         an author who typed nothing wrong.",
        out.len()
    );
    out
}

/// `ports/{a, b, c}` → three leaves; `a.yaml, b.yaml` → two; anything else → one.
fn expand(label: &str) -> Vec<String> {
    if let Some((head, rest)) = label.split_once('{')
        && let Some(inner) = rest.strip_suffix('}')
    {
        return inner
            .split(',')
            .map(|s| format!("{head}{}", s.trim()))
            .collect();
    }
    label
        .split(',')
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .collect()
}

#[test]
fn the_file_count_the_architecture_draft_prints_is_the_number_of_files_in_the_tree() {
    // §12.1's gate table lists this row and says of it, honestly, that NOTHING
    // asserts it. Nothing did, and the number was already wrong: the block said
    // 44 over a tree of 43. §11.1 is the page that argues D14 — a non-technical
    // author builds the whole system — and the headline count is the single
    // number a reader quotes when deciding whether that is real, which is the
    // argument [R5] makes against R3 in the note directly beneath it.
    let files = files();
    let (line, header) = tree_block()
        .into_iter()
        .find(|(_, l)| l.trim_end().ends_with("files"))
        .expect("held by tree_block()");
    let printed: usize = header
        .trim_end()
        .trim_end_matches(" files")
        .rsplit(' ')
        .next()
        .and_then(|s| s.parse().ok())
        .unwrap_or_else(|| {
            panic!(
                "docs/20-ARCHITECTURE-DRAFT.md line {line}: §11.1's tree opens {header:?} and the \
                 count must be a number. Write:  refund-desk/                             {} files",
                files.len()
            )
        });
    assert_eq!(
        printed,
        files.len(),
        "docs/20-ARCHITECTURE-DRAFT.md line {line}: §11.1 says the worked example is {printed} \
         files and `find examples/refund-desk -type f` finds {}. \
         fix: change `{printed} files` to `{} files` on that line",
        files.len(),
        files.len()
    );

    // The same number is quoted a second time, in §1.1 — the first tree a reader
    // of this document ever meets, headed with the command it was regenerated
    // from. It had drifted identically, which is the argument for recomputing
    // every quotation rather than the one the gate row happened to name: a
    // number nobody recomputes decays wherever it is written.
    let mut quoted = 0;
    for (n, line) in architecture_draft().lines().enumerate() {
        if !line.starts_with('#') || !line.contains("examples/refund-desk -type f") {
            continue;
        }
        for (i, word) in line.split_whitespace().enumerate() {
            if !word.starts_with("files") || i == 0 {
                continue;
            }
            let said = line.split_whitespace().nth(i - 1).unwrap_or("");
            let Ok(said) = said.parse::<usize>() else {
                continue;
            };
            quoted += 1;
            assert_eq!(
                said,
                files.len(),
                "docs/20-ARCHITECTURE-DRAFT.md line {}: this line says the worked example is \
                 {said} files and `find examples/refund-desk -type f` finds {}. \
                 fix: change `{said} files` to `{} files` on that line",
                n + 1,
                files.len(),
                files.len()
            );
        }
    }
    assert!(
        quoted >= 1,
        "no line of docs/20-ARCHITECTURE-DRAFT.md quotes a file count beside \
         `find examples/refund-desk -type f` any more. §1.1's tree carried one; if it was \
         removed on purpose, delete this half of the test rather than leaving it blind."
    );
}

#[test]
fn every_path_the_architecture_drafts_tree_block_draws_is_a_file_that_is_really_there() {
    // The direction the block's own header comment records as having failed
    // before: "the block that stood here named ten paths that do not exist".
    let files = files();
    let mut dead = Vec::new();
    for (line, drawn) in drawn_paths() {
        let (what, ok) = match &drawn {
            Drawn::File(p) => (p.clone(), files.contains(p)),
            Drawn::Folder(d) => (
                format!("{d}/"),
                files.iter().any(|f| f.starts_with(&format!("{d}/"))),
            ),
        };
        if !ok {
            let fix = match nearest(what.trim_end_matches('/'), &files) {
                Some(real) => format!("write `{real}` instead"),
                None => "delete the line, or add the file it draws".to_string(),
            };
            dead.push(format!("line {line}: `{what}`\n    fix: {fix}"));
        }
    }
    assert!(
        dead.is_empty(),
        "docs/20-ARCHITECTURE-DRAFT.md §11.1 draws {} path(s) that are not in \
         examples/refund-desk:\n  {}",
        dead.len(),
        dead.join("\n  ")
    );
}

#[test]
fn every_file_in_the_worked_example_is_drawn_in_the_architecture_drafts_tree_block() {
    // And the other direction, which the same header comment records as the
    // other half of the same drift: the block "omitted every kind the parity
    // round added". A kind that exists in the tree and not in §11.1 is a
    // capability the document's own worked example never shows.
    let drawn = drawn_paths();
    let mut missing = Vec::new();
    for file in files() {
        let covered = drawn.iter().any(|(_, d)| match d {
            Drawn::File(p) => *p == file,
            Drawn::Folder(dir) => file.starts_with(&format!("{dir}/")),
        });
        if !covered {
            missing.push(format!(
                "`{file}` is in the tree and in no line of the block\n    fix: add it to \
                 docs/20-ARCHITECTURE-DRAFT.md §11.1, and change the `<n> files` header to match"
            ));
        }
    }
    assert!(
        missing.is_empty(),
        "docs/20-ARCHITECTURE-DRAFT.md §11.1 says it was regenerated from \
         `find examples/refund-desk -type f`, and {} file(s) are not in it:\n  {}",
        missing.len(),
        missing.join("\n  ")
    );
}

#[test]
fn nothing_the_tree_block_lists_as_deliberately_absent_is_present() {
    // The block ends on a list headed "NOT in the tree, and this is the point" —
    // `models/catalog.yaml` is distribution-supplied, `schedules/` is a kind
    // that was folded away by R44. Each line is a claim about the tree, and a
    // claim about an ABSENCE rots the moment somebody adds the thing back: the
    // reader is then told that a folder they can see does not exist, which is
    // worse than an unmentioned folder.
    let files = files();
    let mut present = Vec::new();
    let mut after_tree = false;
    for (line, raw) in tree_block() {
        if raw.contains("NOT in the tree") {
            after_tree = true;
            continue;
        }
        if !after_tree {
            continue;
        }
        let Some(body) = raw.trim().strip_prefix('#') else {
            continue;
        };
        let Some(claim) = body.split('—').next() else {
            continue;
        };
        let claim = claim.trim();
        if claim.is_empty() || !claim.contains(['/', '.']) || claim.contains(' ') {
            continue;
        }
        if let Some(hit) = files.iter().find(|f| describes(claim, f)) {
            present.push(format!(
                "line {line}: `{claim}` is listed as NOT in the tree, and `{hit}` is\n    \
                 fix: delete that line from the list, and give the file a line in the tree above it"
            ));
        }
    }
    assert!(
        present.is_empty(),
        "docs/20-ARCHITECTURE-DRAFT.md §11.1 tells its reader {} thing(s) are absent from \
         examples/refund-desk that are in it:\n  {}",
        present.len(),
        present.join("\n  ")
    );
}

#[test]
fn the_number_the_front_page_quotes_is_the_number_the_binary_prints() {
    // `README.md` opens with a command and the output it produces. It quoted
    // `448 settings` while the binary printed `468`, so the front page of the
    // project failed its own copy-paste check on line 12 — and this is the third
    // place a settings count has gone stale in prose (§7.14a quoted 467, §7.13
    // quoted 468, MOD-1 quoted 459). A number nobody recomputes is a number that
    // decays, so it is recomputed here.
    let repo = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let out = std::process::Command::new(env!("CARGO_BIN_EXE_pact"))
        .args(["check", repo.join("examples/refund-desk").to_str().unwrap()])
        .output()
        .expect("the binary runs");
    let printed = String::from_utf8_lossy(&out.stdout);
    let quoted = printed
        .split(" (")
        .nth(1)
        .and_then(|s| s.split(" settings)").next())
        .expect("`pact check` prints a settings count");

    let readme = std::fs::read_to_string(repo.join("README.md")).expect("README.md");
    assert!(
        readme.contains(&format!("({quoted} settings)")),
        "README.md quotes a settings count the binary does not print. It prints \
         `({quoted} settings)`; update the line under the first command."
    );
}
