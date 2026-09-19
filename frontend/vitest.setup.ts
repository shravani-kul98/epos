import "@testing-library/jest-dom/vitest";

// jsdom implements no layout, so scrolling APIs are absent. Components may call them freely.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function scrollIntoView(): void {
    // Intentionally empty: there is nothing to scroll in a headless DOM.
  };
}

const noLayout = (): void => {
  // Intentionally empty: jsdom has no layout to observe.
};

if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class ResizeObserver {
    observe = noLayout;
    unobserve = noLayout;
    disconnect = noLayout;
  };
}
