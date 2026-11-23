const lib = require("../shared/lib");
// Email-first sign-in. Unlike the earlier neutral reply, this says whether the address is in the
// registry, because the page branches on it: known address → link sent; unknown → registration.
// That lets anyone test whether an address is registered (one probe per address per minute per
// instance). Accepted for the spike at the user's request; see the local security note.
module.exports = lib.guarded(async function (context, req) {
  const email = String((req.body && req.body.email) || "").trim().toLowerCase();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    return lib.json(context, 400, { ok: false, message: "That does not look like an email address." });
  }
  let rec;
  try { rec = await lib.registryFor(email); }
  catch (e) { context.log.error(e); return lib.json(context, 502, { ok: false, message: `The registry could not be read (${e.message.slice(0, 120)}). Try again in a minute.` }); }
  if (!rec) {
    context.log(`unknown ${email}: sent to registration`);
    return lib.json(context, 200, { ok: true, registered: false, message: "That address is not registered yet. Register your organisation first; the sign-in link follows." });
  }
  if (lib.throttled(`link:${email}`)) {
    return lib.json(context, 200, { ok: true, registered: true, sent: false, message: `A link went to ${email} less than a minute ago. Check your inbox and junk folder, or try again shortly.` });
  }
  try {
    // One address in, one link out, to that address only.
    await lib.sendLink(email, lib.linkFor(req, email));
    context.log(`link sent to ${email}`);
  } catch (e) {
    context.log.error(e);
    return lib.json(context, 502, { ok: false, message: `The sign-in link could not be sent (${e.message.slice(0, 120)}). Try again in a minute.` });
  }
  lib.json(context, 200, { ok: true, registered: true, sent: true, organisation: rec.organisation.name,
    message: `A sign-in link is on its way to ${email} for ${rec.organisation.name}. Open it to continue; it works for 15 minutes.` });
});
