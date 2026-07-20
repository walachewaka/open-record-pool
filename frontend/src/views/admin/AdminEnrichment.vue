<template>
  <section>
    <div
      v-if="status"
      class="en-status-card"
    >
      <div class="en-status-head">
        <span
          class="en-mode-badge"
          :class="`en-mode-${status.mode}`"
        >{{ modeLabel }}</span>
        <span class="en-status-title">Beatport enrichment</span>
        <button
          type="button"
          class="en-primary-btn en-backfill-btn"
          :disabled="!status.enabled || backfillBusy"
          :title="!status.enabled ? disabledReasonText : ''"
          @click="runBackfill"
        >
          {{ backfillBusy ? 'Running…' : 'Enrich library' }}
        </button>
      </div>
      <p
        v-if="!status.enabled"
        class="en-disabled-note"
      >
        {{ disabledReasonText }} — see CLAUDE.md for the Beatport partner-application
        and mock-mode setup steps.
      </p>
      <div class="en-stat-row">
        <div
          v-for="stat in statChips"
          :key="stat.key"
          class="en-stat-chip"
        >
          <span class="en-stat-value">{{ stat.value }}</span>
          <span class="en-stat-label">{{ stat.label }}</span>
        </div>
      </div>
      <p class="en-status-footer">
        Auto-enrich on import: <strong>{{ status.auto_enrich_on_import ? 'On' : 'Off' }}</strong>
        (Admin → Settings → Integrations) · rate limit {{ status.rate_limit_rps }} req/s ·
        {{ status.cache_entries }} cached responses
      </p>
    </div>

    <div class="en-toolbar">
      <SegmentedControl
        v-model="statusFilter"
        :options="statusFilters"
      />
    </div>

    <p
      v-if="errorMessage"
      class="en-error"
    >
      {{ errorMessage }}
    </p>

    <div
      v-if="!loading && !items.length"
      class="en-none"
    >
      No {{ statusFilter.replace('_', ' ') }} enrichment rows.
    </div>
    <div
      v-else
      class="en-panel"
    >
      <div class="en-head">
        <span>Track</span>
        <span class="en-h-c">Confidence</span>
        <span>Best candidate</span>
        <span class="en-h-r">Matched</span>
      </div>
      <div
        v-for="row in items"
        :key="row.id"
        class="en-row"
        @click="openDrawer(row)"
      >
        <div class="en-track">
          <span class="en-track-title">{{ row.song && row.song.title || 'Untitled' }}</span>
          <span class="en-track-artist">{{ row.song && row.song.artist || 'Unknown artist' }}</span>
        </div>
        <div
          class="en-conf"
          :class="confClass(row.confidence)"
        >
          {{ row.confidence != null ? Math.round(row.confidence * 100) + '%' : '—' }}
        </div>
        <div class="en-candidate">
          <template v-if="bestCandidate(row)">
            {{ bestCandidate(row).name }} · {{ bestCandidate(row).mix_name }}
            <span class="en-dim">{{ bestCandidate(row).label || 'no label' }}</span>
          </template>
          <span
            v-else
            class="en-dim"
          >none</span>
        </div>
        <div class="en-when">
          {{ row.matched_at ? relativeTime(row.matched_at) : '—' }}
        </div>
      </div>
    </div>

    <div
      v-if="nextCursor"
      class="en-more"
    >
      <button
        type="button"
        class="en-ghost-btn"
        @click="fetchPage(true)"
      >
        Load more
      </button>
    </div>

    <!-- Detail drawer -->
    <template v-if="drawer">
      <div
        class="en-backdrop"
        @click="drawer = null"
      />
      <div class="en-drawer">
        <div class="en-drawer-head">
          <div class="en-drawer-title">
            {{ drawer.song && drawer.song.title || 'Untitled' }}
            <span class="en-chip">{{ drawer.status.replace('_', ' ') }}</span>
          </div>
          <button
            type="button"
            class="en-x"
            @click="drawer = null"
          >
            ×
          </button>
        </div>
        <div class="en-drawer-body">
          <div class="en-search-row">
            <input
              v-model="manualQuery"
              type="text"
              class="en-input"
              placeholder="artist title"
            >
            <button
              type="button"
              class="en-ghost-btn"
              :disabled="searchBusy"
              @click="manualSearch"
            >
              {{ searchBusy ? 'Searching…' : 'Manual search' }}
            </button>
          </div>

          <div
            v-if="!(drawer.candidates || []).length"
            class="en-none"
          >
            No candidates yet.
          </div>
          <div
            v-for="candidate in drawer.candidates || []"
            :key="candidate.beatport_track_id"
            class="en-card"
            :class="{'en-card-active': candidate.beatport_track_id === selectedCandidateId}"
            @click="selectedCandidateId = candidate.beatport_track_id"
          >
            <img
              v-if="candidate.artwork_url"
              class="en-art"
              :src="candidate.artwork_url"
              referrerpolicy="no-referrer"
              loading="lazy"
              alt=""
              @error="$event.target.style.visibility = 'hidden'"
            >
            <div class="en-card-body">
              <div class="en-card-title">
                {{ candidate.name }} <span class="en-dim">({{ candidate.mix_name }})</span>
              </div>
              <div class="en-card-sub">
                {{ (candidate.artists || []).join(', ') || 'Unknown artist' }} ·
                {{ candidate.label || 'no label' }}
              </div>
              <div class="en-card-facts">
                <span>score {{ Math.round(candidate.score * 100) }}%</span>
                <span v-if="candidate.bpm">{{ candidate.bpm }} bpm</span>
                <span v-if="candidate.key">{{ candidate.key }}</span>
                <span v-if="candidate.duration_delta != null">Δ {{ candidate.duration_delta.toFixed(0) }}s</span>
              </div>
            </div>
          </div>

          <div
            v-if="(drawer.candidates || []).length"
            class="en-fields"
          >
            <div class="en-fields-title">
              Fields to apply
            </div>
            <label
              v-for="field in APPLIED_FIELDS"
              :key="field"
              class="en-field-row"
            >
              <input
                v-model="checkedFields"
                type="checkbox"
                :value="field"
                :disabled="isLocked(field)"
              >
              {{ field }}
              <span
                v-if="isLocked(field)"
                class="en-lock"
              >locked: manual edit</span>
            </label>
          </div>
        </div>
        <div class="en-drawer-foot">
          <button
            type="button"
            class="en-primary-btn en-flex"
            :disabled="!(drawer.candidates || []).length"
            @click="accept"
          >
            Accept
          </button>
          <button
            type="button"
            class="en-ghost-btn en-flex"
            @click="reject"
          >
            Reject
          </button>
          <button
            v-if="drawer.status === 'applied'"
            type="button"
            class="en-ghost-btn en-flex"
            @click="unapply"
          >
            Un-apply
          </button>
        </div>
      </div>
    </template>
  </section>
