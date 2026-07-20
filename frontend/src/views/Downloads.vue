<template>
  <section>
    <SegmentedControl
      v-if="canFetch"
      v-model="tab"
      class="dl-tabs"
      :options="tabs"
    />

    <FetchQueue
      v-if="canFetch && tab === 'fetch'"
      :providers="providers"
    />

    <template v-if="!canFetch || tab === 'history'">
      <div class="dl-cards">
        <div class="dl-card">
          <div class="dl-card-label">
            THIS MONTH
          </div>
          <div class="dl-card-value">
            {{ usedLabel }}
          </div>
        </div>
        <div class="dl-card">
          <div class="dl-card-label">
            REMAINING
          </div>
          <div class="dl-card-value dl-card-acc">
            {{ remainingLabel }}
          </div>
        </div>
        <div class="dl-card">
          <div class="dl-card-label">
            MONTHLY QUOTA
          </div>
          <div class="dl-card-value">
            {{ limitLabel }}
          </div>
        </div>
      </div>

      <p
        v-if="errorMessage"
        class="dl-error"
      >
        {{ errorMessage }}
      </p>

      <div
        v-if="!loading && !items.length"
        class="dl-none"
      >
        No downloads yet.
      </div>
      <div
        v-else
        class="dl-panel"
      >
        <div class="dl-head">
          <span>Track</span>
          <span>Version</span>
          <span>Format</span>
          <span class="dl-h-c">Key / BPM</span>
          <span class="dl-h-r">Downloaded</span>
          <span />
        </div>
        <div
          v-for="item in items"
          :key="item.id"
          class="dl-row"
        >
          <div class="dl-track">
            <div
              class="dl-cover"
              :style="{background: tint(item.song)}"
            >
              {{ initials(item.song) }}
            </div>
            <div class="dl-track-meta">
              <div class="dl-title">
                {{ item.song.title || 'Untitled' }}
              </div>
              <div class="dl-sub">
                {{ item.song.artist || 'Unknown artist' }} · {{ item.song.genre || '—' }}
              </div>
            </div>
          </div>
          <div>
            <span class="dl-chip">Original</span>
          </div>
          <div class="dl-format">
            {{ item.format.toUpperCase() }}
          </div>
          <div class="dl-keybpm">
            <span class="dl-key">{{ keyLabel(item.song) }}</span>
            <span class="dl-sep">·</span>
            <span class="dl-bpm">{{ bpmLabel(item.song) }}</span>
          </div>
          <div class="dl-when">
            {{ relativeTime(item.downloaded_at) }}
          </div>
          <div class="dl-again-cell">
            <button
              type="button"
              class="dl-again"
              title="Download again"
              @click="reDownload(item)"
            >
              <svg
                width="15"
                height="15"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <path d="M12 3v12" />
                <path d="M7 11l5 5 5-5" />
                <path d="M4 20h16" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      <nav
        v-if="totalPages > 1"
        class="pager"
      >
        <button
          type="button"
          class="pager-btn"
          :disabled="page <= 1"
          @click="goToPage(page - 1)"
        >
          Previous
        </button>
        <span class="pager-info">Page {{ page }} of {{ totalPages }}</span>
        <button
          type="button"
          class="pager-btn"
          :disabled="page >= totalPages"
          @click="goToPage(page + 1)"
        >
          Next
        </button>
      </nav>
    </template>
  </section>
</template>

<script>
import axios from 'axios';

import FetchQueue from '@/components/FetchQueue.vue';
import SegmentedControl from '@/components/admin/SegmentedControl.vue';
import { downloadSong } from '@/utils/download';

