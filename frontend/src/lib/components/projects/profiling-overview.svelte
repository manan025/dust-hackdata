<script lang="ts">
  import Card from '$lib/components/ui/card.svelte';
  import MetricGraph from '$lib/components/ui/metric-graph.svelte';
  import Progress from '$lib/components/ui/progress.svelte';
  import type { Project } from '$lib/types';

  let { project }: { project: Project } = $props();

  const latestCpu = $derived(project.metrics[0]?.cpuPercent ?? 0);
  const latestMem = $derived(project.metrics[0]?.memoryMb ?? 0);
</script>

<div class="grid gap-4 lg:grid-cols-3">
  <Card class="p-4 lg:col-span-2">
    <div class="mb-2 text-sm font-medium">CPU trend</div>
    <MetricGraph values={project.trend} />
  </Card>

  <Card class="space-y-3 p-4">
    <div>
      <div class="text-sm text-muted-foreground">Latest CPU</div>
      <div class="text-2xl font-semibold">{latestCpu}%</div>
      <Progress value={latestCpu} class="mt-2" />
    </div>
    <div>
      <div class="text-sm text-muted-foreground">Latest Memory</div>
      <div class="text-2xl font-semibold">{latestMem} MB</div>
    </div>
    <div>
      <div class="text-sm text-muted-foreground">Total Profilings</div>
      <div class="text-2xl font-semibold">{project.profilingRuns}</div>
    </div>
  </Card>
</div>
