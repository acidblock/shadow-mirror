import { defineConfig } from "vitest/config";

// A "target project" config the adapter's coverage() must INHERIT, not replace:
// a DOM environment (the .tsx render need) + the project's own setupFiles. Lives in
// this subdir so it scopes ONLY to the inherit test — orders/service (cwd=parent)
// still have no target config and exercise the byte-identical standalone path.
export default defineConfig({
  test: {
    environment: "happy-dom",
    setupFiles: ["./marker.mjs"],
  },
});
