const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const code = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/api/explanation.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const helper = {}, calls = [];
vm.runInNewContext(code, { exports: helper, require: () => ({ api: url => { calls.push(url); return Promise.resolve({}); } }) });
test('NULL, absence and empty string have different user-visible labels', () => {
  const values = [{present: false, value: null}, {present: true, value: 'NULL'}, {present: true, value: ''}, {present: true, value: null}];
  assert.equal(new Set(values.map(helper.observedValue)).size, 4);
  assert.equal(helper.observedValue({present:true, value:'0'}), '0');
  assert.equal(helper.observedValue({present:true, value:'false'}), 'false');
});
test('application IDs are encoded and the next page has an explicit offset', async () => {
  await helper.getApplicationExplanation('run', 'APP &1/Ж', 200);
  assert.equal(calls[0], '/runs/run/apps/APP%20%261%2F%D0%96/explanation?limit=200&offset=200');
});
