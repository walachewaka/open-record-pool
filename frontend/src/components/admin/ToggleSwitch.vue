<template>
  <button
    type="button"
    class="tog"
    :class="{'tog-on': modelValue, 'tog-locked': locked}"
    :disabled="locked"
    :title="locked ? 'Owner always has access' : 'Toggle'"
    @click="$emit('update:modelValue', !modelValue)"
  >
    <span class="tog-knob" />
  </button>
</template>

<script>
// The pill toggle used by the roles matrix and the settings tabs. Locked
// renders the Owner column: on, dimmed, and not clickable.
export default {
  name: 'ToggleSwitch',
  props: {
    modelValue: {
      type: Boolean,
      default: false,
    },
    locked: {
      type: Boolean,
      default: false,
    },
  },
  emits: ['update:modelValue'],
};
</script>

<style scoped>
.tog {
  width: 38px;
  height: 22px;
  border-radius: 12px;
  border: none;
  cursor: pointer;
  background: rgba(255, 255, 255, .1);
  display: flex;
  align-items: center;
  padding: 0 2px;
  justify-content: flex-start;
  transition: background .15s ease;
  flex: none;
}

.tog-knob {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #6b7480;
  transition: transform .15s ease, background .15s ease;
}

.tog-on {
  background: color-mix(in oklab, var(--acc) 62%, transparent);
}

.tog-on .tog-knob {
  background: var(--acc);
  transform: translateX(16px);
}

.tog-locked {
  cursor: default;
  opacity: .6;
}
</style>
