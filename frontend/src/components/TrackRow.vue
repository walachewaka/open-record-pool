<template>
  <div
    class="trow"
    draggable="true"
    @dragstart="onDragStart"
  >
    <button
      type="button"
      class="tr-cover"
      :style="{background: tint}"
      title="Play / pause"
      @click="toggleFromCover"
    >
      <span class="tr-initials">{{ initials }}</span>
      <span class="tr-cover-overlay">
        <svg
          v-if="isPlaying"
          width="15"
          height="15"
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
          width="15"
          height="15"
          viewBox="0 0 24 24"
          fill="currentColor"
        >
          <path d="M8 5v14l11-7z" />
        </svg>
      </span>
    </button>

    <div class="tr-meta">
      <button
        type="button"
        class="tr-title"
        :class="{'tr-title-current': isCurrent}"
        :title="song.title || ''"
        @click="openRelease"
      >
        {{ song.title || 'Untitled' }}
      </button>
      <div class="tr-sub">
        <span class="tr-artist">{{ song.artist || 'Unknown artist' }}</span>
        <span class="tr-dot" />
        <span class="tr-genre">{{ song.genre || '—' }}</span>
      </div>
    </div>

    <button
      type="button"
      class="tr-wave"
      title="Preview"
      @click="playFromWave"
    >
      <div class="tr-bars">
        <span
          v-for="(height, index) in wave"
          :key="index"
          :style="{height: height}"
        />
      </div>
      <div
        v-if="isCurrent"
        class="tr-wave-overlay"
      >
        <div class="tr-bars tr-bars-active">
          <span
            v-for="(height, index) in wave"
            :key="index"
            :style="{height: height}"
          />
        </div>
      </div>
    </button>

    <div class="tr-key">
      {{ keyLabel }}
    </div>
    <div class="tr-bpm">
      {{ bpmLabel }}
    </div>
    <div class="tr-time">
      {{ timeLabel }}
    </div>

    <div class="tr-actions">
      <button
        v-if="removable"
        type="button"
        class="tr-icon tr-remove"
        title="Remove from crate"
        @click="$emit('remove', song)"
      >
        <svg
          width="15"
          height="15"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
        >
          <path d="M6 6l12 12M18 6L6 18" />
        </svg>
      </button>
      <button
        type="button"
        class="tr-icon tr-fav"
        :class="{'tr-fav-on': isFavorite}"
        title="Favorite"
        @click="onToggleFavorite"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          :fill="isFavorite ? 'currentColor' : 'none'"
          stroke="currentColor"
          stroke-width="1.8"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d="M12 20.5S3.5 15 3.5 9.2C3.5 6.6 5.4 5 7.6 5c1.7 0 3.1 1 4.4 2.6C13.3 6 14.7 5 16.4 5c2.2 0 4.1 1.6 4.1 4.2 0 5.8-8.5 11.3-8.5 11.3z" />
        </svg>
      </button>
      <button
        type="button"
        class="tr-dl"
        :class="{'tr-dl-saved': saved}"
        :title="saved ? 'Saved' : 'Download MP3'"
        @click="download"
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
      <button
        type="button"
        class="tr-icon tr-more"
        title="Versions"
        @click="openRelease"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="currentColor"
        >
          <circle
            cx="12"
            cy="6"
            r="1.6"
          />
          <circle
            cx="12"
            cy="12"
            r="1.6"
          />
          <circle
            cx="12"
            cy="18"
            r="1.6"
          />
        </svg>
      </button>
    </div>
  </div>
</template>

<script>
import { mapActions, mapGetters } from 'vuex';

import { downloadSong } from '@/utils/download';
import { fetchPeaks, peaksToBars, waveBars } from '@/utils/waveform';

