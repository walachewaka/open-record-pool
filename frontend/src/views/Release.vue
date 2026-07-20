<template>
  <section class="release">
    <button
      type="button"
      class="rl-back"
      @click="$router.push('/library')"
    >
      <svg
        width="15"
        height="15"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
      >
        <path d="M15 6l-6 6 6 6" />
      </svg>
      Back to library
    </button>

    <p
      v-if="errorMessage"
      class="rl-error"
    >
      {{ errorMessage }}
    </p>

    <template v-if="song">
      <div
        v-if="isSuperseded"
        class="rl-superseded"
      >
        Superseded — a better version of this recording is canonical.
        <router-link :to="`/release/${song.canonical_song_id}`">
          Open the canonical version
        </router-link>
      </div>
      <div class="rl-hero">
        <div
          class="rl-cover"
          :style="{background: tint}"
        >
          <img
            v-if="artOk"
            :src="artUrl"
            class="rl-cover-img"
            alt="Cover"
            @error="artOk = false"
          >
          <template v-else>
            {{ initials }}
          </template>
        </div>
        <div class="rl-info">
          <div
            v-if="song.genre"
            class="rl-eyebrow"
          >
            {{ song.genre }}
          </div>
          <h1 class="rl-title">
            {{ song.title || 'Untitled' }}
          </h1>
          <div class="rl-artist">
            {{ song.artist || 'Unknown artist' }}
          </div>
          <div class="rl-chips">
            <span
              v-if="keyLabel"
              class="rl-chip rl-chip-key"
            >KEY {{ keyLabel }}</span>
            <span
              v-if="song.bpm != null"
              class="rl-chip"
            >{{ Math.round(song.bpm) }} BPM</span>
            <span class="rl-chip">{{ durationLabel }}</span>
            <span
              v-if="loudnessLabel"
              class="rl-chip"
              title="Integrated loudness (EBU R128)"
            >{{ loudnessLabel }}</span>
            <span
              v-if="hasMismatch"
              class="rl-chip rl-chip-mismatch"
              title="The file's tags disagree with the audio analysis"
            >TAG/ANALYSIS MISMATCH</span>
            <span class="rl-added">
              Added {{ addedLabel }} · {{ song.download_count }} downloads · {{ song.play_count }} plays
            </span>
          </div>
          <div
            v-if="detectedLabel"
            class="rl-detected"
          >
            detected: {{ detectedLabel }}
          </div>
          <div
            v-if="song.tags.length"
            class="rl-tags"
          >
            <span class="rl-tags-label">TAGS</span>
            <span
              v-for="tag in song.tags"
              :key="tag"
              class="rl-tag"
            >{{ tag }}</span>
          </div>
          <div class="rl-actions">
            <button
              type="button"
              class="rl-play"
              @click="togglePreview"
            >
              <svg
                v-if="isPlaying"
                width="18"
                height="18"
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
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="currentColor"
              >
                <path d="M8 5v14l11-7z" />
              </svg>
              {{ isPlaying ? 'Pause' : 'Play preview' }}
            </button>
            <button
              type="button"
              class="rl-fav"
              :class="{'rl-fav-on': isFavorite}"
              title="Favorite"
              @click="onToggleFavorite"
            >
              <svg
                width="19"
                height="19"
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
            <span class="rl-divider" />
            <select
              v-model="djTarget"
              class="rl-dj-select"
              title="DJ software"
            >
              <option
                v-for="target in djTargets"
                :key="target"
                :value="target"
              >
                {{ target }}
              </option>
            </select>
            <button
              type="button"
              class="rl-dj-send"
              title="Cue in your DJ software"
              @click="sendToDj"
            >
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
                <path d="M5 4l14 8-14 8z" />
              </svg>
              Send to DJ
            </button>
            <button
              type="button"
              class="rl-dj-send"
              title="Suggest a metadata fix to the curators"
              @click="openSuggest"
            >
              Suggest an edit
            </button>
          </div>
        </div>
      </div>

      <button
        type="button"
        class="rl-wave"
        title="Seek"
        @click="onWaveClick"
      >
        <div class="rl-bars">
          <span
            v-for="(height, index) in wave"
            :key="index"
            :style="{height: height}"
          />
        </div>
        <div
          v-if="isCurrent"
          class="rl-wave-played"
          :style="{clipPath: playedClip}"
        >
          <div class="rl-bars rl-bars-acc">
            <span
              v-for="(height, index) in wave"
              :key="index"
              :style="{height: height}"
            />
          </div>
        </div>
      </button>

      <div class="rl-section-label">
        VERSIONS &amp; FORMATS
      </div>
      <div class="rl-versions">
        <div class="rl-versions-head">
          <span>Version</span>
          <span>Format</span>
          <span class="rl-vh-c">Size</span>
          <span class="rl-vh-r">Get</span>
        </div>
        <div
          v-for="version in song.versions"
          :key="version.id"
          class="rl-version-row"
        >
          <div class="rl-version-name">
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
            <span>{{ version.version }}</span>
          </div>
          <div class="rl-version-fmt">
            {{ formatLabel(version) }}
          </div>
          <div class="rl-version-size">
            {{ sizeLabel(version) }}
          </div>
          <div class="rl-version-get">
            <button
              type="button"
              class="rl-get"
              :class="{'rl-get-saved': saved}"
              :title="saved ? 'Saved' : 'Download'"
              @click="download(version)"
            >
              <svg
                width="14"
                height="14"
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
              Get
            </button>
          </div>
        </div>
      </div>

      <template v-if="related.length">
        <div class="rl-section-label">
          MORE IN {{ song.genre.toUpperCase() }}
        </div>
        <div class="rl-related">
          <div
            v-for="track in related"
            :key="track.id"
            class="rl-card"
          >
            <button
              type="button"
              class="rl-card-cover"
              :style="{background: trackTint(track)}"
              title="Play / pause"
              @click="toggleTrack(track)"
            >
              <span class="rl-card-initials">{{ trackInitials(track) }}</span>
              <span class="rl-card-play">
                <svg
                  v-if="isTrackPlaying(track)"
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
            <div class="rl-card-meta">
              <button
                type="button"
                class="rl-card-title"
                :title="track.title || ''"
                @click="$router.push(`/release/${track.id}`)"
              >
                {{ track.title || 'Untitled' }}
              </button>
              <div class="rl-card-artist">
                {{ track.artist || 'Unknown artist' }}
              </div>
            </div>
          </div>
        </div>
      </template>
    </template>

    <!-- Suggest an edit (member tag proposal) -->
    <div
      v-if="suggest.open"
      class="rl-modal-backdrop"
      @click="suggest.open = false"
    >
      <div
        class="rl-modal"
        @click.stop
      >
        <div class="rl-modal-head">
          <div class="rl-modal-title">
            Suggest an edit
          </div>
          <button
            type="button"
            class="rl-x"
            @click="suggest.open = false"
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
        <div class="rl-modal-body">
          <div class="rl-modal-grid">
            <div
              v-for="field in suggestFields"
              :key="field.key"
              :class="{'rl-span-2': field.wide}"
            >
              <label class="rl-label">{{ field.label }}</label>
              <input
                v-model="suggest.fields[field.key]"
                :type="field.type || 'text'"
              >
            </div>
            <div class="rl-span-2">
              <label class="rl-label">NOTE (OPTIONAL)</label>
              <input
                v-model="suggest.note"
                type="text"
                placeholder="Where did you get this from?"
              >
            </div>
          </div>
          <div class="rl-modal-note">
            Only the fields you change are sent to the curators for review.
          </div>
        </div>
        <div class="rl-modal-foot">
          <button
            type="button"
            class="rl-cancel"
            @click="suggest.open = false"
          >
            Cancel
          </button>
          <button
            type="button"
            class="rl-play rl-submit"
            :disabled="suggest.busy"
            @click="submitSuggestion"
          >
            {{ suggest.busy ? 'Sending…' : 'Send suggestion' }}
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
import { toast } from '@/utils/toast';
import { fetchPeaks, peaksToBars, waveBars } from '@/utils/waveform';

