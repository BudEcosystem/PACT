//! Fields whose values are sentences from a closed vocabulary.
//!
//! `interceptor.rules` is the one that forced this. It was `list of text` with
//! no constraint, so `pact check` — the only tool decision D13's author runs —
//! accepted `if the customer seems angry, escalate to a manager`, and the
//! refusal happened later, in another language, in a process they never start.
//! Meanwhile the four sentences that *do* work were written out in the field's
//! `help:` for a human to read and nowhere for a machine to check, so the help
//! text and the behaviour had nothing holding them together.
//!
//! The forms are **data**, in `spec/schema.yaml`, beside the help that
//! describes them. That is the R6 precedent: an attribute is added when the
//! alternative is a Rust `if` per case, because a vocabulary buried in the core
//! makes the next sentence cost a recompile instead of a line of YAML (F-1).
//!
//! Two things are written in a form besides its words:
//!
//! * `needs:` — the power the sentence uses, which the document must have
//!   declared. A rule that hides values in a document that never said it may is
//!   refused here rather than at run time.
//! * `at:` — the moments the sentence can be bound to. A redirect bound where
//!   nothing carries one out is a rule that loads and does nothing, which is the
//!   failure the whole interceptor design is written against.
//!
//! The values inside the angle brackets **are** checked, and for a round they
//! were not. `replace anything that looks like a passport number with "x"`
//! matched the form and was refused by the adapter — while the field's own help
//! says such a sentence is *"never accepted and quietly ignored"* — and
//! `if paymnets is called more than 1 time in one run, stop and say "..."`
//! loaded clean and let the second refund through, on the one rule the worked
//! example's `stop-runaway-refunds` exists to be.
//!
//! Two vocabularies do it, both written as data on the field:
//!
//! * `recognises:` — a hole whose values are a closed list (`<a thing>` is one
//!   of card number, bank account, email address, phone number, social security number).
//! * `resolve:` — a hole that names something the workspace has (`<a tool>` is
//!   a key of `tools:`).
//!
//! Capture is unambiguous because the matcher takes the FIRST reading that
//! walks the whole sentence, which is the same reading `Forms::recognise`
//! already accepted; nothing about which form matched changes. `<stage>` is
//! deliberately in neither list: an interceptor does not know which agent will
//! name it, so it does not know which loop's stages to hold it against, and
//! `Loop.check_against` does that before the first model call.

/// One sentence an author may write, with what it needs to work.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Form {
    /// The words, with `<name>` where the author fills something in, `<name?>`
    /// where what they fill in may be empty (`with ""` deletes rather than
    /// replaces), and `[word]` for a word they may leave out.
    pub say: String,
    /// The power it uses, named in the sibling field `Forms::declares`.
    pub needs: String,
    /// The moments it works at, checked against the sibling field
    /// `Forms::binds`. Empty means anywhere.
    pub at: Vec<String>,
    /// True when the sentence carries on from an earlier one and is not a rule
    /// on its own — `do the same for anything that looks like <a thing>` reuses
    /// the replacement the line above it chose.
    ///
    /// Written first it has nothing to be the same as and hides nothing, and
    /// until this was data that fact lived only in the adapter: measured, an
    /// interceptor whose one rule was `do the same for anything that looks like
    /// a card number` printed *"loaded cleanly"* and was then refused by the
    /// thing that runs it. That is the split — checked here, refused there, in
    /// a process the author never starts — this whole module exists to close.
    pub continues: bool,
}

impl Form {
    /// The sentence as an author should type it, with the matcher's own marks
    /// taken off: `time[s]` reads `times`, `<text?>` reads `<text>`.
    ///
    /// Printed under every refusal, so what a diagnostic offers is word for word
    /// what the field's `help:` lists. Two hand-written copies of four sentences
    /// is two things to keep in step, and the help text is where an author looks
    /// second.
    pub fn readable(&self) -> String {
        self.say.replace(['[', ']'], "").replace("?>", ">")
    }
}

/// The closed vocabulary of one field, and the two siblings it is held against.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Forms {
    /// The field listing what this document may do — `may:` on an interceptor.
    pub declares: String,
    /// The field saying when it runs — `when:` on an interceptor.
    pub binds: String,
    pub one_of: Vec<Form>,
    /// Holes whose values come from a closed list, by hole name.
    pub recognises: Vec<(String, Vec<String>)>,
    /// Holes whose values name a key of a workspace map, by hole name.
    pub resolve: Vec<(String, String)>,
}

impl Forms {
    /// The sentence this text is, or nothing.
    pub fn recognise(&self, text: &str) -> Option<&Form> {
        self.capture(text).map(|(f, _)| f)
    }

    /// The sentence this text is, and what the author wrote in each hole.
    ///
    /// The article is stripped from a captured value — `a card number`, `the
    /// card number` and `card number` are one answer, exactly as the adapter's
    /// own `_A` prefix makes them one answer.
    pub fn capture(&self, text: &str) -> Option<(&Form, Vec<(String, String)>)> {
        let said = normalise(text);
        for f in &self.one_of {
            let mut holes = Vec::new();
            if walk(&tokens(&f.say), &said, 0, &mut holes) {
                let filled = holes
                    .into_iter()
                    .map(|(name, value)| (name, strip_article(&value)))
                    .collect();
                return Some((f, filled));
            }
        }
        None
    }

