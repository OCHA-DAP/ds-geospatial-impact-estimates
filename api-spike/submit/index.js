const lib = require("../shared/lib");
// Spike persistence: one JSON blob per submission in a test folder on the dev account.
// The real build writes the registry rows in Postgres and fetches the file into bronze.
const BLOB_BASE = "https://imb0chd0dev.blob.core.windows.net/projects/ds-geospatial-impact-estimates/spike/submissions";
module.exports = lib.guarded(async function (context, req) {
  const s = lib.sessionFrom(req);
  if (!s) { context.res = { status: 401, headers: { "Content-Type": "application/json" }, body: { ok: false, message: "Sign in with an emailed link first." } }; return; }
  const sas = lib.secrets().blob_sas;
  if (!sas) { context.res = { status: 500, headers: { "Content-Type": "application/json" }, body: { ok: false, message: "blob_sas missing from the Function's secrets; nothing saved." } }; return; }
  const rec = (req.body && typeof req.body === "object" && !Array.isArray(req.body)) ? req.body : null;
  if (!rec) { context.res = { status: 400, headers: { "Content-Type": "application/json" }, body: { ok: false, message: "Body must be a JSON object." } }; return; }
  // The blob name is built from the organisation slug and event id. Both come from the client, so
  // they are accepted only in their canonical form; a dot, slash or anything else is refused rather
  // than cleaned, because the SAS can write anywhere on the dev account.
  const SAFE = /^[a-z0-9][a-z0-9_-]{0,63}$/;
  for (const k of ["org_slug", "event"]) {
    if (typeof rec[k] !== "string" || !SAFE.test(rec[k])) {
      context.res = { status: 400, headers: { "Content-Type": "application/json" }, body: { ok: false, message: `${k} must be lowercase letters, digits, _ or - (got ${JSON.stringify(rec[k]).slice(0, 80)}). Nothing saved.` } };
      return;
    }
  }
  const ts = new Date();
  const record = { received_at: ts.toISOString(), submitted_by: s.email, form: rec };
  const name = `${ts.toISOString().slice(0, 10)}/${rec.org_slug}_${rec.event}_${ts.toISOString().replace(/[:.]/g, "-")}.json`;
  const r = await fetch(`${BLOB_BASE}/${name}?${sas}`, {
    method: "PUT", headers: { "x-ms-blob-type": "BlockBlob", "Content-Type": "application/json", "x-ms-version": "2021-08-06" },
    body: JSON.stringify(record, null, 2),
  });
  if (!r.ok) {
    context.log.error(`blob write failed: HTTP ${r.status} ${(await r.text()).slice(0, 300)}`);
    context.res = { status: 502, headers: { "Content-Type": "application/json" }, body: { ok: false, message: `Could not write the record to blob storage (HTTP ${r.status}). Nothing saved.` } };
    return;
  }
  context.res = { status: 200, headers: { "Content-Type": "application/json" },
    body: { ok: true, saved_to: `projects/ds-geospatial-impact-estimates/spike/submissions/${name}`, received_at: record.received_at, submitted_by: s.email, delivery: rec.delivery || null } };
});
