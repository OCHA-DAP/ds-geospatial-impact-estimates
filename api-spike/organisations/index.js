const lib = require("../shared/lib");
// Registered organisations, for the picker on the registration page. Unauthenticated: a new
// provider is not signed in yet. Names and types only; no members, no contacts.
module.exports = lib.guarded(async function (context) {
  const all = await lib.listBlobs();
  const rel = (b) => b.name.replace(/^ds-geospatial-impact-estimates\/spike\/submissions\//, "");
  const orgs = [];
  for (const b of all.filter((x) => rel(x).startsWith(`${lib.ORG_PREFIX}/`) && rel(x).endsWith(".json"))) {
    const rec = await lib.getJson(rel(b));
    if (!rec || !rec.organisation) continue;
    orgs.push({ slug: rec.organisation.slug, name: rec.organisation.name, type: rec.organisation.type, members: lib.membersOf(rec).length });
  }
  orgs.sort((a, b) => a.name.localeCompare(b.name));
  lib.json(context, 200, { ok: true, count: orgs.length, organisations: orgs });
});
