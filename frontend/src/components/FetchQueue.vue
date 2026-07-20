<template>
  <div class="fq">
    <div class="fq-submit">
      <div class="fq-input-wrap">
        <span
          v-if="detected"
          class="fq-badge fq-badge-inline"
          :class="{'fq-badge-off': providerDisabled}"
          :style="{color: colorFor(detected)}"
        >
          {{ shortFor(detected) }}
        </span>
        <input
          v-model="url"
          type="text"
          class="fq-input"
          :class="{'fq-input-badged': detected}"
          placeholder="Paste a YouTube, SoundCloud or Spotify track URL…"
          @keyup.enter="submit"
        >
      </div>
      <button
        type="button"
        class="fq-fetch"
        :disabled="!url.trim() || submitting"
        @click="submit"
      >
        {{ submitting ? 'Fetching…' : 'Fetch' }}
      </button>
    </div>

    <p
      v-if="submitError"
      class="fq-error"
    >
      {{ submitError }}
    </p>

    <div
      v-if="providers && providers.daily_limit > 0"
      class="fq-quota"
    >
      {{ providers.used_today }} of {{ providers.daily_limit }} today
    </div>

    <div
      v-if="!loading && !items.length"
      class="fq-none"
    >
      No fetch requests yet.
    </div>
    <div
      v-else
      class="fq-list"
    >
      <div
        v-for="item in items"
        :key="item.id"
        class="fq-row"
      >
        <span
          class="fq-badge"
          :style="{color: colorFor(item.provider)}"
        >
          {{ shortFor(item.provider) }}
        </span>
        <div class="fq-meta">
          <router-link
            v-if="linkFor(item)"
            :to="linkFor(item)"
            class="fq-title fq-title-link"
            :title="item.error || ''"
          >
            {{ titleFor(item) }}
          </router-link>
          <div
            v-else
            class="fq-title"
            :title="item.error || ''"
          >
            {{ titleFor(item) }}
          </div>
          <div class="fq-sub">
            {{ subFor(item) }}
          </div>
          <div
            v-if="isBusy(item.status)"
            class="fq-progress"
          >
            <div
              class="fq-progress-fill"
              :style="{width: pct(item) + '%'}"
            />
          </div>
        </div>
        <span
          class="fq-chip"
          :class="'fq-chip-' + chipClass(item.status)"
        >
          {{ statusLabel(item.status) }}
        </span>
        <div class="fq-actions">
          <button
            v-if="canCancel(item.status)"
            type="button"
            class="fq-act"
            @click="cancel(item)"
          >
            Cancel
          </button>
          <button
            v-if="canRetry(item.status)"
            type="button"
            class="fq-act"
            @click="retry(item)"
          >
            Retry
          </button>
        </div>
      </div>
    </div>

    <div
      v-if="nextCursor"
      class="fq-more"
    >
      <button
        type="button"
        class="fq-more-btn"
        :disabled="loadingMore"
        @click="loadMore"
      >
        {{ loadingMore ? 'Loading…' : 'Load more' }}
      </button>
    </div>
  </div>
</template>

<script>
import axios from 'axios';

import { toast } from '@/utils/toast';

// Client-side hostname → provider detection, mirrored to the badge shown in
// the submit row and each request row.
const PROVIDERS = {
  youtube: {short: 'YT', color: 'var(--danger)'},
  soundcloud: {short: 'SC', color: 'var(--warn)'},
  spotify: {short: 'SP', color: 'var(--ok)'},
};

