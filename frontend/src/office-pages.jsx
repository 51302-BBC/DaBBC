import { useState } from 'react';
import { api, query } from './api.js';
import { formatDateTime, monthRange, taipeiDate } from './dates.js';
import { AttendanceBanner, Calendar } from './dashboard.jsx';
import { Badge, Feedback, Field, PageTitle, Section, StateNotice, Table, useAction, useData } from './ui.jsx';

const weekdays = ['一', '二', '三', '四', '五', '六', '日'];
const attendanceLabels = {
  complete: '已完成', incomplete: '缺卡', missing: '缺卡', absent: '未打卡',
  present: '已出勤', open: '缺下班卡', closed: '已完成', none: '無打卡紀錄',
  not_scheduled: '非工作日', unscheduled: '非工作日', off: '休息日',
  missing_in: '缺上班卡', missing_out: '缺下班卡', correction_required: '需補正',
};
const flagLabels = { ...attendanceLabels, overtime_mismatch: '加班與打卡不符', manual_allocation: '須人工核對時數' };
const minutes = value => value == null ? '—' : Number(value) + ' 分鐘';
const yes = value => value ? '是' : '否';
const peopleLabel = (items, id) => items.find(person => person.id === id)?.name ?? (id ? '#' + id : '—');

function DateRange({ value, onChange, employees }) {
  return <form className="form-grid" onSubmit={event => {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    onChange({ start: fields.get('start'), end: fields.get('end'), employee_id: fields.get('employee_id') || '' });
  }}>
    <Field label="開始日"><input type="date" name="start" defaultValue={value.start} required /></Field>
    <Field label="結束日"><input type="date" name="end" defaultValue={value.end} required /></Field>
    {employees && <Field label="員工"><select name="employee_id" defaultValue={value.employee_id}>
      <option value="">全體員工</option>{employees.map(person => <option key={person.id} value={person.id}>{person.name}</option>)}
    </select></Field>}
    <div className="form-actions"><button className="button secondary">套用日期範圍</button></div>
  </form>;
}

export function AttendancePage({ revision, update }) {
  const [range, setRange] = useState(monthRange);
  const attendance = useData('/attendance?' + query(range), revision);
  return <>
    <PageTitle title="出勤紀錄"><a className="button secondary" href="#requests">前往申請補打卡</a></PageTitle>
    <AttendanceBanner revision={revision} update={update} />
    <Section title="我的出勤">
      <DateRange value={range} onChange={setRange} />
      <StateNotice state={attendance} empty="此期間沒有出勤紀錄。" />
      {Boolean(attendance.data?.length) && <Table name="出勤紀錄" rows={attendance.data} columns={[
        { label: '日期', render: row => row.date },
        { label: '上班', render: row => formatDateTime(row.clock_in) },
        { label: '下班', render: row => formatDateTime(row.clock_out) },
        { label: '實際打卡時間差', render: row => minutes(row.worked_minutes) },
        { label: '狀態', render: row => <Badge tone={row.status === 'complete' ? 'green' : 'neutral'}>{attendanceLabels[row.status] ?? row.status}</Badge> },
        { label: '原始紀錄', render: row => row.original_clock_in && row.original_clock_in !== row.clock_in || row.original_clock_out && row.original_clock_out !== row.clock_out ?
          <details><summary>查看補正前紀錄</summary>{formatDateTime(row.original_clock_in)} – {formatDateTime(row.original_clock_out)}</details> : '—' },
      ]} />}
    </Section>
  </>;
}

function CalendarSettings({ update, close }) {
  const [category, setCategory] = useState('holiday');
  const action = useAction(update);
  return <Section title="新增行事曆事件">
    <form className="form-grid" onSubmit={event => {
      event.preventDefault();
      const fields = new FormData(event.currentTarget);
      const body = { date: fields.get('date'), title: fields.get('title'), category: fields.get('category') };
      const override = fields.get('workday_override');
      if (override) body.workday_override = override === 'working';
      action.run(() => api('/calendar', { method: 'POST', body }), '行事曆事件已新增');
    }}>
      <Field label="事件名稱"><input name="title" required /></Field>
      <Field label="日期"><input name="date" type="date" defaultValue={taipeiDate()} required /></Field>
      <Field label="事件類別"><select name="category" value={category} onChange={event => setCategory(event.currentTarget.value)}><option value="holiday">假期</option><option value="meeting">會議</option></select></Field>
      {category === 'holiday' && <Field label="當日班表調整"><select name="workday_override"><option value="">沿用班表</option><option value="holiday">放假日</option><option value="working">工作日</option></select></Field>}
      <div className="form-actions full"><button className="button primary" disabled={action.busy}>新增事件</button>
        <button className="button secondary" type="button" onClick={close}>取消</button></div>
    </form>
    <Feedback action={action} />
  </Section>;
}

