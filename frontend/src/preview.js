import { taipeiDate } from './dates.js';

const today = taipeiDate();
const month = today.slice(0, 7);
const stamp = today + 'T09:00:00+08:00';
const employees = [
  ['林以安', 'owner'], ['方予晴', 'manager'], ['江立禾', 'employee'], ['周可欣', 'admin'],
].map(([name, role], index) => ({
  id: index + 1, name, roles: [role], email: role + '@example.test', active: true,
  supervisor_id: [null, 1, 2, 1][index],
}));
export const demoUser = employees[0];
const clients = ['青禾設計', '晴川商行', '海嶼製造'].map((name, i) => ({
  id: i + 1, name, active: true, assignee_ids: [1, 3], assignee_names: [demoUser.name, employees[2].name],
}));
const tasks = [
  ['核對當月進項憑證', 'pending', '比對發票與進貨明細，列出缺件清單。'],
  ['編製月結試算表', 'in_progress', '已完成銀行對帳，接續核對應收帳款。'],
  ['覆核營業稅申報資料', 'completed', '申報底稿與附件已完成覆核及歸檔。'],
].map(([title, status, description], i) => ({
  id: i + 1, title, status, description, due_on: today, client_id: clients[i].id,
  client_name: clients[i].name, assignee_id: 1, assignee_name: demoUser.name, creator_id: 1,
}));
const requests = ['leave', 'outing', 'expense'].map((kind, i) => ({
  id: i + 1, kind, employee_id: [3, 2, 1][i], employee_name: employees[[2, 1, 0][i]].name,
  status: i === 2 ? 'approved' : 'pending', created_at: stamp, reviewer_id: 1,
  details: { reason: ['家庭事務', '至客戶公司核對帳冊', '客戶訪視交通費'][i] },
}));
const attendance = { date: today, clock_in: stamp, status: 'present', employee_id: 1 };
const leaveType = { id: 1, name: '特別休假', requires_balance: true };
const events = [
  { date: today, category: 'meeting', title: '月結進度會議' },
  { date: month + '-12', category: 'personnel', title: '江立禾 · 外出訪視' },
  { date: month + '-20', category: 'holiday', title: '事務所休業日（示例）' },
];
const data = {
  '/tasks': tasks, '/employees': employees, '/clients': clients,
  '/notifications': [{ id: 1, message: '月結試算表已指派給你。', created_at: stamp }],
  '/schedule': { weekdays: [0, 1, 2, 3, 4], start_time: '09:00', end_time: '18:00', break_minutes: 60 },
  '/delegates': [], '/leave-types': [leaveType],
  '/leave-balances': [{ ...leaveType, total_minutes: 3360, used_minutes: 480, reserved_minutes: 0, remaining_minutes: 2880 }],
};

export function previewData({ pathname, searchParams }) {
  const scope = searchParams.get('scope');
  const start = searchParams.get('start') || today;
  const end = searchParams.get('end') || today;
  const rows = today >= start && today <= end ? [attendance] : [];
  switch (pathname) {
    case '/calendar': return events.filter(event => event.date.startsWith(searchParams.get('month')));
    case '/requests':
      if (scope === 'mine') return requests.filter(item => item.employee_id === demoUser.id);
      if (scope === 'review') return requests.filter(item => item.status === 'pending');
      return scope === 'unassigned' ? [] : requests;
    case '/attendance': return rows;
    case '/reports': return { start, end, rows: rows.filter(row => !searchParams.get('employee_id') || row.employee_id === Number(searchParams.get('employee_id'))), can_finalize: false };
    case '/overtime-targets': return { employee_id: Number(searchParams.get('employee_id')) || 1, minutes: 120 };
    default: return data[pathname] ?? [];
  }
}
