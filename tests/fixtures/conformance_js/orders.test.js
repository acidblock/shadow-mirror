import { expect, test } from "vitest";
import {
  normalizeQty, applyDiscount, charge, chargeAsync, refund, validateSku,
  lineTotal, slowDouble, OrderError,
} from "./orders.js";

test("normalizeQty recovers to zero", () => {
  expect(normalizeQty("not a number")).toBe(0);   // pins the recovery value
  expect(normalizeQty("7")).toBe(7);
});

test("applyDiscount runs but value unpinned", () => {
  expect(applyDiscount(100.0, {}, "NOPE")).toBeGreaterThanOrEqual(0);  // value-blind
});

test("charge rejects nonpositive", () => {
  expect(() => charge(0)).toThrow(RangeError);     // pins the thrown type
});

test("chargeAsync rejects nonpositive (promise form)", async () => {
  await expect(chargeAsync(-1)).rejects.toThrow(RangeError);  // pins the async-thrown type
  await expect(chargeAsync(5)).resolves.toBe(5);
});

test("refund happy path", () => {
  expect(refund(50, [50])).toBe(50);               // never triggers the throw
});

test("validateSku rejects empty", () => {
  expect(() => validateSku("")).toThrow(OrderError);  // pins a custom type
  expect(validateSku("ABC")).toBe("ABC");
});

test("lineTotal exact value", () => {
  expect(lineTotal(10.0, 3, 0.0)).toBe(30.0);      // strong value -> functional + behavioral
  expect(lineTotal(10.0, 2, 0.1)).toBe(22.0);
});

test("slowDouble within time budget", () => {
  const t0 = performance.now();
  expect(slowDouble(5)).toBe(10);
  expect(performance.now() - t0).toBeLessThan(1000);  // a time bound -> performant proven
});
