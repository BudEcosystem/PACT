//! Schema validation for PACT documents.
//!
//! **The schema is data, not code.** It is itself a PACT document, loaded by the
//! same loader, so adding a field to the specification means editing a YAML file
//! — no Rust changes, no recompile. That is invariant E-3 ("new authoring
//! surface is free") and F-1 ("no capability-affecting literal buried in the
//! core") made concrete rather than aspirational.
//!
//! # Why not JSON Schema
//!
//! JSON Schema is the obvious candidate and it was rejected for one reason:
//! its error messages. `must be valid under one of the given schemas` is
//! actionable for an engineer and useless to the support-operations lead who is
//! decision D13's actual user. Validation here is deliberately small — the
//! constructs PACT needs, and nothing else — so that every failure can produce
//! the four-part diagnostic (where/what/why/**how**) that O7.3 requires.
//!
//! JSON Schema remains the *interchange* format for tool and output contracts,
//! where the consumer is a model or another framework rather than a person.

pub mod coerce;
pub mod elsewhere;
pub mod from_doc;
pub mod sentences;
pub mod shape;
pub mod suggest;
pub mod summary;

use indexmap::IndexMap;
use pact_diag::{Diagnostic, Diagnostics, Span};
use pact_doc::{Map, Node, Value};

/// What a field is allowed to hold.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Ty {
    /// Free text.
    Text,
    /// A yes/no answer. Accepts `yes`/`no`/`true`/`false`/`on`/`off`, because a
    /// non-technical author writes whichever comes naturally (see [`coerce`]).
    YesNo,
    Number,
    Integer,
    /// A length of time: `2s`, `500ms`, `1m30s`, `5 minutes`, `1d`.
    ///
    /// A number and a unit — `ms`, `s`, `m`, `h`, `d`, or their long names —
    /// with the space between them optional and several parts allowed to run
    /// together. The leniency is deliberate and matches
    /// `pact_adapters.limits.seconds` on the other side; what it was missing was
    /// anyone being TOLD, so the friendliest spellings a non-coder reaches for
    /// (`5 minutes`, `1d`) worked and were undiscoverable. Both [`Ty::describe`]
    /// and the fix in [`wrong_type`] now name the whole grammar.
    ///
    /// It is always more than nothing: see [`Schema::check_floor`]. And it is
    /// never longer than the milliseconds it is counted in, which used to crash
    /// the checker rather than say so: see [`Schema::check_ceiling`].
    Duration,
    /// An amount of money: `0.05 USD`.
    Money,
    /// A percentage: `90%`. Always a share of the whole, so `0%..=100%` — the
    /// range is a property of the type, checked in [`coerce`], and not something
    /// each field carrying one has to remember.
    Percent,
    /// A comparison an author can write inline: `> 80`, `>= 0.8`.
    Threshold,
    /// A count of tokens: `32k`, `128k`, `1m`, `200000`.
    ///
    /// It exists because `needs.context-at-least` was `type: text`, so
    /// `context-at-least: quite a lot really` loaded clean and was then compared
    /// against a real context window by the resolver. Every other quantity in
    /// PACT has a type.
    ///
    /// And it is never more than the whole number it is counted in, which used
    /// to saturate to the largest number there is and load clean: see
    /// [`Schema::check_ceiling`].
    Size,
    /// A plain file name: no folders, no climbing out, no leading dot.
    ///
    /// `watch.writes-to`'s own help promises the refusal — *"A name with a `/`
    /// in it, or one that climbs out with `..`, is refused and told what to type
    /// instead"* — and for a round the only thing that kept the promise was
    /// `watches.py`, in another language, in a process the author never starts.
    /// A rule stated in the help of a `tier: core` field has to hold where the
    /// author is.
    FileName,
    /// One line of an answer's schema: `yes or no`, `money`, `one of a, b, c`.
    ///
    /// The vocabulary is closed and lives in [`Ty::AnswerShape`]'s own data,
    /// supplied by `shapes:` on the field — the same shape `parts:` takes for an
    /// address — so the next spelling is a line of YAML. It was checked by
    /// `questions.Shape.parse` and by nothing at check time, which is why the
    /// worked example shipped four lines its own parser refuses.
    AnswerShape(Vec<(String, Vec<String>)>),
    /// How the answers of several items or branches become one (02W §2.0):
    /// `keep-all`, `vote`, `top 3 lowest by confidence`. A closed vocabulary
    /// supplied by `combine-rules:` on the field, one entry per rule with every
    /// spelling that means it. A spelling may hold `<n>` (a whole number of at
    /// least 1) and `<field>` (one word) where the author writes their own.
    CombineRule(Vec<(String, Vec<String>)>),
    /// The one time expression (02W §2.0): a length of time after the stage
    /// starts (`48h`), or a `moment` group (`{at: input.starts-at, before:
    /// 24h}`). Every field that takes a time takes this, and only this.
    Moment,
    /// The right-hand side of a comparison (02W §2.0): a figure or a word
    /// written as the value it is compared with is declared (`5000 USD`, `85%`,
    /// `enterprise`), or a `comparand` group with exactly one of `value:`,
    /// `now-plus:` and `now-minus:`. Whether the figure fits the value is
    /// `pact-loader`'s `conditions.rs`, the only place that reads both.
    Comparand,
    /// One of a fixed set of words.
    OneOf(Vec<String>),
    /// A list of values of one type.
    ListOf(Box<Ty>),
    /// A named group of fields.
    Group(String),
    /// A free-form map from names to values of one type — used where the keys
    /// are author-chosen (agent names, tool names).
    MapOf(Box<Ty>),
    /// Where in a run something happens: `step.tool.before`. Each position is a
    /// closed list, and the lists are **data** — they come from `parts:` on the
    /// field in `spec/schema.yaml`, not from a `match` in here, for the reason
    /// F-1 gives: a vocabulary buried in the core makes the next entry cost a
    /// recompile instead of a line of YAML.
    ///
    /// It exists because for one round `when:` was `type: text` with no
    /// constraint at all, so `pact check` — the only tool the D13 author runs —
    /// said `when: banana` was fine and the refusal happened later, in another
    /// language, in a process they never start.
    ///
    /// The second list is `reaches:` — the addresses this particular field can
    /// be bound to and have something HAPPEN. `parts:` says whether an address
    /// is well formed; it cannot say whether the combination is one a run ever
    /// arrives at, and `session.tool.completed` is three perfectly good words
    /// that nothing ever emits. It is a second list rather than a narrowing of
    /// the first because the two fields that carry addresses reach different
    /// sets: a watch can observe thirty moments, an interceptor runs at five.
    /// Empty means "not checked" — the honest state for a field whose reachable
    /// set nothing here knows.
    EventAddress(Vec<(String, Vec<String>)>, Vec<String>),
    /// Explicitly unconstrained. Used for pass-through and `x-` extensions.
    Anything,
}

impl Ty {
    /// Plain-language description, for diagnostics. Never a type name.
    pub fn describe(&self) -> String {
        match self {
            Ty::Text => "some text".into(),
            Ty::YesNo => "yes or no".into(),
            Ty::Number => "a number".into(),
            Ty::Integer => "a whole number".into(),
            Ty::Duration => "a length of time, like `2s`, `500ms` or `5 minutes`".into(),
            Ty::Money => "an amount of money, like `0.05 USD`".into(),
            Ty::Percent => "a percentage, like `90%`".into(),
            Ty::Threshold => "a comparison, like `> 80`".into(),
            Ty::Size => "a size, like `32k` or `200000`".into(),
            Ty::FileName => "a file name with no folders in it, like `tool-calls.jsonl`".into(),
            Ty::AnswerShape(shapes) => format!(
                "a shape an answer can have — {}",
                shapes
                    .iter()
                    .map(|(name, _)| name.as_str())
                    .collect::<Vec<_>>()
                    .join(", ")
            ),
            Ty::CombineRule(rules) => format!(
                "a way of combining answers — {}",
                rules
                    .iter()
                    .filter_map(|(_, spellings)| spellings.first().map(String::as_str))
                    .collect::<Vec<_>>()
                    .join(", ")
            ),
            Ty::Moment => "a length of time like `48h`, or a moment like \
                           `{at: input.starts-at, before: 24h}`"
                .into(),
            Ty::Comparand => "a figure like `5000 USD` or a word like `enterprise`, or one of \
                              `{value: <binding>}`, `{now-plus: 14 days}`, `{now-minus: 30 days}`"
                .into(),
            Ty::OneOf(v) => format!("one of: {}", v.join(", ")),
            Ty::ListOf(t) => format!("a list, where each item is {}", t.describe()),
            Ty::Group(name) => format!("a set of {name} settings"),
            Ty::MapOf(t) => format!("a set of named entries, each one {}", t.describe()),
            Ty::EventAddress(parts, _) => format!(
                "a moment in a run, written as {}",
                parts
                    .iter()
                    .map(|(name, _)| format!("<{name}>"))
                    .collect::<Vec<_>>()
                    .join(".")
            ),
            Ty::Anything => "anything".into(),
        }
    }
}

#[derive(Debug, Clone)]
pub struct Field {
    pub name: String,
    pub ty: Ty,
    pub required: bool,
    /// One line explaining the field to a non-technical author.
    pub help: String,
    /// A NAME for the setting — one noun phrase — for the sentences that quote
    /// this field inside a refusal about a different one.
    ///
    /// `help:` and this are two strings because they are read at two moments.
    /// Help is read by somebody deciding whether they want the setting, so it
    /// opens with the condition it applies under; a diagnostic drops it inside
    /// *"…so nothing says X"*, which needs the thing rather than the condition.
    /// Taking the first clause of the help and hoping produced *"so nothing says
    /// with `enough-of-them`"* on four of the ten `needed-when:` pairs.
    ///
    /// Empty for most fields, and that is the intended state: [`summary`]
    /// falls back to the first clause of the help, and `from_doc` refuses the
    /// specification at load time where that fallback would not read as English.
    /// So the line is owed exactly where it is needed, and nowhere else.
    pub summary: String,
    /// Alternative spellings accepted on input and reported as the canonical
    /// name. Import compatibility lives here (invariant P-3).
    pub aliases: Vec<String>,
    /// Other fields of the same group that must be set whenever this one is.
    ///
    /// `required` says "this field is always needed"; this says "this field
    /// makes *that* one needed", which is the shape half of PACT's governance
    /// actually has. A ceiling with no declared action, a schedule with no
    /// agent, an escalation with nobody to escalate to: each is a pair where
    /// one half alone is not a smaller version of the feature, it is a hole.
    ///
    /// It lives here rather than as a rule in the validator because the
    /// alternative is a Rust `if` per pairing — a capability-affecting literal
    /// buried in the core, which invariant F-1 forbids and which would make the
    /// next pairing cost a recompile instead of a line of YAML.
    pub needs_also: Vec<String>,
    /// Other fields this one makes necessary, but only when it holds a
    /// particular value: `(that field, the value this one has to hold)`.
    ///
    /// `needs-also:` fires on PRESENCE, which is right for `steps-at-most` — any
    /// ceiling needs an action — and wrong for the three pairings that turned up
    /// this round. `spends-money: no` must not demand a same-request key;
    /// `waits-for: enough-of-them` needs `enough-is:` and the other four spellings
    /// do not; a `does: ask-someone` stage needs `asks:` and a `does: think`
    /// stage has nothing to ask. Each was refused by the Python side at run time
    /// and accepted by `pact check`, which is the split this attribute closes.
    ///
    /// It is data here for the same reason `needs_also` is: the alternative is
    /// one Rust `if` per pairing, which F-1 forbids and which would make the next
    /// pairing cost a recompile instead of a line of YAML.
    pub needed_when: Vec<(String, String)>,
    /// For a closed choice describing a CONDITION, what has to be reachable for
    /// each value to hold: `(the value, what the agent must be able to reach)`.
    ///
    /// `available-when: this-agent-has-procedures` is a claim about a *different*
    /// part of the tree — the agent doing the using, not the tool being used —
    /// and that is the half a type cannot state. It lived in a hand-written table
    /// of three rows in `crates/pact-loader/src/available.rs`, and two of them
    /// named a field the `agent` group does not have (`skills`, `resources`), so
    /// the condition could never hold and the warning could never be fixed: the
    /// text it offered was itself refused when typed. The third row of the
    /// iteration beside it read `("skills", "knows")`, and no agent has `knows:`,
    /// so skills were never checked at all.
    ///
    /// It is data here for the reason `needed_when` is data: a table of names in
    /// Rust is not held against the schema, and six of the names across the four
    /// such tables were wrong. Written here, every value is checked in both
    /// directions — the key must be one of this field's own `choices:`, and the
    /// target must be something an agent can actually reach.
    ///
    /// The target is either a field of the `agent` group (`team`) or a workspace
    /// collection the agent reaches through its `names:` edges (`skills`,
    /// `resources`). One question — *can this agent get to one of those?* — not
    /// two mechanisms.
    pub satisfied_by: Vec<(String, String)>,
    /// Whether a folder of prose is an acceptable way to write this text.
    ///
    /// The Expansion Rule says a directory is a field, and for two fields that
    /// is the whole point: `agents/<name>/instructions.md` and a skill's
    /// `SKILL.md` body are the same thing as the line, written where there is
    /// room for it. A folder of files under `instructions/` arrives as a map of
    /// prose and has to be accepted.
    ///
    /// It was gated on the TYPE, which is one predicate short. `Ty::Text` also
    /// covers the twenty-two fields that carry `names:` — `agent.loop`,
    /// `agent.policy`, `tool.connect`, `evals.graded-by` and the rest — and for
    /// those a map is not a folder of prose, it is a mistake. MEASURED:
    /// `loop: carefull` was refused with the six real loops offered, while
    /// `loop: {banana: purple}` printed "OK — loaded cleanly" and skipped name
    /// resolution altogether. One missing predicate turned off a check that was
    /// already written, on twenty-two fields.
    ///
    /// No field may carry both this and `names:`, and
    /// `a_folder_of_prose_is_never_a_name` says so.
    pub may_be_a_folder: bool,
    /// Whether this field's value can name somewhere outside the workspace.
    ///
    /// `allow-egress:`'s own help promises *"which parts of this system are
    /// allowed to talk to something outside this box. Empty means nothing is."*
    /// Its six choices were all MODEL roles, because models were the only
    /// reachers anything checked — so under `allow-egress: []` a tool with
    /// `url: https://vendor.example.com/upload`, `method: post` and an upload
    /// action printed "OK — loaded cleanly". That door needs no resource file at
    /// all, which is why it is the one an attacker writes.
    ///
    /// It is an attribute rather than a list in Rust for the reason B15 gives:
    /// a table of field names that nothing holds against the schema is a table
    /// that comes to name fields the schema does not have. The sixth outbound
    /// address joins by existing.
    pub reaches_outside: bool,
    /// Exactly one of these fields must be set whenever this one is.
    ///
    /// `needs_also` fires on PRESENCE and names one field, so it could say
    /// "`arg:` needs `more-than:`" and could not say "and exactly one way of
    /// comparing it". That is why A3 could not be written: `arg:` carried
    /// `needs-also: [more-than]`, so `{tool: t/go, arg: reason, is: fraud}` was
    /// refused with *"'arg' is set, but 'more-than' is not"* — a rule the author
    /// had written correctly.
    ///
    /// `crates/pact-loader/src/reach.rs` states the same shape in its own words
    /// for a tool's transport — *"exactly one of these three is a statement
    /// about a set … and a field can say neither of those things about its
    /// siblings"* — which is the second use, already visible, that makes this an
    /// attribute rather than one more module.
    pub needs_one_of: Vec<String>,
    /// Whether this field's value is an amount of money WHEN the thing it
    /// compares is one.
    ///
    /// `more-than:` was `type: money`, and that carried two facts at once: the
    /// shape an author must write, and the fact that `currency.rs` has to check
    /// it. Only the first was wrong — a lead score gated with `more-than: 80`
    /// was told to write `0.05 USD` — so the type became permissive and this
    /// says the second thing on its own.
    ///
    /// Without it, `money_fields` (which selects on `Ty::Money`) silently
    /// stopped covering the one surface where a mispriced currency costs money:
    /// `more-than: 200 JPY` on a desk whose refunds run to hundreds gates at
    /// about 1.30 USD.
    pub may_be_money: bool,
    /// Maps whose keys this field's value has to be one of.
    ///
    /// A bare name is a map at the top of the workspace (`questions`); a `^`
    /// prefix means the nearest enclosing block that has such a key (`^steps`,
    /// for a stage routing to another stage of its own loop). Several may be
    /// given, and the value may name any of them.
    ///
    /// This exists because for one round it did not, and every reference typo a
    /// non-coder makes — `loop: carefull`, `asks: keep-goin`,
    /// `then: {answered: repl}` — loaded with zero diagnostics and failed at run
    /// time in another language, in a process the author never starts.
    pub names: Vec<String>,
    /// Maps whose keys the KEYS of this field's value have to be one of.
    ///
    /// Written the same way `names` is, resolved by the same walk, and reported
    /// with the same `schema/no-such-name` sentence — because it is the same
    /// question asked one level over. `names:` reaches a value; a field typed
    /// `map of ...` has author-chosen keys, and until this existed those keys
    /// were held against nothing at all.
    ///
    /// Two of them mattered. `agent.team`'s own help says *"Give each one a
    /// folder under `agents/`"*, and a member with no folder — `polcy-checker:`
    /// — loaded clean, was offered to the model as somebody it could ask, and
    /// parked the run waiting for an agent that does not exist.
    /// `teamwork.shares`' keys are the same names again, and a misspelt one
    /// gave the real member a slice of 0.0 while the typo held 60% of the pot
    /// (`Pool.share_of`, `delegation.py`).
    pub key_names: Vec<String>,
    /// Literal values accepted besides a name: `done`, `pact:loop/standard`.
    pub or_one_of: Vec<String>,
    /// The smallest number this field may hold. `at-most: 0` on a stage means a
    /// stage that may never run, which is a typo and not a setting.
    pub at_least: Option<i64>,
    /// The closed vocabulary of sentences this field's values must come from,
    /// and the two sibling fields each sentence is held against.
    ///
    /// Here for the same reason `names` is: without it, `rules:` was free text,
    /// `pact check` accepted a sentence nothing can carry out, and the four that
    /// work were written out in `help:` for a person to read and nowhere for a
    /// machine to check. See [`sentences`].
    pub forms: Option<sentences::Forms>,
    /// The powers this field's sentences may use, when the kind FIXES them
    /// instead of reading them off a sibling field.
    ///
    /// `forms.declares` names a field — `may:` on an interceptor — and that is
    /// right where a document chooses what it may do. `redaction.yaml` does not
    /// choose: it hides, and it does nothing else, so there is no `may:` line to
    /// read and there should not be one (a required list with one choice is the
    /// R58 shape: one sensible value and nothing else to say).
    ///
    /// It exists because the two kinds now SHARE one sentence list by anchor.
    /// Without it, `hide:` would have been handed `stop and say "…"` and `go to
    /// the <stage> stage instead` — two sentences a redaction cannot perform —
    /// and the `declares:` check would have passed them vacuously, since a
    /// missing `may:` reads as no powers claimed and the check only fires on a
    /// power claimed and not granted. A sentence that loads and does nothing is
    /// exactly what the vocabulary exists to end.
    ///
    /// Data rather than a Rust `if` for the kind, for the reason `needs_also`
    /// gives: the alternative buries a capability decision in the core and makes
    /// the next kind that shares a vocabulary cost a recompile (F-1).
    pub always_may: Vec<String>,
}