export function CalendarPage({ user, revision, update }) {
  const [adding, setAdding] = useState(false);
  const manager = user.roles.some(role => ['owner', 'admin'].includes(role));
  return <>
    <PageTitle title="行事曆">{manager && <button className="button primary" onClick={() => setAdding(!adding)}>{adding ? '關閉新增事件' : '新增事件'}</button>}</PageTitle>
    {adding && <CalendarSettings update={update} close={() => setAdding(false)} />}
    <Calendar revision={revision} />
  </>;
}

function ScheduleForm({ schedule, update }) {
  const action = useAction(update);
  return <form className="form-grid" onSubmit={event => {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    action.run(() => api('/schedule', { method: 'PUT', body: {
      weekdays: fields.getAll('weekdays').map(Number), start_time: fields.get('start_time'),
      end_time: fields.get('end_time'), break_minutes: Number(fields.get('break_minutes')),
    }}), '班表已儲存');
  }}>
    <fieldset className="full"><legend>每週工作日</legend><div className="checks">
      {weekdays.map((name, index) => <label className="checkbox" key={name}><input type="checkbox" name="weekdays" value={index}
        defaultChecked={schedule?.weekdays?.includes(index)} /> 週{name}</label>)}
    </div></fieldset>
    <Field label="上班時間"><input name="start_time" type="time" defaultValue={schedule?.start_time?.slice(0, 5)} required /></Field>
    <Field label="下班時間"><input name="end_time" type="time" defaultValue={schedule?.end_time?.slice(0, 5)} required /></Field>
    <Field label="休息分鐘"><input name="break_minutes" type="number" min="0" defaultValue={schedule?.break_minutes ?? 0} required /></Field>
    <div className="form-actions full"><button className="button primary" disabled={action.busy}>儲存班表</button></div>
    <div className="full"><Feedback action={action} /></div>
  </form>;
}

export function SchedulePage({ revision, update }) {
  const schedule = useData('/schedule', revision);
  return <>
    <PageTitle title="班表設定" />
    <Section title="全所固定班表">
      <StateNotice state={schedule} />
      {!schedule.loading && !schedule.error && <ScheduleForm schedule={schedule.data} update={update} />}
    </Section>
  </>;
}

