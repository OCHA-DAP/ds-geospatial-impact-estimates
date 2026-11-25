// Landing page ("/" i.e. empty hash): one card per event from the registry.
// Also the unknown-event error card — an explicit failure state, never a
// blank map and never a silent fallback to another event.

import type { EventInfo } from "./events";

// HTML-escape any registry- or URL-derived string before it lands in innerHTML
// or an attribute. The registry (events.json) is a data file, not trusted markup,
// and an unknown-event id is echoed straight from the URL — never assume either
// is already safe to interpolate.
export function esc(s: string): string {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

const card = (ev: EventInfo) => `
  <a class="event-card" href="#/e/${esc(ev.event_id)}">
    <span class="event-status event-status-${esc(ev.status)}">${esc(ev.status)}</span>
    <h2>${esc(ev.name)}</h2>
    <p>${esc(ev.hazard)} · onset ${esc(ev.onset)} · ${esc(ev.countries.join(", "))}</p>
  </a>`;

export function renderLanding(events: EventInfo[], container: HTMLElement): void {
  container.innerHTML = `
    <div class="landing-inner">
      <img src="/ocha_logo.svg" alt="OCHA" width="117" height="28" />
      <h1>Damage Exposure Viewer</h1>
      <p class="sub">Multi-source satellite damage estimates, by emergency event</p>
      ${events.map(card).join("")}
    </div>`;
  container.hidden = false;
}

export function renderEventError(eventId: string, events: EventInfo[], container: HTMLElement): void {
  container.innerHTML = `
    <div class="landing-inner">
      <h1>Unknown event</h1>
      <p class="sub">"${esc(eventId)}" is not in the event registry. Available events:</p>
      ${events.map(card).join("")}
    </div>`;
  container.hidden = false;
}

// The registry fetch/parse itself failed (token/network error, non-2xx, or
// events.json didn't validate) — a real error, distinct from "zero events".
export function renderBootError(message: string, container: HTMLElement): void {
  container.innerHTML = `
    <div class="landing-inner">
      <h1>Couldn't load the event registry</h1>
      <p class="sub">${esc(message)}</p>
    </div>`;
  container.hidden = false;
}

// The registry loaded fine and is well-formed, it just currently lists no
// events — information, not an error, and must not render identically to
// either failure state above.
export function renderEmptyRegistry(container: HTMLElement): void {
  container.innerHTML = `
    <div class="landing-inner">
      <img src="/ocha_logo.svg" alt="OCHA" width="117" height="28" />
      <h1>Damage Exposure Viewer</h1>
      <p class="sub">No events are registered yet.</p>
    </div>`;
  container.hidden = false;
}