impl Field {
    pub fn new(name: impl Into<String>, ty: Ty, help: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            ty,
            required: false,
            help: help.into(),
            summary: String::new(),
            aliases: Vec::new(),
            needs_also: Vec::new(),
            needed_when: Vec::new(),
            satisfied_by: Vec::new(),
            may_be_a_folder: false,
            reaches_outside: false,
            needs_one_of: Vec::new(),
            may_be_money: false,
            names: Vec::new(),
            key_names: Vec::new(),
            or_one_of: Vec::new(),
            at_least: None,
            forms: None,
            always_may: Vec::new(),
        }
    }

    #[must_use]
    pub fn required(mut self) -> Self {
        self.required = true;
        self
    }

    #[must_use]
    pub fn alias(mut self, a: impl Into<String>) -> Self {
        self.aliases.push(a.into());
        self
    }

    #[must_use]
    pub fn needs_also(mut self, other: impl Into<String>) -> Self {
        self.needs_also.push(other.into());
        self
    }

    #[must_use]
    pub fn names(mut self, map: impl Into<String>) -> Self {
        self.names.push(map.into());
        self
    }

    #[must_use]
    pub fn key_names(mut self, map: impl Into<String>) -> Self {
        self.key_names.push(map.into());
        self
    }

    #[must_use]
    pub fn or_one_of(mut self, literal: impl Into<String>) -> Self {
        self.or_one_of.push(literal.into());
        self
    }
}

/// A named group of fields — one document kind, or a nested block within one.
///
/// There is no `open:` flag. It was read out of the schema document and it
/// turned off the unknown-field check for a whole kind, which is exactly the
/// "unvalidated group is an unclassified group" LOAD-13 forbids: §8.2's
/// governance zone is computed from `surface:`, and a field nothing knows about
/// has no `surface:` at all. The extension point that survives is the `x-`
/// prefix, which is per FIELD and per author rather than per kind.
#[derive(Debug, Clone, Default)]
pub struct Group {
    pub name: String,
    pub fields: Vec<Field>,
    /// The plain-language phrase a diagnostic uses instead of `name`.
    ///
    /// `then:` holds a group whose fields are the three ways a stage can end.
    /// Saying "'finished' is not something an outcome can have" is grammatical
    /// and wrong-headed; the author wrote an outcome, not a property of one. So
    /// the group carries the sentence it wants: *"'finished' is not an outcome a
    /// stage can end in."* Empty means the group's own name is used.
    pub describe: String,
}

/// A set of names the DISTRIBUTION knows about, which a `names:` field may
/// resolve against as well as against a map in the workspace.
///
/// It exists because of one field. `agent.model:` names a model, and the list
/// of models is `models/catalog.yaml` — a file the author never writes, that
/// ships with the product, and that is therefore in no workspace map. Without
/// this, `model: qwen2.5-7b-instrukt` loaded clean and failed at run time in
/// another language, which is precisely what `names:` was added to stop; with a
/// plain `names: models` it would have failed the other way, refusing every
/// correct pin in every workspace that never wrote a catalogue of its own.
///
/// Written as data rather than a branch, so the second one costs a line.
#[derive(Debug, Clone, Default)]
pub struct Known {
    /// What to call it in a diagnostic — "the model catalogue", not `pact:models`.
    pub label: String,
    /// What a reader does about a name that is genuinely new, in words they can
    /// act on. This is the half a list of choices cannot give them.
    pub add: String,
    pub names: std::collections::BTreeSet<String>,
}

/// A name a sentence named, and where the author wrote it.
///
/// Produced by [`Schema::names_in_sentences`]. It carries the whole sentence as
/// well as the name, because a refusal about one word inside a line of prose is
/// unreadable without the line.
#[derive(Debug, Clone)]
pub struct SentenceName {
    /// The workspace collection the hole resolves against — `tools`, `programs`.
    pub collection: String,
    /// What the author wrote in the hole, with the article stripped.
    pub name: String,
    /// The whole sentence, as typed.
    pub said: String,
    /// The field the sentence was written in — `rules`, `hide`.
    pub field: String,
    pub at: Span,
}

#[derive(Debug, Clone, Default)]
pub struct Schema {
    groups: IndexMap<String, Group>,
    /// Namespaces the distribution supplies, keyed by the `pact:<name>` a
    /// field's `names:` writes.
    known: IndexMap<String, Known>,
}

impl Schema {
    pub fn new() -> Self {
        Self::default()
    }

    #[must_use]
    pub fn with(mut self, g: Group) -> Self {
        self.groups.insert(g.name.clone(), g);
        self
    }

    /// Teach this schema a set of names the distribution knows about.
    #[must_use]
    pub fn knowing(mut self, namespace: impl Into<String>, known: Known) -> Self {
        self.known.insert(namespace.into(), known);
        self
    }

    pub fn group(&self, name: &str) -> Option<&Group> {
        self.groups.get(name)
    }

    /// Every group the specification declares, in the order it declares them.
    ///
    /// Here so that a check living outside this crate can ask the SCHEMA which
    /// fields carry a given type instead of keeping its own list of names in
    /// Rust. `currency.rs` needs "every field that holds an amount of money",
    /// and the alternative — three field names written out in a Rust `const` —
    /// is the capability-affecting literal F-1 forbids: the next money field
    /// would load cleanly in a currency nothing can price, because the list in
    /// the core had not been updated to know about it.
    pub fn groups(&self) -> impl Iterator<Item = &Group> {
        self.groups.values()
    }

    /// Every name a sentence hole resolved against a workspace map.
    ///
    /// A field with `forms:` holds prose — `replace the answer with what
    /// house-style returns` — and the words inside the angle brackets are names
    /// of real documents. [`Schema::validate`] already resolves them, which is
    /// what refuses a sentence naming a program this workspace has not got.
    ///
    /// Two checks outside this crate need the same answer, and were each getting
    /// it wrong in their own way for want of it. `unnamed.rs` asks "does any line
    /// name this?" by looking at whole string values, so a name inside a sentence
    /// was invisible and the program it named was reported as one nothing
    /// reaches — a false positive on a reference that resolves. `programs.rs`
    /// asks whether a rewriting program is `pure`, which it cannot ask without
    /// knowing which program the sentence names.
    ///
    /// So the walk happens once, here, beside the vocabulary it reads, and both
    /// of them read the result. Doing it twice would be two parsers for one
    /// sentence, which is how the resolver and the reachability register came to
    /// disagree about the same line in the first place.
    pub fn names_in_sentences(&self, document: &Node) -> Vec<SentenceName> {
        let mut found = Vec::new();
        self.sentences_of(document, "workspace", 0, &mut found);
        found
    }

    /// The recursive half of [`Schema::names_in_sentences`].
    fn sentences_of(&self, node: &Node, group: &str, depth: usize, out: &mut Vec<SentenceName>) {
        // The specification is a few levels deep and acyclic; the cap is a
        // backstop, not a design — the same one `handover.rs` writes.
        if depth > 12 {
            return;
        }
        let Some(g) = self.groups.get(group) else { return };
        let Some(map) = node.as_map() else { return };
        for field in &g.fields {
            let Some(entry) = map.get(field.name.as_str()) else { continue };
            if let Some(forms) = &field.forms
                && !forms.resolve.is_empty()
            {
                let items: Vec<&Node> = match &entry.node.value {
                    Value::List(l) => l.iter().collect(),
                    _ => vec![&entry.node],
                };
                for item in items {
                    let Some(said) = item.as_str() else { continue };
                    let Some((_, holes)) = forms.capture(said) else { continue };
                    for (hole, written) in holes {
                        let Some((_, collection)) =
                            forms.resolve.iter().find(|(name, _)| *name == hole)
                        else {
                            continue;
                        };
                        out.push(SentenceName {
                            collection: collection.clone(),
                            name: written,
                            said: said.to_string(),
                            field: field.name.clone(),
                            at: item.span.clone(),
                        });
                    }
                }
            }
            match &field.ty {
                Ty::Group(kind) => self.sentences_of(&entry.node, kind, depth + 1, out),
                Ty::MapOf(inner) | Ty::ListOf(inner) => {
                    if let Ty::Group(kind) = inner.as_ref() {
                        let children: Vec<&Node> = match &entry.node.value {
                            Value::Map(m) => m.values().map(|e| &e.node).collect(),
                            Value::List(l) => l.iter().collect(),
                            _ => Vec::new(),
                        };
                        for child in children {
                            self.sentences_of(child, kind, depth + 1, out);
                        }
                    }
                }
                _ => {}
            }
        }
    }

    /// Validate `node` against the group named `group`, reporting into `diags`.
    pub fn validate(&self, node: &Node, group: &str, diags: &mut Diagnostics) {
        let Some(g) = self.groups.get(group) else {
            diags.push(Diagnostic::error(
                "schema/unknown-group",
                node.span.clone(),
                format!("Nothing is known about '{group}'."),
                "This is a problem with the specification itself, not with your file. \
                 Please report it.",
            ));
            return;
        };
        self.check_group(node, g, diags, &Where::root(node, &g.name));
    }

    fn check_group(&self, node: &Node, g: &Group, diags: &mut Diagnostics, at: &Where) {
        // A document that would not parse is a mistake already reported at the
        // line the author typed. Its name still resolves — see
        // `pact_doc::UNLOADED` — but WHAT IT SET is unknown, so nothing may be
        // reported absent from it: a missing-field complaint here would be a
        // second message about a file the author is already looking at, naming a
        // line they can see on the screen. Measured: one tab in
        // `agents/fraud-checker/agent.yaml` gave both `tabs disallowed within
        // this context` at line 4 and *"An agent must have a 'description'."*
        // while line 2 of that file reads `description: Looks for signs …`.
        //
        // This suppresses the absence complaints and nothing else, where it used
        // to return. The marker now sits on a whole DIRECTORY as well, once that
        // directory's self file fails to parse — and a directory has entries
        // beside its self file which loaded perfectly. Returning took those off
        // the report too: a tab in `workspace.yaml` hid the missing
        // `description:` in `agents/fraud-checker/agent.yaml`, so fixing the tab
        // produced a fresh error that could have been shown in the same pass.
        // Every other check below reasons from a field the author DID write, so
        // all of them stay safe to run.
        let settings_incomplete = node.get(pact_doc::UNLOADED).is_some();
        let Some(map) = node.as_map() else {
            diags.push(Diagnostic::error(
                "schema/wrong-shape",
                node.span.clone(),
                // The group as the author knows it, not as `spec/schema.yaml`
                // keys it — see [`noun_for`]. This sentence and the two below
                // it can all be in one report about one block, and until this
                // read `describe:` too they gave that block two different names.
                format!(
                    "This should be a set of {} settings, but it is {}.",
                    noun_for(g),
                    node.value.kind_name()
                ),
                format!("Write it as `name: value` lines. For example:\n         {}", example(g)),
            ));
            return;
        };

        // Unknown fields, with a suggestion when the author probably made a typo.
        let known: Vec<&str> = g
            .fields
            .iter()
            .flat_map(|f| std::iter::once(f.name.as_str()).chain(f.aliases.iter().map(String::as_str)))
            .collect();

        // The names the author has already been told they probably meant, worked
        // out HERE — before anything below says a setting is missing.
        //
        // A misspelt REQUIRED field used to draw two messages about one line.
        // `desription:` in an agent produced "An agent must have a
        // 'description'." from the loop below and "'desription' is not something
        // an agent can have." from here — and the first one sorts first, so the
        // advice the author acts on is `Add a line: description: ...`. Type it
        // and the block now carries BOTH keys: the fix made the file worse.
        // Measured across twelve typos on the worked example: eight produced the
        // pair, and it reproduced on nested blocks too (`auth: { byref: ... }`).
        //
        // Eve's `ExactDefinition` refuses the unknown key and never says what is
        // absent, which loses the missing-field message for everybody. Both
        // halves are wanted here — but only when they are about different lines.
        // So the suggestion is computed once and consulted twice, and a required
        // field that some unknown key is already being reported as a misspelling
        // of is not also reported absent. What is left is the one message whose
        // fix, typed, leaves a correct file.
        let mut misspelt: Vec<&str> = Vec::new();

        for (key, entry) in map {
            if key.starts_with("x-") {
                continue;
            }
            if known.contains(&key.as_str()) {
                continue;
            }
            let d = match suggest::closest(key, &known) {
                Some(best) => {
                    misspelt.push(best);
                    Diagnostic::error(
                        "schema/unknown-field",
                        entry.key_span.clone(),
                        not_here(key, g),
                        format!("Did you mean '{best}'?"),
                    )
                }
                None => Diagnostic::error(
                    "schema/unknown-field",
                    entry.key_span.clone(),
                    not_here(key, g),
                    format!("Remove it, or use one of: {}.", known.join(", ")),
                ),
            };
            diags.push(d);
        }

        // Companions owed by the fields the author actually wrote: the missing
        // setting, and every line that needs it. Collected rather than reported
        // as they are found, so one absent `when-it-runs-out` is one problem to
        // fix and not four copies of the same sentence.
        let mut owed: IndexMap<String, Vec<(String, pact_diag::Span)>> = IndexMap::new();

        for f in &g.fields {
            // Every spelling of this field that the author actually used. Taking
            // the first match and ignoring the rest silently discards a value
            // the author wrote — a T7 violation, and one that is invisible
            // because the alias also passes the unknown-field check above.
            let spellings: Vec<(&String, &pact_doc::Entry)> = std::iter::once(&f.name)
                .chain(f.aliases.iter())
                .filter_map(|n| map.get_key_value(n))
                .collect();

            // Whether a line in this block is already being reported as a
            // misspelling of this very field — under any of its spellings, since
            // an author who mistypes an alias has made the same mistake. If so
            // its absence is that mistake said a second time, and the second
            // saying is the one that does harm.
            let already_named = misspelt
                .iter()
                .any(|m| *m == f.name || f.aliases.iter().any(|a| a == m));

            match spellings.as_slice() {
                // A field that is missing has no position of its own. `node` is
                // the whole block, and its span starts at the first *value* in
                // it — so reporting the block's span put the underline under
                // `name: Fraud Checker` while the sentence above it talked
                // about `description`. `start_of_block` keeps the line, drops
                // the column and the width: the reader is shown where the block
                // begins and told what line to add to it, and nothing that is
                // already correct is marked as wrong.
                //
                // Both nouns take their article from [`article`] rather than a
                // literal `A`/`a`, and the verb is `must have` rather than
                // `needs`. For six rounds this sentence read "A agent needs a
                // 'description'." — and, on the group whose name is `needs`,
                // "A needs needs a 'because'." It is the first sentence the D13
                // author ever sees from the tool, on the day they are already
                // wrong about something, so it reads as carelessness at exactly
                // the wrong moment. `must have` is what lets one spelling serve
                // `an agent` and `evals` both; `needs` cannot agree with both.
                [] if f.required
                    && !already_named
                    && !settings_incomplete
                    && !declares_itself_a_base(map, g) => {
                    let noun = noun_for(g);
                    let mut subject = format!("{}{noun}", article(&noun));
                    if let Some(head) = subject.get_mut(..1) {
                        head.make_ascii_uppercase();
                    }
                    diags.push(Diagnostic::error(
                        "schema/missing-field",
                        node.span.start_of_block(),
                        format!("{subject} must have {}'{}'.", article(&f.name), f.name),
                        // `help:` is a folded YAML scalar and ends in a newline,
                        // so untrimmed it printed a blank line between the line
                        // the author can type and the `rule:` under it. Every
                        // other site that quotes `help:` already trims; this one
                        // was the exception, and it is the fix a D13 reader sees
                        // most often.
                        // ...and "add a line" presumes a file to add it to. A
                        // block the loader built out of a FOLDER has none, and
                        // the first tree anybody makes is exactly that shape:
                        // one `agents/hello/agent.yaml` and no `workspace.yaml`
                        // opened with `A workspace must have a 'name'.` against
                        // `--> /tmp/hello:1:1`, a line and column in a directory,
                        // and a fix naming no file at all. `file_to_start` is
                        // the loader's answer to which file to create; when it
                        // is set, the sentence says create it.
                        match &node.span.file_to_start {
                            Some(start) => format!(
                                "Create `{start}` and put one line in it: `{}: ...` — {}",
                                f.name,
                                f.help.trim()
                            ),
                            None => format!("Add a line: `{}: ...` — {}", f.name, f.help.trim()),
                        },
                    ));
                }
                [] => {}
                [(_, entry)] => {
                    self.check_value(&entry.node, &f.ty, f, diags, at);
                    note_companions(f, g, map, &entry.key_span, &mut owed);
                }
                [(first_name, first), rest @ ..] => {
                    for (other_name, other) in rest {
                        diags.push(
                            Diagnostic::error(
                                "schema/same-setting-twice",
                                other.key_span.clone(),
                                format!(
                                    "'{other_name}' and '{first_name}' are two names for the same \
                                     setting, and both are set."
                                ),
                                format!(
                                    "Keep one. '{}' is the name to use; delete the other line.",
                                    f.name
                                ),
                            )
                            .with_related(first.key_span.clone(), "also set here"),
                        );
                    }
                    // Still check the first so type errors are not masked.
                    self.check_value(&first.node, &f.ty, f, diags, at);
                    note_companions(f, g, map, &first.key_span, &mut owed);
                }
            }
        }

        self.report_companions(g, owed, diags);
        self.check_conditional_companions(g, map, diags);
        self.check_sentences(g, map, diags, at);
    }

