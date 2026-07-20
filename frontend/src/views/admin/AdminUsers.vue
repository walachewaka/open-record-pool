<template>
  <section>
    <div class="au-toolbar">
      <div class="au-search">
        <span class="au-search-icon">
          <svg
            width="15"
            height="15"
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
          v-model="q"
          type="text"
          placeholder="Search members…"
        >
      </div>
      <SegmentedControl
        v-model="roleFilter"
        :options="roleFilters"
      />
      <button
        type="button"
        class="au-invite"
        @click="openInvite"
      >
        <svg
          width="15"
          height="15"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2.2"
          stroke-linecap="round"
        >
          <path d="M12 5v14M5 12h14" />
        </svg>
        Invite member
      </button>
    </div>
    <div class="au-statusbar">
      <SegmentedControl
        v-model="statusFilter"
        :options="statusFilters"
      />
    </div>

    <p
      v-if="errorMessage"
      class="au-error"
    >
      {{ errorMessage }}
    </p>

    <div
      v-if="!loading && !items.length"
      class="au-none"
    >
      No members match those filters.
    </div>
    <div
      v-else
      class="au-panel"
    >
      <div class="au-head">
        <span>Member</span>
        <span>Role</span>
        <span>Plan</span>
        <span>Status</span>
        <span class="au-h-r">Downloads</span>
        <span class="au-h-r">Joined</span>
      </div>
      <button
        v-for="user in items"
        :key="user.id"
        type="button"
        class="au-row"
        @click="openDrawer(user)"
      >
        <div class="au-member">
          <div
            class="au-avatar"
            :style="{background: tintForId(user.id)}"
          >
            {{ initialsFor(user.full_name || user.username) }}
          </div>
          <div class="au-member-meta">
            <div class="au-name">
              {{ user.full_name || user.username }}
            </div>
            <div class="au-mail">
              {{ user.email || user.username }}
            </div>
          </div>
        </div>
        <div
          class="au-role"
          :style="{color: roleColor(user.role)}"
        >
          <span
            class="au-role-dot"
            :style="{background: roleColor(user.role)}"
          />
          {{ capitalize(user.role) }}
        </div>
        <div class="au-plan">
          {{ capitalize(user.plan) }}
        </div>
        <div>
          <span
            class="au-pill"
            :style="{background: statusBg(user.status), color: statusColor(user.status)}"
          >
            <span
              class="au-pill-dot"
              :style="{background: statusColor(user.status)}"
            />
            {{ capitalize(user.status) }}
          </span>
        </div>
        <div class="au-dls">
          {{ fmtNum(user.downloads) }}
        </div>
        <div class="au-joined">
          {{ durationSince(user.joined) }} ago
        </div>
      </button>
    </div>

    <!-- Manage-member drawer -->
    <template v-if="drawer">
      <div
        class="au-backdrop"
        @click="closeDrawer"
      />
      <div class="au-drawer">
        <div class="au-drawer-head">
          <div class="au-drawer-title">
            Manage member
          </div>
          <button
            type="button"
            class="au-x"
            @click="closeDrawer"
          >
            <svg
              width="17"
              height="17"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
            >
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>
        <div class="au-drawer-body">
          <div class="au-drawer-summary">
            <div
              class="au-avatar au-avatar-lg"
              :style="{background: tintForId(drawer.id)}"
            >
              {{ initialsFor(drawer.full_name || drawer.username) }}
            </div>
            <div>
              <div class="au-drawer-name">
                {{ drawer.full_name || drawer.username }}
              </div>
              <div class="au-mail">
                {{ drawer.email || drawer.username }}
              </div>
            </div>
          </div>
          <div class="au-drawer-stats">
            <div class="au-stat">
              <div class="au-stat-label">
                DOWNLOADS
              </div>
              <div class="au-stat-value">
                {{ fmtNum(drawer.downloads) }}
              </div>
            </div>
            <div class="au-stat">
              <div class="au-stat-label">
                MEMBER FOR
              </div>
              <div class="au-stat-value">
                {{ durationSince(drawer.joined) }}
              </div>
            </div>
          </div>
          <div class="au-fields">
            <div>
              <label class="au-label">ROLE</label>
              <select
                :value="drawer.role"
                :disabled="drawer.role === 'owner'"
                :title="drawer.role === 'owner' ? 'The Owner cannot be demoted' : ''"
                @change="patchUser('role', $event.target.value)"
              >
                <template v-if="drawer.role === 'owner'">
                  <option value="owner">
                    Owner
                  </option>
                </template>
                <template v-else>
                  <option
                    v-for="role in assignableRoles"
                    :key="role"
                    :value="role"
                  >
                    {{ capitalize(role) }}
                  </option>
                </template>
              </select>
            </div>
            <div>
              <label class="au-label">PLAN</label>
              <select
                :value="drawer.plan"
                @change="patchUser('plan', $event.target.value)"
              >
                <option
                  v-for="plan in plans"
                  :key="plan"
                  :value="plan"
                >
                  {{ capitalize(plan) }}
                </option>
              </select>
            </div>
            <div>
              <label class="au-label">STATUS</label>
              <select
                :value="drawer.status"
                :disabled="drawer.role === 'owner'"
                @change="patchUser('status', $event.target.value)"
              >
                <option
                  v-for="status in statuses"
                  :key="status"
                  :value="status"
                >
                  {{ capitalize(status) }}
                </option>
              </select>
            </div>
          </div>
          <div class="au-identities">
            <div class="au-label">
              LINKED IDENTITIES
            </div>
            <div
              v-if="!identities.length"
              class="au-identities-empty"
            >
              No linked identities.
            </div>
            <div
              v-for="identity in identities"
              :key="identity.id"
              class="au-identity"
            >
              <span class="au-identity-chip">{{ identity.provider_name }}</span>
              <span class="au-identity-email">{{ identity.email || 'no email' }}</span>
              <button
                type="button"
                class="au-identity-unlink"
                @click="unlinkIdentity(identity.id)"
              >
                Unlink
              </button>
            </div>
          </div>
        </div>
        <div class="au-drawer-foot">
          <button
            type="button"
            class="au-danger au-trash"
            title="Delete member permanently"
            :disabled="drawer.role === 'owner'"
            @click="deleteUser"
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
              <path d="M4 7h16" />
              <path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
              <path d="M7 7l1 12a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2l1-12" />
            </svg>
          </button>
          <button
            type="button"
            class="au-danger au-suspend"
            :disabled="drawer.role === 'owner'"
            @click="toggleSuspend"
          >
            {{ drawer.status === 'suspended' ? 'Reinstate member' : 'Suspend member' }}
          </button>
          <button
            type="button"
            class="au-signout"
            title="Suspend + sign out = immediate lockout"
            @click="signOutAll"
          >
            Sign out all sessions
          </button>
          <button
            type="button"
            class="au-done"
            @click="closeDrawer"
          >
            Done
          </button>
        </div>
      </div>
    </template>

    <!-- Invite modal -->
    <div
      v-if="invite.open"
      class="au-modal-backdrop"
      @click="invite.open = false"
    >
      <div
        class="au-modal"
        @click.stop
      >
        <div class="au-modal-head">
          <div class="au-modal-title">
            Invite member
          </div>
          <button
            type="button"
            class="au-x"
            @click="invite.open = false"
          >
            <svg
              width="17"
              height="17"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
            >
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>
        <div class="au-modal-body">
          <div class="au-modal-grid">
            <div class="au-span-2">
              <label class="au-label">USERNAME</label>
              <input
                v-model="invite.username"
                type="text"
                placeholder="dj.name"
              >
            </div>
            <div class="au-span-2">
              <label class="au-label">FULL NAME</label>
              <input
                v-model="invite.fullName"
                type="text"
                placeholder="Full name"
              >
            </div>
            <div class="au-span-2">
              <label class="au-label">EMAIL</label>
              <input
                v-model="invite.email"
                type="email"
                placeholder="name@example.com"
              >
            </div>
            <div>
              <label class="au-label">ROLE</label>
              <select v-model="invite.role">
                <option
                  v-for="role in assignableRoles"
                  :key="role"
                  :value="role"
                >
                  {{ capitalize(role) }}
                </option>
              </select>
            </div>
            <div>
              <label class="au-label">PLAN</label>
              <select v-model="invite.plan">
                <option
                  v-for="plan in plans"
                  :key="plan"
                  :value="plan"
                >
                  {{ capitalize(plan) }}
                </option>
              </select>
            </div>
          </div>
        </div>
        <div class="au-modal-foot">
          <button
            type="button"
            class="au-cancel"
            @click="invite.open = false"
          >
            Cancel
          </button>
          <button
            type="button"
            class="au-done"
            :disabled="!invite.username.trim()"
            @click="sendInvite"
          >
            Send invite
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script>
import axios from 'axios';

