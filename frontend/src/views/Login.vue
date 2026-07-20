<template>
  <div class="gate">
    <div class="gate-card">
      <div class="gate-brand">
        <div class="gate-mark">
          <svg
            width="21"
            height="21"
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
        <div>
          <div class="gate-brand-name">
            CRATE
          </div>
          <div class="gate-brand-sub">
            SELF-HOSTED POOL
          </div>
        </div>
      </div>
      <div class="gate-title">
        Sign in to your pool
      </div>
      <div class="gate-sub">
        {{ localLogin ? 'Enter your member credentials to continue.' : 'Sign in with your organisation account.' }}
      </div>
      <form
        v-if="localLogin"
        @submit.prevent="submit"
      >
        <label
          class="gate-label"
          for="username"
        >USERNAME</label>
        <input
          id="username"
          v-model="form.username"
          type="text"
          name="username"
          class="gate-input"
        >
        <label
          class="gate-label"
          for="password"
        >PASSWORD</label>
        <input
          id="password"
          v-model="form.password"
          type="password"
          name="password"
          class="gate-input"
        >
        <p
          v-if="errorMessage"
          class="gate-error"
        >
          {{ errorMessage }}
        </p>
        <button
          type="submit"
          class="gate-submit"
        >
          Sign in
        </button>
      </form>
      <p
        v-else-if="errorMessage"
        class="gate-error"
      >
        {{ errorMessage }}
      </p>
      <template v-if="providers.length">
        <div
          v-if="localLogin"
          class="gate-divider"
        >
          <span>OR CONTINUE WITH</span>
        </div>
        <button
          v-for="provider in providers"
          :key="provider.id"
          type="button"
          class="gate-sso"
          @click="signInWith(provider.id)"
        >
          Continue with {{ provider.display_name }}
        </button>
      </template>
      <div class="gate-foot">
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="var(--ok)"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <rect
            x="5"
            y="11"
            width="14"
            height="9"
            rx="2"
          />
          <path d="M8 11V8a4 4 0 0 1 8 0v3" />
        </svg>
        TLS secured · self-hosted instance
      </div>
    </div>
  </div>
</template>

<script>
import axios from 'axios';
import { mapActions } from 'vuex';

// The SSO flow is a full-page redirect, so a failure comes back as a code in
// the query string. The backend never returns anything more specific than
// these (an error page must not become an account-enumeration oracle).
const SSO_ERRORS = {
  denied: 'Sign-in was cancelled.',
  expired: 'The sign-in attempt expired. Try again.',
  invalid: 'Sign-in failed. Try again.',
  not_permitted: 'This account is not permitted to sign in here. Ask your admin for access.',
  pending_approval: 'Your account was created and is awaiting admin approval.',
  domain_not_allowed: 'Your organisation\'s domain is not allowed on this pool.',
  already_linked: 'That identity is already linked to another account.',
  rate_limited: 'Too many attempts. Wait a minute and try again.',
};

export default {
  name: 'LoginItem',
  data() {
    return {
      form: {
        username: '',
        password:'',
      },
      errorMessage: '',
      localLogin: true,
      providers: [],
    };
  },
  created() {
    const code = this.$route.query.sso_error;
    if (code) {
      this.errorMessage = SSO_ERRORS[code] || SSO_ERRORS.invalid;
      this.$router.replace({query: {}});
    }
    return this.fetchMethods();
  },
  methods: {
    ...mapActions(['logIn']),
    async fetchMethods() {
      try {
        const {data} = await axios.get('auth/methods');
        this.localLogin = data.local_login;
        this.providers = data.providers;
      } catch (error) {
        // Fail open to the local form: a pool with no SSO configured (or a
        // backend that is briefly unhappy) must still be signable-into.
        this.localLogin = true;
        this.providers = [];
      }
    },
    signInWith(providerId) {
      // A full navigation, not an XHR: the OIDC dance is redirect-based.
      window.location.href = `${axios.defaults.baseURL}/auth/oidc/${providerId}/start`;
    },
    async submit() {
      this.errorMessage = '';
      try {
        const User = new FormData();
        User.append('username', this.form.username);
        User.append('password', this.form.password);
        await this.logIn(User);
        this.$router.push('/home');
      } catch (e) {
        const detail = e.response && e.response.data && e.response.data.detail;
        this.errorMessage =
          (typeof detail === 'string' && detail) ||
          'Invalid username or password.';
      }
    }
  }
}
</script>

