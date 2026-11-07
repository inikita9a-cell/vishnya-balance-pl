import { useEffect, useState } from 'react';
import { message } from '../../api/client';
import { getChecks, rerunChecks } from '../../api/real';
import type { Check } from '../../api/types';
import { PageHeading, Panel, DataTable, ErrorBox, Empty, QuietButton, Tag, NoticeSpacing, TableScroller } from '../../components/Ui';
import { InfoNotice } from '../../components/InfoNotice/InfoNotice';
type Props = { runId: string };
export function Checks({ runId }: Props) {
  const [items, setItems] = useState<Check[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let live = true;
    setLoading(true); setError(''); setItems([]);
    getChecks(runId)
      .then(r => { if (live) setItems(r); })
      .catch(e => { if (live) setError(message(e)); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [runId]);
  async function rerun() {
    setBusy(true); setError('');
    try { await rerunChecks(runId); setNotice('Перезапуск проверок запрошен. Обновите таблицу, когда обработка завершится.'); }
    catch (e) { setError(message(e)); }
    finally { setBusy(false); }
  }
  async function reload() {
    setError(''); setBusy(true);
    try { setItems(await getChecks(runId)); setNotice('Список проверок обновлён.'); }
    catch (e) { setError(message(e)); }
    finally { setBusy(false); }
  }
  return <>
    <PageHeading><div><h1>Проверки качества</h1><p>Результаты контрольных проверок · запуск <strong>{runId}</strong></p></div>
      <div style={{ display: 'flex', gap: 12 }}><QuietButton type="button" disabled={busy} onClick={() => void reload()}>Обновить</QuietButton><QuietButton type="button" disabled={busy} onClick={() => void rerun()}>{busy ? 'Отправляем…' : 'Повторить проверки'}</QuietButton></div>
    </PageHeading>
    <NoticeSpacing><InfoNotice title="Как читать проверки качества" defaultOpen={false}>
      <p>Здесь отображаются проверки для выбранного запуска <strong>{runId}</strong>: результат, количество затронутых заявок, метрика и степень уверенности. При смене запуска меняется и список проверок.</p>
      <p>Кнопка «Повторить проверки» обращается к API выбранного запуска и обновляет таблицу. Она запускает фоновый пересчёт; ответ API с полем ok=true подтверждает только приём команды. Обновление таблицы может занять время.</p>
    </InfoNotice></NoticeSpacing>
    {error && <ErrorBox role="alert">{error}</ErrorBox>}
    {notice && <p role="status" style={{ margin: '0 0 14px', color: '#278259', fontSize: 12 }}>{notice}</p>}
    <Panel style={{ padding: 0, overflow: 'hidden' }}>
      <TableScroller><DataTable style={{ minWidth: 660 }}>
        <thead><tr><th>Проверка</th><th>Результат</th><th>Заявки</th><th>Метрика</th><th>Уверенность</th></tr></thead>
        <tbody>{items.map(check => <tr key={check.id}>
          <td><strong>{check.LABEL}</strong></td>
          <td><Tag $tone={check.RESULT === 'PASS' ? 'good' : 'bad'}>{check.RESULT === 'PASS' ? 'Пройдена' : check.RESULT === 'FAIL' ? 'Не пройдена' : 'Ошибка'}</Tag></td>
          <td>{check.CNT} / {check.TOTAL}</td>
          <td>{check.METRIC === null ? '—' : `${Math.round(check.METRIC * 100)}%`}</td>
          <td>{check.CONFIDENCE}</td>
        </tr>)}</tbody>
      </DataTable></TableScroller>
      {!items.length && <Empty>{loading ? 'Загрузка проверок…' : 'Проверки не найдены'}</Empty>}
    </Panel>
  </>;
}
