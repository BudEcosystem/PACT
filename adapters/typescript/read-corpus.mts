import { spend } from "./src/limits.ts";
const xs: string[] = JSON.parse(process.argv[2]);
process.stdout.write(
  JSON.stringify(xs.map((x) => { const [a, c] = spend(x); return [a === null ? null : String(a), c]; })),
);