<style scoped>
.gate {
  flex: 1;
  background: radial-gradient(1100px 560px at 72% -12%, color-mix(in oklab, var(--acc) 20%, var(--bg)), var(--bg));
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.gate-card {
  width: 384px;
  max-width: 100%;
  background: var(--card);
  border: 1px solid rgba(255, 255, 255, .09);
  border-radius: 18px;
  box-shadow: 0 30px 90px rgba(0, 0, 0, .6);
  padding: 30px;
  box-sizing: border-box;
}

.gate-brand {
  display: flex;
  align-items: center;
  gap: 11px;
  margin-bottom: 24px;
}

.gate-mark {
  width: 38px;
  height: 38px;
  border-radius: var(--r-ctl);
  background: var(--acc);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 16px color-mix(in oklab, var(--acc) 45%, transparent);
}

.gate-brand-name {
  font: 700 20px/1 var(--font-disp);
  letter-spacing: .02em;
}

.gate-brand-sub {
  font: 500 10px var(--font-mono);
  color: var(--dim-2);
  letter-spacing: .06em;
  margin-top: 3px;
}

.gate-title {
  font: 600 16px var(--font-disp);
  margin-bottom: 4px;
}

.gate-sub {
  font: 400 12.5px var(--font-ui);
  color: var(--muted);
  margin-bottom: 22px;
}

.gate-label {
  display: block;
  font: 600 10.5px var(--font-mono);
  letter-spacing: .06em;
  color: var(--muted);
  margin-bottom: 7px;
}

.gate-input {
  width: 100%;
  height: 42px;
  padding: 0 13px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, .12);
  background: var(--sunken);
  color: var(--txt);
  font: 400 13.5px var(--font-ui);
  margin-bottom: 14px;
  box-sizing: border-box;
}

.gate-input:focus {
  outline: none;
  border-color: var(--acc-border);
  box-shadow: 0 0 0 3px var(--acc-soft);
}

.gate-error {
  font: 400 12.5px var(--font-ui);
  color: var(--danger);
  margin: 0 0 14px;
}

.gate-submit {
  width: 100%;
  height: 44px;
  border-radius: 10px;
  border: none;
  background: var(--acc);
  color: var(--acc-ink);
  font: 600 14px var(--font-ui);
  cursor: pointer;
  margin: 6px 0 16px;
  transition: filter .15s ease;
}

.gate-submit:hover {
  filter: brightness(1.1);
}

.gate-divider {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 2px 0 14px;
}

.gate-divider::before,
.gate-divider::after {
  content: "";
  flex: 1;
  height: 1px;
  background: rgba(255, 255, 255, .09);
}

.gate-divider span {
  font: 600 10.5px var(--font-mono);
  letter-spacing: .06em;
  color: var(--dim-2);
}

.gate-sso {
  width: 100%;
  height: 42px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, .12);
  background: var(--sunken);
  color: var(--txt);
  font: 600 13.5px var(--font-ui);
  cursor: pointer;
  margin-bottom: 10px;
  transition: border-color .15s ease, box-shadow .15s ease;
}

.gate-sso:hover {
  border-color: var(--acc-border);
  box-shadow: 0 0 0 3px var(--acc-soft);
}

.gate-foot {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  margin-top: 6px;
  font: 400 11px var(--font-mono);
  color: var(--dim-2);
}
</style>
