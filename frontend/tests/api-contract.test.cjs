const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const calls = [];
const responses = {
  '/configs/template': {yaml:'dataset:\n  path: data/example\nchecks: [demo]\n'},
  '/runs': [
    {id:'abc123',status:'done',started_by:'Аналитик',created_at:'2026-11-07T12:00:00',finished_at:'2026-11-07T12:10:00',config_id:2},
    {id:'active',status:'running',started_by:'Никита',created_at:'2026-11-07T12:20:00',finished_at:null,config_id:2},
  ],
  '/configs': [{id:2,name:'Проверка',yaml:'dataset:\n  path: data/RUN-20260827-0001\n'}],
  '/pools': [{id:3,name:'Все',payload:{mode:'all'}}],
  '/procedures': [{id:4,kind:'compare',source:'file',path:'procedures/compare_default.py',code:null}],
  '/runs/abc123': {id:'abc123',status:'done',started_by:'Аналитик',created_at:'2026-11-07T12:00:00',finished_at:'2026-11-07T12:10:00',steps:[{step:'s1_discover',status:'done',progress:100,duration_ms:120,rows_in:2002,rows_out:2002}]},
  '/runs/abc123/summary': {
    total_apps:2002,apps_with_diff:502,apps_decision_changed:385,apps_diff_but_decision_same:117,
    apps_with_quality_issues:7,approval_rates:{before_rate:0.4,after_rate:0.3},
    decision_transitions:[{before:'APPROVE',after:'REJECT',count:20,changed:true}],
    reason_transitions:[{before:'∅',after:'R1',count:20,changed:true}],
    cause_counts:{LOGIC:100,NONE:1500},verdict:{status:'REVIEW_REQUIRED',reason_codes:[],disclaimer:'test'},
  },
  '/runs/abc123/blocks': [{BLOCK:'decisionResult',LEVEL:1,APPS_TOTAL:2002,APPS_CHANGED:200,SHARE:0.1,ROWS_CHANGED:300}],
  '/runs/abc123/checks': [{CHECK_ID:'c1',LABEL:'Sample',RESULT:'FAIL',CNT:1,TOTAL:2002,METRIC:null,CONFIDENCE:'HIGH',SOURCE:'AFTER',ARGUMENT:''}],
  '/runs/abc123/apps/17?diff_only=1': [{APP_ID:'17',PATH:'decision',VALUE_BEFORE:'APPROVE',VALUE_AFTER:'REJECT',DIFF_FLAG:1,CHANGE_TYPE:'VALUE_CHANGED'}],
  '/runs/abc123/apps/17/raw': {BEFORE_MASTER:'{"before":true}',AFTER_BETA:'{"after":true}'},
  '/runs/abc123/steps/s1_discover': {step:'s1_discover',status:'done',params:'{"pool":{"mode":"all"}}',code:'print(1)',message:'ok'},
};
const client = {
  api: async path => {calls.push(['GET',path]); if (!(path in responses)) throw Error(`Unhandled ${path}`); return responses[path];},
  post: async (path, body) => {calls.push(['POST',path,body]);
    if (path === '/configs') return {id:9};
    if (path.endsWith('/explorer/query')) return {rows:[],totalGroups:0,limit:body.limit,offset:body.offset};
    if (path.endsWith('/explorer/apps')) return {items:[],total:0,limit:body.limit,offset:body.offset};
    if (path.endsWith('/drilldown')) return [
      {APP_ID:'17',DECISION_BEFORE:'APPROVE',DECISION_AFTER:'REJECT',DECISION_TRANSITION:'APPROVE→REJECT',REASON_TRANSITION:'∅→R1',N_DIFFS:3,CAUSE:'LOGIC'},
      {APP_ID:'18',DECISION_BEFORE:'APPROVE',DECISION_AFTER:'APPROVE',DECISION_TRANSITION:'APPROVE→APPROVE',REASON_TRANSITION:'∅→∅',N_DIFFS:0,CAUSE:'NONE'},
    ];
    if (path.endsWith('/checks/rerun')) return {ok:true};
    throw Error(`Unhandled POST ${path}`);
  },
};
const source = fs.readFileSync(path.resolve(__dirname,'../src/api/real.ts'),'utf8');
const js = ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const apiExports = {};
vm.runInNewContext(js,{exports: apiExports,require: id => {
  if (id === './client') return client;
  throw Error('Unexpected dependency '+id);
},console});