import SegmentedControl from '@/components/admin/SegmentedControl.vue';
import { toast } from '@/utils/toast';
import {
  capitalize,
  durationSince,
  fmtNum,
  initialsFor,
  roleColor,
  statusBg,
  statusColor,
  tintForId,
} from '@/utils/format';

export default {
  name: 'AdminUsers',
  components: {
    SegmentedControl,
  },
  data() {
    return {
      items: [],
      q: '',
      roleFilter: '',
      statusFilter: '',
      loading: true,
      errorMessage: '',
      drawer: null,
      identities: [],
      invite: {open: false, username: '', fullName: '', email: '', role: 'member', plan: 'free'},
      searchDebounce: null,
      // The owner role is not assignable (single-owner invariant).
      assignableRoles: ['admin', 'curator', 'member'],
      plans: ['free', 'pro', 'crew'],
      statuses: ['active', 'suspended', 'pending', 'invited'],
    };
  },
  computed: {
    roleFilters() {
      return [
        {value: '', label: 'All'},
        {value: 'owner', label: 'Owner'},
        {value: 'admin', label: 'Admin'},
        {value: 'curator', label: 'Curator'},
        {value: 'member', label: 'Member'},
      ];
    },
    statusFilters() {
      return [
        {value: '', label: 'All'},
        {value: 'active', label: 'Active'},
        {value: 'suspended', label: 'Suspended'},
        {value: 'pending', label: 'Pending'},
        {value: 'invited', label: 'Invited'},
      ];
    },
  },
  watch: {
    q() {
      clearTimeout(this.searchDebounce);
      this.searchDebounce = setTimeout(() => this.fetchUsers(), 300);
    },
    roleFilter() {
      this.fetchUsers();
    },
    statusFilter() {
      this.fetchUsers();
    },
  },
  created() {
    return this.fetchUsers();
  },
  beforeUnmount() {
    clearTimeout(this.searchDebounce);
  },
  methods: {
    capitalize,
    durationSince,
    fmtNum,
    initialsFor,
    roleColor,
    statusBg,
    statusColor,
    tintForId,
    async fetchUsers() {
      this.loading = true;
      this.errorMessage = '';
      try {
        const {data} = await axios.get('admin/users', {
          params: {
            q: this.q.trim() || undefined,
            role: this.roleFilter || undefined,
            status: this.statusFilter || undefined,
            page: 1,
            page_size: 300,
          },
        });
        this.items = data.items;
      } catch (error) {
        this.errorMessage = this.detailOf(error, 'Could not load the members.');
      } finally {
        this.loading = false;
      }
    },
    detailOf(error, fallback) {
      const detail = error.response && error.response.data && error.response.data.detail;
      return (typeof detail === 'string' && detail) || fallback;
    },
    openDrawer(user) {
      this.drawer = {...user};
      this.fetchIdentities(user.id);
    },
    closeDrawer() {
      this.drawer = null;
      this.identities = [];
    },
    async fetchIdentities(userId) {
      this.identities = [];
      try {
        const {data} = await axios.get(`admin/users/${userId}/identities`);
        this.identities = data;
      } catch (error) {
        // Non-critical: the section simply shows its empty state.
      }
    },
    async unlinkIdentity(identityId) {
      try {
        await axios.delete(`admin/users/${this.drawer.id}/identities/${identityId}`);
        this.identities = this.identities.filter(identity => identity.id !== identityId);
        toast('Sign-in method removed', 'ok');
      } catch (error) {
        // A 409 here means it was the account's last way to sign in.
        toast(this.detailOf(error, 'Could not remove that sign-in method.'), 'warn');
      }
    },
    applyUpdate(updated) {
      this.items = this.items.map(user => (user.id === updated.id ? updated : user));
      if (this.drawer && this.drawer.id === updated.id) {
        this.drawer = {...updated};
      }
    },
    async patchUser(field, value) {
      try {
        const {data} = await axios.patch(`admin/users/${this.drawer.id}`, {[field]: value});
        this.applyUpdate(data);
        toast('User updated');
      } catch (error) {
        toast(this.detailOf(error, 'Could not update the user.'), 'warn');
      }
    },
    async toggleSuspend() {
      const suspending = this.drawer.status !== 'suspended';
      try {
        const {data} = await axios.patch(`admin/users/${this.drawer.id}`, {
          status: suspending ? 'suspended' : 'active',
        });
        this.applyUpdate(data);
        toast(suspending ? 'Member suspended' : 'Member reinstated');
      } catch (error) {
        toast(this.detailOf(error, 'Could not update the member.'), 'warn');
      }
    },
    async signOutAll() {
      try {
        const {data} = await axios.delete(`admin/users/${this.drawer.id}/sessions`);
        toast(`Revoked ${data.revoked} session(s)`);
      } catch (error) {
        toast(this.detailOf(error, 'Could not revoke sessions.'), 'warn');
      }
    },
    async deleteUser() {
      const name = this.drawer.full_name || this.drawer.username;
      if (!window.confirm(`Delete ${name} permanently? This cannot be undone.`)) {
        return;
      }
      try {
        await axios.delete(`admin/users/${this.drawer.id}`);
        this.items = this.items.filter(user => user.id !== this.drawer.id);
        this.drawer = null;
        toast('Member deleted');
      } catch (error) {
        toast(this.detailOf(error, 'Could not delete the member.'), 'warn');
      }
    },
    openInvite() {
      this.invite = {open: true, username: '', fullName: '', email: '', role: 'member', plan: 'free'};
    },
    async sendInvite() {
      try {
        await axios.post('admin/users', {
          username: this.invite.username.trim(),
          full_name: this.invite.fullName.trim() || null,
          email: this.invite.email.trim() || null,
          role: this.invite.role,
          plan: this.invite.plan,
          status: 'invited',
        });
        this.invite.open = false;
        toast('Invite sent');
        this.fetchUsers();
      } catch (error) {
        toast(this.detailOf(error, 'Could not create the invite.'), 'warn');
      }
    },
  },
};
</script>

