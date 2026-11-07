export const dateTime = (value?: string | null) => value ? new Date(/(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`).toLocaleString('ru-RU', {
  day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'
}) : '—';
export const decision = (value?: string | null) => ({ APPROVE: 'Одобрено', REJECT: 'Отказ' } as Record<string, string>)[value ?? ''] ?? (value || '—');
export const status = (value: string) => ({
  done: 'Завершён', running: 'Выполняется', queued: 'Ожидает', failed: 'Ошибка',
  COMPLETED: 'Завершён', RUNNING: 'Выполняется', PENDING: 'Ожидает', FAILED: 'Ошибка'
} as Record<string, string>)[value] ?? value;
export const isRunDone = (value: string) => value === 'done';
export const isRunActive = (value: string) => value === 'queued' || value === 'running';
export const stageLabel = (key: string) => ({
  s1_discover: 'Поиск данных', s2_s4_normalize: 'Нормализация', s5_union: 'Объединение',
  s6_check_keys: 'Проверка ключей', s7_compare: 'Сравнение', s8_quality: 'Контроль качества',
  s9_segments: 'Сегментация', s10_blocks: 'Анализ блоков', s11_facts: 'Формирование витрины',
  s12_checks: 'Бизнес-проверки', s13_summary: 'Сводка', s15_report: 'HTML-отчёт',
  discover: 'Поиск данных', compare: 'Сравнение', quality: 'Контроль качества',
  segments: 'Сегментация', blocks: 'Анализ блоков', facts: 'Формирование витрины',
  checks: 'Проверки', summary: 'Сводка', report_html: 'Протокол'
} as Record<string, string>)[key] ?? key;
export const causeLabel = (key: string) => ({
  LOGIC: 'Логика стратегии', BOTH: 'Логика и входные данные',
  INPUT_DATA: 'Входные данные', NONE: 'Без изменений'
} as Record<string, string>)[key] ?? key;
