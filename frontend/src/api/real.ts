/** Precise mapping between the November 2026 FastAPI endpoints and UI view models.
 * Server's list routes return JSON ARRAYS (no Page wrapper).
 * Backend's drilldown returns only a subset of segment columns.
 */
import { api, post } from './client';
import type { ExplorerFieldsResponse, ExplorerQueryRequest, ExplorerQueryResponse, ExplorerAppsRequest, ExplorerAppsResponse } from './explorer.types';

export const getExplorerFields = (id: string) =>
  api<ExplorerFieldsResponse>(`/runs/${encodeURIComponent(id)}/explorer/fields`);
export const queryExplorer = (id: string, body: ExplorerQueryRequest) =>
  post<ExplorerQueryResponse>(`/runs/${encodeURIComponent(id)}/explorer/query`, body);
export const getExplorerApps = (id: string, body: ExplorerAppsRequest) =>
  post<ExplorerAppsResponse>(`/runs/${encodeURIComponent(id)}/explorer/apps`, body);
import type { Block, Check, Config, Difference, Pool, Procedure, RawComparison, Run, RunStage, Segment, StepDetail, Summary } from './types';

const n = (value: unknown): number => typeof value === 'number' && Number.isFinite(value) ? value : 0;
const s = (value: unknown): string => value == null ? '' : String(value);
const safeArray = <T>(value: unknown): T[] => Array.isArray(value) ? value as T[] : [];

interface ServerRun {
  id: string; status: string; config_id?: number | string;
  started_by: string; created_at: string; finished_at: string | null;
  error?: string | null;
  steps?: { step: string; status: string; progress: number; duration_ms: number | null;
    rows_in: number | null; rows_out: number | null; message?: string }[];
}
interface ServerConfig { id: number; name: string; yaml: string }
interface ServerPool { id: number; name: string; payload: Record<string, unknown> }
interface ServerProcedure { id: number; kind: string; source: string; path?: string | null; code?: string | null }
interface ServerCell { before: string | null; after: string | null; count: number; changed: boolean }
interface ServerSummary {
  total_apps: number; apps_with_diff: number; apps_decision_changed: number;
  apps_diff_but_decision_same: number; apps_with_quality_issues: number;
  approval_rates?: { before_rate: number | null; after_rate: number | null };
  decision_transitions?: ServerCell[]; reason_transitions?: ServerCell[];
  cause_counts?: Record<string, number>;
  verdict?: Summary['verdict'];
}
interface ServerDrilldown {
  APP_ID: string; DECISION_BEFORE: string | null; DECISION_AFTER: string | null;
  DECISION_TRANSITION: string | null; REASON_TRANSITION: string | null;
  N_DIFFS: number; CAUSE: string;
}

const STAGE_COUNT = 12;
function fromRun(raw: ServerRun): Run {
  const stages: RunStage[] = safeArray<NonNullable<ServerRun['steps']>[number]>(raw.steps).map(l => ({
    step: l.step, status: l.status, progress: n(l.progress),
    duration_ms: l.duration_ms, rows_in: l.rows_in, rows_out: l.rows_out,
    message: l.message,
  }));
  // List API does not return progress. Only detailed stage log lets us estimate it.
  const progress = raw.status === 'done' ? 100 : raw.status === 'queued' ? 0 :
    stages.length ? Math.min(99, Math.round(100 * stages.reduce((acc, st) =>
      acc + (st.status === 'done' ? 1 : st.status === 'running' ? st.progress / 100 : 0), 0) / STAGE_COUNT)) : null;
  return {
    id: raw.id, config_id: raw.config_id == null ? '' : s(raw.config_id),
    started_by: raw.started_by, created_at: raw.created_at, finished_at: raw.finished_at,
    status: raw.status, error: raw.error, stages, progress,
  };
}

