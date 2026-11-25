import { useState } from 'react';
import { api } from './api.js';
import { formatDateTime, taipeiDate } from './dates.js';
import { Badge, Feedback, Field, PageTitle, Section, StateNotice, Table, roles, taskStatuses, useAction, useData } from './ui.jsx';

const taskTones = { pending: 'neutral', in_progress: 'blue', completed: 'green', canceled: 'neutral' };
const id = value => value ? Number(value) : null;
const names = values => values?.map(role => roles[role] ?? role).join('、');
const personLabel = (items, value) => items.find(item => item.id === value)?.name ?? (value ? '#' + value : '—');

function FormActions({ action, editing, cancel, label = '儲存' }) {
  return <div className="form-actions full">
    <button className="button primary" type="submit" disabled={action.busy}>{action.busy ? '處理中…' : label}</button>
    <button className="button secondary" type="button" onClick={cancel}>{editing ? '取消編輯' : '關閉'}</button>
  </div>;
}

function TaskHistory({ taskId, revision }) {
  const history = useData('/tasks/' + taskId + '/history', revision);
  return <div className="form-content">
    <StateNotice state={history} empty="這筆任務目前沒有變更紀錄。" />
    {(history.data ?? []).map((event, index) => <p key={event.id ?? index}>{formatDateTime(event.created_at)}　{event.message ?? event.action ?? (event.status ? taskStatuses[event.status] : '已更新')}</p>)}
  </div>;
}

function TaskForm({ item, clients, employees, roles: userRoles, user, onClose, update }) {
  const [clientId, setClientId] = useState(item?.client_id ?? '');
  const action = useAction(update);
  const owner = userRoles.includes('owner');
  const canAssign = owner || userRoles.some(role => ['manager', 'admin'].includes(role)) && (!item || item.created_by === user.id);
  const terminal = item && ['completed', 'canceled'].includes(item.status);
  const canProgress = item && !terminal && (item.assignee_id === user.id || owner);
  const allowedStatuses = item ? [...new Set([
    item.status, ...(canProgress ? ['pending', 'in_progress', 'completed'] : []),
    ...(item.can_cancel ? ['canceled'] : []), ...(item.can_reopen ? ['pending'] : []),
  ])] : [];
  const selectedClient = clients.find(client => client.id === Number(clientId));
  const employeeMap = new Map(employees.map(person => [person.id, person]));
  if (item?.assignee_id && !employeeMap.has(item.assignee_id)) {
    employeeMap.set(item.assignee_id, { id: item.assignee_id, name: item.assignee_name || '目前負責人' });
  }
  const assignees = [...employeeMap.values()].filter(person => person.id === item?.assignee_id ||
    person.active !== false && selectedClient?.assignee_ids?.includes(person.id) &&
    (owner || userRoles.includes('admin') || userRoles.includes('manager') && person.supervisor_id === user.id));
  function submit(event) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const body = {};
    if (!item) {
      body.title = fields.get('title');
      body.description = fields.get('description');
      body.client_id = id(clientId);
      body.due_on = fields.get('due_on') || null;
    }
    if (canAssign && fields.has('assignee_id') && (!item || Number(fields.get('assignee_id')) !== item.assignee_id)) body.assignee_id = id(fields.get('assignee_id'));
    if (item && fields.has('status') && fields.get('status') !== item.status) body.status = fields.get('status');
    action.run(() => api(item ? '/tasks/' + item.id : '/tasks', { method: item ? 'PATCH' : 'POST', body }));
  }
  return <Section title={item ? item.title : '新增任務'}>
    <form className="form-grid" onSubmit={submit}>
      {!item ? <>
        <Field label="任務名稱" full><input name="title" required maxLength="160" /></Field>
        <Field label="客戶公司"><select value={clientId} required onChange={event => setClientId(event.currentTarget.value)}>
          <option value="">選擇客戶公司</option>{clients.filter(client => client.active !== false).map(client => <option key={client.id} value={client.id}>{client.name}</option>)}
        </select></Field>
        <Field label="到期日"><input name="due_on" type="date" defaultValue={taipeiDate()} /></Field>
        <Field label="任務說明" full><textarea name="description" rows="3" /></Field>
      </> : <div className="full detail-list"><p>客戶公司　{item.client_name ?? '—'}</p><p>到期日　{item.due_on ?? '—'}</p><p>{item.description || '尚無補充說明。'}</p></div>}
      {canAssign && <Field label="主要負責人"><select name="assignee_id" key={clientId} required defaultValue={item?.assignee_id ?? ''}>
        <option value="">選擇負責人</option>{assignees.map(person => <option key={person.id} value={person.id}>{person.name}</option>)}
      </select></Field>}
      {allowedStatuses.length > 1 && <Field label="狀態"><select name="status" defaultValue={item.status}>
        {allowedStatuses.map(key => <option key={key} value={key}>{taskStatuses[key]}</option>)}
      </select></Field>}
      {!item || canAssign || allowedStatuses.length > 1 ? <FormActions action={action} editing={Boolean(item)} cancel={onClose} /> :
        <div className="form-actions full"><button className="button secondary" type="button" onClick={onClose}>關閉</button></div>}
    </form>
    <Feedback action={action} />
    {item && <details className="record-details"><summary>查看改派與狀態紀錄</summary><TaskHistory taskId={item.id} /></details>}
  </Section>;
}

