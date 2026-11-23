const lib = require("../shared/lib");
function safeOrigin(req) { try { return lib.origin(req); } catch (e) { return null; } }
// Who is signed in and, from the registry on blob, which organisation they belong to.
// `org` is null both when none is registered and when the registry could not be read; the second
// case also carries `org_error`, so the pages show a failure instead of "not registered".
module.exports = lib.guarded(async function (context, req) {
  const s = lib.sessionFrom(req);
  if (!s) return lib.json(context, 200, { email: null, link_origin: safeOrigin(req) });
  let rec = null, org_error = null;
  try { rec = await lib.registryFor(s.email); }
  catch (e) { context.log.error(e); org_error = `could not read the registry: ${e.message}`; }
  const me = lib.memberEntry(rec, s.email);
  lib.json(context, 200, { email: s.email, name: (me && me.name) || "", exp: s.exp, via: s.via, org: rec ? rec.organisation : null,
    members: lib.membersOf(rec).map((m) => ({ email: m.email, name: m.name, added_at: m.added_at })), ...(org_error ? { org_error } : {}), link_origin: safeOrigin(req) });
});
