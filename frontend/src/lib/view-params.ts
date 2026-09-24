import { useSearchParams } from "react-router-dom";

/** View state is shareable; unrelated route parameters are preserved. */
export function useViewParams() {
  const [params, setParams] = useSearchParams();
  function update(values: Record<string, string | undefined>): void {
    setParams((current) => {
      const next = new URLSearchParams(current);
      for (const [key, value] of Object.entries(values)) {
        if (value) next.set(key, value);
        else next.delete(key);
      }
      return next;
    });
  }
  function clear(keys: string[]): void {
    update(Object.fromEntries(keys.map((key) => [key, undefined])));
  }
  return { params, update, clear };
}