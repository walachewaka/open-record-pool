import axios from 'axios';

// Song request state (MOO-81): the member's own request list/summary. The
// summary feeds the sidebar badge; deliberately not persisted (re-derives
// from the API, same rule as the admin module's counts).
const state = {
  items: [],
  nextCursor: null,
  summary: {open: 0, unseen_resolved: 0},
};

const getters = {
  stateRequests: state => state.items,
  stateRequestsNextCursor: state => state.nextCursor,
  stateRequestsSummary: state => state.summary,
};

const actions = {
  async fetchMyRequests({commit}, {status, append} = {}) {
    const {data} = await axios.get('requests/mine', {
      params: {status: status || undefined, limit: 50},
    });
    commit(append ? 'appendRequests' : 'setRequests', data.items);
    commit('setNextCursor', data.next_cursor);
    return data.items;
  },
  async loadMoreRequests({commit, state}, {status} = {}) {
    if (!state.nextCursor) {
      return [];
    }
    const {data} = await axios.get('requests/mine', {
      params: {status: status || undefined, limit: 50, cursor: state.nextCursor},
    });
    commit('appendRequests', data.items);
    commit('setNextCursor', data.next_cursor);
    return data.items;
  },
  async submitRequest({commit}, payload) {
    const {data} = await axios.post('requests', payload);
    commit('prependRequest', data);
    return data;
  },
  async cancelRequest({commit}, id) {
    const {data} = await axios.post(`requests/${id}/cancel`);
    commit('replaceRequest', data);
    return data;
  },
  async fetchRequestsSummary({commit, rootGetters}) {
    if (!rootGetters.isAuthenticated) {
      return;
    }
    try {
      const {data} = await axios.get('requests/mine/summary');
      commit('setSummary', data);
    } catch (error) {
      // A stale badge is harmless; the Requests view surfaces real errors.
    }
  },
  async markRequestsSeen({commit, state}) {
    await axios.post('requests/mine/seen');
    commit('setSummary', {open: state.summary.open, unseen_resolved: 0});
  },
};

const mutations = {
  setRequests(state, items) {
    state.items = items;
  },
  appendRequests(state, items) {
    state.items = [...state.items, ...items];
  },
  prependRequest(state, item) {
    state.items = [item, ...state.items];
  },
  replaceRequest(state, item) {
    state.items = state.items.map(existing => (existing.id === item.id ? item : existing));
  },
  setNextCursor(state, cursor) {
    state.nextCursor = cursor;
  },
  setSummary(state, summary) {
    state.summary = summary;
  },
};

export default {
  state,
  getters,
  actions,
  mutations,
};
