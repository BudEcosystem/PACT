// Fence every case read from stdin with the TypeScript port, as
// `mcp_bridge.quarantined` fences it, and read every probe with
// `isQuarantined`. The Python suite compares the answers with the reference's
// own, in `test_both_ports_fence_one_way.py`.
import { readFileSync } from "node:fs";
import { fencedRegions, isQuarantined, quarantined } from "./src/fence.ts";

const given = JSON.parse(readFileSync(0, "utf8")) as {
  cases: { server: string; text: string; options: { pinned?: string; what?: string } }[];
  probes: string[];
};
const regions = given.cases.map((c) => quarantined(c.server, c.text, c.options));
let refusal: string | null = null;
try {
  fencedRegions(given.probes);
} catch (error) {
  refusal = (error as Error).message;
}
process.stdout.write(
  JSON.stringify({ regions, read: [...regions, ...given.probes].map(isQuarantined), refusal }),
);
