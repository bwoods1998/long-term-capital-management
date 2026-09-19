// Alpaca auth and routing (https://docs.alpaca.markets/reference/getaccount-1).
//
// Auth is two headers and no signature, so this module's whole job is to keep the key and the
// secret inside the Worker and to send each path to the right host. Alpaca splits its API over
// two hosts that take the same credentials: trading on `api.alpaca.markets` and market data on
// `data.alpaca.markets`. The paths do not overlap, so the path chooses the host and the floor's
// adapter needs no second venue name.
//
// There is a paper host too (`paper-api.alpaca.markets`). This gateway signs for the production
// account the owner funded; a paper account would be a second set of secrets and a second venue.

export const TRADING_HOST = 'https://api.alpaca.markets';
export const DATA_HOST = 'https://data.alpaca.markets';

//: Path prefixes that belong to the market-data host. Everything else is a trading path.
const DATA_PREFIXES = ['v2/stocks/', 'v2/news', 'v1beta1/', 'v1beta3/'];

/** Which host serves this venue path. */
export function hostFor(path) {
  const clean = String(path || '').replace(/^\/+/, '');
  return DATA_PREFIXES.some(prefix => clean.startsWith(prefix)) ? DATA_HOST : TRADING_HOST;
}

/** The absolute URL a venue path and query forward to. */
export function target(path, search = '') {
  const clean = String(path || '').replace(/^\/+/, '');
  return `${hostFor(clean)}/${clean}${search || ''}`;
}

/** The two headers Alpaca authenticates with. Nothing here is derived; both are the secret. */
export function authHeaders({ keyId, secretKey }) {
  if (typeof keyId !== 'string' || !keyId.trim()) throw new Error('alpaca key id is missing');
  if (typeof secretKey !== 'string' || !secretKey.trim()) throw new Error('alpaca secret key is missing');
  return { 'APCA-API-KEY-ID': keyId.trim(), 'APCA-API-SECRET-KEY': secretKey.trim() };
}
