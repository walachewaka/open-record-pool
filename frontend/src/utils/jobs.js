import axios from 'axios';

/**
 * Polls a background job (MOO-77) until it reaches a terminal state and
 * returns the final job object. Throws on failure/cancellation (with the
 * job's error message when there is one) and on timeout.
 *
 * Scan triggers return an already-terminal job in inline mode — check
 * `job.status === 'succeeded'` before polling to skip the round trips.
 */
export async function pollJob(jobId, {intervalMs = 1000, timeoutMs = 180000} = {}) {
  const startedAt = Date.now();
  for (;;) {
    const {data} = await axios.get(`admin/jobs/${jobId}`);
    if (data.status === 'succeeded') {
      return data;
    }
    if (data.status === 'failed' || data.status === 'cancelled') {
      throw new Error(data.error || `The background job ${data.status}.`);
    }
    if (Date.now() - startedAt > timeoutMs) {
      throw new Error('Timed out waiting for the background job.');
    }
    await new Promise(resolve => setTimeout(resolve, intervalMs));
  }
}
