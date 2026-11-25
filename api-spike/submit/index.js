const lib = require("../shared/lib");
// Spike persistence: one JSON blob per submission in a test folder on the dev account.
// The real build writes the registry rows in Postgres and fetches the file into bronze.
module.exports = lib.guarded(async function (context, req) {
  const s = lib.sessionFrom(req);
  if (!s) return lib.json(context, 401, { ok: false, message: "Sign in with an emailed link first." });
  // The organisation comes from the registry record behind the signed-in address, never from the body.
  const reg = await lib.registryFor(s.email);
  const org = reg ? reg.organisation : null;
  if (!org) return lib.json(context, 403, { ok: false, message: "No organisation is registered for this address. Register it first (For data providers > Register), then submit." });
  const rec = (req.body && typeof req.body === "object" && !Array.isArray(req.body)) ? req.body : null;
  if (!rec) return lib.json(context, 400, { ok: false, message: "Body must be a JSON object." });
  // The event id is client-supplied and goes into the blob name, so it is accepted only in its
  // canonical form; anything else is refused rather than cleaned.
  if (typeof rec.event !== "string" || !lib.SLUG.test(rec.event)) {
    return lib.json(context, 400, { ok: false, message: `event must be lowercase letters, digits, _ or - (got ${JSON.stringify(rec.event).slice(0, 80)}). Nothing saved.` });
  }
  delete rec.org_slug; // if a client sends one, it is ignored, not trusted
  const ts = new Date();
  const record = { received_at: ts.toISOString(), submitted_by: s.email, organisation: org, form: rec };
  const name = `${ts.toISOString().slice(0, 10)}/${org.slug}_${rec.event}_${ts.toISOString().replace(/[:.]/g, "-")}.json`;
  let saved_to;
  try { saved_to = await lib.putJson(name, record); }
  catch (e) { context.log.error(e); return lib.json(context, 502, { ok: false, message: `Could not write the record to blob storage (${e.message.slice(0, 120)}). Nothing saved.` }); }
  lib.json(context, 200, { ok: true, saved_to, received_at: record.received_at, submitted_by: s.email, organisation: org.slug, delivery: rec.delivery || null });
});
