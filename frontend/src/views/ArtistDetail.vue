<template>
  <section v-if="artist">
    <div class="ad-header">
      <span
        class="ad-avatar"
        :style="{background: tintForId(artist.id)}"
      >{{ initialsFor(artist.name) }}</span>
      <div class="ad-info">
        <div class="ad-name">
          {{ artist.name }}
        </div>
        <div class="ad-meta">
          <span>{{ artist.track_count }} tracks in your library</span>
          <span
            v-if="artist.beatport_artist_id"
            class="ad-chip"
          >Tracked on Beatport</span>
          <span
            v-else
            class="ad-chip ad-chip-muted"
          >Not linked to a release source yet</span>
        </div>
      </div>
      <FollowButton
        :artist="artist"
        @changed="patch => Object.assign(artist, patch)"
      />
    </div>

    <template v-if="artist.releases.length">
      <div class="ad-section-title">
        Releases
      </div>
      <div class="list-panel ad-releases">
        <ReleaseRow
          v-for="release in artist.releases"
          :key="release.id"
          :release="release"
          @updated="row => replaceRelease(row)"
        />
      </div>
    </template>

    <div class="ad-section-title">
      In your library
    </div>
    <div class="list-panel">
      <div
        v-if="!tracksLoading && !tracks.length"
        class="list-empty"
      >
        No library tracks for this artist.
      </div>
      <TrackRow
        v-for="song in tracks"
        :key="song.id"
        :song="song"
      />
    </div>
    <button
      v-if="nextCursor"
      type="button"
      class="ad-more"
      :disabled="tracksLoading"
      @click="loadMoreTracks"
    >
      Load more
    </button>
  </section>
</template>

<script>
import axios from 'axios';
import { mapActions } from 'vuex';

import FollowButton from '@/components/FollowButton.vue';
import ReleaseRow from '@/components/ReleaseRow.vue';
import TrackRow from '@/components/TrackRow.vue';
import { initialsFor, tintForId } from '@/utils/format';

export default {
  name: 'ArtistDetailView',
  components: {FollowButton, ReleaseRow, TrackRow},
  data() {
    return {
      artist: null,
      tracks: [],
      nextCursor: null,
      tracksLoading: true,
    };
  },
  created() {
    this.load();
  },
  methods: {
    initialsFor,
    tintForId,
    ...mapActions(['setQueue']),
    async load() {
      const {data} = await axios.get(`artists/${this.$route.params.id}`);
      this.artist = data;
      await this.loadTracks();
    },
    async loadTracks() {
      this.tracksLoading = true;
      try {
        const {data} = await axios.get(`artists/${this.$route.params.id}/tracks`, {
          params: {limit: 50},
        });
        this.tracks = data.items;
        this.nextCursor = data.next_cursor;
        this.setQueue(data.items);
      } finally {
        this.tracksLoading = false;
      }
    },
    async loadMoreTracks() {
      if (!this.nextCursor) {
        return;
      }
      this.tracksLoading = true;
      try {
        const {data} = await axios.get(`artists/${this.$route.params.id}/tracks`, {
          params: {limit: 50, cursor: this.nextCursor},
        });
        this.tracks = [...this.tracks, ...data.items];
        this.nextCursor = data.next_cursor;
        this.setQueue(this.tracks);
      } finally {
        this.tracksLoading = false;
      }
    },
    replaceRelease(row) {
      this.artist.releases = this.artist.releases.map(r => (r.id === row.id ? row : r));
    },
  },
};
</script>

<style scoped>
.ad-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 22px;
}

.ad-avatar {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font: 700 22px var(--font-ui);
  color: #fff;
  flex: none;
}

.ad-info {
  flex: 1;
  min-width: 0;
}

.ad-name {
  font: 700 22px var(--font-disp);
  color: var(--txt);
}

.ad-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 6px;
  font: 500 12.5px var(--font-ui);
  color: var(--dim-2);
}

.ad-chip {
  padding: 3px 9px;
  border-radius: var(--r-pill);
  background: var(--acc-soft-strong);
  color: var(--acc);
  font: 600 10.5px var(--font-mono);
}

.ad-chip-muted {
  background: rgba(255, 255, 255, .06);
  color: var(--dim-2);
}

.ad-section-title {
  font: 600 13px var(--font-mono);
  letter-spacing: .05em;
  text-transform: uppercase;
  color: var(--dim-2);
  margin: 22px 0 10px;
}

.ad-releases {
  margin-bottom: 6px;
}

.list-panel {
  border: 1px solid var(--line);
  border-radius: 13px;
  overflow: hidden;
  background: var(--panel);
}

.list-empty {
  padding: 40px 20px;
  text-align: center;
  color: var(--dim-2);
  font: 400 14px var(--font-ui);
}

.ad-more {
  margin: 14px auto 0;
  display: block;
  height: 36px;
  padding: 0 18px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line-strong);
  background: rgba(255, 255, 255, .03);
  color: var(--txt-2);
  font: 600 12.5px var(--font-ui);
  cursor: pointer;
}
</style>
