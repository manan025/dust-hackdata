<script lang="ts">
  import { cn } from '$lib/utils';
  let { class: className = '', value = 0 } = $props();
  const clamped = $derived(Math.max(0, Math.min(100, value)));
</script>

<div class={cn('relative h-2 w-full overflow-hidden rounded-full bg-secondary', className)}>
  <div class="h-full bg-primary transition-all" style={`width:${clamped}%`}></div>
</div>
