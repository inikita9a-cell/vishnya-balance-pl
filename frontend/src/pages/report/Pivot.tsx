/** P0-05 / P0-06: user-configurable pivot and exact cell-to-application drill-down. */
import { useEffect, useMemo, useRef, useState } from 'react';
import type { DragEvent } from 'react';
import styled from 'styled-components';
import { message } from '../../api/client';
import { getAppComparisonRows, getPivot, getPivotApps, getPivotDimensions, getPivotValues, getRawComparison } from '../../api/real';
import type { PivotApp, PivotFilters, PivotResponse, PivotValue } from '../../api/real';
import type { Difference, RawComparison } from '../../api/types';
import { buildPivotGrid, dimensionLabel, exactCellFilters, matchesCellAttribute, pivotLabel, PIVOT_PRESETS, presetLayout, readablePivotValue } from './pivotModel';
import type { PivotPreset } from './pivotModel';
import { theme } from '../../styles/Theme';
import { DataTable, Empty, ErrorBox, Muted, PageHeading, Panel, QuietButton, TableScroller, TextButton } from '../../components/Ui';

const PAGE_SIZE = 50;
const VIEW_ROWS = 35;
const VIEW_COLS = 5;
const fmt = (number: number) => number.toLocaleString('ru-RU');
const preferredRows = ['PATH', 'PRODUCTS', 'PARTNER_TYPE', 'CHANGE_TYPE'];
const preferredCols = ['CHANGE_TYPE', 'SOURCE', 'DECISION_TRANSITION'];

type Zone = 'rows' | 'cols' | 'filters';
type SelectedCell = { count: number; filters: PivotFilters };

export function Pivot({ runId, onOpenApp }: { runId: string; onOpenApp: (appId: string) => void }) {
  return <PivotRun key={runId} runId={runId} onOpenApp={onOpenApp} />;
}

