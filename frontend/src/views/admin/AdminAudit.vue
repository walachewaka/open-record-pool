<template>
  <section>
    <div class="aa-toolbar">
      <SegmentedControl
        v-model="family"
        :options="familyOptions"
      />
      <input
        v-model="search"
        class="aa-search"
        type="text"
        placeholder="Search actor or target…"
        @keyup.enter="applySearch"
      >
    </div>

    <p
      v-if="errorMessage"
      class="aa-error"
    >
      {{ errorMessage }}
    </p>

    <div class="aa-panel">
      <div
        v-if="!rows.length"
        class="aa-empty"
      >
        No audit events match.
      </div>
      <table
        v-else
        class="aa-table"
      >
        <thead>
          <tr>
            <th>Time</th>
            <th>Event</th>
            <th>Actor</th>
            <th>Target</th>
            <th>IP</th>
            <th>Detail</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.id"
          >
            <td class="aa-mono">
              {{ row.created_at }}
            </td>
            <td>
              <span class="aa-chip">{{ row.event }}</span>
            </td>
            <td>{{ row.actor_username || '—' }}</td>
            <td class="aa-mono">
              {{ targetLabel(row) }}
            </td>
            <td class="aa-mono">
              {{ row.ip || '—' }}
            </td>
            <td>
              <pre
                v-if="row.detail"
                class="aa-detail"
              >{{ formatDetail(row.detail) }}</pre>
              <span v-else>—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div
      v-if="total > pageSize"
      class="aa-pager"
    >
      <button
        type="button"
        class="aa-page-btn"
        :disabled="page <= 1"
        @click="goto(page - 1)"
      >
        Prev
      </button>
      <span class="aa-page-info">Page {{ page }} of {{ pageCount }}</span>
      <button
        type="button"
        class="aa-page-btn"
        :disabled="page >= pageCount"
        @click="goto(page + 1)"
      >
        Next
      </button>
    </div>
  </section>
</template>

<script>
import axios from 'axios';

import SegmentedControl from '@/components/admin/SegmentedControl.vue';

export default {
  name: 'AdminAudit',
  components: {
    SegmentedControl,
  },
  data() {
    return {
      family: '',
      search: '',
      appliedSearch: '',
      rows: [],
      total: 0,
      page: 1,
      pageSize: 50,
      errorMessage: '',
    };
  },
  computed: {
    familyOptions() {
      return [
        {value: '', label: 'All'},
        {value: 'auth.', label: 'Auth'},
        {value: 'user.', label: 'Users'},
        {value: 'content.', label: 'Content'},
        {value: 'settings.', label: 'Settings'},
      ];
    },
    pageCount() {
      return Math.max(1, Math.ceil(this.total / this.pageSize));
    },
  },
  watch: {
    family() {
      this.page = 1;
      this.fetchAudit();
    },
  },
  created() {
    return this.fetchAudit();
  },
  methods: {
    applySearch() {
      this.appliedSearch = this.search.trim();
      this.page = 1;
      this.fetchAudit();
    },
    goto(page) {
      this.page = page;
      this.fetchAudit();
    },
    targetLabel(row) {
      if (!row.target_type && !row.target_id) {
        return '—';
      }
      return `${row.target_type || '?'}#${row.target_id || '?'}`;
    },
    formatDetail(detail) {
      try {
        return JSON.stringify(detail);
      } catch (e) {
        return '';
      }
    },
    async fetchAudit() {
      this.errorMessage = '';
      const params = {page: this.page, page_size: this.pageSize};
      if (this.family) {
        params.event = this.family;
      }
      if (this.appliedSearch) {
        params.q = this.appliedSearch;
      }
      try {
        const {data} = await axios.get('admin/audit', {params});
        this.rows = data.items;
        this.total = data.total;
      } catch (error) {
        const detail = error.response && error.response.data && error.response.data.detail;
        this.errorMessage =
          (typeof detail === 'string' && detail) || 'Could not load the audit log.';
      }
    },
  },
};
</script>

<style scoped>
.aa-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.aa-search {
  flex: none;
  width: 260px;
  padding: 8px 12px;
  border-radius: 9px;
  border: 1px solid var(--line);
  background: var(--panel);
  color: var(--txt);
  font: 400 13px var(--font-ui);
}

.aa-error {
  color: var(--danger);
  font: 400 13px var(--font-ui);
}

.aa-panel {
  padding: 6px;
  border-radius: 13px;
  background: var(--panel);
  border: 1px solid var(--line);
}

.aa-empty {
  padding: 18px;
  font: 400 12.5px var(--font-ui);
  color: var(--dim-2);
}

.aa-table {
  width: 100%;
  border-collapse: collapse;
}

.aa-table th {
  text-align: left;
  padding: 10px 12px;
  font: 600 10px var(--font-mono);
  letter-spacing: .08em;
  color: var(--dim-2);
  border-bottom: 1px solid var(--line);
}

.aa-table td {
  padding: 10px 12px;
  font: 400 12.5px var(--font-ui);
  border-bottom: 1px solid var(--line);
  vertical-align: top;
}

.aa-table tr:last-child td {
  border-bottom: none;
}

.aa-mono {
  font-family: var(--font-mono);
  color: var(--txt-2);
}

.aa-chip {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 7px;
  background: var(--acc-soft);
  border: 1px solid var(--acc-border);
  font: 600 11px var(--font-mono);
  color: var(--txt-2);
}

.aa-detail {
  margin: 0;
  max-width: 320px;
  white-space: pre-wrap;
  word-break: break-word;
  font: 400 11px var(--font-mono);
  color: var(--muted);
}

.aa-pager {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 16px;
}

.aa-page-btn {
  padding: 6px 14px;
  border-radius: 9px;
  border: 1px solid var(--line);
  background: var(--panel);
  color: var(--txt);
  font: 500 12px var(--font-ui);
  cursor: pointer;
}

.aa-page-btn:disabled {
  opacity: .5;
  cursor: default;
}

.aa-page-info {
  font: 500 12px var(--font-mono);
  color: var(--dim);
}
</style>
