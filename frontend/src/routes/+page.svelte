<script lang="ts">
  import ProjectRow from '$lib/components/projects/project-row.svelte';
  import Button from '$lib/components/ui/button.svelte';
  import Card from '$lib/components/ui/card.svelte';
  import Table from '$lib/components/ui/table.svelte';
  import { projectStore } from '$lib/stores/projects';
  import { goto } from '$app/navigation';

  const projects = projectStore;

  async function onRunProfiling(projectId: string) {
    await projectStore.startProfiling(projectId);
    await goto(`/projects/${projectId}`);
  }
</script>

<section class="space-y-6">
  <div class="flex flex-wrap items-center justify-between gap-4">
    <div>
      <h1 class="text-2xl font-semibold">Projects dashboard</h1>
      <p class="text-sm text-muted-foreground">Vercel-style project list with quick graph and actions menu.</p>
    </div>
    <a href="/projects/new"><Button>Add new project</Button></a>
  </div>

  <Card class="p-0">
    <Table>
      <thead>
        <tr class="border-b border-border text-left text-muted-foreground">
          <th class="px-4 py-3 text-xs font-medium">Project</th>
          <th class="px-4 py-3 text-xs font-medium">Source</th>
          <th class="px-4 py-3 text-xs font-medium">Profilings</th>
          <th class="px-4 py-3 text-xs font-medium">Actions</th>
        </tr>
      </thead>
      <tbody>
        {#each $projects as project (project.id)}
          <ProjectRow {project} {onRunProfiling} />
        {/each}
      </tbody>
    </Table>
  </Card>
</section>
