import { api } from './client';

export type ObservedValue = { present: boolean; value: string | null };
export type ApplicationExplanation = {
  run_id: string; app_id: string;
  decision: { before: string | null; after: string | null; comparable: boolean; changed: boolean | null };
  reason: { before: string | null; after: string | null; changed: boolean | null };
  comparison: { complete: boolean; observed_changes: number; has_quality_issues: boolean };
  interpretation: { code: string; headline: string; detail: string; source: string; source_label: string; disclaimer: string };
  changes: { total: number; filtered_total: number; limit: number; offset: number;
    rows: { PATH: string; ARRAY_KEY: string; CHANGE_TYPE: string; BEFORE: ObservedValue; AFTER: ObservedValue }[] };
  quality: { total: number; truncated: boolean; items: { SOURCE: string; ISSUE: string; PATH: string; DETAILS: string }[] };
};

export function observedValue(value: ObservedValue): string {
  if (!value.present) return 'Атрибут отсутствует';
  if (value.value === null) return 'Нет данных';
  if (value.value === '') return '"" (пустая строка)';
  if (value.value === 'NULL') return 'NULL (значение)';
  return value.value;
}

export function getApplicationExplanation(runId: string, appId: string, offset = 0): Promise<ApplicationExplanation> {
  return api(`/runs/${encodeURIComponent(runId)}/apps/${encodeURIComponent(appId)}/explanation?limit=200&offset=${offset}`);
}
