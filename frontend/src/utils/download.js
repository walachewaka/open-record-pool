import axios from 'axios';

import store from '@/store';
import { toast } from '@/utils/toast';

// Mirrors the backend's Content-Disposition filename (see
// backend/src/routes/songs.py::_download_filename).
function downloadFilename(song) {
  const name =
    song.artist && song.title
      ? `${song.artist} - ${song.title}.mp3`
      : `${song.title || song.artist || 'track'}.mp3`;
  return name.replace(/[:*?"<>|\r\n]/g, '_');
}

// Downloads a song through axios (instead of a plain <a href>) so the app
// can react to the outcome: mark the track saved, refresh the live quota
// surfaces, and confirm or warn via a toast. Returns true on success.
export async function downloadSong(song, format = 'mp3') {
  try {
    const response = await axios.get(`songs/${song.id}/download`, {
      responseType: 'blob',
      params: {format},
    });
    const url = URL.createObjectURL(response.data);
    const link = document.createElement('a');
    link.href = url;
    link.download = downloadFilename(song);
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    store.dispatch('markDownloaded', song.id);
    await store.dispatch('fetchQuota');
    const quota = store.getters.stateQuota;
    if (quota && !quota.unlimited && quota.remaining === 0) {
      toast(`Downloaded “${song.title || 'track'}” — monthly quota reached`, 'warn');
    } else {
      toast(`Downloaded “${song.title || 'track'}” · ${format.toUpperCase()}`);
    }
    return true;
  } catch (error) {
    const status = error.response && error.response.status;
    if (status === 429) {
      toast('Monthly download quota exhausted', 'warn');
    } else {
      toast('Download failed', 'warn');
    }
    return false;
  }
}
