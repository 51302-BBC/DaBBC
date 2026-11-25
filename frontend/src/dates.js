const zone = 'Asia/Taipei';

export function taipeiDate(date = new Date()) {
  return new Intl.DateTimeFormat('sv-SE', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(date);
}

export function monthDates(year, month) {
  const first = new Date(Date.UTC(year, month - 1, 1));
  const leading = (first.getUTCDay() + 6) % 7;
  const days = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const length = Math.ceil((leading + days) / 7) * 7;
  return Array.from({ length }, (_, i) => new Date(Date.UTC(year, month - 1, i + 1 - leading)).toISOString().slice(0, 10));
}

export function formatDateTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat('zh-TW', { timeZone: zone, month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(date);
}

export function timeValue(value) {
  return value ? new Date(value + ':00+08:00').toISOString() : null;
}

export function monthRange() {
  const today = taipeiDate();
  const [year, month] = today.split('-').map(Number);
  return { start: today.slice(0, 7) + '-01', end: new Date(Date.UTC(year, month, 0)).toISOString().slice(0, 10) };
}
