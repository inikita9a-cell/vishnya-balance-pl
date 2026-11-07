import { useEffect, useRef, useState } from 'react';
import styled from 'styled-components';
import { message } from '../../api/client';
import { getRuns, getConfigs, getDrilldown, filterSegments, getAppDifferences, getRawComparison } from '../../api/real';
import type { Segment, RawComparison, Run, Config } from '../../api/types';
import { datasetForRun } from '../../api/dataset';
import { theme } from '../../styles/Theme';
import { RegistryFilters, type RegistryStatus } from './components/RegistryFilters';
import { RegistryTable } from './components/RegistryTable';
import { DecisionXRay } from './components/DecisionXRay';
import type { Application, Decision } from './types';
import { PageHeading, ErrorBox, Empty, QuietButton, TextButton, Muted, NoticeSpacing } from '../../components/Ui';
import { AppSelect } from '../../components/AppSelect/AppSelect';
import { InfoNotice } from '../../components/InfoNotice/InfoNotice';
import { Surface } from '../../components/Surface';
import { deepLinkedApplication } from '../../api/deepLinks';

type RegistryProps = {
  runId: string;
  filters?: Record<string, unknown>;
  onRun: () => void;
  onRunChange: (id: string) => void;
  onClearFilters: () => void;
};
const toDecision = (value: string | null): Decision => value === 'APPROVE' ? 'approved' : value === 'REJECT' ? 'declined' : 'review';
const hasFilters = (filters: Record<string, unknown>) => Object.keys(filters).length > 0;