</template>

<script>
import axios from 'axios';

import SegmentedControl from '@/components/admin/SegmentedControl.vue';
import { pollJob } from '@/utils/jobs';
import { toast } from '@/utils/toast';
import { relativeTime } from '@/utils/format';

const APPLIED_FIELDS = ['genre', 'label', 'year'];

export default {
  name: 'AdminEnrichment',
  components: {
    SegmentedControl,
  },
  data() {
    return {
      APPLIED_FIELDS,
      status: null,
      items: [],
      nextCursor: null,
      statusFilter: 'needs_review',
      loading: true,
      errorMessage: '',
      drawer: null,
      selectedCandidateId: null,
      checkedFields: [...APPLIED_FIELDS],
      manualQuery: '',
      backfillBusy: false,
      searchBusy: false,
    };
  },
  computed: {
    modeLabel() {
      const labels = {mock: 'Mock', live: 'Live', disabled: 'Disabled'};
      return this.status ? (labels[this.status.mode] || this.status.mode) : '';
    },
    disabledReasonText() {
      const reasons = {
        credentials_not_configured: 'Credentials not configured (set BEATPORT_CLIENT_ID / BEATPORT_CLIENT_SECRET, or BEATPORT_MOCK=true)',
        disabled_by_env: 'Disabled by BEATPORT_ENABLED=false',
      };
      return (this.status && reasons[this.status.reason]) || 'Beatport integration is not enabled';
    },
    statChips() {
      if (!this.status) {
        return [];
      }
      const counts = this.status.counts || {};
      return Object.keys(counts).map(key => ({
        key,
        label: key.replace('_', ' '),
        value: counts[key],
      }));
    },
    statusFilters() {
      return [
        {value: 'needs_review', label: 'Needs review'},
        {value: 'no_match', label: 'No match'},
        {value: 'applied', label: 'Applied'},
        {value: 'rejected', label: 'Rejected'},
        {value: 'error', label: 'Errors'},
      ];
    },
  },
  watch: {
    statusFilter() {
      this.fetchPage();
    },
  },
  created() {
    this.fetchStatus();
    return this.fetchPage();
  },
  methods: {
    relativeTime,
    detailOf(error, fallback) {
      const detail = error.response && error.response.data && error.response.data.detail;
      return (typeof detail === 'string' && detail) || fallback;
    },
    confClass(confidence) {
      if (confidence == null) {
        return '';
      }
      if (confidence >= 0.85) {
        return 'en-conf-high';
      }
      if (confidence >= 0.6) {
        return 'en-conf-mid';
      }
      return 'en-conf-low';
    },
    bestCandidate(row) {
      return (row.candidates || [])[0] || null;
    },
    isLocked(field) {
      const locks = (this.drawer && this.drawer.song && this.drawer.song.field_locks) || {};
      return locks[field] === 'manual';
    },
    async fetchStatus() {
      try {
        const {data} = await axios.get('admin/enrichment/status');
        this.status = data;
      } catch (error) {
        this.errorMessage = this.detailOf(error, 'Could not load the provider status.');
      }
    },
    async fetchPage(more = false) {
      this.loading = true;
      this.errorMessage = '';
      try {
        const {data} = await axios.get('admin/enrichment/queue', {
          params: {
            status: this.statusFilter,
            cursor: more ? this.nextCursor : undefined,
            limit: 50,
          },
        });
        this.items = more ? this.items.concat(data.items) : data.items;
        this.nextCursor = data.next_cursor;
      } catch (error) {
        this.errorMessage = this.detailOf(error, 'Could not load the review queue.');
      } finally {
        this.loading = false;
      }
    },
    openDrawer(row) {
      this.drawer = row;
      const best = this.bestCandidate(row);
      this.selectedCandidateId = best ? best.beatport_track_id : null;
      this.checkedFields = APPLIED_FIELDS.filter(field => !this.isLocked(field));
      this.manualQuery = [row.song && row.song.artist, row.song && row.song.title].filter(Boolean).join(' ');
    },
    async refreshDrawer() {
      try {
        const {data} = await axios.get(`admin/enrichment/songs/${this.drawer.song_id}`);
        this.drawer = data;
      } catch (error) {
        // Row may have moved out of the current filter; close quietly.
        this.drawer = null;
      }
      this.fetchPage();
      this.fetchStatus();
    },
    async accept() {
      try {
        await axios.post(`admin/enrichment/${this.drawer.id}/accept`, {
          beatport_track_id: this.selectedCandidateId,
          fields: this.checkedFields,
        });
        toast('Enrichment applied.');
        await this.refreshDrawer();
      } catch (error) {
        toast(this.detailOf(error, 'Could not apply the candidate.'), 'warn');
      }
    },
    async reject() {
      try {
        await axios.post(`admin/enrichment/${this.drawer.id}/reject`);
        toast('Marked as not a match.');
        await this.refreshDrawer();
      } catch (error) {
        toast(this.detailOf(error, 'Could not reject the row.'), 'warn');
      }
    },
    async unapply() {
      try {
        await axios.post(`admin/enrichment/${this.drawer.id}/unapply`);
        toast('Reverted to the pre-apply values.');
        await this.refreshDrawer();
      } catch (error) {
        toast(this.detailOf(error, 'Could not un-apply.'), 'warn');
      }
    },
    async manualSearch() {
      if (!this.manualQuery || this.manualQuery.length < 2) {
        toast('Enter at least 2 characters to search.', 'warn');
        return;
      }
      this.searchBusy = true;
      try {
        let {data} = await axios.post(`admin/enrichment/${this.drawer.id}/manual-search`, {
          query: this.manualQuery,
        });
        if (data.status !== 'succeeded') {
          data = await pollJob(data.id);
        }
        toast('Search complete.');
        await this.refreshDrawer();
      } catch (error) {
        toast(this.detailOf(error, 'Manual search failed.'), 'warn');
      } finally {
        this.searchBusy = false;
      }
    },
    async runBackfill() {
      this.backfillBusy = true;
      try {
        let {data} = await axios.post('admin/enrichment/backfill', {});
        if (data.status !== 'succeeded') {
          data = await pollJob(data.id, {timeoutMs: 600000});
        }
        const result = data.result || {};
        toast(
          `Backfill done: ${result.processed || 0} processed, ${result.applied || 0} applied, ` +
          `${result.needs_review || 0} for review`
        );
        this.fetchPage();
        this.fetchStatus();
      } catch (error) {
        toast(this.detailOf(error, 'The backfill failed.'), 'warn');
      } finally {
        this.backfillBusy = false;
      }
    },
  },
};
</script>

