<template>
  <footer class="player">
    <template v-if="song">
      <div class="pl-left">
        <div
          class="pl-cover"
          :style="{background: coverTint}"
        >
          {{ initials }}
        </div>
        <div class="pl-meta">
          <div class="pl-title">
            {{ song.title || 'Unknown title' }}
          </div>
          <div class="pl-artist">
            {{ song.artist || 'Unknown artist' }}
          </div>
        </div>
        <span
          v-if="playing"
          class="pl-eq"
        >
          <span
            v-for="(delay, index) in eqDelays"
            :key="index"
            :style="{animationDelay: delay + 's'}"
          />
        </span>
      </div>

      <div class="pl-center">
        <div class="pl-transport">
          <button
            type="button"
            class="pl-step"
            title="Previous"
            @click="step(-1)"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="currentColor"
            >
              <path d="M8 12l10-7v14z" />
              <rect
                x="5"
                y="5"
                width="2.4"
                height="14"
                rx="1"
              />
            </svg>
          </button>
          <button
            type="button"
            class="pl-play"
            title="Play / pause"
            @click="toggleAudio"
          >
            <svg
              v-if="playing"
              width="17"
              height="17"
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
              width="17"
              height="17"
              viewBox="0 0 24 24"
              fill="currentColor"
            >
              <path d="M8 5v14l11-7z" />
            </svg>
          </button>
          <button
            type="button"
            class="pl-step"
            title="Next"
            @click="step(1)"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="currentColor"
            >
              <path d="M16 12L6 5v14z" />
              <rect
                x="16.6"
                y="5"
                width="2.4"
                height="14"
                rx="1"
              />
            </svg>
          </button>
        </div>
        <div class="pl-progress">
          <span class="pl-time">{{ currentTimeLabel }}</span>
          <button
            type="button"
            class="pl-wave"
            title="Seek"
            @click="onSeek"
          >
            <div class="pl-bars">
              <span
                v-for="(height, index) in wave"
                :key="index"
                :style="{height: height}"
              />
            </div>
            <div
              class="pl-played"
              :style="{clipPath: playedClip}"
            >
              <div class="pl-bars pl-bars-acc">
                <span
                  v-for="(height, index) in wave"
                  :key="index"
                  :style="{height: height}"
                />
              </div>
            </div>
          </button>
          <span class="pl-time pl-time-end">{{ durationLabel }}</span>
        </div>
      </div>

      <div class="pl-right">
        <button
          type="button"
          class="pl-fav"
          :class="{'pl-fav-on': isFavorite}"
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
        <select
          v-model="format"
          class="pl-format"
          title="Format"
        >
          <option value="mp3">
            MP3
          </option>
        </select>
        <button
          type="button"
          class="pl-get"
          title="Download selected"
          @click="getCurrent"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.1"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M12 3v12" />
            <path d="M7 11l5 5 5-5" />
            <path d="M4 20h16" />
          </svg>
          Get
        </button>
        <span class="pl-vol">
          <svg
            width="17"
            height="17"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M4 9v6h3.5L13 19V5L7.5 9H4z" />
            <path d="M16.5 8.5a4.5 4.5 0 0 1 0 7" />
          </svg>
          <input
            type="range"
            min="0"
            max="100"
            :value="volumePct"
            title="Volume"
            @input="onVolume"
          >
        </span>
      </div>

      <audio
        ref="audio"
        class="pl-audio"
        :src="streamUrl"
        @play="onPlay"
        @pause="onPause"
        @timeupdate="onTimeUpdate"
        @ended="onEnded"
      />
    </template>
    <div
      v-else
      class="pl-empty"
    >
      Nothing playing — pick a track from the library
    </div>
  </footer>
</template>

<script>
import axios from 'axios';
import { mapActions, mapGetters } from 'vuex';

import { downloadSong } from '@/utils/download';
import { fetchPeaks, peaksToBars, waveBars } from '@/utils/waveform';

