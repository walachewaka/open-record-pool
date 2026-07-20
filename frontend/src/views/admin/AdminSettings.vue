<template>
  <section class="as-wrap">
    <SegmentedControl
      v-model="tab"
      class="as-tabs"
      :options="tabs"
    />

    <p
      v-if="errorMessage"
      class="as-error"
    >
      {{ errorMessage }}
    </p>

    <template v-if="form">
      <!-- Plans & Billing is informational; every other tab is settings rows. -->
      <div
        v-if="tab !== 'plans'"
        class="as-panel"
      >
        <div
          v-for="row in currentRows"
          :key="row.group + '.' + row.key"
          class="as-row"
        >
          <div class="as-row-text">
            <div class="as-row-label">
              {{ row.label }}
            </div>
            <div class="as-row-desc">
              {{ row.desc }}
            </div>
          </div>
          <ToggleSwitch
            v-if="row.type === 'toggle'"
            :model-value="!!form[row.group][row.key]"
            @update:model-value="form[row.group][row.key] = $event"
          />
          <div
            v-else-if="row.key === 'nas_source_path'"
            class="as-inline"
          >
            <input
              v-model="form[row.group][row.key]"
              type="text"
              class="as-input as-mono"
            >
            <button
              type="button"
              class="as-ghost-btn"
              :disabled="scanning"
              @click="scanNow"
            >
              {{ scanning ? 'Scanning…' : 'Scan now' }}
            </button>
          </div>
          <div
            v-else-if="row.type === 'number'"
            class="as-inline"
          >
            <input
              v-model="form[row.group][row.key]"
              type="number"
              class="as-input as-mono as-input-num"
            >
            <span
              v-if="row.suffix"
              class="as-suffix"
            >{{ row.suffix }}</span>
          </div>
          <div
            v-else-if="row.type === 'roles'"
            class="as-role-list"
          >
            <label
              v-for="role in autoApproveRoleChoices"
              :key="role"
              class="as-role"
            >
              <input
                type="checkbox"
                :checked="form.song_requests.auto_approve_roles.includes(role)"
                @change="toggleAutoApproveRole(role)"
              >
              {{ role }}
            </label>
          </div>
          <input
            v-else
            v-model="form[row.group][row.key]"
            :type="row.type === 'password' ? 'password' : 'text'"
            class="as-input"
            :class="{'as-mono': row.type === 'mono' || row.type === 'password'}"
          >
        </div>
      </div>

      <!-- Library tab extra: search status + reindex -->
      <div
        v-if="tab === 'library'"
        class="as-panel as-search-card"
      >
        <div class="as-search-left">
          <div class="as-search-icon">
            <svg
              width="18"
              height="18"
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
          </div>
          <div>
            <div class="as-row-label">
              Search engine · {{ form.library.search_status }}
            </div>
            <div class="as-search-status">
              <span class="as-dot" /> No external index · reads from PostgreSQL
            </div>
          </div>
        </div>
        <button
          type="button"
          class="as-ghost-btn"
          @click="reindex"
        >
          <svg
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.9"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M20 11a8 8 0 1 0-2 5.3" />
            <path d="M20 4v5h-5" />
          </svg>
          Reindex
        </button>
      </div>

      <!-- Integrations tab extra: fetch engine tool versions -->
      <div
        v-if="tab === 'integrations' && toolVersions"
        class="as-tools"
      >
        <span
          v-for="(version, name) in toolVersions"
          :key="name"
          class="as-tool"
        >{{ name }} {{ version }}</span>
      </div>

      <!-- Integrations tab extra: single sign-on (env-configured, read-only) -->
      <div
        v-if="tab === 'integrations' && sso"
        class="as-panel as-sso"
      >
        <div class="as-row-label">
          Single sign-on
        </div>
        <div class="as-row-desc">
          Providers are configured with environment variables — see INSTALL.md. Secrets are never stored in the database.
        </div>
        <div
          v-if="!sso.providers.length"
          class="as-sso-empty"
        >
          No identity providers configured.
        </div>
        <table
          v-else
          class="as-sso-table"
        >
          <thead>
            <tr>
              <th>Provider</th>
              <th>Issuer</th>
              <th>Policy</th>
              <th>Domains</th>
              <th>Discovery</th>
              <th>Linked</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="provider in sso.providers"
              :key="provider.id"
            >
              <td>{{ provider.display_name }}</td>
              <td class="as-mono-inline as-sso-issuer">
                {{ provider.issuer }}
              </td>
              <td>
                <span class="as-sso-chip">{{ provider.provisioning }}</span>
              </td>
              <td>{{ provider.allowed_domains.join(', ') || '—' }}</td>
              <td>
                <span
                  class="as-sso-chip"
                  :class="'as-sso-' + provider.discovery"
                >{{ provider.discovery }}</span>
              </td>
              <td>{{ provider.linked_identities }}</td>
            </tr>
          </tbody>
        </table>
        <div
          v-for="provider in sso.providers"
          :key="provider.id + '-uri'"
          class="as-sso-uri"
          @click="copyRedirectUri(provider.redirect_uri)"
        >
          <span class="as-sso-uri-label">{{ provider.display_name }} redirect URI</span>
          <code>{{ provider.redirect_uri }}</code>
        </div>
        <div class="as-sso-flags">
          <span class="as-sso-chip">Local login: {{ sso.local_login ? 'on' : 'off' }}</span>
          <span class="as-sso-chip">Email auto-link: {{ sso.email_autolink ? 'on' : 'off' }}</span>
        </div>
      </div>

      <!-- Plans & Billing (informational) -->
      <template v-if="tab === 'plans'">
        <div class="as-plans">
          <div
            v-for="plan in plans"
            :key="plan.name"
            class="as-plan-card"
          >
            <div class="as-plan-name">
              {{ plan.name }}
            </div>
            <div class="as-plan-price">
              {{ plan.price }}
            </div>
            <div class="as-plan-desc">
              {{ plan.desc }}
            </div>
          </div>
        </div>
        <div class="as-panel as-billing-note">
          Plans are informational — the download quota is set instance-wide by
          <span class="as-mono-inline">DOWNLOAD_QUOTA_MONTHLY</span> and no billing
          backend is connected.
        </div>
      </template>

      <div
        v-if="tab !== 'plans'"
        class="as-foot"
      >
        <button
          type="button"
          class="as-ghost-btn"
          :disabled="!dirty"
          @click="reset"
        >
          Reset
        </button>
        <button
          type="button"
          class="as-save-btn"
          :disabled="!dirty || saving"
          @click="save"
        >
          {{ saving ? 'Saving…' : 'Save changes' }}
        </button>
      </div>
    </template>
  </section>
