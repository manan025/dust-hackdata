<script lang="ts">
  import { cn } from '$lib/utils';
  let { class: className = '', ...rest } = $props();
</script>

<textarea
  class={cn(
    'min-h-[90px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50',
    className
  )}
  {...rest}
></textarea>
