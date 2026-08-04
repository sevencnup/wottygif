const API_BASE = import.meta.env.VITE_API_BASE || ''
const DEVICE_STORAGE_KEY = 'wottygif-device-id'

const createDeviceId = () => {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID()
  }
  return `device-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

const getDeviceId = () => {
  try {
    const savedId = window.localStorage.getItem(DEVICE_STORAGE_KEY)
    if (savedId) {
      return savedId
    }
    const nextId = createDeviceId()
    window.localStorage.setItem(DEVICE_STORAGE_KEY, nextId)
    return nextId
  } catch {
    return createDeviceId()
  }
}

const DEVICE_ID = getDeviceId()

const request = async (path, options = {}) => {
  let response

  try {
    const headers = {
      'X-WottyGIF-Device-ID': DEVICE_ID,
      ...options.headers
    }
    if (!(options.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json'
    }

    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers
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

export const createMediaJob = ({ mode, quality, assets, videoOptions = null, imageCropOptions = null }) => {
  const formData = new FormData()
  formData.append('mode', mode)
  formData.append('quality', String(quality))
  if (mode === 'video' && videoOptions) {
    Object.entries(videoOptions).forEach(([key, value]) => {
      if (value !== null && value !== '' && value !== undefined) {
        formData.append(key, String(value))
      }
    })
  }
  if (mode !== 'video' && imageCropOptions) {
    formData.append('image_crop_options', JSON.stringify(imageCropOptions))
  }
  assets.forEach((asset) => {
    formData.append('origins', asset.origin)
    formData.append('files', asset.file, asset.name)
  })

  return request('/api/media/jobs', {
    method: 'POST',
    body: formData
  })
}

export const listMediaJobs = () => request('/api/media/jobs')

export const resolveApiUrl = (path) => {
  const separator = path.includes('?') ? '&' : '?'
  return `${API_BASE}${path}${separator}device_id=${encodeURIComponent(DEVICE_ID)}`
}
