<template>
  <div class="seg">
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      class="seg-btn"
      :class="{'seg-active': option.value === modelValue}"
      @click="$emit('update:modelValue', option.value)"
    >
      {{ option.label }}
    </button>
  </div>
</template>

<script>
// The segmented pill control the admin console uses for every filter row
// (role/status filters, report ranges, settings tabs).
export default {
  name: 'SegmentedControl',
  props: {
    // [{value, label}]
    options: {
      type: Array,
      required: true,
    },
    modelValue: {
      type: [String, Number],
      default: '',
    },
  },
  emits: ['update:modelValue'],
};
</script>

<style scoped>
.seg {
  display: flex;
  gap: 3px;
  padding: 4px;
  border-radius: 10px;
  background: var(--raised);
  border: 1px solid rgba(255, 255, 255, .08);
  width: fit-content;
}

.seg-btn {
  padding: 6px 12px;
  border-radius: 7px;
  border: none;
  cursor: pointer;
  background: transparent;
  color: var(--muted);
  font: 600 12px var(--font-ui);
  white-space: nowrap;
  transition: background .15s ease, color .15s ease;
}

.seg-btn:hover {
  color: var(--txt-2);
}

.seg-active,
.seg-active:hover {
  background: var(--acc-soft-strong);
  color: var(--acc);
}
</style>
