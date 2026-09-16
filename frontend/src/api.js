const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

// A deployed build with VITE_API_BASE_URL unset calls its own origin, where the
// static host answers with index.html. Parsing that as JSON produces a useless
// "unexpected character at line 1 column 1", so name the actual cause instead.
function describeNonJson(response, body) {
  const contentType = response.headers.get('content-type') ?? 'unknown'
  if (body.trimStart().startsWith('<')) {
    return API_BASE
      ? `Expected JSON from ${API_BASE} but received HTML (${contentType}). ` +
        `Check that VITE_API_BASE_URL points at the API and not at the site itself.`
      : 'Expected JSON but received HTML. VITE_API_BASE_URL is not set, so the ' +
        'request went to this site instead of the API. Set it and redeploy.'
  }
  return `Expected JSON but received ${contentType}: ${body.slice(0, 200)}`
}

async function parseResponse(response) {
  const body = await response.text()

  let payload
  try {
    payload = JSON.parse(body)
  } catch {
    throw new Error(
      response.ok
        ? describeNonJson(response, body)
        : `Request failed (${response.status}). ${body.slice(0, 200)}`.trim(),
    )
  }

  if (response.ok) {
    return payload
  }
  throw new Error(payload.detail ?? JSON.stringify(payload) ?? 'Request failed.')
}

export async function fetchConfig() {
  const response = await fetch(`${API_BASE}/api/config`)
  return parseResponse(response)
}

export async function runPairStudy(payload) {
  const response = await fetch(`${API_BASE}/api/studies/pair`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })
  return parseResponse(response)
}

export async function runProfileStudy(payload) {
  const response = await fetch(`${API_BASE}/api/studies/profile`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })
  return parseResponse(response)
}

export async function runResidualStudy(payload) {
  const response = await fetch(`${API_BASE}/api/studies/residual`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })
  return parseResponse(response)
}
