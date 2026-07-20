<template>
  <section>
    <div class="ar-toolbar">
      <SegmentedControl
        v-model="range"
        :options="rangeOptions"
      />
    </div>

    <p
      v-if="errorMessage"
      class="ar-error"
    >
      {{ errorMessage }}
    </p>

    <template v-if="report">
      <div class="ar-stats">
        <div class="ar-card">
          <div class="ar-card-label">
            TOTAL DOWNLOADS
          </div>
          <div class="ar-card-value">
            {{ fmtNum(report.total_downloads) }}
          </div>
          <div class="ar-card-sub">
            {{ report.range.start }} → {{ report.range.end }}
          </div>
        </div>
        <div class="ar-card">
          <div class="ar-card-label">
            ACTIVE MEMBERS
          </div>
          <div class="ar-card-value">
            {{ fmtNum(report.active_members) }}
          </div>
          <div class="ar-card-sub">
            with active status
          </div>
        </div>
        <div class="ar-card">
          <div class="ar-card-label">
            AVG / MEMBER
          </div>
          <div class="ar-card-value">
            {{ report.avg_per_member }}
          </div>
          <div class="ar-card-sub">
            downloads in range
          </div>
        </div>
        <div class="ar-card">
          <div class="ar-card-label">
            CATALOG
          </div>
          <div class="ar-card-value">
            {{ fmtNum(report.catalog) }}
          </div>
          <div class="ar-card-sub">
            tracks total
          </div>
        </div>
      </div>

      <div class="ar-panel ar-chart-panel">
        <div class="ar-panel-head">
          <div class="ar-panel-title">
            Downloads over time
          </div>
          <div class="ar-panel-meta">
            last {{ range }} days
          </div>
        </div>
        <div class="ar-chart">
          <div
            v-for="point in report.downloads_over_time"
            :key="point.date"
            class="ar-bar"
            :style="{height: barHeight(point.count)}"
            :title="`${point.date} · ${point.count}`"
          />
        </div>
      </div>

      <div class="ar-grid">
        <div class="ar-panel">
          <div class="ar-panel-title ar-panel-title-gap">
            Top tracks
          </div>
          <div
            v-if="!report.top_tracks.length"
            class="ar-empty"
          >
            No downloads in this range.
          </div>
          <div
            v-for="entry in report.top_tracks"
            :key="entry.song.id"
            class="ar-track-row"
          >
            <span class="ar-rank">{{ entry.rank }}</span>
            <div
              class="ar-cover"
              :style="{background: tintForId(entry.song.id)}"
            >
              {{ initialsFor(entry.song.title || entry.song.artist) }}
            </div>
            <div class="ar-track-meta">
              <div class="ar-track-title">
                {{ entry.song.title || 'Untitled' }}
              </div>
              <div class="ar-track-artist">
                {{ entry.song.artist || 'Unknown artist' }}
              </div>
            </div>
            <span class="ar-track-dls">{{ fmtNum(entry.downloads) }}</span>
          </div>
        </div>
        <div class="ar-col">
          <div class="ar-panel">
            <div class="ar-panel-title ar-panel-title-gap">
              Top genres
            </div>
            <div
              v-if="!report.top_genres.length"
              class="ar-empty"
            >
              No downloads in this range.
            </div>
            <div
              v-for="genre in report.top_genres"
              :key="genre.genre"
              class="ar-genre-row"
            >
              <span class="ar-genre-name">{{ genre.genre }}</span>
              <div class="ar-genre-track">
                <div
                  class="ar-genre-fill"
                  :style="{width: genreWidth(genre.downloads)}"
                />
              </div>
            </div>
          </div>
          <div class="ar-panel">
            <div class="ar-panel-title ar-panel-title-gap">
              Downloads by format
            </div>
            <div
              v-if="!report.downloads_by_format.length"
              class="ar-empty"
            >
              No downloads in this range.
            </div>
            <div
              v-for="entry in report.downloads_by_format"
              :key="entry.format"
              class="ar-fmt-row"
            >
              <span class="ar-fmt-name">{{ entry.format.toUpperCase() }}</span>
              <div class="ar-fmt-track">
                <div
                  class="ar-fmt-fill"
                  :style="{width: formatWidth(entry.count)}"
                />
              </div>
              <span class="ar-fmt-pct">{{ formatWidth(entry.count) }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>

<script>
import axios from 'axios';

import SegmentedControl from '@/components/admin/SegmentedControl.vue';
import { fmtNum, initialsFor, tintForId } from '@/utils/format';

export default {
  name: 'AdminReports',
  components: {
    SegmentedControl,
  },
  data() {
    return {
      range: '14',
      report: null,
      errorMessage: '',
    };
  },
  computed: {
    rangeOptions() {
      return [
        {value: '7', label: '7d'},
        {value: '14', label: '14d'},
        {value: '30', label: '30d'},
        {value: '90', label: '90d'},
      ];
    },
    maxCount() {
      return this.report
        ? Math.max(1, ...this.report.downloads_over_time.map(point => point.count))
        : 1;
    },
    maxGenre() {
      return this.report
        ? Math.max(1, ...this.report.top_genres.map(genre => genre.downloads))
        : 1;
    },
    formatTotal() {
      return this.report
        ? this.report.downloads_by_format.reduce((sum, entry) => sum + entry.count, 0)
        : 0;
    },
  },
  watch: {
    range() {
      this.fetchReport();
    },
  },
  created() {
    return this.fetchReport();
  },
  methods: {
    fmtNum,
    initialsFor,
    tintForId,
    isoDaysAgo(days) {
      const date = new Date(Date.now() - days * 86400000);
      return date.toISOString().slice(0, 10);
    },
    async fetchReport() {
      this.errorMessage = '';
      try {
        const days = Number(this.range);
        const {data} = await axios.get('admin/stats/reports', {
          params: {
            start: this.isoDaysAgo(days - 1),
            end: this.isoDaysAgo(0),
            limit: 10,
          },
        });
        this.report = data;
      } catch (error) {
        const detail = error.response && error.response.data && error.response.data.detail;
        this.errorMessage =
          (typeof detail === 'string' && detail) || 'Could not load the report.';
      }
    },
    barHeight(count) {
      return Math.max(2, Math.round((count / this.maxCount) * 100)) + '%';
    },
    genreWidth(downloads) {
      return Math.round((downloads / this.maxGenre) * 100) + '%';
    },
    formatWidth(count) {
      if (!this.formatTotal) {
        return '0%';
      }
      return Math.round((count / this.formatTotal) * 100) + '%';
    },
  },
};
</script>

<style scoped>
.ar-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 16px;
}

