import axios from 'axios';

export const WAVE_BARS = 56;

// Real analyzed peaks (MOO-87): songs the analyzer has processed carry
// waveform_ready=true and serve 1000 normalized peaks from
// GET /songs/{id}/waveform. Module-level cache so every component sharing a
// song issues at most one request; the endpoint is content-addressed
// (ETag + Cache-Control) so even cache misses after a reload are cheap.
const peaksCache = new Map(); // songId -> Promise<Array|null>

export function fetchPeaks(song) {
  // The waveform_ready gate means list views only ever request analyzed
  // tracks -- no 404 storms on a fresh library.
  if (!song || !song.waveform_ready) {
    return Promise.resolve(null);
  }
  if (!peaksCache.has(song.id)) {
    peaksCache.set(
      song.id,
      axios
        .get(`songs/${song.id}/waveform`)
        .then((response) => response.data.peaks || null)
        .catch(() => null)
    );
  }
  return peaksCache.get(song.id);
}

export function peaksToBars(peaks, bars = WAVE_BARS) {
  // Bucket-max resample 1000 -> bars; 8% floor keeps quiet tracks visible.
  const out = [];
  for (let i = 0; i < bars; i += 1) {
    const start = Math.floor((i / bars) * peaks.length);
    const end = Math.max(start + 1, Math.floor(((i + 1) / bars) * peaks.length));
    let max = 0;
    for (let j = start; j < end; j += 1) {
      max = Math.max(max, peaks[j]);
    }
    out.push(`${Math.round(Math.max(0.08, max) * 100)}%`);
  }
  return out;
}

// Deterministic PRNG (mulberry32) so a song keeps the same pseudo-random
// waveform between renders and across components (track rows, player bar).
// Used as the universal fallback until the analyzer has produced real peaks.
function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function waveBars(songId, bars = WAVE_BARS) {
  const rng = mulberry32(songId * 2654435761);
  const heights = [];
  let level = 0.55;
  for (let i = 0; i < bars; i += 1) {
    level += (rng() - 0.5) * 0.55;
    level = Math.max(0.12, Math.min(1, level));
    const envelope = 0.55 + 0.45 * Math.sin((i / bars) * Math.PI);
    heights.push(`${Math.round((0.16 + level * 0.82 * envelope) * 100)}%`);
  }
  return heights;
}
