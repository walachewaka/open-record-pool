<template>
  <section>
    <div class="ac-toolbar">
      <div class="ac-search">
        <span class="ac-search-icon">
          <svg
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.9"
            stroke-linecap="round"
          >
            <circle
              cx="11"
              cy="11"
              r="7"
            />
            <path d="M20 20l-3.6-3.6" />
          </svg>
        </span>
        <input
          v-model="q"
          type="text"
          placeholder="Search tracks…"
        >
      </div>
      <SegmentedControl
        v-model="statusFilter"
        :options="statusFilters"
      />
      <button
        v-if="perms.upload_tracks"
        type="button"
        class="ac-upload-btn"
        @click="openUpload"
      >
        <svg
          width="15"
          height="15"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2.1"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d="M12 15V4" />
          <path d="M7 9l5-5 5 5" />
          <path d="M4 20h16" />
        </svg>
        Upload tracks
      </button>
    </div>

    <p
      v-if="errorMessage"
      class="ac-error"
    >
      {{ errorMessage }}
    </p>

    <!-- Selection bar (batch tag edit) -->
    <div
      v-if="selected.length"
      class="ac-selbar"
    >
      <span class="ac-selcount">{{ selected.length }} selected</span>
      <button
        type="button"
        class="ac-selclear"
        @click="selected = []"
      >
        Clear
      </button>
      <button
        type="button"
        class="ac-primary ac-selbatch"
        @click="openBatch"
      >
        Batch edit tags
      </button>
    </div>

    <!-- Undo bar for the last batch write -->
    <div
      v-if="lastBatch"
      class="ac-undobar"
    >
      <span>Updated {{ lastBatch.updated }} track(s) in a batch.</span>
      <button
        type="button"
        class="ac-undo-btn"
        @click="undoBatch"
      >
        Undo batch
      </button>
    </div>

    <div
      v-if="!loading && !items.length"
      class="ac-none"
    >
      No tracks match those filters.
    </div>
    <div
      v-else
      class="ac-panel"
    >
      <div class="ac-head">
        <span>
          <input
            type="checkbox"
            :checked="allSelected"
            @change="toggleAll"
          >
        </span>
        <span>Track</span>
        <span>Genre</span>
        <span class="ac-h-c">Key / BPM</span>
        <span class="ac-h-r">Downloads</span>
        <span>Status</span>
        <span class="ac-h-r">Edit</span>
      </div>
      <div
        v-for="track in items"
        :key="track.id"
        class="ac-row"
      >
        <div>
          <input
            type="checkbox"
            :checked="selected.includes(track.id)"
            @change="toggleOne(track.id)"
          >
        </div>
        <div class="ac-track">
          <div
            class="ac-cover"
            :style="{background: tintForId(track.id)}"
          >
            {{ initialsFor(track.title || track.artist) }}
          </div>
          <div class="ac-track-meta">
            <div class="ac-title">
              {{ track.title || 'Untitled' }}
            </div>
            <div class="ac-sub">
              {{ track.artist || 'Unknown artist' }} ·
              {{ track.source === 'upload' ? `upload by ${track.uploaded_by_username || '—'}` : 'library' }}
            </div>
          </div>
        </div>
        <div class="ac-genre">
          {{ track.genre || '—' }}
        </div>
        <div class="ac-keybpm">
          <span class="ac-key">{{ track.camelot_key || track.musical_key || '—' }}</span>
          <span class="ac-sep">·</span>
          <span class="ac-bpm">{{ track.bpm == null ? '—' : Math.round(track.bpm) }}</span>
        </div>
        <div class="ac-dls">
          {{ fmtNum(track.download_count) }}
        </div>
        <div>
          <button
            type="button"
            class="ac-pill"
            :style="{background: statusBg(track.status), color: statusColor(track.status)}"
            :title="track.status === 'published' ? 'Unpublish (back to draft)' : 'Publish'"
            @click="toggleStatus(track)"
          >
            <span
              class="ac-pill-dot"
              :style="{background: statusColor(track.status)}"
            />
            {{ capitalize(track.status) }}
          </button>
        </div>
        <div class="ac-edit-cell">
          <button
            type="button"
            class="ac-edit-btn"
            title="Edit metadata"
            @click="openEdit(track)"
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
              <path d="M4 20h4L18 10l-4-4L4 16v4z" />
              <path d="M13 7l4 4" />
            </svg>
          </button>
        </div>
      </div>
    </div>

    <!-- Upload modal -->
    <div
      v-if="upload.open"
      class="ac-modal-backdrop"
      @click="upload.open = false"
    >
      <div
        class="ac-modal"
        @click.stop
      >
        <div class="ac-modal-head">
          <div class="ac-modal-title">
            Upload tracks
          </div>
          <button
            type="button"
            class="ac-x"
            @click="upload.open = false"
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
        <div class="ac-modal-body">
          <div
            class="ac-dropzone"
            :class="{'ac-dropzone-over': upload.dragOver}"
            @click="$refs.fileInput.click()"
            @dragover.prevent="upload.dragOver = true"
            @dragleave="upload.dragOver = false"
            @drop.prevent="onDrop"
          >
            <div class="ac-drop-icon">
              <svg
                width="22"
                height="22"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <path d="M12 15V4" />
                <path d="M7 9l5-5 5 5" />
                <path d="M4 20h16" />
              </svg>
            </div>
            <div class="ac-drop-title">
              {{ upload.file ? upload.file.name : 'Drop an audio file here' }}
            </div>
            <div class="ac-drop-sub">
              {{ upload.file ? 'Click to pick a different file' : 'MP3 · or click to browse' }}
            </div>
            <input
              ref="fileInput"
              type="file"
              accept="audio/*,.mp3,.wav"
              class="ac-file-input"
              @change="onPick"
            >
          </div>
          <div class="ac-modal-grid">
            <div class="ac-span-2">
              <label class="ac-label">TITLE</label>
              <input
                v-model="upload.title"
                type="text"
                placeholder="Track title (defaults to the file's tags)"
              >
            </div>
            <div class="ac-span-2">
              <label class="ac-label">ARTIST</label>
              <input
                v-model="upload.artist"
                type="text"
                placeholder="Artist"
              >
            </div>
            <div>
              <label class="ac-label">GENRE</label>
              <input
                v-model="upload.genre"
                type="text"
                placeholder="Genre"
              >
            </div>
            <div class="ac-half-grid">
              <div>
                <label class="ac-label">BPM</label>
                <input
                  v-model="upload.bpm"
                  type="number"
                  class="ac-mono"
                  placeholder="124"
                >
              </div>
              <div>
                <label class="ac-label">KEY</label>
                <input
                  v-model="upload.key"
                  type="text"
                  class="ac-mono"
                  placeholder="8A / Am"
                >
              </div>
            </div>
          </div>
          <label class="ac-approval">
            <input
              v-model="upload.requireApproval"
              type="checkbox"
            >
            Require approval before this appears in the pool
          </label>
        </div>
        <div class="ac-modal-foot">
          <button
            type="button"
            class="ac-cancel"
            @click="upload.open = false"
          >
            Cancel
          </button>
          <button
            type="button"
            class="ac-primary"
            :disabled="!upload.file || upload.busy"
            @click="submitUpload"
          >
            {{ upload.busy ? 'Uploading…' : 'Upload & queue' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Batch tag edit modal -->
    <div
      v-if="batch.open"
      class="ac-modal-backdrop"
      @click="batch.open = false"
    >
      <div
        class="ac-modal"
        @click.stop
      >
        <div class="ac-modal-head">
          <div class="ac-modal-title">
            Batch edit · {{ selected.length }} tracks
          </div>
          <button
            type="button"
            class="ac-x"
            @click="batch.open = false"
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
        <div class="ac-modal-body">
          <div class="ac-modal-grid">
            <div
              v-for="field in batchFields"
              :key="field.key"
              :class="{'ac-span-2': field.wide}"
            >
              <label class="ac-label">{{ field.label }}</label>
              <input
                v-model="batch.fields[field.key]"
                :type="field.type || 'text'"
                placeholder="Leave blank to keep"
              >
            </div>
          </div>
          <div class="ac-drawer-note">
            Only the fields you fill in are written to every selected track.
          </div>
        </div>
        <div class="ac-modal-foot">
          <button
            type="button"
            class="ac-cancel"
            @click="batch.open = false"
          >
            Cancel
          </button>
          <button
            type="button"
            class="ac-primary"
            :disabled="batch.busy"
            @click="submitBatch"
          >
            {{ batch.busy ? 'Saving…' : 'Apply to selection' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Metadata editor drawer -->
    <template v-if="edit">
      <div
        class="ac-backdrop"
        @click="edit = null"
      />
      <div class="ac-drawer">
        <div class="ac-drawer-head">
          <div class="ac-drawer-title">
            Edit metadata
          </div>
          <button
            type="button"
            class="ac-x"
            @click="edit = null"
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
        <div class="ac-drawer-body">
          <div class="ac-drawer-summary">
            <div
              class="ac-cover ac-cover-lg"
              :style="{background: tintForId(edit.id)}"
            >
              {{ initialsFor(edit.title || edit.artist) }}
            </div>
            <div class="ac-drawer-summary-meta">
              <div class="ac-drawer-name">
                {{ edit.title || 'Untitled' }}
              </div>
              <div class="ac-sub">
                {{ edit.artist || 'Unknown artist' }}
              </div>
            </div>
          </div>

          <SegmentedControl
            v-model="tab"
            :options="tabs"
          />

          <!-- Fields -->
          <div
            v-if="tab === 'fields'"
            class="ac-fields ac-tabpane"
          >
            <div
              v-for="field in editFields"
              :key="field.key"
            >
              <label class="ac-label">
                {{ field.label }}
                <span
                  v-if="lockOf(field.key)"
                  class="ac-prov"
                  :class="{'ac-prov-manual': lockOf(field.key) === 'manual'}"
                >{{ lockOf(field.key) }}</span>
              </label>
              <textarea
                v-if="field.type === 'textarea'"
                v-model="edit[field.key]"
                rows="3"
              />
              <input
                v-else
                v-model="edit[field.key]"
                :type="field.type || 'text'"
                :class="field.mono ? 'ac-mono' : ''"
              >
            </div>

            <div>
              <label class="ac-label">CUSTOM TXXX FRAMES</label>
              <div
                v-for="(row, index) in edit.txxxRows"
                :key="index"
                class="ac-txxx-row"
              >
                <input
                  v-model="row.key"
                  type="text"
                  placeholder="Description"
                >
                <input
                  v-model="row.value"
                  type="text"
                  placeholder="Value"
                >
                <button
                  type="button"
                  class="ac-txxx-del"
                  title="Remove"
                  @click="edit.txxxRows.splice(index, 1)"
                >
                  ×
                </button>
              </div>
              <button
                type="button"
                class="ac-ghost"
                @click="edit.txxxRows.push({key: '', value: ''})"
              >
                + Add frame
              </button>
            </div>
          </div>

          <!-- Artwork -->
          <div
            v-else-if="tab === 'artwork'"
            class="ac-tabpane"
          >
            <div class="ac-art-current">
              <img
                v-if="hasArtwork"
                :src="artworkUrl(edit.id)"
                class="ac-art-img"
                alt="Cover"
              >
              <div
                v-else
                class="ac-art-empty"
              >
                No cover
              </div>
              <div class="ac-art-side">
                <div class="ac-sub">
                  {{ hasArtwork
                    ? `${edit.artwork_source} · ${edit.artwork_width}×${edit.artwork_height}`
                    : 'This track has no embedded cover.' }}
                </div>
                <button
                  v-if="hasArtwork"
                  type="button"
                  class="ac-ghost ac-ghost-danger"
                  @click="removeArtwork"
                >
                  Remove cover
                </button>
              </div>
            </div>

            <div
              class="ac-dropzone ac-dropzone-sm"
              :class="{'ac-dropzone-over': art.dragOver}"
              @click="$refs.artInput.click()"
              @dragover.prevent="art.dragOver = true"
              @dragleave="art.dragOver = false"
              @drop.prevent="onArtDrop"
            >
              <div class="ac-drop-title">
                {{ art.busy ? 'Uploading…' : 'Drop a JPEG/PNG here' }}
              </div>
              <div class="ac-drop-sub">
                Max 10 MiB · click to browse
              </div>
              <input
                ref="artInput"
                type="file"
                accept="image/jpeg,image/png"
                class="ac-file-input"
                @change="onArtPick"
              >
            </div>

            <div class="ac-section-label">
              CANDIDATES
            </div>
            <div
              v-if="!art.candidates.length"
              class="ac-sub"
            >
              No candidate covers found.
            </div>
            <div
              v-else
              class="ac-cand-grid"
            >
              <button
                v-for="(candidate, index) in art.candidates"
                :key="index"
                type="button"
                class="ac-cand"
                @click="selectArtwork(candidate)"
              >
                <img
                  :src="candidate.url"
                  class="ac-cand-img"
                  alt="Candidate cover"
                >
                <span class="ac-cand-badge">{{ candidate.origin }}</span>
                <span class="ac-cand-dim">{{ candidate.width }}×{{ candidate.height }}</span>
              </button>
            </div>
          </div>

          <!-- Suggestions -->
          <div
            v-else-if="tab === 'suggestions'"
            class="ac-tabpane"
          >
            <div
              v-if="!suggestions.items.length"
              class="ac-sub"
            >
              {{ suggestions.status === 'loading'
                ? 'Loading…'
                : 'No suggestions for this track.' }}
            </div>
            <template v-else>
              <div class="ac-sugg-head">
                <span class="ac-sub">
                  {{ suggestions.provider }} · confidence
                  {{ Math.round((suggestions.confidence || 0) * 100) }}%
                </span>
                <button
                  type="button"
                  class="ac-ghost"
                  @click="applyAllSuggestions"
                >
                  Apply all
                </button>
              </div>
              <div
                v-for="item in suggestions.items"
                :key="item.field"
                class="ac-sugg-row"
              >
                <div class="ac-sugg-field">
                  {{ item.field }}
                  <span
                    v-if="item.locked"
                    class="ac-lock"
                    title="Manually locked"
                  >🔒</span>
                </div>
                <div class="ac-sugg-values">
                  <span class="ac-sugg-old">{{ item.current || '—' }}</span>
                  <span class="ac-sugg-arrow">→</span>
                  <span class="ac-sugg-new">{{ item.suggested }}</span>
                </div>
                <button
                  type="button"
                  class="ac-ghost"
                  :disabled="item.locked"
                  @click="applySuggestion(item)"
                >
                  Apply
                </button>
              </div>
            </template>
          </div>

          <!-- History -->
          <div
            v-else
            class="ac-tabpane"
          >
            <div
              v-if="!revisions.length"
              class="ac-sub"
            >
              No edits recorded yet.
            </div>
            <div
              v-for="revision in revisions"
              :key="revision.id"
              class="ac-rev"
            >
              <div class="ac-rev-top">
                <span class="ac-rev-who">{{ revision.editor_username || 'system' }}</span>
                <span class="ac-rev-src">{{ revision.source }}</span>
                <span class="ac-rev-when">{{ relativeTime(revision.created_at) }}</span>
              </div>
              <div class="ac-rev-chips">
                <span
                  v-for="field in Object.keys(revision.changes || {})"
                  :key="field"
                  class="ac-chip"
                >{{ field }}</span>
              </div>
              <button
                type="button"
                class="ac-ghost"
                @click="rollback(revision)"
              >
                Undo
              </button>
            </div>
          </div>

          <div
            v-if="tab === 'fields'"
            class="ac-drawer-note"
          >
            Edits apply to the database only — the file on disk is never rewritten.
          </div>
        </div>
        <div
          v-if="tab === 'fields'"
          class="ac-drawer-foot"
        >
          <button
            type="button"
            class="ac-cancel ac-flex"
            @click="edit = null"
          >
            Cancel
          </button>
          <button
            type="button"
            class="ac-primary ac-flex"
            @click="saveEdit"
          >
            Save changes
          </button>
        </div>
      </div>
    </template>
  </section>
</template>

<script>
import axios from 'axios';

import SegmentedControl from '@/components/admin/SegmentedControl.vue';
import { toast } from '@/utils/toast';
import {
  capitalize,
  fmtNum,
  initialsFor,
  relativeTime,
  statusBg,
  statusColor,
  tintForId,
} from '@/utils/format';

const EMPTY_UPLOAD = {
  open: false,
  file: null,
  dragOver: false,
  busy: false,
  title: '',
  artist: '',
  genre: '',
  bpm: '',
  key: '',
  requireApproval: true,
};

// Every ID3 field the editor writes, in drawer order.
const EDIT_FIELDS = [
  {key: 'title', label: 'TITLE'},
  {key: 'artist', label: 'ARTIST'},
  {key: 'album', label: 'ALBUM'},
  {key: 'album_artist', label: 'ALBUM ARTIST'},
  {key: 'composer', label: 'COMPOSER'},
  {key: 'genre', label: 'GENRE'},
  {key: 'label', label: 'LABEL'},
  {key: 'isrc', label: 'ISRC', mono: true},
  {key: 'comment', label: 'COMMENT', type: 'textarea'},
  {key: 'year', label: 'YEAR', type: 'number', mono: true},
  {key: 'track_number', label: 'TRACK NUMBER', type: 'number', mono: true},
  {key: 'disc_number', label: 'DISC NUMBER', type: 'number', mono: true},
  {key: 'bpm', label: 'BPM', type: 'number', mono: true},
  {key: 'musical_key', label: 'KEY', mono: true},
];

const NUMERIC_FIELDS = ['year', 'track_number', 'disc_number', 'bpm'];

// The backend only accepts these on the batch endpoint.
const BATCH_FIELDS = [
  {key: 'artist', label: 'ARTIST', wide: true},
  {key: 'album', label: 'ALBUM', wide: true},
  {key: 'album_artist', label: 'ALBUM ARTIST', wide: true},
  {key: 'genre', label: 'GENRE'},
  {key: 'label', label: 'LABEL'},
  {key: 'year', label: 'YEAR', type: 'number'},
  {key: 'comment', label: 'COMMENT', wide: true},
];

function emptyBatchFields() {
  return BATCH_FIELDS.reduce((fields, field) => ({...fields, [field.key]: ''}), {});
}

export default {
  name: 'AdminContent',
  components: {
    SegmentedControl,
  },
  data() {
    return {
      items: [],
      q: '',
      statusFilter: '',
      loading: true,
      errorMessage: '',
      upload: {...EMPTY_UPLOAD},
      edit: null,
      tab: 'fields',
      editFields: EDIT_FIELDS,
      batchFields: BATCH_FIELDS,
      art: {candidates: [], dragOver: false, busy: false, bust: 0},
      suggestions: {provider: '', status: '', confidence: 0, items: []},
      revisions: [],
      selected: [],
      batch: {open: false, busy: false, fields: emptyBatchFields()},
      lastBatch: null,
      searchDebounce: null,
    };
  },
  computed: {
    perms() {
      return this.$store.getters.userPermissions;
    },
    statusFilters() {
      return [
        {value: '', label: 'All'},
        {value: 'published', label: 'Published'},
        {value: 'draft', label: 'Draft'},
        {value: 'pending', label: 'Pending'},
        {value: 'rejected', label: 'Rejected'},
      ];
    },
    tabs() {
      return [
        {value: 'fields', label: 'Fields'},
        {value: 'artwork', label: 'Artwork'},
        {value: 'suggestions', label: 'Suggestions'},
        {value: 'history', label: 'History'},
      ];
    },
    allSelected() {
      return !!this.items.length && this.selected.length === this.items.length;
    },
    hasArtwork() {
      return !!(this.edit && this.edit.artwork_source);
    },
  },
  watch: {
    q() {
      clearTimeout(this.searchDebounce);
      this.searchDebounce = setTimeout(() => this.fetchContent(), 300);
    },
    statusFilter() {
      this.fetchContent();
    },
    tab(value) {
      if (value === 'artwork') {
        this.fetchCandidates();
      } else if (value === 'suggestions') {
        this.fetchSuggestions();
      } else if (value === 'history') {
        this.fetchRevisions();
      }
    },
  },
  created() {
    return this.fetchContent();
  },
  beforeUnmount() {
    clearTimeout(this.searchDebounce);
  },
  methods: {
    capitalize,
    fmtNum,
    initialsFor,
    relativeTime,
    statusBg,
    statusColor,
    tintForId,
    async fetchContent() {
      this.loading = true;
      this.errorMessage = '';
      try {
        const {data} = await axios.get('admin/content', {
          params: {
            q: this.q.trim() || undefined,
            status: this.statusFilter || undefined,
            page: 1,
            page_size: 300,
          },
        });
        this.items = data.items;
        this.selected = this.selected.filter(
          id => this.items.some(track => track.id === id)
        );
      } catch (error) {
        this.errorMessage = this.detailOf(error, 'Could not load the catalog.');
      } finally {
        this.loading = false;
      }
    },
    detailOf(error, fallback) {
      const detail = error.response && error.response.data && error.response.data.detail;
      return (typeof detail === 'string' && detail) || fallback;
    },
    applyUpdate(updated) {
      this.items = this.items.map(track => (track.id === updated.id ? updated : track));
      if (this.edit && this.edit.id === updated.id) {
        // Keep the drawer's own draft text, but refresh the server-owned facts.
        this.edit.field_locks = updated.field_locks;
        this.edit.artwork_source = updated.artwork_source;
        this.edit.artwork_width = updated.artwork_width;
        this.edit.artwork_height = updated.artwork_height;
        this.art.bust += 1;
      }
    },
    async toggleStatus(track) {
      const next = track.status === 'published' ? 'draft' : 'published';
      try {
        const {data} = await axios.patch(`admin/content/${track.id}/status`, {status: next});
        this.applyUpdate(data);
        toast(next === 'published' ? 'Published' : 'Unpublished');
        // Publishing a pending track empties part of the moderation queue.
        this.$store.dispatch('fetchPendingCount');
      } catch (error) {
        toast(this.detailOf(error, 'Could not change the status.'), 'warn');
      }
    },
    toggleOne(id) {
      this.selected = this.selected.includes(id)
        ? this.selected.filter(value => value !== id)
        : [...this.selected, id];
    },
    toggleAll() {
      this.selected = this.allSelected ? [] : this.items.map(track => track.id);
    },
    lockOf(field) {
      const locks = (this.edit && this.edit.field_locks) || {};
      return locks[field] || '';
    },
    artworkUrl(id) {
      return `${axios.defaults.baseURL}/songs/${id}/artwork?v=${this.art.bust}`;
    },
    openEdit(track) {
      const txxx = track.txxx_frames || {};
      this.edit = {
        ...track,
        txxxRows: Object.keys(txxx).map(key => ({key, value: txxx[key]})),
      };
      this.tab = 'fields';
      this.art = {candidates: [], dragOver: false, busy: false, bust: Date.now()};
      this.suggestions = {provider: '', status: '', confidence: 0, items: []};
      this.revisions = [];
    },
    async saveEdit() {
      const payload = {};
      EDIT_FIELDS.forEach(({key}) => {
        const value = this.edit[key];
        if (NUMERIC_FIELDS.includes(key)) {
          payload[key] = value === '' || value == null ? null : Number(value);
        } else {
          payload[key] = value || null;
        }
      });
      payload.txxx_frames = this.edit.txxxRows.reduce((frames, row) => {
        if (row.key.trim()) {
          frames[row.key.trim()] = row.value;
        }
        return frames;
      }, {});
      try {
        const {data} = await axios.patch(`admin/content/${this.edit.id}`, payload);
        this.applyUpdate(data);
        this.edit = null;
        toast('Metadata saved');
      } catch (error) {
        toast(this.detailOf(error, 'Could not save the metadata.'), 'warn');
      }
    },
    async patchField(field, value) {
      const {data} = await axios.patch(`admin/content/${this.edit.id}`, {[field]: value});
      this.applyUpdate(data);
      if (this.edit) {
        this.edit[field] = data[field];
      }
    },
    // --- Artwork ---
    async fetchCandidates() {
      try {
        const {data} = await axios.get(`admin/content/${this.edit.id}/artwork/candidates`);
        this.art.candidates = data.items;
      } catch (error) {
        this.art.candidates = [];
      }
    },
    onArtPick(event) {
      const file = event.target.files && event.target.files[0];
      if (file) {
        this.uploadArtwork(file);
      }
    },
    onArtDrop(event) {
      this.art.dragOver = false;
      const file = event.dataTransfer.files && event.dataTransfer.files[0];
      if (file) {
        this.uploadArtwork(file);
      }
    },
    async uploadArtwork(file) {
      const form = new FormData();
      form.append('file', file);
      this.art.busy = true;
      try {
        const {data} = await axios.put(`admin/content/${this.edit.id}/artwork`, form);
        this.applyUpdate(data);
        toast('Cover updated');
      } catch (error) {
        const status = error.response && error.response.status;
        toast(
          status === 413
            ? 'That image is larger than 10 MiB.'
            : this.detailOf(error, 'Could not upload that cover.'),
          'warn'
        );
      } finally {
        this.art.busy = false;
      }
    },
    async selectArtwork(candidate) {
      try {
        const {data} = await axios.post(`admin/content/${this.edit.id}/artwork/select`, {
          origin: candidate.origin,
          url: candidate.url,
        });
        this.applyUpdate(data);
        toast('Cover updated');
      } catch (error) {
        toast(this.detailOf(error, 'Could not select that cover.'), 'warn');
      }
    },
    async removeArtwork() {
      try {
        const {data} = await axios.delete(`admin/content/${this.edit.id}/artwork`);
        this.applyUpdate(data);
        toast('Cover removed');
      } catch (error) {
        toast(this.detailOf(error, 'Could not remove the cover.'), 'warn');
      }
    },
    // --- Suggestions ---
    async fetchSuggestions() {
      this.suggestions = {provider: '', status: 'loading', confidence: 0, items: []};
      try {
        const {data} = await axios.get(`admin/content/${this.edit.id}/suggestions`);
        this.suggestions = data;
      } catch (error) {
        this.suggestions = {provider: '', status: '', confidence: 0, items: []};
      }
    },
    async applySuggestion(item) {
      try {
        await this.patchField(item.field, item.suggested);
        this.suggestions.items = this.suggestions.items.filter(
          other => other.field !== item.field
        );
        toast(`${item.field} applied`);
      } catch (error) {
        toast(this.detailOf(error, 'Could not apply that suggestion.'), 'warn');
      }
    },
    async applyAllSuggestions() {
      const open = this.suggestions.items.filter(item => !item.locked);
      if (!open.length) {
        return;
      }
      const payload = open.reduce(
        (fields, item) => ({...fields, [item.field]: item.suggested}),
        {}
      );
      try {
        const {data} = await axios.patch(`admin/content/${this.edit.id}`, payload);
        this.applyUpdate(data);
        Object.keys(payload).forEach((field) => {
          this.edit[field] = data[field];
        });
        this.suggestions.items = this.suggestions.items.filter(item => item.locked);
        toast(`${open.length} field(s) applied`);
      } catch (error) {
        toast(this.detailOf(error, 'Could not apply the suggestions.'), 'warn');
      }
    },
    // --- History ---
    async fetchRevisions() {
      try {
        const {data} = await axios.get(`admin/content/${this.edit.id}/revisions`, {
          params: {limit: 50},
        });
        this.revisions = data.items;
      } catch (error) {
        this.revisions = [];
      }
    },
    async rollback(revision) {
      try {
        const {data} = await axios.post(
          `admin/content/${this.edit.id}/revisions/${revision.id}/rollback`
        );
        this.applyUpdate(data);
        EDIT_FIELDS.forEach(({key}) => {
          this.edit[key] = data[key];
        });
        await this.fetchRevisions();
        toast('Edit undone');
      } catch (error) {
        toast(this.detailOf(error, 'Could not undo that edit.'), 'warn');
      }
    },
    // --- Batch ---
    openBatch() {
      this.batch = {open: true, busy: false, fields: emptyBatchFields()};
    },
    async submitBatch() {
      const fields = {};
      BATCH_FIELDS.forEach(({key}) => {
        const value = String(this.batch.fields[key] || '').trim();
        if (value) {
          fields[key] = key === 'year' ? Number(value) : value;
        }
      });
      if (!Object.keys(fields).length) {
        toast('Fill in at least one field.', 'warn');
        return;
      }
      this.batch.busy = true;
      try {
        const {data} = await axios.post('admin/content/tags/batch', {
          song_ids: this.selected,
          fields,
        });
        this.batch.open = false;
        this.selected = [];
        this.lastBatch = data;
        toast(`${data.updated} track(s) updated`);
        await this.fetchContent();
      } catch (error) {
        toast(this.detailOf(error, 'The batch edit failed.'), 'warn');
      } finally {
        this.batch.busy = false;
      }
    },
    async undoBatch() {
      try {
        const {data} = await axios.post(
          `admin/content/batches/${this.lastBatch.batch_id}/rollback`
        );
        this.lastBatch = null;
        toast(`${data.undone} track(s) restored`);
        await this.fetchContent();
      } catch (error) {
        toast(this.detailOf(error, 'Could not undo the batch.'), 'warn');
      }
    },
    // --- Upload ---
    openUpload() {
      this.upload = {...EMPTY_UPLOAD, open: true};
    },
    onPick(event) {
      const file = event.target.files && event.target.files[0];
      if (file) {
        this.upload.file = file;
      }
    },
    onDrop(event) {
      this.upload.dragOver = false;
      const file = event.dataTransfer.files && event.dataTransfer.files[0];
      if (file) {
        this.upload.file = file;
      }
    },
    async submitUpload() {
      const form = new FormData();
      form.append('file', this.upload.file);
      if (this.upload.title.trim()) {
        form.append('title', this.upload.title.trim());
      }
      if (this.upload.artist.trim()) {
        form.append('artist', this.upload.artist.trim());
      }
      if (this.upload.genre.trim()) {
        form.append('genre', this.upload.genre.trim());
      }
      if (this.upload.bpm !== '') {
        form.append('bpm', this.upload.bpm);
      }
      if (this.upload.key.trim()) {
        form.append('key', this.upload.key.trim());
      }
      form.append('require_approval', this.upload.requireApproval);
      this.upload.busy = true;
      try {
        const {data} = await axios.post('admin/content/upload', form);
        this.upload.open = false;
        toast(
          data.status === 'pending'
            ? 'Upload queued for approval'
            : 'Track uploaded & published'
        );
        this.fetchContent();
        this.$store.dispatch('fetchPendingCount');
      } catch (error) {
        toast(this.detailOf(error, 'The upload failed.'), 'warn');
      } finally {
        this.upload.busy = false;
      }
    },
  },
};
</script>

<style scoped>
.ac-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.ac-search {
  position: relative;
  flex: 1;
  min-width: 220px;
  max-width: 320px;
}

.ac-search-icon {
  position: absolute;
  left: 11px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--dim-2);
  display: flex;
}

.ac-search input {
  width: 100%;
  height: 38px;
  padding: 0 12px 0 34px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line-strong);
  background: var(--raised);
  color: var(--txt);
  font: 400 13px var(--font-ui);
  box-sizing: border-box;
}

.ac-search input::placeholder {
  color: var(--dim-2);
}

.ac-search input:focus {
  outline: none;
  border-color: var(--acc-border);
}

.ac-upload-btn {
  margin-left: auto;
  height: 38px;
  padding: 0 15px;
  border-radius: var(--r-ctl);
  border: none;
  background: var(--acc);
  color: var(--acc-ink);
  font: 600 13px var(--font-ui);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 7px;
  transition: filter .15s ease;
}

.ac-upload-btn:hover {
  filter: brightness(1.1);
}

.ac-error {
  color: var(--danger);
  font: 400 13px var(--font-ui);
}

.ac-none {
  font: 400 13px var(--font-ui);
  color: var(--dim-2);
  padding: 22px 4px;
}

/* Selection + undo bars */

.ac-selbar,
.ac-undobar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  margin-bottom: 12px;
  border-radius: 10px;
  border: 1px solid var(--acc-border);
  background: var(--acc-soft-strong);
  font: 500 12.5px var(--font-ui);
  color: var(--txt-2);
}

.ac-selcount {
  font: 600 12px var(--font-mono);
  color: var(--acc);
}

.ac-selclear,
.ac-undo-btn {
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  color: var(--muted);
  font: 600 12px var(--font-ui);
}

.ac-selclear:hover,
.ac-undo-btn:hover {
  color: var(--txt);
}

.ac-undo-btn {
  margin-left: auto;
  color: var(--acc);
}

.ac-selbatch {
  margin-left: auto;
  height: 34px;
}

.ac-panel {
  border: 1px solid var(--line);
  border-radius: 13px;
  overflow: hidden;
  background: var(--panel);
}

.ac-head,
.ac-row {
  display: grid;
  grid-template-columns: 26px minmax(180px, 2fr) 104px 92px 84px 112px 66px;
  align-items: center;
  gap: 12px;
  padding: 0 16px;
}

.ac-head input,
.ac-row input[type='checkbox'] {
  width: 15px;
  height: 15px;
  accent-color: var(--acc);
}

.ac-head {
  height: 38px;
  border-bottom: 1px solid rgba(255, 255, 255, .07);
  font: 600 10px var(--font-mono);
  letter-spacing: .08em;
  color: var(--dim-2);
  text-transform: uppercase;
}

.ac-h-c {
  text-align: center;
}

.ac-h-r {
  text-align: right;
}

.ac-row {
  height: 56px;
  border-bottom: 1px solid rgba(255, 255, 255, .045);
  transition: background .15s ease;
}

.ac-row:hover {
  background: rgba(255, 255, 255, .03);
}

.ac-row:last-child {
  border-bottom: none;
}

.ac-track {
  display: flex;
  align-items: center;
  gap: 11px;
  min-width: 0;
}

.ac-cover {
  width: 38px;
  height: 38px;
  border-radius: 7px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: none;
  box-shadow: var(--shadow-cover);
  font: 600 10px var(--font-mono);
  color: rgba(255, 255, 255, .72);
}

.ac-cover-lg {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  font: 600 16px var(--font-mono);
}

.ac-track-meta {
  min-width: 0;
}

.ac-title {
  font: 600 13px var(--font-ui);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ac-sub {
  font: 400 12px var(--font-ui);
  color: var(--muted);
  overflow-wrap: anywhere;
}

.ac-genre {
  font: 500 12px var(--font-ui);
  color: var(--txt-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ac-keybpm {
  text-align: center;
  font: 500 12px var(--font-mono);
}

.ac-key {
  color: var(--key);
}

.ac-sep {
  color: var(--dim-2);
}

.ac-bpm {
  color: var(--txt-2);
}

.ac-dls {
  text-align: right;
  font: 600 12px var(--font-mono);
  color: var(--txt-2);
}

.ac-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: var(--r-pill);
  border: none;
  cursor: pointer;
  font: 600 11px var(--font-ui);
  transition: filter .15s ease;
}

.ac-pill:hover {
  filter: brightness(1.15);
}

.ac-pill-dot {
  width: 6px;
  height: 6px;
  border-radius: 3px;
}

.ac-edit-cell {
  display: flex;
  justify-content: flex-end;
}

.ac-edit-btn {
  background: none;
  border: 1px solid var(--line-strong);
  cursor: pointer;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: var(--muted);
  transition: color .15s ease, border-color .15s ease;
}

.ac-edit-btn:hover {
  color: var(--acc);
  border-color: var(--acc-border);
}

/* Modals */

.ac-modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(4, 7, 11, .6);
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.ac-modal {
  width: 560px;
  max-width: 100%;
  max-height: 88vh;
  overflow-y: auto;
  background: var(--modal);
  border: 1px solid var(--line-strong);
  border-radius: var(--r-modal);
  box-shadow: 0 30px 80px rgba(0, 0, 0, .6);
}

.ac-modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 22px;
  border-bottom: 1px solid rgba(255, 255, 255, .07);
}

.ac-modal-title {
  font: 700 16px var(--font-disp);
}

.ac-x {
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
  transition: background .15s ease, color .15s ease;
}

.ac-x:hover {
  background: rgba(255, 255, 255, .06);
  color: var(--txt);
}

.ac-modal-body {
  padding: 22px;
}

.ac-dropzone {
  border: 2px dashed rgba(255, 255, 255, .16);
  border-radius: 13px;
  padding: 32px;
  text-align: center;
  margin-bottom: 20px;
  background: rgba(255, 255, 255, .02);
  cursor: pointer;
  transition: border-color .15s ease;
}

.ac-dropzone-sm {
  padding: 18px;
}

.ac-dropzone:hover,
.ac-dropzone-over {
  border-color: var(--acc-border);
}

.ac-drop-icon {
  width: 46px;
  height: 46px;
  border-radius: 12px;
  background: var(--acc-soft-strong);
  color: var(--acc);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 12px;
}

.ac-drop-title {
  font: 600 14px var(--font-ui);
  color: var(--txt);
  margin-bottom: 4px;
  overflow-wrap: anywhere;
}

.ac-drop-sub {
  font: 400 12.5px var(--font-ui);
  color: var(--dim);
}

.ac-file-input {
  display: none;
}

.ac-modal-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  margin-bottom: 16px;
}

.ac-span-2 {
  grid-column: 1 / -1;
}

.ac-half-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.ac-label {
  display: block;
  font: 600 11px var(--font-mono);
  letter-spacing: .06em;
  color: var(--muted);
  margin-bottom: 7px;
}

.ac-prov {
  margin-left: 7px;
  padding: 1px 6px;
  border-radius: 5px;
  background: rgba(255, 255, 255, .06);
  color: var(--dim);
  font: 600 9.5px var(--font-mono);
  letter-spacing: .04em;
  text-transform: uppercase;
}

.ac-prov-manual {
  background: var(--acc-soft-strong);
  color: var(--acc);
}

.ac-modal input[type='text'],
.ac-modal input[type='number'],
.ac-fields input,
.ac-fields textarea {
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

.ac-fields textarea {
  height: auto;
  padding: 10px 12px;
  resize: vertical;
}

.ac-modal input:focus,
.ac-fields input:focus,
.ac-fields textarea:focus {
  outline: none;
  border-color: var(--acc-border);
}

.ac-mono {
  font-family: var(--font-mono) !important;
}

.ac-approval {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(255, 255, 255, .03);
  border: 1px solid rgba(255, 255, 255, .07);
  cursor: pointer;
  font: 400 13px var(--font-ui);
  color: var(--txt-2);
}

.ac-approval input {
  width: 16px;
  height: 16px;
  accent-color: var(--acc);
}

.ac-modal-foot {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  padding: 16px 22px;
  border-top: 1px solid rgba(255, 255, 255, .07);
}

.ac-cancel {
  height: 40px;
  padding: 0 16px;
  border-radius: var(--r-ctl);
  border: 1px solid rgba(255, 255, 255, .12);
  background: none;
  color: var(--txt-2);
  font: 600 13px var(--font-ui);
  cursor: pointer;
  transition: color .15s ease;
}

.ac-cancel:hover {
  color: var(--txt);
}

.ac-primary {
  height: 40px;
  padding: 0 18px;
  border-radius: var(--r-ctl);
  border: none;
  background: var(--acc);
  color: var(--acc-ink);
  font: 600 13px var(--font-ui);
  cursor: pointer;
  transition: filter .15s ease;
}

.ac-primary:hover:enabled {
  filter: brightness(1.1);
}

.ac-primary:disabled {
  opacity: .5;
  cursor: default;
}

.ac-ghost {
  height: 30px;
  padding: 0 12px;
  border-radius: 8px;
  border: 1px solid var(--line-strong);
  background: rgba(255, 255, 255, .03);
  color: var(--txt-2);
  font: 600 12px var(--font-ui);
  cursor: pointer;
  flex: none;
  transition: border-color .15s ease, color .15s ease;
}

.ac-ghost:hover:enabled {
  border-color: var(--acc-border);
  color: var(--acc);
}

.ac-ghost:disabled {
  opacity: .45;
  cursor: default;
}

.ac-ghost-danger:hover:enabled {
  border-color: var(--danger);
  color: var(--danger);
}

/* Editor drawer */

.ac-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(4, 7, 11, .55);
  z-index: 40;
}

.ac-drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: 440px;
  max-width: 92vw;
  z-index: 41;
  background: var(--card);
  border-left: 1px solid rgba(255, 255, 255, .09);
  box-shadow: -24px 0 60px rgba(0, 0, 0, .5);
  display: flex;
  flex-direction: column;
}

