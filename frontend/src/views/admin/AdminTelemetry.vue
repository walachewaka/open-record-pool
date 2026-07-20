<template>
  <section>
    <div class="at-toolbar">
      <SegmentedControl
        v-model="board"
        :options="boardOptions"
      />
      <div
        v-if="status"
        class="at-chips"
      >
        <span
          class="at-chip"
          :class="status.enabled ? 'at-ok' : 'at-warn'"
        >
          Telemetry {{ status.enabled ? status.level : 'off' }}
        </span>
        <span
          class="at-chip"
          :class="status.es_reachable ? 'at-ok' : 'at-down'"
        >
          Elasticsearch {{ status.es_reachable ? 'connected' : 'down' }}
        </span>
        <span
          class="at-chip"
          :class="status.grafana_reachable ? 'at-ok' : 'at-down'"
        >
          Grafana {{ status.grafana_reachable ? 'up' : 'down' }}
        </span>
        <span class="at-chip at-neutral">
          Buffer <b>{{ status.buffer_size }}</b> / {{ status.buffer_capacity }}
        </span>
        <span
          class="at-chip"
          :class="status.events_dropped ? 'at-warn' : 'at-neutral'"
        >
          Dropped <b>{{ status.events_dropped }}</b>
        </span>
        <span class="at-chip at-neutral">
          Retention {{ status.retention_days }}d
        </span>
      </div>
    </div>

    <p
      v-if="errorMessage"
      class="at-error"
    >
      {{ errorMessage }}
    </p>

    <div class="at-panel">
      <div
        v-if="status && !status.enabled"
        class="at-empty"
      >
        <p>Telemetry is switched off for this instance.</p>
        <p class="at-hint">
          Set <code>TELEMETRY_LEVEL=detailed</code> (and
          <code>TELEMETRY_ENABLED=true</code>) on the backend and worker
          services, then restart the stack.
        </p>
      </div>
      <div
        v-else-if="status && !status.grafana_reachable"
        class="at-empty"
      >
        <p>Grafana is not reachable.</p>
        <p class="at-hint">
          The dashboards are served through this backend, so nothing renders
          until the Grafana container is up: check
          <code>docker compose ps grafana</code>.
        </p>
        <button
          type="button"
          class="at-retry"
          @click="fetchStatus"
        >
          Retry
        </button>
      </div>
      <iframe
        v-else-if="status"
        :key="board"
        class="at-frame"
        :src="frameSrc"
        title="Telemetry dashboard"
      />
    </div>
  </section>
</template>

<script>
// The Insights page (MOO-83): the four provisioned Grafana dashboards, embedded
// through the backend's authenticated /admin/grafana proxy. Grafana itself is
// docker-internal and has no published port -- the iframe src goes to OUR
// origin, the proxy checks view_reports, and only then talks to Grafana.
import axios from 'axios';

import SegmentedControl from '@/components/admin/SegmentedControl.vue';

const POLL_MS = 30000;

export default {
  name: 'AdminTelemetry',
  components: {
    SegmentedControl,
  },
  data() {
    return {
      board: 'orp-listening',
      status: null,
      errorMessage: '',
      timer: null,
    };
  },
  computed: {
    boardOptions() {
      return [
        {value: 'orp-listening', label: 'Listening'},
        {value: 'orp-library', label: 'Library'},
        {value: 'orp-engagement', label: 'Engagement'},
        {value: 'orp-system', label: 'System'},
      ];
    },
    frameSrc() {
      // axios.defaults.baseURL already ends with a slash (VUE_APP_BACKEND_URL).
      const base = axios.defaults.baseURL || '/';
      return `${base}admin/grafana/d/${this.board}?orgId=1&kiosk&theme=dark&refresh=30s`;
    },
  },
  created() {
    this.fetchStatus();
    this.timer = setInterval(this.fetchStatus, POLL_MS);
  },
  beforeUnmount() {
    if (this.timer) {
      clearInterval(this.timer);
    }
  },
  methods: {
    async fetchStatus() {
      try {
        const {data} = await axios.get('admin/telemetry/status');
        this.status = data;
        this.errorMessage = '';
      } catch (error) {
        const detail = error.response && error.response.data && error.response.data.detail;
        this.errorMessage = detail || 'Could not load the telemetry status.';
      }
    },
  },
};
</script>

<style scoped>
.at-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.at-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.at-chip {
  padding: 5px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-family: var(--font-mono);
  border: 1px solid transparent;
}

.at-chip b {
  font-weight: 600;
}

.at-ok {
  color: var(--ok);
  background: color-mix(in oklab, var(--ok) 12%, transparent);
  border-color: color-mix(in oklab, var(--ok) 30%, transparent);
}

.at-warn {
  color: var(--warn);
  background: color-mix(in oklab, var(--warn) 12%, transparent);
  border-color: color-mix(in oklab, var(--warn) 30%, transparent);
}

.at-down {
  color: var(--danger);
  background: color-mix(in oklab, var(--danger) 12%, transparent);
  border-color: color-mix(in oklab, var(--danger) 30%, transparent);
}

.at-neutral {
  color: var(--muted);
  background: var(--raised);
  border-color: var(--line);
}

.at-error {
  margin: 0 0 12px;
  color: var(--danger);
  font-size: 13px;
}

.at-panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--r-panel);
  overflow: hidden;
}

.at-frame {
  display: block;
  width: 100%;
  min-height: 78vh;
  border: 0;
  background: var(--bg);
}

.at-empty {
  padding: 48px 24px;
  text-align: center;
  color: var(--muted);
}

.at-hint {
  font-size: 13px;
  margin-top: 8px;
}

.at-hint code {
  font-family: var(--font-mono);
  color: var(--text);
}

.at-retry {
  margin-top: 16px;
  padding: 8px 18px;
  border: 0;
  border-radius: var(--r-pill);
  background: var(--acc);
  color: var(--acc-ink);
  font-weight: 600;
  cursor: pointer;
}
</style>
