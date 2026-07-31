const API_BASE = import.meta.env.VITE_API_BASE || ''

const request = async (path, options = {}) => {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers
    },
    ...options
  })

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }

  return response.json()
}

export const getHealth = () => request('/api/health')

export const createMediaJob = (payload) =>
  request('/api/media/jobs', {
    method: 'POST',
    body: JSON.stringify(payload)
  })

export const listMediaJobs = () => request('/api/media/jobs')