    /// Every form, as an author would type it. Printed under a refusal, because
    /// nobody should be told what is wrong without being told what to write.
    pub fn spellings(&self) -> Vec<String> {
        self.one_of.iter().map(Form::readable).collect()
    }

    /// The forms a document with exactly these powers can carry out.
    ///
    /// One list now serves two kinds — `interceptor.rules` and `redaction.hide`
    /// share it by anchor, because they are two spellings of one act and were
    /// each missing what the other had. They are not equally able: a redaction
    /// hides and does nothing else, so the two sentences that count tool calls
    /// are refused there. Offering the whole list under that refusal would name
    /// the sentence the author just wrote as the repair for writing it.
    pub fn spellings_needing(&self, powers: &[String]) -> Vec<String> {
        self.one_of
            .iter()
            .filter(|f| f.needs.is_empty() || powers.contains(&f.needs))
            .map(Form::readable)
            .collect()
    }
}

/// Would a rule bound at `written` be carried out at `allowed`?
///
/// Prefix matching, the same as the event bus does, so a rule bound at
/// `step.tool` is judged by what it really catches rather than by string
/// equality. Being stricter here than the thing that runs it would refuse a
/// spelling that works, which is worse than the gap being closed.
pub fn reaches(written: &str, allowed: &str) -> bool {
    let written = written.trim();
    if written.is_empty() || written == "*" {
        return true;
    }
    let mine: Vec<&str> = allowed.split('.').collect();
    let theirs: Vec<&str> = written.split('.').collect();
    theirs.len() <= mine.len()
        && theirs.iter().zip(&mine).all(|(t, m)| *t == "*" || t == m)
}

// ────────────────────────────────────────────────────────────── the matcher

#[derive(Debug, PartialEq, Eq)]
enum Tok {
    /// Words that must be there.
    Lit(String),
    /// Words that may be left out — `time[s]`, `go to [the ]stage`.
    Opt(String),
    /// Something the author fills in: its name, and `true` when it must not be
    /// empty — which is every hole but the replacement text: `with ""` means
    /// delete it, and that is a thing an author writes on purpose.
    Hole(String, bool),
}

/// `a card number`, `the card number`, `an email address` → the thing itself.
///
/// The same three words `interceptors._A` strips, so the two sides read one
/// sentence the same way.
fn strip_article(value: &str) -> String {
    let v = value.trim();
    for article in ["a ", "an ", "the "] {
        if let Some(rest) = v.strip_prefix(article) {
            return rest.trim().to_string();
        }
    }
    v.to_string()
}

/// Collapse runs of whitespace and fold case, so a rule written across three
/// lines of a folded scalar is the same sentence as one written on one, and
/// `Replace Anything` is the same as `replace anything`. `to_ascii_lowercase`
/// rather than `to_lowercase` because it cannot change the length of the string
/// and the matcher walks by byte position.
fn normalise(s: &str) -> String {
    s.split_whitespace().collect::<Vec<_>>().join(" ").to_ascii_lowercase()
}

fn tokens(say: &str) -> Vec<Tok> {
    let say = normalise(say);
    let mut out = Vec::new();
    let mut lit = String::new();
    let mut rest = say.as_str();
    while let Some(open) = rest.find(['<', '[']) {
        let opener = rest.as_bytes()[open];
        let closer = if opener == b'<' { '>' } else { ']' };
        let Some(close) = rest[open..].find(closer).map(|i| i + open) else {
            break;
        };
        lit.push_str(&rest[..open]);
        if !lit.is_empty() {
            out.push(Tok::Lit(std::mem::take(&mut lit)));
        }
        if opener == b'<' {
            let inside = &rest[open + 1..close];
            out.push(Tok::Hole(
                inside.trim_end_matches('?').to_string(),
                !inside.ends_with('?'),
            ));
        } else {
            out.push(Tok::Opt(rest[open + 1..close].to_string()));
        }
        rest = &rest[close + 1..];
    }
    lit.push_str(rest);
    if !lit.is_empty() {
        out.push(Tok::Lit(lit));
    }
    out
}