<style scoped>
.en-status-card {
  border: 1px solid var(--line);
  border-radius: 13px;
  background: var(--panel);
  padding: 16px 18px;
  margin-bottom: 16px;
}

.en-status-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.en-status-title {
  font: 600 14px var(--font-disp);
}

.en-mode-badge {
  padding: 3px 10px;
  border-radius: var(--r-pill);
  font: 700 10.5px var(--font-mono);
  text-transform: uppercase;
  letter-spacing: .05em;
}

.en-mode-live {
  background: var(--acc-soft);
  color: var(--acc);
  border: 1px solid var(--acc-border);
}

.en-mode-mock {
  background: rgba(139, 92, 246, .15);
  color: #a78bfa;
  border: 1px solid rgba(139, 92, 246, .35);
}

.en-mode-disabled {
  background: rgba(255, 255, 255, .06);
  color: var(--dim-2);
  border: 1px solid var(--line-strong);
}

.en-backfill-btn {
  margin-left: auto;
}

.en-disabled-note {
  margin: 10px 0 0;
  font: 400 12.5px var(--font-ui);
  color: var(--dim-2);
}

.en-stat-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
}

.en-stat-chip {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 14px;
  border-radius: 10px;
  background: rgba(255, 255, 255, .03);
  border: 1px solid rgba(255, 255, 255, .07);
  min-width: 74px;
}

