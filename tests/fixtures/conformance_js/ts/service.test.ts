import { afterEach, expect, test, vi } from "vitest";
import { add, computeTax, escalate, recordPurchase } from "./service.ts";

afterEach(() => { vi.restoreAllMocks(); });

test("recordPurchase logs", () => {
  const spy = vi.spyOn(console, "info").mockImplementation(() => {});
  expect(recordPurchase("widget", 3)).toEqual({ item: "widget", qty: 3 });
  expect(spy).toHaveBeenCalled();
});

test("computeTax value", () => {
  vi.spyOn(console, "info").mockImplementation(() => {});
  expect(computeTax(100.0, 0.2)).toBe(20.0);
});

test("escalate passthrough", () => {
  vi.spyOn(console, "warn").mockImplementation(() => {});
  expect(escalate(1)).toBe(1);
});

test("add value", () => {
  expect(add(2, 3)).toBe(5);
});
