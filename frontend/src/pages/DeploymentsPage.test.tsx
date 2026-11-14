import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Deployment } from '../types';

const apiMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  delete: vi.fn(),
}));

vi.mock('../api/client', () => ({ default: apiMock }));

import { DeploymentsPage } from './DeploymentsPage';

const endpointUrl = 'https://current-name.trycloudflare.com';

function makeDeployment(overrides: Partial<Deployment> = {}): Deployment {
  return {
    id: 'deployment-1',
    project_id: 'project-1',
    environment_id: 'environment-1',
    release_id: 'release-1',
    status: 'active',
    strategy: 'rolling',
    progress: 100,
    is_simulated: false,
    adapter_name: 'k8s-production-adapter',
    logs: [],
    metadata_info: {
      endpoint_status: 'ready',
      public_url: endpointUrl,
      endpoint_details: {
        status: 'ready',
        tunnel_provider: 'cloudflare-quick-tunnel',
        tunnel_process_state: 'running',
      },
    },
    started_at: '2026-11-13T00:00:00Z',
    ...overrides,
  };
}

function response(data: unknown) {
  return { data: { data } };
}

function setupApi(deployment: Deployment) {
  apiMock.get.mockImplementation((path: string) => {
    if (path === '/deployments?limit=50') return Promise.resolve(response([deployment]));
    if (path === '/projects') {
      return Promise.resolve(response([{ id: 'project-1', name: 'test-project' }]));
    }
    if (path === `/deployments/${deployment.id}`) return Promise.resolve(response(deployment));
    if (path.endsWith('/health-checks')) return Promise.resolve(response([]));
    if (path.endsWith('/endpoint')) return Promise.resolve(response(deployment));
    return Promise.reject(new Error(`Unexpected API request: ${path}`));
  });
}

