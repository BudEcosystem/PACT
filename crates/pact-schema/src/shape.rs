//! **One line of an answer's shape, read** (02W §2.15).
//!
//! `&the-answer-shapes` in `spec/schema.yaml` is the closed vocabulary — the
//! nine shipped shapes and `date`, `time`, `date-and-time` — and three ways to
//! build on any of them, which are grammar rather than vocabulary, so they live
//! here and in `questions.Shape.parse`, the one Python reader, and nowhere else:
//!
//! | Written | Means |
//! |---|---|
//! | `list of <shape>` | a list, each item in that shape (`lines: list of invoice-line`) |
//! | `<named shape>` | a key of `workspace.shapes`, a shape with parts |
//! | `<shape>, optional` | may be missing; only such an input may be filled from a stage that may not have run (WF-5) |
//!
//! `one of a, b, c` is the shipped fourth: a choice between things the author
//! names. A spelling the vocabulary already holds wins over the grammar, so
//! `list of images` stays the shipped `images` it has always meant.
//!
//! The schema's `schema/not-an-answer-shape` reads every line through [`parse`],
//! and `pact-loader`'s `bindings.rs` reads the same lines to hold a call's
//! `bind:` to what its target takes (WF-39) and an input to its `, optional`
//! (WF-5). One reader, so the checker and the binding rules cannot disagree
//! about what a line says.

/// What a line says, without its `, optional`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Shape {
    /// One of the vocabulary's shapes, by its own name — `text`, `date-and-time`.
    Plain(String),
    /// `one of a, b, c`: the choices as written, in order.
    OneOf(Vec<String>),
    /// `list of <shape>`.
    ListOf(Box<Shape>),
    /// A key of `workspace.shapes`, as written there.
    Named(String),
}

/// One whole line: its shape, and whether it may be missing.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Line {
    pub shape: Shape,
    pub optional: bool,
}

/// A named shape's parts, each read: what [`Shape::fits`] asks of a name.
pub type Parts<'a> = dyn Fn(&str) -> Option<Vec<(String, Line)>> + 'a;

/// Why a line could not be read: the words to put after the quoted line.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Unread {
    /// `one of` with nothing after it.
    NoChoices,
    /// The part that is no shape (all of it, or what follows `list of`).
    NotAShape(String),
}

