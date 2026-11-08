const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const source = fs.readFileSync(path.resolve(__dirname, '../src/pages/report/pivotModel.ts'), 'utf8');
const exportsObj = {};
vm.runInNewContext(ts.transpileModule(source, {compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
}}).outputText, {exports: exportsObj});

const data = {
  columns: ['PATH','CHANGE_TYPE','SOURCE','CNT'],
  dims: ['PATH','CHANGE_TYPE','SOURCE'],
  rows: [
    {PATH:'p.age',CHANGE_TYPE:'VALUE_CHANGED',SOURCE:'BEFORE (MASTER)',CNT:2},
    {PATH:'p.age',CHANGE_TYPE:'VALUE_CHANGED',SOURCE:'AFTER (BETA)',CNT:2},
    {PATH:'p.missing',CHANGE_TYPE:'ATTRIBUTE_NEW',SOURCE:null,CNT:1},
    {PATH:'p.same',CHANGE_TYPE:'SAME',SOURCE:'',CNT:3},
    {PATH:'p.same',CHANGE_TYPE:'SAME',SOURCE:'NULL',CNT:1},
  ],
};

test('grid preserves actual server cell counts; never sums overlapping SOURCE cells', () => {
  const grid=exportsObj.buildPivotGrid(data,['PATH','CHANGE_TYPE'],['SOURCE']);
  assert.equal(grid.rowGroups.length,3);
  const age=grid.rowGroups.find(r=>r.values[0]==='p.age');
  const before=grid.colGroups.find(c=>c.values[0]==='BEFORE (MASTER)');
  const after=grid.colGroups.find(c=>c.values[0]==='AFTER (BETA)');
  assert.equal(grid.getCell(age.id,before.id).CNT,2);
  assert.equal(grid.getCell(age.id,after.id).CNT,2);
});

test('clicked cell merges every axis dimension and keeps SQL NULL, not string NULL', () => {
  const global={PRODUCTS:'X',SOURCE:['BEFORE (MASTER)','AFTER (BETA)']};
  const cell={PATH:'p.missing',CHANGE_TYPE:'ATTRIBUTE_NEW',SOURCE:null,CNT:1};
  const filters=exportsObj.exactCellFilters(global,data.dims,cell);
  assert.equal(filters.PRODUCTS,'X');
  assert.equal(filters.PATH,'p.missing');
  assert.equal(filters.CHANGE_TYPE,'ATTRIBUTE_NEW');
  assert.strictEqual(filters.SOURCE,null);
  assert.deepEqual(global.SOURCE,['BEFORE (MASTER)','AFTER (BETA)']);
  assert.equal(exportsObj.pivotLabel(null),'SQL NULL (отсутствует)');
  assert.equal(exportsObj.pivotLabel('NULL'),'Строка «NULL»');
  assert.equal(exportsObj.pivotLabel(''),'Пустая строка');
});

test('missing grouping dimension throws rather than showing unrelated applications', () => {
  assert.throws(()=>exportsObj.exactCellFilters({},['PATH','SOURCE'],{PATH:'p',CNT:1}),/SOURCE/);
});

test('multiple columns with duplicate row values do not collide by concatenation', () => {
  const special={rows:[
    {a:'x|y',b:'z',CNT:1},
    {a:'x',b:'y|z',CNT:2},
  ]};
  const grid=exportsObj.buildPivotGrid(special,['a','b'],[]);
  assert.equal(grid.rowGroups.length,2);
  assert.equal(grid.getCell(grid.rowGroups[0].id,grid.colGroups[0].id).CNT,1);
  assert.equal(grid.getCell(grid.rowGroups[1].id,grid.colGroups[0].id).CNT,2);
});

test('attribute highlight distinguishes same PATH with different ARRAY_KEY and values', () => {
  const a={PATH:'models.score',ARRAY_KEY:'first',CHANGE_TYPE:'VALUE_CHANGED',DIFF_FLAG:1,ADJUSTED_BEFORE:'0.5',ADJUSTED_AFTER:'0.7'};
  const b={...a,ARRAY_KEY:'second',ADJUSTED_AFTER:'0.9'};
  const cell={PATH:'models.score',ARRAY_KEY:'first',CHANGE_TYPE:'VALUE_CHANGED',SOURCE:'AFTER (BETA)',VALUE_ADJUSTED:'0.7'};
  assert.equal(exportsObj.matchesCellAttribute(a,cell),true);
  assert.equal(exportsObj.matchesCellAttribute(b,cell),false);
  assert.equal(exportsObj.matchesCellAttribute(a,{...cell,VALUE_ADJUSTED:'0.9'}),false);
  assert.equal(exportsObj.matchesCellAttribute(a,{...cell,SOURCE:'BEFORE (MASTER)',VALUE_ADJUSTED:'0.5'}),true);
});

test('readable presets keep SQL dimensions exact but default to changed applications', () => {
  const available=['PATH','CHANGE_TYPE','DIFF_FLAG','DECISION_BEFORE','DECISION_AFTER','PRODUCTS','PARTNER_TYPE','CAUSE'];
  const changes=exportsObj.presetLayout('changes',available);
  assert.equal(changes.rows[0],'PATH');
  assert.equal(changes.cols[0],'CHANGE_TYPE');
  assert.equal(changes.filters.DIFF_FLAG,1);
  const decisions=exportsObj.presetLayout('decisions',available);
  assert.equal(decisions.rows[0],'DECISION_BEFORE');
  assert.equal(decisions.cols[0],'DECISION_AFTER');
  assert.equal(Object.keys(decisions.filters).length,0);
  assert.equal(exportsObj.presetLayout('partners',available).rows[0],'PARTNER_TYPE');
  assert.equal(exportsObj.presetLayout('causes',['PATH','CHANGE_TYPE']),null);
});

test('translated UI captions do not change drill-down identity or null semantics', () => {
  assert.equal(exportsObj.dimensionLabel('PATH'),'Атрибут');
  assert.equal(exportsObj.readablePivotValue('CHANGE_TYPE','ATTRIBUTE_NEW'),'Атрибут появился');
  assert.equal(exportsObj.readablePivotValue('DIFF_FLAG',1),'Да');
  assert.equal(exportsObj.readablePivotValue('SOURCE',null),'Нет значения (SQL NULL)');
  const rawCell={PATH:'p',CHANGE_TYPE:'ATTRIBUTE_NEW',SOURCE:null,CNT:1};
  const filters=exportsObj.exactCellFilters({DIFF_FLAG:1},['PATH','CHANGE_TYPE','SOURCE'],rawCell);
  assert.equal(filters.CHANGE_TYPE,'ATTRIBUTE_NEW');
  assert.strictEqual(filters.SOURCE,null);
  assert.equal(filters.DIFF_FLAG,1);
});
