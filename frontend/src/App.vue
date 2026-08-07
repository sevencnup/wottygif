<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { CircleCheckBig, House, Maximize2, Pause, Play } from '@lucide/vue'
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
    hint: '单个视频最长支持 30 秒。',
    accept: 'video/*'
  }
]

const QUALITY_OPTIONS = [
  { value: 1, label: '低质量', hint: '较小文件', detail: '360p' },
  { value: 2, label: '轻量质量', hint: '日常分享', detail: '540p' },
  { value: 3, label: '标准质量', hint: '清晰度适中', detail: '720p' },
  { value: 4, label: '高质量', hint: '高清画质', detail: '1080p' }
]

const FPS_OPTIONS = [
  { value: 'auto', label: '跟随质量' },
  { value: '6', label: '6 FPS' },
  { value: '10', label: '10 FPS' },
  { value: '15', label: '15 FPS' }
]

const LOOP_OPTIONS = [
  { value: 'forever', label: '无限' },
  { value: 'once', label: '1 次' },
  { value: 'three', label: '3 次' }
]

const health = ref('checking')
const mode = ref('single_image')
const quality = ref(3)
const fpsSetting = ref('auto')
const loopSetting = ref('forever')
const clipStartSeconds = ref('0')
const clipEndSeconds = ref('')
const cropLeftPercent = ref('0')
const cropTopPercent = ref('0')
const cropWidthPercent = ref('100')
const cropHeightPercent = ref('100')
const cropIsDirty = ref(false)
const confirmedCropBox = ref({ left: 0, top: 0, width: 100, height: 100 })
const videoCropEditorOpen = ref(false)
const videoPlaybackStates = ref({})
const videoProgressStates = ref({})
const desktopPreviewVideo = ref(null)
const mobileSourceVideo = ref(null)
const mobilePreviewVideo = ref(null)
const imageCropActive = ref(false)
const imageCropEditorOpen = ref(false)
const imageCropStates = ref({})
const imageCropDraft = ref({ left: 0, top: 0, width: 100, height: 100 })
const imageCropDirty = ref(false)
const assetAspectRatios = ref({})
const assets = ref([])
const parkedAssetGroups = {
  image: { assets: [], selectedAssetId: '' },
  video: { assets: [], selectedAssetId: '' }
}
const jobs = ref([])
const isSubmitting = ref(false)
const errorMessage = ref('')
const queueMessage = ref('')
const fileInput = ref(null)
const mobilePage = ref('home')
const selectedJobId = ref('')
const selectedAssetId = ref('')
let assetSequence = 0
let jobsRefreshTimer = null
let cropInteraction = null
let imageCropInteraction = null

const MOBILE_PAGES = new Set(['home', 'configure', 'preview', 'jobs', 'detail'])

const isMobileViewport = () =>
  window.matchMedia('(max-width: 760px), ((max-height: 520px) and (pointer: coarse))').matches

const setMobilePage = (nextPage, { replace = false } = {}) => {
  if (!MOBILE_PAGES.has(nextPage) || mobilePage.value === nextPage) {
    return
  }

  mobilePage.value = nextPage
  if (!isMobileViewport()) {
    return
  }

  const currentDepth = Number(window.history.state?.wottygifMobileDepth || 0)
  const state = {
    ...window.history.state,
    wottygifMobilePage: nextPage,
    wottygifMobileDepth: replace ? currentDepth : currentDepth + 1
  }
  if (replace) {
    window.history.replaceState(state, '')
  } else {
    window.history.pushState(state, '')
  }
}

const goMobileBack = (fallbackPage) => {
  const depth = Number(window.history.state?.wottygifMobileDepth || 0)
  if (isMobileViewport() && depth > 0) {
    window.history.back()
    return
  }
  setMobilePage(fallbackPage, { replace: true })
}

const handleMobileHistory = (event) => {
  const targetPage = event.state?.wottygifMobilePage
  if (isMobileViewport() && MOBILE_PAGES.has(targetPage)) {
    mobilePage.value = targetPage
  }
}

const CROP_HANDLES = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w']

const modeMeta = computed(
  () => MODE_OPTIONS.find((option) => option.value === mode.value) ?? MODE_OPTIONS[0]
)

const healthLabel = computed(
  () =>
    ({
      checking: '连接中',
      ok: '在线',
      offline: '离线'
    })[health.value] ?? health.value
)

const canSubmit = computed(() => {
  if (mode.value === 'multi_image') {
    return assets.value.length >= 2
  }
  return assets.value.length >= 1
})

const completedJobs = computed(() =>
  jobs.value.filter((job) => job.status === 'completed' && job.result_url)
)

const previewAsset = computed(
  () => assets.value.find((asset) => asset.id === selectedAssetId.value) ?? assets.value[0] ?? null
)

const selectedAssetIndex = computed(() => {
  if (!previewAsset.value) {
    return -1
  }
  return assets.value.findIndex((asset) => asset.id === previewAsset.value.id)
})

const imageAssets = computed(() => assets.value.filter((asset) => asset.kind === 'image'))

const previewFrames = computed(() => assets.value.slice(0, 5))

const selectedJob = computed(() => jobs.value.find((job) => job.id === selectedJobId.value) ?? null)

const currentQualityMeta = computed(
  () => QUALITY_OPTIONS.find((option) => option.value === quality.value) ?? QUALITY_OPTIONS[0]
)

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

  return `${assets.value.length} 个视频待生成（最长 30 秒）`
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

const currentFpsLabel = computed(() => (quality.value <= 2 ? '6 FPS' : quality.value === 3 ? '10 FPS' : '12 FPS'))

const clipBounds = (mediaDuration = 0) => {
  const rawStart = Number(clipStartSeconds.value || 0)
  const requestedEnd = clipEndSeconds.value === '' ? null : Number(clipEndSeconds.value)
  const start = Number.isFinite(rawStart) ? Math.max(0, rawStart) : 0
  const knownDuration = Number.isFinite(mediaDuration) && mediaDuration > 0 ? mediaDuration : 0
  const fallbackEnd = requestedEnd !== null && Number.isFinite(requestedEnd) ? requestedEnd : 0
  const sourceEnd = knownDuration || fallbackEnd
  const end = requestedEnd !== null && Number.isFinite(requestedEnd)
    ? Math.min(Math.max(requestedEnd, start), sourceEnd)
    : sourceEnd
  return { start, end, duration: Math.max(end - start, 0) }
}

const formatPlaybackTime = (seconds) => {
  const safe = Math.max(0, Math.floor(Number.isFinite(seconds) ? seconds : 0))
  const minutes = String(Math.floor(safe / 60)).padStart(2, '0')
  const remain = String(safe % 60).padStart(2, '0')
  return `${minutes}:${remain}`
}

const videoProgress = (surface) => {
  const state = videoProgressStates.value[surface] ?? { currentTime: 0, duration: 0 }
  const bounds = clipBounds(state.duration)
  const elapsed = Math.min(Math.max(state.currentTime - bounds.start, 0), bounds.duration)
  const percent = bounds.duration > 0 ? (elapsed / bounds.duration) * 100 : 0
  return { elapsed, duration: bounds.duration, percent }
}

const videoClipLabel = (surface) => {
  if (mode.value !== 'video') {
    return '00:00 / 00:03'
  }
  const progress = videoProgress(surface)
  return `${formatPlaybackTime(progress.elapsed)} / ${formatPlaybackTime(progress.duration)}`
}

const videoTimelineStyle = (surface) => ({
  width: `${videoProgress(surface).percent}%`
})

const cropSummary = computed(() => {
  if (mode.value !== 'video') {
    return currentQualityMeta.value.detail
  }

  const left = Number(cropLeftPercent.value || 0)
  const top = Number(cropTopPercent.value || 0)
  const width = Number(cropWidthPercent.value || 100)
  const height = Number(cropHeightPercent.value || 100)
  if (left === 0 && top === 0 && width === 100 && height === 100) {
    return '完整画面'
  }
  return `${width}% x ${height}%`
})

const clamp = (value, minimum, maximum) => Math.min(Math.max(value, minimum), maximum)

const cropBox = computed(() => {
  const left = clamp(Number(cropLeftPercent.value) || 0, 0, 99)
  const top = clamp(Number(cropTopPercent.value) || 0, 0, 99)
  const width = clamp(Number(cropWidthPercent.value) || 100, 1, 100 - left)
  const height = clamp(Number(cropHeightPercent.value) || 100, 1, 100 - top)
  return { left, top, width, height }
})

const cropBoxStyle = computed(() => ({
  left: `${cropBox.value.left}%`,
  top: `${cropBox.value.top}%`,
  width: `${cropBox.value.width}%`,
  height: `${cropBox.value.height}%`
}))

const cropWidthMax = computed(() => Math.max(1, 100 - cropBox.value.left))
const cropHeightMax = computed(() => Math.max(1, 100 - cropBox.value.top))

const formatCropValue = (value) => `${Math.round(value * 10) / 10}`
const fullImageCrop = () => ({ left: 0, top: 0, width: 100, height: 100 })

const imageCropBox = computed(() => {
  const left = clamp(Number(imageCropDraft.value.left) || 0, 0, 99)
  const top = clamp(Number(imageCropDraft.value.top) || 0, 0, 99)
  const width = clamp(Number(imageCropDraft.value.width) || 100, 1, 100 - left)
  const height = clamp(Number(imageCropDraft.value.height) || 100, 1, 100 - top)
  return { left, top, width, height }
})

const imageCropBoxStyle = computed(() => ({
  left: `${imageCropBox.value.left}%`,
  top: `${imageCropBox.value.top}%`,
  width: `${imageCropBox.value.width}%`,
  height: `${imageCropBox.value.height}%`
}))

const currentAssetRatio = computed(() => {
  const assetId = previewAsset.value?.id
  return clamp(assetAspectRatios.value[assetId] || 4 / 3, 0.2, 5)
})

const stageStyleForRatio = (ratio, maxHeight, minWidth = 144) => ({
  aspectRatio: `${ratio}`,
  width: ratio < 1 ? `min(100%, ${Math.max(minWidth, Math.round(maxHeight * ratio))}px)` : '100%'
})

