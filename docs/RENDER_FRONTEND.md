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

## Atlas access from Render

Set `ASTRA_MONGODB_URI` on the backend service using the complete private Atlas
URI. The backend reads `astra_bio` and the `observations`/`camera_images`
collections by default. Do not put this URI in the frontend.

In Render, open the backend's **Connect → Outbound** panel. Add all listed
CIDR ranges to the cluster project's **Atlas → Network Access → IP Access List**.
For the current service these are `74.220.48.0/24` and `74.220.56.0/24`.
Keep existing gateway/laptop entries. Allowlisting only the laptop's address
does not grant the hosted backend access. Recheck the panel if the service's
region or outbound configuration changes; do not use its inbound DNS address.

`GET /api/database/status` performs a read-only connection check and returns
fixed error codes and next steps without credentials or raw driver errors.
API health and model readiness are independent of database health. Confirm
telemetry and camera reads after the access-list entries show Active.

## Screening models

On Render, the API startup installs the versioned serving bundle declared in
`data/models/deployment.json`. The release archive and every file are SHA256
verified before installation; no PyTorch training/export packages are needed.
Startup fails if the archive is missing or corrupt, rather than advertising
working screening without weights. Subsequent starts reuse verified files when
present. `ASTRA_INSTALL_MODELS=0` explicitly disables startup installation.

The bundle contains base leaf weights, the evaluated fine-tuned candidate,
four fruit detectors, their class mappings, model cards and provenance. It
selects the evaluated fine-tuned leaf candidate on a fresh cloud installation.
Existing deliberate operator selections are preserved. Set `ASTRA_LEAF_MODEL`
to `base` or `plantdoc-20261011T142833Z` to explicitly select a model at startup.
The fine-tuned candidate improves the recorded source benchmark but remains
experimental; uncertain photos remain unresolved under the same score rules.
Training checkpoints, duplicate exports, sample photographs and
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