/// The words of a line as the vocabulary compares them: lower case, one space
/// between words.
pub fn normalised(written: &str) -> String {
    written
        .trim()
        .to_ascii_lowercase()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

/// Read one line against `vocabulary` (the `shapes:` of an `answer-shape`
/// field) and the names of `workspace.shapes`.
pub fn parse(
    written: &str,
    vocabulary: &[(String, Vec<String>)],
    named: &[&str],
) -> Result<Line, Unread> {
    let s = normalised(written);
    let (s, optional) = match s.strip_suffix("optional") {
        Some(rest) if rest.trim_end().ends_with(',') => (
            rest.trim_end().trim_end_matches(',').trim_end().to_string(),
            true,
        ),
        _ => (s, false),
    };
    Ok(Line {
        shape: shape(&s, vocabulary, named)?,
        optional,
    })
}

fn shape(s: &str, vocabulary: &[(String, Vec<String>)], named: &[&str]) -> Result<Shape, Unread> {
    for prefix in ["one of ", "one-of ", "either "] {
        if let Some(rest) = s
            .strip_prefix(prefix)
            .or_else(|| (s == prefix.trim_end()).then_some(""))
        {
            let choices: Vec<String> = rest
                .replace(" or ", ", ")
                .split(',')
                .map(|c| c.trim().to_string())
                .filter(|c| !c.is_empty())
                .collect();
            if choices.is_empty() {
                return Err(Unread::NoChoices);
            }
            return Ok(Shape::OneOf(choices));
        }
    }
    if let Some((name, _)) = vocabulary
        .iter()
        .find(|(_, words)| words.iter().any(|w| normalised(w) == s))
    {
        return Ok(Shape::Plain(name.clone()));
    }
    if let Some(name) = named.iter().find(|n| normalised(n) == s) {
        return Ok(Shape::Named((*name).to_string()));
    }
    if let Some(rest) = s.strip_prefix("list of ") {
        return Ok(Shape::ListOf(Box::new(shape(
            rest.trim(),
            vocabulary,
            named,
        )?)));
    }
    Err(Unread::NotAShape(s.to_string()))
}

impl Shape {
    /// The spelling that reads back as this shape.
    pub fn written(&self) -> String {
        match self {
            Shape::Plain(name) | Shape::Named(name) => name.clone(),
            Shape::OneOf(choices) => format!("one of {}", choices.join(", ")),
            Shape::ListOf(inner) => format!("list of {}", inner.written()),
        }
    }

    /// Whether a value in `self` can fill an input in `wanted` with no step in
    /// between: the same shape, or one of the safe widenings (A §3 stage 3's
    /// auto-map rung) — anything that is one value into `text`, a whole number
    /// into `number`, fewer choices into more, a list item by item, and a
    /// named shape into another whose every required part it has, in a shape
    /// that fits. `parts` gives a named shape's parts.
    pub fn fits(&self, wanted: &Shape, parts: &Parts) -> bool {
        self.fits_within(wanted, parts, 0)
    }

    fn fits_within(&self, wanted: &Shape, parts: &Parts, depth: usize) -> bool {
        // Named shapes may name each other; a circle is refused where the
        // shapes are declared, and this only stops a walk from following one.
        if depth > 16 || self == wanted {
            return true;
        }
        match (self, wanted) {
            (Shape::ListOf(_) | Shape::Named(_), Shape::Plain(w)) if w == "text" => false,
            (_, Shape::Plain(w)) if w == "text" => true,
            (Shape::Plain(h), Shape::Plain(w)) => h == "whole-number" && w == "number",
            (Shape::OneOf(have), Shape::OneOf(want)) => have
                .iter()
                .all(|h| want.iter().any(|w| w.eq_ignore_ascii_case(h))),
            (Shape::ListOf(have), Shape::ListOf(want)) => have.fits_within(want, parts, depth + 1),
            (Shape::Named(have), Shape::Named(want)) => {
                let (Some(have), Some(want)) = (parts(have), parts(want)) else {
                    return true;
                };
                want.iter().all(
                    |(field, line)| match have.iter().find(|(f, _)| f == field) {
                        Some((_, h)) => h.shape.fits_within(&line.shape, parts, depth + 1),
                        None => line.optional,
                    },
                )
            }
            _ => false,
        }
    }
}

/// The answer-shape vocabulary the specification declares: the `shapes:` of
/// its first `answer-shape` field. Every such field reads the one copy
/// (`&the-answer-shapes`), so the first is all of them.
pub fn vocabulary(schema: &crate::Schema) -> Vec<(String, Vec<String>)> {
    fn find(ty: &crate::Ty) -> Option<&Vec<(String, Vec<String>)>> {
        match ty {
            crate::Ty::AnswerShape(shapes) => Some(shapes),
            crate::Ty::MapOf(inner) | crate::Ty::ListOf(inner) => find(inner),
            _ => None,
        }
    }
    schema
        .groups()
        .flat_map(|g| g.fields.iter())
        .find_map(|f| find(&f.ty))
        .cloned()
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn vocab() -> Vec<(String, Vec<String>)> {
        [
            ("text", &["text", "some text"][..]),
            ("yes-or-no", &["yes-or-no", "yes or no"]),
            ("number", &["number"]),
            ("whole-number", &["whole-number", "whole number"]),
            ("images", &["images", "list of images"]),
            ("date", &["date", "a date"]),
            ("date-and-time", &["date-and-time", "date and time"]),
        ]
        .into_iter()
        .map(|(n, w)| (n.to_string(), w.iter().map(|s| s.to_string()).collect()))
        .collect()
    }

    fn line(s: &str) -> Result<Line, Unread> {
        parse(s, &vocab(), &["invoice-line"])
    }

    #[test]
    fn each_way_to_build_on_a_shape_reads_as_itself() {
        assert_eq!(line("A Date").unwrap().shape, Shape::Plain("date".into()));
        assert_eq!(
            line("date and time").unwrap().shape,
            Shape::Plain("date-and-time".into())
        );
        assert_eq!(
            line("list of invoice-line").unwrap().shape,
            Shape::ListOf(Box::new(Shape::Named("invoice-line".into())))
        );
        let optional = line("text, optional").unwrap();
        assert!(optional.optional);
        assert_eq!(optional.shape, Shape::Plain("text".into()));
        assert!(line("list of whole number ,  optional").unwrap().optional);
        assert_eq!(
            line("list of one of a, b").unwrap().shape,
            Shape::ListOf(Box::new(Shape::OneOf(vec!["a".into(), "b".into()])))
        );
    }

    #[test]
    fn a_spelling_the_vocabulary_holds_wins_over_the_grammar() {
        assert_eq!(
            line("list of images").unwrap().shape,
            Shape::Plain("images".into())
        );
    }

    #[test]
    fn what_is_no_shape_is_named() {
        assert_eq!(
            line("list of invoice-lines"),
            Err(Unread::NotAShape("invoice-lines".into()))
        );
        assert_eq!(line("one of"), Err(Unread::NoChoices));
        assert_eq!(line("optional"), Err(Unread::NotAShape("optional".into())));
    }

    #[test]
    fn a_value_fits_its_own_shape_and_the_safe_widenings_only() {
        let none = |_: &str| None;
        let p = |s: &str| Shape::Plain(s.into());
        assert!(p("whole-number").fits(&p("number"), &none));
        assert!(p("date").fits(&p("text"), &none));
        assert!(!p("number").fits(&p("whole-number"), &none));
        assert!(!p("date").fits(&p("number"), &none));
        let one_of = |c: &[&str]| Shape::OneOf(c.iter().map(|s| s.to_string()).collect());
        assert!(one_of(&["a"]).fits(&one_of(&["a", "b"]), &none));
        assert!(!one_of(&["a", "c"]).fits(&one_of(&["a", "b"]), &none));
        let list = |s: Shape| Shape::ListOf(Box::new(s));
        assert!(list(p("whole-number")).fits(&list(p("number")), &none));
        assert!(!list(p("text")).fits(&p("text"), &none));
    }

    #[test]
    fn a_named_shape_fits_another_that_wants_only_what_it_has() {
        let parts = |name: &str| -> Option<Vec<(String, Line)>> {
            let l = |s: &str, optional| Line {
                shape: Shape::Plain(s.into()),
                optional,
            };
            match name {
                "line" => Some(vec![
                    ("sku".into(), l("text", false)),
                    ("qty".into(), l("whole-number", false)),
                ]),
                "row" => Some(vec![
                    ("sku".into(), l("text", false)),
                    ("note".into(), l("text", true)),
                ]),
                "wide" => Some(vec![
                    ("sku".into(), l("text", false)),
                    ("price".into(), l("number", false)),
                ]),
                _ => None,
            }
        };
        let n = |s: &str| Shape::Named(s.into());
        assert!(n("line").fits(&n("row"), &parts));
        assert!(!n("line").fits(&n("wide"), &parts));
    }
}
