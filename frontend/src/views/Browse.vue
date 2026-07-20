<template>
  <section>
    <div class="filters">
      <div class="fbox">
        <span class="fbox-icon">
          <svg
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.9"
            stroke-linecap="round"
          >
            <path d="M4 6h16M7 12h10M10 18h4" />
          </svg>
        </span>
        <span class="fbox-label">BPM</span>
        <input
          v-model="bpmMin"
          class="fbpm"
          type="number"
          min="0"
          placeholder="min"
          @input="onBpmInput"
        >
        <span class="fdash">–</span>
        <input
          v-model="bpmMax"
          class="fbpm"
          type="number"
          min="0"
          placeholder="max"
          @input="onBpmInput"
        >
      </div>

      <div class="fbox">
        <span class="fbox-label">KEY</span>
        <select
          v-model="key"
          class="fselect"
          @change="applyFilters"
        >
          <option value="">
            Any
          </option>
          <option
            v-for="camelot in camelotKeys"
            :key="camelot"
            :value="camelot"
          >
            {{ camelot }}
          </option>
        </select>
      </div>

      <div class="fbox">
        <span class="fbox-label">SORT</span>
        <select
          v-model="sortMode"
          class="fselect fselect-sans"
          @change="applyFilters"
        >
          <option value="newest">
            Newest
          </option>
          <option value="most_downloaded">
            Most downloaded
          </option>
          <option value="bpm">
            BPM ↑
          </option>
          <option value="genre">
            Genre
          </option>
          <option value="az">
            A–Z
          </option>
        </select>
      </div>

      <button
        type="button"
        class="freset"
        @click="reset"
      >
        Reset
      </button>

      <button
        v-if="canRescan"
        type="button"
        class="frescan"
        :disabled="rescanning"
        :title="rescanning ? 'Rescanning…' : 'Rescan the music folder'"
        @click="rescan"
      >
        <svg
          width="15"
          height="15"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.9"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d="M21 12a9 9 0 1 1-2.6-6.3" />
          <path d="M21 3v6h-6" />
        </svg>
      </button>

      <div class="fcount">
        {{ total }} tracks
      </div>
    </div>

    <div
      v-if="genres.length"
      class="chips"
    >
      <button
        v-for="genre in genres"
        :key="genre"
        type="button"
        class="chip"
        :class="{'chip-on': selGenres.includes(genre)}"
        @click="toggleGenre(genre)"
      >
        {{ genre }}
      </button>
    </div>

    <p
      v-if="errorMessage"
      class="browse-error"
    >
      {{ errorMessage }}
    </p>
    <p
      v-if="notice"
      class="browse-notice"
    >
      {{ notice }}
    </p>

    <div class="list-panel">
      <div class="list-head">
        <span />
        <span>Track</span>
        <span>Waveform</span>
        <span class="lh-c">Key</span>
        <span class="lh-c">BPM</span>
        <span class="lh-c">Time</span>
        <span class="lh-r">Get</span>
      </div>
      <div
        v-if="!loading && !songs.length"
        class="list-empty"
      >
        No tracks match those filters.
      </div>
      <TrackRow
        v-for="song in songs"
        :key="song.id"
        :song="song"
      />
    </div>

    <nav
      v-if="totalPages > 1"
      class="pager"
    >
      <button
        type="button"
        class="pager-btn"
        :disabled="page <= 1"
        @click="goToPage(page - 1)"
      >
        Previous
      </button>
      <span class="pager-info">Page {{ page }} of {{ totalPages }}</span>
      <button
        type="button"
        class="pager-btn"
        :disabled="page >= totalPages"
        @click="goToPage(page + 1)"
      >
        Next
      </button>
    </nav>
  </section>
</template>

<script>
import axios from 'axios';
import { mapActions, mapGetters } from 'vuex';

import TrackRow from '@/components/TrackRow.vue';
import { pollJob } from '@/utils/jobs';

const CAMELOT_KEYS = [];
for (let i = 1; i <= 12; i += 1) {
  CAMELOT_KEYS.push(`${i}A`, `${i}B`);
}

// Sort select options mapped to the backend's sort/order pair (MOO-65).
const SORT_PARAMS = {
  newest: {sort: 'created_at', order: 'desc'},
  most_downloaded: {sort: 'most_downloaded', order: 'desc'},
  bpm: {sort: 'bpm', order: 'asc'},
  genre: {sort: 'genre_title', order: 'asc'},
  az: {sort: 'title', order: 'asc'},
};

