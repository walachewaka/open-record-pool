import { reactive } from 'vue';

// Bottom-center confirmation toasts (~2.6s, accent success / amber warn).
// One toast at a time; a new one replaces whatever is showing. Kept outside
// vuex on purpose: the store is persisted and a toast must never survive a
// reload.
export const toastState = reactive({
  message: '',
  kind: 'ok',
  visible: false,
  // Re-keys the toast element so the slide-in animation replays when a new
  // toast arrives while the previous one is still on screen.
  serial: 0,
});

let timer = null;

export function toast(message, kind = 'ok') {
  clearTimeout(timer);
  toastState.message = message;
  toastState.kind = kind;
  toastState.visible = true;
  toastState.serial += 1;
  timer = setTimeout(() => {
    toastState.visible = false;
  }, 2600);
}