export async function getRuns(): Promise<Run[]> {
  return (await api<ServerRun[]>('/runs')).map(fromRun);
}
export async function getRun(id: string): Promise<Run> {
  // /runs/{id} lacks config_id; join it from /runs for the run info panel.
  const [details, list] = await Promise.all([api<ServerRun>(`/runs/${encodeURIComponent(id)}`), getRuns()]);
  return { ...fromRun(details), config_id: list.find(r => r.id === id)?.config_id ?? '' };
}
export async function getConfigs(): Promise<Config[]> {
  return (await api<ServerConfig[]>('/configs')).map(c => ({ id: String(c.id), name: c.name, yaml: c.yaml }));
}
export async function getPools(): Promise<Pool[]> {
  return (await api<ServerPool[]>('/pools')).map(p => ({
    id: String(p.id), name: p.name, payload: p.payload,
    mode: s(p.payload?.mode || '—'),
  }));
}
export async function getProcedures(): Promise<Procedure[]> {
  return (await api<ServerProcedure[]>('/procedures')).map(p => ({
    id: String(p.id), name: p.path?.split(/[\\/]/).pop() || `${p.kind} #${p.id}`,
    kind: p.kind, source: p.source, code: p.code ?? '',
  }));
}
export async function getStepDetail(id: string, step: string): Promise<StepDetail> {
  const result = await api<Record<string, unknown>>(`/runs/${encodeURIComponent(id)}/steps/${encodeURIComponent(step)}`);
  let params: Record<string, unknown> = {};
  try {
    const decoded: unknown = typeof result.params === 'string' ? JSON.parse(result.params) : result.params;
    params = decoded && typeof decoded === 'object' && !Array.isArray(decoded) ? decoded as Record<string, unknown> : {};
  } catch { params = { raw: result.params }; }
  const status = s(result.status);
  return { step, status, params, code: s(result.code), docstring: '', log: { ...result, status } };
}
export async function getSummary(id: string): Promise<Summary> {
  const raw = await api<ServerSummary>(`/runs/${encodeURIComponent(id)}/summary`);
  return {
    total_apps: n(raw.total_apps), apps_with_diff: n(raw.apps_with_diff),
    apps_decision_changed: n(raw.apps_decision_changed),
    apps_diff_same_decision: n(raw.apps_diff_but_decision_same),
    AR_before: raw.approval_rates?.before_rate ?? null,
    AR_after: raw.approval_rates?.after_rate ?? null,
    quality_issues: n(raw.apps_with_quality_issues),
    decision_matrix: safeArray<ServerCell>(raw.decision_transitions).map(cell => ({
      ...cell, filters: { DECISION_BEFORE: cell.before, DECISION_AFTER: cell.after },
    })),
    reason_matrix: safeArray<ServerCell>(raw.reason_transitions).map(cell => ({
      ...cell, filters: { REASON_TRANSITION: `${cell.before ?? '∅'}→${cell.after ?? '∅'}` },
    })),
    causes: Object.entries(raw.cause_counts ?? {}).map(([cause, count]) => ({ cause, count })),
    llm: null,
    verdict: raw.verdict,
  };
}
interface ServerBlock {
  BLOCK: string; LEVEL: number; APPS_TOTAL: number;
  APPS_CHANGED: number; SHARE: number; ROWS_CHANGED: number;
}
export async function getBlocks(id: string): Promise<Block[]> {
  return (await api<ServerBlock[]>(`/runs/${encodeURIComponent(id)}/blocks`))
    .map(block => ({ ...block }));
}
interface ServerCheck {
  CHECK_ID?: string; LABEL: string; RESULT: string;
  CNT: number; TOTAL: number; METRIC: number | null;
  APP_IDS?: string[]; CONFIDENCE: string; SOURCE: string; ARGUMENT: string;
}
export async function getChecks(id: string): Promise<Check[]> {
  return (await api<ServerCheck[]>(`/runs/${encodeURIComponent(id)}/checks`)).map((c, i) => ({
    ...c, id: `${c.CHECK_ID || c.LABEL}-${i}`, APP_IDS: c.APP_IDS || [],
  }));
}
export async function rerunChecks(id: string): Promise<void> {
  // Server returns {ok:true} immediately; results are updated in a background thread.
  await post(`/runs/${encodeURIComponent(id)}/checks/rerun`, {});
}
export async function getDrilldown(id: string): Promise<Segment[]> {
  // Backend returns ALL rows as an array and supports comparison-table columns ONLY.
  // Fetch once then perform decision/cause filters on the client (2,002 apps are manageable).
  const rows = await post<ServerDrilldown[]>(`/runs/${encodeURIComponent(id)}/drilldown`, {
    rows: [], cols: [], filters: {},
  });
  return rows.map(row => {
    const decisionChanged = !!row.DECISION_TRANSITION && row.DECISION_BEFORE !== row.DECISION_AFTER;
    const reasonParts = (row.REASON_TRANSITION || '').split('→');
    const reason = (value: string | undefined) => value && value !== '∅' ? value : null;
    return {
      APP_ID: s(row.APP_ID), DECISION_BEFORE: row.DECISION_BEFORE,
      DECISION_AFTER: row.DECISION_AFTER, DECISION_CHANGED: decisionChanged,
      REASON_BEFORE: reason(reasonParts[0]), REASON_AFTER: reason(reasonParts[1]),
      N_DIFFS: n(row.N_DIFFS), HAS_DIFF: n(row.N_DIFFS) > 0,
      CAUSE: s(row.CAUSE), QUALITY_ISSUE: null,
    };
  });
}

export function filterSegments(segments: Segment[], filters: Record<string, unknown>): Segment[] {
  return segments.filter(seg => Object.entries(filters).every(([key, val]) => {
    if (key === 'REASON_TRANSITION') {
      const label = `${seg.REASON_BEFORE ?? '∅'}→${seg.REASON_AFTER ?? '∅'}`;
      return label === val;
    }
    const field = seg[key as keyof Segment];
    if (field === undefined) return false;
    const normal = (v: unknown) => typeof v === 'boolean' ? v : v === 0 ? false : v === 1 ? true : v;
    const actual = normal(field), expected = normal(val);
    return Array.isArray(expected) ? expected.includes(actual) : actual === expected;
  }));
}
interface ServerDifference {
  APP_ID: string; PATH: string; VALUE_BEFORE: unknown; VALUE_AFTER: unknown;
  DIFF_FLAG: number; CHANGE_TYPE: string;
}
function printValue(value: unknown): string {
  return value === null || value === undefined ? '—' :
    typeof value === 'object' ? JSON.stringify(value) : String(value);
}
export async function getAppDifferences(id: string, appId: string): Promise<Difference[]> {
  const result = await api<ServerDifference[]>(`/runs/${encodeURIComponent(id)}/apps/${encodeURIComponent(appId)}?diff_only=1`);
  return result.map(row => ({ ...row,
    VALUE_BEFORE: printValue(row.VALUE_BEFORE), VALUE_AFTER: printValue(row.VALUE_AFTER),
  }));
}
export async function getRawComparison(id: string, appId: string): Promise<RawComparison> {
  const raw = await api<{ BEFORE_MASTER?: string; AFTER_BETA?: string }>(
    `/runs/${encodeURIComponent(id)}/apps/${encodeURIComponent(appId)}/raw`);
  return { before: raw.BEFORE_MASTER ?? 'Нет исходного файла', after: raw.AFTER_BETA ?? 'Нет исходного файла' };
}
