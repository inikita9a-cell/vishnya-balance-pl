import type { Config, Run } from './types';

/** Backend does NOT expose dataset_id or a run config snapshot through its REST API. */
export type DatasetReference = { id: string | null; path: string | null; label: string; source: 'id' | 'path' | 'unknown' };

function pathFromYaml(yaml: string): string | null {
  // This is a display-only extraction of dataset.path, not a YAML parser.
  const section = yaml.match(/^dataset:\s*(?:#.*)?\r?\n((?:[ \t]+[^\r\n]*\r?\n?)*)/m)?.[1];
  const value = section?.match(/^[ \t]+path:\s*(.+?)\s*(?:#.*)?$/m)?.[1].trim();
  return value ? value.replace(/^(?:"(.*)"|'(.*)')$/, '$1$2') : null;
}

export function datasetForRun(run: Run, configs: Config[] = []): DatasetReference {
  if (run.dataset_id !== undefined && run.dataset_id !== null && String(run.dataset_id).trim()) {
    return { id: String(run.dataset_id), path: null, label: String(run.dataset_id), source: 'id' };
  }
  const path = pathFromYaml(configs.find(c => c.id === run.config_id)?.yaml ?? '');
  return path
    ? { id: null, path, label: path, source: 'path' }
    : { id: null, path: null, label: 'Не указан', source: 'unknown' };
}
