<template>
  <header class="topbar">
    <div class="tb-heading">
      <div class="tb-title">
        {{ title }}
      </div>
      <div class="tb-sub">
        {{ subtitle }}
      </div>
    </div>

    <div
      v-if="area === 'member'"
      class="tb-search"
    >
      <span class="tb-search-icon">
        <svg
          width="16"
          height="16"
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
        ref="search"
        v-model="q"
        type="text"
        placeholder="Search tracks, artists, genres, labels, BPM, key…"
        @input="onSearchInput"
        @keydown.enter="goSearch"
      >
      <span class="tb-kbd">⌘K</span>
    </div>

    <div class="tb-right">
      <button
        v-if="area === 'member'"
        type="button"
        class="tb-quota"
        title="Downloads left"
        @click="$router.push('/profile')"
      >
        <span class="tb-quota-dot" />
        {{ quotaLabel }}
      </button>
      <button
        type="button"
        class="tb-bell"
        title="Notifications"
      >
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.8"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d="M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6z" />
          <path d="M10 20a2 2 0 0 0 4 0" />
        </svg>
        <span class="tb-bell-dot" />
      </button>
      <div class="tb-user">
        <button
          type="button"
          class="tb-user-btn"
          @click="menuOpen = !menuOpen"
        >
          <div class="tb-avatar">
            {{ initials }}
          </div>
          <div class="tb-user-meta">
            <div class="tb-user-name">
              {{ displayName }}
            </div>
            <div class="tb-user-role">
              {{ roleLabel }}
            </div>
          </div>
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="var(--dim)"
            stroke-width="2"
          >
            <path d="M6 9l6 6 6-6" />
          </svg>
        </button>
        <template v-if="menuOpen">
          <div
            class="tb-menu-backdrop"
            @click="menuOpen = false"
          />
          <div class="tb-menu">
            <div class="tb-menu-head">
              <div class="tb-menu-name">
                {{ displayName }}
              </div>
              <div class="tb-menu-mail">
                {{ username }}
              </div>
            </div>
            <button
              type="button"
              class="tb-menu-item"
              @click="go('/profile')"
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
              >
                <circle
                  cx="12"
                  cy="8"
                  r="3.6"
                />
                <path d="M5 20a7 7 0 0 1 14 0" />
              </svg>
              Account &amp; billing
            </button>
            <button
              v-if="hasAdminAccess"
              type="button"
              class="tb-menu-item"
              @click="go('/admin')"
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linejoin="round"
              >
                <path d="M12 3l8 3v5c0 5-3.5 8-8 9.5C7.5 19 4 16 4 11V6z" />
              </svg>
              Admin console
            </button>
            <div class="tb-menu-sep" />
            <button
              type="button"
              class="tb-menu-item tb-menu-danger"
              @click="logout"
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
                <path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3" />
                <path d="M10 17l-5-5 5-5" />
                <path d="M5 12h11" />
              </svg>
              Log out
            </button>
          </div>
        </template>
      </div>
    </div>
  </header>
</template>

<script>
export default {
  name: 'TopBar',
  props: {
    area: {
      type: String,
      default: 'member',
    },
  },
  data() {
    return {
      q: '',
      menuOpen: false,
      searchDebounce: null,
    };
  },
  computed: {
    title() {
      return this.$route.meta.title || this.$route.name || '';
    },
    subtitle() {
      return this.$route.meta.subtitle || '';
    },
    quotaLabel() {
      const quota = this.$store.getters.stateQuota;
      if (!quota) {
        return '— left';
      }
      return quota.unlimited ? '∞ left' : `${quota.remaining} left`;
    },
    user() {
      return this.$store.getters.stateUser;
    },
    username() {
      return (this.user && this.user.username) || '';
    },
    displayName() {
      return (this.user && (this.user.full_name || this.user.username)) || '';
    },
    roleLabel() {
      const role = (this.user && this.user.role) || 'member';
      return role.charAt(0).toUpperCase() + role.slice(1);
    },
    hasAdminAccess() {
      return this.$store.getters.hasAdminAccess;
    },
    initials() {
      const source = this.displayName || '?';
      const words = source.trim().split(/\s+/);
      const letters = words.length > 1
        ? words[0][0] + words[1][0]
        : source.slice(0, 2);
      return letters.toUpperCase();
    },
  },
  watch: {
    // Keep the box in sync when the Search view changes the query itself
    // (genre chips, back/forward navigation).
    '$route.query.q'() {
      if (this.$route.path === '/search') {
        this.q = this.$route.query.q || '';
      }
    },
  },
  created() {
    if (this.$route.path === '/search') {
      this.q = this.$route.query.q || '';
    }
  },
  mounted() {
    window.addEventListener('keydown', this.onGlobalKey);
  },
  beforeUnmount() {
    window.removeEventListener('keydown', this.onGlobalKey);
    clearTimeout(this.searchDebounce);
  },
  methods: {
    onGlobalKey(event) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        if (this.$refs.search) {
          this.$refs.search.focus();
        }
      }
    },
    // Typing routes to the Search view (replace once there, so every
    // keystroke doesn't grow the history); Enter goes immediately.
    onSearchInput() {
      clearTimeout(this.searchDebounce);
      this.searchDebounce = setTimeout(() => {
        const query = this.q.trim();
        if (this.$route.path === '/search') {
          this.$router.replace({path: '/search', query: query ? {q: query} : {}});
        } else if (query) {
          this.$router.push({path: '/search', query: {q: query}});
        }
      }, 300);
    },
    goSearch() {
      clearTimeout(this.searchDebounce);
      const query = this.q.trim();
      this.$router.push({path: '/search', query: query ? {q: query} : {}});
    },
    go(path) {
      this.menuOpen = false;
      this.$router.push(path);
    },
    async logout() {
      this.menuOpen = false;
      await this.$store.dispatch('logOut');
      this.$router.push('/login');
    },
  },
};
</script>

