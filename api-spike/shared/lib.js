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
  if (SECRETS.blob_sas) SECRETS.blob_sas = SECRETS.blob_sas.replace(/^\?/, ""); // team SAS values carry a leading ?
  for (const k of ["listmonk_base_url", "listmonk_user", "listmonk_key", "signing_secret", "listmonk_manage_user", "listmonk_manage_key", "blob_sas"]) {
    if (!SECRETS[k]) throw new Error(`secrets.json is missing ${k}`);
  }
  return SECRETS;
}

const LIST_ID = 147; // "[TEST] Damage platform providers"
const TEMPLATE_ID = 12; // base_transactional, renders .Tx.Data.content
const LINK_TTL_S = 15 * 60;
const SESSION_TTL_S = 30 * 24 * 3600;
const COOKIE = "spike_session";
// The directory-scoped SAS covers exactly this folder, so organisation records live under it too.
const BLOB_DIR = "https://imb0chd0dev.blob.core.windows.net/projects/ds-geospatial-impact-estimates/spike/submissions";
const BLOB_REL = "projects/ds-geospatial-impact-estimates/spike/submissions";
const ORG_PREFIX = "_organisations";
const ORG_TYPES = ["UN agency", "NGO", "academic", "private sector", "government", "network"];
const LICENCES = ["CC BY", "CC BY-SA", "ODbL", "terms", "restricted"];
const SLUG = /^[a-z0-9][a-z0-9_-]{0,63}$/;

function b64u(buf) { return Buffer.from(buf).toString("base64url"); }
function sign(payloadB64) {
  return crypto.createHmac("sha256", secrets().signing_secret).update(payloadB64).digest("base64url");
}
// Every token carries its kind ("link" = 15-minute emailed token, "session" = 30-day cookie) and
// verify() demands the kind the caller expects, so one can never be presented as the other.
function mint(typ, claims, ttl) {
  const now = Math.floor(Date.now() / 1000);
  const p = b64u(JSON.stringify({ typ, ...claims, iat: now, exp: now + ttl, nonce: crypto.randomBytes(8).toString("hex") }));
  return `${p}.${sign(p)}`;
}
function verify(token, typ) {
  if (typeof token !== "string" || !token.includes(".")) return null;
  const [p, sig] = token.split(".");
  const want = sign(p);
  if (sig.length !== want.length || !crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(want))) return null;
  let claims;
  try { claims = JSON.parse(Buffer.from(p, "base64url").toString("utf8")); } catch { return null; }
  if (!claims.exp || claims.exp * 1000 < Date.now()) return null;
  if (claims.typ !== typ) return null;
  return claims;
}

// Two Listmonk credentials: the sender key (look up subscribers, send mail) is used everywhere;
// the manage key (create and update subscribers) only by sign-up.
function basic(user, key) { return "Basic " + Buffer.from(`${user}:${key}`).toString("base64"); }
function authHeader() { const s = secrets(); return basic(s.listmonk_user, s.listmonk_key); }
function manageAuthHeader() { const s = secrets(); return basic(s.listmonk_manage_user, s.listmonk_manage_key); }