.ac-drawer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, .07);
}

.ac-drawer-title {
  font: 600 13px var(--font-disp);
}

.ac-drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.ac-drawer-summary {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 18px;
}

.ac-drawer-summary-meta {
  min-width: 0;
}

.ac-drawer-name {
  font: 700 16px var(--font-disp);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ac-tabpane {
  margin-top: 18px;
}

.ac-fields {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.ac-txxx-row {
  display: grid;
  grid-template-columns: 1fr 1fr 28px;
  gap: 8px;
  margin-bottom: 8px;
}

.ac-txxx-del {
  border: 1px solid var(--line-strong);
  border-radius: 8px;
  background: none;
  color: var(--muted);
  cursor: pointer;
  font: 600 15px var(--font-ui);
}

.ac-txxx-del:hover {
  color: var(--danger);
  border-color: var(--danger);
}

.ac-drawer-note {
  margin-top: 18px;
  font: 400 12px/1.5 var(--font-ui);
  color: var(--dim);
}

.ac-drawer-foot {
  display: flex;
  gap: 10px;
  padding: 16px 20px;
  border-top: 1px solid rgba(255, 255, 255, .07);
}

.ac-flex {
  flex: 1;
}

/* Artwork tab */

.ac-art-current {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 18px;
}

.ac-art-img,
.ac-art-empty {
  width: 110px;
  height: 110px;
  border-radius: 12px;
  flex: none;
  object-fit: cover;
  box-shadow: var(--shadow-cover);
}

.ac-art-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, .04);
  color: var(--dim-2);
  font: 500 11px var(--font-mono);
}