.en-stat-value {
  font: 700 15px var(--font-mono);
}

.en-stat-label {
  font: 400 10.5px var(--font-ui);
  color: var(--dim);
  text-transform: capitalize;
}

.en-status-footer {
  margin: 12px 0 0;
  font: 400 11.5px var(--font-ui);
  color: var(--dim);
}

.en-toolbar {
  display: flex;
  margin-bottom: 14px;
}

.en-error {
  color: var(--danger);
  font: 400 13px var(--font-ui);
}

.en-none {
  font: 400 13px var(--font-ui);
  color: var(--dim-2);
  padding: 22px 4px;
}

.en-ghost-btn {
  height: 38px;
  padding: 0 14px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line-strong);
  background: none;
  color: var(--txt-2);
  font: 600 13px var(--font-ui);
  cursor: pointer;
}

.en-ghost-btn:hover:enabled {
  color: var(--txt);
  border-color: var(--acc-border);
}

.en-primary-btn {
  height: 38px;
  padding: 0 15px;
  border-radius: var(--r-ctl);
  border: none;
  background: var(--acc);
  color: var(--acc-ink);
  font: 600 13px var(--font-ui);
  cursor: pointer;
}

.en-primary-btn:disabled,
.en-ghost-btn:disabled {
  opacity: .5;
  cursor: default;
}

.en-panel {
  border: 1px solid var(--line);
  border-radius: 13px;
  overflow: hidden;
  background: var(--panel);
}

.en-head,
.en-row {
  display: grid;
  grid-template-columns: minmax(200px, 2fr) 96px minmax(200px, 2fr) 100px;
  align-items: center;
  gap: 12px;
  padding: 0 16px;
}

