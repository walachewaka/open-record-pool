<template>
  <aside
    class="facet-rail"
    :class="{'facet-degraded': degraded}"
  >
    <div class="facet-head">
      <span class="facet-title">FILTERS</span>
      <button
        v-if="anyActive"
        type="button"
        class="facet-clear"
        @click="$emit('clear')"
      >
        Clear all
      </button>
    </div>

    <FacetGroup
      label="GENRE"
      :values="facets.genres || []"
      :selected="selection.genres"
      :class="{'facet-off': !(facets.genres || []).length}"
      @toggle="value => $emit('toggle-genre', value)"
    />

    <div
      class="fp-group"
      :class="{'facet-off': !keyChipsEnabled.size && !selection.key}"
    >
      <div class="fp-label">
        KEY
      </div>
      <div class="key-grid">
        <button
          v-for="code in keyWheel"
          :key="code"
          type="button"
          class="key-chip"
          :class="{'key-on': selectedCamelot === code}"
          :disabled="!keyChipsEnabled.has(code) && selectedCamelot !== code"
          @click="$emit('set-key', selectedCamelot === code ? '' : code)"
        >
          {{ code }}
        </button>
      </div>
    </div>

    <div
      class="fp-group"
      :class="{'facet-off': !bpmFacet}"
    >
      <div class="fp-label">
        BPM
      </div>
      <div class="range-row">
        <input
          type="number"
          class="range-input"
          placeholder="min"
          :value="selection.bpmMin"
          @change="$emit('set-bpm', [$event.target.value, selection.bpmMax])"
        >
        <span class="range-sep">–</span>
        <input
          type="number"
          class="range-input"
          placeholder="max"
          :value="selection.bpmMax"
          @change="$emit('set-bpm', [selection.bpmMin, $event.target.value])"
        >
      </div>
      <div
        v-if="bpmBuckets.length"
        class="bucket-col"
      >
        <button
          v-for="bucket in bpmBuckets"
          :key="bucket.from"
          type="button"
          class="bucket-row"
          :class="{'fg-on': isBpmBucketActive(bucket)}"
          @click="toggleBpmBucket(bucket)"
        >
          <span class="fg-value">{{ bucket.from }}–{{ bucket.to }}</span>
          <span class="fg-count">{{ bucket.count }}</span>
        </button>
      </div>
    </div>

    <div class="fp-group">
      <div class="fp-label">
        YEAR
      </div>
      <div class="range-row">
        <input
          type="number"
          class="range-input"
          placeholder="from"
          :value="selection.yearMin"
          @change="$emit('set-year', [$event.target.value, selection.yearMax])"
        >
        <span class="range-sep">–</span>
        <input
          type="number"
          class="range-input"
          placeholder="to"
          :value="selection.yearMax"
          @change="$emit('set-year', [selection.yearMin, $event.target.value])"
        >
      </div>
      <div
        v-if="yearShortcuts.length"
        class="chips-row"
      >
        <button
          v-for="year in yearShortcuts"
          :key="year.value"
          type="button"
          class="mini-chip"
          :class="{'mini-on': isYearActive(year.value)}"
          @click="toggleYear(year.value)"
        >
          {{ year.value }}
        </button>
      </div>
    </div>

    <div class="fp-group">
      <div class="fp-label">
        BITRATE
      </div>
      <div class="chips-row">
        <button
          v-for="rate in bitrateChips"
          :key="rate"
          type="button"
          class="mini-chip"
          :class="{'mini-on': Number(selection.bitrateMin) === rate}"
          @click="$emit('set-bitrate', Number(selection.bitrateMin) === rate ? '' : String(rate))"
        >
          {{ rate }}+
        </button>
      </div>
    </div>

    <div class="fp-group">
      <div class="fp-label">
        SOURCE
      </div>
      <div class="chips-row">
        <button
          v-for="entry in sourceChips"
          :key="entry"
          type="button"
          class="mini-chip"
          :class="{'mini-on': selection.source === entry}"
          @click="$emit('set-source', selection.source === entry ? '' : entry)"
        >
          {{ entry }}
        </button>
      </div>
    </div>
  </aside>
</template>

<script>
import FacetGroup from '@/components/search/FacetGroup.vue';

// Camelot wheel order, 1A/1B .. 12A/12B.
const KEY_WHEEL = [];
for (let number = 1; number <= 12; number += 1) {
  KEY_WHEEL.push(`${number}A`, `${number}B`);
}

