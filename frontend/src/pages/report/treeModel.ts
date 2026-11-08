import type { ExplorerField } from '../../api/explorer.types';

export interface PathNode {
  path: string;
  label: string;
  field?: ExplorerField;
  children: PathNode[];
}

// Only structural composition: never aggregate counts from descendants.
export function buildPathTree(fields: ExplorerField[]): PathNode[] {
  const roots: PathNode[] = [];
  const nodes = new Map<string, PathNode>();
  for (const field of fields) {
    const parts = field.path.split('.');
    let siblings = roots;
    parts.forEach((label, index) => {
      const path = parts.slice(0, index + 1).join('.');
      let node = nodes.get(path);
      if (!node) {
        node = { path, label, children: [] };
        nodes.set(path, node);
        siblings.push(node);
      }
      if (index === parts.length - 1) node.field = field;
      siblings = node.children;
    });
  }
  const sort = (items: PathNode[]) => {
    items.sort((a, b) => a.label.localeCompare(b.label));
    items.forEach(node => sort(node.children));
  };
  sort(roots);
  return roots;
}

export function searchPathTree(nodes: PathNode[], query: string): PathNode[] {
  const term = query.trim().toLocaleLowerCase();
  if (!term) return nodes;
  return nodes.flatMap(node => {
    const children = searchPathTree(node.children, term);
    return node.path.toLocaleLowerCase().includes(term) || children.length
      ? [{ ...node, children }] : [];
  });
}
