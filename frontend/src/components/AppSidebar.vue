<template>
  <aside class="sidebar">
    <div class="brand">
      <div class="brand-mark">
        <svg
          width="17"
          height="17"
          viewBox="0 0 24 24"
          fill="none"
          stroke="var(--acc-ink)"
          stroke-width="2.2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d="M3 8l9-4 9 4-9 4-9-4z" />
          <path d="M3 8v8l9 4 9-4V8" />
          <path d="M12 12v8" />
        </svg>
      </div>
      <div class="brand-text">
        <div class="brand-name">
          CRATE
        </div>
        <div class="brand-sub">
          SELF-HOSTED POOL
        </div>
      </div>
    </div>

    <template v-if="area === 'member'">
      <nav class="nav">
        <div class="group-label">
          DISCOVER
        </div>
        <router-link
          class="nav-item"
          to="/home"
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
            <path d="M4 11l8-7 8 7" />
            <path d="M6 9.5V20h12V9.5" />
          </svg>
          <span class="nav-label">Home</span>
        </router-link>
        <router-link
          class="nav-item"
          to="/library"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
          >
            <circle
              cx="12"
              cy="12"
              r="8.5"
            />
            <circle
              cx="12"
              cy="12"
              r="2.2"
              fill="currentColor"
              stroke="none"
            />
          </svg>
          <span class="nav-label">New Releases</span>
        </router-link>
        <router-link
          class="nav-item"
          to="/genres"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linejoin="round"
          >
            <rect
              x="3.5"
              y="3.5"
              width="7"
              height="7"
              rx="1.6"
            />
            <rect
              x="13.5"
              y="3.5"
              width="7"
              height="7"
              rx="1.6"
            />
            <rect
              x="3.5"
              y="13.5"
              width="7"
              height="7"
              rx="1.6"
            />
            <rect
              x="13.5"
              y="13.5"
              width="7"
              height="7"
              rx="1.6"
            />
          </svg>
          <span class="nav-label">Genres</span>
        </router-link>
        <router-link
          class="nav-item"
          to="/charts"
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
            <polyline points="3 16.5 9 10.5 13 14.5 21 6.5" />
            <polyline points="15 6.5 21 6.5 21 12.5" />
          </svg>
          <span class="nav-label">Charts</span>
        </router-link>
        <router-link
          class="nav-item"
          to="/search"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
          >
            <circle
              cx="11"
              cy="11"
              r="7"
            />
            <path d="M20 20l-3.6-3.6" />
          </svg>
          <span class="nav-label">Search</span>
        </router-link>
        <router-link
          class="nav-item"
          to="/artists"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
          >
            <circle
              cx="9"
              cy="8"
              r="3.2"
            />
            <path d="M3 19a6 6 0 0 1 12 0" />
            <circle
              cx="17"
              cy="8.5"
              r="2.6"
            />
            <path d="M15.2 12.2A5.5 5.5 0 0 1 21 17.5" />
          </svg>
          <span class="nav-label">Artists</span>
        </router-link>
        <router-link
          class="nav-item"
          :class="{'nav-item-current': $route.path === '/releases'}"
          to="/releases"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linejoin="round"
          >
            <rect
              x="3.5"
              y="4.5"
              width="17"
              height="16"
              rx="2"
            />
            <path d="M3.5 9.5h17M8 3v3M16 3v3" />
          </svg>
          <span class="nav-label">Release Radar</span>
          <span
            v-if="unseenReleases"
            class="mod-badge"
          >{{ unseenReleases }}</span>
        </router-link>

        <div class="group-row">
          <span class="group-label-text">CRATES</span>
          <div class="group-actions">
            <button
              type="button"
              class="icon-btn icon-btn-spark"
              disabled
              title="Generate a crate from Spotify (arrives in a later stage)"
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="currentColor"
              >
                <path d="M12 3l1.5 4.2L18 8.7l-4.5 1.5L12 14.4l-1.5-4.2L6 8.7l4.5-1.5L12 3z" />
                <path d="M18.5 13.5l.9 2.4 2.4.9-2.4.9-.9 2.4-.9-2.4-2.4-.9 2.4-.9.9-2.4z" />
              </svg>
            </button>
            <button
              type="button"
              class="icon-btn"
              title="New crate"
              @click="newCrate"
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
              >
                <path d="M12 5v14M5 12h14" />
              </svg>
            </button>
          </div>
        </div>
        <router-link
          v-for="crate in crates"
          :key="crate.id"
          class="crate-item"
          :class="{'crate-item-over': dragOverId === crate.id}"
          :to="`/crate/${crate.id}`"
          @dragover.prevent="dragOverId = crate.id"
          @dragleave="onCrateLeave(crate.id)"
          @drop.prevent="onCrateDrop(crate, $event)"
        >
          <span
            class="crate-dot"
            :style="{background: crate.color || 'var(--acc)'}"
          />
          <span class="crate-name">{{ crate.name }}</span>
          <span
            v-if="crate.public"
            class="crate-globe"
            title="Public crate"
          >
            <svg
              width="12"
              height="12"
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
          </span>
          <span class="crate-count">{{ crate.track_count }}</span>
        </router-link>
        <div
          v-if="!crates.length"
          class="crates-empty"
        >
          No crates yet
        </div>
        <router-link
          class="nav-item"
          to="/crates/discover"
        >
          <svg
            width="16"
            height="16"
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
          <span class="nav-label">Public Crates</span>
        </router-link>

        <div class="nav-gap" />
        <router-link
          class="nav-item"
          to="/downloads"
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
            <path d="M12 4v10" />
            <path d="M8 11l4 4 4-4" />
            <path d="M5 19h14" />
          </svg>
          <span class="nav-label">Downloads</span>
        </router-link>
        <router-link
          class="nav-item"
          :class="{'nav-item-current': $route.path === '/requests'}"
          to="/requests"
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
            <circle
              cx="12"
              cy="12"
              r="9"
            />
            <path d="M12 8v4l3 2" />
          </svg>
          <span class="nav-label">Requests</span>
          <span
            v-if="requestsUnseenCount"
            class="mod-badge"
          >{{ requestsUnseenCount }}</span>
        </router-link>
        <router-link
          class="nav-item"
          to="/profile"
        >
          <svg
            width="18"
            height="18"
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
          <span class="nav-label">Account</span>
        </router-link>
      </nav>
      <div class="foot">
        <div class="quota-head">
          <span>DOWNLOADS</span>
          <span class="quota-count">{{ quotaCount }}</span>
        </div>
        <div class="quota-bar">
          <div
            class="quota-fill"
            :style="{width: quotaPct + '%'}"
          />
        </div>
        <button
          v-if="hasAdminAccess"
          type="button"
          class="foot-btn"
          @click="$router.push('/admin')"
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
          <span class="foot-btn-label">Admin console</span>
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path d="M9 6l6 6-6 6" />
          </svg>
        </button>
      </div>
    </template>

    <template v-else>
      <nav class="nav">
        <div class="admin-badge">
          ADMIN CONSOLE
        </div>
        <router-link
          v-if="perms.view_reports"
          class="nav-item"
          :class="{'nav-item-current': $route.path === '/admin'}"
          to="/admin"
          active-class="nav-item-inactive"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linejoin="round"
          >
            <rect
              x="3.5"
              y="3.5"
              width="17"
              height="17"
              rx="2"
            />
            <path d="M3.5 9.5h17M9.5 9.5v11" />
          </svg>
          <span class="nav-label">Dashboard</span>
        </router-link>
        <router-link
          v-if="perms.manage_users"
          class="nav-item"
          :class="{'nav-item-current': $route.path === '/admin/users'}"
          to="/admin/users"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
          >
            <circle
              cx="9"
              cy="8"
              r="3.2"
            />
            <path d="M3 19a6 6 0 0 1 12 0" />
            <path d="M16 5.5a3.2 3.2 0 0 1 0 6.2" />
            <path d="M21 19a6 6 0 0 0-4.2-5.7" />
          </svg>
          <span class="nav-label">Users</span>
        </router-link>
        <router-link
          v-if="perms.edit_metadata"
          class="nav-item"
          :class="{'nav-item-current': $route.path === '/admin/content'}"
          to="/admin/content"
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
            <path d="M9 18V6l10-2v12" />
            <circle
              cx="6"
              cy="18"
              r="2.5"
            />
            <circle
              cx="16"
              cy="16"
              r="2.5"
            />
          </svg>
          <span class="nav-label">Content</span>
        </router-link>
        <router-link
          v-if="perms.edit_metadata"
          class="nav-item"
          :class="{'nav-item-current': $route.path === '/admin/duplicates'}"
          to="/admin/duplicates"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.7"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <circle
              cx="9"
              cy="12"
              r="6"
            />
            <circle
              cx="15"
              cy="12"
              r="6"
            />
          </svg>
          <span class="nav-label">Duplicates</span>
          <span
            v-if="duplicatesPendingCount"
            class="mod-badge"
          >{{ duplicatesPendingCount }}</span>
        </router-link>
        <router-link
          v-if="perms.edit_metadata"
          class="nav-item"
          :class="{'nav-item-current': $route.path === '/admin/enrichment'}"
          to="/admin/enrichment"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.7"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <circle
              cx="12"
              cy="12"
              r="9"
            />
            <path d="M9 9l6 3-6 3z" />
          </svg>
          <span class="nav-label">Enrichment</span>
        </router-link>
        <router-link
          v-if="perms.approve_submissions"
          class="nav-item"
          :class="{'nav-item-current': $route.path === '/admin/moderation'}"
          to="/admin/moderation"
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
            <rect
              x="4"
              y="4"
              width="16"
              height="16"
              rx="3"
            />
            <path d="M9 12l2 2 4-5" />
          </svg>
          <span class="nav-label">Moderation</span>
          <span
            v-if="pendingCount"
            class="mod-badge"
          >{{ pendingCount }}</span>
        </router-link>
        <router-link
          v-if="perms.approve_submissions"
          class="nav-item"
          :class="{'nav-item-current': $route.path === '/admin/requests'}"
          to="/admin/requests"
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
            <circle
              cx="12"
              cy="12"
              r="9"
            />
            <path d="M12 8v4l3 2" />
          </svg>
          <span class="nav-label">Requests</span>
          <span
            v-if="requestsPendingCount"
            class="mod-badge"
          >{{ requestsPendingCount }}</span>
        </router-link>
        <router-link
          v-if="perms.manage_roles"
          class="nav-item"
          :class="{'nav-item-current': $route.path === '/admin/roles'}"
          to="/admin/roles"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
          >
            <circle
              cx="7.5"
              cy="15.5"
              r="3.8"
            />
            <path d="M10.5 12.5L20 3" />
            <path d="M16 7l3 3" />
          </svg>
          <span class="nav-label">Roles &amp; Permissions</span>
        </router-link>
        <router-link
          v-if="perms.view_reports"
          class="nav-item"
          :class="{'nav-item-current': $route.path === '/admin/downloads'}"
          to="/admin/downloads"
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
            <path d="M12 4v10" />
            <path d="M8 11l4 4 4-4" />
            <path d="M5 19h14" />
          </svg>
          <span class="nav-label">Downloads</span>
        </router-link>
        <router-link
          v-if="perms.view_reports"
          class="nav-item"
          :class="{'nav-item-current': $route.path === '/admin/reports'}"
          to="/admin/reports"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
          >
            <path d="M5 20V10" />
            <path d="M12 20V4" />
            <path d="M19 20v-6" />
          </svg>
          <span class="nav-label">Reports</span>
        </router-link>
        <router-link
          v-if="perms.view_reports"
          class="nav-item"
          :class="{'nav-item-current': $route.path === '/admin/insights'}"
          to="/admin/insights"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
          >
            <path d="M3 17l5-5 4 3 6-7" />
            <path d="M14 8h5v5" />
          </svg>
          <span class="nav-label">Insights</span>
        </router-link>
        <router-link
          v-if="perms.view_reports"
          class="nav-item"
          :class="{'nav-item-current': $route.path === '/admin/audit'}"
          to="/admin/audit"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
          >
            <path d="M4 5h16M4 12h16M4 19h10" />
          </svg>
          <span class="nav-label">Audit log</span>
        </router-link>
        <router-link
          v-if="perms.site_settings"
          class="nav-item"
          :class="{'nav-item-current': $route.path === '/admin/settings'}"
          to="/admin/settings"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
          >
            <path d="M4 8h9M17.5 8H20M4 16h2.5M11 16h9" />
            <circle
              cx="15.5"
              cy="8"
              r="2.2"
            />
            <circle
              cx="8.5"
              cy="16"
              r="2.2"
            />
          </svg>
          <span class="nav-label">Settings</span>
        </router-link>
      </nav>
      <div class="foot">
        <button
          type="button"
          class="foot-btn"
          @click="$router.push('/library')"
        >
          <svg
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path d="M15 6l-6 6 6 6" />
          </svg>
          <span class="foot-btn-label">Back to library</span>
        </button>
        <div class="version">
          CRATE · self-hosted
        </div>
      </div>
    </template>
  </aside>
