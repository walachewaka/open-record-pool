<template>
  <section>
    <p
      v-if="errorMessage"
      class="crate-error"
    >
      {{ errorMessage }}
    </p>
    <template v-else-if="crate">
      <div class="crate-head">
        <div
          class="crate-tile"
          :class="{'crate-tile-owner': !readOnly}"
          :style="tileStyle"
        >
          <img
            v-if="coverSrc"
            :src="coverSrc"
            class="crate-cover-img"
            alt=""
          >
          <svg
            v-else
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="rgba(0, 0, 0, .55)"
            stroke-width="2"
            stroke-linejoin="round"
          >
            <path d="M3 8l9-4 9 4-9 4-9-4z" />
            <path d="M3 8v8l9 4 9-4V8" />
          </svg>
          <label
            v-if="!readOnly"
            class="crate-cover-overlay"
            title="Change cover"
          >
            {{ uploadingCover ? '…' : 'Change cover' }}
            <input
              type="file"
              accept="image/jpeg,image/png"
              class="crate-cover-input"
              @change="onCoverPick"
            >
          </label>
          <button
            v-if="!readOnly && crate.cover_url"
            type="button"
            class="crate-cover-remove"
            title="Remove cover"
            @click="removeCover"
          >
            ×
          </button>
        </div>
        <div class="crate-id">
          <div class="crate-eyebrow">
            {{ readOnly ? `PUBLIC CRATE · by ${crate.owner_username}` : 'CRATE' }}
          </div>
          <input
            v-if="!readOnly"
            v-model="name"
            class="crate-name-input"
            type="text"
            title="Rename crate"
            @change="rename"
            @keydown.enter="$event.target.blur()"
          >
          <div
            v-else
            class="crate-name-static"
          >
            {{ crate.name }}
          </div>
          <div class="crate-stats">
            {{ crate.track_count }} tracks · {{ totalMinutes }} min
          </div>
          <textarea
            v-if="!readOnly"
            v-model="description"
            class="crate-desc-input"
            placeholder="Add a description"
            @change="updateDescription"
          />
          <p
            v-else-if="crate.description"
            class="crate-desc"
          >
            {{ crate.description }}
          </p>
        </div>
        <div class="crate-actions">
          <button
            type="button"
            class="drop-browse"
            :disabled="!tracks.length"
            @click="playAll"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="currentColor"
            >
              <path d="M8 5v14l11-7z" />
            </svg>
            Play All
          </button>
          <button
            type="button"
            class="act-btn"
            @click="exportM3U"
          >
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <path d="M12 3v12" />
              <path d="M7 11l5 5 5-5" />
              <path d="M4 20h16" />
            </svg>
            Export M3U
          </button>
          <button
            type="button"
            class="act-btn"
            title="Serato / Traktor / rekordbox bundle for a USB stick"
            @click="exportDj = true"
          >
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <circle
                cx="12"
                cy="12"
                r="8"
              />
              <circle
                cx="12"
                cy="12"
                r="2"
              />
            </svg>
            Export for DJ
          </button>
          <button
            v-if="readOnly"
            type="button"
            class="act-btn"
            @click="duplicate"
          >
            Duplicate to my crates
          </button>
          <template v-else>
            <button
              type="button"
              class="act-btn"
              title="Toggle public visibility"
              @click="togglePublic"
            >
              <svg
                width="15"
                height="15"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
              >
                <circle
                  cx="12"
                  cy="12"
                  r="9"
                />
                <path d="M3 12h18" />
                <path d="M12 3c2.5 2.5 2.5 15 0 18M12 3c-2.5 2.5-2.5 15 0 18" />
              </svg>
              Public
              <span
                class="pub-pill"
                :class="{'pub-pill-on': crate.public}"
              >
                <span class="pub-knob" />
              </span>
            </button>
            <button
              type="button"
              class="act-icon"
              title="Copy share link"
              @click="share"
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
                <circle
                  cx="18"
                  cy="5"
                  r="2.6"
                />
                <circle
                  cx="6"
                  cy="12"
                  r="2.6"
                />
                <circle
                  cx="18"
                  cy="19"
                  r="2.6"
                />
                <path d="M8.3 10.7l7.4-4.3M8.3 13.3l7.4 4.3" />
              </svg>
            </button>
            <button
              type="button"
              class="act-icon act-danger"
              title="Delete crate"
              @click="destroy"
            >
              <svg
                width="15"
                height="15"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <path d="M4 7h16" />
                <path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
                <path d="M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13" />
              </svg>
            </button>
          </template>
        </div>
      </div>

      <div
        class="crate-drop"
        :class="{'crate-drop-over': dragOver}"
        @dragover.prevent="readOnly || (dragOver = true)"
        @dragleave="dragOver = false"
        @drop.prevent="onDrop"
      >
        <template v-if="tracks.length">
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
            v-for="entry in tracks"
            :key="entry.song.id"
            class="reorder-row"
            :class="{'drop-before': dropBeforeSongId === entry.song.id}"
            :draggable="!readOnly"
            @dragstart="dragStartRow(entry.song, $event)"
            @dragover.prevent="dragOverRow(entry.song)"
            @drop.prevent.stop="dropRow(entry.song, $event)"
            @dragend="dragEndRow"
          >
            <TrackRow
              :song="entry.song"
              :removable="!readOnly"
              @remove="removeTrack"
            />
          </div>
          <button
            v-if="nextCursor"
            type="button"
            class="drop-browse crate-load-more"
            :disabled="loadingMore"
            @click="loadMore"
          >
            {{ loadingMore ? 'Loading…' : 'Load more' }}
          </button>
        </template>
        <div
          v-else
          class="drop-empty"
        >
          <div class="drop-glyph">
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linejoin="round"
            >
              <path d="M3 8l9-4 9 4-9 4-9-4z" />
              <path d="M3 8v8l9 4 9-4V8" />
            </svg>
          </div>
          <div class="drop-title">
            {{ readOnly ? 'This crate is empty' : 'Drag tracks here to build your set' }}
          </div>
          <div
            v-if="!readOnly"
            class="drop-sub"
          >
            Grab any row from New Releases, Charts or Search and drop it onto
            this crate — or onto its name in the sidebar.
          </div>
          <button
            v-if="!readOnly"
            type="button"
            class="drop-browse"
            @click="$router.push('/library')"
          >
            Browse New Releases
          </button>
        </div>
      </div>

      <ExportDjModal
        v-if="exportDj"
        :crate="crate"
        :tracks="tracks"
        :read-only="readOnly"
        @close="exportDj = false"
      />
    </template>
  </section>
