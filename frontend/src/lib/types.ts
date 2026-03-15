export type Architecture = 'x86_64' | 'arm64' | 'wasm32' | 'riscv64';

export type SourceType = 'github' | 'upload';

export type ProfilingMetric = {
  id: string;
  startedAt: string;
  durationMs: number;
  cpuPercent: number;
  memoryMb: number;
};

export type ProfilingRunRecord = {
  id: string;
  createdAt: string;
  url: string;
  output: string;
  zip: string;
};

export type Project = {
  id: string;
  name: string;
  sourceType: SourceType;
  githubUrl?: string;
  sourceFileName?: string;
  sourceFileUrl?: string;
  architectures: Architecture[];
  profilingRuns: number;
  trend: number[];
  metrics: ProfilingMetric[];
  isProfiling?: boolean;
  profilingError?: string;
  lastProfilingOutput?: string;
  lastProfiledAt?: string;
  lastImprovedZip?: string;
  profilingHistory: ProfilingRunRecord[];
};

export type NewProjectPayload = {
  name: string;
  sourceType: SourceType;
  githubUrl?: string;
  sourceFileName?: string;
  sourceFileUrl?: string;
  architectures: Architecture[];
};