</template>

<script>
import axios from 'axios';

import SegmentedControl from '@/components/admin/SegmentedControl.vue';
import ToggleSwitch from '@/components/admin/ToggleSwitch.vue';
import { pollJob } from '@/utils/jobs';
import { toast } from '@/utils/toast';

// The editable settings rows per tab; keys mirror the backend's grouped
// settings store exactly (unknown keys are rejected with a 422).
const ROWS = [
  {group: 'general', key: 'pool_name', label: 'Pool name', desc: 'Shown in the sidebar and browser title', type: 'text'},
  {group: 'general', key: 'tagline', label: 'Tagline', desc: 'A short description of your pool', type: 'text'},
  {group: 'general', key: 'public_signup', label: 'Public sign-up', desc: 'Stored for reference — registration stays admin-gated', type: 'toggle'},
  {group: 'general', key: 'require_approval', label: 'Require approval', desc: 'New uploads enter the moderation queue by default', type: 'toggle'},
  {group: 'library', key: 'nas_source_path', label: 'Library source', desc: 'The read-only /music mount the scanner ingests from', type: 'mono'},
  {group: 'library', key: 'strip_unsafe_tags', label: 'Strip unsafe tag comments', desc: 'Remove injected comments from MP3 tags on import', type: 'toggle'},
  {group: 'library', key: 'dedupe', label: 'Detect duplicates on import', desc: 'Skip files whose artist, title and duration already exist', type: 'toggle'},
  {group: 'storage', key: 'media_path', label: 'Media path', desc: 'The writable volume admin uploads land on', type: 'mono'},
  {group: 'storage', key: 'max_upload_mb', label: 'Max upload size', desc: 'Per-file limit in megabytes', type: 'number', suffix: 'MB'},
  {group: 'storage', key: 'transcode', label: 'Transcode on upload', desc: 'Stored for reference — no transcoder is installed', type: 'toggle'},
  {group: 'storage', key: 'keep_wav', label: 'Keep WAV masters', desc: 'Retain lossless originals for future WAV downloads', type: 'toggle'},
  {group: 'storage', key: 'high_performance_mode', label: 'High-performance mode', desc: 'Stored for reference — tunes future streaming behaviour', type: 'toggle'},
  {group: 'integrations', key: 'smtp_host', label: 'SMTP host', desc: 'Used for invites and password resets', type: 'mono'},
  {group: 'integrations', key: 'smtp_port', label: 'SMTP port', desc: 'Usually 587 (STARTTLS) or 465', type: 'number'},
  {group: 'integrations', key: 'smtp_user', label: 'SMTP user', desc: 'Login for the mail server', type: 'mono'},
  {group: 'integrations', key: 'smtp_password', label: 'SMTP password', desc: 'Stored in the instance settings', type: 'password'},
  {group: 'integrations', key: 'webhook_url', label: 'Discord webhook', desc: 'Post new releases to your server', type: 'mono'},
  {group: 'integrations', key: 's3_bucket', label: 'S3 backup bucket', desc: 'Nightly off-site backup target', type: 'mono'},
  {group: 'integrations', key: 's3_region', label: 'S3 region', desc: 'Region of the backup bucket', type: 'mono'},
  {group: 'integrations', key: 's3_access_key', label: 'S3 access key', desc: 'Credentials for the backup bucket', type: 'mono'},
  {group: 'integrations', key: 's3_secret_key', label: 'S3 secret key', desc: 'Stored in the instance settings', type: 'password'},
  {group: 'integrations', key: 'downloads_enabled', label: 'Download engine', desc: 'Master switch for the URL fetch engine', type: 'toggle'},
  {group: 'integrations', key: 'downloads_youtube', label: 'YouTube', desc: 'Owner-enabled integration — check the legality of source ripping in your jurisdiction', type: 'toggle'},
  {group: 'integrations', key: 'downloads_soundcloud', label: 'SoundCloud', desc: 'Owner-enabled integration — check the legality of source ripping in your jurisdiction', type: 'toggle'},
  {group: 'integrations', key: 'downloads_spotify', label: 'Spotify', desc: 'Owner-enabled integration — check the legality of source ripping in your jurisdiction', type: 'toggle'},
  {group: 'integrations', key: 'downloads_require_approval', label: 'Require approval', desc: 'Fetched tracks enter the moderation queue', type: 'toggle'},
  {group: 'integrations', key: 'downloads_daily_limit', label: 'Daily limit', desc: 'Per-user fetches allowed each day', type: 'number', suffix: 'per day'},
  {group: 'integrations', key: 'beatport_auto_enrich', label: 'Beatport auto-enrich', desc: 'Auto-enqueue Beatport enrichment on library scan/upload — see Admin → Enrichment for provider status', type: 'toggle'},
  {group: 'song_requests', key: 'enabled', label: 'Accept song requests', desc: 'Master switch — submitting 403s when off', type: 'toggle'},
  {group: 'song_requests', key: 'auto_approve_roles', label: 'Auto-approve roles', desc: 'These roles skip moderation — Owner is always auto-approved', type: 'roles'},
  {group: 'song_requests', key: 'daily_quota', label: 'Daily quota', desc: 'Requests a member may submit each day, 0 = unlimited', type: 'number', suffix: 'per day'},
];

