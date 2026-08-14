// Landing page ("/" i.e. empty hash): one card per event from the registry.
// Also the unknown-event error card — an explicit failure state, never a
// blank map and never a silent fallback to another event.

import type { EventInfo } from "./events";

const card = (ev: EventInfo) => `
  <a class="event-card" href="#/e/${ev.event_id}">
    <span class="event-status event-status-${ev.status}">${ev.status}</span>
    <h2>${ev.name}</h2>
    <p>${ev.hazard} · onset ${ev.onset} · ${ev.countries.join(", ")}</p>
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
      <p class="sub">"${eventId}" is not in the event registry. Available events:</p>
      ${events.map(card).join("")}
    </div>`;
  container.hidden = false;
}
