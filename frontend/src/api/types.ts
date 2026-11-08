/** UI view models, normalized from the actual Python backend responses in real.ts. */
export type Page<T> = { items: T[]; total: number; offset: number; limit: number };
export type User = { name: string; id?: string; auth_mode?: 'basic' | string };
export type RunStage = {
  step: string;
  status: string;
  progress: number;
  started_by?: string;
  duration_ms: number | null;
  rows_in?: number | null;
  rows_out?: number | null;
  message?: string;
};
export type Run = {
  id: string;
  config_id: string;
  dataset_id?: string | number | null;
  started_by: string;
  created_at: string;
  finished_at: string | null;
  status: string;
  progress: number | null;
  stages: RunStage[];
  error?: string | null;
};
export type Config = { id: string; name: string; yaml: string };
export type Pool = { id: string; name: string; payload: Record<string, unknown>; mode: string };
export type Procedure = { id: string; name: string; kind: string; source: string; code: string };
export type MatrixCell = { before: string | null; after: string | null; count: number; filters: Record<string, unknown> };
export type Summary = {
  total_apps: number;
  apps_with_diff: number;
  apps_decision_changed: number;
  apps_diff_same_decision: number;
  AR_before: number | null;
  AR_after: number | null;
  quality_issues: number;
  decision_matrix: MatrixCell[];
  reason_matrix: MatrixCell[];
  causes: { cause: string; count: number }[];
  llm: unknown;
  verdict?: { status: string; reason_codes: string[]; disclaimer: string };
};
export type Segment = {
  REASON_TRANSITION?: string | null;
  APP_ID: string;
  DECISION_BEFORE: string | null;
  DECISION_AFTER: string | null;
  DECISION_CHANGED: boolean;
  REASON_BEFORE: string | null;
  REASON_AFTER: string | null;
  N_DIFFS: number;
  HAS_DIFF: boolean;
  CAUSE: string;
  QUALITY_ISSUE: number | null;
};
export type Difference = {
  APP_ID: string;
  ARRAY_KEY?: string | null;
  PATH: string;
  VALUE_BEFORE: string;
  VALUE_AFTER: string;
  ADJUSTED_BEFORE?: string | null;
  ADJUSTED_AFTER?: string | null;
  DIFF_FLAG: number;
  CHANGE_TYPE: string;
};
export type Block = {
  BLOCK: string; LEVEL: number; APPS_TOTAL: number; APPS_CHANGED: number;
  SHARE: number; ROWS_CHANGED: number;
};
export type Check = {
  id: string;
  CHECK_ID: string; ROW_ID: string;
  LABEL: string; RESULT: string;
  CNT: number; TOTAL: number; METRIC: number | string | null;
  APP_IDS: string[]; CONFIDENCE: string; SOURCE: string; ARGUMENT: string;
};
export type StepDetail = {
  step: string; status: string; docstring: string; code: string;
  params: Record<string, unknown>;
  log: Record<string, unknown> & { status: string };
};
export type RawComparison = { before: string; after: string };

export type CheckAppsPage = {
  check_id: string; row_id: string; total: number; declared_cnt: number;
  truncated: boolean; has_more: boolean; items: string[]; limit: number;
  offset: number; source: 'APP_IDS' | 'FILTERS';
};