const NUMBER_KEYS = [
  ['storage', 'max_upload_mb'],
  ['integrations', 'smtp_port'],
  ['integrations', 'downloads_daily_limit'],
  ['song_requests', 'daily_quota'],
];

const AUTO_APPROVE_ROLE_CHOICES = ['admin', 'curator', 'member'];

export default {
  name: 'AdminSettings',
  components: {
    SegmentedControl,
    ToggleSwitch,
  },
  data() {
    return {
      saved: null,
      form: null,
      tab: 'general',
      saving: false,
      scanning: false,
      errorMessage: '',
      toolVersions: null,
      sso: null,
      plans: [
        {name: 'Free', price: '$0', desc: 'Browse & stream, limited downloads'},
        {name: 'Pro', price: '$18', desc: 'Full monthly download quota'},
        {name: 'Crew', price: '$39', desc: 'For collectives sharing one pool'},
      ],
    };
  },
  computed: {
    tabs() {
      return [
        {value: 'general', label: 'General'},
        {value: 'library', label: 'Library'},
        {value: 'storage', label: 'Storage'},
        {value: 'plans', label: 'Plans & Billing'},
        {value: 'integrations', label: 'Integrations'},
        {value: 'song_requests', label: 'Requests'},
      ];
    },
    currentRows() {
      return ROWS.filter(row => row.group === this.tab);
    },
    autoApproveRoleChoices() {
      return AUTO_APPROVE_ROLE_CHOICES;
    },
    dirty() {
      return JSON.stringify(this.form) !== JSON.stringify(this.saved);
    },
  },
  created() {
    this.fetchProviders();
    this.fetchSso();
    return this.fetchSettings();
  },
  methods: {
    async fetchSso() {
      // Read-only: the registry is environment config (MOO-88), so there is
      // nothing to edit here — this reports what the backend actually loaded.
      try {
        const {data} = await axios.get('admin/sso/providers');
        this.sso = data;
      } catch (error) {
        this.sso = null;
      }
    },
    async copyRedirectUri(uri) {
      try {
        await navigator.clipboard.writeText(uri);
        toast('Copied', 'ok');
      } catch (error) {
        toast('Could not copy — select the URI manually', 'warn');
      }
    },
    async fetchProviders() {
      // Tool versions are informational; a missing/disabled engine just hides
      // the version strip.
      try {
        const {data} = await axios.get('fetch/providers');
        this.toolVersions = data.tool_versions;
      } catch (error) {
        this.toolVersions = null;
      }
    },
    async fetchSettings() {
      this.errorMessage = '';
      try {
        const {data} = await axios.get('admin/settings');
        this.saved = data;
        this.form = JSON.parse(JSON.stringify(data));
      } catch (error) {
        const detail = error.response && error.response.data && error.response.data.detail;
        this.errorMessage =
          (typeof detail === 'string' && detail) || 'Could not load the settings.';
      }
    },
    reset() {
      this.form = JSON.parse(JSON.stringify(this.saved));
    },
    toggleAutoApproveRole(role) {
      const roles = this.form.song_requests.auto_approve_roles;
      this.form.song_requests.auto_approve_roles = roles.includes(role)
        ? roles.filter(existing => existing !== role)
        : [...roles, role];
    },
    async save() {
      const payload = JSON.parse(JSON.stringify(this.form));
      // Number inputs bind as strings; the backend stores what it is given.
      NUMBER_KEYS.forEach(([group, key]) => {
        payload[group][key] = Number(payload[group][key]) || 0;
      });
      this.saving = true;
      try {
        const {data} = await axios.put('admin/settings', payload);
        this.saved = data;
        this.form = JSON.parse(JSON.stringify(data));
        toast('Settings saved');
      } catch (error) {
        const detail = error.response && error.response.data && error.response.data.detail;
        toast((typeof detail === 'string' && detail) || 'Could not save the settings.', 'warn');
      } finally {
        this.saving = false;
      }
    },
    async scanNow() {
      this.scanning = true;
      try {
        // The scan is a background job since MOO-77: a 202 envelope. Inline
        // mode returns it already succeeded; otherwise poll until terminal.
        const {data} = await axios.post('admin/settings/scan');
        const job = data.status === 'succeeded' ? data : await pollJob(data.id);
        const result = job.result;
        toast(
          `Scan complete · ${result.files_parsed} files parsed, ` +
            `${result.songs_created} new, ${result.songs_total} total`
        );
      } catch (error) {
        const detail = error.response && error.response.data && error.response.data.detail;
        toast((typeof detail === 'string' && detail) || 'The library scan failed.', 'warn');
      } finally {
        this.scanning = false;
      }
    },
    async reindex() {
      try {
        const {data} = await axios.post('admin/settings/reindex');
        toast(data.message || 'Reindex requested');
      } catch (error) {
        toast('The reindex request failed.', 'warn');
      }
    },
  },
};
</script>

