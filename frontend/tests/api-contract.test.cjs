const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const calls = [];
const responses = {
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
