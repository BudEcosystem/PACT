//! **`every:` is held to the grammar a clock can keep, where the author is.**
//!
//! `port.every:` is *"plain words like `weekday mornings at 9`, or a cron line
//! if you know them"*, and the words are read by a closed table
//! (`adapters/python/src/pact_adapters/schedules.py`). That table lived only in
//! Python, so it was applied when a runtime started and never when the line was
//! written: `every: every fortnight` and `every: 0 0 30 2 *` (the 30th of
//! February) both printed `OK — loaded cleanly` under `--deny-warnings` and then
//! failed the server that was supposed to keep the timer.
//!
//! This is the same table, in the same order, so `pact check` refuses exactly
//! the lines a runtime would. Two readers of one grammar drift, so neither is
//! trusted to agree with the other: `tests/conformance/schedules.json` lists
//! what an author may write beside the one line a clock keeps, and what neither
//! may read, and both sides test every row of it.
//!
//! # What a line becomes
//!
//! `@every <n>s` for an interval, or six cron fields with seconds first. The
//! loader does not need the line, only the verdict, but [`read`] returns it so
//! the conformance list can hold the two readers to the same READING and not
//! merely to the same yes or no — `nights at 2` accepted as two in the
//! afternoon by one side would pass a yes-or-no comparison.
//!
//! # A time is never guessed
//!
//! An hour says which half of the day it is in (`4pm`, `16:30`, `mornings at
//! 9`, `noon`) or the line is refused. A part of the day means the hours people
//! mean by it ([`half_of`]): the small hours are the night's, and its twelve is
//! midnight.

use pact_diag::{Diagnostic, Diagnostics};
use pact_doc::{Node, Value};

/// The forms that work, quoted in every refusal (`schedules.FORMS`).
const FORMS: &str = "plain words like `Friday at 4pm`, `weekday mornings at 9`, \
                     `every 10 minutes` or `daily`, or a cron line such as `0 16 * * 5`";

/// Why a line was refused.
#[derive(Debug, PartialEq, Eq)]
pub enum Unreadable {
    /// Nothing in the table reads it.
    NotATime,
    /// It is nearly a time, and this sentence says what is wrong with it.
    Because(String),
    /// A cron line naming a day no month has.
    NeverComes,
}

/// Cron fields, seconds first: what each is called, and its lowest and highest.
const FIELDS: [(&str, u32, u32); 6] = [
    ("second", 0, 59),
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day of the month", 1, 31),
    ("month", 1, 12),
    ("day of the week", 0, 7),
];

const DAYS: [(&str, u32); 17] = [
    ("sun", 0),
    ("sunday", 0),
    ("mon", 1),
    ("monday", 1),
    ("tue", 2),
    ("tues", 2),
    ("tuesday", 2),
    ("wed", 3),
    ("wednesday", 3),
    ("thu", 4),
    ("thur", 4),
    ("thurs", 4),
    ("thursday", 4),
    ("fri", 5),
    ("friday", 5),
    ("sat", 6),
    ("saturday", 6),
];

const MONTHS: [&str; 12] = [
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
];

/// The words that are a whole schedule by themselves.
const NAMED: [(&str, &str); 8] = [
    ("hourly", "0 0 * * * *"),
    ("daily", "0 0 0 * * *"),
    ("every day", "0 0 0 * * *"),
    ("weekly", "0 0 0 * * 1"),
    ("monthly", "0 0 0 1 * *"),
    ("every hour", "@every 3600s"),
    ("every minute", "@every 60s"),
    ("every second", "@every 1s"),
];

const UNITS: [(&str, u64); 4] = [
    ("second", 1),
    ("minute", 60),
    ("hour", 3600),
    ("day", 86400),
];

/// One `every:` line as the one form a clock keeps, or why it is not one.
pub fn read(written: &str) -> Result<String, Unreadable> {
    let text = written
        .to_lowercase()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ");
    if text.is_empty() {
        return Err(Unreadable::NotATime);
    }
    if let Some((_, line)) = NAMED.iter().find(|(word, _)| *word == text) {
        return Ok((*line).to_string());
    }
    if let Some(seconds) = interval(&text) {
        // An interval is counted from 1970, so its first firing is at least one
        // whole interval after it: longer than the last date a clock can name
        // (the end of the year 9999) and it never fires.
        const LAST_SECOND_A_CLOCK_NAMES: u64 = 253_402_300_799;
        return if seconds <= LAST_SECOND_A_CLOCK_NAMES {
            Ok(format!("@every {seconds}s"))
        } else {
            Err(Unreadable::NeverComes)
        };
    }
    let line = match cron(&text)? {
        Some(line) => line,
        None => calendar(&text)?.ok_or(Unreadable::NotATime)?,
    };
    if comes_round(&line) {
        Ok(line)
    } else {
        Err(Unreadable::NeverComes)
    }
}