const DJ_TARGETS = ['Serato DJ', 'rekordbox', 'Traktor Pro', 'Engine DJ'];

// The fields a member may propose an edit for (MOO-82).
const SUGGEST_FIELDS = [
  {key: 'title', label: 'TITLE', wide: true},
  {key: 'artist', label: 'ARTIST', wide: true},
  {key: 'album', label: 'ALBUM', wide: true},
  {key: 'genre', label: 'GENRE'},
  {key: 'year', label: 'YEAR', type: 'number'},
  {key: 'bpm', label: 'BPM', type: 'number'},
  {key: 'musical_key', label: 'KEY'},
];

const NUMERIC_SUGGEST_FIELDS = ['year', 'bpm'];

export default {
  name: 'ReleaseView',
  data() {
    return {
      song: null,
      related: [],
      djTarget: DJ_TARGETS[0],
      djTargets: DJ_TARGETS,
      errorMessage: '',
      // Analyzer facts (MOO-87): real waveform peaks + the analysis row.
      realPeaks: null,
      analysis: null,
      // Cover art (MOO-82): the member song shape carries no "has art" flag,
      // so the <img> is rendered optimistically and falls back on 404.
      artOk: true,
      suggestFields: SUGGEST_FIELDS,
      suggest: {open: false, busy: false, note: '', fields: {}},
    };
  },
  computed: {
    ...mapGetters({
      currentSong: 'stateSong',
      playing: 'statePlaying',
      progress: 'stateProgress',
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
      const override = this.favOverrides[this.song.id];
      return override === undefined ? !!this.song.is_favorite : override;
    },
    saved() {
      return this.downloadedIds.includes(this.song.id);
    },
    isSuperseded() {
      // Superseded versions are 404s for members (MOO-90); only admins
      // auditioning a losing version ever see this banner.
      return !!this.song
        && this.song.canonical_song_id != null
        && this.song.canonical_song_id !== this.song.id;
    },
    initials() {
      return this.trackInitials(this.song);
    },
    tint() {
      return this.trackTint(this.song);
    },
    artUrl() {
      return `${axios.defaults.baseURL}/songs/${this.song.id}/artwork`;
    },
    wave() {
      return this.realPeaks
        ? peaksToBars(this.realPeaks)
        : waveBars(this.song.id);
    },
    playedClip() {
      return `inset(0 ${100 - this.progress * 100}% 0 0)`;
    },
    keyLabel() {
      return this.song.camelot_key || this.song.musical_key || '';
    },
    loudnessLabel() {
      const lufs = this.analysis && this.analysis.loudness_lufs;
      return lufs == null ? '' : `${lufs.toFixed(1)} LUFS`;
    },
    hasMismatch() {
      return !!this.analysis
        && (this.analysis.bpm_mismatch || this.analysis.key_mismatch);
    },
    detectedLabel() {
      // Provenance line (MOO-87 D5): shown only when the analyzer detected
      // something different from what the (coalesced) chips display.
      if (!this.analysis) {
        return '';
      }
      const parts = [];
      const bpm = this.analysis.bpm_detected;
      if (bpm != null && this.song.bpm != null
          && Math.round(bpm) !== Math.round(this.song.bpm)) {
        parts.push(`${bpm.toFixed(1)} BPM`);
      }
      const key = this.analysis.key_detected;
      if (key && this.song.musical_key && key !== this.song.musical_key) {
        parts.push(key);
      }
      return parts.join(' / ');
    },
    durationLabel() {
      const seconds = this.song.duration_seconds;
      if (seconds == null) {
        return '—';
      }
      const total = Math.round(seconds);
      return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
    },
    addedLabel() {
      if (!this.song.created_at) {
        return '—';
      }
      return new Date(this.song.created_at).toLocaleDateString('en', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      });
    },
  },
  watch: {
    // Related-track clicks navigate to this same route with a new id.
    '$route.params.id'(id) {
      if (id && this.$route.name === 'Release') {
        this.fetchRelease(id);
      }
    },
  },
  created() {
    return this.fetchRelease(this.$route.params.id);
  },
  methods: {
    ...mapActions(['playSong', 'togglePlayback', 'toggleFavorite', 'requestSeek']),
    async fetchRelease(id) {
      this.errorMessage = '';
      try {
        const {data} = await axios.get(`songs/${id}`);
        this.song = data;
        this.realPeaks = null;
        this.analysis = null;
        this.artOk = true;
        // Analyzer facts (MOO-87), both best-effort: seeded bars and plain
        // chips are the fallbacks, errors are deliberately ignored.
        fetchPeaks(data).then((peaks) => {
          if (this.song && this.song.id === data.id) {
            this.realPeaks = peaks;
          }
        });
        axios.get(`songs/${data.id}/analysis`)
          .then((response) => {
            if (this.song && this.song.id === data.id) {
              this.analysis = response.data;
            }
          })
          .catch(() => {});
        await this.fetchRelated();
      } catch (error) {
        const status = error.response && error.response.status;
        this.song = null;
        this.related = [];
        this.errorMessage =
          status === 404 ? 'This release no longer exists.' : 'Could not load the release.';
      }
    },
    async fetchRelated() {
      if (!this.song.genre) {
        this.related = [];
        return;
      }
      try {
        const {data} = await axios.get('songs', {
          params: {
            genre: this.song.genre,
            sort: 'created_at',
            order: 'desc',
            page_size: 7,
          },
        });
        this.related = data.items
          .filter(track => track.id !== this.song.id)
          .slice(0, 6);
      } catch (error) {
        this.related = [];
      }
    },
    togglePreview() {
      if (this.isCurrent) {
        this.togglePlayback();
      } else {
        this.playSong(this.song);
      }
    },
    onWaveClick(event) {
      if (!this.isCurrent) {
        this.playSong(this.song);
        return;
      }
      const rect = event.currentTarget.getBoundingClientRect();
      const fraction = Math.min(
        1,
        Math.max(0, (event.clientX - rect.left) / rect.width)
      );
      this.requestSeek(fraction);
    },
    async onToggleFavorite() {
      try {
        await this.toggleFavorite(this.song);
      } catch (error) {
        // Leave the heart untouched; the axios interceptor already handles
        // an expired session.
      }
    },
    openSuggest() {
      const fields = {};
      SUGGEST_FIELDS.forEach(({key}) => {
        const value = this.song[key];
        fields[key] = value == null ? '' : value;
      });
      this.suggest = {open: true, busy: false, note: '', fields};
    },
    async submitSuggestion() {
      const changes = {};
      SUGGEST_FIELDS.forEach(({key}) => {
        const raw = String(this.suggest.fields[key] || '').trim();
        const current = this.song[key] == null ? '' : String(this.song[key]);
        if (raw && raw !== current) {
          changes[key] = NUMERIC_SUGGEST_FIELDS.includes(key) ? Number(raw) : raw;
        }
      });
      if (!Object.keys(changes).length) {
        toast('Change at least one field first.', 'warn');
        return;
      }
      this.suggest.busy = true;
      try {
        await axios.post(`songs/${this.song.id}/tag-proposals`, {
          changes,
          note: this.suggest.note.trim() || undefined,
        });
        this.suggest.open = false;
        toast('Suggestion sent for review');
      } catch (error) {
        const status = error.response && error.response.status;
        if (status === 429) {
          // The axios interceptor already toasted the rate-limit message.
          return;
        }
        const detail = error.response && error.response.data && error.response.data.detail;
        toast(
          status === 409
            ? (detail || 'You already have a pending suggestion for this track.')
            : ((typeof detail === 'string' && detail) || 'Could not send the suggestion.'),
          'warn'
        );
      } finally {
        this.suggest.busy = false;
      }
    },
    sendToDj() {
      // Still UI-only: a single-track push needs a local bridge to the DJ
      // software, which does not exist. Crate export (MOO-86) is the real path
      // onto a stick, so point at it instead of dead-ending.
      toast(
        `Add this track to a crate, then use "Export for DJ" on the crate to get a ${this.djTarget}-ready USB bundle`,
        'info'
      );
    },
    formatLabel(version) {
      const format = version.format.toUpperCase();
      return version.bitrate_kbps ? `${format} ${version.bitrate_kbps}` : format;
    },
    sizeLabel(version) {
      const bytes = version.file_size_bytes;
      return bytes == null ? '—' : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    },
    download(version) {
      // The API lists formats display-cased ("MP3"); the download endpoint
      // expects them lowercase.
      downloadSong(this.song, version.format.toLowerCase());
    },
    trackInitials(track) {
      const source = track.title || track.artist || '?';
      const words = source.trim().split(/\s+/);
      const letters = words.length > 1
        ? words[0][0] + words[1][0]
        : source.slice(0, 2);
      return letters.toUpperCase();
    },
    trackTint(track) {
      return `var(--tint-${(track.id % 10) + 1})`;
    },
    isTrackPlaying(track) {
      return !!this.currentSong && this.currentSong.id === track.id && this.playing;
    },
    toggleTrack(track) {
      if (this.currentSong && this.currentSong.id === track.id) {
        this.togglePlayback();
      } else {
        this.playSong(track);
      }
    },
  },
};
</script>