describe('DeploymentsPage public endpoint handling', () => {
  beforeEach(() => {
    apiMock.get.mockReset();
    apiMock.post.mockReset();
    apiMock.delete.mockReset();
    vi.spyOn(window, 'alert').mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('uses the same verified URL for card, selected details, opening, and copying', async () => {
    const deployment = makeDeployment();
    setupApi(deployment);
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });

    render(<DeploymentsPage />);

    const cardUrls = await screen.findAllByText(endpointUrl);
    expect(cardUrls).toHaveLength(2);
    fireEvent.click(screen.getAllByText('test-project')[0]);

    const openLink = await screen.findByRole('link', { name: /Open Application/i });
    expect(openLink).toHaveAttribute('href', endpointUrl);
    expect(screen.getByText('Quick Tunnel URLs change when a tunnel is recreated.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Copy URL' }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(endpointUrl));
    expect(screen.getAllByText(endpointUrl)).toHaveLength(2);
  });

  it('shows loading and failure states when endpoint discovery fails', async () => {
    const pending = makeDeployment({
      metadata_info: {
        endpoint_status: 'pending',
        endpoint_error: 'Cloudflare is still starting.',
      },
    });
    setupApi(pending);

    let resolveEndpoint: ((value: ReturnType<typeof response>) => void) | undefined;
    apiMock.get.mockImplementation((path: string) => {
      if (path.endsWith('/endpoint')) {
        return new Promise((resolve) => {
          resolveEndpoint = resolve;
        });
      }
      if (path === '/deployments?limit=50') return Promise.resolve(response([pending]));
      if (path === '/projects') {
        return Promise.resolve(response([{ id: 'project-1', name: 'test-project' }]));
      }
      if (path === `/deployments/${pending.id}`) return Promise.resolve(response(pending));
      if (path.endsWith('/health-checks')) return Promise.resolve(response([]));
      return Promise.reject(new Error(`Unexpected API request: ${path}`));
    });

    render(<DeploymentsPage />);
    fireEvent.click((await screen.findAllByText('test-project'))[0]);
    expect(await screen.findByText('Checking Kubernetes readiness and public endpoint...')).toBeInTheDocument();

    const failed = makeDeployment({
      metadata_info: {
        endpoint_status: 'error',
        endpoint_error: 'Public health check failed.',
      },
    });
    await act(async () => {
      resolveEndpoint?.(response(failed));
    });

    expect(await screen.findAllByText('Verifying public endpoint failed')).toHaveLength(3);
    expect(screen.getByText('Public health check failed.')).toBeInTheDocument();
  });

  it('does not display an invalid private URL even when the API marks it ready', async () => {
    const invalid = makeDeployment({
      metadata_info: {
        endpoint_status: 'ready',
        public_url: 'http://10.0.0.5:3000',
        endpoint_details: { status: 'ready' },
      },
    });
    setupApi(invalid);

    render(<DeploymentsPage />);

    expect(await screen.findAllByText('Waiting for Kubernetes service readiness')).toHaveLength(3);
    expect(screen.queryByRole('link', { name: /Open Application/i })).toBeNull();
    expect(screen.queryByText('http://10.0.0.5:3000')).toBeNull();
  });

  it('refreshes the selected deployment endpoint on demand', async () => {
    const deployment = makeDeployment();
    const refreshedUrl = 'https://refreshed-name.trycloudflare.com';
    const refreshed = makeDeployment({
      metadata_info: {
        endpoint_status: 'ready',
        public_url: refreshedUrl,
        endpoint_details: {
          status: 'ready',
          tunnel_provider: 'cloudflare-quick-tunnel',
          tunnel_process_state: 'running',
        },
      },
    });
    setupApi(deployment);
    apiMock.get.mockImplementation((path: string) => {
      if (path.endsWith('/endpoint')) return Promise.resolve(response(refreshed));
      if (path === '/deployments?limit=50') return Promise.resolve(response([deployment]));
      if (path === '/projects') {
        return Promise.resolve(response([{ id: 'project-1', name: 'test-project' }]));
      }
      if (path === `/deployments/${deployment.id}`) return Promise.resolve(response(deployment));
      if (path.endsWith('/health-checks')) return Promise.resolve(response([]));
      return Promise.reject(new Error(`Unexpected API request: ${path}`));
    });

    render(<DeploymentsPage />);
    fireEvent.click((await screen.findAllByText('test-project'))[0]);
    fireEvent.click(await screen.findByRole('button', { name: 'Refresh Endpoint' }));

    await waitFor(() => {
      expect(screen.getAllByText(refreshedUrl)).toHaveLength(2);
    });
    expect(screen.queryByText(endpointUrl)).toBeNull();
    expect(apiMock.get).toHaveBeenCalledWith(
      `/deployments/${deployment.id}/endpoint`,
    );
  });

  it('does not let an older list response overwrite a newer endpoint result', async () => {
    vi.useFakeTimers();
    const stale = makeDeployment({
      metadata_info: {
        endpoint_status: 'pending',
      },
    });
    let staleListResolve: ((value: ReturnType<typeof response>) => void) | undefined;
    let listCalls = 0;
    apiMock.get.mockImplementation((path: string) => {
      if (path === '/deployments?limit=50') {
        listCalls += 1;
        if (listCalls === 2) {
          return new Promise((resolve) => {
            staleListResolve = resolve;
          });
        }
        return Promise.resolve(response([stale]));
      }
      if (path === '/projects') {
        return Promise.resolve(response([{ id: 'project-1', name: 'test-project' }]));
      }
      if (path === `/deployments/${stale.id}/health-checks`) {
        return Promise.resolve(response([]));
      }
      if (path.endsWith('/endpoint')) {
        return Promise.resolve(
          response(
            makeDeployment({
              metadata_info: {
                endpoint_status: 'ready',
                public_url: endpointUrl,
                endpoint_details: {
                  status: 'ready',
                  tunnel_provider: 'cloudflare-quick-tunnel',
                  tunnel_process_state: 'running',
                },
              },
            }),
          ),
        );
      }
      return Promise.reject(new Error(`Unexpected API request: ${path}`));
    });

    render(<DeploymentsPage />);
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(8000);
    });
    expect(apiMock.get).toHaveBeenCalledWith(`/deployments/${stale.id}/endpoint`);

    await act(async () => {
      staleListResolve?.(response([stale]));
      await Promise.resolve();
    });
    expect(screen.getAllByText(endpointUrl)).toHaveLength(2);
  });
});
