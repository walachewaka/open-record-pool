import axios from 'axios';

const state = {
  user: null,
};

// The permissions that open any part of the admin surface (MOO-72). A user
// holding at least one of these sees the Admin console entry points.
const ADMIN_SURFACE_PERMISSIONS = [
  'view_reports',
  'manage_users',
  'edit_metadata',
  'approve_submissions',
  'manage_roles',
  'site_settings',
];

const getters = {
  isAuthenticated: state => !!state.user,
  stateUser: state => state.user,
  // Effective permissions from /users/whoami; {} for sessions persisted
  // before MOO-72 (refreshed by the viewMe dispatch on app boot).
  userPermissions: state => (state.user && state.user.permissions) || {},
  hasAdminAccess: (state, getters) =>
    ADMIN_SURFACE_PERMISSIONS.some(key => getters.userPermissions[key]),
};

const actions = {
  async register({dispatch}, form) {
    await axios.post('register', form);
    let UserForm = new FormData();
    UserForm.append('username', form.username);
    UserForm.append('password', form.password);
    await dispatch('logIn', UserForm);
  },
  async logIn({dispatch}, user) {
    await axios.post('login', user);
    await dispatch('viewMe');
  },
  async viewMe({commit}) {
    let {data} = await axios.get('users/whoami');
    await commit('setUser', data);
  },
  // eslint-disable-next-line no-empty-pattern
  async deleteUser({}, id) {
    await axios.delete(`user/${id}`);
  },
  async logOut({commit}) {
    // Revoke the server-side session so the cookie can't be replayed (MOO-89).
    // Best-effort: an expired/invalid session still clears the local state.
    try {
      await axios.post('logout');
    } catch (e) {
      // ignore - proceed to clear local state regardless
    }
    let user = null;
    commit('logout', user);
  }
};

const mutations = {
  setUser(state, username) {
    state.user = username;
  },
  logout(state, user){
    state.user = user;
  },
};

export default {
  state,
  getters,
  actions,
  mutations
};
