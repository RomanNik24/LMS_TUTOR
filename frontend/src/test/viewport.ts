/** Подмена `window.matchMedia` под заданную ширину окна: Tailwind-классы в jsdom не работают, а лэйауты выбирают вид по `useBreakpoint`. */
const MIN_WIDTH = /\(min-width:\s*(\d+)px\)/;

export function setViewport(width: number): void {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string): MediaQueryList => {
      const match = MIN_WIDTH.exec(query);
      return {
        matches: match?.[1] !== undefined && width >= Number(match[1]),
        media: query,
        onchange: null,
        addListener: () => undefined,
        removeListener: () => undefined,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        dispatchEvent: () => false,
      } satisfies MediaQueryList;
    },
  });
}
