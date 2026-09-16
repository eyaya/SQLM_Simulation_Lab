const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

async function parseResponse(response) {
  if (response.ok) {
    return response.json()
  }

  let detail = 'Request failed.'
  try {
    const payload = await response.json()
    detail = payload.detail ?? JSON.stringify(payload)
  } catch {
    detail = await response.text()
  }
  throw new Error(detail || 'Request failed.')
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
