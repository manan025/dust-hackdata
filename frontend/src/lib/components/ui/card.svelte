<script lang="ts">
  import { cn } from '$lib/utils';
  let { class: className = '' } = $props();
</script>

<div class={cn('rounded-lg border border-border bg-background shadow-card', className)}>
  <slot />
</div>

