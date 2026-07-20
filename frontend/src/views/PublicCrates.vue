<template>
  <section>
    <div class="pc-head">
      <input
        v-model="q"
        type="text"
        class="pc-search"
        placeholder="Search public crates by name, description, or creator…"
      >
    </div>

    <p
      v-if="errorMessage"
      class="pc-error"
    >
      {{ errorMessage }}
    </p>

    <div
      v-if="!loading && !items.length"
      class="pc-empty"
    >
      No public crates yet
    </div>

    <div class="pc-grid">
      <router-link
        v-for="crate in items"
        :key="crate.id"
        :to="`/crate/${crate.id}`"
        class="pc-card"
      >
        <div
          class="pc-cover"
          :style="crate.cover_url ? {} : collageStyle(crate)"
        >
          <img
            v-if="crate.cover_url"
            :src="`${backendUrl}${crate.cover_url}`"
            alt=""
          >
        </div>
        <div class="pc-name">
          {{ crate.name }}
        </div>
        <div class="pc-by">
          by {{ crate.owner_username }}
        </div>
        <div class="pc-count">
          {{ crate.track_count }} tracks
        </div>
      </router-link>
    </div>

    <button
      v-if="nextCursor"
      type="button"
      class="pc-load-more"
      :disabled="loading"
      @click="load(false)"
    >
      {{ loading ? 'Loading…' : 'Load more' }}
    </button>
  </section>
</template>

<script>
import axios from 'axios';
import { mapActions } from 'vuex';

export default {
  name: 'PublicCrates',
  data() {
    return {
      q: '',
      items: [],
      nextCursor: null,
      loading: false,
      errorMessage: '',
      debounceHandle: null,
    };
  },
  computed: {
    backendUrl() {
      return axios.defaults.baseURL;
    },
  },
  watch: {
    q() {
      clearTimeout(this.debounceHandle);
      this.debounceHandle = setTimeout(() => this.load(true), 300);
    },
  },
  mounted() {
    this.load(true);
  },
  methods: {
    ...mapActions(['fetchPublicCrates']),
    collageStyle(crate) {
      const color = crate.color || 'var(--acc)';
      const shades = [80, 55, 35, 65];
      const stops = shades
        .map((pct, i) => {
          const mix = i % 2 === 0 ? 'black' : 'white';
          return `color-mix(in oklab, ${color} ${100 - pct}%, ${mix})`;
        })
        .join(', ');
      return {background: `conic-gradient(${stops})`};
    },
    async load(reset) {
      this.loading = true;
      this.errorMessage = '';
      try {
        const data = await this.fetchPublicCrates({
          q: this.q,
          cursor: reset ? null : this.nextCursor,
        });
        this.items = reset ? data.items : this.items.concat(data.items);
        this.nextCursor = data.next_cursor;
      } catch (error) {
        this.errorMessage = 'Could not load public crates.';
      } finally {
        this.loading = false;
      }
    },
  },
};
</script>

<style scoped>
.pc-head {
  margin-bottom: 18px;
}

.pc-search {
  width: 100%;
  max-width: 480px;
  height: 40px;
  padding: 0 14px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line-strong);
  background: var(--panel);
  color: var(--txt);
  font: 400 13.5px var(--font-ui);
}

.pc-search:focus {
  outline: none;
  border-color: color-mix(in oklab, var(--acc) 55%, transparent);
}

.pc-error {
  font: 400 12.5px var(--font-ui);
  color: var(--danger);
}

.pc-empty {
  padding: 60px 24px;
  text-align: center;
  color: var(--dim-2);
  font: 600 15px var(--font-disp);
}

.pc-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 18px;
}

.pc-card {
  display: block;
  text-decoration: none;
  color: inherit;
}

.pc-cover {
  width: 100%;
  aspect-ratio: 1;
  border-radius: 12px;
  overflow: hidden;
  background: var(--panel);
  border: 1px solid var(--line);
}

.pc-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.pc-name {
  margin-top: 8px;
  font: 600 14px var(--font-disp);
  color: var(--txt);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pc-by {
  font: 400 12px var(--font-ui);
  color: var(--muted);
}

.pc-count {
  font: 400 11px var(--font-mono);
  color: var(--dim-2);
}

.pc-load-more {
  display: block;
  margin: 22px auto 0;
  height: 38px;
  padding: 0 16px;
  border-radius: var(--r-ctl);
  border: none;
  background: var(--acc);
  color: var(--acc-ink);
  font: 600 13px var(--font-ui);
  cursor: pointer;
}

.pc-load-more:disabled {
  opacity: .5;
  cursor: default;
}
</style>