    /// The companions owed only when a sibling holds a particular value.
    ///
    /// Separate from [`Self::report_companions`] because the two say different
    /// things and offer different fixes. A missing `when-it-runs-out` is *"you
    /// set a ceiling and did not say what happens at it"*; a missing `enough-is`
    /// is *"`waits-for:` says `enough-of-them`, and nothing says how many"* — and
    /// the second sentence has to quote the value that made the line necessary,
    /// or the reader cannot tell why they are being asked.
    ///
    /// Every message here has a twin in the adapter that refuses the same
    /// document at run time (`delegation.Teamwork.check`, `loops.Loop.resolve`),
    /// deliberately: the author must not be able to tell which half refused them.
    fn check_conditional_companions(
        &self,
        g: &Group,
        map: &pact_doc::Map,
        diags: &mut Diagnostics,
    ) {
        for f in &g.fields {
            let Some(entry) = map.get(&f.name) else { continue };
            let Some(written) = entry.node.as_str().map(str::trim) else { continue };
            for (want, only_when) in &f.needed_when {
                // Compared through the field's own type, so `spends-money: true`
                // and `spends-money: yes` are the same answer — the leniency
                // `coerce` grants everywhere else must not stop at this check.
                let same = match &f.ty {
                    Ty::YesNo => {
                        coerce::check(&entry.node, &f.ty)
                            == coerce::check(
                                &Node::str(only_when.clone(), entry.node.span.clone()),
                                &f.ty,
                            )
                    }
                    _ => written.eq_ignore_ascii_case(only_when),
                };
                if !same || map.contains_key(want) {
                    continue;
                }
                let Some(other) = g.fields.iter().find(|x| &x.name == want) else {
                    continue;
                };
                diags.push(Diagnostic::error(
                    "schema/missing-companion",
                    entry.key_span.clone(),
                    format!(
                        "'{}' says '{written}', and '{want}' is not set — so nothing says {}.",
                        f.name,
                        // The other field's `summary:` — its NAME — falling back
                        // to the first clause of its help. Reading the help
                        // alone is what made this sentence end *"so nothing says
                        // with `enough-of-them`"*: a help opens with the
                        // condition the setting applies under, which is right
                        // for somebody reading a list of settings and useless
                        // inside "nothing says …". `from_doc` refuses the
                        // specification where neither string works, so this call
                        // cannot silently pick up a broken one again.
                        summary::quotable(other)
                    ),
                    format!(
                        "Add a line next to it: `{want}: {}`.{} — {}",
                        placeholder(&other.ty),
                        choices_clause(&other.ty),
                        other.help.trim()
                    ),
                ));
            }
        }
    }

    /// Fields whose values come from a closed vocabulary, held against it.
    ///
    /// Separate from `check_value` because the question is not about the value
    /// alone: a sentence is only a rule if the document also declared the power
    /// it uses and bound it to a moment that can carry it out. Those live in
    /// sibling fields, which `check_value` cannot see.
    ///
    /// Every message here has a twin in the adapter that executes these rules,
    /// deliberately: the two halves are in different languages and the author
    /// must not be able to tell which one refused them.
    fn check_sentences(
        &self,
        g: &Group,
        map: &pact_doc::Map,
        diags: &mut Diagnostics,
        at: &Where,
    ) {
        for f in &g.fields {
            let Some(forms) = &f.forms else { continue };
            let Some(entry) = map.get(&f.name) else { continue };
            // The powers this document may use. Read off the sibling field the
            // vocabulary names — `may:` on an interceptor — unless the KIND
            // fixes them, which is what `always-may:` says. `redaction.yaml`
            // hides and does nothing else, so it has no `may:` line to read, and
            // reading an absent one gives "no powers claimed" — under which the
            // check below never fires and the two counting sentences the shared
            // vocabulary now contains would load in a redaction and count
            // nothing. See `Field::always_may`.
            let fixed = !f.always_may.is_empty();
            let declared: Vec<&str> = if fixed {
                f.always_may.iter().map(String::as_str).collect()
            } else {
                words_of(map, &forms.declares)
            };
            // `binds:` names MOMENTS, plural. `interceptor.when` became a list
            // so that a rule which has to run before the customer's words reach
            // the model AND before a value is handed to a tool is one file
            // rather than two copies differing in two lines.
            //
            // Read with `as_str()` alone this was `""` for any list, and
            // `sentences::reaches("", …)` answers true for everything — so the
            // check below would have passed vacuously the moment an author typed
            // a second moment, and `stop and say "…"` bound at
            // `turn.message.after` would have gone back to loading clean.
            let bound: Vec<&str> = words_of(map, &forms.binds);

            // Neither of the two CONSEQUENCE checks below is run when the line
            // it reasons from is already being told off.
            //
            // Measured: `when: step.mesage.before` on
            // `interceptors/redact-card-numbers.yaml`, which carries two
            // sentences, printed three problems — `schema/not-a-moment` naming
            // the misspelling, then `schema/rule-at-the-wrong-moment` once per
            // sentence, each quoting `step.mesage.before` back and offering
            // *"Change `when:` to one of: …"* under a caret sitting on a
            // `rules:` line the author must not change. One mistake, three
            // messages, two of them pointing away from it. That is the shape
            // `one_typo_is_one_message.rs` already pins down at the top level,
            // arriving one level in.
            //
            // Each check is silenced by ITS OWN antecedent, never by the other.
            // A misspelt `when:` says nothing about whether `may:` declares the
            // power a sentence needs, and a blanket *"something in this block is
            // wrong, say nothing else"* would swallow a second, unrelated
            // mistake — the trade
            // `a_typo_pointing_at_one_setting_does_not_silence_a_different_one_that_is_missing`
            // exists to refuse.
            //
            // Asked by re-running the sibling's OWN check into a throwaway
            // buffer rather than by re-deciding here what a sound address or a
            // sound power looks like. That is what carries this across changes
            // of shape: `when:` went from one address to a list of them, and
            // nothing here had to learn about it.
            let moment_is_sound = !self.field_complains(g, map, &forms.binds, at);
            // Where the KIND fixes the powers there is no author line to be
            // wrong, so there is nothing to suppress: a redaction has no `may:`.
            let powers_are_sound = fixed || !self.field_complains(g, map, &forms.declares, at);

            // A POWER NO SENTENCE AT THIS DOCUMENT'S MOMENTS CAN USE.
            //
            // The two checks below run over (sentence × what it needs). This one
            // runs the other way, over (power × where it could be used), and it
            // is the direction R24 is about: `docs/50-NOT-COPIED.md` §G5 states
            // the invariant — *"Every power in that list has a sentence that
            // reaches it and an address that carries it out"* — and nothing held
            // it. MEASURED: `may: [hide-values, stop-the-run]` at
            // `turn.message.after` with one hiding rule printed "OK — loaded
            // cleanly". `stop-the-run` is real, the harness honours it there, and
            // no sentence in the closed vocabulary produces one at that moment.
            // So the line reads as a safety control and is not one.
            //
            // Only where the document chose its own powers. Where the KIND fixes
            // them there is no author line to be wrong, and a redaction carrying
            // a power its moments cannot use is a fact about the specification,
            // reported by `spellings_needing` at the point of use instead.
            //
            // Silenced by either antecedent being wrong, for the reason the two
            // below are: a misspelt `when:` makes every moment unreachable and
            // would turn one typo into one message per declared power.
            if !fixed && moment_is_sound && powers_are_sound && !bound.is_empty() {
                for power in &declared {
                    let usable = forms.one_of.iter().any(|form| {
                        form.needs == *power
                            && (form.at.is_empty()
                                || form
                                    .at
                                    .iter()
                                    .any(|a| bound.iter().any(|b| sentences::reaches(b, a))))
                    });
                    if usable {
                        continue;
                    }
                    let works_at: Vec<&str> = forms
                        .one_of
                        .iter()
                        .filter(|form| form.needs == *power)
                        .flat_map(|form| form.at.iter().map(String::as_str))
                        .collect();
                    let mut seen = std::collections::BTreeSet::new();
                    let works_at: Vec<&str> =
                        works_at.into_iter().filter(|a| seen.insert(*a)).collect();
                    let fix = if works_at.is_empty() {
                        format!(
                            "Take `{power}` off the `{}:` line — no sentence PACT knows \
                             uses it.",
                            forms.declares
                        )
                    } else {
                        format!(
                            "Take `{power}` off the `{}:` line, or add a moment it works \
                             at: {}.",
                            forms.declares,
                            works_at.join(", ")
                        )
                    };
                    // Anchored on the `may:` line, which is the line the message
                    // is about and the line the fix says to change. Pointing at
                    // `rules:` would send an author to edit sentences that are
                    // all correct — see `a_caret_points_at_what_the_message_names`.
                    let span = map
                        .get(&forms.declares)
                        .map(|e| e.key_span.clone())
                        .unwrap_or_else(|| entry.key_span.clone());
                    diags.push(Diagnostic::error(
                        "loader/power-nothing-can-use",
                        span,
                        format!(
                            "this rule may `{power}`, and no sentence you can write at \
                             `{}` uses it — so that power sits there and nothing can \
                             reach it.",
                            bound.join("`, `")
                        ),
                        fix,
                    ));
                }
            }

            // What to offer under a refusal: the whole list where a document
            // chooses its own powers, and only what this KIND can carry out
            // where they are fixed. Offering a redaction `stop and say "…"` as
            // the repair for a sentence it cannot perform sends the author
            // straight to the next refusal, which is a fix in shape only.
            let offer: Vec<String> = if fixed {
                forms.spellings_needing(&f.always_may)
            } else {
                forms.spellings()
            };

            // The two consequence checks COLLECT rather than report, keyed by
            // the one thing that decides both what the message says and what
            // the fix offers — the power a sentence wanted, or the moments it
            // would have worked at. Two sentences wrong the same way share a
            // repair, so they are one problem with the second line underlined
            // beneath the first; two sentences wrong in different ways have
            // different repairs and stay two problems. A shared fix is the
            // whole test of whether the author is looking at one mistake.
            //
            // Before this, a file with N sentences and one bad `when:` printed
            // N identical errors, and the author had to read all of them to
            // find out they were the same one.
            let mut no_power: IndexMap<String, Vec<pact_diag::Span>> = IndexMap::new();
            let mut wrong_moment: IndexMap<String, Vec<pact_diag::Span>> = IndexMap::new();
            // The same rule, one level in: a WORD that is wrong is one mistake
            // however many sentences say it. `when:` and `may:` are read once
            // per file, so collecting them was enough to make one bad line one
            // message — but the words inside the angle brackets are read once
            // per sentence, and nothing was collecting those.
            //
            // Measured on an interceptor whose two rules both counted a
            // `payouts` tool the workspace has not got:
            //
            // ```text
            // error: This rule is about 'payouts', and there is no such entry in `tools:`.
            //   fix: Change it to one of: payments, zendesk — or add a file `tools/payouts.yaml`.
            // error: This rule is about 'payouts', and there is no such entry in `tools:`.
            //   fix: Change it to one of: payments, zendesk — or add a file `tools/payouts.yaml`.
            // ```
            //
            // Two errors, word for word the same, with the same fix under each,
            // for one tool that has to be added once. Same for a thing nothing
            // can recognise: `a passport number` written on two lines printed
            // `schema/not-a-recognisable-thing` twice.
            //
            // Keyed by the HOLE as well as the word, because the hole decides
            // what the fix offers — the same word written where two different
            // vocabularies apply is two mistakes needing two different repairs,
            // and merging them would offer one of the two the wrong list.
            let mut unknown_thing: IndexMap<(String, String), (String, Vec<pact_diag::Span>)> =
                IndexMap::new();
            let mut unknown_name: IndexMap<(String, String), (NotFound, Vec<pact_diag::Span>)> =
                IndexMap::new();
            // The powers of the sentences already read, so a `continues:` form
            // can ask whether anything above it is a sentence it can carry on
            // from. Kept as it walks rather than gathered first, because "above
            // it" is the author's own order and nothing else.
            let mut started: Vec<&str> = Vec::new();

            let items: Vec<&Node> = match &entry.node.value {
                Value::List(l) => l.iter().collect(),
                _ => vec![&entry.node],
            };
            for item in items {
                let Some(said) = item.as_str() else { continue };
                let Some((form, holes)) = forms.capture(said) else {
                    diags.push(Diagnostic::error(
                        "schema/not-a-rule",
                        item.span.clone(),
                        format!(
                            "'{said}' is not a rule PACT knows how to carry out, so it \
                             would load and do nothing."
                        ),
                        format!("Write one of:\n         {}", offer.join("\n         ")),
                    ));
                    continue;
                };
                // The words inside the angle brackets. A sentence from the right
                // form naming a thing nothing recognises, or a tool this
                // workspace has not got, is a rule that loads and does nothing —
                // which is what the sentence vocabulary itself exists to end.
                for (hole, written) in &holes {
                    if let Some((_, allowed)) =
                        forms.recognises.iter().find(|(name, _)| name == hole)
                        && !allowed.iter().any(|a| a == written)
                    {
                        unknown_thing
                            .entry((hole.clone(), written.clone()))
                            .or_insert_with(|| (allowed.join(", "), Vec::new()))
                            .1
                            .push(item.span.clone());
                    }
                    if let Some((_, collection)) =
                        forms.resolve.iter().find(|(name, _)| name == hole)
                    {
                        let holder = Field::new(f.name.clone(), Ty::Text, f.help.clone())
                            .names(collection.clone());
                        // The answer is carried rather than formatted here, for
                        // the reason `NotFound` exists: everything the refusal
                        // says depends only on the word, so working it out again
                        // per line would be the same answer computed twice and
                        // one more place for the two copies to differ.
                        if let Some(missing) =
                            self.look_up(&holder.names, &[], written, at, &f.name)
                        {
                            unknown_name
                                .entry((hole.clone(), written.clone()))
                                .or_insert_with(|| (missing, Vec::new()))
                                .1
                                .push(item.span.clone());
                        }
                    }
                }
                if powers_are_sound
                    && !form.needs.is_empty()
                    && !declared.contains(&form.needs.as_str())
                {
                    no_power.entry(form.needs.clone()).or_default().push(item.span.clone());
                }
                // A sentence that carries on from another one, with no other one
                // above it. `do the same for anything that looks like a card
                // number` written first has nothing to be the same as, so it
                // hides nothing — and `pact check` said *"loaded cleanly"* for
                // exactly that file while the thing that runs it refused the
                // same line. Checked here, refused there, in a process D13's
                // author never starts: the split this vocabulary exists to
                // close, reached through the one sentence in the list that is
                // not a rule on its own.
                //
                // Reported at once rather than collected, because unlike the two
                // above it there is no second line that could share the repair:
                // this sentence needs a DIFFERENT sentence written above it, and
                // that sentence is the one printed in the fix.
                if form.continues && !started.contains(&form.needs.as_str()) {
                    // The sentences it could have carried on from, which are the
                    // same sentences it can be replaced by — so one list answers
                    // both ways out. Narrowed to the ones this document may
                    // perform, the same way `offer` is: telling a redaction to
                    // write `stop and say "…"` is the untypeable fix
                    // `always-may:` exists to prevent.
                    let alone: Vec<String> = forms
                        .one_of
                        .iter()
                        .filter(|f| {
                            !f.continues
                                && f.needs == form.needs
                                && (!fixed || f.needs.is_empty() || declared.contains(&f.needs.as_str()))
                        })
                        .map(sentences::Form::readable)
                        .collect();
                    diags.push(Diagnostic::error(
                        "schema/rule-with-nothing-above-it",
                        item.span.clone(),
                        format!(
                            "'{said}' says to do the same as the rule before it, and no rule \
                             before it says what to do."
                        ),
                        format!(
                            "Write one of these here instead — or put one above this line and \
                             let this one carry on from it:\n         {}",
                            alone.join("\n         ")
                        ),
                    ));
                } else if !form.continues {
                    started.push(&form.needs);
                }
                // At least ONE of the moments named has to be able to carry the
                // sentence out — not all of them. A file that redacts at two
                // moments and counts tool calls at one is the composition the
                // list exists to allow, and the counting sentence really does
                // fire at the moment that counts; demanding every moment carry
                // every sentence would send that author straight back to two
                // files. What stays refused is the failure this check was
                // written for: a sentence NO named moment can carry out, which
                // loads and does nothing.
                if moment_is_sound
                    && !form.at.is_empty()
                    && !bound.is_empty()
                    && !bound
                        .iter()
                        .any(|b| form.at.iter().any(|a| sentences::reaches(b, a)))
                {
                    // Keyed by the moments this sentence WOULD work at, because
                    // that list is the fix. Two sentences that want different
                    // moments cannot be repaired by one line and are not one
                    // problem.
                    wrong_moment
                        .entry(form.at.join(", "))
                        .or_default()
                        .push(item.span.clone());
                }
            }

            // Emitted after the walk rather than inside it, so the count of
            // lines that earned each refusal is known before it is written. The
            // printed ORDER is unaffected: a report is sorted by file and
            // position before anybody sees it, and each of these anchors on the
            // first line the author wrote.
            for ((_, written), (allowed, spans)) in unknown_thing {
                diags.push(with_the_rest(
                    Diagnostic::error(
                        "schema/not-a-recognisable-thing",
                        spans[0].clone(),
                        // No count in this one. The sentence is about the WORD
                        // and reads the same for one line or five — "Nothing
                        // here knows what 'a passport number' looks like" is
                        // already the whole fact, and a number in front of it
                        // would be one the reader has no use for.
                        format!("Nothing here knows what '{written}' looks like."),
                        format!(
                            "The things that can be recognised are: {allowed}. Change it to \
                             one of those."
                        ),
                    ),
                    &spans,
                ));
            }

            for ((_, written), (missing, spans)) in unknown_name {
                diags.push(with_the_rest(
                    Diagnostic::error(
                        "schema/no-such-name",
                        spans[0].clone(),
                        format!(
                            "{} about '{written}', {}",
                            these_rules(spans.len(), "is", "are"),
                            missing.because(&f.name)
                        ),
                        missing.fix(),
                    ),
                    &spans,
                ));
            }

            for (needs, spans) in no_power {
                // Two refusals, because there are two situations and only one
                // of them has a line to type. A document that CHOOSES its
                // powers is told which line to add; a kind that fixes them is
                // told what it can do instead, because "add a line under
                // `may:`" names a setting `redaction.yaml` does not have —
                // and a fix an author cannot type is not one.
                let (why, fix) = if fixed {
                    (
                        format!(
                            "{} to {}, and a {} may only {}.",
                            these_rules(spans.len(), "needs", "need"),
                            needs.replace('-', " "),
                            g.name,
                            f.always_may
                                .iter()
                                .map(|p| p.replace('-', " "))
                                .collect::<Vec<_>>()
                                .join(", ")
                        ),
                        format!("Write one of:\n         {}", offer.join("\n         ")),
                    )
                } else {
                    (
                        format!(
                            "{} to {}, and '{}' does not say {} may.",
                            these_rules(spans.len(), "needs", "need"),
                            needs.replace('-', " "),
                            forms.declares,
                            if spans.len() == 1 { "it" } else { "they" }
                        ),
                        format!("Add a line under `{}:` — `- {needs}`.", forms.declares),
                    )
                };
                diags.push(with_the_rest(
                    Diagnostic::error("schema/rule-without-the-power", spans[0].clone(), why, fix),
                    &spans,
                ));
            }

            for (works_at, spans) in wrong_moment {
                let (subject, verb) = if spans.len() == 1 {
                    ("this rule".to_string(), "it would")
                } else {
                    (format!("these {} rules", spans.len()), "they would")
                };
                diags.push(with_the_rest(
                    Diagnostic::error(
                        "schema/rule-at-the-wrong-moment",
                        spans[0].clone(),
                        format!(
                            "Nothing at `{}` can carry {subject} out, so {verb} \
                             do nothing.",
                            bound.join("`, `")
                        ),
                        format!("Change `{}:` to one of: {works_at}.", forms.binds),
                    ),
                    &spans,
                ));
            }
        }
    }

