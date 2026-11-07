"""Этап 5: достроить blocks/facts по существующему запуску без чтения JSON."""
import argparse
import json
import yaml
from .aggregates import prepare_aggregates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, help='Папка с comparison.parquet и segments.parquet')
    parser.add_argument('--config', default='configs/default_spr.yaml')
    args = parser.parse_args()
    with open(args.config, encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    try:
        result = prepare_aggregates(args.run, cfg)
    except FileExistsError as exc:
        parser.exit(2, f'{exc}\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
