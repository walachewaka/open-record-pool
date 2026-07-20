<template>
  <section>
    <div class="art-toolbar">
      <input
        v-model="q"
        type="text"
        class="art-search"
        placeholder="Search artists..."
        @input="onSearchInput"
      >
      <SegmentedControl
        v-model="filter"
        :options="[{value: 'all', label: 'All'}, {value: 'following', label: 'Following'}]"
        @update:model-value="reload"
      />
    </div>

    <div
      v-if="externalResults.length"
      class="art-external"
    >
      <div class="art-external-head">
        From Beatport
      </div>
      <div
        v-for="ext in externalResults"
        :key="ext.external_id"
        class="art-external-row"
      >
        <span>{{ ext.name }}</span>
        <span
          v-if="!ext.artist_id"
          class="art-external-hint"
        >Not yet in your library</span>
      </div>
    </div>
    <div
      v-else-if="q.length >= 2 && !sourcesConfigured"
      class="art-degraded"
    >
      No release source configured — add Beatport credentials in the environment to start tracking releases.
    </div>

    <div class="list-panel">
      <div
        v-if="!loading && !artists.length"
        class="list-empty"
      >
        {{ filter === 'following' ? 'You are not following any artists yet.' : 'No artists found.' }}
      </div>
      <div
        v-for="artist in artists"
        :key="artist.id"
        class="art-row"
      >
        <router-link
          class="art-row-main"
          :to="`/artist/${artist.id}`"
        >
          <span
            class="art-avatar"
            :style="{background: tintForId(artist.id)}"
          >{{ initialsFor(artist.name) }}</span>
          <span class="art-name">{{ artist.name }}</span>
          <span class="art-count">{{ artist.track_count }} tracks</span>
          <span
            v-if="artist.latest_release_date"
            class="art-latest"
          >latest {{ artist.latest_release_date }}</span>
        </router-link>
        <FollowButton
          :artist="artist"
          @changed="patch => onFollowChanged(artist, patch)"
        />
      </div>
    </div>
    <button
      v-if="nextCursor"
      type="button"
      class="art-more"
      :disabled="loading"
      @click="loadMore"
    >
      Load more
    </button>
  </section>
</template>

<script>
import axios from 'axios';

import FollowButton from '@/components/FollowButton.vue';
import SegmentedControl from '@/components/admin/SegmentedControl.vue';
import { initialsFor, tintForId } from '@/utils/format';

let searchTimer = null;

export default {
  name: 'ArtistsView',
  components: {FollowButton, SegmentedControl},
  data() {
    return {
      q: '',
      filter: 'all',
      artists: [],
      nextCursor: null,
      loading: true,
      externalResults: [],
      sourcesConfigured: true,
    };
  },
  created() {
    this.reload();
  },
  methods: {
    initialsFor,
    tintForId,
    onSearchInput() {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        this.reload();
        if (this.q.trim().length >= 2) {
          this.searchExternal();
        } else {
          this.externalResults = [];
        }
      }, 300);
    },
    async reload() {
      this.loading = true;
      try {
        const {data} = await axios.get('artists', {
          params: {
            q: this.q || undefined,
            followed: this.filter === 'following' || undefined,
            limit: 50,
          },
        });
        this.artists = data.items;
        this.nextCursor = data.next_cursor;
      } finally {
        this.loading = false;
      }
    },
    async loadMore() {
      if (!this.nextCursor) {
        return;
      }
      this.loading = true;
      try {
        const {data} = await axios.get('artists', {
          params: {
            q: this.q || undefined,
            followed: this.filter === 'following' || undefined,
            limit: 50,
            cursor: this.nextCursor,
          },
        });
        this.artists = [...this.artists, ...data.items];
        this.nextCursor = data.next_cursor;
      } finally {
        this.loading = false;
      }
    },
    async searchExternal() {
      try {
        const {data} = await axios.get('artists/search', {params: {q: this.q}});
        this.externalResults = data.external;
        this.sourcesConfigured = data.sources_configured;
      } catch (error) {
        this.externalResults = [];
      }
    },
    onFollowChanged(artist, patch) {
      Object.assign(artist, patch);
      if (this.filter === 'following' && !patch.is_followed) {
        this.artists = this.artists.filter(a => a.id !== artist.id);
      }
    },
  },
};
</script>

<style scoped>
.art-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.art-search {
  flex: 1;
  max-width: 360px;
  height: 36px;
  padding: 0 12px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line-strong);
  background: var(--panel);
  color: var(--txt);
  font: 500 13px var(--font-ui);
}

.art-search:focus {
  outline: none;
  border-color: var(--acc-border);
}

.art-external {
  margin-bottom: 14px;
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 10px 12px;
  background: var(--panel);
}

.art-external-head {
  font: 600 10px var(--font-mono);
  letter-spacing: .1em;
  color: var(--dim-2);
  text-transform: uppercase;
  margin-bottom: 6px;
}

.art-external-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font: 500 12.5px var(--font-ui);
  color: var(--txt-2);
  padding: 4px 0;
}

.art-external-hint {
  font: 400 11px var(--font-ui);
  color: var(--dim-3);
}

.art-degraded {
  margin-bottom: 14px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px dashed var(--line-strong);
  color: var(--dim-2);
  font: 400 12.5px var(--font-ui);
}

.list-panel {
  border: 1px solid var(--line);
  border-radius: 13px;
  overflow: hidden;
  background: var(--panel);
}

.list-empty {
  padding: 56px 20px;
  text-align: center;
  color: var(--dim-2);
  font: 400 14px var(--font-ui);
}

.art-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  height: 58px;
  padding: 0 14px;
  border-bottom: 1px solid rgba(255, 255, 255, .06);
}

.art-row:last-child {
  border-bottom: none;
}

.art-row-main {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
  color: inherit;
}

.art-avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font: 700 12px var(--font-ui);
  color: #fff;
  flex: none;
}

.art-name {
  font: 600 13.5px var(--font-ui);
  color: var(--txt);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.art-count,
.art-latest {
  font: 500 11.5px var(--font-mono);
  color: var(--dim-2);
  white-space: nowrap;
  flex: none;
}

.art-more {
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

.art-more:hover {
  border-color: var(--acc-border);
  color: var(--txt);
}

.art-more:disabled {
  opacity: .5;
  cursor: default;
}
</style>
