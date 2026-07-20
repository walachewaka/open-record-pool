<template>
  <section>
    <div class="hd-greet">
      <div class="hd-greet-title">
        {{ greeting }}
      </div>
      <div class="hd-greet-sub">
        Here’s what’s fresh in the pool today
      </div>
    </div>

    <div
      v-if="chips.length"
      class="hd-chips"
    >
      <button
        v-for="chip in chips"
        :key="chip.genre"
        type="button"
        class="hd-chip"
        @click="goBrowseGenre(chip.genre)"
      >
        {{ chip.genre }}
      </button>
    </div>

    <div
      v-if="hero"
      class="hero"
    >
      <div class="hero-glow" />
      <div class="hero-body">
        <div class="hero-eyebrow">
          ★ FEATURED RELEASE
        </div>
        <div class="hero-title">
          {{ hero.song.title || 'Untitled' }}
        </div>
        <div class="hero-artist">
          {{ hero.song.artist || 'Unknown artist' }}
        </div>
        <div class="hero-chips">
          <span
            v-if="hero.song.genre"
            class="hero-chip"
          >{{ hero.song.genre }}</span>
          <span
            v-if="hero.song.camelot_key || hero.song.musical_key"
            class="hero-chip hero-chip-key"
          >KEY {{ hero.song.camelot_key || hero.song.musical_key }}</span>
          <span
            v-if="hero.song.bpm != null"
            class="hero-chip hero-chip-mono"
          >{{ Math.round(hero.song.bpm) }} BPM</span>
          <span
            v-if="hero.metric != null"
            class="hero-dls"
          >{{ fmtNum(hero.metric) }} downloads</span>
        </div>
        <div class="hero-actions">
          <button
            type="button"
            class="hero-play"
            @click="play([hero.song], hero.song)"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="currentColor"
            >
              <path d="M8 5v14l11-7z" />
            </svg>
            Play preview
          </button>
          <button
            type="button"
            class="hero-view"
            @click="$router.push(`/release/${hero.song.id}`)"
          >
            View release
          </button>
        </div>
      </div>
      <div
        class="hero-cover"
        :style="{background: tintForId(hero.song.id)}"
      >
        <span>{{ initialsFor(hero.song.title || hero.song.artist) }}</span>
      </div>
    </div>

    <div
      v-if="jumpBackIn.length"
      class="hd-jump"
    >
      <div class="hd-jump-head">
        <div class="hd-jump-title">
          Jump back in
        </div>
        <button
          type="button"
          class="hd-showall"
          @click="$router.push('/downloads')"
        >
          Show all
        </button>
      </div>
      <div class="hd-jump-grid">
        <button
          v-for="song in jumpBackIn"
          :key="song.id"
          type="button"
          class="jb-tile"
          :title="song.title || ''"
          @click="play(jumpBackIn, song)"
        >
          <span
            class="jb-cover"
            :style="{background: tintForId(song.id)}"
          >{{ initialsFor(song.title || song.artist) }}</span>
          <span class="jb-meta">
            <span class="jb-title">{{ song.title || 'Untitled' }}</span>
            <span class="jb-artist">{{ song.artist || 'Unknown artist' }}</span>
          </span>
        </button>
      </div>
    </div>

    <HomeShelf
      v-if="newest.length"
      title="New releases"
      subtitle="Fresh cuts just added to the pool"
      show-all="Show all"
      @show-all="$router.push('/library')"
    >
      <ReleaseCard
        v-for="song in newest"
        :key="song.id"
        :song="song"
        @play="play(newest, song)"
      />
    </HomeShelf>

    <HomeShelf
      v-if="recommended.length"
      title="Recommended for you"
      :subtitle="recoReason"
    >
      <ReleaseCard
        v-for="song in recommended"
        :key="song.id"
        :song="song"
        @play="play(recommended, song)"
      />
    </HomeShelf>

    <HomeShelf
      v-if="packs.length"
      title="Hot crates &amp; packs"
      subtitle="Curated sets and your own crates"
    >
      <div
        v-for="pack in packs"
        :key="pack.kind + pack.id"
        class="pk"
      >
        <button
          type="button"
          class="pk-tile"
          :style="{background: `linear-gradient(150deg, ${pack.color}, #0c0f14)`}"
          :title="pack.name"
          @click="openPack(pack)"
        >
          <span class="pk-wave">
            <span style="height: 46%" />
            <span style="height: 82%" />
            <span style="height: 58%" />
            <span style="height: 100%" />
          </span>
          <span class="pk-glyph">
            <svg
              width="22"
              height="22"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linejoin="round"
            >
              <path d="M3 8l9-4 9 4-9 4-9-4z" />
              <path d="M3 8v8l9 4 9-4V8" />
            </svg>
          </span>
        </button>
        <div class="pk-name">
          {{ pack.name }}
        </div>
        <div class="pk-sub">
          {{ pack.sub }}
        </div>
      </div>
    </HomeShelf>

    <HomeShelf
      v-if="topTen.length"
      title="Top 10 this week"
      subtitle="Most downloaded across the pool"
      show-all="Full chart"
      @show-all="$router.push('/charts')"
    >
      <div
        v-for="entry in topTen"
        :key="entry.song.id"
        class="tt"
      >
        <span class="tt-rank">{{ entry.rank }}</span>
        <button
          type="button"
          class="tt-cover"
          :style="{background: tintForId(entry.song.id)}"
          title="Play"
          @click="play(topTen.map(e => e.song), entry.song)"
        >
          <span class="tt-initials">{{ initialsFor(entry.song.title || entry.song.artist) }}</span>
          <span class="tt-overlay">
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="currentColor"
            >
              <path d="M8 5v14l11-7z" />
            </svg>
          </span>
        </button>
        <div class="tt-meta">
          <button
            type="button"
            class="tt-title"
            :title="entry.song.title || ''"
            @click="$router.push(`/release/${entry.song.id}`)"
          >
            {{ entry.song.title || 'Untitled' }}
          </button>
          <div class="tt-artist">
            {{ entry.song.artist || 'Unknown artist' }}
          </div>
          <div class="tt-dls">
            {{ fmtNum(entry.metric) }} downloads
          </div>
        </div>
      </div>
    </HomeShelf>

    <HomeShelf
      v-if="artists.length"
      title="Artists to follow"
      subtitle="Producers moving the pool right now"
    >
      <div
        v-for="artist in artists"
        :key="artist.name"
        class="ar"
      >
        <button
          type="button"
          class="ar-avatar"
          :style="{background: artist.tint}"
          :title="artist.name"
          @click="goSearch(artist.name)"
        >
          <span>{{ artist.initials }}</span>
        </button>
        <div class="ar-name">
          {{ artist.name }}
        </div>
        <div class="ar-kind">
          Artist
        </div>
      </div>
    </HomeShelf>

    <HomeShelf
      v-if="labels.length"
      title="Fresh on labels"
      subtitle="Imprints stocking the pool"
    >
      <div
        v-for="label in labels"
        :key="label.name"
        class="lb"
      >
        <button
          type="button"
          class="lb-tile"
          :style="{background: `linear-gradient(150deg, ${label.tint}, #0c0f14)`}"
          :title="label.name"
          @click="goSearch(label.name)"
        >
          <span>{{ label.initials }}</span>
        </button>
        <div class="lb-name">
          {{ label.name }}
        </div>
        <div class="lb-kind">
          Label
        </div>
      </div>
    </HomeShelf>
  </section>
