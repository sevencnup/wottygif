<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { createMediaJob, getHealth, listMediaJobs, resolveApiUrl } from './api/client.js'

const MODE_OPTIONS = [
  {
    value: 'single_image',
    label: '单图模式',
    hint: '每张图片单独创建任务。',
    accept: 'image/*'
  },
  {
    value: 'multi_image',
    label: '多图模式',
    hint: '多张图片合成一个结果。',
    accept: 'image/*'
  },
  {
    value: 'video',
    label: '视频制作',
    hint: '视频素材进入制作队列。',
    accept: 'video/*'
  }
]

const PANEL_TABS = [
  { value: 'assets', label: '素材' },
  { value: 'jobs', label: '队列' }
]

const health = ref('checking')
const mode = ref('single_image')
const quality = ref(3)
const assets = ref([])
const jobs = ref([])
const isSubmitting = ref(false)
const errorMessage = ref('')
const queueMessage = ref('')
const fileInput = ref(null)
const mobilePanel = ref('assets')
let assetSequence = 0
let jobsRefreshTimer = null

const modeMeta = computed(
  () => MODE_OPTIONS.find((option) => option.value === mode.value) ?? MODE_OPTIONS[0]
)

const canSubmit = computed(() => {
  if (mode.value === 'multi_image') {
    return assets.value.length >= 2
  }
  return assets.value.length >= 1
})

const totalSizeLabel = computed(() => {
  const total = assets.value.reduce((sum, asset) => sum + asset.size_bytes, 0)
  return formatBytes(total)
})

const queueSummary = computed(() => {
  if (!assets.value.length) {
    return '等待素材'
  }

  if (mode.value === 'single_image') {
    return `${assets.value.length} 张单独提交`
  }

  if (mode.value === 'multi_image') {
    return `${assets.value.length} 张合成 1 个任务`
  }

  return `${assets.value.length} 个视频待提交`
})

const submitHint = computed(() => {
  if (health.value === 'offline') {
    return '后端未连接，提交会失败。'
  }
  if (mode.value === 'multi_image' && assets.value.length < 2) {
    return '多图模式至少需要 2 张图片。'
  }
  if (!assets.value.length) {
    return '先加入素材。'
  }
  return '可以直接生成 GIF。'
})

const cleanupAssetUrl = (asset) => {
  if (asset.preview_url) {
    URL.revokeObjectURL(asset.preview_url)
  }
}

const resetAssets = (options = { clearMessage: true }) => {
  assets.value.forEach(cleanupAssetUrl)
  assets.value = []
  if (options.clearMessage) {
    queueMessage.value = ''
  }
}

const refreshJobs = async () => {
  jobs.value = await listMediaJobs()
}

const checkHealth = async () => {
  try {
    const result = await getHealth()
    health.value = result.status
  } catch (error) {
    health.value = 'offline'
    errorMessage.value = error.message
  }
}

const isAcceptedFile = (file) => {
  if (mode.value === 'video') {
    return file.type.startsWith('video/')
  }
  return file.type.startsWith('image/')
}

const createAsset = (file, origin) => {
  assetSequence += 1

  return {
    id: `${Date.now()}-${assetSequence}`,
    name: file.name || `clipboard-${assetSequence}.${file.type.split('/')[1] || 'bin'}`,
    kind: file.type.startsWith('video/') ? 'video' : 'image',
    origin,
    mime_type: file.type || 'application/octet-stream',
    size_bytes: file.size || 1,
    preview_url: file.type.startsWith('image/') ? URL.createObjectURL(file) : '',
    file
  }
}

const addFiles = (files, origin) => {
  const nextAssets = []
  const rejected = []

  files.forEach((file) => {
    if (isAcceptedFile(file)) {
      nextAssets.push(createAsset(file, origin))
    } else {
      rejected.push(file.name || 'unnamed file')
    }
  })

  if (!nextAssets.length && rejected.length) {
    errorMessage.value = `当前模式不支持这些素材: ${rejected.join(', ')}`
    return
  }

  assets.value = [...assets.value, ...nextAssets]
  queueMessage.value = ''
  mobilePanel.value = 'assets'

  if (rejected.length) {
    errorMessage.value = `已跳过不匹配模式的素材: ${rejected.join(', ')}`
  } else {
    errorMessage.value = ''
  }
}

const extractClipboardFiles = (event) => {
  const directFiles = Array.from(event.clipboardData?.files || [])
  if (directFiles.length) {
    return directFiles
  }

  const items = Array.from(event.clipboardData?.items || [])
  return items
    .filter((item) => item.kind === 'file')
    .map((item) => item.getAsFile())
    .filter(Boolean)
}

const handlePaste = (event) => {
  const files = extractClipboardFiles(event)

  if (!files.length) {
    errorMessage.value = '剪贴板里没有可用文件。'
    return
  }

  event.preventDefault()
  addFiles(files, 'paste')
}

