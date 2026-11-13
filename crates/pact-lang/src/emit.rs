//! Writing a value as a setting — `key: value`, in YAML.
//!
//! This is the form that can say anything, and the one every other way of
//! writing a line falls back to. Two modes: the ordinary one writes text the
//! way a person would (bare where that is unambiguous, folded where it is
//! long, as a block where it runs to several lines); `safe` writes every piece
//! of text in double quotes on one line, which is ugly and cannot be misread.
//!
//! Nothing here decides whether what it wrote reads back as what it was given.
//! The caller does, by reading it back (`write.rs`), and asks again in `safe`
//! mode when it does not.

use pact_doc::{Node, Value};

/// How wide a line of writing is allowed to get before it is folded.
const WIDTH: usize = 88;

/// Something that cannot be written as text at all: a reference to a file's
/// bytes, or a folder carried as files. Those stay as files.
#[derive(Debug)]
pub struct StaysAFile;

/// `key` as it has to be written on the left of a colon.
pub fn key(key: &str) -> String {
    let bare = !key.is_empty()
        && key
            .chars()
            .next()
            .is_some_and(|c| c.is_ascii_alphabetic() || c == '_')
        && key
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || matches!(c, '_' | '-' | '.' | '/'))
        && !matches!(
            key,
            "true" | "True" | "TRUE" | "false" | "False" | "FALSE" | "null" | "Null" | "NULL"
        );
    if bare { key.to_string() } else { quoted(key) }
}

