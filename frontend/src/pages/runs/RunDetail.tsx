import { useEffect, useState } from 'react';
import styled from 'styled-components';
import { getRun } from '../../api/real';
import { message } from '../../api/client';
import type { Run } from '../../api/types';
import { dateTime, isRunActive, isRunDone, stageLabel, status } from '../../api/format';
import { PageHeading, Panel, DataTable, TableScroller, TextButton, QuietButton, Empty, ErrorBox, Muted } from '../../components/Ui';

type Props = {
  id: string; onBack: () => void; onReport: () => void; onPivot: () => void; onRegistry: () => void;
  onChecks: () => void; onStep: (key: string) => void;
};

export function RunDetail({ id, onBack, onReport, onPivot, onRegistry, onChecks, onStep }: Props) {
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setRun(null);
    setError('');
    async function load() {
      try {
        const result = await getRun(id);
        if (!live) return;
        setRun(result);
        setError('');
        if (isRunActive(result.status)) timer = setTimeout(() => void load(), 3000);
      } catch (e) { if (live) setError(message(e)); }
    }
    void load();
    return () => { live = false; clearTimeout(timer); };
  }, [id, refresh]);
  return <>
    <PageHeading><div><h1>Запуск {id}</h1><p>{run ? status(run.status) : 'Параметры и этапы обработки'}</p></div>
      <Actions><QuietButton type="button" onClick={onBack}>История запусков</QuietButton><QuietButton type="button" onClick={() => setRefresh(value => value + 1)}>Обновить</QuietButton></Actions>
    </PageHeading>
    {error && <ErrorBox role="alert">{error}</ErrorBox>}
    {!run && !error && <Empty role="status">Загружаем запуск…</Empty>}
    {run && <>
      <Panel>
        <p>Создан: {dateTime(run.created_at)} · Завершён: {dateTime(run.finished_at)}</p>
        <p>Инициатор: {run.started_by} · Конфигурация: {run.config_id || '—'}</p>
        {run.progress !== null && <p>Прогресс: {run.progress}%</p>}
        {run.error && <ErrorBox role="alert">{run.error}</ErrorBox>}
        <Actions>
          <QuietButton type="button" disabled={!isRunDone(run.status)} onClick={onReport}>Сравнительный отчёт</QuietButton>
          <QuietButton type="button" disabled={!isRunDone(run.status)} onClick={onPivot}>Свободная сводная</QuietButton>
          <QuietButton type="button" disabled={!isRunDone(run.status)} onClick={onRegistry}>Реестр заявок</QuietButton>
          <QuietButton type="button" disabled={!isRunDone(run.status)} onClick={onChecks}>Проверки</QuietButton>
        </Actions>
        {!isRunDone(run.status) && <Muted>Результаты доступны после успешного завершения запуска.</Muted>}
      </Panel>
      <Stages><TableScroller><DataTable>
        <thead><tr><th>Этап</th><th>Статус</th><th>Прогресс</th><th>Длительность, мс</th><th></th></tr></thead>
        <tbody>{run.stages.map(stage => <tr key={stage.step}><td>{stageLabel(stage.step)}</td><td>{status(stage.status)}</td><td>{stage.progress}%</td><td>{stage.duration_ms ?? '—'}</td>
          <td><TextButton type="button" onClick={() => onStep(stage.step)}>Подробнее →</TextButton></td></tr>)}</tbody>
      </DataTable></TableScroller>{!run.stages.length && <Empty>Этапы пока не зарегистрированы</Empty>}</Stages>
    </>}
  </>;
}

const Actions = styled.div`display: flex; flex-wrap: wrap; gap: 12px; margin: 12px 0;`;
const Stages = styled(Panel)`margin-top: 20px;`;
