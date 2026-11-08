import { useEffect, useRef, useState } from 'react';
import { message } from '../../api/client';
import { getChecks, rerunChecks, getCheckRowApps, getAppDifferences } from '../../api/real';
import type { Check, CheckAppsPage, Difference } from '../../api/types';
import { PageHeading, Panel, DataTable, ErrorBox, Empty, QuietButton, Tag, NoticeSpacing, TableScroller } from '../../components/Ui';
import { InfoNotice } from '../../components/InfoNotice/InfoNotice';

type Props = { runId: string };
const LIMIT = 100;

export function Checks({ runId }: Props) {
  const [items, setItems] = useState<Check[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Check | null>(null);
  const [appsPage, setAppsPage] = useState<CheckAppsPage | null>(null);
  const [appsLoading, setAppsLoading] = useState(false);
  const [appsError, setAppsError] = useState('');
  const [appSelected, setAppSelected] = useState<string | null>(null);
  const [differences, setDifferences] = useState<Difference[]>([]);
  const [differencesLoading, setDifferencesLoading] = useState(false);
  // Ignore stale HTTP responses after a different row, page or application is clicked.
  const appsRequest = useRef(0);
  const differencesRequest = useRef(0);

  useEffect(() => {
    let live = true;
    appsRequest.current++; differencesRequest.current++;
    setLoading(true); setError(''); setItems([]);
    setSelected(null); setAppsPage(null); setAppSelected(null);
    getChecks(runId)
      .then(rows => { if (live) setItems(rows); })
      .catch(e => { if (live) setError(message(e)); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [runId]);

  async function rerun() {
    setBusy(true); setError('');
    try {
      await rerunChecks(runId);
      appsRequest.current++; differencesRequest.current++;
      setSelected(null); setAppsPage(null); setAppSelected(null);
      setNotice('Перезапуск проверок запрошен. Обновите таблицу после завершения расчёта.');
    } catch (e) { setError(message(e)); }
    finally { setBusy(false); }
  }
  async function reload() {
    setError(''); setBusy(true);
    try {
      setItems(await getChecks(runId));
      appsRequest.current++; differencesRequest.current++;
      setSelected(null); setAppsPage(null); setAppSelected(null);
      setNotice('Список проверок обновлён.');
    } catch (e) { setError(message(e)); }
    finally { setBusy(false); }
  }
  async function openRow(check: Check, offset = 0) {
    const request = ++appsRequest.current;
    differencesRequest.current++;
    setSelected(check); setAppsPage(null); setAppsError('');
    setAppSelected(null); setDifferences([]); setAppsLoading(true);
    try {
      // Always send the server-provided ROW_ID, not a CHECK_ID/ARGUMENT pair.
      const result = await getCheckRowApps(runId, check.CHECK_ID, check.ROW_ID, LIMIT, offset);
      if (request !== appsRequest.current) return;
      setAppsPage(result);
      if (result.total !== check.CNT) {
        setAppsError(`Число заявок (${result.total}) отличается от CNT (${check.CNT}).`);
      }
    } catch (e) { if (request === appsRequest.current) setAppsError(message(e)); }
    finally { if (request === appsRequest.current) setAppsLoading(false); }
  }
  async function changePage(offset: number) {
    if (!selected) return;
    const request = ++appsRequest.current;
    differencesRequest.current++;
    setAppsLoading(true); setAppsError(''); setAppSelected(null); setDifferences([]);
    try {
      const result = await getCheckRowApps(runId, selected.CHECK_ID, selected.ROW_ID, LIMIT, offset);
      if (request === appsRequest.current) setAppsPage(result);
    } catch (e) { if (request === appsRequest.current) setAppsError(message(e)); }
    finally { if (request === appsRequest.current) setAppsLoading(false); }
  }
  async function openApp(appId: string) {
    const request = ++differencesRequest.current;
    setAppSelected(appId); setDifferences([]); setDifferencesLoading(true);
    try {
      const result = await getAppDifferences(runId, appId);
      if (request === differencesRequest.current) setDifferences(result);
    } catch (e) { if (request === differencesRequest.current) setAppsError(message(e)); }
    finally { if (request === differencesRequest.current) setDifferencesLoading(false); }
  }
  return <>
    <PageHeading><div><h1>Проверки качества</h1><p>Результаты контрольных проверок · запуск <strong>{runId}</strong></p></div>
      <div style={{ display: 'flex', gap: 12 }}>
        <QuietButton type="button" disabled={busy} onClick={() => void reload()}>Обновить</QuietButton>
        <QuietButton type="button" disabled={busy} onClick={() => void rerun()}>{busy ? 'Отправляем…' : 'Повторить проверки'}</QuietButton>
      </div></PageHeading>
    <NoticeSpacing><InfoNotice title="Как читать проверки качества" defaultOpen={false}>
      <p>Нажмите на число заявок конкретной строки, чтобы увидеть её полный список, а затем — изменённые атрибуты BEFORE/AFTER.</p>
      <p>Если проверка вернула только примеры без фильтров для восстановления списка, приложение покажет ошибку, а не подменит полный список примерами.</p>
    </InfoNotice></NoticeSpacing>
    {error && <ErrorBox role="alert">{error}</ErrorBox>}
    {notice && <p role="status" style={{ margin: '0 0 14px', fontSize: 12 }}>{notice}</p>}
    <Panel style={{ padding: 0, overflow: 'hidden' }}>
      <TableScroller><DataTable style={{ minWidth: 860 }}>
        <thead><tr><th>Проверка</th><th>Срез</th><th>Аргумент</th><th>Результат</th><th>Заявки</th><th>Метрика</th><th>Уверенность</th></tr></thead>
        <tbody>{items.map(check => <tr key={check.ROW_ID || check.id}>
          <td><strong>{check.LABEL}</strong></td>
          <td>{check.SOURCE}</td><td>{check.ARGUMENT || '—'}</td>
          <td><Tag $tone={check.RESULT === 'PASS' ? 'good' : 'bad'}>{check.RESULT === 'PASS' ? 'Пройдена' : check.RESULT === 'FAIL' ? 'Не пройдена' : 'Ошибка'}</Tag></td>
          <td>{check.CNT > 0 && check.ROW_ID ?
            <button type="button" onClick={() => void openRow(check)} aria-label={`Показать ${check.CNT} заявок строки ${check.ROW_ID}`}
              style={{ background: 'none', border: 'none', textDecoration: 'underline', cursor: 'pointer', color: 'inherit', fontWeight: 700 }}>
              {check.CNT}</button> : check.CNT} / {check.TOTAL}</td>
          <td>{typeof check.METRIC === 'number' ? `${Math.round(check.METRIC * 10000) / 100}%` : check.METRIC == null ? '—' : String(check.METRIC)}</td>
          <td>{check.CONFIDENCE}</td>
        </tr>)}</tbody>
      </DataTable></TableScroller>
      {!items.length && <Empty>{loading ? 'Загрузка проверок…' : 'Проверки не найдены'}</Empty>}
    </Panel>
    {selected && <Panel>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
        <div><h2>Заявки конкретной строки</h2>
          <p>{selected.LABEL} · {selected.SOURCE} · {selected.ARGUMENT || '—'}</p></div>
        <QuietButton type="button" onClick={() => { appsRequest.current++; differencesRequest.current++; setSelected(null); setAppsPage(null); setAppSelected(null); }}>Закрыть</QuietButton>
      </div>
      {appsError && <ErrorBox role="alert">{appsError}</ErrorBox>}
      {appsLoading && <p>Загрузка списка заявок…</p>}
      {appsPage && <>
        <p>Всего заявок: <strong>{appsPage.total}</strong> из CNT={selected.CNT}. Показаны {appsPage.items.length ? appsPage.offset + 1 : 0}–{appsPage.offset + appsPage.items.length}.</p>
        <ul style={{ display: 'flex', gap: 8, flexWrap: 'wrap', padding: 0, listStyle: 'none' }}>
          {appsPage.items.map(id => <li key={id}>
            <button type="button" onClick={() => void openApp(id)}>{id}</button>
          </li>)}
        </ul>
        <div style={{ display: 'flex', gap: 12 }}>
          <QuietButton type="button" disabled={appsLoading || appsPage.offset === 0} onClick={() => void changePage(Math.max(0, appsPage.offset - LIMIT))}>Назад</QuietButton>
          <QuietButton type="button" disabled={appsLoading || !appsPage.has_more} onClick={() => void changePage(appsPage.offset + LIMIT)}>Далее</QuietButton>
        </div>
      </>}
      {appSelected && <section aria-label={`Карточка заявки ${appSelected}`}>
        <h3>Заявка {appSelected}: изменённые атрибуты</h3>
        {differencesLoading ? <p>Загрузка изменений…</p> : <TableScroller><DataTable>
          <thead><tr><th>Атрибут</th><th>BEFORE</th><th>AFTER</th><th>Тип изменения</th></tr></thead>
          <tbody>{differences.map((d, i) => <tr key={`${d.PATH}-${i}`} style={{ fontWeight: d.PATH === selected.ARGUMENT ? 700 : undefined }}>
            <td>{d.PATH}</td><td>{d.VALUE_BEFORE}</td><td>{d.VALUE_AFTER}</td><td>{d.CHANGE_TYPE}</td></tr>)}
          </tbody>
        </DataTable></TableScroller>}
        {!differencesLoading && !differences.length && <p>В витрине нет отличающихся атрибутов этой заявки.</p>}
      </section>}
    </Panel>}
  </>;
}
