//! Writing a workflow's stages as statements, in the order they run.
//!
//! The other half of `read/flow.rs`, and the less certain half: a set of
//! stages that each say where to go next can be wired in ways no order of
//! lines can say. So this writes statements only for the wirings it knows —
//! one stage after another, a body inside a `for each`, a `repeat` or a
//! `together`, a decision whose branches end or come back together at one
//! stage — and says `None` for the rest, which are then written as the
//! settings they are.
//!
//! It does not have to be right about which is which. Whatever it writes is
//! read back and compared before it is used (`Printer::checked`), and a
//! workflow that does not come back the same is written plainly.

use super::*;
use crate::unbound;

/// The stages that are one word and nothing else, as the reader has them.
const PLAIN: &[(&str, &str)] = &[
    ("think", "think"),
    ("use-tools", "use tools"),
    ("check-its-work", "check its work"),
    ("run-code", "run code"),
];

fn bare(text: &str) -> bool {
    !text.is_empty() && text.chars().all(|c| c.is_alphanumeric() || matches!(c, '_' | '-'))
}

/// Where a stage goes when it has answered, if it says.
fn answered(stage: &Map) -> Option<&str> {
    stage.get("then")?.node.as_map()?.get("answered")?.node.as_str()
}

fn does(stage: &Map) -> Option<&str> {
    stage.get("does")?.node.as_str()
}

/// `brief: input.brief, findings: research.findings`.
fn binds(node: &Node) -> Option<String> {
    let fields = node.as_map().filter(|m| !m.is_empty())?;
    let mut parts = Vec::new();
    for (name, from) in fields {
        let from = one_line(&from.node).filter(|f| !f.contains([',', ' ', ':']))?;
        (!name.is_empty() && !name.contains([',', ' ', ':'])).then_some(())?;
        parts.push(format!("{name}: {}", unbound(from)));
    }
    Some(parts.join(", "))
}

impl<'a> Printer<'a> {
    /// The `steps:` of a workflow, a loop or the inside of a stage, as
    /// statements — or `None` when an order of lines cannot say them.
    pub(super) fn statements(&self, settings: &Map, in_turn: bool, indent: usize) -> Option<String> {
        let steps = settings.get("steps")?.node.as_map().filter(|m| !m.is_empty())?;
        let mut out = String::new();
        let mut seen: BTreeSet<&str> = BTreeSet::new();
        if in_turn {
            let first = settings.get("starts-at")?.node.as_str()?;
            self.run(steps, first, None, indent, &mut seen, &mut out)?;
            // Stages the order did not reach — the ones a stage goes to when
            // it has run `too-many-times`, say — are written after it. That
            // reads back the same only where the stage before them says where
            // it goes itself, and the comparison is what finds out.
            for name in steps.keys() {
                if !seen.contains(name.as_str()) {
                    self.run(steps, name, None, indent, &mut seen, &mut out)?;
                }
            }
        } else {
            // Every stage of a `together` starts at once, so none follows
            // another and none is where it starts.
            if settings.contains_key("starts-at") {
                return None;
            }
            for (name, entry) in steps {
                let stage = entry.node.as_map()?;
                (does(stage)? != "decide").then_some(())?;
                seen.insert(name);
                self.statement(name, stage, false, indent, &mut out)?;
            }
        }
        (seen.len() == steps.len()).then_some(out)
    }