<style scoped>
.as-wrap {
  max-width: 820px;
}

.as-tabs {
  margin-bottom: 20px;
}

.as-error {
  color: var(--danger);
  font: 400 13px var(--font-ui);
}

.as-panel {
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--panel);
  overflow: hidden;
}

.as-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 18px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, .05);
}

.as-row:last-child {
  border-bottom: none;
}

.as-row-text {
  min-width: 0;
}

.as-row-label {
  font: 600 13.5px var(--font-ui);
}

.as-row-desc {
  font: 400 12px var(--font-ui);
  color: var(--dim);
  margin-top: 2px;
}

.as-input {
  width: 260px;
  height: 38px;
  padding: 0 12px;
  border-radius: var(--r-ctl);
  border: 1px solid rgba(255, 255, 255, .12);
  background: var(--sunken);
  color: var(--txt);
  font: 400 13px var(--font-ui);
  box-sizing: border-box;
  flex: none;
}

.as-input:focus {
  outline: none;
  border-color: var(--acc-border);
}

.as-mono {
  font-family: var(--font-mono);
  font-size: 12.5px;
  color: var(--txt-2);
}

.as-input-num {
  width: 90px;
  text-align: center;
}

.as-inline {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}

.as-inline .as-input {
  width: 220px;
}

.as-inline .as-input-num {
  width: 90px;
}

