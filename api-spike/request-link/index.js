const lib = require("../shared/lib");
const recent = new Map(); // best-effort throttle per instance: one link per address per minute
const NEUTRAL = "If that address is on the provider list, a sign-in link is on its way. Check your junk folder if nothing arrives within a few minutes.";
module.exports = async function (context, req) {
  const email = String((req.body && req.body.email) || "").trim().toLowerCase();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    context.res = { status: 400, headers: { "Content-Type": "application/json" }, body: { ok: false, message: "That does not look like an email address." } };
    return;
  }
  const last = recent.get(email) || 0;
  if (Date.now() - last > 60_000) {
    recent.set(email, Date.now());
    try {
      if (await lib.onProviderList(email)) {
        const link = `${lib.origin(req)}/api/redeem?t=${lib.mint({ email, list: lib.LIST_ID }, lib.LINK_TTL_S)}`;
        await lib.sendLink(email, link);
        context.log(`link sent to ${email}`);
      } else {
        context.log(`refused ${email}: not on list ${lib.LIST_ID}`);
      }
    } catch (e) {
      // A broken dependency is a server error, not a quiet "nothing arrived".
      context.log.error(e);
      context.res = { status: 502, headers: { "Content-Type": "application/json" }, body: { ok: false, message: "The sign-in service could not reach the mailing system. Try again in a minute." } };
      return;
    }
  }
  context.res = { status: 200, headers: { "Content-Type": "application/json" }, body: { ok: true, message: NEUTRAL } };
};
