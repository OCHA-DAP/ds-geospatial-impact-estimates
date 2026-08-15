// Event registry access + hash routing. The registry (platinum/events.json,
// published from events.yaml) is the single authority for which events exist.
// Routes: "#/e/<event_id>" is an event view; empty/other hash -> landing page.

export interface EventInfo {
  event_id: string;
  name: string;
  hazard: string;
  onset: string;
  countries: string[];
  bbox: [number, number, number, number];
  status: string;
  external_ids: Record<string, string>;
}

export async function fetchEvents(tok: any): Promise<EventInfo[]> {
  const r = await fetch(`${tok.base_url}/${tok.platinum_dir}/events.json?${tok.sas}`);
  if (!r.ok) throw new Error(`events.json fetch failed: HTTP ${r.status}`);
  const data = await r.json();
  if (!Array.isArray(data?.events)) throw new Error("events.json: malformed registry");
  return data.events as EventInfo[];
}

export function currentEventId(): string | null {
  // No trailing $ anchor: a hash like "#/e/foo/bar" (or "#/e/foo?whatever") still
  // captures "foo" here rather than falling through to null (-> the landing page,
  // silently). The registry is the only authority on whether "foo" is real — an
  // id that isn't in it renders the explicit unknown-event error card instead.
  const m = location.hash.match(/^#\/e\/([^/]+)/);
  return m ? m[1] : null;
}

// The ONE place an event-scoped platinum base URL is built.
export function eventDir(tok: any, eventId: string): string {
  return `${tok.base_url}/${tok.platinum_dir}/event=${eventId}`;
}
