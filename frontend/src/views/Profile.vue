<template>
  <section>
    <h1>Your Profile</h1>
    <hr><br>
    <div>
      <p><strong>Full Name:</strong> <span>{{ user.full_name }}</span></p>
      <p><strong>Username:</strong> <span>{{ user.username }}</span></p>
      <p>
        <button
          class="btn btn-primary"
          @click="deleteAccount()"
        >
          Delete Account
        </button>
      </p>
    </div>
  </section>
</template>

<script>
import { mapGetters, mapActions } from 'vuex';
export default {
  name: 'ProfileItem',
  computed: {
    ...mapGetters({user: 'stateUser' }),
  },  
  created: function() {
    return this.$store.dispatch('viewMe');
  },
  methods: {
    ...mapActions(['deleteUser']),
    async deleteAccount() {
      try {
        await this.deleteUser(this.user.id);
        await this.$store.dispatch('logOut');
        this.$router.push('/');
      } catch (error) {
        console.error(error);
      }
    }
  },
}
</script>