    /// One stage after another from `first`, until one goes nowhere the order
    /// can say or `join` is reached.
    fn run<'m>(
        &self,
        steps: &'m Map,
        first: &'m str,
        join: Option<&str>,
        indent: usize,
        seen: &mut BTreeSet<&'m str>,
        out: &mut String,
    ) -> Option<()> {
        let mut cur = first;
        loop {
            if Some(cur) == join {
                return Some(());
            }
            let (name, entry) = steps.get_key_value(cur)?;
            let stage = entry.node.as_map()?;
            if !seen.insert(name.as_str()) {
                return None;
            }
            let what = does(stage)?;
            if what == "decide" {
                match self.decision(steps, name, stage, join, indent, seen, out)? {
                    Some(on) => {
                        cur = on;
                        continue;
                    }
                    None => return Some(()),
                }
            }
            // The order says where a stage goes only when that is a stage
            // beside it that has not been written yet. `done`, a stage already
            // written (going back) and anything after an `answer` stay as the
            // `then:` they are.
            let next = answered(stage).filter(|n| {
                what != "answer"
                    && steps.contains_key(*n)
                    && (!seen.contains(*n) || Some(*n) == join)
            });
            self.statement(name, stage, next.is_some(), indent, out)?;
            match next {
                Some(next) => cur = steps.get_key_value(next)?.0.as_str(),
                None => return Some(()),
            }
        }
    }

    /// One stage as a statement, with its other settings beneath it.
    /// `in_order` is whether the line after it says where it goes.
    fn statement(
        &self,
        name: &str,
        stage: &Map,
        in_order: bool,
        indent: usize,
        out: &mut String,
    ) -> Option<()> {
        let pad = " ".repeat(indent);
        let mut rest = stage.clone();
        let what = does(stage)?;
        rest.shift_remove("does");
        let with = |rest: &mut Map| -> String {
            match rest.get("bind").and_then(|e| binds(&e.node)) {
                Some(said) => {
                    rest.shift_remove("bind");
                    format!(" with {said}")
                }
                None => String::new(),
            }
        };
        let (said, default) = match what {
            "call" => {
                let target = one_line(&rest.shift_remove("call")?.node)
                    .filter(|t| !t.contains(' '))?
                    .to_string();
                let with = with(&mut rest);
                (format!("call {target}{with}"), slug(&target))
            }
            "answer" => {
                let with = with(&mut rest);
                (format!("answer{with}"), "answer".to_string())
            }
            "each" => {
                let over = one_line(&rest.shift_remove("over")?.node)
                    .filter(|t| !t.contains(' '))?
                    .to_string();
                (format!("for each item in {}", unbound(&over)), "each".to_string())
            }
            "repeat" => {
                let count = match rest.get("at-most").map(|e| &e.node.value) {
                    Some(Value::Int(n)) => Some(*n),
                    _ => None,
                };
                let said = match count {
                    Some(n) => {
                        rest.shift_remove("at-most");
                        format!("repeat at most {n} times")
                    }
                    None => "repeat".to_string(),
                };
                (said, "repeat".to_string())
            }
            "together" => ("together".to_string(), "together".to_string()),
            "stop" => {
                let stops = one_line(&rest.shift_remove("stops")?.node)
                    .filter(|t| !t.contains(' '))?
                    .to_string();
                (format!("stop {}", unbound(&stops)), "stop".to_string())
            }
            "ask-someone" => {
                let asks = one_line(&rest.shift_remove("asks")?.node)?.to_string();
                let said = format!("ask {asks}");
                let default = slug(&said);
                (said, default)
            }
            other => {
                let (word, said) = PLAIN.iter().find(|(word, _)| *word == other)?;
                ((*said).to_string(), (*word).to_string())
            }
        };
        if in_order {
            // The line after this one says it.
            let mut then = rest.shift_remove("then")?.node.as_map()?.clone();
            then.shift_remove("answered");
            if !then.is_empty() {
                rest.insert(
                    "then".to_string(),
                    Entry {
                        key_span: at(),
                        node: Node::map(then, at()),
                    },
                );
            }
        }
        let inside = if matches!(what, "each" | "repeat" | "together") && rest.contains_key("steps") {
            let in_turn = what != "together";
            let text = self.statements(&rest, in_turn, indent + 2)?;
            rest.shift_remove("steps");
            if in_turn {
                rest.shift_remove("starts-at");
            }
            text
        } else {
            String::new()
        };
        bare(name).then_some(())?;
        if name == default {
            out.push_str(&format!("{pad}{said}\n"));
        } else {
            out.push_str(&format!("{pad}{name} = {said}\n"));
        }
        self.lines(out, Kind::Plain, &rest, indent + 2, Style::Rich, &[]).ok()?;
        out.push_str(&inside);
        Some(())
    }

    /// A decision, with the stages each label leads to beneath its `if`.
    /// Gives back the stage its branches come back together at, where the
    /// order goes on — or `None` when they do not come back together.
    #[allow(clippy::too_many_arguments)]
    fn decision<'m>(
        &self,
        steps: &'m Map,
        name: &str,
        stage: &'m Map,
        outer: Option<&str>,
        indent: usize,
        seen: &mut BTreeSet<&'m str>,
        out: &mut String,
    ) -> Option<Option<&'m str>> {
        let pad = " ".repeat(indent);
        let choices = stage.get("chooses-between")?.node.as_map()?;
        let mut rest = stage.clone();
        rest.shift_remove("does");
        rest.shift_remove("chooses-between");

        // Each label that leads to a stage not written yet: that stage and
        // the ones after it, as far as one line after another goes.
        let mut branches: Vec<(&str, Vec<&'m str>)> = Vec::new();
        let mut led: BTreeSet<&str> = BTreeSet::new();
        for (label, to) in choices {
            let to = to.node.as_str()?;
            if !steps.contains_key(to) || seen.contains(to) || Some(to) == outer || !led.insert(to) {
                continue;
            }
            let mut chain: Vec<&'m str> = Vec::new();
            let mut cur = Some(steps.get_key_value(to)?.0.as_str());
            while let Some(here) = cur {
                if seen.contains(here) || chain.contains(&here) {
                    break;
                }
                let inner = steps.get(here)?.node.as_map()?;
                chain.push(here);
                let what = does(inner)?;
                if what == "decide" || what == "answer" {
                    break;
                }
                cur = answered(inner).and_then(|n| steps.get_key_value(n)).map(|(k, _)| k.as_str());
            }
            branches.push((label.as_str(), chain));
        }
        // Where they come back together: the first stage of one branch that
        // another branch reaches too.
        let mut join: Option<&'m str> = None;
        'found: for (i, (_, chain)) in branches.iter().enumerate() {
            for here in chain {
                if branches.iter().enumerate().any(|(k, (_, other))| k != i && other.contains(here)) {
                    join = Some(*here);
                    break 'found;
                }
            }
        }

        bare(name).then_some(())?;
        if name == "decide" {
            out.push_str(&format!("{pad}decide\n"));
        } else {
            out.push_str(&format!("{pad}{name} = decide\n"));
        }
        self.lines(out, Kind::Plain, &rest, indent + 2, Style::Rich, &[]).ok()?;
        let comes_back = join.or(outer.and_then(|o| steps.get_key_value(o)).map(|(k, _)| k.as_str()));
        for (label, to) in choices {
            let to = to.node.as_str()?;
            (bare(label) && a_name(to) && !to.contains(':')).then_some(())?;
            let own = branches.iter().any(|(l, _)| *l == label.as_str()) && Some(to) != join;
            if own {
                out.push_str(&format!("{pad}  if {label}\n"));
                let first = steps.get_key_value(to)?.0.as_str();
                self.run(steps, first, comes_back, indent + 4, seen, out)?;
            } else {
                out.push_str(&format!("{pad}  if {label}: {to}\n"));
            }
        }
        Some(join)
    }
}
