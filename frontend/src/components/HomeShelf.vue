<template>
  <div class="shelf">
    <div class="shelf-head">
      <div>
        <div class="shelf-title">
          {{ title }}
        </div>
        <div
          v-if="subtitle"
          class="shelf-sub"
        >
          {{ subtitle }}
        </div>
      </div>
      <div class="shelf-ctrls">
        <button
          v-if="showAll"
          type="button"
          class="shelf-all"
          @click="$emit('show-all')"
        >
          {{ showAll }}
        </button>
        <button
          type="button"
          class="shelf-arrow"
          title="Scroll left"
          @click="scrollBy(-1)"
        >
          <svg
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M15 6l-6 6 6 6" />
          </svg>
        </button>
        <button
          type="button"
          class="shelf-arrow"
          title="Scroll right"
          @click="scrollBy(1)"
        >
          <svg
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M9 6l6 6-6 6" />
          </svg>
        </button>
      </div>
    </div>
    <div
      ref="scroller"
      class="shelf-scroller"
    >
      <slot />
    </div>
  </div>
</template>

<script>
// One horizontal Home shelf (MOO-94): header with title/subtitle, an optional
// "Show all" pill, prev/next round arrows, over a snap-scrolling flex row.
export default {
  name: 'HomeShelf',
  props: {
    title: {
      type: String,
      required: true,
    },
    subtitle: {
      type: String,
      default: '',
    },
    // Label of the optional "Show all" pill; hidden when empty.
    showAll: {
      type: String,
      default: '',
    },
  },
  emits: ['show-all'],
  methods: {
    scrollBy(direction) {
      const scroller = this.$refs.scroller;
      scroller.scrollBy({
        left: direction * Math.round(scroller.clientWidth * 0.82),
        behavior: 'smooth',
      });
    },
  },
};
</script>

<style scoped>
.shelf {
  margin-bottom: 32px;
}

.shelf-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.shelf-title {
  font: 700 19px var(--font-disp);
}

.shelf-sub {
  font: 400 12px var(--font-ui);
  color: var(--dim);
  margin-top: 2px;
}

.shelf-ctrls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.shelf-all {
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

.shelf-all:hover {
  color: var(--txt);
  border-color: rgba(255, 255, 255, .24);
}

.shelf-arrow {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, .12);
  background: rgba(255, 255, 255, .03);
  cursor: pointer;
  color: var(--txt-2);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color .15s ease, border-color .15s ease;
}

.shelf-arrow:hover {
  color: #fff;
  border-color: rgba(255, 255, 255, .25);
}

.shelf-scroller {
  display: flex;
  gap: 16px;
  overflow-x: auto;
  scroll-snap-type: x proximity;
  padding-bottom: 4px;
  /* Hidden scrollbar: arrows + trackpad/drag do the scrolling. */
  scrollbar-width: none;
}

.shelf-scroller::-webkit-scrollbar {
  display: none;
}
</style>
