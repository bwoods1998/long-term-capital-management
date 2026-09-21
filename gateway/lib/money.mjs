// Exact money. A cap that is off by a float rounding error is not a cap, so every amount that
// reaches a comparison here is a BigInt: `pico` is 10^-12 of a dollar, `micro` is 10^-6 and is
// what the Durable Object stores (a whole trading day of 400 dollars is 4e8, far inside the
// integer range SQLite and JSON both round-trip exactly).

export const PICO = 10n ** 12n;
export const MICRO = 10n ** 6n;
const PICO_PER_MICRO = 10n ** 6n;
const DECIMAL = /^(-?)(\d+)(?:\.(\d+))?$/;

/** A venue's decimal string (or a JSON number) as picodollars. `null` when it is not a number. */
export function parsePico(value) {
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return null;
    value = Number.isInteger(value) ? String(value) : value.toFixed(12);
  }
  if (typeof value !== 'string') return null;
  const match = DECIMAL.exec(value.trim());
  if (!match) return null;
  const fraction = (match[3] || '').slice(0, 12).padEnd(12, '0');
  const magnitude = BigInt(match[2]) * PICO + BigInt(fraction);
  return match[1] === '-' ? -magnitude : magnitude;
}

/** Whole US dollars as picodollars, for a cap read out of an environment variable. */
export function parseUsdMicro(value, fallback) {
  const pico = parsePico(value);
  if (pico === null || pico < 0n) return fallback;
  return picoToMicro(pico);
}

export function parseCount(value, fallback) {
  const parsed = Number(String(value ?? '').trim());
  return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : fallback;
}

/** `a * b` where both are picodollar-scaled, rounded **up**: a cap never rounds in our favour. */
export function mulPico(a, b) {
  const product = a * b;
  return product <= 0n ? 0n : (product + PICO - 1n) / PICO;
}

/** Cents (Kalshi's legacy order surface counts them) as picodollars. */
export function centsToPico(value) {
  const pico = parsePico(value);
  return pico === null ? null : pico / 100n;
}

/** Picodollars as micro, rounded up. */
export function picoToMicro(pico) {
  if (pico <= 0n) return 0n;
  return (pico + PICO_PER_MICRO - 1n) / PICO_PER_MICRO;
}

/** Micro as a plain `"12.34"` for a JSON body. Never a float. */
export function formatUsd(micro) {
  const value = BigInt(micro ?? 0n);
  const sign = value < 0n ? '-' : '';
  const absolute = value < 0n ? -value : value;
  const cents = (absolute + 9999n) / 10000n; // micro -> cents, rounded up
  return `${sign}${cents / 100n}.${String(cents % 100n).padStart(2, '0')}`;
}

/** Lossless meter receipts. Display rounding must never manufacture a reservation breach. */
export function formatUsdMicro(micro) {
  const value = BigInt(micro ?? 0n);
  const sign = value < 0n ? '-' : '';
  const absolute = value < 0n ? -value : value;
  return `${sign}${absolute / MICRO}.${String(absolute % MICRO).padStart(6, '0')}`;
}
