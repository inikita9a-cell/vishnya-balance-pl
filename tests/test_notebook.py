"""Execute actual notebook cells in a fresh IPython process, then verify parity.

No socket-based kernel is required. The notebook's independent second run
compares all seven tables and business check/summary output with run_pipeline.
"""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys

import nbformat
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('broken', [False, True], ids=['public-demo', 'missing-and-corrupt'])
def test_notebook_executes_top_to_bottom_and_matches_pipeline(tmp_path, broken):
    output = tmp_path / 'outputs'
    env = os.environ.copy()
    for key in ('SPR_DATASET_PATH', 'SPR_CONFIG_PATH', 'SPR_NOTEBOOK_OUTPUT_ROOT', 'LLM_API_KEY'):
        env.pop(key, None)
    env['PYTHONIOENCODING'] = 'utf-8'
    env['SPR_NOTEBOOK_VERIFY_PIPELINE'] = '1'
    command = [sys.executable, str(ROOT/'notebooks/run_notebook.py'), '--output-root', str(output)]
    if broken:
        dataset = tmp_path / 'dataset'
        shutil.copytree(ROOT/'notebooks/demo_data', dataset)
        after = sorted((dataset/'RESULTS/AFTER_BETA').glob('*.json'))
        after[0].unlink()
        after[1].write_text('{broken json', encoding='utf-8')
        command.extend(['--dataset', str(dataset)])
    result = subprocess.run(command, cwd=ROOT/'notebooks', env=env,
                            capture_output=True, text=True, encoding='utf-8', timeout=180)
    assert result.returncode == 0, result.stdout + '\n' + result.stderr
    notebooks = list(output.glob('*/pipeline.executed.ipynb'))
    assert len(notebooks) == 1
    run = notebooks[0].parent
    notebook = nbformat.read(notebooks[0], as_version=4)
    nbformat.validate(notebook)
    code_cells = [cell for cell in notebook.cells if cell.cell_type == 'code']
    assert all(cell.execution_count is not None for cell in code_cells)
    assert not any(o.output_type == 'error' for c in code_cells for o in c.outputs)
    verification = json.loads((run/'notebook_verification.json').read_text(encoding='utf-8'))
    assert verification['status'] == 'PASS'
    assert len(verification['tables']) == 7 and verification['checks_equal'] and verification['summary_equal']
    stages = json.loads((run/'notebook_stage_log.json').read_text(encoding='utf-8'))
    assert len(stages) == 14  # s1..s13 + s15; s14 is explicitly optional/off
    assert all(item['status'] == 'done' for item in stages)
    assert (run/'report.html').is_file()
    assert not (run/'llm_opinion.txt').exists()
    quality = pd.read_parquet(run/'quality.parquet')
    segments = pd.read_parquet(run/'segments.parquet')
    assert len(segments) == 4
    if broken:
        assert {'APP_MISSING_AFTER', 'PARSE_ERROR'} <= set(quality.ISSUE)
        assert int(segments.COMPARISON_COMPLETE.eq(0).sum()) == 2
    else:
        assert quality.empty
