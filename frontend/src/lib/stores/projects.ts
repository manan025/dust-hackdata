import { browser } from '$app/environment';
import { get, writable } from 'svelte/store';
import { initialProjects } from '$lib/mock-data';
import type { NewProjectPayload, Project, ProfilingMetric } from '$lib/types';

const STORAGE_KEY = 'profiling_dashboard_projects';

function normalizeProject(project: Project): Project {
  return {
    ...project,
    isProfiling: project.isProfiling ?? false,
    profilingHistory: project.profilingHistory ?? []
  };
}

function loadProjects() {
  if (!browser) return initialProjects.map(normalizeProject);
  const saved = localStorage.getItem(STORAGE_KEY);
  if (!saved) return initialProjects.map(normalizeProject);

  try {
    return (JSON.parse(saved) as Project[]).map(normalizeProject);
  } catch {
    return initialProjects.map(normalizeProject);
  }
}

function nextMetric(): ProfilingMetric {
  return {
    id: crypto.randomUUID(),
    startedAt: new Date().toISOString(),
    durationMs: Math.floor(900 + Math.random() * 700),
    cpuPercent: Math.floor(45 + Math.random() * 40),
    memoryMb: Math.floor(180 + Math.random() * 150)
  };
}

function createProjectStore() {
  const store = writable<Project[]>(loadProjects());

  if (browser) {
    store.subscribe((value) => {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
    });
  }

  return {
    subscribe: store.subscribe,
    addProject(payload: NewProjectPayload) {
      store.update((projects) => {
        const created: Project = {
          id: crypto.randomUUID(),
          name: payload.name,
          sourceType: payload.sourceType,
          githubUrl: payload.githubUrl,
          sourceFileName: payload.sourceFileName,
          sourceFileUrl: payload.sourceFileUrl,
          architectures: payload.architectures,
          profilingRuns: 0,
          trend: [45, 43, 47, 44, 46, 45],
          metrics: [],
          isProfiling: false,
          profilingHistory: []
        };
        return [created, ...projects];
      });
    },
    runProfiling(projectId: string) {
      store.update((projects) =>
        projects.map((project) => {
          if (project.id !== projectId) return project;

          const metric = nextMetric();
          const nextPoint = Math.max(30, Math.min(85, metric.cpuPercent + (Math.random() > 0.5 ? 3 : -3)));

          return {
            ...project,
            profilingRuns: project.profilingRuns + 1,
            trend: [...project.trend.slice(-5), nextPoint],
            metrics: [metric, ...project.metrics],
            isProfiling: false
          };
        })
      );
    },
    async startProfiling(projectId: string) {
      const project = get(store).find((item) => item.id === projectId);
      if (!project) return { ok: false };

      const sourceUrl = project.sourceFileUrl ?? project.githubUrl;

      if (!sourceUrl) {
        store.update((projects) =>
          projects.map((item) =>
            item.id === projectId ? { ...item, profilingError: 'No source URL found for this project.', isProfiling: false } : item
          )
        );
        return { ok: false };
      }

      store.update((projects) =>
        projects.map((item) =>
          item.id === projectId ? { ...item, isProfiling: true, profilingError: undefined } : item
        )
      );

      try {
        const response = await fetch('/api/profiling/run', {
          method: 'POST',
          headers: {
            'content-type': 'application/json'
          },
          body: JSON.stringify({ url: sourceUrl })
        });

        const result = (await response.json()) as { output?: string; zip?: string; error?: string };

        if (!response.ok || !result.output || !result.zip) {
          throw new Error(result.error ?? 'Profiling request failed.');
        }

        const metric = nextMetric();
        const nextPoint = Math.max(30, Math.min(85, metric.cpuPercent + (Math.random() > 0.5 ? 3 : -3)));
        const historyRun = {
          id: crypto.randomUUID(),
          createdAt: new Date().toISOString(),
          url: sourceUrl,
          output: result.output,
          zip: result.zip
        };

        store.update((projects) =>
          projects.map((item) => {
            if (item.id !== projectId) return item;
            return {
              ...item,
              profilingRuns: item.profilingRuns + 1,
              trend: [...item.trend.slice(-5), nextPoint],
              metrics: [metric, ...item.metrics],
              lastProfilingOutput: result.output,
              lastImprovedZip: result.zip,
              lastProfiledAt: historyRun.createdAt,
              profilingHistory: [historyRun, ...(item.profilingHistory ?? [])],
              isProfiling: false,
              profilingError: undefined
            };
          })
        );

        return { ok: true };
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Profiling request failed.';
        store.update((projects) =>
          projects.map((item) => (item.id === projectId ? { ...item, isProfiling: false, profilingError: message } : item))
        );
        return { ok: false, error: message };
      }
    },
    byId(projectId: string) {
      return get(store).find((project) => project.id === projectId);
    }
  };
}

export const projectStore = createProjectStore();
