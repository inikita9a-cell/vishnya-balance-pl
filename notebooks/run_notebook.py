"""Выполнить реальные ячейки pipeline.ipynb через IPython без Jupyter-сервера.

Это не второй пайплайн: исполняется код из .ipynb, rich outputs сохраняются.
Каждый вызов CLI — новый процесс с новым пространством имён. Удобно для CI и
сред, где запрещены локальные сокеты Jupyter kernel. Интерфейс Jupyter можно
использовать независимо от этого файла.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import traceback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', help='Папка с manifest.json и RESULTS; без аргумента — demo')
    parser.add_argument('--config', help='YAML конфигурации')
    parser.add_argument('--output-root', help='Каталог для новых notebook-run, по умолчанию runs')
    parser.add_argument('--no-verify', action='store_true', help='Не выполнять повторный обычный пайплайн')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    # Разрешаем переданные относительные пути относительно каталога пользователя.
    for arg, env in ((args.dataset, 'SPR_DATASET_PATH'), (args.config, 'SPR_CONFIG_PATH'),
                     (args.output_root, 'SPR_NOTEBOOK_OUTPUT_ROOT')):
        if arg is not None:
            os.environ[env] = str(Path(arg).expanduser().resolve())
    if args.no_verify:
        os.environ['SPR_NOTEBOOK_VERIFY_PIPELINE'] = '0'
    os.chdir(root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    import nbformat
    from IPython.core.interactiveshell import InteractiveShell
    from IPython.utils.capture import capture_output

    path = root / 'notebooks/pipeline.ipynb'
    notebook = nbformat.read(path, as_version=4)
    nbformat.validate(notebook)
    shell = InteractiveShell.instance()
    failure = None
    started = datetime.now(timezone.utc).isoformat()
    for cell_number, cell in enumerate(notebook.cells, 1):
        if cell.cell_type != 'code':
            continue
        cell.outputs = []
        with capture_output(stdout=True, stderr=True, display=True) as captured:
            result = shell.run_cell(cell.source, store_history=True)
        cell.execution_count = shell.execution_count - 1
        if captured.stdout:
            cell.outputs.append(nbformat.v4.new_output('stream', name='stdout', text=captured.stdout))
        if captured.stderr:
            cell.outputs.append(nbformat.v4.new_output('stream', name='stderr', text=captured.stderr))
        for output in captured.outputs:
            cell.outputs.append(nbformat.v4.new_output('display_data', data=output.data, metadata=output.metadata))
        error = result.error_before_exec or result.error_in_exec
        if error:
            cell.outputs.append(nbformat.v4.new_output('error', ename=type(error).__name__,
                                evalue=str(error), traceback=traceback.format_exception(error)))
            failure = (cell_number, error)
            break
        print(f'Cell {cell_number}: OK', flush=True)
    run_dir = shell.user_ns.get('run_dir')
    if isinstance(run_dir, Path) and run_dir.is_dir():
        destination = run_dir / 'pipeline.executed.ipynb'
        notebook.metadata['execution_method'] = 'IPython InteractiveShell; no network kernel'
        notebook.metadata['execution_started_at'] = started
        nbformat.write(notebook, destination)
        print(f'Executed notebook: {destination}', flush=True)
    if failure:
        print(f'FAILED cell {failure[0]}: {type(failure[1]).__name__}: {failure[1]}', file=sys.stderr)
        return 1
    execution = shell.user_ns.get('execution', {})
    print('NOTEBOOK OK:', execution.get('total_apps'), 'applications;',
          'pipeline comparison:', execution.get('verification'), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
