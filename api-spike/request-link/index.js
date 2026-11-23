const lib = require("../shared/lib");
const NEUTRAL = "If that address is on the provider list, a sign-in link is on its way. Check your junk folder if nothing arrives within a few minutes.";
module.exports = lib.guarded(async function (context, req) {
  const email = String((req.body && req.body.email) || "").trim().toLowerCase();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    return lib.json(context, 400, { ok: false, message: "That does not look like an email address." });
  }
  if (!lib.throttled(`link:${email}`)) {
    try {
      if (await lib.onProviderList(email)) {
        await lib.sendLink(email, lib.linkFor(req, email));
        context.log(`link sent to ${email}`);
      } else {
        context.log(`refused ${email}: not on list ${lib.LIST_ID}`);
      }
    } catch (e) {
      // A broken dependency is a server error, not a quiet "nothing arrived".
      context.log.error(e);
      return lib.json(context, 502, { ok: false, message: "The sign-in service could not reach the mailing system. Try again in a minute." });
    }
  }
  lib.json(context, 200, { ok: true, message: NEUTRAL });
});