const imageCropEditorStyle = computed(() => stageStyleForRatio(currentAssetRatio.value, 300))
const desktopImageCropStageStyle = computed(() => ({
  aspectRatio: `${currentAssetRatio.value}`,
  width: `min(100%, ${currentAssetRatio.value * 100}cqh)`
}))
const imageCropWidthMax = computed(() => Math.max(1, 100 - imageCropBox.value.left))
const imageCropHeightMax = computed(() => Math.max(1, 100 - imageCropBox.value.top))

const currentImageCropState = computed(() => {
  const assetId = previewAsset.value?.id
  return assetId ? imageCropStates.value[assetId] ?? null : null
})

const showImageCropEditor = computed(
  () => imageCropActive.value && imageCropEditorOpen.value && previewAsset.value?.kind === 'image'
)

const appliedPreviewCrop = computed(() => {
  if (!previewAsset.value) {
    return fullImageCrop()
  }
  if (previewAsset.value.kind === 'video') {
    return videoCropEditorOpen.value ? fullImageCrop() : confirmedCropBox.value
  }
  const state = imageCropStates.value[previewAsset.value.id]
  return state?.status === 'confirmed' ? state : fullImageCrop()
})

const hasAppliedPreviewCrop = computed(() => {
  const crop = appliedPreviewCrop.value
  return crop.left !== 0 || crop.top !== 0 || crop.width !== 100 || crop.height !== 100
})

const appliedPreviewRatio = computed(() => {
  const crop = appliedPreviewCrop.value
  return currentAssetRatio.value * (crop.width / crop.height)
})

const mediaPreviewStageStyle = computed(() => stageStyleForRatio(appliedPreviewRatio.value, 420, 1))
const desktopMediaPreviewViewportStyle = computed(() => ({
  aspectRatio: `${appliedPreviewRatio.value}`
}))

const mediaPreviewTransformStyle = computed(() => {
  const crop = appliedPreviewCrop.value
  return {
    width: `${10000 / crop.width}%`,
    height: `${10000 / crop.height}%`,
    left: `${(-crop.left / crop.width) * 100}%`,
    top: `${(-crop.top / crop.height) * 100}%`
  }
})

const imageCropIncomplete = computed(() => {
  if (!imageCropActive.value) {
    return false
  }
  return (
    imageCropDirty.value ||
    imageAssets.value.some((asset) => !['confirmed', 'skipped'].includes(imageCropStates.value[asset.id]?.status))
  )
})

const imageCropProgress = computed(() => {
  const completed = imageAssets.value.filter((asset) =>
    ['confirmed', 'skipped'].includes(imageCropStates.value[asset.id]?.status)
  ).length
  return `${completed} / ${imageAssets.value.length}`
})

const setCropBox = ({ left, top, width, height }, options = { markDirty: true }) => {
  cropLeftPercent.value = formatCropValue(left)
  cropTopPercent.value = formatCropValue(top)
  cropWidthPercent.value = formatCropValue(width)
  cropHeightPercent.value = formatCropValue(height)
  if (options.markDirty) {
    cropIsDirty.value = true
  }
}

const constrainCropFields = () => {
  const left = clamp(Number(cropLeftPercent.value) || 0, 0, 99)
  const top = clamp(Number(cropTopPercent.value) || 0, 0, 99)
  const width = clamp(Number(cropWidthPercent.value) || 1, 1, 100 - left)
  const height = clamp(Number(cropHeightPercent.value) || 1, 1, 100 - top)
  setCropBox({ left, top, width, height })
}

const resetCrop = () => {
  setCropBox({ left: 0, top: 0, width: 100, height: 100 })
}

const confirmCrop = () => {
  constrainCropFields()
  confirmedCropBox.value = { ...cropBox.value }
  cropIsDirty.value = false
  videoCropEditorOpen.value = false
}

const cancelCropChanges = () => {
  setCropBox(confirmedCropBox.value, { markDirty: false })
  cropIsDirty.value = false
  videoCropEditorOpen.value = false
}

const openVideoCropEditor = () => {
  setCropBox(confirmedCropBox.value, { markDirty: false })
  cropIsDirty.value = false
  videoCropEditorOpen.value = true
}

const resetCropForNewVideo = () => {
  const fullFrame = { left: 0, top: 0, width: 100, height: 100 }
  setCropBox(fullFrame, { markDirty: false })
  confirmedCropBox.value = fullFrame
  cropIsDirty.value = false
  videoCropEditorOpen.value = true
  clipStartSeconds.value = '0'
  clipEndSeconds.value = ''
}

const updateVideoProgress = (video, surface) => {
  if (!surface) {
    return
  }
  videoProgressStates.value = {
    ...videoProgressStates.value,
    [surface]: {
      currentTime: Number.isFinite(video.currentTime) ? video.currentTime : 0,
      duration: Number.isFinite(video.duration) ? video.duration : 0
    }
  }
}

const handleVideoMetadata = (event, assetId = previewAsset.value?.id, surface = '') => {
  const video = event.currentTarget
  if (video.videoWidth > 0 && video.videoHeight > 0) {
    if (assetId) {
      assetAspectRatios.value = {
        ...assetAspectRatios.value,
        [assetId]: video.videoWidth / video.videoHeight
      }
    }
  }
  const bounds = clipBounds(video.duration)
  if (bounds.start < video.duration && (video.currentTime < bounds.start || video.currentTime >= bounds.end)) {
    video.currentTime = bounds.start
  }
  updateVideoProgress(video, surface)
}

const handleVideoTimeUpdate = (event, surface) => {
  const video = event.currentTarget
  const bounds = clipBounds(video.duration)
  if (!video.paused && video.currentTime < bounds.start) {
    video.currentTime = bounds.start
  } else if (!video.paused && bounds.duration > 0 && video.currentTime >= bounds.end) {
    if (Math.abs(video.currentTime - bounds.end) > 0.04) {
      video.currentTime = bounds.end
    }
    video.pause()
  }
  updateVideoProgress(video, surface)
}

const videoRefs = [
  desktopPreviewVideo,
  mobileSourceVideo,
  mobilePreviewVideo
]

const isVideoPlaying = (surface) => videoPlaybackStates.value[surface] === true

const setVideoPlaybackState = (surface, playing) => {
  videoPlaybackStates.value = {
    ...videoPlaybackStates.value,
    [surface]: playing
  }
}

const syncVideoPlaybackState = (event, surface) => {
  const currentVideo = event.currentTarget
  videoRefs.forEach((videoRef) => {
    const video = videoRef.value
    if (video && video !== currentVideo && !video.paused) {
      video.pause()
    }
  })
  updateVideoProgress(currentVideo, surface)
  setVideoPlaybackState(surface, !currentVideo.paused)
}

const stopVideoPlaybackState = (surface) => {
  setVideoPlaybackState(surface, false)
}

const toggleVideoPlayback = (video, surface) => {
  if (!video) {
    return
  }

  if (video.paused) {
    const bounds = clipBounds(video.duration)
    if (video.currentTime < bounds.start || video.currentTime >= bounds.end - 0.04) {
      video.currentTime = bounds.start
      updateVideoProgress(video, surface)
    }
    video.play().catch(() => {
      setVideoPlaybackState(surface, false)
    })
    return
  }

  video.pause()
}

const startCropInteraction = (event, handle) => {
  if (event.button !== undefined && event.button !== 0) {
    return
  }

  const stage = event.currentTarget.closest('.video-crop-stage')
  if (!stage) {
    return
  }

  cropInteraction = {
    handle,
    pointerId: event.pointerId,
    target: event.currentTarget,
    stageRect: stage.getBoundingClientRect(),
    startX: event.clientX,
    startY: event.clientY,
    startBox: { ...cropBox.value }
  }
  window.addEventListener('pointermove', moveCropInteraction, { passive: false })
  window.addEventListener('pointerup', finishCropInteraction)
  window.addEventListener('pointercancel', finishCropInteraction)
}

const moveCropInteraction = (event) => {
  if (!cropInteraction || cropInteraction.pointerId !== event.pointerId) {
    return
  }

  event.preventDefault()
  const { handle, stageRect, startX, startY, startBox } = cropInteraction
  const deltaX = ((event.clientX - startX) / stageRect.width) * 100
  const deltaY = ((event.clientY - startY) / stageRect.height) * 100
  const minimumSize = 8
  let { left, top, width, height } = startBox
  const right = startBox.left + startBox.width
  const bottom = startBox.top + startBox.height

  if (handle === 'move') {
    left = clamp(startBox.left + deltaX, 0, 100 - width)
    top = clamp(startBox.top + deltaY, 0, 100 - height)
  } else {
    if (handle.includes('e')) {
      width = clamp(startBox.width + deltaX, minimumSize, 100 - startBox.left)
    }
    if (handle.includes('s')) {
      height = clamp(startBox.height + deltaY, minimumSize, 100 - startBox.top)
    }
    if (handle.includes('w')) {
      left = clamp(startBox.left + deltaX, 0, right - minimumSize)
      width = right - left
    }
    if (handle.includes('n')) {
      top = clamp(startBox.top + deltaY, 0, bottom - minimumSize)
      height = bottom - top
    }
  }

  setCropBox({ left, top, width, height })
}

const finishCropInteraction = (event) => {
  if (!cropInteraction || cropInteraction.pointerId !== event.pointerId) {
    return
  }
  window.removeEventListener('pointermove', moveCropInteraction)
  window.removeEventListener('pointerup', finishCropInteraction)
  window.removeEventListener('pointercancel', finishCropInteraction)
  cropInteraction = null
  window.removeEventListener('pointermove', moveImageCropInteraction)
  window.removeEventListener('pointerup', finishImageCropInteraction)
  window.removeEventListener('pointercancel', finishImageCropInteraction)
  imageCropInteraction = null
}

const handleAssetImageLoad = (assetId, event) => {
  const image = event.currentTarget
  if (image.naturalWidth > 0 && image.naturalHeight > 0) {
    assetAspectRatios.value = {
      ...assetAspectRatios.value,
      [assetId]: image.naturalWidth / image.naturalHeight
    }
  }
}