export function Registry({ runId, filters = {}, onRun, onRunChange, onClearFilters }: RegistryProps) {
  const [segments, setSegments] = useState<Segment[]>([]);
  const [applications, setApplications] = useState<Application[]>([]);
  const [total, setTotal] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [filter, setFilter] = useState<RegistryStatus>('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [detailError, setDetailError] = useState('');
  const [loadingChanges, setLoadingChanges] = useState(false);
  const [raw, setRaw] = useState<RawComparison | null>(null);
  const [rawLoading, setRawLoading] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const [runs, setRuns] = useState<Run[]>([]);
  const [configs, setConfigs] = useState<Config[]>([]);
  const rawSelectionRef = useRef('');
  rawSelectionRef.current = `${runId}:${selectedId ?? ''}`;

  // Keep the run's dataset context tied to actual run metadata and config snapshots.
  useEffect(() => {
    let live = true;
    Promise.all([getRuns(), getConfigs()])
      .then(([a, b]) => { if (live) { setRuns(a); setConfigs(b); } })
      .catch(() => { /* The registry remains usable if the optional switcher fails. */ });
    return () => { live = false; };
  }, [runId]);

  const serializedFilters = JSON.stringify(filters);
  useEffect(() => {
    let live = true;
    setLoading(true);
    setError('');
    setSegments([]);
    setApplications([]);
    setTotal(0);
    setSelectedId(null);
    setDetailError('');
    setRaw(null);
    setShowRaw(false);
    setSearchQuery('');
    setFilter('all');
    getDrilldown(runId).then(rows => {
      if (!live) return;
      const selected = filterSegments(rows, JSON.parse(serializedFilters) as Record<string, unknown>);
      const requestedFilters = JSON.parse(serializedFilters) as Record<string, unknown>;
      setSelectedId(deepLinkedApplication(requestedFilters, selected.map(item => item.APP_ID)));
      if (typeof requestedFilters.APP_ID === 'string' && !selected.some(item => item.APP_ID === requestedFilters.APP_ID)) {
        setDetailError(`Заявка ${requestedFilters.APP_ID} не найдена в реестре этого запуска.`);
      }
      setTotal(selected.length);
      setSegments(selected);
      setApplications(selected.map(item => ({
        id: item.APP_ID,
        date: '—', // No application date is exposed by /drilldown.
        status: toDecision(item.DECISION_AFTER),
        previousDecision: toDecision(item.DECISION_BEFORE),
        currentDecision: toDecision(item.DECISION_AFTER),
        changesCount: item.N_DIFFS,
        summary: item.DECISION_CHANGED
          ? 'Новая стратегия изменила итоговое решение по заявке.'
          : item.HAS_DIFF ? 'Параметры заявки изменились, но итоговое решение осталось прежним.'
            : 'Наблюдаемых изменений между версиями не обнаружено.',
        changes: []
      })));
    }).catch(e => { if (live) setError(message(e)); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [runId, serializedFilters]);

  useEffect(() => {
    if (!selectedId) return;
    let live = true;
    setLoadingChanges(true);
    setDetailError('');
    setRaw(null);
    getAppDifferences(runId, selectedId)
      .then(result => {
        if (live) setApplications(current => current.map(a => a.id !== selectedId ? a : {
          ...a, changes: result.map(d => ({
            name: d.PATH, before: d.VALUE_BEFORE, after: d.VALUE_AFTER, reason: d.CHANGE_TYPE
          }))
        }));
      }).catch(e => { if (live) setDetailError(message(e)); })
      .finally(() => { if (live) setLoadingChanges(false); });
    return () => { live = false; };
  }, [runId, selectedId]);

  const filtered = applications.filter(a => a.id.toLowerCase().includes(searchQuery.trim().toLowerCase()) && (filter === 'all' || a.status === filter));
  const selected = applications.find(a => a.id === selectedId) ?? null;
  const currentSegment = segments.find(s => s.APP_ID === selectedId);
  const activeRun = runs.find(r => r.id === runId);
  const dataset = activeRun ? datasetForRun(activeRun, configs) : null;
  const completed = runs.filter(r => r.status === 'done').sort((a, b) => b.created_at.localeCompare(a.created_at));
  const runOptions = completed.map(r => ({
    value: r.id,
    label: `${datasetForRun(r, configs).source === 'id' ? 'ID' : 'Датасет'}: ${datasetForRun(r, configs).label} · ${r.id}`
  }));
  if (runId && !runOptions.some(option => option.value === runId)) runOptions.unshift({ value: runId, label: `Текущий запуск · ${runId}` });

  async function toggleRaw() {
    if (showRaw) { setShowRaw(false); return; }
    setShowRaw(true);
    if (!selectedId || raw) return;
    setRawLoading(true);
    setDetailError('');
    const requestFor = `${runId}:${selectedId}`;
    try {
      const result = await getRawComparison(runId, selectedId);
      if (rawSelectionRef.current === requestFor) setRaw(result);
    } catch (e) {
      if (rawSelectionRef.current === requestFor) { setDetailError(message(e)); setShowRaw(false); }
    } finally {
      if (rawSelectionRef.current === requestFor) setRawLoading(false);
    }
  }

  return <>
    <PageHeading>
      <div><h1>Реестр заявок</h1><p>Детализация результатов · запуск <strong>{runId}</strong></p></div>
      <QuietButton type="button" onClick={onRun}>Параметры запуска</QuietButton>
    </PageHeading>
    <NoticeSpacing><InfoNotice title="Как работать с реестром" defaultOpen={false}>
      <p>В реестре показаны заявки, обработанные в запуске <strong>{runId}</strong>. Данные реестра и Decision X-Ray запрашиваются для указанного запуска; сравнение показывает исходную и новую стратегии. Информация загружается из артефактов указанного запуска FastAPI.</p>
      <p>Выберите заявку, чтобы раскрыть на всю ширину изменения значений. Поиск и выбор решения применяются к полному списку заявок, полученному одним запросом. Если вы пришли из отчёта, фильтр анализа уже применён — его можно сбросить. Переключатель датасета выбирает другой готовый запуск, а не пересчитывает текущий.</p>
    </InfoNotice></NoticeSpacing>
    <ContextBar>
      <ContextText><h2>Контекст анализа</h2><p>Выбранный запуск определяет данные реестра</p>
        <ContextMeta><span>ИД датасета: <strong>{dataset?.id ?? '—'}</strong></span>
          {dataset?.path && <span>Путь в пресете: <strong>{dataset.path}</strong></span>}
          <span>Запуск: <strong>{runId}</strong></span>
        </ContextMeta>
      </ContextText>
      <ContextSelect><label>Переключить запуск / датасет</label>
        <AppSelect ariaLabel="Выбрать завершённый запуск и датасет" value={runId} onChange={onRunChange} options={runOptions} disabled={!completed.length} />
      </ContextSelect>
    </ContextBar>
    {hasFilters(filters) && <AppliedFilter>
      <div><strong>Фильтр из отчёта</strong><span>{Object.entries(filters).map(([key, val]) => `${key}: ${String(val)}`).join(' · ')}</span></div>
      <TextButton type="button" onClick={onClearFilters}>Сбросить фильтр ×</TextButton>
    </AppliedFilter>}
    {error && <ErrorBox role="alert">{error}</ErrorBox>}
    <Layout>
      <RegistryFilters
        searchQuery={searchQuery}
        onSearchChange={v => { setSearchQuery(v); setSelectedId(null); }}
        status={filter}
        onStatusChange={v => { setFilter(v); setSelectedId(null); }}
      />
      {loading ? <Empty>Загружаем заявки…</Empty> : <>
        <RegistryTable applications={filtered} selectedId={selectedId} onSelect={id => {
          setSelectedId(old => old === id ? null : id);
          setShowRaw(false);
          setRaw(null);
        }} />
        {total > applications.length && <Muted>Показаны первые {applications.length} из {total} заявок. Обрабатывается полный список; для больших выборок нужна серверная пагинация.</Muted>}
        {detailError && <ErrorBox role="alert">{detailError}</ErrorBox>}
        {selected && <DecisionXRay application={selected} segment={currentSegment} loadingChanges={loadingChanges}
          onClose={() => setSelectedId(null)} onShowRaw={() => void toggleRaw()}
          showRaw={showRaw} raw={raw} rawLoading={rawLoading} />}
      </>}
    </Layout>
  </>;
}
const Layout = styled.section` display: grid; gap: 20px; width: 100%; min-width: 0; `;
const ContextBar = styled(Surface)`
  display: flex; justify-content: space-between; align-items: center; gap: 20px;
  position: relative; z-index: 15;
  padding: 23px 27px; margin-bottom: 20px;
  @media (max-width: 880px) { flex-direction: column; align-items: stretch; }
`;
const ContextText = styled.div`
  flex: 1; min-width: 0;
  h2 { font: 700 14px ${theme.fonts.interface}; }
  p { color: #777782; font: 400 12px ${theme.fonts.interface}; margin-top: 8px; }
`;
const ContextMeta = styled.div`
  display: flex; flex-wrap: wrap; gap: 10px 20px; margin-top: 16px;
  span { font: 400 11px ${theme.fonts.interface}; color: #777782; overflow-wrap: anywhere; }
  strong { color: ${theme.colors.darkBgColor}; font-weight: 600; }
`;
const ContextSelect = styled.div`
  width: min(100%, 410px); flex: 0 1 410px; min-width: 0;
  label { display: block; font: 500 12px ${theme.fonts.interface}; color: #777782; margin-bottom: 9px; }
  @media (max-width: 880px) { flex: 1 1 auto; }
`;
const AppliedFilter = styled.div`
  display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center;
  gap: 12px; margin-bottom: 18px; padding: 14px 20px;
  background: #fff; border: 1px solid #eeeef1; border-radius: 15px;
  div { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; min-width: 0; }
  strong { font: 600 12px ${theme.fonts.interface}; }
  span { font: 400 11px ${theme.fonts.interface}; color: #898993; overflow-wrap: anywhere; }
`;