<style scoped>
.au-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.au-search {
  position: relative;
  flex: 1;
  min-width: 220px;
  max-width: 320px;
}

.au-search-icon {
  position: absolute;
  left: 11px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--dim-2);
  display: flex;
}

.au-search input {
  width: 100%;
  height: 38px;
  padding: 0 12px 0 34px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line-strong);
  background: var(--raised);
  color: var(--txt);
  font: 400 13px var(--font-ui);
  box-sizing: border-box;
}

.au-search input::placeholder {
  color: var(--dim-2);
}

.au-search input:focus {
  outline: none;
  border-color: var(--acc-border);
}

.au-invite {
  margin-left: auto;
  height: 38px;
  padding: 0 15px;
  border-radius: var(--r-ctl);
  border: none;
  background: var(--acc);
  color: var(--acc-ink);
  font: 600 13px var(--font-ui);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 7px;
  transition: filter .15s ease;
}

.au-invite:hover {
  filter: brightness(1.1);
}

.au-statusbar {
  margin-bottom: 14px;
}

.au-error {
  color: var(--danger);
  font: 400 13px var(--font-ui);
}

.au-none {
  font: 400 13px var(--font-ui);
  color: var(--dim-2);
  padding: 22px 4px;
}

.au-panel {
  border: 1px solid var(--line);
  border-radius: 13px;
  overflow: hidden;
  background: var(--panel);
}