function PivotRun({ runId, onOpenApp }: { runId: string; onOpenApp: (appId: string) => void }) {
  const [available, setAvailable] = useState<string[]>([]);
  const [rows, setRows] = useState<string[]>(['PATH']);
  const [cols, setCols] = useState<string[]>(['CHANGE_TYPE']);
  const [filters, setFilters] = useState<PivotFilters>({});
  const [field, setField] = useState('');
  const [values, setValues] = useState<PivotValue[]>([]);
  const [valuesMore, setValuesMore] = useState(false);
  const [valueIndex, setValueIndex] = useState('0');
  const [manualValue, setManualValue] = useState('');
  const [data, setData] = useState<PivotResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [fieldsError, setFieldsError] = useState('');
  const [rowPage, setRowPage] = useState(0);
  const [colPage, setColPage] = useState(0);
  const [preset, setPreset] = useState<PivotPreset | 'custom'>('changes');
  const [showBuilder, setShowBuilder] = useState(false);
  const detailRef = useRef<HTMLElement | null>(null);
  const appRef = useRef<HTMLDivElement | null>(null);
  const [selected, setSelected] = useState<SelectedCell | null>(null);
  const [page, setPage] = useState(0);
  const [apps, setApps] = useState<PivotApp[]>([]);
  const [appTotal, setAppTotal] = useState<number | null>(null);
  const [appsError, setAppsError] = useState('');
  const [appsBusy, setAppsBusy] = useState(false);
  const [appId, setAppId] = useState('');
  const [appRows, setAppRows] = useState<Difference[]>([]);
  const [appError, setAppError] = useState('');
  const [appBusy, setAppBusy] = useState(false);
  const [raw, setRaw] = useState<RawComparison | null>(null);
  const [rawError, setRawError] = useState('');
  const [rawBusy, setRawBusy] = useState(false);

  useEffect(() => {
    let live = true;
    getPivotDimensions(runId).then(({ dimensions }) => {
      if (!live) return;
      setAvailable(dimensions);
      const initial = presetLayout('changes', dimensions);
      const rowDefault = preferredRows.find(name => dimensions.includes(name)) ?? dimensions[0];
      const colDefault = preferredCols.find(name => dimensions.includes(name) && name !== rowDefault);
      setRows(initial?.rows ?? (rowDefault ? [rowDefault] : []));
      setCols(initial?.cols ?? (colDefault ? [colDefault] : []));
      setFilters(initial?.filters ?? {});
      setPreset(initial ? 'changes' : 'custom');
      setField(dimensions.includes('PRODUCTS') ? 'PRODUCTS' : (dimensions[0] ?? ''));
    }).catch(err => { if (live) setFieldsError(message(err)); });
    return () => { live = false; };
  }, [runId]);

  useEffect(() => {
    if (!field) return;
    let live = true;
    setValues([]);
    setValueIndex('0');
    getPivotValues(runId, field).then(result => {
      if (live) { setValues(result.values); setValuesMore(result.has_more); }
    }).catch(err => { if (live) setFieldsError(message(err)); });
    return () => { live = false; };
  }, [runId, field]);

  const rowsKey = JSON.stringify(rows), colsKey = JSON.stringify(cols);
  const filtersKey = JSON.stringify(filters);
  useEffect(() => {
    if (!available.length) return;
    if (!rows.length && !cols.length) {
      setData(null); setSelected(null); setBusy(false);
      setError('Выберите хотя бы одно поле для строк или колонок.');
      return;
    }
    let live = true;
    setBusy(true); setError(''); setData(null); setSelected(null);
    setRowPage(0); setColPage(0); setPage(0); setAppId('');
    getPivot(runId, rows, cols, filters).then(result => {
      if (live) setData(result);
    }).catch(err => { if (live) setError(message(err)); })
      .finally(() => { if (live) setBusy(false); });
    return () => { live = false; };
    // serialized keys make re-querying deliberate even if the filter object is recreated
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, available, rowsKey, colsKey, filtersKey]);

  useEffect(() => {
    if (!selected) return;
    let live = true;
    setAppsBusy(true); setAppsError(''); setApps([]); setAppTotal(null);
    getPivotApps(runId, selected.filters, PAGE_SIZE, page).then(result => {
      if (!live) return;
      setApps(result.items); setAppTotal(result.total);
      if (result.total !== selected.count) {
        setApps([]); setAppTotal(null);
        setAppsError(`Ошибка согласованности данных: в ячейке ${fmt(selected.count)}, API возвращает ${fmt(result.total)} заявок.`);
        return;
      }
    }).catch(err => { if (live) setAppsError(message(err)); })
      .finally(() => { if (live) setAppsBusy(false); });
    return () => { live = false; };
  }, [runId, selected, page]);

  useEffect(() => {
    if (!appId) return;
    let live = true;
    setAppRows([]); setAppError(''); setAppBusy(true);
    setRaw(null); setRawError('');
    getAppComparisonRows(runId, appId).then(result => {
      if (live) setAppRows(result);
    }).catch(err => { if (live) setAppError(message(err)); })
      .finally(() => { if (live) setAppBusy(false); });
    return () => { live = false; };
  }, [runId, appId]);

  const grid = useMemo(() => data ? buildPivotGrid(data, rows, cols) : null, [data, rowsKey, colsKey]);
  const displayedRows = grid?.rowGroups.slice(rowPage * VIEW_ROWS, (rowPage + 1) * VIEW_ROWS) ?? [];
  const displayedCols = grid?.colGroups.slice(colPage * VIEW_COLS, (colPage + 1) * VIEW_COLS) ?? [];
  const hasAttributeScope = !!selected && ['PATH', 'ARRAY_KEY', 'CHANGE_TYPE', 'VALUE_ADJUSTED'].some(field => field in selected.filters);
  const visibleAppRows = useMemo(() => [...appRows].sort((a, b) => {
    const aHit = !!selected && matchesCellAttribute(a, selected.filters), bHit = !!selected && matchesCellAttribute(b, selected.filters);
    return Number(bHit) - Number(aHit) || Number(b.DIFF_FLAG) - Number(a.DIFF_FLAG);
  }), [appRows, selected]);

  useEffect(() => {
    if (selected) detailRef.current?.scrollIntoView({behavior: 'smooth', block: 'start'});
  }, [selected]);
  useEffect(() => {
    if (appId) appRef.current?.scrollIntoView({behavior: 'smooth', block: 'start'});
  }, [appId]);

  function activatePreset(name: PivotPreset) {
    const config = presetLayout(name, available);
    if (!config) return;
    setRows(config.rows); setCols(config.cols); setFilters(config.filters);
    setPreset(name); setShowBuilder(false); setColPage(0);
  }

  function place(fieldName: string, zone: Zone) {
    setPreset('custom');
    if (!available.includes(fieldName)) return;
    if (zone === 'filters') { setField(fieldName); return; }
    setRows(current => zone === 'rows' && !current.includes(fieldName)
      ? [...current, fieldName] : current.filter(item => item !== fieldName));
    setCols(current => zone === 'cols' && !current.includes(fieldName)
      ? [...current, fieldName] : current.filter(item => item !== fieldName));
  }
  function handleDrop(ev: DragEvent<HTMLDivElement>, zone: Zone) {
    ev.preventDefault();
    place(ev.dataTransfer.getData('text/plain'), zone);
  }
  function shift(list: string[], setList: (items: string[]) => void, index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= list.length) return;
    const copy = [...list]; [copy[index], copy[target]] = [copy[target], copy[index]];
    setList(copy);
  }
  function addFilter() {
    setPreset('custom');
    if (!field) return;
    let next: PivotValue;
    if (manualValue.trim()) {
      const text = manualValue.trim();
      if (text === 'null') next = null;
      else if (text === 'true' || text === 'false') next = text === 'true';
      else if (/^-?(?:0|[1-9]\d*)(?:\.\d+)?$/.test(text) && values.some(v => typeof v === 'number')) next = Number(text);
      else next = text;
    } else {
      if (!values.length) return;
      next = values[Number(valueIndex)];
      if (next === undefined) return;
    }
    setFilters(current => {
      if (!(field in current)) return { ...current, [field]: next };
      const prev = Array.isArray(current[field]) ? [...current[field]] : [current[field]];
      if (!prev.some(item => item === next)) prev.push(next);
      return { ...current, [field]: prev };
    });
    setManualValue('');
  }
  function openCell(cell: Record<string, PivotValue> & { CNT: number }) {
    const cellFilters = exactCellFilters(filters, data?.dims ?? [], cell);
    setSelected({ filters: cellFilters, count: cell.CNT });
    setPage(0); setAppId(''); setAppRows([]); setRaw(null);
  }
  async function showRaw() {
    if (raw) { setRaw(null); return; }
    if (!appId) return;
    setRawBusy(true); setRawError('');
    try { setRaw(await getRawComparison(runId, appId)); }
    catch (err) { setRawError(message(err)); }
    finally { setRawBusy(false); }
  }

  return <>
    <PageHeading><div><h1>Сводная таблица</h1><p>Заявки, затронутые изменениями стратегии · запуск <strong>{runId}</strong></p></div></PageHeading>
    <Intro>Выберите, <strong>какой вопрос хотите изучить</strong>. Ниже появятся числа заявок. Нажмите на число — откроется точный список заявок и значения атрибутов до и после.</Intro>
    <Presets aria-label="Готовые виды сводной">
      {PIVOT_PRESETS.map(item => <PresetButton type="button" key={item.id}
        $active={preset === item.id} disabled={!presetLayout(item.id, available)} onClick={() => activatePreset(item.id)}
        aria-pressed={preset === item.id}><strong>{item.title}</strong><span>{item.description}</span></PresetButton>)}
    </Presets>
    <Toolbar><Description>Сейчас: {rows.map(dimensionLabel).join(' → ')} {cols.length ? `× ${cols.map(dimensionLabel).join(' → ')}` : ''}.
      {' Фильтры: ' + (Object.keys(filters).length ? Object.entries(filters).map(([name, value]) => `${dimensionLabel(name)} — ${(Array.isArray(value) ? value : [value]).map(v => readablePivotValue(name, v)).join(' или ')}`).join('; ') : 'нет')}.</Description>
      <QuietButton type="button" onClick={() => setShowBuilder(x => !x)}>{showBuilder ? 'Скрыть конструктор' : 'Настроить свои поля и фильтры'}</QuietButton></Toolbar>
    {fieldsError && <ErrorBox role="alert">{fieldsError}</ErrorBox>}
    {showBuilder && <PivotLayout>
      <Panel>
        <h2>Все доступные поля</h2>
        <Description>Это расширенный режим. Добавляйте не больше 1–2 полей в каждую ось, чтобы таблица оставалась понятной.</Description>
        <Dimensions>{available.map(name => <Dimension key={name} draggable
          onDragStart={event => event.dataTransfer.setData('text/plain', name)}>
          <span title={name}>{dimensionLabel(name)} <CodeName>{name}</CodeName></span><div><SmallButton type="button" title={`Добавить ${name} в строки`} onClick={() => place(name, 'rows')}>Строки</SmallButton>
          <SmallButton type="button" title={`Добавить ${name} в колонки`} onClick={() => place(name, 'cols')}>Колонки</SmallButton>
          <SmallButton type="button" title={`Выбрать ${name} как фильтр`} onClick={() => place(name, 'filters')}>Фильтр</SmallButton></div>
        </Dimension>)}</Dimensions>
      </Panel>
      <Panel>
        <Zones>
          {(['rows', 'cols'] as const).map(zone => {
            const values = zone === 'rows' ? rows : cols;
            const setList = zone === 'rows' ? setRows : setCols;
            return <DropZone key={zone} onDragOver={event => event.preventDefault()} onDrop={event => handleDrop(event, zone)}>
              <h2>{zone === 'rows' ? 'Строки (что сравниваем)' : 'Колонки (по чему раскладываем)'}</h2>
              {values.map((name, index) => <Chip key={name}><strong title={name}>{dimensionLabel(name)}</strong>
                <SmallButton type="button" disabled={index === 0} onClick={() => shift(values, setList, index, -1)} aria-label={`Поднять ${name}`}>↑</SmallButton>
                <SmallButton type="button" disabled={index === values.length - 1} onClick={() => shift(values, setList, index, 1)} aria-label={`Опустить ${name}`}>↓</SmallButton>
                <SmallButton type="button" onClick={() => setList(values.filter(item => item !== name))} aria-label={`Убрать ${name}`}>×</SmallButton>
              </Chip>)}
              {!values.length && <Muted>Перетащите поле сюда</Muted>}
            </DropZone>;
          })}
        </Zones>
        <DropZone onDragOver={event => event.preventDefault()} onDrop={event => handleDrop(event, 'filters')}>
          <h2>Фильтры</h2>
          <FilterControls><label>Поле<select aria-label="Измерение фильтра" value={field} onChange={event => {setField(event.target.value); setManualValue('');}}>
            {available.map(name => <option key={name} value={name}>{dimensionLabel(name)} ({name})</option>)}
          </select></label>
          <label>Значение из данных<select aria-label="Значение фильтра" value={valueIndex} onChange={event => setValueIndex(event.target.value)}>
            {values.map((value, i) => <option key={i} value={String(i)}>{readablePivotValue(field, value)}</option>)}
          </select></label></FilterControls>
          <label>Или введите точное значение вручную<input value={manualValue} onChange={event => setManualValue(event.target.value)} placeholder="Значение, например CASH_LOAN" /></label>
          {valuesMore && <Muted>В списке показаны первые 200 значений. Для остальных используйте ручной ввод.</Muted>}
          <QuietButton type="button" disabled={!field || (!manualValue.trim() && !values.length)} onClick={addFilter}>Добавить значение фильтра</QuietButton>
          {Object.entries(filters).map(([name, values]) => <Chip key={name}><strong>{dimensionLabel(name)}:</strong>
            <span>{(Array.isArray(values) ? values : [values]).map(value => readablePivotValue(name, value)).join(' ИЛИ ')}</span>
            <SmallButton type="button" onClick={() => {setPreset('custom');setFilters(prev => {
              const copy = { ...prev }; delete copy[name]; return copy;
            });}} aria-label={`Удалить фильтр ${name}`}>×</SmallButton></Chip>)}
          <Muted>Между полями — И, внутри одного поля — ИЛИ. NULL не равен строке «NULL».</Muted>
        </DropZone>
        <Description>Счётчик — <strong>COUNT(DISTINCT APP_ID)</strong>. Нельзя суммировать значения разных ячеек: заявки могут пересекаться.</Description>
      </Panel>
    </PivotLayout>}

    <Panel>
      <h2>Результат сводной</h2>
      {busy && <Empty role="status">Пересчитываем раскладку…</Empty>}
      {error && <ErrorBox role="alert">{error}</ErrorBox>}
      {data && grid && <>
        <Description>Строк: {fmt(grid.rowGroups.length)} · вариантов колонок: {fmt(grid.colGroups.length)}. <strong>Каждое число — уникальные заявки с признаками выбранной строки и колонки.</strong> Одни и те же заявки могут встречаться в разных строках.</Description>
        {grid.colGroups.length > VIEW_COLS && <Pager><Muted>Колонки {colPage * VIEW_COLS + 1}–{Math.min((colPage + 1) * VIEW_COLS, grid.colGroups.length)} из {grid.colGroups.length}</Muted>
          <QuietButton type="button" disabled={colPage === 0} onClick={() => setColPage(p => p - 1)}>← Предыдущие колонки</QuietButton>
          <QuietButton type="button" disabled={(colPage + 1) * VIEW_COLS >= grid.colGroups.length} onClick={() => setColPage(p => p + 1)}>Следующие колонки →</QuietButton></Pager>}
        <ResultScroller><PivotTable>
          <thead><tr>
            {rows.map((name, i) => <RowHeading $first={i === 0} key={name} title={name}>{dimensionLabel(name)}</RowHeading>)}
            {displayedCols.map(col => <th key={col.id} title={cols.length ? cols.map((name, i) => `${dimensionLabel(name)}: ${readablePivotValue(name, col.values[i])}`).join(' · ') : 'Заявок'}>{cols.length ? cols.map((name, i) => <ColumnPart key={name}><b>{dimensionLabel(name)}:</b> {readablePivotValue(name, col.values[i])}</ColumnPart>) : 'Заявок'}</th>)}
          </tr></thead>
          <tbody>{displayedRows.map(row => <tr key={row.id}>
            {row.values.map((value, i) => <RowValue $first={i === 0} title={pivotLabel(value)} key={rows[i]}>{readablePivotValue(rows[i], value)}</RowValue>)}
            {displayedCols.map(col => {
              const cell = grid.getCell(row.id, col.id);
              return <td key={col.id}>{cell ? <TextButton type="button" onClick={() => openCell(cell)}
                aria-label={`Открыть ${cell.CNT} заявок из ячейки`} title="Показать точный список заявок">{fmt(cell.CNT)} →</TextButton> : '—'}</td>;
            })}
          </tr>)}</tbody>
        </PivotTable></ResultScroller>
        {!grid.rowGroups.length && <Empty>Нет групп по выбранным фильтрам</Empty>}
        <Pager><Muted>{grid.rowGroups.length ? `${rowPage * VIEW_ROWS + 1}–${Math.min((rowPage + 1) * VIEW_ROWS, grid.rowGroups.length)}` : '0'} из {fmt(grid.rowGroups.length)} групп</Muted>
          <QuietButton type="button" disabled={rowPage === 0} onClick={() => setRowPage(p => p - 1)}>Назад</QuietButton>
          <QuietButton type="button" disabled={(rowPage + 1) * VIEW_ROWS >= grid.rowGroups.length} onClick={() => setRowPage(p => p + 1)}>Далее</QuietButton>
        </Pager>
      </>}
    </Panel>

    {selected && <Panel ref={detailRef}>
      <DetailHeader><div><h2>Заявки выбранной ячейки: {fmt(selected.count)}</h2>
        <Description>{Object.entries(selected.filters).map(([key, val]) => `${dimensionLabel(key)}: ${(Array.isArray(val) ? val : [val]).map(v => readablePivotValue(key, v)).join(' ИЛИ ')}`).join(' · ')}</Description></div>
        <QuietButton type="button" onClick={() => {setSelected(null);setAppId('');}}>Закрыть ×</QuietButton></DetailHeader>
      {appsBusy && <Empty role="status">Загружаем заявки…</Empty>}
      {appsError && <ErrorBox role="alert">{appsError}</ErrorBox>}
      {appTotal !== null && <>
        <Description>Сервер подтвердил: {fmt(appTotal)} уникальных заявок. Показана страница {Math.floor(page / PAGE_SIZE) + 1}.</Description>
        <TableScroller><DataTable><thead><tr><th>Заявка</th><th>Решение до</th><th>Решение после</th><th>Причина</th><th>Всего отличий в заявке</th><th></th></tr></thead>
          <tbody>{apps.map(app => <tr key={app.APP_ID}>
            <td>{app.APP_ID}</td><td>{app.DECISION_BEFORE ?? '—'}</td><td>{app.DECISION_AFTER ?? '—'}</td>
            <td>{app.REASON_TRANSITION ?? '—'}</td><td>{app.N_DIFFS}</td>
            <td><TextButton type="button" onClick={() => setAppId(app.APP_ID)}>Атрибуты</TextButton> · <TextButton type="button" onClick={() => onOpenApp(app.APP_ID)}>Карточка →</TextButton></td>
          </tr>)}</tbody></DataTable></TableScroller>
        <Pager><Muted>{appTotal ? `${page + 1}–${Math.min(page + PAGE_SIZE, appTotal)}` : '0'} из {fmt(appTotal)}</Muted>
          <QuietButton type="button" disabled={page === 0} onClick={() => {setPage(p => p - PAGE_SIZE);setAppId('');}}>Назад</QuietButton>
          <QuietButton type="button" disabled={page + PAGE_SIZE >= appTotal} onClick={() => {setPage(p => p + PAGE_SIZE);setAppId('');}}>Далее</QuietButton></Pager>
      </>}
      {appId && <AppPanel ref={appRef}>
        <DetailHeader><h2>Атрибуты заявки {appId}: BEFORE → AFTER</h2>
          <QuietButton type="button" onClick={() => setAppId('')}>Скрыть</QuietButton></DetailHeader>
        {appBusy && <Empty>Загружаем атрибуты…</Empty>}
        {appError && <ErrorBox role="alert">{appError}</ErrorBox>}
        {!!visibleAppRows.length && <TableScroller><DataTable>
          <thead><tr><th>Путь</th><th>Ключ массива</th><th>BEFORE</th><th>AFTER</th><th>Тип изменения</th></tr></thead>
          <tbody>{visibleAppRows.map((row, index) => <tr key={`${row.PATH}-${row.ARRAY_KEY ?? ''}-${index}`} style={hasAttributeScope && selected && matchesCellAttribute(row, selected.filters) ? {background: '#fef3ed'} : undefined}>
            <td>{row.PATH}</td><td>{row.ARRAY_KEY || '—'}</td><td>{row.VALUE_BEFORE}</td><td>{row.VALUE_AFTER}</td><td>{readablePivotValue('CHANGE_TYPE', row.CHANGE_TYPE)}</td>
          </tr>)}</tbody>
        </DataTable></TableScroller>}
        {!appBusy && !appError && !visibleAppRows.length && <Empty>Нет строк сравнения для заявки</Empty>}
        <QuietButton type="button" disabled={rawBusy} onClick={() => void showRaw()}>{raw ? 'Скрыть исходные ответы' : 'Посмотреть исходные ответы JSON/XML'}</QuietButton>
        {rawError && <ErrorBox role="alert">{rawError}</ErrorBox>}
        {raw && <RawGrid><pre>{raw.before}</pre><pre>{raw.after}</pre></RawGrid>}
      </AppPanel>}
    </Panel>}
  </>;
}

