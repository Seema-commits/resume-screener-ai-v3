/** "2026-11-14 09:30 UTC" - the API stores times in UTC. */
export function formatUtc(iso: string): string {
  return `${iso.slice(0, 16).replace('T', ' ')} UTC`
}

export function oneLine(text: string, max = 90): string {
  const flat = text.replace(/\s+/g, ' ').trim()
  return flat.length > max ? `${flat.slice(0, max - 1)}…` : flat
}
