//! "Did you mean …?" — the difference between a fixable error and a dead end
//! for an author who cannot read a schema (D13).

/// The closest known name to `input`, if one is close enough to be a likely typo.
///
/// The threshold scales with word length: a 4-letter word gets one edit, a
/// 12-letter word gets three. Suggesting `team` for `tools` would be worse than
/// suggesting nothing, so the bar is deliberately conservative.
///
/// Where the edit distance finds nothing, [`shortened`] gets a look — it sees
/// the one shape of near-miss the distance cannot.
pub fn closest<'a>(input: &str, candidates: &[&'a str]) -> Option<&'a str> {
    let budget = match input.chars().count() {
        0..=3 => 1,
        4..=7 => 2,
        _ => 3,
    };
    candidates
        .iter()
        .map(|c| (*c, distance(&input.to_lowercase(), &c.to_lowercase())))
        .filter(|(_, d)| *d <= budget)
        .min_by_key(|(c, d)| (*d, c.len()))
        .map(|(c, _)| c)
        .or_else(|| shortened(input, candidates))
}

/// The one candidate `input` is a shortening of, ignoring separators and case.
///
/// The budget above scales with the length of what was *typed*, so a deliberate
/// abbreviation is invisible to it: `byref` is five characters and
/// `by-reference` is seven edits away, so an author who wrote
/// `auth: { byref: host/zendesk-credential }` was told to remove the line rather
/// than to spell it out. Hyphenated names invite exactly that abbreviation, and
/// shortening is the one near-miss an edit distance is structurally blind to,
/// because every letter left off costs a whole edit.
///
/// Deliberately narrow, for the reason the module opens with — a wrong
/// suggestion is worse than none. Four characters at least; a prefix, not a
/// scattering of the right letters; and silence when two candidates would both
/// fit, because two answers is no answer. It is consulted only where the edit
/// distance already found nothing, so no suggestion this crate makes today can
/// change: this can turn silence into advice and never advice into other advice.
fn shortened<'a>(input: &str, candidates: &[&'a str]) -> Option<&'a str> {
    let typed = plain(input);
    if typed.chars().count() < 4 {
        return None;
    }
    let mut only = None;
    for candidate in candidates {
        if plain(candidate).starts_with(&typed) {
            if only.is_some() {
                return None;
            }
            only = Some(*candidate);
        }
    }
    only
}

/// A name with its punctuation and case taken off, so `by-reference`,
/// `by_reference` and `ByReference` are one word.
fn plain(s: &str) -> String {
    s.chars().filter(|c| c.is_alphanumeric()).flat_map(char::to_lowercase).collect()
}

/// Levenshtein distance, two-row variant.
fn distance(a: &str, b: &str) -> usize {
    let a: Vec<char> = a.chars().collect();
    let b: Vec<char> = b.chars().collect();
    if a.is_empty() {
        return b.len();
    }
    if b.is_empty() {
        return a.len();
    }
    let mut prev: Vec<usize> = (0..=b.len()).collect();
    let mut cur = vec![0usize; b.len() + 1];
    for (i, ca) in a.iter().enumerate() {
        cur[0] = i + 1;
        for (j, cb) in b.iter().enumerate() {
            let cost = usize::from(ca != cb);
            cur[j + 1] = (prev[j + 1] + 1).min(cur[j] + 1).min(prev[j] + cost);
        }
        std::mem::swap(&mut prev, &mut cur);
    }
    prev[b.len()]
}

#[cfg(test)]
mod tests {
    use super::*;

    const FIELDS: &[&str] = &["name", "description", "instructions", "tools", "team", "uses"];

    #[test]
    fn catches_realistic_typos() {
        assert_eq!(closest("descriptoin", FIELDS), Some("description"));
        assert_eq!(closest("Description", FIELDS), Some("description"));
        assert_eq!(closest("instuctions", FIELDS), Some("instructions"));
        assert_eq!(closest("nmae", FIELDS), Some("name"));
    }

    #[test]
    fn stays_quiet_when_nothing_is_close() {
        // A wrong suggestion is worse than none: it sends the author down a
        // path that will not work.
        assert_eq!(closest("orchestration-topology", FIELDS), None);
        assert_eq!(closest("zzzzzz", FIELDS), None);
    }

    #[test]
    fn does_not_confuse_two_genuinely_different_short_fields() {
        // `team` and `uses` are both 4 letters; neither should suggest the other.
        assert_ne!(closest("team", &["uses"]), Some("uses"));
    }

    #[test]
    fn prefers_the_nearest_then_the_shortest() {
        assert_eq!(closest("nam", &["name", "names"]), Some("name"));
    }

    #[test]
    fn an_abbreviation_of_a_hyphenated_name_is_recognised() {
        // `byref` for `by-reference`: seven edits, five characters typed, so the
        // distance budget can never reach it. It is still obvious to a reader.
        assert_eq!(closest("byref", &["by-reference"]), Some("by-reference"));
        assert_eq!(closest("asked", &["asked-of", "answer"]), Some("asked-of"));
    }

    #[test]
    fn an_abbreviation_that_fits_two_names_suggests_neither() {
        // Two answers is no answer: `finish` opens both, so the author is given
        // the list instead of a coin toss.
        assert_eq!(closest("finish", &["finishes-within", "finishes-by"]), None);
    }

    #[test]
    fn a_stub_too_short_to_mean_anything_is_left_alone() {
        // Three characters open too many doors. `des` is `description` and
        // `destination` and `desk`, and guessing between them is the wrong-guess
        // failure this module exists to avoid.
        assert_eq!(closest("des", &["description"]), None);
        assert_eq!(closest("desc", &["description"]), Some("description"));
    }

    #[test]
    fn shortening_never_overrules_a_suggestion_the_distance_already_made() {
        // The guard that lets this be added safely: every suggestion the crate
        // made before still stands, because shortening only ever speaks into
        // silence. `nam` is one edit from `name` and a prefix of `names`, and the
        // edit wins.
        assert_eq!(closest("nam", &["names", "name"]), Some("name"));
    }

    #[test]
    fn distance_is_symmetric_and_zero_on_equality() {
        assert_eq!(distance("abc", "abc"), 0);
        assert_eq!(distance("abc", "abd"), distance("abd", "abc"));
        assert_eq!(distance("", "abc"), 3);
    }
}