/// `every <n> <unit>[s]`, in seconds.
fn interval(text: &str) -> Option<u64> {
    let mut words = text.split(' ');
    let (every, count, unit) = (words.next()?, words.next()?, words.next()?);
    if every != "every" || words.next().is_some() {
        return None;
    }
    let unit = unit.strip_suffix('s').unwrap_or(unit);
    let seconds = UNITS.iter().find(|(name, _)| *name == unit)?.1;
    if count.is_empty() || !count.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    // More digits than a number holds is still an interval, and one no clock
    // can keep: the caller refuses it as never coming round.
    let n = count
        .parse::<u64>()
        .ok()
        .and_then(|n| n.checked_mul(seconds))
        .unwrap_or(u64::MAX);
    (n > 0).then_some(n)
}

/// Digits and nothing else, as a cron field or a clock's hour writes them.
fn whole(text: &str) -> Option<u32> {
    if text.is_empty() || !text.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    text.parse().ok()
}

/// A cron line of five or six fields, seconds put first. `Ok(None)` when the
/// text is not a cron line at all, so the words are tried next.
fn cron(text: &str) -> Result<Option<String>, Unreadable> {
    let mut fields: Vec<&str> = text.split(' ').collect();
    let in_cron = |f: &&str| {
        !f.is_empty()
            && f.bytes().all(|b| {
                b.is_ascii_lowercase()
                    || b.is_ascii_digit()
                    || matches!(b, b'*' | b'/' | b',' | b'-')
            })
    };
    if !matches!(fields.len(), 5 | 6) || !fields.iter().all(in_cron) {
        return Ok(None);
    }
    if fields.len() == 5 {
        fields.insert(0, "0");
    }
    for (field, at) in fields.iter().zip(0..) {
        match values(field, at) {
            Ok(Some(_)) => {}
            Ok(None) => return Ok(None),
            Err(why) => return Err(why),
        }
    }
    Ok(Some(fields.join(" ")))
}

/// What one cron field names, as a bit per value. `Ok(None)` when it is not a
/// cron field (a word, a step of nothing).
fn values(field: &str, at: usize) -> Result<Option<u64>, Unreadable> {
    let (name, low, high) = FIELDS[at];
    let named = |word: &str| -> Option<u32> {
        match at {
            4 => MONTHS
                .iter()
                .zip(1..)
                .find(|(m, _)| **m == word)
                .map(|(_, i)| i),
            5 => DAYS.iter().find(|(d, _)| *d == word).map(|(_, i)| *i),
            _ => None,
        }
    };
    let number = |word: &str| named(word).or_else(|| whole(word));
    let mut out = 0u64;
    for item in field.split(',') {
        let (body, step_text) = match item.split_once('/') {
            Some((body, step)) => (body, Some(step)),
            None => (item, None),
        };
        let step = match step_text {
            // `partition` in the other reader: an empty step is no step.
            Some("") | None => 1,
            Some(step) => match whole(step) {
                Some(step) if step >= 1 => step,
                _ => return Ok(None),
            },
        };
        let stepped = step_text.is_some_and(|s| !s.is_empty());
        let (lo, hi) = if body == "*" {
            (low, high)
        } else {
            let (first, last) = body.split_once('-').unwrap_or((body, ""));
            let Some(lo) = number(first) else {
                return Ok(None);
            };
            let hi = if last.is_empty() {
                if stepped { high } else { lo }
            } else {
                let Some(hi) = number(last) else {
                    return Ok(None);
                };
                hi
            };
            (lo, hi)
        };
        if !(low <= lo && lo <= hi && hi <= high) {
            return Err(Unreadable::Because(format!(
                "`{field}` is outside {low}-{high}, the {name}s a cron line can name."
            )));
        }
        let mut value = lo;
        while value <= hi {
            out |= 1 << value;
            value += step;
        }
    }
    Ok(Some(out))
}

