import axios from 'axios';

import { toast } from '@/utils/toast';

// Default colours for new crates, cycled by crate count (from the CRATE
// design prototype).
const CRATE_COLORS = ['#17b9ff', '#9d8bff', '#35d07a', '#ffb62e', '#ff5266'];

const state = {
  // The user's crate summaries (GET /crates); drives the sidebar list and
  // is refreshed after every crate mutation. Session-only, never persisted.
  crates: [],
  // The crate detail currently open in the crate view (GET /crates/{id}).
  activeCrate: null,
};

const getters = {
  stateCrates: state => state.crates,
  stateActiveCrate: state => state.activeCrate,
};

const actions = {
  async fetchCrates({commit}) {
    try {
      const {data} = await axios.get('crates');
      commit('setCrates', data);
    } catch (error) {
      // The sidebar simply keeps its last known list.
    }
  },
  async fetchCrate({commit}, crateId) {
    const {data} = await axios.get(`crates/${crateId}`);
    commit('setActiveCrate', data);
    commit('patchCrate', data);
    return data;
  },
  async createCrate({commit, state}) {
    const number = state.crates.length + 1;
    const {data} = await axios.post('crates', {
      name: `New Crate ${number}`,
      color: CRATE_COLORS[(number - 1) % CRATE_COLORS.length],
    });
    commit('patchCrate', data);
    toast('Crate created');
    return data;
  },
  async updateCrate({commit}, {crateId, changes}) {
    const {data} = await axios.patch(`crates/${crateId}`, changes);
    commit('patchCrate', data);
    return data;
  },
  async deleteCrate({commit}, crateId) {
    await axios.delete(`crates/${crateId}`);
    commit('removeCrate', crateId);
    toast('Crate deleted');
  },
  // Used by every drop target. Handles the duplicate-add 409 gracefully so
  // dropping a track twice never errors or duplicates a row.
  async addTrackToCrate({commit, state}, {crateId, songId}) {
    const crate = state.crates.find(c => c.id === crateId);
    const name = (crate && crate.name) || 'crate';
    try {
      const {data} = await axios.post(`crates/${crateId}/tracks`, {song_id: songId});
      commit('patchCrate', data);
      if (state.activeCrate && state.activeCrate.id === crateId) {
        commit('setActiveCrate', data);
      }
      toast(`Added to ${name}`);
    } catch (error) {
      const status = error.response && error.response.status;
      if (status === 409) {
        toast(`Already in ${name}`, 'warn');
      } else {
        toast('Could not add the track', 'warn');
      }
    }
  },
  async removeTrackFromCrate({dispatch}, {crateId, songId}) {
    await axios.delete(`crates/${crateId}/tracks/${songId}`);
    // Refetch so positions, count, and total duration stay honest.
    await dispatch('fetchCrate', crateId);
    toast('Removed from crate');
  },
  // One further keyset page of a crate's tracks (GET /crates/{id}/tracks).
  // Returns {items, next_cursor}; the view appends items itself.
  // eslint-disable-next-line no-empty-pattern
  async fetchCrateTracksPage({}, {crateId, cursor}) {
    const params = cursor ? {cursor} : {};
    const {data} = await axios.get(`crates/${crateId}/tracks`, {params});
    return data;
  },
  // Single-track drag-and-drop reorder: place songId after afterSongId (top
  // when null/undefined).
  // eslint-disable-next-line no-empty-pattern
  async moveCrateTrack({}, {crateId, songId, afterSongId}) {
    const {data} = await axios.patch(`crates/${crateId}/tracks/${songId}`, {
      after_song_id: afterSongId != null ? afterSongId : null,
    });
    return data;
  },
  async duplicateCrate({commit}, {crateId, name}) {
    const {data} = await axios.post(`crates/${crateId}/duplicate`, {name: name || null});
    commit('patchCrate', data);
    toast('Added to your crates');
    return data;
  },
  // Public crate discovery (view-local: results are not stored).
  // eslint-disable-next-line no-empty-pattern
  async fetchPublicCrates({}, {q, cursor} = {}) {
    const params = {};
    if (q) {
      params.q = q;
    }
    if (cursor) {
      params.cursor = cursor;
    }
    const {data} = await axios.get('crates/public', {params});
    return data;
  },
  async uploadCrateCover({commit}, {crateId, file}) {
    const form = new FormData();
    form.append('file', file);
    const {data} = await axios.post(`crates/${crateId}/cover`, form, {
      headers: {'Content-Type': 'multipart/form-data'},
    });
    commit('patchCrate', data);
    return data;
  },
  async deleteCrateCover({dispatch}, crateId) {
    await axios.delete(`crates/${crateId}/cover`);
    await dispatch('fetchCrate', crateId);
  },
  async rotateShareToken({commit}, crateId) {
    const {data} = await axios.post(`crates/${crateId}/share/rotate`);
    commit('patchCrate', data);
    return data;
  },
};

const mutations = {
  setCrates(state, crates) {
    state.crates = crates;
  },
  setActiveCrate(state, crate) {
    state.activeCrate = crate;
  },
  // Upserts one crate's summary fields into the sidebar list (the payload
  // may be a summary or a detail — details are a superset) and mirrors the
  // change onto the open detail.
  patchCrate(state, crate) {
    const summary = {
      id: crate.id,
      name: crate.name,
      color: crate.color,
      description: crate.description,
      cover_url: crate.cover_url,
      public: crate.public,
      share_token: crate.share_token,
      track_count: crate.track_count,
      created_at: crate.created_at,
    };
    const index = state.crates.findIndex(c => c.id === crate.id);
    if (index === -1) {
      state.crates.push(summary);
    } else {
      state.crates.splice(index, 1, summary);
    }
    if (state.activeCrate && state.activeCrate.id === crate.id && crate !== state.activeCrate) {
      state.activeCrate = Object.assign({}, state.activeCrate, crate);
    }
  },
  removeCrate(state, crateId) {
    state.crates = state.crates.filter(c => c.id !== crateId);
    if (state.activeCrate && state.activeCrate.id === crateId) {
      state.activeCrate = null;
    }
  },
};

export default {
  state,
  getters,
  actions,
  mutations
};