test('creating a template fetches its full YAML and defers only dataset existence checks', async () => {
  calls.length = 0;
  const created = await apiExports.createTemplateConfig();
  assert.equal(created.id, 9);
  assert.equal(calls[0][0], 'GET');
  assert.equal(calls[0][1], '/configs/template');
  assert.equal(calls[1][0], 'POST');
  assert.equal(calls[1][1], '/configs');
  assert.equal(calls[1][2].yaml, responses['/configs/template'].yaml);
  assert.equal(calls[1][2].check_dataset, false);
});

test('Explorer preserves exact drilldown filters, opaque array keys and pagination', async () => {
  const filters = {PATH:'items.amount', DIFF_FLAG:1, ARRAY_KEY:'a%7Cb|x+y', VALUE_BEFORE:[null], VALUE_AFTER:['NULL']};
  const body = {groupBy:['VALUE_BEFORE','VALUE_AFTER','CHANGE_TYPE'],filters,includeUnchanged:false,limit:20,offset:40};
  await apiExports.queryExplorer('run /1',body);
  assert.deepEqual(calls.at(-1),['POST','/runs/run%20%2F1/explorer/query',body]);
  await apiExports.getExplorerApps('run /1',{filters,limit:20,offset:20});
  assert.strictEqual(calls.at(-1)[2].filters,filters);
  assert.equal(calls.at(-1)[1],'/runs/run%20%2F1/explorer/apps');
  assert.equal(calls.at(-1)[2].offset,20);
  responses['/runs/run%20%2F1/explorer/fields'] = {fields:[],dimensions:['PATH']};
  assert.strictEqual(await apiExports.getExplorerFields('run /1'),responses['/runs/run%20%2F1/explorer/fields']);
});

const treeSource = fs.readFileSync(path.resolve(__dirname,'../src/pages/report/treeModel.ts'),'utf8');
const treeExports = {};
vm.runInNewContext(ts.transpileModule(treeSource,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports:treeExports});

const chartSource = fs.readFileSync(path.resolve(__dirname,'../src/pages/report/chartTreeModel.ts'),'utf8');
const chartExports = {};
vm.runInNewContext(ts.transpileModule(chartSource,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports:chartExports});

test('chart projection bounds wide/deep trees and preserves real attribute-parent identity', () => {
  const fields = Array.from({length:1000},(_,i)=>({path:`root.branch${i}.value`,appsCount:7,changedAppsCount:3,depth:3,hasArrayInstances:true}));
  fields.push({path:'root',appsCount:7,changedAppsCount:3,depth:1,hasArrayInstances:false});
  const roots = treeExports.buildPathTree(fields);
  const index = chartExports.indexPaths(roots);
  const initial = chartExports.projectChart(roots,undefined,new Set(),0);
  assert.equal(initial.root.children.length,1);
  assert.equal(initial.root.children[0].children,undefined);
  assert.equal(initial.root.children[0].attribute,true);
  assert.equal(initial.root.children[0].branch,true);
  const expanded = new Set(index.keys());
  const page = chartExports.projectChart(roots,index.get('root'),expanded,1);
  assert.equal(page.totalChildren,1000);
  assert.equal(page.root.children.length,30);
  assert.equal(page.root.children[0].path,roots[0].children[30].path);
  assert.equal(page.omitted,true);
  const countNodes = node=>1+(node.children||[]).reduce((n,child)=>n+countNodes(child),0);
  assert.ok(countNodes(page.root)<=chartExports.NODE_LIMIT);
  const leaf = chartExports.projectChart(roots,index.get('root.branch999.value'),new Set(),0);
  assert.equal(leaf.root.path,'root.branch999.value');
  assert.equal(leaf.root.attribute,true);
  assert.equal(leaf.root.appsCount,undefined);
  assert.equal(index.get('root.branch999.value').field.hasArrayInstances,true);
});

