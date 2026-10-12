"""A separate HTTPS ingress exposes only authenticated ESP32 telemetry, not the planner."""
from __future__ import annotations

from datetime import datetime, timezone
import json

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .mongo_runtime import GatewaySettings, MongoConfigurationError, load_settings, telemetry_reader
from .mongo_telemetry import MongoTelemetryUnavailable
from .storage import FLAGS, RANGES, validate_observation

MAX_PACKET_BYTES = 16384
ALLOWED = {"device_id", "sample_id", "source", "ts_utc", *RANGES, *FLAGS}


def create_app(settings: GatewaySettings | None = None, store=None) -> FastAPI:
    settings_supplied = settings is not None
    if settings is None:
        settings = load_settings()
    gateway = FastAPI(title="ASTRA-BIO ESP32 telemetry", docs_url=None, redoc_url=None, openapi_url=None)
    hosts = ["127.0.0.1", "localhost"]
    if settings:
        hosts.append(settings.lan_host)
    gateway.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

    @gateway.middleware("http")
    async def gateway_requests(request: Request, call_next):
        if request.url.scheme != "https":
            return JSONResponse({"detail": "Use the verified HTTPS telemetry endpoint."}, status_code=403)
        if request.headers.get("origin"):
            return JSONResponse({"detail": "This endpoint accepts device requests only."}, status_code=403)
        result = await call_next(request)
        result.headers["Cache-Control"] = "no-store"
        result.headers["X-Content-Type-Options"] = "nosniff"
        return result

    def authenticate(request: Request) -> str:
        active_settings = settings if settings_supplied else load_settings()
        header = request.headers.get("authorization", "")
        token = header[7:] if header.startswith("Bearer ") else ""
        if len(token) > 256 or not token or active_settings is None:
            raise HTTPException(401, "Invalid device token.", headers={"WWW-Authenticate": "Bearer"})
        device = active_settings.authenticated_device(token)
        if device is None:
            raise HTTPException(401, "Invalid device token.", headers={"WWW-Authenticate": "Bearer"})
        return device

    def repository():
        result = store if store is not None else telemetry_reader()
        if result is None:
            raise MongoConfigurationError("MongoDB has not been configured.")
        return result

    @gateway.exception_handler(MongoTelemetryUnavailable)
    @gateway.exception_handler(MongoConfigurationError)
    async def unavailable(request, error):
        return JSONResponse({"detail": "MongoDB telemetry is unavailable. Retry this same sample later."},
            status_code=503, headers={"Retry-After": "10"})

    @gateway.get("/v1/health")
    def health(request: Request):
        authenticate(request)
        status = repository().status()
        return JSONResponse({"service": "astra-bio-telemetry", "storage": status},
            status_code=200 if status["connected"] else 503)

    @gateway.post("/v1/telemetry")
    async def ingest(request: Request):
        device = authenticate(request)
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise HTTPException(415, "Send application/json.")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_PACKET_BYTES:
                raise HTTPException(413, "Telemetry exceeds 16 KiB.")
        try:
            payload = json.loads(body, parse_constant=lambda value: (_ for _ in ()).throw(ValueError()))
        except (ValueError, UnicodeError):
            raise HTTPException(422, "Telemetry must be valid finite JSON.") from None
        if not isinstance(payload, dict) or set(payload) - ALLOWED:
            raise HTTPException(422, "Telemetry contains unsupported fields.")
        if payload.get("device_id") != device:
            raise HTTPException(403, "The device token may publish only its own readings.")
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        timestamp = payload.get("ts_utc")
        payload["ts_utc"] = timestamp if timestamp is not None else now
        payload.update(transport="https", received_at_utc=now,
            device_ts_utc=timestamp, timestamp_origin="device" if timestamp is not None else "gateway",
            actuation_enabled=False)
        try:
            validate_observation(payload)
            result = await run_in_threadpool(repository().ingest, payload)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        return JSONResponse({**result, "storage": "mongodb", "actuation_enabled": False},
            status_code=200 if result["duplicate"] else 201)

    return gateway


app = create_app()