</template>

<script>
import axios from 'axios';
import { mapActions, mapGetters } from 'vuex';

import HomeShelf from '@/components/HomeShelf.vue';
import ReleaseCard from '@/components/ReleaseCard.vue';
import { fmtNum, initialsFor, tintForId } from '@/utils/format';

// Gradient palette for the crate-pack and label tiles (design handoff rev 2).
const PACK_PALETTE = ['#17b9ff', '#9d8bff', '#35d07a', '#ffb62e', '#ff5266', '#12b3ff'];

export default {
  name: 'HomeDashboard',
  components: {HomeShelf, ReleaseCard},
  data() {
    return {
      newest: [],
      genreStats: [],
      // /charts most_downloaded entries: {rank, metric, song}.
      chart: [],
      recentDownloads: [],
      recentFavorites: [],
      recommended: [],
      recoGenre: '',
    };
  },
  computed: {
    ...mapGetters({
      user: 'stateUser',
      currentSong: 'stateSong',
      stateCrates: 'stateCrates',
    }),
    greeting() {
      const hour = new Date().getHours();
      const part = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
      const name = (this.user && (this.user.full_name || this.user.username)) || 'DJ';
      return `${part}, ${name}`;
    },
    // Top genres by track count feed the quick-pick chips and the packs.
    topGenres() {
      return this.genreStats.slice().sort((a, b) => b.track_count - a.track_count);
    },
    chips() {
      return this.topGenres.slice(0, 8);
    },
    // The top-downloaded release; newest release when nothing has downloads.
    hero() {
      if (this.chart.length) {
        return this.chart[0];
      }
      if (this.newest.length) {
        return {song: this.newest[0], metric: null};
      }
      return null;
    },
    jumpBackIn() {
      const seen = {};
      const songs = [];
      const push = song => {
        if (song && !seen[song.id]) {
          seen[song.id] = true;
          songs.push(song);
        }
      };
      this.recentDownloads.forEach(item => push(item.song));
      this.recentFavorites.forEach(push);
      this.newest.forEach(song => {
        if (songs.length < 8) {
          push(song);
        }
      });
      return songs.slice(0, 8);
    },
    packs() {
      const crates = this.stateCrates.map(crate => ({
        kind: 'crate',
        id: crate.id,
        name: crate.name,
        sub: `${crate.track_count} tracks`,
        color: crate.color || 'var(--acc)',
      }));
      const genres = this.topGenres.slice(0, 6).map((stat, index) => ({
        kind: 'genre',
        id: stat.genre,
        name: `${stat.genre} Weapons`,
        sub: `${stat.track_count} in pool`,
        color: PACK_PALETTE[index % PACK_PALETTE.length],
      }));
      return crates.concat(genres);
    },
    topTen() {
      return this.chart.slice(0, 10);
    },
    artists() {
      const seen = {};
      const artists = [];
      this.newest.forEach(song => {
        const name = (song.artist || '').split(' feat.')[0].trim();
        if (name && !seen[name]) {
          seen[name] = true;
          artists.push({name, initials: initialsFor(name), tint: tintForId(song.id)});
        }
      });
      return artists.slice(0, 12);
    },
    labels() {
      const seen = {};
      const labels = [];
      this.newest.forEach(song => {
        const name = (song.label || '').trim();
        if (name && !seen[name]) {
          seen[name] = true;
          labels.push({
            name,
            initials: initialsFor(name),
            tint: PACK_PALETTE[labels.length % PACK_PALETTE.length],
          });
        }
      });
      return labels.slice(0, 8);
    },
    recoReason() {
      return this.recoGenre ? `Because you play ${this.recoGenre}` : 'Popular in the pool';
    },
  },
  created() {
    this.fetchShelves();
  },
  methods: {
    ...mapActions(['playSong', 'setQueue', 'togglePlayback']),
    fmtNum,
    initialsFor,
    tintForId,
    async fetchShelves() {
      // Every shelf degrades gracefully: a failed fetch just hides it.
      await Promise.all([
        this.fetch('songs', {page_size: 60, sort: 'created_at', order: 'desc'},
          data => { this.newest = data.items; }),
        this.fetch('songs/genres/stats', null,
          data => { this.genreStats = data; }),
        this.fetch('charts', {mode: 'most_downloaded', limit: 10},
          data => { this.chart = data.entries; }),
        this.fetch('downloads', {page_size: 12},
          data => { this.recentDownloads = data.items; }),
        this.fetch('favorites', {page_size: 12},
          data => { this.recentFavorites = data.items; }),
      ]);
      this.fetchRecommended();
    },
    async fetch(url, params, apply) {
      try {
        const {data} = await axios.get(url, params ? {params} : undefined);
        apply(data);
      } catch (error) {
        // Leave the shelf's data empty; the section stays hidden.
      }
    },
    async fetchRecommended() {
      // Recommendations key off the genres of the user's downloads +
      // favorites; new members fall back to the pool's top genre.
      const counts = {};
      this.recentDownloads.forEach(item => {
        if (item.song && item.song.genre) {
          counts[item.song.genre] = (counts[item.song.genre] || 0) + 1;
        }
      });
      this.recentFavorites.forEach(song => {
        if (song.genre) {
          counts[song.genre] = (counts[song.genre] || 0) + 1;
        }
      });
      const played = Object.keys(counts).sort((a, b) => counts[b] - counts[a])[0];
      this.recoGenre = played || '';
      const genre = played || (this.topGenres[0] && this.topGenres[0].genre);
      if (!genre) {
        return;
      }
      const params = new URLSearchParams();
      params.set('page_size', 12);
      params.set('sort', 'most_downloaded');
      params.set('order', 'desc');
      params.append('genre', genre);
      await this.fetch('songs', params, data => { this.recommended = data.items; });
    },
    play(list, song) {
      if (this.currentSong && this.currentSong.id === song.id) {
        this.togglePlayback();
        return;
      }
      // The player's prev/next and auto-advance walk the card's shelf.
      this.setQueue(list);
      this.playSong(song);
    },
    goBrowseGenre(genre) {
      this.$router.push({path: '/library', query: {genre}});
    },
    goSearch(q) {
      this.$router.push({path: '/search', query: {q}});
    },
    openPack(pack) {
      if (pack.kind === 'crate') {
        this.$router.push(`/crate/${pack.id}`);
      } else {
        this.goBrowseGenre(pack.id);
      }
    },
  },
};
</script>

