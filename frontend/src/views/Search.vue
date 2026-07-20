<template>
  <section>
    <p
      v-if="errorMessage"
      class="search-error"
    >
      {{ errorMessage }}
    </p>

    <div
      v-if="degraded && hasQuery"
      class="degraded-banner"
    >
      SEARCH ENGINE OFFLINE — showing database results; facets limited.
    </div>

    <div
      v-if="!hasQuery"
      class="search-start"
    >
      <div
        v-if="genres.length"
        class="search-label"
      >
        BROWSE BY GENRE
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
          @click="searchFor(genre)"
        >
          {{ genre }}
        </button>
      </div>

      <div class="search-label">
        SEARCH TIPS
      </div>
      <div class="tips">
        <div class="tip">
          <span class="tip-kbd">8A</span>
          Type a Camelot key to find harmonic matches
        </div>
        <div class="tip">
          <span class="tip-kbd">126</span>
          Search a BPM to find tracks that mix in tempo
        </div>
        <div class="tip">
          <span class="tip-kbd">↵</span>
          Combine with the genre, key &amp; BPM filters on the left
        </div>
      </div>
    </div>

    <div
      v-else
      class="search-layout"
    >
      <FacetPanel
        :facets="facets"
        :selection="selection"
        :degraded="degraded"
        @toggle-genre="toggleGenre"
        @set-key="value => setQueryParams({key: value})"
        @set-bpm="range => setQueryParams({bpm_min: range[0], bpm_max: range[1]})"
        @set-year="range => setQueryParams({year_min: range[0], year_max: range[1]})"
        @set-bitrate="value => setQueryParams({bitrate_min: value})"
        @set-source="value => setQueryParams({source: value})"
        @clear="clearFacets"
      />

      <div class="search-results">
        <div class="search-count-line">
          <span class="search-count">{{ totalLabel }} results<template v-if="q"> for “{{ q }}”</template></span>
          <span class="search-took">{{ tookMs }} ms</span>
        </div>
        <div
          class="loading-bar"
          :class="{'loading-on': loading}"
        />

        <div
          v-if="!loading && !songs.length"
          class="search-none"
        >
          <div class="search-none-title">
            No matches
          </div>
          <div class="search-none-sub">
            Try a different title, artist, genre, label, BPM or key — or clear
            some filters.
          </div>
        </div>

        <template v-else>
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
            <TrackRow
              v-for="song in songs"
              :key="song.id"
              :song="song"
            />
          </div>

          <div
            v-if="nextCursor"
            class="load-more-row"
          >
            <button
              type="button"
              class="load-more"
              :disabled="loadingMore"
              @click="loadMore"
            >
              {{ loadingMore ? 'Loading…' : 'Load more' }}
            </button>
          </div>
        </template>
      </div>
    </div>
  </section>
</template>

<script>
import axios from 'axios';
import { mapActions } from 'vuex';

import FacetPanel from '@/components/search/FacetPanel.vue';
import TrackRow from '@/components/TrackRow.vue';

const FACET_QUERY_KEYS = [
  'genre', 'key', 'bpm_min', 'bpm_max', 'year_min', 'year_max',
  'bitrate_min', 'source',
];

