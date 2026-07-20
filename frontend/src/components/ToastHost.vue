<template>
  <div
    v-if="state.visible"
    :key="state.serial"
    class="toast"
  >
    <span
      class="toast-dot"
      :class="{'toast-dot-warn': state.kind === 'warn'}"
    />
    <span class="toast-text">{{ state.message }}</span>
  </div>
</template>

<script>
import { toastState } from '@/utils/toast';

export default {
  name: 'ToastHost',
  computed: {
    state() {
      return toastState;
    },
  },
};
</script>

<style scoped>
.toast {
  position: fixed;
  left: 50%;
  bottom: 96px;
  transform: translateX(-50%);
  z-index: 60;
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 11px 16px;
  border-radius: 11px;
  background: #161c24;
  border: 1px solid rgba(255, 255, 255, .12);
  box-shadow: 0 16px 44px rgba(0, 0, 0, .5);
  animation: toastin .22s ease;
}

.toast-dot {
  width: 8px;
  height: 8px;
  border-radius: 4px;
  background: var(--acc);
  flex: none;
}

.toast-dot-warn {
  background: var(--warn);
}

.toast-text {
  font: 500 13px var(--font-ui);
  color: var(--txt);
  white-space: nowrap;
}
</style>
