<template>
  <div class="crate-app">
    <template v-if="isLoggedIn">
      <div class="crate-body">
        <AppSidebar :area="area" />
        <main class="crate-main">
          <TopBar :area="area" />
          <div class="crate-content">
            <router-view />
          </div>
        </main>
      </div>
      <PlayerBar v-if="area === 'member'" />
    </template>
    <div
      v-else
      class="crate-public"
    >
      <router-view />
    </div>
    <ToastHost />
  </div>
</template>

<script>
// @ is an alias to /src
import AppSidebar from '@/components/AppSidebar.vue'
import PlayerBar from '@/components/PlayerBar.vue'
import ToastHost from '@/components/ToastHost.vue'
import TopBar from '@/components/TopBar.vue'
export default {
  components: {
    AppSidebar,
    PlayerBar,
    ToastHost,
    TopBar
  },
  computed: {
    isLoggedIn() {
      return this.$store.getters.isAuthenticated;
    },
    // member | admin — drives the sidebar variant and hides the player
    // outside the member area.
    area() {
      return this.$route.meta.area || 'member';
    }
  },
  watch: {
    // The sidebar meter and topbar pill need the quota as soon as a member
    // session exists; downloads keep it fresh afterwards. viewMe refreshes
    // the persisted user so role/permission changes apply on reload (MOO-72).
    isLoggedIn: {
      immediate: true,
      handler(loggedIn) {
        if (loggedIn) {
          this.$store.dispatch('viewMe');
          this.$store.dispatch('fetchQuota');
        }
      },
    },
  },
}
</script>
