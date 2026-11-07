import styled from 'styled-components';
import { theme } from '../../../styles/Theme';
import { causeLabel } from '../../../api/format';
import type { RawComparison, Segment } from '../../../api/types';
import { Muted, QuietButton, TextButton } from '../../../components/Ui';
import type { Application } from '../types';

type Props = {
  application: Application;
  segment?: Segment;
  loadingChanges: boolean;
  onClose: () => void;
  onShowRaw: () => void;
  showRaw: boolean;
  raw: RawComparison | null;
  rawLoading: boolean;
};

const decisions = { approved: 'Одобрено', declined: 'Отказ', review: 'Не определено' };
const fieldLabels: Record<string, string> = {
  'decisionResult.decision': 'Решение стратегии',
  'decisionResult.reason': 'Основание решения',
  'characteristics.score': 'Скоринговый балл'
};
const changeLabels: Record<string, string> = {
  VALUE_CHANGED: 'Изменилось значение', ATTRIBUTE_NEW: 'Добавлено', ATTRIBUTE_LOST: 'Удалено', TYPE_CHANGED: 'Изменился тип'
};

export function DecisionXRay({ application, segment, loadingChanges, onClose, onShowRaw, showRaw, raw, rawLoading }: Props) {
  const changed = application.previousDecision !== application.currentDecision;
  return <XRay aria-label={`Детали заявки ${application.id}`}>
    <Header>
      <div>
        <Eyebrow>DECISION X-RAY / ЗАЯВКА</Eyebrow>
        <h2>{application.id}</h2>
        <Subtitle>Сопоставление результата двух стратегий</Subtitle>
      </div>
      <Close type="button" aria-label="Закрыть заявку" onClick={onClose}>×</Close>
    </Header>
    <Content>
      <Overview>
        <h3>Результат сравнения</h3>
        <DecisionLine>
          <span>Исходная стратегия</span>
          <DecisionValue $approved={application.previousDecision === 'approved'}>{decisions[application.previousDecision]}</DecisionValue>
        </DecisionLine>
        <DecisionLine>
          <span>Новая стратегия</span>
          <DecisionValue $approved={application.currentDecision === 'approved'}>{decisions[application.currentDecision]}</DecisionValue>
        </DecisionLine>
        <Result $changed={changed}><ResultDot />{changed ? 'Решение изменилось' : 'Решение сохранено'}</Result>
        <SectionLabel>Интерпретация</SectionLabel>
        <Description>{application.summary}</Description>
        {segment && <Meta>
          <MetaRow><span>Причина изменений</span><strong>{causeLabel(segment.CAUSE)}</strong></MetaRow>
          <MetaRow><span>Расхождений в данных</span><strong>{segment.N_DIFFS}</strong></MetaRow>
          <MetaRow><span>Контроль качества</span><strong>{segment.QUALITY_ISSUE === null ? 'Нет данных в drilldown' : segment.QUALITY_ISSUE ? 'Есть замечания' : 'Без замечаний'}</strong></MetaRow>
        </Meta>}
      </Overview>
      <Changes>
        <ChangesHeader><div><h3>Точки расхождения</h3><p>Какие поля поменялись между версиями заявки</p></div><Muted>{segment?.N_DIFFS ?? application.changes.length} полей</Muted></ChangesHeader>
        {loadingChanges ? <Description>Загружаем изменённые поля…</Description> : application.changes.length > 0 ?
          <ChangeList>{application.changes.map((change, i) => <ChangeRow key={`${change.name}-${i}`}>
            <ChangeTitle title={change.name}>{fieldLabels[change.name] ?? change.name}<code>{change.name}</code></ChangeTitle>
            <ValueCompare>
              <ValueColumn><span>До</span><ValueText>{change.before || '—'}</ValueText></ValueColumn>
              <ChangeArrow aria-hidden="true">→</ChangeArrow>
              <ValueColumn><span>После</span><ValueText>{change.after || '—'}</ValueText></ValueColumn>
            </ValueCompare>
            <ChangeType>{changeLabels[change.reason] ?? change.reason}</ChangeType>
          </ChangeRow>)}</ChangeList>
        : <Description>Для заявки нет изменённых полей.</Description>}
        <RawFooter>
          <TextButton type="button" onClick={onShowRaw}>{showRaw ? 'Скрыть исходные данные ↑' : 'Показать исходные JSON ↓'}</TextButton>
        </RawFooter>
      </Changes>
    </Content>
    {showRaw && <RawComparisonBlock>
      {rawLoading ? <Muted>Загрузка исходных данных…</Muted> : raw ? <RawColumns>
        <div><SectionLabel>Версия до</SectionLabel><pre>{raw.before}</pre></div>
        <div><SectionLabel>Версия после</SectionLabel><pre>{raw.after}</pre></div>
      </RawColumns> : <Muted>Исходные данные недоступны.</Muted>}
      <QuietButton type="button" onClick={onShowRaw}>Свернуть JSON</QuietButton>
    </RawComparisonBlock>}
  </XRay>;
}

