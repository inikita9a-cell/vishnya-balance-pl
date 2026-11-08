export type ExplorerScalar = string | number | boolean | null;
export type ExplorerDimension =
  | 'PATH' | 'PREFIX' | 'CLASS' | 'SUFFIX' | 'KEY' | 'ARRAY_KEY' | 'DEPTH'
  | 'CHANGE_TYPE' | 'DIFF_FLAG' | 'ADJUSTED_BEFORE' | 'ADJUSTED_AFTER'
  | 'VALUE_BEFORE' | 'VALUE_AFTER' | 'DECISION_BEFORE' | 'DECISION_AFTER'
  | 'DECISION_TRANSITION' | 'REASON_TRANSITION' | 'CAUSE' | 'PARTNER_TYPE'
  | 'PRODUCTS' | 'TOP_OFFER_BEFORE' | 'TOP_OFFER_AFTER' | 'QUALITY_ISSUE' | 'COMPARISON_COMPLETE';
export type ExplorerFilters = Partial<Record<ExplorerDimension, ExplorerScalar | ExplorerScalar[]>>;
export interface ExplorerField {
  path: string;
  depth: number | null;
  appsCount: number;
  changedAppsCount: number;
  hasArrayInstances: boolean;
}
export interface ExplorerFieldsResponse { fields: ExplorerField[]; dimensions: ExplorerDimension[] }
export interface ExplorerQueryRequest {
  groupBy: ExplorerDimension[];
  filters?: ExplorerFilters;
  includeUnchanged?: boolean;
  limit?: number;
  offset?: number;
}
export interface ExplorerQueryRow {
  values: Partial<Record<ExplorerDimension, ExplorerScalar>>;
  appsCount: number;
  occurrencesCount: number;
  drilldownFilters: ExplorerFilters;
}
export interface ExplorerQueryResponse {
  totalGroups: number; rows: ExplorerQueryRow[]; limit: number; offset: number;
}
export interface ExplorerAppsRequest { filters: ExplorerFilters; limit?: number; offset?: number }
export interface ExplorerAppsResponse {
  total: number; limit: number; offset: number;
  items: {
    APP_ID: string; DECISION_BEFORE: string | null; DECISION_AFTER: string | null;
    N_DIFFS: number; COMPARISON_COMPLETE: number;
  }[];
}
