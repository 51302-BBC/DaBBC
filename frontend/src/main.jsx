import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ApiError, api } from './api.js';
import { Dashboard } from './dashboard.jsx';
import { ClientsPage, EmployeesPage, NotificationsPage, TasksPage } from './core-pages.jsx';
import { RequestsPage } from './request-pages.jsx';
import { AttendancePage, BalancesPage, CalendarPage, DelegatesPage, ReportsPage, SchedulePage } from './office-pages.jsx';
import { Feedback, Field, roles, useAction } from './ui.jsx';
import './styles.css';

const adminRoles = ['owner', 'admin'];
const routes = [
  ['dashboard', '工作台', Dashboard],
  ['tasks', '任務總覽', TasksPage],
  ['clients', '客戶公司', ClientsPage],
  ['attendance', '出勤紀錄', AttendancePage],
  ['calendar', '行事曆', CalendarPage],
  ['requests', '我的申請', RequestsPage],
  ['balances', '假別與時數', BalancesPage],
  ['reviews', '待審申請', RequestsPage, ['owner', 'manager', 'admin']],
  ['employees', '員工與組織', EmployeesPage, adminRoles],
  ['delegates', '代理審核', DelegatesPage, ['owner']],
  ['schedule', '班表設定', SchedulePage, adminRoles],
  ['reports', '報表與月結', ReportsPage, adminRoles],
  ['notifications', '通知中心', NotificationsPage],
];

function Brand() {
  return <a className="brand" href="#dashboard"><span aria-hidden="true" className="brand-mark">帳</span><span>會計事務所</span></a>;
}

function accountLink() {
  const query = new URLSearchParams(location.search);
  const token = query.get('token');
  const destination = query.get('action') || location.pathname.split('/').at(-1) || location.hash.slice(1);
  return token && ['activate', 'reset'].includes(destination) ? { token, destination } : null;
}

function SessionPage({ authenticate }) {
  const link = accountLink();
  const token = link?.token;
  const [mode, setMode] = useState(link?.destination ?? 'login');
  const [initialized, setInitialized] = useState('');
  const action = useAction(result => {
    if (mode === 'login') authenticate(result?.user ?? result);
    if (mode === 'activate' || mode === 'reset') {
      setInitialized(mode === 'activate' ? '帳號已啟用，請登入。' : '密碼已更新，請登入。');
      history.replaceState(null, '', '/');
      setMode('login');
    }
  });
  const titles = { login: '登入工作台', forgot: '重設密碼', activate: '啟用員工帳號', reset: '設定新密碼' };
  const buttons = { login: '登入', forgot: '寄送重設連結', activate: '啟用帳號', reset: '更新密碼' };
  return <main className="auth-shell">
    <section className="auth-intro">
      <Brand />
      <div><h1>會計事務所<br />內部工作台</h1><p>在同一處管理任務、出勤與申請。</p></div>
    </section>
    <section className="auth-form">
      <h2>{titles[mode]}</h2>
      {initialized && <p className="notice success" role="status">{initialized}</p>}
      <form className="auth-inputs" key={mode} onSubmit={event => {
        event.preventDefault();
        const fields = new FormData(event.currentTarget);
        const body = mode === 'forgot' ? { email: fields.get('email') } :
          mode === 'login' ? { email: fields.get('email'), password: fields.get('password') } :
          { token, password: fields.get('password') };
        action.run(() => api('/auth/' + mode, { method: 'POST', body }), mode === 'forgot' ? '若帳號已開通，請查收密碼重設信。' : '');
      }}>
        {['login', 'forgot'].includes(mode) && <Field label="電子郵件"><input name="email" type="email" autoComplete="username" required /></Field>}
        {mode !== 'forgot' && <Field label={mode === 'login' ? '密碼' : '新密碼'}>
          <input name="password" type="password" minLength={mode === 'login' ? undefined : 12} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required />
        </Field>}
        <button className="button primary" type="submit" disabled={action.busy}>{action.busy ? '處理中…' : buttons[mode]}</button>
      </form>
      <Feedback action={action} />
      {(mode === 'login' || mode === 'forgot') && <button className="link-button secondary-link" onClick={() => setMode(mode === 'login' ? 'forgot' : 'login')}>{mode === 'login' ? '忘記密碼' : '返回登入'}</button>}
    </section>
  </main>;
}

