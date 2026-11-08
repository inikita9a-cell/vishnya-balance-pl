import { lazy, Suspense, useEffect, useState } from 'react';
import styled from 'styled-components';
import { getSankey, type SankeyData } from '../../api/sankey';
import { message } from '../../api/client';
import { Empty, ErrorBox, Muted, TextButton } from '../../components/Ui';
import { flowLabel } from './sankeyLabels';

const SankeyChart = lazy(() => import('./SankeyChart'));

export function ReportSankey({ runId, onRegistry }: {
  runId: string; onRegistry: (filters?: Record<string, unknown>) => void;
}) {
  const [state, setState] = useState<{ data?: SankeyData; error?: string }>({});
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    setState({});
    getSankey(runId).then(data => { if (live) setState({ data }); })
      .catch(error => { if (live) setState({ error: message(error) }); });
    return () => { live = false; };
  }, [runId, attempt]);
  return <Container>
    <ChartIntro><Muted>Толщина потока — количество заявок. Нажмите на поток, чтобы открыть их.</Muted>
      <Guide><summary>Как читать диаграмму</summary><p>Читаем слева направо: исходное решение, новое решение и основание. Поток между одинаковыми решениями означает, что решение сохранилось. «Сохранено» справа — основание не изменилось, «Новое» — появилось, «Не указано» — отсутствует. Полное описание и число заявок — при наведении.</p></Guide>
    </ChartIntro>
    {state.error && <ErrorBox role="alert">{state.error} <TextButton type="button" onClick={() => setAttempt(value => value + 1)}>Повторить</TextButton></ErrorBox>}
    {!state.data && !state.error && <Empty role="status">Загружаем потоки решений…</Empty>}
    {state.data && (state.data.links.length ? <>
      <Suspense fallback={<Empty role="status">Загружаем диаграмму…</Empty>}>
        <SankeyChart data={state.data} onSelect={onRegistry} />
      </Suspense>
      <details><summary>Все потоки и количество заявок</summary>
        <FlowList>{state.data.links.map(link => <li key={`${link.source}:${link.target}`}>
          <TextButton type="button" onClick={() => onRegistry(link.filters)}>
            {flowLabel(state.data!, link)} {link.value.toLocaleString('ru-RU')} заявок
          </TextButton>
        </li>)}</FlowList>
      </details>
    </> : <Empty>Переходов решений для этого запуска нет</Empty>)}
  </Container>;
}

const Container = styled.div`margin-top: 18px; min-width: 0; details { margin-top: 12px; } summary { cursor: pointer; }`;
const FlowList = styled.ul`display: grid; gap: 10px; max-height: 300px; overflow: auto; padding: 16px; button { text-align: left; overflow-wrap: anywhere; }`;
const ChartIntro = styled.div`display: flex; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; gap: 10px 24px;`;
const Guide = styled.details`font-size: 12px; color: #777782; max-width: 600px; summary { cursor: pointer; white-space: nowrap; } p { padding: 12px 0 0; line-height: 1.7; }`;