/// Text in double quotes, on one line, with everything awkward escaped.
pub fn quoted(text: &str) -> String {
    let mut out = String::with_capacity(text.len() + 2);
    out.push('"');
    for c in text.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\t' => out.push_str("\\t"),
            '\r' => out.push_str("\\r"),
            '\u{0}' => out.push_str("\\0"),
            c if (c as u32) < 0x20 || c == '\u{7f}' => {
                out.push_str(&format!("\\x{:02x}", c as u32));
            }
            '\u{85}' | '\u{a0}' | '\u{2028}' | '\u{2029}' | '\u{feff}' => {
                out.push_str(&format!("\\u{:04x}", c as u32));
            }
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

/// Can this text be written bare after `key: ` and be read back as itself?
///
/// Conservative on purpose: a false "no" costs a pair of quotes, a false "yes"
/// costs a round trip.
fn bare(text: &str) -> bool {
    if text.is_empty() || text != text.trim() {
        return false;
    }
    let first = text.chars().next().unwrap_or(' ');
    if "-?:,[]{}#&*!|>'\"%@`~=<".contains(first) {
        return false;
    }
    if text.contains(": ")
        || text.contains(" #")
        || text.ends_with(':')
        || text.chars().any(|c| c.is_control())
    {
        return false;
    }
    // Whether what is left would be taken for a number, a yes/no or nothing
    // is the reader's own to say, so it is asked rather than guessed at:
    // `30d` is text and `30` is not, and no rule written here would stay
    // right about that for long.
    reads_back(text, &Value::Str(text.to_string()))
}

/// Does `written`, after `k: `, read back as exactly `expected`?
fn reads_back(written: &str, expected: &Value) -> bool {
    let file = camino::Utf8Path::new("written.yaml");
    pact_doc::parse_yaml(&format!("k: {written}\n"), file)
        .ok()
        .and_then(|n| n.get("k").map(|v| same(&v.value, expected)))
        .unwrap_or(false)
}

fn same(a: &Value, b: &Value) -> bool {
    match (a, b) {
        (Value::List(x), Value::List(y)) => {
            x.len() == y.len() && x.iter().zip(y).all(|(p, q)| same(&p.value, &q.value))
        }
        (Value::Map(x), Value::Map(y)) => {
            x.len() == y.len()
                && x.iter().all(|(k, e)| y.get(k).is_some_and(|f| same(&e.node.value, &f.node.value)))
        }
        _ => a == b,
    }
}

/// A short list of plain values, or a short set of them, on one line:
/// `[tags, the-agent]`, `{ tool: payments/issue-refund, arg: amount }`.
/// `None` when it would not fit, or would not read back.
fn flow(node: &Node, room: usize) -> Option<String> {
    let plain = |n: &Node| match &n.value {
        Value::Str(s) if s.contains([',', '[', ']', '{', '}', '\n']) || s.is_empty() => None,
        Value::Str(_) | Value::Int(_) | Value::Bool(_) => inline(n, false).ok().flatten(),
        _ => None,
    };
    let text = match &node.value {
        Value::List(items) if !items.is_empty() => {
            let parts: Vec<String> = items.iter().map(plain).collect::<Option<_>>()?;
            format!("[{}]", parts.join(", "))
        }
        Value::Map(m) if !m.is_empty() && m.len() <= 4 => {
            let parts: Vec<String> = m
                .iter()
                .map(|(k, e)| Some(format!("{}: {}", key(k), plain(&e.node)?)))
                .collect::<Option<_>>()?;
            format!("{{ {} }}", parts.join(", "))
        }
        _ => return None,
    };
    (text.len() <= room && reads_back(&text, &node.value)).then_some(text)
}

/// A value that fits on the line after `key: `, or `None` when it needs lines
/// of its own.
fn inline(node: &Node, safe: bool) -> Result<Option<String>, StaysAFile> {
    Ok(Some(match &node.value {
        Value::Null => "null".to_string(),
        Value::Bool(b) => b.to_string(),
        Value::Int(i) => i.to_string(),
        Value::Float(f) => {
            let s = format!("{f:?}");
            if s.contains(['.', 'e', 'E']) { s } else { format!("{s}.0") }
        }
        // Several lines that could be a block were written as one by
        // `setting` before it asked here; what reaches this is the rest.
        Value::Str(s) => {
            if !safe && !s.contains('\n') && bare(s) { s.clone() } else { quoted(s) }
        }
        Value::List(items) if items.is_empty() => "[]".to_string(),
        Value::Map(m) if m.is_empty() => "{}".to_string(),
        Value::List(_) | Value::Map(_) => return Ok(None),
        Value::File(_) | Value::Payload(_) => return Err(StaysAFile),
    }))
}

/// Can several lines of text be written as a `|` block and read back?
///
/// The reader trims the END of a block, so text that ends in white space is
/// not one; and a first line that is blank or indented would need an
/// indentation marker nobody should have to read.
pub fn blockable(text: &str) -> bool {
    text.contains('\n')
        && text == text.trim_end()
        && !text.starts_with([' ', '\n', '\t'])
        && !text.contains('\r')
        && !text.contains('\t')
        && !text.chars().any(|c| c.is_control() && c != '\n')
        && text.lines().all(|l| l == l.trim_end())
}

/// Can one long line be folded over several with `>-` and read back?
fn foldable(text: &str) -> bool {
    !text.contains('\n')
        && text == text.trim()
        && !text.contains("  ")
        && !text.chars().any(|c| c.is_control())
        && text.contains(' ')
}

fn fold(text: &str, width: usize) -> Vec<String> {
    let mut lines = Vec::new();
    let mut line = String::new();
    for word in text.split(' ') {
        if !line.is_empty() && line.len() + 1 + word.len() > width {
            lines.push(std::mem::take(&mut line));
        }
        if !line.is_empty() {
            line.push(' ');
        }
        line.push_str(word);
    }
    if !line.is_empty() {
        lines.push(line);
    }
    lines
}

/// Write `key: value` at `indent`, on as many lines as it takes.
pub fn setting(
    out: &mut String,
    name: &str,
    node: &Node,
    indent: usize,
    safe: bool,
) -> Result<(), StaysAFile> {
    let pad = " ".repeat(indent);
    let k = key(name);
    if let Value::Str(s) = &node.value
        && !safe
    {
        if blockable(s) {
            out.push_str(&format!("{pad}{k}: |\n"));
            block_lines(out, s, indent + 2);
            return Ok(());
        }
        if pad.len() + k.len() + 2 + s.len() > WIDTH && foldable(s) && bare_fold(s) {
            out.push_str(&format!("{pad}{k}: >-\n"));
            for line in fold(s, WIDTH.saturating_sub(indent + 2).max(40)) {
                out.push_str(&format!("{pad}  {line}\n"));
            }
            return Ok(());
        }
    }
    if !safe
        && matches!(node.value, Value::List(_))
        && let Some(v) = flow(node, WIDTH.saturating_sub(pad.len() + k.len() + 2))
    {
        out.push_str(&format!("{pad}{k}: {v}\n"));
        return Ok(());
    }
    match inline(node, safe)? {
        Some(v) => out.push_str(&format!("{pad}{k}: {v}\n")),
        None => {
            out.push_str(&format!("{pad}{k}:\n"));
            nested(out, node, indent + 2, safe)?;
        }
    }
    Ok(())
}

/// A folded line must not start a continuation with something the reader
/// takes for structure.
fn bare_fold(text: &str) -> bool {
    !text.split(' ').any(|w| w.starts_with('#'))
}

/// The lines of a text block, each at `indent`; blank lines stay blank.
pub fn block_lines(out: &mut String, text: &str, indent: usize) {
    let pad = " ".repeat(indent);
    for line in text.split('\n') {
        if line.is_empty() {
            out.push('\n');
        } else {
            out.push_str(&format!("{pad}{line}\n"));
        }
    }
}

/// The lines beneath `key:` for a list or a set of settings.
fn nested(out: &mut String, node: &Node, indent: usize, safe: bool) -> Result<(), StaysAFile> {
    let pad = " ".repeat(indent);
    match &node.value {
        Value::Map(m) => {
            for (k, e) in m {
                setting(out, k, &e.node, indent, safe)?;
            }
        }
        Value::List(items) => {
            for item in items {
                if !safe
                    && matches!(item.value, Value::Map(_))
                    && let Some(v) = flow(item, WIDTH.saturating_sub(indent + 2))
                {
                    out.push_str(&format!("{pad}- {v}\n"));
                    continue;
                }
                match &item.value {
                    Value::Map(m) if !m.is_empty() => {
                        let mut inner = String::new();
                        for (k, e) in m {
                            setting(&mut inner, k, &e.node, indent + 2, safe)?;
                        }
                        // The first setting sits on the `- ` line.
                        out.push_str(&pad);
                        out.push_str("- ");
                        out.push_str(&inner[indent + 2..]);
                    }
                    Value::List(inner) if !inner.is_empty() => {
                        // A list inside a list is rare enough to be written
                        // the one way that is never ambiguous: as JSON, which
                        // the reader takes as it stands.
                        assert_no_files(item)?;
                        out.push_str(&format!("{pad}- {}\n", item.to_json()));
                    }
                    _ => {
                        let v = inline(item, safe)?.unwrap_or_else(|| "null".to_string());
                        out.push_str(&format!("{pad}- {v}\n"));
                    }
                }
            }
        }
        _ => unreachable!("`inline` wrote everything that is not a list or a set of settings"),
    }
    Ok(())
}

fn assert_no_files(node: &Node) -> Result<(), StaysAFile> {
    match &node.value {
        Value::File(_) | Value::Payload(_) => Err(StaysAFile),
        Value::List(items) => items.iter().try_for_each(assert_no_files),
        Value::Map(m) => m.values().try_for_each(|e| assert_no_files(&e.node)),
        _ => Ok(()),
    }
}

/// A single-line value as it is written INSIDE a sentence — bare when it
/// reads back as itself, in double quotes otherwise.
pub fn word(node: &Node) -> Option<String> {
    match &node.value {
        Value::Str(s) if s.contains('\n') => None,
        Value::Str(_) | Value::Int(_) | Value::Float(_) | Value::Bool(_) => {
            inline(node, false).ok().flatten()
        }
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use camino::Utf8Path;
    use pact_doc::parse_yaml;

    fn back(text: &str) -> serde_json::Value {
        parse_yaml(text, Utf8Path::new("t.yaml")).unwrap().to_json()
    }

    #[test]
    fn text_that_could_be_misread_is_quoted_and_reads_back() {
        for s in [
            "plain words",
            "yes",
            "no",
            "true",
            "null",
            "12",
            "1e3",
            "0x1f",
            "- a dash first",
            "a: colon inside",
            "ends with colon:",
            "has a # hash",
            " leading space",
            "trailing space ",
            "",
            "quote \" inside",
            "back\\slash",
            "tab\there",
            "200 USD",
            "30d",
            "one of approved, declined",
            "https://example.com/a?b=c",
            "@mention",
            "100%",
            "été",
        ] {
            for safe in [false, true] {
                let mut out = String::new();
                let node = Node::str(s, pact_diag::Span::whole_file("t"));
                setting(&mut out, "k", &node, 0, safe).unwrap();
                assert_eq!(back(&out), serde_json::json!({ "k": s }), "{out:?} (safe={safe})");
            }
        }
    }

    #[test]
    fn long_and_many_lined_text_reads_back() {
        let long = "word ".repeat(60).trim().to_string();
        let lines = "First line.\n\n# A heading\n  indented\nlast: line";
        for s in [long.as_str(), lines, "ends with newline\n", "\nstarts blank", "a\n \nb"] {
            let mut out = String::new();
            let node = Node::str(s, pact_diag::Span::whole_file("t"));
            setting(&mut out, "k", &node, 2, false).unwrap();
            assert_eq!(back(&out), serde_json::json!({ "k": s }), "{out}");
        }
    }

    #[test]
    fn nesting_reads_back() {
        let text = "a:\n  - x: 1\n    y: [1, [2, 3]]\n    z: {}\n  - plain\n  - - 1\n    - two\nb:\n  c:\n    d: 1.5\n    e: []\n\"odd key\": yes\n";
        let node = parse_yaml(text, Utf8Path::new("t.yaml")).unwrap();
        for safe in [false, true] {
            let mut out = String::new();
            for (k, e) in node.as_map().unwrap() {
                setting(&mut out, k, &e.node, 0, safe).unwrap();
            }
            assert_eq!(back(&out), node.to_json(), "{out}");
        }
    }
}
