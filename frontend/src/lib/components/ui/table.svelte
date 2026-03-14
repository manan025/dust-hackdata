<script lang="ts">
  import { cn } from '$lib/utils';
  let { class: className = '' } = $props();
</script>

<div class="relative w-full overflow-auto">
  <table class={cn('w-full caption-bottom text-sm', className)}>
    <slot />
  </table>
</div>

