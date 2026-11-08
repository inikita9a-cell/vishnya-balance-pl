import { useEffect, useState } from 'react';
import { getRuns } from '../../api/real';
import { message } from '../../api/client';
import type { Run } from '../../api/types';
import { dateTime, status } from '../../api/format';
import { PageHeading, Panel, DataTable, TableScroller, TextButton, QuietButton, Empty, ErrorBox } from '../../components/Ui';

export function Runs({ onOpen }: { onOpen: (id: string) => void }) {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let live = true;
    setRuns(null);
    setError('');
    getRuns().then(rows => {
      if (live) setRuns([...rows].sort((a, b) => b.created_at.localeCompare(a.created_at)));
    }).catch(e => { if (live) setError(message(e)); });
    return () => { live = false; };
  }, [refresh]);
  return <>
    <PageHeading><div><h1>История запусков</h1><p>Результаты обработки и сравнения стратегий</p></div>
      <QuietButton type="button" onClick={() => setRefresh(value => value + 1)}>Обновить</QuietButton>
    </PageHeading>
    {error && <ErrorBox role="alert">{error}</ErrorBox>}
    {!runs && !error && <Empty role="status">Загружаем запуски…</Empty>}
    {runs && <Panel>{runs.length ? <TableScroller><DataTable>
      <thead><tr><th>Запуск</th><th>Создан</th><th>Статус</th><th>Инициатор</th><th></th></tr></thead>
      <tbody>{runs.map(run => <tr key={run.id}><td>{run.id}</td><td>{dateTime(run.created_at)}</td><td>{status(run.status)}</td><td>{run.started_by}</td>
        <td><TextButton type="button" onClick={() => onOpen(run.id)}>Открыть →</TextButton></td></tr>)}</tbody>
    </DataTable></TableScroller> : <Empty>Запусков пока нет. Создайте запуск в разделе конфигурации.</Empty>}</Panel>}
  </>;
}
