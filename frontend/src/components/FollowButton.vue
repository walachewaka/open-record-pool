<template>
  <div
    class="follow-wrap"
    @keyup.esc="open = false"
  >
    <button
      v-if="!artist.is_followed"
      type="button"
      class="fb fb-outline"
      @click="follow"
    >
      Follow
    </button>
    <template v-else>
      <button
        type="button"
        class="fb fb-on"
        @click="open = !open"
      >
        Following
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2.2"
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      <div
        v-if="open"
        class="fb-pop"
      >
        <div class="fb-row">
          <span>Notify on new releases</span>
          <ToggleSwitch
            :model-value="settings.notify"
            @update:model-value="val => updateSetting('notify', val)"
          />
        </div>
        <div class="fb-row">
          <div>
            <span>Auto-grab new releases</span>
            <div class="fb-help">
              Queues a download when a release is not in the library
            </div>
          </div>
          <ToggleSwitch
            :model-value="settings.auto_grab"
            @update:model-value="val => updateSetting('auto_grab', val)"
          />
        </div>
        <button
          type="button"
          class="fb-unfollow"
          @click="unfollow"
        >
          Unfollow
        </button>
      </div>
    </template>
  </div>
</template>

<script>
import ToggleSwitch from '@/components/admin/ToggleSwitch.vue';
import { toast } from '@/utils/toast';

export default {
  name: 'FollowButton',
  components: {ToggleSwitch},
  props: {
    artist: {
      type: Object,
      required: true,
    },
  },
  emits: ['changed'],
  data() {
    return {
      open: false,
    };
  },
  computed: {
    settings() {
      return this.artist.follow_settings || {auto_grab: false, notify: true};
    },
  },
  mounted() {
    document.addEventListener('click', this.onDocumentClick, true);
  },
  beforeUnmount() {
    document.removeEventListener('click', this.onDocumentClick, true);
  },
  methods: {
    onDocumentClick(event) {
      if (this.open && !this.$el.contains(event.target)) {
        this.open = false;
      }
    },
    async follow() {
      try {
        const data = await this.$store.dispatch('toggleFollow', {
          artistId: this.artist.id,
          settings: {auto_grab: false, notify: true},
        });
        this.$emit('changed', {is_followed: true, follow_settings: data.settings});
        toast('Following ' + this.artist.name);
      } catch (error) {
        toast('Could not follow this artist', 'warn');
      }
    },
    async updateSetting(key, value) {
      try {
        const data = await this.$store.dispatch('updateFollowSettings', {
          artistId: this.artist.id,
          settings: {[key]: value},
        });
        this.$emit('changed', {is_followed: true, follow_settings: data.settings});
      } catch (error) {
        toast('Could not update follow settings', 'warn');
      }
    },
    async unfollow() {
      try {
        await this.$store.dispatch('unfollowArtist', this.artist.id);
        this.open = false;
        this.$emit('changed', {is_followed: false, follow_settings: null});
        toast('Unfollowed ' + this.artist.name);
      } catch (error) {
        toast('Could not unfollow this artist', 'warn');
      }
    },
  },
};
</script>

<style scoped>
.follow-wrap {
  position: relative;
  flex: none;
}

.fb {
  height: 32px;
  padding: 0 13px;
  border-radius: var(--r-ctl);
  font: 600 12px var(--font-ui);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: border-color .15s ease, background .15s ease, color .15s ease;
}

.fb-outline {
  border: 1px solid var(--line-strong);
  background: rgba(255, 255, 255, .03);
  color: var(--txt-2);
}

.fb-outline:hover {
  border-color: var(--acc-border);
  color: var(--txt);
}

.fb-on {
  border: 1px solid transparent;
  background: var(--acc-soft-strong);
  color: var(--acc);
}

.fb-pop {
  position: absolute;
  right: 0;
  top: calc(100% + 6px);
  z-index: 20;
  width: 240px;
  padding: 12px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line);
  background: var(--panel);
  box-shadow: 0 12px 28px rgba(0, 0, 0, .35);
}

.fb-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 6px 0;
  font: 500 12.5px var(--font-ui);
  color: var(--txt-2);
}

.fb-help {
  font: 400 11px var(--font-ui);
  color: var(--dim-2);
  margin-top: 2px;
}

.fb-unfollow {
  margin-top: 8px;
  width: 100%;
  height: 30px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line);
  background: none;
  color: var(--danger);
  font: 600 12px var(--font-ui);
  cursor: pointer;
}

.fb-unfollow:hover {
  border-color: var(--danger);
}
</style>
