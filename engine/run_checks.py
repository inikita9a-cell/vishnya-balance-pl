"""s12: build/rerun the automated checks report from an existing run."""
import argparse
import json
from pathlib import Path
import yaml
from .checks_service import prepare_checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, help='Directory with comparison/segments.parquet')
    parser.add_argument('--config', default='configs/default_spr.yaml')
    parser.add_argument('--checks-dir', default=str(Path(__file__).resolve().parents[1] / 'procedures' / 'checks'))
    parser.add_argument('--check', action='append', dest='check_ids',
                        help='Run only this check ID (repeatable); by default use config checks')
    args = parser.parse_args()
    with open(args.config, encoding='utf-8') as file:
        cfg = yaml.safe_load(file)
    status = prepare_checks(args.run, cfg, checks_dir=args.checks_dir,
                            check_ids=args.check_ids)
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