</template>

<script>
import axios from 'axios';
import { mapActions } from 'vuex';

import ExportDjModal from '@/components/ExportDjModal.vue';
import TrackRow from '@/components/TrackRow.vue';
import { toast } from '@/utils/toast';

export default {
  name: 'CrateView',
  components: {ExportDjModal, TrackRow},
  props: {
    // Read-only share-link mode: the crate is resolved by token instead of
    // id and every owner action (rename, toggle, export, drop, remove) is
    // hidden.
    shared: {
      type: Boolean,
      default: false,
    },
  },
  data() {
    return {
      // Local copy of the crate name so typing never fights the store.
      name: '',
      description: '',
      dragOver: false,
      errorMessage: '',
      // The crate resolved from a share token (shared mode only); owner
      // mode reads the store's active crate instead.
      sharedCrate: null,
      // Tracks accumulate locally as further pages are loaded (the store's
      // active crate only ever holds the first page from the API).
      loadedTracks: [],
      nextCursor: null,
      loadingMore: false,
      draggingSongId: null,
      dropBeforeSongId: null,
      uploadingCover: false,
      // "Export for DJ" modal (MOO-86): Serato/Traktor/rekordbox USB bundle.
      exportDj: false,
    };
  },
  computed: {
    crateId() {
      return Number(this.$route.params.id);
    },
    crate() {
      if (this.shared) {
        return this.sharedCrate;
      }
      const active = this.$store.getters.stateActiveCrate;
      return active && active.id === this.crateId ? active : null;
    },
    // Read-only whenever this is a share-link view, or the viewer isn't the
    // crate's owner (browsing someone else's public crate by id).
    readOnly() {
      if (this.shared || !this.crate) {
        return this.shared;
      }
      const user = this.$store.getters.stateUser;
      return !user || user.id !== this.crate.owner_id;
    },
    tracks() {
      return this.loadedTracks;
    },
    totalMinutes() {
      return Math.floor(((this.crate && this.crate.total_duration_seconds) || 0) / 60);
    },
    coverSrc() {
      if (!this.crate || !this.crate.cover_url) {
        return null;
      }
      return `${axios.defaults.baseURL}${this.crate.cover_url}`;
    },
    // The 4-quadrant collage fallback when no custom cover is set: a
    // deterministic conic gradient derived from the crate's color. Pure
    // frontend -- no network, no album-art dependency.
    tileStyle() {
      const color = (this.crate && this.crate.color) || 'var(--acc)';
      const boxShadow = `0 6px 20px color-mix(in oklab, ${color} 40%, transparent)`;
      if (this.coverSrc) {
        return {boxShadow};
      }
      const shades = [80, 55, 35, 65];
      const stops = shades
        .map((pct, i) => {
          const mix = i % 2 === 0 ? 'black' : 'white';
          return `color-mix(in oklab, ${color} ${100 - pct}%, ${mix})`;
        })
        .join(', ');
      return {boxShadow, background: `conic-gradient(${stops})`};
    },
  },
  watch: {
    // Covers both /crate/:id and /crate/shared/:token — the same component
    // is reused across the two routes.
    '$route.params': {
      immediate: true,
      handler() {
        this.load();
      },
    },
    // The player's prev/next and auto-advance walk the crate's tracks.
    tracks(entries) {
      if (this.crate) {
        this.setQueue(entries.map(entry => entry.song));
      }
    },
  },
  methods: {
    ...mapActions([
      'addTrackToCrate',
      'deleteCrate',
      'deleteCrateCover',
      'duplicateCrate',
      'fetchCrate',
      'fetchCrateTracksPage',
      'moveCrateTrack',
      'playSong',
      'removeTrackFromCrate',
      'setQueue',
      'updateCrate',
      'uploadCrateCover',
    ]),
    async load() {
      this.errorMessage = '';
      this.loadedTracks = [];
      this.nextCursor = null;
      try {
        let crate;
        if (this.shared) {
          const {data} = await axios.get(`crates/shared/${this.$route.params.token}`);
          this.sharedCrate = data;
          crate = data;
        } else {
          crate = await this.fetchCrate(this.crateId);
          this.name = crate.name;
        }
        this.description = crate.description || '';
        this.loadedTracks = crate.tracks || [];
        this.nextCursor = crate.tracks_next_cursor || null;
      } catch (error) {
        const detail = error.response && error.response.data && error.response.data.detail;
        this.errorMessage =
          (typeof detail === 'string' && detail) || 'Could not load this crate.';
      }
    },
    async loadMore() {
      if (!this.nextCursor || this.loadingMore) {
        return;
      }
      this.loadingMore = true;
      try {
        const page = await this.fetchCrateTracksPage({
          crateId: this.crateId,
          cursor: this.nextCursor,
        });
        this.loadedTracks = this.loadedTracks.concat(page.items);
        this.nextCursor = page.next_cursor;
      } catch (error) {
        toast('Could not load more tracks', 'warn');
      } finally {
        this.loadingMore = false;
      }
    },
    async rename() {
      const name = this.name.trim();
      if (!name || name === this.crate.name) {
        this.name = this.crate.name;
        return;
      }
      try {
        await this.updateCrate({crateId: this.crateId, changes: {name}});
      } catch (error) {
        this.name = this.crate.name;
        toast('Could not rename the crate', 'warn');
      }
    },
    async updateDescription() {
      const description = this.description.trim();
      if (description === (this.crate.description || '')) {
        return;
      }
      try {
        await this.updateCrate({crateId: this.crateId, changes: {description}});
      } catch (error) {
        this.description = this.crate.description || '';
        toast('Could not update the description', 'warn');
      }
    },
    playAll() {
      if (!this.tracks.length) {
        return;
      }
      this.setQueue(this.tracks.map(entry => entry.song));
      this.playSong(this.tracks[0].song);
    },
    async duplicate() {
      try {
        const created = await this.duplicateCrate({crateId: this.crateId});
        this.$router.push(`/crate/${created.id}`);
      } catch (error) {
        toast('Could not duplicate the crate', 'warn');
      }
    },
    onCoverPick(event) {
      const file = event.target.files && event.target.files[0];
      event.target.value = '';
      if (!file) {
        return;
      }
      if (file.size > 2 * 1024 * 1024) {
        toast('Cover must be under 2 MiB', 'warn');
        return;
      }
      this.uploadingCover = true;
      this.uploadCrateCover({crateId: this.crateId, file})
        .catch(() => toast('Could not upload the cover', 'warn'))
        .finally(() => {
          this.uploadingCover = false;
        });
    },
    removeCover() {
      this.deleteCrateCover(this.crateId).catch(() => {
        toast('Could not remove the cover', 'warn');
      });
    },
    async togglePublic() {
      const makePublic = !this.crate.public;
      try {
        await this.updateCrate({crateId: this.crateId, changes: {public: makePublic}});
        toast(
          makePublic
            ? 'Crate is now public — anyone with the link can view'
            : 'Crate set to private'
        );
      } catch (error) {
        toast('Could not update the crate', 'warn');
      }
    },
    async share() {
      const link = `${window.location.origin}/crate/shared/${this.crate.share_token}`;
      try {
        await navigator.clipboard.writeText(link);
        toast('Share link copied to clipboard');
      } catch (error) {
        // Clipboard access needs a secure context; fall back to showing the
        // link so it can be copied by hand.
        window.prompt('Copy the share link:', link);
      }
    },
    async exportM3U() {
      try {
        const response = await axios.get(`crates/${this.crateId}/export.m3u`, {
          responseType: 'blob',
        });
        const filename = `${this.crate.name}.m3u`.replace(/[\\/:*?"<>|\r\n]/g, '_');
        const url = URL.createObjectURL(response.data);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
        toast(`Exported ${filename}`);
      } catch (error) {
        toast('Export failed', 'warn');
      }
    },
    async destroy() {
      const sure = window.confirm(
        `Delete "${this.crate.name}"? The tracks stay in the library.`
      );
      if (!sure) {
        return;
      }
      try {
        await this.deleteCrate(this.crateId);
        this.$router.push('/library');
      } catch (error) {
        toast('Could not delete the crate', 'warn');
      }
    },
    onDrop(event) {
      this.dragOver = false;
      if (this.readOnly) {
        return;
      }
      const songId = Number(event.dataTransfer.getData('text/plain'));
      if (songId) {
        this.addTrackToCrate({crateId: this.crateId, songId});
      }
    },
    removeTrack(song) {
      this.removeTrackFromCrate({crateId: this.crateId, songId: song.id}).catch(() => {
        toast('Could not remove the track', 'warn');
      });
    },
    // Single-track drag reorder within the list (owner only). Uses a
    // dedicated dataTransfer type so it never triggers the crate's own
    // add-track drop zone.
    dragStartRow(song, event) {
      this.draggingSongId = song.id;
      event.dataTransfer.setData('application/x-crate-reorder', String(song.id));
      event.dataTransfer.effectAllowed = 'move';
    },
    dragOverRow(song) {
      if (this.draggingSongId != null && this.draggingSongId !== song.id) {
        this.dropBeforeSongId = song.id;
      }
    },
    dragEndRow() {
      this.draggingSongId = null;
      this.dropBeforeSongId = null;
    },
    async dropRow(targetSong, event) {
      const raw = event.dataTransfer.getData('application/x-crate-reorder');
      const songId = Number(raw);
      this.dropBeforeSongId = null;
      this.draggingSongId = null;
      if (!songId || songId === targetSong.id) {
        return;
      }
      const index = this.tracks.findIndex(entry => entry.song.id === targetSong.id);
      const afterSongId = index > 0 ? this.tracks[index - 1].song.id : null;
      if (afterSongId === songId) {
        return;
      }
      try {
        await this.moveCrateTrack({crateId: this.crateId, songId, afterSongId});
        await this.load();
      } catch (error) {
        toast('Could not reorder', 'warn');
      }
    },
  },
};
</script>

<style scoped>
.crate-error {
  font: 400 12.5px var(--font-ui);
  color: var(--danger);
  margin: 0;
}

.crate-head {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 18px;
}

.crate-tile {
  position: relative;
  width: 96px;
  height: 96px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: none;
  overflow: hidden;
}

.crate-cover-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.crate-cover-overlay {
  position: absolute;
  inset: auto 0 0 0;
  padding: 6px 0;
  text-align: center;
  background: rgba(0, 0, 0, .6);
  color: #fff;
  font: 600 10px var(--font-ui);
  cursor: pointer;
  opacity: 0;
  transition: opacity .15s ease;
}

.crate-tile-owner:hover .crate-cover-overlay {
  opacity: 1;
}

.crate-cover-input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}

.crate-cover-remove {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: none;
  background: rgba(0, 0, 0, .6);
  color: #fff;
  line-height: 1;
  cursor: pointer;
}

.crate-id {
  flex: 1;
  min-width: 0;
}

.crate-eyebrow {
  font: 600 10px var(--font-mono);
  letter-spacing: .1em;
  color: var(--dim-2);
  margin-bottom: 3px;
}

.crate-name-input {
  width: 100%;
  max-width: 440px;
  background: none;
  border: none;
  color: var(--txt);
  font: 700 24px/1.1 var(--font-disp);
  padding: 0;
}

.crate-name-input:focus {
  outline: none;
}

.crate-name-static {
  color: var(--txt);
  font: 700 24px/1.1 var(--font-disp);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.crate-stats {
  font: 400 13px var(--font-ui);
  color: var(--muted);
  margin-top: 3px;
}

.crate-desc-input {
  display: block;
  width: 100%;
  max-width: 520px;
  resize: vertical;
  margin-top: 6px;
  background: none;
  border: none;
  color: var(--muted);
  font: 400 13.5px var(--font-ui);
  padding: 0;
  min-height: 18px;
}

.crate-desc-input:focus {
  outline: none;
}

.crate-desc {
  margin: 6px 0 0;
  color: var(--muted);
  font: 400 13.5px var(--font-ui);
}

.crate-actions {
  display: flex;
  align-items: center;
  gap: 9px;
  flex: none;
}

.act-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 38px;
  padding: 0 12px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line-strong);
  background: rgba(255, 255, 255, .03);
  cursor: pointer;
  color: var(--txt-2);
  font: 600 12px var(--font-ui);
  transition: border-color .15s ease, color .15s ease;
  box-sizing: border-box;
}

