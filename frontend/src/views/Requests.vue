<template>
  <section>
    <div class="rq-form">
      <SegmentedControl
        v-model="kind"
        class="rq-kind"
        :options="kindOptions"
      />

      <template v-if="kind === 'free_text'">
        <div class="rq-row">
          <input
            v-model="artist"
            type="text"
            class="rq-input"
            placeholder="Artist"
          >
          <input
            v-model="title"
            type="text"
            class="rq-input"
            placeholder="Title"
          >
        </div>
        <div class="rq-row">
          <input
            v-model="mixName"
            type="text"
            class="rq-input"
            placeholder="Mix name (optional, e.g. Extended Mix)"
          >
        </div>
        <div
          v-if="matches.length"
          class="rq-matches"
        >
          <div class="rq-matches-label">
            Already in the pool?
          </div>
          <router-link
            v-for="song in matches"
            :key="song.id"
            :to="`/release/${song.id}`"
            class="rq-match"
          >
            <span class="rq-match-title">{{ song.title || 'Untitled' }}</span>
            <span class="rq-match-sub">{{ song.artist || 'Unknown artist' }}</span>
          </router-link>
        </div>
      </template>

      <template v-else>
        <div class="rq-row">
          <div class="rq-url-wrap">
            <span
              v-if="detected"
              class="rq-badge rq-badge-inline"
              :style="{color: colorFor(detected)}"
            >{{ shortFor(detected) }}</span>
            <input
              v-model="sourceUrl"
              type="text"
              class="rq-input"
              :class="{'rq-input-badged': detected}"
              placeholder="Paste a YouTube, SoundCloud or Spotify track URL…"
            >
          </div>
        </div>
        <p
          v-if="sourceUrl.trim() && !detected"
          class="rq-hint"
        >
          Unsupported host. Paste a full youtube.com, soundcloud.com or open.spotify.com track URL.
        </p>
      </template>

      <div class="rq-row">
        <input
          v-model="notes"
          type="text"
          class="rq-input"
          maxlength="500"
          placeholder="Notes (optional)"
        >
      </div>

      <p
        v-if="submitError"
        class="rq-error"
      >
        {{ submitError }}
      </p>

      <button
        type="button"
        class="rq-submit"
        :disabled="!canSubmit || submitting"
        @click="submit"
      >
        {{ submitting ? 'Submitting…' : 'Submit request' }}
      </button>
    </div>

    <SegmentedControl
      v-model="statusFilter"
      class="rq-filters"
      :options="statusFilters"
    />

    <div
      v-if="!loading && !items.length"
      class="rq-none"
    >
      No requests yet — ask for a track above.
    </div>
    <div
      v-else
      class="rq-list"
    >
      <div
        v-for="item in items"
        :key="item.id"
        class="rq-item"
      >
        <div class="rq-meta">
          <div class="rq-item-title">
            {{ titleFor(item) }}
          </div>
          <div class="rq-item-sub">
            {{ subFor(item) }} · {{ relativeTime(item.created_at) }}
          </div>
          <div
            v-if="item.reason"
            class="rq-item-reason"
          >
            {{ item.reason }}
          </div>
          <router-link
            v-if="linkedSong(item)"
            :to="`/release/${linkedSong(item).id}`"
            class="rq-item-link"
          >
            → {{ linkedSong(item).artist }} – {{ linkedSong(item).title }}
          </router-link>
        </div>
        <span
          class="rq-chip"
          :class="'rq-chip-' + chipClass(item.status)"
        >
          {{ statusLabel(item.status) }}
        </span>
        <div class="rq-actions">
          <button
            v-if="item.status === 'pending'"
            type="button"
            class="rq-act"
            @click="cancelItem(item)"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>

    <div
      v-if="nextCursor"
      class="rq-more"
    >
      <button
        type="button"
        class="rq-more-btn"
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
  pending: {label: 'Pending', cls: 'neutral'},
  approved: {label: 'Approved', cls: 'acc'},
  downloading: {label: 'Downloading', cls: 'acc'},
  fulfilled: {label: 'Fulfilled', cls: 'ok'},
  duplicate: {label: 'In library', cls: 'warn'},
  rejected: {label: 'Rejected', cls: 'danger'},
  failed: {label: 'Failed', cls: 'danger'},
  cancelled: {label: 'Cancelled', cls: 'dim'},
};

const OPEN_STATUSES = ['pending', 'approved', 'downloading'];

