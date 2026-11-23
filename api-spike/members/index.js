const lib = require("../shared/lib");
// Members of the signed-in user's organisation. add: the colleague is indexed to the organisation,
// gets a Listmonk subscriber record so mail can reach them, and receives a sign-in link at once.
// remove: dropped from the member list (the index is left pointing at the organisation; the list
// is the authority). A member cannot remove themself if they are the last one.
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
module.exports = lib.guarded(async function (context, req) {
  const s = lib.sessionFrom(req);
  if (!s) return lib.json(context, 401, { ok: false, message: "Sign in first." });
  const rec = await lib.registryFor(s.email);
  if (!rec) return lib.json(context, 403, { ok: false, message: "Your address is not a member of a registered organisation." });
  const b = (req.body && typeof req.body === "object") ? req.body : {};
  const action = String(b.action || ""), email = String(b.email || "").trim().toLowerCase(), name = String(b.name || "").trim();
  if (!EMAIL.test(email)) return lib.json(context, 400, { ok: false, message: "That does not look like an email address." });
  const now = new Date().toISOString(), slug = rec.organisation.slug;
  rec.members = lib.membersOf(rec); // normalise a pre-members record before any write
  if (action === "add") {
    if (name.length < 1 || name.length > 120) return lib.json(context, 400, { ok: false, message: "A name is required." });
    if (lib.memberOf(rec, email)) return lib.json(context, 200, { ok: true, message: `${email} is already a member.`, members: rec.members });
    const theirs = await lib.getJson(lib.contactRel(email));
    if (theirs && theirs.slug !== slug) {
      const other = await lib.getJson(lib.orgRel(theirs.slug));
      if (lib.memberOf(other, email)) return lib.json(context, 409, { ok: false, message: `${email} is already a member of "${other.organisation.name}". One organisation per address in this spike.` });
    }
    if (lib.throttled(`member-add:${slug}`)) return lib.json(context, 429, { ok: false, message: "One addition per minute per organisation. Try again shortly." });
    await lib.ensureSubscriber(email, name);
    rec.members.push({ email, name, added_at: now, added_by: s.email }); rec.updated_at = now;
    await lib.putJson(lib.orgRel(slug), rec);
    await lib.putJson(lib.contactRel(email), { email, slug, updated_at: now });
    await lib.sendLink(email, lib.linkFor(req, email), `${lib.escHtml(s.email)} added you to <b>${lib.escHtml(rec.organisation.name)}</b> on the damage analysis platform. This link signs you in.`,
      `[test] You were added to ${rec.organisation.name} on the damage analysis platform`);
    context.log(`member added ${email} to ${slug} by ${s.email}`);
    return lib.json(context, 200, { ok: true, message: `${name} (${email}) added; a sign-in link is on its way to them.`, members: rec.members });
  }
  if (action === "remove") {
    if (!lib.memberOf(rec, email)) return lib.json(context, 404, { ok: false, message: `${email} is not a member.` });
    if (rec.members.length === 1) return lib.json(context, 400, { ok: false, message: "An organisation keeps at least one member." });
    rec.members = rec.members.filter((m) => String(m.email).toLowerCase() !== email); rec.updated_at = now;
    await lib.putJson(lib.orgRel(slug), rec);
    context.log(`member removed ${email} from ${slug} by ${s.email}`);
    return lib.json(context, 200, { ok: true, message: `${email} removed.${email === s.email ? " You are signed out of the organisation." : ""}`, members: rec.members });
  }
  lib.json(context, 400, { ok: false, message: "action must be add or remove." });
});
