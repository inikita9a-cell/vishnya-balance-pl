"""Шаблоны путей: * — сегмент, ** — ноль или больше сегментов."""
from functools import lru_cache
from fnmatch import fnmatchcase


def matches(pattern, path, subtree=False):
    pattern, path = tuple(pattern.split('.')), tuple(path.split('.'))
    @lru_cache(maxsize=None)
    def match(i, j):
        if i == len(pattern):
            return subtree or j == len(path)
        if pattern[i] == '**':
            return match(i+1, j) or (j < len(path) and match(i, j+1))
        return j < len(path) and fnmatchcase(path[j], pattern[i]) and match(i+1, j+1)
    return match(0, 0)


class PathMatcher:
    def __init__(self, patterns):
        self.patterns = list(patterns or [])
        self.match = lru_cache(maxsize=8192)(self._match)

    def _match(self, path):
        return any(matches(p, path, subtree=True) for p in self.patterns)

    def which(self, path):
        return next((p for p in self.patterns if matches(p, path, subtree=True)), None)

    def __bool__(self):
        return bool(self.patterns)


class ArrayRules:
    def __init__(self, arrays):
        self.exact = {k: v for k, v in (arrays or {}).items() if '*' not in k}
        self.wild = sorted(((k, v) for k, v in (arrays or {}).items() if '*' in k),
                           key=lambda kv: (kv[0].count('*'), -len(kv[0])))
        self.lookup = lru_cache(maxsize=8192)(self._lookup)

    def _lookup(self, path):
        if path in self.exact:
            return self.exact[path]
        return next((v for k, v in self.wild if matches(k, path)), None)

    def array_paths(self):
        return list(self.exact)


def join(*parts):
    return '.'.join(p for p in parts if p)
