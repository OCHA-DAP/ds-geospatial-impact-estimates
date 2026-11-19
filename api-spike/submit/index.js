const lib = require("../shared/lib");
module.exports = async function (context, req) {
  const s = lib.sessionFrom(req);
  if (!s) { context.res = { status: 401, headers: { "Content-Type": "application/json" }, body: { ok: false, message: "Sign in with an emailed link first." } }; return; }
  // Nothing is stored in the spike: echo what the registry would receive.
  context.res = { status: 200, headers: { "Content-Type": "application/json" },
    body: { ok: true, received_at: new Date().toISOString(), submitted_by: s.email, record: req.body || {} } };
};
