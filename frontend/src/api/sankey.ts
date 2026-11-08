import { post } from './client';

export interface FlowNode {
  name: string;
  label: string;
  depth: number;
  filters: Record<string, unknown>;
}
export interface FlowLink {
  source: string;
  target: string;
  value: number;
  filters: Record<string, unknown>;
}
export interface SankeyData { nodes: FlowNode[]; links: FlowLink[] }

export function getSankey(runId: string): Promise<SankeyData> {
  return post<SankeyData>(`/runs/${encodeURIComponent(runId)}/sankey`, { filters: {} });
}
