import { describe, expect, it } from 'vitest';
import { get } from 'svelte/store';
import { projectStore } from '$lib/stores/projects';

describe('projectStore', () => {
  it('adds a project and increments profiling runs', () => {
    const before = get(projectStore).length;

    projectStore.addProject({
      name: 'unit-test-project',
      sourceType: 'github',
      githubUrl: 'https://github.com/acme/unit-test-project',
      architectures: ['x86_64']
    });

    const all = get(projectStore);
    expect(all.length).toBe(before + 1);

    const created = all.find((item) => item.name === 'unit-test-project');
    expect(created).toBeDefined();

    if (!created) return;

    projectStore.runProfiling(created.id);
    const updated = get(projectStore).find((item) => item.id === created.id);
    expect(updated?.profilingRuns).toBe(1);
    expect(updated?.metrics.length).toBe(1);
  });
});
