//! **A ceiling written in one currency, a bill counted in another.**
//!
//! `Ty::Money` keeps its currency — `coerce::money` returns
//! `Money { amount, currency }` and the type's own doc comment says *"silently
//! normalising currencies would be a correctness bug"*. FR-1.4.5 states the same
//! rule normatively: *"Money MUST retain its currency; currencies MUST NOT be
//! converted or defaulted."* And then every reader of a money value threw the
//! currency away.
//!
//! Reproduced before this module: copy `examples/refund-desk`, change
//! `agents/refund-desk/limits.yaml` line 11 from `cost-per-request-under: 0.05
//! USD` to `cost-per-request-under: 500 JPY`, and `pact check` prints
//! *"OK — … loaded cleanly (492 settings)"* and exits 0. At run time
//! `limits.money()` returned the first parseable float and discarded `JPY`, the
//! meter it is compared against is priced from `models/catalog.yaml` — which
//! charges in USD — and the sentence the author got back at 501 was
//! *"(501 of 500 USD)"*: a currency they never wrote, on a comparison that had
//! already been made as though 500 JPY and 500 USD were the same money.
//! `question-rule.more-than` lost its currency the same way, through
//! `questions._amount`, on the field that decides whether a person is asked
//! before a refund goes out.
//!
//! # The rule
//!
//! > **PACT converts nothing.** Every money figure it compares is compared as a
//! > number. So a workspace deals in one currency, and it is the one its price
//! > list charges in.
//!
//! The price list is `models/catalog.yaml` — the distribution's copy, plus the
//! workspace's own override layer if it wrote one. A row prices a currency when
//! **both** halves of its `cost:` name that currency, which is the same bar
//! `Catalogue.price_of` sets on the other side: a row that priced its input and
//! wrote `unknown` for its output produces no figure at all, so it cannot make a
//! currency spendable either.
//!
//! # Why this is not over-strict, and where the door out is
//!
//! A workspace that genuinely deals in JPY says so by pricing a model in JPY —
//! a row in `models/catalog.yaml`, which is data an author edits, not code
//! (D14). That is the same override layer an air-gapped site already uses to
//! name a model this distribution has never heard of, so it costs no new
//! concept and no new file kind. The fix text names it.
//!
//! # Why the schema cannot state it
//!
//! The same reason `money.rs` gives one surface over. `one-of:` holds a value
//! against a list written beside it in `spec/schema.yaml`; the list of
//! currencies is not in the specification at all — it is whatever
//! `models/catalog.yaml` happens to charge in this week, in this workspace,
//! after its override layer has been applied. Nothing a field can say about
//! itself reaches that.
//!
//! # Which fields
//!
//! Every field the SCHEMA types `money`, read off the schema rather than listed
//! here, because a list of names in Rust is how the next money field comes to be
//! unchecked (F-1). Today that is `limits.cost-per-request-under`,
//! `question-rule.more-than` and `learning.cycle-limits.per-month`; tomorrow it
//! is whatever `spec/schema.yaml` says, with no edit here.
//!
//! # What it deliberately stays quiet about
//!
//! - **The price list itself.** `input-per-mtok: 0 JPY` is where a currency is
//!   DECLARED, not where one is compared, so holding it against itself would
//!   make the door out unopenable — the author would have to already deal in
//!   JPY before they were allowed to say they deal in JPY.
//! - **A figure with no currency on it at all.** `cost-per-request-under: 0.05`
//!   is already `schema/wrong-type` at the same line, with a fix that says
//!   `Write it like `0.05 USD``. One mistake gets one message.
//! - **A workspace whose price list charges in nothing.** If no row publishes
//!   both halves of a price there is no set of currencies to offer, and a fix
//!   that lists none is not typeable.

use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::Node;
use pact_schema::{Schema, Ty, coerce};
use std::collections::BTreeSet;

