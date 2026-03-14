import { browser } from '$app/environment';
import { get, writable } from 'svelte/store';
import { initialProjects } from '$lib/mock-data';
import type { NewProjectPayload, Project, ProfilingMetric } from '$lib/types';

const STORAGE_KEY = 'profiling_dashboard_projects';

function loadProjects() {
  if (!browser) return initialProjects;
  const saved = localStorage.getItem(STORAGE_KEY);
  if (!saved) return initialProjects;

  try {
    return JSON.parse(saved) as Project[];
  } catch {
    return initialProjects;
  }
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
          binaryFileName: payload.binaryFileName,
          architectures: payload.architectures,
          profilingRuns: 0,
          trend: [45, 43, 47, 44, 46, 45],
          metrics: []
        };
        return [created, ...projects];
      });
    },
    runProfiling(projectId: string) {
      store.update((projects) =>
        projects.map((project) => {
          if (project.id !== projectId) return project;

          const metric: ProfilingMetric = {
            id: crypto.randomUUID(),
            startedAt: new Date().toISOString(),
            durationMs: Math.floor(900 + Math.random() * 700),
            cpuPercent: Math.floor(45 + Math.random() * 40),
            memoryMb: Math.floor(180 + Math.random() * 150)
          };

          const nextPoint = Math.max(30, Math.min(85, metric.cpuPercent + (Math.random() > 0.5 ? 3 : -3)));

          return {
            ...project,
            profilingRuns: project.profilingRuns + 1,
            trend: [...project.trend.slice(-5), nextPoint],
            metrics: [metric, ...project.metrics]
          };
        })
      );
    },
    byId(projectId: string) {
      return get(store).find((project) => project.id === projectId);
    }
  };
}

export const projectStore = createProjectStore();
