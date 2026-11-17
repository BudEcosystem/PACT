//! **The detector dialect**: which patterns a `detectors:` entry may write
//! under `looks-like:`, so that one document detects the same values on every
//! runtime.
//!
//! A pattern is in the dialect when Python's `re` and the Rust `regex` crate
//! both read it, and it means what Python's `re` makes of it; the TypeScript
//! port (`adapters/typescript/src/detectors.ts`) translates exactly these
//! patterns to JavaScript. The dialect has literals, `.`, `^`, `$`, `\A`,
//! `\Z`, `\b`, `\B`, the classes `\d \D \w \W \s \S` (in their Unicode
//! meaning) and `[...]` with ranges, the escapes `\n \t \r \f \v \a \xHH
//! \uHHHH \UHHHHHHHH` and escaped ASCII punctuation, groups `(...)`,
//! `(?:...)`, `(?P<name>...)`, flag groups `(?i:...)`, `(?m:...)`,
//! `(?s:...)`, alternation, and the quantifiers `* + ? {n} {n,} {n,m}` with
//! their lazy forms.
//!
//! A pattern that can match an empty value is outside it too: it would find
//! something in every text, and Python's `re` and JavaScript step past an
//! empty match differently, so they would not find the same values.
//!
//! Everything else is outside it, and [`outside`] says why: lookaround,
//! back-references, octal escapes, possessive and open-below (`{,m}`)
//! quantifiers, atomic and conditional groups, comments, flags for the whole
//! pattern, flags turned off, nested classes and class set operations, a `{`
//! that is no quantifier, Unicode property escapes, and a range of letters
//! beyond ASCII inside `(?i:...)`. Each of those is either read differently by
//! the two engines or not read by one of them, so a tree that wrote one would
//! hide a value on one runtime and let it through on another.
//!
//! The shared cases are `tests/conformance/detectors.json`.

/// Python's `re` refuses a repetition count from this one up
/// (`sre_constants.MAXREPEAT`).
const PYTHON_MAX_REPEAT: u64 = 4_294_967_295;

/// Why a pattern is outside the dialect, and the character (counted from 0,
/// in Unicode scalar values) where the reader stopped.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Outside {
    /// What the pattern writes and why the dialect does not read it.
    pub reason: String,
    /// The character the reader stopped at.
    pub at: usize,
}

/// Why `pattern` is outside the detector dialect, or `None` when it is in it.
#[must_use]
pub fn outside(pattern: &str) -> Option<Outside> {
    let mut reader = Reader {
        chars: pattern.chars().collect(),
        at: 0,
        names: Vec::new(),
    };
    reader.pattern().err()
}

/// One whole pattern's detectors as `detectors.declared_in` joins them: each
/// non-blank `looks-like:` line in its own `(?:...)`, joined by `|`.
#[must_use]
pub fn joined(lines: &[&str]) -> String {
    lines
        .iter()
        .filter(|line| !line.trim().is_empty())
        .map(|line| format!("(?:{line})"))
        .collect::<Vec<_>>()
        .join("|")
}

/// What one class item is: a character, which may start or end a range, or a
/// class escape such as `\d`, which may not.
#[derive(Clone, Copy)]
enum Item {
    Char(u32),
    Set,
}

/// What one atom is to the atoms around it.
#[derive(Clone, Copy)]
struct Atom {
    /// A quantifier may follow it.
    repeatable: bool,
    /// It can match an empty value.
    empty: bool,
}

impl Atom {
    /// A character or a class: one character, repeatable.
    const CHARACTER: Self = Self { repeatable: true, empty: false };
    /// `^`, `$`, `\b` and the like: no character, and nothing to repeat.
    const ASSERTION: Self = Self { repeatable: false, empty: true };

    /// A group, repeatable, empty when its alternatives can be.
    fn group(empty: bool) -> Self {
        Self { repeatable: true, empty }
    }
}

struct Reader {
    chars: Vec<char>,
    at: usize,
    names: Vec<String>,
}