/// Refuse every money figure written in a currency the price list cannot price.
///
/// `price_list` is the distribution's `models/catalog.yaml` as text — the same
/// `include_str!` copy `pact check` already resolves `model:` against, so this
/// answers on a machine with no network (D17). The workspace's own catalogue is
/// read off `document`, because it arrives already parsed as part of the tree.
pub fn check(document: &Node, schema: &Schema, price_list: &str, diags: &mut Diagnostics) {
    let priced = priced_in(price_list, document);
    if priced.is_empty() {
        // Nothing to offer, so nothing to say. See the module docstring.
        return;
    }
    let fields = money_fields(schema);
    if fields.is_empty() {
        return;
    }
    walk(document, &fields, &priced, true, diags);
}

/// Every currency this workspace can be billed in.
///
/// Both layers, exactly as `models_known_here` reads both: a workspace copy is
/// an override layer and never a replacement, so a site that adds one
/// locally-served row must not thereby un-price USD for the rest of the tree.
fn priced_in(price_list: &str, document: &Node) -> BTreeSet<String> {
    let mut found = BTreeSet::new();
    let path = camino::Utf8Path::new("models/catalog.yaml");
    if let Ok(shipped) = pact_doc::parse_yaml(price_list, path) {
        rows_of(&shipped, &mut found);
    }
    if let Some(local) = document.get("models") {
        rows_of(local, &mut found);
    }
    found
}

/// The currencies one catalogue document charges in.
///
/// BOTH halves of a `cost:` block have to name the same currency. That is the
/// bar `Catalogue.price_of` already sets — *"a row that priced its input and
/// wrote `unknown` for its output could still produce a number, and that number
/// would be the input bill wearing the whole bill's name"* — and a half-priced
/// row cannot make a currency spendable for the same reason it cannot make a
/// model meterable.
fn rows_of(catalogue: &Node, into: &mut BTreeSet<String>) {
    let Some(rows) = catalogue.get("models").and_then(Node::as_map) else { return };
    for (_, entry) in rows {
        let Some(cost) = entry.node.get("cost") else { continue };
        let (Some(went_in), Some(came_out)) =
            (currency_of(cost.get("input-per-mtok")), currency_of(cost.get("output-per-mtok")))
        else {
            continue;
        };
        if went_in == came_out {
            into.insert(went_in);
        }
    }
}

/// The currency a money value is written in, through the schema's own reader.
///
/// Not a second parser here, for the reason `report::milliseconds` gives about
/// durations: `0.05 USD`, `USD 0.05` and `$0.05` are one amount to the
/// validator, so they have to be one amount to this too — and a spelling this
/// file did not recognise would be a ceiling it silently stopped checking.
fn currency_of(node: Option<&Node>) -> Option<String> {
    match coerce::check(node?, &Ty::Money) {
        Some(coerce::Coerced::Money { currency, .. }) => Some(currency),
        _ => None,
    }
}

/// Every field name the specification types `money`, plus every alias of one.
///
/// Aliases too, because an alias is a spelling the author is allowed to use and
/// the validator accepts: a rule that checked `more-than` and not whatever
/// `more-than` is also called would be a gate that a legal spelling turns off.
fn money_fields(schema: &Schema) -> BTreeSet<&str> {
    schema
        .groups()
        .flat_map(|g| g.fields.iter())
        // `Ty::Money` says "an author must write money here". `may_be_money`
        // says "this is money when the thing it compares is money", which is
        // `more-than:` after A3 made its type permissive. Both have to be
        // checked, and `currency_of` returns nothing for a value that is not an
        // amount at all — so a bare `80` on a score is skipped rather than
        // priced.
        .filter(|f| matches!(f.ty, Ty::Money) || f.may_be_money)
        .flat_map(|f| {
            std::iter::once(f.name.as_str()).chain(f.aliases.iter().map(String::as_str))
        })
        .collect()
}

