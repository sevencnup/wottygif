<script setup>
import { onMounted, ref } from 'vue'
import { createMediaJob, getHealth, listMediaJobs } from './api/client.js'

const health = ref('checking')
const jobType = ref('image_to_gif')
const sourceName = ref('demo.png')
const jobs = ref([])
const isSubmitting = ref(false)
const errorMessage = ref('')

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

const submitJob = async () => {
  errorMessage.value = ''
  isSubmitting.value = true

  try {
    await createMediaJob({
      job_type: jobType.value,
      source_name: sourceName.value
    })
    sourceName.value = ''
    await refreshJobs()
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    isSubmitting.value = false
  }
}

onMounted(async () => {
  await checkHealth()
  await refreshJobs()
})
</script>

<template>
  <main class="app-shell">
    <section class="workspace">
      <header class="topbar">
        <div>
          <p class="eyebrow">WottyGIF Studio</p>
          <h1>媒体转 GIF 工作台</h1>
        </div>
        <span :class="['status', health]">{{ health }}</span>
      </header>

      <form class="job-panel" @submit.prevent="submitJob">
        <label>
          处理类型
          <select v-model="jobType">
            <option value="image_to_gif">图片转 GIF</option>
            <option value="video_to_gif">视频转 GIF</option>
          </select>
        </label>

        <label>
          源文件名
          <input v-model.trim="sourceName" placeholder="example.mp4" required />
        </label>

        <button type="submit" :disabled="isSubmitting || !sourceName">
          {{ isSubmitting ? '提交中...' : '创建任务' }}
        </button>
      </form>

      <p v-if="errorMessage" class="error">{{ errorMessage }}</p>

      <section class="jobs">
        <h2>任务队列</h2>
        <article v-for="job in jobs" :key="job.id" class="job-card">
          <div>
            <strong>{{ job.source_name }}</strong>
            <span>{{ job.job_type }}</span>
          </div>
          <em>{{ job.status }}</em>
        </article>
        <p v-if="jobs.length === 0" class="empty">暂无任务</p>
      </section>
    </section>
  </main>
</template>
