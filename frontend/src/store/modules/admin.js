import axios from 'axios';

// Admin-console shared state (MOO-72): the moderation pending count feeds the
// sidebar badge and is refreshed by the views that change it (moderation
// approve/reject, content uploads). Deliberately not persisted.
const state = {
  pendingCount: 0,
  duplicatesPendingCount: 0,
  requestsPendingCount: 0,
};

const getters = {
  statePendingCount: state => state.pendingCount,
  stateDuplicatesPendingCount: state => state.duplicatesPendingCount,
  stateRequestsPendingCount: state => state.requestsPendingCount,
};

const actions = {
  async fetchPendingCount({commit, rootGetters}) {
    if (!rootGetters.userPermissions.approve_submissions) {
      commit('setPendingCount', 0);
      return;
    }
    try {
      const {data} = await axios.get('admin/moderation', {
        params: {page: 1, page_size: 1},
      });
      commit('setPendingCount', data.total);
    } catch (error) {
      // A stale badge is harmless; the moderation view surfaces real errors.
    }
  },
  // The duplicates review-queue badge (MOO-90). Keyset pagination carries no
  // total, so the badge counts the first page and shows "50+" beyond it.
  async fetchDuplicatesPendingCount({commit, rootGetters}) {
    if (!rootGetters.userPermissions.edit_metadata) {
      commit('setDuplicatesPendingCount', 0);
      return;
    }
    try {
      const {data} = await axios.get('admin/duplicates', {
        params: {status: 'pending', limit: 50},
      });
      commit(
        'setDuplicatesPendingCount',
        data.next_cursor ? '50+' : data.items.length
      );
    } catch (error) {
      // A stale badge is harmless; the duplicates view surfaces real errors.
    }
  },
  // The song-request queue badge (MOO-81). GET /admin/requests/stats returns
  // a real count (no keyset "50+" cap needed).
  async fetchRequestsPendingCount({commit, rootGetters}) {
    if (!rootGetters.userPermissions.approve_submissions) {
      commit('setRequestsPendingCount', 0);
      return;
    }
    try {
      const {data} = await axios.get('admin/requests/stats');
      commit('setRequestsPendingCount', data.pending);
    } catch (error) {
      // A stale badge is harmless; the requests view surfaces real errors.
    }
  },
};

const mutations = {
  setPendingCount(state, count) {
    state.pendingCount = count;
  },
  setDuplicatesPendingCount(state, count) {
    state.duplicatesPendingCount = count;
  },
  setRequestsPendingCount(state, count) {
    state.requestsPendingCount = count;
  },
};

export default {
  state,
  getters,
  actions,
  mutations,
};
