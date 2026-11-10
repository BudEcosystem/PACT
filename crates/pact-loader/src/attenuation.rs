//! **Permissions only shrink** (law 5 of `docs/97-PRIMITIVES.md`;
//! `docs/98-PRIMITIVES-ENGINEERING-PLAN.md` WP-5).
//!
//! | Rule | Severity | Fires when |
//! |---|---|---|
//! | `loader/a-locked-part-changed-below` | error | an entry `based-on:` another restates a part `owners:` locks `here-and-below` on the base |
//! | `loader/a-copy-wider-than-its-template` | warning | an entry `based-on:` another raises one of its ceilings (`steps-at-most`, `tool-calls-at-most`, `tokens-at-most`, `cost-per-request-under`) |
//! | `loader/a-budget-from-nowhere` | error | `cost-per-request-from:` reads something the run is not given (docs/98 WP-14) |
//! | `loader/a-helper-allowed-more-than-its-caller` | error | a teammate's own `cost-per-request-under` is above its caller's, in the same currency |
//!
//! # Why these three
//!
//! An allowance handed on is never wider than the one it came from. Three
//! hand-ons are written in a tree: a copy made from a template (`based-on:`), a
//! teammate asked by its caller, and a learning cycle writing the definition
//! (held by `learning:`'s closed lists and, at run time, by `docs/98` WP-15).
//!
//! The first two run on the document as written, BEFORE `based-on:` is
//! resolved (`derive.rs` calls [`before_derive`]): once resolved, a copy reads
//! like longhand and which lines it restated is gone.
//!
//! `locked: here-and-below` is the schema's own promise — "not in any workspace
//! based on this one either" — which nothing held. A copy that restates a
//! locked part changes what the owner locked, whatever value it writes.

use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::{Map, Node};
use pact_schema::Ty;
use pact_schema::coerce::{self, Coerced};

const CEILINGS: [&str; 3] = ["steps-at-most", "tool-calls-at-most", "tokens-at-most"];

/// The `based-on:` half, on the document before it is resolved.
pub fn before_derive(root: &Node, collections: &[String], diags: &mut Diagnostics) {
    let owners = root.get("owners").and_then(Node::as_map);
    for kind in collections {
        let Some(entries) = root.get(kind).and_then(Node::as_map) else {
            continue;
        };
        for (name, entry) in entries {
            let Some(base) = entry
                .node
                .get("based-on")
                .and_then(Node::as_str)
                .map(str::trim)
            else {
                continue;
            };
            // `name@version` names the template before the last `@`.
            let base = base.rsplit_once('@').map_or(base, |(b, _)| b);
            if base.starts_with("pact:") {
                continue;
            }
            let Some(base_entry) = entries.get(base) else {
                continue;
            };
            let Some(own) = entry.node.as_map() else {
                continue;
            };
            locked_below(
                kind,
                name,
                base,
                own,
                base_entry.node.as_map(),
                owners,
                diags,
            );
            wider_copy(name, base, own, &base_entry.node, diags);
        }
    }
}

/// Every owners key that locks a part of `kind.base` `here-and-below`, as the
/// field under the entry it names (`None` for the whole entry).
fn locks_on(owners: Option<&Map>, kind: &str, base: &str) -> Vec<(Option<String>, String)> {
    let Some(owners) = owners else {
        return Vec::new();
    };
    owners
        .iter()
        .filter_map(|(key, entry)| {
            let lock = entry.node.get("locked").and_then(Node::as_str)?.trim();
            if lock != "here-and-below" {
                return None;
            }
            let parts: Vec<&str> = key.split(['.', '/']).map(str::trim).collect();
            let who = entry
                .node
                .get("owned-by")
                .and_then(Node::as_str)
                .map_or_else(|| "its owner".to_string(), |o| format!("'{}'", o.trim()));
            match parts.as_slice() {
                [k, b] if *k == kind && *b == base => Some((None, who)),
                [k, b, field, ..] if *k == kind && *b == base => {
                    Some((Some((*field).to_string()), who))
                }
                _ => None,
            }
        })
        .collect()
}

fn locked_below(
    kind: &str,
    name: &str,
    base: &str,
    own: &Map,
    base_map: Option<&Map>,
    owners: Option<&Map>,
    diags: &mut Diagnostics,
) {
    for (field, who) in locks_on(owners, kind, base) {
        let restated: Vec<(&String, &pact_doc::Entry)> = own
            .iter()
            .filter(|(k, _)| match &field {
                Some(f) => *k == f,
                // A whole entry locked: every setting the base carries. A copy
                // still says what it does (`instructions:` the base never had);
                // it may not change what the owner locked.
                None => {
                    !matches!(k.as_str(), "based-on" | "name" | "description" | "base")
                        && base_map.is_some_and(|b| b.contains_key(k.as_str()))
                }
            })
            .collect();
        for (k, e) in restated {
            let what = field
                .as_deref()
                .map_or_else(|| format!("'{base}'"), |f| format!("`{f}:` of '{base}'"));
            diags.push(Diagnostic::error(
                "loader/a-locked-part-changed-below",
                e.key_span.clone(),
                format!(
                    "'{name}' is based on '{base}' and restates `{k}:`, and {who} locked {what} \
                     `here-and-below` under `owners:` — it may not change in anything built from \
                     '{base}'."
                ),
                format!(
                    "Take `{k}:` out of '{name}' so it keeps '{base}'s, or ask {who} to change \
                     the lock."
                ),
            ));
        }
    }
}