.ar-error {
  color: var(--danger);
  font: 400 13px var(--font-ui);
}

.ar-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.ar-card {
  padding: 16px 18px;
  border-radius: 13px;
  background: var(--panel);
  border: 1px solid var(--line);
}

.ar-card-label {
  font: 600 10px var(--font-mono);
  letter-spacing: .08em;
  color: var(--dim-2);
  margin-bottom: 10px;
}

.ar-card-value {
  font: 700 26px var(--font-disp);
}

.ar-card-sub {
  font: 400 11.5px var(--font-ui);
  color: var(--dim);
  margin-top: 2px;
}

.ar-panel {
  padding: 18px;
  border-radius: 13px;
  background: var(--panel);
  border: 1px solid var(--line);
}

.ar-chart-panel {
  margin-bottom: 16px;
}

.ar-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
}

.ar-panel-title {
  font: 600 13px var(--font-disp);
}

.ar-panel-title-gap {
  margin-bottom: 16px;
}

.ar-panel-meta {
  font: 600 12px var(--font-mono);
  color: var(--dim);
}

.ar-chart {
  display: flex;
  align-items: flex-end;
  gap: 4px;
  height: 150px;
}

.ar-bar {
  flex: 1;
  min-width: 2px;
  border-radius: 3px 3px 0 0;
  background: linear-gradient(180deg, var(--acc), color-mix(in oklab, var(--acc) 35%, transparent));
}

.ar-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  align-items: start;
}

.ar-col {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.ar-empty {
  font: 400 12.5px var(--font-ui);
  color: var(--dim-2);
}

.ar-track-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.ar-track-row:last-child {
  margin-bottom: 0;
}

.ar-rank {
  font: 600 13px var(--font-mono);
  color: var(--dim-2);
  width: 16px;
}

.ar-cover {
  width: 36px;
  height: 36px;
  border-radius: 7px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: none;
  box-shadow: var(--shadow-cover);
  font: 600 10px var(--font-mono);
  color: rgba(255, 255, 255, .7);
}

.ar-track-meta {
  flex: 1;
  min-width: 0;
}

.ar-track-title {
  font: 600 12.5px var(--font-ui);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ar-track-artist {
  font: 400 11.5px var(--font-ui);
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ar-track-dls {
  font: 600 12px var(--font-mono);
  color: var(--txt-2);
}

.ar-genre-row {
  display: flex;
  align-items: center;
  gap: 11px;
  margin-bottom: 10px;
}

.ar-genre-row:last-child {
  margin-bottom: 0;
}

.ar-genre-name {
  width: 84px;
  font: 500 12px var(--font-ui);
  color: var(--txt-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ar-genre-track {
  flex: 1;
  height: 8px;
  border-radius: 4px;
  background: rgba(255, 255, 255, .05);
  overflow: hidden;
}

.ar-genre-fill {
  height: 100%;
  background: var(--key);
  border-radius: 4px;
}

.ar-fmt-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.ar-fmt-row:last-child {
  margin-bottom: 0;
}

.ar-fmt-name {
  width: 56px;
  font: 600 12px var(--font-mono);
  color: var(--txt-2);
}

.ar-fmt-track {
  flex: 1;
  height: 14px;
  border-radius: 7px;
  background: rgba(255, 255, 255, .05);
  overflow: hidden;
}

.ar-fmt-fill {
  height: 100%;
  background: var(--acc);
}

.ar-fmt-pct {
  font: 600 12px var(--font-mono);
  color: var(--muted);
  width: 36px;
  text-align: right;
}
</style>