export function BalancesPage({ user, revision, update }) {
  const [employee, setEmployee] = useState('');
  const [settings, setSettings] = useState(false);
  const canManage = user.roles.some(role => ['owner', 'admin'].includes(role));
  const employees = useData(canManage ? '/employees' : null, revision);
  const leaveTypes = useData('/leave-types', revision);
  const balances = useData('/leave-balances?' + query({ employee_id: employee }), revision);
  const action = useAction(update);
  const overtime = useData(canManage ? '/overtime-targets?' + query({ employee_id: employee }) : null, revision);
  return <>
    <PageTitle title="假別與時數">{canManage && <button className="button primary" onClick={() => setSettings(!settings)}>{settings ? '關閉設定' : '管理假別與時數'}</button>}</PageTitle>
    {settings && <>
      <Section title="新增假別">
        <form className="form-grid" onSubmit={event => {
          event.preventDefault();
          const fields = new FormData(event.currentTarget);
          action.run(() => api('/leave-types', { method: 'POST', body: { name: fields.get('name'), requires_balance: fields.has('requires_balance') }}), '假別已新增');
        }}>
          <Field label="假別名稱"><input name="name" required /></Field>
          <label className="checkbox"><input name="requires_balance" type="checkbox" defaultChecked /> 需要可用額度</label>
          <div className="form-actions full"><button className="button primary" disabled={action.busy}>新增假別</button></div>
        </form>
      </Section>
      <Section title="設定員工請假額度">
        <form className="form-grid" onSubmit={event => {
          event.preventDefault();
          const fields = new FormData(event.currentTarget);
          action.run(() => api('/leave-balances', { method: 'PUT', body: {
            employee_id: Number(fields.get('employee_id')), leave_type_id: Number(fields.get('leave_type_id')),
            total_minutes: Number(fields.get('total_minutes')),
          }}), '請假額度已儲存');
        }}>
          <Field label="員工"><select name="employee_id" required defaultValue=""><option value="">選擇員工</option>
            {(employees.data ?? []).map(person => <option value={person.id} key={person.id}>{person.name}</option>)}
          </select></Field>
          <Field label="假別"><select name="leave_type_id" required defaultValue=""><option value="">選擇假別</option>
            {(leaveTypes.data ?? []).filter(item => item.requires_balance).map(item => <option value={item.id} key={item.id}>{item.name}</option>)}
          </select></Field>
          <Field label="額度（分鐘）"><input name="total_minutes" type="number" min="0" required /></Field>
          <div className="form-actions full"><button className="button primary" disabled={action.busy}>儲存額度</button></div>
        </form>
      </Section>
      <Section title="設定員工加班時數">
        <form className="form-grid" onSubmit={event => {
          event.preventDefault();
          const fields = new FormData(event.currentTarget);
          action.run(() => api('/overtime-targets', { method: 'PUT', body: {
            employee_id: Number(fields.get('employee_id')), minutes: Number(fields.get('minutes')),
          }}), '加班時數已儲存');
        }}>
          <Field label="員工"><select name="employee_id" required defaultValue=""><option value="">選擇員工</option>
            {(employees.data ?? []).map(person => <option value={person.id} key={person.id}>{person.name}</option>)}
          </select></Field>
          <Field label="加班時數（分鐘）"><input name="minutes" type="number" min="0" required /></Field>
          <div className="form-actions full"><button className="button primary" disabled={action.busy}>儲存加班時數</button></div>
        </form>
      </Section>
      <Feedback action={action} />
    </>}
    {canManage && <Section title="已設定加班時數"><StateNotice state={overtime} />
      {overtime.data && <p className="notice">{peopleLabel(employees.data ?? [], overtime.data.employee_id ?? user.id)}　{minutes(overtime.data.minutes)}</p>}
    </Section>}
    <Section title="請假餘額" action={canManage && <select aria-label="員工" value={employee} onChange={event => setEmployee(event.currentTarget.value)}>
      <option value="">我的餘額</option>{(employees.data ?? []).map(person => <option value={person.id} key={person.id}>{person.name}</option>)}
    </select>}>
      <StateNotice state={balances} empty="此員工目前沒有設定假別。" />
      {Boolean(balances.data?.length) && <Table name="請假餘額" rows={balances.data} columns={[
        { label: '假別', render: balance => balance.name },
        { label: '需要額度', render: balance => yes(balance.requires_balance) },
        { label: '額度', render: balance => minutes(balance.total_minutes) },
        { label: '已使用', render: balance => minutes(balance.used_minutes) },
        { label: '待審保留', render: balance => minutes(balance.reserved_minutes) },
        { label: '剩餘', render: balance => minutes(balance.remaining_minutes) },
      ]} />}
    </Section>
  </>;
}

