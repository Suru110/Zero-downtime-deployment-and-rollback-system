import { describe, expect, it } from 'vitest';
import { isPublicHttpUrl, resolvePublicUrl } from './publicUrl';

describe('isPublicHttpUrl', () => {
  it.each([
    ['https://dynamic-name.trycloudflare.com', true],
    ['https://example.com/application', true],
    ['http://127.0.0.1:3000', false],
    ['http://localhost:3000', false],
    ['http://10.0.0.5', false],
    ['http://172.20.1.2', false],
    ['http://192.168.1.2', false],
    ['http://169.254.1.2', false],
    ['http://[::1]', false],
    ['http://[fc00::1]', false],
    ['https://[2606:4700:4700::1111]', true],
    ['http://app.namespace.svc.cluster.local', false],
    ['https://user:password@example.com', false],
    ['', false],
    ['not a URL', false],
    ['ftp://example.com', false],
  ])('validates %s', (url, expected) => {
    expect(isPublicHttpUrl(url)).toBe(expected);
  });
});

describe('resolvePublicUrl', () => {
  it('resolves the verified top-level public URL', () => {
    expect(
      resolvePublicUrl({
        endpoint_status: 'ready',
        public_url: 'https://dynamic-name.trycloudflare.com',
      }),
    ).toBe('https://dynamic-name.trycloudflare.com');
  });

  it('supports a verified URL nested under endpoint_details', () => {
    expect(
      resolvePublicUrl({
        endpoint_status: 'ready',
        endpoint_details: {
          status: 'ready',
          public_url: 'https://example.com',
        },
      }),
    ).toBe('https://example.com');
  });

  it('rejects local URLs and unverified endpoint states', () => {
    expect(
      resolvePublicUrl({
        endpoint_status: 'ready',
        public_url: 'http://127.0.0.1:3000',
      }),
    ).toBeUndefined();
    expect(
      resolvePublicUrl({
        endpoint_status: 'pending',
        public_url: 'https://example.com',
      }),
    ).toBeUndefined();
    expect(
      resolvePublicUrl({
        endpoint_status: 'ready',
        endpoint_details: { status: 'pending' },
        public_url: 'https://example.com',
      }),
    ).toBeUndefined();
    expect(
      resolvePublicUrl({
        endpoint_status: 'ready',
        adapter_details: { public_url: 'https://example.com' },
      }),
    ).toBeUndefined();
  });
});
