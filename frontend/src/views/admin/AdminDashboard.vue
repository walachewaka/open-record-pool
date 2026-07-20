<template>
  <section>
    <p
      v-if="errorMessage"
      class="ad-error"
    >
      {{ errorMessage }}
    </p>

    <template v-if="stats">
      <div class="ad-stats">
        <div class="ad-card">
          <div class="ad-card-head">
            <span class="ad-card-icon ad-icon-acc">
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <path d="M9 18V6l10-2v12" />
                <circle
                  cx="6"
                  cy="18"
                  r="2.5"
                />
                <circle
                  cx="16"
                  cy="16"
                  r="2.5"
                />
              </svg>
            </span>
            <span class="ad-card-label">TRACKS</span>
          </div>
          <div class="ad-card-value">
            {{ fmtNum(stats.total_tracks) }}
          </div>
          <div class="ad-card-sub">
            {{ fmtNum(stats.published_tracks) }} published
          </div>
        </div>
        <div class="ad-card">
          <div class="ad-card-head">
            <span class="ad-card-icon ad-icon-key">
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
              >
                <circle
                  cx="9"
                  cy="8"
                  r="3.2"
                />
                <path d="M3 19a6 6 0 0 1 12 0" />
                <path d="M16 5.5a3.2 3.2 0 0 1 0 6.2" />
              </svg>
            </span>
            <span class="ad-card-label">ACTIVE MEMBERS</span>
          </div>
          <div class="ad-card-value">
            {{ fmtNum(stats.active_members) }}
          </div>
          <div class="ad-card-sub">
            {{ stats.avg_per_member }} downloads / member · 14d
          </div>
        </div>
        <div class="ad-card">
          <div class="ad-card-head">
            <span class="ad-card-icon ad-icon-ok">
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <path d="M12 4v10" />
                <path d="M8 11l4 4 4-4" />
                <path d="M5 19h14" />
              </svg>
            </span>
            <span class="ad-card-label">DOWNLOADS TODAY</span>
          </div>
          <div class="ad-card-value">
            {{ fmtNum(stats.downloads_today) }}
          </div>
          <div class="ad-card-sub">
            {{ fmtNum(windowTotal) }} in the last 14 days
          </div>
        </div>
        <div class="ad-card">
          <div class="ad-card-head">
            <span class="ad-card-icon ad-icon-warn">
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <path d="M4 7c0-1.5 3.6-2.5 8-2.5s8 1 8 2.5-3.6 2.5-8 2.5-8-1-8-2.5z" />
                <path d="M4 7v10c0 1.5 3.6 2.5 8 2.5s8-1 8-2.5V7" />
              </svg>
            </span>
            <span class="ad-card-label">STORAGE</span>
          </div>
          <div class="ad-card-value">
            {{ fmtBytes(stats.storage.disk_used_bytes) }}
          </div>
          <div class="ad-storage-bar">
            <div
              class="ad-storage-fill"
              :style="{width: stats.storage.percent_used + '%'}"
            />
          </div>
          <div class="ad-card-sub">
            {{ stats.storage.percent_used }}% of {{ fmtBytes(stats.storage.disk_total_bytes) }}
          </div>
        </div>
      </div>

      <div class="ad-grid">
        <div class="ad-col">
          <div class="ad-panel">
            <div class="ad-panel-head">
              <div class="ad-panel-title">
                Downloads · last 14 days
              </div>
              <div class="ad-panel-meta">
                {{ fmtNum(windowTotal) }} total
              </div>
            </div>
            <div class="ad-chart">
              <div
                v-for="point in stats.downloads_14d"
                :key="point.date"
                class="ad-bar"
                :style="{height: barHeight(point.count)}"
                :title="`${point.date} · ${point.count}`"
              />
            </div>
            <div class="ad-chart-axis">
              <span>{{ axisLabel(stats.downloads_14d[0]) }}</span>
              <span>{{ axisLabel(stats.downloads_14d[stats.downloads_14d.length - 1]) }}</span>
            </div>
          </div>
          <div class="ad-panel">
            <div class="ad-panel-title ad-panel-title-gap">
              Top genres by downloads
            </div>
            <div
              v-if="!stats.top_genres.length"
              class="ad-empty"
            >
              No downloads yet.
            </div>
            <div
              v-for="genre in stats.top_genres"
              :key="genre.genre"
              class="ad-genre-row"
            >
              <span class="ad-genre-name">{{ genre.genre }}</span>
              <div class="ad-genre-track">
                <div
                  class="ad-genre-fill"
                  :style="{width: genreWidth(genre.downloads)}"
                />
              </div>
              <span class="ad-genre-count">{{ fmtNum(genre.downloads) }}</span>
            </div>
          </div>
        </div>

        <div class="ad-col">
          <div
            class="ad-panel"
            :class="{'ad-attention': pending > 0}"
          >
            <div class="ad-attention-head">
              <span
                class="ad-attention-icon"
                :class="{'ad-attention-icon-warm': pending > 0}"
              >
                <svg
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.8"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                >
                  <path d="M12 8v5" />
                  <path d="M12 17h.01" />
                  <path d="M10.3 3.9L2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
                </svg>
              </span>
              <span class="ad-panel-title">Needs attention</span>
            </div>
            <div class="ad-attention-body">
              <template v-if="pending > 0">
                <b class="ad-attention-count">{{ pending }} submission{{ pending === 1 ? '' : 's' }}</b>
                waiting for review.
              </template>
              <template v-else>
                Queue is clear — no submissions waiting.
              </template>
            </div>
            <button
              v-if="pending > 0 && perms.approve_submissions"
              type="button"
              class="ad-review-btn"
              @click="$router.push('/admin/moderation')"
            >
              Review queue
            </button>
          </div>

          <div class="ad-panel">
            <div class="ad-panel-title ad-panel-title-gap">
              System health
            </div>
            <div
              v-for="row in healthRows"
              :key="row.label"
              class="ad-health-row"
            >
              <span class="ad-health-label">{{ row.label }}</span>
              <span class="ad-health-value">
                <span
                  class="ad-dot"
                  :style="{background: row.color}"
                />
                {{ row.value }}
              </span>
            </div>
          </div>

          <div
            v-if="perms.edit_metadata"
            class="ad-panel"
          >
            <div class="ad-panel-title ad-panel-title-gap">
              Recent activity
            </div>
            <div
              v-if="!activity.length"
              class="ad-empty"
            >
              Nothing yet.
            </div>
            <div
              v-for="item in activity"
              :key="item.id"
              class="ad-activity-row"
            >
              <span
                class="ad-dot ad-activity-dot"
                :style="{background: statusColor(item.status)}"
              />
              <div class="ad-activity-text">
                <b>{{ item.uploaded_by_username || 'Library scan' }}</b>
                {{ item.source === 'upload' ? 'uploaded' : 'added' }}
                <span class="ad-activity-what">{{ item.title || 'Untitled' }}</span>
                <template v-if="item.genre">
                  · {{ item.genre }}
                </template>
                <div class="ad-activity-when">
                  {{ relativeTime(item.created_at) }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>

<script>
import axios from 'axios';

import { fmtBytes, fmtNum, relativeTime, statusColor } from '@/utils/format';

export default {
  name: 'AdminDashboard',
  data() {
    return {
      stats: null,
      activity: [],
      errorMessage: '',
    };
  },
  computed: {
    perms() {
      return this.$store.getters.userPermissions;
    },
    pending() {
      return this.stats ? this.stats.needs_attention.pending : 0;
    },
    windowTotal() {
      return this.stats
        ? this.stats.downloads_14d.reduce((sum, point) => sum + point.count, 0)
        : 0;
    },
    maxCount() {
      return this.stats
        ? Math.max(1, ...this.stats.downloads_14d.map(point => point.count))
        : 1;
    },
    maxGenre() {
      return this.stats
        ? Math.max(1, ...this.stats.top_genres.map(genre => genre.downloads))
        : 1;
    },
    healthRows() {
      const health = this.stats.system_health;
      return [
        {
          label: 'Search index',
          value: health.search === 'n/a' ? 'n/a · PostgreSQL reads' : health.search,
          color: health.search === 'n/a' ? 'var(--dim)' : 'var(--ok)',
        },
        {
          label: 'NAS source',
          value: health.nas_readable ? 'Mounted · readable' : 'Not readable',
          color: health.nas_readable ? 'var(--ok)' : 'var(--danger)',
        },
        {
          label: 'Duplicates',
          value: health.duplicates > 0 ? `${health.duplicates} flagged` : 'None flagged',
          color: health.duplicates > 0 ? 'var(--warn)' : 'var(--ok)',
        },
      ];
    },
  },
  created() {
    this.fetchStats();
    if (this.perms.edit_metadata) {
      this.fetchActivity();
    }
  },
  methods: {
    fmtBytes,
    fmtNum,
    relativeTime,
    statusColor,
    async fetchStats() {
      try {
        const {data} = await axios.get('admin/stats/dashboard');
        this.stats = data;
      } catch (error) {
        const detail = error.response && error.response.data && error.response.data.detail;
        this.errorMessage =
          (typeof detail === 'string' && detail) || 'Could not load the dashboard.';
      }
    },
    // "Recent activity" = the newest catalog entries; the closest thing the
    // admin API exposes to an event feed.
    async fetchActivity() {
      try {
        const {data} = await axios.get('admin/content', {
          params: {page: 1, page_size: 6},
        });
        this.activity = data.items;
      } catch (error) {
        // The card just stays empty; the dashboard error covers the rest.
      }
    },
    barHeight(count) {
      return Math.max(2, Math.round((count / this.maxCount) * 100)) + '%';
    },
    genreWidth(downloads) {
      return Math.round((downloads / this.maxGenre) * 100) + '%';
    },
    axisLabel(point) {
      if (!point) {
        return '';
      }
      const date = new Date(`${point.date}T00:00:00Z`);
      const month = date
        .toLocaleString('en-US', {month: 'short', timeZone: 'UTC'})
        .toUpperCase();
      return `${point.date.slice(8, 10)} ${month}`;
    },
  },
};
</script>

<style scoped>
.ad-error {
  color: var(--danger);
  font: 400 13px var(--font-ui);
}

.ad-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.ad-card {
  padding: 16px 18px;
  border-radius: 13px;
  background: var(--panel);
  border: 1px solid var(--line);
}

.ad-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.ad-card-icon {
  display: flex;
}

.ad-icon-acc {
  color: var(--acc);
}

.ad-icon-key {
  color: var(--key);
}

.ad-icon-ok {
  color: var(--ok);
}

.ad-icon-warn {
  color: var(--warn);
}

.ad-card-label {
  font: 600 10px var(--font-mono);
  letter-spacing: .08em;
  color: var(--dim-2);
}

.ad-card-value {
  font: 700 27px var(--font-disp);
}

.ad-card-sub {
  font: 400 11.5px var(--font-ui);
  color: var(--dim);
  margin-top: 2px;
}

.ad-storage-bar {
  height: 5px;
  border-radius: 3px;
  background: rgba(255, 255, 255, .09);
  overflow: hidden;
  margin-top: 8px;
}

.ad-storage-fill {
  height: 100%;
  background: var(--warn);
  border-radius: 3px;
}

.ad-grid {
  display: grid;
  grid-template-columns: 1.6fr 1fr;
  gap: 16px;
  align-items: start;
}

.ad-col {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.ad-panel {
  padding: 18px;
  border-radius: 13px;
  background: var(--panel);
  border: 1px solid var(--line);
}

.ad-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
}

.ad-panel-title {
  font: 600 13px var(--font-disp);
}

.ad-panel-title-gap {
  margin-bottom: 14px;
}

.ad-panel-meta {
  font: 600 12px var(--font-mono);
  color: var(--dim);
}

.ad-chart {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  height: 120px;
}

.ad-bar {
  flex: 1;
  min-width: 4px;
  border-radius: 3px 3px 0 0;
  background: linear-gradient(180deg, var(--acc), color-mix(in oklab, var(--acc) 40%, transparent));
}

.ad-chart-axis {
  display: flex;
  justify-content: space-between;
  font: 500 10px var(--font-mono);
  color: var(--dim-2);
  margin-top: 8px;
}

.ad-genre-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 11px;
}