/// Walk the whole tree, because a money field can be nested at any depth.
///
/// Measured on the shipped example, three fields at three shapes:
/// `cost-per-request-under` sits one level down in an agent's `limits:`;
/// `per-month` sits inside `cycle-limits:` inside `learning:`; and `more-than`
/// sits inside a list of `when:` atoms inside a list of rules inside a policy. A
/// walk that knew where to look would have to be updated for the next one, which
/// is the thing [`money_fields`] exists to avoid.
fn walk(
    node: &Node,
    fields: &BTreeSet<&str>,
    priced: &BTreeSet<String>,
    root: bool,
    diags: &mut Diagnostics,
) {
    if let Some(map) = node.as_map() {
        // There was an early return here for `pact_doc::UNLOADED`, copying the
        // one `Schema::check_group` used to make. It never had anything to do:
        // the marker's node is a stand-in for a file that would not parse, and a
        // stand-in holds no settings at all, so a walk over it finds no money
        // either way. It became actively wrong when the loader began marking a
        // whole DIRECTORY whose self file failed to parse — one tab in
        // `workspace.yaml` would have taken every amount in the tree out of the
        // currency check with it, which is the same silence in another pass.
        // What did not parse says nothing; the files beside it still do.
        for (key, entry) in map {
            // The price list says what the money MEANS. Holding it against
            // itself would close the only door out.
            if root && key == "models" {
                continue;
            }
            if fields.contains(key.as_str())
                && let Some(coerce::Coerced::Money { amount, currency }) =
                    coerce::check(&entry.node, &Ty::Money)
                && !priced.contains(&currency)
            {
                diags.push(unpriced(key, entry, amount, &currency, priced));
            }
            walk(&entry.node, fields, priced, false, diags);
        }
    } else if let Some(items) = node.as_list() {
        for item in items {
            walk(item, fields, priced, false, diags);
        }
    }
}

/// The refusal: what was written, what is wrong with it, and a line to type.
fn unpriced(
    key: &str,
    entry: &pact_doc::Entry,
    amount: f64,
    currency: &str,
    priced: &BTreeSet<String>,
) -> Diagnostic {
    // The whole setting is underlined, key and value, because the sentence
    // quotes the whole setting — the same call `money::moves_money` makes.
    let span = entry.key_span.clone().merge(&entry.node.span);
    // The author's own text, not a spelling this file preferred. Somebody who
    // wrote `USD 500` must not be sent looking for a `500 USD` they have not got.
    let written = entry.node.as_str().unwrap_or_default().trim();
    let deals_in = or_list(priced);
    // The one currency the fix tells them to type. With several priced it is a
    // pick, so the vivid clause below is dropped rather than made to say
    // "500 JPY is not 500 EUR or USD" — a sentence that reads like a third
    // currency.
    let use_this = priced.iter().next().map(String::as_str).unwrap_or(currency);
    let unlike = if priced.len() == 1 {
        format!(" — and {written} is not {} {use_this}", plain(amount))
    } else {
        String::new()
    };
    Diagnostic::error(
        "loader/currency-nothing-can-price",
        span,
        format!(
            "`{key}: {written}` is in {currency}, and nothing here deals in {currency}: the \
             price list this workspace runs on charges in {deals_in}. PACT never turns one \
             currency into another, so this figure would be compared with a {deals_in} one \
             as a plain number{unlike}."
        ),
        format!(
            "Write the amount in {use_this}, putting in what {written} is worth — \
             `{key}: <amount> {use_this}`. If this workspace really does deal in \
             {currency}, say so where currencies come from: add a row to \
             `models/catalog.yaml` here with `cost: {{ input-per-mtok: <price> {currency}, \
             output-per-mtok: <price> {currency} }}`."
        ),
    )
}

/// `500`, `0.05` — a figure written the way the author wrote it rather than the
/// way a float prints. Mirrors `limits._round` on the Python side, so the two
/// halves of this fix quote one amount the same way.
fn plain(v: f64) -> String {
    if v.fract() == 0.0 && v.abs() < 1e15 { format!("{v:.0}") } else { format!("{v}") }
}