</template>

<script>
export default {
  name: 'AppSidebar',
  props: {
    area: {
      type: String,
      default: 'member',
    },
  },
  data() {
    return {
      // The crate id currently hovered by a dragged track row.
      dragOverId: null,
    };
  },
  computed: {
    crates() {
      return this.$store.getters.stateCrates;
    },
    perms() {
      return this.$store.getters.userPermissions;
    },
    hasAdminAccess() {
      return this.$store.getters.hasAdminAccess;
    },
    pendingCount() {
      return this.$store.getters.statePendingCount;
    },
    duplicatesPendingCount() {
      return this.$store.getters.stateDuplicatesPendingCount;
    },
    requestsPendingCount() {
      return this.$store.getters.stateRequestsPendingCount;
    },
    requestsUnseenCount() {
      return this.$store.getters.stateRequestsSummary.unseen_resolved;
    },
    unseenReleases() {
      return this.$store.getters.stateUnseenReleases;
    },
    quota() {
      return this.$store.getters.stateQuota;
    },
    quotaCount() {
      if (!this.quota) {
        return '— / —';
      }
      const limit = this.quota.unlimited ? '∞' : this.quota.limit;
      return `${this.quota.used} / ${limit}`;
    },
    quotaPct() {
      if (!this.quota || this.quota.unlimited || !this.quota.limit) {
        return 0;
      }
      return Math.min(100, Math.round((this.quota.used / this.quota.limit) * 100));
    },
  },
  watch: {
    // The moderation badge only matters (and is only fetchable) once the
    // sidebar shows the admin nav.
    area: {
      immediate: true,
      handler(area) {
        if (area === 'admin') {
          this.$store.dispatch('fetchPendingCount');
          this.$store.dispatch('fetchDuplicatesPendingCount');
          this.$store.dispatch('fetchRequestsPendingCount');
        }
      },
    },
  },
  created() {
    this.$store.dispatch('fetchCrates');
    this.$store.dispatch('fetchRequestsSummary');
    if (this.area === 'member') {
      this.$store.dispatch('fetchFeedState');
    }
  },
  methods: {
    async newCrate() {
      try {
        const crate = await this.$store.dispatch('createCrate');
        this.$router.push(`/crate/${crate.id}`);
      } catch (error) {
        // The axios interceptor already surfaced the failure.
      }
    },
    onCrateLeave(crateId) {
      if (this.dragOverId === crateId) {
        this.dragOverId = null;
      }
    },
    onCrateDrop(crate, event) {
      this.dragOverId = null;
      const songId = Number(event.dataTransfer.getData('text/plain'));
      if (songId) {
        this.$store.dispatch('addTrackToCrate', {crateId: crate.id, songId});
      }
    },
  },
};
</script>

