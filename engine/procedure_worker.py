"""Private trusted-code worker. Invoked by procedure_runtime, not a public API."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import pickle
import sys


def main():
    from .procedure_runtime import ProcedureError, validate_normalized
    task = pickle.loads(Path(sys.argv[1]).read_bytes())
    kind, spec, cfg, payload = (task[k] for k in ('kind', 'spec', 'cfg', 'payload'))
    namespace = {'__name__': '__spr_procedure__', '__file__': spec.get('path') or '<workspace>'}
    exec(compile(spec['code'], namespace['__file__'], 'exec'), namespace)
    entry = namespace.get(spec['entry'])
    if not callable(entry):
        raise ProcedureError(f'{kind}: callable {spec["entry"]!r} not found')
    if kind == 'normalize':
        output, issues = [], []
        for pair in payload['pairs']:
            local_issues = []
            value = entry(before=deepcopy(pair['BEFORE']) or {}, after=deepcopy(pair['AFTER']) or {},
                          cfg=deepcopy(cfg), params=deepcopy(spec['params']),
                          app_id=pair['APP_ID'], issues=local_issues)
            if not isinstance(value, (tuple, list)) or len(value) != 2:
                raise ProcedureError('normalize: expected (before_rows, after_rows)')
            before = validate_normalized(value[0], pair['APP_ID'], 'BEFORE')
            after = validate_normalized(value[1], pair['APP_ID'], 'AFTER')
            if (pair['BEFORE'] is None and before) or (pair['AFTER'] is None and after):
                raise ProcedureError('normalize: cannot create rows for a missing source document')
            output.append((before, after))
            issues.extend(local_issues)
        result = {'rows': output, 'issues': issues}
    elif kind == 'compare':
        issues = []
        result = {'frame': entry(union_df=payload['union_df'], cfg=cfg,
                                 params=spec['params'], issues=issues), 'issues': issues}
    elif kind == 'facts':
        result = entry(comparison=payload['comparison'], segments=payload['segments'],
                       cfg=cfg, params=spec['params'])
    else:
        raise ProcedureError(f'Unknown procedure kind: {kind}')
    Path(sys.argv[2]).write_bytes(pickle.dumps(result))


if __name__ == '__main__':
    main()