// Status → chip label + colour class. The active states also draw a thin
// progress bar under the title.
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
  name: 'FetchQueue',
  props: {
    // The /fetch/providers payload from the parent (enabled flags + quota).
    providers: {
      type: Object,
      default: null,
    },
  },
  data() {
    return {
      url: '',
      submitError: '',
      submitting: false,
      items: [],
      nextCursor: null,
      loading: true,
      loadingMore: false,
      limit: 20,
      pollTimer: null,
    };
  },
  computed: {
    detected() {
      return this.detectProvider(this.url);
    },
    providerDisabled() {
      return !!(
        this.detected &&
        this.providers &&
        this.providers.providers &&
        this.providers.providers[this.detected] === false
      );
    },
    hasActive() {
      return this.items.some(item => this.isActive(item.status));
    },
  },
  created() {
    return this.fetchList();
  },
  beforeUnmount() {
    this.stopPolling();
  },
  methods: {
    detectProvider(value) {
      let host;
      try {
        host = new URL(value.trim()).hostname.replace(/^www\./, '');
      } catch (error) {
        return null;
      }
      if (/(^|\.)youtube\.com$/.test(host) || host === 'youtu.be') {
        return 'youtube';
      }
      if (/(^|\.)soundcloud\.com$/.test(host)) {
        return 'soundcloud';
      }
      if (/(^|\.)spotify\.com$/.test(host)) {
        return 'spotify';
      }
      return null;
    },
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
    isActive(status) {
      return ACTIVE.indexOf(status) !== -1;
    },
    isBusy(status) {
      return status === 'fetching' || status === 'postprocessing';
    },
    canCancel(status) {
      return this.isActive(status);
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
      if (meta && meta.artist) {
        return meta.album ? `${meta.artist} · ${meta.album}` : meta.artist;
      }
      return item.url;
    },
    linkFor(item) {
      if ((item.status === 'imported' || item.status === 'duplicate_skipped') && item.song_id) {
        return `/release/${item.song_id}`;
      }
      return null;
    },
    detailOf(error, fallback) {
      const detail = error.response && error.response.data && error.response.data.detail;
      return (typeof detail === 'string' && detail) || fallback;
    },
    async submit() {
      const url = this.url.trim();
      if (!url || this.submitting) {
        return;
      }
      this.submitting = true;
      this.submitError = '';
      try {
        const {data} = await axios.post('fetch', {url});
        this.items = [data, ...this.items];
        this.url = '';
        toast('Added to the fetch queue');
        this.syncPolling();
      } catch (error) {
        this.submitError = this.detailOf(error, 'Could not queue that URL.');
      } finally {
        this.submitting = false;
      }
    },
    async fetchList() {
      this.loading = true;
      try {
        const {data} = await axios.get('fetch', {params: {limit: this.limit}});
        this.items = data.items;
        this.nextCursor = data.next_cursor;
        this.syncPolling();
      } catch (error) {
        // The axios interceptor already surfaced the failure.
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
        const {data} = await axios.get('fetch', {
          params: {limit: this.limit, cursor: this.nextCursor},
        });
        this.items = [...this.items, ...data.items];
        this.nextCursor = data.next_cursor;
      } catch (error) {
        // The axios interceptor already surfaced the failure.
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
        this.syncPolling();
      } catch (error) {
        toast(this.detailOf(error, 'Could not cancel that request.'), 'warn');
      }
    },
    async retry(item) {
      try {
        const {data} = await axios.post(`fetch/${item.id}/retry`);
        this.replace(data);
        this.syncPolling();
      } catch (error) {
        toast(this.detailOf(error, 'Could not retry that request.'), 'warn');
      }
    },
    merge(fetched) {
      const byId = new Map(fetched.map(item => [item.id, item]));
      this.items = this.items.map(item => byId.get(item.id) || item);
      const known = new Set(this.items.map(item => item.id));
      const fresh = fetched.filter(item => !known.has(item.id));
      if (fresh.length) {
        this.items = [...fresh, ...this.items];
      }
    },
    async poll() {
      if (!this.hasActive) {
        this.stopPolling();
        return;
      }
      try {
        const {data} = await axios.get('fetch', {params: {limit: this.limit}});
        this.merge(data.items);
      } catch (error) {
        // Transient poll failure — keep the interval and try again.
      }
      this.syncPolling();
    },
    syncPolling() {
      if (this.hasActive) {
        this.startPolling();
      } else {
        this.stopPolling();
      }
    },
    startPolling() {
      if (this.pollTimer) {
        return;
      }
      this.pollTimer = setInterval(this.poll, 3000);
    },
    stopPolling() {
      if (this.pollTimer) {
        clearInterval(this.pollTimer);
        this.pollTimer = null;
      }
    },
  },
};
</script>

<style scoped>
.fq-submit {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  max-width: 720px;
}