<style scoped>
.hd-greet {
  margin-bottom: 20px;
}

.hd-greet-title {
  font: 700 26px/1.05 var(--font-disp);
}

.hd-greet-sub {
  font: 400 13px var(--font-ui);
  color: var(--muted);
  margin-top: 5px;
}

.hd-chips {
  display: flex;
  gap: 9px;
  flex-wrap: wrap;
  margin-bottom: 26px;
}

.hd-chip {
  padding: 7px 13px;
  border-radius: var(--r-pill);
  border: 1px solid var(--line-strong);
  background: rgba(255, 255, 255, .03);
  color: var(--txt-2);
  font: 500 12.5px var(--font-ui);
  cursor: pointer;
  transition: border-color .15s ease, color .15s ease;
}

.hd-chip:hover {
  border-color: color-mix(in oklab, var(--acc) 45%, transparent);
  color: var(--txt);
}

/* ---------- Featured hero ---------- */

.hero {
  position: relative;
  overflow: hidden;
  border-radius: 18px;
  margin-bottom: 34px;
  min-height: 236px;
  display: flex;
  align-items: center;
  background: linear-gradient(120deg, #13212c 0%, #0c0f14 62%);
  border: 1px solid rgba(255, 255, 255, .08);
}

.hero-glow {
  position: absolute;
  inset: 0;
  background: radial-gradient(620px 320px at 86% 18%, color-mix(in oklab, var(--acc) 24%, transparent), transparent);
  pointer-events: none;
}

.hero-body {
  position: relative;
  flex: 1;
  padding: 34px 36px;
  min-width: 0;
}

.hero-eyebrow {
  font: 600 11px var(--font-mono);
  letter-spacing: .12em;
  color: var(--acc);
  margin-bottom: 12px;
}

.hero-title {
  font: 700 34px/1.05 var(--font-disp);
  margin-bottom: 8px;
  max-width: 520px;
  text-wrap: pretty;
}

.hero-artist {
  font: 400 15px var(--font-ui);
  color: var(--txt-3);
  margin-bottom: 16px;
}

.hero-chips {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 22px;
}

.hero-chip {
  padding: 5px 11px;
  border-radius: 8px;
  background: rgba(255, 255, 255, .06);
  border: 1px solid rgba(255, 255, 255, .09);
  font: 500 12px var(--font-ui);
  color: var(--txt-2);
}

.hero-chip-key {
  background: rgba(157, 139, 255, .13);
  border-color: rgba(157, 139, 255, .28);
  font: 600 12px var(--font-mono);
  color: var(--key-bright);
}

.hero-chip-mono {
  font: 600 12px var(--font-mono);
}

.hero-dls {
  font: 400 12px var(--font-ui);
  color: var(--dim);
  margin-left: 2px;
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 11px;
}

.hero-play {
  height: 44px;
  padding: 0 22px;
  border-radius: 10px;
  border: none;
  background: var(--acc);
  color: var(--acc-ink);
  font: 600 14px var(--font-ui);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 9px;
  transition: filter .15s ease;
}

.hero-play:hover {
  filter: brightness(1.1);
}

.hero-view {
  height: 44px;
  padding: 0 18px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, .14);
  background: rgba(255, 255, 255, .04);
  color: var(--txt);
  font: 600 13.5px var(--font-ui);
  cursor: pointer;
  transition: border-color .15s ease;
}