export default {
  name: 'BrowseView',
  components: {TrackRow},
  data() {
    return {
      songs: [],
      genres: [],
      total: 0,
      page: 1,
      pageSize: 50,
      bpmMin: '',
      bpmMax: '',
      key: '',
      sortMode: 'newest',
      selGenres: [],
      camelotKeys: CAMELOT_KEYS,
      loading: true,
      rescanning: false,
      notice: '',
      errorMessage: '',
      bpmDebounce: null,
    };
  },
  computed: {
    ...mapGetters(['userPermissions']),
    totalPages() {
      return Math.max(1, Math.ceil(this.total / this.pageSize));
    },
    // Rescanning is an instance-wide mutation gated by site_settings since
    // MOO-77 — hide the button from members the backend would 403 anyway.
    canRescan() {
      return !!this.userPermissions.site_settings;
    },
  },
  watch: {
    // The Home dashboard's genre chips and packs route here pre-filtered
    // (MOO-94); re-seed if the query changes while the view is mounted.
    '$route.query.genre'() {
      if (this.$route.path === '/library') {
        this.seedGenresFromRoute();
        this.applyFilters();
      }
    },
  },
  created() {
    this.seedGenresFromRoute();
    this.fetchGenres();
    return this.fetchSongs();
  },
  beforeUnmount() {
    clearTimeout(this.bpmDebounce);
  },
  methods: {
    ...mapActions(['setQueue']),
    seedGenresFromRoute() {
      const preset = this.$route.query.genre;
      if (preset) {
        this.selGenres = Array.isArray(preset) ? preset.slice() : [preset];
      }
    },
    async fetchSongs() {
      this.loading = true;
      this.errorMessage = '';
      try {
        // URLSearchParams so the repeatable `genre` filter serializes as
        // `genre=X&genre=Y` — axios 0.x would add brackets to a plain array.
        const params = new URLSearchParams();
        params.set('page', this.page);
        params.set('page_size', this.pageSize);
        const {sort, order} = SORT_PARAMS[this.sortMode];
        params.set('sort', sort);
        params.set('order', order);
        if (this.bpmMin !== '') {
          params.set('bpm_min', this.bpmMin);
        }
        if (this.bpmMax !== '') {
          params.set('bpm_max', this.bpmMax);
        }
        if (this.key) {
          params.set('key', this.key);
        }
        this.selGenres.forEach(genre => params.append('genre', genre));
        const {data} = await axios.get('songs', {params});
        this.songs = data.items;
        this.total = data.total;
        // The player's prev/next and auto-advance walk this list.
        this.setQueue(data.items);
      } catch (error) {
        const detail = error.response && error.response.data && error.response.data.detail;
        this.errorMessage =
          (typeof detail === 'string' && detail) ||
          'Could not load the track feed.';
      } finally {
        this.loading = false;
      }
    },
    async fetchGenres() {
      try {
        const {data} = await axios.get('songs/genres');
        this.genres = data;
      } catch (error) {
        // The chips row simply stays hidden.
        this.genres = [];
      }
    },
    applyFilters() {
      this.page = 1;
      this.fetchSongs();
    },
    onBpmInput() {
      clearTimeout(this.bpmDebounce);
      this.bpmDebounce = setTimeout(this.applyFilters, 350);
    },
    toggleGenre(genre) {
      const index = this.selGenres.indexOf(genre);
      if (index === -1) {
        this.selGenres.push(genre);
      } else {
        this.selGenres.splice(index, 1);
      }
      this.applyFilters();
    },
    reset() {
      this.bpmMin = '';
      this.bpmMax = '';
      this.key = '';
      this.sortMode = 'newest';
      this.selGenres = [];
      this.applyFilters();
    },
    goToPage(page) {
      this.page = page;
      this.fetchSongs();
    },
    async rescan() {
      this.rescanning = true;
      this.errorMessage = '';
      this.notice = '';
      try {
        // The scan is a background job since MOO-77: a 202 envelope. Inline
        // mode returns it already succeeded; otherwise poll until terminal
        // (the job detail route allows its creator, not just admins).
        const {data} = await axios.post('songs/extract');
        const job = data.status === 'succeeded' ? data : await pollJob(data.id);
        const result = job.result;
        this.notice =
          `Scanned ${result.files_parsed} files: ${result.songs_created} new, ` +
          `${result.songs_updated} updated, ${result.songs_deleted} removed, ` +
          `${result.duplicates_skipped} duplicates skipped.`;
        this.page = 1;
        await Promise.all([this.fetchSongs(), this.fetchGenres()]);
      } catch (error) {
        const detail = error.response && error.response.data && error.response.data.detail;
        this.errorMessage =
          (typeof detail === 'string' && detail) ||
          error.message ||
          'Rescanning the library failed.';
      } finally {
        this.rescanning = false;
      }
    },
  },
};
</script>

