<template>
  <section>
    <div class="dp-toolbar">
      <SegmentedControl
        v-model="statusFilter"
        :options="statusFilters"
      />
      <div
        v-if="perms.site_settings"
        class="dp-backfill"
      >
        <button
          type="button"
          class="dp-ghost-btn"
          :disabled="backfillBusy"
          @click="runBackfill(true)"
        >
          Dry-run backfill
        </button>
        <button
          type="button"
          class="dp-primary-btn"
          :disabled="backfillBusy"
          @click="runBackfill(false)"
        >
          {{ backfillBusy ? 'Running…' : 'Run backfill' }}
        </button>
      </div>
    </div>

    <p
      v-if="errorMessage"
      class="dp-error"
    >
      {{ errorMessage }}
    </p>

    <div
      v-if="checked.length && bulkAllowed"
      class="dp-bulk"
    >
      <span class="dp-bulk-count">{{ checked.length }} selected</span>
      <button
        type="button"
        class="dp-primary-btn"
        @click="bulkResolve('accept_suggested')"
      >
        Accept suggested ({{ checked.length }})
      </button>
      <button
        type="button"
        class="dp-ghost-btn"
        @click="bulkResolve('not_duplicate')"
      >
        Not duplicates ({{ checked.length }})
      </button>
    </div>

    <div
      v-if="!loading && !items.length"
      class="dp-none"
    >
      No {{ statusFilter.replace('_', '-') }} duplicate pairs.
    </div>
    <div
      v-else
      class="dp-panel"
    >
      <div class="dp-head">
        <span />
        <span>Pair</span>
        <span>Layer</span>
        <span class="dp-h-c">Confidence</span>
        <span>Quality</span>
        <span class="dp-h-r">Detected</span>
      </div>
      <div
        v-for="row in items"
        :key="row.id"
        class="dp-row"
        @click="openDrawer(row)"
      >
        <div @click.stop>
          <input
            v-if="bulkAllowed"
            v-model="checked"
            type="checkbox"
            class="dp-check"
            :value="row.id"
          >
        </div>
        <div class="dp-pair">
          <div
            v-for="side in ['song_a', 'song_b']"
            :key="side"
            class="dp-side"
          >
            <span
              v-if="row.suggested_winner_id === row[side].id"
              class="dp-keep"
            >keep</span>
            <span class="dp-side-title">{{ row[side].artist || 'Unknown' }} – {{ row[side].title || 'Untitled' }}</span>
          </div>
        </div>
        <div>
          <span class="dp-chip">{{ layerLabel(row.layer) }}</span>
        </div>
        <div class="dp-conf">
          {{ Math.round(row.confidence * 100) }}%
        </div>
        <div class="dp-quality">
          <div
            v-for="side in ['song_a', 'song_b']"
            :key="side"
            class="dp-quality-line"
          >
            {{ qualitySummary(row[side]) }}
            <span
              v-if="row[side].suspect_transcode"
              class="dp-suspect"
            >transcode?</span>
          </div>
        </div>
        <div class="dp-when">
          {{ relativeTime(row.created_at) }}
        </div>
      </div>
    </div>

    <div
      v-if="nextCursor"
      class="dp-more"
    >
      <button
        type="button"
        class="dp-ghost-btn"
        @click="fetchPage(true)"
      >
        Load more
      </button>
    </div>

    <!-- Compare drawer -->
    <template v-if="drawer">
      <div
        class="dp-backdrop"
        @click="drawer = null"
      />
      <div class="dp-drawer">
        <div class="dp-drawer-head">
          <div class="dp-drawer-title">
            Compare versions
            <span class="dp-chip">{{ layerLabel(drawer.layer) }}</span>
          </div>
          <button
            type="button"
            class="dp-x"
            @click="drawer = null"
          >
            <svg
              width="17"
              height="17"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
            >
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>
        <div class="dp-drawer-body">
          <div
            v-if="drawer.duration_delta != null"
            class="dp-delta"
          >
            Duration delta: {{ drawer.duration_delta.toFixed(1) }}s ·
            confidence {{ Math.round(drawer.confidence * 100) }}%
          </div>
          <div class="dp-cards">
            <div
              v-for="side in ['song_a', 'song_b']"
              :key="side"
              class="dp-card"
              :class="{'dp-card-win': drawer.suggested_winner_id === drawer[side].id}"
            >
              <div class="dp-card-head">
                <div class="dp-card-title">
                  {{ drawer[side].title || 'Untitled' }}
                </div>
                <span
                  v-if="drawer.suggested_winner_id === drawer[side].id"
                  class="dp-keep"
                >keep</span>
              </div>
              <div class="dp-card-sub">
                {{ drawer[side].artist || 'Unknown artist' }} · {{ drawer[side].mix_norm }}
              </div>
              <div class="dp-facts">
                <div
                  v-for="fact in qualityRows(drawer[side])"
                  :key="fact.label"
                  class="dp-fact"
                >
                  <span class="dp-fact-label">{{ fact.label }}</span>
                  <span
                    class="dp-fact-value"
                    :class="{'dp-fact-best': isBest(fact.key, side)}"
                  >{{ fact.value }}</span>
                </div>
              </div>
              <audio
                class="dp-audio"
                controls
                preload="none"
                :src="`${apiBase}/songs/${drawer[side].id}/stream`"
                @play="pauseOthers($event)"
              />
            </div>
          </div>
        </div>
        <div class="dp-drawer-foot">
          <template v-if="['pending', 'proposed'].includes(drawer.status)">
            <button
              type="button"
              class="dp-primary-btn dp-flex"
              @click="resolve(drawer, 'merge', drawer.song_a.id)"
            >
              Keep left
            </button>
            <button
              type="button"
              class="dp-primary-btn dp-flex"
              @click="resolve(drawer, 'merge', drawer.song_b.id)"
            >
              Keep right
            </button>
            <button
              type="button"
              class="dp-ghost-btn dp-flex"
              @click="resolve(drawer, 'not_duplicate')"
            >
              Not a duplicate
            </button>
          </template>
          <div
            v-else
            class="dp-resolved-note"
          >
            Resolved: {{ drawer.status.replace('_', ' ') }}
          </div>
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
import { fmtBytes, relativeTime } from '@/utils/format';

