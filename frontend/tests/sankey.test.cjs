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
  const { sankeyOption } = load('pages/report/sankeyModel.ts', { '../../styles/Theme': {
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