.act-btn:hover {
  border-color: rgba(255, 255, 255, .2);
  color: var(--txt);
}

.act-icon {
  width: 38px;
  height: 38px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line-strong);
  background: rgba(255, 255, 255, .03);
  cursor: pointer;
  color: var(--txt-2);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: border-color .15s ease, color .15s ease;
  box-sizing: border-box;
}

.act-icon:hover {
  border-color: rgba(255, 255, 255, .2);
  color: var(--txt);
}

.act-danger:hover {
  border-color: color-mix(in oklab, var(--danger) 55%, transparent);
  color: var(--danger);
}

.pub-pill {
  width: 32px;
  height: 19px;
  border-radius: 11px;
  background: rgba(255, 255, 255, .1);
  display: flex;
  align-items: center;
  padding: 0 2px;
  justify-content: flex-start;
  box-sizing: border-box;
}

.pub-pill-on {
  background: color-mix(in oklab, var(--acc) 62%, transparent);
  justify-content: flex-end;
}

.pub-knob {
  width: 15px;
  height: 15px;
  border-radius: 50%;
  background: #6b7480;
}

.pub-pill-on .pub-knob {
  background: var(--acc);
}

.crate-drop {
  border: 1px solid var(--line);
  border-radius: 13px;
  overflow: hidden;
  background: var(--panel);
  transition: background .15s ease;
}

