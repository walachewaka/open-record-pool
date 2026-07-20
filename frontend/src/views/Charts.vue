<template>
  <section>
    <div class="ch-head">
      <div>
        <div class="ch-eyebrow">
          UPDATED TODAY · {{ todayLabel }}
        </div>
        <div class="ch-title">
          {{ title }}
        </div>
      </div>
      <div class="ch-modes">
        <button
          v-for="option in modes"
          :key="option.mode"
          type="button"
          class="ch-mode"
          :class="{'ch-mode-on': option.mode === mode}"
          @click="setMode(option.mode)"
        >
          {{ option.label }}
        </button>
      </div>
    </div>

    <p
      v-if="errorMessage"
      class="ch-error"
    >
      {{ errorMessage }}
    </p>

    <div class="list-panel">
      <div class="ch-list-head">
        <span>#</span>
        <span>Track</span>
        <span>Waveform</span>
        <span class="lh-c">Key</span>
        <span class="lh-c">BPM</span>
        <span class="lh-r">{{ metricLabel }}</span>
        <span />
      </div>
      <div
        v-if="!loading && !entries.length"
        class="list-empty"
      >
        Nothing charted yet — play and download some tracks first.
      </div>
      <div
        v-for="entry in entries"
        :key="entry.song.id"
        class="ch-row"
        draggable="true"
        @dragstart="onDragStart($event, entry.song)"
      >
        <div class="ch-rank">
          <span class="ch-rank-num">{{ rankLabel(entry.rank) }}</span>
          <span
            v-if="isNew(entry.song)"
            class="ch-new"
          >NEW</span>
          <span
            v-else
            class="ch-same"
          />
        </div>

        <div class="ch-track">
          <button
            type="button"
            class="ch-cover"
            :style="{background: tint(entry.song)}"
            title="Play / pause"
            @click="toggleFromCover(entry.song)"
          >
            <span class="ch-initials">{{ initials(entry.song) }}</span>
            <span class="ch-cover-overlay">
              <svg
                v-if="isPlaying(entry.song)"
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="currentColor"
              >
                <rect
                  x="6"
                  y="5"
                  width="4"
                  height="14"
                  rx="1"
                />
                <rect
                  x="14"
                  y="5"
                  width="4"
                  height="14"
                  rx="1"
                />
              </svg>
              <svg
                v-else
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="currentColor"
              >
                <path d="M8 5v14l11-7z" />
              </svg>
            </span>
          </button>
          <div class="ch-meta">
            <button
              type="button"
              class="ch-name"
              :class="{'ch-name-current': isCurrent(entry.song)}"
              :title="entry.song.title || ''"
              @click="openRelease(entry.song)"
            >
              {{ entry.song.title || 'Untitled' }}
            </button>
            <div class="ch-sub">
              {{ entry.song.artist || 'Unknown artist' }} · {{ entry.song.genre || '—' }}
            </div>
          </div>
        </div>

        <button
          type="button"
          class="ch-wave"
          title="Preview"
          @click="playFromWave(entry.song)"
        >
          <div class="ch-bars">
            <span
              v-for="(height, index) in wave(entry.song)"
              :key="index"
              :style="{height: height}"
            />
          </div>
          <div
            v-if="isCurrent(entry.song)"
            class="ch-wave-overlay"
          >
            <div class="ch-bars ch-bars-active">
              <span
                v-for="(height, index) in wave(entry.song)"
                :key="index"
                :style="{height: height}"
              />
            </div>
          </div>
        </button>

        <div class="ch-key">
          {{ keyLabel(entry.song) }}
        </div>
        <div class="ch-bpm">
          {{ bpmLabel(entry.song) }}
        </div>
        <div class="ch-metric">
          {{ metricValue(entry) }}
        </div>

        <div class="ch-get">
          <button
            type="button"
            class="ch-dl"
            :class="{'ch-dl-saved': saved(entry.song)}"
            :title="saved(entry.song) ? 'Saved' : 'Download MP3'"
            @click="download(entry.song)"
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
  </section>
</template>

<script>
import axios from 'axios';
import { mapActions, mapGetters } from 'vuex';

import { downloadSong } from '@/utils/download';
import { waveBars } from '@/utils/waveform';

const MODES = [
  {mode: 'most_downloaded', label: 'Most downloaded', title: 'Top 40 — Most Downloaded', metric: 'Downloads'},
  {mode: 'most_played', label: 'Most played', title: 'Most Played', metric: 'Plays'},
  {mode: 'added_this_month', label: 'Added this month', title: 'Added This Month', metric: 'Added'},
];

