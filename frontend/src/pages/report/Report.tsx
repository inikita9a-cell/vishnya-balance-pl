import { useEffect, useState } from 'react';
import styled from 'styled-components';
import { API_BASE, message } from '../../api/client';
import { getSummary, getBlocks } from '../../api/real';
import type { Summary, Block } from '../../api/types';
import { causeLabel, decision } from '../../api/format';
import { theme } from '../../styles/Theme';
import { Panel, PageHeading, ErrorBox, Empty, DataTable, Muted, QuietButton, TextButton, TableScroller, NoticeSpacing } from '../../components/Ui';
import { InfoNotice } from '../../components/InfoNotice/InfoNotice';
import { ReportTree } from './ReportTree';
import { ReportSankey } from './ReportSankey';

type ReportProps = {
  runId: string;
  onRegistry: (filters?: Record<string, unknown>) => void;
};

const percentage = (number: number) => `${Math.round(Math.max(0, Math.min(1, number)) * 100)}%`;
const number = (value: number) => value.toLocaleString('ru-RU');
const share = (part: number, total: number) => total > 0 ? Math.min(100, Math.max(0, 100 * part / total)) : 0;

export function Report({ runId, onRegistry }: ReportProps) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [error, setError] = useState('');
  const [matrixMode, setMatrixMode] = useState<'decisions' | 'reasons'>('decisions');
  const [changesMode, setChangesMode] = useState<'sankey' | 'tree'>('sankey');

  useEffect(() => {
    let live = true;
    setSummary(null);
    setBlocks([]);
    setError('');
    Promise.all([
      getSummary(runId),
      getBlocks(runId)
    ]).then(([s, b]) => {
      if (live) { setSummary(s); setBlocks(b); }
    }).catch(e => { if (live) setError(message(e)); });
    return () => { live = false; };
  }, [runId]);

  const total = summary?.total_apps ?? 0;
  const changedDecision = summary?.apps_decision_changed ?? 0;
  const changedSameDecision = summary?.apps_diff_same_decision ?? 0;
  const unchanged = Math.max(0, total - (summary?.apps_with_diff ?? 0));
  const approvalDelta = summary ? ((summary.AR_after ?? 0) - (summary.AR_before ?? 0)) * 100 : 0;

  return <>
    <PageHeading>
      <div>
        <h1>Сравнительный отчёт</h1>
        <p>Результаты сравнения стратегий · запуск <strong>{runId}</strong></p>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
        <QuietButton type="button" onClick={() => onRegistry()}>Открыть реестр заявок →</QuietButton>
        <QuietButton type="button" onClick={() => window.open(`${API_BASE}/api/runs/${encodeURIComponent(runId)}/report.html`, '_blank', 'noopener,noreferrer')}>HTML-отчёт ↗</QuietButton>
      </div>
    </PageHeading>
    <NoticeSpacing>
      <InfoNotice title="Как читать отчёт" defaultOpen={false}>
        <p>Отчёт формируется для выбранного запуска <strong>{runId}</strong>. При открытии другого запуска показатели и таблицы заново запрашиваются по его ID. Информация загружается из результатов конкретного запуска FastAPI.</p>
        <p>Нажмите на категорию изменений, переход решения или причину — откроется реестр заявок с соответствующим фильтром. Фильтрация по блокам пока не поддерживается REST API. Доли вычислены из данных API, а не из демонстрационных значений интерфейса.</p>
      </InfoNotice>
    </NoticeSpacing>
    {error && <ErrorBox role="alert">{error}</ErrorBox>}
    {!summary && !error && <Empty>Загрузка результатов…</Empty>}
    {summary && <ReportGrid>
      {summary.verdict && <Panel><SectionHeader><div><h2>Аналитический вердикт</h2><p>{summary.verdict.disclaimer}</p></div><strong>{({ REVIEW_REQUIRED: 'Требуется проверка', INCOMPLETE: 'Неполные данные', CHECKS_PENDING: 'Проверки не завершены', NO_CHANGES_OBSERVED: 'Изменений не обнаружено' } as Record<string,string>)[summary.verdict.status] ?? summary.verdict.status}</strong></SectionHeader></Panel>}
      <Overview>
        <SectionHeader>
          <div><h2>Картина изменений</h2><p>Как результаты новой стратегии отличаются от исходной</p></div>
          <Muted>{number(total)} заявок в анализе</Muted>
        </SectionHeader>
        <OverviewContent>
          <ChartArea>
            <MatrixMode aria-label="Диаграмма картины изменений">
              <MatrixButton type="button" $active={changesMode === 'sankey'} aria-pressed={changesMode === 'sankey'} onClick={() => setChangesMode('sankey')}>Потоки решений</MatrixButton>
              <MatrixButton type="button" $active={changesMode === 'tree'} aria-pressed={changesMode === 'tree'} onClick={() => setChangesMode('tree')}>Дерево атрибутов</MatrixButton>
            </MatrixMode>
            {changesMode === 'sankey' ? <ReportSankey key={runId} runId={runId} onRegistry={onRegistry} /> : <ReportTree runId={runId} />}
          </ChartArea>
          <Legend>
            <LegendRow type="button" onClick={() => onRegistry({ DECISION_CHANGED: true })}>
              <LegendName><LegendDot $color={theme.colors.accent} />Смена решения</LegendName>
              <LegendValues><b>{number(changedDecision)}</b><span>{percentage(share(changedDecision, total) / 100)}</span><Arrow aria-hidden="true">↗</Arrow></LegendValues>
            </LegendRow>
            <LegendRow type="button" onClick={() => onRegistry({ HAS_DIFF: true, DECISION_CHANGED: false })}>
              <LegendName><LegendDot $color="#efbba7" />Изменились параметры, но не решение</LegendName>
              <LegendValues><b>{number(changedSameDecision)}</b><span>{percentage(share(changedSameDecision, total) / 100)}</span><Arrow aria-hidden="true">↗</Arrow></LegendValues>
            </LegendRow>
            <LegendRow type="button" onClick={() => onRegistry({ HAS_DIFF: false })}>
              <LegendName><LegendDot $color="#e7e7eb" />Без изменений</LegendName>
              <LegendValues><b>{number(unchanged)}</b><span>{percentage(share(unchanged, total) / 100)}</span><Arrow aria-hidden="true">↗</Arrow></LegendValues>
            </LegendRow>
            <LegendFooter>
              <span>С расхождениями: <strong>{number(summary.apps_with_diff)}</strong></span>
              <TextButton type="button" onClick={() => onRegistry({ HAS_DIFF: true })}>Смотреть заявки →</TextButton>
            </LegendFooter>
          </Legend>
        </OverviewContent>
      </Overview>

      <SecondaryGrid>
        <Panel>
          <SectionHeader><div><h2>Доля одобрений</h2><p>Изменение уровня одобрения</p></div></SectionHeader>
          <ApprovalRows>
            <ApprovalRow>
              <MetricLabel><span>Исходная стратегия</span><strong>{summary.AR_before === null ? '—' : percentage(summary.AR_before)}</strong></MetricLabel>
              <Track><Fill $width={(summary.AR_before ?? 0) * 100} $old /></Track>
            </ApprovalRow>
            <ApprovalRow>
              <MetricLabel><span>Новая стратегия</span><strong>{summary.AR_after === null ? '—' : percentage(summary.AR_after)}</strong></MetricLabel>
              <Track><Fill $width={(summary.AR_after ?? 0) * 100} /></Track>
            </ApprovalRow>
          </ApprovalRows>
          {summary.AR_before !== null && summary.AR_after !== null && <Impact $positive={approvalDelta >= 0}>
            <strong>{approvalDelta > 0 ? '+' : ''}{approvalDelta.toFixed(1)} п. п.</strong>
            <span>изменение доли одобрений</span>
          </Impact>}
        </Panel>
        <Panel>
          <SectionHeader><div><h2>Причины расхождений</h2><p>Распределение по интерпретации изменений</p></div></SectionHeader>
          <CauseList>
            {summary.causes.length ? summary.causes.filter(c => c.count > 0 && c.cause !== 'NONE').map(c => <CauseRow key={c.cause} type="button" onClick={() => onRegistry({ CAUSE: c.cause })}>
              <CauseLabel><span>{causeLabel(c.cause)}</span><strong>{number(c.count)}</strong></CauseLabel>
              <Track><Fill $width={share(c.count, total)} /></Track>
            </CauseRow>) : <Muted>Нет сведений о причинах</Muted>}
            {!summary.causes.some(c => c.count > 0 && c.cause !== 'NONE') && <Muted>Нет расхождений по причинам</Muted>}
          </CauseList>
        </Panel>
      </SecondaryGrid>

      <TablePanel>
        <MatrixHeader>
          <div><h2>Как изменились решения</h2><p>Сопоставьте итоговые решения и основания, затем откройте нужные заявки</p></div>
          <MatrixMode aria-label="Режим матрицы">
            <MatrixButton type="button" $active={matrixMode === 'decisions'} aria-pressed={matrixMode === 'decisions'} onClick={() => setMatrixMode('decisions')}>Решения</MatrixButton>
            <MatrixButton type="button" $active={matrixMode === 'reasons'} aria-pressed={matrixMode === 'reasons'} onClick={() => setMatrixMode('reasons')}>Основания</MatrixButton>
          </MatrixMode>
        </MatrixHeader>
        <TableScroller><DataTable>
          <thead><tr><th>{matrixMode === 'decisions' ? 'Решение до' : 'Основание до'}</th><th>{matrixMode === 'decisions' ? 'Решение после' : 'Основание после'}</th><th>Заявок</th><th>Доля</th><th></th></tr></thead>
          <tbody>{(matrixMode === 'decisions' ? summary.decision_matrix : summary.reason_matrix).map((cell, i) => <tr key={`${matrixMode}-${cell.before}-${cell.after}-${i}`}>
            <td>{matrixMode === 'decisions' ? decision(cell.before) : (cell.before || 'Не указано')}</td>
            <td>{matrixMode === 'decisions' ? decision(cell.after) : (cell.after || 'Не указано')}</td>
            <td><strong>{number(cell.count)}</strong></td>
            <td>{percentage(share(cell.count, total) / 100)}</td>
            <td><TextButton type="button" onClick={() => onRegistry(cell.filters)}>Открыть →</TextButton></td>
          </tr>)}</tbody>
        </DataTable></TableScroller>
      </TablePanel>

      <TablePanel>
        <SectionHeader><div><h2>Где произошли изменения</h2><p>Доля заявок с отличиями по блокам данных; одна заявка может входить в несколько блоков</p></div>
        </SectionHeader>
        <TableScroller><DataTable>
          <thead><tr><th>Блок данных</th><th>С изменениями</th><th>Доля от заявок</th><th>Изменённых строк</th><th></th></tr></thead>
          <tbody>{blocks.map((block, i) => <tr key={`${block.BLOCK}-${i}`}>
            <td><strong>{block.BLOCK}</strong></td>
            <td>{number(block.APPS_CHANGED)} из {number(block.APPS_TOTAL)}</td>
            <td><BarCell><Track><Fill $width={block.SHARE * 100} /></Track><span>{percentage(block.SHARE)}</span></BarCell></td>
            <td>{number(block.ROWS_CHANGED)}</td>
            <td><Muted title="Фильтр по блокам пока отсутствует в API">Нет фильтра API</Muted></td>
          </tr>)}</tbody>
        </DataTable></TableScroller>
        {blocks.length === 0 && <Empty>Данных по блокам пока нет</Empty>}
      </TablePanel>
      {summary.quality_issues > 0 && <Footnote>Замечаний по качеству данных: <strong>{number(summary.quality_issues)}</strong>. Подробности доступны на вкладке «Проверки».</Footnote>}
      {summary.llm !== null && summary.llm !== undefined && <Panel>
        <SectionHeader><div><h2>Интерпретация анализа</h2></div></SectionHeader>
        <Explanation>{typeof summary.llm === 'string' ? summary.llm : JSON.stringify(summary.llm, null, 2)}</Explanation>
      </Panel>}
    </ReportGrid>}
  </>;
}

