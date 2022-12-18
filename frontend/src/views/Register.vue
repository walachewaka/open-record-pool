<template>
  <section>
    <form @submit.prevent="submit">
      <div class="mb-3">
        <label
          for="username"
          class="form-label"
        >Username:</label>
        <input
          v-model="user.username"
          type="text"
          name="username"
          class="form-control"
        >
      </div>
      <div class="mb-3">
        <label
          for="full_name"
          class="form-label"
        >Full Name:</label>
        <input
          v-model="user.full_name"
          type="text"
          name="full_name"
          class="form-control"
        >
      </div>
      <div class="mb-3">
        <label
          for="password"
          class="form-label"
        >Password:</label>
        <input
          v-model="user.password"
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
    <p v-if="errorMessage">
      {{ errorMessage }}
    </p>
  </section>
</template>




<script>
import { mapActions } from 'vuex';
export default {
  name: 'RegisterItem',
  data() {
    return {
      user: {
        username: '',
        full_name: '',
        password: '',
      },
      errorMessage: '',
    };
  },
  methods: {
    ...mapActions(['register']),
    async submit() {
      try {
        await this.register(this.user);
        this.$router.push('/dashboard');
      } catch (error) {
        this.errorMessage = 'Username already exists. Please try again.';
      }
    },
  },
};
</script>