export default {
  name: 'DownloadsView',
  components: {
    FetchQueue,
    SegmentedControl,
  },
  data() {
    return {
      items: [],
      total: 0,
      page: 1,
      pageSize: 50,
      loading: true,
      errorMessage: '',
      // Fetch engine (MOO-78): the History | Fetch switcher only appears when
      // the member may upload and the engine reports itself enabled.
      tab: 'history',
      providers: null,
      fetchEnabled: false,
    };
  },
  computed: {
    canFetch() {
      return this.$store.getters.userPermissions.upload_tracks === true && this.fetchEnabled;
    },
    tabs() {
      return [
        {value: 'history', label: 'History'},
        {value: 'fetch', label: 'Fetch'},
      ];
    },
    quota() {
      return this.$store.getters.stateQuota;
    },
    usedLabel() {
      return this.quota ? String(this.quota.used) : '—';
    },
    remainingLabel() {
      if (!this.quota) {
        return '—';
      }
      return this.quota.unlimited ? '∞' : String(this.quota.remaining);
    },
    limitLabel() {
      if (!this.quota) {
        return '—';
      }
      return this.quota.unlimited ? '∞' : String(this.quota.limit);
    },
    totalPages() {
      return Math.max(1, Math.ceil(this.total / this.pageSize));
    },
  },
  created() {
    this.$store.dispatch('fetchQuota');
    this.fetchProviders();
    return this.fetchHistory();
  },
  methods: {
    async fetchProviders() {
      // Best-effort: the engine may be off or the endpoint absent, in which
      // case the switcher stays hidden and this view is unchanged.
      try {
        const {data} = await axios.get('fetch/providers');
        this.providers = data;
        this.fetchEnabled = data.enabled === true;
      } catch (error) {
        this.fetchEnabled = false;
      }
    },
    async fetchHistory() {
      this.loading = true;
      this.errorMessage = '';
      try {
        const {data} = await axios.get('downloads', {
          params: {page: this.page, page_size: this.pageSize},
        });
        this.items = data.items;
        this.total = data.total;
      } catch (error) {
        const detail = error.response && error.response.data && error.response.data.detail;
        this.errorMessage =
          (typeof detail === 'string' && detail) ||
          'Could not load your download history.';
      } finally {
        this.loading = false;
      }
    },
    goToPage(page) {
      this.page = page;
      this.fetchHistory();
    },
    async reDownload(item) {
      // Re-downloads never count against the quota, but they do add a fresh
      // history entry — refetch so the newest row shows up.
      if (await downloadSong(item.song, item.format)) {
        this.page = 1;
        this.fetchHistory();
      }
    },
    initials(song) {
      const source = song.title || song.artist || '?';
      const words = source.trim().split(/\s+/);
      const letters = words.length > 1
        ? words[0][0] + words[1][0]
        : source.slice(0, 2);
      return letters.toUpperCase();
    },
    tint(song) {
      return `var(--tint-${(song.id % 10) + 1})`;
    },
    keyLabel(song) {
      return song.camelot_key || song.musical_key || '—';
    },
    bpmLabel(song) {
      return song.bpm == null ? '—' : String(Math.round(song.bpm));
    },
    relativeTime(value) {
      // The backend serializes naive UTC datetimes; force the Z suffix so
      // the browser doesn't parse them as local time.
      const iso = /Z|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`;
      const seconds = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
      if (seconds < 60) {
        return 'just now';
      }
      const minutes = Math.round(seconds / 60);
      if (minutes < 60) {
        return `${minutes}m ago`;
      }
      const hours = Math.round(minutes / 60);
      if (hours < 24) {
        return `${hours}h ago`;
      }
      return `${Math.round(hours / 24)}d ago`;
    },
  },
};
</script>

<style scoped>
.dl-tabs {
  margin-bottom: 20px;
}

.dl-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 20px;
  max-width: 640px;
}

.dl-card {
  padding: 16px;
  border-radius: var(--r-panel);
  background: var(--panel);
  border: 1px solid var(--line);
}

.dl-card-label {
  font: 600 10px var(--font-mono);
  letter-spacing: .08em;
  color: var(--dim-2);
  margin-bottom: 8px;
}

.dl-card-value {
  font: 600 26px var(--font-disp);
  color: var(--txt);
}

.dl-card-acc {
  color: var(--acc);
}

.dl-error {
  font: 400 12.5px var(--font-ui);
  color: var(--danger);
  margin: 0 0 12px;
}

.dl-none {
  padding: 60px;
  text-align: center;
  color: var(--dim-2);
  font: 400 14px var(--font-ui);
}

.dl-panel {
  border: 1px solid var(--line);
  border-radius: 13px;
  overflow: hidden;
  background: var(--panel);
}

.dl-head,
.dl-row {
  display: grid;
  grid-template-columns: minmax(200px, 2fr) 130px 96px 96px 116px 44px;
  align-items: center;
  gap: 12px;
  padding: 0 16px;
}

.dl-head {
  height: 36px;
  border-bottom: 1px solid rgba(255, 255, 255, .07);
  font: 600 10px var(--font-mono);
  letter-spacing: .08em;
  color: var(--dim-2);
  text-transform: uppercase;
}

.dl-h-c {
  text-align: center;
}

.dl-h-r {
  text-align: right;
}

.dl-row {
  height: 56px;
  border-bottom: 1px solid rgba(255, 255, 255, .045);
  transition: background .15s ease;
}

.dl-row:hover {
  background: rgba(255, 255, 255, .03);
}

.dl-track {
  display: flex;
  align-items: center;
  gap: 11px;
  min-width: 0;
}

.dl-cover {
  width: 38px;
  height: 38px;
  border-radius: 7px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: none;
  box-shadow: var(--shadow-cover);
  font: 600 10px var(--font-mono);
  color: rgba(255, 255, 255, .7);
}

.dl-track-meta {
  min-width: 0;
}

.dl-title {
  font: 600 13px var(--font-ui);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dl-sub {
  font: 400 12px var(--font-ui);
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dl-chip {
  padding: 4px 9px;
  border-radius: 6px;
  background: rgba(255, 255, 255, .05);
  border: 1px solid rgba(255, 255, 255, .08);
  font: 500 11.5px var(--font-ui);
  color: var(--txt-2);
}

.dl-format {
  font: 600 12px var(--font-mono);
  color: var(--txt-3);
}

.dl-keybpm {
  text-align: center;
  font: 500 12px var(--font-mono);
}

.dl-key {
  color: var(--key);
}

.dl-sep {
  color: var(--dim-2);
}

.dl-bpm {
  color: var(--txt-2);
}

.dl-when {
  text-align: right;
  font: 400 12px var(--font-mono);
  color: var(--dim);
}

.dl-again-cell {
  display: flex;
  justify-content: flex-end;
}

.dl-again {
  background: none;
  border: 1px solid var(--line-strong);
  padding: 0;
  margin: 0;
  cursor: pointer;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: var(--muted);
  transition: color .15s ease, border-color .15s ease;
}

.dl-again:hover {
  color: var(--acc);
  border-color: color-mix(in oklab, var(--acc) 45%, transparent);
}

.pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 16px;
}

.pager-btn {
  height: 32px;
  padding: 0 14px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line-strong);
  background: rgba(255, 255, 255, .03);
  color: var(--txt-2);
  font: 600 12px var(--font-ui);
  cursor: pointer;
  transition: border-color .15s ease, color .15s ease;
}

.pager-btn:hover:enabled {
  border-color: var(--acc-border);
  color: var(--txt);
}

.pager-btn:disabled {
  opacity: .45;
  cursor: default;
}

.pager-info {
  font: 500 12px var(--font-mono);
  color: var(--dim);
}
</style>
