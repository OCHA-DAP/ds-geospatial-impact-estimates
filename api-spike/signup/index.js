const lib = require("../shared/lib");
// Organisation sign-up. Unauthenticated by design: this is how a provider gets into the registry.
// It (1) validates the organisation fields, (2) makes sure Listmonk has a subscriber record for the
// contact so the relay can deliver (no list membership), (3) writes the organisation record and the
// per-address index to the registry on blob, (4) emails the contact the sign-in link.
// So registering and first sign-in are one step, and the emailed link proves the address.
// Spike shortcut: no staff approval. Anyone who registers can submit. The real build gates on review.
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const slugOf = (name) => name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 64);

function validate(b) {
  const errs = [];
  const org_name = String(b.org_name || "").trim();
  const contact = String(b.contact || "").trim().toLowerCase();
  const contact_name = String(b.contact_name || "").trim();
  const org_type = String(b.org_type || "");
  const licence = String(b.licence || "");
  const licence_url = String(b.licence_url || "").trim();
  const pub = String(b.public || "");
  if (org_name.length < 2 || org_name.length > 120) errs.push("organisation name must be 2 to 120 characters");
  const slug = slugOf(org_name);
  if (!lib.SLUG.test(slug)) errs.push("organisation name must contain at least one letter or digit");
  if (!EMAIL.test(contact)) errs.push("contact email does not look like an email address");
  if (contact_name.length < 1 || contact_name.length > 120) errs.push("contact name is required");
  if (!lib.ORG_TYPES.includes(org_type)) errs.push(`organisation type must be one of ${lib.ORG_TYPES.join(", ")}`);
  if (!lib.LICENCES.includes(licence)) errs.push(`licence must be one of ${lib.LICENCES.join(", ")}`);
  if (licence === "terms" && !/^https:\/\/\S+$/.test(licence_url)) errs.push("a link to the terms (https) is required for 'provider terms'");
  if (!["yes", "no"].includes(pub)) errs.push("'may be shown publicly' must be yes or no");
  const org = { slug, name: org_name, type: org_type, licence, licence_url: licence === "terms" ? licence_url : "",
    public: licence === "restricted" ? "no" : pub };
  return { errs, org, contact, contact_name };
}

module.exports = lib.guarded(async function (context, req) {
  const body = (req.body && typeof req.body === "object" && !Array.isArray(req.body)) ? req.body : null;
  if (!body) return lib.json(context, 400, { ok: false, message: "Body must be a JSON object." });
  const { errs, org, contact, contact_name } = validate(body);
  if (errs.length) return lib.json(context, 400, { ok: false, message: "Cannot register: " + errs.join("; ") + ".", errors: errs });

  // Ownership rules. An address belongs to one organisation: if it is already indexed to another
  // slug, refuse. A slug already registered can be rewritten only by its contact or by a session
  // that belongs to it.
  const mine = await lib.getJson(lib.contactRel(contact));
  if (mine && mine.slug !== org.slug) {
    const theirs = await lib.getJson(lib.orgRel(mine.slug));
    if (theirs && String(theirs.contact).toLowerCase() === contact) {
      return lib.json(context, 409, { ok: false, message: `${contact} is already registered as the contact for "${theirs.organisation.name}". Sign in and edit that registration, or use another address for a second organisation.` });
    }
  }
  const existing = await lib.getJson(lib.orgRel(org.slug));
  const session = lib.sessionFrom(req);
  const sessionRec = session ? await lib.registryFor(session.email) : null;
  const isMember = existing && (lib.memberOf(existing, contact) || (sessionRec && sessionRec.organisation.slug === org.slug));
  if (existing && !isMember) {
    // Someone else's organisation. Offer the join path instead of a dead end.
    return lib.json(context, 409, { ok: false, joinable: true, slug: org.slug, organisation: existing.organisation.name,
      members: lib.membersOf(existing).map((m) => lib.maskEmail(m.email)),
      message: `"${existing.organisation.name}" is already registered. Ask a member to add you, or send them a request from here.` });
  }
  if (lib.throttled(`signup:${contact}`) || lib.throttled(`signup-ip:${lib.clientIp(req)}`)) {
    return lib.json(context, 429, { ok: false, message: "One registration per minute. Try again shortly." });
  }

  const now = new Date().toISOString();
  const how = await lib.ensureSubscriber(contact, contact_name);
  // Members: on create, the registrant; on update, the existing list with this contact's name refreshed.
  const members = existing ? lib.membersOf(existing).map((m) => (String(m.email).toLowerCase() === contact ? { ...m, name: contact_name } : m)) : [{ email: contact, name: contact_name, added_at: now, added_by: "registration" }];
  if (!members.some((m) => String(m.email).toLowerCase() === contact)) members.push({ email: contact, name: contact_name, added_at: now, added_by: session ? session.email : "registration" });
  const record = { organisation: org, contact: existing ? existing.contact : contact, contact_name: existing ? existing.contact_name : contact_name, members,
    registered_at: existing ? existing.registered_at : now, updated_at: now };
  const saved_to = await lib.putJson(lib.orgRel(org.slug), record);
  await lib.putJson(lib.contactRel(contact), { email: contact, slug: org.slug, updated_at: now });
  const link = lib.linkFor(req, contact);
  await lib.sendLink(contact, link, `<b>${org.name.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]))}</b> is ${existing ? "updated" : "registered"} on the damage analysis platform. This link signs you in so you can submit.`);
  context.log(`signup ${contact} for ${org.slug} (subscriber ${how})`);
  lib.json(context, 200, { ok: true, message: `${existing ? "Updated" : "Registered"} ${org.name}. A sign-in link is on its way to ${contact}; open it to submit.`,
    organisation: org, subscriber: how, saved_to });
});