// The faceted-filter rail of the Search view (MOO-79). All selection state
// lives in the route query (owned by Search.vue); this component only
// renders the last response's facet counts and emits intents.
export default {
  name: 'FacetPanel',
  components: {FacetGroup},
  props: {
    facets: {
      type: Object,
      default: () => ({}),
    },
    selection: {
      type: Object,
      required: true,
    },
    degraded: {
      type: Boolean,
      default: false,
    },
  },
  emits: [
    'toggle-genre',
    'set-key',
    'set-bpm',
    'set-year',
    'set-bitrate',
    'set-source',
    'clear',
  ],
  data() {
    return {
      keyWheel: KEY_WHEEL,
      bitrateChips: [320, 256, 192],
      sourceChips: ['library', 'upload'],
    };
  },
  computed: {
    anyActive() {
      const sel = this.selection;
      return Boolean(
        sel.genres.length || sel.key || sel.bpmMin || sel.bpmMax ||
        sel.yearMin || sel.yearMax || sel.bitrateMin || sel.source,
      );
    },
    keyChipsEnabled() {
      return new Set((this.facets.keys || []).map(entry => entry.value));
    },
    selectedCamelot() {
      return (this.selection.key || '').toUpperCase();
    },
    bpmFacet() {
      return this.facets.bpm || null;
    },
    bpmBuckets() {
      return (this.bpmFacet && this.bpmFacet.buckets) || [];
    },
    yearShortcuts() {
      return (this.facets.years || []).slice(0, 6);
    },
  },
  methods: {
    isBpmBucketActive(bucket) {
      return Number(this.selection.bpmMin) === bucket.from &&
        Number(this.selection.bpmMax) === bucket.to;
    },
    toggleBpmBucket(bucket) {
      if (this.isBpmBucketActive(bucket)) {
        this.$emit('set-bpm', ['', '']);
      } else {
        this.$emit('set-bpm', [String(bucket.from), String(bucket.to)]);
      }
    },
    isYearActive(year) {
      return Number(this.selection.yearMin) === year &&
        Number(this.selection.yearMax) === year;
    },
    toggleYear(year) {
      if (this.isYearActive(year)) {
        this.$emit('set-year', ['', '']);
      } else {
        this.$emit('set-year', [String(year), String(year)]);
      }
    },
  },
};
</script>

<style scoped>
.facet-rail {
  width: 240px;
  flex: none;
  border: 1px solid var(--line);
  border-radius: 13px;
  background: var(--panel);
  padding: 14px 12px;
  align-self: flex-start;
}

.facet-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.facet-title {
  font: 600 11px var(--font-mono);
  letter-spacing: .1em;
  color: var(--dim-2);
}

.facet-clear {
  border: none;
  background: none;
  cursor: pointer;
  font: 500 11px var(--font-mono);
  color: var(--dim);
  padding: 0;
}

.facet-clear:hover {
  color: var(--acc);
}

.fp-group {
  margin-bottom: 18px;
}

.fp-label {
  font: 600 11px var(--font-mono);
  letter-spacing: .1em;
  color: var(--dim-2);
  margin-bottom: 7px;
}

.facet-off {
  opacity: .45;
  pointer-events: none;
}

.facet-degraded .fp-group,
.facet-degraded .fg {
  opacity: .45;
}

.key-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 5px;
}

.key-chip {
  height: 26px;
  border-radius: var(--r-pill);
  border: 1px solid var(--line-strong);
  background: rgba(255, 255, 255, .03);
  color: var(--txt-3);
  font: 600 10.5px var(--font-mono);
  cursor: pointer;
  transition: border-color .15s ease, color .15s ease;
}

.key-chip:hover:enabled {
  border-color: rgba(255, 255, 255, .24);
}

.key-chip:disabled {
  opacity: .3;
  cursor: default;
}

.key-on {
  border-color: var(--acc-border);
  color: var(--acc);
}

.range-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}

.range-input {
  width: 100%;
  min-width: 0;
  height: 28px;
  padding: 0 8px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line-strong);
  background: var(--raised);
  color: var(--txt);
  font: 400 12px var(--font-mono);
  box-sizing: border-box;
}

.range-input:focus {
  outline: none;
  border-color: var(--acc-border);
}

.range-sep {
  color: var(--dim-2);
  font: 400 12px var(--font-mono);
}

.bucket-col {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.bucket-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  padding: 4px 8px 4px 10px;
  border: none;
  border-left: 2px solid transparent;
  border-radius: 6px;
  background: none;
  cursor: pointer;
  text-align: left;
  transition: background .15s ease;
}

.bucket-row:hover {
  background: var(--hover);
}

.fg-on {
  border-left-color: var(--acc);
  background: rgba(255, 255, 255, .04);
}

.fg-on .fg-value {
  color: var(--acc);
}

.fg-value {
  font: 400 12.5px var(--font-ui);
  color: var(--txt-3);
}

.fg-count {
  font: 500 11px var(--font-mono);
  color: var(--dim-2);
}

.chips-row {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
}

.mini-chip {
  padding: 5px 10px;
  border-radius: var(--r-pill);
  border: 1px solid var(--line-strong);
  background: rgba(255, 255, 255, .03);
  color: var(--txt-3);
  font: 500 11.5px var(--font-ui);
  cursor: pointer;
  transition: border-color .15s ease, color .15s ease;
}

.mini-chip:hover {
  border-color: rgba(255, 255, 255, .24);
}

.mini-on {
  border-color: var(--acc-border);
  color: var(--acc);
}
</style>