const LAYER_LABELS = {
  checksum: 'checksum',
  pcm_hash: 'pcm',
  fingerprint: 'fingerprint',
  metadata: 'metadata',
};

export default {
  name: 'AdminDuplicates',
  components: {
    SegmentedControl,
  },
  data() {
    return {
      items: [],
      nextCursor: null,
      statusFilter: 'pending',
      checked: [],
      loading: true,
      errorMessage: '',
      drawer: null,
      backfillBusy: false,
    };
  },
  computed: {
    apiBase() {
      return axios.defaults.baseURL ? axios.defaults.baseURL.replace(/\/$/, '') : '';
    },
    perms() {
      return this.$store.getters.userPermissions;
    },
    statusFilters() {
      return [
        {value: 'pending', label: 'Pending'},
        {value: 'proposed', label: 'Proposed'},
        {value: 'auto_resolved', label: 'Auto'},
        {value: 'confirmed', label: 'Confirmed'},
        {value: 'rejected', label: 'Rejected'},
      ];
    },
    bulkAllowed() {
      return ['pending', 'proposed'].includes(this.statusFilter);
    },
  },
  watch: {
    statusFilter() {
      this.checked = [];
      this.fetchPage();
    },
  },
  created() {
    return this.fetchPage();
  },
  methods: {
    relativeTime,
    layerLabel(layer) {
      return LAYER_LABELS[layer] || layer;
    },
    detailOf(error, fallback) {
      const detail = error.response && error.response.data && error.response.data.detail;
      return (typeof detail === 'string' && detail) || fallback;
    },
    qualitySummary(side) {
      const bits = [];
      bits.push(side.effective_bitrate_kbps ? `${side.effective_bitrate_kbps} kbps` : '— kbps');
      if (side.sample_rate_hz) {
        bits.push(`${(side.sample_rate_hz / 1000).toFixed(1)} kHz`);
      }
      bits.push(side.format_class === 2 ? 'Lossless' : 'MP3');
      return bits.join(' · ');
    },
    qualityRows(side) {
      return [
        {key: 'format_class', label: 'Format class', value: side.format_class === 2 ? 'Lossless' : 'Lossy'},
        {
          key: 'effective_bitrate_kbps',
          label: 'Effective / declared kbps',
          value: `${side.effective_bitrate_kbps || '—'} / ${side.bitrate_kbps || '—'}`,
        },
        {
          key: 'spectral_cutoff_hz',
          label: 'Spectral cutoff',
          value: side.spectral_cutoff_hz ? `${side.spectral_cutoff_hz} Hz` : 'unanalyzed',
        },
        {key: 'sample_rate_hz', label: 'Sample rate', value: `${side.sample_rate_hz || '—'} Hz`},
        {key: 'suspect', label: 'Transcode check', value: side.suspect_transcode ? 'SUSPECT' : 'clean'},
        {key: 'source', label: 'Source', value: side.source || '—'},
        {key: 'file_size_bytes', label: 'File size', value: fmtBytes(side.file_size_bytes)},
        {key: 'version_status', label: 'Version status', value: side.version_status},
      ];
    },
    isBest(key, side) {
      if (!this.drawer) {
        return false;
      }
      const mine = this.drawer[side];
      const other = this.drawer[side === 'song_a' ? 'song_b' : 'song_a'];
      const numeric = ['effective_bitrate_kbps', 'spectral_cutoff_hz', 'sample_rate_hz', 'file_size_bytes', 'format_class'];
      if (numeric.includes(key)) {
        return (mine[key] || 0) > (other[key] || 0);
      }
      if (key === 'suspect') {
        return !mine.suspect_transcode && other.suspect_transcode;
      }
      return false;
    },
    pauseOthers(event) {
      document.querySelectorAll('.dp-audio').forEach(el => {
        if (el !== event.target) {
          el.pause();
        }
      });
    },
    async fetchPage(more = false) {
      this.loading = true;
      this.errorMessage = '';
      try {
        const {data} = await axios.get('admin/duplicates', {
          params: {
            status: this.statusFilter,
            cursor: more ? this.nextCursor : undefined,
            limit: 50,
          },
        });
        this.items = more ? this.items.concat(data.items) : data.items;
        this.nextCursor = data.next_cursor;
      } catch (error) {
        this.errorMessage = this.detailOf(error, 'Could not load the duplicates queue.');
      } finally {
        this.loading = false;
      }
    },
    async openDrawer(row) {
      try {
        const {data} = await axios.get(`admin/duplicates/${row.id}`);
        this.drawer = data;
      } catch (error) {
        toast(this.detailOf(error, 'Could not load the pair.'), 'warn');
      }
    },
    async resolve(row, action, winnerSongId = null) {
      try {
        await axios.post(`admin/duplicates/${row.id}/resolve`, {
          action,
          winner_song_id: winnerSongId,
        });
        toast(action === 'merge' ? 'Duplicate resolved — one canonical version kept' : 'Marked as not a duplicate');
        this.drawer = null;
        this.items = this.items.filter(item => item.id !== row.id);
        this.checked = this.checked.filter(id => id !== row.id);
        this.$store.dispatch('fetchDuplicatesPendingCount');
      } catch (error) {
        toast(this.detailOf(error, 'Could not resolve the pair.'), 'warn');
      }
    },
    async bulkResolve(action) {
      try {
        const {data} = await axios.post('admin/duplicates/bulk-resolve', {
          ids: this.checked,
          action,
        });
        toast(`Resolved ${data.resolved} — skipped ${data.skipped.length}`);
        this.checked = [];
        this.fetchPage();
        this.$store.dispatch('fetchDuplicatesPendingCount');
      } catch (error) {
        toast(this.detailOf(error, 'Bulk resolve failed.'), 'warn');
      }
    },
    async runBackfill(dryRun) {
      this.backfillBusy = true;
      try {
        let {data} = await axios.post('admin/duplicates/backfill', {dry_run: dryRun});
        if (data.status !== 'succeeded') {
          data = await pollJob(data.id, {timeoutMs: 600000});
        }
        const result = data.result || {};
        toast(
          `${dryRun ? 'Dry-run' : 'Backfill'} done: ${result.songs_scanned || 0} scanned, ` +
          `${result.auto_resolved || 0} merged, ${result.proposed || 0} proposed, ` +
          `${result.borderline || 0} for review`
        );
        this.fetchPage();
        this.$store.dispatch('fetchDuplicatesPendingCount');
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
.dp-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.dp-backfill {
  margin-left: auto;
  display: flex;
  gap: 8px;
}

.dp-ghost-btn {
  height: 38px;
  padding: 0 14px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line-strong);
  background: none;
  color: var(--txt-2);
  font: 600 13px var(--font-ui);
  cursor: pointer;
  transition: color .15s ease, border-color .15s ease;
}

.dp-ghost-btn:hover:enabled {
  color: var(--txt);
  border-color: var(--acc-border);
}

.dp-primary-btn {
  height: 38px;
  padding: 0 15px;
  border-radius: var(--r-ctl);
  border: none;
  background: var(--acc);
  color: var(--acc-ink);
  font: 600 13px var(--font-ui);
  cursor: pointer;
  transition: filter .15s ease;
}

.dp-primary-btn:hover:enabled {
  filter: brightness(1.1);
}

.dp-primary-btn:disabled,
.dp-ghost-btn:disabled {
  opacity: .5;
  cursor: default;
}

.dp-error {
  color: var(--danger);
  font: 400 13px var(--font-ui);
}

.dp-none {
  font: 400 13px var(--font-ui);
  color: var(--dim-2);
  padding: 22px 4px;
}

.dp-bulk {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  margin-bottom: 12px;
  border: 1px solid var(--acc-border);
  border-radius: 11px;
  background: var(--acc-soft);
}

.dp-bulk-count {
  font: 600 12px var(--font-mono);
  color: var(--acc);
}

.dp-panel {
  border: 1px solid var(--line);
  border-radius: 13px;
  overflow: hidden;
  background: var(--panel);
}

.dp-head,
.dp-row {
  display: grid;
  grid-template-columns: 30px minmax(220px, 2fr) 96px 90px minmax(170px, 1fr) 90px;
  align-items: center;
  gap: 12px;
  padding: 0 16px;
}

.dp-head {
  height: 38px;
  border-bottom: 1px solid rgba(255, 255, 255, .07);
  font: 600 10px var(--font-mono);
  letter-spacing: .08em;
  color: var(--dim-2);
  text-transform: uppercase;
}

.dp-h-c {
  text-align: center;
}

.dp-h-r {
  text-align: right;
}

.dp-row {
  min-height: 60px;
  padding-top: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(255, 255, 255, .045);
  cursor: pointer;
  transition: background .15s ease;
}

.dp-row:hover {
  background: rgba(255, 255, 255, .03);
}

.dp-row:last-child {
  border-bottom: none;
}

.dp-check {
  width: 15px;
  height: 15px;
  accent-color: var(--acc);
  cursor: pointer;
}

.dp-pair {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.dp-side {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}

.dp-side-title {
  font: 500 12.5px var(--font-ui);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dp-keep {
  flex: none;
  padding: 1px 7px;
  border-radius: var(--r-pill);
  background: var(--acc);
  color: var(--acc-ink);
  font: 700 9.5px var(--font-mono);
  letter-spacing: .05em;
  text-transform: uppercase;
}

.dp-chip {
  display: inline-block;
  padding: 3px 9px;
  border-radius: var(--r-pill);
  background: var(--acc-soft);
  border: 1px solid var(--acc-border);
  color: var(--acc);
  font: 600 10.5px var(--font-mono);
}

.dp-conf {
  text-align: center;
  font: 600 12.5px var(--font-mono);
  color: var(--txt-2);
}

.dp-quality {
  display: flex;
  flex-direction: column;
  gap: 3px;
  font: 400 11.5px var(--font-mono);
  color: var(--muted);
  min-width: 0;
}

.dp-quality-line {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dp-suspect {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: var(--r-pill);
  background: rgba(255, 82, 102, .13);
  color: var(--danger);
  font: 700 9.5px var(--font-mono);
}

.dp-when {
  text-align: right;
  font: 400 11.5px var(--font-ui);
  color: var(--dim);
  white-space: nowrap;
}

.dp-more {
  display: flex;
  justify-content: center;
  padding: 14px 0;
}

/* Drawer */

.dp-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(4, 7, 11, .55);
  z-index: 40;
}

.dp-drawer {
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

.dp-drawer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, .07);
}

.dp-drawer-title {
  font: 600 13px var(--font-disp);
  display: flex;
  align-items: center;
  gap: 10px;
}

.dp-x {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--muted);
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  transition: background .15s ease, color .15s ease;
}

.dp-x:hover {
  background: rgba(255, 255, 255, .06);
  color: var(--txt);
}

.dp-drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.dp-delta {
  margin-bottom: 16px;
  padding: 10px 14px;
  border-radius: 10px;
  background: rgba(255, 255, 255, .03);
  border: 1px solid rgba(255, 255, 255, .07);
  font: 500 12px var(--font-mono);
  color: var(--txt-2);
}

.dp-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.dp-card {
  border: 1px solid var(--line-strong);
  border-radius: 12px;
  padding: 14px;
  background: var(--raised);
}

.dp-card-win {
  border-color: var(--acc-border);
}

.dp-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.dp-card-title {
  font: 600 13px var(--font-ui);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dp-card-sub {
  font: 400 12px var(--font-ui);
  color: var(--muted);
  margin: 3px 0 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dp-facts {
  display: flex;
  flex-direction: column;
  gap: 7px;
  margin-bottom: 12px;
}

.dp-fact {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

.dp-fact-label {
  font: 400 11px var(--font-ui);
  color: var(--dim);
}

.dp-fact-value {
  font: 600 11px var(--font-mono);
  color: var(--txt-2);
  text-align: right;
}

.dp-fact-best {
  color: var(--acc);
}

.dp-audio {
  width: 100%;
  height: 34px;
}

.dp-drawer-foot {
  display: flex;
  gap: 10px;
  padding: 16px 20px;
  border-top: 1px solid rgba(255, 255, 255, .07);
}

.dp-flex {
  flex: 1;
}

.dp-resolved-note {
  font: 500 12.5px var(--font-ui);
  color: var(--muted);
  padding: 8px 0;
}
</style>
