<template>
  <div class="fg">
    <div class="fg-label">
      {{ label }}
    </div>
    <button
      v-for="entry in visibleValues"
      :key="String(entry.value)"
      type="button"
      class="fg-row"
      :class="{'fg-on': isSelected(entry.value)}"
      @click="$emit('toggle', entry.value)"
    >
      <span class="fg-value">{{ entry.value }}</span>
      <span class="fg-count">{{ entry.count }}</span>
    </button>
    <button
      v-if="values.length > shown && !expanded"
      type="button"
      class="fg-more"
      @click="expanded = true"
    >
      + {{ values.length - shown }} more
    </button>
  </div>
</template>

<script>
// One facet group of the search rail (MOO-79): checkbox-style value rows
// with counts from the last response. Zero-count values of an unselected
// group are hidden (the backend's excluded-own-dimension aggs keep the
// counts correct under multi-select).
export default {
  name: 'FacetGroup',
  props: {
    label: {
      type: String,
      required: true,
    },
    values: {
      type: Array,
      default: () => [],
    },
    selected: {
      type: Array,
      default: () => [],
    },
  },
  emits: ['toggle'],
  data() {
    return {
      expanded: false,
      shown: 8,
    };
  },
  computed: {
    visibleValues() {
      const rows = this.values.filter(
        entry => entry.count > 0 || this.isSelected(entry.value),
      );
      return this.expanded ? rows : rows.slice(0, this.shown);
    },
  },
  methods: {
    isSelected(value) {
      return this.selected.some(item => String(item).toLowerCase() === String(value).toLowerCase());
    },
  },
};
</script>

<style scoped>
.fg {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: 18px;
}

.fg-label {
  font: 600 11px var(--font-mono);
  letter-spacing: .1em;
  color: var(--dim-2);
  margin-bottom: 7px;
}

.fg-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  padding: 5px 8px 5px 10px;
  border: none;
  border-left: 2px solid transparent;
  border-radius: 6px;
  background: none;
  cursor: pointer;
  text-align: left;
  transition: background .15s ease, color .15s ease;
}

.fg-row:hover {
  background: var(--hover);
}

.fg-value {
  font: 400 12.5px var(--font-ui);
  color: var(--txt-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fg-count {
  font: 500 11px var(--font-mono);
  color: var(--dim-2);
  flex: none;
}

.fg-on {
  border-left-color: var(--acc);
  background: rgba(255, 255, 255, .04);
}

.fg-on .fg-value {
  color: var(--acc);
}

.fg-more {
  align-self: flex-start;
  border: none;
  background: none;
  cursor: pointer;
  padding: 4px 10px;
  font: 500 11px var(--font-mono);
  color: var(--dim);
}

.fg-more:hover {
  color: var(--txt-2);
}
</style>
