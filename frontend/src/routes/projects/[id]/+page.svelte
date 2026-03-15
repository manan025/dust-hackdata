<script lang="ts">
  import ProfilingOverview from '$lib/components/projects/profiling-overview.svelte';
  import ProfilingTable from '$lib/components/projects/profiling-table.svelte';
  import Badge from '$lib/components/ui/badge.svelte';
  import Button from '$lib/components/ui/button.svelte';
  import Card from '$lib/components/ui/card.svelte';
  import { projectStore } from '$lib/stores/projects';
  import { parsePipelineOutput } from '$lib/parsers/pipeline-output';
  import type { PageData } from './$types';

  const SHOW_GRAPH_SECTIONS = false;
  const SHOW_RELOAD_BUTTON = false;

  let { data }: { data: PageData } = $props();
  let refreshedAt = $state(new Date().toLocaleTimeString());

  const projectId = $derived(data.project.id);
  const activeProject = $derived(projectStore.byId(projectId) ?? data.project);
  const sourceUrl = $derived(activeProject.sourceFileUrl ?? activeProject.githubUrl ?? '');
  const historyForSource = $derived(
    (activeProject.profilingHistory ?? []).filter((run) => run.url === sourceUrl)
  );
  const parsedHistory = $derived(
    historyForSource.map((run) => ({ run, parsed: parsePipelineOutput(run.output) }))
  );
  const latestRun = $derived(historyForSource[0]);
  const latestParsed = $derived(latestRun ? parsePipelineOutput(latestRun.output) : null);

  async function runProfiling() {
    await projectStore.startProfiling(projectId);
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
      <p class="text-sm text-muted-foreground">Latest profiling output and run history.</p>
    </div>
    <div class="flex items-center gap-2">
      <Badge>{activeProject.sourceType === 'github' ? 'GitHub' : 'Uploaded source'}</Badge>
      <Badge>{activeProject.profilingRuns} runs</Badge>
    </div>
  </div>

  <Card class="p-4">
    <div class="text-sm text-muted-foreground">Profiling source URL</div>
    <a href={sourceUrl} target="_blank" rel="noreferrer" class="text-sm text-primary hover:underline break-all">{sourceUrl}</a>
  </Card>

  {#if SHOW_GRAPH_SECTIONS}
    <ProfilingOverview project={activeProject} />
  {/if}

  <Card class="space-y-3 p-4">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h2 class="text-lg font-semibold">Manual profiling</h2>
      <div class="text-xs text-muted-foreground">Last reload: {refreshedAt}</div>
    </div>
    <p class="text-sm text-muted-foreground">Run pipeline, wait for completion, and review output plus improved-code ZIP.</p>
    <div class="flex flex-wrap gap-2">
      <Button onclick={runProfiling} disabled={activeProject.isProfiling}>
        {activeProject.isProfiling ? 'Loading...' : 'Start Profile'}
      </Button>
      {#if SHOW_RELOAD_BUTTON}
        <Button variant="outline" onclick={reloadMetrics}>Reload metrics panel</Button>
      {/if}
    </div>

    {#if activeProject.profilingError}
      <div class="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
        {activeProject.profilingError}
      </div>
    {/if}

    {#if latestRun}
      <div class="rounded-md border border-border p-3 space-y-3">
        <div class="text-sm font-medium">Latest output</div>
        <div class="text-xs text-muted-foreground">{new Date(latestRun.createdAt).toLocaleString()}</div>
        <a href={latestRun.zip} target="_blank" rel="noreferrer" class="text-sm text-primary hover:underline break-all">Download improved code ZIP</a>

        {#if latestParsed && latestParsed.iterations.length > 0}
          <div class="space-y-3">
            {#each latestParsed.iterations as iteration}
              <div class="rounded-md border border-border p-3 space-y-2">
                <div class="text-sm font-semibold">{iteration.iterationLabel}</div>
                {#if iteration.summary}
                  <p class="text-xs text-muted-foreground">{iteration.summary}</p>
                {/if}
                {#if iteration.files.length > 0}
                  <div class="space-y-2">
                    <div class="text-xs font-medium">Generated files</div>
                    {#each iteration.files as file}
                      <details class="rounded border border-border p-2">
                        <summary class="cursor-pointer text-xs font-medium">{file.path}</summary>
                        <pre class="mt-2 max-h-64 overflow-auto whitespace-pre-wrap text-xs text-muted-foreground">{file.content}</pre>
                      </details>
                    {/each}
                  </div>
                {/if}
              </div>
            {/each}
          </div>
        {:else}
          <pre class="max-h-96 overflow-auto whitespace-pre-wrap text-xs text-muted-foreground">{latestRun.output}</pre>
        {/if}
      </div>
    {/if}
  </Card>

  <Card class="space-y-3 p-4">
    <h3 class="text-base font-semibold">History for this source link</h3>
    {#if historyForSource.length === 0}
      <p class="text-sm text-muted-foreground">No runs yet for this source URL.</p>
    {:else}
      <div class="space-y-3">
        {#each parsedHistory as item, index (item.run.id)}
          <div class="rounded-md border border-border p-3 space-y-2">
            <div class="flex items-center justify-between gap-2">
              <div class="text-sm font-medium">Run #{parsedHistory.length - index}</div>
              <div class="text-xs text-muted-foreground">{new Date(item.run.createdAt).toLocaleString()}</div>
            </div>
            <a href={item.run.zip} target="_blank" rel="noreferrer" class="text-sm text-primary hover:underline break-all">{item.run.zip}</a>
            {#if item.parsed.iterations.length > 0}
              {#each item.parsed.iterations as iteration}
                <div class="rounded-md border border-border p-2 space-y-1">
                  <div class="text-xs font-semibold">{iteration.iterationLabel}</div>
                  {#if iteration.summary}
                    <p class="text-xs text-muted-foreground">{iteration.summary}</p>
                  {/if}
                  {#if iteration.files.length > 0}
                    <div class="text-xs text-muted-foreground">
                      Files: {iteration.files.map((file) => file.path).join(', ')}
                    </div>
                  {/if}
                </div>
              {/each}
            {:else}
              <pre class="max-h-64 overflow-auto whitespace-pre-wrap text-xs text-muted-foreground">{item.run.output}</pre>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  </Card>

  {#if SHOW_GRAPH_SECTIONS}
    <ProfilingTable metrics={activeProject.metrics} />
  {/if}
</section>
