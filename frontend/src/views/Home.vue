<template>
  <section>
    <p>
      Open-Record-Pool is a self-hosted open-source web app that allows users
      and more importantly DJs with large collections to keep track of their
      library in a structured manner. This tool can be used to dynamically
      create playlists using Spotify’s API, manage song metadata with the help
      of PuddleTag, manage user’s access to your library but also share your
      playlists with others.
    </p>

    <div v-if="isLoggedIn" id="logout">
      <p id="logout">Click <a href="/dashboard">here</a> to view all notes.</p>
    </div>
    <p v-else>
      <span><a href="/register">Register</a></span>
      <span> or </span>
      <span><a href="/login">Log In</a></span>
    </p>
  </section>
</template>
<script>

export default {
  name: 'Home',
  computed : {
    isLoggedIn: function() {
      return this.$store.getters.isAuthenticated;
    }
  },
}
</script>
