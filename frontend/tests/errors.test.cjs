const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const source = fs.readFileSync(path.join(__dirname,'../src/api/errors.ts'),'utf8');
const exportsObject = {};
vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,{exports:exportsObject});
const format = exportsObject.formatApiError;

test('nested invalid-run response shows the missing dataset instead of JSON',()=>{
  const text = format({detail:{detail:'Invalid run config', report:{valid:true,errors:[],warnings:[{path:'dataset.path',message:'Dataset path does not exist: data/RUN-1'}]}}},'failed');
  assert.match(text,/Датасет не найден: data\/RUN-1/);
  assert.match(text,/dataset.path/);
  assert.ok(!text.includes('{'));
});
test('duplicate check job has a clear user-facing message',()=>{
  assert.match(format({detail:'A checks job is already queued/running for this run'},'failed'),/Проверки этого запуска уже/);
});
test('Pydantic validation and unknown details are preserved',()=>{
  assert.equal(format({detail:[{msg:'Invalid limit'}]},'failed'),'Invalid limit');
  assert.equal(format({detail:'custom failure'},'failed'),'custom failure');
  assert.equal(format(null,'HTTP 500'),'HTTP 500');
});
