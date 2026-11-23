const lib = require("../shared/lib");
// Lists the spike's saved submissions so testers can see records land. Signed-in users only.
// Organisation records (the _organisations/ prefix) are listed separately.
module.exports = lib.guarded(async function (context, req) {
  const s = lib.sessionFrom(req);
  if (!s) return lib.json(context, 401, { ok: false, message: "Sign in first." });
  const all = await lib.listBlobs();
  const isOrg = (b) => b.name.includes(`/${lib.ORG_PREFIX}/`), isContact = (b) => b.name.includes(`/${lib.CONTACT_PREFIX}/`);
  const submissions = all.filter((b) => !isOrg(b) && !isContact(b)).reverse(), organisations = all.filter(isOrg);
  lib.json(context, 200, { ok: true, count: submissions.length, submissions, organisations });
});
