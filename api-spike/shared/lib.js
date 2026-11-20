// Throwaway spike. Secrets come from secrets.json, written by the PR workflow from repository
// secrets at deploy time (the spike cannot set Static Web App settings). Never committed.
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const SECRETS_PATH = path.join(__dirname, "..", "secrets.json");
let SECRETS = null;
function secrets() {
  if (SECRETS) return SECRETS;
  if (!fs.existsSync(SECRETS_PATH)) throw new Error("secrets.json missing: the deploy workflow did not write it");
  SECRETS = JSON.parse(fs.readFileSync(SECRETS_PATH, "utf8"));
  for (const k of ["listmonk_base_url", "listmonk_user", "listmonk_key", "signing_secret"]) {
    if (!SECRETS[k]) throw new Error(`secrets.json is missing ${k}`);
  }
  return SECRETS;
}

const LIST_ID = 147; // "[TEST] Damage platform providers"
const TEMPLATE_ID = 12; // base_transactional, renders .Tx.Data.content
const LINK_TTL_S = 15 * 60;
const SESSION_TTL_S = 30 * 24 * 3600;
const COOKIE = "spike_session";

function b64u(buf) { return Buffer.from(buf).toString("base64url"); }
function sign(payloadB64) {
  return crypto.createHmac("sha256", secrets().signing_secret).update(payloadB64).digest("base64url");
}
function mint(claims, ttl) {
  const now = Math.floor(Date.now() / 1000);
  const p = b64u(JSON.stringify({ ...claims, iat: now, exp: now + ttl, nonce: crypto.randomBytes(8).toString("hex") }));
  return `${p}.${sign(p)}`;
}
function verify(token) {
  if (typeof token !== "string" || !token.includes(".")) return null;
  const [p, sig] = token.split(".");
  const want = sign(p);
  if (sig.length !== want.length || !crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(want))) return null;
  let claims;
  try { claims = JSON.parse(Buffer.from(p, "base64url").toString("utf8")); } catch { return null; }
  if (!claims.exp || claims.exp * 1000 < Date.now()) return null;
  return claims;
}

function authHeader() {
  const s = secrets();
  return "Basic " + Buffer.from(`${s.listmonk_user}:${s.listmonk_key}`).toString("base64");
}
async function onProviderList(email) {
  // 'search' (plain text), not 'query' (SQL): the sender key lacks subscribers:sql_query.
  const u = new URL(`${secrets().listmonk_base_url}/subscribers`);
  u.searchParams.set("list_id", String(LIST_ID)); u.searchParams.set("search", email); u.searchParams.set("per_page", "50");
  const r = await fetch(u, { headers: { Authorization: authHeader() } });
  if (!r.ok) throw new Error(`Listmonk subscriber lookup failed: HTTP ${r.status}`);
  const hits = (await r.json()).data.results.filter((h) => h.email.toLowerCase() === email.toLowerCase());
  return hits.some((h) => h.status === "enabled" && h.lists.some((l) => l.id === LIST_ID && l.subscription_status !== "unsubscribed"));
}
async function sendLink(email, link) {
  const content = `
<p>You asked for a sign-in link to the <b>damage analysis submission form</b>.</p>
<p style="margin:24px 0"><a href="${link}" style="background:#1e795f;color:#fff;padding:12px 18px;text-decoration:none;font-weight:600">Open the form</a></p>
<p>The link works for ${LINK_TTL_S / 60} minutes and signs in the browser it is opened in. After that you stay signed in on that device for the rest of the activation.</p>
<p style="color:#5e6a6b;font-size:13px">If you did not request this, ignore it; nothing happens unless the link is opened. Your address received it because it is on the provider list. This is a test of the next-event platform's sign-in.</p>`;
  const r = await fetch(`${secrets().listmonk_base_url}/tx`, {
    method: "POST", headers: { Authorization: authHeader(), "Content-Type": "application/json" },
    body: JSON.stringify({ subscriber_email: email, template_id: TEMPLATE_ID, content_type: "html",
      subject: "[test] Your sign-in link for the damage analysis submission form", data: { content } }),
  });
  if (!r.ok) throw new Error(`Listmonk tx send failed: HTTP ${r.status} ${(await r.text()).slice(0, 200)}`);
}

function readCookie(req) {
  const raw = req.headers && (req.headers.cookie || req.headers.Cookie);
  if (!raw) return null;
  for (const part of raw.split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k === COOKIE) return v.join("=");
  }
  return null;
}
function sessionFrom(req) {
  const c = readCookie(req);
  return c ? verify(c) : null;
}
function setCookie(value, maxAge) {
  return `${COOKIE}=${value}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${maxAge}`;
}
function origin(req) {
  // Inside a managed Function the Host header is the Function app's internal
  // <guid>.azurewebsites.net, which must never appear in an emailed link (Safe Browsing flags it
  // wholesale). Static Web Apps forwards the original URL; use that or refuse.
  const h = req.headers || {};
  const orig = h["x-ms-original-url"] || h["X-MS-ORIGINAL-URL"];
  if (orig) return new URL(orig).origin;
  const fwd = h["x-forwarded-host"];
  if (fwd && !/\.azurewebsites\.net$/i.test(fwd)) return `https://${fwd}`;
  throw new Error("cannot determine the public site address from the request headers; refusing to build a link");
}

module.exports = { LIST_ID, LINK_TTL_S, SESSION_TTL_S, mint, verify, onProviderList, sendLink, sessionFrom, setCookie, origin };
