<template>
  <div class="mg">
    <div class="mg-head">
      <button
        type="button"
        class="mg-nav"
        @click="$emit('prev')"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        ><path d="M15 6l-6 6 6 6" /></svg>
      </button>
      <div class="mg-title">
        {{ title }}
      </div>
      <button
        type="button"
        class="mg-nav"
        @click="$emit('next')"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        ><path d="M9 6l6 6-6 6" /></svg>
      </button>
    </div>
    <div class="mg-weekdays">
      <span
        v-for="label in weekdayLabels"
        :key="label"
      >{{ label }}</span>
    </div>
    <div class="mg-grid">
      <div
        v-for="cell in cells"
        :key="cell.iso"
        class="mg-cell"
        :class="{'mg-cell-dim': !cell.inMonth, 'mg-cell-today': cell.isToday}"
      >
        <div class="mg-daynum">
          {{ cell.day }}
        </div>
        <router-link
          v-for="release in cell.releases.slice(0, 3)"
          :key="release.id"
          class="mg-chip"
          :to="`/artist/${release.artist.id}`"
        >
          <span
            class="mg-dot"
            :class="`mg-dot-${release.status}`"
          />
          <span class="mg-chip-text">{{ release.title }}</span>
        </router-link>
        <div
          v-if="cell.releases.length > 3"
          class="mg-more"
        >
          +{{ cell.releases.length - 3 }} more
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'MonthGrid',
  props: {
    month: {
      type: String,
      required: true, // YYYY-MM
    },
    days: {
      type: Array,
      default: () => [], // [{date, releases}]
    },
  },
  emits: ['prev', 'next'],
  data() {
    return {
      weekdayLabels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
    };
  },
  computed: {
    title() {
      const [year, mon] = this.month.split('-').map(Number);
      const d = new Date(Date.UTC(year, mon - 1, 1));
      return d.toLocaleDateString('en-US', {month: 'long', year: 'numeric', timeZone: 'UTC'});
    },
    releasesByDate() {
      const map = {};
      this.days.forEach(day => {
        map[day.date] = day.releases;
      });
      return map;
    },
    cells() {
      const [year, mon] = this.month.split('-').map(Number);
      const first = new Date(Date.UTC(year, mon - 1, 1));
      const last = new Date(Date.UTC(year, mon, 0));
      // Monday-first offset: JS getUTCDay() is 0=Sun..6=Sat.
      const leading = (first.getUTCDay() + 6) % 7;
      const totalDays = last.getUTCDate();
      const totalCells = Math.ceil((leading + totalDays) / 7) * 7;
      const todayIso = new Date().toISOString().slice(0, 10);
      const cells = [];
      for (let i = 0; i < totalCells; i += 1) {
        const date = new Date(Date.UTC(year, mon - 1, 1 - leading + i));
        const iso = date.toISOString().slice(0, 10);
        cells.push({
          iso,
          day: date.getUTCDate(),
          inMonth: date.getUTCMonth() === mon - 1,
          isToday: iso === todayIso,
          releases: this.releasesByDate[iso] || [],
        });
      }
      return cells;
    },
  },
};
</script>

<style scoped>
.mg-head {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  margin-bottom: 14px;
}

.mg-title {
  font: 600 15px var(--font-mono);
  min-width: 160px;
  text-align: center;
}

.mg-nav {
  width: 30px;
  height: 30px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line-strong);
  background: rgba(255, 255, 255, .03);
  color: var(--txt-2);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.mg-nav:hover {
  border-color: var(--acc-border);
  color: var(--txt);
}

.mg-weekdays {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  padding: 0 2px 6px;
  font: 600 10px var(--font-mono);
  letter-spacing: .08em;
  color: var(--dim-3);
  text-transform: uppercase;
  text-align: center;
}

.mg-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 6px;
}

.mg-cell {
  min-height: 92px;
  border-radius: 10px;
  border: 1px solid var(--line);
  background: var(--panel);
  padding: 6px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.mg-cell-dim {
  opacity: .38;
}

.mg-cell-today {
  border-color: var(--acc-border);
}

.mg-daynum {
  font: 600 11px var(--font-mono);
  color: var(--dim-2);
  margin-bottom: 2px;
}

.mg-chip {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 2px 5px;
  border-radius: 5px;
  background: rgba(255, 255, 255, .04);
  font: 500 10.5px var(--font-ui);
  color: var(--txt-2);
  white-space: nowrap;
  overflow: hidden;
}

.mg-chip:hover {
  background: rgba(255, 255, 255, .08);
}

.mg-chip-text {
  overflow: hidden;
  text-overflow: ellipsis;
}

.mg-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex: none;
  background: var(--dim-2);
}

.mg-dot-in_library {
  background: var(--ok, #5ac882);
}

.mg-dot-missing {
  background: var(--warn);
}

.mg-dot-grabbed {
  background: var(--acc);
}

.mg-more {
  font: 500 10px var(--font-mono);
  color: var(--dim-3);
  padding: 0 5px;
}
</style>
