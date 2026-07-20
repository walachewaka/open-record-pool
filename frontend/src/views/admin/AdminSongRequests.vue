<template>
  <section>
    <div class="aq-toolbar">
      <SegmentedControl
        v-model="statusFilter"
        :options="statusFilters"
      />
      <input
        v-model="q"
        type="text"
        class="aq-search"
        placeholder="Search artist, title, URL or requester…"
      >
    </div>

    <p
      v-if="errorMessage"
      class="aq-error"
    >
      {{ errorMessage }}
    </p>

    <div
      v-if="!loading && !items.length"
      class="aq-none"
    >
      No requests match those filters.
    </div>
    <div
      v-else
      class="aq-list"
    >
      <div
        v-for="item in items"
        :key="item.id"
        class="aq-card"
      >
        <input
          v-if="item.status === 'pending' || item.status === 'failed'"
          type="checkbox"
          class="aq-check"
          :checked="selected.has(item.id)"
          @change="toggleSelect(item.id)"
        >
        <div
          v-else
          class="aq-check-spacer"
        />

        <div class="aq-meta">
          <div class="aq-title-row">
            <span class="aq-title">{{ titleFor(item) }}</span>
            <span class="aq-kind">{{ item.kind === 'free_text' ? 'FREE TEXT' : (item.provider || 'link').toUpperCase() }}</span>
          </div>
          <div class="aq-sub">
            by {{ item.requester_username || '—' }} · {{ relativeTime(item.created_at) }}
          </div>
          <div
            v-if="item.notes"
            class="aq-notes"
          >
            {{ item.notes }}
          </div>
          <router-link
            v-if="item.possible_duplicate_of"
            :to="`/release/${item.possible_duplicate_of.id}`"
            class="aq-dup-warn"
          >
            Possible duplicate of {{ item.possible_duplicate_of.artist }} – {{ item.possible_duplicate_of.title }}
          </router-link>
          <div
            v-if="item.reason"
            class="aq-reason"
          >
            {{ item.reason }}
          </div>

          <div
            v-if="pendingUrlFor[item.id] !== undefined"
            class="aq-url-row"
          >
            <input
              v-model="pendingUrlFor[item.id]"
              type="text"
              class="aq-url-input"
              placeholder="Source URL to fetch this from…"
            >
          </div>
        </div>

        <span
          class="aq-chip"
          :class="'aq-chip-' + chipClass(item.status)"
        >
          {{ statusLabel(item.status) }}
        </span>

        <div class="aq-actions">
          <template v-if="item.status === 'pending'">
            <button
              v-if="pendingUrlFor[item.id] === undefined"
              type="button"
              class="aq-act"
              @click="startUrl(item)"
            >
              {{ item.kind === 'free_text' ? 'Add URL' : 'Approve' }}
            </button>
            <button
              v-if="pendingUrlFor[item.id] !== undefined"
              type="button"
              class="aq-act aq-act-primary"
              @click="approveItem(item)"
            >
              Approve
            </button>
            <button
              type="button"
              class="aq-act"
              @click="rejectItem(item)"
            >
              Reject
            </button>
          </template>
          <template v-else-if="item.status === 'failed'">
            <button
              type="button"
              class="aq-act"
              @click="retryItem(item)"
            >
              Retry
            </button>
            <button
              type="button"
              class="aq-act"
              @click="rejectItem(item)"
            >
              Reject
            </button>
          </template>
        </div>
      </div>
    </div>

    <div
      v-if="nextCursor"
      class="aq-more"
    >
      <button
        type="button"
        class="aq-more-btn"
        :disabled="loadingMore"
        @click="loadMore"
      >
        {{ loadingMore ? 'Loading…' : 'Load more' }}
      </button>
    </div>

    <div
      v-if="selected.size"
      class="aq-bulk"
    >
      <span class="aq-bulk-count">{{ selected.size }} selected</span>
      <button
        type="button"
        class="aq-act aq-act-primary"
        @click="bulkApprove"
      >
        Approve {{ selected.size }}
      </button>
      <button
        type="button"
        class="aq-act"
        @click="bulkReject"
      >
        Reject {{ selected.size }}
      </button>
    </div>
  </section>
</template>

<script>
import axios from 'axios';