.au-head,
.au-row {
  display: grid;
  grid-template-columns: minmax(200px, 2fr) 96px 80px 116px 96px 92px;
  align-items: center;
  gap: 12px;
  padding: 0 16px;
}

.au-head {
  height: 38px;
  border-bottom: 1px solid rgba(255, 255, 255, .07);
  font: 600 10px var(--font-mono);
  letter-spacing: .08em;
  color: var(--dim-2);
  text-transform: uppercase;
}

.au-h-r {
  text-align: right;
}

.au-row {
  width: 100%;
  height: 58px;
  border: none;
  border-bottom: 1px solid rgba(255, 255, 255, .045);
  background: none;
  cursor: pointer;
  text-align: left;
  transition: background .15s ease;
}

.au-row:hover {
  background: rgba(255, 255, 255, .03);
}

.au-row:last-child {
  border-bottom: none;
}

.au-member {
  display: flex;
  align-items: center;
  gap: 11px;
  min-width: 0;
}

.au-avatar {
  width: 38px;
  height: 38px;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: none;
  font: 600 12px var(--font-mono);
  color: rgba(255, 255, 255, .8);
}

.au-avatar-lg {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  font: 600 17px var(--font-mono);
}

.au-member-meta {
  min-width: 0;
}

.au-name {
  font: 600 13px var(--font-ui);
  color: var(--txt);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.au-mail {
  font: 400 12px var(--font-mono);
  color: var(--dim);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.au-role {
  display: flex;
  align-items: center;
  gap: 6px;
  font: 600 12px var(--font-ui);
}

.au-role-dot {
  width: 6px;
  height: 6px;
  border-radius: 3px;
}

.au-plan {
  font: 500 12px var(--font-ui);
  color: var(--txt-3);
}

.au-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: var(--r-pill);
  font: 600 11px var(--font-ui);
}

.au-pill-dot {
  width: 6px;
  height: 6px;
  border-radius: 3px;
}

.au-dls {
  text-align: right;
  font: 600 12px var(--font-mono);
  color: var(--txt-2);
}

.au-joined {
  text-align: right;
  font: 400 12px var(--font-mono);
  color: var(--dim);
}

/* Drawer */

.au-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(4, 7, 11, .55);
  z-index: 40;
}