<style scoped>
.release {
  max-width: 1040px;
}

.rl-back {
  display: flex;
  align-items: center;
  gap: 7px;
  background: none;
  border: none;
  padding: 0;
  margin: 0 0 20px;
  cursor: pointer;
  color: var(--muted);
  font: 500 12.5px var(--font-ui);
  transition: color .15s ease;
}

.rl-back:hover {
  color: var(--txt);
}

.rl-error {
  font: 400 13px var(--font-ui);
  color: var(--danger);
  margin: 0 0 12px;
}

/* Admin-only banner on a superseded version (MOO-90). */
.rl-superseded {
  margin: 0 0 14px;
  padding: 10px 14px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, .1);
  background: rgba(255, 255, 255, .04);
  font: 400 12.5px var(--font-ui);
  color: var(--muted);
}

.rl-superseded a {
  color: var(--acc);
  text-decoration: none;
  margin-left: 4px;
}

.rl-superseded a:hover {
  text-decoration: underline;
}

.rl-hero {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
  margin-bottom: 26px;
}

.rl-cover {
  width: 170px;
  height: 170px;
  border-radius: 16px;
  flex: none;
  box-shadow: 0 12px 40px rgba(0, 0, 0, .45), var(--shadow-cover);
  display: flex;
  align-items: center;
  justify-content: center;
  font: 600 30px var(--font-mono);
  color: rgba(255, 255, 255, .7);
}