const PivotLayout = styled.div`display:grid;grid-template-columns:minmax(280px,1fr) minmax(320px,1.5fr);gap:20px;margin-bottom:20px; & > section{min-width:0} @media(max-width:900px){grid-template-columns:1fr}`;
const Description = styled.p`font:400 12px/1.6 ${theme.fonts.interface};color:#777782;margin:12px 0 18px;overflow-wrap:anywhere;`;
const Dimensions = styled.div`display:grid;gap:8px;max-height:370px;overflow:auto;`;
const Dimension = styled.div`display:flex;align-items:center;justify-content:space-between;gap:10px;border:1px solid #eeeef0;padding:8px;border-radius:9px;cursor:grab;flex-wrap:wrap;span{font:600 12px ${theme.fonts.interface};overflow-wrap:anywhere}div{display:flex;gap:4px;flex-wrap:wrap}`;
const SmallButton = styled.button`border:1px solid #e1e1e5;background:white;color:${theme.colors.darkBgColor};border-radius:6px;padding:5px 7px;cursor:pointer;font-size:11px;&:hover{border-color:${theme.colors.accent}}&:disabled{opacity:.35;cursor:default}`;
const Zones = styled.div`display:grid;grid-template-columns:1fr 1fr;gap:12px;@media(max-width:600px){grid-template-columns:1fr}`;
const DropZone = styled.div`display:grid;align-content:start;gap:9px;min-height:80px;padding:12px;margin-bottom:13px;border:1px dashed #cccbd1;border-radius:11px;h2{font:650 14px ${theme.fonts.interface};margin-bottom:5px}label{display:grid;gap:5px;font-size:12px;min-width:0}select,input{min-width:0;width:100%;border:1px solid #dddde1;background:white;border-radius:7px;padding:8px}`;
const Chip = styled.div`display:flex;align-items:center;flex-wrap:wrap;gap:6px;padding:7px 8px;border-radius:7px;background:#f5f5f7;font-size:11px;overflow-wrap:anywhere;strong{font-weight:650}`;
const FilterControls = styled.div`display:grid;grid-template-columns:1fr 1fr;gap:9px;@media(max-width:600px){grid-template-columns:1fr}`;
const Pager = styled.div`display:flex;justify-content:flex-end;align-items:center;flex-wrap:wrap;gap:10px;margin:15px 0;`;
const DetailHeader = styled.div`display:flex;justify-content:space-between;flex-wrap:wrap;align-items:center;gap:15px;margin-bottom:14px;`;
const AppPanel = styled.div`border-top:1px solid #e9e9ec;margin-top:18px;padding-top:18px;`;
const RawGrid = styled.div`display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px;pre{max-height:400px;overflow:auto;padding:10px;background:#f5f5f7;border-radius:8px;font-size:11px;white-space:pre-wrap;overflow-wrap:anywhere}@media(max-width:780px){grid-template-columns:1fr}`;