.en-head {
  height: 38px;
  border-bottom: 1px solid rgba(255, 255, 255, .07);
  font: 600 10px var(--font-mono);
  letter-spacing: .08em;
  color: var(--dim-2);
  text-transform: uppercase;
}

.en-h-c {
  text-align: center;
}

.en-h-r {
  text-align: right;
}

.en-row {
  min-height: 56px;
  padding-top: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(255, 255, 255, .045);
  cursor: pointer;
}

.en-row:hover {
  background: rgba(255, 255, 255, .03);
}

.en-row:last-child {
  border-bottom: none;
}

.en-track {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.en-track-title {
  font: 600 12.5px var(--font-ui);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.en-track-artist {
  font: 400 11.5px var(--font-ui);
  color: var(--muted);
}

.en-conf {
  text-align: center;
  font: 700 12.5px var(--font-mono);
}

.en-conf-high {
  color: var(--acc);
}

.en-conf-mid {
  color: #d97706;
}

.en-conf-low {
  color: var(--danger);
}

.en-candidate {
  font: 400 12px var(--font-ui);
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.en-dim {
  color: var(--dim);
}

.en-when {
  text-align: right;
  font: 400 11.5px var(--font-ui);
  color: var(--dim);
  white-space: nowrap;
}

.en-more {
  display: flex;
  justify-content: center;
  padding: 14px 0;
}

.en-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(4, 7, 11, .55);
  z-index: 40;
}

.en-drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: 640px;
  max-width: 94vw;
  z-index: 41;
  background: var(--card);
  border-left: 1px solid rgba(255, 255, 255, .09);
  box-shadow: -24px 0 60px rgba(0, 0, 0, .5);
  display: flex;
  flex-direction: column;
}

.en-drawer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, .07);
}

.en-drawer-title {
  font: 600 13px var(--font-disp);
  display: flex;
  align-items: center;
  gap: 10px;
}

.en-chip {
  display: inline-block;
  padding: 3px 9px;
  border-radius: var(--r-pill);
  background: var(--acc-soft);
  border: 1px solid var(--acc-border);
  color: var(--acc);
  font: 600 10.5px var(--font-mono);
  text-transform: capitalize;
}

.en-x {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--muted);
  font-size: 20px;
  width: 30px;
  height: 30px;
}

.en-drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.en-search-row {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.en-input {
  flex: 1;
  height: 38px;
  padding: 0 12px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line-strong);
  background: var(--raised);
  color: var(--txt);
  font: 400 13px var(--font-ui);
}

.en-card {
  display: flex;
  gap: 12px;
  border: 1px solid var(--line-strong);
  border-radius: 12px;
  padding: 12px;
  background: var(--raised);
  margin-bottom: 10px;
  cursor: pointer;
}

.en-card-active {
  border-color: var(--acc-border);
}

.en-art {
  width: 56px;
  height: 56px;
  border-radius: 8px;
  object-fit: cover;
  flex: none;
  background: rgba(255, 255, 255, .05);
}

.en-card-body {
  min-width: 0;
}

.en-card-title {
  font: 600 13px var(--font-ui);
}

.en-card-sub {
  font: 400 12px var(--font-ui);
  color: var(--muted);
  margin: 3px 0 8px;
}

.en-card-facts {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  font: 600 11px var(--font-mono);
  color: var(--txt-2);
}

.en-fields {
  margin-top: 8px;
}

.en-fields-title {
  font: 600 11px var(--font-mono);
  text-transform: uppercase;
  letter-spacing: .06em;
  color: var(--dim-2);
  margin-bottom: 8px;
}

.en-field-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font: 400 13px var(--font-ui);
  padding: 6px 0;
  text-transform: capitalize;
}

.en-lock {
  font: 400 11px var(--font-ui);
  color: var(--dim);
  text-transform: none;
}

.en-drawer-foot {
  display: flex;
  gap: 10px;
  padding: 16px 20px;
  border-top: 1px solid rgba(255, 255, 255, .07);
}

.en-flex {
  flex: 1;
}
</style>
