import type { Check } from '../../api/types';

const builtins = new Set(['ar_drop_by_product', 'attribute_new_loss', 'external_score_drift', 'stop_factor_disappeared', 'target_model_changed']);

export function checkOutcome(check: Pick<Check, 'CHECK_ID' | 'RESULT'>): {
  label: string; tone: 'good' | 'busy' | 'bad'; detail: string;
} {
  if (check.RESULT === 'ERROR') return {
    label: 'Ошибка выполнения', tone: 'bad', detail: 'Проверка не смогла получить результат. Это техническая ошибка.',
  };
  if (builtins.has(check.CHECK_ID)) {
    if (check.RESULT === 'FAIL') return {
      label: 'Есть сигнал', tone: 'busy', detail: 'Обнаружено изменение или превышение заданного порога. Требуется оценка аналитика; проверка выполнилась.',
    };
    if (check.RESULT === 'PASS') return {
      label: 'Сигнал не выявлен', tone: 'good', detail: 'Условие бизнес-проверки не сработало. Это не означает отсутствия любых изменений в заявках.',
    };
  }
  if (check.RESULT === 'PASS') return { label: 'Условие выполнено', tone: 'good', detail: 'Пользовательская проверка вернула PASS.' };
  if (check.RESULT === 'FAIL') return { label: 'Условие нарушено', tone: 'busy', detail: 'Пользовательская проверка вернула FAIL; это не ошибка выполнения.' };
  return { label: `Неизвестный результат: ${check.RESULT || 'не указан'}`, tone: 'bad', detail: 'Не удалось интерпретировать результат проверки.' };
}

export function checkMetricLabel(check: Pick<Check, 'CHECK_ID'>): string {
  return check.CHECK_ID === 'ar_drop_by_product'
    ? 'Относительное падение доли одобрений по продукту. Это не доля заявок из соседнего столбца.'
    : 'Метрика проверки; для стандартных проверок состава атрибутов, модели и стоп-фактора — доля затронутых заявок.';
}

export function confidenceLabel(value: string): string {
  return ({ HIGH: 'Высокая', LOW: 'Низкая', MEDIUM: 'Средняя' } as Record<string, string>)[value] ?? value;
}
