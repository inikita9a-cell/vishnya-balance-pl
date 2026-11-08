import { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import { SankeyChart } from 'echarts/charts';
import { TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import styled from 'styled-components';
import type { FlowLink, FlowNode, SankeyData } from '../../api/sankey';
import { theme } from '../../styles/Theme';

echarts.use([SankeyChart, TooltipComponent, CanvasRenderer]);
import { sankeyOption } from './sankeyModel';

export default function DecisionSankey({ data, onSelect }: {
  data: SankeyData; onSelect: (filters: Record<string, unknown>) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.EChartsType | null>(null);
  const select = useRef(onSelect);
  select.current = onSelect;
  const largestColumn = Math.max(1, ...[0, 1, 2].map(depth => data.nodes.filter(node => node.depth === depth).length));
  // Give every node room; scroll for large reason sets, never drop applications.
  const height = Math.max(430, largestColumn * 27 + 100);
  useEffect(() => {
    if (!host.current) return;
    const instance = echarts.init(host.current, undefined, { renderer: 'canvas' });
    chart.current = instance;
    const click = (event: unknown) => {
      const item = (event as { data?: FlowLink | FlowNode }).data;
      if (item?.filters) select.current(item.filters);
    };
    instance.on('click', click);
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(host.current);
    return () => { observer.disconnect(); instance.off('click', click); instance.dispose(); chart.current = null; };
  }, []);
  useEffect(() => {
    const option = sankeyOption(data);
    chart.current?.setOption(option, { notMerge: true });
    chart.current?.resize();
  }, [data, height]);
  return <Scroll>
    <Headings><span>Исходная стратегия</span><span>Новая стратегия</span><span>Переход основания</span></Headings>
    <Canvas ref={host} style={{ height }} role="img" aria-label="Потоки решений до и после изменения стратегии. Точный список потоков доступен под диаграммой." />
  </Scroll>;
}

const Scroll = styled.div`max-height: 720px; overflow: auto; margin-top: 18px; border: 1px solid #eeeef2; border-radius: 12px;`;
const Headings = styled.div`min-width: 760px; display: flex; justify-content: space-between; gap: 16px; padding: 16px 22px 0; font: 600 12px ${theme.fonts.interface}; color: #777782;`;
const Canvas = styled.div`width: 100%; min-width: 760px;`;
