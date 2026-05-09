// Vitest setup — kører før hver test-fil.
//
// Importer @testing-library/jest-dom så vi får matchers som
// .toBeInTheDocument(), .toHaveClass() osv.
import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

// Ryd op efter hver test — vigtigt for tests der renderer komponenter
// til DOM. Uden cleanup leaker DOM-noder mellem tests, og selectors
// matcher tilfældigt et element fra en tidligere test.
afterEach(() => {
  cleanup();
  // Ryd alle vi.fn()-mocks så hver test starter clean.
  vi.clearAllMocks();
});
