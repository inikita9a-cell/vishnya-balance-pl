import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import styled from 'styled-components';
import { message } from '../../api/client';
import { getExplorerApps, getExplorerFields, queryExplorer } from '../../api/real';
import type { ExplorerField, ExplorerFilters, ExplorerQueryRow, ExplorerScalar } from '../../api/explorer.types';
import { DataTable, Empty, ErrorBox, Muted, QuietButton, TableScroller, TextButton } from '../../components/Ui';
import { theme } from '../../styles/Theme';
import { buildPathTree } from './treeModel';
const PathTreeChart = lazy(() => import('./PathTreeChart'));

const PAGE_SIZE = 20;
const count = (value: number) => value.toLocaleString('ru-RU');
const valueLabel = (value: ExplorerScalar | undefined) => value == null ? 'Отсутствует' : value === '' ? 'Пустая строка' : String(value);
const changeLabel = (value: ExplorerScalar | undefined) => ({
  VALUE_CHANGED: 'Изменено', ATTRIBUTE_NEW: 'Добавлено', ATTRIBUTE_LOST: 'Удалено', SAME: 'Без изменений',
}[String(value)] ?? String(value ?? '—'));

// Each effect owns its result. Cleanup prevents old requests from updating a new selection/page.
function useRequest<T>(request: () => Promise<T>) {
  const [state, setState] = useState<{ data?: T; error?: string; loading: boolean }>({ loading: true });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    setState({ loading: true });
    request().then(data => { if (live) setState({ data, loading: false }); })
      .catch(error => { if (live) setState({ error: message(error), loading: false }); });
    return () => { live = false; };
  }, [request, attempt]);
  return { ...state, retry: () => setAttempt(value => value + 1) };
}

function RequestError({ error, retry }: { error: string; retry: () => void }) {
  return <ErrorBox role="alert">{error} <TextButton type="button" onClick={retry}>Повторить</TextButton></ErrorBox>;
}

function Pager({ offset, total, onChange }: { offset: number; total: number; onChange: (offset: number) => void }) {
  return <Toolbar aria-label="Страницы результатов">
    <Muted>{total ? `${offset + 1}–${Math.min(offset + PAGE_SIZE, total)} из ${count(total)}` : 'Нет результатов'}</Muted>
    <QuietButton type="button" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - PAGE_SIZE))}>Назад</QuietButton>
    <QuietButton type="button" disabled={offset + PAGE_SIZE >= total} onClick={() => onChange(offset + PAGE_SIZE)}>Далее</QuietButton>
  </Toolbar>;
}

export function ReportTree({ runId }: { runId: string }) {
  // Remount all explorer state when the run changes, including pending requests.
  return <TreeForRun key={runId} runId={runId} />;
}

function TreeForRun({ runId }: { runId: string }) {
  const request = useCallback(() => getExplorerFields(runId), [runId]);
  const { data, loading, error, retry } = useRequest(request);
  const [selected, setSelected] = useState<ExplorerField | null>(null);
  const tree = useMemo(() => buildPathTree(data?.fields ?? []), [data]);
  return <Container>
    <Hint>Счётчики относятся только к точному атрибуту. Промежуточные ветки служат для навигации.</Hint>
    {loading && <Empty role="status">Загружаем атрибуты…</Empty>}
    {error && <RequestError error={error} retry={retry} />}
    {data && (tree.length ? <ExplorerLayout>
      <div><Suspense fallback={<Empty>Загружаем диаграмму…</Empty>}><PathTreeChart roots={tree} onSelect={setSelected} /></Suspense></div>
      <SidePanel aria-label="Миграции выбранного атрибута">
        {selected ? <Migrations key={selected.path} runId={runId} field={selected} /> : <Empty>Выберите атрибут для просмотра изменений BEFORE → AFTER</Empty>}
      </SidePanel>
    </ExplorerLayout> : <Empty>Каталог атрибутов пуст</Empty>)}
  </Container>;
}
function Migrations({ runId, field }: { runId: string; field: ExplorerField }) {
  const [offset, setOffset] = useState(0);
  // A new keyed page unmounts old requests and drill-down when paging.
  return <Detail>
    <h3>{field.path}</h3>
    <Hint>Изменения: {count(field.changedAppsCount)} уникальных заявок. Всего с атрибутом: {count(field.appsCount)}.</Hint>
    {field.hasArrayInstances && <Hint>Все экземпляры массива включены. Одна заявка может иметь несколько вхождений и миграций.</Hint>}
    <MigrationPage key={offset} runId={runId} path={field.path} offset={offset} onPage={setOffset} />
  </Detail>;
}