    /// Is the sibling a sentence vocabulary reasons FROM already wrong itself?
    ///
    /// `check_sentences` reads two other lines to judge a rule — the powers
    /// under `may:` and the moments under `when:` — and both of those lines have
    /// already been held against their own type by the time it runs. When one of
    /// them failed, every conclusion drawn from it is a restatement of a mistake
    /// the author has already been shown, with a caret on a line they must not
    /// change.
    ///
    /// Asked by running the field's own check again into a buffer that is thrown
    /// away, rather than by a second copy of what a sound value looks like. A
    /// second copy is a second thing to keep in step, and this one would have had
    /// to know that `when:` is a list of addresses — which it was not, one round
    /// ago, and may not be one round from now.
    ///
    /// A field the group does not have, or one the author did not write, cannot
    /// be wrong: a redaction has no `may:` line, and nothing is suppressed there.
    fn field_complains(&self, g: &Group, map: &Map, name: &str, at: &Where) -> bool {
        let Some(f) = g.fields.iter().find(|x| x.name == name) else {
            return false;
        };
        let Some(entry) = map.get(name) else { return false };
        let mut thrown_away = Diagnostics::new();
        self.check_value(&entry.node, &f.ty, f, &mut thrown_away, at);
        !thrown_away.items().is_empty()
    }

    /// One diagnostic per missing companion, however many settings ask for it.
    ///
    /// It anchors on the first line the author *did* write and points at the
    /// rest, because that is what they are looking at, and it offers a value to
    /// type rather than a rule to satisfy — for a `one-of` companion it names
    /// the actual choices, which is the difference between a fixable error and
    /// a dead end for the reader D13 describes.
    fn report_companions(
        &self,
        g: &Group,
        owed: IndexMap<String, Vec<(String, pact_diag::Span)>>,
        diags: &mut Diagnostics,
    ) {
        for (want, needed_by) in owed {
            let (first_name, first_span) = &needed_by[0];
            // The exactly-one-of set, which has no single companion to name.
            if let Some(listed) = want.strip_prefix("__one_of__") {
                let choices: Vec<&str> = listed.split("`, `").collect();
                diags.push(Diagnostic::error(
                    "schema/missing-one-of",
                    first_span.clone(),
                    format!(
                        "'{first_name}' is set, and exactly one of `{}` has to be set \
                         with it — so the rule says what to look at and never says what \
                         to look for.",
                        choices.join("`, `")
                    ),
                    format!(
                        "Add one of them beside it: {}.",
                        choices
                            .iter()
                            .map(|c| format!("`{c}: …`"))
                            .collect::<Vec<_>>()
                            .join(", ")
                    ),
                ));
                continue;
            }
            let Some(other) = g.fields.iter().find(|x| x.name == want) else {
                diags.push(Diagnostic::error(
                    "schema/unknown-companion",
                    first_span.clone(),
                    format!("'{first_name}' says it needs '{want}', and no such setting exists."),
                    "This is a problem with the specification itself, not with your file. \
                     Please report it.",
                ));
                continue;
            };
            let mut d = Diagnostic::error(
                "schema/missing-companion",
                first_span.clone(),
                format!("'{first_name}' is set, but '{}' is not.", other.name),
                format!(
                    "Add a line next to it: `{}: {}`.{} — {}",
                    other.name,
                    placeholder(&other.ty),
                    choices_clause(&other.ty),
                    other.help.trim()
                ),
            );
            for (name, span) in &needed_by[1..] {
                d = d.with_related(span.clone(), format!("'{name}' needs it too"));
            }
            diags.push(d);
        }
    }

    fn check_value(
        &self,
        node: &Node,
        ty: &Ty,
        field: &Field,
        diags: &mut Diagnostics,
        at: &Where,
    ) {
        match ty {
            Ty::Anything => {}
            // A moment is a length of time or a set of `moment` settings, and
            // each half is checked exactly as a field of that type would be.
            Ty::Moment if node.as_map().is_some() => {
                self.check_value(node, &Ty::Group("moment".into()), field, diags, at)
            }
            Ty::Moment => self.check_value(node, &Ty::Duration, field, diags, at),
            // Each setting is checked as the `comparand` group's, and exactly one
            // is written: `{value: a, now-plus: 1 day}` compares with two things.
            Ty::Comparand if node.as_map().is_some() => {
                self.check_value(node, &Ty::Group("comparand".into()), field, diags, at);
                let written = node.as_map().map_or(0, |m| m.len());
                if written != 1 {
                    diags.push(Diagnostic::error(
                        "schema/not-a-comparand",
                        node.span.clone(),
                        format!(
                            "'{}' compares with {} — so nothing says what it is compared with.",
                            field.name,
                            if written == 0 { "nothing" } else { "more than one thing at once" }
                        ),
                        "Write exactly one of `value: <binding>`, `now-plus: <length of time>` and \
                         `now-minus: <length of time>` — or a figure on its own, like `5000 USD`."
                            .to_string(),
                    ));
                }
            }
            Ty::Group(name) => match self.groups.get(name) {
                Some(g) => self.check_group(node, g, diags, &at.inside(node)),
                None => diags.push(Diagnostic::error(
                    "schema/unknown-group",
                    node.span.clone(),
                    format!("Nothing is known about '{name}'."),
                    "This is a problem with the specification itself. Please report it.",
                )),
            },
            Ty::ListOf(inner) => match &node.value {
                // A REQUIRED list written with nothing in it. `required:` asks
                // only whether the line is there, which was the whole answer
                // while the field was a scalar — `when:` with nothing after it
                // is a missing value and was already refused. As a list, `when:
                // []` satisfied the same check and bound the rule to no moment
                // at all, so every sentence in the file loaded and did nothing,
                // silently. That is the failure this specification refuses
                // everywhere else, arriving through the fix for another one.
                //
                // The empty folder under a `text:` field is judged the same way
                // and for the same reason (see `is_all_prose`): a field the
                // author meant to write and did not.
                Value::List(items) if items.is_empty() && field.required => {
                    diags.push(Diagnostic::error(
                        "schema/nothing-written-here",
                        node.span.clone(),
                        format!(
                            "'{}' is here with nothing in it, so it says nothing \
                             at all.",
                            field.name
                        ),
                        // No help text after it, unlike `schema/missing-field`:
                        // that one is read by somebody who has not met the
                        // field, and this one by somebody who just wrote it.
                        // What they need is the shape of one entry.
                        format!(
                            "Write at least one line under it: `- {}` — or take \
                             the `{}:` line out.",
                            placeholder(inner),
                            field.name
                        ),
                    ));
                }
                Value::List(items) => {
                    for item in items {
                        self.check_value(item, inner, field, diags, at);
                    }
                }
                // A MAP is not the harmless slip below it. It fell into the same
                // arm and was checked as `Ty::Text`, which reports nothing — so
                // `uses:\n  weather: yes` (the shape `team:` and `remembers:`
                // use two lines away in the same file) printed "OK — loaded
                // cleanly", and `ir._as_list` then returned `[]`: the agent was
                // offered ZERO tools and nothing anywhere said so. Sixty-two
                // fields in the specification are `list of` or `map of`, so the
                // two shapes sit next to each other everywhere.
                Value::Map(map) => {
                    let example = map
                        .keys()
                        .next()
                        .map(String::as_str)
                        .unwrap_or("the first one");
                    diags.push(Diagnostic::error(
                        "schema/list-written-as-a-map",
                        node.span.clone(),
                        format!(
                            "'{}' is a list of things, and this is written as \
                             settings with a value each.",
                            field.name
                        ),
                        format!(
                            "Put a `- ` in front of each one and take the `:` off: \
                             write `- {example}` on the line under `{}:`, not \
                             `{example}: ...`.",
                            field.name
                        ),
                    ));
                }
                // A single value where a list is expected is such a common and
                // harmless slip that we accept it and say so, rather than
                // failing. Being strict here would teach nothing.
                _ => self.check_value(node, inner, field, diags, at),
            },
            Ty::MapOf(inner) => match node.as_map() {
                Some(map) => {
                    // The keys first. They are held at `at` rather than at
                    // `at.inside(node)` because a key is a property of the field
                    // where it was written, not of anything inside the map — the
                    // same position the field's own value would be resolved from.
                    self.check_keys(map, field, diags, at);
                    for entry in map.values() {
                        self.check_value(&entry.node, inner, field, diags, &at.inside(node));
                    }
                }
                None => diags.push(wrong_type(node, &field.name, ty)),
            },
            Ty::EventAddress(parts, reaches) => match node.as_str() {
                Some(s) => {
                    if let Some(d) = check_address(node, &field.name, s, parts, reaches) {
                        diags.push(d);
                    }
                }
                None => diags.push(wrong_type(node, &field.name, ty)),
            },
            // A REQUIRED text written BLANK. The empty-list arm above says why
            // `required:` on its own is not the whole answer — it asks whether
            // the line is there, never whether anything was written on it — and
            // it said so only for lists.
            //
            // Measured on the round that made `agent.instructions` required:
            // `rm` on all three `examples/refund-desk/agents/*/instructions.md`
            // was refused three times, and `truncate -s 0` on the same three
            // files printed *"OK — loaded cleanly (490 settings)"*, exit 0, and
            // `pact show` handed the tree to an adapter. The refusal that had
            // just been added was one keystroke wide: a workspace of three
            // agents that would say nothing still passed the command an author
            // runs to find out whether it works. Emptying a file is what an
            // author does when they mean to start over, so it is the likelier
            // of the two, not the exotic one.
            //
            // Trimmed, because a `.md` file holding one newline is what an
            // editor writes when it is saved empty, and it means exactly what
            // the zero-byte one means. Required only, matching the list arm: an
            // optional line left blank is a placeholder, not a hole.
            Ty::Text if field.required && node.as_str().is_some_and(|s| s.trim().is_empty()) => {
                diags.push(Diagnostic::error(
                    // The same rule name and the same sentence as the empty
                    // list. One vocabulary for "you wrote it and left it
                    // empty" — a second name for the same mistake would be a
                    // second thing for a reader to learn.
                    "schema/nothing-written-here",
                    node.span.clone(),
                    format!(
                        "'{}' is here with nothing in it, so it says nothing at \
                         all.",
                        field.name
                    ),
                    // The list's fix offers "or take the line out"; this one
                    // cannot, because the line is required. What is left is the
                    // help — which for `instructions` names both places the
                    // words are allowed to go, so an author who emptied
                    // `instructions.md` is not sent to `agent.yaml` instead.
                    format!("Write what it should say — {}", field.help.trim()),
                ));
            }
            // A `text` field written as a FOLDER. *"A directory is a field; a
            // field may be a directory"* is the headline rule of both READMEs and
            // `examples/refund-desk/README.md` uses `instructions` as its own
            // example — *"Start with one file; split it up when it gets long.
            // Nothing else changes."* It was not true: `agents/helper/
            // instructions/01-tone.md` + `02-length.md` gave *"'instructions'
            // should be some text, but it is a set of settings. fix: Change it to
            // some text"*, whose fix is "undo what you did".
            //
            // The entries are joined in the order the loader put them — ordinals
            // first, then by name, which is the order the author numbered them —
            // with a blank line between, because they are separate paragraphs of
            // one document and running them together would change the prose.
            //
            // Only where every entry is itself text. A folder of `map`s under a
            // `text` field is a different mistake and keeps its own message.
            Ty::Text if field.may_be_a_folder && node.as_map().is_some_and(is_all_prose) => {}
            scalar => {
                match coerce::check(node, scalar) {
                    None => diags.push(wrong_type(node, &field.name, ty)),
                    Some(coerce::Coerced::Text(s)) => match spelling(node, &field.name, scalar, &s, at)
                    {
                        // A file name with a folder in it and an answer shape
                        // nothing can read are both text that fits the type and
                        // breaks the type's one rule, so they are reported here
                        // rather than resolved as a name.
                        Some(d) => diags.push(d),
                        None => self.check_name(node, field, &s, diags, at),
                    },
                    // One door for "the value fits the type and is still not a
                    // usable value", and both ends of every quantity go through
                    // it. Each half returns for the kinds that have no floor
                    // and no ceiling, so a second route would only be a second
                    // place to forget. Nothing can be under the floor and over
                    // the ceiling at once — a value that does not fit carries no
                    // number to compare — so they never both speak.
                    Some(c) => {
                        self.check_floor(node, field, &c, diags);
                        self.check_ceiling(node, field, &c, diags);
                    }
                }
            }
        }
    }

