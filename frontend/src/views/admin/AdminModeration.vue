<template>
  <section class="am-wrap">
    <div class="am-header">
      <div class="am-title">
        {{ tab === 'queue' ? 'Submission queue' : 'Tag suggestions' }}
      </div>
      <span
        v-if="tab === 'queue' && items.length"
        class="am-count"
      >{{ items.length }} pending</span>
      <span
        v-if="tab === 'tags' && proposals.length"
        class="am-count"
      >{{ proposals.length }} pending</span>
      <SegmentedControl
        v-model="tab"
        class="am-tabs"
        :options="tabs"
      />
    </div>

    <p
      v-if="errorMessage"
      class="am-error"
    >
      {{ errorMessage }}
    </p>

    <!-- Tag suggestions (member-proposed ID3 edits) -->
    <template v-if="tab === 'tags'">
      <div
        v-if="!proposals.length && !errorMessage"
        class="am-empty"
      >
        <div class="am-empty-title">
          Nothing to review
        </div>
        <div class="am-empty-sub">
          Member-suggested tag edits land here.
        </div>
      </div>
      <div class="am-list">
        <div
          v-for="proposal in proposals"
          :key="proposal.id"
          class="am-card"
        >
          <div class="am-meta">
            <div class="am-meta-title">
              <span class="am-track-title">{{ proposal.song_title || 'Untitled' }}</span>
              <span class="am-pending-badge">PENDING</span>
            </div>
            <div class="am-artist">
              {{ proposal.song_artist || 'Unknown artist' }} ·
              by {{ proposal.proposer_username || '—' }} ·
              {{ relativeTime(proposal.created_at) }}
            </div>
            <div class="am-chips">
              <span
                v-for="field in Object.keys(proposal.changes || {})"
                :key="field"
                class="am-chip"
              >
                {{ field }}: {{ chipFor(proposal, field) }}
              </span>
            </div>
            <div
              v-if="proposal.note"
              class="am-note"
            >
              “{{ proposal.note }}”
            </div>
          </div>
          <div class="am-actions">
            <button
              type="button"
              class="am-reject"
              title="Reject"
              @click="reviewProposal(proposal, 'reject')"
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.2"
                stroke-linecap="round"
              >
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
            <button
              type="button"
              class="am-approve"
              @click="reviewProposal(proposal, 'approve')"
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.4"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <path d="M5 12l4 4L19 6" />
              </svg>
              Approve
            </button>
          </div>
        </div>
      </div>
    </template>

    <template v-else>
      <div
        v-if="!loading && !items.length && !errorMessage"
        class="am-empty"
      >
        <div class="am-empty-icon">
          <svg
            width="26"
            height="26"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M5 12l4 4L19 6" />
          </svg>
        </div>
        <div class="am-empty-title">
          Queue is clear
        </div>
        <div class="am-empty-sub">
          Every submission has been reviewed. New uploads that require approval will show up here.
        </div>
      </div>

      <div class="am-list">
        <div
          v-for="track in items"
          :key="track.id"
          class="am-card"
        >
          <div
            class="am-cover"
            :style="{background: tintForId(track.id)}"
          >
            {{ initialsFor(track.title || track.artist) }}
          </div>
          <div class="am-meta">
            <div class="am-meta-title">
              <span class="am-track-title">{{ track.title || 'Untitled' }}</span>
              <span class="am-pending-badge">PENDING</span>
            </div>
            <div class="am-artist">
              {{ track.artist || 'Unknown artist' }} · {{ track.album || '—' }}
            </div>
            <div class="am-chips">
              <span class="am-chip am-chip-key">{{ track.camelot_key || track.musical_key || '—' }}</span>
              <span class="am-chip">{{ track.bpm == null ? '—' : Math.round(track.bpm) }} BPM</span>
              <span class="am-chip am-chip-genre">{{ track.genre || '—' }}</span>
            </div>
          </div>
          <div class="am-uploader">
            <div class="am-uploader-name">
              by {{ track.uploaded_by_username || '—' }}
            </div>
            <div class="am-uploader-when">
              {{ relativeTime(track.created_at) }}
            </div>
          </div>
          <div class="am-actions">
            <button
              type="button"
              class="am-reject"
              title="Reject"
              @click="reject(track)"
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.2"
                stroke-linecap="round"
              >
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
            <button
              type="button"
              class="am-approve"
              @click="approve(track)"
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.4"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <path d="M5 12l4 4L19 6" />
              </svg>
              Approve
            </button>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>

<script>
import axios from 'axios';

import SegmentedControl from '@/components/admin/SegmentedControl.vue';
import { toast } from '@/utils/toast';
import { initialsFor, relativeTime, tintForId } from '@/utils/format';

