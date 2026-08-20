<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'

const props = defineProps({
  min: { type: Number, required: true },
  max: { type: Number, required: true },
  start: { type: Number, required: true },
  end: { type: Number, required: true },
  step: { type: Number, default: 0.1 }
})

const emit = defineEmits(['update:start', 'update:end', 'scrub'])

const clamp = (value, low, high) => Math.min(Math.max(value, low), high)

const trackEl = ref(null)
let drag = null

const span = computed(() => Math.max(props.max - props.min, 0.0001))
const startPct = computed(() => ((clamp(props.start, props.min, props.max) - props.min) / span.value) * 100)
const endPct = computed(() => ((clamp(props.end, props.min, props.max) - props.min) / span.value) * 100)

const valueFromClientX = (clientX) => {
  const rect = trackEl.value.getBoundingClientRect()
  const ratio = (clientX - rect.left) / rect.width
  const raw = props.min + ratio * span.value
  const stepped = Math.round(raw / props.step) * props.step
  return clamp(stepped, props.min, props.max)
}

const startDrag = (type, event) => {
  drag = {
    type,
    pointerId: event.pointerId,
    originX: event.clientX,
    originStart: props.start,
    originEnd: props.end
  }
  trackEl.value.setPointerCapture?.(event.pointerId)
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
  window.addEventListener('pointercancel', onPointerUp)
}

const onTrackPointerDown = (event) => {
  // 在轨道上（非手柄，手柄已 stop 冒泡）按下时整体平移两端
  drag = {
    type: 'move',
    pointerId: event.pointerId,
    originX: event.clientX,
    originStart: props.start,
    originEnd: props.end
  }
  trackEl.value.setPointerCapture?.(event.pointerId)
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
  window.addEventListener('pointercancel', onPointerUp)
  event.preventDefault()
}

const onPointerMove = (event) => {
  if (!drag || event.pointerId !== drag.pointerId) {
    return
  }
  const value = valueFromClientX(event.clientX)
  if (drag.type === 'start') {
    const v = clamp(value, props.min, props.end - props.step)
    emit('update:start', v)
    emit('scrub', v)
  } else if (drag.type === 'end') {
    const v = clamp(value, props.start + props.step, props.max)
    emit('update:end', v)
    emit('scrub', v)
  } else {
    const rect = trackEl.value.getBoundingClientRect()
    const delta = ((event.clientX - drag.originX) / rect.width) * span.value
    const windowSize = drag.originEnd - drag.originStart
    const shift = clamp(delta, -drag.originStart, props.max - drag.originStart - windowSize)
    const newStart = Math.round((drag.originStart + shift) * 10) / 10
    const newEnd = Math.round((drag.originEnd + shift) * 10) / 10
    emit('update:start', newStart)
    emit('update:end', newEnd)
    emit('scrub', newStart)
  }
}

const onPointerUp = (event) => {
  if (!drag || event.pointerId !== drag.pointerId) {
    return
  }
  drag = null
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  window.removeEventListener('pointercancel', onPointerUp)
}

const nudge = (type, delta) => {
  if (type === 'start') {
    const v = clamp(props.start + delta, props.min, props.end - props.step)
    emit('update:start', v)
    emit('scrub', v)
  } else {
    const v = clamp(props.end + delta, props.start + props.step, props.max)
    emit('update:end', v)
    emit('scrub', v)
  }
}

onBeforeUnmount(() => {
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  window.removeEventListener('pointercancel', onPointerUp)
})
</script>

<template>
  <div ref="trackEl" class="dual-range" @pointerdown="onTrackPointerDown">
    <div
      class="dual-range-fill"
      :style="{ left: startPct + '%', width: Math.max(endPct - startPct, 0.1) + '%' }"
    ></div>
    <button
      type="button"
      class="dual-range-handle dual-range-handle--start"
      :style="{ left: startPct + '%' }"
      aria-label="截取起点"
      @pointerdown.stop="startDrag('start', $event)"
      @keydown.left.prevent="nudge('start', -step)"
      @keydown.right.prevent="nudge('start', step)"
    ></button>
    <button
      type="button"
      class="dual-range-handle dual-range-handle--end"
      :style="{ left: endPct + '%' }"
      aria-label="截取终点"
      @pointerdown.stop="startDrag('end', $event)"
      @keydown.left.prevent="nudge('end', -step)"
      @keydown.right.prevent="nudge('end', step)"
    ></button>
  </div>
</template>

<style scoped>
.dual-range {
  position: relative;
  height: 26px;
  min-width: 0;
  touch-action: none;
  cursor: pointer;
  user-select: none;
}

.dual-range::before {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  top: 50%;
  height: 6px;
  transform: translateY(-50%);
  border-radius: 999px;
  background: var(--line, #d8dce3);
}

.dual-range-fill {
  position: absolute;
  top: 50%;
  height: 6px;
  transform: translateY(-50%);
  border-radius: 999px;
  background: var(--accent-strong, #3b82f6);
  pointer-events: none;
}

.dual-range-handle {
  position: absolute;
  top: 50%;
  width: 20px;
  height: 20px;
  padding: 0;
  border: 2px solid #ffffff;
  border-radius: 999px;
  background: var(--accent-strong, #3b82f6);
  transform: translate(-50%, -50%);
  cursor: grab;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.35);
  touch-action: none;
}

.dual-range-handle:active {
  cursor: grabbing;
  transform: translate(-50%, -50%) scale(1.08);
}

@media (pointer: coarse) {
  .dual-range {
    height: 32px;
  }
  .dual-range-handle {
    width: 26px;
    height: 26px;
  }
}
</style>
