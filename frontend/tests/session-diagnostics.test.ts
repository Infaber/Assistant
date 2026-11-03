import { test } from "node:test";
import assert from "node:assert/strict";
import { responseStatistics } from "../lib/session-diagnostics";
test("response chart preserves measurement order and uses nearest-rank p95", () => {
  const stats = responseStatistics([1400, 900, 1200, 1000]);
  assert.deepEqual(stats, {values:[1400,900,1200,1000], median:1100, p95:1400});
});
test("missing and invalid samples never become fabricated timings", () => {
  assert.deepEqual(responseStatistics(undefined), {values:[],median:null,p95:null});
  assert.deepEqual(responseStatistics([null, "900", -1, Infinity, NaN, 0]).values, [0]);
  assert.equal(responseStatistics(Array.from({length:150},(_,i)=>i)).values[0],50);
});
