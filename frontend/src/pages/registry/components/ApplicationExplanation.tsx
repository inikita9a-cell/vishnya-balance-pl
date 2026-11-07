import { useEffect, useRef, useState } from 'react';
import styled from 'styled-components';
import { message } from '../../../api/client';
import { getApplicationExplanation, observedValue, type ApplicationExplanation as Explanation } from '../../../api/explanation';
import { ErrorBox, Muted, QuietButton, TextButton } from '../../../components/Ui';

type Props = { runId: string; appId: string; onShowRaw: () => void; showRaw: boolean };
const labels: Record<string, string> = { VALUE_CHANGED: 'Значение изменилось', ATTRIBUTE_NEW: 'Атрибут добавлен', ATTRIBUTE_LOST: 'Атрибут исчез' };
const issueLabels: Record<string, string> = {
  DECISION_WITHOUT_REASON: 'Решение есть, причина не указана', REQUIRED_FIELD_MISSING: 'Нет обязательного поля',
  APP_MISSING_BEFORE: 'Отсутствует заявка BEFORE', APP_MISSING_AFTER: 'Отсутствует заявка AFTER',
  PARSE_ERROR: 'Не удалось прочитать ответ', DUPLICATE_KEY: 'Неоднозначный ключ массива',
  ARRAY_KEY_MISSING: 'Нет ключа элемента массива', ARRAY_KEY_FALLBACK: 'Массив сопоставлен по позиции',
  DEPTH_TRUNCATED: 'Достигнут предел вложенности',
};

export function ApplicationExplanation({ runId, appId, onShowRaw, showRaw }: Props) {
  const [data, setData] = useState<Explanation | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [more, setMore] = useState(false);
  const selection = useRef('');
  selection.current = `${runId}:${appId}`;
  useEffect(() => {
    let live = true;
    setData(null); setError(''); setLoading(true); setMore(false);
    getApplicationExplanation(runId, appId)
      .then(result => { if (live) setData(result); })
      .catch(e => { if (live) setError(message(e)); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [runId, appId]);

  async function loadMore() {
    if (!data || more) return;
    const requested = `${runId}:${appId}`;
    setMore(true); setError('');
    try {
      const result = await getApplicationExplanation(runId, appId, data.changes.rows.length);
      if (selection.current === requested) setData(current => current ? {
        ...current, changes: { ...current.changes, rows: [...current.changes.rows, ...result.changes.rows] }
      } : current);
    } catch (e) { if (selection.current === requested) setError(message(e)); }
    finally { if (selection.current === requested) setMore(false); }
  }
  return <Section>
    {loading && <Muted>Загружаем объяснение изменений…</Muted>}
    {error && <ErrorBox role="alert">{error}</ErrorBox>}
    {data && <>
      <Status $warning={!data.comparison.complete || !data.decision.comparable} role="status">
        <h3>{data.interpretation.headline}</h3><p>{data.interpretation.detail}</p>
      </Status>
      <Cards>
        <div><h3>Решение</h3><p>{data.decision.before ?? 'Нет данных'} → {data.decision.after ?? 'Нет данных'}</p></div>
        <div><h3>Причина решения</h3><p>{data.reason.before ?? 'Не указана'} → {data.reason.after ?? 'Не указана'}</p></div>
      </Cards>
      <p><strong>Наблюдаемые изменения:</strong> {data.interpretation.source_label}</p>
      <Muted>{data.interpretation.disclaimer}</Muted>
      {data.quality.total > 0 && <Status $warning>
        <h3>Замечания к данным: {data.quality.total}</h3>
        {data.quality.items.map((item, i) => <p key={i}><strong>{item.SOURCE} · {issueLabels[item.ISSUE] ?? item.ISSUE}</strong><br />
          <code>{item.PATH}</code> — {item.DETAILS}</p>)}
        {data.quality.truncated && <p>Показаны первые {data.quality.items.length} из {data.quality.total} замечаний.</p>}
      </Status>}
      <h3>Изменённые атрибуты: {data.changes.total}</h3>
      {!data.comparison.complete && <p>Ниже показаны только наблюдаемые различия. Односторонние значения не подтверждают исчезновение атрибута в полной паре.</p>}
      <TableWrap><table><thead><tr><th>Путь / ключ массива</th><th>BEFORE</th><th>AFTER</th><th>Изменение</th></tr></thead>
        <tbody>{data.changes.rows.map((row, i) => <tr key={`${row.PATH}:${row.ARRAY_KEY}:${i}`}>
          <td><code>{row.PATH}</code>{row.ARRAY_KEY && <small>{row.ARRAY_KEY}</small>}</td>
          <td>{observedValue(row.BEFORE)}</td><td>{observedValue(row.AFTER)}</td>
          <td>{labels[row.CHANGE_TYPE] ?? row.CHANGE_TYPE}</td>
        </tr>)}</tbody></table></TableWrap>
      {!data.changes.rows.length && <p>{data.comparison.complete ? 'Наблюдаемых изменений атрибутов нет.' : 'Строки сравнения недоступны; это не подтверждение равенства.'}</p>}
      {data.changes.rows.length < data.changes.filtered_total && <>
        <Muted>Показано {data.changes.rows.length} из {data.changes.filtered_total} строк.</Muted>
        <QuietButton type="button" disabled={more} onClick={() => void loadMore()}>{more ? 'Загружаем…' : 'Показать ещё'}</QuietButton>
      </>}
    </>}
    <TextButton type="button" onClick={onShowRaw}>{showRaw ? 'Скрыть исходные данные ↑' : 'Показать исходные JSON / XML ↓'}</TextButton>
  </Section>;
}

const Section = styled.section`grid-column: 1 / -1; display: grid; gap: 16px; min-width: 0; font-size: 13px; line-height: 1.6; code { overflow-wrap: anywhere; }`;
const Cards = styled.div`display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; > div { padding: 16px; border: 1px solid #ebebee; border-radius: 12px; } p { overflow-wrap: anywhere; } @media(max-width: 640px) { grid-template-columns: 1fr; }`;
const Status = styled.div<{ $warning: boolean }>`padding: 16px; border-radius: 12px; background: ${p => p.$warning ? '#fff5df' : '#f4f7fa'}; p { margin-top: 8px; overflow-wrap: anywhere; }`;
const TableWrap = styled.div`overflow-x: auto; table { width: 100%; border-collapse: collapse; min-width: 560px; } th, td { text-align: left; padding: 12px; border-bottom: 1px solid #ebebee; vertical-align: top; overflow-wrap: anywhere; max-width: 340px; } small { display: block; color: #777782; margin-top: 6px; }`;