.rl-cover-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 16px;
  display: block;
}

.rl-info {
  flex: 1;
  min-width: 280px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.rl-eyebrow {
  font: 600 11px var(--font-mono);
  letter-spacing: .1em;
  color: var(--acc);
  margin-bottom: 8px;
}

.rl-title {
  font: 700 30px/1.05 var(--font-disp);
  margin: 0 0 6px;
}

.rl-artist {
  font: 400 16px var(--font-ui);
  color: var(--txt-3);
  margin-bottom: 16px;
}

.rl-chips {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 20px;
}

.rl-chip {
  display: flex;
  align-items: center;
  padding: 6px 11px;
  border-radius: 8px;
  background: rgba(255, 255, 255, .05);
  border: 1px solid rgba(255, 255, 255, .09);
  font: 600 12px var(--font-mono);
  color: var(--txt-2);
}

.rl-chip-key {
  background: rgba(157, 139, 255, .12);
  border-color: rgba(157, 139, 255, .28);
  color: var(--key-bright);
}

.rl-chip-mismatch {
  border-color: var(--danger);
  color: var(--danger);
  background: rgba(255, 82, 102, .08);
}

.rl-detected {
  font: 500 11.5px var(--font-mono);
  color: var(--dim);
  margin: -12px 0 16px;
}

.rl-added {
  font: 400 12px var(--font-ui);
  color: var(--dim);
  margin-left: 4px;
}

.rl-tags {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
  margin-bottom: 20px;
}

.rl-tags-label {
  font: 600 10px var(--font-mono);
  letter-spacing: .06em;
  color: var(--dim-2);
  margin-right: 2px;
}

.rl-tag {
  padding: 4px 10px;
  border-radius: var(--r-pill);
  background: rgba(255, 255, 255, .05);
  border: 1px solid rgba(255, 255, 255, .09);
  font: 500 11.5px var(--font-ui);
  color: var(--txt-3);
}

.rl-actions {
  display: flex;
  align-items: center;
  gap: 11px;
  flex-wrap: wrap;
}

.rl-play {
  height: 44px;
  padding: 0 20px;
  border-radius: 10px;
  border: none;
  cursor: pointer;
  background: var(--acc);
  color: var(--acc-ink);
  font: 600 14px var(--font-ui);
  display: flex;
  align-items: center;
  gap: 9px;
  transition: filter .15s ease;
}

.rl-play:hover {
  filter: brightness(1.1);
}

.rl-fav {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  border: 1px solid var(--line-strong);
  background: rgba(255, 255, 255, .03);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--muted);
  transition: border-color .15s ease, color .15s ease;
}

