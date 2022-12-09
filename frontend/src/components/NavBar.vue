<template>
  <header>
    <nav class="navbar navbar-expand-md navbar-dark bg-dark">
      <div class="container">
        <a class="navbar-brand" href="/">Open Record Pool</a>
        <div class="collapse navbar-collapse" id="navbarCollapse">
          <ul v-if="isLoggedIn" class="navbar-nav me-auto mb-2 mb-md-0">
            <li class="nav-item">Home</li>
            <li class="nav-item">Dashboard</li>
            <li class="nav-item">My Profile</li>
            <li class="nav-item">
              <a class="nav-link">Log Out</a>
            </li>
          </ul>
          <ul v-else="" class="navbar-nav me-auto mb-2 mb-md-0">
            <li class="nav-item">Home</li>
            <li class="nav-item">Register</li>
            <li class="nav-item">Log In</li>
          </ul>
        </div>
      </div>
    </nav>
  </header>
</template>
<script>
export default {
  name: 'NavBar',
  computed: {
    isLoggedIn: function() {
      return this.$store.getters.isAuthenticated;
    }
  },
  methods: {
    async logout () {
      await this.$store.dispatch('logOut');
      this.$router.push('/login');
    }
  },
}
</script>
<style scoped="">


a {
  cursor: pointer;
}
</style>
