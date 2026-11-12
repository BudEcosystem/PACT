//! Printing a document as a `.pact` file — and as a folder of YAML.
//!
//! # Why this cannot drift from the reader
//!
//! Every block is written, read back with [`crate::read`], and compared with
//! what it was written from. A block that does not come back identical is
//! written again more plainly:
//!
//! 1. **rich** — sentences where there is one, text blocks, bare words;
//! 2. **plain** — settings only, as a person would write YAML;
//! 3. **safe** — settings only, every piece of text in double quotes.
//!
//! The third can say anything the document model can hold, so the ladder
//! always ends. The consequence is that a sentence printer here only has to be
//! USUALLY right: where it is wrong about some value nobody thought of — a
//! shape with a colon in it, a name with a comma — the block is quietly
//! written as settings instead, and the round trip still holds.
//!
//! # What stays a file
//!
//! A document read from a folder can hold references to files — a knowledge
//! set's documents, a skill's scripts. Those are not text and are not written;
//! [`Written::left_as_files`] names them, and a `.pact` file beside the folders
//! they live in reads as the whole workspace (`docs/99` §4.4).

use std::collections::{BTreeMap, BTreeSet};

use camino::Utf8Path;
use pact_doc::{Entry, Map, Node, Value, canonical_string};

use crate::emit::{self, StaysAFile};
use crate::read::{default_description, read};
use crate::{SINGLES, slug, word_for};

mod flow;