export default {
  name: 'TrackRow',
  props: {
    song: {
      type: Object,
      required: true,
    },
    // Shows the remove-from-crate button (crate view only).
    removable: {
      type: Boolean,
      default: false,
    },
  },
  emits: ['remove'],
  data() {
    return {
      // Analyzed waveform peaks (MOO-87); null keeps the seeded bars.
      realPeaks: null,
    };
  },
  computed: {
    ...mapGetters({
      currentSong: 'stateSong',
      playing: 'statePlaying',
      favOverrides: 'stateFavOverrides',
      downloadedIds: 'stateDownloadedIds',
    }),
    isCurrent() {
      return !!this.currentSong && this.currentSong.id === this.song.id;
    },
    isPlaying() {
      return this.isCurrent && this.playing;
    },
    isFavorite() {
      // Store overrides keep hearts in sync with the player bar; the API's
      // is_favorite flag is the source of truth until a toggle happens.
      const override = this.favOverrides[this.song.id];
      return override === undefined ? !!this.song.is_favorite : override;
    },
    saved() {
      return this.downloadedIds.includes(this.song.id);
    },
    initials() {
      const source = this.song.title || this.song.artist || '?';
      const words = source.trim().split(/\s+/);
      const letters = words.length > 1
        ? words[0][0] + words[1][0]
        : source.slice(0, 2);
      return letters.toUpperCase();
    },
    tint() {
      return `var(--tint-${(this.song.id % 10) + 1})`;
    },
    wave() {
      return this.realPeaks
        ? peaksToBars(this.realPeaks)
        : waveBars(this.song.id);
    },
    keyLabel() {
      return this.song.camelot_key || this.song.musical_key || '—';
    },
    bpmLabel() {
      return this.song.bpm == null ? '—' : String(Math.round(this.song.bpm));
    },
    timeLabel() {
      const seconds = this.song.duration_seconds;
      if (seconds == null) {
        return '—';
      }
      const total = Math.round(seconds);
      return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
    },
  },
  watch: {
    'song.id': {
      immediate: true,
      handler() {
        this.realPeaks = null;
        const songId = this.song.id;
        fetchPeaks(this.song).then((peaks) => {
          if (this.song && this.song.id === songId) {
            this.realPeaks = peaks;
          }
        });
      },
    },
  },
  methods: {
    ...mapActions(['playSong', 'togglePlayback', 'toggleFavorite']),
    toggleFromCover() {
      if (this.isCurrent) {
        this.togglePlayback();
      } else {
        this.playSong(this.song);
      }
    },
    playFromWave() {
      if (!this.isCurrent) {
        this.playSong(this.song);
      } else if (!this.playing) {
        this.togglePlayback();
      }
    },
    openRelease() {
      this.$router.push(`/release/${this.song.id}`);
    },
    async onToggleFavorite() {
      try {
        await this.toggleFavorite(this.song);
      } catch (error) {
        // Leave the heart untouched; the axios interceptor already handles
        // an expired session.
      }
    },
    download() {
      downloadSong(this.song);
    },
    onDragStart(event) {
      // The Crates stage consumes this payload for drag-and-drop adds.
      event.dataTransfer.setData('text/plain', String(this.song.id));
      event.dataTransfer.effectAllowed = 'copy';
    },
  },
};
</script>

<style scoped>
.trow {
  display: grid;
  grid-template-columns: 40px minmax(168px, 1.5fr) minmax(120px, 1.9fr) 40px 48px 46px 96px;
  align-items: center;
  gap: 10px;
  height: var(--rowh);
  padding: 0 10px;
  border-bottom: 1px solid rgba(255, 255, 255, .045);
  cursor: grab;
  transition: background .15s ease;
}

.trow:hover {
  background: rgba(255, 255, 255, .035);
}

.tr-cover {
  position: relative;
  width: 36px;
  height: 36px;
  border-radius: 6px;
  border: none;
  padding: 0;
  margin: 0;
  cursor: pointer;
  box-shadow: var(--shadow-cover);
  overflow: hidden;
}

.tr-initials {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font: 600 10px var(--font-mono);
  color: rgba(255, 255, 255, .72);
  letter-spacing: .02em;
}

.tr-cover-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(4, 10, 16, .58);
  color: #fff;
  opacity: 0;
  transition: opacity .15s ease;
}

.tr-cover:hover .tr-cover-overlay {
  opacity: 1;
}

.tr-meta {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  justify-content: center;
}

.tr-title {
  background: none;
  border: none;
  padding: 0;
  margin: 0;
  cursor: pointer;
  font: 600 13px/1.2 var(--font-ui);
  color: var(--txt);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: left;
}

.tr-title-current {
  color: var(--acc);
}

.tr-sub {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.tr-artist {
  font: 400 12px/1.2 var(--font-ui);
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tr-dot {
  width: 3px;
  height: 3px;
  border-radius: 2px;
  background: #3a424e;
  flex: none;
}

.tr-genre {
  font: 400 11.5px/1.2 var(--font-ui);
  color: #6b7480;
  white-space: nowrap;
  flex: none;
}

.tr-wave {
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

.tr-bars {
  display: flex;
  align-items: flex-end;
  gap: 2px;
  width: 100%;
  height: 26px;
}

.tr-bars span {
  flex: 1;
  min-width: 1px;
  background: #2b333e;
  border-radius: 1px;
}

.tr-wave-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  pointer-events: none;
}

.tr-bars-active span {
  background: var(--acc);
}

.tr-key {
  font: 600 12px/1 var(--font-mono);
  color: var(--key);
  text-align: center;
}

.tr-bpm {
  font: 500 12px/1 var(--font-mono);
  color: var(--txt-2);
  text-align: center;
}

.tr-time {
  font: 400 12px/1 var(--font-mono);
  color: var(--dim);
  text-align: center;
}

.tr-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 5px;
}

.tr-icon {
  background: none;
  border: none;
  padding: 0;
  margin: 0;
  cursor: pointer;
  width: 26px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 7px;
  color: var(--dim);
  transition: background .15s ease, color .15s ease;
}

.tr-fav {
  width: 28px;
}

.tr-fav:hover {
  background: rgba(255, 255, 255, .06);
}

.tr-fav-on {
  color: var(--acc);
}

.tr-remove:hover {
  background: rgba(255, 82, 102, .14);
  color: var(--danger);
}

.tr-more:hover {
  background: rgba(255, 255, 255, .06);
  color: var(--txt);
}

.tr-dl {
  width: 30px;
  height: 30px;
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

.tr-dl:hover {
  filter: brightness(1.15);
  color: var(--txt);
}

.tr-dl-saved {
  background: var(--acc-soft-strong);
  color: var(--acc);
}

.tr-dl-saved:hover {
  color: var(--acc);
}
</style>
