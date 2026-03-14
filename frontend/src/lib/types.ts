export type Architecture = 'x86_64' | 'arm64' | 'wasm32' | 'riscv64';

export type SourceType = 'github' | 'upload';

export type ProfilingMetric = {
  id: string;
  startedAt: string;
  durationMs: number;
  cpuPercent: number;
  memoryMb: number;
};

export type Project = {
  id: string;
  name: string;
  sourceType: SourceType;
  githubUrl?: string;
  sourceFileName?: string;
  sourceFileUrl?: string;
  binaryFileName: string;
  architectures: Architecture[];
  profilingRuns: number;
  trend: number[];
  metrics: ProfilingMetric[];
};

export type NewProjectPayload = {
  name: string;
  sourceType: SourceType;
  githubUrl?: string;
  sourceFileName?: string;
  sourceFileUrl?: string;
  binaryFileName: string;
  architectures: Architecture[];
};
