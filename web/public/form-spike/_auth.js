// Throwaway spike: render the Static Web Apps identity (/.auth/me) into #auth.
(async function () {
  const box = document.getElementById("auth");
  if (!box) return;
  const q = new URLSearchParams(location.search);
  let r;
  try {
    r = await fetch("/.auth/me", { credentials: "include" });
  } catch (e) {
    box.innerHTML = '<span class="chip chip-warn">auth endpoint unreachable</span> ' + e;
    return;
  }
  if (!r.ok) { box.innerHTML = `<span class="chip chip-warn">/.auth/me returned ${r.status}</span> (expected when served outside Static Web Apps)`; return; }
  const data = await r.json();
  const p = data.clientPrincipal;
  const note = q.get("denied") ? '<p><span class="chip chip-warn">401</span> That page needs a signed-in user. Sign in below and try again.</p>'
    : q.get("forbidden") ? '<p><span class="chip chip-warn">403</span> Signed in, but that page needs the <code>provider</code> role, which only an invitation grants.</p>' : "";
  if (!p) {
    box.innerHTML = note + '<span class="chip chip-info">anonymous</span> Not signed in. '
      + '<code>/.auth/me</code> returned <code>clientPrincipal: null</code>.<br><br>'
      + '<a class="btn" href="/.auth/login/aad?post_login_redirect_uri=/form-spike/index.html">Sign in with a Microsoft account</a>'
      + '<a class="btn btn-2" href="/.auth/login/github?post_login_redirect_uri=/form-spike/index.html">Sign in with GitHub</a>';
    return;
  }
  box.innerHTML = note + '<span class="chip chip-ok">signed in</span> '
    + '<b>' + p.userDetails + '</b> via <code>' + p.identityProvider + '</code> · roles: <code>' + p.userRoles.join(", ") + '</code>'
    + ' · <a href="/.auth/logout?post_logout_redirect_uri=/form-spike/index.html">sign out</a>'
    + '<details style="margin-top:8px"><summary class="muted">raw clientPrincipal</summary><pre>' + JSON.stringify(p, null, 2) + '</pre></details>';
})();