<style scoped>
.sidebar {
  width: var(--sidebar-w);
  flex: none;
  display: flex;
  flex-direction: column;
  background: var(--panel);
  border-right: 1px solid var(--line);
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 16px 14px;
}

.brand-mark {
  width: 30px;
  height: 30px;
  border-radius: 7px;
  background: var(--acc);
  display: flex;
  align-items: center;
  justify-content: center;
  flex: none;
  box-shadow: var(--shadow-brand);
}

.brand-name {
  font: 700 16px/1 var(--font-disp);
  letter-spacing: .02em;
}

.brand-sub {
  font: 500 9.5px/1.4 var(--font-mono);
  color: var(--dim-2);
  letter-spacing: .06em;
  margin-top: 3px;
}

.nav {
  flex: 1;
  overflow-y: auto;
  padding: 6px 10px 10px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.group-label {
  font: 600 10px var(--font-mono);
  letter-spacing: .12em;
  color: var(--dim-3);
  padding: 12px 8px 6px;
}

.group-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 8px 6px;
}

.group-label-text {
  font: 600 10px var(--font-mono);
  letter-spacing: .12em;
  color: var(--dim-3);
}

.group-actions {
  display: flex;
  align-items: center;
  gap: 9px;
}

.icon-btn {
  background: none;
  border: none;
  padding: 0;
  margin: 0;
  cursor: pointer;
  color: var(--dim);
  display: flex;
}

