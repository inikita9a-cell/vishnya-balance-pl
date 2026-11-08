/** All UI paths (e.g. /runs) are mapped to the real FastAPI /api routes. */
import { formatApiError } from './errors';
export const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '');

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  const url = `${API_BASE}/api${path.startsWith('/') ? path : `/${path}`}`;
  let response: Response;
  try {
    response = await fetch(url, { ...init, headers, credentials: 'include' });
  } catch {
    throw new ApiError(`Не удалось подключиться к FastAPI (${API_BASE || '/api'}). Проверьте запуск сервера (по умолчанию порт 8000) и VITE_BACKEND_URL в настройках Vite.`, 0);
  }
  if (!response.ok) {
    const data: unknown = await response.json().catch(() => null);
    throw new ApiError(formatApiError(data, `${response.status} ${response.statusText}`), response.status);
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}
export const post = <T>(path: string, body: unknown) => api<T>(path, { method: 'POST', body: JSON.stringify(body) });
export const put = <T>(path: string, body: unknown) => api<T>(path, { method: 'PUT', body: JSON.stringify(body) });
export const message = (error: unknown) => error instanceof Error ? error.message : 'Произошла ошибка запроса';
