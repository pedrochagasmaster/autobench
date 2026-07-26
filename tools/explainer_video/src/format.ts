export const formatThousands = (value: number): string =>
  Math.round(value)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, ",");

export const formatMultiplier = (value: number): string =>
  (Math.round(value * 100) / 100).toFixed(2);
