<template>
  <div class="rr">
    <div
      class="rr-art"
      :style="release.artwork_url ? {} : {background: tint}"
    >
      <img
        v-if="release.artwork_url"
        :src="release.artwork_url"
        alt=""
      >
    </div>
    <div class="rr-main">
      <div class="rr-title">
        {{ release.title }}
      </div>
      <router-link
        class="rr-artist"
        :to="`/artist/${release.artist.id}`"
      >
        {{ release.artist.name }}
      </router-link>
      <div
        v-if="release.label"
        class="rr-label"
      >
        {{ release.label }}
      </div>
    </div>
    <div class="rr-date">
      {{ formattedDate }}
    </div>
    <div class="rr-count">
      {{ release.track_count }} tr
    </div>
    <span
      class="rr-status"
      :class="`rr-status-${release.status}`"
    >{{ statusLabel }}</span>
    <div class="rr-actions">
      <a
        v-if="release.source_url"
        :href="release.source_url"
        target="_blank"
        rel="noopener"
        class="rr-link"
        title="Open on source"
      >
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <path d="M14 4h6v6M20 4l-9 9M9 4H5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4" />
        </svg>
      </a>
      <button
        v-if="release.status === 'missing'"
        type="button"
        class="rr-btn"
        :disabled="busy"
        @click="grab"
      >
        Grab
      </button>
      <button
        v-if="release.status === 'missing' || release.status === 'grabbed'"
        type="button"
        class="rr-btn rr-btn-ghost"
        :disabled="busy"
        @click="ignore"
      >
        Ignore
      </button>
      <button
        v-if="release.status === 'ignored'"
        type="button"
        class="rr-btn rr-btn-ghost"
        :disabled="busy"
        @click="unignore"
      >
        Unignore
      </button>
    </div>
  </div>
</template>

<script>
import axios from 'axios';

import { tintForId } from '@/utils/format';
import { toast } from '@/utils/toast';

const STATUS_LABELS = {
  missing: 'Missing',
  in_library: 'In library',
  grabbed: 'Grabbed',
  ignored: 'Ignored',
};

export default {
  name: 'ReleaseRow',
  props: {
    release: {
      type: Object,
      required: true,
    },
  },
  emits: ['updated'],
  data() {
    return {
      busy: false,
    };
  },
  computed: {
    tint() {
      return tintForId(this.release.artist.id);
    },
    statusLabel() {
      return STATUS_LABELS[this.release.status] || this.release.status;
    },
    formattedDate() {
      if (!this.release.release_date) {
        return '—';
      }
      const d = new Date(`${this.release.release_date}T00:00:00Z`);
      return d.toLocaleDateString('en-US', {
        year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC',
      });
    },
  },
  methods: {
    async grab() {
      this.busy = true;
      try {
        const {data} = await axios.post(`releases/${this.release.id}/grab`);
        this.$emit('updated', data.release);
        const count = (data.request_ids || []).length;
        toast(count ? `Queued ${count} request(s)` : 'Nothing new to request');
      } catch (error) {
        const detail = error.response && error.response.data && error.response.data.detail;
        toast((typeof detail === 'string' && detail) || 'Could not grab this release', 'warn');
      } finally {
        this.busy = false;
      }
    },
    async ignore() {
      this.busy = true;
      try {
        const {data} = await axios.post(`releases/${this.release.id}/ignore`);
        this.$emit('updated', data);
      } catch (error) {
        toast('Could not ignore this release', 'warn');
      } finally {
        this.busy = false;
      }
    },
    async unignore() {
      this.busy = true;
      try {
        const {data} = await axios.post(`releases/${this.release.id}/unignore`);
        this.$emit('updated', data);
      } catch (error) {
        toast('Could not unignore this release', 'warn');
      } finally {
        this.busy = false;
      }
    },
  },
};
</script>

<style scoped>
.rr {
  display: grid;
  grid-template-columns: 44px minmax(160px, 2fr) 90px 56px 96px auto;
  align-items: center;
  gap: 12px;
  height: 62px;
  padding: 0 12px;
  border-bottom: 1px solid rgba(255, 255, 255, .06);
}

.rr:last-child {
  border-bottom: none;
}

.rr-art {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  overflow: hidden;
  flex: none;
}

.rr-art img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.rr-main {
  min-width: 0;
}

.rr-title {
  font: 600 13.5px var(--font-ui);
  color: var(--txt);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rr-artist {
  font: 500 12px var(--font-ui);
  color: var(--dim-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rr-artist:hover {
  color: var(--acc);
}

.rr-label {
  font: 400 11px var(--font-ui);
  color: var(--dim-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rr-date {
  font: 500 12px var(--font-mono);
  color: var(--muted);
}

.rr-count {
  font: 500 11px var(--font-mono);
  color: var(--dim-2);
}

.rr-status {
  padding: 3px 9px;
  border-radius: var(--r-pill);
  font: 600 10.5px var(--font-mono);
  white-space: nowrap;
  width: fit-content;
}

.rr-status-in_library {
  background: rgba(90, 200, 130, .14);
  color: var(--ok, #5ac882);
}

.rr-status-missing {
  background: rgba(255, 182, 46, .14);
  color: var(--warn);
}

.rr-status-grabbed {
  background: var(--acc-soft-strong);
  color: var(--acc);
}

.rr-status-ignored {
  background: rgba(255, 255, 255, .06);
  color: var(--dim-2);
}

.rr-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  justify-self: end;
}

.rr-link {
  color: var(--dim-2);
  display: flex;
}

.rr-link:hover {
  color: var(--acc);
}

.rr-btn {
  height: 28px;
  padding: 0 10px;
  border-radius: var(--r-ctl);
  border: 1px solid transparent;
  background: var(--acc-soft-strong);
  color: var(--acc);
  font: 600 11.5px var(--font-ui);
  cursor: pointer;
}

.rr-btn:disabled {
  opacity: .5;
  cursor: default;
}

.rr-btn-ghost {
  background: none;
  border: 1px solid var(--line-strong);
  color: var(--muted);
}
</style>
