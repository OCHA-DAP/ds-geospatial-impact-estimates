const lib = require("../shared/lib");
// Organisation sign-up. Unauthenticated by design: this is how a provider gets onto the list.
// It (1) validates the organisation fields, (2) creates or updates the contact as a subscriber
// on the provider list with the organisation in its attributes, (3) writes an organisation record
// to the spike folder, (4) emails the contact the same sign-in link the sign-in page sends.
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

  // Who may write this organisation's record: a new slug is free for anyone; an existing one only
  // for its registered contact or a signed-in session that belongs to it.
  const rel = `${lib.ORG_PREFIX}/${org.slug}.json`;
  const existing = await lib.getJson(rel);
  const session = lib.sessionFrom(req);
  const sessionOrg = session ? lib.orgFrom(await lib.findSubscriber(session.email)) : null;
  if (existing && existing.contact !== contact && !(sessionOrg && sessionOrg.slug === org.slug)) {
    return lib.json(context, 409, { ok: false, message: `"${org.name}" is already registered by another address. Sign in with that address to change it, or ask the team to add you.` });
  }
  if (lib.throttled(`signup:${contact}`) || lib.throttled(`signup-ip:${lib.clientIp(req)}`)) {
    return lib.json(context, 429, { ok: false, message: "One registration per minute. Try again shortly." });
  }

  const now = new Date().toISOString();
  const how = await lib.upsertSubscriber(contact, contact_name, org);
  const record = { organisation: org, contact, contact_name, registered_at: existing ? existing.registered_at : now, updated_at: now,
    ...(existing && existing.contact !== contact ? { previous_contact: existing.contact } : {}) };
  const saved_to = await lib.putJson(rel, record);
  const link = lib.linkFor(req, contact);
  await lib.sendLink(contact, link, `<b>${org.name.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]))}</b> is ${existing ? "updated" : "registered"} on the damage analysis platform. This link signs you in so you can submit.`);
  context.log(`signup ${how} ${contact} for ${org.slug}`);
  lib.json(context, 200, { ok: true, message: `${existing ? "Updated" : "Registered"} ${org.name}. A sign-in link is on its way to ${contact}; open it to submit.`,
    organisation: org, subscriber: how, saved_to });
});
