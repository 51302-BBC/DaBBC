import { useEffect, useState } from 'react';
import { api } from './api.js';

export const roles = {
  owner: '老闆', manager: '主管', admin: '行政',
  employee: '員工',
};

export const taskStatuses = {
  pending: '待處理', in_progress: '進行中', completed: '已完成', canceled: '已取消',
};

export const kindLabels = {
  leave: '請假', outing: '外出', overtime: '加班',
  clock_correction: '補打卡', expense: '報帳', profile_change: '個人資料修改',
  cancellation: '撤銷申請', cancellation_request: '撤銷申請', cancel: '撤銷申請',
};

export const requestStatuses = {
  pending: '待審', approved: '已核准', returned: '已退回', withdrawn: '已撤回',
  canceled: '已撤銷', paid: '已付款', unassigned: '待指派',
};

export function useData(path, revision = 0) {
  const [result, setResult] = useState({ path: null, data: null, error: null, loading: Boolean(path) });
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    setResult(previous => ({
      path, data: previous.path === path ? previous.data : null, error: null, loading: true,
    }));
    api(path, { signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) setResult({ path, data, error: null, loading: false });
    }, error => {
      if (!controller.signal.aborted) setResult({ path, data: null, error, loading: false });
    });
    return () => controller.abort();
  }, [path, revision]);
  if (!path) return { data: null, error: null, loading: false };
  if (result.path !== path) return { data: null, error: null, loading: true };
  return result;
}

export function useAction(onSuccess) {
  const [state, setState] = useState({ busy: false, error: null, success: '' });
  async function run(work, success = '已儲存') {
    setState({ busy: true, error: null, success: '' });
    try {
      const result = await work();
      onSuccess?.(result);
      setState({ busy: false, error: null, success });
      return result;
    } catch (error) {
      setState({ busy: false, error, success: '' });
      return undefined;
    }
  }
  return { ...state, run };
}

export function Badge({ tone = 'neutral', children }) {
  return <span className={'badge badge-' + tone}>{children}</span>;
}

export function Section({ title, action, className = '', children }) {
  return <section className={'panel ' + className}>
    <header className="panel-heading"><h2>{title}</h2>{action}</header>
    {children}
  </section>;
}

export function PageTitle({ title, children }) {
  return <div className="page-title"><h1>{title}</h1>{children}</div>;
}

export function StateNotice({ state, empty = '目前沒有紀錄。' }) {
  if (state.error) return <p className="notice error" role="alert">{state.error.message}</p>;
  if (state.loading && state.data == null) return <p className="notice" role="status">載入中…</p>;
  if (Array.isArray(state.data) && !state.data.length) return <p className="notice">{empty}</p>;
  return null;
}

export function Feedback({ action }) {
  if (action.error) return <p className="notice error" role="alert">{action.error.message}</p>;
  if (action.success) return <p className="notice success" role="status">{action.success}</p>;
  return null;
}

export function Field({ label, children, full = false }) {
  return <label className={'field' + (full ? ' full' : '')}><span>{label}</span>{children}</label>;
}

export function Table({ columns, rows, name }) {
  return <div className="table-scroll"><table aria-label={name}>
    <thead><tr>{columns.map(column => <th key={column.label} scope="col">{column.label}</th>)}</tr></thead>
    <tbody>{rows.map((row, index) => <tr key={row.id ?? index}>
      {columns.map(column => <td key={column.label}>{column.render(row)}</td>)}
    </tr>)}</tbody>
  </table></div>;
}
