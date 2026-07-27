import { h } from "preact";

// Three components exercising the JSX-parse-surface levels (P7-tsx-jsx-spike.md):
// functional (return <jsx> -> null), behavioral (JSX-embedded {n*2}), observable
// (console.* in a component body). Resilient/performant are byte-identical to the
// same constructs in any function (already TS-conformance-proven) and are omitted.

export function Badge(n: number): any {
  return <span class="b">{n * 2}</span>; // {n*2}: behavioral site; pinned by a render test
}

export function Loose(n: number): any {
  return <span class="l">{n * 2}</span>; // same site, but its test is value-blind -> gap
}

export function Logged(n: number): any {
  console.info("rendered", n); // observable emit; spy-asserted on render
  return <b>{n}</b>;
}