function formatTime(seconds) {
  const total = Math.max(0, Math.round(seconds || 0));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

export default {
  name: 'PlayerBar',
  data() {
    return {
      // Song id whose play event was already recorded, so resuming a
      // paused track doesn't count as another play (MOO-65).
      postedPlayId: null,
      currentTime: 0,
      // Duration reported by the <audio> element; falls back to the song's
      // tag metadata until playback provides the real value.
      mediaDuration: 0,
      volume: 0.8,
      format: 'mp3',
      // Staggered starts so the equalizer bars don't pulse in unison.
      eqDelays: [0, 0.22, 0.44, 0.15],
      // Analyzed waveform peaks (MOO-87); null keeps the seeded bars.
      realPeaks: null,
      // Last known playback position of the current track, for the telemetry
      // beacon (MOO-83). Cleared once the beacon is sent, so a track is never
      // reported twice.
      playback: null,
    };
  },
  computed: {
    ...mapGetters({
      song: 'stateSong',
      playing: 'statePlaying',
      queue: 'stateQueue',
      toggleRequests: 'stateToggleRequests',
      favOverrides: 'stateFavOverrides',
      seekRequest: 'stateSeek',
    }),
    streamUrl() {
      // axios.defaults.baseURL may or may not carry a trailing slash.
      const base = axios.defaults.baseURL.replace(/\/+$/, '');
      return `${base}/songs/${this.song.id}/stream`;
    },
    initials() {
      const source = this.song.title || this.song.artist || '?';
      const words = source.trim().split(/\s+/);
      const letters = words.length > 1
        ? words[0][0] + words[1][0]
        : source.slice(0, 2);
      return letters.toUpperCase();
    },
    coverTint() {
      return `var(--tint-${(this.song.id % 10) + 1})`;
    },
    wave() {
      return this.realPeaks
        ? peaksToBars(this.realPeaks)
        : waveBars(this.song.id);
    },
    duration() {
      return this.mediaDuration || this.song.duration_seconds || 0;
    },
    progress() {
      return this.duration ? Math.min(1, this.currentTime / this.duration) : 0;
    },
    playedClip() {
      return `inset(0 ${100 - this.progress * 100}% 0 0)`;
    },
    currentTimeLabel() {
      return formatTime(this.currentTime);
    },
    durationLabel() {
      return formatTime(this.duration);
    },
    isFavorite() {
      const override = this.favOverrides[this.song.id];
      return override === undefined ? !!this.song.is_favorite : override;
    },
    volumePct() {
      return Math.round(this.volume * 100);
    },
  },
  watch: {
    song(newSong) {
      // The previous track was replaced before it ended: that is a skip.
      this.sendBeacon(false);
      if (!newSong) {
        this.setPlaying(false);
        return;
      }
      // Analyzed waveform (MOO-87): swap in the real peaks when available.
      this.realPeaks = null;
      const songId = newSong.id;
      fetchPeaks(newSong).then((peaks) => {
        if (this.song && this.song.id === songId) {
          this.realPeaks = peaks;
        }
      });
      this.currentTime = 0;
      this.mediaDuration = 0;
      this.setProgress(0);
      // Wait for the src binding to settle before playing. Selecting the song
      // that is already loaded simply resumes it.
      this.$nextTick(() => {
        const audio = this.$refs.audio;
        if (audio) {
          audio.volume = this.volume;
          audio.play().catch(() => {
            // Autoplay may be blocked (e.g. on a restored session); the user
            // can still press play on the transport.
          });
        }
      });
    },
    toggleRequests() {
      this.toggleAudio();
    },
    seekRequest(request) {
      const audio = this.$refs.audio;
      if (!audio || !this.duration) {
        return;
      }
      audio.currentTime = request.fraction * this.duration;
      this.currentTime = audio.currentTime;
      this.setProgress(this.progress);
    },
  },
  mounted() {
    // The store is persisted across reloads but the <audio> element starts
    // paused, so any restored `playing` flag (and progress) is stale.
    this.setPlaying(false);
    this.setProgress(0);
    // A restored session skips the song watcher: resolve its peaks here.
    if (this.song) {
      const songId = this.song.id;
      fetchPeaks(this.song).then((peaks) => {
        if (this.song && this.song.id === songId) {
          this.realPeaks = peaks;
        }
      });
    }
    this.$nextTick(() => {
      const audio = this.$refs.audio;
      if (audio) {
        audio.volume = this.volume;
      }
    });
    window.addEventListener('keydown', this.onGlobalKey);
  },
  beforeUnmount() {
    window.removeEventListener('keydown', this.onGlobalKey);
    // A teardown mid-track (logout, navigation away) is a skip too.
    this.sendBeacon(false);
  },
  methods: {
    ...mapActions(['playSong', 'setPlaying', 'setProgress', 'toggleFavorite']),
    toggleAudio() {
      const audio = this.$refs.audio;
      if (!audio) {
        return;
      }
      if (audio.paused) {
        audio.play().catch(() => {});
      } else {
        audio.pause();
      }
    },
    onGlobalKey(event) {
      // Spacebar toggles play/pause — but never while typing in a field.
      if (event.code !== 'Space' || event.repeat) {
        return;
      }
      const target = event.target;
      const tag = target ? target.tagName : '';
      if (
        tag === 'INPUT' ||
        tag === 'TEXTAREA' ||
        tag === 'SELECT' ||
        (target && target.isContentEditable)
      ) {
        return;
      }
      event.preventDefault();
      this.toggleAudio();
    },
    onPlay() {
      this.setPlaying(true);
      if (this.song && this.song.id !== this.postedPlayId) {
        this.postedPlayId = this.song.id;
        // Fire-and-forget: play stats must never interrupt playback.
        axios.post(`songs/${this.song.id}/play`).catch(() => {});
      }
    },
    onPause() {
      this.setPlaying(false);
    },
    onTimeUpdate() {
      const audio = this.$refs.audio;
      if (!audio) {
        return;
      }
      this.currentTime = audio.currentTime;
      if (audio.duration && isFinite(audio.duration)) {
        this.mediaDuration = audio.duration;
      }
      this.setProgress(this.progress);
      // Keep the last known position for the telemetry beacon (MOO-83); the
      // beacon fires from a moment where the <audio> element has already moved
      // on to the next track.
      if (this.song && this.duration) {
        this.playback = {
          songId: this.song.id,
          positionMs: Math.round(this.currentTime * 1000),
          durationMs: Math.round(this.duration * 1000),
        };
      }
    },
    onEnded() {
      this.sendBeacon(true);
      this.step(1);
    },
    sendBeacon(ended) {
      // Telemetry beacon (MOO-83): the browser is the only place that knows how
      // far into a track we actually got, which is what separates a completed
      // play from a skip. Fire-and-forget: never toast, never block playback.
      const played = this.playback;
      this.playback = null;
      if (!played || !played.durationMs) {
        return;
      }
      axios.post('telemetry/beacon', {
        type: 'play.end',
        song_id: played.songId,
        position_ms: played.positionMs,
        duration_ms: played.durationMs,
        ended: !!ended,
      }).catch(() => {});
    },
    step(delta) {
      if (!this.song || !this.queue.length) {
        return;
      }
      const index = this.queue.findIndex(entry => entry.id === this.song.id);
      const nextSong =
        this.queue[(index + delta + this.queue.length) % this.queue.length];
      if (nextSong.id === this.song.id) {
        // Single-item queue: restart the track instead.
        const audio = this.$refs.audio;
        if (audio) {
          audio.currentTime = 0;
          audio.play().catch(() => {});
        }
        return;
      }
      this.playSong(nextSong);
    },
    onSeek(event) {
      const audio = this.$refs.audio;
      if (!audio || !this.duration) {
        return;
      }
      const rect = event.currentTarget.getBoundingClientRect();
      const fraction = Math.min(
        1,
        Math.max(0, (event.clientX - rect.left) / rect.width)
      );
      // The stream endpoint supports HTTP Range, so the element can jump
      // anywhere without downloading the whole file first.
      audio.currentTime = fraction * this.duration;
      this.currentTime = audio.currentTime;
      this.setProgress(this.progress);
    },
    onVolume(event) {
      this.volume = event.target.value / 100;
      const audio = this.$refs.audio;
      if (audio) {
        audio.volume = this.volume;
      }
    },
    async onToggleFavorite() {
      try {
        await this.toggleFavorite(this.song);
      } catch (error) {
        // Leave the heart untouched; the axios interceptor already handles
        // an expired session.
      }
    },
    getCurrent() {
      downloadSong(this.song, this.format);
    },
  },
};
</script>

<style scoped>
.player {
  height: var(--player-h);
  flex: none;
  display: grid;
  grid-template-columns: minmax(230px, 1fr) minmax(360px, 2.1fr) minmax(230px, 1fr);
  align-items: center;
  gap: 18px;
  padding: 0 20px;
  background: var(--panel);
  border-top: 1px solid rgba(255, 255, 255, .08);
}

.pl-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.pl-cover {
  width: 48px;
  height: 48px;
  border-radius: 8px;
  flex: none;
  box-shadow: var(--shadow-cover);
  display: flex;
  align-items: center;
  justify-content: center;
  font: 600 12px var(--font-mono);
  color: rgba(255, 255, 255, .72);
}

.pl-meta {
  min-width: 0;
}

.pl-title {
  font: 600 13.5px/1.25 var(--font-ui);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pl-artist {
  font: 400 12px/1.2 var(--font-ui);
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pl-eq {
  margin-left: auto;
  display: inline-flex;
  align-items: flex-end;
  gap: 2px;
  height: 15px;
  flex: none;
}

.pl-eq span {
  display: inline-block;
  width: 3px;
  height: 15px;
  border-radius: 2px;
  background: var(--acc);
  transform-origin: bottom;
  animation: eqp .9s ease-in-out infinite;
}

.pl-center {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.pl-transport {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
}

.pl-step {
  background: none;
  border: none;
  padding: 0;
  margin: 0;
  cursor: pointer;
  color: var(--muted);
  display: flex;
  transition: color .15s ease;
}

.pl-step:hover {
  color: var(--txt);
}

.pl-play {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  border: none;
  cursor: pointer;
  background: var(--acc);
  color: var(--acc-ink);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: filter .15s ease;
}

.pl-play:hover {
  filter: brightness(1.1);
}

.pl-progress {
  display: flex;
  align-items: center;
  gap: 10px;
}

.pl-time {
  font: 500 11px var(--font-mono);
  color: var(--dim);
  width: 34px;
  text-align: right;
  flex: none;
}

.pl-time-end {
  text-align: left;
}

.pl-wave {
  position: relative;
  flex: 1;
  background: none;
  border: none;
  padding: 0;
  margin: 0;
  cursor: pointer;
  height: 30px;
  display: flex;
  align-items: center;
  min-width: 0;
}

.pl-bars {
  display: flex;
  align-items: flex-end;
  gap: 2px;
  width: 100%;
  height: 24px;
}

.pl-bars span {
  flex: 1;
  min-width: 1px;
  background: #2b333e;
  border-radius: 1px;
  pointer-events: none;
}

.pl-played {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  overflow: hidden;
  pointer-events: none;
}

.pl-bars-acc span {
  background: var(--acc);
}

.pl-right {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  min-width: 0;
}

.pl-fav {
  background: none;
  border: none;
  padding: 0;
  margin: 0;
  cursor: pointer;
  width: 30px;
  height: 30px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 7px;
  color: var(--dim);
  transition: background .15s ease, color .15s ease;
}

.pl-fav:hover {
  background: rgba(255, 255, 255, .06);
}

.pl-fav-on {
  color: var(--acc);
}

.pl-format {
  height: 32px;
  padding: 0 8px;
  border-radius: 8px;
  border: 1px solid var(--line-strong);
  background: var(--raised);
  color: var(--txt-2);
  font: 500 11.5px var(--font-mono);
  cursor: pointer;
}

.pl-format:focus {
  outline: none;
  border-color: var(--acc-border);
}

.pl-get {
  height: 32px;
  padding: 0 12px;
  border-radius: 8px;
  border: none;
  cursor: pointer;
  background: var(--acc);
  color: var(--acc-ink);
  font: 600 12px var(--font-ui);
  display: flex;
  align-items: center;
  gap: 6px;
  transition: filter .15s ease;
}

.pl-get:hover {
  filter: brightness(1.1);
}

.pl-vol {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-left: 2px;
  color: var(--dim);
}

.pl-vol input {
  width: 74px;
  accent-color: var(--acc);
  cursor: pointer;
}

.pl-audio {
  display: none;
}

.pl-empty {
  grid-column: 1 / -1;
  text-align: center;
  font: 400 12.5px var(--font-ui);
  color: var(--dim-2);
}
</style>
