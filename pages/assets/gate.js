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

// Back-to-home link, injected into the decrypted document (team convention: every nested page
// links back to the landing page — KB methods/static-data-apps.md § "Nested pages link back
// home"). Injected here rather than at render/encrypt time so it survives every republish
// without a re-render, and appears even when a cached passphrase skips the gate page entirely.
// Fixed-position because the deck is reveal.js, which layers the whole viewport — a link in
// normal document flow would be painted over. Styles are inline because the decrypted artefacts
// are standalone documents that do not load site.css (colors mirror its --b6/--b05/--b1).
const HOME_URL = new URL("..", import.meta.url); // assets/ sits directly under the site root
const HOME_LINK = `
<style>
  .gie-home-link { position:fixed; top:10px; left:10px; z-index:1000; padding:6px 12px;
    font:500 13px/1 'Roboto',system-ui,sans-serif; color:#1e795f; background:#e9f5f1;
    border:1px solid #d4eae4; border-radius:4px; text-decoration:none; }
  .gie-home-link:hover { background:#d4eae4; }
  @media print { .gie-home-link { display:none; } }
</style>
<a class="gie-home-link" href="${HOME_URL}">← Geospatial impact estimates</a>`;

function withHomeLink(html) {
  // First <body ...> tag only; the artefacts are complete HTML documents (encrypt_page.py
  // round-trips them), so a missing body tag means a malformed document — refuse rather than
  // display it quietly without the link.
  const injected = html.replace(/<body[^>]*>/i, (tag) => tag + HOME_LINK);
  if (injected === html) {
    throw new GateError("load", "Decrypted document has no <body> tag; refusing to display it.");
  }
  return injected;
}

function render(html) {
  // Point of no return: this tears down the current document, including this script.
  document.open();
  document.write(withHomeLink(html));
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
