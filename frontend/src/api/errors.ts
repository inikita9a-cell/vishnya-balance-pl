/** Convert structured FastAPI failures to useful text, preserving unknown details. */
function readable(message: string): string {
  const missing = 'Dataset path does not exist:';
  if (message.startsWith(missing)) {
    return `Датасет не найден: ${message.slice(missing.length).trim()}. Укажите существующий dataset.path в настройках и сохраните конфигурацию.`;
  }
  if (message === 'A checks job is already queued/running for this run') {
    return 'Проверки этого запуска уже выполняются или ожидают выполнения. Дождитесь завершения и обновите таблицу.';
  }
  if (message === 'Invalid run config' || message === 'Invalid config') return 'Проверьте настройки конфигурации.';
  if (message === 'login required') return 'Необходимо войти в приложение.';
  return message;
}

export function formatApiError(data: unknown, fallback: string): string {
  if (typeof data === 'string') return readable(data);
  if (!data || typeof data !== 'object') return fallback;
  if (Array.isArray(data)) {
    const messages = data.map(item => formatApiError(item, '')).filter(Boolean);
    return messages.length ? messages.join('; ') : fallback;
  }
  const item = data as Record<string, unknown>;
  const report = item.report;
  if (report && typeof report === 'object') {
    const r = report as Record<string, unknown>;
    const errors = Array.isArray(r.errors) ? r.errors : [];
    const warnings = Array.isArray(r.warnings) ? r.warnings : [];
    // This function handles failed responses only, never successful warnings.
    if (errors.length || warnings.length) return formatApiError([...errors, ...warnings], fallback);
  }
  if ('detail' in item) return formatApiError(item.detail, fallback);
  const message = item.message ?? item.msg;
  return typeof message === 'string' ? readable(message) : fallback;
}
