import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from astra_bio.hosting import hosting_settings


def test_render_frontend_preflight_and_backend_host(monkeypatch):
    monkeypatch.setenv('RENDER_EXTERNAL_HOSTNAME', 'astra-bio-api.onrender.com')
    monkeypatch.setenv('ASTRA_ALLOWED_ORIGINS', 'https://astra-bio-ui.onrender.com/')
    monkeypatch.delenv('ASTRA_ALLOWED_HOSTS', raising=False)
    hosts, origins = hosting_settings()
    app = FastAPI()
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)
    app.add_middleware(CORSMiddleware, allow_origins=sorted(origins), allow_methods=['GET','POST'], allow_headers=['Content-Type'])
    @app.get('/api/health')
    def health():
        return {'status': 'ok'}
    client = TestClient(app, base_url='https://astra-bio-api.onrender.com')
    response = client.options('/api/health', headers={'Origin':'https://astra-bio-ui.onrender.com',
        'Access-Control-Request-Method':'POST', 'Access-Control-Request-Headers':'content-type'})
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'https://astra-bio-ui.onrender.com'
    assert client.get('/api/health').status_code == 200
    assert client.get('/api/health', headers={'Host':'untrusted.example'}).status_code == 400
    assert client.options('/api/health', headers={'Origin':'https://untrusted.example',
        'Access-Control-Request-Method':'POST'}).status_code == 400


@pytest.mark.parametrize('origin', ['*','https://site.example/api','https://site.example?query=1'])
def test_invalid_browser_origin_is_rejected(monkeypatch, origin):
    monkeypatch.setenv('ASTRA_ALLOWED_ORIGINS', origin)
    with pytest.raises(ValueError):
        hosting_settings()
