// TS mirror of observable_demo/service.py (and conformance_js/service.js). console.*
// is the emit surface (stdlib-logging analog); vi.spyOn is the caplog analog. Types
// present so the TS adapter's _observable_sites is exercised under annotations.

export function recordPurchase(item: string, qty: number): { item: string; qty: number } {
  console.info("purchase recorded: %s x%d", item, qty);
  return { item, qty };
}

export function computeTax(amount: number, rate: number): number {
  const tax: number = Math.round(amount * rate * 100) / 100;
  console.info("tax computed: %s", tax); // exercised, but no test observes it
  return tax;
}

export function escalate(level: number): number {
  if (level > 5) {
    console.warn("escalation: level %d", level); // never exercised
  }
  return level;
}

export function add(a: number, b: number): number {
  return a + b; // no emit — Observable does not apply
}
