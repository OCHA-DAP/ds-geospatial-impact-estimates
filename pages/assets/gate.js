/* Passphrase form for an encrypted page. All crypto lives in decrypt.js; this is UI only.
 *
 * The form element carries the ciphertext filename:
 *   <form data-gate data-enc="content.enc"> ... </form>
 *
 * On success the decrypted document replaces this one wholesale via document.write. The
 * artefacts are complete HTML documents with their own <head> and scripts — reveal.js in
 * particular handles keyboard navigation and fullscreen badly inside an iframe — so becoming
 * the page is the behaviour we want, and the URL stays put.
 */

import { decryptPage, GateError } from "./decrypt.js";

// Survives navigation between the gated pages, dies with the tab. Holding the passphrase (not
// a derived key) is what lets the second page decrypt its own differently-salted file without
// prompting again. Same-origin, session-scoped; it is no more exposed than the form field it
// came from.
const CACHE_KEY = "gie-page-pass";

const form = document.querySelector("[data-gate]");
if (!form) throw new Error("gate.js loaded on a page with no [data-gate] form");

const encUrl = form.dataset.enc;
if (!encUrl) throw new Error("gate form is missing its data-enc filename");

const input = form.querySelector("[data-gate-input]");
const button = form.querySelector("[data-gate-submit]");
const message = form.querySelector("[data-gate-message]");

function say(text, kind) {
  message.textContent = text;
  message.dataset.kind = kind; // "error" | "busy" | "" — styled by site.css
}

function busy(isBusy) {
  input.disabled = isBusy;
  button.disabled = isBusy;
  button.textContent = isBusy ? "Decrypting…" : "Open";
}

async function fetchEnvelope() {
  let res;
  try {
    // `cache: "no-cache"` = always revalidate with the server (a 304 when unchanged, a real
    // download only after a republish). The default mode was tried first and serves a stale
    // ciphertext for up to 10 minutes after a deploy (GitHub Pages sends max-age=600, and within
    // that window the browser answers from cache without asking) — readers mid-review kept seeing
    // the previous version. `cache: "force-cache"` was also tried, to avoid refetching several MB
    // on a return visit, and was observed hanging indefinitely in Chrome — no network request, no
    // resolve, no reject — when the entry was already in the HTTP cache. Revalidation is the
    // behaviour we actually want; GitHub Pages sends both ETag and Last-Modified.
    res = await fetch(encUrl, { cache: "no-cache" });
  } catch (err) {
    throw new GateError("load", `Could not reach ${encUrl}: ${err.message}`);
  }
  if (!res.ok) {
    throw new GateError("load", `Could not load the encrypted content (HTTP ${res.status}).`);
  }
  return res.arrayBuffer();
}

function render(html) {
  // Point of no return: this tears down the current document, including this script.
  document.open();
  document.write(html);
  document.close();
}

/** Returns true on success. `silent` suppresses the error text for the cached-passphrase
 *  attempt on load, where a stale cached value is expected rather than a reader's mistake. */
async function attempt(passphrase, { silent = false } = {}) {
  busy(true);
  say(silent ? "Opening…" : "Decrypting…", "busy");
  try {
    const html = await decryptPage(await fetchEnvelope(), passphrase);
    sessionStorage.setItem(CACHE_KEY, passphrase);
    render(html);
    return true;
  } catch (err) {
    if (!(err instanceof GateError)) throw err;
    if (err.kind === "passphrase") {
      // A cached passphrase that no longer works is a rotation, not a reader error: drop it
      // and fall through to the form rather than retrying it on every load.
      sessionStorage.removeItem(CACHE_KEY);
    }
    say(silent && err.kind === "passphrase" ? "" : err.message, silent && err.kind === "passphrase" ? "" : "error");
    busy(false);
    if (!silent) input.select();
    return false;
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!input.value) {
    say("Enter the passphrase.", "error");
    return;
  }
  attempt(input.value);
});

const cached = sessionStorage.getItem(CACHE_KEY);
if (cached) {
  attempt(cached, { silent: true });
} else {
  input.focus();
}