test('PATH tree preserves attribute-parent nodes without summing overlapping application counts', () => {
  const field = path => ({path,depth:2,appsCount:10,changedAppsCount:7,hasArrayInstances:false});
  const parent = field('root.attribute');
  const tree = treeExports.buildPathTree([field('root.attribute.child'),parent,field('root.other')]);
  assert.equal(tree.length,1);
  assert.equal(tree[0].field,undefined);
  assert.equal(tree[0].appsCount,undefined);
  const node = tree[0].children.find(n=>n.path === parent.path);
  assert.strictEqual(node.field,parent);
  assert.equal(node.field.changedAppsCount,7);
  assert.equal(node.children[0].path,'root.attribute.child');
  const matches = treeExports.searchPathTree(tree,'CHILD');
  assert.equal(matches[0].children.length,1);
  assert.equal(matches[0].children[0].children[0].path,'root.attribute.child');
  assert.equal(treeExports.searchPathTree(tree,'unknown').length,0);
  assert.strictEqual(treeExports.searchPathTree(tree,'  '),tree);
});

test('run and config APIs are adapted from plain arrays, with lowercase statuses',async()=>{
  const runs=await apiExports.getRuns();
  assert.equal(runs[0].status,'done');
  assert.equal(runs[0].progress,100);
  assert.equal(runs[1].progress,null);
  assert.equal(runs[0].config_id,'2');
  const configs=await apiExports.getConfigs();
  assert.equal(configs[0].id,'2');
  assert.match(configs[0].yaml,/dataset:/);
  const detail=await apiExports.getRun('abc123');
  assert.equal(detail.stages[0].step,'s1_discover');
  assert.equal(detail.config_id,'2');
});
test('summary mapping uses the real approval_rates and transitions',async()=>{
  const summary=await apiExports.getSummary('abc123');
  assert.equal(summary.total_apps,2002);
  assert.equal(summary.apps_diff_same_decision,117);
  assert.equal(summary.AR_before,0.4);
  assert.equal(summary.decision_matrix[0].filters.DECISION_BEFORE,'APPROVE');
  assert.equal(summary.verdict.status,'REVIEW_REQUIRED');
  assert.equal((await apiExports.getBlocks('abc123'))[0].BLOCK,'decisionResult');
});
test('drilldown shape supports client-side decision/cause filtering',async()=>{
  const segments=await apiExports.getDrilldown('abc123');
  assert.equal(segments.length,2);
  assert.equal(segments[0].DECISION_CHANGED,true);
  assert.equal(segments[0].QUALITY_ISSUE,null);
  assert.equal(apiExports.filterSegments(segments,{DECISION_CHANGED:true}).length,1);
  assert.equal(apiExports.filterSegments(segments,{HAS_DIFF:false}).length,1);
  assert.equal(apiExports.filterSegments(segments,{CAUSE:'LOGIC'}).length,1);
  assert.equal(apiExports.filterSegments(segments,{REASON_TRANSITION:'∅→R1'}).length,1);
  assert.ok(calls.some(x=>x[0]==='POST'&&x[1].endsWith('/drilldown')&&Object.keys(x[2].filters).length===0));
});
test('checks, app details, source documents and step JSON mapping',async()=>{
  assert.equal((await apiExports.getChecks('abc123'))[0].METRIC,null);
  await apiExports.rerunChecks('abc123');
  assert.equal((await apiExports.getAppDifferences('abc123','17'))[0].CHANGE_TYPE,'VALUE_CHANGED');
  assert.equal((await apiExports.getRawComparison('abc123','17')).before,'{"before":true}');
  assert.equal((await apiExports.getStepDetail('abc123','s1_discover')).params.pool.mode,'all');
});
