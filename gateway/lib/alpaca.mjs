// Alpaca auth and routing (https://docs.alpaca.markets/reference/getaccount-1).
//
// Auth is two headers and no signature, so this module's whole job is to keep the key and the
// secret inside the Worker and to send each path to the right host. Alpaca splits its API over
// two hosts that take the same credentials: trading on `api.alpaca.markets` and market data on
// `data.alpaca.markets`. The paths do not overlap, so the path chooses the host and the floor's
// adapter needs no second venue name.
//
// There is a paper host too (`paper-api.alpaca.markets`). It is the venue `alpaca-paper`: the same
// paths, a second pair of secrets (`ALPACA_PAPER_*`), never metered and never stopped by the kill
// switch, because no money is behind it.

export const TRADING_HOST = 'https://api.alpaca.markets';
//: The paper account's trading host (venue `alpaca-paper`): the same API, simulated money.
export const PAPER_HOST = 'https://paper-api.alpaca.markets';
export const DATA_HOST = 'https://data.alpaca.markets';

//: Path prefixes that belong to the market-data host. Everything else is a trading path.
const DATA_PREFIXES = ['v2/stocks/', 'v2/news', 'v1beta1/', 'v1beta3/'];

/** Which host serves this venue path. Market data is one host for both accounts. */
export function hostFor(path, { paper = false } = {}) {
  const clean = String(path || '').replace(/^\/+/, '');
  if (DATA_PREFIXES.some(prefix => clean.startsWith(prefix))) return DATA_HOST;
  return paper ? PAPER_HOST : TRADING_HOST;
}

/** The absolute URL a venue path and query forward to. */
export function target(path, search = '', options = {}) {
  const clean = String(path || '').replace(/^\/+/, '');
  return `${hostFor(clean, options)}/${clean}${search || ''}`;
}

/** The two headers Alpaca authenticates with. Nothing here is derived; both are the secret. */
export function authHeaders({ keyId, secretKey }) {
  if (typeof keyId !== 'string' || !keyId.trim()) throw new Error('alpaca key id is missing');
  if (typeof secretKey !== 'string' || !secretKey.trim()) throw new Error('alpaca secret key is missing');
  return { 'APCA-API-KEY-ID': keyId.trim(), 'APCA-API-SECRET-KEY': secretKey.trim() };
}