export function ReportsPage({ revision, update }) {
  const [range, setRange] = useState(monthRange);
  const action = useAction(update);
  const search = query(range);
  const report = useData('/reports?' + search, revision);
  const employees = useData('/employees', revision);
  const result = report.data;
  async function exportExcel() {
    const { content, filename } = await api('/reports/export', {
      method: 'POST', responseType: 'file', body: {
        start: result.start, end: result.end, employee_id: range.employee_id ? Number(range.employee_id) : null,
      },
    });
    const downloadUrl = URL.createObjectURL(content);
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.download = filename || 'work-hours.xlsx';
    link.click();
    setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
  }
  return <>
    <PageTitle title="工時與假勤報表" />
    <Section title="報表條件">
      <DateRange value={range} onChange={setRange} employees={employees.data ?? []} />
      {result && <div className="panel-foot form-actions">
        {result.note && <p className="muted">{result.note}</p>}
        {result.calculation_configured === false && <p className="muted">工時計算尚未完成設定，請以原始紀錄核對出勤。</p>}
        <button className="button secondary" disabled={action.busy || report.loading}
          onClick={() => action.run(exportExcel, 'Excel 已匯出')}>匯出 Excel</button>
        <button className="button primary" disabled={action.busy || !result.can_finalize} onClick={() => action.run(() => api('/reports/finalize', {
          method: 'POST', body: { start: range.start, end: range.end, employee_id: range.employee_id ? Number(range.employee_id) : null },
        }), '報表定稿已儲存')}>保留定稿</button>
      </div>}
      <StateNotice state={report} />
      <Feedback action={action} />
    </Section>
    {result && <>
      <Section title="逐日明細">
        {result.rows?.length ? <Table name="工作時數明細" rows={result.rows} columns={[
          { label: '日期', render: row => row.date },
          { label: '員工', render: row => row.employee_name ?? peopleLabel(employees.data ?? [], row.employee_id) },
          { label: '上班', render: row => formatDateTime(row.clock_in) },
          { label: '下班', render: row => formatDateTime(row.clock_out) },
          { label: '正常工時', render: row => minutes(row.normal_minutes ?? row.regular_minutes) },
          { label: '加班', render: row => minutes(row.overtime_minutes ?? row.approved_overtime_minutes) },
          { label: '請假', render: row => minutes(row.leave_minutes) },
          { label: '外出', render: row => minutes(row.outing_minutes) },
          { label: '異常', render: row => (row.flags ?? []).map(flag => flagLabels[flag] ?? flag).join('、') || '—' },
        ]} /> : <p className="notice">此期間沒有工時明細。</p>}
      </Section>
      <Section title="請假與加班彙總">
        {Array.isArray(result.summary) && result.summary.length ? <Table name="假勤時數彙總" rows={result.summary} columns={[
          { label: '員工', render: row => row.employee_name ?? peopleLabel(employees.data ?? [], row.employee_id) },
          { label: '請假', render: row => minutes(row.leave_minutes) },
          { label: '加班', render: row => minutes(row.overtime_minutes ?? row.approved_overtime_minutes) },
          { label: '正常工時', render: row => minutes(row.normal_minutes ?? row.regular_minutes) },
        ]} /> : <p className="notice">此期間沒有彙總資料。</p>}
      </Section>
      <Section title="歷史定稿">
        {result.versions?.length ? <Table name="歷史定稿" rows={result.versions} columns={[
          { label: '版本', render: row => '第 ' + row.version + ' 版' },
          { label: '定稿日期', render: row => formatDateTime(row.created_at) },
          { label: '下載', render: row => <a href={'/api/reports/' + row.id + '/download'}>下載 Excel</a> },
        ]} /> : <p className="notice">這個報表期間目前沒有定稿。</p>}
      </Section>
    </>}
  </>;
}

export function DelegatesPage({ revision, update }) {
  const action = useAction(update);
  const delegates = useData('/delegates', revision);
  const employees = useData('/employees', revision);
  const people = (employees.data ?? []).filter(person => person.active !== false);
  return <>
    <PageTitle title="代理審核" />
    <Section title="指定代理人">
      <form className="form-grid" onSubmit={event => {
        event.preventDefault();
        const fields = new FormData(event.currentTarget);
        const body = {
          supervisor_id: fields.get('supervisor_id') ? Number(fields.get('supervisor_id')) : null,
          reviewer_id: Number(fields.get('reviewer_id')), start: fields.get('start'), end: fields.get('end'),
        };
        action.run(() => api('/delegates', { method: 'POST', body }), '代理審核已設定');
      }}>
        <Field label="原主管"><select name="supervisor_id"><option value="">未指定直屬主管時</option>
          {people.filter(person => person.roles?.some(role => ['owner', 'manager'].includes(role))).map(person => <option value={person.id} key={person.id}>{person.name}</option>)}
        </select></Field>
        <Field label="代理審核人"><select name="reviewer_id" required defaultValue=""><option value="">選擇代理人</option>
          {people.filter(person => person.roles?.some(role => ['owner', 'manager'].includes(role))).map(person => <option value={person.id} key={person.id}>{person.name}</option>)}
        </select></Field>
        <Field label="生效日"><input name="start" type="date" required defaultValue={taipeiDate()} /></Field>
        <Field label="結束日"><input name="end" type="date" required /></Field>
        <div className="form-actions full"><button className="button primary" disabled={action.busy}>設定代理人</button></div>
      </form>
      <Feedback action={action} />
    </Section>
    <Section title="代理設定紀錄">
      <StateNotice state={delegates} empty="目前尚無代理設定。" />
      {Boolean(delegates.data?.length) && <Table name="代理設定紀錄" rows={delegates.data} columns={[
        { label: '原主管', render: row => row.supervisor_name || (row.supervisor_id ? peopleLabel(people, row.supervisor_id) : '無直屬主管') },
        { label: '代理人', render: row => row.reviewer_name || peopleLabel(people, row.reviewer_id) },
        { label: '生效日', render: row => row.start },
        { label: '結束日', render: row => row.end },
      ]} />}
    </Section>
  </>;
}
