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
  let githubUrl = $state('');
  let sourceFileName = $state('');
  let sourceFileUrl = $state('');
  let sourceFile = $state<File | null>(null);
  let selectedArchitectures = $state<Architecture[]>(['x86_64']);
  let error = $state('');
  let isUploading = $state(false);

  function toggleArchitecture(architecture: Architecture, checked: boolean) {
    if (checked) {
      selectedArchitectures = Array.from(new Set([...selectedArchitectures, architecture]));
      return;
    }

    selectedArchitectures = selectedArchitectures.filter((item) => item !== architecture);
  }

  function onSourceFileChange(event: Event) {
    const target = event.currentTarget as HTMLInputElement;
    sourceFile = target.files?.[0] ?? null;
    sourceFileName = sourceFile?.name ?? '';
    sourceFileUrl = '';
  }

  async function uploadSource() {
    if (!sourceFile) {
      throw new Error('Select a source file before uploading.');
    }

    const formData = new FormData();
    formData.append('file', sourceFile);

    const response = await fetch('/api/uploads/source', {
      method: 'POST',
      body: formData
    });

    const result = (await response.json()) as { url?: string; name?: string; error?: string };

    if (!response.ok || !result.url) {
      throw new Error(result.error ?? 'Failed to upload source file.');
    }

    sourceFileUrl = result.url;
    sourceFileName = result.name ?? sourceFile.name;
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

    if (sourceType === 'upload') {
      if (!sourceFile) {
        error = 'Source code file is required in upload mode.';
        return;
      }

      if (!sourceFileUrl) {
        try {
          isUploading = true;
          await uploadSource();
        } catch (uploadError) {
          error = uploadError instanceof Error ? uploadError.message : 'Upload failed.';
          return;
        } finally {
          isUploading = false;
        }
      }
    }

    if (selectedArchitectures.length === 0) {
      error = 'Select at least one architecture.';
      return;
    }

    projectStore.addProject({
      name,
      sourceType,
      githubUrl: sourceType === 'github' ? githubUrl : undefined,
      sourceFileName: sourceType === 'upload' ? sourceFileName : undefined,
      sourceFileUrl: sourceType === 'upload' ? sourceFileUrl : undefined,
      architectures: selectedArchitectures
    });

    await goto('/');
  }
</script>

<section class="space-y-6">
  <div>
    <a href="/" class="text-sm text-muted-foreground hover:underline">Back to dashboard</a>
    <h1 class="mt-1 text-2xl font-semibold">Add new project</h1>
    <p class="text-sm text-muted-foreground">Link GitHub or upload source code and choose target architectures.</p>
  </div>

  <Card class="space-y-6 p-6">
    <div class="space-y-2">
      <Label for="name">Project name</Label>
      <Input id="name" bind:value={name} placeholder="example-service" />
    </div>

    <div class="space-y-3 rounded-lg border border-border p-4">
      <div class="text-sm font-medium">Source setup</div>
      <div class="flex gap-2">
        <Button variant={sourceType === 'github' ? 'default' : 'outline'} size="sm" onclick={() => (sourceType = 'github')}>
          GitHub link
        </Button>
        <Button variant={sourceType === 'upload' ? 'default' : 'outline'} size="sm" onclick={() => (sourceType = 'upload')}>
          Upload source
        </Button>
      </div>

      {#if sourceType === 'github'}
        <div class="space-y-2">
          <Label for="github">GitHub URL</Label>
          <Input id="github" bind:value={githubUrl} placeholder="https://github.com/org/repo" />
        </div>
      {:else}
        <div class="space-y-3">
          <div class="space-y-2">
            <Label for="sourcefile">Source code file</Label>
            <input
              id="sourcefile"
              name="sourcefile"
              type="file"
              class="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              onchange={onSourceFileChange}
            />
            <p class="text-xs text-muted-foreground">Only file uploads are accepted in this mode.</p>
          </div>

          {#if sourceFileUrl}
            <div class="rounded-md border border-border p-3">
              <div class="text-xs text-muted-foreground">Uploaded source URL</div>
              <a href={sourceFileUrl} target="_blank" rel="noreferrer" class="text-sm text-primary hover:underline">{sourceFileUrl}</a>
            </div>
          {/if}
        </div>
      {/if}
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
      <Button onclick={submit} disabled={isUploading}>{isUploading ? 'Uploading...' : 'Create project'}</Button>
      <a href="/"><Button variant="outline">Cancel</Button></a>
    </div>
  </Card>
</section>
