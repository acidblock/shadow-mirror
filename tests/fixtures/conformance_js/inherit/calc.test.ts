import { expect, test } from "vitest";
import { dbl } from "./calc.ts";

// The SINGLE covering test for `dbl` depends on all three things the merge must
// preserve, so the engine's behavioral=proven verdict proves all three at once:
//  - environment inherited: `document` exists only under the target's happy-dom env;
//  - target setupFiles inherited: the marker global is set by ./marker.mjs;
//  - attribution intact: pinning the arithmetic requires non-empty line_tests.
// If any were dropped, this test throws before dbl runs (or the pin doesn't register)
// and dbl's behavioral verdict degrades away from proven.
test("dbl doubles, in the inherited DOM env with the inherited setup", () => {
  expect(typeof document).not.toBe("undefined");
  expect(globalThis.__SM_TARGET_SETUP_RAN__).toBe(true);
  expect(dbl(3)).toBe(6);
});
