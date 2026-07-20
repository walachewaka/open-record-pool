import axios from 'axios';

import { toast } from '@/utils/toast';

const state = {
  // Last GET /downloads/quota payload; null until the first fetch. Refreshed
  // after every download so the sidebar meter and topbar pill stay live.
  quota: null,
  // song id -> latest favorite state, so hearts stay consistent across track
  // rows and the player without refetching lists. Session-only (see the
  // persistedstate paths in store/index.js): a fresh session reads the truth
  // from the API's is_favorite flags.
  favOverrides: {},
  // Songs the user downloaded from this browser; drives the "saved" state on
  // download icons.
  downloadedIds: [],
};

const getters = {
  stateQuota: state => state.quota,
  stateFavOverrides: state => state.favOverrides,
  stateDownloadedIds: state => state.downloadedIds,
};

const actions = {
  async fetchQuota({commit}) {
    try {
      const {data} = await axios.get('downloads/quota');
      commit('setQuota', data);
    } catch (error) {
      // The quota surfaces simply keep their last known value.
    }
  },
  async toggleFavorite({commit}, song) {
    const {data} = await axios.post(`songs/${song.id}/favorite`);
    commit('setFavOverride', data);
    toast(data.is_favorite ? 'Added to favorites' : 'Removed from favorites');
  },
  markDownloaded({commit}, songId) {
    commit('addDownloadedId', songId);
  },
};

const mutations = {
  setQuota(state, quota) {
    state.quota = quota;
  },
  setFavOverride(state, {song_id, is_favorite}) {
    state.favOverrides[song_id] = is_favorite;
  },
  addDownloadedId(state, songId) {
    if (!state.downloadedIds.includes(songId)) {
      state.downloadedIds.push(songId);
    }
  },
};

export default {
  state,
  getters,
  actions,
  mutations
};
