<template>
  <section>
    <div class="ad-toolbar">
      <SegmentedControl
        v-model="statusFilter"
        :options="statusFilters"
      />
      <select
        v-model="providerFilter"
        class="ad-select"
      >
        <option value="">
          All providers
        </option>
        <option value="youtube">
          YouTube
        </option>
        <option value="soundcloud">
          SoundCloud
        </option>
        <option value="spotify">
          Spotify
        </option>
      </select>
    </div>

    <p
      v-if="errorMessage"
      class="ad-error"
    >
      {{ errorMessage }}
    </p>

    <div
      v-if="!loading && !items.length"
      class="ad-none"
    >
      No fetch requests match those filters.
    </div>
    <div
      v-else
      class="ad-panel"
    >
      <div class="ad-head">
        <span>ID</span>
        <span>Provider</span>
        <span>Track</span>
        <span>User</span>
        <span>Status</span>
        <span class="ad-h-c">Attempts</span>
        <span class="ad-h-r">Created</span>
        <span />
      </div>
      <div
        v-for="item in items"
        :key="item.id"
        class="ad-row"
      >
        <div class="ad-id">
          #{{ item.id }}
        </div>
        <div class="ad-prov">
          <span
            class="ad-badge"
            :style="{color: colorFor(item.provider)}"
          >
            {{ shortFor(item.provider) }}
          </span>
        </div>
        <div class="ad-track-meta">
          <div class="ad-title">
            {{ titleFor(item) }}
          </div>
          <div class="ad-sub">
            {{ subFor(item) }}
          </div>
        </div>
        <div class="ad-user">
          {{ item.requested_by_username || '—' }}
        </div>
        <div class="ad-status">
          <span
            class="ad-chip"
            :class="'ad-chip-' + chipClass(item.status)"
            :title="item.error || ''"
          >
            {{ statusLabel(item.status) }}
          </span>
          <div
            v-if="isBusy(item.status)"
            class="ad-progress"
          >
            <div
              class="ad-progress-fill"
              :style="{width: pct(item) + '%'}"
            />
          </div>
        </div>
        <div class="ad-attempts">
          {{ item.attempts }}
        </div>
        <div class="ad-created">
          {{ relativeTime(item.created_at) }}
        </div>
        <div class="ad-actions">
          <button
            v-if="canCancel(item.status)"
            type="button"
            class="ad-act"
            @click="cancel(item)"
          >
            Cancel
          </button>
          <button
            v-if="canRetry(item.status)"
            type="button"
            class="ad-act"
            @click="retry(item)"
          >
            Retry
          </button>
        </div>
      </div>
    </div>

    <div
      v-if="nextCursor"
      class="ad-more"
    >
      <button
        type="button"
        class="ad-more-btn"
        :disabled="loadingMore"
        @click="loadMore"
      >
        {{ loadingMore ? 'Loading…' : 'Load more' }}
      </button>
    </div>
  </section>
</template>

<script>
import axios from 'axios';

import SegmentedControl from '@/components/admin/SegmentedControl.vue';
import { relativeTime } from '@/utils/format';
import { toast } from '@/utils/toast';

const PROVIDERS = {
  youtube: {short: 'YT', color: 'var(--danger)'},
  soundcloud: {short: 'SC', color: 'var(--warn)'},
  spotify: {short: 'SP', color: 'var(--ok)'},
};

const STATUS_META = {
  queued: {label: 'Queued', cls: 'neutral'},
  fetching: {label: 'Fetching', cls: 'acc'},
  postprocessing: {label: 'Processing', cls: 'acc'},
  imported: {label: 'Imported', cls: 'ok'},
  duplicate_skipped: {label: 'Duplicate', cls: 'warn'},
  failed: {label: 'Failed', cls: 'danger'},
  cancelled: {label: 'Cancelled', cls: 'dim'},
};

const ACTIVE = ['queued', 'fetching', 'postprocessing'];