export default {
  name: 'ChartsView',
  data() {
    return {
      mode: 'most_downloaded',
      modes: MODES,
      entries: [],
      loading: true,
      errorMessage: '',
    };
  },
  computed: {
    ...mapGetters({
      currentSong: 'stateSong',
      playing: 'statePlaying',
      downloadedIds: 'stateDownloadedIds',
    }),
    title() {
      return MODES.find(option => option.mode === this.mode).title;
    },
    metricLabel() {
      return MODES.find(option => option.mode === this.mode).metric;
    },
    todayLabel() {
      const now = new Date();
      const month = now.toLocaleString('en', {month: 'short'}).toUpperCase();
      return `${String(now.getDate()).padStart(2, '0')} ${month}`;
    },
    // No previous-period data in the charts API, so the movement indicator
    // is simply NEW (added this month) vs same (a dash).
    monthStart() {
      const now = new Date();
      return new Date(now.getFullYear(), now.getMonth(), 1);
    },
  },
  created() {
    return this.fetchCharts();
  },
  methods: {
    ...mapActions(['playSong', 'togglePlayback', 'setQueue']),
    async fetchCharts() {
      this.loading = true;
      this.errorMessage = '';
      try {
        const {data} = await axios.get('charts', {
          params: {mode: this.mode, limit: 40},
        });
        this.entries = data.entries;
        // The player's prev/next and auto-advance walk this list.
        this.setQueue(data.entries.map(entry => entry.song));
      } catch (error) {
        const detail = error.response && error.response.data && error.response.data.detail;
        this.errorMessage =
          (typeof detail === 'string' && detail) ||
          'Could not load the charts.';
      } finally {
        this.loading = false;
      }
    },
    setMode(mode) {
      if (this.mode === mode) {
        return;
      }
      this.mode = mode;
      this.fetchCharts();
    },
    rankLabel(rank) {
      return String(rank).padStart(2, '0');
    },
    isNew(song) {
      return !!song.created_at && new Date(song.created_at) >= this.monthStart;
    },
    metricValue(entry) {
      if (this.mode === 'added_this_month') {
        return entry.metric === 0 ? 'today' : `${entry.metric}d ago`;
      }
      return entry.metric >= 1000
        ? `${(entry.metric / 1000).toFixed(1)}k`
        : String(entry.metric);
    },
    isCurrent(song) {
      return !!this.currentSong && this.currentSong.id === song.id;
    },
    isPlaying(song) {
      return this.isCurrent(song) && this.playing;
    },
    saved(song) {
      return this.downloadedIds.includes(song.id);
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
    wave(song) {
      return waveBars(song.id, 48);
    },
    keyLabel(song) {
      return song.camelot_key || song.musical_key || '—';
    },
    bpmLabel(song) {
      return song.bpm == null ? '—' : String(Math.round(song.bpm));
    },
    toggleFromCover(song) {
      if (this.isCurrent(song)) {
        this.togglePlayback();
      } else {
        this.playSong(song);
      }
    },
    playFromWave(song) {
      if (!this.isCurrent(song)) {
        this.playSong(song);
      } else if (!this.playing) {
        this.togglePlayback();
      }
    },
    openRelease(song) {
      this.$router.push(`/release/${song.id}`);
    },
    download(song) {
      downloadSong(song);
    },
    onDragStart(event, song) {
      // Same payload as TrackRow so sidebar crates accept chart rows too.
      event.dataTransfer.setData('text/plain', String(song.id));
      event.dataTransfer.effectAllowed = 'copy';
    },
  },
};
</script>

<style scoped>
.ch-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 14px;
  margin-bottom: 18px;
}

.ch-eyebrow {
  font: 600 11px var(--font-mono);
  letter-spacing: .1em;
  color: var(--acc);
  margin-bottom: 6px;
}

.ch-title {
  font: 700 24px/1 var(--font-disp);
}

.ch-modes {
  display: flex;
  gap: 4px;
  padding: 4px;
  border-radius: 10px;
  background: var(--raised);
  border: 1px solid rgba(255, 255, 255, .08);
}

.ch-mode {
  padding: 6px 13px;
  border-radius: 7px;
  border: none;
  cursor: pointer;
  background: transparent;
  color: var(--muted);
  font: 600 12px var(--font-ui);
  transition: background .15s ease, color .15s ease;
}

.ch-mode-on {
  background: var(--acc-soft-strong);
  color: var(--acc);
}

