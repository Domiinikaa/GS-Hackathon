// Helper for backend requests with automatic JWT Bearer authentication.
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const token = localStorage.getItem('gs_jwt_token');
  const headers = new Headers(init?.headers || {});
  
  if (!headers.has('Content-Type') && !(init?.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const res = await fetch(`/api${path}`, {
    ...init,
    headers,
  });

  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`${res.status} ${errorText}`);
  }
  return res.json() as Promise<T>;
}