.rl-fav:hover {
  border-color: rgba(255, 255, 255, .24);
}

.rl-fav-on {
  color: var(--acc);
}

.rl-divider {
  width: 1px;
  height: 28px;
  background: var(--line-strong);
  margin: 0 3px;
}

.rl-dj-select {
  height: 44px;
  padding: 0 12px;
  border-radius: 10px;
  border: 1px solid var(--line-strong);
  background: var(--menu);
  color: var(--txt-2);
  font: 500 12.5px var(--font-ui);
  cursor: pointer;
}

.rl-dj-select:focus {
  outline: none;
  border-color: var(--acc-border);
}

.rl-dj-send {
  height: 44px;
  padding: 0 16px;
  border-radius: 10px;
  border: 1px solid var(--line-strong);
  background: rgba(255, 255, 255, .03);
  color: var(--txt-2);
  font: 600 13px var(--font-ui);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: border-color .15s ease, color .15s ease;
}

.rl-dj-send:hover {
  border-color: var(--acc-border);
  color: var(--acc);
}

.rl-wave {
  position: relative;
  width: 100%;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 26px;
  cursor: pointer;
  display: block;
}

.rl-bars {
  display: flex;
  align-items: flex-end;
  gap: 2px;
  width: 100%;
  height: 64px;
}

