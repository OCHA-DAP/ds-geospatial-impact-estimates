/* Decrypt a page encrypted by scripts/encrypt_page.py.
 *
 * Pure — no DOM, no globals beyond WebCrypto and the compression streams — so the same code
 * that runs in the browser can be exercised directly under Node. gate.js does the UI.
 *
 * Envelope layout, written by encrypt_page.py:
 *
 *   offset  bytes  field
 *   0       8      magic "GIEENC01"
 *   8       16     PBKDF2 salt
 *   24      12     AES-GCM nonce
 *   36      4      PBKDF2 iteration count, uint32 big-endian
 *   40      ...    AES-GCM ciphertext with its 16-byte tag appended
 *
 * The iteration count is read from the header rather than hardcoded here, so raising the cost
 * on the Python side cannot silently break already-published files.
 */

const MAGIC = "GIEENC01";
const HEADER_BYTES = 40;

/* Failures a reader must be able to tell apart. `kind` is one of:
 *   "load"       — the ciphertext could not be fetched. The site is broken.
 *   "malformed"  — fetched, but not a recognised envelope. The build is broken.
 *   "passphrase" — decryption was authenticated and rejected. The reader can fix this.
 *   "internal"   — a bug here, or a browser missing something we need.
 * Collapsing these into one "something went wrong" is the failure mode worth avoiding:
 * a reader would have no way to know whether to retype or to report. */
export class GateError extends Error {
  constructor(kind, message) {
    super(message);
    this.name = "GateError";
    this.kind = kind;
  }
}

export function parseEnvelope(buffer) {
  const bytes = new Uint8Array(buffer);
  if (bytes.length <= HEADER_BYTES) {
    throw new GateError("malformed", `File is ${bytes.length} bytes — too short to be a page.`);
  }
  const magic = new TextDecoder().decode(bytes.subarray(0, MAGIC.length));
  if (magic !== MAGIC) {
    throw new GateError("malformed", "This file is not a recognised encrypted page.");
  }
  return {
    salt: bytes.subarray(8, 24),
    iv: bytes.subarray(24, 36),
    iterations: new DataView(bytes.buffer, bytes.byteOffset + 36, 4).getUint32(0, false),
    sealed: bytes.subarray(HEADER_BYTES),
  };
}

async function deriveKey(passphrase, salt, iterations) {
  const material = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(passphrase), "PBKDF2", false, ["deriveKey"],
  );
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", salt, iterations, hash: "SHA-256" },
    material,
    { name: "AES-GCM", length: 256 },
    false,
    ["decrypt"],
  );
}

async function gunzip(buffer) {
  const stream = new Blob([buffer]).stream().pipeThrough(new DecompressionStream("gzip"));
  return new Response(stream).text();
}

/** Envelope bytes + passphrase -> the original HTML document as a string. */
export async function decryptPage(buffer, passphrase) {
  const { salt, iv, iterations, sealed } = parseEnvelope(buffer);
  const key = await deriveKey(passphrase, salt, iterations);

  let compressed;
  try {
    compressed = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, sealed);
  } catch (err) {
    // AES-GCM's authentication tag failing IS the passphrase check — there is no string
    // comparison here to bypass. Anything else is our bug, and must not be reported as a
    // bad passphrase or the reader will retype forever.
    //
    // A corrupted or truncated-in-transit ciphertext fails the same tag check and is
    // reported the same way; the primitive cannot distinguish a wrong key from altered
    // bytes. A mistyped passphrase is overwhelmingly the likelier cause, so that is what
    // we say — but a reader who is certain of the passphrase should suspect the file.
    if (err instanceof Error && err.name === "OperationError") {
      throw new GateError("passphrase", "Wrong passphrase.");
    }
    throw new GateError("internal", `Decryption failed unexpectedly: ${err.message}`);
  }

  try {
    return await gunzip(compressed);
  } catch (err) {
    throw new GateError("internal", `Could not decompress the decrypted page: ${err.message}`);
  }
}
