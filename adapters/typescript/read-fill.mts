// Fill every case read from stdin with the TypeScript port (`src/fill.ts`, the
// WebAssembly build at the path given), as `pact_adapters.holes.fill` fills it.
// The Python suite compares the answers with `tests/conformance/fill.json`, in
// `test_words_are_filled_as_the_shared_cases_say.py`.
import { readFileSync } from "node:fs";
import { Filler } from "./src/fill.ts";

const filler = await Filler.load(readFileSync(process.argv[2]));
const given = JSON.parse(readFileSync(0, "utf8")) as { cases: Parameters<Filler["fill"]>[0][] };
process.stdout.write(
  JSON.stringify(
    given.cases.map((c) => {
      const answer = filler.fill(c);
      return "said" in answer ? { said: answer.said } : { refused: answer.refused };
    }),
  ),
);
