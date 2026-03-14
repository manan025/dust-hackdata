<script lang="ts">
  import { cn } from '$lib/utils';
  let { class: className = '' } = $props();
</script>

<details class={cn('relative inline-block', className)}>
  <summary class="list-none cursor-pointer rounded-md border border-input bg-background px-2 py-1 text-xs hover:bg-accent">
    <slot name="trigger">...</slot>
  </summary>
  <div class="absolute right-0 z-20 mt-2 min-w-36 rounded-md border border-border bg-background p-1 shadow-md">
    <slot />
  </div>
</details>