// The subscriber record for an address, or null. Exact, case-insensitive match on the email.
async function findSubscriber(email) {
  // 'search' (plain text), not 'query' (SQL): the sender key lacks subscribers:sql_query.
  const u = new URL(`${secrets().listmonk_base_url}/subscribers`);
  u.searchParams.set("search", email); u.searchParams.set("per_page", "50");
  const r = await fetch(u, { headers: { Authorization: authHeader() } });
  if (!r.ok) throw new Error(`Listmonk subscriber lookup failed: HTTP ${r.status}`);
  return (await r.json()).data.results.find((h) => h.email.toLowerCase() === email.toLowerCase()) || null;
}
function onList(hit) {
  return !!hit && hit.status === "enabled" && hit.lists.some((l) => l.id === LIST_ID && l.subscription_status !== "unsubscribed");
}
async function onProviderList(email) { return onList(await findSubscriber(email)); }
// The organisation a provider registered, kept in the subscriber's attributes by sign-up.
function orgFrom(hit) {
  const o = hit && hit.attribs && hit.attribs.org;
  return o && typeof o === "object" && SLUG.test(o.slug || "") ? o : null;
}
// Create the subscriber on the provider list, or update an existing one; the organisation goes in attribs.
async function upsertSubscriber(email, name, org) {
  const base = secrets().listmonk_base_url, hdr = { Authorization: manageAuthHeader(), "Content-Type": "application/json" };
  const existing = await findSubscriber(email);
  if (!existing) {
    const r = await fetch(`${base}/subscribers`, { method: "POST", headers: hdr,
      body: JSON.stringify({ email, name, status: "enabled", lists: [LIST_ID], attribs: { org }, preconfirm_subscriptions: true }) });
    if (!r.ok) throw new Error(`Listmonk subscriber create failed: HTTP ${r.status} ${(await r.text()).slice(0, 200)}`);
    return "created";
  }
  const lists = [...new Set([...existing.lists.map((l) => l.id), LIST_ID])];
  const r = await fetch(`${base}/subscribers/${existing.id}`, { method: "PUT", headers: hdr,
    body: JSON.stringify({ email: existing.email, name: name || existing.name, status: "enabled", lists, attribs: { ...(existing.attribs || {}), org }, preconfirm_subscriptions: true }) });
  if (!r.ok) throw new Error(`Listmonk subscriber update failed: HTTP ${r.status} ${(await r.text()).slice(0, 200)}`);
  return "updated";
}
async function sendLink(email, link, intro) {
  const content = `
<p>${intro || "You asked for a sign-in link to the <b>damage analysis submission form</b>."}</p>
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
function linkFor(req, email) {
  return `${origin(req)}/api/redeem?t=${mint("link", { email, list: LIST_ID }, LINK_TTL_S)}`;
}

// Blob helpers for the spike folder. `rel` is a path under the folder; callers build it from
// validated values only, because the SAS allows writes anywhere inside the folder.
function blobHeaders(extra) { return { "x-ms-version": "2021-08-06", ...(extra || {}) }; }
async function putJson(rel, obj) {
  const r = await fetch(`${BLOB_DIR}/${rel}?${secrets().blob_sas}`, { method: "PUT",
    headers: blobHeaders({ "x-ms-blob-type": "BlockBlob", "Content-Type": "application/json" }), body: JSON.stringify(obj, null, 2) });
  if (!r.ok) throw new Error(`blob write failed for ${rel}: HTTP ${r.status} ${(await r.text()).slice(0, 300)}`);
  return `${BLOB_REL}/${rel}`;
}
// Parsed JSON, or null when the blob does not exist. Any other failure throws.
async function getJson(rel) {
  const r = await fetch(`${BLOB_DIR}/${rel}?${secrets().blob_sas}`, { headers: blobHeaders() });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`blob read failed for ${rel}: HTTP ${r.status}`);
  return r.json();
}
async function listBlobs() {
  const u = `https://imb0chd0dev.blob.core.windows.net/projects?restype=container&comp=list&prefix=ds-geospatial-impact-estimates/spike/submissions/&${secrets().blob_sas}`;
  const r = await fetch(u, { headers: blobHeaders() });
  if (!r.ok) throw new Error(`blob listing failed: HTTP ${r.status}`);
  const xml = await r.text();
  return [...xml.matchAll(/<Blob><Name>([^<]+)<\/Name>.*?<Last-Modified>([^<]+)<\/Last-Modified>.*?<Content-Length>(\d+)<\/Content-Length>/gs)].map((m) => ({ name: m[1], modified: m[2], bytes: Number(m[3]) }));
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
  return c ? verify(c, "session") : null;
}
function setCookie(value, maxAge) {
  return `${COOKIE}=${value}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${maxAge}`;
}
// Hosts an emailed link may point at: this Static Web App's production and PR-preview hostnames.
// Static Web Apps overwrites x-ms-original-url itself (verified: a client-supplied value is
// replaced), so this allowlist is defence in depth, not the only barrier.
const SITE_HOST = /^ashy-sea-03134990f(-\d+)?(\.[a-z0-9]+)*\.azurestaticapps\.net$/;
function origin(req) {
  // Inside a managed Function the Host header is the Function app's internal
  // <guid>.azurewebsites.net, which must never appear in an emailed link (Safe Browsing flags it
  // wholesale). Static Web Apps forwards the original URL; use that or refuse.
  const h = req.headers || {};
  const orig = h["x-ms-original-url"] || h["X-MS-ORIGINAL-URL"];
  if (!orig) throw new Error("x-ms-original-url missing: not behind Static Web Apps; refusing to build a link");
  const u = new URL(orig);
  if (u.protocol !== "https:" || !SITE_HOST.test(u.hostname)) throw new Error(`refusing to build a link for host ${u.hostname}: not this site`);
  return u.origin;
}
function json(context, status, body, extraHeaders) {
  context.res = { status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store", ...(extraHeaders || {}) }, body };
}
// Best-effort per-instance throttle: one action per key per minute. Resets on cold start.
const recent = new Map();
function throttled(key) {
  const last = recent.get(key) || 0;
  if (Date.now() - last < 60_000) return true;
  recent.set(key, Date.now());
  return false;
}
function clientIp(req) {
  const h = req.headers || {};
  return String(h["x-forwarded-for"] || h["X-Forwarded-For"] || "").split(",")[0].trim() || "unknown";
}

// Wrap a handler so an unexpected throw becomes a JSON 500 instead of an empty response.
function guarded(fn) {
  return async function (context, req) {
    try { await fn(context, req); }
    catch (e) {
      context.log.error(e);
      json(context, 500, { ok: false, message: `Function error: ${e.message}` });
    }
  };
}
module.exports = { LIST_ID, LINK_TTL_S, SESSION_TTL_S, ORG_PREFIX, ORG_TYPES, LICENCES, SLUG, secrets, mint, verify,
  findSubscriber, onList, onProviderList, orgFrom, upsertSubscriber, sendLink, linkFor, putJson, getJson, listBlobs,
  sessionFrom, setCookie, origin, json, throttled, clientIp, guarded };
