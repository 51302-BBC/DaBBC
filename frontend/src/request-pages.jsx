import { useState } from 'react';
import { api } from './api.js';
import { formatDateTime, taipeiDate, timeValue } from './dates.js';
import { Badge, Feedback, Field, PageTitle, Section, StateNotice, Table, kindLabels, requestStatuses, useAction, useData } from './ui.jsx';

const requestKinds = ['leave', 'outing', 'overtime', 'clock_correction', 'expense', 'profile_change'];
const statusColors = { approved: 'green', pending: 'amber', returned: 'amber', paid: 'green', unassigned: 'amber' };
const reviewLabels = { submitted: '已送出', submit: '已送出', rerouted: '已轉派', cancelled: '已撤銷', approve: '核准', return: '退回', withdraw: '撤回申請', cancel: '提出撤銷', assign: '指派審核人', paid: '標記已付款', resubmit: '修正重送' };

const detailLabels = {
  start_at: '開始時間', end_at: '結束時間', reason: '事由', leave_type_id: '假別',
  minutes: '申請分鐘', date: '日期', direction: '打卡類型', corrected_at: '補正時間',
  amount: '金額', purpose: '用途', client_id: '客戶公司', attachment_name: '憑證',
  phone: '電話', address: '地址', emergency_contact: '緊急聯絡人', original_id: '原申請單',
};

function localValue(value) {
  if (!value) return '';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '';
  const fields = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Taipei', dateStyle: 'short', timeStyle: 'short' }).format(parsed);
  return fields.replace(' ', 'T').slice(0, 16);
}

function asData(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('無法讀取憑證，請重新選取檔案。'));
    reader.onload = () => resolve(String(reader.result).split(',')[1]);
    reader.readAsDataURL(file);
  });
}

function RequestForm({ original, revision, update, close }) {
  const [kind, setKind] = useState(original?.kind ?? 'leave');
  const data = original?.details ?? {};
  const leaveTypes = useData(kind === 'leave' ? '/leave-types' : null, revision);
  const clients = useData(kind === 'expense' ? '/clients' : null, revision);
  const action = useAction(update);
  const interval = ['leave', 'outing', 'overtime'].includes(kind);
  async function makeDetails(fields) {
    if (interval) {
      const start = fields.get('start_at');
      const end = fields.get('end_at');
      if (start >= end) throw new Error('結束時間必須晚於開始時間。');
      const details = { start_at: timeValue(start), end_at: timeValue(end), reason: fields.get('reason') };
      if (kind === 'leave') details.leave_type_id = Number(fields.get('leave_type_id'));
      if (fields.get('minutes')) details.minutes = Number(fields.get('minutes'));
      return details;
    }
    if (kind === 'clock_correction') return {
      date: fields.get('date'), direction: fields.get('direction'),
      corrected_at: timeValue(fields.get('corrected_at')), reason: fields.get('reason'),
    };
    if (kind === 'expense') {
      const details = {
        date: fields.get('date'), amount: Number(fields.get('amount')), purpose: fields.get('purpose'),
        client_id: fields.get('client_id') ? Number(fields.get('client_id')) : null,
      };
      const file = fields.get('attachment');
      if (file?.size > 5 * 1024 * 1024) throw new Error('憑證不得超過 5 MB。');
      if (file?.size) {
        details.attachment_name = file.name;
        details.attachment_data = await asData(file);
      } else if (data.attachment_name) {
        details.attachment_name = data.attachment_name;
        if (data.attachment_data) details.attachment_data = data.attachment_data;
      }
      return details;
    }
    const changed = ['phone', 'address', 'emergency_contact'].filter(field => fields.get(field)?.trim());
    if (!changed.length) throw new Error('請至少填寫一項要修改的個人資料。');
    return Object.fromEntries(changed.map(field => [field, fields.get(field).trim()]));
  }
  return <Section title={original ? '修正重送：' + (kindLabels[kind] ?? kind) : '新增申請'}>
    <form className="form-grid" onSubmit={event => {
      event.preventDefault();
      const form = event.currentTarget;
      const fields = new FormData(form);
      action.run(async () => {
        const details = await makeDetails(fields);
        return api(original ? '/requests/' + original.id + '/resubmit' : '/requests', {
          method: 'POST', body: original ? { details } : { kind, details },
        });
      }, original ? '申請已重送' : '申請已送出').then(result => {
        if (result !== undefined && !original) form.reset();
      });
    }}>
      {!original && <Field label="申請類型"><select value={kind} onChange={event => setKind(event.currentTarget.value)}>
        {requestKinds.map(key => <option key={key} value={key}>{kindLabels[key]}</option>)}
      </select></Field>}
      {interval && <>
        {kind === 'leave' && <Field label="假別"><select name="leave_type_id" required defaultValue={data.leave_type_id ?? ''}>
          <option value="">選擇假別</option>
          {(leaveTypes.data ?? []).map(item => <option value={item.id} key={item.id}>{item.name}</option>)}
        </select></Field>}
        <Field label="開始時間"><input name="start_at" type="datetime-local" defaultValue={localValue(data.start_at)} required /></Field>
        <Field label="結束時間"><input name="end_at" type="datetime-local" defaultValue={localValue(data.end_at)} required /></Field>
        {kind !== 'outing' && <Field label="申請分鐘（選填）"><input name="minutes" type="number" min="1" defaultValue={data.minutes ?? ''} /></Field>}
        <Field label="事由" full><textarea name="reason" defaultValue={data.reason} required rows="3" /></Field>
      </>}
      {kind === 'clock_correction' && <>
        <Field label="出勤日期"><input name="date" type="date" defaultValue={data.date ?? taipeiDate()} required /></Field>
        <Field label="打卡類型"><select name="direction" defaultValue={data.direction ?? 'in'}><option value="in">上班</option><option value="out">下班</option></select></Field>
        <Field label="補正時間"><input name="corrected_at" type="datetime-local" defaultValue={localValue(data.corrected_at)} required /></Field>
        <Field label="補正事由" full><textarea name="reason" defaultValue={data.reason} required rows="3" /></Field>
      </>}
      {kind === 'expense' && <>
        <Field label="費用日期"><input name="date" type="date" defaultValue={data.date ?? taipeiDate()} required /></Field>
        <Field label="金額（新臺幣）"><input name="amount" type="number" step="0.01" min="0.01" defaultValue={data.amount} required /></Field>
        <Field label="關聯客戶公司（選填）"><select name="client_id" defaultValue={data.client_id ?? ''}><option value="">未指定</option>
          {(clients.data ?? []).map(client => <option value={client.id} key={client.id}>{client.name}</option>)}
        </select></Field>
        <Field label="用途" full><textarea name="purpose" defaultValue={data.purpose} required rows="3" /></Field>
        <Field label="憑證（5 MB 以內）" full><input name="attachment" type="file" accept=".pdf,.png,.jpeg,.jpg,.webp" /></Field>
      </>}
      {kind === 'profile_change' && <>
        <Field label="新電話"><input name="phone" type="tel" defaultValue={data.phone} /></Field>
        <Field label="新緊急聯絡人"><input name="emergency_contact" defaultValue={data.emergency_contact} /></Field>
        <Field label="新地址" full><input name="address" defaultValue={data.address} /></Field>
      </>}
      <div className="form-actions full"><button className="button primary" type="submit" disabled={action.busy}>{action.busy ? '送出中…' : '送出申請'}</button>
        <button className="button secondary" type="button" onClick={close}>關閉</button></div>
    </form>
    <StateNotice state={leaveTypes} empty="目前尚未設定假別。" />
    <StateNotice state={{ ...clients, data: null }} />
    <Feedback action={action} />
  </Section>;
}

