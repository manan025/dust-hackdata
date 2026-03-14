<script lang="ts">
  let { values = [] as number[] } = $props();

  const width = 220;
  const height = 74;

  const max = $derived(Math.max(...values, 1));
  const min = $derived(Math.min(...values, 0));
  const range = $derived(max - min || 1);

  const points = $derived(
    values
      .map((value, index) => {
        const x = (index / Math.max(values.length - 1, 1)) * width;
        const y = height - ((value - min) / range) * height;
        return `${x},${y}`;
      })
      .join(' ')
  );
</script>

<svg viewBox={`0 0 ${width} ${height}`} class="h-[74px] w-full">
  <polyline fill="none" stroke="currentColor" stroke-width="2" points={points} class="text-primary" />
</svg>