/// A document as PACT-language text.
pub struct Written {
    pub text: String,
    /// The settings that are references to files and were left out, as dotted
    /// paths — `knowledge.staff-handbook.documents`.
    pub left_as_files: Vec<String>,
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Style {
    Rich,
    Plain,
    Safe,
}

const LADDER: [Style; 3] = [Style::Rich, Style::Plain, Style::Safe];

/// Print `root` as one `.pact` file.
///
/// `Err` only when the text could not be made to read back as the document —
/// which the ladder above is built to make impossible, so it is reported as
/// what it would be: a defect here, never something to print anyway.
pub fn write(root: &Node) -> Result<Written, String> {
    let mut left = Vec::new();
    let pruned = prune(root, "", &mut left)
        .filter(|n| n.as_map().is_some())
        .ok_or("the document is not a set of settings, so it is not a workspace")?;
    let text = Printer::new(&pruned).all()?;
    let back = read(&text, Utf8Path::new("written.pact"));
    if !back.diagnostics.is_empty() || canonical_string(&back.node) != canonical_string(&pruned) {
        return Err("the PACT-language text did not read back as the document it was written \
                    from — this is a defect in `pact write`, and nothing was printed"
            .to_string());
    }
    Ok(Written {
        text,
        left_as_files: left,
    })
}

/// `node` without the settings that are references to files.
fn prune(node: &Node, path: &str, left: &mut Vec<String>) -> Option<Node> {
    match &node.value {
        Value::File(_) | Value::Payload(_) => {
            left.push(path.to_string());
            None
        }
        Value::Map(m) => {
            let mut out = Map::new();
            for (k, e) in m {
                let inner = if path.is_empty() { k.clone() } else { format!("{path}.{k}") };
                if let Some(kept) = prune(&e.node, &inner, left) {
                    out.insert(
                        k.clone(),
                        Entry {
                            key_span: e.key_span.clone(),
                            node: kept,
                        },
                    );
                }
            }
            Some(Node::map(out, node.span.clone()))
        }
        Value::List(items) => {
            let mut out = Vec::new();
            let before = left.len();
            for item in items {
                match prune(item, path, left) {
                    Some(kept) => out.push(kept),
                    None => {
                        // A list with a file in it is left whole: taking one
                        // item out would change what the others are.
                        left.truncate(before);
                        left.push(path.to_string());
                        return None;
                    }
                }
            }
            Some(Node::list(out, node.span.clone()))
        }
        _ => Some(node.clone()),
    }
}

fn same(text: &str, expected: &Node) -> bool {
    let back = read(text, Utf8Path::new("written.pact"));
    back.diagnostics.is_empty() && canonical_string(&back.node) == canonical_string(expected)
}

fn at() -> pact_diag::Span {
    pact_diag::Span::whole_file("written.pact")
}

fn rooted(entries: Vec<(&str, &str, &Node)>) -> Node {
    let mut root = Map::new();
    for (collection, id, node) in entries {
        let holder = root.entry(collection.to_string()).or_insert_with(|| Entry {
            key_span: at(),
            node: Node::map(Map::new(), at()),
        });
        if let Some(m) = holder.node.as_map_mut() {
            m.insert(
                id.to_string(),
                Entry {
                    key_span: at(),
                    node: node.clone(),
                },
            );
        }
    }
    Node::map(root, at())
}

fn text_of(node: &Node) -> Option<&str> {
    node.as_str()
}

fn one_line(node: &Node) -> Option<&str> {
    text_of(node).filter(|s| !s.is_empty() && !s.contains('\n') && *s == s.trim())
}

fn a_name(text: &str) -> bool {
    !text.is_empty() && !text.contains([' ', '\n', '"', ',']) && !text.starts_with('#')
}

/// A name as it is written on a header line.
fn named(id: &str) -> String {
    if a_name(id) && !id.contains(':') { id.to_string() } else { emit::quoted(id) }
}

fn lower_first(text: &str) -> String {
    let mut c = text.chars();
    match c.next() {
        Some(f) => f.to_lowercase().collect::<String>() + c.as_str(),
        None => String::new(),
    }
}

/// The `when` sentence a reaction's signal can be written as, with the keys
/// that sentence stands for.
fn signal_sentence(map: &Map) -> Option<(String, Vec<&'static str>)> {
    let get = |k: &str| map.get(k).map(|e| &e.node);
    let present: Vec<&str> = ["event", "at", "when-this", "more-than", "topic", "judged"]
        .into_iter()
        .filter(|k| map.contains_key(*k))
        .collect();
    let the_call = || {
        let lines = get("when-this")?.as_list()?;
        let [only] = lines else { return None };
        let atom = only.as_map()?;
        (atom.len() == 1).then_some(())?;
        atom.get("tool")?.node.as_str().filter(|t| a_name(t))
    };
    let count = || match get("more-than").map(|n| &n.value) {
        Some(Value::Int(n)) if *n >= 1 => Some(*n),
        _ => None,
    };
    let moment = get("at").and_then(Node::as_str);
    match present.as_slice() {
        ["event"] => {
            let e = get("event")?.as_str().filter(|e| a_name(e))?;
            Some((format!("{e} happens"), vec!["event"]))
        }
        ["topic"] => {
            let t = get("topic")?.as_str().filter(|t| a_name(t))?;
            Some((format!("the work touches {t}"), vec!["topic"]))
        }
        ["judged"] | ["at", "judged"] => {
            (get("judged")?.as_str() == Some("yes")).then_some(())?;
            let described = get("description").and_then(one_line).unwrap_or("this happens");
            let trimmed = described.strip_suffix('.').unwrap_or(described);
            let lowered = lower_first(trimmed);
            let what = if default_description("", Some(&lowered)) == described {
                lowered
            } else {
                trimmed.to_string()
            };
            Some((format!("it looks like {what}"), vec!["judged"]))
        }
        ["at", "when-this"] if moment == Some("step.tool.before") => {
            Some((format!("the agent is about to call {}", the_call()?), vec!["at", "when-this"]))
        }
        ["at", "when-this", "more-than"] if moment == Some("step.tool.before") => Some((
            format!("the agent has called {} more than {} times", the_call()?, count()?),
            vec!["at", "when-this", "more-than"],
        )),
        ["at", "when-this"] if moment == Some("step.tool.completed") => {
            Some((format!("{} has answered", the_call()?), vec!["at", "when-this"]))
        }
        ["at", "more-than"] if moment == Some("step.run.started") => Some((
            format!("the agent has taken more than {} steps", count()?),
            vec!["at", "more-than"],
        )),
        ["at"] => {
            let said = match moment? {
                "turn.run.started" => "a turn starts",
                "step.delegate.before" => "the agent is about to ask a teammate",
                "step.message.after" => "the agent has written a step",
                _ => return None,
            };
            Some((said.to_string(), vec!["at"]))
        }
        _ => None,
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Form {
    /// `when …` at the left margin: it covers every agent.
    Everyone,
    /// `when …` inside an agent's block: that agent names it.
    Inside,
    /// `reaction <name>`, with its signal as a `when` line where it has one.
    Block,
    /// `event <name>`, the same way.
    Event,
}

struct Printer<'a> {
    root: &'a Map,
    /// How many agents list each reaction.
    listed: BTreeMap<&'a str, usize>,
}

impl<'a> Printer<'a> {
    fn new(root: &'a Node) -> Self {
        let root = root.as_map().expect("`write` checked that the document is a set of settings");
        let mut listed: BTreeMap<&str, usize> = BTreeMap::new();
        for (_, agent) in root.get("agents").and_then(|e| e.node.as_map()).into_iter().flatten() {
            for name in agent
                .node
                .get("reactions")
                .and_then(Node::as_list)
                .into_iter()
                .flatten()
                .filter_map(Node::as_str)
            {
                *listed.entry(name).or_default() += 1;
            }
        }
        Printer { root, listed }
    }

    fn reaction(&self, id: &str) -> Option<&'a Map> {
        self.root.get("reactions")?.node.get(id)?.as_map()
    }

    /// The reactions this agent lists, when every one of them can be written
    /// inside its block: listed by this agent alone, covering nobody else, and
    /// waiting for something a `when` sentence can say.
    fn inside(&self, agent: &'a Map) -> Option<Vec<&'a str>> {
        let names: Vec<&str> = agent
            .get("reactions")?
            .node
            .as_list()?
            .iter()
            .map(Node::as_str)
            .collect::<Option<_>>()?;
        let distinct: BTreeSet<&str> = names.iter().copied().collect();
        if names.is_empty() || distinct.len() != names.len() {
            return None;
        }
        for name in &names {
            let reaction = self.reaction(name)?;
            if reaction.contains_key("applies-to")
                || self.listed.get(name).copied() != Some(1)
                || signal_sentence(reaction).is_none()
            {
                return None;
            }
        }
        Some(names)
    }

    fn all(&self) -> Result<String, String> {
        let mut blocks: Vec<String> = Vec::new();
        let mut workspace = Map::new();
        let mut done: BTreeSet<String> = BTreeSet::new();

        // Agents first, because an agent's block may take reactions with it.
        let mut agents: Vec<String> = Vec::new();
        if let Some(entries) = self.blocks_of("agents") {
            for (id, entry) in entries {
                let agent = entry.node.as_map().expect("`blocks_of` returns sets of settings");
                let mut written = None;
                if let Some(names) = self.inside(agent) {
                    let mut expected = vec![("agents", id.as_str(), &entry.node)];
                    let reactions: Vec<(&str, Node)> = names
                        .iter()
                        .map(|n| (*n, Node::map(self.reaction(n).cloned().unwrap_or_default(), at())))
                        .collect();
                    expected.extend(reactions.iter().map(|(n, node)| ("reactions", *n, node)));
                    let text = self.block("agent", id, agent, Style::Rich, &names);
                    if same(&text, &rooted(expected)) {
                        done.extend(names.iter().map(|n| n.to_string()));
                        written = Some(text);
                    }
                }
                let text = match written {
                    Some(text) => text,
                    None => self.checked("agent", "agents", id, &entry.node)?,
                };
                agents.push(text);
            }
        }

        for (key, entry) in self.root {
            if key == "name" && one_line(&entry.node).is_some() {
                continue;
            }
            if key == "agents" && self.blocks_of("agents").is_some() {
                blocks.append(&mut agents);
                continue;
            }
            if let (Some(word), Some(entries)) = (word_for(key), self.blocks_of(key)) {
                for (id, e) in entries {
                    if key == "reactions" && done.contains(id) {
                        continue;
                    }
                    blocks.push(self.checked(word, key, id, &e.node)?);
                }
                continue;
            }
            if SINGLES.contains(&key.as_str()) && entry.node.as_map().is_some() {
                blocks.push(self.single(key, &entry.node)?);
                continue;
            }
            workspace.insert(key.clone(), entry.clone());
        }

        let mut out = String::new();
        let head = self.workspace(&workspace)?;
        if !head.is_empty() {
            out.push_str(&head);
        }
        for block in blocks {
            if !out.is_empty() {
                out.push('\n');
            }
            out.push_str(&block);
        }
        Ok(out)
    }

    /// The entries of a collection, when every one of them is a set of
    /// settings and so can be a block. An empty collection is a setting of the
    /// workspace: there is no block to write it as.
    fn blocks_of(&self, collection: &str) -> Option<&'a Map> {
        let entries = self.root.get(collection)?.node.as_map()?;
        (!entries.is_empty() && entries.values().all(|e| e.node.as_map().is_some()))
            .then_some(entries)
    }

    fn workspace(&self, settings: &Map) -> Result<String, String> {
        let name = self.root.get("name").map(|e| &e.node).and_then(one_line);
        if name.is_none() && settings.is_empty() {
            return Ok(String::new());
        }
        let mut expected = settings.clone();
        if let (Some(_), Some(e)) = (name, self.root.get("name")) {
            expected.insert("name".to_string(), e.clone());
        }
        let expected = Node::map(expected, at());
        for style in LADDER {
            let mut out = match name {
                Some(n) => format!("workspace {}\n", emit::quoted(n)),
                None => "workspace\n".to_string(),
            };
            if self.lines(&mut out, Kind::Plain, settings, 2, style, &[]).is_ok()
                && same(&out, &expected)
            {
                return Ok(out);
            }
        }
        Err("the workspace's own settings could not be written".to_string())
    }

    fn single(&self, word: &str, node: &Node) -> Result<String, String> {
        let settings = node.as_map().expect("checked by the caller");
        let mut root = Map::new();
        root.insert(
            word.to_string(),
            Entry {
                key_span: at(),
                node: node.clone(),
            },
        );
        let expected = Node::map(root, at());
        for style in LADDER {
            let mut out = format!("{word}\n");
            if self.lines(&mut out, Kind::Plain, settings, 2, style, &[]).is_ok()
                && same(&out, &expected)
            {
                return Ok(out);
            }
        }
        Err(format!("`{word}` could not be written"))
    }

    /// One entry of a collection, written the richest way that reads back.
    fn checked(&self, word: &str, collection: &str, id: &str, node: &Node) -> Result<String, String> {
        let settings = node.as_map().expect("`blocks_of` returns sets of settings");
        let expected = rooted(vec![(collection, id, node)]);
        for style in LADDER {
            let text = self.block(word, id, settings, style, &[]);
            if same(&text, &expected) {
                return Ok(text);
            }
        }
        Err(format!("the {word} '{id}' could not be written"))
    }

    fn block(&self, word: &str, id: &str, settings: &Map, style: Style, inside: &[&str]) -> String {
        let kind = Kind::of(word);
        if kind == Kind::Reaction && style == Style::Rich {
            let everyone = settings.get("applies-to").and_then(|e| e.node.as_str())
                == Some("every-agent");
            let form = if everyone { Form::Everyone } else { Form::Block };
            if let Some(text) = self
                .reaction_block(id, settings, form, 0)
                .or_else(|| self.reaction_block(id, settings, Form::Block, 0))
            {
                return text;
            }
        }
        if kind == Kind::Event
            && style == Style::Rich
            && let Some(text) = self.reaction_block(id, settings, Form::Event, 0)
        {
            return text;
        }
        // One figure and nothing said about it: `let refund-limit = 200 USD`.
        if word == "value"
            && style == Style::Rich
            && settings.len() == 1
            && a_name(id)
            && let Some(figure) = settings.get("value").and_then(|e| emit::word(&e.node))
        {
            return format!("let {id} = {figure}\n");
        }
        let mut out = format!("{word} {}", named(id));
        let mut rest = settings.clone();
        if kind == Kind::Agent
            && style == Style::Rich
            && let Some(shown) = settings.get("name").map(|e| &e.node).and_then(one_line)
        {
            out.push(' ');
            out.push_str(&emit::quoted(shown));
            rest.shift_remove("name");
        }
        out.push('\n');
        if self.lines(&mut out, kind, &rest, 2, style, inside).is_err() {
            // Something that stays a file was not pruned: say nothing useful,
            // and let the comparison fail this style.
            return String::new();
        }
        out
    }

    /// A reaction as a block of its own, or `None` when this form cannot say it.
    fn reaction_block(&self, id: &str, settings: &Map, form: Form, indent: usize) -> Option<String> {
        let pad = " ".repeat(indent);
        let signal = signal_sentence(settings);
        let mut skip: Vec<&str> = Vec::new();
        let mut out = String::new();
        let mut body = String::new();
        let inner = indent + 2;
        let ipad = " ".repeat(inner);
        match form {
            Form::Everyone | Form::Inside => {
                let (sentence, keys) = signal.as_ref()?;
                out.push_str(&format!("{pad}when {sentence}\n"));
                skip.extend(keys);
                if form == Form::Everyone {
                    skip.push("applies-to");
                }
                if slug(sentence) != id {
                    body.push_str(&format!("{ipad}called {}\n", named(id)));
                }
            }
            Form::Block | Form::Event => {
                let word = if form == Form::Event { "event" } else { "reaction" };
                out.push_str(&format!("{pad}{word} {}\n", named(id)));
                if let Some((sentence, keys)) = &signal {
                    body.push_str(&format!("{ipad}when {sentence}\n"));
                    skip.extend(keys);
                }
            }
        }
        if let Some((sentence, _)) = &signal {
            let judged = sentence.strip_prefix("it looks like ");
            let described = default_description(sentence, judged);
            if settings.get("description").and_then(|e| e.node.as_str()) == Some(described.as_str()) {
                skip.push("description");
            }
        }
        for (key, entry) in settings {
            if skip.contains(&key.as_str()) {
                continue;
            }
            match key.as_str() {
                "fires" if entry.node.as_str() == Some("every-time") => {
                    body.push_str(&format!("{ipad}every time\n"));
                }
                "then" => match steps(&entry.node) {
                    Some(lines) => {
                        for line in lines {
                            body.push_str(&format!("{ipad}{line}\n"));
                        }
                    }
                    None => emit::setting(&mut body, key, &entry.node, inner, false).ok()?,
                },
                _ => self.one(&mut body, key, &entry.node, inner, Style::Rich).ok()?,
            }
        }
        out.push_str(&body);
        Some(out)
    }

    /// One setting, as a text block where it is several lines of writing and a
    /// setting otherwise.
    fn one(
        &self,
        out: &mut String,
        key: &str,
        node: &Node,
        indent: usize,
        style: Style,
    ) -> Result<(), StaysAFile> {
        if style == Style::Rich
            && let Some(text) = node.as_str()
            && emit::blockable(text)
            && key.chars().all(|c| c.is_ascii_alphanumeric() || matches!(c, '_' | '-'))
            && !key.is_empty()
        {
            out.push_str(&format!("{}{key}\n", " ".repeat(indent)));
            emit::block_lines(out, text, indent + 2);
            return Ok(());
        }
        emit::setting(out, key, node, indent, style == Style::Safe)
    }

    /// The body of a block.
    fn lines(
        &self,
        out: &mut String,
        kind: Kind,
        settings: &Map,
        indent: usize,
        style: Style,
        inside: &[&str],
    ) -> Result<(), StaysAFile> {
        let pad = " ".repeat(indent);
        // A workflow's stages, in the order they run — where they can be said
        // that way. `steps:` and `starts-at:` are then the statements' to say.
        let statements = (style == Style::Rich && kind == Kind::Flow)
            .then(|| self.statements(settings, true, indent))
            .flatten();
        // `based on <name> with <name>: <value>, …` — the base, and what it
        // left open, on one line.
        let based_on = (style == Style::Rich)
            .then(|| settings.get("based-on").and_then(|e| one_line(&e.node)))
            .flatten()
            .filter(|n| !n.contains(" with "));
        let with = based_on.and_then(|_| settings.get("with")).and_then(|e| given(&e.node));
        for (key, entry) in settings {
            let node = &entry.node;
            if statements.is_some() && matches!(key.as_str(), "steps" | "starts-at") {
                continue;
            }
            if let Some(name) = based_on {
                if key == "based-on" {
                    let with = with.as_deref().map(|w| format!(" with {w}")).unwrap_or_default();
                    out.push_str(&format!("{pad}based on {}{with}\n", named(name)));
                    continue;
                }
                if key == "with" && with.is_some() {
                    continue;
                }
            }
            if style == Style::Rich
                && let Some(lines) = self.sentence(kind, key, node, indent, inside)
            {
                out.push_str(&lines);
                continue;
            }
            if style == Style::Rich
                && kind == Kind::Agent
                && key == "limits"
                && let Some(limits) = node.as_map()
            {
                let mut rest = Map::new();
                for (k, e) in limits {
                    match limit(k, &e.node) {
                        Some(line) => out.push_str(&format!("{pad}{line}\n")),
                        None => {
                            rest.insert(k.clone(), e.clone());
                        }
                    }
                }
                if !rest.is_empty() || limits.is_empty() {
                    emit::setting(out, key, &Node::map(rest, at()), indent, false)?;
                }
                continue;
            }
            self.one(out, key, node, indent, style)?;
        }
        if let Some(statements) = statements {
            out.push_str(&statements);
        }
        Ok(())
    }

    /// The sentence a setting is written as in this kind of block, as whole
    /// lines — or `None` when there is none for it.
    fn sentence(
        &self,
        kind: Kind,
        key: &str,
        node: &Node,
        indent: usize,
        inside: &[&str],
    ) -> Option<String> {
        let pad = " ".repeat(indent);
        match (kind, key) {
            (Kind::Agent | Kind::Flow, "accepts") | (Kind::Program, "takes") => {
                Some(format!("{pad}takes {}\n", shapes(node)?))
            }
            (Kind::Agent | Kind::Flow | Kind::Program, "answers-with") => {
                Some(format!("{pad}gives {}\n", shapes(node)?))
            }
            (Kind::Agent, "uses") => Some(format!("{pad}uses {}\n", names(node)?)),
            (Kind::Tagged, "topics") => Some(format!("{pad}about {}\n", names(node)?)),
            (Kind::Agent, "team") => {
                let members = node.as_map().filter(|m| !m.is_empty())?;
                let mut out = String::new();
                for (who, what) in members {
                    let what = one_line(&what.node)?;
                    (a_name(who) && !who.contains(':')).then_some(())?;
                    out.push_str(&format!("{pad}asks {who}: {what}\n"));
                }
                Some(out)
            }
            (Kind::Agent, "remembers") => {
                let facts = node.as_map().filter(|m| !m.is_empty())?;
                let mut out = String::new();
                for (name, fact) in facts {
                    let settings = fact.node.as_map()?;
                    out.push_str(&format!("{pad}remembers {}\n", named(name)));
                    self.lines(&mut out, Kind::Plain, settings, indent + 2, Style::Rich, &[]).ok()?;
                }
                Some(out)
            }
            (Kind::Agent, "listens-for") => {
                let lines = node.as_list().filter(|l| !l.is_empty())?;
                let mut out = String::new();
                for line in lines {
                    let m = line.as_map().filter(|m| m.len() == 2)?;
                    let (what, name) = ["topic", "event"]
                        .into_iter()
                        .find_map(|k| Some((k, m.get(k)?.node.as_str()?)))?;
                    let how = match m.get("how")?.node.as_str()? {
                        "asked-first" => "asked first",
                        "told-after" => "told after",
                        _ => return None,
                    };
                    a_name(name).then_some(())?;
                    out.push_str(&format!("{pad}listens for {what} {name}: {how}\n"));
                }
                Some(out)
            }
            (Kind::Agent, "reactions") if !inside.is_empty() => {
                let mut out = String::new();
                for name in inside {
                    out.push_str(&self.reaction_block(
                        name,
                        self.reaction(name)?,
                        Form::Inside,
                        indent,
                    )?);
                }
                Some(out)
            }
            (Kind::Policy, "ask-a-person") => {
                let rules = node.as_list().filter(|l| !l.is_empty())?;
                let mut out = String::new();
                for rule in rules {
                    out.push_str(&format!("{pad}{}\n", before(rule)?));
                }
                Some(out)
            }
            _ => None,
        }
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Kind {
    Agent,
    Tagged,
    Policy,
    Reaction,
    Event,
    /// A workflow or a loop: its `steps:` are written as statements.
    Flow,
    Program,
    Plain,
}

impl Kind {
    fn of(word: &str) -> Kind {
        match word {
            "agent" => Kind::Agent,
            "tool" | "knowledge" => Kind::Tagged,
            "policy" => Kind::Policy,
            "reaction" => Kind::Reaction,
            "event" => Kind::Event,
            "workflow" | "loop" => Kind::Flow,
            "program" => Kind::Program,
            _ => Kind::Plain,
        }
    }
}

/// `message: text, photos: list of images`
fn shapes(node: &Node) -> Option<String> {
    let fields = node.as_map().filter(|m| !m.is_empty())?;
    let mut parts = Vec::new();
    for (name, shape) in fields {
        let shape = one_line(&shape.node)?;
        (name.chars().all(|c| c.is_alphanumeric() || matches!(c, '_' | '-')) && !name.is_empty())
            .then_some(())?;
        parts.push(format!("{name}: {shape}"));
    }
    Some(parts.join(", "))
}

/// `zendesk, payments`
/// `domain: refunds, daily-cap: 0.05 USD` — or `None` when a comma or a colon
/// in one of the figures would make the line read as something else.
fn given(node: &Node) -> Option<String> {
    let fields = node.as_map().filter(|m| !m.is_empty())?;
    let mut parts = Vec::new();
    for (name, figure) in fields {
        let figure = emit::word(&figure.node).filter(|f| !f.contains(',') && !f.is_empty())?;
        (name.chars().all(|c| c.is_alphanumeric() || matches!(c, '_' | '-')) && !name.is_empty())
            .then_some(())?;
        parts.push(format!("{name}: {figure}"));
    }
    Some(parts.join(", "))
}

fn names(node: &Node) -> Option<String> {
    let items = node.as_list().filter(|l| !l.is_empty())?;
    let mut parts = Vec::new();
    for item in items {
        let name = one_line(item).filter(|n| !n.contains(','))?;
        parts.push(name);
    }
    Some(parts.join(", "))
}

/// One line of `limits:` as a sentence.
fn limit(key: &str, node: &Node) -> Option<String> {
    let whole = || match &node.value {
        Value::Int(n) => Some(*n),
        _ => None,
    };
    match key {
        "steps-at-most" => Some(format!("at most {} steps", whole()?)),
        "tool-calls-at-most" => Some(format!("at most {} tool calls", whole()?)),
        "tokens-at-most" => Some(format!("at most {} tokens", whole()?)),
        "cost-per-request-under" => {
            let money = one_line(node)?;
            Some(format!("spends under {money} a request"))
        }
        "when-it-runs-out" => {
            let what = one_line(node).filter(|w| !w.contains(' '))?;
            Some(format!("when it runs out: {}", what.replace('-', " ")))
        }
        _ => None,
    }
}

/// A reaction's `then:` as sentences, when every step is one a sentence says.
fn steps(node: &Node) -> Option<Vec<String>> {
    let list = node.as_list().filter(|l| !l.is_empty())?;
    let mut out = Vec::new();
    for step in list {
        let m = step.as_map().filter(|m| m.len() == 1)?;
        let (verb, value) = m.iter().next()?;
        let value = one_line(&value.node)?;
        out.push(match verb.as_str() {
            "remind" => format!("remind it: {value}"),
            "stop" => format!("stop and say: {value}"),
            "consult" => format!("consult {value}"),
            "tell" => format!("tell {value}"),
            _ => return None,
        });
    }
    Some(out)
}

/// One `ask-a-person:` rule as a `before …` sentence.
fn before(rule: &Node) -> Option<String> {
    let m = rule.as_map().filter(|m| m.len() == 3)?;
    let question = one_line(&m.get("question")?.node).filter(|q| a_name(q))?;
    let because = one_line(&m.get("because")?.node)?;
    let [atom] = m.get("when")?.node.as_list()? else { return None };
    let atom = atom.as_map()?;
    let tool = atom.get("tool")?.node.as_str().filter(|t| a_name(t))?;
    let compared = match atom.len() {
        1 => String::new(),
        3 => {
            let arg = atom.get("arg")?.node.as_str().filter(|a| a_name(a))?;
            let (word, figure) = [("more-than", "is more than"), ("less-than", "is less than"), ("is", "is")]
                .into_iter()
                .find_map(|(k, words)| Some((words, &atom.get(k)?.node)))?;
            format!(", when {arg} {word} {}", emit::word(figure)?)
        }
        _ => return None,
    };
    Some(format!("before {tool}{compared}: ask {question}, because {because}"))
}

// ── a folder of YAML ────────────────────────────────────────────────────────

/// The same document as a folder of YAML and Markdown: each file's path
/// relative to the folder, and what goes in it.
///
/// One file per entry — `tools/payments.yaml`, `agents/desk/agent.yaml` with
/// its `instructions.md` — and `workspace.yaml` for the workspace's own
/// settings. A collection with a name in it that cannot be a file name is
/// written inside `workspace.yaml` instead. The caller reads the folder back
/// and compares; see `pact build`.
pub fn tree(root: &Node) -> Result<Vec<(String, String)>, String> {
    let mut left = Vec::new();
    let pruned = prune(root, "", &mut left)
        .filter(|n| n.as_map().is_some())
        .ok_or("the document is not a set of settings, so it is not a workspace")?;
    let root = pruned.as_map().expect("checked above");
    let mut files: Vec<(String, String)> = Vec::new();
    let mut top = Map::new();
    for (key, entry) in root {
        let entries = entry.node.as_map().filter(|m| {
            word_for(key).is_some()
                && !m.is_empty()
                && m.iter().all(|(id, e)| a_file_name(id) && e.node.as_map().is_some())
        });
        let Some(entries) = entries else {
            if SINGLES.contains(&key.as_str()) && entry.node.as_map().is_some_and(|m| !m.is_empty()) {
                // `evals/suite.yaml`, because an agent may name its checks by
                // that path (`evals: /evals/suite.yaml`) and the path has to be
                // one that is there.
                let file = if key == "evals" { "evals/suite.yaml".to_string() } else { format!("{key}.yaml") };
                files.push((file, yaml(&entry.node)?));
            } else {
                top.insert(key.clone(), entry.clone());
            }
            continue;
        };
        for (id, e) in entries {
            if key == "agents" {
                let mut agent = e.node.as_map().cloned().unwrap_or_default();
                if let Some(words) = agent
                    .get("instructions")
                    .and_then(|i| i.node.as_str())
                    .filter(|w| !w.is_empty() && *w == w.trim() && !w.starts_with("---"))
                    .map(str::to_string)
                {
                    agent.shift_remove("instructions");
                    files.push((format!("agents/{id}/instructions.md"), format!("{words}\n")));
                }
                files.push((format!("agents/{id}/agent.yaml"), yaml(&Node::map(agent, at()))?));
            } else {
                files.push((format!("{key}/{id}.yaml"), yaml(&e.node)?));
            }
        }
    }
    files.insert(0, ("workspace.yaml".to_string(), yaml(&Node::map(top, at()))?));
    Ok(files)
}

/// The whole document as one `workspace.yaml` — the form a folder falls back
/// to when its split form does not read back identically.
pub fn one_file(root: &Node) -> Result<String, String> {
    let mut left = Vec::new();
    let pruned = prune(root, "", &mut left).ok_or("the document is not a workspace")?;
    yaml(&pruned)
}

/// A name that is safely a file's: nothing the loader gives a meaning of its
/// own — a leading dot, a path, or a number in front that it would read as an
/// order.
fn a_file_name(id: &str) -> bool {
    !id.is_empty()
        && id.chars().all(|c| c.is_ascii_alphanumeric() || matches!(c, '_' | '-'))
        && !id.starts_with(|c: char| c.is_ascii_digit() || c == '_' || c == '-')
}

fn yaml(node: &Node) -> Result<String, String> {
    let settings = node.as_map().ok_or("not a set of settings")?;
    for safe in [false, true] {
        let mut out = String::new();
        let ok = settings
            .iter()
            .try_for_each(|(k, e)| emit::setting(&mut out, k, &e.node, 0, safe))
            .is_ok();
        if ok
            && let Ok(back) = pact_doc::parse_yaml(&out, Utf8Path::new("written.yaml"))
            && canonical_string(&back) == canonical_string(node)
        {
            return Ok(out);
        }
        if ok && settings.is_empty() {
            return Ok(String::new());
        }
    }
    Err("a file could not be written as YAML that reads back the same".to_string())
}
