import { useEffect, useRef, useState } from 'react';
import { message } from '../../api/client';
import { getChecks, rerunChecks, getCheckRowApps } from '../../api/real';
import type { Check, CheckAppsPage } from '../../api/types';
import { PageHeading, Panel, DataTable, ErrorBox, Empty, QuietButton, Tag, NoticeSpacing, TableScroller } from '../../components/Ui';
import { checkOutcome, checkMetricLabel, confidenceLabel } from './checkPresentation';
import { CheckApplicationLinks } from './CheckApplicationLinks';
import { InfoNotice } from '../../components/InfoNotice/InfoNotice';

type Props = { runId: string; onApplication: (appId: string) => void };
const LIMIT = 100;

export function Checks({ runId, onApplication }: Props) {
  const [items, setItems] = useState<Check[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Check | null>(null);
  const [appsPage, setAppsPage] = useState<CheckAppsPage | null>(null);
  const [appsLoading, setAppsLoading] = useState(false);
  const [appsError, setAppsError] = useState('');
  // A row request is tied to this run and selection; stale responses are ignored.
  const appsRequest = useRef(0);
  const appsPanel = useRef<HTMLElement>(null);

  useEffect(() => {
    if (selected) appsPanel.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [selected]);

  useEffect(() => {
    let live = true;
    appsRequest.current++;
    setLoading(true); setError(''); setItems([]);
    setSelected(null); setAppsPage(null);
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
      appsRequest.current++;
      setSelected(null); setAppsPage(null);
      setNotice('Перезапуск проверок запрошен. Обновите таблицу после завершения расчёта.');
    } catch (e) { setError(message(e)); }
    finally { setBusy(false); }
  }
  async function reload() {
    setError(''); setBusy(true);
    try {
      setItems(await getChecks(runId));
      appsRequest.current++;
      setSelected(null); setAppsPage(null);
      setNotice('Список проверок обновлён.');
    } catch (e) { setError(message(e)); }
    finally { setBusy(false); }
  }
  async function openRow(check: Check, offset = 0) {
    const request = ++appsRequest.current;
    setSelected(check); setAppsPage(null); setAppsError('');
    setAppsLoading(true);
    try {
      // Always send the server-provided ROW_ID, not a CHECK_ID/ARGUMENT pair.
      const result = await getCheckRowApps(runId, check.CHECK_ID, check.ROW_ID, LIMIT, offset);
      if (request !== appsRequest.current) return;
      setAppsPage(result);
      if (result.total !== check.CNT) {
        setAppsError(`Получено ${result.total} заявок; в результате проверки указано ${check.CNT}.`);
      }
    } catch (e) { if (request === appsRequest.current) setAppsError(message(e)); }
    finally { if (request === appsRequest.current) setAppsLoading(false); }
  }
  async function changePage(offset: number) {
    if (!selected) return;
    const request = ++appsRequest.current;
    setAppsLoading(true); setAppsError('');
    try {
      const result = await getCheckRowApps(runId, selected.CHECK_ID, selected.ROW_ID, LIMIT, offset);
      if (request === appsRequest.current) setAppsPage(result);
    } catch (e) { if (request === appsRequest.current) setAppsError(message(e)); }
    finally { if (request === appsRequest.current) setAppsLoading(false); }
  }
  return <>
    <PageHeading><div><h1>Проверки изменений</h1><p>Сигналы бизнес-проверок · запуск <strong>{runId}</strong></p></div>
      <div style={{ display: 'flex', gap: 12 }}>
        <QuietButton type="button" disabled={busy} onClick={() => void reload()}>Обновить</QuietButton>
        <QuietButton type="button" disabled={busy} onClick={() => void rerun()}>{busy ? 'Отправляем…' : 'Повторить проверки'}</QuietButton>
      </div></PageHeading>
    <p style={{ marginBottom: 16, lineHeight: 1.6 }}>Сигнал означает обнаруженное изменение или превышение порога. Он требует оценки аналитика и не означает сбой расчёта.</p>
    <NoticeSpacing><InfoNotice title="Как читать результаты проверок" defaultOpen={false}>
      <p>Нажмите на число заявок конкретной строки, чтобы увидеть её полный список, а затем открыть полную карточку заявки.</p>
      <p>«Есть сигнал» означает, что бизнес-проверка нашла изменение или превышение заданного порога. Это результат анализа, а не ошибка выполнения и не автоматический вывод о качестве новой стратегии. «Ошибка выполнения» означает, что результат получить не удалось.</p>
      <p>Нажмите на заявку в списке — откроется её полная карточка в реестре: решения, основания, изменения BEFORE/AFTER и исходные данные.</p>
    </InfoNotice></NoticeSpacing>
    {error && <ErrorBox role="alert">{error}</ErrorBox>}
    {notice && <p role="status" style={{ margin: '0 0 14px', fontSize: 12 }}>{notice}</p>}
    <Panel style={{ padding: 0, overflow: 'hidden' }}>
      <TableScroller><DataTable style={{ minWidth: 860 }}>
        <thead><tr><th>Проверка</th><th>Срез</th><th>Аргумент</th><th>Вывод проверки</th><th>Заявки</th><th>Метрика</th><th>Уверенность</th></tr></thead>
        <tbody>{items.map(check => <tr key={check.ROW_ID || check.id}>
          <td><strong>{check.LABEL}</strong></td>
          <td>{check.SOURCE}</td><td>{check.ARGUMENT || '—'}</td>
          <td><Tag $tone={checkOutcome(check).tone} title={checkOutcome(check).detail}>{checkOutcome(check).label}</Tag></td>
          <td>{check.CNT > 0 && check.ROW_ID ?
            <button type="button" onClick={() => void openRow(check)} aria-label={`Показать ${check.CNT} заявок строки ${check.ROW_ID}`}
              style={{ background: 'none', border: 'none', textDecoration: 'underline', cursor: 'pointer', color: 'inherit', fontWeight: 700 }}>
              {check.CNT}</button> : check.CNT} / {check.TOTAL}</td>
          <td title={checkMetricLabel(check)}>{typeof check.METRIC === 'number' ? `${Math.round(check.METRIC * 10000) / 100}%` : check.METRIC == null ? '—' : String(check.METRIC)}</td>
          <td>{confidenceLabel(check.CONFIDENCE)}</td>
        </tr>)}</tbody>
      </DataTable></TableScroller>
      {!items.length && <Empty>{loading ? 'Загрузка проверок…' : 'Проверки не найдены'}</Empty>}
    </Panel>
    {selected && <Panel ref={appsPanel}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
        <div><h2>Заявки конкретной строки</h2>
          <p>{selected.LABEL} · {selected.SOURCE} · {selected.ARGUMENT || '—'}</p></div>
        <QuietButton type="button" onClick={() => { appsRequest.current++; setSelected(null); setAppsPage(null); }}>Закрыть</QuietButton>
      </div>
      {appsError && <ErrorBox role="alert">{appsError}</ErrorBox>}
      {appsLoading && <p>Загрузка списка заявок…</p>}
      {appsPage && <>
        <p>Всего заявок: <strong>{appsPage.total}</strong>. Показаны {appsPage.items.length ? appsPage.offset + 1 : 0}–{appsPage.offset + appsPage.items.length}.</p>
        <CheckApplicationLinks appIds={appsPage.items} onApplication={onApplication} disabled={appsLoading} />
        <div style={{ display: 'flex', gap: 12 }}>
          <QuietButton type="button" disabled={appsLoading || appsPage.offset === 0} onClick={() => void changePage(Math.max(0, appsPage.offset - LIMIT))}>Назад</QuietButton>
          <QuietButton type="button" disabled={appsLoading || !appsPage.has_more} onClick={() => void changePage(appsPage.offset + LIMIT)}>Далее</QuietButton>
        </div>
      </>}
    </Panel>}
  </>;
}