<style scoped>
.topbar {
  height: var(--topbar-h);
  flex: none;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 0 22px;
  border-bottom: 1px solid var(--line);
  background: rgba(10, 13, 18, .72);
  backdrop-filter: blur(10px);
  z-index: 5;
}

.tb-heading {
  min-width: 150px;
}

.tb-title {
  font: 600 15px/1.1 var(--font-disp);
}

.tb-sub {
  font: 400 11.5px/1.3 var(--font-ui);
  color: var(--dim);
  margin-top: 2px;
}

.tb-search {
  flex: 1;
  max-width: 540px;
  position: relative;
  margin: 0 auto;
}

.tb-search-icon {
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--dim-2);
  display: flex;
}

.tb-search input {
  width: 100%;
  height: 38px;
  padding: 0 42px 0 36px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line-strong);
  background: var(--raised);
  color: var(--txt);
  font: 400 13px var(--font-ui);
  box-sizing: border-box;
}

.tb-search input::placeholder {
  color: var(--dim-2);
}

.tb-search input:focus {
  outline: none;
  border-color: var(--acc-border);
}

.tb-kbd {
  position: absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  font: 600 10px var(--font-mono);
  color: var(--dim-2);
  border: 1px solid rgba(255, 255, 255, .12);
  border-radius: 5px;
  padding: 2px 6px;
}

.tb-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 14px;
}

.tb-quota {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 34px;
  padding: 0 12px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line-strong);
  background: rgba(255, 255, 255, .03);
  cursor: pointer;
  color: var(--txt-2);
  font: 600 12px var(--font-mono);
  transition: border-color .15s ease;
}

.tb-quota:hover {
  border-color: var(--acc-border);
}

.tb-quota-dot {
  width: 7px;
  height: 7px;
  border-radius: 2px;
  background: var(--acc);
}

.tb-bell {
  position: relative;
  background: none;
  border: none;
  padding: 0;
  margin: 0;
  cursor: pointer;
  color: var(--muted);
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--r-ctl);
  transition: background .15s ease, color .15s ease;
}

.tb-bell:hover {
  background: var(--hover);
  color: var(--txt);
}

.tb-bell-dot {
  position: absolute;
  top: 7px;
  right: 8px;
  width: 7px;
  height: 7px;
  border-radius: 4px;
  background: var(--danger);
  border: 1.5px solid var(--bg);
}

.tb-user {
  position: relative;
  padding-left: 6px;
  border-left: 1px solid rgba(255, 255, 255, .08);
}

.tb-user-btn {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 3px 4px;
  border: none;
  background: none;
  cursor: pointer;
  border-radius: 8px;
  transition: background .15s ease;
}

.tb-user-btn:hover {
  background: var(--hover);
}

.tb-avatar {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: var(--tint-2);
  display: flex;
  align-items: center;
  justify-content: center;
  font: 600 12px var(--font-mono);
  color: #bfe6f5;
}

.tb-user-meta {
  line-height: 1.1;
  text-align: left;
}

.tb-user-name {
  font: 600 12.5px var(--font-ui);
  color: var(--txt);
}

.tb-user-role {
  font: 500 10.5px var(--font-mono);
  color: var(--dim);
}

.tb-menu-backdrop {
  position: fixed;
  inset: 0;
  z-index: 30;
}

.tb-menu {
  position: absolute;
  top: 46px;
  right: 0;
  z-index: 31;
  width: 216px;
  background: var(--menu);
  border: 1px solid var(--line-strong);
  border-radius: var(--r-panel);
  box-shadow: var(--shadow-overlay);
  padding: 6px;
}

.tb-menu-head {
  padding: 8px 10px 9px;
  border-bottom: 1px solid var(--line);
  margin-bottom: 4px;
}

.tb-menu-name {
  font: 600 12.5px var(--font-ui);
}

.tb-menu-mail {
  font: 400 11px var(--font-mono);
  color: var(--dim);
}

.tb-menu-item {
  display: flex;
  align-items: center;
  gap: 11px;
  width: 100%;
  height: 36px;
  padding: 0 10px;
  border: none;
  border-radius: 8px;
  background: none;
  cursor: pointer;
  color: var(--txt-2);
  font: 500 13px var(--font-ui);
  text-align: left;
  transition: background .15s ease, color .15s ease;
}

.tb-menu-item:hover {
  background: rgba(255, 255, 255, .06);
  color: var(--txt);
}

.tb-menu-sep {
  height: 1px;
  background: var(--line);
  margin: 4px 0;
}

.tb-menu-danger {
  color: #ff7d8c;
}

.tb-menu-danger:hover {
  background: rgba(255, 82, 102, .12);
  color: #ff7d8c;
}
</style>
