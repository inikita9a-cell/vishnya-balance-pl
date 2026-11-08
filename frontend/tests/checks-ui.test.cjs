const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');

function load(file, dependencies={}) {
  const exports={};
  const js=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src',file),'utf8'),{
    compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX},
  }).outputText;
  vm.runInNewContext(js,{exports,require:id=>id in dependencies?dependencies[id]:require(id)});
  return exports;
}
const presentation=load('pages/checks/checkPresentation.ts');

test('builtin signals are distinguished from execution errors without changing raw results',()=>{
  for (const CHECK_ID of ['ar_drop_by_product','attribute_new_loss','external_score_drift','stop_factor_disappeared','target_model_changed']) {
    const row={CHECK_ID,RESULT:'FAIL'};
    const outcome=presentation.checkOutcome(row);
    assert.equal(outcome.label,'Есть сигнал');
    assert.equal(outcome.tone,'busy');
    assert.equal(row.RESULT,'FAIL');
    assert.equal(presentation.checkOutcome({...row,RESULT:'ERROR'}).label,'Ошибка выполнения');
    assert.equal(presentation.checkOutcome({...row,RESULT:'ERROR'}).tone,'bad');
    assert.equal(presentation.checkOutcome({...row,RESULT:'PASS'}).label,'Сигнал не выявлен');
  }
});

test('custom FAIL and unknown outcomes are never hidden as successful checks',()=>{
  assert.equal(presentation.checkOutcome({CHECK_ID:'custom',RESULT:'FAIL'}).label,'Условие нарушено');
  assert.equal(presentation.checkOutcome({CHECK_ID:'custom',RESULT:'PASS'}).label,'Условие выполнено');
  assert.equal(presentation.checkOutcome({CHECK_ID:'custom',RESULT:'unexpected'}).tone,'bad');
  assert.match(presentation.checkMetricLabel({CHECK_ID:'ar_drop_by_product'}),/Относительное падение/);
});

test('each application button opens the exact opaque ID rather than an empty inline card',()=>{
  const {CheckApplicationLinks}=load('pages/checks/CheckApplicationLinks.tsx',{
    '../../components/Ui':{QuietButton:props=>React.createElement('button',props)},
  });
  const ids=['I32554678','APP &1/Ж'],opened=[];
  const tree=CheckApplicationLinks({appIds:ids,onApplication:id=>opened.push(id)});
  const html=renderToStaticMarkup(tree);
  assert.match(html,/Открыть карточку заявки I32554678/);
  const buttons=React.Children.toArray(tree.props.children).map(li=>li.props.children);
  buttons[1].props.onClick();
  assert.deepEqual(opened,['APP &1/Ж']);
  buttons[0].props.onClick();
  assert.deepEqual(opened,['APP &1/Ж','I32554678']);
  const loading=CheckApplicationLinks({appIds:ids,onApplication:()=>{},disabled:true});
  assert.match(renderToStaticMarkup(loading),/disabled/);
});
