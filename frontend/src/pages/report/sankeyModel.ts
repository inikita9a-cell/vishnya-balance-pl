import type { SankeySeriesOption } from 'echarts/charts';
import type { TooltipComponentOption } from 'echarts/components';
import type { ComposeOption } from 'echarts/core';
import type { FlowLink, FlowNode, SankeyData } from '../../api/sankey';
import { theme } from '../../styles/Theme';
import { nodeLabel, flowLabel } from './sankeyLabels';
type Option = ComposeOption<SankeySeriesOption | TooltipComponentOption>;

export function sankeyHeight(data: SankeyData): number {
  const largestColumn = Math.max(1, ...[0, 1, 2].map(depth => data.nodes.filter(node => node.depth === depth).length));
  return Math.max(460, largestColumn * 38 + 64);
}

export function sankeyOption(data: SankeyData): Option {
  const labels = new Map(data.nodes.map(node => [node.name, nodeLabel(node)]));
  const nodeCounts = new Map(data.nodes.map(node => [node.name, data.links
    .filter(link => node.depth === 0 ? link.source === node.name : link.target === node.name)
    .reduce((total, link) => total + link.value, 0)]));
  return {
      animation: false,
      tooltip: { trigger: 'item', renderMode: 'richText', confine: true, formatter: params => {
        const item = (Array.isArray(params) ? params[0] : params).data as FlowLink | FlowNode;
        return 'source' in item
          ? `${flowLabel(data, item)}\n${item.value.toLocaleString('ru-RU')} заявок\nНажмите, чтобы открыть список`
          : `${labels.get(item.name)?.detail}\n${(nodeCounts.get(item.name) ?? 0).toLocaleString('ru-RU')} заявок\nНажмите, чтобы открыть список`;
      } },
      series: [{ type: 'sankey', left: 24, right: 240, top: 24, bottom: 24,
        nodeWidth: 16, nodeGap: 24, draggable: false, layoutIterations: 32,
        data: data.nodes.map(({ name, depth, filters }) => ({ name, depth, filters })), links: data.links.map(link => ({ ...link })),
        label: { fontFamily: theme.fonts.interface, fontSize: 12, lineHeight: 18, color: theme.colors.darkBgColor,
          width: 216, overflow: 'truncate', formatter: params => (labels.get(params.name)?.short ?? params.name).replace(/[\r\n]+/g, ' ') },
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
