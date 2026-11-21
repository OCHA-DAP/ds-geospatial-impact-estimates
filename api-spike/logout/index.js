const lib = require("../shared/lib");
module.exports = lib.guarded(async function (context) {
  context.res = { status: 302, headers: { Location: "/form-spike/index.html", "Set-Cookie": lib.setCookie("", 0) } };
});