const ReportGrid = styled.div` display: grid; gap: 20px; `;
const Overview = styled(Panel)` padding: 28px; `;
const SectionHeader = styled.div`
  display: flex; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; gap: 12px;
  margin-bottom: 23px;
  h2 { font: 700 15px ${theme.fonts.interface}; color: ${theme.colors.darkBgColor}; }
  p { margin-top: 6px; color: #888892; font: 400 12px ${theme.fonts.interface}; line-height: 1.55; }
`;
const OverviewContent = styled.div`
  display: grid; gap: 22px; min-width: 0;
`;
const ChartArea = styled.div`min-width: 0; width: 100%;`;
const Legend = styled.div` width: 100%; display: grid; `;
const LegendRow = styled.button`
  display: flex; align-items: center; justify-content: space-between; gap: 20px;
  width: 100%; padding: 17px 4px; text-align: left; background: transparent;
  border: 0; border-bottom: 1px solid #efeff1; cursor: pointer;
  &:hover { color: ${theme.colors.accent}; }
  &:focus-visible { outline: 2px solid ${theme.colors.accent}; outline-offset: 1px; }
`;
const LegendName = styled.span` display: flex; align-items: center; gap: 11px; font: 500 13px ${theme.fonts.interface}; line-height: 1.5; `;
const LegendDot = styled.span<{ $color: string }>` width: 10px; height: 10px; border-radius: 50%; background: ${p => p.$color}; flex-shrink: 0; `;
const LegendValues = styled.span`
  display: flex; align-items: center; gap: 16px; flex-shrink: 0;
  b { font: 700 15px ${theme.fonts.interface}; }
  span { font: 400 12px ${theme.fonts.interface}; color: #9696a1; min-width: 37px; text-align: right; }
`;
const Arrow = styled.span` font-size: 13px; color: #a1a1aa; `;
const LegendFooter = styled.div`
  display: flex; justify-content: space-between; flex-wrap: wrap; align-items: center;
  gap: 10px; padding: 18px 4px 0; font: 400 12px ${theme.fonts.interface}; color: #858590;
  strong { color: ${theme.colors.darkBgColor}; }
`;
const SecondaryGrid = styled.div`
  display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 20px;
  & > section { padding: 27px; }
  @media (max-width: 840px) { grid-template-columns: 1fr; }
`;
const ApprovalRows = styled.div` display: grid; gap: 23px; padding: 4px 0; `;
const ApprovalRow = styled.div` display: grid; gap: 9px; `;
const MetricLabel = styled.div`
  display: flex; justify-content: space-between; align-items: center; gap: 12px;
  font: 500 12px ${theme.fonts.interface}; color: #777782;
  strong { color: ${theme.colors.darkBgColor}; font: 700 18px ${theme.fonts.interface}; }
`;
const Track = styled.div` height: 9px; border-radius: 99px; background: #f0f0f2; overflow: hidden; min-width: 80px; `;
const Fill = styled.div<{ $width: number; $old?: boolean }>`
  height: 100%; width: ${p => Math.max(0, Math.min(100, p.$width))}%;
  background: ${p => p.$old ? '#b7b7c1' : theme.colors.accent}; border-radius: inherit;
  transition: width .3s ease;
`;
const Impact = styled.div<{ $positive: boolean }>`
  display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap;
  margin-top: 25px; padding-top: 17px; border-top: 1px solid #efeff1;
  strong { font: 700 20px ${theme.fonts.interface}; color: ${p => p.$positive ? '#278259' : '#ba5844'}; }
  span { color: #898993; font: 400 12px ${theme.fonts.interface}; }
`;
const CauseList = styled.div` display: grid; gap: 13px; `;
const CauseRow = styled.button`
  display: grid; width: 100%; gap: 9px; text-align: left;
  border: 0; padding: 3px 0; background: transparent; cursor: pointer;
  &:hover span { color: ${theme.colors.accent}; }
  &:focus-visible { outline: 2px solid ${theme.colors.accent}; outline-offset: 3px; }
`;
const CauseLabel = styled.span`
  display: flex; justify-content: space-between; align-items: center; gap: 10px;
  span { font: 500 12px ${theme.fonts.interface}; }
  strong { font: 600 13px ${theme.fonts.interface}; }
`;
const TablePanel = styled(Panel)` padding: 0; overflow: hidden; ${SectionHeader} { padding: 24px 27px 0; } table { min-width: 650px; } `;
const BarCell = styled.div` display: flex; align-items: center; gap: 12px; ${Track} { flex: 1; max-width: 145px; } span { white-space: nowrap; } `;
const Footnote = styled.div` color: #777782; font: 500 12px ${theme.fonts.interface}; padding: 4px 0; `;
const Explanation = styled.pre` white-space: pre-wrap; word-break: break-word; font: 400 12px/1.7 ${theme.fonts.interface}; color: #555561; `;

const MatrixHeader = styled(SectionHeader)`
  align-items: center;
`;
const MatrixMode = styled.div`
  display: inline-flex; flex-wrap: wrap; gap: 3px; background: #f1f1f4; padding: 4px;
  border-radius: 12px;
`;
const MatrixButton = styled.button<{ $active: boolean }>`
  border: 0; border-radius: 9px; padding: 9px 13px;
  font: 500 12px ${theme.fonts.interface}; cursor: pointer;
  background: ${p => p.$active ? '#fff' : 'transparent'};
  color: ${p => p.$active ? theme.colors.darkBgColor : '#8c8c95'};
  box-shadow: ${p => p.$active ? '0 2px 7px rgba(24,24,36,.06)' : 'none'};
  &:hover { color: ${theme.colors.accent}; }
  &:focus-visible { outline: 2px solid ${theme.colors.accent}; outline-offset: 2px; }
`;
