import { lazy, Suspense, useEffect, useState } from 'react';
import styled from 'styled-components';
import { getSankey, type SankeyData } from '../../api/sankey';
import { message } from '../../api/client';
import { Empty, ErrorBox, Muted, TextButton } from '../../components/Ui';

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
    <Muted>Решение до → решение после → переход основания. Толщина потока — число уникальных заявок. Нажмите на поток или узел, чтобы открыть заявки.</Muted>
    {state.error && <ErrorBox role="alert">{state.error} <TextButton type="button" onClick={() => setAttempt(value => value + 1)}>Повторить</TextButton></ErrorBox>}
    {!state.data && !state.error && <Empty role="status">Загружаем потоки решений…</Empty>}
    {state.data && (state.data.links.length ? <>
      <Suspense fallback={<Empty role="status">Загружаем диаграмму…</Empty>}>
        <SankeyChart data={state.data} onSelect={onRegistry} />
      </Suspense>
      <details><summary>Потоки списком — открыть заявки с клавиатуры</summary>
        <FlowList>{state.data.links.map(link => <li key={`${link.source}:${link.target}`}>
          <TextButton type="button" onClick={() => onRegistry(link.filters)}>
            {state.data!.nodes.find(node => node.name === link.source)?.label} → {state.data!.nodes.find(node => node.name === link.target)?.label}: {link.value.toLocaleString('ru-RU')} заявок
          </TextButton>
        </li>)}</FlowList>
      </details>
    </> : <Empty>Переходов решений для этого запуска нет</Empty>)}
  </Container>;
}

const Container = styled.div`margin-top: 18px; min-width: 0; details { margin-top: 12px; } summary { cursor: pointer; }`;
const FlowList = styled.ul`display: grid; gap: 10px; max-height: 300px; overflow: auto; padding: 16px; button { text-align: left; overflow-wrap: anywhere; }`;