/// `<days> [<part of day>] at <time>`, or `<days>` alone (at midnight).
fn calendar(text: &str) -> Result<Option<String>, Unreadable> {
    let text = text
        .strip_prefix("on ")
        .or_else(|| text.strip_prefix("every "))
        .unwrap_or(text);
    let (days_part, time_part) = text.split_once(" at ").unwrap_or((text, ""));
    let spaced = days_part.replace(',', " ");
    let mut words: Vec<&str> = spaced.split_whitespace().collect();
    let part = words
        .last()
        .map(|w| w.trim_end_matches('s'))
        .filter(|w| PARTS.contains(w))
        .map(str::to_string);
    if part.is_some() {
        words.pop();
    }
    let Some(days) = days(&words) else {
        return Ok(None);
    };
    if time_part.is_empty() {
        // `weekday mornings` names no hour, and midnight is not a morning.
        return Ok(part.is_none().then(|| format!("0 0 0 * * {days}")));
    }
    Ok(time(time_part, part.as_deref())?
        .map(|(hour, minute)| format!("0 {minute} {hour} * * {days}")))
}

fn days(words: &[&str]) -> Option<String> {
    match words {
        [] | ["day"] | ["days"] | ["daily"] => return Some("*".to_string()),
        ["weekday"] | ["weekdays"] => return Some("1-5".to_string()),
        ["weekend"] | ["weekends"] => return Some("0,6".to_string()),
        _ => {}
    }
    let day = |word: &str| DAYS.iter().find(|(d, _)| *d == word).map(|(_, i)| *i);
    let mut named = Vec::new();
    for word in words.iter().filter(|w| **w != "and") {
        named.push(day(word).or_else(|| day(word.trim_end_matches('s')))?);
    }
    named.sort_unstable();
    named.dedup();
    (!named.is_empty()).then(|| {
        named
            .iter()
            .map(u32::to_string)
            .collect::<Vec<_>>()
            .join(",")
    })
}

/// The parts of a day a line may name.
const PARTS: [&str; 4] = ["morning", "afternoon", "evening", "night"];

/// Which half of the day `hour` is in when `part` is written beside it, or
/// `None` when that part of the day has no such hour.
fn half_of(part: &str, hour: u32) -> Option<&'static str> {
    match (part, hour) {
        ("morning", 1..=11) => Some("am"),
        ("afternoon", 12 | 1..=6) => Some("pm"),
        ("evening", 4..=11) => Some("pm"),
        // The small hours are the night's, and its twelve is midnight.
        ("night", 6..=11) => Some("pm"),
        ("night", 12 | 1..=5) => Some("am"),
        _ => None,
    }
}

/// The hour and minute `text` names. `Ok(None)` when it is not a time at all;
/// an error when it could be either half of the day, or is an hour the part of
/// the day written beside it does not hold.
fn time(text: &str, part: Option<&str>) -> Result<Option<(u32, u32)>, Unreadable> {
    let text = text.trim();
    match text {
        "noon" | "midday" => return Ok(Some((12, 0))),
        "midnight" => return Ok(Some((0, 0))),
        _ => {}
    }
    let (clock, written_half) = match text.strip_suffix("am").map(|c| (c, "am")) {
        Some(found) => found,
        None => text.strip_suffix("pm").map_or((text, ""), |c| (c, "pm")),
    };
    let clock = clock.trim_end();
    let (hour_text, minute_text) = match clock.split_once(':') {
        Some((h, m)) => (h, Some(m)),
        None => (clock, None),
    };
    if !matches!(hour_text.len(), 1 | 2) || minute_text.is_some_and(|m| m.len() != 2) {
        return Ok(None);
    }
    let (Some(mut hour), Some(minute)) = (whole(hour_text), minute_text.map_or(Some(0), whole))
    else {
        return Ok(None);
    };
    let mut half = written_half;
    if let Some(part) = part {
        match half_of(part, hour) {
            Some(found) if half.is_empty() || half == found => half = found,
            _ => {
                return Err(Unreadable::Because(format!(
                    "`{text}` is not an hour of the {part}."
                )));
            }
        }
    }
    if !half.is_empty() {
        if !(1..=12).contains(&hour) {
            return Ok(None);
        }
        hour = hour % 12 + if half == "pm" { 12 } else { 0 };
    } else if minute_text.is_none() && (1..=12).contains(&hour) {
        return Err(Unreadable::Because(format!(
            "`at {hour}` could be {hour}am or {hour}pm: say which, or write the \
             24-hour time (`{hour:02}:00`)."
        )));
    }
    Ok((hour <= 23 && minute <= 59).then_some((hour, minute)))
}

