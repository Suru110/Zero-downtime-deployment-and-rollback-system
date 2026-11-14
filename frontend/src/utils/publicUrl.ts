const NON_PUBLIC_SUFFIXES = [
  '.localhost',
  '.local',
  '.internal',
  '.svc',
  '.cluster.local',
  '.home.arpa',
  '.test',
  '.invalid',
];

interface EndpointDetails {
  status?: unknown;
  public_url?: unknown;
  tunnel_provider?: unknown;
}

interface DeploymentEndpointMetadata extends Record<string, unknown> {
  endpoint_status?: unknown;
  public_url?: unknown;
  endpoint_details?: EndpointDetails;
}

function isPublicIpv4(host: string): boolean {
  const octets = host.split('.');
  if (
    octets.length !== 4 ||
    octets.some((octet) => !/^\d+$/.test(octet) || Number(octet) > 255)
  ) {
    return false;
  }
  const parts = octets.map(Number);

  const [first, second, third] = parts;
  if (
    first === 0 ||
    first === 10 ||
    first === 127 ||
    first >= 224 ||
    (first === 100 && second >= 64 && second <= 127) ||
    (first === 169 && second === 254) ||
    (first === 172 && second >= 16 && second <= 31) ||
    (first === 192 && second === 168) ||
    (first === 192 && second === 0 && third === 0) ||
    (first === 192 && second === 0 && third === 2) ||
    (first === 192 && second === 88 && third === 99) ||
    (first === 198 && (second === 18 || second === 19)) ||
    (first === 198 && second === 51 && third === 100) ||
    (first === 203 && second === 0 && third === 113)
  ) {
    return false;
  }
  return true;
}

function parseIpv6(host: string): number[] | undefined {
  if (host.includes('%')) return undefined;
  let value = host.toLowerCase();
  const ipv4 = value.match(/(?:^|:)(\d+\.\d+\.\d+\.\d+)$/);
  if (ipv4) {
    if (!isPublicIpv4(ipv4[1])) return undefined;
    const octets = ipv4[1].split('.').map(Number);
    const encoded = [
      ((octets[0] << 8) | octets[1]).toString(16),
      ((octets[2] << 8) | octets[3]).toString(16),
    ];
    value = value.slice(0, -ipv4[1].length) + encoded.join(':');
  }

  const halves = value.split('::');
  if (halves.length > 2) return undefined;
  const left = halves[0] ? halves[0].split(':') : [];
  const right = halves.length === 2 && halves[1] ? halves[1].split(':') : [];
  const missing = 8 - left.length - right.length;
  if ((halves.length === 1 && missing !== 0) || (halves.length === 2 && missing < 1)) {
    return undefined;
  }
  const groups = [
    ...left,
    ...Array(halves.length === 2 ? missing : 0).fill('0'),
    ...right,
  ];
  if (groups.length !== 8 || groups.some((group) => !/^[0-9a-f]{1,4}$/.test(group))) {
    return undefined;
  }
  return groups.map((group) => parseInt(group, 16));
}

function isPublicHost(hostname: string): boolean {
  const host = hostname.replace(/^\[|\]$/g, '').toLowerCase().replace(/\.$/, '');
  if (
    !host ||
    host === 'localhost' ||
    NON_PUBLIC_SUFFIXES.some((suffix) => host.endsWith(suffix))
  ) {
    return false;
  }

  if (host.includes(':')) {
    const groups = parseIpv6(host);
    if (!groups) return false;
    const globalUnicast = groups[0] >= 0x2000 && groups[0] <= 0x3fff;
    const documentation = groups[0] === 0x2001 && groups[1] === 0x0db8;
    return globalUnicast && !documentation;
  }

  if (/^[\d.]+$/.test(host)) return isPublicIpv4(host);
  const labels = host.split('.');
  return (
    labels.length >= 2 &&
    labels.every((label) => /^[a-z\d](?:[a-z\d-]{0,61}[a-z\d])?$/i.test(label))
  );
}

export function isPublicHttpUrl(value: unknown): value is string {
  if (typeof value !== 'string' || !value.trim()) return false;
  try {
    const parsed = new URL(value.trim());
    return (
      ['http:', 'https:'].includes(parsed.protocol) &&
      !parsed.username &&
      !parsed.password &&
      isPublicHost(parsed.hostname)
    );
  } catch {
    return false;
  }
}

export function resolvePublicUrl(
  metadata: DeploymentEndpointMetadata | undefined,
): string | undefined {
  if (!metadata) return undefined;
  const details = metadata.endpoint_details;
  const statuses = [metadata.endpoint_status, details?.status].filter(
    (status): status is string => typeof status === 'string',
  );
  if (!statuses.length || statuses.some((status) => status !== 'ready')) return undefined;

  const candidates = [metadata.public_url, details?.public_url];
  return candidates.find(
    (candidate): candidate is string =>
      typeof candidate === 'string' && candidate.trim().startsWith('http'),
  );
}
