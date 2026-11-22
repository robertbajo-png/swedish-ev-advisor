// Use only in standalone PGlite tests. Real permits must still expire.
export function useNewsBudgetTestClock() {
  const OriginalDate = globalThis.Date;
  let epoch = OriginalDate.parse('2026-11-20T12:00:00Z');
  globalThis.Date = class extends OriginalDate {
    constructor(...args) {
      super(...(args.length ? args : [epoch]));
    }

    static now() {
      return epoch;
    }
  };
  return {
    advanceToPricingExpiry() {
      epoch = OriginalDate.parse('2026-11-21T00:00:00Z');
    },
    restore() {
      globalThis.Date = OriginalDate;
    },
  };
}