.hero-view:hover {
  border-color: rgba(255, 255, 255, .3);
}

.hero-cover {
  position: relative;
  width: 210px;
  height: 210px;
  margin-right: 36px;
  border-radius: 16px;
  box-shadow: 0 16px 46px rgba(0, 0, 0, .5), inset 0 0 0 1px rgba(255, 255, 255, .1);
  display: flex;
  align-items: center;
  justify-content: center;
  flex: none;
}

.hero-cover span {
  font: 600 40px var(--font-mono);
  color: rgba(255, 255, 255, .66);
}

/* ---------- Jump back in ---------- */

.hd-jump {
  margin-bottom: 32px;
}

.hd-jump-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.hd-jump-title {
  font: 700 19px var(--font-disp);
}

.hd-showall {
  height: 30px;
  padding: 0 12px;
  border-radius: var(--r-pill);
  border: 1px solid var(--line-strong);
  background: none;
  color: var(--muted);
  font: 600 11.5px var(--font-ui);
  cursor: pointer;
  transition: color .15s ease, border-color .15s ease;
}

.hd-showall:hover {
  color: var(--txt);
  border-color: rgba(255, 255, 255, .24);
}

.hd-jump-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(232px, 1fr));
  gap: 10px;
}

.jb-tile {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 60px;
  padding: 0;
  border-radius: 10px;
  border: none;
  background: rgba(255, 255, 255, .045);
  cursor: pointer;
  overflow: hidden;
  text-align: left;
  transition: background .15s ease;
}