export default {
  name: 'AdminModeration',
  components: {
    SegmentedControl,
  },
  data() {
    return {
      items: [],
      proposals: [],
      tab: 'queue',
      loading: true,
      errorMessage: '',
    };
  },
  computed: {
    tabs() {
      return [
        {value: 'queue', label: 'Submissions'},
        {value: 'tags', label: 'Tag suggestions'},
      ];
    },
  },
  watch: {
    tab(value) {
      if (value === 'tags') {
        this.fetchProposals();
      }
    },
  },
  created() {
    return this.fetchQueue();
  },
  methods: {
    initialsFor,
    relativeTime,
    tintForId,
    // Proposals only carry the *new* value; for title/artist the list row
    // already knows the current one, so those get a real old -> new chip.
    chipFor(proposal, field) {
      const current = field === 'title'
        ? proposal.song_title
        : (field === 'artist' ? proposal.song_artist : '');
      const next = proposal.changes[field];
      return current ? `${current} → ${next}` : next;
    },
    async fetchProposals() {
      this.errorMessage = '';
      try {
        const {data} = await axios.get('admin/tag-proposals', {
          params: {status: 'pending', limit: 100},
        });
        this.proposals = data.items;
      } catch (error) {
        this.errorMessage = 'Could not load the tag suggestions.';
      }
    },
    async reviewProposal(proposal, action) {
      try {
        await axios.post(`admin/tag-proposals/${proposal.id}/${action}`);
        this.proposals = this.proposals.filter(item => item.id !== proposal.id);
        toast(
          action === 'approve' ? 'Tag edit applied' : 'Suggestion rejected',
          action === 'approve' ? 'ok' : 'warn'
        );
      } catch (error) {
        toast(`Could not ${action} the suggestion.`, 'warn');
      }
    },
    async fetchQueue() {
      this.loading = true;
      this.errorMessage = '';
      try {
        const {data} = await axios.get('admin/moderation', {
          params: {page: 1, page_size: 300},
        });
        this.items = data.items;
      } catch (error) {
        const detail = error.response && error.response.data && error.response.data.detail;
        this.errorMessage =
          (typeof detail === 'string' && detail) || 'Could not load the queue.';
      } finally {
        this.loading = false;
      }
    },
    remove(track) {
      this.items = this.items.filter(item => item.id !== track.id);
      this.$store.dispatch('fetchPendingCount');
    },
    async approve(track) {
      try {
        await axios.post(`admin/content/${track.id}/approve`);
        this.remove(track);
        toast('Track approved & published');
      } catch (error) {
        toast('Could not approve the submission.', 'warn');
      }
    },
    async reject(track) {
      try {
        await axios.post(`admin/content/${track.id}/reject`);
        this.remove(track);
        toast('Submission rejected', 'warn');
      } catch (error) {
        toast('Could not reject the submission.', 'warn');
      }
    },
  },
};
</script>

<style scoped>
.am-wrap {
  max-width: 940px;
}

.am-header {
  display: flex;
  align-items: center;
  gap: 11px;
  margin-bottom: 18px;
}

.am-title {
  font: 600 15px var(--font-disp);
}

.am-tabs {
  margin-left: auto;
}

.am-note {
  margin-top: 9px;
  font: 400 12.5px var(--font-ui);
  color: var(--dim);
}

.am-count {
  padding: 4px 10px;
  border-radius: var(--r-pill);
  background: rgba(255, 182, 46, .14);
  color: var(--warn);
  font: 600 11px var(--font-mono);
}

.am-error {
  color: var(--danger);
  font: 400 13px var(--font-ui);
}

.am-empty {
  padding: 70px 24px;
  text-align: center;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--panel);
}

.am-empty-icon {
  width: 52px;
  height: 52px;
  border-radius: 14px;
  background: rgba(53, 208, 122, .12);
  color: var(--ok);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 16px;
}

.am-empty-title {
  font: 600 16px var(--font-disp);
  color: var(--txt-2);
  margin-bottom: 6px;
}

.am-empty-sub {
  color: var(--dim-2);
  font: 400 13.5px var(--font-ui);
}

.am-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.am-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px;
  border: 1px solid rgba(255, 255, 255, .07);
  border-radius: 14px;
  background: var(--panel);
}

.am-cover {
  width: 64px;
  height: 64px;
  border-radius: 11px;
  box-shadow: var(--shadow-cover);
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  font: 600 15px var(--font-mono);
  color: rgba(255, 255, 255, .68);
}

.am-meta {
  flex: 1;
  min-width: 0;
}

.am-meta-title {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 5px;
}

.am-track-title {
  font: 600 15px var(--font-ui);
  color: var(--txt);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.am-pending-badge {
  flex: none;
  padding: 2px 8px;
  border-radius: 6px;
  background: rgba(255, 182, 46, .13);
  color: var(--warn);
  font: 600 10px var(--font-mono);
}

.am-artist {
  font: 400 12.5px var(--font-ui);
  color: var(--muted);
  margin-bottom: 9px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.am-chips {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
}

.am-chip {
  padding: 3px 9px;
  border-radius: 6px;
  background: rgba(255, 255, 255, .05);
  color: var(--txt-2);
  font: 600 11px var(--font-mono);
}

.am-chip-key {
  background: rgba(157, 139, 255, .12);
  color: var(--key-bright);
}

.am-chip-genre {
  font: 500 11px var(--font-ui);
}

.am-uploader {
  text-align: right;
  flex: none;
  margin-right: 4px;
}

.am-uploader-name {
  font: 500 11px var(--font-ui);
  color: var(--muted);
}

.am-uploader-when {
  font: 400 11px var(--font-mono);
  color: var(--dim-2);
  margin-top: 2px;
}

.am-actions {
  display: flex;
  gap: 8px;
  flex: none;
}

.am-reject {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  border: 1px solid rgba(255, 82, 102, .3);
  background: rgba(255, 82, 102, .08);
  color: var(--danger);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background .15s ease;
}

.am-reject:hover {
  background: rgba(255, 82, 102, .18);
}

.am-approve {
  height: 40px;
  padding: 0 16px;
  border-radius: 10px;
  border: none;
  background: var(--ok);
  color: #032414;
  font: 600 13px var(--font-ui);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 7px;
  transition: filter .15s ease;
}

.am-approve:hover {
  filter: brightness(1.08);
}
</style>