.fq-input-wrap {
  position: relative;
  flex: 1;
}

.fq-input {
  width: 100%;
  height: 40px;
  padding: 0 12px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line-strong);
  background: var(--raised);
  color: var(--txt);
  font: 400 13px var(--font-ui);
  box-sizing: border-box;
}

.fq-input-badged {
  padding-left: 46px;
}

.fq-input::placeholder {
  color: var(--dim-2);
}

.fq-input:focus {
  outline: none;
  border-color: var(--acc-border);
}

.fq-badge-inline {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
}

.fq-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 22px;
  flex: none;
  border-radius: 6px;
  background: rgba(255, 255, 255, .05);
  border: 1px solid rgba(255, 255, 255, .08);
  font: 600 10px var(--font-mono);
  letter-spacing: .04em;
}

.fq-badge-off {
  opacity: .4;
}

.fq-fetch {
  height: 40px;
  padding: 0 18px;
  border-radius: var(--r-ctl);
  border: none;
  background: var(--acc);
  color: var(--acc-ink);
  font: 600 13px var(--font-ui);
  cursor: pointer;
  flex: none;
  transition: filter .15s ease;
}

.fq-fetch:hover:enabled {
  filter: brightness(1.1);
}

.fq-fetch:disabled {
  opacity: .5;
  cursor: default;
}

.fq-error {
  font: 400 12.5px var(--font-ui);
  color: var(--danger);
  margin: 0 0 12px;
}

.fq-quota {
  font: 500 11px var(--font-mono);
  color: var(--dim);
  margin-bottom: 14px;
}

.fq-none {
  padding: 60px;
  text-align: center;
  color: var(--dim-2);
  font: 400 14px var(--font-ui);
}

.fq-list {
  border: 1px solid var(--line);
  border-radius: 13px;
  overflow: hidden;
  background: var(--panel);
}

.fq-row {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) 108px 96px;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, .045);
}

.fq-row:last-child {
  border-bottom: none;
}

.fq-row:hover {
  background: rgba(255, 255, 255, .03);
}

.fq-meta {
  min-width: 0;
}

.fq-title {
  display: block;
  font: 600 13px var(--font-ui);
  color: var(--txt);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.fq-title-link:hover {
  color: var(--acc);
}

.fq-sub {
  font: 400 12px var(--font-ui);
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 2px;
}

.fq-progress {
  height: 3px;
  border-radius: 3px;
  background: rgba(255, 255, 255, .08);
  overflow: hidden;
  margin-top: 7px;
}

.fq-progress-fill {
  height: 100%;
  background: var(--acc);
  border-radius: 3px;
  transition: width .3s ease;
}

.fq-chip {
  justify-self: start;
  padding: 4px 10px;
  border-radius: var(--r-pill);
  font: 600 11px var(--font-ui);
  white-space: nowrap;
}

.fq-chip-neutral {
  background: rgba(255, 255, 255, .06);
  color: var(--txt-2);
}

.fq-chip-acc {
  background: var(--acc-soft-strong);
  color: var(--acc);
}

.fq-chip-ok {
  background: rgba(53, 208, 122, .13);
  color: var(--ok);
}

.fq-chip-warn {
  background: rgba(255, 182, 46, .13);
  color: var(--warn);
}

.fq-chip-danger {
  background: rgba(255, 82, 102, .13);
  color: var(--danger);
}

.fq-chip-dim {
  background: rgba(255, 255, 255, .04);
  color: var(--dim);
}

.fq-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
}

.fq-act {
  height: 30px;
  padding: 0 12px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line-strong);
  background: rgba(255, 255, 255, .03);
  color: var(--txt-2);
  font: 600 12px var(--font-ui);
  cursor: pointer;
  transition: border-color .15s ease, color .15s ease;
}

.fq-act:hover {
  border-color: var(--acc-border);
  color: var(--txt);
}

.fq-more {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}

.fq-more-btn {
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

.fq-more-btn:hover:enabled {
  border-color: var(--acc-border);
  color: var(--txt);
}

.fq-more-btn:disabled {
  opacity: .5;
  cursor: default;
}
</style>