.ac-art-side {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
  min-width: 0;
}

.ac-section-label {
  font: 600 10px var(--font-mono);
  letter-spacing: .08em;
  color: var(--dim-2);
  margin: 18px 0 10px;
}

.ac-cand-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
  gap: 10px;
}

.ac-cand {
  position: relative;
  padding: 0;
  border: 1px solid var(--line-strong);
  border-radius: 10px;
  overflow: hidden;
  background: none;
  cursor: pointer;
  aspect-ratio: 1;
}

.ac-cand:hover {
  border-color: var(--acc-border);
}

.ac-cand-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.ac-cand-badge {
  position: absolute;
  top: 6px;
  left: 6px;
  padding: 2px 7px;
  border-radius: 6px;
  background: rgba(4, 7, 11, .75);
  color: var(--acc);
  font: 600 9.5px var(--font-mono);
  text-transform: uppercase;
}

.ac-cand-dim {
  position: absolute;
  bottom: 6px;
  right: 6px;
  padding: 2px 6px;
  border-radius: 6px;
  background: rgba(4, 7, 11, .75);
  color: var(--dim);
  font: 500 9.5px var(--font-mono);
}

/* Suggestions tab */

.ac-sugg-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}

.ac-sugg-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid rgba(255, 255, 255, .05);
}