const setImageCropDraft = ({ left, top, width, height }, options = { markDirty: true }) => {
  const safeLeft = clamp(Number(left) || 0, 0, 99)
  const safeTop = clamp(Number(top) || 0, 0, 99)
  imageCropDraft.value = {
    left: Number(formatCropValue(safeLeft)),
    top: Number(formatCropValue(safeTop)),
    width: Number(formatCropValue(clamp(Number(width) || 1, 1, 100 - safeLeft))),
    height: Number(formatCropValue(clamp(Number(height) || 1, 1, 100 - safeTop)))
  }
  if (options.markDirty) {
    imageCropDirty.value = true
    imageCropEditorOpen.value = true
  }
}

const loadImageCropAsset = (assetId) => {
  const state = imageCropStates.value[assetId]
  if (!state) {
    return
  }
  selectedAssetId.value = assetId
  setImageCropDraft(state, { markDirty: false })
  imageCropDirty.value = false
  errorMessage.value = ''
}

const registerImageCropAssets = (nextAssets) => {
  if (!imageCropActive.value) {
    return
  }
  const nextStates = { ...imageCropStates.value }
  nextAssets
    .filter((asset) => asset.kind === 'image')
    .forEach((asset) => {
      if (!nextStates[asset.id]) {
        nextStates[asset.id] = { status: 'pending', ...fullImageCrop() }
      }
    })
  imageCropStates.value = nextStates
}

const startImageCropWorkflow = async () => {
  if (!imageAssets.value.length) {
    openPicker()
    return
  }
  imageCropActive.value = true
  imageCropEditorOpen.value = true
  const nextStates = { ...imageCropStates.value }
  imageAssets.value.forEach((asset) => {
    if (!nextStates[asset.id]) {
      nextStates[asset.id] = { status: 'pending', ...fullImageCrop() }
    }
  })
  imageCropStates.value = nextStates
  const currentId = previewAsset.value?.kind === 'image' ? previewAsset.value.id : imageAssets.value[0].id
  loadImageCropAsset(currentId)
  await nextTick()
  document.querySelector('.mobile-source-stage.image-crop-stage, .desktop-preview-crop-stage')?.scrollIntoView({
    behavior: 'smooth',
    block: 'center'
  })
}

const canLeaveCurrentImageCrop = () => {
  if (!imageCropActive.value || !previewAsset.value || previewAsset.value.kind !== 'image') {
    return true
  }
  return !imageCropDirty.value && ['confirmed', 'skipped'].includes(currentImageCropState.value?.status)
}

const moveToImageCropAsset = (assetId) => {
  if (!canLeaveCurrentImageCrop()) {
    errorMessage.value = '请先确认裁剪或跳过当前图片，再切换素材。'
    return false
  }
  loadImageCropAsset(assetId)
  return true
}

const moveAfterImageCrop = () => {
  const currentIndex = selectedAssetIndex.value
  const immediateNext = imageAssets.value[currentIndex + 1]
  if (immediateNext) {
    loadImageCropAsset(immediateNext.id)
    return
  }
  const anyPending = imageAssets.value.find((asset) => imageCropStates.value[asset.id]?.status === 'pending')
  if (anyPending) {
    loadImageCropAsset(anyPending.id)
  } else {
    imageCropEditorOpen.value = false
    queueMessage.value = '全部图片裁剪已处理，可以进入预览。'
  }
}

const confirmCurrentImageCrop = () => {
  const assetId = previewAsset.value?.id
  if (!assetId) {
    return
  }
  imageCropStates.value = {
    ...imageCropStates.value,
    [assetId]: { status: 'confirmed', ...imageCropBox.value }
  }
  imageCropDirty.value = false
  errorMessage.value = ''
  moveAfterImageCrop()
}

const skipCurrentImageCrop = () => {
  const assetId = previewAsset.value?.id
  if (!assetId) {
    return
  }
  imageCropStates.value = {
    ...imageCropStates.value,
    [assetId]: { status: 'skipped', ...fullImageCrop() }
  }
  setImageCropDraft(fullImageCrop(), { markDirty: false })
  imageCropDirty.value = false
  errorMessage.value = ''
  moveAfterImageCrop()
}

const moveImageCropBy = (offset) => {
  const targetIndex = selectedAssetIndex.value + offset
  const target = imageAssets.value[targetIndex]
  if (!target) {
    return
  }
  moveToImageCropAsset(target.id)
}

const resetCurrentImageCrop = () => {
  setImageCropDraft(fullImageCrop())
}

const imageCropStatusLabel = (asset) => {
  if (asset.id === previewAsset.value?.id && imageCropDirty.value) {
    return '待确认'
  }
  const status = imageCropStates.value[asset.id]?.status
  return ({ pending: '待裁剪', confirmed: '已裁剪', skipped: '已跳过' })[status] ?? ''
}

const startImageCropInteraction = (event, handle) => {
  if (event.button !== undefined && event.button !== 0) {
    return
  }
  const stage = event.currentTarget.closest('.image-crop-stage')
  if (!stage) {
    return
  }
  imageCropInteraction = {
    handle,
    pointerId: event.pointerId,
    stageRect: stage.getBoundingClientRect(),
    startX: event.clientX,
    startY: event.clientY,
    startBox: { ...imageCropBox.value }
  }
  window.addEventListener('pointermove', moveImageCropInteraction, { passive: false })
  window.addEventListener('pointerup', finishImageCropInteraction)
  window.addEventListener('pointercancel', finishImageCropInteraction)
}

const moveImageCropInteraction = (event) => {
  if (!imageCropInteraction || imageCropInteraction.pointerId !== event.pointerId) {
    return
  }
  event.preventDefault()
  const { handle, stageRect, startX, startY, startBox } = imageCropInteraction
  const deltaX = ((event.clientX - startX) / stageRect.width) * 100
  const deltaY = ((event.clientY - startY) / stageRect.height) * 100
  const minimumSize = 8
  let { left, top, width, height } = startBox
  const right = startBox.left + startBox.width
  const bottom = startBox.top + startBox.height

  if (handle === 'move') {
    left = clamp(startBox.left + deltaX, 0, 100 - width)
    top = clamp(startBox.top + deltaY, 0, 100 - height)
  } else {
    if (handle.includes('e')) width = clamp(startBox.width + deltaX, minimumSize, 100 - startBox.left)
    if (handle.includes('s')) height = clamp(startBox.height + deltaY, minimumSize, 100 - startBox.top)
    if (handle.includes('w')) {
      left = clamp(startBox.left + deltaX, 0, right - minimumSize)
      width = right - left
    }
    if (handle.includes('n')) {
      top = clamp(startBox.top + deltaY, 0, bottom - minimumSize)
      height = bottom - top
    }
  }
  setImageCropDraft({ left, top, width, height })
}

const finishImageCropInteraction = (event) => {
  if (!imageCropInteraction || imageCropInteraction.pointerId !== event.pointerId) {
    return
  }
  window.removeEventListener('pointermove', moveImageCropInteraction)
  window.removeEventListener('pointerup', finishImageCropInteraction)
  window.removeEventListener('pointercancel', finishImageCropInteraction)
  imageCropInteraction = null
}

const cleanupAssetUrl = (asset) => {
  if (asset.preview_url) {
    URL.revokeObjectURL(asset.preview_url)
  }
}