type Read<T> = Result<T, Outside>;

impl Reader {
    fn refuse<T>(&self, reason: impl Into<String>) -> Read<T> {
        self.refuse_at(reason, self.at)
    }

    fn refuse_at<T>(&self, reason: impl Into<String>, at: usize) -> Read<T> {
        Err(Outside { reason: reason.into(), at })
    }

    fn peek(&self, offset: usize) -> Option<char> {
        self.chars.get(self.at + offset).copied()
    }

    fn starts_with(&self, text: &str) -> bool {
        let mut i = self.at;
        for c in text.chars() {
            if self.chars.get(i) != Some(&c) {
                return false;
            }
            i += 1;
        }
        true
    }

    fn pattern(&mut self) -> Read<()> {
        let empty = self.alternation(false)?;
        if self.at < self.chars.len() {
            return self.refuse("a `)` that closes no group; write `\\)` for the character");
        }
        if empty {
            return self.refuse_at(
                "a pattern that can match an empty value, so it finds something in every text and runtimes disagree on what; make every branch need at least one character",
                0,
            );
        }
        Ok(())
    }

    /// Alternatives; `true` when one of them can match an empty value.
    fn alternation(&mut self, ignore_case: bool) -> Read<bool> {
        let mut empty = self.sequence(ignore_case)?;
        while self.peek(0) == Some('|') {
            self.at += 1;
            empty |= self.sequence(ignore_case)?;
        }
        Ok(empty)
    }

    /// Atoms in a row; `true` when all of them can match an empty value.
    fn sequence(&mut self, ignore_case: bool) -> Read<bool> {
        let mut empty = true;
        loop {
            match self.peek(0) {
                None | Some('|' | ')') => return Ok(empty),
                Some(_) => {}
            }
            let start = self.at;
            let atom = self.atom(ignore_case)?;
            let mut atom_empty = atom.empty;
            if atom.repeatable {
                atom_empty |= self.quantifier()?;
            } else if self.quantifier_ahead()? {
                return self.refuse_at("a quantifier after something that is no character or group", start);
            }
            empty &= atom_empty;
        }
    }

    fn quantifier_ahead(&self) -> Read<bool> {
        Ok(match self.peek(0) {
            Some('*' | '+' | '?') => true,
            Some('{') => self.brace_quantifier()?.is_some(),
            _ => false,
        })
    }

    /// A `{n}`, `{n,}` or `{n,m}` at the cursor: how many characters it takes
    /// and its lower bound, or `None` when the brace is no quantifier.
    fn brace_quantifier(&self) -> Read<Option<(usize, u64)>> {
        let mut i = self.at + 1;
        let digits = |i: &mut usize| {
            let from = *i;
            while self.chars.get(*i).is_some_and(char::is_ascii_digit) {
                *i += 1;
            }
            self.chars[from..*i].iter().collect::<String>()
        };
        let low = digits(&mut i);
        let comma = self.chars.get(i) == Some(&',');
        if comma {
            i += 1;
        }
        let high = digits(&mut i);
        if self.chars.get(i) != Some(&'}') || (low.is_empty() && !comma) {
            return Ok(None);
        }
        let text: String = self.chars[self.at..=i].iter().collect();
        if low.is_empty() {
            return self.refuse(
                "a `{,m}` quantifier with no lower bound, which the Rust regex crate does not read; write `{0,m}`",
            );
        }
        let count = |digits: &str| digits.parse::<u64>().unwrap_or(u64::MAX);
        if !high.is_empty() && count(&high) < count(&low) {
            return self.refuse(format!("a quantifier `{text}` whose upper bound is below its lower bound"));
        }
        if count(&low) >= PYTHON_MAX_REPEAT || (!high.is_empty() && count(&high) >= PYTHON_MAX_REPEAT) {
            return self.refuse(format!(
                "a quantifier `{text}` above the largest repetition count Python's re reads"
            ));
        }
        Ok(Some((i + 1 - self.at, count(&low))))
    }

