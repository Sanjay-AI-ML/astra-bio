"""Optional USB JPEG relay: ESP32 serial -> verified HTTPS -> MongoDB Atlas.

Nothing accesses a COM port on import. The default execution keeps the JPEG in
memory and acknowledges the board only after a matching storage receipt. This
is a serial_bridge transport, not evidence that board Wi-Fi uploads succeeded.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from hashlib import sha256
import ipaddress
import json
from pathlib import Path
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = Path(__file__).resolve().parent / "include" / "config.h"
MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_CAMERA_PIXELS = 20_000_000
SERIAL_TIMEOUT_SECONDS = 60
END_MARKER = b"\nASTRA_JPEG_END\n"
FRAME_HEADER = re.compile(rb"ASTRA_JPEG_BEGIN:([0-9]{1,7}):([a-fA-F0-9]{64}):([A-Za-z0-9_-]{1,96}):([0-9]{1,5}):([0-9]{1,5})\n")


class CaptureError(Exception):
    """A deliberately public message containing no private header values."""


@dataclass(frozen=True)
class DeviceConfig:
    endpoint: str
    device_id: str
    token: str = field(repr=False)
    root_ca: str = field(repr=False)


@dataclass(frozen=True)
class Capture:
    image: bytes = field(repr=False)
    sha256: str
    sample_id: str
    width: int
    height: int


def _define(text: str, name: str, *, optional: bool = False) -> str | None:
    # Generated C headers use JSON-compatible escapes and occasionally adjacent
    # quoted literals or a multiline R"PEM(...)PEM" certificate. Never eval C.
    text = re.sub(r"\\\r?\n", " ", text)
    matches = list(re.finditer(r"(?m)^[ \t]*#[ \t]*define[ \t]+" + re.escape(name) + r"[ \t]+", text))
    if not matches and optional:
        return None
    if len(matches) != 1:
        raise CaptureError("Private camera header has a missing or duplicate required setting.")
    remaining = text[matches[0].end():]
    if remaining.startswith('R"'):
        match = re.match(r'R"([A-Za-z0-9_]{0,16})\(([\s\S]*?)\)\1"', remaining)
        if not match:
            raise CaptureError("Private camera header contains an invalid raw string.")
        trailing = remaining[match.end():].split("\n", 1)[0].strip()
        if trailing and not trailing.startswith("//"):
            raise CaptureError("Private camera header contains an unsupported string expression.")
        return match.group(2)
    expression = remaining.split("\n", 1)[0].strip()
    chunks = []
    while expression:
        if expression.startswith("//"):
            break
        match = re.match(r'"(?:\\.|[^"\\])*"', expression)
        if not match:
            raise CaptureError("Private camera header contains an unsupported string expression.")
        try:
            chunks.append(json.loads(match.group(0)))
        except (ValueError, TypeError):
            raise CaptureError("Private camera header contains an invalid string escape.") from None
        expression = expression[match.end():].strip()
    if not chunks:
        raise CaptureError("Private camera header contains an empty setting expression.")
    return "".join(chunks)


def parse_config(text: str) -> DeviceConfig:
    endpoint = _define(text, "IMAGE_GATEWAY_URL", optional=True)
    if endpoint is None:
        endpoint = _define(text, "GATEWAY_URL")
        if endpoint and endpoint.endswith("/v1/telemetry"):
            endpoint = endpoint[:-len("/v1/telemetry")] + "/v1/images"
    try:
        url = urllib.parse.urlsplit(endpoint or "")
        address = ipaddress.ip_address(url.hostname or "")
        port = url.port
    except ValueError:
        raise CaptureError("Camera gateway must use a configured private LAN IP address.") from None
    allowed_networks = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
    private = any(address.version == network.version and address in network
                  for network in map(ipaddress.ip_network, allowed_networks))
    if (url.scheme != "https" or not private or url.username is not None or url.password is not None
            or url.path != "/v1/images" or url.query or url.fragment or port == 0):
        raise CaptureError("Camera gateway must be HTTPS /v1/images on the configured private LAN.")
    device_id, token, root_ca = (_define(text, name) for name in ("DEVICE_ID", "DEVICE_TOKEN", "ROOT_CA"))
    if not isinstance(device_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", device_id):
        raise CaptureError("Private camera header has an invalid device identity.")
    if (not isinstance(token, str) or not 16 <= len(token) <= 512 or token.startswith("REPLACE_")
            or any(ord(character) < 33 or ord(character) > 126 for character in token)):
        raise CaptureError("Private camera header needs the generated device authentication token.")
    if not root_ca or "-----BEGIN CERTIFICATE-----" not in root_ca or "REPLACE_" in root_ca:
        raise CaptureError("Private camera header needs the generated gateway root certificate.")
    return DeviceConfig(endpoint, device_id, token, root_ca)


def read_config(path: Path) -> DeviceConfig:
    try:
        if path.stat().st_size > 65536:
            raise CaptureError("Private camera header exceeds the supported size.")
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        raise CaptureError("Private camera configuration could not be read.") from None
    return parse_config(text)


def jpeg_dimensions(image: bytes) -> tuple[int, int]:
    """Check complete JPEG markers and read bounded SOF dimensions.

    This is structural checking, not entropy decoding. The HTTPS gateway also
    fully decodes the image before storage and acknowledgment.
    """
    if not image.startswith(b"\xff\xd8") or not image.endswith(b"\xff\xd9"):
        raise CaptureError("Serial image is not a complete JPEG.")
    cursor = 2
    sof = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while cursor < len(image) - 2:
        if image[cursor] != 0xFF:
            raise CaptureError("Serial JPEG contains an invalid header marker.")
        while cursor < len(image) and image[cursor] == 0xFF:
            cursor += 1
        if cursor >= len(image):
            break
        marker = image[cursor]
        cursor += 1
        if marker in {0x00, 0xD8, 0xD9, 0xDA}:
            break
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:
            continue
        if cursor + 2 > len(image):
            break
        size = int.from_bytes(image[cursor:cursor + 2], "big")
        if size < 2 or cursor + size > len(image) - 2:
            break
        if marker in sof:
            if size < 8:
                break
            height = int.from_bytes(image[cursor + 3:cursor + 5], "big")
            width = int.from_bytes(image[cursor + 5:cursor + 7], "big")
            if width < 1 or height < 1 or width * height > MAX_CAMERA_PIXELS:
                raise CaptureError("Serial JPEG dimensions exceed the supported range.")
            return width, height
        cursor += size
    raise CaptureError("Serial JPEG has no valid frame dimensions.")


def _read_exact(serial_port, count: int, deadline: float, clock) -> bytes:
    data = bytearray()
    while len(data) < count:
        if clock() >= deadline:
            raise CaptureError("USB JPEG transfer timed out; the frame remains pending on the board.")
        chunk = serial_port.read(min(16384, count - len(data)))
        if chunk:
            data.extend(chunk)
    return bytes(data)


def read_frame(serial_port, timeout: float = SERIAL_TIMEOUT_SECONDS, *, clock=time.monotonic) -> Capture:
    if not 0 < timeout <= SERIAL_TIMEOUT_SECONDS:
        raise CaptureError("USB read timeout must be between 0 and 60 seconds.")
    deadline = clock() + timeout
    while True:
        line = bytearray()
        while not line.endswith(b"\n"):
            line.extend(_read_exact(serial_port, 1, deadline, clock))
            if len(line) > 512:
                raise CaptureError("USB serial header exceeds the supported size.")
        if not line.startswith(b"ASTRA_JPEG_BEGIN:"):
            # Diagnostics are intentionally discarded instead of printed.
            continue
        match = FRAME_HEADER.fullmatch(line)
        if not match:
            raise CaptureError("USB JPEG frame header is malformed.")
        length, expected_sha, sample_id, width, height = match.groups()
        length, width, height = int(length), int(width), int(height)
        if not 0 < length <= MAX_IMAGE_BYTES:
            raise CaptureError("USB JPEG frame must contain 1 byte to 2 MiB.")
        if width < 1 or height < 1 or width * height > MAX_CAMERA_PIXELS:
            raise CaptureError("USB JPEG frame dimensions exceed the supported range.")
        image = _read_exact(serial_port, length, deadline, clock)
        if _read_exact(serial_port, len(END_MARKER), deadline, clock) != END_MARKER:
            raise CaptureError("USB JPEG end marker was not received intact.")
        digest = sha256(image).hexdigest()
        if digest != expected_sha.decode("ascii").lower():
            raise CaptureError("USB JPEG SHA-256 does not match the board's declared image.")
        if jpeg_dimensions(image) != (width, height):
            raise CaptureError("USB JPEG dimensions do not match the frame declaration.")
        return Capture(image, digest, sample_id.decode("ascii"), width, height)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        raise CaptureError("Image gateway redirect refused; the frame remains pending.")


def upload_capture(config: DeviceConfig, capture: Capture, *, opener=None) -> dict:
    if opener is None:
        try:
            context = ssl.create_default_context(cadata=config.root_ca)
        except (ssl.SSLError, ValueError):
            raise CaptureError("Gateway root certificate is invalid; verified HTTPS could not start.") from None
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=context), NoRedirect())
    request = urllib.request.Request(config.endpoint, data=capture.image, method="POST", headers={
        "Content-Type": "image/jpeg", "Authorization": "Bearer " + config.token,
        "X-Device-Id": config.device_id, "X-Sample-Id": capture.sample_id,
        "X-Source": "hardware", "X-Transport": "serial_bridge",
    })
    try:
        with opener.open(request, timeout=30) as response:
            if response.status not in {200, 201}:
                raise CaptureError("Image gateway did not confirm storage; the frame remains pending.")
            encoded = response.read(65537)
            if len(encoded) > 65536:
                raise CaptureError("Image gateway receipt exceeds the supported size.")
            receipt = json.loads(encoded)
    except urllib.error.HTTPError as error:
        raise CaptureError("Image gateway rejected the upload (HTTP " + str(error.code) + "); the frame remains pending.") from None
    except (urllib.error.URLError, OSError, ValueError):
        raise CaptureError("Verified image upload failed; the frame remains pending. Check the gateway and network.") from None
    return validate_receipt(receipt, config, capture)


def validate_receipt(receipt, config: DeviceConfig, capture: Capture) -> dict:
    metadata = receipt.get("image") if isinstance(receipt, dict) else None
    valid_transport = isinstance(metadata, dict) and (metadata.get("transport") == "serial_bridge" or
        (receipt.get("duplicate") is True and metadata.get("transport") == "wifi_https"))
    if (not isinstance(metadata, dict) or not isinstance(receipt.get("id"), str)
            or not re.fullmatch(r"[a-fA-F0-9]{24}", receipt["id"]) or metadata.get("id") != receipt["id"]
            or metadata.get("sample_id") != capture.sample_id or metadata.get("sha256") != capture.sha256
            or metadata.get("device_id") != config.device_id or metadata.get("source") != "hardware"
            or not valid_transport or metadata.get("bytes") != len(capture.image)
            or metadata.get("width") != capture.width or metadata.get("height") != capture.height):
        raise CaptureError("Storage receipt does not match this camera frame; no acknowledgment was sent.")
    # Explicit allowlist excludes unexpected response fields from console output.
    return {**{key: metadata.get(key) for key in ("id", "device_id", "source", "transport", "sample_id",
        "received_at_utc", "captured_at_utc", "width", "height", "bytes", "sha256")}, "duplicate": receipt.get("duplicate") is True}


def acknowledge(serial_port, capture: Capture, receipt: dict) -> None:
    if (receipt.get("sample_id") != capture.sample_id or receipt.get("sha256") != capture.sha256
            or not isinstance(receipt.get("id"), str) or not re.fullmatch(r"[a-fA-F0-9]{24}", receipt["id"])
            or receipt.get("source") != "hardware" or receipt.get("width") != capture.width
            or receipt.get("height") != capture.height or receipt.get("bytes") != len(capture.image)):
        raise CaptureError("Camera acknowledgment requires a matching storage receipt.")
    command = ("a " + capture.sample_id + "\n").encode("ascii")
    if serial_port.write(command) != len(command):
        raise CaptureError("USB acknowledgment was incomplete; check whether the board still has the frame.")
    serial_port.flush()


def output_path(value: str | None) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()
    if (not path.is_relative_to((PROJECT_ROOT / "runtime").resolve()) or path.suffix.lower() not in {".jpg", ".jpeg"}
            or path.exists()):
        raise CaptureError("Optional output must be a new .jpg or .jpeg file inside the ignored project runtime directory.")
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Capture a real ESP32 JPEG over USB and relay it through verified HTTPS to Atlas.")
    parser.add_argument("--port", required=True, help="Attached COM port, for example COM8")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Ignored private include/config.h (never printed)")
    parser.add_argument("--output", help="Optional new JPEG path inside ignored runtime; default keeps image in memory")
    arguments = parser.parse_args(argv)
    serial_port = None
    try:
        config = read_config(arguments.config)
        destination = output_path(arguments.output)
        try:
            import serial
        except ImportError:
            raise CaptureError("pyserial is required for USB capture. Install it in the hardware tooling environment.") from None
        # Configure control lines before opening; do not reset or toggle BOOT/EN.
        serial_port = serial.Serial(port=None, baudrate=115200, timeout=0.25, write_timeout=5)
        serial_port.dtr = False
        serial_port.rts = False
        serial_port.port = arguments.port
        serial_port.open()
        if serial_port.write(b"s\n") != 2:
            raise CaptureError("USB capture command was not transmitted completely.")
        serial_port.flush()
        capture = read_frame(serial_port)
        if destination is not None:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as handle:
                handle.write(capture.image)
        receipt = upload_capture(config, capture)
        acknowledge(serial_port, capture, receipt)
        print("Stored actual camera JPEG through USB serial -> verified HTTPS -> MongoDB Atlas.")
        print(json.dumps(receipt, indent=2))
        return 0
    except CaptureError as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception:
        # Driver/network exception messages can contain configuration context.
        print("USB camera relay failed. No automatic discard or reset was requested; inspect the device and gateway.", file=sys.stderr)
        return 1
    finally:
        if serial_port is not None:
            try:
                serial_port.close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
