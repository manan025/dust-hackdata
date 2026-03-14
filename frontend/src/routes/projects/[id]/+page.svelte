<script lang="ts">
  import ProfilingOverview from '$lib/components/projects/profiling-overview.svelte';
  import ProfilingTable from '$lib/components/projects/profiling-table.svelte';
  import Badge from '$lib/components/ui/badge.svelte';
  import Button from '$lib/components/ui/button.svelte';
  import Card from '$lib/components/ui/card.svelte';
  import { projectStore } from '$lib/stores/projects';
  import type { PageData } from './$types';

  let { data }: { data: PageData } = $props();
  let refreshedAt = $state(new Date().toLocaleTimeString());

  const projectId = $derived(data.project.id);
  const activeProject = $derived(projectStore.byId(projectId) ?? data.project);

  function runProfiling() {
    projectStore.runProfiling(projectId);
  }

  function reloadMetrics() {
    refreshedAt = new Date().toLocaleTimeString();
  }
</script>

<section class="space-y-6">
  <div class="flex flex-wrap items-center justify-between gap-4">
    <div>
      <a href="/" class="text-sm text-muted-foreground hover:underline">Back to dashboard</a>
      <h1 class="mt-1 text-2xl font-semibold">{activeProject.name}</h1>
      <p class="text-sm text-muted-foreground">Detailed profiling and metrics dashboard.</p>
    </div>
    <div class="flex items-center gap-2">
      <Badge>{activeProject.framework}</Badge>
      <Badge>{activeProject.profilingRuns} runs</Badge>
    </div>
  </div>

  <ProfilingOverview project={activeProject} />

  <Card class="space-y-3 p-4">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h2 class="text-lg font-semibold">Manual profiling</h2>
      <div class="text-xs text-muted-foreground">Last reload: {refreshedAt}</div>
    </div>
    <p class="text-sm text-muted-foreground">Start profiling manually, then reload this panel to reflect the latest run counts and metrics.</p>
    <div class="flex flex-wrap gap-2">
      <Button onclick={runProfiling}>Start profiling now</Button>
      <Button variant="outline" onclick={reloadMetrics}>Reload metrics panel</Button>
    </div>
  </Card>

  <ProfilingTable metrics={activeProject.metrics} />
</section>
