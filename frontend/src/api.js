import { previewData } from './preview.js';

export function query(values) {
  const pairs = Object.entries(values).filter(([, value]) => value !== '' && value != null);
  return new URLSearchParams(pairs).toString();
}

export async function api(path, { method = 'GET' } = {}) {
  if (method !== 'GET') throw new Error('展示版僅供瀏覽，無法送出或儲存資料。');
  return previewData(new URL(path, 'https://preview.invalid'));
}