const XRay = styled.section`
  background: #fff; border: 1px solid #ebebee; border-radius: 20px;
  padding: 27px 30px; min-width: 0;
  @media (max-width: 640px) { padding: 20px; }
`;
const Header = styled.div`
  display: flex; justify-content: space-between; align-items: flex-start;
  gap: 16px; padding-bottom: 22px; border-bottom: 1px solid #efeff1;
  h2 { margin-top: 9px; font: 650 19px ${theme.fonts.primary}; }
`;
const Eyebrow = styled.span` color: ${theme.colors.accent}; font: 600 10px ${theme.fonts.interface}; letter-spacing: .085em; `;
const Subtitle = styled.p` color: #92929b; font: 400 12px ${theme.fonts.interface}; margin-top: 7px; `;
const Close = styled.button`
  border: 1px solid #ebebee; width: 34px; height: 34px; flex: 0 0 auto;
  border-radius: 50%; color: #64646e; background: #fff; font-size: 22px; cursor: pointer;
  &:hover { color: ${theme.colors.accent}; border-color: ${theme.colors.accent}; }
  &:focus-visible { outline: 2px solid ${theme.colors.accent}; outline-offset: 2px; }
`;
const Content = styled.div`
  display: grid; grid-template-columns: minmax(245px, .9fr) minmax(0, 1.4fr); gap: clamp(26px, 4vw, 70px); padding-top: 26px;
  @media (max-width: 850px) { grid-template-columns: 1fr; }
`;
const Overview = styled.div`
  min-width: 0;
  h3 { font: 700 14px ${theme.fonts.interface}; margin-bottom: 20px; }
`;
const DecisionLine = styled.div`
  display: flex; justify-content: space-between; align-items: center; gap: 12px;
  padding: 13px 0; border-bottom: 1px solid #f0f0f2;
  span { font: 400 12px ${theme.fonts.interface}; color: #84848e; }
`;
const DecisionValue = styled.strong<{ $approved: boolean }>` color: ${p => p.$approved ? '#278259' : '#bd584b'}; font: 600 13px ${theme.fonts.interface}; `;
const Result = styled.div<{ $changed: boolean }>`
  display: flex; align-items: center; gap: 8px; color: ${p => p.$changed ? theme.colors.accent : '#278259'};
  font: 600 12px ${theme.fonts.interface}; margin: 20px 0 27px;
`;
const ResultDot = styled.span` width: 7px; height: 7px; flex-shrink: 0; background: currentColor; border-radius: 50%; `;
const SectionLabel = styled.h4` font: 600 12px ${theme.fonts.interface}; margin-bottom: 9px; `;
const Description = styled.p` font: 400 12px/1.7 ${theme.fonts.interface}; color: #777781; `;
const Meta = styled.div` display: grid; gap: 13px; margin-top: 22px; padding-top: 17px; border-top: 1px solid #efeff1; `;
const MetaRow = styled.div`
  display: flex; justify-content: space-between; gap: 12px; font: 400 12px ${theme.fonts.interface};
  span { color: #92929b; } strong { text-align: right; font-weight: 600; }
`;
const Changes = styled.div` min-width: 0; `;
const ChangesHeader = styled.div`
  display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 12px; margin-bottom: 18px;
  h3 { font: 700 14px ${theme.fonts.interface}; }
  p { font: 400 12px ${theme.fonts.interface}; color: #92929b; margin-top: 6px; }
`;
const ChangeList = styled.div` display: grid; `;
const ChangeRow = styled.div` padding: 15px 0 19px; border-top: 1px solid #efeff1; min-width: 0; `;
const ChangeTitle = styled.div`
  font: 600 12px ${theme.fonts.interface}; overflow-wrap: anywhere;
  code { display: block; margin-top: 4px; color: #9999a3; font: 400 11px ${theme.fonts.interface}; }
`;
const ValueCompare = styled.div`
  display: grid; grid-template-columns: minmax(0,1fr) 18px minmax(0,1fr);
  align-items: center; gap: 14px; margin-top: 14px;
`;
const ValueColumn = styled.div`
  min-width: 0; display: grid; gap: 7px;
  & > span { font: 400 11px ${theme.fonts.interface}; color: #9999a3; }
`;
const ValueText = styled.div`
  padding: 10px 12px; background: #f7f7f9; border: 1px solid #f0f0f2;
  border-radius: 10px; overflow-wrap: anywhere; font: 500 12px ${theme.fonts.interface};
`;
const ChangeArrow = styled.span` color: ${theme.colors.accent}; font-size: 16px; `;
const ChangeType = styled.div` color: #9999a3; font: 400 11px ${theme.fonts.interface}; margin-top: 8px; `;
const RawFooter = styled.div` margin-top: 15px; `;
const RawComparisonBlock = styled.div`
  margin-top: 25px; padding-top: 22px; border-top: 1px solid #efeff1;
  & > button { margin-top: 14px; }
`;
const RawColumns = styled.div`
  display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 16px;
  pre { font: 400 11px/1.6 monospace; overflow-x: auto; white-space: pre-wrap; overflow-wrap: anywhere; background: #f7f7f9; border-radius: 12px; padding: 16px; margin-top: 10px; }
  @media (max-width: 700px) { grid-template-columns: 1fr; }
`;
