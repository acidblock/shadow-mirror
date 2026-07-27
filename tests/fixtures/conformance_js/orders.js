// JS mirror of tests/fixtures/resilient_demo/orders.py — the conformance fixture.
// Same functions, same test strengths, so sm's per-level verdicts correspond.
// qualname correspondence (snake_case <-> camelCase) is declared in the
// conformance test, not forced into either language.

export function normalizeQty(raw) {
  try {
    return JSON.parse(raw);   // throws on invalid input (like Python int()) — an
  } catch (e) {               // IMPLICIT throw, so the only branch is the catch
    return 0;                 // recovery, faithful to orders.py's single `except`.
  }
}

export function applyDiscount(price, codeTable, code) {
  let rate;
  try {
    if (!(code in codeTable)) {
      throw new Error("missing code");
    }
    rate = codeTable[code];
  } catch (e) {
    rate = 0.0;
  }
  return Math.round(price * (1 - rate) * 100) / 100;
}

export function charge(amount) {
  if (amount <= 0) {
    throw new RangeError("amount must be positive");
  }
  return amount;
}

export async function chargeAsync(amount) {
  // Async mirror of `charge` (resilient_demo/orders.py::charge_async). An async
  // throw asserted with `rejects.toThrow(Type)` pins the type exactly as the
  // sync `toThrow` does — the throw-type-swap sentinel is killed -> proven.
  if (amount <= 0) {
    throw new RangeError("amount must be positive");
  }
  return amount;
}

export function refund(amount, ledger) {
  if (!ledger.includes(amount)) {
    throw new RangeError("no such charge");
  }
  ledger.splice(ledger.indexOf(amount), 1);
  return amount;
}

export class OrderError extends Error {}

export function validateSku(sku) {
  if (!sku) {
    throw new OrderError("empty sku");
  }
  return sku;
}

export function lineTotal(unitPrice, qty, taxRate) {
  const subtotal = unitPrice * qty;
  return Math.round(subtotal * (1 + taxRate) * 100) / 100;
}

export function slowDouble(x) {
  return x * 2;
}