// The ES-backed instant Search view (MOO-79): results and facet counts
// update on every keystroke (the TopBar debounces ?q= at 300 ms) and every
// facet click. All state lives in the route query, so searches are
// shareable and back-button-safe.
export default {
  name: 'SearchView',
  components: {FacetPanel, TrackRow},
  data() {
    return {
      songs: [],
      genres: [],
      facets: {},
      total: 0,
      totalRelation: 'eq',
      tookMs: 0,
      degraded: false,
      nextCursor: null,
      loading: false,
      loadingMore: false,
      errorMessage: '',
      cancelSource: null,
    };
  },
  computed: {
    // The topbar search box owns the query; it routes here with ?q=.
    q() {
      return (this.$route.query.q || '').trim();
    },
    selection() {
      const query = this.$route.query;
      const genre = query.genre;
      return {
        genres: Array.isArray(genre) ? genre : (genre ? [genre] : []),
        key: query.key || '',
        bpmMin: query.bpm_min || '',
        bpmMax: query.bpm_max || '',
        yearMin: query.year_min || '',
        yearMax: query.year_max || '',
        bitrateMin: query.bitrate_min || '',
        source: query.source || '',
      };
    },
    anyFacetActive() {
      const sel = this.selection;
      return Boolean(
        sel.genres.length || sel.key || sel.bpmMin || sel.bpmMax ||
        sel.yearMin || sel.yearMax || sel.bitrateMin || sel.source,
      );
    },
    hasQuery() {
      return Boolean(this.q) || this.anyFacetActive;
    },
    totalLabel() {
      return this.totalRelation === 'gte'
        ? `${this.total.toLocaleString()}+`
        : String(this.total);
    },
  },
  watch: {
    // One watcher covers q and every facet param.
    '$route.query'() {
      if (this.$route.path === '/search') {
        this.fetchResults();
      }
    },
  },
  created() {
    this.fetchGenres();
    if (this.hasQuery) {
      return this.fetchResults();
    }
  },
  beforeUnmount() {
    if (this.cancelSource) {
      this.cancelSource.cancel('leaving search');
    }
  },
  methods: {
    ...mapActions(['setQueue']),
    buildParams(cursor) {
      // URLSearchParams so the repeatable `genre` facet serializes as
      // `genre=X&genre=Y` — axios 0.x would add brackets to a plain array.
      const params = new URLSearchParams();
      if (this.q) {
        params.set('q', this.q);
      }
      const sel = this.selection;
      sel.genres.forEach(genre => params.append('genre', genre));
      if (sel.key) {
        params.set('key', sel.key);
      }
      if (sel.bpmMin !== '') {
        params.set('bpm_min', sel.bpmMin);
      }
      if (sel.bpmMax !== '') {
        params.set('bpm_max', sel.bpmMax);
      }
      if (sel.yearMin !== '') {
        params.set('year_min', sel.yearMin);
      }
      if (sel.yearMax !== '') {
        params.set('year_max', sel.yearMax);
      }
      if (sel.bitrateMin !== '') {
        params.set('bitrate_min', sel.bitrateMin);
      }
      if (sel.source) {
        params.set('source', sel.source);
      }
      params.set('limit', 50);
      if (cursor) {
        params.set('cursor', cursor);
      }
      return params;
    },
    async fetchResults(cursor) {
      if (!this.hasQuery) {
        this.songs = [];
        this.facets = {};
        this.total = 0;
        this.nextCursor = null;
        return;
      }
      const append = Boolean(cursor);
      // Abort the in-flight request: a stale response must never overwrite
      // a newer one while typing.
      if (this.cancelSource) {
        this.cancelSource.cancel('superseded');
      }
      this.cancelSource = axios.CancelToken.source();
      if (append) {
        this.loadingMore = true;
      } else {
        this.loading = true;
      }
      this.errorMessage = '';
      try {
        const {data} = await axios.get('search', {
          params: this.buildParams(cursor),
          cancelToken: this.cancelSource.token,
        });
        this.songs = append ? this.songs.concat(data.items) : data.items;
        this.facets = data.facets || {};
        this.total = data.total;
        this.totalRelation = data.total_relation || 'eq';
        this.tookMs = data.took_ms || 0;
        this.degraded = Boolean(data.degraded);
        this.nextCursor = data.next_cursor;
        // The player's prev/next and auto-advance walk everything loaded.
        this.setQueue(this.songs);
        this.loading = false;
        this.loadingMore = false;
      } catch (error) {
        if (axios.isCancel(error)) {
          return; // a newer request owns the state now
        }
        const detail = error.response && error.response.data && error.response.data.detail;
        this.errorMessage =
          (typeof detail === 'string' && detail) ||
          'The search failed.';
        this.loading = false;
        this.loadingMore = false;
      }
    },
    loadMore() {
      if (this.nextCursor) {
        this.fetchResults(this.nextCursor);
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
    searchFor(text) {
      this.$router.push({path: '/search', query: {q: text}});
    },
    setQueryParams(changes) {
      const query = {...this.$route.query};
      Object.keys(changes).forEach(key => {
        const value = changes[key];
        if (value === '' || value === null || value === undefined ||
            (Array.isArray(value) && !value.length)) {
          delete query[key];
        } else {
          query[key] = value;
        }
      });
      // replace, not push: facet clicks shouldn't grow the history.
      this.$router.replace({path: '/search', query});
    },
    toggleGenre(value) {
      const current = this.selection.genres;
      const next = current.some(item => item.toLowerCase() === String(value).toLowerCase())
        ? current.filter(item => item.toLowerCase() !== String(value).toLowerCase())
        : current.concat([value]);
      this.setQueryParams({genre: next});
    },
    clearFacets() {
      const changes = {};
      FACET_QUERY_KEYS.forEach(key => {
        changes[key] = '';
      });
      this.setQueryParams(changes);
    },
  },
};
</script>

<style scoped>
.search-error {
  font: 400 12.5px var(--font-ui);
  color: var(--danger);
  margin: 0 0 12px;
}

.degraded-banner {
  border: 1px solid var(--acc-border);
  border-radius: var(--r-ctl);
  font: 500 12px var(--font-mono);
  color: var(--acc);
  padding: 8px 12px;
  margin-bottom: 14px;
}

.search-start {
  max-width: 640px;
}

.search-label {
  font: 600 11px var(--font-mono);
  letter-spacing: .1em;
  color: var(--dim-2);
  margin-bottom: 12px;
}

.chips {
  display: flex;
  gap: 7px;
  flex-wrap: wrap;
  margin-bottom: 26px;
}

.chip {
  padding: 7px 13px;
  border-radius: var(--r-pill);
  border: 1px solid var(--line-strong);
  background: rgba(255, 255, 255, .03);
  color: var(--txt-3);
  font: 500 12.5px var(--font-ui);
  cursor: pointer;
  transition: border-color .15s ease;
}

.chip:hover {
  border-color: rgba(255, 255, 255, .24);
}

.tips {
  display: flex;
  flex-direction: column;
  gap: 9px;
}

.tip {
  display: flex;
  align-items: center;
  gap: 11px;
  color: var(--muted);
  font: 400 13.5px var(--font-ui);
}

.tip-kbd {
  font: 600 11px var(--font-mono);
  color: var(--acc);
  border: 1px solid var(--acc-border);
  border-radius: 6px;
  padding: 3px 8px;
}

.search-layout {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.search-results {
  flex: 1;
  min-width: 0;
}

.search-none {
  padding: 70px 20px;
  text-align: center;
}

.search-none-title {
  font: 600 16px var(--font-disp);
  color: var(--txt-2);
  margin-bottom: 6px;
}

.search-none-sub {
  color: var(--dim-2);
  font: 400 13.5px var(--font-ui);
}

.search-count-line {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 6px;
}

.search-count {
  font: 600 15px var(--font-disp);
}

.search-took {
  font: 500 11px var(--font-mono);
  color: var(--dim-2);
}

.loading-bar {
  height: 2px;
  border-radius: 1px;
  background: transparent;
  margin-bottom: 8px;
  overflow: hidden;
  position: relative;
}

.loading-on {
  background: rgba(255, 255, 255, .06);
}

.loading-on::after {
  content: '';
  position: absolute;
  inset: 0;
  width: 40%;
  background: var(--acc);
  animation: loading-slide 1s linear infinite;
}

@keyframes loading-slide {
  from { transform: translateX(-100%); }
  to { transform: translateX(250%); }
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

.load-more-row {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}

.load-more {
  height: 32px;
  padding: 0 18px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line-strong);
  background: rgba(255, 255, 255, .03);
  color: var(--txt-2);
  font: 600 12px var(--font-ui);
  cursor: pointer;
  transition: border-color .15s ease, color .15s ease;
}

.load-more:hover:enabled {
  border-color: var(--acc-border);
  color: var(--txt);
}

.load-more:disabled {
  opacity: .45;
  cursor: default;
}
</style>