    /// A value under the floor beneath it — the one its field declares, or the
    /// one its type carries.
    ///
    /// **The declared floor** is `at-least:` in `spec/schema.yaml`, and
    /// `at-most: 0` on a stage is the one that matters: it reads as a setting
    /// and means "this stage may never run", so the loop routes past it forever
    /// and the author never finds out why.
    ///
    /// **The type's own floor** is that a length of time is more than nothing,
    /// and it needs no `at-least:` line because no duration field anywhere can
    /// mean zero. It sits in the type for the reason a percentage is `0..=1` and
    /// money carries a currency (see [`coerce`]): a property every value of the
    /// type has costs nothing per field and cannot be forgotten on the next one.
    ///
    /// A zero is not inert, which is why refusing it is worth a diagnostic
    /// rather than a shrug. The ceilings are compared as `spent >= limit`
    /// (`limits.py`, `Limits.reached`), so `finishes-within: 0s` is reached
    /// before the first step and every run stops instantly, reporting a ceiling
    /// the author believed they were being generous with. `answer-within: 0s` is
    /// a deadline that expires before anybody is asked; `forget-after: 0s`
    /// discards what it remembers on the way in.
    ///
    /// **Money is the same argument**, and for a round it was the one quantity
    /// here with no bottom at all: `Ty::Money` got its currency and neither a
    /// range nor a check that the figure is a figure.
    ///
    /// `NaN USD` and `inf USD` are the hole from the far end, and worse than a
    /// zero: in IEEE-754 every comparison against a NaN is false, so a cap of
    /// `NaN USD` is not a loose cap, it is **no cap at all**, on a run that
    /// reports itself fully metered. That is the outcome
    /// `Limits.priced_at_nothing` already names as the one to avoid — *"a spend
    /// cap that can never be reached, under an author who believes they capped
    /// their spend"* — arriving by a route nothing was watching. That half of
    /// the argument holds on any comparison and needs nothing else said about
    /// it.
    ///
    /// **The ZERO half is per field, because the two money ceilings are not
    /// compared the same way.** This doc said *"the same comparison"* and it was
    /// measurably wrong about the second of them:
    ///
    /// * `limits.cost-per-request-under` really is the `0s` case exactly.
    ///   `Limits.reached` is `at >= c.limit` (`adapters/python/src/pact_adapters/limits.py`),
    ///   so `0 USD` is reached before the first step and every run stops
    ///   instantly, reporting a ceiling its author believed they were being
    ///   generous with.
    /// * `learning.cycle-limits.per-month` is compared `would_reach > amount`
    ///   (`learning.py`, `Learner._decide`), and `MonthlySpend.per_run` is
    ///   `0.0` until something has been scored — *"the honest forecast for the
    ///   first cycle of a month"*. So on the first cycle `0.0 > 0.0` is false.
    ///   MEASURED, three real cycles at 8.00 USD each against a real
    ///   `.pact/learning/` ledger with `per-month: 0 USD`: cycle 1 RUNS and
    ///   spends 8.00, cycles 2 and 3 are refused. `0 USD` there is not "every
    ///   cycle stopped instantly" — it is "one cycle's worth of spending, then
    ///   nothing", which is not what its author meant by zero either, and is a
    ///   ceiling that lets through exactly the spend it was written to prevent.
    ///   It is refused for THAT reason, not for a borrowed one. Held by
    ///   `adapters/python/tests/test_a_monthly_ceiling_nothing_can_reach_refuses_the_cycle.py`,
    ///   which pins the measurement so this paragraph stays checkable.
    ///
    /// `-5 USD` is the `0s` case on both, and on both it is the sentence *"less
    /// than nothing"* rather than a comparison argument: a ceiling below zero is
    /// not a budget under any reading.
    ///
    /// This is here rather than in [`coerce::money`] on purpose.
    /// `pact-loader`'s `currency.rs` re-runs `coerce::check(.., &Ty::Money)` to
    /// read the currency off a value it is not otherwise judging — including
    /// off `models/catalog.yaml`, where `input-per-mtok: 0 USD` is how a
    /// locally-served model DECLARES a currency and is a legitimate zero. A
    /// floor inside the coercer would make that row unreadable and close the
    /// only door out of the currency check. It cannot be an `at-least:` line
    /// either: [`Field::at_least`] is a whole number, and the floor a spend cap
    /// needs is "more than nothing", not "at least one".
    ///
    /// **Which money fields.** Both ceilings — `limits.cost-per-request-under`
    /// and `learning.cycle-limits.per-month` — and deliberately NOT
    /// `question-rule.more-than`, the figure above which a person is asked.
    /// That one is a GATE and not a ceiling: `more-than: 0 USD` means "stop for
    /// a person on ANY spend", which is a strict rule rather than a broken one,
    /// and nothing ever runs out against it. It stays out by construction and
    /// not by an exception listed here — A3 made it `type: text` so a score
    /// could be gated by a score, so it never coerces to `Money` and never
    /// reaches this function. A non-finite threshold is a different matter and
    /// is `money.rs`'s to hold, beside the rest of what it says about that
    /// field; see the concerns note on this change.
    ///
    /// That "by construction" is load-bearing and is now checked rather than
    /// asserted. `may-be-money: yes` is the escape hatch A3 created and the
    /// specification recommends for money-shaped fields, and a field carrying it
    /// gets `pact-loader`'s CURRENCY check (derived from the schema) and no
    /// floor from here (it is `type: text`). So the day a second such field
    /// appears it would be price-checked and figure-unchecked, which is the
    /// defect this whole function exists to close, in a new slot.
    /// `currency::tests::every_field_this_check_selects_is_also_held_to_being_a_figure`
    /// fails where somebody is adding it: it enumerates every field the
    /// specification types `money`, validates `NaN USD` into it and requires
    /// `schema/below-the-floor` back, and pins the `may-be-money` set to the one
    /// field `money.rs` reaches by hand.
    fn check_floor(&self, node: &Node, f: &Field, value: &coerce::Coerced, diags: &mut Diagnostics) {
        let (what, fix) = match value {
            coerce::Coerced::Integer(n) => match f.at_least {
                Some(floor) if *n < floor => (
                    format!("'{}' is {n}, and the smallest it may be is {floor}.", f.name),
                    format!("Write `{}: {floor}` or more, or remove the line.", f.name),
                ),
                _ => return,
            },
            // Anything that rounds to no milliseconds at all: `0`, `0s`, `0ms`,
            // and `0.4ms`, which reads as a length of time and is not one.
            coerce::Coerced::Duration(0) => (
                format!(
                    "'{}' is {}, which is no time at all.",
                    f.name,
                    node.as_str().unwrap_or("0").trim()
                ),
                format!(
                    "Write `{}: {}`, or any length of time above zero, or remove the line.",
                    f.name,
                    placeholder(&Ty::Duration)
                ),
            ),
            // The same mistake in the same shape one type over: a count of
            // tokens that reads as a size and is not one. `context-at-least:
            // 0.0004k` is 0.4 tokens and `"0.5"` is half of one — figures an
            // `f64` holds to the last bit — and both TRUNCATE to nothing at
            // `coerce::size`'s `as u64`, leaving a requirement no model has to
            // meet out of a line that was asking for one. For one round they
            // were sent to the ceiling instead and told they were "closer to
            // zero than this can keep track of", which is false about a figure
            // that was held exactly, with a fix (*"any number further from
            // zero"*) that `0.0004k` already satisfies.
            //
            // It is asked of the FIGURE AS WRITTEN, and that is what keeps a
            // zero somebody MEANT out of it: `0` and `0k` carry no non-zero
            // digit. A figure that never underflowed is the only thing here —
            // `1e-999` and `1e-999m` are `coerce::Coerced::SizeTooSmall` and are
            // refused at the ceiling by name.
            //
            // It asked `node.as_str()` until `coerce::size` learned to read a
            // figure the document layer had held as a number, and then a bare
            // `context-at-least: 0.5` had no text to answer with and loaded
            // CLEANLY as a context window of zero — the exact silence this arm
            // exists to break, let back in by the door beside it. Measured
            // through the shipped binary: `"0.5"` in quotes was
            // `schema/below-the-floor` and `0.5` without them was `OK — loaded
            // cleanly`.
            coerce::Coerced::Size(0)
                if as_written(node).chars().any(|c| c.is_ascii_digit() && c != '0') =>
            {
                (
                    format!("'{}' is {}, which is no tokens at all.", f.name, as_written(node)),
                    format!(
                        "Write `{}: {}`, or any size above zero, or remove the line.",
                        f.name,
                        placeholder(&Ty::Size)
                    ),
                )
            }
            // An amount of money that is not one to spend. Three sentences
            // rather than one, because they are three different mistakes and a
            // reader told that infinity is "too small" would go looking for a
            // bigger number to write.
            coerce::Coerced::Money { amount, .. }
                if (!amount.is_finite() || *amount <= 0.0)
                    && !money_past_counting(*amount, node) =>
            {
                let written = node.as_str().unwrap_or_default().trim();
                (
                    format!(
                        "'{}' is {written}, which is {}.",
                        f.name,
                        if amount.is_nan() || (amount.is_infinite() && !has_a_digit(written)) {
                            // `NaN` and `inf` are spelled the way a number is
                            // spelled and are not amounts, so the sentence says
                            // so rather than ranking them. A figure that
                            // OVERFLOWED to infinity — `1e400` — is a real
                            // amount and is not here; it is over the ceiling,
                            // and being told it is not a figure would send its
                            // author hunting for a typo that is not there.
                            "not an amount of money"
                        } else if *amount < 0.0 {
                            "less than nothing"
                        } else {
                            "no money at all"
                        }
                    ),
                    format!(
                        "Write `{}: {}`, or any amount above zero, or remove the line.",
                        f.name,
                        placeholder(&Ty::Money)
                    ),
                )
            }
            _ => return,
        };
        diags.push(Diagnostic::error(
            "schema/below-the-floor",
            node.span.clone(),
            what,
            format!("{fix} — {}", f.help.trim()),
        ));
    }

    /// The far end of [`Schema::check_floor`]: a quantity bigger than the whole
    /// number it is counted in — a length of time past the milliseconds, a
    /// count of tokens past the count.
    ///
    /// `finishes-within: 99999999999999999999h` is spelled the way the help
    /// says to spell it, and it asks for more milliseconds than a whole number
    /// here can hold. That used to be added up anyway, and the addition went
    /// over the top: `pact check` on a debug build — the build `cargo run` and
    /// the README both give an author — died with *"attempt to add with
    /// overflow"*, no file, no line, no field. A release build did not die; it
    /// wrapped, and kept a ceiling with no relation to the line that was
    /// written, which is the worse of the two because nothing says so.
    ///
    /// Refused here rather than in [`coerce`] for the reason `0s` is: the line
    /// is not misspelled, and *"'finishes-within' is not a length of time"*
    /// would send its author hunting for a typo that is not there. Here the
    /// field's name and line are known and the sentence can be the true one.
    ///
    /// **A count of tokens is the same cast and the same answer.**
    /// `context-at-least: 99999999999999999999m` multiplies in floating point
    /// and casts once, with no addition after it to overflow — so it never
    /// crashed, it was only ever quietly wrong: the cast saturated, the field
    /// became a requirement no model on earth meets, and `pact check` said
    /// *"OK — loaded cleanly"*. That is exactly the half of the duration defect
    /// a release build had, sitting one function away in the same file, so it
    /// is closed by the same door rather than left as a lesson the comments
    /// claim and the code does not apply.
    fn check_ceiling(
        &self,
        node: &Node,
        f: &Field,
        value: &coerce::Coerced,
        diags: &mut Diagnostics,
    ) {
        // Two quantities, two sentences: told that a number of tokens is "a
        // longer time than this can keep track of", a reader would have no idea
        // what to change. Each names its own kind and offers its own type's
        // placeholder.
        let (rule, what, shorter, ty) = match value {
            // THE SET THIS OFFERS HAS TO HOLD. For one round these two arms
            // said *"any shorter length of time"* and *"any smaller number"*,
            // which is the false-set sentence [`HELD`] was written to replace
            // and which reached `Ty::Number` and `Ty::Threshold` only. Measured
            // through the shipped binary: `finishes-within: 1e999s` was refused
            // with *"any shorter"* and the SHORTER `1e300h` was refused by the
            // identical rule; `context-at-least: 1e19` was refused with *"any
            // smaller"* and the SMALLER `1e16` was refused with it. The refused
            // set is `|v| >= bound`, so from a figure that is already past the
            // bound every step downward the author is invited to take lands
            // inside it again.
            //
            // A length of time cannot use [`HELD`] as it stands, because the
            // digits do not settle it: `999999999999999ms` and `…s` load and
            // `…h` and `…d` do not. So it names a length instead — one this
            // holds with room to spare (`1000d` is 8.64e10 milliseconds against
            // a `u64` ceiling of 1.8e19) and one an author can type.
            coerce::Coerced::DurationTooLong => (
                "schema/too-long-to-count",
                "a longer time than this can keep track of",
                "any length of time up to `1000d`",
                Ty::Duration,
            ),
            coerce::Coerced::SizeTooBig => (
                "schema/too-big-to-count",
                "more than this can keep track of",
                HELD,
                Ty::Size,
            ),
            // An amount of money is the same overflow one type over, and it
            // arrives here rather than at the floor for the same reason `0s`
            // goes to the floor and `99999999999999999999h` does not: the two
            // are one `f64::INFINITY` after the parse and two different edits.
            // `cost-per-request-under: 1e400 USD` is a figure somebody meant,
            // and telling them it "is not an amount of money" — the floor's
            // sentence for `NaN` and `inf`, which are spelled the way a number
            // is spelled — would send them hunting a typo that is not there.
            coerce::Coerced::Money { amount, .. } if money_past_counting(*amount, node) => (
                "schema/too-much-to-count",
                "a larger amount than this can keep track of",
                "any smaller amount",
                Ty::Money,
            ),
            // A plain number is the same overflow with none of money's shape,
            // and it arrives here rather than being refused as text for the
            // reason above: `temperature: 1e999` is spelled exactly the way a
            // number is spelled. `coerce::number` keeps a figure that overflowed
            // and drops a WORD that never did — `inf` and `nan` carry no digit
            // and stay `schema/wrong-type`, which is the true sentence for them.
            //
            // Both ends get their own sentence, which money does not need: an
            // amount below zero is refused at the floor as "less than nothing"
            // before its size is ever in question, while `-1e999` on a plain
            // number is a real figure at the bottom of the scale. Told it was
            // "more than this can keep track of", its author would go looking
            // for a smaller number and find the one they had already written.
            // THE SPELLING NO `is_finite` GUARD CAN SEE, WHICH IS WHY THIS ASKS
            // THE FIGURE AND NOT THE TEXT. `temperature: 99999999999999999999`
            // parses to a perfectly finite `1e20`, so an `is_finite` arm alone
            // passed over it, `pact check` said *"OK — loaded cleanly"*, and the
            // runtime was handed `1e20`: a figure nobody wrote, with no report
            // and exit 0, which is the silent degradation T7 and FR-8.1.1
            // forbid. Three documents saying `99999999999999999999`, `…98` and
            // `100000000000000000000` also digested to one hash.
            //
            // For a round the extra arm asked `parse::<i64>()` of the author's
            // TEXT, and that was a question about spelling: `temperature: 1e19`
            // loaded while `temperature: 10000000000000000000` — the same `f64`
            // to the last bit — was refused as *"more than this can keep track
            // of"*, a sentence the first line proves false, and one `.` was
            // enough to walk past it (`99999999999999999999.0` loaded and
            // shipped `1e+20` to the runtime). [`coerce::PAST_COUNTING`] is the
            // figure the sentence has always been about: past 2^53 a double
            // cannot tell one whole number from the next, so it cannot keep
            // track of the one that was written, whatever it was punctuated
            // with.
            coerce::Coerced::Number(n) if coerce::past_counting_figure(*n) => {
                past_counting(*n, Ty::Number)
            }
            // A whole number field that was handed a whole number too big to be
            // one. `tool-calls-at-most: 9223372036854775808` used to be
            // *"should be a whole number, but it is a number"*; see
            // [`coerce::Coerced::IntegerTooBig`].
            coerce::Coerced::IntegerTooBig(n) => past_counting(*n, Ty::Integer),
            // THE BOTTOM OF THAT SAME FIELD, which C12 left open and, worse,
            // made read wrongly. `steps-at-most: 1e999` is refused by name one
            // line above; measured before this arm, `steps-at-most: 1e-999` was
            // *"should be a whole number, but it is some text"* — byte for byte
            // the sentence `steps-at-most: abc` gets — because keeping an
            // underflowing scalar as text is what stops `pact show` losing it
            // and `wrong_type` reads its noun off the value. The same figure one
            // order up the scale got a sentence naming it; this one was told it
            // was not a figure at all. See [`coerce::Coerced::IntegerTooSmall`].
            coerce::Coerced::IntegerTooSmall(_) => (
                "schema/too-small-to-count",
                "closer to zero than this can keep track of",
                "any number further from zero",
                Ty::Integer,
            ),
            // A comparison is that same figure with an operator in front of it.
            // `MMLU: "> 1e999"` became a bar of `> inf` — one no published score
            // can ever clear, so the `needs:` block it belongs to could never be
            // met by any model — and loaded clean.
            // `MMLU: "> 99999999999999999999"` is a bar of `> 1e20` — not the
            // bar that was written — and `past_counting`'s own note says the two
            // types must not drift into two different sentences for the same
            // figure, so the comparison's figure is asked the question the plain
            // number's figure is asked, in the same words.
            coerce::Coerced::Threshold { value, .. } if coerce::past_counting_figure(*value) => {
                past_counting(*value, Ty::Threshold)
            }
            // THE BOTTOM OF THE SAME SCALE. `temperature: 1e-999` parses to a
            // number this can hold — `0.0` — and it is not the number that was
            // written. `yaml::resolve_scalar` keeps the author's text rather
            // than the zero, which is what stops `pact show` and the digest
            // losing it; this is the other half, for the fields where the
            // specification says a figure is wanted. Without it the document
            // layer hands the text on, `coerce::number` reads `0.0` back out of
            // it, and a spend of nothing is checked against a setting the author
            // never wrote — silently, which is the whole complaint.
            //
            // One sentence for both signs, unlike `past_counting`: `-1e-999`
            // arrives as `-0.0` and "closer to zero than this can keep track of"
            // is the true and useful thing to say about either end, because the
            // edit both authors need is the same one — write a bigger figure.
            coerce::Coerced::Number(n) if underflowed_to_zero(*n, node) => (
                "schema/too-small-to-count",
                "closer to zero than this can keep track of",
                "any number further from zero",
                Ty::Number,
            ),
            coerce::Coerced::Threshold { value, .. } if underflowed_to_zero(*value, node) => (
                "schema/too-small-to-count",
                "closer to zero than this can keep track of",
                "any number further from zero",
                Ty::Threshold,
            ),
            // THE SHARE-OF-THE-WHOLE SPELLING OF THE COMPARISON ABOVE, and the
            // one type this pass reached and did not close for a round.
            // `must-pass: 1e-999%` is `> 1e-999` written the way an eval suite
            // writes a bar: `coerce::percent` parses it, divides by a hundred,
            // finds `0.0` inside `0.0..=1.0` and hands back `Percent(0.0)` — a
            // bar every suite on earth clears, out of a line that was setting
            // one. Measured before this arm: `OK — rd loaded cleanly (498
            // settings)`, exit 0, on `examples/refund-desk` with its `must-pass:
            // 70%` replaced. `when-full: 1e-999%` is the same silence one field
            // over, and tidies a conversation that has nothing in it yet.
            //
            // It is asked of the TEXT for the reason every other arm here is:
            // `0.0` is what arrived and `0.0` says nothing about what was
            // written. `0%`, `0.0` and `-0.0` carry no non-zero digit and are
            // shares somebody meant, so they are none of its business — and
            // `0.0000001%` is `1e-9`, held exactly, not zero, and never here.
            coerce::Coerced::Percent(p) if underflowed_to_zero(*p, node) => (
                "schema/too-small-to-count",
                "closer to zero than this can keep track of",
                "any number further from zero",
                Ty::Percent,
            ),
            // AND THE TOP OF THAT SAME FIELD, which the round that closed the
            // bottom left open — so one field read correctly at one end only.
            // Measured through the shipped binary with the bottom closed:
            // `when-full: 1e-999%` was named (`schema/too-small-to-count`) and
            // `when-full: 1e999%` was *"should be a percentage, like `90%`, but
            // it is some text"* about a line that is a figure. The fix is not
            // *"any smaller number"* here, because a share is not made right by
            // being smaller — `-1e999%` is smaller and `1e-999%` is smaller
            // still. It is the range, which is the thing that makes a share a
            // share.
            coerce::Coerced::PercentPastHolding(p) => (
                "schema/too-big-to-count",
                if p.is_sign_positive() {
                    "more than this can keep track of"
                } else {
                    "further below zero than this can keep track of"
                },
                "any share between `0%` and `100%`",
                Ty::Percent,
            ),
            // THE BOTTOM OF THE SCALE FOR A COUNT OF TOKENS, and it arrived by
            // the top's own door. Keeping an underflowing scalar as text is what
            // stops `pact show` losing it — and it also handed `coerce::size` a
            // `Value::Str` where a `Value::Float(0.0)` used to be refused
            // outright, so `context-at-least: 1e-999` and
            // `context-at-least: 0.0000001k` started loading CLEANLY as a
            // context window of zero, indistinguishable from an authored
            // `context-at-least: 0`. A requirement no model has to meet, out of
            // a line asking for one, silently.
            //
            // For one round this arm was `Size(0) if underflowed_to_zero(0.0,
            // node)` — a hard-coded zero, which never asked whether anything
            // had underflowed and only asked whether the text carried a figure.
            // So it said "closer to zero than this can keep track of" about
            // `context-at-least: "0.5"` and `"0.9"`, which an `f64` holds to the
            // last bit, and offered the fix *"any number further from zero"* to
            // `0.0004k`, which already is one. Three different things reached it
            // as one `Size(0)`: a zero somebody meant, a real figure that
            // TRUNCATED to no tokens at the `as u64` cast, and a figure that was
            // never held. `coerce::size` now tells them apart while it still
            // can — before the multiplier — and only the third arrives here.
            // The second is `check_floor`'s, beside `Duration(0)`.
            coerce::Coerced::SizeTooSmall => (
                "schema/too-small-to-count",
                "closer to zero than this can keep track of",
                "any number further from zero",
                Ty::Size,
            ),
            _ => return,
        };
        diags.push(Diagnostic::error(
            rule,
            node.span.clone(),
            format!("'{}' is {}, which is {what}.", f.name, as_written(node)),
            match ty {
                // A comparison is the one of these that is normally a line
                // INSIDE a map — `scores:` is `map of threshold`, and every
                // entry of a map is checked against the map's own field, so
                // `f.name` there is `scores` and not `MMLU`. *"Write `scores:
                // > 80`"* is then a fix that fails if it is typed, which is
                // worse than no fix at all. `wrong_type` leaves the name out
                // for this type for the same reason — *"Write it like `> 80`"*
                // — so the comparison is offered on its own here too.
                Ty::Threshold => format!(
                    "Write `{}`, or {shorter}, or remove the line. — {}",
                    placeholder(&ty),
                    f.help.trim()
                ),
                _ => format!(
                    "Write `{}: {}`, or {shorter}, or remove the line. — {}",
                    f.name,
                    placeholder(&ty),
                    f.help.trim()
                ),
            },
        ));
    }

