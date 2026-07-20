<template>
  <section class="ar-wrap">
    <p class="ar-intro">
      Toggle what each role can do. Changes apply instantly to every member with
      that role. The <b class="ar-owner">Owner</b> role always keeps full access.
    </p>

    <p
      v-if="errorMessage"
      class="ar-error"
    >
      {{ errorMessage }}
    </p>

    <div
      v-if="matrix"
      class="ar-panel"
    >
      <div
        class="ar-head"
        :style="gridStyle"
      >
        <div class="ar-head-perm">
          Permission
        </div>
        <div
          v-for="role in matrix.roles"
          :key="role.key"
          class="ar-head-role"
        >
          <div
            class="ar-role-name"
            :style="{color: roleColor(role.key)}"
          >
            <span
              class="ar-role-dot"
              :style="{background: roleColor(role.key)}"
            />
            {{ role.name }}
          </div>
          <div class="ar-role-desc">
            {{ role.description }}
          </div>
        </div>
      </div>
      <div
        v-for="permission in matrix.permissions"
        :key="permission.key"
        class="ar-row"
        :style="gridStyle"
      >
        <div class="ar-perm-label">
          {{ permission.label }}
        </div>
        <div
          v-for="role in matrix.roles"
          :key="role.key"
          class="ar-cell"
        >
          <ToggleSwitch
            :model-value="role.permissions[permission.key]"
            :locked="role.locked"
            @update:model-value="setPermission(role, permission.key, $event)"
          />
        </div>
      </div>
    </div>
  </section>
</template>

<script>
import axios from 'axios';

import ToggleSwitch from '@/components/admin/ToggleSwitch.vue';
import { toast } from '@/utils/toast';
import { roleColor } from '@/utils/format';

export default {
  name: 'AdminRoles',
  components: {
    ToggleSwitch,
  },
  data() {
    return {
      matrix: null,
      errorMessage: '',
    };
  },
  computed: {
    gridStyle() {
      const roles = this.matrix ? this.matrix.roles.length : 4;
      return {gridTemplateColumns: `minmax(200px, 2fr) repeat(${roles}, 1fr)`};
    },
  },
  created() {
    return this.fetchMatrix();
  },
  methods: {
    roleColor,
    async fetchMatrix() {
      this.errorMessage = '';
      try {
        const {data} = await axios.get('admin/roles');
        this.matrix = data;
      } catch (error) {
        const detail = error.response && error.response.data && error.response.data.detail;
        this.errorMessage =
          (typeof detail === 'string' && detail) || 'Could not load the permission matrix.';
      }
    },
    async setPermission(role, key, value) {
      // Optimistic flip; the PUT returns the whole matrix to resync.
      role.permissions[key] = value;
      try {
        const {data} = await axios.put(`admin/roles/${role.key}`, {
          permissions: role.permissions,
        });
        this.matrix = data;
        toast('Permissions updated');
      } catch (error) {
        await this.fetchMatrix();
        const detail = error.response && error.response.data && error.response.data.detail;
        toast(
          (typeof detail === 'string' && detail) || 'Could not update the permissions.',
          'warn'
        );
      }
    },
  },
};
</script>

<style scoped>
.ar-wrap {
  max-width: 920px;
}

.ar-intro {
  font: 400 13.5px/1.5 var(--font-ui);
  color: var(--muted);
  margin: 0 0 18px;
  max-width: 620px;
}

.ar-owner {
  color: var(--acc);
  font-weight: 600;
}

.ar-error {
  color: var(--danger);
  font: 400 13px var(--font-ui);
}

.ar-panel {
  border: 1px solid var(--line);
  border-radius: 14px;
  overflow: hidden;
  background: var(--panel);
}

.ar-head {
  display: grid;
  gap: 10px;
  padding: 16px;
  border-bottom: 1px solid rgba(255, 255, 255, .08);
  background: rgba(255, 255, 255, .02);
}

.ar-head-perm {
  font: 600 10px var(--font-mono);
  letter-spacing: .08em;
  color: var(--dim-2);
  text-transform: uppercase;
  display: flex;
  align-items: flex-end;
}

.ar-head-role {
  text-align: center;
}

.ar-role-name {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font: 700 13px var(--font-disp);
}

.ar-role-dot {
  width: 7px;
  height: 7px;
  border-radius: 4px;
}

.ar-role-desc {
  font: 400 10.5px/1.3 var(--font-ui);
  color: var(--dim-2);
  margin-top: 4px;
}

.ar-row {
  display: grid;
  gap: 10px;
  align-items: center;
  padding: 0 16px;
  height: 52px;
  border-bottom: 1px solid rgba(255, 255, 255, .045);
  transition: background .15s ease;
}

.ar-row:hover {
  background: rgba(255, 255, 255, .02);
}

.ar-row:last-child {
  border-bottom: none;
}

.ar-perm-label {
  font: 500 13px var(--font-ui);
  color: var(--txt);
}

.ar-cell {
  display: flex;
  justify-content: center;
}
</style>
