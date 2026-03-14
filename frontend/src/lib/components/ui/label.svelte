<script lang="ts">
  import { cn } from '$lib/utils';
  let { class: className = '', for: htmlFor = '' } = $props();
</script>

<label for={htmlFor} class={cn('text-sm font-medium leading-none', className)}>
  <slot />
</label>