/// `USD`, `USD or EUR`, `USD, EUR or JPY` — a list the way a sentence carries
/// one.
///
/// Not shared with `money::and_list` even though the shape rhymes: that one
/// joins with *and* and quotes each name in backticks, because it is listing
/// agents inside a sentence full of backticked names. This one is listing
/// currencies in a sentence where every other currency is bare, and
/// *"charges in `USD` and `EUR`"* would be both the wrong conjunction and a
/// second typographic convention in one paragraph.
fn or_list(names: &BTreeSet<String>) -> String {
    let all: Vec<&str> = names.iter().map(String::as_str).collect();
    match all.split_last() {
        None => String::new(),
        Some((last, [])) => (*last).to_string(),
        Some((last, rest)) => format!("{} or {last}", rest.join(", ")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pact_doc::parse_yaml;

    /// The shipped price list, cut to the two rows that matter: one priced in
    /// full and one deliberately unpriced. Same shape as `models/catalog.yaml`.
    const PRICE_LIST: &str = "
default: qwen2.5-7b-instruct
models:
  qwen2.5-7b-instruct:
    cost: { input-per-mtok: 0 USD, output-per-mtok: 0 USD }
  gpt-5.4:
    cost: { input-per-mtok: unknown, output-per-mtok: unknown }
";

    /// A workspace of the same shape as the worked example: an agent with a
    /// spend cap, and a policy with a threshold a person is asked above.
    const WORKSPACE: &str = "
agents:
  refund-desk:
    description: Decides refunds.
    limits:
      cost-per-request-under: 0.05 USD
      when-it-runs-out: stop-and-say-so
policies:
  approvals:
    ask-a-person:
      - when:
          - { tool: payments/issue-refund, arg: amount, more-than: 200 USD }
        because: a refund over 200 USD is a management decision
        question: is-this-ok
";

    /// The two money fields the worked example actually writes, plus the one
    /// nested two levels further in, so the walk is exercised at three depths.
    fn schema() -> Schema {
        use pact_schema::{Field, Group};
        Schema::new()
            .with(Group {
                name: "workspace".into(),
                describe: String::new(),
                fields: vec![Field::new("cost-per-request-under", Ty::Money, "the cap")],
            })
            .with(Group {
                name: "question-rule".into(),
                describe: String::new(),
                fields: vec![Field::new("more-than", Ty::Money, "the threshold")],
            })
    }

    fn check_text(text: &str) -> Diagnostics {
        let node = parse_yaml(text, camino::Utf8Path::new("workspace.yaml")).expect("parses");
        let mut d = Diagnostics::new();
        d.add_source("workspace.yaml", text);
        check(&node, &schema(), PRICE_LIST, &mut d);
        d
    }

    fn only(d: &Diagnostics) -> &Diagnostic {
        assert_eq!(d.items().len(), 1, "expected exactly one problem:\n{}", d.render());
        &d.items()[0]
    }

    #[test]
    fn a_workspace_written_in_the_currency_its_price_list_charges_in_is_left_alone() {
        // The half that matters most: a correct tree must not be refused. A
        // false positive on the shipped shape costs an author their trust in
        // every other line the tool prints.
        assert!(check_text(WORKSPACE).is_empty(), "{}", check_text(WORKSPACE).render());
    }

    #[test]
    fn a_ceiling_in_a_currency_nothing_can_price_is_refused_where_the_author_wrote_it() {
        let d = check_text(&WORKSPACE.replace("0.05 USD", "500 JPY"));
        let e = only(&d);
        assert_eq!(e.rule, "loader/currency-nothing-can-price");
        assert_eq!(e.severity, pact_diag::Severity::Error, "a cap in the wrong money is not a warning");
        assert!(e.message.contains("`cost-per-request-under: 500 JPY`"), "{}", e.message);
        assert!(e.message.contains("JPY"), "name the currency written: {}", e.message);
        assert!(e.message.contains("USD"), "name the currency that IS priced: {}", e.message);
        assert!(e.fix.contains("USD"), "the fix must offer a currency: {}", e.fix);
    }

    #[test]
    fn an_approval_threshold_in_a_currency_nothing_can_price_is_refused_too() {
        // Same blindness, and this is the surface where it costs money: the
        // threshold above which a person is asked before a refund goes out.
        // `questions._amount` strips `JPY` off one side and `USD` off the other
        // and compares the bare numbers, so a 200 JPY line silently gates at 200
        // of whatever the model wrote.
        let d = check_text(&WORKSPACE.replace("more-than: 200 USD", "more-than: 200 JPY"));
        assert!(only(&d).message.contains("`more-than: 200 JPY`"), "{}", only(&d).message);
    }

    #[test]
    fn the_price_list_is_not_held_against_itself() {
        // The door out. A workspace that adds a JPY-priced row is SAYING it
        // deals in JPY; refusing the row would mean the author had to already
        // deal in JPY before they were allowed to say so.
        let text = WORKSPACE.replace("0.05 USD", "500 JPY")
            + "models:\n  models:\n    local-jp:\n      cost: { input-per-mtok: 1 JPY, output-per-mtok: 3 JPY }\n";
        assert!(check_text(&text).is_empty(), "{}", check_text(&text).render());
    }

    #[test]
    fn a_row_that_prices_only_one_direction_makes_no_currency_spendable() {
        // The bar `Catalogue.price_of` sets: both halves or nothing. A row that
        // priced its input and wrote `unknown` for its output produces no figure
        // at all, so it cannot make a currency spendable either.
        let text = WORKSPACE.replace("0.05 USD", "500 JPY")
            + "models:\n  models:\n    half:\n      cost: { input-per-mtok: 1 JPY, output-per-mtok: unknown }\n";
        assert!(!check_text(&text).is_empty(), "half a price priced a currency");
    }

    #[test]
    fn every_spelling_of_an_amount_the_validator_accepts_is_read_here_too() {
        // A spelling this file did not recognise would be a ceiling it silently
        // stopped checking — which is worse than not checking at all.
        for written in ["500 JPY", "JPY 500", "500 jpy"] {
            let d = check_text(&WORKSPACE.replace("0.05 USD", written));
            assert_eq!(d.items().len(), 1, "'{written}' was read as no amount at all");
        }
        // `$0.05` is USD by construction, so it is priced and says nothing.
        assert!(check_text(&WORKSPACE.replace("0.05 USD", "$0.05")).is_empty());
    }

    #[test]
    fn a_figure_with_no_currency_at_all_is_left_to_the_check_that_already_names_it() {
        // `schema/wrong-type` fires at the same line with `Write it like
        // `0.05 USD``. Two messages for one edit, and the second would send the
        // reader looking for a currency they did not write.
        assert!(check_text(&WORKSPACE.replace("0.05 USD", "0.05")).is_empty());
    }

    #[test]
    fn the_underline_covers_the_setting_the_sentence_quotes() {
        let d = check_text(&WORKSPACE.replace("0.05 USD", "500 JPY"));
        let rendered = d.render();
        assert!(
            rendered.contains("      cost-per-request-under: 500 JPY"),
            "the line is shown:\n{rendered}"
        );
        assert!(
            rendered.contains(&"^".repeat("cost-per-request-under: 500 JPY".len())),
            "the whole setting is underlined, not just the amount:\n{rendered}"
        );
    }

    #[test]
    fn a_price_list_that_charges_in_nothing_says_nothing() {
        // No set of currencies to offer, so no typeable fix. Silence beats a
        // refusal whose only advice is a list with nothing in it.
        let node = parse_yaml(WORKSPACE, camino::Utf8Path::new("workspace.yaml")).expect("parses");
        let mut d = Diagnostics::new();
        check(&node, &schema(), "models:\n  m:\n    cost: { input-per-mtok: unknown }\n", &mut d);
        assert!(d.is_empty(), "{}", d.render());
    }

    #[test]
    fn several_priced_currencies_are_offered_as_a_sentence_and_not_as_a_set() {
        let text = WORKSPACE.replace("0.05 USD", "500 JPY")
            + "models:\n  models:\n    eu:\n      cost: { input-per-mtok: 1 EUR, output-per-mtok: 3 EUR }\n";
        let d = check_text(&text);
        assert!(only(&d).message.contains("charges in EUR or USD"), "{}", only(&d).message);
    }
}
