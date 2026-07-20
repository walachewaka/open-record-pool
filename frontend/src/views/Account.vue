<template>
  <section class="account">
    <div class="ac-top">
      <div class="ac-member-card">
        <div class="ac-member-head">
          <div>
            <div class="ac-member-label">
              CURRENT MEMBERSHIP
            </div>
            <div class="ac-member-plan">
              {{ planName }} plan
            </div>
          </div>
          <span class="ac-active">ACTIVE</span>
        </div>
        <div class="ac-quota-line">
          <span>DOWNLOAD QUOTA</span>
          <span class="ac-quota-used">{{ quotaLabel }}</span>
        </div>
        <div class="ac-quota-bar">
          <div :style="{width: quotaPct}" />
        </div>
        <div class="ac-member-foot">
          <button
            type="button"
            class="ac-manage"
            @click="managePlan"
          >
            Manage plan
          </button>
          <span
            v-if="resetLabel"
            class="ac-renew"
          >Quota resets {{ resetLabel }}</span>
        </div>
      </div>
      <div class="ac-stats">
        <div class="ac-stat ac-stat-wide">
          <div class="ac-stat-label">
            LIFETIME DOWNLOADS
          </div>
          <div class="ac-stat-value">
            {{ statLabel(downloadsTotal) }}
          </div>
        </div>
        <div class="ac-stat-pair">
          <div class="ac-stat">
            <div class="ac-stat-label">
              CRATES
            </div>
            <div class="ac-stat-value">
              {{ crates.length }}
            </div>
          </div>
          <div class="ac-stat">
            <div class="ac-stat-label">
              FAVORITES
            </div>
            <div class="ac-stat-value">
              {{ statLabel(favoritesTotal) }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="ac-section-label">
      PLANS
    </div>
    <div class="ac-plans">
      <div
        v-for="plan in plans"
        :key="plan.name"
        class="ac-plan"
        :class="{'ac-plan-current': plan.name === planName}"
      >
        <span
          v-if="plan.name === planName"
          class="ac-current-badge"
        >CURRENT</span>
        <div class="ac-plan-name">
          {{ plan.name }}
        </div>
        <div class="ac-plan-price">
          {{ plan.price }}<span>/mo</span>
        </div>
        <div class="ac-plan-perks">
          <div
            v-for="perk in plan.perks"
            :key="perk"
          >
            {{ perk }}
          </div>
        </div>
      </div>
    </div>

    <div class="ac-section-label">
      BILLING
    </div>
    <div class="ac-billing">
      <div class="ac-billing-info">
        <div class="ac-billing-tile">
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
          >
            <rect
              x="3"
              y="5"
              width="18"
              height="14"
              rx="2"
            />
            <path d="M3 10h18" />
          </svg>
        </div>
        <div>
          <div class="ac-billing-title">
            No billing configured
          </div>
          <div class="ac-billing-sub">
            This self-hosted instance doesn't process payments — plans are informational.
          </div>
        </div>
      </div>
    </div>

    <div class="ac-sessions">
      <div class="ac-sessions-head">
        <h2 class="ac-sessions-title">
          Sign-in methods
        </h2>
      </div>
      <div class="ac-session-row">
        <div class="ac-session-meta">
          <div class="ac-session-ua">
            Password
          </div>
          <div class="ac-session-sub">
            {{ hasPassword ? 'Local account credentials' : 'Not set — this account signs in with SSO only' }}
          </div>
        </div>
        <span
          v-if="hasPassword"
          class="ac-session-badge"
        >Active</span>
      </div>
      <div
        v-for="identity in identities"
        :key="identity.id"
        class="ac-session-row"
      >
        <div class="ac-session-meta">
          <div class="ac-session-ua">
            {{ identity.provider_name }}
          </div>
          <div class="ac-session-sub">
            {{ identity.email || 'no email' }} ·
            {{ identity.last_login_at ? `used ${relativeTime(identity.last_login_at)}` : 'never used' }}
          </div>
        </div>
        <button
          type="button"
          class="ac-session-revoke"
          @click="unlinkIdentity(identity.id)"
        >
          Unlink
        </button>
      </div>
      <div class="ac-link-row">
        <button
          v-for="provider in unlinkedProviders"
          :key="provider.id"
          type="button"
          class="ac-link-btn"
          @click="linkProvider(provider.id)"
        >
          Link {{ provider.display_name }}
        </button>
      </div>
    </div>

    <div class="ac-sessions">
      <div class="ac-sessions-head">
        <h2 class="ac-sessions-title">
          Active sessions
        </h2>
        <button
          type="button"
          class="ac-logout-all"
          @click="logoutEverywhere"
        >
          Log out everywhere
        </button>
      </div>
      <div
        v-if="!sessions.length"
        class="ac-sessions-empty"
      >
        No active sessions to show.
      </div>
      <div
        v-for="s in sessions"
        :key="s.id"
        class="ac-session-row"
      >
        <div class="ac-session-meta">
          <div class="ac-session-ua">
            {{ s.user_agent || 'Unknown device' }}
            <span
              v-if="s.current"
              class="ac-session-badge"
            >This device</span>
          </div>
          <div class="ac-session-sub">
            {{ s.ip || 'unknown IP' }} · seen {{ relativeTime(s.last_seen_at) }}
          </div>
        </div>
        <button
          v-if="!s.current"
          type="button"
          class="ac-session-revoke"
          @click="revokeSession(s.id)"
        >
          Revoke
        </button>
      </div>
    </div>
  </section>
</template>

<script>
import axios from 'axios';
import { mapActions, mapGetters } from 'vuex';

import { toast } from '@/utils/toast';
import { relativeTime } from '@/utils/format';

// Informational tiers from the CRATE design; the current one is inferred
// from the instance's configured monthly quota (there is no billing backend).
// Mirrors the login gate's map: the SSO redirect can only ever come back with
// one of these codes (MOO-88).
const SSO_ERRORS = {
  denied: 'Sign-in was cancelled.',
  expired: 'The sign-in attempt expired. Try again.',
  invalid: 'Linking failed. Try again.',
  not_permitted: 'That identity may not be linked here.',
  pending_approval: 'That account is awaiting admin approval.',
  domain_not_allowed: 'Your organisation\'s domain is not allowed on this pool.',
  already_linked: 'That identity is already linked to another account.',
  rate_limited: 'Too many attempts. Wait a minute and try again.',
};

const PLANS = [
  {name: 'Free', price: '$0', perks: ['25 downloads / mo', 'MP3 320 only', 'Standard catalog']},
  {name: 'Pro', price: '$18', perks: ['200 downloads / mo', 'MP3 + WAV', 'Early access drops']},
  {name: 'Crew', price: '$39', perks: ['500 downloads / mo', 'All formats + stems', 'Full catalog + crate sharing']},
];

export default {
  name: 'AccountView',
  data() {
    return {
      plans: PLANS,
      downloadsTotal: null,
      favoritesTotal: null,
      sessions: [],
      identities: [],
      providers: [],
    };
  },
  computed: {
    ...mapGetters({
      quota: 'stateQuota',
      crates: 'stateCrates',
      user: 'stateUser',
    }),
    hasPassword() {
      // A session persisted before MOO-88 has no has_password field; those are
      // local accounts by definition.
      return !this.user || this.user.has_password !== false;
    },
    unlinkedProviders() {
      const linked = this.identities.map(identity => identity.provider);
      return this.providers.filter(provider => linked.indexOf(provider.id) === -1);
    },
    planName() {
      if (!this.quota) {
        return '—';
      }
      if (this.quota.unlimited || this.quota.limit > 200) {
        return 'Crew';
      }
      return this.quota.limit <= 25 ? 'Free' : 'Pro';
    },
    quotaLabel() {
      if (!this.quota) {
        return '—';
      }
      if (this.quota.unlimited) {
        return `${this.quota.used} used · unlimited`;
      }
      return `${this.quota.used} / ${this.quota.limit} used`;
    },
    quotaPct() {
      if (!this.quota || this.quota.unlimited || !this.quota.limit) {
        return '0%';
      }
      return `${Math.min(100, (this.quota.used / this.quota.limit) * 100)}%`;
    },
    resetLabel() {
      if (!this.quota || this.quota.unlimited) {
        return '';
      }
      // quota.month is "YYYY-MM" (UTC); the quota resets on the first of the
      // next month.
      const [year, month] = this.quota.month.split('-').map(Number);
      return new Date(year, month, 1).toLocaleDateString('en', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      });
    },
  },
  created() {
    this.fetchQuota();
    this.fetchCrates();
    this.fetchSessions();
    this.fetchIdentities();
    this.readLinkResult();
    return this.fetchTotals();
  },
  methods: {
    ...mapActions(['fetchQuota', 'fetchCrates']),
    relativeTime,
    readLinkResult() {
      // The link flow is a full-page redirect back to /profile.
      const {link, sso_error: ssoError} = this.$route.query;
      if (!link && !ssoError) {
        return;
      }
      if (link === 'ok') {
        toast('Sign-in method linked', 'ok');
      } else if (ssoError) {
        toast(SSO_ERRORS[ssoError] || SSO_ERRORS.invalid, 'error');
      }
      this.$router.replace({query: {}});
    },
    async fetchIdentities() {
      try {
        const [identities, methods] = await Promise.all([
          axios.get('users/me/identities'),
          axios.get('auth/methods'),
        ]);
        this.identities = identities.data;
        this.providers = methods.data.providers;
      } catch (error) {
        // Non-critical: the card falls back to the password row alone.
      }
    },
    linkProvider(providerId) {
      window.location.href = `${axios.defaults.baseURL}/auth/oidc/${providerId}/start?link=1`;
    },
    async unlinkIdentity(id) {
      try {
        await axios.delete(`users/me/identities/${id}`);
        this.identities = this.identities.filter(identity => identity.id !== id);
        toast('Sign-in method removed', 'ok');
      } catch (error) {
        const detail = error.response && error.response.data && error.response.data.detail;
        toast(detail || 'Could not remove that sign-in method', 'error');
      }
    },
    async fetchSessions() {
      try {
        const {data} = await axios.get('users/me/sessions');
        this.sessions = data;
      } catch (error) {
        // Non-critical: the card simply stays empty.
      }
    },
    async revokeSession(id) {
      try {
        await axios.delete(`users/me/sessions/${id}`);
        this.sessions = this.sessions.filter(s => s.id !== id);
        toast('Session revoked', 'ok');
      } catch (error) {
        toast('Could not revoke that session', 'error');
      }
    },
    async logoutEverywhere() {
      try {
        await axios.post('logout-all');
      } catch (error) {
        // Even if the call fails, clear the local session below.
      }
      await this.$store.dispatch('logOut');
      this.$router.push('/login');
    },
    async fetchTotals() {
      // Only the totals matter here, so ask for the smallest pages.
      try {
        const [downloads, favorites] = await Promise.all([
          axios.get('downloads', {params: {page_size: 1}}),
          axios.get('favorites', {params: {page_size: 1}}),
        ]);
        this.downloadsTotal = downloads.data.total;
        this.favoritesTotal = favorites.data.total;
      } catch (error) {
        // The stat cards simply keep their placeholder dashes.
      }
    },
    statLabel(value) {
      return value == null ? '—' : String(value);
    },
    managePlan() {
      toast('Plans are informational on this self-hosted instance', 'warn');
    },
  },
};
</script>