const Intro = styled.p`font:500 14px/1.6 ${theme.fonts.interface};color:#3b3b46;margin:-4px 0 20px;max-width:940px;`;
const Presets = styled.div`display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin-bottom:14px;@media(max-width:1150px){grid-template-columns:repeat(3,1fr)}@media(max-width:720px){grid-template-columns:repeat(2,1fr)}`;
const PresetButton = styled.button<{$active:boolean}>`display:flex;flex-direction:column;align-items:flex-start;gap:5px;text-align:left;padding:14px;border-radius:13px;background:${p=>p.$active?'#fff1eb':'white'};border:2px solid ${p=>p.$active?theme.colors.accent:'#ebebee'};min-height:84px;cursor:pointer;strong{font-size:13px;color:#22222c}span{font-size:11px;line-height:1.4;color:#737382}&:hover:not(:disabled){border-color:${theme.colors.accent}}&:disabled{opacity:.45;cursor:not-allowed}`;
const Toolbar = styled.div`display:flex;justify-content:space-between;align-items:center;gap:16px;margin:8px 0 18px;flex-wrap:wrap;p{margin:0;flex:1}`;
const CodeName = styled.small`color:#9393a0;margin-left:4px;font:400 10px ${theme.fonts.interface};`;
const ResultScroller = styled.div`width:100%;overflow-x:auto;border:1px solid #ececf0;border-radius:12px;`;
const PivotTable = styled(DataTable)`width:max-content;min-width:100%;table-layout:fixed;th{vertical-align:top;min-width:148px;max-width:210px;white-space:normal;line-height:1.5;overflow-wrap:anywhere;text-transform:none;color:#393944;font-size:12px;}td{min-width:145px;max-width:290px;overflow-wrap:anywhere;}tbody tr:hover td{background:#f9fafb;}thead th{position:sticky;top:0;z-index:1}`;
const RowHeading = styled.th<{$first:boolean}>`&&{min-width:${p=>p.$first?'280px':'160px'};max-width:${p=>p.$first?'320px':'220px'};${p=>p.$first?'position:sticky;left:0;z-index:4;':''}background:#f5f5f8;}`;
const RowValue = styled.td<{$first:boolean}>`&&{min-width:${p=>p.$first?'280px':'160px'};max-width:${p=>p.$first?'320px':'220px'};${p=>p.$first?'position:sticky;left:0;z-index:2;':''}background:#fff;font-weight:${p=>p.$first?'600':'400'};}`;
const ColumnPart = styled.div`&+&{margin-top:4px}b{font-weight:600}`;