.crate-drop-over {
  border: 2px dashed color-mix(in oklab, var(--acc) 55%, transparent);
  background: color-mix(in oklab, var(--acc) 7%, transparent);
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

.drop-empty {
  padding: 60px 24px;
  text-align: center;
}

.drop-glyph {
  width: 52px;
  height: 52px;
  border-radius: 13px;
  background: rgba(255, 255, 255, .04);
  border: 1px solid rgba(255, 255, 255, .09);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 16px;
  color: var(--dim-2);
}

.drop-title {
  font: 600 16px var(--font-disp);
  color: var(--txt-2);
  margin-bottom: 6px;
}

.drop-sub {
  color: var(--dim-2);
  font: 400 13.5px var(--font-ui);
  margin-bottom: 18px;
}

.drop-browse {
  height: 38px;
  padding: 0 16px;
  border-radius: var(--r-ctl);
  border: none;
  background: var(--acc);
  color: var(--acc-ink);
  font: 600 13px var(--font-ui);
  cursor: pointer;
  transition: filter .15s ease;
}

.drop-browse:hover {
  filter: brightness(1.1);
}

.drop-browse:disabled {
  opacity: .5;
  cursor: default;
}

.crate-load-more {
  display: block;
  margin: 14px auto;
  background: rgba(255, 255, 255, .06);
  color: var(--txt-2);
}

.reorder-row {
  border-top: 2px solid transparent;
}

.reorder-row.drop-before {
  border-top: 2px solid var(--acc);
}
</style>