.icon-btn:hover:enabled {
  color: var(--acc);
}

.icon-btn:disabled {
  opacity: .45;
  cursor: default;
}

.crate-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  height: 34px;
  padding: 0 10px;
  border-radius: 8px;
  color: var(--txt-2);
  font: 500 12.5px var(--font-ui);
  text-align: left;
  transition: background .15s ease;
  box-sizing: border-box;
}

.crate-item:hover {
  background: var(--hover);
  color: var(--txt-2);
}

.crate-item.router-link-active {
  background: var(--hover);
}

.crate-item-over {
  background: color-mix(in oklab, var(--acc) 16%, transparent);
}

.crate-item-over .crate-dot {
  box-shadow: 0 0 0 3px color-mix(in oklab, var(--acc) 40%, transparent);
}

.crate-dot {
  width: 9px;
  height: 9px;
  border-radius: 3px;
  flex: none;
  /* Dragged rows must not fire enter/leave on the item's children. */
  pointer-events: none;
}

.crate-name {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  pointer-events: none;
}

.crate-globe {
  color: var(--dim-2);
  display: flex;
  flex: none;
  pointer-events: none;
}

.crate-count {
  font: 500 11px var(--font-mono);
  color: var(--dim-2);
  pointer-events: none;
}

.crates-empty {
  font: 400 12px var(--font-ui);
  color: var(--dim-2);
  padding: 4px 10px;
}