fn wider_copy(name: &str, base: &str, own: &Map, base_node: &Node, diags: &mut Diagnostics) {
    let Some(mine) = own.get("limits").and_then(|e| e.node.as_map()) else {
        return;
    };
    let Some(theirs) = base_node.get("limits").and_then(Node::as_map) else {
        return;
    };
    for field in CEILINGS {
        let (Some(m), Some(t)) = (mine.get(field), theirs.get(field)) else {
            continue;
        };
        if let (Some(a), Some(b)) = (whole(&m.node), whole(&t.node))
            && a > b
        {
            diags.push(wider(name, base, field, &a.to_string(), &b.to_string(), m));
        }
    }
    if let (Some(m), Some(t)) = (
        mine.get("cost-per-request-under"),
        theirs.get("cost-per-request-under"),
    ) && let (Some((a, ca)), Some((b, cb))) = (money(&m.node), money(&t.node))
        && ca == cb
        && a > b
    {
        diags.push(wider(
            name,
            base,
            "cost-per-request-under",
            &format!("{a} {ca}"),
            &format!("{b} {cb}"),
            m,
        ));
    }
}

fn wider(
    name: &str,
    base: &str,
    field: &str,
    mine: &str,
    theirs: &str,
    at: &pact_doc::Entry,
) -> Diagnostic {
    Diagnostic::warning(
        "loader/a-copy-wider-than-its-template",
        at.key_span.clone(),
        format!(
            "'{name}' is based on '{base}' and raises `{field}:` from {theirs} to {mine}. A copy \
             is usually a narrower version of what it is based on; this one is allowed more."
        ),
        format!(
            "If '{name}' really needs more, say why in a comment beside the line. Otherwise keep \
             {theirs}, or less."
        ),
    )
}

/// A budget handed in at run time (`cost-per-request-from:`, docs/98 WP-14)
/// comes from something the run is actually given: a declared `run-inputs:`
/// entry on an agent, the run's `input` in a workflow.
fn budgets_come_from_somewhere(root: &Node, diags: &mut Diagnostics) {
    for (collection, root_word) in [("agents", "run-inputs."), ("workflows", "input.")] {
        for (name, entry) in root
            .get(collection)
            .and_then(Node::as_map)
            .into_iter()
            .flatten()
        {
            let Some(line) = entry
                .node
                .get("limits")
                .and_then(|l| l.get("cost-per-request-from"))
            else {
                continue;
            };
            let written = line.as_str().map(str::trim).unwrap_or("");
            let declared: Vec<&str> = if collection == "agents" {
                entry
                    .node
                    .get("run-inputs")
                    .and_then(Node::as_map)
                    .map(|m| m.keys().map(String::as_str).collect())
                    .unwrap_or_default()
            } else {
                entry
                    .node
                    .get("accepts")
                    .and_then(Node::as_map)
                    .map(|m| m.keys().map(String::as_str).collect())
                    .unwrap_or_default()
            };
            let ok = written
                .strip_prefix(root_word)
                .is_some_and(|rest| declared.contains(&rest.split('.').next().unwrap_or(rest)));
            if ok {
                continue;
            }
            let offered = declared
                .iter()
                .map(|d| format!("`{root_word}{d}`"))
                .collect::<Vec<_>>()
                .join(", ");
            diags.push(Diagnostic::error(
                "loader/a-budget-from-nowhere",
                line.span.clone(),
                format!(
                    "'{name}' takes its money ceiling from `{written}`, which is not something a \
                     run of it is given."
                ),
                if offered.is_empty() {
                    format!(
                        "Declare what the surrounding system hands in (`{}`) and read it as \
                         `{root_word}<name>`.",
                        if collection == "agents" {
                            "run-inputs:"
                        } else {
                            "accepts:"
                        }
                    )
                } else {
                    format!("Read one of: {offered}.")
                },
            ));
        }
    }
}

/// The teammate half, on the resolved document.
pub fn check(root: &Node, diags: &mut Diagnostics) {
    budgets_come_from_somewhere(root, diags);
    let Some(agents) = root.get("agents").and_then(Node::as_map) else {
        return;
    };
    for (caller, entry) in agents {
        let Some(team) = entry.node.get("team").and_then(Node::as_map) else {
            continue;
        };
        let Some((pot, currency)) = entry
            .node
            .get("limits")
            .and_then(|l| l.get("cost-per-request-under"))
            .and_then(money)
        else {
            continue;
        };
        for member in team.keys() {
            let Some(line) = agents
                .get(member)
                .and_then(|m| m.node.get("limits"))
                .and_then(Node::as_map)
                .and_then(|l| l.get("cost-per-request-under"))
            else {
                continue;
            };
            let Some((own, cur)) = money(&line.node) else {
                continue;
            };
            if cur != currency || own <= pot {
                continue;
            }
            diags.push(Diagnostic::error(
                "loader/a-helper-allowed-more-than-its-caller",
                line.key_span.clone(),
                format!(
                    "'{member}' may spend {own} {cur} on a request, and '{caller}', which asks \
                     it for help, may spend {pot} {currency} on the whole request. A helper is \
                     never allowed more than the one it works for."
                ),
                format!(
                    "Lower '{member}'s `cost-per-request-under:` to {pot} {currency} or less, or \
                     raise '{caller}'s."
                ),
            ));
        }
    }
}

fn whole(n: &Node) -> Option<i64> {
    match &n.value {
        pact_doc::Value::Int(i) => Some(*i),
        pact_doc::Value::Str(s) => s.trim().parse().ok(),
        _ => None,
    }
}

fn money(n: &Node) -> Option<(f64, String)> {
    match coerce::check(n, &Ty::Money)? {
        Coerced::Money { amount, currency } => Some((amount, currency)),
        _ => None,
    }
}