    /// The cross-reference check: a value that names something must name
    /// something that is there.
    ///
    /// Every candidate is offered in the fix, and so is the file to create —
    /// because "no loop called 'carefull'" without the list is a dead end for
    /// exactly the reader D13 describes, who cannot grep for what does exist.
    ///
    /// Unless the workspace already has the name somewhere else, in which case
    /// "there is no such entry" is false and "add a file" is harmful advice —
    /// see [`elsewhere`].
    fn check_name(
        &self,
        node: &Node,
        f: &Field,
        value: &str,
        diags: &mut Diagnostics,
        at: &Where,
    ) {
        let value = value.trim();
        let Some(missing) = self.look_up(&f.names, &f.or_one_of, value, at, &f.name) else {
            return;
        };
        diags.push(Diagnostic::error(
            "schema/no-such-name",
            node.span.clone(),
            format!("'{}' names '{value}', {}", f.name, missing.because(&f.name)),
            missing.fix(),
        ));
    }

    /// The same check, one level over: the KEYS of a `map of ...`.
    ///
    /// Two fields needed it and neither had it. `team:` says in its own help
    /// *"Give each one a folder under `agents/`"*, and `team: {polcy-checker:
    /// ...}` loaded clean — the misspelt member was then offered to the model as
    /// somebody it could ask, and asking parked the run on an agent that will
    /// never answer. `shares: {polcy-checker: 60%}` loaded clean too, and gave
    /// the real member a slice of 0.0.
    ///
    /// The caret goes on the KEY, not on the value beside it: the author wrote
    /// `polcy-checker: 60%`, and the 60% is not what is wrong with it.
    ///
    /// There is no `x-` escape here, unlike an unknown field or a position of an
    /// address. Those maps hold settings, where an author's own key is data
    /// nobody else has to understand; a map with `key-names:` holds nothing BUT
    /// references, so an `x-` key would be a reference to nothing wearing a
    /// prefix that says "do not check me".
    fn check_keys(&self, map: &Map, f: &Field, diags: &mut Diagnostics, at: &Where) {
        if f.key_names.is_empty() {
            return;
        }
        for (key, entry) in map {
            let key = key.trim();
            let Some(missing) = self.look_up(&f.key_names, &[], key, at, &f.name) else {
                continue;
            };
            diags.push(Diagnostic::error(
                "schema/no-such-name",
                entry.key_span.clone(),
                format!("'{}' lists '{key}', {}", f.name, missing.because(&f.name)),
                missing.fix(),
            ));
        }
    }

    /// Resolve one name against the maps `wants` points at. `None` means it
    /// resolved — or that nothing was asked of it.
    ///
    /// One body for both callers rather than two that drift: a key and a value
    /// are the same question about the same sets, and the only thing that
    /// differs is the sentence naming which of the two went wrong.
    fn look_up(
        &self,
        wants: &[String],
        literals: &[String],
        value: &str,
        at: &Where,
        field: &str,
    ) -> Option<NotFound> {
        // A field may carry only `or-one-of:` and no `names:` at all — that is
        // "one of these two literals and nothing else", which is what
        // `loop.based-on` is: a workspace loop name is refused there too, so
        // there is no map to resolve against and the literals ARE the vocabulary.
        if wants.is_empty() && literals.is_empty() {
            return None;
        }
        if value.is_empty() || literals.iter().any(|x| x == value) {
            return None;
        }

        let mut known: Vec<String> = literals.to_vec();
        let mut roots: Vec<&str> = Vec::new();
        let mut supplied: Option<&Known> = None;
        for want in wants {
            // A `pact:` namespace is the distribution's own list, not a map in
            // the tree — see `Known`. Both are consulted, so a workspace that
            // adds a model of its own extends the set rather than replacing it.
            if let Some(name) = want.strip_prefix("pact:") {
                if let Some(k) = self.known.get(name) {
                    if k.names.contains(value) {
                        return None;
                    }
                    supplied = Some(k);
                    known.extend(k.names.iter().cloned());
                }
                continue;
            }
            let (map, is_root) = at.resolve(want);
            if is_root {
                roots.push(want.trim_start_matches('^'));
            }
            if let Some(m) = map {
                if m.contains_key(value) {
                    return None;
                }
                known.extend(m.keys().cloned());
            }
        }
        known.sort();
        known.dedup();

        let places = wants
            .iter()
            .map(|n| match n.strip_prefix("pact:") {
                Some(name) => self
                    .known
                    .get(name)
                    .map(|k| k.label.clone())
                    .unwrap_or_else(|| format!("`{name}:`")),
                None => format!("`{}:`", n.trim_start_matches('^')),
            })
            .collect::<Vec<_>>();
        // `or_list` and not `.join(" or ")`. With two places the two read the
        // same; with three it is the difference between "in `tools:`, `skills:`
        // or `knowledge:`" and "in `tools:` or `skills:` or `knowledge:`" — and
        // the SAME message builds its file list with `or_list` one screen down,
        // so the sentence contradicted itself in its own second half.
        let places = or_list(&places);
        let choices = if known.is_empty() { String::new() } else { known.join(", ") };
        // A top-level map is a folder in the workspace, so "add a file" is a
        // real instruction. A `^` map is a block inside the document already
        // open, so the instruction is to add an entry to it. A distribution
        // namespace has neither, so it carries its own sentence — the fix for a
        // model PACT has never heard of is a row in the workspace's own
        // catalogue, and nobody could guess that from a list of ids.
        //
        // EVERY root, not `roots.first()`. `names: [tools, skills, agents]` used
        // to offer `tools/<name>.yaml` for all three, so an author who meant a
        // teammate was told to create a tool — and two of the three are not even
        // that shape: a skill is a FOLDER with a `SKILL.md` in it and an agent is
        // `agents/<name>/agent.yaml`. The per-kind template is data on the kind,
        // for the reason everything else here is data.
        // A value with a space, a slash or a question mark in it is not a file
        // name, so offering one produces something nobody can type. The author
        // wrote wording where a name belongs, and the honest fix is the list —
        // for a round this printed ``add a file `questions/Is it OK to carry on
        // without the fraud check?.yaml` ``.
        let unnameable = value.contains([' ', '/', '?', '\\']);
        let files: Vec<String> =
            roots.iter().map(|dir| format!("`{}`", file_for(dir, value))).collect();
        let add = match (files.is_empty() || unnameable, supplied) {
            (false, _) => format!("add a file {}", or_list(&files)),
            (true, Some(k)) => k.add.replace("{}", value),
            // Nothing to add to when the vocabulary is two literals.
            (true, None) if places.is_empty() => String::new(),
            (true, None) => format!("add a `{value}:` entry under {places}"),
        };
        // ...and every one of those three is wrong if the workspace already has
        // this name under a different kind. "Make a file" then means "make a
        // second copy of the document you are looking at", which loads, is read
        // by nothing, and says so nowhere. Only the file form is quoted back in
        // the refusal, because it is the only one of the three that damages
        // anything when followed.
        let consulted: Vec<&str> =
            wants.iter().map(|w| w.trim_start_matches('^')).collect();
        let elsewhere =
            elsewhere::find(&self.groups, at.root, at.root_group, value, &consulted, field);
        let add_a_file = if files.is_empty() || unnameable { None } else { Some(add.clone()) };
        Some(NotFound { places, choices, add, elsewhere, add_a_file })
    }
}

/// The file that would hold a document of this kind, by the kind's own shape.
///
/// A tool is one file, a skill is a FOLDER with a `SKILL.md` in it, an agent is
/// a folder with an `agent.yaml` in it. Offering `tools/<name>.yaml` for all
/// three sent an author who meant a teammate off to create a tool.
fn file_for(collection: &str, name: &str) -> String {
    match collection {
        "skills" => format!("skills/{name}/SKILL.md"),
        "agents" => format!("agents/{name}/agent.yaml"),
        // A program is a FOLDER — a declaration and a `body/` beside it — so the
        // file to create is inside it, not `programs/<name>.yaml`.
        "programs" => format!("programs/{name}/program.yaml"),
        other => format!("{other}/{name}.yaml"),
    }
}

/// `a`, `a or b`, `a, b or c` — a list a person reads out loud.
fn or_list(items: &[String]) -> String {
    match items.split_last() {
        None => String::new(),
        Some((last, [])) => last.clone(),
        Some((last, front)) => format!("{} or {last}", front.join(", ")),
    }
}

/// A name that resolved against nothing: where it was looked for, what is there
/// instead, and what to do about a name that is genuinely new.
///
/// Carried rather than formatted on the spot so that the two callers — a value
/// and a key — share every part of the answer except the sentence that says
/// which of the two the author wrote.
struct NotFound {
    places: String,
    choices: String,
    add: String,
    /// Where the workspace really keeps this name, when it keeps it at all.
    elsewhere: Option<elsewhere::Elsewhere>,
    /// `add`, but only when it is the "make a file" form — the one shape of
    /// advice that does harm when it is followed for the wrong reason.
    add_a_file: Option<String>,
}

impl NotFound {
    /// The rest of the sentence after "'may-use' names 'refund-policy',".
    fn because(&self, field: &str) -> String {
        match (&self.elsewhere, self.places.is_empty()) {
            (Some(e), _) => e.because(field, &self.places),
            (None, true) => "and that is not one of the shapes PACT ships.".to_string(),
            (None, false) => format!("and there is no such entry in {}.", self.places),
        }
    }

    /// The typeable fix — and never a list of nothing.
    ///
    /// A workspace whose `tools/` folder does not exist yet used to be told
    /// ``Change it to one of: nothing is declared yet — or add a file
    /// `tools/zendesk.yaml` ``, which instructs the reader to type the phrase
    /// "nothing is declared yet". It is the first thing a new author hits, and
    /// the only half of it that means anything is the second.
    fn fix(&self) -> String {
        match (&self.elsewhere, self.choices.is_empty()) {
            (Some(e), _) => e.fix(&self.choices, self.add_a_file.as_deref()),
            (None, true) => {
                let mut instruction = self.add.clone();
                if let Some(head) = instruction.get_mut(..1) {
                    head.make_ascii_uppercase();
                }
                format!("Nothing is declared there yet. {instruction}.")
            }
            (None, false) if self.add.is_empty() => {
                format!("Change it to one of: {}.", self.choices)
            }
            (None, false) => format!("Change it to one of: {} — or {}.", self.choices, self.add),
        }
    }
}

/// Where in the document a value sits, so `names:` can be resolved against the
/// workspace root or against the nearest block that carries the map.
///
/// It holds borrowed nodes rather than paths because the alternative — naming
/// the path from the root — would make `then: {answered: repl}` resolve against
/// *any* loop's stages rather than its own.
struct Where<'a> {
    root: &'a Node,
    /// Which kind the root was validated as — `workspace` for a tree with
    /// `agents:`, `agent` for a single one. Carried because it is the only way
    /// to ask the specification which of the root's keys are sections holding
    /// named documents and which are blocks of settings (see [`elsewhere`]).
    root_group: &'a str,
    enclosing: Vec<&'a Node>,
}

impl<'a> Where<'a> {
    fn root(node: &'a Node, group: &'a str) -> Self {
        Where { root: node, root_group: group, enclosing: vec![node] }
    }