import SegmentedControl from '@/components/admin/SegmentedControl.vue';
import { relativeTime } from '@/utils/format';
import { toast } from '@/utils/toast';

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

export default {
  name: 'AdminSongRequests',
  components: {
    SegmentedControl,
  },
  data() {
    return {
      items: [],
      statusFilter: 'pending',
      q: '',
      nextCursor: null,
      loading: true,
      loadingMore: false,
      limit: 50,
      errorMessage: '',
      selected: new Set(),
      pendingUrlFor: {},
      searchTimer: null,
      pollTimer: null,
    };
  },
  computed: {
    statusFilters() {
      return [
        {value: 'pending', label: 'Pending'},
        {value: 'downloading', label: 'In flight'},
        {value: 'fulfilled', label: 'Fulfilled'},
        {value: 'rejected', label: 'Declined'},
        {value: 'all', label: 'All'},
      ];
    },
  },
  watch: {
    statusFilter() {
      this.selected = new Set();
      this.fetchList();
    },
    q() {
      clearTimeout(this.searchTimer);
      this.searchTimer = setTimeout(() => this.fetchList(), 300);
    },
  },
  created() {
    this.fetchList();
    this.pollTimer = setInterval(() => {
      this.$store.dispatch('fetchRequestsPendingCount');
    }, 60000);
  },
  beforeUnmount() {
    clearTimeout(this.searchTimer);
    clearInterval(this.pollTimer);
  },
  methods: {
    relativeTime,
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
    detailOf(error, fallback) {
      const detail = error.response && error.response.data && error.response.data.detail;
      return (typeof detail === 'string' && detail) || fallback;
    },
    toggleSelect(id) {
      const next = new Set(this.selected);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      this.selected = next;
    },
    startUrl(item) {
      this.pendingUrlFor = {...this.pendingUrlFor, [item.id]: item.source_url || ''};
    },
    params(extra) {
      return {
        status: this.statusFilter,
        q: this.q.trim() || undefined,
        limit: this.limit,
        ...extra,
      };
    },
    async fetchList() {
      this.loading = true;
      this.errorMessage = '';
      try {
        const {data} = await axios.get('admin/requests', {params: this.params()});
        this.items = data.items;
        this.nextCursor = data.next_cursor;
      } catch (error) {
        this.errorMessage = this.detailOf(error, 'Could not load the requests.');
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
        const {data} = await axios.get('admin/requests', {
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
    refreshBadge() {
      this.$store.dispatch('fetchRequestsPendingCount');
    },
    async approveItem(item) {
      const url = this.pendingUrlFor[item.id];
      try {
        const {data} = await axios.post(`admin/requests/${item.id}/approve`, {
          source_url: url || undefined,
        });
        this.replace(data);
        const rest = {...this.pendingUrlFor};
        delete rest[item.id];
        this.pendingUrlFor = rest;
        toast(data.status === 'downloading' ? 'Approved — download queued' : 'Approved');
        this.refreshBadge();
      } catch (error) {
        toast(this.detailOf(error, 'Could not approve that request.'), 'warn');
      }
    },
    async rejectItem(item) {
      try {
        const {data} = await axios.post(`admin/requests/${item.id}/reject`, {});
        this.replace(data);
        toast('Rejected');
        this.refreshBadge();
      } catch (error) {
        toast(this.detailOf(error, 'Could not reject that request.'), 'warn');
      }
    },
    async retryItem(item) {
      try {
        const {data} = await axios.post(`admin/requests/${item.id}/retry`);
        this.replace(data);
        toast(data.status === 'downloading' ? 'Retry queued' : 'Retried');
      } catch (error) {
        toast(this.detailOf(error, 'Could not retry that request.'), 'warn');
      }
    },
    async bulkApprove() {
      await this.runBulk('approve');
    },
    async bulkReject() {
      await this.runBulk('reject');
    },
    async runBulk(action) {
      const ids = Array.from(this.selected);
      try {
        const {data} = await axios.post('admin/requests/bulk', {ids, action});
        toast(`${action === 'approve' ? 'Approved' : 'Rejected'} ${data.updated}${data.skipped.length ? `, skipped ${data.skipped.length}` : ''}`);
        this.selected = new Set();
        this.refreshBadge();
        this.fetchList();
      } catch (error) {
        toast(this.detailOf(error, 'Bulk action failed.'), 'warn');
      }
    },
  },
};
</script>

<style scoped>
.aq-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.aq-search {
  height: 38px;
  padding: 0 12px;
  border-radius: var(--r-ctl);
  border: 1px solid rgba(255, 255, 255, .12);
  background: var(--menu);
  color: var(--txt);
  font: 400 13px var(--font-ui);
  min-width: 260px;
}

.aq-error {
  color: var(--danger);
  font: 400 13px var(--font-ui);
}

.aq-none {
  font: 400 13px var(--font-ui);
  color: var(--dim-2);
  padding: 22px 4px;
}

.aq-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-bottom: 70px;
}

.aq-card {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr) 110px 170px;
  align-items: start;
  gap: 12px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--panel);
}

.aq-check,
.aq-check-spacer {
  width: 16px;
  height: 16px;
  margin-top: 3px;
}

.aq-meta {
  min-width: 0;
}

.aq-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.aq-title {
  font: 600 13px var(--font-ui);
  color: var(--txt);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.aq-kind {
  flex: none;
  padding: 2px 7px;
  border-radius: 6px;
  background: rgba(255, 255, 255, .05);
  border: 1px solid rgba(255, 255, 255, .08);
  font: 600 10px var(--font-mono);
  color: var(--txt-3);
}

.aq-sub {
  font: 400 12px var(--font-ui);
  color: var(--muted);
  margin-top: 2px;
}

.aq-notes {
  font: 400 12px var(--font-ui);
  color: var(--txt-3);
  margin-top: 4px;
}

.aq-dup-warn {
  display: block;
  margin-top: 6px;
  padding: 6px 10px;
  border-radius: 8px;
  background: rgba(255, 182, 46, .1);
  border: 1px solid rgba(255, 182, 46, .2);
  font: 500 11.5px var(--font-ui);
  color: var(--warn);
  text-decoration: none;
}

.aq-reason {
  font: 400 11.5px var(--font-ui);
  color: var(--dim-2);
  margin-top: 4px;
}

.aq-url-row {
  margin-top: 8px;
}

.aq-url-input {
  width: 100%;
  height: 34px;
  padding: 0 10px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line-strong);
  background: var(--raised);
  color: var(--txt);
  font: 400 12px var(--font-mono);
  box-sizing: border-box;
}

.aq-chip {
  justify-self: start;
  padding: 4px 10px;
  border-radius: var(--r-pill);
  font: 600 11px var(--font-ui);
  white-space: nowrap;
}

.aq-chip-neutral {
  background: rgba(255, 255, 255, .06);
  color: var(--txt-2);
}

.aq-chip-acc {
  background: var(--acc-soft-strong);
  color: var(--acc);
}

.aq-chip-ok {
  background: rgba(53, 208, 122, .13);
  color: var(--ok);
}

.aq-chip-warn {
  background: rgba(255, 182, 46, .13);
  color: var(--warn);
}

.aq-chip-danger {
  background: rgba(255, 82, 102, .13);
  color: var(--danger);
}

.aq-chip-dim {
  background: rgba(255, 255, 255, .04);
  color: var(--dim);
}

.aq-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}

.aq-act {
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

.aq-act:hover {
  border-color: var(--acc-border);
  color: var(--txt);
}

.aq-act-primary {
  background: var(--acc);
  border-color: var(--acc);
  color: var(--acc-ink);
}

.aq-act-primary:hover {
  filter: brightness(1.1);
  color: var(--acc-ink);
}

.aq-more {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}

.aq-more-btn {
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

.aq-more-btn:hover:enabled {
  border-color: var(--acc-border);
  color: var(--txt);
}

.aq-more-btn:disabled {
  opacity: .5;
  cursor: default;
}

.aq-bulk {
  position: fixed;
  left: 50%;
  bottom: 20px;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-radius: 12px;
  background: var(--panel);
  border: 1px solid var(--line);
  box-shadow: 0 10px 30px rgba(0, 0, 0, .35);
  z-index: 20;
}

.aq-bulk-count {
  font: 600 12px var(--font-ui);
  color: var(--txt-2);
  margin-right: 4px;
}
</style>
