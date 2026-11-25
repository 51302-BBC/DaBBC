import { useState } from 'react';
import { api, query } from './api.js';
import { formatDateTime, monthDates, taipeiDate } from './dates.js';
import { Badge, Feedback, PageTitle, Section, StateNotice, kindLabels, taskStatuses, useAction, useData } from './ui.jsx';

const calendarCategories = { personnel: '人事', holiday: '假期', meeting: '會議' };
const flowStates = ['pending', 'in_progress', 'completed'];
const stateTones = { pending: 'neutral', in_progress: 'blue', completed: 'green', canceled: 'neutral' };

export function AttendanceBanner({ revision, update }) {
  const today = taipeiDate();
  const data = useData('/attendance?' + query({ start: today, end: today }), revision);
  const action = useAction(update);
  const day = data.data?.[0];
  const next = !day?.clock_in ? 'in' : !day?.clock_out ? 'out' : null;
  const labels = { in: '上班打卡', out: '下班打卡' };
  return <>
    <section className="clock-banner">
      <div>
        <h2>{!day?.clock_in ? '今日尚未上班打卡' : day?.clock_out ? '今日已完成打卡' : '今日已上班打卡'}</h2>
        <p>{day?.clock_in ? '上班 ' + formatDateTime(day.clock_in) : '打卡時間以伺服器的臺北時間為準'}{day?.clock_out ? '　下班 ' + formatDateTime(day.clock_out) : ''}</p>
      </div>
      {next && <button className="button amber" disabled={action.busy || data.loading || Boolean(data.error)}
        onClick={() => action.run(() => api('/attendance/clock', { method: 'POST', body: { action: next } }), '打卡已記錄')}>
        {action.busy ? '記錄中…' : labels[next]}
      </button>}
    </section>
    {data.error && <StateNotice state={data} />}
    <Feedback action={action} />
  </>;
}

