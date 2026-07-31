const API_BASE = import.meta.env.VITE_API_BASE || ''

const request = async (path, options = {}) => {
  let response

  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers
      },
      ...options
    })
  } catch (error) {
    throw new Error('无法连接后端服务，请先启动 FastAPI。')
  }

  let data = null
  const contentType = response.headers.get('content-type') || ''

  if (contentType.includes('application/json')) {
    data = await response.json()
  } else {
    data = await response.text()
  }

  if (!response.ok) {
    const detail =
      typeof data === 'string'
        ? data
        : data?.detail
          ? Array.isArray(data.detail)
            ? data.detail.map((item) => item.msg || String(item)).join('; ')
            : data.detail
          : `Request failed: ${response.status}`

    throw new Error(detail)
  }

  return data
}

export const getHealth = () => request('/api/health')

export const createMediaJob = (payload) =>
  request('/api/media/jobs', {
    method: 'POST',
    body: JSON.stringify(payload)
  })

export const listMediaJobs = () => request('/api/media/jobs')
