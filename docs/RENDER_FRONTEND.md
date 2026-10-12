# Deploy the ASTRA-BIO frontend to Render

Create a **Static Site** from `Sanjay-AI-ML/astra-bio`, using the same branch as
the backend. This repository's Git root is `astra-bio`, so use:

| Setting | Value |
| --- | --- |
| Root directory | `frontend` |
| Build command | `npm ci && npm run build` |
| Publish directory | `dist` |
| Environment variable | `VITE_API_ORIGIN=https://astra-bio-api.onrender.com` |

The URL is public build-time configuration; never put MongoDB credentials or
Gemini keys in frontend environment variables. The app uses hash routes, so
`/#leaf` and `/#fruit` work without a catch-all rewrite. Do not rewrite `/api`
to `index.html`.

After Render assigns the Static Site URL, set these backend environment variables:

```text
ASTRA_ALLOWED_HOSTS=astra-bio-api.onrender.com
ASTRA_ALLOWED_ORIGINS=https://astra-bio.onrender.com
```

Use the exact frontend origin with no path. Custom domains can be added as
comma-separated origins. Render's `RENDER_EXTERNAL_HOSTNAME` is also recognized
automatically. Deploy the backend changes and restart/redeploy it after updating
these environment variables. Use `uvicorn astra_bio.api:app --host 0.0.0.0 --port $PORT`
as the backend start command if serving this FastAPI app directly.

Verify `/api/health` and `/api/bootstrap` on the backend, then load the frontend
and submit a sample simulation, test leaf/fruit uploads, and refresh Live devices.
Requests, telemetry, camera image URLs and template downloads all use the backend
origin. If a POST returns 403, check `ASTRA_ALLOWED_ORIGINS`; if a request returns
400 "Invalid host header", check `ASTRA_ALLOWED_HOSTS`. A 503 camera-storage
response indicates backend storage configuration, not a frontend build failure.

These settings enable deployment connectivity. They do not add user accounts or
authentication. Anyone who can reach the hosted prototype may access its API;
use demonstration crew data for a public deployment.