<style scoped>
.account {
  max-width: 960px;
}

.ac-top {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}

.ac-member-card {
  padding: 20px;
  border-radius: 14px;
  background: linear-gradient(135deg, color-mix(in oklab, var(--acc) 16%, var(--panel)), var(--panel));
  border: 1px solid color-mix(in oklab, var(--acc) 22%, transparent);
}

.ac-member-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
}

.ac-member-label {
  font: 600 10px var(--font-mono);
  letter-spacing: .1em;
  color: var(--muted);
  margin-bottom: 6px;
}

.ac-member-plan {
  font: 700 24px var(--font-disp);
}

.ac-active {
  padding: 6px 12px;
  border-radius: var(--r-pill);
  background: color-mix(in oklab, var(--acc) 20%, transparent);
  color: var(--acc);
  font: 600 11px var(--font-mono);
}

.ac-quota-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font: 500 12px var(--font-mono);
  color: var(--muted);
  margin-bottom: 7px;
}

.ac-quota-used {
  color: var(--txt);
}

.ac-quota-bar {
  height: 8px;
  border-radius: 4px;
  background: rgba(255, 255, 255, .09);
  overflow: hidden;
  margin-bottom: 16px;
}

.ac-quota-bar div {
  height: 100%;
  background: var(--acc);
  border-radius: 4px;
}