export default {
  name: 'AdminDownloads',
  components: {
    SegmentedControl,
  },
  data() {
    return {
      items: [],
      statusFilter: '',
      providerFilter: '',
      nextCursor: null,
      loading: true,
      loadingMore: false,
      limit: 50,
      errorMessage: '',
    };
  },
  computed: {
    statusFilters() {
      return [
        {value: '', label: 'All'},
        {value: 'queued', label: 'Queued'},
        {value: 'fetching', label: 'Fetching'},
        {value: 'imported', label: 'Imported'},
        {value: 'failed', label: 'Failed'},
        {value: 'cancelled', label: 'Cancelled'},
        {value: 'duplicate_skipped', label: 'Duplicates'},
      ];
    },
  },
  watch: {
    statusFilter() {
      this.fetchList();
    },
    providerFilter() {
      this.fetchList();
    },
  },
  created() {
    return this.fetchList();
  },
  methods: {
    relativeTime,
    shortFor(provider) {
      return (PROVIDERS[provider] || {}).short || '?';
    },
    colorFor(provider) {
      return (PROVIDERS[provider] || {}).color || 'var(--muted)';
    },
    statusLabel(status) {
      return (STATUS_META[status] || {label: status}).label;
    },
    chipClass(status) {
      return (STATUS_META[status] || {cls: 'neutral'}).cls;
    },
    isBusy(status) {
      return status === 'fetching' || status === 'postprocessing';
    },
    canCancel(status) {
      return ACTIVE.indexOf(status) !== -1;
    },
    canRetry(status) {
      return status === 'failed' || status === 'cancelled';
    },
    pct(item) {
      return Math.round((item.progress || 0) * 100);
    },
    titleFor(item) {
      const meta = item.source_metadata;
      return (meta && meta.title) || item.url;
    },
    subFor(item) {
      const meta = item.source_metadata;
      return (meta && meta.artist) || item.url;
    },
    detailOf(error, fallback) {
      const detail = error.response && error.response.data && error.response.data.detail;
      return (typeof detail === 'string' && detail) || fallback;
    },
    params(extra) {
      return {
        status: this.statusFilter || undefined,
        provider: this.providerFilter || undefined,
        limit: this.limit,
        ...extra,
      };
    },
    async fetchList() {
      this.loading = true;
      this.errorMessage = '';
      try {
        const {data} = await axios.get('admin/fetch', {params: this.params()});
        this.items = data.items;
        this.nextCursor = data.next_cursor;
      } catch (error) {
        this.errorMessage = this.detailOf(error, 'Could not load the fetch requests.');
      } finally {
        this.loading = false;
      }
    },
    async loadMore() {
      if (!this.nextCursor) {
        return;
      }
      this.loadingMore = true;
      try {
        const {data} = await axios.get('admin/fetch', {
          params: this.params({cursor: this.nextCursor}),
        });
        this.items = [...this.items, ...data.items];
        this.nextCursor = data.next_cursor;
      } catch (error) {
        toast(this.detailOf(error, 'Could not load more requests.'), 'warn');
      } finally {
        this.loadingMore = false;
      }
    },
    replace(updated) {
      this.items = this.items.map(item => (item.id === updated.id ? updated : item));
    },
    async cancel(item) {
      try {
        const {data} = await axios.post(`fetch/${item.id}/cancel`);
        this.replace(data);
        toast('Request cancelled');
      } catch (error) {
        toast(this.detailOf(error, 'Could not cancel that request.'), 'warn');
      }
    },
    async retry(item) {
      try {
        const {data} = await axios.post(`fetch/${item.id}/retry`);
        this.replace(data);
        toast('Request requeued');
      } catch (error) {
        toast(this.detailOf(error, 'Could not retry that request.'), 'warn');
      }
    },
  },
};
</script>

<style scoped>
.ad-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.ad-select {
  height: 38px;
  padding: 0 12px;
  border-radius: var(--r-ctl);
  border: 1px solid rgba(255, 255, 255, .12);
  background: var(--menu);
  color: var(--txt);
  font: 500 13px var(--font-ui);
  cursor: pointer;
}

