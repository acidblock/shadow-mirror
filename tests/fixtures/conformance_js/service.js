// JS mirror of tests/fixtures/observable_demo/service.py — observable conformance.
// console.* is the universal emit surface (the stdlib-logging analog); assertions
// are spy-based (vi.spyOn), the caplog analog.

export function recordPurchase(item, qty) {
  console.info("purchase recorded: %s x%d", item, qty);
  return { item, qty };
}

export function computeTax(amount, rate) {
  const tax = Math.round(amount * rate * 100) / 100;
  console.info("tax computed: %s", tax); // exercised, but no test observes it
  return tax;
}

export function escalate(level) {
  if (level > 5) {
    console.warn("escalation: level %d", level); // never exercised
  }
  return level;
}

export function add(a, b) {
  return a + b; // no emit — Observable does not apply
}