.ac-member-foot {
  display: flex;
  align-items: center;
  gap: 10px;
}

.ac-manage {
  height: 38px;
  padding: 0 16px;
  border-radius: 9px;
  border: none;
  cursor: pointer;
  background: var(--acc);
  color: var(--acc-ink);
  font: 600 13px var(--font-ui);
  transition: filter .15s ease;
}

.ac-manage:hover {
  filter: brightness(1.1);
}

.ac-renew {
  font: 400 12.5px var(--font-ui);
  color: var(--muted);
}

.ac-stats {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.ac-stat {
  padding: 16px 18px;
  border-radius: 14px;
  background: var(--panel);
  border: 1px solid var(--line);
}

.ac-stat-wide {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.ac-stat-pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.ac-stat-label {
  font: 600 10px var(--font-mono);
  letter-spacing: .08em;
  color: var(--dim-2);
  margin-bottom: 6px;
}

.ac-stat-value {
  font: 700 22px var(--font-disp);
  color: var(--txt);
}

.ac-stat-wide .ac-stat-value {
  font-size: 24px;
}

.ac-section-label {
  font: 600 11px var(--font-mono);
  letter-spacing: .1em;
  color: var(--dim-2);
  margin: 22px 0 12px;
}

.ac-plans {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 24px;
}

.ac-plan {
  position: relative;
  padding: 18px;
  border-radius: 13px;
  background: var(--panel);
  border: 1px solid var(--line);
}

.ac-plan-current {
  background: color-mix(in oklab, var(--acc) 8%, var(--panel));
  border: 1.5px solid color-mix(in oklab, var(--acc) 45%, transparent);
}

.ac-current-badge {
  position: absolute;
  top: 14px;
  right: 14px;
  padding: 3px 8px;
  border-radius: 6px;
  background: var(--acc);
  color: var(--acc-ink);
  font: 700 9px var(--font-mono);
  letter-spacing: .06em;
}

.ac-plan-name {
  font: 600 15px var(--font-disp);
  margin-bottom: 4px;
}

.ac-plan-price {
  font: 700 22px var(--font-disp);
  color: var(--txt);
  margin-bottom: 2px;
}

.ac-plan-price span {
  font: 400 12px var(--font-ui);
  color: var(--dim);
}

.ac-plan-perks {
  font: 400 12.5px/1.7 var(--font-ui);
  color: var(--muted);
  margin-top: 10px;
}

.ac-plan-current .ac-plan-perks {
  color: var(--txt-2);
}

.ac-billing {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 18px;
  border-radius: 13px;
  background: var(--panel);
  border: 1px solid var(--line);
}

.ac-billing-info {
  display: flex;
  align-items: center;
  gap: 13px;
}

.ac-billing-tile {
  width: 42px;
  height: 30px;
  border-radius: 6px;
  background: #1a2029;
  border: 1px solid var(--line-strong);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--txt-2);
  flex: none;
}

.ac-billing-title {
  font: 500 13px var(--font-ui);
  color: var(--txt);
}

.ac-billing-sub {
  font: 400 11.5px var(--font-ui);
  color: var(--dim);
}

@media (max-width: 860px) {
  .ac-top,
  .ac-plans {
    grid-template-columns: 1fr;
  }
}

.ac-sessions {
  margin-top: 20px;
  padding: 18px;
  border-radius: 13px;
  background: var(--panel);
  border: 1px solid var(--line);
}

.ac-sessions-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.ac-sessions-title {
  margin: 0;
  font: 600 14px var(--font-disp);
}

.ac-logout-all {
  padding: 7px 14px;
  border-radius: 9px;
  border: none;
  background: var(--acc);
  color: var(--acc-ink, #0b0b0b);
  font: 600 12px var(--font-ui);
  cursor: pointer;
}

.ac-sessions-empty {
  font: 400 12.5px var(--font-ui);
  color: var(--dim-2);
}

.ac-session-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-top: 1px solid var(--line);
}

.ac-session-row:first-of-type {
  border-top: none;
}

.ac-session-ua {
  font: 500 12.5px var(--font-ui);
  display: flex;
  align-items: center;
  gap: 8px;
}

.ac-session-badge {
  padding: 2px 7px;
  border-radius: 6px;
  background: var(--acc-soft);
  border: 1px solid var(--acc-border);
  color: var(--acc);
  font: 600 10px var(--font-mono);
}

.ac-session-sub {
  font: 400 11.5px var(--font-mono);
  color: var(--dim);
  margin-top: 3px;
}

.ac-session-revoke {
  flex: none;
  padding: 6px 12px;
  border-radius: 8px;
  border: 1px solid var(--line);
  background: transparent;
  color: var(--txt-2);
  font: 500 12px var(--font-ui);
  cursor: pointer;
}

.ac-link-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.ac-link-btn {
  padding: 8px 14px;
  border-radius: 9px;
  border: 1px solid rgba(255, 255, 255, .12);
  background: var(--sunken);
  color: var(--txt);
  font: 600 12.5px var(--font-ui);
  cursor: pointer;
  transition: border-color .15s ease, box-shadow .15s ease;
}

.ac-link-btn:hover {
  border-color: var(--acc-border);
  box-shadow: 0 0 0 3px var(--acc-soft);
}
</style>
