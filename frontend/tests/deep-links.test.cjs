const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const source = fs.readFileSync(path.resolve(__dirname, '../src/api/deepLinks.ts'), 'utf8');
const output = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  reportDiagnostics: true,
});
const helper = {};
vm.runInNewContext(output.outputText, { exports: helper });

test('APP_ID from downloaded link selects the exact application', () => {
  const id = 'APP A&1/Юникод#?="<';
  const query = new URLSearchParams({page: 'registry', run: 'run', filters: JSON.stringify({APP_ID: id})});
  const filters = JSON.parse(new URLSearchParams(query.toString()).get('filters'));
  assert.equal(helper.deepLinkedApplication(filters, ['other', id]), id);
});
test('missing or malformed target never opens another application', () => {
  for (const filters of [{}, {APP_ID: 'missing'}, {APP_ID: ['one']}, {APP_ID: null}, {APP_ID: 1}]) {
    assert.equal(helper.deepLinkedApplication(filters, ['one']), null);
  }
});
test('logging in retains report and application deep links', () => {
  for (const section of ['report', 'registry', 'detail', 'checks', 'step']) {
    assert.equal(helper.retainDeepLinkAfterLogin(section, 'run'), true);
  }
  assert.equal(helper.retainDeepLinkAfterLogin('runs', 'run'), false);
  assert.equal(helper.retainDeepLinkAfterLogin('registry', ''), false);
});