.ad-genre-row:last-child {
  margin-bottom: 0;
}

.ad-genre-name {
  width: 92px;
  font: 500 12px var(--font-ui);
  color: var(--txt-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ad-genre-track {
  flex: 1;
  height: 8px;
  border-radius: 4px;
  background: rgba(255, 255, 255, .05);
  overflow: hidden;
}

.ad-genre-fill {
  height: 100%;
  background: var(--acc);
  border-radius: 4px;
}

.ad-genre-count {
  width: 44px;
  text-align: right;
  font: 600 11px var(--font-mono);
  color: var(--muted);
}

.ad-empty {
  font: 400 12.5px var(--font-ui);
  color: var(--dim-2);
}

.ad-attention {
  background: color-mix(in oklab, var(--warn) 9%, var(--panel));
  border-color: rgba(255, 182, 46, .22);
}

.ad-attention-head {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 8px;
}

.ad-attention-icon {
  display: flex;
  color: var(--dim);
}

.ad-attention-icon-warm {
  color: var(--warn);
}

.ad-attention-body {
  font: 400 13px/1.5 var(--font-ui);
  color: var(--txt-2);
}

.ad-attention-count {
  color: var(--warn);
}

.ad-review-btn {
  margin-top: 14px;
  height: 36px;
  padding: 0 15px;
  border-radius: var(--r-ctl);
  border: none;
  background: var(--warn);
  color: #2a1c00;
  font: 600 12.5px var(--font-ui);
  cursor: pointer;
  transition: filter .15s ease;
}

.ad-review-btn:hover {
  filter: brightness(1.06);
}

.ad-health-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 11px;
}

.ad-health-row:last-child {
  margin-bottom: 0;
}

.ad-health-label {
  font: 500 12.5px var(--font-ui);
  color: var(--txt-2);
}

.ad-health-value {
  display: flex;
  align-items: center;
  gap: 7px;
  font: 500 11.5px var(--font-mono);
  color: var(--muted);
}

.ad-dot {
  width: 7px;
  height: 7px;
  border-radius: 4px;
  flex: none;
}

.ad-activity-row {
  display: flex;
  gap: 11px;
  align-items: flex-start;
  margin-bottom: 14px;
}

.ad-activity-row:last-child {
  margin-bottom: 0;
}

.ad-activity-dot {
  margin-top: 6px;
}

.ad-activity-text {
  font: 400 12.5px/1.45 var(--font-ui);
  color: var(--muted);
}

.ad-activity-text b {
  color: var(--txt);
  font-weight: 600;
}

.ad-activity-what {
  color: var(--txt-2);
}

.ad-activity-when {
  font: 500 10.5px var(--font-mono);
  color: var(--dim-2);
  margin-top: 2px;
}
</style>
