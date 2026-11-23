const lib = require("../shared/lib");
module.exports = lib.guarded(async function (context, req) {
  const claims = lib.verify(req.query && req.query.t, "link");
  if (!claims || !claims.email) {
    context.res = { status: 302, headers: { Location: "/form-spike/index.html?bad=1" } };
    return;
  }
  const session = lib.mint("session", { email: claims.email, via: "magic-link" }, lib.SESSION_TTL_S);
  context.res = { status: 302, headers: { Location: "/form-spike/submit.html", "Set-Cookie": lib.setCookie(session, lib.SESSION_TTL_S) } };
});