.ac-sugg-field {
  width: 84px;
  flex: none;
  font: 600 10.5px var(--font-mono);
  color: var(--dim-2);
  text-transform: uppercase;
}

.ac-sugg-values {
  flex: 1;
  min-width: 0;
  font: 400 12.5px var(--font-ui);
  overflow-wrap: anywhere;
}

.ac-sugg-old {
  color: var(--dim);
  text-decoration: line-through;
}

.ac-sugg-arrow {
  color: var(--dim-2);
  margin: 0 6px;
}

.ac-sugg-new {
  color: var(--txt);
  font-weight: 600;
}

.ac-lock {
  margin-left: 4px;
}

/* History tab */

.ac-rev {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  padding: 12px 0;
  border-bottom: 1px solid rgba(255, 255, 255, .05);
}

.ac-rev-top {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ac-rev-who {
  font: 600 12.5px var(--font-ui);
  color: var(--txt);
}

.ac-rev-src {
  padding: 2px 7px;
  border-radius: 6px;
  background: rgba(255, 255, 255, .06);
  color: var(--muted);
  font: 600 10px var(--font-mono);
  text-transform: uppercase;
}

.ac-rev-when {
  font: 400 11px var(--font-mono);
  color: var(--dim-2);
}

.ac-rev-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.ac-chip {
  padding: 3px 8px;
  border-radius: 6px;
  background: rgba(255, 255, 255, .05);
  color: var(--txt-2);
  font: 600 10.5px var(--font-mono);
}
</style>
