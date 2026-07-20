<template>
  <section>
    <p
      v-if="errorMessage"
      class="genres-error"
    >
      {{ errorMessage }}
    </p>

    <div
      v-if="stats.length"
      class="gtiles"
    >
      <button
        v-for="stat in stats"
        :key="stat.genre"
        type="button"
        class="gtile"
        :class="{'gtile-on': selected.includes(stat.genre)}"
        :style="{background: tint(stat.genre)}"
        @click="toggle(stat.genre)"
      >
        <div class="gtile-wave">
          <span style="height: 40%" />
          <span style="height: 80%" />
          <span style="height: 55%" />
          <span style="height: 100%" />
          <span style="height: 65%" />
        </div>
        <div class="gtile-name">
          {{ stat.genre }}
        </div>
        <div class="gtile-count">
          {{ stat.track_count }} tracks
        </div>
      </button>
    </div>
    <div
      v-else-if="!loading"
      class="genres-empty"
    >
      No genres in the library yet.
    </div>

    <template v-if="selected.length">
      <div class="gsel-head">
        <div class="gsel-title">
          {{ total }} tracks in your selection
        </div>
        <button
          type="button"
          class="gsel-clear"
          @click="clearSelection"
        >
          Clear selection
        </button>
      </div>

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
          v-if="!listLoading && !songs.length"
          class="list-empty"
        >
          No tracks in the selected genres.
        </div>
        <TrackRow
          v-for="song in songs"
          :key="song.id"
          :song="song"
        />
      </div>
    </template>
  </section>
</template>

<script>
import axios from 'axios';
import { mapActions } from 'vuex';

import TrackRow from '@/components/TrackRow.vue';

export default {
  name: 'GenresView',
  components: {TrackRow},
  data() {
    return {
      stats: [],
      selected: [],
      songs: [],
      total: 0,
      loading: true,
      listLoading: false,
      errorMessage: '',
    };
  },
  async created() {
    try {
      const {data} = await axios.get('songs/genres/stats');
      this.stats = data;
    } catch (error) {
      const detail = error.response && error.response.data && error.response.data.detail;
      this.errorMessage =
        (typeof detail === 'string' && detail) ||
        'Could not load the genres.';
    } finally {
      this.loading = false;
    }
  },
  methods: {
    ...mapActions(['setQueue']),
    // Same stable tint bucket TrackRow uses for covers, keyed on the genre
    // name instead of the song id.
    tint(genre) {
      let hash = 0;
      for (let i = 0; i < genre.length; i += 1) {
        hash = (hash * 31 + genre.charCodeAt(i)) >>> 0;
      }
      return `var(--tint-${(hash % 10) + 1})`;
    },
    toggle(genre) {
      const index = this.selected.indexOf(genre);
      if (index === -1) {
        this.selected.push(genre);
      } else {
        this.selected.splice(index, 1);
      }
      if (this.selected.length) {
        this.fetchSongs();
      } else {
        this.songs = [];
        this.total = 0;
      }
    },
    clearSelection() {
      this.selected = [];
      this.songs = [];
      this.total = 0;
    },
    async fetchSongs() {
      this.listLoading = true;
      this.errorMessage = '';
      try {
        // URLSearchParams so the repeatable `genre` filter serializes as
        // `genre=X&genre=Y` — axios 0.x would add brackets to a plain array.
        const params = new URLSearchParams();
        params.set('page_size', 300);
        params.set('sort', 'created_at');
        params.set('order', 'desc');
        this.selected.forEach(genre => params.append('genre', genre));
        const {data} = await axios.get('songs', {params});
        this.songs = data.items;
        this.total = data.total;
        // The player's prev/next and auto-advance walk this list.
        this.setQueue(data.items);
      } catch (error) {
        const detail = error.response && error.response.data && error.response.data.detail;
        this.errorMessage =
          (typeof detail === 'string' && detail) ||
          'Could not load the selected genres.';
      } finally {
        this.listLoading = false;
      }
    },
  },
};
</script>

<style scoped>
.gtiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(184px, 1fr));
  gap: 12px;
  margin-bottom: 26px;
}

.gtile {
  position: relative;
  height: 108px;
  border-radius: 13px;
  border: none;
  cursor: pointer;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, .09);
  overflow: hidden;
  text-align: left;
  padding: 15px;
  transition: filter .15s ease;
}

.gtile:hover {
  filter: brightness(1.08);
}

.gtile-on {
  box-shadow: 0 0 0 2px var(--acc);
}

.gtile-wave {
  position: absolute;
  right: -14px;
  bottom: -14px;
  display: flex;
  align-items: flex-end;
  gap: 3px;
  height: 56px;
  opacity: .28;
}

.gtile-wave span {
  width: 5px;
  background: #fff;
  border-radius: 2px;
}

.gtile-name {
  font: 700 17px/1.1 var(--font-disp);
  color: #fff;
}

.gtile-count {
  position: absolute;
  left: 15px;
  bottom: 13px;
  font: 500 11px var(--font-mono);
  color: rgba(255, 255, 255, .72);
}

.genres-error {
  font: 400 12.5px var(--font-ui);
  color: var(--danger);
  margin: 0 0 12px;
}

.genres-empty {
  padding: 56px 20px;
  text-align: center;
  color: var(--dim-2);
  font: 400 14px var(--font-ui);
}

.gsel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.gsel-title {
  font: 600 15px var(--font-disp);
}

.gsel-clear {
  height: 34px;
  padding: 0 13px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line-strong);
  background: rgba(255, 255, 255, .03);
  color: var(--muted);
  font: 600 12px var(--font-ui);
  cursor: pointer;
  transition: color .15s ease;
}

.gsel-clear:hover {
  color: var(--txt);
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
</style>
