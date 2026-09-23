import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { App, display, type Snapshot } from "./App";

const fixture: Snapshot = {
  generated_ms: 1,
  runtime: {
    mode: "paper",
    run_id: null,
    status: "UNKNOWN",
    freshness: "UNKNOWN",
    source_freshness: "UNKNOWN",
    engine: "ENGINE_UNKNOWN",
    safety: "ENTRY_BLOCKED",
    age_ms: null,
    source_ms: null,
    live: "LIVE_DISABLED",
  },
  account: null,
  events: { position: [], order: [], trade: [], market: [], rejection: [] },
  manifests: [],
  campaign: null,
  evidence: { integrity: "UNKNOWN", errors: [], journals: 0 },
  system: { api: "AVAILABLE", authority: "READ_ONLY", live: "LIVE_DISABLED" },
};
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
describe("truthful workstation", () => {
  it("preserves unknown and zero distinctly", () => {
    expect(display(null)).toBe("Unknown");
    expect(display("0")).toBe("0");
    expect(display(undefined)).toBe("Unknown");
  });
  it("navigates all pages and filters without invented evidence", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => fixture,
    } as Response);
    render(<App />);
    await screen.findByText("No positions recorded for this run.");
    for (const page of [
      "Alpha Lab",
      "Symbols",
      "Experiments",
      "Performance",
      "System",
    ]) {
      fireEvent.click(screen.getByRole("button", { name: page }));
      expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(page);
    }
    fireEvent.click(screen.getByRole("button", { name: "Alpha Lab" }));
    fireEvent.change(screen.getByLabelText("Filter families"), {
      target: { value: "missing" },
    });
    expect(
      screen.getByText("No research campaign artifact available."),
    ).toBeTruthy();
  });
  it("drops stale data on failure", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("offline"));
    render(<App />);
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain(
        "Cached values have been removed",
      ),
    );
    expect(screen.getByText("Evidence unavailable")).toBeTruthy();
  });
  it("filters families by visible identity without hidden trial data", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        ...fixture,
        campaign: {
          families: [
            { family: "rsi_reversion", mechanism: "Oversold reversal", status: "REJECTED" },
            { family: "volume_shock", mechanism: "Volume impulse", status: "REJECTED", hidden_trials: "rsi" },
          ],
        },
      }),
    } as Response);
    render(<App />);
    await screen.findByText("No positions recorded for this run.");
    fireEvent.click(screen.getByRole("button", { name: "Alpha Lab" }));
    fireEvent.change(screen.getByLabelText("Filter families"), {
      target: { value: "rsi" },
    });
    expect(screen.getByText("rsi_reversion")).toBeTruthy();
    expect(screen.queryByText("volume_shock")).toBeNull();
  });
});
