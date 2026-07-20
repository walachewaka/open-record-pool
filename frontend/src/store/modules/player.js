const state = {
  song: null,
  playing: false,
  // The list the player's prev/next walk: the songs of the last list view
  // fetch (Browse keeps it in sync). Auto-advance at track end uses it too.
  queue: [],
  // Bumped by togglePlayback(); the PlayerBar owns the <audio> element and
  // pauses/resumes it in response (track rows can't reach the element).
  toggleRequests: 0,
  // Playback progress (0–1) mirrored from the PlayerBar's <audio> element so
  // other views (the release waveform) can render the played portion.
  progress: 0,
  // Seek requests from outside the PlayerBar (release waveform clicks). The
  // serial makes repeated seeks to the same fraction re-fire the watcher.
  seek: {fraction: 0, serial: 0},
};

const getters = {
  stateSong: state => state.song,
  statePlaying: state => state.playing,
  stateQueue: state => state.queue,
  stateToggleRequests: state => state.toggleRequests,
  stateProgress: state => state.progress,
  stateSeek: state => state.seek,
};

const actions = {
  playSong({commit}, song) {
    commit('setSong', song);
  },
  setQueue({commit}, songs) {
    commit('setQueue', songs);
  },
  togglePlayback({commit}) {
    commit('bumpToggleRequests');
  },
  setPlaying({commit}, playing) {
    commit('setPlaying', playing);
  },
  setProgress({commit}, progress) {
    commit('setProgress', progress);
  },
  requestSeek({commit}, fraction) {
    commit('requestSeek', fraction);
  },
};

const mutations = {
  setSong(state, song) {
    state.song = song;
  },
  setQueue(state, songs) {
    state.queue = songs;
  },
  setPlaying(state, playing) {
    state.playing = playing;
  },
  bumpToggleRequests(state) {
    state.toggleRequests += 1;
  },
  setProgress(state, progress) {
    state.progress = progress;
  },
  requestSeek(state, fraction) {
    state.seek = {fraction, serial: state.seek.serial + 1};
  },
};

export default {
  state,
  getters,
  actions,
  mutations
};