export function TasksPage({ user, revision, update }) {
  const [editing, setEditing] = useState(null);
  const [filter, setFilter] = useState('');
  const [mine, setMine] = useState(!user.roles.includes('owner'));
  const canCreate = user.roles.some(role => ['owner', 'manager', 'admin'].includes(role));
  const tasks = useData('/tasks', revision);
  const clients = useData(canCreate ? '/clients' : null, revision);
  const employees = useData(canCreate ? '/employees' : null, revision);
  let items = tasks.data ?? [];
  if (mine) items = items.filter(task => task.assignee_id === user.id);
  if (filter) items = items.filter(task => task.status === filter);
  const current = editing && editing !== 'new' ? tasks.data?.find(item => item.id === editing) : null;
  return <>
    <PageTitle title="任務總覽">{canCreate && <button className="button primary" onClick={() => setEditing('new')}>新增任務</button>}</PageTitle>
    {editing && <TaskForm key={editing} item={current} clients={clients.data ?? []} employees={employees.data ?? []} roles={user.roles} user={user} update={update} onClose={() => setEditing(null)} />}
    {editing && <><StateNotice state={clients} /><StateNotice state={employees} /></>}
    <Section title={mine ? '我的任務' : '可查看的任務'} action={<span className="inline-controls">
      <label className="checkbox"><input type="checkbox" checked={mine} onChange={event => setMine(event.currentTarget.checked)} /> 只看我的</label>
      <select aria-label="任務狀態" value={filter} onChange={event => setFilter(event.currentTarget.value)}>
        <option value="">所有狀態</option>{Object.entries(taskStatuses).map(([key, value]) => <option key={key} value={key}>{value}</option>)}
      </select>
    </span>}>
      <StateNotice state={{ ...tasks, data: tasks.data ? items : null }} empty="沒有符合條件的任務。" />
      {Boolean(items.length) && <Table name="任務總覽" rows={items} columns={[
        { label: '任務', render: task => <button className="link-button" onClick={() => setEditing(task.id)}>{task.title}</button> },
        { label: '客戶公司', render: task => task.client_name ?? '—' },
        { label: '負責人', render: task => task.assignee_name ?? '—' },
        { label: '到期', render: task => task.due_on ?? '—' },
        { label: '狀態', render: task => <Badge tone={taskTones[task.status]}>{taskStatuses[task.status] ?? task.status}</Badge> }
      ]} />}
    </Section>
  </>;
}

function ClientForm({ item, employees, update, close }) {
  const action = useAction(update);
  return <Section title={item ? '編輯客戶公司' : '新增客戶公司'}>
    <form className="form-grid" onSubmit={event => {
      event.preventDefault();
      const fields = new FormData(event.currentTarget);
      action.run(() => api(item ? '/clients/' + item.id : '/clients', { method: item ? 'PATCH' : 'POST', body: {
        name: fields.get('name'), active: fields.has('active'), assignee_ids: fields.getAll('assignee_ids').map(Number),
      }}));
    }}>
      <Field label="公司名稱"><input name="name" defaultValue={item?.name} required maxLength="160" /></Field>
      <label className="checkbox"><input type="checkbox" name="active" defaultChecked={item?.active !== false} /> 公司啟用</label>
      <fieldset className="full"><legend>公司負責人</legend><div className="checks">
        {employees.filter(employee => employee.active !== false || item?.assignee_ids?.includes(employee.id)).map(employee => <label className="checkbox" key={employee.id}>
          <input type="checkbox" name="assignee_ids" value={employee.id} defaultChecked={item?.assignee_ids?.includes(employee.id)} /> {employee.name}
        </label>)}
        {!employees.length && <span className="muted">目前沒有可選擇的員工。</span>}
      </div></fieldset>
      <FormActions action={action} editing={Boolean(item)} cancel={close} />
    </form>
    <Feedback action={action} />
  </Section>;
}