function ProfilePage({ user }) {
  const fields = [
    ['姓名', user.name], ['角色', user.roles.map(role => roles[role] ?? role).join('、')],
    ['電子郵件', user.email], ['聯絡電話', user.phone],
    ['地址', user.address], ['緊急聯絡人', user.emergency_contact],
  ];
  return <>
    <h1>個人資料</h1>
    <section className="panel form-content" aria-label="帳戶資料">
      <dl className="detail-list">{fields.map(([label, value]) =>
        <div key={label}><dt>{label}</dt><dd>{value || '未填寫'}</dd></div>
      )}</dl>
    </section>
  </>;
}

function Shell({ user, logout }) {
  const [route, setRoute] = useState(() => location.hash.slice(1) || 'dashboard');
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    function navigate() {
      setRoute(location.hash.slice(1) || 'dashboard');
      window.scrollTo(0, 0);
    }
    window.addEventListener('hashchange', navigate);
    return () => window.removeEventListener('hashchange', navigate);
  }, []);
  const available = routes.filter(([, , , access]) => !access || access.some(role => user.roles.includes(role)));
  const active = available.find(([key]) => key === route);
  const Page = route === 'profile' ? ProfilePage : active?.[2];
  const action = useAction(logout);
  return <>
    <a className="skip" href="#main-view" onClick={event => {
      event.preventDefault();
      document.querySelector('#main-view').focus();
    }}>跳到主要內容</a>
    <header className="site-header"><div className="header-inner">
      <Brand />
      <div className="profile">
        <a className="profile-link" href="#profile" aria-label={user.name + '的個人資料'} aria-current={route === 'profile' ? 'page' : undefined}>
          <span className="avatar" aria-hidden="true">{user.name?.[0] || '員'}</span>
          <span><strong>{user.name}</strong><small>{user.roles.map(role => roles[role] ?? role).join('、')}</small></span>
        </a>
        <button className="button secondary compact" disabled={action.busy} onClick={() => action.run(() => api('/auth/logout', { method: 'POST' }), '')}>登出</button>
      </div>
    </div></header>
    <div className="app-grid">
      <nav className="side-nav" aria-label="主要導覽">
        {available.map(([key, label]) => <a key={key} href={'#' + key} aria-current={key === route ? 'page' : undefined}>{label}</a>)}
      </nav>
      <main className="app-main" id="main-view" tabIndex={-1}>
        <Feedback action={action} />
        {Page ? <Page key={route} user={user} revision={revision} reviewing={route === 'reviews'} update={() => setRevision(value => value + 1)} /> :
          <section className="panel form-content"><h1>找不到頁面</h1><p>請從導覽選擇可使用的功能。</p><a href="#dashboard">返回工作台</a></section>}
      </main>
    </div>
  </>;
}

function App() {
  const [state, setState] = useState({ loading: true, user: null, error: null });
  async function refresh() {
    setState({ loading: true, user: null, error: null });
    try {
      const user = await api('/auth/me');
      setState({ loading: false, user: user.user ?? user, error: null });
    } catch (error) {
      setState({ loading: false, user: null, error: error instanceof ApiError && error.status === 401 ? null : error });
    }
  }
  useEffect(() => {
    if (accountLink()) setState({ loading: false, user: null, error: null });
    else refresh();
  }, []);
  if (state.loading) return <main className="session-status" role="status">工作台載入中…</main>;
  if (state.error) return <main className="session-status"><p role="alert">{state.error.message}</p><button className="button primary" onClick={refresh}>重新連線</button></main>;
  if (!state.user) return <SessionPage authenticate={refresh} />;
  return <Shell user={state.user} logout={() => {
    history.replaceState(null, '', '/');
    setState({ loading: false, user: null, error: null });
  }} />;
}

createRoot(document.getElementById('root')).render(<App />);
