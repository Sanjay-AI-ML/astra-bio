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

## Screening models

On Render, the API startup installs the versioned serving bundle declared in
`data/models/deployment.json`. The release archive and every file are SHA256
verified before installation; no PyTorch training/export packages are needed.
Startup fails if the archive is missing or corrupt, rather than advertising
working screening without weights. Subsequent starts reuse verified files when
present. `ASTRA_INSTALL_MODELS=0` explicitly disables startup installation.

The bundle contains base leaf weights, the evaluated fine-tuned candidate,
four fruit detectors, their class mappings, model cards and provenance. It
preserves the current base leaf selection and any later deliberate operator
selection. Training checkpoints, duplicate exports, sample photographs and
datasets are excluded. Inference never downloads weights during an upload.

For a local explicit install of the same serving bundle:

```powershell
.\.venv\Scripts\python.exe -m astra_bio.model_deployment
```

Check `/api/plant-overview/status` for leaf readiness and `/api/fruit-models` for
fruit availability. Fruit registry listing checks files without loading all
detectors. The selected graph is validated before inference; one fruit session
is cached and one fruit request is processed at a time to bound memory use.

To rebuild a release from verified local artifacts, use
`python scripts/package-models.py`, publish the generated archive and commit its
manifest together with the deployment changes. Retain the bundled model cards
and notices; artifact licenses remain separate from the application license.

These settings enable deployment connectivity. They do not add user accounts or
authentication. Anyone who can reach the hosted prototype may access its API;
use demonstration crew data for a public deployment.