.rl-bars span {
  flex: 1;
  min-width: 1px;
  background: #2b333e;
  border-radius: 1px;
  pointer-events: none;
}

.rl-wave-played {
  position: absolute;
  left: 16px;
  right: 16px;
  top: 16px;
  bottom: 16px;
  overflow: hidden;
  pointer-events: none;
}

.rl-bars-acc span {
  background: var(--acc);
}

.rl-section-label {
  font: 600 11px var(--font-mono);
  letter-spacing: .1em;
  color: var(--dim-2);
  margin-bottom: 12px;
}

.rl-versions {
  border: 1px solid var(--line);
  border-radius: 13px;
  overflow: hidden;
  background: var(--panel);
  margin-bottom: 28px;
}

.rl-versions-head {
  display: grid;
  grid-template-columns: 1fr 150px 110px 150px;
  align-items: center;
  gap: 12px;
  height: 38px;
  padding: 0 16px;
  border-bottom: 1px solid rgba(255, 255, 255, .07);
  font: 600 10px var(--font-mono);
  letter-spacing: .08em;
  color: var(--dim-2);
  text-transform: uppercase;
}

.rl-vh-c {
  text-align: center;
}

.rl-vh-r {
  text-align: right;
  padding-right: 24px;
}

.rl-version-row {
  display: grid;
  grid-template-columns: 1fr 150px 110px 150px;
  align-items: center;
  gap: 12px;
  height: 52px;
  padding: 0 16px;
  border-bottom: 1px solid rgba(255, 255, 255, .045);
  transition: background .15s ease;
}

.rl-version-row:last-child {
  border-bottom: none;
}

.rl-version-row:hover {
  background: rgba(255, 255, 255, .03);
}

.rl-version-name {
  display: flex;
  align-items: center;
  gap: 10px;
  font: 500 13.5px var(--font-ui);
  color: var(--txt);
}

.rl-version-name svg {
  color: var(--dim-2);
  flex: none;
}

.rl-version-fmt {
  font: 600 12px var(--font-mono);
  color: var(--txt-3);
}

.rl-version-size {
  font: 400 12px var(--font-mono);
  color: var(--dim);
  text-align: center;
}

