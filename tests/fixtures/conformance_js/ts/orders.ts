// TS mirror of resilient_demo/orders.py (and conformance_js/orders.js), fully
// type-annotated so the TsAdapter's site-finders are exercised with types present
// on the very nodes the operators target (params, return types).

export function normalizeQty(raw: string): number {
  try {
    return JSON.parse(raw);   // implicit throw -> single catch branch
  } catch (e) {
    return 0;                 // recovery pinned by `=== 0` test -> resilient proven
  }
}

export function applyDiscount(
  price: number,
  codeTable: Record<string, number>,
  code: string,
): number {
  let rate: number;
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

export function charge(amount: number): number {
  if (amount <= 0) {
    throw new RangeError("amount must be positive");
  }
  return amount;
}

export async function chargeAsync(amount: number): Promise<number> {
  if (amount <= 0) {
    throw new RangeError("amount must be positive");
  }
  return amount;
}

export function refund(amount: number, ledger: number[]): number {
  if (!ledger.includes(amount)) {
    throw new RangeError("no such charge");
  }
  ledger.splice(ledger.indexOf(amount), 1);
  return amount;
}

export class OrderError extends Error {}

export function validateSku(sku: string): string {
  if (!sku) {
    throw new OrderError("empty sku");
  }
  return sku;
}

export function lineTotal(unitPrice: number, qty: number, taxRate: number): number {
  const subtotal: number = unitPrice * qty;
  return Math.round(subtotal * (1 + taxRate) * 100) / 100;
}

export function slowDouble(x: number): number {
  return x * 2;
}
