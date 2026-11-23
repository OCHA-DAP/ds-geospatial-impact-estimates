const lib = require("../shared/lib");
function safeOrigin(req) { try { return lib.origin(req); } catch (e) { return null; } }
// Who is signed in and, from the provider list, which organisation they registered.
// `org` is null both when none is registered and when the list could not be read; the second case
// also carries `org_error`, so the pages can show a failure instead of "not registered".
module.exports = lib.guarded(async function (context, req) {
  const s = lib.sessionFrom(req);
  if (!s) return lib.json(context, 200, { email: null, link_origin: safeOrigin(req) });
  let hit = null, org_error = null;
  try { hit = await lib.findSubscriber(s.email); }
  catch (e) { context.log.error(e); org_error = `could not read the provider list: ${e.message}`; }
  lib.json(context, 200, { email: s.email, name: (hit && hit.name) || "", exp: s.exp, via: s.via, org: lib.orgFrom(hit), ...(org_error ? { org_error } : {}), link_origin: safeOrigin(req) });
});
