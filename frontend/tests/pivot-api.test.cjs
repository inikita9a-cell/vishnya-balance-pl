const {test} = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const records = [];
const mock = {
  api: async url => {records.push(['GET',url]);
    if (url.endsWith('/pivot/dimensions')) return {dimensions:['PATH','SOURCE','PRODUCTS','PARTNER_TYPE','CHANGE_TYPE']};
    if (url.includes('/pivot/values?')) return {field:'SOURCE',values:[null,'NULL','',false,0],has_more:false};
    if (url.endsWith('?diff_only=0')) return [{APP_ID:'a&b',PATH:'p',ARRAY_KEY:'a|b',VALUE_BEFORE:null,VALUE_AFTER:'NULL',DIFF_FLAG:1,CHANGE_TYPE:'VALUE_CHANGED'}];
    throw Error(`Unexpected GET ${url}`);
  },
  post: async (url,body) => {records.push(['POST',url,body]);
    if (url.endsWith('/pivot')) return {columns:['PATH','SOURCE','CNT'],dims:['PATH','SOURCE'],rows:[{PATH:'p',SOURCE:null,CNT:1}]};
    if (url.endsWith('/pivot/apps')) return {total:1,items:[{APP_ID:'a&b'}],limit:body.limit,offset:body.offset};
    throw Error(`Unexpected POST ${url}`);
  },
};
const src=fs.readFileSync(path.resolve(__dirname,'../src/api/real.ts'),'utf8');
const js=ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const e={};
vm.runInNewContext(js,{exports:e,require: id=>id==='./client'?mock:(()=>{throw Error(id)})(),console});

test('pivot uses real dynamically listed dimensions and values including SQL NULL',async()=>{
  assert.ok((await e.getPivotDimensions('id /1')).dimensions.includes('PARTNER_TYPE'));
  const values=(await e.getPivotValues('id /1','SOURCE')).values;
  assert.equal(values[0],null);assert.equal(values[1],'NULL');
  assert.equal(records.at(-1)[1],'/runs/id%20%2F1/pivot/values?field=SOURCE');
});

test('pivot sends raw NULL and all axes; server page filters are passed unchanged',async()=>{
  const filters={SOURCE:null,PARTNER_TYPE:['retail','office']};
  const result=await e.getPivot('r/1',['PATH'],['SOURCE'],filters);
  assert.equal(result.rows[0].CNT,1);
  assert.strictEqual(records.at(-1)[2].filters,filters);
  assert.equal(records.at(-1)[1],'/runs/r%2F1/pivot');
  const page=await e.getPivotApps('r/1',{...filters,PATH:'p'},50,100);
  assert.equal(page.total,1);assert.equal(records.at(-1)[2].offset,100);
  assert.equal(records.at(-1)[2].filters.SOURCE,null);
});

test('drill through same/new/value-changed cells loads full comparison and safe app id',async()=>{
  const rows=await e.getAppComparisonRows('r','a&b');
  assert.equal(rows[0].ARRAY_KEY,'a|b');
  assert.equal(rows[0].VALUE_BEFORE,'—');
  assert.equal(rows[0].VALUE_AFTER,'NULL');
  assert.equal(records.at(-1)[1],'/runs/r/apps/a%26b?diff_only=0');
});
