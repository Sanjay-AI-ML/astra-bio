import {afterEach, expect, it, vi} from 'vitest';
import {apiUrl, readApiResponse} from './api-url.js';
afterEach(()=>vi.unstubAllEnvs());
it('keeps local API requests on the current origin',()=>{
  vi.stubEnv('VITE_API_ORIGIN','');
  expect(apiUrl('/api/bootstrap')).toBe('/api/bootstrap');
});
it('explains a static-host 404 instead of exposing a JSON parse error',async()=>{
  await expect(readApiResponse(new Response('Not Found', {status:404}), '/api/bootstrap')).rejects.toThrow('VITE_API_ORIGIN');
});
it('explains a backend host rejection',async()=>{
  await expect(readApiResponse(new Response('Invalid host header', {status:400}), '/api/bootstrap')).rejects.toThrow('ASTRA_ALLOWED_HOSTS');
});
it('preserves JSON API errors and successful data',async()=>{
  await expect(readApiResponse(new Response(JSON.stringify({detail:'Review inputs'}), {status:422}), '/api/plans')).rejects.toThrow('Review inputs');
  expect(await readApiResponse(new Response(JSON.stringify({status:'ok'})), '/api/health')).toEqual({status:'ok'});
});
it('routes requests and stored images to the deployed backend',()=>{
  vi.stubEnv('VITE_API_ORIGIN','https://astra-bio-api.onrender.com/');
  expect(apiUrl('/api/telemetry?source=hardware')).toBe('https://astra-bio-api.onrender.com/api/telemetry?source=hardware');
  expect(apiUrl('/api/camera-images/123/content')).toBe('https://astra-bio-api.onrender.com/api/camera-images/123/content');
});
