import { h, render } from "preact";
import { afterEach, expect, test, vi } from "vitest";
import { Badge, Logged, Loose } from "./components.tsx";

afterEach(() => {
  vi.restoreAllMocks();
});

// render() in the TEST body (not a shared beforeEach), so the component's embedded
// logic runs inside the per-test attribution window.
test("Badge renders the doubled value", () => {
  const root = document.createElement("div"); // needs the inherited happy-dom env
  render(Badge(3), root);
  expect(root.textContent).toBe("6"); // PINS n*2 -> functional + behavioral proven
});

test("Loose renders something (value-blind)", () => {
  const root = document.createElement("div");
  render(Loose(3), root);
  expect(typeof root.textContent).toBe("string"); // does NOT pin the value -> behavioral gap
});

test("Logged emits on render", () => {
  const spy = vi.spyOn(console, "info").mockImplementation(() => {});
  const root = document.createElement("div");
  render(Logged(5), root);
  expect(spy).toHaveBeenCalled(); // observes the emit -> observable proven
});
