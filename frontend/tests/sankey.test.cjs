const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function load(file, dependencies) {
  const code = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src', file), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const exports = {};
  vm.runInNewContext(code, { exports, require: id => {
    assert.ok(id in dependencies, `unexpected dependency ${id}`);
    return dependencies[id];
  } });
  return exports;
}

test('sankey requests the actual run API with a safely encoded run ID', async () => {
  const calls = [];
  const api = load('api/sankey.ts', { './client': { post: async (...args) => { calls.push(args); return { nodes: [], links: [] }; } } });
  await api.getSankey('run /Ж');
  assert.equal(calls[0][0], '/runs/run%20%2F%D0%96/sankey');
  assert.equal(JSON.stringify(calls[0][1]), '{"filters":{}}');
});

test('actual ECharts Sankey renders unchanged decisions and preserves click filters', async () => {
  const { sankeyOption } = load('pages/report/sankeyModel.ts', { './sankeyLabels': load('pages/report/sankeyLabels.ts', {}), '../../styles/Theme': {
    theme: { fonts: { interface: 'sans-serif' }, colors: { accent: '#ff593b', darkBgColor: '#222' } },
  } });
  const data = { nodes: [
    {name:'before:approve', label:'Одобрено', depth:0, filters:{DECISION_BEFORE:'APPROVE'}},
    {name:'after:approve', label:'Одобрено', depth:1, filters:{DECISION_AFTER:'APPROVE'}},
    {name:'reason:null', label:'Нет данных', depth:2, filters:{DECISION_AFTER:'APPROVE', REASON_TRANSITION:null}},
  ], links: [
    {source:'before:approve', target:'after:approve', value:2002, filters:{DECISION_BEFORE:'APPROVE',DECISION_AFTER:'APPROVE'}},
    {source:'after:approve', target:'reason:null', value:2002, filters:{DECISION_AFTER:'APPROVE',REASON_TRANSITION:null}},
  ] };
  const option = sankeyOption(data);
  const series = option.series[0];
  assert.strictEqual(series.data[2].filters, data.nodes[2].filters);
  assert.strictEqual(series.links[1].filters, data.links[1].filters);
  assert.equal(series.links[0].value, 2002);
  assert.equal(typeof series.data[0].label, 'undefined'); // ECharts reserves label for styling.
  assert.match(option.tooltip.formatter({data:data.links[0]}), /2002|2[\s\u00a0\u202f]002/);
  const echarts = await import('echarts/core');
  const {SankeyChart} = await import('echarts/charts');
  const {SVGRenderer} = await import('echarts/renderers');
  const {TooltipComponent} = await import('echarts/components');
  echarts.use([SankeyChart, SVGRenderer, TooltipComponent]);
  const chart = echarts.init(null, null, {renderer:'svg',ssr:true,width:1000,height:450});
  try {
    chart.setOption(option);
    const svg = chart.renderToSVGString();
    assert.ok(svg.includes('<path'));
    assert.ok(svg.includes('Одобрено'));
    assert.ok(!svg.includes('NaN'));
  } finally { chart.dispose(); }
});

test('reason labels explain missing, retained, added and removed reasons without changing filters', () => {
  const {reasonLabel,nodeLabel,flowLabel}=load('pages/report/sankeyLabels.ts',{});
  assert.match(reasonLabel('∅→∅').detail,/не указано ни в исходной, ни в новой/);
  assert.match(reasonLabel('AGELOW@21→AGELOW@21').detail,/сохранилось: AGELOW@21/);
  assert.match(reasonLabel('∅→DOCS_EXPIRED').short,/Новое/);
  assert.match(reasonLabel('AGELOW@21→∅').detail,/В новой стратегии основание не указано/);
  assert.match(reasonLabel('A→B').detail,/изменилось/);
  assert.notEqual(reasonLabel(null).short,reasonLabel('').short);
  const node={name:'reason',depth:2,label:'AGELOW@21→AGELOW@21',filters:{REASON_TRANSITION:'AGELOW@21→AGELOW@21'}};
  assert.match(nodeLabel(node).short,/Сохранено/);
  assert.equal(node.filters.REASON_TRANSITION,'AGELOW@21→AGELOW@21');
  const before={name:'b',depth:0,filters:{DECISION_BEFORE:'REJECT'}};
  const after={name:'a',depth:1,filters:{DECISION_AFTER:'REJECT'}};
  assert.equal(flowLabel({nodes:[before,after]}, {source:'b',target:'a'}),'Решение сохранилось: Отказ.');
  assert.notEqual(nodeLabel(before).detail,nodeLabel(after).detail);
  assert.match(reasonLabel('MFO_ZAIMER_2026_VERY_LONG_REASON_15→MFO_ZAIMER_2026_VERY_LONG_REASON_15').short,/15$/);
});