/// Whether a calendar line names a day that exists. Only a day of the month
/// with the day of the week left free can name none: `0 0 30 2 *`.
fn comes_round(line: &str) -> bool {
    let fields: Vec<&str> = line.split(' ').collect();
    if fields.len() != 6 || fields[3] == "*" || fields[5] != "*" {
        return true;
    }
    let (Ok(Some(days)), Ok(Some(months))) = (values(fields[3], 3), values(fields[4], 4)) else {
        return true;
    };
    // The longest each month ever is; February in a leap year.
    const LONGEST: [u32; 12] = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    let first = days.trailing_zeros();
    LONGEST
        .iter()
        .zip(1..)
        .any(|(longest, month)| months & (1 << month) != 0 && first <= *longest)
}

/// Refuse an `every:` line no clock can keep, on every port that writes one.
pub fn check(document: &Node, diags: &mut Diagnostics) {
    let Some(ports) = document.get("ports").and_then(Node::as_map) else {
        return;
    };
    for (name, entry) in ports {
        let Some(every) = entry.node.as_map().and_then(|m| m.get("every")) else {
            continue;
        };
        let written = match &every.node.value {
            Value::Str(s) => s.trim().to_string(),
            Value::Int(n) => n.to_string(),
            // Anything else is not text, and the schema says so by itself.
            _ => continue,
        };
        let said = match read(&written) {
            Ok(_) => continue,
            Err(Unreadable::NotATime) if written.is_empty() => {
                format!("`every:` in the port '{name}' is empty, so nothing says when to run.")
            }
            Err(Unreadable::NotATime) => {
                format!("`every: {written}` in the port '{name}' is not a time PACT can read.")
            }
            Err(Unreadable::Because(why)) => {
                format!("`every: {written}` in the port '{name}' — {why}")
            }
            Err(Unreadable::NeverComes) => format!(
                "`every: {written}` in the port '{name}' never comes round: no month has \
                 such a day."
            ),
        };
        diags.push(Diagnostic::error(
            "loader/every-is-not-a-time",
            every.key_span.clone().merge(&every.node.span),
            format!("{said} A runtime would refuse to start this timer."),
            format!("Write {FORMS}."),
        ));
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pact_doc::parse_yaml;

    fn conformance() -> serde_json::Value {
        let path = concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../../tests/conformance/schedules.json"
        );
        serde_json::from_str(&std::fs::read_to_string(path).expect("the conformance list"))
            .expect("json")
    }

    #[test]
    fn every_line_the_list_accepts_is_read_into_the_line_it_names() {
        let list = conformance();
        let accepted = list["accepted"].as_object().expect("accepted");
        assert!(
            accepted.len() >= 30,
            "the list is the grammar; it is not a sample"
        );
        for (written, line) in accepted {
            assert_eq!(
                read(written).as_deref(),
                Ok(line.as_str().unwrap()),
                "every: {written}"
            );
        }
    }

    #[test]
    fn every_line_the_list_refuses_is_refused() {
        let list = conformance();
        for written in list["refused"].as_array().expect("refused") {
            let written = written.as_str().unwrap();
            assert!(
                read(written).is_err(),
                "`every: {written}` was read: {:?}",
                read(written)
            );
        }
    }

    #[test]
    fn a_time_that_could_be_either_half_of_the_day_says_so() {
        let Err(Unreadable::Because(why)) = read("Friday at 4") else {
            panic!("read")
        };
        assert!(why.contains("4am or 4pm"), "{why}");
        assert_eq!(read("0 0 30 2 *"), Err(Unreadable::NeverComes));
        assert_eq!(read("every fortnight"), Err(Unreadable::NotATime));
    }

    fn checked(every: &str) -> Diagnostics {
        let text = format!("ports:\n  weekly:\n    description: x\n    every: {every}\n");
        let node = parse_yaml(&text, camino::Utf8Path::new("w.yaml")).expect("parses");
        let mut d = Diagnostics::new();
        check(&node, &mut d);
        d
    }

    #[test]
    fn a_port_whose_line_a_clock_can_keep_is_left_alone() {
        for every in ["Friday at 4pm", "'0 9 13 * 5'", "every 10 minutes"] {
            let d = checked(every);
            assert!(d.is_empty(), "{}", d.render());
        }
    }

    #[test]
    fn a_port_whose_line_no_clock_can_keep_is_refused_at_the_line() {
        for every in [
            "every fortnight",
            "'0 0 30 2 *'",
            "nights at 14",
            "Friday at 4",
        ] {
            let d = checked(every);
            let e = d
                .items()
                .first()
                .unwrap_or_else(|| panic!("`every: {every}` loaded"));
            assert_eq!(e.rule, "loader/every-is-not-a-time");
            assert_eq!(e.span.line, 4);
            assert!(e.fix.contains("`Friday at 4pm`"), "{}", e.fix);
        }
    }
}