.ch-error {
  font: 400 12.5px var(--font-ui);
  color: var(--danger);
  margin: 0 0 12px;
}

.list-panel {
  border: 1px solid var(--line);
  border-radius: 13px;
  overflow: hidden;
  background: var(--panel);
}

.ch-list-head {
  display: grid;
  grid-template-columns: 52px minmax(180px, 1.5fr) minmax(120px, 1.7fr) 40px 46px 92px 60px;
  align-items: center;
  gap: 10px;
  height: 36px;
  padding: 0 14px;
  border-bottom: 1px solid rgba(255, 255, 255, .07);
  font: 600 10px var(--font-mono);
  letter-spacing: .08em;
  color: var(--dim-2);
  text-transform: uppercase;
}

.lh-c {
  text-align: center;
}

.lh-r {
  text-align: right;
}

.list-empty {
  padding: 56px 20px;
  text-align: center;
  color: var(--dim-2);
  font: 400 14px var(--font-ui);
}

.ch-row {
  display: grid;
  grid-template-columns: 52px minmax(180px, 1.5fr) minmax(120px, 1.7fr) 40px 46px 92px 60px;
  align-items: center;
  gap: 10px;
  height: 56px;
  padding: 0 14px;
  border-bottom: 1px solid rgba(255, 255, 255, .045);
  cursor: grab;
  transition: background .15s ease;
}

.ch-row:hover {
  background: rgba(255, 255, 255, .035);
}

.ch-rank {
  display: flex;
  align-items: center;
  gap: 6px;
}

.ch-rank-num {
  font: 600 15px var(--font-mono);
  color: var(--txt);
  min-width: 20px;
}

.ch-new {
  font: 700 7.5px var(--font-mono);
  color: var(--acc);
  letter-spacing: .04em;
}

.ch-same {
  width: 8px;
  height: 2px;
  background: var(--dim-2);
  border-radius: 2px;
}

.ch-track {
  display: flex;
  align-items: center;
  gap: 11px;
  min-width: 0;
}

.ch-cover {
  position: relative;
  width: 40px;
  height: 40px;
  border-radius: 7px;
  border: none;
  padding: 0;
  margin: 0;
  cursor: pointer;
  box-shadow: var(--shadow-cover);
  overflow: hidden;
  flex: none;
}

.ch-initials {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font: 600 11px var(--font-mono);
  color: rgba(255, 255, 255, .72);
}

.ch-cover-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(4, 10, 16, .55);
  color: #fff;
  opacity: 0;
  transition: opacity .15s ease;
}

.ch-cover:hover .ch-cover-overlay {
  opacity: 1;
}

.ch-meta {
  min-width: 0;
}

.ch-name {
  background: none;
  border: none;
  padding: 0;
  margin: 0;
  cursor: pointer;
  display: block;
  font: 600 13.5px/1.2 var(--font-ui);
  color: var(--txt);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: left;
  max-width: 100%;
}

.ch-name-current {
  color: var(--acc);
}

.ch-sub {
  font: 400 12px/1.3 var(--font-ui);
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ch-wave {
  position: relative;
  background: none;
  border: none;
  padding: 0;
  margin: 0;
  cursor: pointer;
  height: 34px;
  display: flex;
  align-items: center;
  min-width: 0;
}

.ch-bars {
  display: flex;
  align-items: flex-end;
  gap: 2px;
  width: 100%;
  height: 26px;
}

.ch-bars span {
  flex: 1;
  min-width: 1px;
  background: #2b333e;
  border-radius: 1px;
}

.ch-wave-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  pointer-events: none;
}

.ch-bars-active span {
  background: var(--acc);
}

.ch-key {
  font: 600 12px var(--font-mono);
  color: var(--key);
  text-align: center;
}

.ch-bpm {
  font: 500 12px var(--font-mono);
  color: var(--txt-2);
  text-align: center;
}

.ch-metric {
  font: 600 13px var(--font-mono);
  color: var(--txt);
  text-align: right;
}

.ch-get {
  display: flex;
  justify-content: flex-end;
}

.ch-dl {
  width: 34px;
  height: 34px;
  flex: none;
  border: none;
  padding: 0;
  margin: 0;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 7px;
  background: rgba(255, 255, 255, .06);
  color: var(--txt);
  transition: filter .15s ease;
}

.ch-dl:hover {
  filter: brightness(1.15);
}

.ch-dl-saved {
  background: var(--acc-soft-strong);
  color: var(--acc);
}
</style>
