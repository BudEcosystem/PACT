// Read every case of `tests/conformance/detectors.json`, given on stdin, with
// the TypeScript port: whether `translateDetectorPattern` refuses the pattern
// and why, and otherwise every match it finds in each text, in order. The
// Python suite compares the answers with the cases, in
// `test_every_port_reads_one_detector_dialect.py`.
import { readFileSync } from "node:fs";
import { translateDetectorPattern } from "./src/detectors.ts";

const given = JSON.parse(readFileSync(0, "utf8")) as {
  texts: string[];
  cases: { "looks-like": string }[];
};
const answers = given.cases.map((c) => {
  const translation = translateDetectorPattern(c["looks-like"]);
  if (!translation.ok) return { outside: true, reason: translation.reason };
  const finds = given.texts.flatMap((text, index) => {
    const found = [...text.matchAll(new RegExp(translation.source, "gu"))].map((match) => match[0]);
    return found.length === 0 ? [] : [{ in: index, found }];
  });
  return { outside: false, finds };
});
process.stdout.write(JSON.stringify(answers));