export function ClientsPage({ user, revision, update }) {
  const [editing, setEditing] = useState(null);
  const canEdit = user.roles.some(role => ['owner', 'admin'].includes(role));
  const clients = useData('/clients', revision);
  const employees = useData(canEdit ? '/employees' : null, revision);
  const current = editing && editing !== 'new' ? clients.data?.find(item => item.id === editing) : null;
  return <>
    <PageTitle title="客戶公司">{canEdit && <button className="button primary" onClick={() => setEditing('new')}>新增客戶公司</button>}</PageTitle>
    {editing && <ClientForm key={editing} item={current} employees={employees.data ?? []} update={update} close={() => setEditing(null)} />}
    <Section title={canEdit ? '公司與負責人' : '我負責的公司'}>
      <StateNotice state={clients} empty="目前沒有可查看的客戶公司。" />
      {Boolean(clients.data?.length) && <Table name="客戶公司" rows={clients.data} columns={[
        { label: '公司名稱', render: item => canEdit ? <button className="link-button" onClick={() => setEditing(item.id)}>{item.name}</button> : item.name },
        { label: '負責人', render: item => item.assignee_names?.join('、') || item.assignee_ids?.map(value => personLabel(employees.data ?? [], value)).join('、') || '—' },
        { label: '狀態', render: item => <Badge tone={item.active ? 'green' : 'neutral'}>{item.active ? '啟用' : '已停用'}</Badge> }
      ]} />}
    </Section>
  </>;
}

function Handoff({ employeeId, revision }) {
  const data = useData('/employees/' + employeeId + '/handoff', revision);
  const labels = {
    tasks: '未完成任務', pending_requests: '待審申請', requests: '待審申請',
    direct_reports: '直屬員工', employees: '直屬員工', subordinates: '直屬員工',
  };
  return <div className="form-content">
    <StateNotice state={data} />
    {Object.entries(data.data ?? {}).map(([key, items]) => <section key={key}>
      <h3>{labels[key] ?? key}</h3>
      {Array.isArray(items) && items.length ? <ul>{items.map((entry, i) => <li key={entry.id ?? i}>{entry.title ?? entry.name ?? entry.employee_name ?? ('#' + (entry.id ?? entry))}</li>)}</ul> : <p className="muted">沒有需要交接的紀錄。</p>}
    </section>)}
  </div>;
}

