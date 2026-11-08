import type { SankeySeriesOption } from 'echarts/charts';
import type { TooltipComponentOption } from 'echarts/components';
import type { ComposeOption } from 'echarts/core';
import type { FlowLink, FlowNode, SankeyData } from '../../api/sankey';
import { theme } from '../../styles/Theme';
type Option = ComposeOption<SankeySeriesOption | TooltipComponentOption>;

export function sankeyOption(data: SankeyData): Option {
  const labels = new Map(data.nodes.map(node => [node.name, node.label]));
  return {
      animation: false,
      tooltip: { trigger: 'item', renderMode: 'richText', confine: true, formatter: params => {
        const item = (Array.isArray(params) ? params[0] : params).data as FlowLink | FlowNode;
        return 'source' in item
          ? `${labels.get(item.source)} → ${labels.get(item.target)}\n${item.value.toLocaleString('ru-RU')} заявок`
          : `${labels.get(item.name)}\nОткрыть заявки`;
      } },
      series: [{ type: 'sankey', left: 20, right: 180, top: 28, bottom: 28,
        nodeWidth: 18, nodeGap: 14, draggable: false, layoutIterations: 32,
        data: data.nodes.map(({ name, depth, filters }) => ({ name, depth, filters })), links: data.links.map(link => ({ ...link })),
        label: { fontFamily: theme.fonts.interface, fontSize: 12, color: theme.colors.darkBgColor,
          width: 160, overflow: 'truncate', formatter: params => labels.get(params.name) ?? params.name },
        lineStyle: { color: 'gradient', opacity: 0.28, curveness: 0.5 },
        emphasis: { focus: 'adjacency', lineStyle: { opacity: 0.65 } },
        levels: [
          { depth: 0, itemStyle: { color: '#a1a5b3' } },
          { depth: 1, itemStyle: { color: theme.colors.accent } },
          { depth: 2, itemStyle: { color: '#efbba7' } },
        ],
      }],
    };
}
