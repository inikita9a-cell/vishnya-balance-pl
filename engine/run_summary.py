"""s13: создаёт/обновляет summary.json для готового запуска без повторной нормализации."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import yaml

from .summary import prepare_summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, help='Existing directory with Parquet results')
    parser.add_argument('--config', default='configs/default_spr.yaml',
                        help='YAML containing segments.approve_value and summary.top_n')
    args = parser.parse_args()
    with Path(args.config).open(encoding='utf-8') as f:
        cfg = yaml.safe_load(f) or {}
    summary = prepare_summary(args.run, cfg)
    # Concise CLI result, full document is in runs/<id>/summary.json.
    print(json.dumps({
        'stage': 'summary', 'run_id': summary['run_id'],
        'total_apps': summary['total_apps'],
        'apps_with_diff': summary['apps_with_diff'],
        'apps_decision_changed': summary['apps_decision_changed'],
        'top_changed_paths': len(summary['top_changed_paths']),
        'top_changed_blocks': len(summary['top_changed_blocks']),
        'checks_status': summary['checks']['status'],
        'checks_error': summary['checks']['error'],
        'verdict': summary['verdict']['status'],
        'summary_seconds': summary['summary_seconds'],
        'path': str(Path(args.run) / 'summary.json')
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
