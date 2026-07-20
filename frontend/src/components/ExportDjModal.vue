<template>
  <div
    class="modal-scrim"
    @click.self="close"
  >
    <div class="modal">
      <header class="modal-head">
        <h2>Export for DJ</h2>
        <button
          type="button"
          class="x-btn"
          @click="close"
        >
          ×
        </button>
      </header>

      <!-- picking -->
      <template v-if="phase === 'form'">
        <p class="lede">
          Builds a ZIP you extract onto the root of a USB stick — audio plus the
          crate file your software reads.
        </p>

        <div class="targets">
          <button
            v-for="target in targets"
            :key="target.value"
            type="button"
            class="target"
            :class="{'target-on': format === target.value}"
            @click="format = target.value"
          >
            <span class="target-name">{{ target.label }}</span>
            <span class="target-hint">{{ target.hint }}</span>
          </button>
        </div>

        <label class="field">
          <span class="field-label">USB volume label</span>
          <input
            v-model.trim="volumeLabel"
            class="field-input"
            maxlength="32"
          >
          <span class="field-hint">Name your stick this, so paths resolve on any machine.</span>
        </label>

        <label
          v-if="format === 'rekordbox'"
          class="field"
        >
          <span class="field-label">Stick mount point</span>
          <input
            v-model.trim="rekordboxRoot"
            class="field-input"
            maxlength="256"
          >
          <span class="field-hint">
            macOS: /Volumes/{{ volumeLabel || 'ORP_USB' }} — Windows: a drive letter like E:
          </span>
        </label>

        <p class="meta">
          {{ trackCount }} track{{ trackCount === 1 ? '' : 's' }} · about {{ sizeLabel }}
        </p>
        <p
          v-if="tooBigForFat32"
          class="warn"
        >
          Bundle is over 4 GB — format the stick as exFAT (FAT32 cannot store it).
        </p>
        <p class="note">
          Tags, BPM and key are included; beatgrids and cue points are not — your DJ
          software analyzes on first load and reads the tags natively.
        </p>

        <footer class="modal-foot">
          <button
            type="button"
            class="btn"
            @click="close"
          >
            Cancel
          </button>
          <button
            type="button"
            class="btn btn-primary"
            :disabled="!format"
            @click="start"
          >
            Export
          </button>
        </footer>
      </template>

      <!-- building -->
      <template v-else-if="phase === 'running'">
        <p class="lede">
          Building your {{ format }} bundle — copying audio and writing tags.
        </p>
        <div class="bar">
          <div
            class="bar-fill"
            :style="{width: `${Math.round(progress * 100)}%`}"
          />
        </div>
        <p class="meta">
          {{ Math.round(progress * 100) }}%
        </p>
        <footer class="modal-foot">
          <button
            type="button"
            class="btn"
            @click="close"
          >
            Close
          </button>
        </footer>
      </template>

      <!-- done -->
      <template v-else>
        <p class="lede">
          {{ job.result.track_count }} track(s) bundled ·
          {{ formatBytes(job.result.zip_size_bytes) }}
        </p>
        <ul
          v-if="job.result.skipped && job.result.skipped.length"
          class="skipped"
        >
          <li
            v-for="item in job.result.skipped"
            :key="item.song_id"
          >
            Skipped song {{ item.song_id }} — {{ item.reason }}
          </li>
        </ul>
        <p class="note">
          The link expires in about {{ ttlHours }} hours.
        </p>
        <footer class="modal-foot">
          <button
            type="button"
            class="btn"
            @click="close"
          >
            Close
          </button>
          <a
            class="btn btn-primary"
            :href="href"
            :download="job.result.bundle_filename"
          >
            Download bundle
          </a>
        </footer>
      </template>
    </div>
  </div>
</template>

<script>
import {
  DJ_TARGETS,
  FAT32_LIMIT,
  downloadUrl,
  formatBytes,
  pollExport,
  submitExport,
} from '@/utils/exports';
import { toast } from '@/utils/toast';

