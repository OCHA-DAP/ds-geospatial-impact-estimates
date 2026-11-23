const lib = require("../shared/lib");
// "Request to join": an unregistered address asks an existing organisation's members to add them.
// Unauthenticated by design. Sends one note per member (each a separate single-recipient send),
// throttled per requester and per organisation. Nothing is written to the registry.
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
module.exports = lib.guarded(async function (context, req) {
  const b = (req.body && typeof req.body === "object") ? req.body : {};
  const email = String(b.email || "").trim().toLowerCase(), name = String(b.name || "").trim(), slug = String(b.slug || "");
  if (!EMAIL.test(email)) return lib.json(context, 400, { ok: false, message: "That does not look like an email address." });
  if (name.length < 1 || name.length > 120) return lib.json(context, 400, { ok: false, message: "Your name is required so the members know who is asking." });
  if (!lib.SLUG.test(slug)) return lib.json(context, 400, { ok: false, message: "Unknown organisation." });
  const rec = await lib.getJson(lib.orgRel(slug));
  if (!rec) return lib.json(context, 404, { ok: false, message: "Unknown organisation." });
  if (lib.memberOf(rec, email)) return lib.json(context, 200, { ok: true, message: "You are already a member. Enter your email on the sign-in page for a link." });
  if (lib.throttled(`join:${email}`) || lib.throttled(`join-org:${slug}`) || lib.throttled(`join-ip:${lib.clientIp(req)}`)) {
    return lib.json(context, 429, { ok: false, message: "A request was sent recently. Give the members a little time." });
  }
  let origin; try { origin = lib.origin(req); } catch (e) { context.log.error(e); return lib.json(context, 500, { ok: false, message: "Could not build the page link." }); }
  const html = `<p><b>${lib.escHtml(name)}</b> (${lib.escHtml(email)}) asks to join <b>${lib.escHtml(rec.organisation.name)}</b> on the damage analysis platform.</p>
<p>If they belong to your organisation, sign in and add them under Members on your organisation page:</p>
<p style="margin:20px 0"><a href="${origin}/form-spike/providers.html" style="background:#1e795f;color:#fff;padding:12px 18px;text-decoration:none;font-weight:600">Open the platform</a></p>
<p style="color:#5e6a6b;font-size:13px">If you do not know this person, ignore this email; nothing happens unless a member adds them. This is a test of the next-event platform.</p>`;
  for (const m of rec.members) await lib.sendNote(m.email, `[test] ${name} asks to join ${rec.organisation.name} on the damage analysis platform`, html);
  context.log(`join request from ${email} to ${slug} (${rec.members.length} members notified)`);
  lib.json(context, 200, { ok: true, message: `Request sent to the ${rec.members.length === 1 ? "member" : rec.members.length + " members"} of ${rec.organisation.name}. Once one of them adds you, a sign-in link arrives by email.` });
});