.rl-version-get {
  display: flex;
  justify-content: flex-end;
}

.rl-get {
  height: 34px;
  padding: 0 16px;
  border-radius: 8px;
  border: 1px solid var(--line-strong);
  background: rgba(255, 255, 255, .04);
  color: var(--txt);
  font: 600 12px var(--font-ui);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 7px;
  transition: border-color .15s ease, color .15s ease;
}

.rl-get:hover {
  border-color: var(--acc-border);
  color: var(--acc);
}

.rl-get-saved {
  background: var(--acc-soft-strong);
  border-color: var(--acc-border);
  color: var(--acc);
}

.rl-related {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 14px;
}

.rl-card {
  display: flex;
  flex-direction: column;
  gap: 9px;
}

.rl-card-cover {
  position: relative;
  width: 100%;
  aspect-ratio: 1;
  border-radius: 12px;
  border: none;
  padding: 0;
  margin: 0;
  cursor: pointer;
  box-shadow: var(--shadow-cover);
  overflow: hidden;
  transition: filter .15s ease;
}

.rl-card-cover:hover {
  filter: brightness(1.06);
}

.rl-card-initials {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font: 600 16px var(--font-mono);
  color: rgba(255, 255, 255, .62);
}

.rl-card-play {
  position: absolute;
  right: 9px;
  bottom: 9px;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: var(--acc);
  color: var(--acc-ink);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 12px rgba(0, 0, 0, .4);
}

.rl-card-meta {
  min-width: 0;
}

.rl-card-title {
  background: none;
  border: none;
  padding: 0;
  margin: 0;
  cursor: pointer;
  display: block;
  font: 600 13px/1.25 var(--font-ui);
  color: var(--txt);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: left;
  max-width: 100%;
}

.rl-card-title:hover {
  color: var(--acc);
}

.rl-card-artist {
  font: 400 12px var(--font-ui);
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Suggest-an-edit modal */

.rl-modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(4, 7, 11, .6);
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.rl-modal {
  width: 520px;
  max-width: 100%;
  max-height: 88vh;
  overflow-y: auto;
  background: var(--modal);
  border: 1px solid var(--line-strong);
  border-radius: var(--r-modal);
  box-shadow: 0 30px 80px rgba(0, 0, 0, .6);
}

.rl-modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 22px;
  border-bottom: 1px solid rgba(255, 255, 255, .07);
}

.rl-modal-title {
  font: 700 16px var(--font-disp);
}

.rl-x {
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
}

.rl-x:hover {
  background: rgba(255, 255, 255, .06);
  color: var(--txt);
}

.rl-modal-body {
  padding: 22px;
}

.rl-modal-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.rl-span-2 {
  grid-column: 1 / -1;
}

.rl-label {
  display: block;
  font: 600 11px var(--font-mono);
  letter-spacing: .06em;
  color: var(--muted);
  margin-bottom: 7px;
}

.rl-modal input {
  width: 100%;
  height: 40px;
  padding: 0 12px;
  border-radius: var(--r-ctl);
  border: 1px solid rgba(255, 255, 255, .12);
  background: var(--sunken);
  color: var(--txt);
  font: 400 13.5px var(--font-ui);
  box-sizing: border-box;
}

.rl-modal input:focus {
  outline: none;
  border-color: var(--acc-border);
}

.rl-modal-note {
  margin-top: 16px;
  font: 400 12px/1.5 var(--font-ui);
  color: var(--dim);
}

.rl-modal-foot {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  padding: 16px 22px;
  border-top: 1px solid rgba(255, 255, 255, .07);
}

.rl-cancel {
  height: 40px;
  padding: 0 16px;
  border-radius: var(--r-ctl);
  border: 1px solid rgba(255, 255, 255, .12);
  background: none;
  color: var(--txt-2);
  font: 600 13px var(--font-ui);
  cursor: pointer;
}

.rl-cancel:hover {
  color: var(--txt);
}

.rl-submit {
  height: 40px;
  padding: 0 18px;
  font: 600 13px var(--font-ui);
}

.rl-submit:disabled {
  opacity: .5;
  cursor: default;
}
</style>