.jb-tile:hover {
  background: rgba(255, 255, 255, .09);
}

.jb-cover {
  width: 60px;
  height: 60px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  font: 600 13px var(--font-mono);
  color: rgba(255, 255, 255, .7);
}

.jb-meta {
  min-width: 0;
  flex: 1;
  padding-right: 12px;
}

.jb-title {
  display: block;
  font: 600 13px var(--font-ui);
  color: var(--txt);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.jb-artist {
  display: block;
  font: 400 11.5px var(--font-ui);
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 2px;
}

/* ---------- Hot crates & packs ---------- */

.pk {
  flex: none;
  width: 168px;
  scroll-snap-align: start;
}

.pk-tile {
  position: relative;
  display: block;
  width: 168px;
  height: 168px;
  border-radius: 12px;
  border: none;
  padding: 0;
  cursor: pointer;
  overflow: hidden;
  box-shadow: var(--shadow-cover);
  margin-bottom: 11px;
  transition: filter .15s ease;
}

.pk-tile:hover {
  filter: brightness(1.08);
}

.pk-wave {
  position: absolute;
  right: -14px;
  bottom: -14px;
  display: flex;
  align-items: flex-end;
  gap: 4px;
  height: 74px;
  opacity: .28;
}

.pk-wave span {
  width: 7px;
  background: #fff;
  border-radius: 3px;
}

.pk-glyph {
  position: absolute;
  left: 13px;
  top: 13px;
  color: rgba(255, 255, 255, .9);
}

.pk-name {
  font: 600 13.5px var(--font-ui);
  color: var(--txt);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pk-sub {
  font: 400 12px var(--font-ui);
  color: var(--muted);
  margin-top: 2px;
}

/* ---------- Top 10 ---------- */

.tt {
  flex: none;
  width: 294px;
  scroll-snap-align: start;
  display: flex;
  align-items: center;
  gap: 8px;
  height: 84px;
  padding: 0 14px 0 6px;
  border-radius: 12px;
  background: rgba(255, 255, 255, .03);
  border: 1px solid rgba(255, 255, 255, .05);
  box-sizing: border-box;
  transition: background .15s ease;
}

.tt:hover {
  background: rgba(255, 255, 255, .055);
}

.tt-rank {
  width: 34px;
  text-align: center;
  font: 700 24px var(--font-disp);
  color: #3a424e;
  flex: none;
}

.tt-cover {
  position: relative;
  width: 56px;
  height: 56px;
  border-radius: 9px;
  border: none;
  padding: 0;
  cursor: pointer;
  box-shadow: var(--shadow-cover);
  overflow: hidden;
  flex: none;
}

.tt-initials {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font: 600 13px var(--font-mono);
  color: rgba(255, 255, 255, .62);
}

.tt-overlay {
  position: absolute;
  inset: 0;
  background: rgba(4, 10, 16, .5);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  opacity: 0;
  transition: opacity .15s ease;
}

.tt-cover:hover .tt-overlay {
  opacity: 1;
}

.tt-meta {
  min-width: 0;
  flex: 1;
}

.tt-title {
  display: block;
  max-width: 100%;
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  font: 600 13px var(--font-ui);
  color: var(--txt);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: left;
  transition: color .15s ease;
}

.tt-title:hover {
  color: var(--acc);
}

.tt-artist {
  font: 400 11.5px var(--font-ui);
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 2px;
}

.tt-dls {
  font: 500 10px var(--font-mono);
  color: var(--dim-2);
  margin-top: 2px;
}

/* ---------- Artists ---------- */

.ar {
  flex: none;
  width: 132px;
  scroll-snap-align: start;
  text-align: center;
}

.ar-avatar {
  display: block;
  width: 132px;
  height: 132px;
  border-radius: 50%;
  border: none;
  padding: 0;
  cursor: pointer;
  overflow: hidden;
  box-shadow: var(--shadow-cover);
  margin-bottom: 11px;
  transition: filter .15s ease;
}

.ar-avatar:hover {
  filter: brightness(1.08);
}

.ar-avatar span {
  display: flex;
  width: 100%;
  height: 100%;
  align-items: center;
  justify-content: center;
  font: 600 26px var(--font-mono);
  color: rgba(255, 255, 255, .62);
}

.ar-name {
  font: 600 13px var(--font-ui);
  color: var(--txt);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ar-kind {
  font: 400 11.5px var(--font-ui);
  color: var(--dim);
  margin-top: 1px;
}

/* ---------- Labels ---------- */

.lb {
  flex: none;
  width: 150px;
  scroll-snap-align: start;
}

.lb-tile {
  position: relative;
  display: block;
  width: 150px;
  height: 150px;
  border-radius: 12px;
  border: none;
  padding: 0;
  cursor: pointer;
  overflow: hidden;
  box-shadow: var(--shadow-cover);
  margin-bottom: 11px;
  transition: filter .15s ease;
}

.lb-tile:hover {
  filter: brightness(1.08);
}

.lb-tile span {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font: 700 30px var(--font-disp);
  color: rgba(255, 255, 255, .82);
}

.lb-name {
  font: 600 13px var(--font-ui);
  color: var(--txt);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.lb-kind {
  font: 400 11.5px var(--font-ui);
  color: var(--dim);
  margin-top: 1px;
}
</style>