const handleGlobalPaste = (event) => {
  handlePaste(event)
}

const handleFileSelect = (event) => {
  const files = Array.from(event.target.files || [])
  if (files.length) {
    addFiles(files, 'upload')
  }
  event.target.value = ''
}

const handleDrop = (event) => {
  event.preventDefault()
  const files = Array.from(event.dataTransfer?.files || [])
  if (files.length) {
    addFiles(files, 'upload')
  }
}

const openPicker = () => {
  fileInput.value?.click()
}

const removeAsset = (assetId) => {
  const asset = assets.value.find((item) => item.id === assetId)
  if (asset) {
    cleanupAssetUrl(asset)
  }
  assets.value = assets.value.filter((item) => item.id !== assetId)
}

const applyModeRules = (nextMode) => {
  mode.value = nextMode

  const expectedKind = mode.value === 'video' ? 'video' : 'image'
  const keptAssets = assets.value.filter((asset) => asset.kind === expectedKind)
  const removedAssets = assets.value.filter((asset) => asset.kind !== expectedKind)

  removedAssets.forEach(cleanupAssetUrl)
  assets.value = keptAssets
  queueMessage.value = ''

  if (removedAssets.length) {
    errorMessage.value = '模式已切换，不匹配的素材已经自动移除。'
  } else {
    errorMessage.value = ''
  }
}

const createPayloadForAssets = (selectedAssets) => ({
  mode: mode.value,
  quality: quality.value,
  assets: selectedAssets
})

const submitJob = async () => {
  errorMessage.value = ''
  queueMessage.value = ''

  if (!canSubmit.value) {
    errorMessage.value =
      mode.value === 'multi_image' ? '多图模式至少需要 2 张图片。' : '请先添加素材。'
    return
  }

  isSubmitting.value = true

  try {
    let createdJobs
    if (mode.value === 'single_image' || mode.value === 'video') {
      createdJobs = await Promise.all(
        assets.value.map((asset) => createMediaJob(createPayloadForAssets([asset])))
      )
    } else {
      createdJobs = [await createMediaJob(createPayloadForAssets(assets.value))]
    }

    await refreshJobs()
    const failedJob = createdJobs.find((job) => job.status === 'failed')
    if (failedJob) {
      throw new Error(failedJob.error_message || '生成失败，请查看任务状态。')
    }

    queueMessage.value = `已生成 ${createdJobs.length} 个 GIF 成品。`
    resetAssets({ clearMessage: false })
    await checkHealth()
    mobilePanel.value = 'jobs'
  } catch (error) {
    errorMessage.value = error.message
    await refreshJobs()
    mobilePanel.value = 'jobs'
  } finally {
    isSubmitting.value = false
  }
}

