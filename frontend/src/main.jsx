import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { demoUser } from './preview.js';
import { Dashboard } from './dashboard.jsx';
import { ClientsPage, EmployeesPage, NotificationsPage, TasksPage } from './core-pages.jsx';
import { RequestsPage } from './request-pages.jsx';
import { AttendancePage, BalancesPage, CalendarPage, DelegatesPage, ReportsPage, SchedulePage } from './office-pages.jsx';
import { roles } from './ui.jsx';
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

function Shell({ user }) {
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

      </div>
    </div></header>
    <div className="app-grid">
      <nav className="side-nav" aria-label="主要導覽">
        {available.map(([key, label]) => <a key={key} href={'#' + key} aria-current={key === route ? 'page' : undefined}>{label}</a>)}
      </nav>
      <main className="app-main" id="main-view" tabIndex={-1}>
        <small className="preview-note">版面展示 · 虛構資料 · 僅供瀏覽</small>
        {Page ? <Page key={route} user={user} revision={revision} reviewing={route === 'reviews'} update={() => setRevision(value => value + 1)} /> :
          <section className="panel form-content"><h1>找不到頁面</h1><p>請從導覽選擇可使用的功能。</p><a href="#dashboard">返回工作台</a></section>}
      </main>
    </div>
  </>;
}

createRoot(document.getElementById('root')).render(<Shell user={demoUser} />);