    /// The quantifier at the cursor, if any; `true` when it allows no repeat.
    fn quantifier(&mut self) -> Read<bool> {
        let none = match self.peek(0) {
            Some(c @ ('*' | '+' | '?')) => {
                self.at += 1;
                c != '+'
            }
            Some('{') => match self.brace_quantifier()? {
                Some((taken, low)) => {
                    self.at += taken;
                    low == 0
                }
                None => return Ok(false),
            },
            _ => return Ok(false),
        };
        if self.peek(0) == Some('?') {
            self.at += 1;
        } else if self.peek(0) == Some('+') {
            return self.refuse("a possessive quantifier, which the Rust regex crate does not read");
        }
        if self.quantifier_ahead()? {
            return self.refuse("two quantifiers in a row; put the first in a group `(?:...)`");
        }
        Ok(none)
    }

    /// One atom: whether a quantifier may follow it, and whether it can match
    /// an empty value.
    fn atom(&mut self, ignore_case: bool) -> Read<Atom> {
        let Some(c) = self.peek(0) else {
            return Ok(Atom::ASSERTION);
        };
        match c {
            '(' => self.group(ignore_case),
            '[' => self.class(ignore_case).map(|()| Atom::CHARACTER),
            '*' | '+' | '?' => self.refuse("a quantifier with nothing before it to repeat"),
            '{' => {
                if self.brace_quantifier()?.is_some() {
                    return self.refuse("a quantifier with nothing before it to repeat");
                }
                self.refuse("a `{` that is no quantifier; write `\\{` for the character")
            }
            '^' | '$' => {
                self.at += 1;
                Ok(Atom::ASSERTION)
            }
            '\\' => {
                self.at += 1;
                self.escape()
            }
            _ => {
                self.at += 1;
                Ok(Atom::CHARACTER)
            }
        }
    }

    fn group(&mut self, ignore_case: bool) -> Read<Atom> {
        let start = self.at;
        if self.starts_with("(?P<") {
            self.at += 4;
            let from = self.at;
            if !self.peek(0).is_some_and(|c| c.is_ascii_alphabetic() || c == '_') {
                return self.refuse_at(
                    "a group name that is not a letter or `_` followed by letters, digits or `_`",
                    start,
                );
            }
            while self.peek(0).is_some_and(|c| c.is_ascii_alphanumeric() || c == '_') {
                self.at += 1;
            }
            if self.peek(0) != Some('>') {
                return self.refuse_at(
                    "a group name that is not a letter or `_` followed by letters, digits or `_`",
                    start,
                );
            }
            let name: String = self.chars[from..self.at].iter().collect();
            if self.names.contains(&name) {
                return self.refuse_at(format!("the group name `{name}` written twice"), start);
            }
            self.names.push(name);
            self.at += 1;
            return self.closed(ignore_case, start).map(Atom::group);
        }
        for opener in ["(?=", "(?!", "(?<=", "(?<!"] {
            if self.starts_with(opener) {
                return self.refuse(format!(
                    "a lookaround `{opener}...)`, which the Rust regex crate does not read"
                ));
            }
        }
        if self.starts_with("(?P=") || self.starts_with("(?P>") {
            return self.refuse("a back-reference to a named group, which the Rust regex crate does not read");
        }
        if self.starts_with("(?#") {
            return self.refuse("a comment group, which the Rust regex crate does not read");
        }
        if self.starts_with("(?>") {
            return self.refuse("an atomic group, which the Rust regex crate does not read");
        }
        if self.starts_with("(?(") {
            return self.refuse("a conditional group, which neither the Rust regex crate nor the PACT dialect reads");
        }
        if self.starts_with("(?<") {
            return self.refuse(
                "a named group written `(?<name>...)`, which Python's re refuses; write `(?P<name>...)`",
            );
        }
        if self.starts_with("(?:") {
            self.at += 3;
            return self.closed(ignore_case, start).map(Atom::group);
        }
        if self.starts_with("(?") {
            let mut i = self.at + 2;
            while self.chars.get(i).is_some_and(|c| c.is_ascii_alphabetic() || *c == '-') {
                i += 1;
            }
            let end = self.chars.get(i).copied();
            if !matches!(end, Some(':' | ')')) {
                return self.refuse("a `(?` that opens no group the dialect reads");
            }
            let letters: String = self.chars[self.at + 2..i].iter().collect();
            if end == Some(')') {
                return self.refuse(
                    "a flag for the whole pattern, which the reference adapter cannot read inside a detector; write `(?i:...)` around the part it applies to",
                );
            }
            if letters.contains('-') {
                return self.refuse("a group that turns a flag off, which the PACT dialect does not read");
            }
            if let Some(other) = letters.chars().find(|c| !matches!(c, 'i' | 'm' | 's')) {
                return self.refuse(format!(
                    "the flag `{other}`, which the PACT dialect does not read; it reads `i`, `m` and `s`"
                ));
            }
            self.at = i + 1;
            return self.closed(ignore_case || letters.contains('i'), start).map(Atom::group);
        }
        self.at += 1;
        self.closed(ignore_case, start).map(Atom::group)
    }

