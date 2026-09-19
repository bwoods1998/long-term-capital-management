// PEM and DER plumbing. WebCrypto imports exactly one private-key encoding, PKCS#8, but the key
// file a venue hands out is not always in it: Kalshi's RSA download is often PKCS#1
// (`BEGIN RSA PRIVATE KEY`). It is the same key material inside a different envelope, so it is
// re-wrapped here rather than asking the owner to convert a private key by hand on the machine
// we are trying to keep it off.

const BLOCK = /-----BEGIN ([A-Z0-9 ]+)-----([\s\S]*?)-----END \1-----/;

/** `{ label, der }` for the first PEM block in `text`, or `null` when there is none. */
export function readPem(text) {
  const match = BLOCK.exec(String(text || '').replace(/\\n/g, '\n'));
  if (!match) return null;
  const body = match[2].replace(/[^A-Za-z0-9+/=]/g, '');
  if (!body) return null;
  return { label: match[1].trim(), der: new Uint8Array(Buffer.from(body, 'base64')) };
}

export const concat = (...parts) => {
  const total = parts.reduce((sum, part) => sum + part.length, 0);
  const out = new Uint8Array(total);
  let at = 0;
  for (const part of parts) {
    out.set(part, at);
    at += part.length;
  }
  return out;
};

/** DER definite-length encoding of `n`. */
export function derLength(n) {
  if (n < 0x80) return Uint8Array.of(n);
  if (n < 0x100) return Uint8Array.of(0x81, n);
  if (n < 0x10000) return Uint8Array.of(0x82, n >> 8, n & 0xff);
  return Uint8Array.of(0x83, (n >> 16) & 0xff, (n >> 8) & 0xff, n & 0xff);
}

export const derTag = (tag, body) => concat(Uint8Array.of(tag), derLength(body.length), body);
export const derSequence = body => derTag(0x30, body);
export const derOctetString = body => derTag(0x04, body);

const VERSION_0 = Uint8Array.of(0x02, 0x01, 0x00);
// AlgorithmIdentifier SEQUENCE { OID 1.2.840.113549.1.1.1 rsaEncryption, NULL }
const RSA_ALGORITHM = Uint8Array.of(
  0x30, 0x0d, 0x06, 0x09, 0x2a, 0x86, 0x48, 0x86, 0xf7, 0x0d, 0x01, 0x01, 0x01, 0x05, 0x00,
);

const wrap = (algorithm, inner) =>
  derSequence(concat(VERSION_0, algorithm, derOctetString(inner)));

/** A PKCS#1 `RSAPrivateKey` as a PKCS#8 `PrivateKeyInfo`. */
export const pkcs1ToPkcs8 = der => wrap(RSA_ALGORITHM, der);
