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
    candidate_id: null,
    candidate_stage: null,
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
    expect(screen.getByRole("row", { name: /rsi_reversion/ })).toBeTruthy();
    expect(screen.queryByRole("row", { name: /volume_shock/ })).toBeNull();
  });
  it("shows final forward evidence, paired stress and unknown attribution honestly", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        ...fixture,
        searches: [{ search_id: "INITIAL" }, { search_id: "FINAL" }],
        campaign: {
          search_id: "FINAL",
          final_holdout_state: "NO_UNTOUCHED_HISTORICAL_HOLDOUT",
          search_budget: { configurations: 28, selection_evaluations: 112, total_replays: 336 },
          promoted_candidates: [],
          families: [{ family: "ridge_ohlcv", mechanism: "Linear net-cost hurdle",
            status: "REJECTED", discovery: { eligible_trials: 3 },
            forward: { mean_net_r: -0.0487, trades: 454, total_net_pnl: -566.59 },
            folds: [{ forward: { total_net_pnl: -1 } }],
            stress_total_net_pnl: { wide_costs: -700, severe_plausible: -900 },
            parameter_stability: { neighbor_positive_folds: 0 }, adjusted_pvalue: 1 }],
        },
        experiments: [{ hypothesis: "ridge_ohlcv", checkpoint: 1,
          treatment: "wide_costs", n: 12, mean_paired_delta: -2,
          ci: null, status: "DESCRIPTIVE_ONLY" }],
        symbols: [{ symbol: "BTCUSDT", signals: 0, opportunities: 0, entries: 0,
          closed_trades: 0, net_usdt: null, net_r: null, spread_bps: null,
          source_age_ms: null, rejections: 0 }],
        performance: { net_usdt: null, net_r: null },
      }),
    } as Response);
    render(<App />);
    await screen.findByText("No positions recorded for this run.");
    fireEvent.click(screen.getByRole("button", { name: "Alpha Lab" }));
    expect(screen.getByRole("row", { name: /ridge_ohlcv/ })).toBeTruthy();
    expect(screen.getByText(/454 trades/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Experiments" }));
    expect(screen.getByText("Paired execution-cost stress")).toBeTruthy();
    expect(screen.getByText("DESCRIPTIVE_ONLY")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Symbols" }));
    expect(screen.getByRole("rowheader", { name: "BTCUSDT" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Performance" }));
    expect(screen.getByText(/Unrecorded strategy/)).toBeTruthy();
  });
  it("shows Search 004 costs and keeps sealed earlier searches selectable", async () => {
    const fetcher = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({ ...fixture,
        searches: [{ search_id: "TRADEV2_FINAL_ALPHA_003" },
          { search_id: "TRADEV2_ALPHA_SEARCH_004" }],
        campaign: { search_id: "TRADEV2_ALPHA_SEARCH_004", trial_count: 12,
          evaluation_count: 108, promoted_candidates: [],
          dataset: { dataset_id: "BYBIT_PUBLIC_POST003_004" },
          families: [{ family: "dispersion_exhaustion", status: "REJECTED",
            forward_mean_net_r: 0.069, forward_trades: 112,
            positive_folds: 2, costs: { base_taker: 192.89,
              wide_costs: 34.41, severe_plausible: -146.08 },
            neighbor_positive_folds: 0, reason: "Cost failure" }] },
      }),
    } as Response);
    render(<App />);
    await screen.findByText("No positions recorded for this run.");
    fireEvent.click(screen.getByRole("button", { name: "Alpha Lab" }));
    expect(screen.getByRole("row", { name: /dispersion_exhaustion/ }).textContent)
      .toContain("-146.08");
    fireEvent.change(screen.getByLabelText("Research search"), {
      target: { value: "TRADEV2_FINAL_ALPHA_003" },
    });
    await waitFor(() => expect(fetcher).toHaveBeenCalledWith(
      expect.stringContaining("search_id=TRADEV2_FINAL_ALPHA_003"),
      expect.anything(),
    ));
  });
});