const formatBytes = (size) => {
  if (size < 1024) {
    return `${size} B`
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`
  }
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

const formatJobMode = (jobMode) => {
  return MODE_OPTIONS.find((item) => item.value === jobMode)?.label ?? jobMode
}

const formatJobStatus = (status) =>
  ({
    queued: '等待中',
    processing: '生成中',
    completed: '已完成',
    failed: '失败'
  })[status] ?? status

onMounted(async () => {
  window.addEventListener('paste', handleGlobalPaste)
  await checkHealth()
  await refreshJobs()
  jobsRefreshTimer = window.setInterval(() => {
    if (jobs.value.some((job) => ['queued', 'processing'].includes(job.status))) {
      refreshJobs().catch(() => {})
    }
  }, 2000)
})

onBeforeUnmount(() => {
  window.removeEventListener('paste', handleGlobalPaste)
  if (jobsRefreshTimer) {
    window.clearInterval(jobsRefreshTimer)
  }
  assets.value.forEach(cleanupAssetUrl)
})
</script>

<template>
  <main class="app-shell" @dragover.prevent @drop="handleDrop">
    <section class="workspace">
      <header class="hero">
        <div class="hero-copy">
          <p class="eyebrow">WottyGIF Studio</p>
          <h1>媒体工作台</h1>
          <p class="hero-note">粘贴图片或视频，直接生成、预览并下载 GIF。</p>
        </div>
        <div class="hero-side">
          <div class="hero-status">
            <span :class="['status', health]">{{ health }}</span>
            <p class="mode-hint">{{ modeMeta.hint }}</p>
          </div>
          <div class="hero-metrics">
            <div>
              <span>模式</span>
              <strong>{{ modeMeta.label }}</strong>
            </div>
            <div>
              <span>素材</span>
              <strong>{{ assets.length }} 个</strong>
            </div>
            <div>
              <span>队列</span>
              <strong>{{ jobs.length }} 条</strong>
            </div>
          </div>
        </div>
      </header>

      <section class="studio-grid">
        <form class="control-panel" @submit.prevent="submitJob">
          <div class="mode-strip">
            <button
              v-for="option in MODE_OPTIONS"
              :key="option.value"
              class="mode-card"
              :class="{ active: option.value === mode }"
              type="button"
              @click="applyModeRules(option.value)"
            >
              <strong>{{ option.label }}</strong>
              <span>{{ option.hint }}</span>
            </button>
          </div>

          <div class="field-group">
            <label class="field">
              <span>生成质量</span>
              <div class="quality-box">
                <input v-model="quality" type="range" min="1" max="5" step="1" />
                <strong>Lv.{{ quality }}</strong>
              </div>
            </label>
          </div>

          <div class="paste-zone" tabindex="0">
            <div class="paste-copy">
              <span class="paste-badge">全页粘贴</span>
              <h2>粘贴、拖入或选择素材</h2>
              <p>整页直接按 Ctrl+V 也会识别，不用先点输入框。</p>
            </div>

            <div class="paste-actions">
              <button class="secondary-button" type="button" @click="openPicker">选择素材</button>
              <button class="ghost-button" type="button" @click="resetAssets" :disabled="!assets.length">
                清空
              </button>
            </div>

            <input
              ref="fileInput"
              class="hidden-input"
              type="file"
              :accept="modeMeta.accept"
              :multiple="true"
              @change="handleFileSelect"
            />
          </div>

          <div class="summary-bar">
            <div>
              <span class="summary-label">当前素材</span>
              <strong>{{ assets.length }} 个</strong>
            </div>
            <div>
              <span class="summary-label">总大小</span>
              <strong>{{ totalSizeLabel }}</strong>
            </div>
            <div>
              <span class="summary-label">提交结果</span>
              <strong>{{ queueSummary }}</strong>
            </div>
          </div>

          <p v-if="errorMessage" class="message error">{{ errorMessage }}</p>
          <p v-if="queueMessage" class="message success">{{ queueMessage }}</p>

          <div class="submit-row">
            <button class="primary-button" type="submit" :disabled="isSubmitting">
              {{ isSubmitting ? '生成中...' : '开始生成' }}
            </button>
            <p class="submit-hint">{{ submitHint }}</p>
          </div>
        </form>

        <section class="side-stage">
          <div class="mobile-panel-switch" role="tablist" aria-label="移动端面板切换">
            <button
              v-for="tab in PANEL_TABS"
              :key="tab.value"
              class="panel-tab"
              :class="{ active: mobilePanel === tab.value }"
              type="button"
              @click="mobilePanel = tab.value"
            >
              {{ tab.label }}
            </button>
          </div>

          <section class="preview-panel" :class="{ mobileHidden: mobilePanel !== 'assets' }">
            <div class="panel-head">
              <h2>素材预览</h2>
              <span>{{ modeMeta.label }}</span>
            </div>

            <div v-if="assets.length" class="asset-grid">
              <article v-for="asset in assets" :key="asset.id" class="asset-card">
                <div class="asset-preview">
                  <img v-if="asset.preview_url" :src="asset.preview_url" :alt="asset.name" />
                  <div v-else class="video-placeholder">VIDEO</div>
                </div>
                <div class="asset-meta">
                  <strong>{{ asset.name }}</strong>
                  <span>{{ asset.origin === 'paste' ? '粘贴' : '上传' }} · {{ formatBytes(asset.size_bytes) }}</span>
                </div>
                <button class="remove-button" type="button" @click="removeAsset(asset.id)">移除</button>
              </article>
            </div>

            <div v-else class="empty-preview">
              <p>这里会显示刚加入的素材。</p>
            </div>
          </section>

          <section class="jobs-panel" :class="{ mobileHidden: mobilePanel !== 'jobs' }">
            <div class="panel-head">
              <h2>任务队列</h2>
              <span>{{ jobs.length }} 条</span>
            </div>

            <div v-if="jobs.length" class="job-list">
              <article v-for="job in jobs" :key="job.id" class="job-card">
                <img
                  v-if="job.status === 'completed' && job.result_url"
                  class="job-result-preview"
                  :src="resolveApiUrl(job.result_url)"
                  :alt="job.result_name"
                />
                <div class="job-main">
                  <strong>{{ job.source_name }}</strong>
                  <span>{{ formatJobMode(job.mode) }} · 质量 {{ job.quality }} · {{ job.asset_count }} 个素材</span>
                  <span v-if="job.error_message" class="job-error">{{ job.error_message }}</span>
                </div>
                <div class="job-actions">
                  <em :class="`job-status ${job.status}`">{{ formatJobStatus(job.status) }}</em>
                  <a
                    v-if="job.status === 'completed' && job.result_url"
                    class="result-button"
                    :href="resolveApiUrl(job.result_url)"
                    :download="job.result_name"
                  >
                    下载 GIF
                  </a>
                </div>
              </article>
            </div>

            <p v-else class="empty-jobs">暂无任务</p>
          </section>
        </section>
      </section>
    </section>
  </main>
</template>