const resetAssets = (options = { clearMessage: true }) => {
  const removedIds = new Set(assets.value.map((asset) => asset.id))
  assets.value.forEach(cleanupAssetUrl)
  assets.value = []
  selectedAssetId.value = ''
  assetAspectRatios.value = Object.fromEntries(
    Object.entries(assetAspectRatios.value).filter(([assetId]) => !removedIds.has(assetId))
  )
  if (mode.value !== 'video') {
    imageCropActive.value = false
    imageCropEditorOpen.value = false
    imageCropStates.value = Object.fromEntries(
      Object.entries(imageCropStates.value).filter(([assetId]) => !removedIds.has(assetId))
    )
    imageCropDirty.value = false
  }
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
    preview_url:
      file.type.startsWith('image/') || file.type.startsWith('video/') ? URL.createObjectURL(file) : '',
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

  const hadAssets = assets.value.length > 0
  assets.value = [...assets.value, ...nextAssets]
  if (imageCropActive.value && mode.value !== 'video') {
    registerImageCropAssets(nextAssets)
    if (canLeaveCurrentImageCrop() && nextAssets[0]) {
      loadImageCropAsset(nextAssets[0].id)
    }
  } else {
    selectedAssetId.value = nextAssets[0]?.id ?? selectedAssetId.value
  }
  if (mode.value === 'video' && !hadAssets && nextAssets.length) {
    resetCropForNewVideo()
  }
  queueMessage.value = ''

  if (rejected.length) {
    errorMessage.value = `已跳过不匹配模式的素材: ${rejected.join(', ')}`
  } else {
    errorMessage.value = ''
  }

  if (assets.value.length) {
    if (mobilePage.value === 'home') {
      setMobilePage('configure')
    }
    nextTick(() => {
      document.querySelector('.mobile-asset-workspace')?.scrollIntoView({ block: 'start' })
    })
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

const handlePickerAreaClick = (event) => {
  if (event.target.closest('button')) {
    return
  }
  openPicker()
}

const removeAsset = (assetId) => {
  const removedIndex = assets.value.findIndex((item) => item.id === assetId)
  const asset = assets.value.find((item) => item.id === assetId)
  if (asset) {
    cleanupAssetUrl(asset)
  }
  assets.value = assets.value.filter((item) => item.id !== assetId)
  const nextCropStates = { ...imageCropStates.value }
  delete nextCropStates[assetId]
  imageCropStates.value = nextCropStates
  const nextRatios = { ...assetAspectRatios.value }
  delete nextRatios[assetId]
  assetAspectRatios.value = nextRatios
  if (selectedAssetId.value === assetId) {
    const nextAsset = assets.value[Math.min(removedIndex, assets.value.length - 1)] ?? null
    selectedAssetId.value = nextAsset?.id ?? ''
    if (imageCropActive.value && nextAsset?.kind === 'image') {
      loadImageCropAsset(nextAsset.id)
    }
  }
  if (!imageAssets.value.length) {
    imageCropActive.value = false
    imageCropEditorOpen.value = false
    imageCropDirty.value = false
  }
}

const selectAsset = (assetId) => {
  if (imageCropActive.value && mode.value !== 'video') {
    moveToImageCropAsset(assetId)
    return
  }
  selectedAssetId.value = assetId
}

const moveSelectedAsset = (offset) => {
  if (imageCropActive.value && !canLeaveCurrentImageCrop()) {
    errorMessage.value = '请先确认裁剪或跳过当前图片，再调整顺序。'
    return
  }
  const index = selectedAssetIndex.value
  const targetIndex = index + offset
  if (index < 0 || targetIndex < 0 || targetIndex >= assets.value.length) {
    return
  }
  const reordered = [...assets.value]
  const [asset] = reordered.splice(index, 1)
  reordered.splice(targetIndex, 0, asset)
  assets.value = reordered
}

const applyModeRules = (nextMode) => {
  const previousKind = mode.value === 'video' ? 'video' : 'image'
  const nextKind = nextMode === 'video' ? 'video' : 'image'
  const hadCurrentAssets = assets.value.length > 0

  if (previousKind !== nextKind) {
    parkedAssetGroups[previousKind] = {
      assets: assets.value,
      selectedAssetId: selectedAssetId.value
    }
    const restoredGroup = parkedAssetGroups[nextKind]
    parkedAssetGroups[nextKind] = { assets: [], selectedAssetId: '' }
    assets.value = restoredGroup.assets
    selectedAssetId.value =
      restoredGroup.assets.some((asset) => asset.id === restoredGroup.selectedAssetId)
        ? restoredGroup.selectedAssetId
        : restoredGroup.assets[0]?.id ?? ''
  }

  mode.value = nextMode
  queueMessage.value = ''
  errorMessage.value =
    previousKind !== nextKind && hadCurrentAssets ? '已保留原模式素材，切换回来可以继续编辑。' : ''
}

const openHomePage = () => {
  setMobilePage('home')
}

const openModeConfigurator = (nextMode) => {
  applyModeRules(nextMode)
  setMobilePage('configure')
}

const openConfigurePage = () => {
  setMobilePage('configure')
}

const openPreviewPage = () => {
  if (!assets.value.length) {
    openPicker()
    return
  }
  if (mode.value === 'video' && cropIsDirty.value) {
    errorMessage.value = '请先确认画面裁剪，再进入预览。'
    openMobileVideoEditor()
    return
  }
  if (mode.value !== 'video' && imageCropIncomplete.value) {
    errorMessage.value = '请先确认或跳过每一张图片，再进入预览。'
    openMobileImageCropEditor()
    return
  }
  if (mode.value === 'video') {
    videoCropEditorOpen.value = false
  }
  errorMessage.value = ''
  setMobilePage('preview')
}

const confirmMobileCrop = () => {
  if (!assets.value.length || !previewAsset.value) {
    return
  }
  if (mode.value === 'video') {
    if (previewAsset.value.kind !== 'video') {
      return
    }
    confirmCrop()
    return
  }
  confirmCurrentImageCrop()
}

const openMobileVideoEditor = async () => {
  setMobilePage('configure')
  openVideoCropEditor()
  await nextTick()
  document.querySelector('.mobile-source-stage')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

const openMobileImageCropEditor = async () => {
  setMobilePage('configure')
  imageCropEditorOpen.value = true
  await nextTick()
  document.querySelector('.mobile-source-stage.image-crop-stage')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

const reopenImageCropEditor = async () => {
  imageCropEditorOpen.value = true
  await nextTick()
  document.querySelector('.desktop-preview-crop-stage')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

const openJobsPage = () => {
  setMobilePage('jobs')
  refreshJobs().catch(() => {})
}

const openJobDetail = (job) => {
  selectedJobId.value = job.id
  setMobilePage('detail')
}

const closeJobDetail = () => {
  goMobileBack('jobs')
}

const buildImageCropOptions = (selectedAssets) => {
  if (!imageCropActive.value || mode.value === 'video') {
    return null
  }
  return selectedAssets.map((asset) => {
    const state = imageCropStates.value[asset.id]
    if (!state || state.status === 'skipped') {
      return { skip: true }
    }
    return {
      crop_left_percent: state.left,
      crop_top_percent: state.top,
      crop_width_percent: state.width,
      crop_height_percent: state.height
    }
  })
}

const createPayloadForAssets = (selectedAssets) => ({
  mode: mode.value,
  quality: quality.value,
  assets: selectedAssets,
  videoOptions: mode.value === 'video' ? buildVideoOptions() : null,
  imageCropOptions: mode.value !== 'video' ? buildImageCropOptions(selectedAssets) : null
})

const parseNumberField = (value, fallback = null) => {
  if (value === '') {
    return fallback
  }
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : Number.NaN
}

const buildVideoOptions = () => {
  const start = parseNumberField(clipStartSeconds.value, 0)
  const end = parseNumberField(clipEndSeconds.value, null)
  const left = parseNumberField(cropLeftPercent.value, 0)
  const top = parseNumberField(cropTopPercent.value, 0)
  const width = parseNumberField(cropWidthPercent.value, 100)
  const height = parseNumberField(cropHeightPercent.value, 100)

  if ([start, left, top, width, height].some((value) => Number.isNaN(value))) {
    throw new Error('视频剪辑参数里有无效数字，请检查后重试。')
  }
  if (end !== null && Number.isNaN(end)) {
    throw new Error('结束时间格式不正确，请检查后重试。')
  }
  if (start < 0) {
    throw new Error('开始时间不能小于 0 秒。')
  }
  if (end !== null && end <= start) {
    throw new Error('结束时间必须大于开始时间。')
  }
  if (left < 0 || top < 0 || width <= 0 || height <= 0) {
    throw new Error('裁剪参数必须是正数，左和上不能小于 0。')
  }
  if (left + width > 100 || top + height > 100) {
    throw new Error('裁剪区域超出画面边界，请调整百分比。')
  }

  return {
    clip_start_seconds: start,
    clip_end_seconds: end,
    crop_left_percent: left,
    crop_top_percent: top,
    crop_width_percent: width,
    crop_height_percent: height
  }
}

const submitJob = async () => {
  errorMessage.value = ''
  queueMessage.value = ''

  if (!canSubmit.value) {
    errorMessage.value =
      mode.value === 'multi_image' ? '多图模式至少需要 2 张图片。' : '请先添加素材。'
    return
  }

  if (mode.value !== 'video' && imageCropIncomplete.value) {
    errorMessage.value = '请先确认或跳过每一张图片，再生成 GIF。'
    await openMobileImageCropEditor()
    return
  }

  isSubmitting.value = true

  try {
    if (mode.value === 'video') {
      if (cropIsDirty.value) {
        throw new Error('请先确认画面裁剪，再生成 GIF。')
      }
      buildVideoOptions()
      videoCropEditorOpen.value = false
    }

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
    if (createdJobs.length === 1) {
      selectedJobId.value = createdJobs[0].id
      setMobilePage('jobs')
      setMobilePage('detail')
    } else {
      selectedJobId.value = ''
      setMobilePage('jobs')
    }
  } catch (error) {
    errorMessage.value = error.message
    await refreshJobs()
    setMobilePage('jobs')
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

const downloadCompletedJobs = () => {
  if (!completedJobs.value.length) {
    return
  }
  window.location.assign(resolveApiUrl('/api/media/jobs/batch-download'))
}

const openJobPreview = (job) => {
  if (job.status !== 'completed' || !job.result_url) {
    return
  }
  window.open(resolveApiUrl(job.result_url), '_blank', 'noopener,noreferrer')
}

onMounted(async () => {
  window.addEventListener('paste', handleGlobalPaste)
  window.addEventListener('popstate', handleMobileHistory)
  if (isMobileViewport()) {
    window.history.replaceState(
      {
        ...window.history.state,
        wottygifMobilePage: mobilePage.value,
        wottygifMobileDepth: 0
      },
      ''
    )
  }
  await checkHealth()
  await refreshJobs()
  jobsRefreshTimer = window.setInterval(() => {
    refreshJobs().catch(() => {})
  }, 2000)
})

onBeforeUnmount(() => {
  window.removeEventListener('pointermove', moveCropInteraction)
  window.removeEventListener('pointerup', finishCropInteraction)
  window.removeEventListener('pointercancel', finishCropInteraction)
  cropInteraction = null
  window.removeEventListener('paste', handleGlobalPaste)
  window.removeEventListener('popstate', handleMobileHistory)
  if (jobsRefreshTimer) {
    window.clearInterval(jobsRefreshTimer)
  }
  const allAssets = [
    ...assets.value,
    ...parkedAssetGroups.image.assets,
    ...parkedAssetGroups.video.assets
  ]
  const cleanedIds = new Set()
  allAssets.forEach((asset) => {
    if (!cleanedIds.has(asset.id)) {
      cleanupAssetUrl(asset)
      cleanedIds.add(asset.id)
    }
  })
})
</script>

<template>
  <main class="app-shell" @dragover.prevent @drop="handleDrop">
    <section class="workspace studio-grid">
      <form class="control-panel" @submit.prevent="submitJob">
        <header class="brand-header">
          <div class="brand-mark">GIF</div>
          <div class="brand-copy">
            <h1>GIF 制作器</h1>
            <p>轻松制作，快速生成</p>
          </div>
          <span :class="['status', health]" role="status">{{ healthLabel }}</span>
        </header>

        <section class="control-section">
          <h2 class="section-title">选择模式</h2>
          <div class="mode-strip">
            <button
              v-for="option in MODE_OPTIONS"
              :key="option.value"
              class="mode-card"
              :class="[{ active: option.value === mode }, `mode-${option.value}`]"
              type="button"
              :aria-pressed="option.value === mode"
              @click="applyModeRules(option.value)"
            >
              <span class="mode-icon" aria-hidden="true"></span>
              <strong>{{ option.label }}</strong>
              <small>{{ option.hint }}</small>
            </button>
          </div>
        </section>

        <section class="control-section">
          <h2 class="section-title">上传内容</h2>
          <div
            class="paste-zone"
            role="button"
            tabindex="0"
            aria-label="点击选择素材，也可以粘贴或拖入素材"
            @click="handlePickerAreaClick"
            @keydown.enter.prevent="openPicker"
            @keydown.space.prevent="openPicker"
          >
            <span class="upload-icon" aria-hidden="true"></span>
            <div class="paste-copy">
              <strong>点击上传图片</strong>
              <p>支持 JPG、PNG、WEBP；视频最长 30 秒</p>
            </div>
          </div>
        </section>

        <section class="control-section quality-section">
          <h2 class="section-title">生成质量</h2>
          <div class="quality-grid" role="radiogroup" aria-label="生成质量">
            <button
              v-for="option in QUALITY_OPTIONS"
              :key="option.value"
              class="quality-card"
              :class="{ active: option.value === quality }"
              type="button"
              role="radio"
              :aria-checked="option.value === quality"
              @click="quality = option.value"
            >
              <strong>{{ option.label }}</strong>
              <span>{{ option.hint }}</span>
              <em>{{ option.detail }}</em>
            </button>
          </div>
        </section>

        <section class="control-section settings-section">
          <h2 class="section-title">设置选项</h2>
          <div v-if="mode === 'video'" class="video-edit-panel">
            <div v-if="previewAsset?.kind === 'video'" class="crop-editor">
              <div class="crop-editor-head">
                <div>
                  <strong>画面裁剪</strong>
                  <span>{{ cropSummary }}</span>
                </div>
                <button type="button" @click="videoCropEditorOpen ? resetCrop() : openVideoCropEditor()">
                  {{ videoCropEditorOpen ? '重置' : '重新裁剪' }}
                </button>
              </div>
              <div v-if="videoCropEditorOpen" class="crop-range-list">
                <label>
                  <span>裁剪宽度</span>
                  <input
                    v-model="cropWidthPercent"
                    type="range"
                    min="1"
                    :max="cropWidthMax"
                    step="1"
                    @input="constrainCropFields"
                  />
                  <output>{{ cropBox.width }}%</output>
                </label>
                <label>
                  <span>裁剪高度</span>
                  <input
                    v-model="cropHeightPercent"
                    type="range"
                    min="1"
                    :max="cropHeightMax"
                    step="1"
                    @input="constrainCropFields"
                  />
                  <output>{{ cropBox.height }}%</output>
                </label>
              </div>
              <div v-if="videoCropEditorOpen" class="crop-editor-actions">
                <button type="button" @click="cancelCropChanges">取消修改</button>
                <button
                  class="crop-confirm-button"
                  :class="{ confirmed: !cropIsDirty }"
                  type="button"
                  @click="confirmCrop"
                >
                  {{ cropIsDirty ? '确认裁剪' : '完成裁剪' }}
                </button>
              </div>
            </div>

            <div class="video-edit-row">
              <label class="number-field">
                <span>开始时间</span>
                <input v-model="clipStartSeconds" type="number" min="0" step="0.1" inputmode="decimal" />
                <small>秒</small>
              </label>
              <label class="number-field">
                <span>结束时间</span>
                <input v-model="clipEndSeconds" type="number" min="0" step="0.1" inputmode="decimal" placeholder="到结尾" />
                <small>秒</small>
              </label>
            </div>

            <div v-if="videoCropEditorOpen" class="video-edit-row crop-row">
              <label class="number-field">
                <span>左侧位置</span>
                <input v-model="cropLeftPercent" type="number" min="0" max="100" step="1" inputmode="decimal" @change="constrainCropFields" />
                <small>%</small>
              </label>
              <label class="number-field">
                <span>顶部位置</span>
                <input v-model="cropTopPercent" type="number" min="0" max="100" step="1" inputmode="decimal" @change="constrainCropFields" />
                <small>%</small>
              </label>
              <label class="number-field">
                <span>裁剪宽度</span>
                <input v-model="cropWidthPercent" type="number" min="1" :max="cropWidthMax" step="1" inputmode="decimal" @change="constrainCropFields" />
                <small>%</small>
              </label>
              <label class="number-field">
                <span>裁剪高度</span>
                <input v-model="cropHeightPercent" type="number" min="1" :max="cropHeightMax" step="1" inputmode="decimal" @change="constrainCropFields" />
                <small>%</small>
              </label>
            </div>
          </div>

          <div v-else class="image-edit-panel">
            <button
              v-if="!showImageCropEditor"
              class="image-crop-launch"
              type="button"
              :disabled="!imageAssets.length"
              @click="imageCropActive ? reopenImageCropEditor() : startImageCropWorkflow()"
            >
              {{ imageCropActive ? '继续裁剪' : '裁剪图片' }}
            </button>

            <div
              v-if="showImageCropEditor"
              class="image-crop-editor desktop-image-crop-editor"
            >
              <div class="image-crop-head">
                <div>
                  <strong>图片裁剪</strong>
                  <span>{{ imageCropProgress }} · {{ imageCropStatusLabel(previewAsset) }}</span>
                </div>
                <button type="button" @click="resetCurrentImageCrop">重置</button>
              </div>
              <div class="crop-range-list">
                <label>
                  <span>裁剪宽度</span>
                  <input
                    :value="imageCropBox.width"
                    type="range"
                    min="1"
                    :max="imageCropWidthMax"
                    step="1"
                    @input="setImageCropDraft({ ...imageCropBox, width: $event.target.value })"
                  />
                  <output>{{ imageCropBox.width }}%</output>
                </label>
                <label>
                  <span>裁剪高度</span>
                  <input
                    :value="imageCropBox.height"
                    type="range"
                    min="1"
                    :max="imageCropHeightMax"
                    step="1"
                    @input="setImageCropDraft({ ...imageCropBox, height: $event.target.value })"
                  />
                  <output>{{ imageCropBox.height }}%</output>
                </label>
              </div>
              <div class="image-crop-nav">
                <button
                  type="button"
                  :disabled="selectedAssetIndex <= 0 || !canLeaveCurrentImageCrop()"
                  @click="moveImageCropBy(-1)"
                >
                  上一张
                </button>
                <strong>{{ selectedAssetIndex + 1 }} / {{ imageAssets.length }}</strong>
                <button
                  type="button"
                  :disabled="selectedAssetIndex >= imageAssets.length - 1 || !canLeaveCurrentImageCrop()"
                  @click="moveImageCropBy(1)"
                >
                  下一张
                </button>
              </div>
              <div class="image-crop-actions">
                <button type="button" @click="skipCurrentImageCrop">跳过此张</button>
                <button class="confirm" type="button" @click="confirmCurrentImageCrop">
                  {{ selectedAssetIndex < imageAssets.length - 1 ? '确认并下一张' : '确认裁剪' }}
                </button>
              </div>
            </div>

            <div class="settings-grid">
              <label class="select-field">
                <span>帧率 (FPS)</span>
                <select v-model="fpsSetting" disabled>
                  <option v-for="option in FPS_OPTIONS" :key="option.value" :value="option.value">
                    {{ option.label }}
                  </option>
                </select>
              </label>
              <label class="select-field">
                <span>循环次数</span>
                <select v-model="loopSetting" disabled>
                  <option v-for="option in LOOP_OPTIONS" :key="option.value" :value="option.value">
                    {{ option.label }}
                  </option>
                </select>
              </label>
            </div>
          </div>
        </section>

        <div class="summary-bar" aria-live="polite">
          <div>
            <span class="summary-label">素材</span>
            <strong>{{ assets.length }} 个</strong>
          </div>
          <div>
            <span class="summary-label">大小</span>
            <strong>{{ totalSizeLabel }}</strong>
          </div>
          <div>
            <span class="summary-label">任务</span>
            <strong>{{ queueSummary }}</strong>
          </div>
        </div>

        <p v-if="errorMessage" class="message error" role="alert">{{ errorMessage }}</p>
        <p v-if="queueMessage" class="message success" aria-live="polite">{{ queueMessage }}</p>

        <div class="submit-row">
          <button class="primary-button" type="submit" :disabled="isSubmitting">
            <span aria-hidden="true">✦</span>
            {{ isSubmitting ? '生成中...' : '生成 GIF' }}
          </button>
          <button class="ghost-button" type="button" @click.stop="resetAssets" :disabled="!assets.length">
            清空素材
          </button>
        </div>
        <p class="submit-hint">{{ submitHint }}</p>
      </form>

      <section class="preview-panel">
        <div class="panel-head">
          <h2>制作预览</h2>
          <span>{{ modeMeta.label }}</span>
        </div>

        <div class="preview-workbench">
          <div class="preview-canvas">
            <div
              v-if="showImageCropEditor"
              class="image-crop-stage desktop-preview-crop-stage"
              :style="desktopImageCropStageStyle"
            >
              <img
                :src="previewAsset.preview_url"
                :alt="`${previewAsset.name} 裁剪预览`"
                @load="handleAssetImageLoad(previewAsset.id, $event)"
              />
              <div
                class="crop-box"
                :style="imageCropBoxStyle"
                role="application"
                aria-label="图片裁剪区域"
                @pointerdown.prevent="startImageCropInteraction($event, 'move')"
              >
                <span class="crop-thirds" aria-hidden="true"></span>
                <span
                  v-for="handle in CROP_HANDLES"
                  :key="handle"
                  class="crop-handle"
                  :class="`handle-${handle}`"
                  aria-hidden="true"
                  @pointerdown.stop.prevent="startImageCropInteraction($event, handle)"
                ></span>
              </div>
            </div>
            <div
              v-else-if="previewAsset"
              class="media-crop-viewport desktop-media-crop-viewport video-preview-surface"
              :class="{
                cropped: hasAppliedPreviewCrop,
                'video-crop-stage': previewAsset.kind === 'video' && videoCropEditorOpen
              }"
              :style="desktopMediaPreviewViewportStyle"
            >
              <img
                v-if="previewAsset.kind === 'image'"
                class="media-crop-content"
                :style="mediaPreviewTransformStyle"
                :src="previewAsset.preview_url"
                :alt="previewAsset.name"
                @load="handleAssetImageLoad(previewAsset.id, $event)"
              />
              <video
                v-else
                ref="desktopPreviewVideo"
                class="media-crop-content"
                :style="mediaPreviewTransformStyle"
                :src="previewAsset.preview_url"
                muted
                playsinline
                preload="metadata"
                :controls="false"
                :autoplay="false"
                :loop="false"
                :aria-label="previewAsset.name"
                @loadedmetadata="handleVideoMetadata($event, previewAsset.id, 'desktop-preview')"
                @timeupdate="handleVideoTimeUpdate($event, 'desktop-preview')"
                @play="syncVideoPlaybackState($event, 'desktop-preview')"
                @pause="stopVideoPlaybackState('desktop-preview')"
                @ended="stopVideoPlaybackState('desktop-preview')"
              ></video>
              <div
                v-if="previewAsset.kind === 'video' && videoCropEditorOpen"
                class="crop-box"
                :style="cropBoxStyle"
                role="application"
                aria-label="视频画面裁剪区域"
                @pointerdown.prevent="startCropInteraction($event, 'move')"
              >
                <span class="crop-thirds" aria-hidden="true"></span>
                <span
                  v-for="handle in CROP_HANDLES"
                  :key="handle"
                  class="crop-handle"
                  :class="`handle-${handle}`"
                  aria-hidden="true"
                  @pointerdown.stop.prevent="startCropInteraction($event, handle)"
                ></span>
              </div>
            </div>
            <div v-else class="empty-preview">
              <span class="empty-mark" aria-hidden="true"></span>
              <p>上传后预览会显示在这里</p>
            </div>
          </div>

          <div class="preview-controls video-preview-surface">
            <button
              class="icon-button"
              type="button"
              :aria-label="isVideoPlaying('desktop-preview') ? '预览暂停' : '预览播放'"
              @click="toggleVideoPlayback(desktopPreviewVideo, 'desktop-preview')"
            >
              <Pause v-if="isVideoPlaying('desktop-preview')" :size="18" :stroke-width="2.4" aria-hidden="true" />
              <Play v-else :size="18" :stroke-width="2.4" aria-hidden="true" />
            </button>
            <span class="time-label">{{ videoClipLabel('desktop-preview') }}</span>
            <div class="timeline" aria-hidden="true"><span :style="videoTimelineStyle('desktop-preview')"></span></div>
            <strong>{{ quality <= 2 ? '6 FPS' : quality === 3 ? '10 FPS' : '12 FPS' }}</strong>
            <button class="icon-button" type="button" aria-label="全屏预览">
              <Maximize2 :size="17" :stroke-width="2.3" aria-hidden="true" />
            </button>
          </div>

          <div
            v-if="mode === 'video' && previewAsset?.kind === 'video'"
            class="video-clip-controls preview-video-clip-controls"
          >
            <label class="number-field">
              <span>片段开始</span>
              <input v-model="clipStartSeconds" type="number" min="0" step="0.1" inputmode="decimal" />
              <small>秒</small>
            </label>
            <label class="number-field">
              <span>片段结束</span>
              <input
                v-model="clipEndSeconds"
                type="number"
                min="0"
                step="0.1"
                inputmode="decimal"
                placeholder="到结尾"
              />
              <small>秒</small>
            </label>
          </div>

          <div class="frame-strip">
            <article v-for="(asset, index) in previewFrames" :key="asset.id" class="frame-card">
              <img v-if="asset.kind === 'image'" :src="asset.preview_url" :alt="asset.name" />
              <video v-else :src="asset.preview_url" muted playsinline :aria-label="asset.name"></video>
              <span>{{ index + 1 }}</span>
              <button type="button" :aria-label="`移除 ${asset.name}`" @click="removeAsset(asset.id)">×</button>
            </article>
            <button class="add-frame" type="button" aria-label="继续添加素材" @click="openPicker">+</button>
          </div>
        </div>
      </section>

      <section class="jobs-panel">
        <div class="panel-head">
          <h2>已完成</h2>
          <button
            class="batch-button"
            type="button"
            :disabled="!completedJobs.length"
            @click="downloadCompletedJobs"
          >
            批量下载 {{ completedJobs.length }}
          </button>
        </div>

        <div v-if="jobs.length" class="job-list">
          <article v-for="job in jobs" :key="job.id" class="job-card">
            <img
              v-if="job.status === 'completed' && job.result_url"
              class="job-result-preview"
              :src="resolveApiUrl(job.result_url)"
              :alt="job.result_name"
              loading="lazy"
            />
            <div v-else class="job-result-preview placeholder">{{ formatJobStatus(job.status) }}</div>

            <div class="job-main">
              <strong>{{ job.result_name || job.source_name }}</strong>
              <span>{{ formatJobMode(job.mode) }} · 质量 {{ job.quality }} · {{ job.asset_count }} 个素材</span>
              <span v-if="job.error_message" class="job-error">{{ job.error_message }}</span>
            </div>

            <div class="job-actions">
              <button
                class="icon-button"
                type="button"
                aria-label="预览成品"
                :disabled="job.status !== 'completed' || !job.result_url"
                @click="openJobPreview(job)"
              >
                <span aria-hidden="true">▶</span>
              </button>
              <a
                v-if="job.status === 'completed' && job.result_url"
                class="icon-link"
                :href="resolveApiUrl(job.result_url)"
                :download="job.result_name"
                aria-label="下载 GIF"
              >
                <span aria-hidden="true">⇩</span>
              </a>
              <span v-else class="job-status" :class="job.status">{{ formatJobStatus(job.status) }}</span>
            </div>
          </article>
        </div>

        <p v-else class="empty-jobs">暂无任务</p>
      </section>
    </section>

    <section class="mobile-shell">
      <section v-if="mobilePage === 'home'" class="mobile-page mobile-home">
        <header class="mobile-topbar">
          <span class="topbar-spacer"></span>
          <h2>GIF 制作</h2>
          <span class="topbar-spacer"></span>
        </header>

        <div class="mobile-page-body">
          <section class="mobile-section">
            <h3>选择模式</h3>
            <div class="mobile-mode-list">
              <button
                v-for="option in MODE_OPTIONS"
                :key="option.value"
                class="mobile-mode-card"
                :class="{ active: option.value === mode }"
                type="button"
                @click="openModeConfigurator(option.value)"
              >
                <span class="mobile-mode-icon" :class="`mode-${option.value}`" aria-hidden="true"></span>
                <span class="mobile-mode-copy">
                  <strong>{{ option.label }}</strong>
                  <small>{{ option.hint }}</small>
                </span>
                <span class="mobile-chevron" aria-hidden="true">›</span>
              </button>
            </div>
          </section>
        </div>

        <nav class="mobile-tabbar" aria-label="移动端导航">
          <button class="mobile-tab active" type="button" aria-current="page">
            <House class="mobile-tab-icon" :size="22" :stroke-width="2" aria-hidden="true" />
            <strong>首页</strong>
          </button>
          <button class="mobile-tab" type="button" @click="openJobsPage">
            <CircleCheckBig class="mobile-tab-icon" :size="22" :stroke-width="2" aria-hidden="true" />
            <strong>已完成</strong>
          </button>
        </nav>
      </section>

      <section v-else-if="mobilePage === 'configure'" class="mobile-page">
        <header class="mobile-topbar">
          <button class="nav-icon" type="button" aria-label="返回首页" @click="goMobileBack('home')">
            <span aria-hidden="true">‹</span>
          </button>
          <h2>{{ modeMeta.label }}</h2>
          <button class="nav-icon" type="button" aria-label="打开预览" @click="openPreviewPage">
            <span aria-hidden="true">◌</span>
          </button>
        </header>

        <div class="mobile-page-body">
          <div
            class="mobile-upload-card"
            :class="{ compact: assets.length }"
            role="button"
            tabindex="0"
            aria-label="点击选择素材，也可以粘贴或拖入素材"
            @click="handlePickerAreaClick"
            @keydown.enter.prevent="openPicker"
            @keydown.space.prevent="openPicker"
          >
            <span class="upload-icon" aria-hidden="true"></span>
            <strong>
              {{ assets.length ? '继续添加素材' : mode === 'video' ? '点击上传视频' : '点击上传图片' }}
            </strong>
            <p>
              {{
                assets.length
                  ? `${assets.length} 个素材 · ${totalSizeLabel}`
                  : mode === 'video'
                    ? '支持 MP4、MOV；可截取 30 秒内片段'
                    : '支持 JPG、PNG、WEBP 格式'
              }}
            </p>
          </div>

          <section v-if="previewAsset" class="mobile-asset-workspace">
            <header class="mobile-asset-head">
              <div>
                <span>素材 {{ selectedAssetIndex + 1 }} / {{ assets.length }}</span>
                <strong>{{ previewAsset.name }}</strong>
              </div>
              <button
                class="mobile-remove-asset"
                type="button"
                :aria-label="`移除 ${previewAsset.name}`"
                title="移除素材"
                @click="removeAsset(previewAsset.id)"
              >
                ×
              </button>
            </header>

            <div
              class="mobile-source-stage"
              :class="{
                'video-preview-surface': previewAsset.kind === 'video',
                'image-crop-stage': showImageCropEditor,
                'media-crop-viewport': !showImageCropEditor,
                'video-crop-stage': previewAsset.kind === 'video' && videoCropEditorOpen,
                cropped: !showImageCropEditor && hasAppliedPreviewCrop
              }"
              :style="showImageCropEditor ? imageCropEditorStyle : mediaPreviewStageStyle"
            >
              <template v-if="showImageCropEditor">
                <img
                  :src="previewAsset.preview_url"
                  :alt="`${previewAsset.name} 裁剪预览`"
                  @load="handleAssetImageLoad(previewAsset.id, $event)"
                />
                <div
                  class="crop-box"
                  :style="imageCropBoxStyle"
                  role="application"
                  aria-label="图片裁剪区域"
                  @pointerdown.prevent="startImageCropInteraction($event, 'move')"
                >
                  <span class="crop-thirds" aria-hidden="true"></span>
                  <span
                    v-for="handle in CROP_HANDLES"
                    :key="handle"
                    class="crop-handle"
                    :class="`handle-${handle}`"
                    aria-hidden="true"
                    @pointerdown.stop.prevent="startImageCropInteraction($event, handle)"
                  ></span>
                </div>
              </template>
              <template v-else>
                <img
                  v-if="previewAsset.kind === 'image'"
                  class="media-crop-content"
                  :style="mediaPreviewTransformStyle"
                  :src="previewAsset.preview_url"
                  :alt="previewAsset.name"
                  @load="handleAssetImageLoad(previewAsset.id, $event)"
                />
                <video
                  v-else
                  ref="mobileSourceVideo"
                  class="media-crop-content"
                  :style="mediaPreviewTransformStyle"
                  :src="previewAsset.preview_url"
                  muted
                  playsinline
                  :controls="false"
                  :autoplay="false"
                  :loop="false"
                  preload="metadata"
                  :aria-label="previewAsset.name"
                  @loadedmetadata="handleVideoMetadata($event, previewAsset.id, 'mobile-source')"
                  @timeupdate="handleVideoTimeUpdate($event, 'mobile-source')"
                  @play="syncVideoPlaybackState($event, 'mobile-source')"
                  @pause="stopVideoPlaybackState('mobile-source')"
                  @ended="stopVideoPlaybackState('mobile-source')"
                ></video>
                <div
                  v-if="previewAsset.kind === 'video' && videoCropEditorOpen"
                  class="crop-box"
                  :style="cropBoxStyle"
                  role="application"
                  aria-label="视频画面裁剪区域"
                  @pointerdown.prevent="startCropInteraction($event, 'move')"
                >
                  <span class="crop-thirds" aria-hidden="true"></span>
                  <span
                    v-for="handle in CROP_HANDLES"
                    :key="handle"
                    class="crop-handle"
                    :class="`handle-${handle}`"
                    aria-hidden="true"
                    @pointerdown.stop.prevent="startCropInteraction($event, handle)"
                  ></span>
                </div>
              </template>
            </div>

            <div v-if="previewAsset.kind === 'video' && videoCropEditorOpen" class="crop-video-controls">
              <button
                class="icon-button"
                type="button"
                :aria-label="isVideoPlaying('mobile-source') ? '暂停裁剪预览' : '播放裁剪预览'"
                @click="toggleVideoPlayback(mobileSourceVideo, 'mobile-source')"
              >
                <Pause v-if="isVideoPlaying('mobile-source')" :size="18" :stroke-width="2.4" aria-hidden="true" />
                <Play v-else :size="18" :stroke-width="2.4" aria-hidden="true" />
              </button>
              <span>在当前预览中检查裁剪画面</span>
            </div>

            <div class="mobile-asset-strip" role="tablist" aria-label="已上传素材">
              <button
                v-for="(asset, index) in assets"
                :key="asset.id"
                class="mobile-asset-thumb"
                :class="{ active: asset.id === previewAsset.id }"
                type="button"
                role="tab"
                :aria-selected="asset.id === previewAsset.id"
                :aria-label="`查看素材 ${index + 1}: ${asset.name}`"
                @click="selectAsset(asset.id)"
              >
                <img
                  v-if="asset.kind === 'image'"
                  :src="asset.preview_url"
                  :alt="asset.name"
                  @load="handleAssetImageLoad(asset.id, $event)"
                />
                <video v-else :src="asset.preview_url" muted playsinline preload="metadata"></video>
                <span>{{ index + 1 }}</span>
                <em v-if="imageCropActive && asset.kind === 'image'">{{ imageCropStatusLabel(asset) }}</em>
              </button>
              <button class="mobile-add-asset" type="button" aria-label="继续添加素材" title="继续添加" @click="openPicker">
                +
              </button>
            </div>

            <div class="mobile-asset-actions">
              <button
                type="button"
                :disabled="selectedAssetIndex <= 0"
                aria-label="素材前移"
                title="前移"
                @click="moveSelectedAsset(-1)"
              >
                ←
              </button>
              <button
                type="button"
                :disabled="selectedAssetIndex < 0 || selectedAssetIndex >= assets.length - 1"
                aria-label="素材后移"
                title="后移"
                @click="moveSelectedAsset(1)"
              >
                →
              </button>
              <button v-if="mode === 'video'" class="edit-command" type="button" @click="openMobileVideoEditor">
                编辑画面
              </button>
              <button
                v-else
                class="edit-command"
                type="button"
                @click="imageCropActive ? openMobileImageCropEditor() : startImageCropWorkflow()"
              >
                {{ imageCropActive ? '继续裁剪' : '裁剪图片' }}
              </button>
            </div>
          </section>

          <section
            v-if="showImageCropEditor"
            class="image-crop-editor mobile-image-crop-editor"
          >
            <div class="image-crop-head">
              <div>
                <strong>图片裁剪</strong>
                <span>{{ imageCropProgress }} · {{ imageCropStatusLabel(previewAsset) }}</span>
              </div>
              <button type="button" @click="resetCurrentImageCrop">重置</button>
            </div>
            <div class="crop-range-list">
              <label>
                <span>裁剪宽度</span>
                <input
                  :value="imageCropBox.width"
                  type="range"
                  min="1"
                  :max="imageCropWidthMax"
                  step="1"
                  @input="setImageCropDraft({ ...imageCropBox, width: $event.target.value })"
                />
                <output>{{ imageCropBox.width }}%</output>
              </label>
              <label>
                <span>裁剪高度</span>
                <input
                  :value="imageCropBox.height"
                  type="range"
                  min="1"
                  :max="imageCropHeightMax"
                  step="1"
                  @input="setImageCropDraft({ ...imageCropBox, height: $event.target.value })"
                />
                <output>{{ imageCropBox.height }}%</output>
              </label>
            </div>
            <div class="image-crop-nav">
              <button
                type="button"
                :disabled="selectedAssetIndex <= 0 || !canLeaveCurrentImageCrop()"
                @click="moveImageCropBy(-1)"
              >
                上一张
              </button>
              <strong>{{ selectedAssetIndex + 1 }} / {{ imageAssets.length }}</strong>
              <button
                type="button"
                :disabled="selectedAssetIndex >= imageAssets.length - 1 || !canLeaveCurrentImageCrop()"
                @click="moveImageCropBy(1)"
              >
                下一张
              </button>
            </div>
            <div class="image-crop-actions">
              <button type="button" @click="skipCurrentImageCrop">跳过此张</button>
              <button class="confirm" type="button" @click="confirmCurrentImageCrop">
                {{ selectedAssetIndex < imageAssets.length - 1 ? '确认并下一张' : '确认裁剪' }}
              </button>
            </div>
          </section>

          <section v-if="mode === 'video' && previewAsset?.kind === 'video'" class="mobile-section mobile-video-crop-section">
            <h3>画面裁剪</h3>
            <div class="crop-editor mobile-crop-editor">
              <div class="crop-editor-head">
                <div>
                  <strong>裁剪区域</strong>
                  <span>{{ cropSummary }}</span>
                </div>
                <button type="button" @click="videoCropEditorOpen ? resetCrop() : openVideoCropEditor()">
                  {{ videoCropEditorOpen ? '重置' : '重新裁剪' }}
                </button>
              </div>
              <div v-if="videoCropEditorOpen" class="crop-editor-actions">
                <button type="button" @click="cancelCropChanges">取消修改</button>
                <button
                  class="crop-confirm-button"
                  :class="{ confirmed: !cropIsDirty }"
                  type="button"
                  @click="confirmCrop"
                >
                  {{ cropIsDirty ? '确认裁剪' : '完成裁剪' }}
                </button>
              </div>
              <div v-if="videoCropEditorOpen" class="crop-range-list">
                <label>
                  <span>裁剪宽度</span>
                  <input
                    v-model="cropWidthPercent"
                    type="range"
                    min="1"
                    :max="cropWidthMax"
                    step="1"
                    @input="constrainCropFields"
                  />
                  <output>{{ cropBox.width }}%</output>
                </label>
                <label>
                  <span>裁剪高度</span>
                  <input
                    v-model="cropHeightPercent"
                    type="range"
                    min="1"
                    :max="cropHeightMax"
                    step="1"
                    @input="constrainCropFields"
                  />
                  <output>{{ cropBox.height }}%</output>
                </label>
              </div>
              <div v-if="videoCropEditorOpen" class="crop-grid">
                <label class="number-field">
                  <span>左侧位置</span>
                  <input v-model="cropLeftPercent" type="number" min="0" max="100" step="1" inputmode="decimal" @change="constrainCropFields" />
                  <small>%</small>
                </label>
                <label class="number-field">
                  <span>顶部位置</span>
                  <input v-model="cropTopPercent" type="number" min="0" max="100" step="1" inputmode="decimal" @change="constrainCropFields" />
                  <small>%</small>
                </label>
                <label class="number-field">
                  <span>裁剪宽度</span>
                  <input v-model="cropWidthPercent" type="number" min="1" :max="cropWidthMax" step="1" inputmode="decimal" @change="constrainCropFields" />
                  <small>%</small>
                </label>
                <label class="number-field">
                  <span>裁剪高度</span>
                  <input v-model="cropHeightPercent" type="number" min="1" :max="cropHeightMax" step="1" inputmode="decimal" @change="constrainCropFields" />
                  <small>%</small>
                </label>
              </div>
            </div>
          </section>

          <section class="mobile-section">
            <h3>生成质量</h3>
            <div class="mobile-quality-row">
              <button
                v-for="option in QUALITY_OPTIONS"
                :key="option.value"
                class="mobile-quality-pill"
                :class="{ active: option.value === quality }"
                type="button"
                @click="quality = option.value"
              >
                <span>{{ option.label.replace('质量', '') }}</span>
                <strong>{{ option.detail }}</strong>
              </button>
            </div>
          </section>

          <section v-if="mode === 'video'" class="mobile-section">
            <h3>片段时间</h3>
            <div class="mobile-time-grid">
              <label class="number-field">
                <span>开始时间</span>
                <input v-model="clipStartSeconds" type="number" min="0" step="0.1" inputmode="decimal" />
                <small>秒</small>
              </label>
              <label class="number-field">
                <span>结束时间</span>
                <input
                  v-model="clipEndSeconds"
                  type="number"
                  min="0"
                  step="0.1"
                  inputmode="decimal"
                  placeholder="到结尾"
                />
                <small>秒</small>
              </label>
            </div>
          </section>

          <section v-else class="mobile-section">
            <h3>设置选项</h3>
            <div class="mobile-setting-list">
              <div class="mobile-setting-row">
                <span>帧率</span>
                <strong>{{ currentFpsLabel }}</strong>
              </div>
              <div class="mobile-setting-row">
                <span>循环次数</span>
                <strong>无限循环</strong>
              </div>
              <div class="mobile-setting-row">
                <span>最大边长</span>
                <strong>{{ currentQualityMeta.detail }}</strong>
              </div>
            </div>
          </section>

          <div class="mobile-summary">
            <span>{{ assets.length }} 个素材</span>
            <strong>{{ queueSummary }}</strong>
          </div>

          <p v-if="errorMessage" class="message error" role="alert">{{ errorMessage }}</p>
          <p v-if="queueMessage" class="message success" aria-live="polite">{{ queueMessage }}</p>
        </div>

        <div class="mobile-bottom-cta">
          <button class="ghost-button" type="button" :disabled="!assets.length" @click="resetAssets">清空</button>
          <button class="primary-button" type="button" :disabled="!assets.length" @click="confirmMobileCrop">确认裁剪</button>
        </div>
      </section>

      <section v-else-if="mobilePage === 'preview'" class="mobile-page">
        <header class="mobile-topbar">
          <button class="nav-icon" type="button" aria-label="返回参数页" @click="goMobileBack('configure')">
            <span aria-hidden="true">‹</span>
          </button>
          <h2>制作预览</h2>
          <button class="nav-icon" type="button" aria-label="打开已完成" @click="openJobsPage">
            <span aria-hidden="true">◔</span>
          </button>
        </header>

        <div class="mobile-page-body preview-body">
          <div
            class="mobile-preview-stage media-crop-viewport video-preview-surface"
            :class="{ cropped: hasAppliedPreviewCrop }"
            :style="mediaPreviewStageStyle"
          >
            <template v-if="previewAsset">
              <img
                v-if="previewAsset.kind === 'image'"
                class="media-crop-content"
                :style="mediaPreviewTransformStyle"
                :src="previewAsset.preview_url"
                :alt="previewAsset.name"
                @load="handleAssetImageLoad(previewAsset.id, $event)"
              />
              <video
                v-else
                ref="mobilePreviewVideo"
                class="media-crop-content"
                :style="mediaPreviewTransformStyle"
                :src="previewAsset.preview_url"
                muted
                playsinline
                preload="metadata"
                :controls="false"
                :autoplay="false"
                :loop="false"
                :aria-label="previewAsset.name"
                @loadedmetadata="handleVideoMetadata($event, previewAsset.id, 'mobile-preview')"
                @timeupdate="handleVideoTimeUpdate($event, 'mobile-preview')"
                @play="syncVideoPlaybackState($event, 'mobile-preview')"
                @pause="stopVideoPlaybackState('mobile-preview')"
                @ended="stopVideoPlaybackState('mobile-preview')"
              ></video>
            </template>
            <div v-else class="empty-preview">
              <span class="empty-mark" aria-hidden="true"></span>
              <p>上传后预览会显示在这里</p>
            </div>
          </div>

          <div class="mobile-preview-toolbar video-preview-surface">
            <button
              class="nav-icon compact"
              type="button"
              :aria-label="isVideoPlaying('mobile-preview') ? '预览暂停' : '预览播放'"
              @click="toggleVideoPlayback(mobilePreviewVideo, 'mobile-preview')"
            >
              <Pause v-if="isVideoPlaying('mobile-preview')" :size="17" :stroke-width="2.4" aria-hidden="true" />
              <Play v-else :size="17" :stroke-width="2.4" aria-hidden="true" />
            </button>
            <span>{{ videoClipLabel('mobile-preview') }}</span>
            <div class="timeline" aria-hidden="true"><span :style="videoTimelineStyle('mobile-preview')"></span></div>
            <strong>{{ currentFpsLabel }}</strong>
          </div>

          <div
            v-if="mode === 'video' && previewAsset?.kind === 'video'"
            class="video-clip-controls preview-video-clip-controls"
          >
            <label class="number-field">
              <span>片段开始</span>
              <input v-model="clipStartSeconds" type="number" min="0" step="0.1" inputmode="decimal" />
              <small>秒</small>
            </label>
            <label class="number-field">
              <span>片段结束</span>
              <input
                v-model="clipEndSeconds"
                type="number"
                min="0"
                step="0.1"
                inputmode="decimal"
                placeholder="到结尾"
              />
              <small>秒</small>
            </label>
          </div>

          <div class="mobile-frame-strip">
            <article v-for="(asset, index) in previewFrames" :key="asset.id" class="frame-card">
              <img v-if="asset.kind === 'image'" :src="asset.preview_url" :alt="asset.name" />
              <video v-else :src="asset.preview_url" muted playsinline :aria-label="asset.name"></video>
              <span>{{ index + 1 }}</span>
            </article>
            <button class="add-frame" type="button" aria-label="继续添加素材" @click="openPicker">+</button>
          </div>

          <div class="mobile-tool-row">
            <button class="mobile-tool" type="button" @click="openConfigurePage">
              <span aria-hidden="true">▥</span>
              <small>调整素材</small>
            </button>
            <button
              class="mobile-tool"
              type="button"
              @click="mode === 'video' ? openMobileVideoEditor() : openConfigurePage()"
            >
              <span aria-hidden="true">◔</span>
              <small>{{ mode === 'video' ? '截取片段' : '预览素材' }}</small>
            </button>
            <button
              class="mobile-tool"
              type="button"
              @click="mode === 'video' ? openMobileVideoEditor() : openConfigurePage()"
            >
              <span aria-hidden="true">⌗</span>
              <small>{{ mode === 'video' ? '调整裁剪' : '修改质量' }}</small>
            </button>
          </div>

          <p v-if="errorMessage" class="message error" role="alert">{{ errorMessage }}</p>
          <p v-if="queueMessage" class="message success" aria-live="polite">{{ queueMessage }}</p>
        </div>

        <div class="mobile-bottom-cta single">
          <button class="primary-button" type="button" :disabled="isSubmitting" @click="submitJob">
            {{ isSubmitting ? '生成中...' : '生成 GIF' }}
          </button>
        </div>
      </section>

      <section v-else-if="mobilePage === 'jobs'" class="mobile-page">
        <header class="mobile-topbar">
          <button class="nav-icon" type="button" aria-label="返回首页" @click="goMobileBack('home')">
            <span aria-hidden="true">‹</span>
          </button>
          <h2>已完成</h2>
          <button class="header-action" type="button" :disabled="!completedJobs.length" @click="downloadCompletedJobs">
            打包
          </button>
        </header>

        <div class="mobile-page-body jobs-body">
          <div v-if="jobs.length" class="mobile-job-list">
            <button v-for="job in jobs" :key="job.id" class="mobile-job-card" type="button" @click="openJobDetail(job)">
              <img
                v-if="job.status === 'completed' && job.result_url"
                class="mobile-job-thumb"
                :src="resolveApiUrl(job.result_url)"
                :alt="job.result_name"
                loading="lazy"
              />
              <div v-else class="mobile-job-thumb placeholder">{{ formatJobStatus(job.status) }}</div>
              <span class="mobile-job-copy">
                <strong>{{ job.result_name || job.source_name }}</strong>
                <small>{{ formatJobMode(job.mode) }} · 质量 {{ job.quality }}</small>
                <small v-if="job.error_message" class="job-error">{{ job.error_message }}</small>
              </span>
              <span class="mobile-chevron" aria-hidden="true">›</span>
            </button>
          </div>
          <p v-else class="empty-jobs">暂无任务</p>
        </div>

        <nav class="mobile-tabbar" aria-label="移动端导航">
          <button class="mobile-tab" type="button" @click="openHomePage">
            <House class="mobile-tab-icon" :size="22" :stroke-width="2" aria-hidden="true" />
            <strong>首页</strong>
          </button>
          <button class="mobile-tab active" type="button" aria-current="page">
            <CircleCheckBig class="mobile-tab-icon" :size="22" :stroke-width="2" aria-hidden="true" />
            <strong>已完成</strong>
          </button>
        </nav>
      </section>

      <section v-else-if="mobilePage === 'detail'" class="mobile-page">
        <header class="mobile-topbar">
          <button class="nav-icon" type="button" aria-label="返回已完成" @click="closeJobDetail">
            <span aria-hidden="true">‹</span>
          </button>
          <h2>预览</h2>
          <span class="topbar-spacer"></span>
        </header>

        <div v-if="selectedJob" class="mobile-page-body detail-body">
          <div class="mobile-detail-stage">
            <img
              v-if="selectedJob.status === 'completed' && selectedJob.result_url"
              :src="resolveApiUrl(selectedJob.result_url)"
              :alt="selectedJob.result_name"
            />
            <div v-else class="empty-preview">
              <p>{{ formatJobStatus(selectedJob.status) }}</p>
            </div>
          </div>

          <div class="mobile-detail-meta">
            <strong>{{ selectedJob.result_name || selectedJob.source_name }}</strong>
            <span>{{ formatJobMode(selectedJob.mode) }} · 质量 {{ selectedJob.quality }}</span>
            <span>{{ selectedJob.asset_count }} 个素材</span>
          </div>

          <div class="mobile-detail-actions">
            <button
              class="icon-button detail-action"
              type="button"
              :disabled="selectedJob.status !== 'completed' || !selectedJob.result_url"
              @click="openJobPreview(selectedJob)"
            >
              <span aria-hidden="true">▶</span>
              <small>播放</small>
            </button>
            <a
              v-if="selectedJob.status === 'completed' && selectedJob.result_url"
              class="icon-link detail-action"
              :href="resolveApiUrl(selectedJob.result_url)"
              :download="selectedJob.result_name"
            >
              <span aria-hidden="true">⇩</span>
              <small>下载</small>
            </a>
          </div>
        </div>

        <div v-else class="mobile-page-body detail-body">
          <p class="empty-jobs">该任务已不存在。</p>
        </div>

        <div class="mobile-bottom-cta single">
          <button class="primary-button" type="button" @click="closeJobDetail">完成</button>
        </div>
      </section>

    </section>

    <input
      ref="fileInput"
      class="hidden-input"
      type="file"
      :accept="modeMeta.accept"
      :multiple="true"
      @change="handleFileSelect"
    />
  </main>
</template>
