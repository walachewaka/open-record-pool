// DJ bundle exports (MOO-86): submit, poll, and format the result.
import axios from 'axios';

export const DJ_TARGETS = [
  {
    value: 'serato',
    label: 'Serato',
    hint: 'Crate appears under the stick automatically — no import step.',
  },
  {
    value: 'traktor',
    label: 'Traktor',
    hint: 'Drag the .nml onto Traktor’s Playlists node to import.',
  },
  {
    value: 'rekordbox',
    label: 'rekordbox',
    hint: 'Preferences → Advanced → Database → rekordbox xml.',
  },
];

// FAT32 cannot hold a file over 4 GiB; warn before the DJ finds out at the club.
export const FAT32_LIMIT = 4 * 1024 * 1024 * 1024;

export function formatBytes(bytes) {
  if (!bytes) {
    return '0 MB';
  }
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const power = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / Math.pow(1024, power);
  return `${value.toFixed(power >= 2 ? 1 : 0)} ${units[power]}`;
}

export function submitExport(crateId, body) {
  return axios.post(`crates/${crateId}/export`, body).then((response) => response.data);
}

const TERMINAL = ['succeeded', 'failed', 'cancelled'];

// Poll an export job until it is terminal. onProgress gets the job on every
// tick, so the caller can bind a progress bar to it.
export async function pollExport(jobId, {intervalMs = 1500, timeoutMs = 600000, onProgress} = {}) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const {data} = await axios.get(`exports/${jobId}`);
    if (onProgress) {
      onProgress(data);
    }
    if (TERMINAL.includes(data.status)) {
      return data;
    }
    if (Date.now() > deadline) {
      throw new Error('Export timed out');
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

export function downloadUrl(job) {
  // baseURL may or may not carry a trailing slash; download_url always starts
  // with one. Cookie auth makes a plain <a download> work same-site.
  const base = (axios.defaults.baseURL || '').replace(/\/+$/, '');
  return `${base}${job.result.download_url}`;
}