/// Backtracking, because an optional word makes two readings possible and a
/// hole makes as many as there are places the next words could start.
///
/// `holes` collects what the author wrote in each hole, on the reading that
/// succeeds. It is truncated on the way back out of a failed branch, so a
/// half-explored reading never leaves a capture behind.
fn walk(tokens: &[Tok], text: &str, i: usize, holes: &mut Vec<(String, String)>) -> bool {
    let Some((first, rest)) = tokens.split_first() else {
        return i == text.len();
    };
    match first {
        Tok::Lit(s) => text[i..].starts_with(s.as_str()) && walk(rest, text, i + s.len(), holes),
        Tok::Opt(s) => {
            let mark = holes.len();
            if text[i..].starts_with(s.as_str()) && walk(rest, text, i + s.len(), holes) {
                return true;
            }
            holes.truncate(mark);
            walk(rest, text, i, holes)
        }
        // A hole names something, so it is not empty: `replace anything that
        // looks like with "x"` names nothing to replace and is not the sentence.
        // The one exception is marked in the form itself — see `Tok::Hole`.
        Tok::Hole(name, required) => {
            let start = if *required { i + 1 } else { i };
            let mark = holes.len();
            let take = |end: usize, holes: &mut Vec<(String, String)>| {
                holes.truncate(mark);
                holes.push((name.clone(), text[i..end].to_string()));
            };
            match rest.first() {
                // The common shape, and the reason this is not quadratic: the
                // words after the hole say where it can end, so only those
                // places are tried rather than every position in the sentence.
                Some(Tok::Lit(next)) => {
                    let mut from = start;
                    while let Some(found) = text.get(from..).and_then(|t| t.find(next.as_str())) {
                        let at = from + found;
                        take(at, holes);
                        if walk(rest, text, at, holes) {
                            return true;
                        }
                        from = at + 1;
                    }
                    holes.truncate(mark);
                    false
                }
                None => {
                    if i < text.len() || !*required {
                        take(text.len(), holes);
                        true
                    } else {
                        false
                    }
                }
                _ => {
                    for j in (start..=text.len()).filter(|j| text.is_char_boundary(*j)) {
                        take(j, holes);
                        if walk(rest, text, j, holes) {
                            return true;
                        }
                    }
                    holes.truncate(mark);
                    false
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn forms() -> Forms {
        Forms {
            declares: "may".into(),
            binds: "when".into(),
            one_of: vec![
                Form {
                    say: "replace anything that looks like <a thing> with \"<text?>\"".into(),
                    needs: "hide-values".into(),
                    at: vec!["step.message.before".into(), "step.tool.before".into()],
                    continues: false,
                },
                Form {
                    say: "if <a tool> is called more than <n> time[s] in one run, \
                          stop and say \"<why>\""
                        .into(),
                    needs: "stop-the-run".into(),
                    at: vec!["step.tool.before".into()],
                    continues: false,
                },
                Form {
                    say: "if <a tool> is called more than <n> time[s] in one run, \
                          go to [the ]<stage>[ stage] instead"
                        .into(),
                    needs: "send-elsewhere".into(),
                    at: vec!["step.tool.before".into()],
                    continues: false,
                },
            ],
            ..Default::default()
        }
    }

    #[test]
    fn a_sentence_from_the_vocabulary_is_recognised_however_it_is_spaced() {
        let f = forms();
        for said in [
            "replace anything that looks like a card number with \"[removed]\"",
            "Replace anything that looks   like an email address with \"x\"",
            "replace anything that looks like the phone number with \"\"",
        ] {
            assert!(f.recognise(said).is_some(), "{said:?} should be recognised");
        }
    }

    #[test]
    fn a_word_the_author_may_leave_out_is_optional_in_both_directions() {
        let f = forms();
        for said in [
            "if payments is called more than 1 time in one run, go to the re-read stage instead",
            "if payments is called more than 2 times in one run, go to re-read instead",
            "if payments is called more than 1 time in one run, stop and say \"no\"",
        ] {
            assert!(f.recognise(said).is_some(), "{said:?} should be recognised");
        }
    }

    #[test]
    fn the_two_counting_sentences_are_told_apart_by_their_ending() {
        let f = forms();
        let stops = f.recognise("if p is called more than 1 time in one run, stop and say \"x\"");
        let goes = f.recognise("if p is called more than 1 time in one run, go to check instead");
        assert_eq!(stops.map(|x| x.needs.as_str()), Some("stop-the-run"));
        assert_eq!(goes.map(|x| x.needs.as_str()), Some("send-elsewhere"));
    }

    #[test]
    fn free_prose_is_not_a_sentence_this_vocabulary_has() {
        let f = forms();
        for said in [
            "if the customer seems angry, escalate to a manager",
            "be careful about card numbers",
            "replace anything that looks like with \"x\"",
            "replace anything that looks like a card number",
        ] {
            assert!(f.recognise(said).is_none(), "{said:?} should be refused");
        }
    }

    #[test]
    fn a_refusal_offers_the_sentences_the_way_an_author_would_type_them() {
        assert_eq!(
            forms().spellings(),
            vec![
                "replace anything that looks like <a thing> with \"<text>\"",
                "if <a tool> is called more than <n> times in one run, stop and say \"<why>\"",
                "if <a tool> is called more than <n> times in one run, go to the <stage> \
                 stage instead",
            ]
        );
    }

    #[test]
    fn a_binding_is_judged_by_what_it_catches_not_by_how_it_is_spelled() {
        assert!(reaches("step.tool.before", "step.tool.before"));
        assert!(reaches("step.tool", "step.tool.before"));
        assert!(reaches("step", "step.tool.before"));
        assert!(reaches("*", "step.tool.before"));
        assert!(!reaches("turn.message.after", "step.tool.before"));
        assert!(!reaches("step.message", "step.tool.before"));
    }
}
