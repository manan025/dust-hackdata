<script lang="ts">
  import { cn } from '$lib/utils';

  type Variant = 'default' | 'secondary' | 'ghost' | 'outline' | 'destructive';
  type Size = 'default' | 'sm' | 'lg';
  type ButtonType = 'button' | 'submit' | 'reset';

  let {
    class: className = '',
    variant = 'default' as Variant,
    size = 'default' as Size,
    type = 'button' as ButtonType,
    ...rest
  } = $props();

  const variants: Record<Variant, string> = {
    default: 'bg-primary text-primary-foreground hover:opacity-95',
    secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
    ghost: 'hover:bg-accent hover:text-accent-foreground',
    outline: 'border border-input bg-background hover:bg-accent hover:text-accent-foreground',
    destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90'
  };

  const sizes: Record<Size, string> = {
    default: 'h-10 px-4 py-2',
    sm: 'h-9 rounded-md px-3',
    lg: 'h-11 rounded-md px-8'
  };
</script>

<button
  {type}
  class={cn(
    'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50',
    variants[variant],
    sizes[size],
    className
  )}
  {...rest}
>
  <slot />
</button>