    fn inside(&self, node: &'a Node) -> Where<'a> {
        let mut enclosing = self.enclosing.clone();
        enclosing.push(node);
        Where { root: self.root, root_group: self.root_group, enclosing }
    }

    /// The map `want` refers to, and whether it was found at the workspace root.
    fn resolve(&self, want: &str) -> (Option<&'a Map>, bool) {
        match want.strip_prefix('^') {
            // Innermost first, so a stage routing to `repl` is checked against
            // its own loop's stages and not against some other loop that happens
            // to have one. Three places, in this order:
            //
            // 1. the block the value is written in, when it has one — a
            //    `starts-at:` beside its own `steps:`;
            // 2. the nearest such map the value sits INSIDE — a stage's `then:`
            //    names its siblings, even when the stage has `steps:` of its own
            //    (a workflow's `each`, whose outcome leads to a stage beside it,
            //    never into its own body);
            // 3. the nearest enclosing block that has one — a workflow stage's
            //    `asks:` finds the workflow's own `questions:`.
            Some(key) => {
                let held = |n: &&'a Node| -> Option<&'a Map> {
                    let n: &'a Node = n;
                    n.get(key).and_then(Node::as_map)
                };
                let innermost = self.enclosing.last().and_then(held);
                let around = self.enclosing.windows(2).rev().find_map(|pair| {
                    let (outer, inner): (&'a Node, &'a Node) = (pair[0], pair[1]);
                    let map = outer.get(key)?;
                    std::ptr::eq(map, inner).then(|| map.as_map()).flatten()
                });
                let nearest = || self.enclosing.iter().rev().find_map(held);
                (innermost.or(around).or_else(nearest), false)
            }
            None => (self.root.get(want).and_then(Node::as_map), true),
        }
    }
}

/// Whether this block says `base: yes` — and its kind even HAS a `base:`
/// field. Keyed off the group's own declaration so the hole exists only where
/// the specification put it (today: agents); giving another kind the word is
/// a YAML edit, not an edit here.
fn declares_itself_a_base(map: &Map, g: &Group) -> bool {
    if !g.fields.iter().any(|fld| fld.name == "base") {
        return false;
    }
    map.get("base").is_some_and(|e| match &e.node.value {
        Value::Bool(b) => *b,
        Value::Str(s) => matches!(s.trim(), "yes" | "true" | "on"),
        _ => false,
    })
}

/// What to call a group in a diagnostic: its own sentence if it has one.
///
/// The article comes from [`article`] rather than a literal `a`, so `agent`,
/// `action`, `interceptor` and `outcome` read correctly and `evals` — which is
/// plural and can take no indefinite article at all — reads "is not something
/// evals can have". `can have` was already number-agnostic, so dropping the
/// article was the whole fix on this side.
fn not_here(key: &str, g: &Group) -> String {
    if g.describe.is_empty() {
        format!("'{key}' is not something {}{} can have.", article(&g.name), g.name)
    } else {
        format!("'{key}' is not {}.", g.describe.trim())
    }
}

/// The same group, as the SUBJECT of a sentence: the thing it is, with no
/// article on the front — `credential reference`, `approval rule`, `agent`.
///
/// [`not_here`] honoured `describe:` and the other two sentences that name a
/// group did not, so one report called one group two things. Measured on a copy
/// of the worked example, with `auth: { by-reference: ... }` in
/// `resources/zendesk-server.yaml` changed to a key nothing knows:
///
/// ```text
/// error: A credential-reference must have a 'by-reference'.
/// error: 'vault-path' is not something a credential reference can have.
/// ```
///
/// The first sentence shows the author `credential-reference`, which is a key in
/// `spec/schema.yaml` and a word they have never seen. `when-this` and
/// `call-order` did the same, and `call-order` is the worse of the two: `a
/// call-order` is not an unfamiliar word, it is a familiar one meaning something
/// one word longer, so the reader has no way to tell the two sentences are about
/// the same block.
///
/// `describe:` is written as a PREDICATE — it completes *"'x' is not …"* — so
/// the subject has to be lifted out of it. Two shapes cover every phrase the
/// specification uses, and both are read the same way: the phrase opens with a
/// noun, and when that noun is the placeholder `something` the real subject is
/// the owner it hands off to, running up to the verb.
///
/// ```text
/// something a credential reference can have  →  credential reference
/// an outcome a stage can end in              →  outcome
/// ```
///
/// The article is dropped here and put back by [`article`] at each site, so one
/// phrase reads correctly in three different sentence frames and a plural
/// (`a model's abilities`) or vowel-initial (`an approval rule`) name comes out
/// right without the schema author having to get an article right in a phrase
/// that does not even use it.
///
/// A `describe:` in neither shape falls back to the group's own name — which is
/// what all three sentences said before this existed. A phrase this cannot read
/// makes the report plainer, never wrong.
fn noun_for(g: &Group) -> String {
    let said: Vec<&str> = g.describe.split_whitespace().collect();
    let Some(head) = said.first() else { return g.name.clone() };
    // Where the opening noun phrase ends: the next article, or the verb.
    let end = said
        .iter()
        .enumerate()
        .skip(1)
        .find(|(_, w)| matches!(**w, "a" | "an" | "the" | "can"))
        .map_or(said.len(), |(i, _)| i);
    let phrase = if said.len() == 1 || (*head != "something" && *head != "anything") {
        &said[..end]
    } else {
        // `something` stands in for the group itself, so the phrase that names
        // it is the owner after it — up to `can`, which is where every
        // `describe:` in the specification turns into a verb.
        match said.iter().position(|w| *w == "can") {
            Some(verb) if verb > end => &said[end..verb],
            _ => return g.name.clone(),
        }
    };
    match phrase {
        ["a" | "an" | "the", rest @ ..] if !rest.is_empty() => rest.join(" "),
        [] => g.name.clone(),
        all => all.join(" "),
    }
}

/// An address, held against the closed list for each of its positions — and then
/// against the moments this field can actually be bound to.
///
/// Two questions, because they have two different fixes and two different
/// failures. `turn.answer.after` is not an address at all and the fix is the
/// vocabulary; `session.tool.completed` is three perfectly good words in the
/// right order that **nothing in a run ever reaches**, and the fix is the list of
/// moments that thing really has. The second check was missing for a round, so a
/// watch bound to a well-formed address that never fires passed `pact check` and
/// was refused later, in Python, in a process the author never starts — the exact
/// "loads and does nothing" failure `type: event-address` was added to end.
///
/// One diagnostic naming the position that is wrong and the words that belong
/// there, rather than "this is not an address" — an author who typed
/// `step.phase.before` needs to be told that `phase` is not a thing that
/// happens and that `stage` is, not that the whole line is malformed.
///
/// A position may carry an author's own word behind an `x-` prefix, which is
/// how the lattice grows without a schema bump; `x-` is never confused with the
/// closed words because nothing in them starts with it. An address carrying one
/// is exempt from the reachability check too: whatever emits it is the host's,
/// so nothing here has a list to hold it against and refusing would be a guess.
fn check_address(
    node: &Node,
    field: &str,
    written: &str,
    parts: &[(String, Vec<String>)],
    reaches: &[String],
) -> Option<Diagnostic> {
    let shape: Vec<String> = parts.iter().map(|(n, _)| format!("<{n}>")).collect();
    let example: Vec<&str> = parts
        .iter()
        .map(|(_, words)| words.first().map(String::as_str).unwrap_or("..."))
        .collect();
    let given: Vec<&str> = written.trim().split('.').collect();
    if given.len() != parts.len() {
        return Some(Diagnostic::error(
            "schema/not-a-moment",
            node.span.clone(),
            format!("'{field}' should say when it runs, and '{written}' does not."),
            format!(
                "Write it as `{}` — for example `{}: {}`.",
                shape.join("."),
                field,
                example.join(".")
            ),
        ));
    }
    for (word, (name, allowed)) in given.iter().zip(parts) {
        if word.starts_with("x-") || allowed.iter().any(|a| a == word) {
            continue;
        }
        return Some(Diagnostic::error(
            "schema/not-a-moment",
            node.span.clone(),
            format!("'{word}' is not {}{name} PACT knows about.", article(name)),
            format!(
                "Change it to one of: {} — or, for one of your own, give it an 'x-' \
                 prefix. The whole line reads `{}`.",
                allowed.join(", "),
                shape.join(".")
            ),
        ));
    }

    // Well formed, and nothing this field is bound to ever happens there.
    let address = written.trim();
    if reaches.is_empty()
        || given.iter().any(|w| w.starts_with("x-"))
        || reaches.iter().any(|a| a == address)
    {
        return None;
    }
    // The moments the same THING really has, so the fix is a short list rather
    // than thirty lines. `session.tool.completed` becomes "a tool has
    // `cancelled`, `completed`, `started`", which is the sentence an author can
    // act on without reading the lattice.
    let subject = given.get(1).copied().unwrap_or("");
    let same: Vec<&str> = reaches
        .iter()
        .map(String::as_str)
        .filter(|a| a.split('.').nth(1) == Some(subject))
        .collect();
    let offer = if same.is_empty() {
        reaches.iter().map(String::as_str).collect::<Vec<_>>().join(", ")
    } else {
        same.join(", ")
    };
    Some(Diagnostic::error(
        "schema/nothing-happens-there",
        node.span.clone(),
        // "nothing in a run ever reaches X" is literally false wherever a WATCH
        // binds at X and an interceptor may not — `step.tool.completed` was
        // exactly that for a round, so the message told an author their address
        // did not exist while another field in the same tree accepted it. What
        // is true, and what they can act on, is that no rule is handed the run
        // there.
        format!(
            "no rule is handed the run at '{address}', so '{field}' would sit there \
             and never fire."
        ),
        format!("Change it to one of: {offer}."),
    ))
}

/// *"This rule needs"* / *"These 3 rules need"*, *"This rule is"* / *"These 2
/// rules are"* — the opening of a refusal that may be about one sentence or
/// several.
///
/// A count in the first clause is what tells the reader, before they look at
/// anything else, that the three underlined lines are one problem and not three.
///
/// The verb comes from the caller in both numbers because English will not let
/// the subject carry it, and a second helper per verb would be a second copy of
/// the counting rule to keep in step.
fn these_rules(n: usize, one: &str, many: &str) -> String {
    if n == 1 {
        format!("This rule {one}")
    } else {
        format!("These {n} rules {many}")
    }
}

/// Attach every line after the first as a related location on one diagnostic.
///
/// The alternative — one top-level error per line — is what this replaces: a
/// file with five sentences and one bad `when:` printed five word-for-word
/// identical errors, each offering the same fix, and the author had to read all
/// five to learn they were one. Related lines are underlined under the first
/// message instead, so the count of problems is the count of mistakes.
///
/// The same anchoring `report_companions` uses: the first line the author wrote,
/// because that is the one they are looking at.
fn with_the_rest(d: Diagnostic, spans: &[pact_diag::Span]) -> Diagnostic {
    spans[1..]
        .iter()
        .fold(d, |d, s| d.with_related(s.clone(), "and this one, for the same reason"))
}

/// The words written under `name:`, whether the author wrote a list or one line.
///
/// Both fields a sentence vocabulary consults are lists that may be written as a
/// bare scalar — `may:` always was, and `when:` became one so that a rule
/// running at two moments is one file. Written out twice, one of the two copies
/// read only `as_str()` and silently saw nothing where a list was.
fn words_of<'a>(map: &'a Map, name: &str) -> Vec<&'a str> {
    map.get(name)
        .map(|e| match e.node.as_list() {
            Some(l) => l.iter().filter_map(Node::as_str).collect(),
            None => e.node.as_str().into_iter().collect(),
        })
        .unwrap_or_default()
}

/// Is every entry of this block prose, so the block is one document split up?
///
/// The test for whether a folder under a `text:` field is the *"split it up when
/// it gets long"* the READMEs promise, or a mistake. Every entry text, and at
/// least one — an empty folder is a field the author meant to write and did not.
fn is_all_prose(map: &Map) -> bool {
    !map.is_empty()
        && map.values().all(|e| matches!(e.node.value, Value::Str(_)))
}

/// The rule a scalar type puts on the SPELLING of its text, when it has one.
///
/// Two types do. Both were checked only by the Python adapter for a round, so
/// the author's own tool said the file was fine and the refusal happened later,
/// in another language, in a process they never start — which is the split this
/// whole file exists to close.
fn spelling(node: &Node, field: &str, ty: &Ty, written: &str, at: &Where) -> Option<Diagnostic> {
    match ty {
        Ty::FileName => {
            let name = written.trim();
            // The same four refusals `watches._check_destination` makes, and the
            // same offered name, so the two halves cannot be told apart.
            let bad = if name.is_empty() {
                "is empty"
            } else if name.contains('/') || name.contains('\\') {
                "has a folder in it"
            } else if name.starts_with('.') {
                "starts with a dot, which hides it"
            } else {
                return None;
            };
            let plain: String = name
                .rsplit(['/', '\\'])
                .next()
                .unwrap_or("")
                .trim_start_matches('.')
                .to_string();
            // `escape.jsonl` must not be offered back as `escape.jsonl.jsonl`.
            let stem = plain.strip_suffix(".jsonl").unwrap_or(&plain);
            let offer = if stem.is_empty() { "record".to_string() } else { stem.to_string() };
            Some(Diagnostic::error(
                "schema/not-a-file-name",
                node.span.clone(),
                format!("'{written}' {bad}, and `{field}:` is just a file name."),
                format!(
                    "Write `{field}: {offer}.jsonl`. The file is put in this workspace's own \
                     `.pact` area, which is chosen for you, so a record can never land on top \
                     of one of your files."
                ),
            ))
        }
        Ty::AnswerShape(shapes) => {
            // Read by the one reader (`shape.rs`), with the names of the
            // workspace's own `shapes:`, so `list of invoice-line` is a shape
            // exactly where `invoice-line` is declared.
            let named: Vec<&str> = at
                .root
                .get("shapes")
                .and_then(Node::as_map)
                .map(|m| m.keys().map(String::as_str).collect())
                .unwrap_or_default();
            match shape::parse(written, shapes, &named) {
                Ok(_) => None,
                Err(shape::Unread::NoChoices) => Some(Diagnostic::error(
                    "schema/not-an-answer-shape",
                    node.span.clone(),
                    format!("'{written}' does not say what to choose between."),
                    "Write the choices after it, like `one of yes, no, maybe`.".to_string(),
                )),
                Err(shape::Unread::NotAShape(part)) => {
                    let whole = shape::normalised(written);
                    let not = if whole.contains(&part) && whole != part {
                        format!("'{written}' is not a shape an answer can have: '{part}' is none, so nothing could read it.")
                    } else {
                        format!("'{written}' is not a shape an answer can have, so nothing could read it.")
                    };
                    let mut known: Vec<&str> = shapes.iter().map(|(n, _)| n.as_str()).collect();
                    known.extend(named.iter().copied());
                    Some(Diagnostic::error(
                        "schema/not-an-answer-shape",
                        node.span.clone(),
                        not,
                        format!(
                            "Change it to one of: {} — or `one of a, b, c` to choose between things \
                             you name. Any of them may be written `list of <shape>`, and followed \
                             by `, optional` when it may be missing; a shape with parts is named \
                             under `shapes:` in workspace.yaml.",
                            known.join(", ")
                        ),
                    ))
                }
            }
        }
        Ty::CombineRule(rules) => {
            if rules.iter().any(|(_, spellings)| spellings.iter().any(|s| spelt_as(written, s))) {
                return None;
            }
            Some(Diagnostic::error(
                "schema/not-a-combine-rule",
                node.span.clone(),
                format!(
                    "'{written}' is not a way of combining answers, so nothing could say what \
                     '{field}' comes to."
                ),
                format!(
                    "Change it to one of: {}.",
                    rules
                        .iter()
                        .filter_map(|(_, s)| s.first().map(|s| format!("`{s}`")))
                        .collect::<Vec<_>>()
                        .join(", ")
                ),
            ))
        }
        _ => None,
    }
}

/// Whether `written` is `spelling`, word for word and ignoring case, where a
/// `<n>` in the spelling stands for a whole number of at least 1 and any other
/// `<...>` for one word of the author's own (`top <n> lowest by <field>`).
fn spelt_as(written: &str, spelling: &str) -> bool {
    let said: Vec<&str> = written.split_whitespace().collect();
    let want: Vec<&str> = spelling.split_whitespace().collect();
    said.len() == want.len()
        && said.iter().zip(&want).all(|(s, w)| match *w {
            "<n>" => s.parse::<u64>().is_ok_and(|n| n >= 1),
            w if w.starts_with('<') && w.ends_with('>') => !s.is_empty(),
            w => s.eq_ignore_ascii_case(w),
        })
}

/// Names that take no indefinite article at all, because no spelling of one
/// works: `learning` and `teamwork` are uncountable, so `a learning` is wrong
/// the way `a weather` is wrong.
///
/// Written down because countability is not visible in the spelling. Plurals
/// are — see [`article`] — so they are not listed here.
const UNCOUNTABLE: &[&str] = &["learning", "teamwork"];

/// The indefinite article a name from `spec/schema.yaml` takes, with the space
/// after it: `a `, `an `, or nothing. Compose it in front of the name —
/// `an agent`, `a tool`, `evals`, `learning`.
///
/// **This is not English and does not try to be.** English needs a pronunciation
/// dictionary for `an hour` and `a user`, and a countability dictionary for
/// `learning`. PACT has thirty-two group names and every one is a lowercase
/// ASCII word we chose ourselves, so the leading letter settles all of them and
/// the two uncountable ones are listed above. A name this would get wrong is a
/// name not to add; if one arrives anyway, the fix is a word in `UNCOUNTABLE`
/// here, beside this comment, and not a special case in whichever sentence
/// happened to notice.
///
/// It is a function rather than three corrected string literals so that a group
/// added to `spec/schema.yaml` later — which is a YAML edit, never a Rust change
/// (E-3) — reads correctly without anybody remembering this file exists.
///
/// The empty arm is the part that is easy to miss: `a evals` is not fixed by
/// `an evals`, because a plural takes no indefinite article in *either*
/// spelling. That is why the sentences built from this say `must have` and
/// `can have` — verbs that agree with `an agent` and with `evals` alike.
fn article(name: &str) -> &'static str {
    // A trailing `s` that is not `ss` — `evals`, `limits`, `needs`, `settings`,
    // and the field names `asks`, `answers`, `does`, `lasts`. Reading it off the
    // spelling rather than a list is what makes a plural group name added later
    // come out right on its own.
    if name.ends_with('s') && !name.ends_with("ss") {
        return "";
    }
    if UNCOUNTABLE.contains(&name) {
        return "";
    }
    if name.starts_with(['a', 'e', 'i', 'o', 'u']) {
        return "an ";
    }
    "a "
}

/// What to call the thing the author actually wrote, for the *"but it is …"*
/// half of [`wrong_type`].
///
/// **A figure is never text, however it had to be carried.** The noun used to
/// come straight off `Value::kind_name`, and that stopped being the same
/// question the day a figure this cannot hold started being KEPT as the
/// author's text: `1e999` and `99999999999999999999` at the top of the scale,
/// `1e-999` at the bottom, all of them `Value::Str` so that `pact show` and the
/// digest do not lose them, and all of them therefore *"some text"*. Measured
/// on the build before this function, `finishes-within: 1e-999` and
/// `finishes-within: abc` gave byte-identical reports, and `steps-at-most: 0.5`
/// — one order up the same scale, held exactly, still a `Value::Float` — said
/// *"a number"*. An author with a figure on the page was told they had not
/// written one and sent hunting for a typo that is not there, which is the harm
/// `coerce::number`, `coerce::size` and `underflowed_to_zero` are each written
/// to prevent, appearing in the one place that reads none of them.
///
/// So the noun is read off the TEXT, and it answers exactly what the value
/// kinds would have answered had the tree been able to hold the figure: a run
/// of digits is *"a whole number"* (what `Value::Int` says), anything else that
/// parses as a figure is *"a number"* (what `Value::Float` says).
///
/// **Unless there is no digit in it.** `.inf`, `.nan` and `lots` are words
/// spelled where a figure goes — `".inf".parse::<f64>()` fails and `inf` alone
/// carries no digit — and *"some text"* is the true sentence for them. That is
/// the same line `coerce::integer` and `coerce::size` draw, drawn once more for
/// the sentence rather than the rule.
/// The figure a diagnostic quotes back, for a node that may not be text.
///
/// Every value the ceiling refuses used to be a `Value::Str` — a figure past
/// holding was kept as the author's text — so `node.as_str()` was enough. It
/// stopped being enough the moment the ceiling started asking about the FIGURE
/// rather than the spelling: `temperature: 1e19` is a number the document layer
/// holds exactly, and quoting `node.as_str()` for it would have printed
/// *"'temperature' is , which is more than this can keep track of"*, an empty
/// space where the value goes.
///
/// A double is written back the way the rest of this format writes one, so the
/// sentence names the same figure the author wrote even where it does not name
/// the same notation: `1e19` is quoted as `10000000000000000000`. The caret
/// under the line is what points at the notation.
///
/// Except where writing it out in full would bury the sentence. `1e308` in full
/// is three hundred and nine digits, and *"'finishes-within' is 1000…000, which
/// is a longer time than this can keep track of"* is a message with a paragraph
/// of zeros in the middle of it — measured, in the shipped binary, before this
/// line. Past twenty-one digits (which is `1e20`, and covers every figure a
/// person plausibly types out) the exponent form is the readable one and it is
/// the form such a figure was written in anyway.
fn as_written(node: &Node) -> String {
    match &node.value {
        Value::Str(s) => s.trim().to_string(),
        Value::Int(i) => i.to_string(),
        Value::Float(x) => {
            let full = format!("{x}");
            if full.len() > 21 { format!("{x:e}") } else { full }
        }
        other => other.kind_name().to_string(),
    }
}

fn kind_as_written(node: &Node) -> &'static str {
    let Value::Str(written) = &node.value else {
        return node.value.kind_name();
    };
    let written = written.trim();
    if !has_a_digit(written) || written.parse::<f64>().is_err() {
        return node.value.kind_name();
    }
    let digits = written.strip_prefix(['-', '+']).unwrap_or(written);
    if digits.bytes().all(|b| b.is_ascii_digit()) {
        "a whole number"
    } else {
        "a number"
    }
}

