/** Exact pivot cell identities. Never add CNT values across groups: apps can overlap. */
export type PivotValue = string | number | boolean | null;
export type PivotFilters = Record<string, PivotValue | PivotValue[]>;
export type PivotRecord = Record<string, PivotValue> & { CNT: number };
export type PivotResponse = { columns: string[]; dims: string[]; rows: PivotRecord[] };
export type PivotGroup = { id: string; values: PivotValue[] };

export const pivotLabel = (value: PivotValue) =>
  value === null ? 'SQL NULL (отсутствует)' :
  value === '' ? 'Пустая строка' :
  value === 'NULL' ? 'Строка «NULL»' : String(value);

export function buildPivotGrid(response: PivotResponse, rowDims: string[], colDims: string[]) {
  const rowGroups = new Map<string, PivotGroup>();
  const colGroups = new Map<string, PivotGroup>();
  const cells = new Map<string, PivotRecord>();
  for (const cell of response.rows) {
    const rowValues = rowDims.map(dim => cell[dim]);
    const colValues = colDims.map(dim => cell[dim]);
    const rowId = JSON.stringify(rowValues);
    const colId = JSON.stringify(colValues);
    if (!rowGroups.has(rowId)) rowGroups.set(rowId, { id: rowId, values: rowValues });
    if (!colGroups.has(colId)) colGroups.set(colId, { id: colId, values: colValues });
    cells.set(JSON.stringify([rowId, colId]), cell);
  }
  return {
    rowGroups: Array.from(rowGroups.values()),
    colGroups: Array.from(colGroups.values()),
    getCell: (rowId: string, colId: string) => cells.get(JSON.stringify([rowId, colId])),
  };
}

/** Preserve original JSON scalars (particularly null, 0, false and empty string). */
export function exactCellFilters(globalFilters: PivotFilters, dims: string[], cell: PivotRecord): PivotFilters {
  const filters: PivotFilters = { ...globalFilters };
  for (const dim of dims) {
    if (!Object.prototype.hasOwnProperty.call(cell, dim)) {
      throw new Error(`Отсутствует измерение ячейки: ${dim}`);
    }
    filters[dim] = cell[dim];
  }
  return filters;
}

/** Highlight the exact comparison attribute behind a selected pivot cell. */
export function matchesCellAttribute(
  row: { PATH: string; ARRAY_KEY?: string | null; CHANGE_TYPE: string;
    DIFF_FLAG: number; ADJUSTED_BEFORE?: string | null; ADJUSTED_AFTER?: string | null },
  filters: PivotFilters,
): boolean {
  const accept = (actual: PivotValue, expected: PivotValue | PivotValue[] | undefined) =>
    expected === undefined || (Array.isArray(expected) ? expected : [expected]).includes(actual);
  if (!accept(row.PATH, filters.PATH)) return false;
  if (!accept(row.ARRAY_KEY ?? null, filters.ARRAY_KEY)) return false;
  if (!accept(row.CHANGE_TYPE, filters.CHANGE_TYPE)) return false;
  if (!accept(row.DIFF_FLAG, filters.DIFF_FLAG)) return false;
  if (filters.VALUE_ADJUSTED !== undefined) {
    const source = filters.SOURCE;
    const selectedSources = source === undefined ? [] : Array.isArray(source) ? source : [source];
    const checkBefore = !selectedSources.length || selectedSources.includes('BEFORE (MASTER)');
    const checkAfter = !selectedSources.length || selectedSources.includes('AFTER (BETA)');
    return (checkBefore && accept(row.ADJUSTED_BEFORE ?? null, filters.VALUE_ADJUSTED)) ||
      (checkAfter && accept(row.ADJUSTED_AFTER ?? null, filters.VALUE_ADJUSTED));
  }
  return true;
}

