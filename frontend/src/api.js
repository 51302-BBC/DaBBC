export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

export function query(values) {
  const pairs = Object.entries(values).filter(([, value]) => value !== '' && value != null);
  return new URLSearchParams(pairs).toString();
}

export async function api(path, options = {}) {
  const { body, method = 'GET', signal, responseType } = options;
  const response = await fetch('/api' + path, {
    method, signal, credentials: 'same-origin',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 204) return null;
  if (response.ok && responseType === 'file') {
    const filename = response.headers.get('content-disposition')?.match(/filename="([^"]+)"/)?.[1];
    return { content: await response.blob(), filename };
  }
  const json = response.headers.get('content-type')?.includes('application/json');
  const result = json ? await response.json() : null;
  if (!response.ok) {
    let detail = result?.detail;
    if (Array.isArray(detail)) detail = detail.map(item => item.msg).join('、');
    throw new ApiError(response.status, typeof detail === 'string' ? detail : '操作未完成，請稍後再試。');
  }
  return result;
}
