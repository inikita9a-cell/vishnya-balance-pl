"""Локальный запуск этапов до витрины сравнения."""
import argparse
import json
import yaml
from .steps import prepare_comparison


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='configs/default_spr.yaml')
    parser.add_argument('--dataset', help='Override dataset.path')
    parser.add_argument('--out', required=True, help='New run directory')
    args = parser.parse_args()
    with open(args.config, encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    if args.dataset:
        cfg['dataset']['path'] = args.dataset
    print(json.dumps(prepare_comparison(cfg, args.out), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