export default {
  name: 'ExportDjModal',
  props: {
    crate: {
      type: Object,
      required: true,
    },
    tracks: {
      type: Array,
      default: () => [],
    },
    // Non-owners can still export a crate they can read; they just cannot
    // change the crate's stored default target.
    readOnly: {
      type: Boolean,
      default: false,
    },
  },
  emits: ['close'],
  data() {
    return {
      targets: DJ_TARGETS,
      format: this.crate.dj_target || null,
      volumeLabel: 'ORP_USB',
      rekordboxRoot: '',
      phase: 'form',
      job: null,
      progress: 0,
      ttlHours: 24,
    };
  },
  computed: {
    trackCount() {
      return this.crate.track_count != null ? this.crate.track_count : this.tracks.length;
    },
    // Estimated from the tracks already loaded in the view; the server returns
    // the authoritative estimate with the job.
    estimatedBytes() {
      return this.tracks.reduce(
        (total, item) => total + ((item.song && item.song.file_size_bytes) || 0),
        0
      );
    },
    sizeLabel() {
      return formatBytes(this.estimatedBytes);
    },
    tooBigForFat32() {
      return this.estimatedBytes > FAT32_LIMIT;
    },
    href() {
      return this.job ? downloadUrl(this.job) : '';
    },
  },
  methods: {
    formatBytes,
    close() {
      this.$emit('close');
    },
    async start() {
      const body = {
        format: this.format,
        volume_label: this.volumeLabel || 'ORP_USB',
      };
      if (this.format === 'rekordbox' && this.rekordboxRoot) {
        body.rekordbox_root = this.rekordboxRoot;
      }
      // Remember the pick on the crate itself, so next time it is preselected.
      if (!this.readOnly && this.format !== this.crate.dj_target) {
        this.$store
          .dispatch('updateCrate', {
            crateId: this.crate.id,
            changes: {dj_target: this.format},
          })
          .catch(() => {});
      }

      this.phase = 'running';
      try {
        let job = await submitExport(this.crate.id, body);
        if (job.status !== 'succeeded' && job.status !== 'failed') {
          job = await pollExport(job.id, {
            onProgress: (tick) => {
              this.progress = tick.progress || 0;
            },
          });
        }
        if (job.status !== 'succeeded') {
          throw new Error(job.error || 'Export failed');
        }
        this.job = job;
        this.progress = 1;
        this.phase = 'done';
      } catch (error) {
        const detail =
          (error.response && error.response.data && error.response.data.detail) ||
          error.message;
        toast(detail || 'Export failed', 'warn');
        this.phase = 'form';
      }
    },
  },
};
</script>

<style scoped>
.modal-scrim {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.55);
  padding: 1rem;
}

.modal {
  width: min(30rem, 100%);
  background: var(--bg-1, #14161a);
  border: 1px solid var(--acc-border, rgba(255, 255, 255, 0.12));
  border-radius: 14px;
  padding: 1.1rem 1.25rem 1.25rem;
  color: inherit;
}

.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.modal-head h2 {
  font-size: 1.05rem;
  margin: 0;
}

.x-btn {
  background: none;
  border: 0;
  color: inherit;
  cursor: pointer;
  font-size: 1.3rem;
  line-height: 1;
}

.lede {
  color: var(--fg-2, #a7adba);
  font-size: 0.85rem;
  margin: 0.35rem 0 0.9rem;
}

.targets {
  display: grid;
  gap: 0.5rem;
  margin-bottom: 0.9rem;
}

.target {
  text-align: left;
  padding: 0.6rem 0.75rem;
  border-radius: 10px;
  border: 1px solid var(--acc-border, rgba(255, 255, 255, 0.12));
  background: transparent;
  color: inherit;
  cursor: pointer;
  display: grid;
  gap: 0.15rem;
}

.target-on {
  border-color: var(--acc, #6ee7b7);
  background: var(--acc-soft, rgba(110, 231, 183, 0.1));
}

.target-name {
  font-weight: 600;
  font-size: 0.9rem;
}

.target-hint {
  font-size: 0.75rem;
  color: var(--fg-2, #a7adba);
}

.field {
  display: grid;
  gap: 0.25rem;
  margin-bottom: 0.75rem;
}

.field-label {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--fg-2, #a7adba);
}

.field-input {
  font-family: var(--font-mono, monospace);
  padding: 0.45rem 0.6rem;
  border-radius: 8px;
  border: 1px solid var(--acc-border, rgba(255, 255, 255, 0.12));
  background: rgba(255, 255, 255, 0.04);
  color: inherit;
}

.field-hint,
.note {
  font-size: 0.72rem;
  color: var(--fg-2, #a7adba);
}

.meta {
  font-family: var(--font-mono, monospace);
  font-size: 0.8rem;
  margin: 0.6rem 0 0.3rem;
}

.warn {
  font-size: 0.78rem;
  color: #f59e0b;
  margin: 0 0 0.4rem;
}

.skipped {
  font-size: 0.75rem;
  color: #f59e0b;
  padding-left: 1rem;
  margin: 0.3rem 0;
}

.bar {
  height: 8px;
  border-radius: 99px;
  background: rgba(255, 255, 255, 0.08);
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  background: var(--acc, #6ee7b7);
  transition: width 0.3s ease;
}

.modal-foot {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 1rem;
}

.btn {
  padding: 0.45rem 0.9rem;
  border-radius: 8px;
  border: 1px solid var(--acc-border, rgba(255, 255, 255, 0.12));
  background: transparent;
  color: inherit;
  cursor: pointer;
  font-size: 0.85rem;
  text-decoration: none;
}

.btn-primary {
  border-color: var(--acc, #6ee7b7);
  background: var(--acc-soft, rgba(110, 231, 183, 0.12));
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