/** User-facing labels: the API contract remains the original column names. */
export const PIVOT_FIELD_LABELS: Record<string, string> = {
  PATH: 'Атрибут', PREFIX: 'Блок данных', CLASS: 'Раздел', SUFFIX: 'Подраздел',
  KEY: 'Поле', ARRAY_KEY: 'Ключ элемента массива', VALUE_ADJUSTED: 'Значение / диапазон',
  CHANGE_TYPE: 'Тип изменения', DIFF_FLAG: 'Есть изменение', SOURCE: 'Срез',
  DECISION_BEFORE: 'Решение до', DECISION_AFTER: 'Решение после',
  DECISION_CHANGED: 'Решение изменилось', DECISION_TRANSITION: 'Переход решения',
  REASON_BEFORE: 'Причина до', REASON_AFTER: 'Причина после',
  REASON_TRANSITION: 'Переход причины', CAUSE: 'Источник различий',
  PARTNER_TYPE: 'Тип партнёра', PRODUCTS: 'Продукты',
};

export const dimensionLabel = (name: string) => PIVOT_FIELD_LABELS[name] ?? name;

export function readablePivotValue(field: string, value: PivotValue): string {
  if (value === null) return 'Нет значения (SQL NULL)';
  if (value === '') return 'Пустая строка';
  if (value === 'NULL') return 'Текст «NULL»';
  const translations: Record<string, string> = {
    SAME: 'Без изменений', VALUE_CHANGED: 'Значение изменилось',
    ATTRIBUTE_NEW: 'Атрибут появился', ATTRIBUTE_LOST: 'Атрибут исчез',
    'BEFORE (MASTER)': 'До изменений (MASTER)', 'AFTER (BETA)': 'После изменений (BETA)',
    INPUT_DATA: 'Входные данные', LOGIC: 'Логика стратегии', BOTH: 'Данные и логика',
    NONE: 'Нет различий', APPROVE: 'Одобрено', REJECT: 'Отказ',
    VERIFICATION: 'Проверка',
  };
  if (field === 'DIFF_FLAG' || field === 'DECISION_CHANGED') {
    if (value === 1 || value === '1' || value === true) return 'Да';
    if (value === 0 || value === '0' || value === false) return 'Нет';
  }
  if (['CHANGE_TYPE', 'CAUSE', 'SOURCE', 'DECISION_BEFORE', 'DECISION_AFTER'].includes(field)) {
    return translations[String(value)] ?? pivotLabel(value);
  }
  return pivotLabel(value);
}

export type PivotPreset = 'changes' | 'decisions' | 'products' | 'partners' | 'causes';

export const PIVOT_PRESETS: ReadonlyArray<{ id: PivotPreset; title: string; description: string; rows: string[]; cols: string[]; changedOnly: boolean }> = [
  {id: 'changes', title: 'Что изменилось', description: 'По атрибутам и типам изменения', rows: ['PATH'], cols: ['CHANGE_TYPE'], changedOnly: true},
  {id: 'decisions', title: 'Решения до / после', description: 'Сколько заявок перешло в другое решение', rows: ['DECISION_BEFORE'], cols: ['DECISION_AFTER'], changedOnly: false},
  {id: 'products', title: 'По продуктам', description: 'Какие продукты затронули изменения', rows: ['PRODUCTS'], cols: ['CHANGE_TYPE'], changedOnly: true},
  {id: 'partners', title: 'По партнёрам', description: 'Различия по типам партнёров', rows: ['PARTNER_TYPE'], cols: ['CHANGE_TYPE'], changedOnly: true},
  {id: 'causes', title: 'По источнику различий', description: 'Классификация по правилам, не доказанная причина', rows: ['CAUSE'], cols: ['CHANGE_TYPE'], changedOnly: true},
];

/** Returns null when a run has no dimensions required by this preset. */
export function presetLayout(id: PivotPreset, available: string[]) {
  const def = PIVOT_PRESETS.find(item => item.id === id);
  if (!def || ![...def.rows, ...def.cols].every(d => available.includes(d))) return null;
  const filters: PivotFilters = def.changedOnly && available.includes('DIFF_FLAG') ? {DIFF_FLAG: 1} : {};
  return { rows: [...def.rows], cols: [...def.cols], filters };
}
