/**
 * Reads a server-sent-events body (event: name / data: json) from a
 * fetch response. EventSource can't POST files, so the scan upload uses
 * fetch and this reader.
 */

export interface SseEvent {
  event: string
  data: unknown
}

/** Splits complete events off the front of a buffer. */
export function parseSse(buffer: string): { events: SseEvent[]; rest: string } {
  const blocks = buffer.split('\n\n')
  const rest = blocks.pop() ?? ''
  const events: SseEvent[] = []

  for (const block of blocks) {
    let event = 'message'
    const data: string[] = []
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
    }
    if (data.length) events.push({ event, data: JSON.parse(data.join('\n')) })
  }
  return { events, rest }
}

export async function* readSse(response: Response): AsyncGenerator<SseEvent> {
  const reader = response.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const { events, rest } = parseSse(buffer)
    buffer = rest
    yield* events
  }
  if (buffer.trim()) yield* parseSse(`${buffer}\n\n`).events
}
