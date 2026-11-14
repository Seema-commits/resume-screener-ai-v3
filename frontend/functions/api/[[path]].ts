/**
 * Cloudflare Pages Function: forwards /api/* to the FastAPI backend on
 * Cloud Run, so the browser only ever talks to this site. That keeps the
 * session cookie first-party (SameSite=Lax, works in Safari too), needs
 * no CORS, and lets the CSP stay at connect-src 'self'.
 *
 * API_ORIGIN is set in Cloudflare Pages -> Settings -> Variables,
 * e.g. https://talentlens-api-xxxxx.a.run.app (no trailing slash).
 */

interface Context {
  request: Request
  env: { API_ORIGIN?: string }
}

export async function onRequest({ request, env }: Context): Promise<Response> {
  if (!env.API_ORIGIN?.startsWith('https://')) {
    return Response.json({ detail: 'The API address is not configured.' }, { status: 503 })
  }
  const url = new URL(request.url)
  // Only the path and query are taken from the visitor - never the host
  const target = new URL(url.pathname + url.search, env.API_ORIGIN)
  return fetch(new Request(target, request), { redirect: 'manual' })
}
