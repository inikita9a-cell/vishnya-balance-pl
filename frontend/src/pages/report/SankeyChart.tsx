import { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import { SankeyChart } from 'echarts/charts';
import { TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import styled from 'styled-components';
import type { FlowLink, FlowNode, SankeyData } from '../../api/sankey';
import { theme } from '../../styles/Theme';

echarts.use([SankeyChart, TooltipComponent, CanvasRenderer]);
import { sankeyOption, sankeyHeight } from './sankeyModel';

export default function DecisionSankey({ data, onSelect }: {
  data: SankeyData; onSelect: (filters: Record<string, unknown>) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.EChartsType | null>(null);
  const select = useRef(onSelect);
  select.current = onSelect;
  // Give every node room; scroll for large reason sets, never drop applications.
  const height = sankeyHeight(data);
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
    <Headings><span>Исходная стратегия</span><span>Новая стратегия</span><span>Основание</span></Headings>
    <Canvas ref={host} style={{ height }} role="img" aria-label="Потоки решений до и после изменения стратегии. Точный список потоков доступен под диаграммой." />
  </Scroll>;
}

const Scroll = styled.div`max-height: 740px; overflow: auto; margin-top: 16px; border: 1px solid #eeeef2; border-radius: 14px;`;
const Headings = styled.div`min-width: 920px; display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) 240px; padding: 20px 24px 4px; box-sizing: border-box; font: 600 11px ${theme.fonts.interface}; letter-spacing: .025em; color: #8b8b95;`;
const Canvas = styled.div`width: 100%; min-width: 920px;`;
