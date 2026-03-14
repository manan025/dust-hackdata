<script lang="ts">
  import { cn } from '$lib/utils';
  let {
    class: className = '',
    checked = false,
    value = '',
    name = '',
    id = '',
    disabled = false,
    onchange
  } = $props();
</script>

<input
  {id}
  {name}
  {value}
  type="checkbox"
  {checked}
  {disabled}
  class={cn(
    'h-4 w-4 rounded border border-input text-primary focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50',
    className
  )}
  {onchange}
/>
