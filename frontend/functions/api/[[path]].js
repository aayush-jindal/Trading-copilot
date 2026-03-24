const BACKEND = 'https://trading-copilot-apq1.onrender.com'

export async function onRequest(context) {
  const { request, params } = context

  const path = params.path ? params.path.join('/') : ''
  const origin = new URL(request.url)
  const targetUrl = `${BACKEND}/${path}${origin.search}`

  const proxyRequest = new Request(targetUrl, {
    method: request.method,
    headers: request.headers,
    body: request.method !== 'GET' && request.method !== 'HEAD'
      ? request.body
      : undefined,
    redirect: 'follow',
    duplex: 'half',
  })

  const response = await fetch(proxyRequest)

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  })
}
