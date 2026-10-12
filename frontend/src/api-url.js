// This is a public build-time URL; leave unset for local or same-origin hosting.
export function apiUrl(path) {
  const origin = (import.meta.env.VITE_API_ORIGIN || '').trim().replace(/\/+$/, '');
  return origin + path;
}

export async function readApiResponse(response, url) {
  let data;
  try {
    data = await response.json();
  } catch {
    const status = response.status;
    if (status === 404) throw new Error(`API endpoint not found (404): ${url}. Check the frontend VITE_API_ORIGIN and redeploy.`);
    if (status === 400) throw new Error(`API rejected the request (400): ${url}. Check the backend ASTRA_ALLOWED_HOSTS setting.`);
    throw new Error(`API returned an unreadable response (HTTP ${status}): ${url}. Check the backend deployment and logs.`);
  }
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || `Request failed (HTTP ${response.status})`));
  return data;
}