test('registry retains raw reason transition including SQL NULL and empty string', async () => {
  const rows = [null, '', 'NULL', 'A→B'].map((reason,i) => ({APP_ID:String(i), DECISION_BEFORE:'APPROVE',DECISION_AFTER:'REJECT',REASON_TRANSITION:reason,N_DIFFS:1}));
  const api = load('api/real.ts', {'./client': {post:async()=>rows}});
  const mapped = await api.getDrilldown('r');
  for (const reason of [null,'','NULL','A→B']) {
    const selected = api.filterSegments(mapped,{REASON_TRANSITION:reason});
    assert.equal(selected.length,1);
    assert.equal(selected[0].REASON_TRANSITION,reason);
  }
});

test('many tiny reason flows keep single-line labels separated at narrow and wide widths', async () => {
  const {sankeyOption,sankeyHeight}=load('pages/report/sankeyModel.ts',{
    './sankeyLabels':load('pages/report/sankeyLabels.ts',{}),
    '../../styles/Theme':{theme:{fonts:{interface:'sans-serif'},colors:{accent:'#ff593b',darkBgColor:'#30303a'}}},
  });
  const nodes=[
    {name:'before-a',depth:0,filters:{DECISION_BEFORE:'APPROVE'}},
    {name:'before-r',depth:0,filters:{DECISION_BEFORE:'REJECT'}},
    {name:'after-a',depth:1,filters:{DECISION_AFTER:'APPROVE'}},
    {name:'after-r',depth:1,filters:{DECISION_AFTER:'REJECT'}},
  ];
  const links=[
    {source:'before-a',target:'after-a',value:400,filters:{}},
    {source:'before-a',target:'after-r',value:600,filters:{}},
    {source:'before-r',target:'after-r',value:1002,filters:{}},
  ];
  for(let i=0;i<16;i++) {
    const reason=i===0?'∅→∅':`MFO_ZAIMER_2026_VERY_LONG_REASON_${i}→MFO_ZAIMER_2026_VERY_LONG_REASON_${i}`;
    nodes.push({name:`reason-${i}`,depth:2,filters:{REASON_TRANSITION:reason,DECISION_AFTER:i===0?'APPROVE':'REJECT'}});
    links.push({source:i===0?'after-a':'after-r',target:`reason-${i}`,value:i===0?400:i===1?1504:7,filters:{}});
  }
  const data={nodes,links};
  const echarts=await import('echarts/core');
  const {SankeyChart}=await import('echarts/charts');
  const {SVGRenderer}=await import('echarts/renderers');
  const {TooltipComponent}=await import('echarts/components');
  echarts.use([SankeyChart,SVGRenderer,TooltipComponent]);
  for(const width of [920,1440]) {
    const chart=echarts.init(null,null,{renderer:'svg',ssr:true,width,height:sankeyHeight(data)});
    try {
      const option=sankeyOption(data);
      chart.setOption(option);
      const series=chart.getModel().getSeriesByIndex(0).getData();
      const centers=nodes.map((node,i)=>({node,layout:series.getItemLayout(i)}))
        .filter(item=>item.node.depth===2).map(({layout})=>layout.y+layout.dy/2).sort((a,b)=>a-b);
      for(let i=1;i<centers.length;i++) assert.ok(centers[i]-centers[i-1]>=18,'Reason labels overlap');
      for(const node of nodes) assert.ok(!option.series[0].label.formatter({name:node.name}).includes('\n'));
      assert.equal(option.series[0].links.length,links.length);
      if(process.env.REPORT_CHART_QA && width===1440) fs.writeFileSync(process.env.REPORT_CHART_QA,chart.renderToSVGString());
    } finally {chart.dispose();}
  }
});
