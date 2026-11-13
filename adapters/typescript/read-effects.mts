// Print every agent's and workflow's effect, as `pact discover` prints an
// agent's, for one document `pact show` printed (read from the file named by
// the first argument). The Python suite compares it with the checker's own,
// in `test_both_ports_compute_one_effect.py`.
import { readFileSync } from "node:fs";
import { discovered, effectOf } from "./src/effects.ts";

const document = JSON.parse(readFileSync(process.argv[2] ?? "", "utf8")) as {
  agents?: Record<string, unknown>;
  workflows?: Record<string, unknown>;
};
const of = (names: string[]) => Object.fromEntries(names.map((name) => [name, discovered(effectOf(document, name))]));
process.stdout.write(
  JSON.stringify({ agents: of(Object.keys(document.agents ?? {})), workflows: of(Object.keys(document.workflows ?? {})) }),
);
