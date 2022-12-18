<template>
  <section>
    <form @submit.prevent="submit">
      <div class="mb-3">
        <label
          for="username"
          class="form-label"
        >Username:</label>
        <input
          v-model="form.username"
          type="text"
          name="username"
          class="form-control"
        >
      </div>
      <div class="mb-3">
        <label
          for="password"
          class="form-label"
        >Password:</label>
        <input
          v-model="form.password"
          type="password"
          name="password"
          class="form-control"
        >
      </div>
      <button
        type="submit"
        class="btn btn-primary"
      >
        Submit
      </button>
    </form>
  </section>
</template>

<script>
import { mapActions } from 'vuex';
export default {
  name: 'LoginItem',
  data() {
    return {
      form: {
        username: '',
        password:'',
      }
    };
  },
  methods: {
    ...mapActions(['logIn']),
    async submit() {
      const User = new FormData();
      User.append('username', this.form.username);
      User.append('password', this.form.password);
      await this.logIn(User);
      this.$router.push('/dashboard');
    }
  }
}
</script>
