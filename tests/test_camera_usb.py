"""USB fallback verification with fake serial and HTTPS only; no physical COM access."""
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from io import BytesIO
import json
from pathlib import Path
import sys

from PIL import Image
import pytest

HELPER = Path(__file__).resolve().parents[1] / "integration" / "esp32-camera-mongodb" / "capture_usb.py"
spec = spec_from_file_location("camera_usb_helper", HELPER)
usb = module_from_spec(spec)
sys.modules[spec.name] = usb
spec.loader.exec_module(usb)

DEVICE_TOKEN = "unit-test-token-not-a-physical-device"
CONFIG = '\n'.join([
    '#define GATEWAY_URL "https://192.168.1.50:8502/v1/telemetry"',
    '#define DEVICE_ID "tray-01"',
    '#define DEVICE_TOKEN ' + json.dumps(DEVICE_TOKEN),
    '#define ROOT_CA R"PEM(-----BEGIN CERTIFICATE-----\nfake-unit-test-certificate\n-----END CERTIFICATE-----\n)PEM"',
])


class FakeSerial:
    def __init__(self, data=b""):
        self.remaining = bytearray(data)
        self.writes = []
        self.flushed = False

    def read(self, size):
        length = min(size, 7, len(self.remaining))
        result = bytes(self.remaining[:length])
        del self.remaining[:length]
        return result

    def write(self, data):
        self.writes.append(data)
        return len(data)

    def flush(self):
        self.flushed = True


@pytest.fixture
def jpeg():
    stream = BytesIO()
    Image.new("RGB", (8, 6), (60, 110, 50)).save(stream, format="JPEG")
    return stream.getvalue()


def framed(image, *, digest=None, width=8, height=6, sample="cam-unit-test-1", suffix=None):
    return (b"Camera initialized successfully!\r\n" +
        f"ASTRA_JPEG_BEGIN:{len(image)}:{digest or sha256(image).hexdigest()}:{sample}:{width}:{height}\n".encode() +
        image + (usb.END_MARKER if suffix is None else suffix))


def receipt(capture, **overrides):
    image = {"id": "507f1f77bcf86cd799439011", "device_id": "tray-01", "source": "hardware", "transport": "serial_bridge",
        "sample_id": capture.sample_id, "sha256": capture.sha256, "width": capture.width, "height": capture.height,
        "bytes": len(capture.image), "captured_at_utc": None, "received_at_utc": "2026-10-12T08:00:00Z", **overrides}
    return {"id": image["id"], "duplicate": False, "image": image}


def test_private_config_parses_json_escapes_and_raw_pem_without_eval():
    config = usb.parse_config(CONFIG)
    assert config.endpoint == "https://192.168.1.50:8502/v1/images"
    assert config.device_id == "tray-01" and config.token == DEVICE_TOKEN
    assert config.root_ca.startswith("-----BEGIN CERTIFICATE-----\n")
    assert DEVICE_TOKEN not in repr(config) and "fake-unit-test-certificate" not in repr(config)
    quoted = CONFIG.split('#define ROOT_CA', 1)[0] + '#define ROOT_CA "-----BEGIN CERTIFICATE-----\\n" \\\n "fake-unit-test-certificate\\n" \\\n "-----END CERTIFICATE-----\\n"'
    assert usb.parse_config(quoted).root_ca == config.root_ca


@pytest.mark.parametrize("url", ["http://192.168.1.50:8502/v1/images", "https://8.8.8.8/v1/images",
    "https://example.com/v1/images", "https://token@192.168.1.50/v1/images", "https://192.168.1.50/v1/images?secret=1",
    "https://192.168.1.50/v1/wrong"])
def test_config_refuses_external_or_unverified_endpoint(url):
    text = CONFIG + '\n#define IMAGE_GATEWAY_URL ' + json.dumps(url)
    with pytest.raises(usb.CaptureError):
        usb.parse_config(text)


def test_fragmented_serial_transfer_is_byte_exact_and_has_real_jpeg_dimensions(jpeg):
    stream = FakeSerial(framed(jpeg))
    capture = usb.read_frame(stream)
    assert capture.image == jpeg and capture.sha256 == sha256(jpeg).hexdigest()
    assert (capture.width, capture.height) == (8, 6)
    assert capture.sample_id == "cam-unit-test-1" and stream.writes == []


@pytest.mark.parametrize("changes", [{"digest": "0" * 64}, {"width": 7}, {"suffix": b"\nASTRA_JPEG_BAD\n"}])
def test_transfer_refuses_hash_dimension_or_end_marker_mismatch(jpeg, changes):
    with pytest.raises(usb.CaptureError):
        usb.read_frame(FakeSerial(framed(jpeg, **changes)))


def test_frame_refuses_oversize_before_reading_image_and_bounds_wait():
    header = f"ASTRA_JPEG_BEGIN:{usb.MAX_IMAGE_BYTES + 1}:{'0' * 64}:sample:8:6\n".encode()
    with pytest.raises(usb.CaptureError, match="2 MiB"):
        usb.read_frame(FakeSerial(header))
    clock = iter([0, 61])
    with pytest.raises(usb.CaptureError, match="timed out"):
        usb.read_frame(FakeSerial(), clock=lambda: next(clock))