function presentDetail(field, value, leaveTypes, clients) {
  if (field.endsWith('_at')) return formatDateTime(value);
  if (field === 'direction') return value === 'in' ? '上班' : '下班';
  if (field === 'leave_type_id') return leaveTypes.find(item => item.id === value)?.name ?? value;
  if (field === 'client_id') return clients.find(item => item.id === value)?.name ?? value;
  return String(value);
}

function RequestDetail({ item, user, scope, revision, update, close, edit }) {
  const [pendingAction, setPendingAction] = useState(null);
  const action = useAction(update);
  const leaveTypes = useData(item.kind === 'leave' ? '/leave-types' : null, revision);
  const clients = useData(item.kind === 'expense' ? '/clients' : null, revision);
  const employees = useData(scope === 'unassigned' ? '/employees' : null, revision);
  const own = item.employee_id === user.id;
  const timeRequest = ['leave', 'outing', 'overtime'].includes(item.kind);
  const canReview = !own && scope === 'review' && item.status === 'pending';
  const canPaid = !own && item.kind === 'expense' && item.status === 'approved' && user.roles.includes('admin') && (item.reviewer_id === user.id || item.reviewer_id == null);
  const actions = [
    ...(canReview ? ['approve', 'return'] : []),
    ...(own && timeRequest && item.status === 'pending' ? ['withdraw'] : []),
    ...(own && timeRequest && item.status === 'approved' && !item.original_id ? ['cancel'] : []),
    ...(own && item.status === 'returned' ? ['resubmit'] : []),
    ...(scope === 'unassigned' && item.status === 'pending' ? ['assign'] : []),
    ...(canPaid ? ['paid'] : []),
  ];
  function perform(name, body = {}) {
    action.run(() => api('/requests/' + item.id + '/' + name, { method: 'POST', body }), '申請狀態已更新').then(result => {
      if (result !== undefined) setPendingAction(null);
    });
  }
  return <Section title={(kindLabels[item.kind] ?? item.kind) + (item.original_id ? '撤銷申請' : '申請')} action={<Badge tone={statusColors[item.status]}>{requestStatuses[item.status] ?? item.status}</Badge>}>
    <div className="form-content">
      <dl className="detail-list">
        <div><dt>申請人</dt><dd>{item.employee_name ?? '員工 #' + item.employee_id}</dd></div>
        <div><dt>送件時間</dt><dd>{formatDateTime(item.created_at)}</dd></div>
        {item.original_id && <div><dt>原申請單</dt><dd>#{item.original_id}</dd></div>}
        {Object.entries(item.details ?? {}).filter(([field, value]) => detailLabels[field] && value != null && value !== '').map(([field, value]) => <div key={field}>
          <dt>{detailLabels[field]}</dt><dd>{presentDetail(field, value, leaveTypes.data ?? [], clients.data ?? [])}</dd>
        </div>)}
      </dl>
      {item.details?.attachment_name && <a className="button secondary compact" href={'/api/requests/' + item.id + '/attachment'}>下載憑證</a>}
      <div className="form-actions">
        {actions.map(name => <button className={'button ' + (name === 'approve' ? 'primary' : 'secondary')} key={name} disabled={action.busy} onClick={() => {
          if (name === 'resubmit') edit(item);
          else setPendingAction(name);
        }}>{reviewLabels[name]}</button>)}
        <button className="button secondary" onClick={close}>關閉明細</button>
      </div>
      {pendingAction && <form className="form-grid embedded" onSubmit={event => {
        event.preventDefault();
        const fields = new FormData(event.currentTarget);
        const body = {};
        if (pendingAction === 'return') body.reason = fields.get('reason');
        if (pendingAction === 'assign') body.reviewer_id = Number(fields.get('reviewer_id'));
        perform(pendingAction, body);
      }}>
        {pendingAction === 'return' && <Field label="退回原因" full><textarea name="reason" required /></Field>}
        {pendingAction === 'assign' && <Field label="審核人"><select name="reviewer_id" required defaultValue=""><option value="">選擇審核人</option>
          {(employees.data ?? []).filter(person => person.id !== item.employee_id && person.active !== false && person.roles?.some(role => timeRequest ? ['owner', 'manager'].includes(role) : role === 'admin')).map(person => <option value={person.id} key={person.id}>{person.name}</option>)}
        </select></Field>}
        <div className="form-actions full"><button className="button primary" disabled={action.busy}>{'確認' + reviewLabels[pendingAction]}</button>
          <button className="button secondary" type="button" onClick={() => setPendingAction(null)}>取消</button></div>
      </form>}
      <Feedback action={action} />
      <h3>審核歷程</h3>
      {!item.history?.length ? <p className="muted">目前沒有審核紀錄。</p> : <ol className="history">
        {item.history.map((entry, index) => <li key={entry.id ?? index}>
          {formatDateTime(entry.created_at ?? entry.at)}　{reviewLabels[entry.action] ?? requestStatuses[entry.status] ?? entry.action ?? '已送出'}{entry.actor_name && '　' + entry.actor_name}{entry.reason && '　' + entry.reason}
        </li>)}
      </ol>}
    </div>
  </Section>;
}

export function RequestsPage({ user, revision, update, reviewing = false }) {
  const [scope, setScope] = useState(reviewing ? 'review' : 'mine');
  const [selected, setSelected] = useState(null);
  const [editor, setEditor] = useState(null);
  const data = useData('/requests?scope=' + scope, revision);
  const current = data.data?.find(item => item.id === selected);
  const owner = user.roles.includes('owner');
  return <>
    <PageTitle title={reviewing ? '申請與審核' : '我的申請'}>
      {!reviewing && <button className="button primary" onClick={() => setEditor('new')}>新增申請</button>}
    </PageTitle>
    {editor && <RequestForm key={editor.id ?? editor} original={editor === 'new' ? null : editor} revision={revision} update={update} close={() => setEditor(null)} />}
    {current && <RequestDetail key={current.id} item={current} user={user} scope={scope} revision={revision} update={update} close={() => setSelected(null)} edit={setEditor} />}
    <Section title={scope === 'unassigned' ? '待指派清單' : scope === 'all' ? '申請紀錄' : reviewing ? '審核收件匣' : '申請紀錄'}
      action={reviewing && <select value={scope} aria-label="審核範圍" onChange={event => { setScope(event.currentTarget.value); setSelected(null); }}>
        <option value="review">審核收件匣</option>{owner && <option value="unassigned">待指派</option>}<option value="all">可查看的申請</option>
      </select>}>
      <StateNotice state={data} empty={reviewing ? '沒有符合條件的申請。' : '你還沒有送出申請。'} />
      {Boolean(data.data?.length) && <Table name="申請清單" rows={data.data} columns={[
        { label: '申請', render: item => <button className="link-button" onClick={() => setSelected(item.id)}>{kindLabels[item.kind] ?? item.kind}{item.original_id && '撤銷申請'}</button> },
        ...(reviewing ? [{ label: '申請人', render: item => item.employee_name ?? '#' + item.employee_id }] : []),
        { label: '送件時間', render: item => formatDateTime(item.created_at) },
        { label: '狀態', render: item => <Badge tone={statusColors[item.status]}>{requestStatuses[item.status] ?? item.status}</Badge> },
      ]} />}
    </Section>
  </>;
}
