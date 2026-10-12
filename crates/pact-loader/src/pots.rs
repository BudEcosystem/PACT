//! **One money pot per run, and what a ceiling is counted across** (02W §2.10,
//! §3 WF-31, R32).
//!
//! | Rule | 02W | Fires when |
//! |---|---|---|
//! | `loader/a-share-of-no-pot` | WF-31 | a stage writes `cost-per-request-under:` and neither the workflow nor a stage around it has one (a stage's figure is its share, never a second pot), or the shares written directly under one pot add up to more than it, in its currency |
//! | `loader/counted-across-nothing` | §2.10 | `counted-per:` is not `run`, `connection` or `team`, nor (in a workflow) a binding; a binding is then held to what it names by `bindings.rs` (WF-4) |

use crate::bindings::is_binding;
use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::{Map, Node};
use pact_schema::Ty;
use pact_schema::coerce::{self, Coerced};

/// The words `counted-per:` takes besides a binding.
const COUNTED_ACROSS: [&str; 3] = ["run", "connection", "team"];

/// A money figure as written: its amount, its currency, and where it is.
struct Figure {
    amount: f64,
    currency: String,
    at: Span,
}

/// One pot and the shares written directly under it.
struct Pot {
    owner: String,
    figure: Figure,
    shares: Vec<f64>,
}

/// Every check on money pots and on `counted-per:`, over the loaded document.
pub fn check(document: &Node, diags: &mut Diagnostics) {
    for (_, entry) in document
        .get("agents")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        counted(entry.node.get("limits"), false, diags);
    }
    for (name, entry) in document
        .get("workflows")
        .and_then(Node::as_map)
        .into_iter()
        .flatten()
    {
        let w = &entry.node;
        counted(w.get("limits"), true, diags);
        let mut pots: Vec<Pot> = figure_of(w.get("limits"))
            .map(|figure| Pot {
                owner: format!("the workflow '{name}'"),
                figure,
                shares: Vec::new(),
            })
            .into_iter()
            .collect();
        let top = (!pots.is_empty()).then_some(0);
        if let Some(steps) = w.get("steps").and_then(Node::as_map) {
            shares(name, steps, top, &mut pots, diags);
        }
        for pot in pots {
            over(&pot, diags);
        }
    }
}

/// The stages of `steps`, each share held to `pot` (an index into `pots`).
fn shares(
    flow: &str,
    steps: &Map,
    pot: Option<usize>,
    pots: &mut Vec<Pot>,
    diags: &mut Diagnostics,
) {
    for (stage, entry) in steps {
        let limits = entry.node.get("limits");
        counted(limits, true, diags);
        let mine = figure_of(limits);
        let inner = match (mine, pot) {
            (None, _) => pot,
            (Some(figure), None) => {
                diags.push(Diagnostic::error(
                    "loader/a-share-of-no-pot",
                    figure.at.clone(),
                    format!(
                        "'{stage}' has a money ceiling, and the workflow '{flow}' has none — a \
                         stage's figure is its share of the run's, never a second pot, so this \
                         is a share of nothing."
                    ),
                    "Put the figure on the workflow — `cost-per-request-under:` under its own \
                     `limits:`, with `when-it-runs-out:` — and keep this line as the stage's \
                     share."
                        .to_string(),
                ));
                None
            }
            (Some(figure), Some(i)) => {
                if figure.currency == pots[i].figure.currency {
                    pots[i].shares.push(figure.amount);
                }
                pots.push(Pot {
                    owner: format!("'{stage}'"),
                    figure,
                    shares: Vec::new(),
                });
                Some(pots.len() - 1)
            }
        };
        if let Some(body) = entry.node.get("steps").and_then(Node::as_map) {
            shares(flow, body, inner, pots, diags);
        }
    }
}

/// WF-31's second half: shares that add up to more than their pot.
fn over(pot: &Pot, diags: &mut Diagnostics) {
    let sum: f64 = pot.shares.iter().sum();
    if sum <= pot.figure.amount + 1e-9 {
        return;
    }
    let (figure, currency) = (written(pot.figure.amount), &pot.figure.currency);
    diags.push(Diagnostic::error(
        "loader/a-share-of-no-pot",
        pot.figure.at.clone(),
        format!(
            "The stages under {} give themselves {} {currency} in all, more than its own \
             {figure} {currency} — so they could not all spend their share.",
            pot.owner,
            written(sum)
        ),
        format!(
            "Lower the stages' figures to add up to {figure} {currency} or less, or raise this \
             one."
        ),
    ));
}

/// A figure as an author writes it: `1.5`, not `1.50000000001`.
fn written(amount: f64) -> String {
    let s = format!("{amount:.4}");
    s.trim_end_matches('0').trim_end_matches('.').to_string()
}

/// The `cost-per-request-under:` of a `limits:` group, read.
fn figure_of(limits: Option<&Node>) -> Option<Figure> {
    let entry = limits?.as_map()?.get("cost-per-request-under")?;
    match coerce::check(&entry.node, &Ty::Money)? {
        Coerced::Money { amount, currency } => Some(Figure {
            amount,
            currency,
            at: entry.key_span.clone(),
        }),
        _ => None,
    }
}

/// `counted-per:` names one of its three words or, in a workflow, a binding.
fn counted(limits: Option<&Node>, in_workflow: bool, diags: &mut Diagnostics) {
    let Some(entry) = limits
        .and_then(Node::as_map)
        .and_then(|m| m.get("counted-per"))
    else {
        return;
    };
    let Some(said) = entry.node.as_str().map(str::trim) else {
        return;
    };
    if COUNTED_ACROSS.contains(&said) || in_workflow && is_binding(said) {
        return;
    }
    let fix = if in_workflow {
        "Write `run`, `connection` or `team`, or a binding — `input.customer-id` for a ceiling \
         per customer."
    } else {
        "Write `run`, `connection` or `team`; a ceiling per value of a binding is written in a \
         workflow, which has inputs to read."
    };
    diags.push(Diagnostic::error(
        "loader/counted-across-nothing",
        entry.node.span.clone(),
        format!("`counted-per: {said}` names nothing a ceiling can be counted across."),
        fix.to_string(),
    ));
}
