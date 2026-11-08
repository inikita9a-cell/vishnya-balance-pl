import type { PathNode } from './treeModel';

export const CHILD_PAGE = 30;
export const NODE_LIMIT = 180;
export interface ChartNode {
  id: string; name: string; path?: string; branch: boolean; attribute: boolean;
  children?: ChartNode[];
}

export function indexPaths(roots: PathNode[]): Map<string, PathNode> {
  const index = new Map<string, PathNode>();
  const visit = (nodes: PathNode[]) => nodes.forEach(node => { index.set(node.path, node); visit(node.children); });
  visit(roots);
  return index;
}

// Bounded structural projection only. No analytical values are calculated here.
export function projectChart(roots: PathNode[], focus: PathNode | undefined, expanded: Set<string>, page: number) {
  let remaining = NODE_LIMIT - 1;
  let omitted = false;
  const convert = (node: PathNode): ChartNode => {
    remaining--;
    const result: ChartNode = { id: `path:${node.path}`, name: node.label || '(пустое имя)', path: node.path,
      branch: node.children.length > 0, attribute: Boolean(node.field) };
    if (expanded.has(node.path) && node.children.length) {
      result.children = [];
      for (const child of node.children.slice(0, CHILD_PAGE)) {
        if (remaining <= 0) { omitted = true; break; }
        result.children.push(convert(child));
      }
      if (node.children.length > CHILD_PAGE) omitted = true;
    }
    return result;
  };
  const children = focus ? focus.children : roots;
  const root: ChartNode = { id: focus ? `path:${focus.path}` : 'root', name: focus?.label || 'Атрибуты',
    path: focus?.path, branch: true, attribute: Boolean(focus?.field), children: [] };
  for (const child of children.slice(page * CHILD_PAGE, (page + 1) * CHILD_PAGE)) {
    if (remaining <= 0) { omitted = true; break; }
    root.children!.push(convert(child));
  }
  if (children.length > CHILD_PAGE) omitted = true;
  return { root, omitted, totalChildren: children.length };
}
