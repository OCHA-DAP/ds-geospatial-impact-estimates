const lib = require("../shared/lib");
// Lists the spike's saved submissions so testers can see records land. Signed-in users only.
module.exports = async function (context, req) {
  const s = lib.sessionFrom(req);
  if (!s) { context.res = { status: 401, headers: { "Content-Type": "application/json" }, body: { ok: false, message: "Sign in first." } }; return; }
  const sas = lib.secrets().blob_sas;
  const u = `https://imb0chd0dev.blob.core.windows.net/projects?restype=container&comp=list&prefix=ds-geospatial-impact-estimates/spike/submissions/&${sas}`;
  const r = await fetch(u, { headers: { "x-ms-version": "2021-08-06" } });
  if (!r.ok) { context.res = { status: 502, headers: { "Content-Type": "application/json" }, body: { ok: false, message: `listing failed: HTTP ${r.status}` } }; return; }
  const xml = await r.text();
  const items = [...xml.matchAll(/<Blob><Name>([^<]+)<\/Name>.*?<Last-Modified>([^<]+)<\/Last-Modified>.*?<Content-Length>(\d+)<\/Content-Length>/gs)].map((m) => ({ name: m[1], modified: m[2], bytes: Number(m[3]) }));
  context.res = { status: 200, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" }, body: { ok: true, count: items.length, submissions: items.reverse() } };
};
