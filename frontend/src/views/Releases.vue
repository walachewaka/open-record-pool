<template>
  <section>
    <div class="rl-toolbar">
      <SegmentedControl
        v-model="mode"
        :options="[
          {value: 'upcoming', label: 'Upcoming'},
          {value: 'recent', label: 'Recent'},
          {value: 'calendar', label: 'Calendar'},
        ]"
        @update:model-value="onModeChange"
      />
      <SegmentedControl
        v-model="scope"
        :options="[{value: 'following', label: 'Following'}, {value: 'everyone', label: 'Everyone'}]"
        @update:model-value="reload"
      />
    </div>

    <div
      v-if="mode === 'calendar'"
      class="list-panel rl-calendar-panel"
    >
      <MonthGrid
        :month="month"
        :days="calendarDays"
        @prev="shiftMonth(-1)"
        @next="shiftMonth(1)"
      />
    </div>
    <template v-else>
      <div class="list-panel">
        <div
          v-if="!loading && !releases.length"
          class="list-empty"
        >
          <template v-if="scope === 'following' && !hasAnyFollow">
            Follow artists to start tracking releases.
            <router-link to="/artists">
              Browse artists
            </router-link>
          </template>
          <template v-else>
            No releases tracked yet. Releases appear once a release source (Beatport) is configured.
          </template>
        </div>
        <ReleaseRow
          v-for="release in releases"
          :key="release.id"
          :release="release"
          @updated="row => replaceRelease(row)"
        />
      </div>
      <button
        v-if="nextCursor"
        type="button"
        class="rl-more"
        :disabled="loading"
        @click="loadMore"
      >
        Load more
      </button>
    </template>
  </section>
</template>

<script>
import axios from 'axios';

import MonthGrid from '@/components/MonthGrid.vue';
import ReleaseRow from '@/components/ReleaseRow.vue';
import SegmentedControl from '@/components/admin/SegmentedControl.vue';

function currentMonth() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

export default {
  name: 'ReleasesView',
  components: {MonthGrid, ReleaseRow, SegmentedControl},
  data() {
    return {
      mode: 'upcoming',
      scope: 'following',
      releases: [],
      nextCursor: null,
      loading: true,
      month: currentMonth(),
      calendarDays: [],
      hasAnyFollow: true,
    };
  },
  created() {
    this.$store.dispatch('markFeedSeen');
    this.reload();
  },
  methods: {
    onModeChange() {
      if (this.mode === 'calendar') {
        this.loadCalendar();
      } else {
        this.reload();
      }
    },
    async reload() {
      if (this.mode === 'calendar') {
        this.loadCalendar();
        return;
      }
      this.loading = true;
      try {
        const {data} = await axios.get('releases', {
          params: {
            range: this.mode,
            followed_only: this.scope === 'following',
            limit: 50,
          },
        });
        this.releases = data.items;
        this.nextCursor = data.next_cursor;
        this.hasAnyFollow = this.releases.length > 0 || this.scope !== 'following';
      } finally {
        this.loading = false;
      }
    },
    async loadMore() {
      if (!this.nextCursor) {
        return;
      }
      this.loading = true;
      try {
        const {data} = await axios.get('releases', {
          params: {
            range: this.mode,
            followed_only: this.scope === 'following',
            limit: 50,
            cursor: this.nextCursor,
          },
        });
        this.releases = [...this.releases, ...data.items];
        this.nextCursor = data.next_cursor;
      } finally {
        this.loading = false;
      }
    },
    async loadCalendar() {
      this.loading = true;
      try {
        const {data} = await axios.get('releases/calendar', {
          params: {month: this.month, followed_only: this.scope === 'following'},
        });
        this.calendarDays = data.days;
      } finally {
        this.loading = false;
      }
    },
    shiftMonth(delta) {
      const [year, mon] = this.month.split('-').map(Number);
      const d = new Date(Date.UTC(year, mon - 1 + delta, 1));
      this.month = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
      this.loadCalendar();
    },
    replaceRelease(row) {
      this.releases = this.releases.map(r => (r.id === row.id ? row : r));
    },
  },
};
</script>

<style scoped>
.rl-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.list-panel {
  border: 1px solid var(--line);
  border-radius: 13px;
  overflow: hidden;
  background: var(--panel);
}

.rl-calendar-panel {
  padding: 16px;
}

.list-empty {
  padding: 56px 20px;
  text-align: center;
  color: var(--dim-2);
  font: 400 14px var(--font-ui);
}

.rl-more {
  margin: 14px auto 0;
  display: block;
  height: 36px;
  padding: 0 18px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line-strong);
  background: rgba(255, 255, 255, .03);
  color: var(--txt-2);
  font: 600 12.5px var(--font-ui);
  cursor: pointer;
}
</style>
