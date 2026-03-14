<script lang="ts">
  import '../app.css';
</script>

<div class="min-h-screen bg-background">
  <header class="border-b border-border bg-background/90">
    <div class="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
      <a href="/" class="text-lg font-semibold">Profiler Console</a>
      <a href="/projects/new" class="rounded-md border border-input px-3 py-1.5 text-sm hover:bg-accent">Add project</a>
    </div>
  </header>

  <main class="mx-auto max-w-6xl px-6 py-8">
    <slot />
  </main>
</div>

