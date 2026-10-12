import React from 'react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import CameraImages from './CameraImages.jsx';

const newestId = '507f1f77bcf86cd799439011', olderId = '507f1f77bcf86cd799439012';
const photo = (overrides = {}) => ({id: newestId, device_id: 'esp32-cam-01', source: 'hardware',
  sample_id: 'photo-42', received_at_utc: new Date(Date.now() - 45000).toISOString(), captured_at_utc: null,
  width: 640, height: 480, bytes: 12345, sha256: 'a'.repeat(64),
  content_url: '/api/camera-images/' + (overrides.id || newestId) + '/content', ...overrides});
const collection = (items = [], overrides = {}) => ({items, storage: {backend: 'mongodb', configured: true, connected: true}, ...overrides});
const deferred = () => {let resolve, reject; const promise = new Promise((yes, no) => {resolve = yes; reject = no;}); return {promise, resolve, reject};};
const loadedImage = () => screen.findByRole('img', {name: 'Stored camera photograph from esp32-cam-01'});

afterEach(cleanup);

describe('Stored camera images', () => {
  it('loads hardware JPEGs and shows source, original dimensions and actual receipt evidence', async () => {
    const request = vi.fn().mockResolvedValue(collection([photo()]));
    render(<CameraImages request={request}/>);
    const image = await loadedImage();
    expect(request).toHaveBeenCalledWith('/camera-images?source=hardware&limit=24');
    expect(image.getAttribute('src')).toBe('/api/camera-images/' + newestId + '/content');
    expect(image.getAttribute('width')).toBe('640');
    expect(image.getAttribute('height')).toBe('480');
    expect(screen.getByText(/640 × 480 px · Original JPEG/)).toBeTruthy();
    expect(screen.getByText(/Received recently/)).toBeTruthy();
    expect(screen.getByText('Device capture time').nextElementSibling.textContent).toBe('Not reported');
    expect(screen.getByText('Sample ID').nextElementSibling.textContent).toBe('photo-42');
    expect(screen.getByRole('link', {name: 'Open original JPEG'}).getAttribute('href')).toBe(image.getAttribute('src'));
    expect(screen.getByText(/Images are displayed only/)).toBeTruthy();
    expect(request).toHaveBeenCalledTimes(1);
  });

  it('clears photos while refreshing and does not show a result if the refresh fails', async () => {
    const retry = deferred();
    const request = vi.fn().mockResolvedValueOnce(collection([photo()])).mockReturnValueOnce(retry.promise);
    render(<CameraImages request={request}/>); await loadedImage();
    fireEvent.click(screen.getByRole('button', {name: 'Refresh camera images'}));
    expect(screen.queryByRole('img')).toBeNull();
    expect(screen.getByRole('status').textContent).toContain('Checking stored camera images');
    await act(async () => retry.reject(new Error('Image storage unavailable.')));
    expect(screen.getByRole('alert').textContent).toBe('Image storage unavailable.');
    expect(screen.queryByRole('img')).toBeNull();
    expect(request).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('button', {name: 'Refresh camera images'}).disabled).toBe(false);
  });

  it('labels synthetic images and withholds records from another source even if the API mixes channels', async () => {
    const syntheticPhoto = photo({source: 'synthetic'});
    const request = vi.fn().mockResolvedValueOnce(collection([syntheticPhoto])).mockResolvedValueOnce(collection([photo(), syntheticPhoto]));
    render(<CameraImages request={request}/>);
    await screen.findByRole('heading', {name: 'No stored images for this selection'});
    expect(screen.queryByRole('img')).toBeNull();
    fireEvent.change(screen.getByLabelText('Camera source'), {target: {value: 'synthetic'}});
    await loadedImage();
    expect(request).toHaveBeenLastCalledWith('/camera-images?source=synthetic&limit=24');
    expect(screen.getByText(/SYNTHETIC IMAGE — this channel/)).toBeTruthy();
    expect(screen.getByText(/Synthetic test image · 640/)).toBeTruthy();
    expect(screen.getByText('Synthetic test image', {selector: '.status-chip'})).toBeTruthy();
  });

  it('applies a device filter explicitly and rejects returned photos from another device', async () => {
    const request = vi.fn().mockResolvedValue(collection([photo(), photo({id: olderId, device_id: 'another-camera'})]));
    render(<CameraImages request={request}/>); await loadedImage();
    fireEvent.change(screen.getByLabelText('Camera device ID'), {target: {value: '  another-camera  '}});
    expect(request).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', {name: 'Apply camera filter'}));
    await screen.findByRole('img', {name: 'Stored camera photograph from another-camera'});
    expect(request).toHaveBeenLastCalledWith('/camera-images?source=hardware&limit=24&device_id=another-camera');
    expect(screen.queryByRole('img', {name: 'Stored camera photograph from esp32-cam-01'})).toBeNull();
    expect(screen.queryByRole('navigation', {name: 'Stored camera image history'})).toBeNull();
  });

  it('ignores a late result when the source changes', async () => {
    const hardware = deferred();
    const request = vi.fn().mockReturnValueOnce(hardware.promise).mockResolvedValueOnce(collection([photo({source: 'synthetic'})]));
    render(<CameraImages request={request}/>);
    fireEvent.change(screen.getByLabelText('Camera source'), {target: {value: 'synthetic'}});
    await loadedImage();
    await act(async () => hardware.resolve(collection([photo({device_id: 'late-hardware'})])));
    expect(screen.queryByRole('img', {name: 'Stored camera photograph from late-hardware'})).toBeNull();
    expect(screen.getByText(/Synthetic test image · 640/)).toBeTruthy();
  });

  it('switches original images through the accessible history and does not imply an old photo is live', async () => {
    const older = photo({id: olderId, received_at_utc: new Date(Date.now() - 7200000).toISOString(), sample_id: 'photo-41'});
    render(<CameraImages request={vi.fn().mockResolvedValue(collection([photo(), older]))}/>);
    await loadedImage();
    const history = screen.getByRole('navigation', {name: 'Stored camera image history'});
    const chooseOlder = within(history).getByRole('button', {name: 'View stored photo 2 from esp32-cam-01'});
    fireEvent.click(chooseOlder);
    expect((await loadedImage()).getAttribute('src')).toBe('/api/camera-images/' + olderId + '/content');
    expect(chooseOlder.getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByText(/Older stored image · 2 hours/)).toBeTruthy();
    expect(screen.getByText(/does not establish that the camera is online/)).toBeTruthy();
    expect(screen.getByText('Sample ID').nextElementSibling.textContent).toBe('photo-41');
  });

  it('distinguishes a USB serial relay from direct Wi-Fi delivery', async () => {
    const images = [photo({transport: 'serial_bridge'}), photo({id: olderId, transport: 'wifi_https'})];
    render(<CameraImages request={vi.fn().mockResolvedValue(collection(images))}/>); await loadedImage();
    expect(screen.getByText('Delivery transport').nextElementSibling.textContent).toBe('USB serial → laptop gateway');
    fireEvent.click(screen.getByRole('button', {name: 'View stored photo 2 from esp32-cam-01'}));
    expect(screen.getByText('Delivery transport').nextElementSibling.textContent).toBe('Wi-Fi → HTTPS gateway');
  });

  it('displays image-byte retrieval failure separately from metadata and can retry', async () => {
    const request = vi.fn().mockResolvedValue(collection([photo()]));
    render(<CameraImages request={request}/>);
    fireEvent.error(await loadedImage());
    expect(screen.getByRole('alert').textContent).toContain('Stored photo could not be displayed');
    expect(screen.getByText('Sample ID').nextElementSibling.textContent).toBe('photo-42');
    fireEvent.click(screen.getByRole('button', {name: 'Refresh camera images'}));
    await loadedImage();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('never loads external or mismatched image URLs', async () => {
    const request = vi.fn().mockResolvedValue(collection([
      photo({content_url: 'https://example.com/private.jpg'}),
      photo({id: '../escape', content_url: '/api/camera-images/../escape/content'}),
      photo({id: olderId, content_url: '/api/camera-images/' + newestId + '/content'}),
    ]));
    render(<CameraImages request={request}/>);
    await screen.findByRole('heading', {name: 'No stored images for this selection'});
    expect(screen.queryByRole('img')).toBeNull();
    expect(screen.queryByRole('link', {name: 'Open original JPEG'})).toBeNull();
  });

  it('bounds the history to 24 photos', async () => {
    const items = Array.from({length: 30}, (_, index) => photo({id: index.toString(16).padStart(24, '0')}));
    render(<CameraImages request={vi.fn().mockResolvedValue(collection(items))}/>);
    await loadedImage();
    expect(within(screen.getByRole('navigation', {name: 'Stored camera image history'})).getAllByRole('button')).toHaveLength(24);
  });

  it.each([
    [collection([], {storage: {backend: 'mongodb', configured: false, connected: false}}), 'Camera image storage is not configured.'],
    [collection([]), 'No stored images for this selection'],
    [{images: []}, 'Camera image list was not returned.'],
  ])('handles unavailable configuration, empty data or invalid responses (%j)', async (result, message) => {
    render(<CameraImages request={vi.fn().mockResolvedValue(result)}/>);
    await waitFor(() => expect(screen.getByText(new RegExp(message.replaceAll('.', '\\.')))).toBeTruthy());
    expect(screen.queryByRole('img')).toBeNull();
  });
});