    /// A group's alternatives and its `)`; `true` when it can match an empty value.
    fn closed(&mut self, ignore_case: bool, start: usize) -> Read<bool> {
        let empty = self.alternation(ignore_case)?;
        if self.peek(0) != Some(')') {
            return self.refuse_at("a group that is never closed", start);
        }
        self.at += 1;
        Ok(empty)
    }

    /// The character a character escape names, past the `\`; `None` when the
    /// escape names no character.
    fn escaped_char(&mut self, letter: char) -> Read<Option<u32>> {
        if let Some(code) = match letter {
            'n' => Some(0x0a),
            't' => Some(0x09),
            'r' => Some(0x0d),
            'f' => Some(0x0c),
            'v' => Some(0x0b),
            'a' => Some(0x07),
            _ => None,
        } {
            self.at += 1;
            return Ok(Some(code));
        }
        let digits = match letter {
            'x' => 2,
            'u' => 4,
            'U' => 8,
            _ => 0,
        };
        if digits > 0 {
            let hex: String = self.chars.iter().skip(self.at + 1).take(digits).collect();
            if hex.chars().count() != digits || !hex.chars().all(|c| c.is_ascii_hexdigit()) {
                return self.refuse(format!("`\\{letter}` followed by other than {digits} hexadecimal digits"));
            }
            let code = u32::from_str_radix(&hex, 16).unwrap_or(u32::MAX);
            if code > 0x0010_ffff {
                return self.refuse(format!("`\\{letter}{hex}`, which is no character"));
            }
            self.at += 1 + digits;
            return Ok(Some(code));
        }
        if letter.is_ascii_punctuation() {
            self.at += 1;
            return Ok(Some(u32::from(letter)));
        }
        Ok(None)
    }

    fn refuse_escape<T>(&self, letter: Option<char>) -> Read<T> {
        match letter {
            None => self.refuse("a `\\` that ends the pattern"),
            Some(d) if d.is_ascii_digit() => self.refuse(format!(
                "`\\{d}`, a back-reference or an octal escape, which the Rust regex crate does not read"
            )),
            Some(other) => self.refuse(format!(
                "the escape `\\{other}`, which Python's re and the Rust regex crate do not read alike"
            )),
        }
    }

    /// An escape outside a class, past the `\`.
    fn escape(&mut self) -> Read<Atom> {
        let letter = self.peek(0);
        match letter {
            Some('b' | 'B' | 'A' | 'Z') => {
                self.at += 1;
                Ok(Atom::ASSERTION)
            }
            Some('d' | 'D' | 'w' | 'W' | 's' | 'S') => {
                self.at += 1;
                Ok(Atom::CHARACTER)
            }
            Some(l) => match self.escaped_char(l)? {
                Some(_) => Ok(Atom::CHARACTER),
                None => self.refuse_escape(letter),
            },
            None => self.refuse_escape(None),
        }
    }

