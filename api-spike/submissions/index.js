const lib = require("../shared/lib");
// The signed-in organisation's submissions, as table rows: the records are read back from the
// spike folder and summarised. Scoped to the organisation (no cross-organisation listing).
module.exports = lib.guarded(async function (context, req) {
  const s = lib.sessionFrom(req);
  if (!s) return lib.json(context, 401, { ok: false, message: "Sign in first." });
  const rec = await lib.registryFor(s.email);
  if (!rec) return lib.json(context, 403, { ok: false, message: "Your address is not a member of a registered organisation." });
  const slug = rec.organisation.slug, prefix = `${lib.ORG_PREFIX}/`, cprefix = `${lib.CONTACT_PREFIX}/`;
  const all = await lib.listBlobs();
  const rel = (b) => b.name.replace(/^ds-geospatial-impact-estimates\/spike\/submissions\//, "");
  // Blob names are <date>/<slug>_<event>_<ts>.json; the slug is validated at write time so the
  // underscore split is reliable only on our own prefix, hence the exact-prefix test.
  const mine = all.filter((b) => { const r = rel(b); return !r.startsWith(prefix) && !r.startsWith(cprefix) && /^\d{4}-\d{2}-\d{2}\//.test(r) && r.slice(11).startsWith(`${slug}_`); });
  const rows = [];
  for (const b of mine.slice(-100).reverse()) {
    const r = rel(b);
    let d;
    try { d = await lib.getJson(r); } catch (e) { rows.push({ saved_to: r, error: e.message }); continue; }
    if (!d) { rows.push({ saved_to: r, error: "record vanished between listing and read" }); continue; }
    const f = d.form || {};
    rows.push({ saved_to: r, received_at: d.received_at, submitted_by: d.submitted_by, event: f.event, product: f.product, category: f.category, method: f.method,
      status: f.status, provider_version: f.provider_version, url: f.url, extent_url: f.extent_url, extent: f.extent, post_from: f.post_from, post_to: f.post_to,
      n_analysed: f.n_analysed, n_damaged: f.n_damaged, delivery: f.delivery });
  }
  lib.json(context, 200, { ok: true, organisation: rec.organisation, count: rows.length, submissions: rows });
});