<style scoped>
.filters {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.fbox {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 38px;
  padding: 0 12px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line-strong);
  background: var(--raised);
  box-sizing: border-box;
}

.fbox-icon {
  color: var(--dim);
  display: flex;
}

.fbox-label {
  font: 600 11px var(--font-mono);
  color: var(--muted);
  letter-spacing: .04em;
}

.fbpm {
  width: 44px;
  height: 26px;
  border: none;
  background: none;
  color: var(--txt);
  font: 500 12px var(--font-mono);
  text-align: center;
  appearance: textfield;
  -moz-appearance: textfield;
}

.fbpm::-webkit-outer-spin-button,
.fbpm::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

.fbpm:focus {
  outline: none;
}

.fbpm::placeholder {
  color: var(--dim-2);
}

.fdash {
  color: var(--dim-2);
}

.fselect {
  height: 26px;
  border: none;
  background: none;
  color: var(--txt);
  font: 500 12px var(--font-mono);
  cursor: pointer;
}

.fselect option {
  background: var(--menu);
  color: var(--txt);
}

.fselect:focus {
  outline: none;
}

.fselect-sans {
  font: 500 12px var(--font-ui);
}

.freset {
  height: 38px;
  padding: 0 13px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line-strong);
  background: rgba(255, 255, 255, .03);
  color: var(--muted);
  font: 600 12px var(--font-ui);
  cursor: pointer;
  transition: color .15s ease;
}

.freset:hover {
  color: var(--txt);
}

/* Not in the design spec: kept from the old library view so the music
   folder can still be re-indexed before the admin console stage lands. */
.frescan {
  height: 38px;
  width: 38px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line-strong);
  background: rgba(255, 255, 255, .03);
  color: var(--muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color .15s ease, border-color .15s ease;
}

.frescan:hover:enabled {
  color: var(--txt);
  border-color: var(--acc-border);
}

.frescan:disabled {
  opacity: .55;
  cursor: default;
}

.fcount {
  margin-left: auto;
  font: 500 12px var(--font-mono);
  color: var(--dim);
}

.chips {
  display: flex;
  gap: 7px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.chip {
  padding: 6px 12px;
  border-radius: var(--r-pill);
  border: 1px solid var(--line-strong);
  background: rgba(255, 255, 255, .03);
  color: var(--txt-3);
  font: 500 12px var(--font-ui);
  cursor: pointer;
  transition: border-color .15s ease;
}

.chip:hover {
  border-color: rgba(255, 255, 255, .24);
}

.chip-on {
  background: var(--acc-soft-strong);
  color: var(--acc);
  border-color: color-mix(in oklab, var(--acc) 45%, transparent);
}

.browse-error {
  font: 400 12.5px var(--font-ui);
  color: var(--danger);
  margin: 0 0 12px;
}

.browse-notice {
  font: 400 12.5px var(--font-ui);
  color: var(--muted);
  margin: 0 0 12px;
}

.list-panel {
  border: 1px solid var(--line);
  border-radius: 13px;
  overflow: hidden;
  background: var(--panel);
}

.list-head {
  display: grid;
  grid-template-columns: 40px minmax(168px, 1.5fr) minmax(120px, 1.9fr) 40px 48px 46px 96px;
  align-items: center;
  gap: 10px;
  height: 36px;
  padding: 0 10px;
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
  padding-right: 4px;
}

.list-empty {
  padding: 56px 20px;
  text-align: center;
  color: var(--dim-2);
  font: 400 14px var(--font-ui);
}

.pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 16px;
}

.pager-btn {
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

.pager-btn:hover:enabled {
  border-color: var(--acc-border);
  color: var(--txt);
}

.pager-btn:disabled {
  opacity: .45;
  cursor: default;
}

.pager-info {
  font: 500 12px var(--font-mono);
  color: var(--dim);
}
</style>
