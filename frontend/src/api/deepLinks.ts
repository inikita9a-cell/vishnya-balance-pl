/** The APP_ID filter is also the target for downloaded report links. */
export function deepLinkedApplication(filters: Record<string, unknown>, availableIds: string[]): string | null {
  const appId = filters.APP_ID;
  return typeof appId === 'string' && availableIds.includes(appId) ? appId : null;
}

export function retainDeepLinkAfterLogin(section: string, runId: string): boolean {
  return !!runId && ['report', 'pivot', 'registry', 'detail', 'checks', 'step'].includes(section);
}
