<script lang="ts">
  import Button from '$lib/components/ui/button.svelte';
  import Card from '$lib/components/ui/card.svelte';
  import Checkbox from '$lib/components/ui/checkbox.svelte';
  import Input from '$lib/components/ui/input.svelte';
  import Label from '$lib/components/ui/label.svelte';
  import { projectStore } from '$lib/stores/projects';
  import type { Architecture, SourceType } from '$lib/types';
  import { goto } from '$app/navigation';

  const architectureOptions: Architecture[] = ['x86_64', 'arm64', 'wasm32', 'riscv64'];

  let sourceType = $state<SourceType>('github');
  let name = $state('');
  let framework = $state('SvelteKit');
  let githubUrl = $state('');
  let sourceFileName = $state('');
  let binaryFileName = $state('');
  let selectedArchitectures = $state<Architecture[]>(['x86_64']);
  let error = $state('');

  function toggleArchitecture(architecture: Architecture, checked: boolean) {
    if (checked) {
      selectedArchitectures = Array.from(new Set([...selectedArchitectures, architecture]));
      return;
    }

    selectedArchitectures = selectedArchitectures.filter((item) => item !== architecture);
  }

  async function submit() {
    error = '';

    if (!name.trim()) {
      error = 'Project name is required.';
      return;
    }

    if (sourceType === 'github' && !githubUrl.trim()) {
      error = 'GitHub URL is required for GitHub source mode.';
      return;
    }

    if (sourceType === 'upload' && !sourceFileName.trim()) {
      error = 'Source code file name is required in upload mode.';
      return;
    }

    if (!binaryFileName.trim()) {
      error = 'Binary file name is required.';
      return;
    }

    if (selectedArchitectures.length === 0) {
      error = 'Select at least one architecture.';
      return;
    }

    projectStore.addProject({
      name,
      framework,
      sourceType,
      githubUrl: sourceType === 'github' ? githubUrl : undefined,
      sourceFileName: sourceType === 'upload' ? sourceFileName : undefined,
      binaryFileName,
      architectures: selectedArchitectures
    });

    await goto('/');
  }
</script>

<section class="space-y-6">
  <div>
    <a href="/" class="text-sm text-muted-foreground hover:underline">Back to dashboard</a>
    <h1 class="mt-1 text-2xl font-semibold">Add new project</h1>
    <p class="text-sm text-muted-foreground">Link GitHub or upload source code, then attach binary and target architectures.</p>
  </div>

  <Card class="space-y-6 p-6">
    <div class="grid gap-4 md:grid-cols-2">
      <div class="space-y-2">
        <Label for="name">Project name</Label>
        <Input id="name" bind:value={name} placeholder="example-service" />
      </div>
      <div class="space-y-2">
        <Label for="framework">Framework</Label>
        <Input id="framework" bind:value={framework} placeholder="SvelteKit, Rust, Node" />
      </div>
    </div>

    <div class="space-y-3 rounded-lg border border-border p-4">
      <div class="text-sm font-medium">Source setup</div>
      <div class="flex gap-2">
        <Button variant={sourceType === 'github' ? 'default' : 'outline'} size="sm" on:click={() => (sourceType = 'github')}>
          GitHub link
        </Button>
        <Button variant={sourceType === 'upload' ? 'default' : 'outline'} size="sm" on:click={() => (sourceType = 'upload')}>
          Upload source
        </Button>
      </div>

      {#if sourceType === 'github'}
        <div class="space-y-2">
          <Label for="github">GitHub URL</Label>
          <Input id="github" bind:value={githubUrl} placeholder="https://github.com/org/repo" />
        </div>
      {:else}
        <div class="space-y-2">
          <Label for="sourcefile">Source code file name</Label>
          <Input id="sourcefile" bind:value={sourceFileName} placeholder="repo-source.zip" />
        </div>
      {/if}
    </div>

    <div class="space-y-2">
      <Label for="binary">Binary file name</Label>
      <Input id="binary" bind:value={binaryFileName} placeholder="app-linux-amd64 or app.wasm" />
    </div>

    <div class="space-y-3 rounded-lg border border-border p-4">
      <div class="text-sm font-medium">Architectures</div>
      <div class="grid gap-2 md:grid-cols-2">
        {#each architectureOptions as architecture}
          <label class="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm">
            <Checkbox
              checked={selectedArchitectures.includes(architecture)}
              onchange={(event: Event) =>
                toggleArchitecture(architecture, (event.currentTarget as HTMLInputElement).checked)}
            />
            {architecture}
          </label>
        {/each}
      </div>
    </div>

    {#if error}
      <p class="text-sm text-destructive">{error}</p>
    {/if}

    <div class="flex gap-2">
      <Button on:click={submit}>Create project</Button>
      <a href="/"><Button variant="outline">Cancel</Button></a>
    </div>
  </Card>
</section>