.au-drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: 400px;
  max-width: 92vw;
  z-index: 41;
  background: var(--card);
  border-left: 1px solid rgba(255, 255, 255, .09);
  box-shadow: -24px 0 60px rgba(0, 0, 0, .5);
  display: flex;
  flex-direction: column;
}

.au-drawer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, .07);
}

.au-drawer-title {
  font: 600 13px var(--font-disp);
}

.au-x {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--muted);
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  transition: background .15s ease, color .15s ease;
}

.au-x:hover {
  background: rgba(255, 255, 255, .06);
  color: var(--txt);
}

.au-drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.au-drawer-summary {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 22px;
}

.au-drawer-name {
  font: 700 17px var(--font-disp);
}

.au-drawer-stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 20px;
}

.au-stat {
  padding: 12px 14px;
  border-radius: 11px;
  background: rgba(255, 255, 255, .03);
  border: 1px solid var(--line);
}

.au-stat-label {
  font: 600 9.5px var(--font-mono);
  letter-spacing: .08em;
  color: var(--dim-2);
  margin-bottom: 5px;
}

.au-stat-value {
  font: 600 18px var(--font-disp);
}

.au-fields {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.au-label {
  display: block;
  font: 600 11px var(--font-mono);
  letter-spacing: .06em;
  color: var(--muted);
  margin-bottom: 7px;
}

.au-fields select,
.au-modal select {
  width: 100%;
  height: 40px;
  padding: 0 12px;
  border-radius: var(--r-ctl);
  border: 1px solid rgba(255, 255, 255, .12);
  background: var(--menu);
  color: var(--txt);
  font: 500 13px var(--font-ui);
  cursor: pointer;
  box-sizing: border-box;
}

.au-fields select:disabled {
  opacity: .55;
  cursor: default;
}

.au-identities {
  margin-top: 20px;
}

.au-identities-empty {
  margin-top: 8px;
  font: 400 12.5px var(--font-ui);
  color: var(--dim-2);
}

.au-identity {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 0;
  border-bottom: 1px solid var(--line);
}

.au-identity-chip {
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--acc-soft);
  border: 1px solid var(--acc-border);
  color: var(--acc);
  font: 600 10.5px var(--font-mono);
}

