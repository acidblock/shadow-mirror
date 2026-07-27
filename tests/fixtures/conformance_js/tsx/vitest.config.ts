import { defineConfig } from "vitest/config";

// Target "project" config the adapter's coverage() must INHERIT (slice 1): a DOM
// environment for component renders + the classic Preact JSX transform. `esbuild`
// is a sibling of `test:` at config root — verified to survive the merge. Scoped to
// this subdir so it does not affect the other conformance runs.
export default defineConfig({
  test: { environment: "happy-dom" },
  esbuild: { jsx: "transform", jsxFactory: "h", jsxFragment: "Fragment" },
});
