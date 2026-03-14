<script lang="ts">
  import Card from '$lib/components/ui/card.svelte';
  import Table from '$lib/components/ui/table.svelte';
  import type { ProfilingMetric } from '$lib/types';

  let { metrics }: { metrics: ProfilingMetric[] } = $props();
</script>

<Card class="p-0">
  <Table>
    <thead>
      <tr class="border-b border-border text-left text-muted-foreground">
        <th class="px-4 py-3 text-xs font-medium">Started at</th>
        <th class="px-4 py-3 text-xs font-medium">Duration (ms)</th>
        <th class="px-4 py-3 text-xs font-medium">CPU (%)</th>
        <th class="px-4 py-3 text-xs font-medium">Memory (MB)</th>
      </tr>
    </thead>
    <tbody>
      {#if metrics.length === 0}
        <tr>
          <td class="px-4 py-8 text-center text-muted-foreground" colspan="4">No profiling runs yet.</td>
        </tr>
      {:else}
        {#each metrics as metric}
          <tr class="border-b border-border">
            <td class="px-4 py-3">{new Date(metric.startedAt).toLocaleString()}</td>
            <td class="px-4 py-3">{metric.durationMs}</td>
            <td class="px-4 py-3">{metric.cpuPercent}</td>
            <td class="px-4 py-3">{metric.memoryMb}</td>
          </tr>
        {/each}
      {/if}
    </tbody>
  </Table>
</Card>