function EmployeeForm({ item, employees, user, update, revision, close }) {
  const action = useAction(update);
  const [showHandoff, setShowHandoff] = useState(false);
  const owner = user.roles.includes('owner');
  const protectLogin = !owner && item?.roles?.includes('admin');
  function submit(event) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const body = {
      name: fields.get('name'), ...(protectLogin ? {} : { email: fields.get('email') }),
      supervisor_id: id(fields.get('supervisor_id')), started_on: fields.get('started_on') || null,
    };
    if (item) {
      if (!protectLogin) body.active = fields.has('active');
      for (const field of ['phone', 'address', 'emergency_contact']) body[field] = fields.get(field);
    }
    if (owner) body.roles = fields.getAll('roles');
    action.run(() => api(item ? '/employees/' + item.id : '/employees', { method: item ? 'PATCH' : 'POST', body }), item ? '員工資料已儲存' : '員工帳號已建立');
  }
  return <Section title={item ? '編輯員工資料' : '建立員工帳號'}>
    <form className="form-grid" onSubmit={submit}>
      <Field label="姓名"><input name="name" defaultValue={item?.name} required /></Field>
      <Field label="電子郵件"><input name="email" type="email" defaultValue={item?.email} disabled={protectLogin} required /></Field>
      <Field label="到職日期"><input name="started_on" type="date" defaultValue={item?.started_on ?? ''} /></Field>
      <Field label="直屬主管"><select name="supervisor_id" defaultValue={item?.supervisor_id ?? ''}>
        <option value="">尚未指定</option>{employees.filter(employee => employee.id !== item?.id && employee.active !== false && employee.roles?.some(role => ['owner', 'manager'].includes(role))).map(employee => <option key={employee.id} value={employee.id}>{employee.name}</option>)}
      </select></Field>
      {item && <>
        <Field label="電話"><input name="phone" type="tel" defaultValue={item.phone ?? ''} /></Field>
        <Field label="緊急聯絡人"><input name="emergency_contact" defaultValue={item.emergency_contact ?? ''} /></Field>
        <Field label="地址" full><input name="address" defaultValue={item.address ?? ''} /></Field>
        <label className="checkbox"><input type="checkbox" name="active" disabled={protectLogin} defaultChecked={item.active} /> 帳號啟用</label>
        <div className="form-actions full">
          <button className="button secondary" type="button" onClick={() => setShowHandoff(!showHandoff)} aria-expanded={showHandoff}>查看離職交接</button>
          {item.active && <button className="button secondary" type="button" disabled={action.busy} onClick={() =>
            action.run(() => api('/employees/' + item.id + '/invite', { method: 'POST' }), '啟用邀請已寄出')}>重寄啟用邀請</button>}
        </div>
      </>}
      {owner && <fieldset className="full"><legend>角色</legend><div className="checks">
        {Object.entries(roles).map(([key, label]) => <label key={key} className="checkbox">
          <input type="checkbox" name="roles" value={key} defaultChecked={(item?.roles ?? ['employee']).includes(key)} /> {label}
        </label>)}
      </div></fieldset>}
      <FormActions action={action} editing={Boolean(item)} cancel={close} label={item ? '儲存員工資料' : '建立員工帳號'} />
    </form>
    <Feedback action={action} />
    {showHandoff && <Handoff employeeId={item.id} revision={revision} />}
  </Section>;
}

export function EmployeesPage({ user, revision, update }) {
  const [editing, setEditing] = useState(null);
  const employees = useData('/employees', revision);
  const list = employees.data ?? [];
  const current = editing && editing !== 'new' ? list.find(item => item.id === editing) : null;
  return <>
    <PageTitle title="員工與組織"><button className="button primary" onClick={() => setEditing('new')}>新增員工</button></PageTitle>
    {editing && <EmployeeForm key={editing} item={current} employees={list} user={user} revision={revision} update={update} close={() => setEditing(null)} />}
    <Section title="員工名單">
      <StateNotice state={employees} empty="目前沒有員工紀錄。" />
      {Boolean(list.length) && <Table name="員工名單" rows={list} columns={[
        { label: '員工', render: item => item.roles?.includes('owner') && !user.roles.includes('owner') ? item.name :
          <button className="link-button" onClick={() => setEditing(item.id)}>{item.name}</button> },
        { label: '電子郵件', render: item => item.email ?? '—' },
        { label: '直屬主管', render: item => personLabel(list, item.supervisor_id) },
        { label: '角色', render: item => names(item.roles) || '—' },
        { label: '狀態', render: item => <Badge tone={item.active ? 'green' : 'neutral'}>{item.active ? '啟用' : '已停用'}</Badge> }
      ]} />}
    </Section>
  </>;
}

export function NotificationsPage({ revision, update }) {
  const notifications = useData('/notifications', revision);
  const action = useAction(update);
  return <>
    <PageTitle title="通知中心" />
    <Section title="系統通知" action={<Badge tone="blue">{(notifications.data ?? []).filter(item => !item.read_at).length} 封未讀</Badge>}>
      <StateNotice state={notifications} empty="目前沒有通知。" />
      {(notifications.data ?? []).map(item => <div className="list-row" key={item.id}>
        <div><strong>{item.message}</strong><small>{formatDateTime(item.created_at)}</small></div>
        {item.read_at ? <Badge>已讀</Badge> : <button className="button secondary compact" disabled={action.busy} onClick={() => action.run(() => api('/notifications/' + item.id + '/read', { method: 'PATCH' }), '已標為已讀')}>標為已讀</button>}
      </div>)}
      <Feedback action={action} />
    </Section>
  </>;
}