    fn class_item(&mut self) -> Read<Item> {
        let Some(c) = self.peek(0) else {
            return self.refuse("a class `[` that is never closed");
        };
        if c == '[' {
            return self.refuse(
                "a `[` inside a class, which the Rust regex crate reads as a nested class; write `\\[`",
            );
        }
        if c == '\\' {
            self.at += 1;
            let letter = self.peek(0);
            if matches!(letter, Some('d' | 'D' | 'w' | 'W' | 's' | 'S')) {
                self.at += 1;
                return Ok(Item::Set);
            }
            if letter == Some('b') {
                return self.refuse(
                    "`\\b` inside a class, which Python reads as a backspace and the Rust regex crate refuses",
                );
            }
            return match letter {
                Some(l) => match self.escaped_char(l)? {
                    Some(code) => Ok(Item::Char(code)),
                    None => self.refuse_escape(letter),
                },
                None => self.refuse_escape(None),
            };
        }
        for operation in ["&&", "--", "~~"] {
            if self.starts_with(operation) {
                return self.refuse(format!(
                    "`{operation}` inside a class, which the Rust regex crate reads as a set operation; escape one of the two"
                ));
            }
        }
        self.at += 1;
        Ok(Item::Char(u32::from(c)))
    }

    fn class(&mut self, ignore_case: bool) -> Read<()> {
        let start = self.at;
        self.at += 1;
        if self.peek(0) == Some('^') {
            self.at += 1;
        }
        let mut first = true;
        loop {
            let Some(c) = self.peek(0) else {
                return self.refuse_at("a class `[` that is never closed", start);
            };
            if c == ']' && !first {
                break;
            }
            first = false;
            if c == ']' {
                self.at += 1;
                continue;
            }
            let item = self.class_item()?;
            if self.starts_with("--") {
                return self.refuse(
                    "`--` inside a class, which the Rust regex crate reads as a set operation; escape one of the two",
                );
            }
            let dash = self.peek(0) == Some('-') && !matches!(self.peek(1), Some(']') | None);
            if !dash {
                continue;
            }
            let dash_at = self.at;
            self.at += 1;
            let end = self.class_item()?;
            let (Item::Char(from), Item::Char(to)) = (item, end) else {
                return self.refuse_at("a range whose end is a class such as `\\d`", dash_at);
            };
            if to < from {
                return self.refuse_at("a range whose end comes before its start", dash_at);
            }
            if ignore_case && to > 0x7f {
                return self.refuse(
                    "a range of letters beyond ASCII inside `(?i:...)`, which the PACT dialect does not read; list the letters",
                );
            }
        }
        self.at += 1;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_shipped_example_pattern_is_in_the_dialect() {
        assert_eq!(outside("ORD-[0-9]{8}"), None);
        assert_eq!(outside(&joined(&["ORD-[0-9]{8}", "  ", "R-\\d+"])), None);
    }

    #[test]
    fn a_lookbehind_is_refused_where_it_starts() {
        let refused = outside("ab(?<=x)y").expect("outside");
        assert_eq!(refused.at, 2);
        assert!(refused.reason.contains("lookaround"), "{}", refused.reason);
    }

    #[test]
    fn a_pattern_that_can_match_nothing_is_refused() {
        for empty in ["x*?", "a?", "(?:ab)*|c", "^$", "\\b", "(?:a|)", "a{0,3}"] {
            let refused = outside(empty).unwrap_or_else(|| panic!("{empty} is outside"));
            assert!(refused.reason.contains("empty value"), "{empty}: {}", refused.reason);
        }
        for some in ["a*b", "\\bfoo\\b", "(?:a|b)+", "x{1,}?", "^line"] {
            assert_eq!(outside(some), None, "{some}");
        }
    }

    #[test]
    fn a_position_counts_characters_not_bytes() {
        assert_eq!(outside("é(?=x)").expect("outside").at, 1);
    }
}