.nav-gap {
  height: 14px;
  flex: none;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 11px;
  width: 100%;
  height: 38px;
  padding: 0 11px;
  border: none;
  border-radius: var(--r-ctl);
  cursor: pointer;
  background: none;
  color: var(--txt-3);
  font: 500 13.5px var(--font-ui);
  text-align: left;
  transition: background .15s ease, color .15s ease;
  box-sizing: border-box;
}

.nav-item:hover {
  background: var(--hover);
  color: var(--txt);
}

.nav-item.router-link-active,
.nav-item.nav-item-current {
  background: var(--acc-soft-strong);
  color: var(--acc);
}

.mod-badge {
  flex: none;
  padding: 2px 8px;
  border-radius: var(--r-pill);
  background: rgba(255, 182, 46, .14);
  color: var(--warn);
  font: 600 11px var(--font-mono);
}

.nav-label {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.admin-badge {
  display: inline-flex;
  align-self: flex-start;
  align-items: center;
  gap: 6px;
  margin: 8px;
  padding: 4px 9px;
  border-radius: 6px;
  background: var(--acc-soft-strong);
  color: var(--acc);
  font: 600 10px var(--font-mono);
  letter-spacing: .1em;
}

.foot {
  padding: 12px 14px;
  border-top: 1px solid var(--line);
}

.quota-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font: 500 11px var(--font-mono);
  color: var(--muted);
  margin-bottom: 6px;
}

.quota-count {
  color: var(--txt-2);
}

.quota-bar {
  height: 5px;
  border-radius: 3px;
  background: rgba(255, 255, 255, .08);
  overflow: hidden;
}

.quota-fill {
  height: 100%;
  background: var(--acc);
  border-radius: 3px;
}

.foot-btn {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  height: 36px;
  padding: 0 11px;
  border: 1px solid var(--line-strong);
  border-radius: var(--r-ctl);
  cursor: pointer;
  background: rgba(255, 255, 255, .03);
  color: var(--txt-2);
  font: 600 12.5px var(--font-ui);
  transition: border-color .15s ease, color .15s ease;
  box-sizing: border-box;
}

.foot-btn:hover {
  border-color: var(--acc-border);
  color: var(--txt);
}

.foot-btn-label {
  flex: 1;
  text-align: left;
}

.version {
  margin-top: 10px;
  font: 500 10.5px var(--font-mono);
  color: var(--dim-3);
  letter-spacing: .04em;
}
</style>