def test_marker_and_jpeg_structure_are_required(jpeg):
    with pytest.raises(usb.CaptureError, match="complete JPEG"):
        usb.read_frame(FakeSerial(framed(jpeg[:-2])))
    with pytest.raises(usb.CaptureError, match="malformed"):
        usb.read_frame(FakeSerial(b"ASTRA_JPEG_BEGIN:invalid\n"))


class FakeResponse:
    status = 201

    def __init__(self, value):
        self.data = json.dumps(value).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, count):
        return self.data[:count]


class FakeOpener:
    def __init__(self, response):
        self.response = response
        self.request = None

    def open(self, request, timeout):
        self.request = request
        assert timeout == 30
        return FakeResponse(self.response)


def test_https_upload_sends_actual_jpeg_labels_serial_transport_then_acknowledges_exact_sample(jpeg):
    config = usb.parse_config(CONFIG)
    stream = FakeSerial(framed(jpeg))
    capture = usb.read_frame(stream)
    opener = FakeOpener(receipt(capture) | {"unexpected_private_field": "not printable"})
    stored = usb.upload_capture(config, capture, opener=opener)
    assert opener.request.full_url == config.endpoint and opener.request.data == jpeg
    headers = dict((key.lower(), value) for key, value in opener.request.header_items())
    assert headers["content-type"] == "image/jpeg" and headers["authorization"] == "Bearer " + DEVICE_TOKEN
    assert headers["x-source"] == "hardware" and headers["x-transport"] == "serial_bridge"
    assert headers["x-device-id"] == "tray-01" and headers["x-sample-id"] == capture.sample_id
    assert "x-captured-at" not in headers and "unexpected_private_field" not in stored
    usb.acknowledge(stream, capture, stored)
    assert stream.writes == [b"a cam-unit-test-1\n"] and stream.flushed


@pytest.mark.parametrize("changes", [{"sha256": "0" * 64}, {"sample_id": "wrong-sample"}, {"device_id": "other-device"},
    {"source": "synthetic"}, {"transport": "wifi_https"}, {"width": 4}, {"bytes": 0}, {"id": "invalid"}])
def test_mismatched_receipt_never_acknowledges_board(jpeg, changes):
    config = usb.parse_config(CONFIG)
    stream = FakeSerial(framed(jpeg))
    capture = usb.read_frame(stream)
    with pytest.raises(usb.CaptureError, match="does not match"):
        usb.upload_capture(config, capture, opener=FakeOpener(receipt(capture, **changes)))
    assert stream.writes == []


def test_exact_duplicate_can_preserve_original_wifi_transport(jpeg):
    config = usb.parse_config(CONFIG)
    capture = usb.read_frame(FakeSerial(framed(jpeg)))
    original = receipt(capture, transport="wifi_https") | {"duplicate": True}
    stored = usb.validate_receipt(original, config, capture)
    assert stored["transport"] == "wifi_https" and stored["duplicate"] is True


def test_ack_refuses_wrong_sample_or_hash(jpeg):
    stream = FakeSerial()
    capture = usb.Capture(jpeg, sha256(jpeg).hexdigest(), "sample", 8, 6)
    with pytest.raises(usb.CaptureError):
        usb.acknowledge(stream, capture, {"sample_id": "other", "sha256": capture.sha256})
    assert stream.writes == []


def test_https_uses_private_root_ca_and_refuses_redirects(monkeypatch, jpeg):
    config = usb.parse_config(CONFIG)
    capture = usb.read_frame(FakeSerial(framed(jpeg)))
    contexts = []
    context = object()
    monkeypatch.setattr(usb.ssl, "create_default_context", lambda **kwargs: contexts.append(kwargs) or context)
    handlers = []
    def build(*values):
        handlers.extend(values)
        return FakeOpener(receipt(capture))
    monkeypatch.setattr(usb.urllib.request, "build_opener", build)
    usb.upload_capture(config, capture)
    assert contexts == [{"cadata": config.root_ca}]
    assert any(isinstance(handler, usb.urllib.request.HTTPSHandler) and handler._context is context for handler in handlers)
    assert any(isinstance(handler, usb.urllib.request.ProxyHandler) and handler.proxies == {} for handler in handlers)
    redirect = next(handler for handler in handlers if isinstance(handler, usb.NoRedirect))
    with pytest.raises(usb.CaptureError, match="redirect refused"):
        redirect.redirect_request(None, None, 302, "redirect", None, "https://external.invalid/")


def test_optional_output_is_off_by_default_and_confined_to_ignored_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(usb, "PROJECT_ROOT", tmp_path)
    assert usb.output_path(None) is None
    assert usb.output_path("runtime/camera/photo.jpg") == (tmp_path / "runtime" / "camera" / "photo.jpg").resolve()
    for path in ("data/photo.jpg", "runtime/../public/photo.jpg", "runtime/photo.json"):
        with pytest.raises(usb.CaptureError):
            usb.output_path(path)