export function TaskBoard({ items }) {
  const [filter, setFilter] = useState('');
  const today = taipeiDate();
  const statuses = filter ? [filter] : flowStates;
  return <Section title="我的任務進度" className="task-board" action={<select value={filter} aria-label="依任務狀態篩選" onChange={event => setFilter(event.currentTarget.value)}>
    <option value="">全部</option>{Object.entries(taskStatuses).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
  </select>}>
    <div className={'lanes' + (filter ? ' single' : '')}>
      {statuses.map(status => {
        const tasks = items.filter(task => task.status === status);
        return <div className={'lane lane-' + stateTones[status]} key={status}>
          <h3>{taskStatuses[status]} <span>{tasks.length}</span></h3>
          {!tasks.length && <p className="empty-lane">沒有{taskStatuses[status]}的任務</p>}
          {tasks.map(task => <details className="task-ticket" key={task.id}>
            <summary>
              <strong>{task.title}</strong>
              <span>{task.client_name || '—'}</span>
              {task.due_on && <div className="ticket-date">
                {task.due_on === today && status !== 'completed' ? <Badge tone="amber">今日到期</Badge> : <time dateTime={task.due_on}>{task.due_on.slice(5).replace('-', '/')} 到期</time>}
              </div>}
            </summary>
            <div className="ticket-detail">
              <strong>任務說明</strong>
              <p>{task.description || '尚無補充說明。'}</p>
            </div>
          </details>)}
        </div>;
      })}
    </div>
    <div className="panel-foot"><a href="#tasks">查看任務清單</a></div>
  </Section>;
}

export function Calendar({ revision, actions }) {
  const today = taipeiDate();
  const [month, setMonth] = useState(today.slice(0, 7));
  const [selected, setSelected] = useState(today);
  const [year, monthNumber] = month.split('-').map(Number);
  const data = useData('/calendar?' + query({ month }), revision);
  const events = data.data ?? [];
  function shift(amount) {
    const next = new Date(Date.UTC(year, monthNumber - 1 + amount, 1)).toISOString().slice(0, 7);
    setMonth(next);
    setSelected(next + '-01');
  }
  function onDay(date) {
    return events.filter(event => event.date <= date && (event.end_date ?? event.date) >= date);
  }
  return <Section title="公司行事曆" action={<div className="month-controls">
    <button className="button secondary compact" type="button" onClick={() => shift(-1)}>上月</button>
    <strong>{year} 年 {monthNumber} 月</strong>
    <button className="button secondary compact" type="button" onClick={() => shift(1)}>下月</button>
  </div>}>
    <div className="legend">{Object.entries(calendarCategories).map(([category, label]) => <span key={category}><i className={'marker ' + category} />{label}</span>)}</div>
    <StateNotice state={{ ...data, data: null }} />
    <div className="calendar-grid">
      {['一', '二', '三', '四', '五', '六', '日'].map(day => <span className="weekday" key={day}>{day}</span>)}
      {monthDates(year, monthNumber).map(date => {
        if (!date.startsWith(month)) return <span className="date-blank" key={date} />;
        const categories = [...new Set(onDay(date).map(event => event.category))];
        return <button key={date} type="button" className="date-cell" aria-pressed={date === selected}
          aria-current={date === today ? 'date' : undefined}
          aria-label={date + (categories.length ? '，' + categories.map(category => calendarCategories[category] ?? category).join('、') : '')}
          onClick={() => setSelected(date)}>
          <span>{Number(date.slice(-2))}</span>
          <span className="markers" aria-hidden="true">{categories.map(category => <i className={'marker ' + category} key={category} />)}</span>
        </button>;
      })}
    </div>
    <div className="event-detail" aria-live="polite">
      <h3>{Number(selected.slice(5, 7))} 月 {Number(selected.slice(-2))} 日</h3>
      {onDay(selected).length ? <ul>{onDay(selected).map((event, index) => <li key={event.id ?? index}>
        <Badge tone={event.category === 'holiday' ? 'amber' : event.category === 'meeting' ? 'purple' : 'blue'}>{calendarCategories[event.category] ?? event.category}</Badge>
        <span>{event.title}{event.start_at && event.end_at ? '　' + formatDateTime(event.start_at) + '–' + formatDateTime(event.end_at) : ''}</span>
      </li>)}</ul> : <p>這天沒有事件。</p>}
    </div>
    {actions}
  </Section>;
}

export function Dashboard({ user, revision, update }) {
  const tasks = useData('/tasks', revision);
  const canReview = user.roles.some(role => ['owner', 'manager', 'admin'].includes(role));
  const review = useData('/requests?scope=' + (canReview ? 'review' : 'mine'), revision);
  const pending = (review.data ?? []).filter(item => item.status === 'pending');
  return <>
    <PageTitle title="工作台"><time dateTime={taipeiDate()}>{new Intl.DateTimeFormat('zh-TW', { timeZone: 'Asia/Taipei', dateStyle: 'full' }).format(new Date())}</time></PageTitle>
    <AttendanceBanner revision={revision} update={update} />
    <StateNotice state={tasks} empty="目前沒有分派給你的任務。" />
    <TaskBoard items={(tasks.data ?? []).filter(task => task.assignee_id === user.id)} />
    <div className="dashboard-duo">
      <Calendar revision={revision} />
      <Section title={canReview ? '待審申請' : '我的申請'} action={<Badge tone="amber">{pending.length} 件待審</Badge>}>
        <StateNotice state={review} />
        {pending.map(item => <a className="list-row" key={item.id} href={canReview ? '#reviews' : '#requests'}>
          <div><strong>{item.employee_name ?? '員工 #' + item.employee_id}</strong><small>{formatDateTime(item.created_at)}</small></div>
          <Badge tone="blue">{kindLabels[item.kind] ?? item.kind}</Badge>
        </a>)}
        <div className="panel-foot"><a href={canReview ? '#reviews' : '#requests'}>查看申請</a></div>
      </Section>
    </div>
  </>;
}
