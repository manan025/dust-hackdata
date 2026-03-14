<script lang="ts">
  import { cn } from '$lib/utils';
  let { class: className = '' } = $props();
</script>

<span
  class={cn(
    'inline-flex items-center rounded-full border border-transparent bg-secondary px-2.5 py-0.5 text-xs font-medium text-secondary-foreground',
    className
  )}
>
  <slot />
</span>