export default {
  name: 'RequestsView',
  components: {
    SegmentedControl,
  },
  data() {
    return {
      kind: 'free_text',
      artist: '',
      title: '',
      mixName: '',
      sourceUrl: '',
      notes: '',
      submitting: false,
      submitError: '',
      matches: [],
      matchTimer: null,
      statusFilter: '',
      items: [],
      nextCursor: null,
      loading: true,
      loadingMore: false,
      pollTimer: null,
    };
  },
  computed: {
    kindOptions() {
      return [
        {value: 'free_text', label: 'Free text'},
        {value: 'url', label: 'Link'},
      ];
    },
    statusFilters() {
      return [
        {value: '', label: 'All'},
        {value: 'open', label: 'Open'},
        {value: 'fulfilled', label: 'Fulfilled'},
        {value: 'rejected', label: 'Declined'},
      ];
    },
    detected() {
      let host;
      try {
        host = new URL(this.sourceUrl.trim()).hostname.replace(/^www\./, '');
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
    canSubmit() {
      if (this.kind === 'free_text') {
        return this.artist.trim() && this.title.trim();
      }
      return !!this.detected;
    },
    hasActive() {
      return this.items.some(item => OPEN_STATUSES.indexOf(item.status) !== -1);
    },
  },
  watch: {
    statusFilter() {
      this.fetchList();
    },
    artist() {
      this.scheduleMatch();
    },
    title() {
      this.scheduleMatch();
    },
  },
  created() {
    this.fetchList();
    this.$store.dispatch('markRequestsSeen');
  },
  beforeUnmount() {
    this.stopPolling();
    clearTimeout(this.matchTimer);
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
    titleFor(item) {
      if (item.kind === 'free_text') {
        return item.mix_name ? `${item.artist} – ${item.title} (${item.mix_name})` : `${item.artist} – ${item.title}`;
      }
      return item.source_url;
    },
    subFor(item) {
      return item.kind === 'free_text' ? 'Free text' : (item.provider || 'link').toUpperCase();
    },
    linkedSong(item) {
      return item.fulfilled_song || item.duplicate_of || null;
    },
    detailOf(error, fallback) {
      const detail = error.response && error.response.data && error.response.data.detail;
      return (typeof detail === 'string' && detail) || fallback;
    },
    scheduleMatch() {
      clearTimeout(this.matchTimer);
      if (this.kind !== 'free_text' || !this.artist.trim() || !this.title.trim()) {
        this.matches = [];
        return;
      }
      this.matchTimer = setTimeout(this.runMatch, 250);
    },
    async runMatch() {
      try {
        const {data} = await axios.get('search', {
          params: {q: `${this.artist} ${this.title}`.trim(), limit: 5},
        });
        this.matches = data.items;
      } catch (error) {
        this.matches = [];
      }
    },
    async submit() {
      if (!this.canSubmit || this.submitting) {
        return;
      }
      this.submitting = true;
      this.submitError = '';
      const payload = this.kind === 'free_text'
        ? {
          kind: 'free_text',
          artist: this.artist.trim(),
          title: this.title.trim(),
          mix_name: this.mixName.trim() || undefined,
          notes: this.notes.trim() || undefined,
        }
        : {
          kind: 'url',
          source_url: this.sourceUrl.trim(),
          notes: this.notes.trim() || undefined,
        };
      try {
        const data = await this.$store.dispatch('submitRequest', payload);
        if (data.status === 'duplicate') {
          toast(`Already in the library — check ${this.titleFor(data)}`, 'warn');
        } else if (data.status === 'downloading') {
          toast('Request auto-approved — download started');
        } else {
          toast('Request submitted for review');
        }
        this.artist = '';
        this.title = '';
        this.mixName = '';
        this.sourceUrl = '';
        this.notes = '';
        this.matches = [];
        this.applyClientFilter();
        this.syncPolling();
      } catch (error) {
        this.submitError = this.detailOf(error, 'Could not submit that request.');
      } finally {
        this.submitting = false;
      }
    },
    params(extra) {
      const status = this.statusFilter === 'open' ? undefined : this.statusFilter || undefined;
      return {status, ...extra};
    },
    async fetchList() {
      this.loading = true;
      try {
        const items = await this.$store.dispatch('fetchMyRequests', {status: this.params().status});
        this.applyClientFilter();
        this.nextCursor = this.$store.getters.stateRequestsNextCursor;
        this.syncPolling();
        return items;
      } catch (error) {
        toast(this.detailOf(error, 'Could not load your requests.'), 'warn');
      } finally {
        this.loading = false;
      }
    },
    applyClientFilter() {
      const all = this.$store.getters.stateRequests;
      this.items = this.statusFilter === 'open'
        ? all.filter(item => OPEN_STATUSES.indexOf(item.status) !== -1)
        : all;
    },
    async loadMore() {
      if (!this.nextCursor) {
        return;
      }
      this.loadingMore = true;
      try {
        await this.$store.dispatch('loadMoreRequests', {status: this.params().status});
        this.applyClientFilter();
        this.nextCursor = this.$store.getters.stateRequestsNextCursor;
      } catch (error) {
        toast(this.detailOf(error, 'Could not load more requests.'), 'warn');
      } finally {
        this.loadingMore = false;
      }
    },
    async cancelItem(item) {
      try {
        await this.$store.dispatch('cancelRequest', item.id);
        this.applyClientFilter();
        toast('Request cancelled');
      } catch (error) {
        toast(this.detailOf(error, 'Could not cancel that request.'), 'warn');
      }
    },
    async poll() {
      if (!this.hasActive) {
        this.stopPolling();
        return;
      }
      await this.fetchList();
      this.$store.dispatch('fetchRequestsSummary');
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
      this.pollTimer = setInterval(this.poll, 5000);
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
.rq-form {
  border: 1px solid var(--line);
  border-radius: 13px;
  background: var(--panel);
  padding: 16px;
  max-width: 640px;
  margin-bottom: 20px;
}

.rq-kind {
  margin-bottom: 12px;
}

.rq-row {
  display: flex;
  gap: 10px;
  margin-bottom: 10px;
}

.rq-input {
  flex: 1;
  height: 40px;
  padding: 0 12px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line-strong);
  background: var(--raised);
  color: var(--txt);
  font: 400 13px var(--font-ui);
  box-sizing: border-box;
  min-width: 0;
}

.rq-input::placeholder {
  color: var(--dim-2);
}

.rq-input:focus {
  outline: none;
  border-color: var(--acc-border);
}

.rq-url-wrap {
  position: relative;
  flex: 1;
}

.rq-input-badged {
  padding-left: 46px;
}

.rq-badge-inline {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
}

.rq-badge {
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

.rq-hint {
  font: 400 12px var(--font-ui);
  color: var(--danger);
  margin: -4px 0 10px;
}

.rq-matches {
  margin-bottom: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(255, 182, 46, .07);
  border: 1px solid rgba(255, 182, 46, .18);
}

.rq-matches-label {
  font: 600 10px var(--font-mono);
  letter-spacing: .06em;
  text-transform: uppercase;
  color: var(--warn);
  margin-bottom: 6px;
}

.rq-match {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 4px 0;
  text-decoration: none;
  font: 400 12.5px var(--font-ui);
}

.rq-match-title {
  color: var(--txt);
}

.rq-match-sub {
  color: var(--muted);
}

.rq-match:hover .rq-match-title {
  color: var(--acc);
}

.rq-error {
  font: 400 12.5px var(--font-ui);
  color: var(--danger);
  margin: 0 0 10px;
}

.rq-submit {
  height: 40px;
  padding: 0 18px;
  border-radius: var(--r-ctl);
  border: none;
  background: var(--acc);
  color: var(--acc-ink);
  font: 600 13px var(--font-ui);
  cursor: pointer;
  transition: filter .15s ease;
}

.rq-submit:hover:enabled {
  filter: brightness(1.1);
}

.rq-submit:disabled {
  opacity: .5;
  cursor: default;
}

.rq-filters {
  margin-bottom: 14px;
}

.rq-none {
  padding: 60px;
  text-align: center;
  color: var(--dim-2);
  font: 400 14px var(--font-ui);
}

.rq-list {
  border: 1px solid var(--line);
  border-radius: 13px;
  overflow: hidden;
  background: var(--panel);
}

.rq-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 110px 90px;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, .045);
}

.rq-item:last-child {
  border-bottom: none;
}

.rq-item:hover {
  background: rgba(255, 255, 255, .03);
}

.rq-meta {
  min-width: 0;
}

.rq-item-title {
  font: 600 13px var(--font-ui);
  color: var(--txt);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rq-item-sub {
  font: 400 12px var(--font-ui);
  color: var(--muted);
  margin-top: 2px;
}

.rq-item-reason {
  font: 400 11.5px var(--font-ui);
  color: var(--dim-2);
  margin-top: 3px;
}

.rq-item-link {
  display: inline-block;
  margin-top: 4px;
  font: 500 12px var(--font-ui);
  color: var(--acc);
  text-decoration: none;
}

.rq-item-link:hover {
  text-decoration: underline;
}

.rq-chip {
  justify-self: start;
  padding: 4px 10px;
  border-radius: var(--r-pill);
  font: 600 11px var(--font-ui);
  white-space: nowrap;
}

.rq-chip-neutral {
  background: rgba(255, 255, 255, .06);
  color: var(--txt-2);
}

.rq-chip-acc {
  background: var(--acc-soft-strong);
  color: var(--acc);
}

.rq-chip-ok {
  background: rgba(53, 208, 122, .13);
  color: var(--ok);
}

.rq-chip-warn {
  background: rgba(255, 182, 46, .13);
  color: var(--warn);
}

.rq-chip-danger {
  background: rgba(255, 82, 102, .13);
  color: var(--danger);
}

.rq-chip-dim {
  background: rgba(255, 255, 255, .04);
  color: var(--dim);
}

.rq-actions {
  display: flex;
  justify-content: flex-end;
}

.rq-act {
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

.rq-act:hover {
  border-color: var(--acc-border);
  color: var(--txt);
}

.rq-more {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}

.rq-more-btn {
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

.rq-more-btn:hover:enabled {
  border-color: var(--acc-border);
  color: var(--txt);
}

.rq-more-btn:disabled {
  opacity: .5;
  cursor: default;
}
</style>
