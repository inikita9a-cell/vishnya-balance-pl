"""Single execution contract for the platform: comparison -> checks -> verdict -> HTML.

The platform owns users, queueing and SQL logs. The engine owns calculations.
No decision-system-specific fields are hardcoded here.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .steps import prepare_comparison
from .checks_runner import run_checks
from .summary import prepare_summary
from .report_html import write_report_html


def run_pipeline(cfg: dict, run_dir: str | Path,
                 on_event: Callable[[dict], None] | None = None) -> dict:
    """Run all stages; publish nothing as 'done' before HTML has been written.

    on_event receives {step, status, progress?, rows_in?, rows_out?, message?}.
    Existing CLI `prepare_comparison(cfg, path)` is unchanged and remains s1-s11.
    """
    root = Path(run_dir)
    root.mkdir(parents=True, exist_ok=True)

    def notify(step, status, **details):
        if on_event:
            on_event({'step': step, 'status': status, **details})

    from .procedure_runtime import write_snapshot
    from .platform_checks_adapter import freeze_checks, checks_snapshot_event
    cfg = write_snapshot(freeze_checks(cfg), root)
    status = prepare_comparison(cfg, root, on_event=on_event)
    notify('s12_checks', 'running', **checks_snapshot_event(cfg))
    path = Path(run_checks({'cfg': cfg, 'run_dir': str(root)}))
    if not path.is_file():
        raise FileNotFoundError(f'Checks report not created: {path}')
    import json
    checks = json.loads(path.read_text(encoding='utf-8'))
    notify('s12_checks', 'done', progress=100, rows_out=len(checks))

    notify('s13_summary', 'running')
    summary = prepare_summary(root, cfg)
    notify('s13_summary', 'done', progress=100,
           rows_out=summary.get('total_apps'),
           message=summary.get('verdict', {}).get('status'))

    notify('s15_report', 'running')
    report = write_report_html(root, cfg)
    notify('s15_report', 'done', progress=100, message=str(report))
    required = ('union.parquet', 'comparison.parquet', 'segments.parquet',
                'blocks.parquet', 'facts.parquet', 'fact_apps.parquet',
                'checks.json', 'summary.json', 'report.html')
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise RuntimeError(f'Pipeline missing outputs: {missing}')
    return {'run_id': root.name, 'status': 'done', 'artifacts': list(required),
            'summary': summary, 'comparison_status': status}


def main():
    """Optional CLI smoke test of the exact same chain used by FastAPI."""
    import argparse
    import json
    import yaml
    parser = argparse.ArgumentParser(description='Run comparison, checks, summary and HTML')
    parser.add_argument('--config', default='configs/default_spr.yaml')
    parser.add_argument('--dataset', help='Override dataset.path without editing a config')
    parser.add_argument('--out', required=True, help='New output directory (do not reuse past runs)')
    args = parser.parse_args()
    with open(args.config, encoding='utf-8') as stream:
        cfg = yaml.safe_load(stream) or {}
    if args.dataset:
        cfg.setdefault('dataset', {})['path'] = args.dataset

    def show(event):
        if event['status'] in ('running', 'done', 'failed'):
            print(f"[{event['status']}] {event['step']} "
                  f"rows={event.get('rows_out', '-')}", flush=True)

    result = run_pipeline(cfg, args.out, on_event=show)
    print(json.dumps({'run_id': result['run_id'], 'status': result['status'],
                      'total_apps': result['summary']['total_apps'],
                      'apps_with_diff': result['summary']['apps_with_diff'],
                      'apps_decision_changed': result['summary']['apps_decision_changed'],
                      'verdict': result['summary']['verdict']['status']},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
