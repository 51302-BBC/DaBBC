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
export function previewUser(role) {
  return employees.find(person => person.roles.includes(role)) ?? employees[0];
}

const clients = ['青禾設計', '晴川商行', '海嶼製造'].map((name, i) => ({
  id: i + 1, name, active: true, assignee_ids: [[1, 3], [1, 2], [1, 4]][i], assignee_names: [[1, 3], [1, 2], [1, 4]][i].map(id => employees[id - 1].name),
}));
const tasks = [
  ['核對當月進項憑證', 'pending', '比對發票與進貨明細，列出缺件清單。', 1, 1, 1],
  ['編製月結試算表', 'in_progress', '接續核對應收帳款。', 2, 1, 1],
  ['覆核營業稅申報資料', 'completed', '申報底稿與附件已完成覆核。', 3, 1, 1],
  ['覆核客戶對帳差異', 'in_progress', '整理差異並回覆承辦同仁。', 2, 2, 1],
  ['登錄本期進貨發票', 'pending', '依發票日期逐筆登錄。', 1, 3, 2],
  ['彙整缺件清單', 'completed', '已將缺件通知寄給客戶。', 1, 3, 4],
  ['分派本週收件', 'pending', '核對簽收紀錄並指派承辦人。', 3, 4, 4],
].map(([title, status, description, client_id, assignee_id, created_by], i) => ({
  id: i + 1, title, status, description, due_on: today, client_id, assignee_id, created_by,
  client_name: clients[client_id - 1].name, assignee_name: employees[assignee_id - 1].name,
}));
const requests = [
  ['leave', 3, 2, 'pending', '家庭事務'], ['outing', 2, 1, 'pending', '拜訪客戶'],
  ['expense', 1, 4, 'pending', '訪視交通費'], ['overtime', 4, 1, 'approved', '月結收件'],
].map(([kind, employee_id, reviewer_id, status, reason], i) => ({
  id: i + 1, kind, employee_id, employee_name: employees[employee_id - 1].name,
  status, created_at: stamp, reviewer_id, details: { reason },
}));
const attendance = employees.map(person => ({
  date: today, clock_in: today + 'T08:5' + person.id + ':00+08:00',
  status: 'present', employee_id: person.id, employee_name: person.name,
}));
const leaveTypes = ['特別休假', '補休'].map((name, index) => ({ id: index + 1, name, requires_balance: true }));
const leaveHours = {
  1: [[56, 8, 0], [12, 4, 0]],
  2: [[80, 16, 0], [8, 2, 0]],
  3: [[56, 4, 8], [6, 1.5, 0]],
  4: [[72, 12, 0], [8, 4, 0]],
};
const events = [
  { date: today, category: 'meeting', title: '月結進度會議' },
  { date: month + '-12', category: 'personnel', title: '江立禾 · 外出訪視' },
  { date: month + '-20', category: 'holiday', title: '事務所休業日（示例）' },
];
const data = {
  '/schedule': { weekdays: [0, 1, 2, 3, 4], start_time: '09:00', end_time: '18:00', break_minutes: 60 },
  '/delegates': [], '/leave-types': leaveTypes,
};

export function previewData({ pathname, searchParams }, user) {
  const scope = searchParams.get('scope');
  const start = searchParams.get('start') || today;
  const end = searchParams.get('end') || today;
  const rows = today >= start && today <= end ? attendance : [];
  const role = user.roles[0];
  const team = employees.filter(person => person.id === user.id || role === 'manager' && person.supervisor_id === user.id);
  const visibleTasks = tasks.filter(task => role === 'owner' || task.created_by === user.id || team.some(person => person.id === task.assignee_id));
  switch (pathname) {
    case '/leave-balances': {
      const id = ['owner', 'admin'].includes(role) && searchParams.get('employee_id') || user.id;
      return (leaveHours[id] ?? []).map(([total, used, reserved], index) => ({
        ...leaveTypes[index], total_minutes: total * 60, used_minutes: used * 60,
        reserved_minutes: reserved * 60, remaining_minutes: (total - used - reserved) * 60,
      }));
    }
    case '/employees': return ['owner', 'admin'].includes(role) ? employees : team;
    case '/tasks': return visibleTasks;
    case '/clients': return clients.filter(client => ['owner', 'admin'].includes(role) ||
      team.some(person => client.assignee_ids.includes(person.id)) || visibleTasks.some(task => task.client_id === client.id));
    case '/notifications': return tasks.filter(task => task.assignee_id === user.id).map(task => ({
      id: task.id, message: '任務已指派給你：' + task.title, created_at: stamp,
    }));
    case '/calendar': return events.filter(event => event.date.startsWith(searchParams.get('month')));
    case '/requests':
      if (scope === 'mine') return requests.filter(item => item.employee_id === user.id);
      if (scope === 'review') return requests.filter(item => item.status === 'pending' && item.reviewer_id === user.id);
      return scope === 'unassigned' ? [] : requests.filter(item => role === 'owner' || item.employee_id === user.id || item.reviewer_id === user.id);
    case '/attendance': return rows.filter(row => row.employee_id === user.id);
    case '/reports': return { start, end, rows: rows.filter(row => !searchParams.get('employee_id') || row.employee_id === Number(searchParams.get('employee_id'))), can_finalize: false };
    case '/overtime-targets': return { employee_id: Number(searchParams.get('employee_id')) || user.id, minutes: 120 };
    default: return data[pathname] ?? [];
  }
}