.ad-error {
  color: var(--danger);
  font: 400 13px var(--font-ui);
}

.ad-none {
  font: 400 13px var(--font-ui);
  color: var(--dim-2);
  padding: 22px 4px;
}

.ad-panel {
  border: 1px solid var(--line);
  border-radius: 13px;
  overflow: hidden;
  background: var(--panel);
}

.ad-head,
.ad-row {
  display: grid;
  grid-template-columns: 64px 60px minmax(180px, 2fr) 120px 128px 80px 96px 96px;
  align-items: center;
  gap: 12px;
  padding: 0 16px;
}

.ad-head {
  height: 38px;
  border-bottom: 1px solid rgba(255, 255, 255, .07);
  font: 600 10px var(--font-mono);
  letter-spacing: .08em;
  color: var(--dim-2);
  text-transform: uppercase;
}

.ad-h-c {
  text-align: center;
}

.ad-h-r {
  text-align: right;
}

.ad-row {
  min-height: 58px;
  border-bottom: 1px solid rgba(255, 255, 255, .045);
  transition: background .15s ease;
}

.ad-row:last-child {
  border-bottom: none;
}

.ad-row:hover {
  background: rgba(255, 255, 255, .03);
}

.ad-id {
  font: 600 12px var(--font-mono);
  color: var(--dim);
}

.ad-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 22px;
  border-radius: 6px;
  background: rgba(255, 255, 255, .05);
  border: 1px solid rgba(255, 255, 255, .08);
  font: 600 10px var(--font-mono);
  letter-spacing: .04em;
}

.ad-track-meta {
  min-width: 0;
}

.ad-title {
  font: 600 13px var(--font-ui);
  color: var(--txt);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ad-sub {
  font: 400 12px var(--font-ui);
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ad-user {
  font: 500 12px var(--font-ui);
  color: var(--txt-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ad-chip {
  display: inline-block;
  padding: 4px 10px;
  border-radius: var(--r-pill);
  font: 600 11px var(--font-ui);
  white-space: nowrap;
}

.ad-chip-neutral {
  background: rgba(255, 255, 255, .06);
  color: var(--txt-2);
}

.ad-chip-acc {
  background: var(--acc-soft-strong);
  color: var(--acc);
}

.ad-chip-ok {
  background: rgba(53, 208, 122, .13);
  color: var(--ok);
}

.ad-chip-warn {
  background: rgba(255, 182, 46, .13);
  color: var(--warn);
}

.ad-chip-danger {
  background: rgba(255, 82, 102, .13);
  color: var(--danger);
}

.ad-chip-dim {
  background: rgba(255, 255, 255, .04);
  color: var(--dim);
}

.ad-progress {
  height: 3px;
  border-radius: 3px;
  background: rgba(255, 255, 255, .08);
  overflow: hidden;
  margin-top: 6px;
}

.ad-progress-fill {
  height: 100%;
  background: var(--acc);
  border-radius: 3px;
  transition: width .3s ease;
}

.ad-attempts {
  text-align: center;
  font: 600 12px var(--font-mono);
  color: var(--txt-2);
}

.ad-created {
  text-align: right;
  font: 400 12px var(--font-mono);
  color: var(--dim);
}

.ad-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
}

.ad-act {
  height: 30px;
  padding: 0 11px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line-strong);
  background: rgba(255, 255, 255, .03);
  color: var(--txt-2);
  font: 600 12px var(--font-ui);
  cursor: pointer;
  transition: border-color .15s ease, color .15s ease;
}

.ad-act:hover {
  border-color: var(--acc-border);
  color: var(--txt);
}

.ad-more {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}

.ad-more-btn {
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

.ad-more-btn:hover:enabled {
  border-color: var(--acc-border);
  color: var(--txt);
}

.ad-more-btn:disabled {
  opacity: .5;
  cursor: default;
}
</style>
