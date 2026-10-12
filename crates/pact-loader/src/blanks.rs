//! **A blank in a tool's address that no argument fills.**
//!
//! A `url:` may leave parts of the address for each call to fill:
//! `host/pets/{pet-id}` puts the call's `pet-id` argument in the path, and
//! `host/pets/{pet-id}?tag={tag}` puts `tag` in the query (where a pair is left
//! out when the call has no value for a blank in it). A blank is `{`, up to the
//! next `}`, its name trimmed, anywhere in the address. That is how an API whose addresses carry their own
//! values is reached at all, and it is what `pact-import --as openapi` writes
//! for every operation with a path parameter.
//!
//! A blank names an argument, so a blank naming no argument would send the
//! braces themselves to the server on every call — the "loads clean, fails on
//! the first call" defect. So each `{name}` must be a `takes:` line or a
//! `bind:` line of every action the tool has, refused here otherwise, with the
//! arguments that do exist.

use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::Node;
use std::collections::BTreeSet;

/// Every `{name}` in an address, in the order written.
pub fn blanks(address: &str) -> Vec<String> {
    let mut found = Vec::new();
    let mut rest = address;
    while let Some(open) = rest.find('{') {
        let after = &rest[open + 1..];
        let Some(close) = after.find('}') else { break };
        let name = after[..close].trim();
        if !name.is_empty() && !found.iter().any(|f| f == name) {
            found.push(name.to_string());
        }
        rest = &after[close + 1..];
    }
    found
}

/// Refuse every blank in a `url:` that some action of its tool does not fill.
pub fn check(document: &Node, diags: &mut Diagnostics) {
    let Some(tools) = document.get("tools").and_then(Node::as_map) else {
        return;
    };
    for (name, entry) in tools {
        let Some(fields) = entry.node.as_map() else {
            continue;
        };
        let Some(url) = fields.get("url") else {
            continue;
        };
        let Some(address) = url.node.as_str() else {
            continue;
        };
        let wanted = blanks(address);
        if wanted.is_empty() {
            continue;
        }
        let actions = fields.get("actions").and_then(|a| a.node.as_map());
        let each: Vec<(String, BTreeSet<String>)> = match actions {
            Some(actions) if !actions.is_empty() => actions
                .iter()
                .map(|(action, a)| (action.to_string(), arguments(&a.node)))
                .collect(),
            _ => vec![(String::new(), BTreeSet::new())],
        };
        for (action, has) in each {
            for blank in wanted.iter().filter(|b| !has.contains(*b)) {
                let who = if action.is_empty() {
                    format!("'{name}' has no action to fill it")
                } else if has.is_empty() {
                    format!("its action '{action}' takes no arguments")
                } else {
                    format!(
                        "its action '{action}' takes only {}",
                        has.iter()
                            .map(|h| format!("`{h}`"))
                            .collect::<Vec<_>>()
                            .join(", ")
                    )
                };
                diags.push(Diagnostic::error(
                    "loader/a-blank-in-the-address-nothing-fills",
                    url.key_span.clone().merge(&url.node.span),
                    format!(
                        "'{name}' calls `{address}`, which leaves `{{{blank}}}` for each call to \
                         fill, and {who} — so every call would send the braces themselves."
                    ),
                    format!(
                        "Add `{blank}: text` (or its real shape) under `takes:`, or under `bind:` \
                         when the system fills it rather than the model; or take `{{{blank}}}` out \
                         of `url:`."
                    ),
                ));
            }
        }
    }
}

/// The names an action's call is given: its `takes:` lines and its `bind:` lines.
fn arguments(action: &Node) -> BTreeSet<String> {
    ["takes", "bind"]
        .iter()
        .filter_map(|k| action.get(k).and_then(Node::as_map))
        .flat_map(|m| m.iter().map(|(k, _)| k.to_string()))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use pact_doc::parse_yaml;

    const WORKSPACE: &str = "
tools:
  pets:
    description: The pet shop.
    url: shop/pets/{pet-id}?tag={tag}
    method: get
    actions:
      get:
        description: One pet.
        takes:
          pet-id: whole-number
          tag: text, optional
";

    fn check_text(text: &str) -> Diagnostics {
        let node = parse_yaml(text, camino::Utf8Path::new("workspace.yaml")).expect("parses");
        let mut d = Diagnostics::new();
        d.add_source("workspace.yaml", text);
        check(&node, &mut d);
        d
    }

    #[test]
    fn an_address_whose_blanks_are_all_arguments_is_left_alone() {
        let d = check_text(WORKSPACE);
        assert!(d.is_empty(), "{}", d.render());
        let bound = WORKSPACE.replace("          tag: text, optional\n", "")
            + "        bind:\n          tag: run-inputs.tag\n";
        let d = check_text(&bound);
        assert!(
            d.is_empty(),
            "a bound argument fills a blank too: {}",
            d.render()
        );
    }

    #[test]
    fn a_blank_no_argument_fills_is_refused_with_the_arguments_there_are() {
        let d = check_text(&WORKSPACE.replace("{tag}", "{tags}"));
        assert_eq!(d.items().len(), 1, "{}", d.render());
        let e = &d.items()[0];
        assert_eq!(e.rule, "loader/a-blank-in-the-address-nothing-fills");
        assert!(e.message.contains("`{tags}`"), "{}", e.message);
        assert!(e.message.contains("`pet-id`, `tag`"), "{}", e.message);
        assert!(e.fix.contains("`tags: text`"), "{}", e.fix);
    }

    #[test]
    fn a_blank_on_a_tool_with_no_action_is_refused() {
        let text = "
tools:
  pets:
    description: The pet shop.
    url: shop/pets/{pet-id}
    method: get
";
        let d = check_text(text);
        assert_eq!(d.items().len(), 1, "{}", d.render());
        assert!(d.items()[0].message.contains("no action to fill it"));
    }

    #[test]
    fn the_blanks_are_read_in_order_and_once() {
        assert_eq!(blanks("a/{x}/b/{y}?z={x}"), vec!["x", "y"]);
        assert!(blanks("host/payments").is_empty());
        assert!(blanks("host/{unclosed").is_empty());
        // budFlow's `url_tools.filled` reads them the same way and fills every one: trimmed,
        // anywhere in the path or in a query pair, and `{}` is none.
        assert_eq!(blanks("a/{ x }.json?q=s:{y}&{z}=1"), vec!["x", "y", "z"]);
        assert!(blanks("a/{}").is_empty());
    }
}
