import type { Project } from '$lib/types';

const now = Date.now();

export const initialProjects: Project[] = [
  {
    id: 'proj-1',
    name: 'checkout-service',
    framework: 'SvelteKit',
    sourceType: 'github',
    githubUrl: 'https://github.com/acme/checkout-service',
    binaryFileName: 'checkout-linux-amd64',
    architectures: ['x86_64', 'arm64'],
    profilingRuns: 6,
    trend: [42, 44, 43, 45, 47, 49],
    metrics: [
      {
        id: 'm-1',
        startedAt: new Date(now - 1000 * 60 * 90).toISOString(),
        durationMs: 1190,
        cpuPercent: 61,
        memoryMb: 198
      },
      {
        id: 'm-2',
        startedAt: new Date(now - 1000 * 60 * 40).toISOString(),
        durationMs: 1130,
        cpuPercent: 58,
        memoryMb: 205
      }
    ]
  },
  {
    id: 'proj-2',
    name: 'image-inference',
    framework: 'Svelte + Rust',
    sourceType: 'upload',
    sourceFileName: 'image-inference.zip',
    binaryFileName: 'inference.wasm',
    architectures: ['wasm32', 'x86_64'],
    profilingRuns: 3,
    trend: [58, 52, 51, 48, 49, 47],
    metrics: [
      {
        id: 'm-3',
        startedAt: new Date(now - 1000 * 60 * 70).toISOString(),
        durationMs: 1320,
        cpuPercent: 72,
        memoryMb: 291
      }
    ]
  }
];

