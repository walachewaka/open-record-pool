// Small display formatters shared by the admin console views (MOO-72).

export function fmtNum(value) {
  return Number(value || 0).toLocaleString('en-US');
}

export function fmtBytes(bytes) {
  const value = Number(bytes || 0);
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let unit = 0;
  let scaled = value;
  while (scaled >= 1024 && unit < units.length - 1) {
    scaled /= 1024;
    unit += 1;
  }
  return `${unit === 0 ? scaled : scaled.toFixed(1)} ${units[unit]}`;
}

export function initialsFor(text) {
  const source = (text || '?').trim();
  const words = source.split(/\s+/);
  const letters = words.length > 1 ? words[0][0] + words[1][0] : source.slice(0, 2);
  return letters.toUpperCase();
}

export function tintForId(id) {
  return `var(--tint-${(Number(id) % 10) + 1})`;
}

export function relativeTime(value) {
  if (!value) {
    return '—';
  }
  // The backend serializes naive UTC datetimes; force the Z suffix so the
  // browser doesn't parse them as local time.
  const iso = /Z|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`;
  const seconds = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) {
    return 'just now';
  }
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m ago`;
  }
  const hours = Math.round(minutes / 60);
  if (hours < 24) {
    return `${hours}h ago`;
  }
  const days = Math.round(hours / 24);
  if (days < 60) {
    return `${days}d ago`;
  }
  return `${Math.round(days / 30)}mo ago`;
}

// "member for" style durations: 12d, 4mo, 2y.
export function durationSince(value) {
  if (!value) {
    return '—';
  }
  const iso = /Z|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`;
  const days = Math.max(
    0,
    Math.floor((Date.now() - new Date(iso).getTime()) / 86400000)
  );
  if (days < 60) {
    return `${days}d`;
  }
  const months = Math.floor(days / 30);
  if (months < 24) {
    return `${months}mo`;
  }
  return `${Math.floor(days / 365)}y`;
}

// Status pill colours shared by users (account status) and content
// (moderation status). Mirrors the design prototype's statusMeta().
const STATUS_META = {
  active: ['var(--ok)', 'rgba(53, 208, 122, .13)'],
  published: ['var(--ok)', 'rgba(53, 208, 122, .13)'],
  suspended: ['var(--danger)', 'rgba(255, 82, 102, .13)'],
  rejected: ['var(--danger)', 'rgba(255, 82, 102, .13)'],
  pending: ['var(--warn)', 'rgba(255, 182, 46, .13)'],
  invited: ['var(--muted)', 'rgba(255, 255, 255, .07)'],
  draft: ['var(--muted)', 'rgba(255, 255, 255, .07)'],
};

export function statusColor(status) {
  return (STATUS_META[status] || STATUS_META.draft)[0];
}

export function statusBg(status) {
  return (STATUS_META[status] || STATUS_META.draft)[1];
}

export function capitalize(value) {
  const text = String(value || '');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

const ROLE_COLORS = {
  owner: 'var(--acc)',
  admin: 'var(--key)',
  curator: 'var(--ok)',
  member: 'var(--muted)',
};

export function roleColor(role) {
  return ROLE_COLORS[role] || ROLE_COLORS.member;
}
