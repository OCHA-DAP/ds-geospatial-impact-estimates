const lib = require("../shared/lib");
function safeOrigin(req) { try { return lib.origin(req); } catch (e) { return null; } }
// Who is signed in and, from the provider list, which organisation they registered (null if none yet).
module.exports = lib.guarded(async function (context, req) {
  const s = lib.sessionFrom(req);
  const hit = s ? await lib.findSubscriber(s.email) : null;
  const org = lib.orgFrom(hit);
  lib.json(context, 200, { ...(s ? { email: s.email, name: (hit && hit.name) || "", exp: s.exp, via: s.via, org } : { email: null }), link_origin: safeOrigin(req) });
});
