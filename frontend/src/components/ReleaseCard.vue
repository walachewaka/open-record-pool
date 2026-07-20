<template>
  <div class="rc">
    <button
      type="button"
      class="rc-cover"
      :style="{background: tint}"
      :title="`Play ${song.title || 'track'}`"
      @click="$emit('play', song)"
    >
      <span class="rc-initials">{{ initials }}</span>
      <span class="rc-overlay">
        <span class="rc-fab">
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="currentColor"
          >
            <path d="M8 5v14l11-7z" />
          </svg>
        </span>
      </span>
    </button>
    <button
      type="button"
      class="rc-title"
      :title="song.title || ''"
      @click="$router.push(`/release/${song.id}`)"
    >
      {{ song.title || 'Untitled' }}
    </button>
    <div class="rc-artist">
      {{ song.artist || 'Unknown artist' }}
    </div>
    <div class="rc-meta">
      {{ meta }}
    </div>
  </div>
</template>

<script>
// A square Home release card (MOO-94): 168px tinted cover with a play FAB
// revealed on parent hover, title -> release, "Key · BPM" meta line.
export default {
  name: 'ReleaseCard',
  props: {
    song: {
      type: Object,
      required: true,
    },
  },
  emits: ['play'],
  computed: {
    initials() {
      const source = this.song.title || this.song.artist || '?';
      const words = source.trim().split(/\s+/);
      const letters = words.length > 1
        ? words[0][0] + words[1][0]
        : source.slice(0, 2);
      return letters.toUpperCase();
    },
    tint() {
      return `var(--tint-${(this.song.id % 10) + 1})`;
    },
    meta() {
      const key = this.song.camelot_key || this.song.musical_key;
      const bpm = this.song.bpm == null ? null : `${Math.round(this.song.bpm)} BPM`;
      return [key, bpm].filter(Boolean).join(' · ') || '—';
    },
  },
};
</script>

<style scoped>
.rc {
  flex: none;
  width: 168px;
  scroll-snap-align: start;
}

.rc-cover {
  position: relative;
  display: block;
  width: 168px;
  height: 168px;
  border-radius: 12px;
  border: none;
  padding: 0;
  cursor: pointer;
  box-shadow: var(--shadow-cover);
  overflow: hidden;
  margin-bottom: 11px;
}

.rc-initials {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font: 600 30px var(--font-mono);
  color: rgba(255, 255, 255, .56);
}

.rc-overlay {
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, transparent 45%, rgba(4, 10, 16, .5));
  display: flex;
  align-items: flex-end;
  justify-content: flex-end;
  padding: 11px;
  box-sizing: border-box;
  opacity: 0;
  transition: opacity .15s ease;
}

.rc-cover:hover .rc-overlay {
  opacity: 1;
}

.rc-fab {
  width: 42px;
  height: 42px;
  border-radius: 50%;
  background: var(--acc);
  color: var(--acc-ink);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8px 18px rgba(0, 0, 0, .45);
}

.rc-title {
  display: block;
  max-width: 100%;
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  font: 600 13.5px/1.25 var(--font-ui);
  color: var(--txt);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: left;
  transition: color .15s ease;
}

.rc-title:hover {
  color: var(--acc);
}

.rc-artist {
  font: 400 12px/1.35 var(--font-ui);
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 2px;
}

.rc-meta {
  font: 500 10.5px var(--font-mono);
  color: var(--dim-2);
  margin-top: 3px;
}
</style>
