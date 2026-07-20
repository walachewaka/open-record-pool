import createPersistedState from "vuex-persistedstate";
import { createStore } from 'vuex';

import admin from './modules/admin';
import crates from './modules/crates';
import follows from './modules/follows';
import library from './modules/library';
import notes from './modules/notes';
import player from './modules/player';
import songRequests from './modules/song_requests';
import users from './modules/users';


export default createStore({
  modules: {
    admin,
    crates,
    follows,
    library,
    notes,
    player,
    songRequests,
    users,
  },
  plugins: [createPersistedState({
    // Everything but the library and crates modules persists as before. Of
    // the library state only downloadedIds survives a reload: quota is
    // refetched on login and favOverrides must not shadow fresher
    // is_favorite flags from the API. Crates are always refetched.
    paths: ['notes', 'player', 'users', 'library.downloadedIds'],
  })]
});
