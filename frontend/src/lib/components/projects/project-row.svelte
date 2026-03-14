<script lang="ts">
  import Badge from '$lib/components/ui/badge.svelte';
  import Button from '$lib/components/ui/button.svelte';
  import Dropdown from '$lib/components/ui/dropdown.svelte';
  import MetricGraph from '$lib/components/ui/metric-graph.svelte';
  import type { Project } from '$lib/types';

  let {
    project,
    onRunProfiling
  }: {
    project: Project;
    onRunProfiling: (projectId: string) => void;
  } = $props();

  let showGraph = $state(false);
</script>

<tr class="border-b border-border align-top">
  <td class="px-4 py-4 font-medium text-primary">
    <a href={`/projects/${project.id}`} class="hover:underline">{project.name}</a>
  </td>
  <td class="px-4 py-4 text-muted-foreground">
    {#if project.sourceType === 'github'}
      GitHub
    {:else}
      Uploaded file{project.sourceFileName ? `: ${project.sourceFileName}` : ''}
    {/if}
  </td>
  <td class="px-4 py-4">
    <Badge>{project.profilingRuns} runs</Badge>
  </td>
  <td class="px-4 py-4">
    <div class="flex items-center gap-2">
      <Button variant="outline" size="sm" onclick={() => (showGraph = !showGraph)}>
        Graph
      </Button>
      <Dropdown>
        <span slot="trigger">...</span>
        <button class="block w-full rounded px-2 py-1 text-left text-sm hover:bg-accent" onclick={() => onRunProfiling(project.id)}>
          Start profiling
        </button>
        <a href={`/projects/${project.id}`} class="block rounded px-2 py-1 text-sm hover:bg-accent">Open details</a>
      </Dropdown>
    </div>
    {#if showGraph}
      <div class="mt-2 rounded-md border border-border p-2 text-muted-foreground">
        <MetricGraph values={project.trend} />
      </div>
    {/if}
  </td>
</tr>