.au-identity-email {
  flex: 1;
  font: 400 11.5px var(--font-mono);
  color: var(--dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.au-identity-unlink {
  flex: none;
  padding: 5px 11px;
  border-radius: 8px;
  border: 1px solid var(--line);
  background: transparent;
  color: var(--txt-2);
  font: 500 12px var(--font-ui);
  cursor: pointer;
}

.au-drawer-foot {
  display: flex;
  gap: 10px;
  padding: 16px 20px;
  border-top: 1px solid rgba(255, 255, 255, .07);
}

.au-danger {
  border: 1px solid rgba(255, 82, 102, .35);
  background: rgba(255, 82, 102, .08);
  color: var(--danger);
  cursor: pointer;
  border-radius: var(--r-ctl);
  transition: background .15s ease;
}

.au-danger:hover:enabled {
  background: rgba(255, 82, 102, .18);
}

.au-danger:disabled {
  opacity: .4;
  cursor: default;
}

.au-trash {
  flex: none;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.au-suspend {
  flex: 1;
  height: 40px;
  font: 600 12.5px var(--font-ui);
}

.au-signout {
  flex: 1;
  height: 40px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--line);
  background: transparent;
  color: var(--txt-2);
  font: 600 12.5px var(--font-ui);
  cursor: pointer;
}

.au-done {
  flex: 1;
  height: 40px;
  border-radius: var(--r-ctl);
  border: none;
  background: var(--acc);
  color: var(--acc-ink);
  font: 600 12.5px var(--font-ui);
  cursor: pointer;
  transition: filter .15s ease;
}

.au-done:hover:enabled {
  filter: brightness(1.1);
}

.au-done:disabled {
  opacity: .5;
  cursor: default;
}

/* Invite modal */

.au-modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(4, 7, 11, .6);
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.au-modal {
  width: 480px;
  max-width: 100%;
  background: var(--modal);
  border: 1px solid var(--line-strong);
  border-radius: var(--r-modal);
  box-shadow: 0 30px 80px rgba(0, 0, 0, .6);
}

.au-modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 22px;
  border-bottom: 1px solid rgba(255, 255, 255, .07);
}

.au-modal-title {
  font: 700 16px var(--font-disp);
}

.au-modal-body {
  padding: 22px;
}

.au-modal-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.au-span-2 {
  grid-column: 1 / -1;
}

.au-modal input {
  width: 100%;
  height: 40px;
  padding: 0 12px;
  border-radius: var(--r-ctl);
  border: 1px solid rgba(255, 255, 255, .12);
  background: var(--sunken);
  color: var(--txt);
  font: 400 13.5px var(--font-ui);
  box-sizing: border-box;
}

.au-modal input:focus {
  outline: none;
  border-color: var(--acc-border);
}

.au-modal-foot {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  padding: 16px 22px;
  border-top: 1px solid rgba(255, 255, 255, .07);
}

.au-modal-foot .au-done {
  flex: none;
  padding: 0 18px;
}

.au-cancel {
  height: 40px;
  padding: 0 16px;
  border-radius: var(--r-ctl);
  border: 1px solid rgba(255, 255, 255, .12);
  background: none;
  color: var(--txt-2);
  font: 600 13px var(--font-ui);
  cursor: pointer;
  transition: color .15s ease;
}

.au-cancel:hover {
  color: var(--txt);
}
</style>
