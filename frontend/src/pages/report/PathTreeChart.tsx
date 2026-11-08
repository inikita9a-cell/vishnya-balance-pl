import { useEffect, useMemo, useRef, useState } from 'react';
import * as echarts from 'echarts/core';
import { TreeChart, type TreeSeriesOption } from 'echarts/charts';
import { TooltipComponent, type TooltipComponentOption } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { LabelLayout } from 'echarts/features';
import styled from 'styled-components';
import type { ExplorerField } from '../../api/explorer.types';
import { Field, Muted, QuietButton, TextButton } from '../../components/Ui';
import { theme } from '../../styles/Theme';
import type { PathNode } from './treeModel';
import { CHILD_PAGE, indexPaths, projectChart, type ChartNode } from './chartTreeModel';

echarts.use([TreeChart, TooltipComponent, CanvasRenderer, LabelLayout]);
type Option = echarts.ComposeOption<TreeSeriesOption | TooltipComponentOption>;
type Props = { roots: PathNode[]; onSelect: (field: ExplorerField) => void };

export default function PathTreeChart({ roots, onSelect }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.EChartsType | null>(null);
  const handlers = useRef({ click: (_path: string) => {} });
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [focusPath, setFocusPath] = useState<string>();
  const [activePath, setActivePath] = useState<string>();
  const [page, setPage] = useState(0);
  const [search, setSearch] = useState('');
  const [searchPage, setSearchPage] = useState(0);
  const index = useMemo(() => indexPaths(roots), [roots]);
  const matches = useMemo(() => search.trim() ? [...index.values()].filter(node => node.path.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())) : [], [index, search]);
  const focus = focusPath === undefined ? undefined : index.get(focusPath);
  const active = activePath === undefined ? undefined : index.get(activePath);
  const projection = useMemo(() => projectChart(roots, focus, expanded, page), [roots, focus, expanded, page]);
  const enter = (node?: PathNode) => { setFocusPath(node?.path); setPage(0); setExpanded(new Set()); };
  handlers.current.click = path => {
    const node = index.get(path);
    if (!node) return;
    setActivePath(path);
    if (node.field) onSelect(node.field);
    if (node.children.length && path !== focusPath) setExpanded(previous => {
      const next = new Set(previous);
      if (next.has(path)) next.delete(path); else next.add(path);
      return next;
    });
  };
  useEffect(() => {
    if (!host.current) return;
    const instance = echarts.init(host.current, undefined, { renderer: 'canvas' });
    chart.current = instance;
    const click = (event: unknown) => {
      const data = (event as { data?: ChartNode }).data;
      if (data?.path !== undefined) handlers.current.click(data.path);
    };
    instance.on('click', click);
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(host.current);
    return () => { observer.disconnect(); instance.off('click', click); instance.dispose(); chart.current = null; };
  }, []);

  useEffect(() => {
    type Datum = NonNullable<TreeSeriesOption['data']>[number];
    const decorate = (node: ChartNode, root = false): Datum => ({
      ...node,
      name: `${node.name}${node.branch && !root ? expanded.has(node.path!) ? ' −' : ' +' : ''}`,
      symbol: root ? 'roundRect' : node.attribute ? 'circle' : 'emptyCircle',
      symbolSize: root ? 15 : node.attribute ? 9 : 11,
      itemStyle: { color: root || node.path === activePath ? theme.colors.accent : node.attribute ? theme.colors.darkBgColor : '#fff', borderColor: node.path === activePath ? theme.colors.accent : theme.colors.darkBgColor, borderWidth: 1.5 },
      label: { color: node.path === activePath ? theme.colors.accent : theme.colors.darkBgColor, fontWeight: root || node.path === activePath ? 700 : 400 },
      children: node.children?.map(child => decorate(child)),
    });
    const option: Option = {
      backgroundColor: '#fff', animationDurationUpdate: 200,
      tooltip: { trigger: 'item', renderMode: 'richText', confine: true, formatter: params => {
        const item = (Array.isArray(params) ? params[0] : params).data as ChartNode;
        const field = item.path === undefined ? undefined : index.get(item.path)?.field;
        return `${item.path ?? 'Атрибуты'}${field ? `\nЗаявок с изменениями: ${field.changedAppsCount}\nЗаявок с атрибутом: ${field.appsCount}${field.hasArrayInstances ? '\nМассив: все экземпляры' : ''}` : '\nНавигационная ветка'}`;
      } },
      series: [{ id: 'paths', type: 'tree', data: [decorate(projection.root, true)], orient: 'LR',
        top: 28, bottom: 28, left: 100, right: 150, roam: true, scaleLimit: { min: 0.25, max: 4 },
        initialTreeDepth: -1,
        // React controls expansion so ECharts never receives thousands of hidden descendants.
        expandAndCollapse: false, edgeShape: 'curve', edgeForkPosition: '50%',
        lineStyle: { color: '#bfc0c8', width: 1.3, curveness: 0.5 },
        label: { position: 'left', align: 'right', verticalAlign: 'middle', fontFamily: theme.fonts.interface, fontSize: 12, width: 120, overflow: 'truncate' },
        leaves: { label: { position: 'right', align: 'left' } },
        labelLayout: { hideOverlap: true }, emphasis: { focus: 'descendant' },
      }],
    };
    chart.current?.setOption(option, { notMerge: true });
  }, [projection, activePath, expanded, index]);

  return <>
    <label>Поиск по PATH<Field type="search" value={search} placeholder="Название или полный путь" onChange={event => { setSearch(event.target.value); setSearchPage(0); }} /></label>
    {search.trim() && <Results aria-label="Результаты поиска">
      <Muted>Найдено: {matches.length}</Muted>
      {matches.slice(searchPage * 20, (searchPage + 1) * 20).map(node => <TextButton key={node.path} type="button" onClick={() => {
        setActivePath(node.path); enter(node); if (node.field) onSelect(node.field);
      }}>{node.path} →</TextButton>)}
      <Controls><QuietButton disabled={!searchPage} onClick={() => setSearchPage(value => value - 1)}>Назад</QuietButton><QuietButton disabled={(searchPage + 1) * 20 >= matches.length} onClick={() => setSearchPage(value => value + 1)}>Далее</QuietButton></Controls>
    </Results>}
    <Controls>
      <QuietButton type="button" onClick={() => { enter(); setActivePath(undefined); }}>Всё дерево / сброс вида</QuietButton>
      {focus && <QuietButton type="button" onClick={() => enter(index.get(focus.path.split('.').slice(0, -1).join('.')))}>На уровень выше</QuietButton>}
      {active?.children.length ? <QuietButton type="button" onClick={() => enter(active)}>Открыть выбранную ветку</QuietButton> : null}
    </Controls>
    <Muted>{focus ? `Ветка: ${focus.path}` : 'Все атрибуты'} · клик раскрывает ветку и выбирает атрибут; колесо — масштаб, перетаскивание — перемещение.</Muted>
    <Canvas ref={host} role="img" aria-label="Диаграмма атрибутов слева направо. Для выбора с клавиатуры используйте поиск по PATH." />
    {projection.omitted && <Muted>Детализация ограничена: до 30 детей на ветку и 180 узлов. Откройте нужную ветку отдельно или найдите PATH поиском.</Muted>}
    {projection.totalChildren > CHILD_PAGE && <Controls>
      <QuietButton disabled={!page} onClick={() => setPage(value => value - 1)}>Предыдущие ветки</QuietButton>
      <Muted>{page * CHILD_PAGE + 1}–{Math.min((page + 1) * CHILD_PAGE, projection.totalChildren)} из {projection.totalChildren}</Muted>
      <QuietButton disabled={(page + 1) * CHILD_PAGE >= projection.totalChildren} onClick={() => setPage(value => value + 1)}>Следующие ветки</QuietButton>
    </Controls>}
  </>;
}

const Canvas = styled.div`width: 100%; height: 620px; margin: 16px 0; border: 1px solid ${theme.colors.surface}; border-radius: 12px; overflow: hidden;`;
const Controls = styled.div`display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 12px 0;`;
const Results = styled.div`display: grid; gap: 6px; max-height: 280px; overflow: auto; padding: 12px; button { text-align: left; overflow-wrap: anywhere; }`;
