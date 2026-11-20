const lib = require("../shared/lib");
function safeOrigin(req) { try { return lib.origin(req); } catch (e) { return null; } }
module.exports = async function (context, req) {
  const s = lib.sessionFrom(req);
  context.res = { status: 200, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
    body: { ...(s ? { email: s.email, exp: s.exp, via: s.via } : { email: null }), link_origin: safeOrigin(req) } };
};
