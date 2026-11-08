import type { FlowLink, FlowNode, SankeyData } from '../../api/sankey';

const decision = (value: unknown) => value == null ? 'не указано' : value === '' ? 'пустая строка'
  : ({ APPROVE: 'Одобрено', REJECT: 'Отказ' } as Record<string, string>)[String(value)] ?? String(value);
const code = (value: string, max = 20) => value.length <= max ? value
  : `${value.slice(0, Math.floor((max - 1) / 2))}…${value.slice(-Math.ceil((max - 1) / 2))}`;

export function reasonLabel(value: unknown): { short: string; detail: string } {
  if (value == null) return { short: 'Нет сведений', detail: 'В результатах нет сведений о переходе основания.' };
  if (value === '') return { short: 'Пустая запись', detail: 'В результатах сохранена пустая строка перехода основания.' };
  const parts = String(value).split('→');
  if (parts.length !== 2) return { short: String(value), detail: `Основание: ${String(value)}` };
  const [before, after] = parts;
  const absent = (text: string) => text === '∅';
  if (absent(before) && absent(after)) return {
    short: 'Не указано', detail: 'Основание не указано ни в исходной, ни в новой стратегии.',
  };
  if (before === after) return { short: `Сохранено · ${code(before)}`, detail: `Основание сохранилось: ${before}.` };
  if (absent(before)) return { short: `Новое · ${code(after)}`, detail: `Ранее основание не было указано. После: ${after}.` };
  if (absent(after)) return { short: `Не указано · ${code(before)}`, detail: `До: ${before}. В новой стратегии основание не указано.` };
  return { short: `Смена · ${code(before, 12)} → ${code(after, 12)}`, detail: `Основание изменилось. До: ${before}. После: ${after}.` };
}

export function nodeLabel(node: FlowNode): { short: string; detail: string } {
  if (node.depth === 2) return reasonLabel(node.filters.REASON_TRANSITION);
  const before = node.depth === 0;
  const value = decision(node.filters[before ? 'DECISION_BEFORE' : 'DECISION_AFTER']);
  return { short: value, detail: `Решение ${before ? 'исходной' : 'новой'} стратегии: ${value}.` };
}

export function flowLabel(data: SankeyData, link: FlowLink): string {
  const source = data.nodes.find(node => node.name === link.source);
  const target = data.nodes.find(node => node.name === link.target);
  if (!source || !target) return 'Поток заявок';
  if (source.depth === 0 && target.depth === 1) {
    const before = source.filters.DECISION_BEFORE, after = target.filters.DECISION_AFTER;
    return before === after ? `Решение сохранилось: ${decision(before)}.`
      : `Решение изменилось: ${decision(before)} → ${decision(after)}.`;
  }
  return `Решение после: ${decision(source.filters.DECISION_AFTER)}. ${nodeLabel(target).detail}`;
}