.as-suffix {
  font: 500 12px var(--font-mono);
  color: var(--dim);
}

.as-role-list {
  display: flex;
  gap: 14px;
  flex: none;
}

.as-role {
  display: flex;
  align-items: center;
  gap: 6px;
  font: 500 12.5px var(--font-ui);
  color: var(--txt-2);
  text-transform: capitalize;
  cursor: pointer;
}

.as-ghost-btn {
  height: 38px;
  padding: 0 14px;
  border-radius: var(--r-ctl);
  border: 1px solid rgba(255, 255, 255, .12);
  background: rgba(255, 255, 255, .03);
  color: var(--txt-2);
  font: 600 12px var(--font-ui);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 7px;
  flex: none;
  transition: color .15s ease;
}

.as-ghost-btn:hover:enabled {
  color: var(--txt);
}

.as-ghost-btn:disabled {
  opacity: .5;
  cursor: default;
}

.as-search-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 18px 20px;
  margin-top: 16px;
}

.as-search-left {
  display: flex;
  align-items: center;
  gap: 13px;
}

.as-search-icon {
  width: 36px;
  height: 36px;
  border-radius: 9px;
  background: rgba(53, 208, 122, .14);
  color: var(--ok);
  display: flex;
  align-items: center;
  justify-content: center;
}

.as-search-status {
  font: 400 12px var(--font-mono);
  color: var(--dim);
  margin-top: 3px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.as-dot {
  width: 7px;
  height: 7px;
  border-radius: 4px;
  background: var(--ok);
}

.as-tools {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 12px;
  padding: 0 4px;
}

.as-tool {
  font: 400 11.5px var(--font-mono);
  color: var(--dim-2);
}

.as-plans {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.as-plan-card {
  padding: 16px;
  border-radius: 12px;
  background: var(--panel);
  border: 1px solid var(--line);
}

.as-plan-name {
  font: 600 13px var(--font-disp);
  margin-bottom: 10px;
}

.as-plan-price {
  font: 600 20px var(--font-mono);
  margin-bottom: 8px;
}

.as-plan-desc {
  font: 400 12px var(--font-ui);
  color: var(--muted);
}

.as-billing-note {
  padding: 18px 20px;
  font: 400 13px/1.5 var(--font-ui);
  color: var(--muted);
}

.as-mono-inline {
  font: 500 12px var(--font-mono);
  color: var(--txt-2);
}

.as-foot {
  position: sticky;
  bottom: 0;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 18px;
  padding: 12px 0;
  background: linear-gradient(180deg, transparent, var(--bg) 30%);
}

.as-save-btn {
  height: 40px;
  padding: 0 20px;
  border-radius: var(--r-ctl);
  border: none;
  background: var(--acc);
  color: var(--acc-ink);
  font: 600 13px var(--font-ui);
  cursor: pointer;
  transition: filter .15s ease;
}

.as-save-btn:hover:enabled {
  filter: brightness(1.1);
}

.as-save-btn:disabled {
  opacity: .5;
  cursor: default;
}

.as-sso {
  margin-top: 12px;
  padding: 18px;
}

.as-sso-empty {
  margin-top: 12px;
  font: 400 12.5px var(--font-ui);
  color: var(--dim-2);
}

.as-sso-table {
  width: 100%;
  margin-top: 14px;
  border-collapse: collapse;
  font: 400 12.5px var(--font-ui);
}

.as-sso-table th {
  text-align: left;
  padding: 6px 10px 6px 0;
  font: 600 10px var(--font-mono);
  letter-spacing: .08em;
  color: var(--dim-2);
  border-bottom: 1px solid var(--line);
}

.as-sso-table td {
  padding: 9px 10px 9px 0;
  border-bottom: 1px solid var(--line);
  color: var(--txt-2);
}

.as-sso-issuer {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.as-sso-chip {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--acc-soft);
  border: 1px solid var(--acc-border);
  color: var(--acc);
  font: 600 10.5px var(--font-mono);
}

.as-sso-ok {
  color: var(--ok);
}

.as-sso-error {
  color: var(--danger);
}

.as-sso-uri {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 10px;
  padding: 9px 12px;
  border-radius: 9px;
  background: var(--sunken);
  border: 1px solid var(--line);
  cursor: pointer;
}

.as-sso-uri-label {
  font: 500 11.5px var(--font-ui);
  color: var(--muted);
}

.as-sso-uri code {
  font: 400 11.5px var(--font-mono);
  color: var(--txt);
}

.as-sso-flags {
  display: flex;
  gap: 8px;
  margin-top: 14px;
}
</style>
