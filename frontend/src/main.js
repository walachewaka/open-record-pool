import 'bootstrap/dist/css/bootstrap.css';
import '@/assets/crate.css';
import axios from 'axios';
import { createApp } from 'vue';

import App from './App.vue';
import router from './router';
import store from './store';
import { toast } from '@/utils/toast';

const default_backend_url = 'http://localhost:5000';

axios.defaults.withCredentials = true;
axios.defaults.baseURL = process.env.VUE_APP_BACKEND_URL || default_backend_url; // the FastAPI backend

axios.interceptors.response.use(undefined, function (error) {
  const originalRequest = (error && error.config) || {};
  const status = error && error.response && error.response.status;
  const url = originalRequest.url || '';
  // A 401 on the login/register endpoints is a form error the component
  // shows inline, not an expired session, so don't force a logout/redirect.
  const isAuthRequest = url.indexOf('login') !== -1 || url.indexOf('register') !== -1;
  if (status === 401 && !isAuthRequest && !originalRequest._retry) {
    originalRequest._retry = true;
    store.dispatch('logOut');
    router.push('/login');
  }
  // Rate limiting (MOO-89): surface the backend's "try again in N seconds"
  // message so the user knows why the action was refused.
  if (status === 429) {
    const detail = (error.response && error.response.data && error.response.data.detail);
    toast(detail || 'Too many requests - slow down.', 'error');
  }
  // Always re-reject so the caller's catch block runs and can surface the error.
  return Promise.reject(error);
});

createApp(App).use(router).use(store).mount('#app');

