import axios from 'axios';

// Artist follows / release tracking state (MOO-80). Not persisted (no
// vuex-persistedstate path added): the badge and follow map re-derive from
// the API on every load, same rule as the other activity modules.
const state = {
  unseen: 0,
};

const getters = {
  stateUnseenReleases: state => state.unseen,
};

const actions = {
  async fetchFeedState({commit, rootGetters}) {
    if (!rootGetters.isAuthenticated) {
      return;
    }
    try {
      const {data} = await axios.get('follows/feed/state');
      commit('setUnseen', data.unseen_count);
    } catch (error) {
      // A stale badge is harmless.
    }
  },
  async markFeedSeen({commit}) {
    await axios.post('follows/feed/seen');
    commit('setUnseen', 0);
  },
  async toggleFollow({dispatch}, {artistId, settings}) {
    const {data} = await axios.post(`artists/${artistId}/follow`, settings || {});
    dispatch('fetchFeedState');
    return data;
  },
  async updateFollowSettings(_ctx, {artistId, settings}) {
    const {data} = await axios.patch(`artists/${artistId}/follow`, settings);
    return data;
  },
  async unfollowArtist({dispatch}, artistId) {
    const {data} = await axios.delete(`artists/${artistId}/follow`);
    dispatch('fetchFeedState');
    return data;
  },
};

const mutations = {
  setUnseen(state, count) {
    state.unseen = count;
  },
};

export default {
  state,
  getters,
  actions,
  mutations,
};