fn wrong_type(node: &Node, field: &str, ty: &Ty) -> Diagnostic {
    Diagnostic::error(
        "schema/wrong-type",
        node.span.clone(),
        format!("'{field}' should be {}, but it is {}.", ty.describe(), kind_as_written(node)),
        match ty {
            Ty::OneOf(v) => format!("Change it to one of: {}.", v.join(", ")),
            // Every spelling an author can type, because for a round the fix
            // named three of them and somebody who wanted "five minutes" had no
            // way to find out that `5 minutes` already worked.
            //
            // The unit is not optional here even though `coerce::duration`
            // tolerates a bare number, and that is deliberate: `finishes-within:
            // 90` could mean ninety seconds or ninety minutes, and guessing
            // wrong moves a ceiling by sixty times without saying so — the same
            // reason `Ty::Percent` refuses a bare `90`. Written that way in a
            // file it is a whole number, not text, so it is refused by this very
            // diagnostic and the author is told to add the unit.
            Ty::Duration => "Write it like `2s`, `500ms`, `1m30s`, `5 minutes` or `1d` — a \
                             number and a unit, where the unit is `ms`, `s`, `m`, `h` or `d` \
                             or its long name (`milliseconds`, `seconds`, `minutes`, `hours`, \
                             `days`), the space between them is optional, and parts may run \
                             together."
                .to_string(),
            Ty::Money => "Write it like `0.05 USD`.".to_string(),
            // The range is named, because for a round it was not held at all and
            // `-50%` and `150%` both loaded clean. A fix that says `90%` and
            // nothing else does not tell a reader who typed `150%` what is wrong.
            Ty::Percent => "Write it like `90%` — a share of the whole, so between `0%` and \
                            `100%`."
                .to_string(),
            Ty::Threshold => "Write it like `> 80` or `>= 0.8`.".to_string(),
            Ty::Size => "Write it like `32k`, `128k`, `1m` or `200000` — a number of words the \
                         model reads at once."
                .to_string(),
            Ty::FileName => "Write just a file name, like `tool-calls.jsonl` — no folders in it."
                .to_string(),
            Ty::YesNo => "Write `yes` or `no`.".to_string(),
            other => format!("Change it to {}.", other.describe()),
        },
    )
}

/// Record what `f` needs alongside it, unless the author already wrote it.
///
/// Checked against every spelling the companion accepts, so an alias satisfies
/// the requirement — otherwise an imported document would be told to add a line
/// it already has under another name.
fn note_companions(
    f: &Field,
    g: &Group,
    map: &pact_doc::Map,
    at: &pact_diag::Span,
    owed: &mut IndexMap<String, Vec<(String, pact_diag::Span)>>,
) {
    // Exactly one of a set, which `needs_also` cannot state: it names one field
    // and fires on presence, so `arg:` could demand `more-than:` and could not
    // say "or `is:`, or `is-one-of:`, and only one of them".
    if !f.needs_one_of.is_empty() {
        let set: Vec<&str> = f.needs_one_of.iter().map(String::as_str).collect();
        let written: Vec<&str> = set
            .iter()
            .copied()
            .filter(|want| {
                g.fields
                    .iter()
                    .find(|x| x.name == *want)
                    .map(|other| {
                        std::iter::once(&other.name)
                            .chain(other.aliases.iter())
                            .any(|n| map.contains_key(n))
                    })
                    .unwrap_or(false)
            })
            .collect();
        if written.len() != 1 {
            let listed = set.join("`, `");
            owed.entry(format!("__one_of__{listed}")).or_default().push((
                f.name.clone(),
                at.clone(),
            ));
        }
    }
    for want in &f.needs_also {
        let written = g
            .fields
            .iter()
            .find(|x| &x.name == want)
            .map(|other| {
                std::iter::once(&other.name)
                    .chain(other.aliases.iter())
                    .any(|n| map.contains_key(n))
            })
            .unwrap_or(false);
        if written {
            continue;
        }
        owed.entry(want.clone()).or_default().push((f.name.clone(), at.clone()));
    }
}

/// A value of type `ty` that an author can literally type. Used in fixes, where
/// The sentence naming every word a companion accepts, or nothing.
///
/// It looked only at a bare `one-of`, so the moment a companion was a LIST of
/// choices the author was told to add `may-improve-on-its-own: phrasing` and
/// never told the other three words existed. `learning.enabled:
/// applies-safe-changes-itself` is exactly that pairing — the setting that puts
/// wording changes live with nobody reading them — and picking one of four
/// blind, on that line, is the wrong governance decision made by accident.
/// Whether the figure an author actually typed carried a digit.
///
/// The only thing that tells `1e400 USD` apart from `inf USD` once it is parsed,
/// because both are `f64::INFINITY` by the time anything here sees them — and
/// they are two different mistakes: one is a real amount past the end of what
/// can be counted, the other is not an amount.
fn has_a_digit(written: &str) -> bool {
    written.chars().any(|c| c.is_ascii_digit())
}

/// Which end of the number line a figure ran off, in the four parts
/// [`Schema::check_ceiling`] builds its sentence from.
///
/// One function and not two arms, because the two types that use it — a number
/// and a comparison against one — are the same figure and must not drift into
/// two different sentences for it.
///
/// **Both ends, and each with its own words.** `temperature: 1e999` is more
/// than can be kept track of; `temperature: -1e999` is not — it is further
/// BELOW zero than can be kept track of, and an author told that the smallest
/// number they could write is "more than" something would go looking for a
/// smaller one and find the one they had already written. This is where a
/// number parts company with money, which needs only the top end: an amount
/// below zero is refused at [`Schema::check_floor`] as "less than nothing"
/// before its size is ever in question, while `-1e999` on a plain number is a
/// real figure at the bottom of a scale that runs both ways.
/// A figure that ran off the BOTTOM of the scale: written with a digit that is
/// not zero, arrived as zero.
///
/// The mirror of [`past_counting`], and it has to read the text rather than the
/// figure because the figure is the one thing that no longer says anything —
/// `1e-999`, `0.0` and `0` all arrive here as the same `0.0`. What tells them
/// apart is what the author wrote, and `yaml::resolve_scalar` is the reason it
/// is still there to read: a scalar that parses to zero while carrying a figure
/// is kept as text, so `as_str` answers for exactly the values this is about and
/// answers `None` for an honest `0` or `0.0`, which are `Int` and `Float`.
///
/// The same significand rule as the document layer, and for the same reason:
/// `0e10` is a zero somebody meant, `1e-999` is not.
fn underflowed_to_zero(n: f64, node: &Node) -> bool {
    if n != 0.0 {
        return false;
    }
    let Some(written) = node.as_str() else {
        return false;
    };
    let written = written.trim();
    let significand = written.split(['e', 'E']).next().unwrap_or(written);
    significand.chars().any(|c| c.is_ascii_digit() && c != '0')
}

/// **The fix names a set the author can actually write in, which for a round it
/// did not.** It said *"or any smaller number"*, and the accepted set does not
/// run downward: measured through the shipped binary, `temperature:
/// 1e999` was refused with that fix and `temperature: 9223372036854775808` — a
/// smaller number, obediently written — was refused by the identical rule. A fix
/// that fails when it is followed is worse than no fix, and the test that
/// guarded this line only checked that the sentence was PRESENT, never that it
/// was true.
///
/// Fifteen digits is the largest count that is true whatever the type asking:
/// every whole number under 10^15 is inside [`coerce::PAST_COUNTING`] (2^53,
/// sixteen digits) and inside `i64` (nineteen), so a reader who follows this
/// sentence lands somewhere every one of these fields accepts. It is
/// deliberately a bound this can promise rather than the exact edge of what is
/// held — an author edits a file, and `9007199254740991` is not something to ask
/// them to type.
const HELD: &str = "any figure of fifteen digits or fewer";

fn past_counting(n: f64, ty: Ty) -> (&'static str, &'static str, &'static str, Ty) {
    if n.is_sign_positive() {
        ("schema/too-big-to-count", "more than this can keep track of", HELD, ty)
    } else {
        ("schema/too-big-to-count", "further below zero than this can keep track of", HELD, ty)
    }
}

/// An amount that overflowed to infinity on the way in: written with digits,
/// arrived as `+inf`.
///
/// The one money value that belongs to [`Schema::check_ceiling`] rather than to
/// [`Schema::check_floor`], and the only thing telling the two apart for money.
/// A NEGATIVE overflow is deliberately not here: `-1e400 USD` is less than
/// nothing before it is large, and "less than nothing" is the sentence that gets
/// its author to the right edit.
fn money_past_counting(amount: f64, node: &Node) -> bool {
    amount == f64::INFINITY && has_a_digit(node.as_str().unwrap_or_default())
}

fn choices_clause(ty: &Ty) -> String {
    match ty {
        Ty::OneOf(v) => format!(" The choices are: {}.", v.join(", ")),
        // A list of choices, which is the same question with more than one
        // answer allowed — and the leniency that accepts a bare value where a
        // list belongs is what makes the placeholder above typeable either way.
        Ty::ListOf(inner) => match inner.as_ref() {
            Ty::OneOf(v) => format!(" The choices are: {}, and you may write several.", v.join(", ")),
            _ => String::new(),
        },
        _ => String::new(),
    }
}

/// `...` is a correct answer and a useless one.
fn placeholder(ty: &Ty) -> String {
    match ty {
        Ty::OneOf(v) => v.first().cloned().unwrap_or_else(|| "...".into()),
        Ty::YesNo => "yes".into(),
        Ty::Number | Ty::Integer => "10".into(),
        Ty::Duration => "30s".into(),
        Ty::Money => "0.05 USD".into(),
        Ty::Percent => "90%".into(),
        Ty::Threshold => "> 80".into(),
        Ty::Size => "32k".into(),
        Ty::FileName => "what-happened.jsonl".into(),
        Ty::AnswerShape(shapes) => {
            shapes.first().map(|(n, _)| n.clone()).unwrap_or_else(|| "text".into())
        }
        Ty::CombineRule(rules) => rules
            .first()
            .and_then(|(_, spellings)| spellings.first().cloned())
            .unwrap_or_else(|| "keep-all".into()),
        Ty::Moment => "3 days".into(),
        Ty::Comparand => "80".into(),
        // A moment the field really REACHES, when it names any. Built out of
        // the first word of each position, the offer was
        // `session.message.requested` — three good words in the right order that
        // nothing in a run ever arrives at, so an author who typed the fix was
        // refused by the very next check with `schema/nothing-happens-there`.
        // A fix that fails is worse than no fix, because it costs a round trip
        // to learn the tool was guessing.
        Ty::EventAddress(parts, reaches) => match reaches.first() {
            Some(first) => first.clone(),
            None => parts
                .iter()
                .map(|(_, words)| words.first().map(String::as_str).unwrap_or("..."))
                .collect::<Vec<_>>()
                .join("."),
        },
        // A list offers what ONE of its entries looks like, since a single value
        // is accepted wherever a list is. `interceptor.when` became a list and
        // every fix that names it went from `when: step.message.before` to
        // `when: ...`, which is the useless answer this function exists to avoid.
        Ty::ListOf(inner) => placeholder(inner),
        _ => "...".into(),
    }
}

fn example(g: &Group) -> String {
    g.fields
        .iter()
        .take(2)
        .map(|f| format!("{}: ...", f.name))
        .collect::<Vec<_>>()
        .join("\n         ")
}

#[cfg(test)]
mod tests {
    use super::*;
    use camino::Utf8Path;
    use pact_doc::parse_yaml;

    fn agent_schema() -> Schema {
        Schema::new().with(Group {
            name: "agent".into(),
            describe: String::new(),
            fields: vec![
                Field::new("name", Ty::Text, "what to call this agent").required(),
                Field::new("description", Ty::Text, "one line on what it does")
                    .required()
                    .alias("does"),
                Field::new("instructions", Ty::Text, "what it should actually do"),
                Field::new(
                    "reasoning",
                    Ty::OneOf(vec!["simple".into(), "careful".into(), "expert".into()]),
                    "how much thinking it needs",
                ),
                Field::new("tools", Ty::YesNo, "whether it can use tools"),
                Field::new("finishes-within", Ty::Duration, "how long it may take"),
                Field::new("uses", Ty::ListOf(Box::new(Ty::Text)), "what it may use"),
                Field::new("team", Ty::MapOf(Box::new(Ty::Text)), "who helps"),
                Field::new("steps-at-most", Ty::Integer, "how many steps before it must stop")
                    .needs_also("when-it-runs-out"),
                Field::new(
                    "when-it-runs-out",
                    Ty::OneOf(vec![
                        "stop-and-say-so".into(),
                        "ask-a-person".into(),
                        "answer-with-what-it-has".into(),
                    ]),
                    "what to do on reaching a ceiling",
                ),
            ],
        })
    }

    fn check(yaml: &str) -> Diagnostics {
        let node = parse_yaml(yaml, Utf8Path::new("agent.yaml")).expect("parses");
        let mut d = Diagnostics::new();
        d.add_source("agent.yaml", yaml);
        agent_schema().validate(&node, "agent", &mut d);
        d.sort();
        d
    }

    #[test]
    fn a_correct_document_produces_nothing() {
        let d = check(
            "name: Refund Desk\ndescription: Decides refunds\nreasoning: careful\n\
             tools: yes\nfinishes-within: 30s\nuses:\n  - zendesk\nteam:\n  helper: does things\n",
        );
        assert!(!d.has_errors(), "{}", d.render());
    }

    #[test]
    fn a_typo_gets_a_suggestion_not_a_list() {
        // D13: "did you mean" is the difference between a fixable error and a
        // dead end for someone who cannot read a schema.
        let d = check("name: X\ndescription: Y\ndescriptoin: Z\n");
        let e = d.items().iter().find(|x| x.rule == "schema/unknown-field").expect("caught");
        assert!(e.fix.contains("Did you mean 'description'"), "got: {}", e.fix);
    }

    #[test]
    fn a_missing_required_field_says_what_to_add() {
        let d = check("name: X\n");
        let e = d.items().iter().find(|x| x.rule == "schema/missing-field").expect("caught");
        assert!(e.message.contains("description"));
        assert!(e.fix.contains("description:"), "the fix must be typeable: {}", e.fix);
    }

    #[test]
    fn an_alias_is_accepted_so_imports_do_not_break() {
        let d = check("name: X\ndoes: handles refunds\n");
        assert!(!d.has_errors(), "{}", d.render());
    }

    #[test]
    fn setting_a_field_under_two_names_is_refused_not_silently_dropped() {
        // Found by adversarial review of this file: `or_else` took the first
        // spelling and discarded the rest, and the alias also passed the
        // unknown-field check — so an author's value vanished with no message.
        let d = check("name: X\ndescription: real\ndoes: also real\n");
        let e = d
            .items()
            .iter()
            .find(|x| x.rule == "schema/same-setting-twice")
            .expect("T7: a discarded value must be reported");
        assert!(e.message.contains("does") && e.message.contains("description"));
        assert_eq!(e.related.len(), 1, "must point at the other spelling");
        assert!(e.fix.contains("description"), "must name the preferred spelling: {}", e.fix);
    }

    #[test]
    fn a_wrong_word_lists_the_allowed_ones() {
        let d = check("name: X\ndescription: Y\nreasoning: brilliant\n");
        let e = d.items().iter().find(|x| x.rule == "schema/wrong-type").expect("caught");
        assert!(e.fix.contains("simple"), "must name the choices: {}", e.fix);
        assert!(e.fix.contains("careful"));
    }

    #[test]
    fn yes_and_no_are_accepted_for_a_yes_no_field() {
        for v in ["yes", "no", "true", "false", "on", "off", "YES"] {
            let d = check(&format!("name: X\ndescription: Y\ntools: {v}\n"));
            assert!(!d.has_errors(), "'{v}' should be accepted: {}", d.render());
        }
    }

    #[test]
    fn a_single_value_is_accepted_where_a_list_was_expected() {
        // Being strict about `uses: zendesk` vs `uses: [zendesk]` teaches the
        // author nothing and costs them a round trip.
        let d = check("name: X\ndescription: Y\nuses: zendesk\n");
        assert!(!d.has_errors(), "{}", d.render());
    }

    #[test]
    fn extension_fields_pass_through_untouched() {
        // E-2 / P-3: unknown `x-` data survives a round trip rather than being
        // dropped or rejected.
        let d = check("name: X\ndescription: Y\nx-internal-ticket: ABC-123\n");
        assert!(!d.has_errors(), "{}", d.render());
    }

    #[test]
    fn a_ceiling_set_without_saying_what_happens_at_it_is_refused() {
        // The whole point of the termination algebra: stopping silently, asking
        // a person, and answering as if finished are three different governance
        // decisions. A system that picks one for you has made that decision on
        // your behalf, so the pairing is enforced rather than defaulted.
        let d = check("name: X\ndescription: Y\nsteps-at-most: 12\n");
        let e = d
            .items()
            .iter()
            .find(|x| x.rule == "schema/missing-companion")
            .expect("a ceiling with no action must be caught");
        assert!(e.message.contains("steps-at-most") && e.message.contains("when-it-runs-out"));
    }

    #[test]
    fn the_fix_for_a_missing_action_names_a_value_the_author_can_type() {
        let d = check("name: X\ndescription: Y\nsteps-at-most: 12\n");
        let e = d.items().iter().find(|x| x.rule == "schema/missing-companion").unwrap();
        assert!(
            e.fix.contains("`when-it-runs-out: stop-and-say-so`"),
            "the fix must be a line to type: {}",
            e.fix
        );
        // And all three choices, because picking one blind is how the wrong
        // governance decision gets made by accident.
        for choice in ["stop-and-say-so", "ask-a-person", "answer-with-what-it-has"] {
            assert!(e.fix.contains(choice), "'{choice}' missing from: {}", e.fix);
        }
    }

    #[test]
    fn a_ceiling_with_its_action_set_is_accepted() {
        let d = check(
            "name: X\ndescription: Y\nsteps-at-most: 12\nwhen-it-runs-out: ask-a-person\n",
        );
        assert!(!d.has_errors(), "{}", d.render());
    }

    #[test]
    fn a_companion_is_only_demanded_when_the_field_that_needs_it_is_present() {
        // The mechanism must cost nothing when unused: an agent with no ceiling
        // is not asked what to do when it reaches one.
        let d = check("name: X\ndescription: Y\n");
        assert!(!d.has_errors(), "{}", d.render());
    }

    #[test]
    fn every_schema_diagnostic_is_free_of_jargon() {
        let d = check("name: 5\ndescriptoin: Y\nreasoning: nope\nfinishes-within: soon\n");
        assert!(d.error_count() >= 3, "{}", d.render());
        let text = d.render().to_lowercase();
        for jargon in ["enum", "variant", "deserialize", "expected type", "vec<", "option<", "null pointer"] {
            assert!(!text.contains(jargon), "diagnostic leaked '{jargon}':\n{}", d.render());
        }
        for item in d.items() {
            assert!(!item.fix.trim().is_empty(), "{} had no fix", item.rule);
        }
    }
}