function MigrationPage({ runId, path, offset, onPage }: { runId: string; path: string; offset: number; onPage: (offset: number) => void }) {
  const request = useCallback(() => queryExplorer(runId, {
    groupBy: ['VALUE_BEFORE', 'VALUE_AFTER', 'CHANGE_TYPE'],
    filters: { PATH: path, DIFF_FLAG: 1 }, includeUnchanged: false, limit: PAGE_SIZE, offset,
  }), [runId, path, offset]);
  const { data, loading, error, retry } = useRequest(request);
  const [selected, setSelected] = useState<ExplorerQueryRow | null>(null);
  return <>
    {loading && <Empty role="status">Загружаем миграции…</Empty>}
    {error && <RequestError error={error} retry={retry} />}
    {data && <>
      {data.rows.length ? <TableScroller><MigrationTable>
        <thead><tr><th>BEFORE</th><th>AFTER</th><th>Изменение</th><th>Заявок</th><th>Вхождений</th></tr></thead>
        <tbody>{data.rows.map((row, index) => <tr key={index}>
          <td>{valueLabel(row.values.VALUE_BEFORE)}</td><td>{valueLabel(row.values.VALUE_AFTER)}</td>
          <td>{changeLabel(row.values.CHANGE_TYPE)}</td>
          <td><TextButton type="button" aria-label={`Открыть заявки: ${count(row.appsCount)}`} onClick={() => setSelected(row)}>{count(row.appsCount)} →</TextButton></td>
          <td>{count(row.occurrencesCount)}</td>
        </tr>)}</tbody>
      </MigrationTable></TableScroller> : <Empty>Миграций на этой странице нет</Empty>}
      <Pager offset={offset} total={data.totalGroups} onChange={onPage} />
      <Hint>Заявки между миграциями могут пересекаться. Значения «Отсутствует», «NULL» и «Пустая строка» различаются.</Hint>
    </>}
    {selected && <Applications key={JSON.stringify(selected.drilldownFilters)} runId={runId} filters={selected.drilldownFilters} onClose={() => setSelected(null)} />}
  </>;
}

function Applications({ runId, filters, onClose }: { runId: string; filters: ExplorerFilters; onClose: () => void }) {
  const [offset, setOffset] = useState(0);
  return <Detail>
    <Toolbar><h3>Заявки выбранной миграции</h3><TextButton type="button" onClick={onClose}>Закрыть ×</TextButton></Toolbar>
    <AppsPage key={offset} runId={runId} filters={filters} offset={offset} onPage={setOffset} />
  </Detail>;
}

function AppsPage({ runId, filters, offset, onPage }: { runId: string; filters: ExplorerFilters; offset: number; onPage: (offset: number) => void }) {
  // Keep the exact server filters, including any opaque ARRAY_KEY, unchanged.
  const request = useCallback(() => getExplorerApps(runId, { filters, limit: PAGE_SIZE, offset }), [runId, filters, offset]);
  const { data, loading, error, retry } = useRequest(request);
  return <>
    {loading && <Empty role="status">Загружаем заявки…</Empty>}
    {error && <RequestError error={error} retry={retry} />}
    {data && <>
      {data.items.length ? <TableScroller><MigrationTable>
        <thead><tr><th>Заявка</th><th>Решение до</th><th>Решение после</th><th>Изменений в заявке</th><th>Полнота сравнения</th></tr></thead>
        <tbody>{data.items.map(item => <tr key={item.APP_ID}><td>{item.APP_ID}</td><td>{item.DECISION_BEFORE ?? '—'}</td><td>{item.DECISION_AFTER ?? '—'}</td><td>{count(item.N_DIFFS)}</td><td>{item.COMPARISON_COMPLETE ? 'Полное' : 'Неполное'}</td></tr>)}</tbody>
      </MigrationTable></TableScroller> : <Empty>Заявок не найдено</Empty>}
      <Pager offset={offset} total={data.total} onChange={onPage} />
    </>}
  </>;
}

const Container = styled.div`padding: 0 24px 24px; font: 400 13px ${theme.fonts.interface}; color: ${theme.colors.darkBgColor};`;
const Hint = styled.p`font: 400 12px/1.6 ${theme.fonts.interface}; color: #777782; margin: 12px 0;`;
const Detail = styled.section`margin-top: 22px; padding-top: 18px; border-top: 1px solid ${theme.colors.surface}; h3 { font: 600 14px ${theme.fonts.interface}; overflow-wrap: anywhere; }`;
const Toolbar = styled.div`display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin: 14px 0;`;
const MigrationTable = styled(DataTable)`td { overflow-wrap: anywhere; max-width: 300px; white-space: pre-wrap; }`;

const ExplorerLayout = styled.div`display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr); gap: 24px; > div, > section { min-width: 0; } @media (max-width: 1100px) { grid-template-columns: 1fr; }`;
const SidePanel = styled.section`padding: 0 16px; background: #fafafb; border: 1px solid ${theme.colors.surface}; border-radius: 12px; max-height: 900px; overflow: auto;`;
