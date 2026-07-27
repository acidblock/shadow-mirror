import { afterEach, expect, test, vi } from "vitest";
import { add, computeTax, escalate, recordPurchase } from "./service.js";

afterEach(() => { vi.restoreAllMocks(); });

test("recordPurchase logs", () => {
  const spy = vi.spyOn(console, "info").mockImplementation(() => {});
  expect(recordPurchase("widget", 3)).toEqual({ item: "widget", qty: 3 });
  expect(spy).toHaveBeenCalled(); // observes the emit -> proven
});

test("computeTax value", () => {
  vi.spyOn(console, "info").mockImplementation(() => {}); // silence, do not assert
  expect(computeTax(100.0, 0.2)).toBe(20.0); // emit unobserved -> gap-unasserted
});

test("escalate passthrough", () => {
  vi.spyOn(console, "warn").mockImplementation(() => {});
  expect(escalate(1)).toBe(1); // warn branch never taken -> gap-unexercised
});

test("add value", () => {
  expect(add(2, 3)).toBe(5); // no emit -> n/a
});
