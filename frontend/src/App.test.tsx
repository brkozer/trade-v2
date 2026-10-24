import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import React from "react";
import { App, badgeTone, display, formatted, runtimeContext, type Snapshot } from "./App";

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
  it("renders a sealed discovery search with frozen configurations and no promotion", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({ ...fixture,
        searches: [{ search_id: "TRADEV2_ALPHA_SEARCH_004" }, { search_id: "TRADEV2_DISCOVERY_009" }],
        campaign: { search_id: "TRADEV2_DISCOVERY_009", evidence_role: "DISCOVERY_ONLY_NOT_FRESH_VALIDATION",
          status: "REJECTED_DISCOVERY_ONLY", family: "cross_sectional_idiosyncratic_max_effect",
          trial_count: 2, evaluation_count: 24, frozen_candidate: null, complete: true,
          promotion: "NONE; discovery-only cannot satisfy fresh validation",
          dataset: { id: "BYBIT_PUBLIC_REUSED_39_OHLCV_210D", role: "REUSED_HISTORICAL_DISCOVERY" },
          mechanism: "Lottery demand" },
        candidates: [{ family: "cross_sectional_idiosyncratic_max_effect", label: "lookback=1344",
          status: "DISCOVERY_GATES_FAILED", forward_trades: 464, forward_mean_gross_r: 0.0008,
          forward_mean_net_r: -0.0193, positive_folds: 1,
          costs: { base_taker: -225.12, wide_costs: -381.58, severe_plausible: -120.5 }, holm_pvalue: 1 }],
        experiments: [{ hypothesis: "SEARCH009_IDIOSYNCRATIC_MAX_14D", checkpoint: 1,
          treatment: "base_taker", n: 116, net_r: -0.01, ci: null, status: "FORWARD" }],
      }),
    } as Response);
    render(<App />);
    await screen.findByText("No positions recorded for this run.");
    fireEvent.click(screen.getByRole("button", { name: "Alpha Lab" }));
    expect(screen.getByText("DISCOVERY_ONLY")).toBeTruthy();
    const row = screen.getByRole("row", { name: /lookback=1344/ });
    expect(row.textContent).toContain("464");
    expect(row.textContent).toContain("-225.12");
    expect(row.textContent).toContain("DISCOVERY_GATES_FAILED");
    expect(screen.getByText("NONE")).toBeTruthy();
    expect(screen.queryByText("No research campaign artifact available.")).toBeNull();
    fireEvent.change(screen.getByLabelText("Filter configurations"), { target: { value: "2688" } });
    expect(screen.getByText("No configurations match this filter.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Experiments" }));
    expect(screen.getByRole("heading", { name: "Chronological trial ledger" })).toBeTruthy();
    expect(screen.getByRole("table", { name: "Chronological trial ledger" })).toBeTruthy();
    expect(screen.getByText("FORWARD")).toBeTruthy();
  });
  it("words the Trader notice from runtime status and freshness, never assuming current", async () => {
    const cases: [string, string, string][] = [
      ["RUNNING_UNVERIFIED", "FRESH", "current runtime · fresh record"],
      ["RUNNING_UNVERIFIED", "STALE", "stale record, not current account"],
      ["FAILED", "STALE", "last run, not current account"],
      ["STOPPED", "STALE", "last run, not current account"],
      ["NOT_RUNNING", "UNKNOWN", "no run recorded"],
      ["UNKNOWN", "UNKNOWN", "evidence unverified"],
    ];
    for (const [status, freshness, wording] of cases) {
      expect(runtimeContext(status, freshness)).toBe(wording);
      vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true,
        json: async () => ({ ...fixture, runtime: { ...fixture.runtime, status, freshness } }),
      } as Response);
      render(<App />);
      await screen.findByText(new RegExp(wording.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
      expect(screen.queryByText(/CURRENT runtime/)).toBeNull();
      cleanup();
      vi.restoreAllMocks();
    }
  });
  it("refuses to show zero counts when journal integrity failed", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true,
      json: async () => ({ ...fixture, evidence: { integrity: "FAILED",
        errors: ["JOURNAL_INTEGRITY_FAILED"], journals: 1 } }),
    } as Response);
    render(<App />);
    await screen.findAllByText("Evidence refused: journal integrity is not verified.");
    expect(screen.queryByText("No positions recorded for this run.")).toBeNull();
    const tabs = screen.getByRole("group", { name: "Execution evidence" });
    expect(tabs.textContent).not.toMatch(/\d/);
    expect(tabs.textContent).toContain("Unknown");
    fireEvent.click(screen.getByRole("button", { name: "Performance" }));
    expect(screen.getAllByText("Evidence refused: journal integrity is not verified.").length).toBe(2);
  });
  it("removes previously shown account values when a later poll fails", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const fetcher = vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true,
        json: async () => ({ ...fixture, account: { equity: "10123.45" } }),
      } as Response);
      render(<App />);
      await screen.findByText("10123.45");
      fetcher.mockRejectedValue(new Error("offline"));
      await vi.advanceTimersByTimeAsync(15_100);
      await waitFor(() => expect(screen.getByRole("alert").textContent)
        .toContain("Cached values have been removed"));
      expect(screen.queryByText("10123.45")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });
  it("shows verbatim holdout state and validation-period detail for the initial campaign", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true,
      json: async () => ({ ...fixture, searches: [{ search_id: "TRADEV2_INITIAL_ALPHA_001" }],
        campaign: { search_id: "TRADEV2_INITIAL_ALPHA_001", final_holdout_state: "NOT_ACQUIRED_NOT_CONSUMED",
          promoted_candidates: [], families: [{ family: "rsi_reversion", mechanism: "Oversold",
            status: "REJECTED", positive_folds: null, oos: { mean_net_r: -0.0198, trades: 1516 },
            folds: [{ validation: { total_net_pnl: -1 } }, { validation: {} }],
            reasons: ["negative aggregate validation economics"] }] } }),
    } as Response);
    render(<App />);
    await screen.findByText("No positions recorded for this run.");
    fireEvent.click(screen.getByRole("button", { name: "Alpha Lab" }));
    expect(screen.getByText("NOT_ACQUIRED_NOT_CONSUMED")).toBeTruthy();
    expect(screen.queryByText("NOT ACQUIRED")).toBeNull();
    expect(screen.getByRole("row", { name: /rsi_reversion/ }).textContent)
      .toContain("Unknown positive folds");
    fireEvent.change(screen.getByLabelText("Candidate detail"), { target: { value: "rsi_reversion" } });
    const detail = screen.getByRole("region", { name: "Selected candidate detail" });
    expect(detail.textContent).toContain("Validation net R · HISTORICAL");
    expect(detail.textContent).toContain("-0.0198");
    expect(detail.textContent).toContain("1516");
  });
  it("formats only real numbers and keeps exact decimal strings and adverse badges honest", () => {
    expect(formatted(-146.085, 2)).toBe("-146.09");
    expect(formatted("-146.085", 2)).toBe("-146.085");
    expect(formatted(true, 2)).toBe("true");
    expect(formatted([], 2)).toBe("[]");
    expect(formatted("NOT_EVALUATED", 2)).toBe("NOT_EVALUATED");
    expect(formatted(null, 2)).toBe("Unknown");
    expect(formatted(Number.NaN, 2)).toBe("Unknown");
    for (const adverse of ["API UNAVAILABLE", "UNSUPPORTED_WITH_CURRENT_DATA", "NOT_RUNNING",
      "NO PROMOTION", "STARTING", "WAITING_FOR_DATA", "NOT_COMPLETED", "DISCOVERY_GATES_FAILED",
      "CHAIN_INTEGRITY_FAILED", "STALE"])
      expect(badgeTone(adverse)).toBe("amber");
    for (const healthy of ["VERIFIED", "FRESH", "AVAILABLE", "RECENT"]) expect(badgeTone(healthy)).toBe("");
  });
  it("does not move focus to the heading on initial load", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true, json: async () => fixture } as Response);
    render(<React.StrictMode><App /></React.StrictMode>);
    await screen.findByText("No positions recorded for this run.");
    expect(document.activeElement).not.toBe(screen.getByRole("heading", { level: 1 }));
    fireEvent.click(screen.getByRole("button", { name: "System" }));
    expect(document.activeElement).toBe(screen.getByRole("heading", { level: 1 }));
  });
  it("shows the prospective evidence gate without inventing coverage", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({ ...fixture,
        prospective: { status: "NO_PROSPECTIVE_DATA", candles: null, open_interest: null,
          alignment: null, gate: { required_forward_days: 28, covered_days: null, remaining_days: null },
          collector: { state: "UNKNOWN", last_collected_at: null } } }),
    } as Response);
    render(<App />);
    await screen.findByText("No positions recorded for this run.");
    fireEvent.click(screen.getByRole("button", { name: "Alpha Lab" }));
    const gate = screen.getByRole("region", { name: "Next evidence gate" });
    expect(gate.textContent).toContain("NO_PROSPECTIVE_DATA");
    expect(gate.textContent).toContain("Coverage and collector state remain Unknown");
    expect(gate.textContent).not.toContain("Covered forward days0");
    cleanup();
    vi.restoreAllMocks();
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({ ...fixture,
        prospective: { status: "WAITING_FOR_DATA", error: null,
          candles: { chunks: 34, symbols: 20, points_per_symbol: 105, first_utc: "2026-09-23T10:00:00+00:00",
            last_close_utc: "2026-09-24T12:15:00+00:00", contiguous: true, hash_verified: true },
          open_interest: { chunks: 13, points_per_symbol: 66 },
          alignment: { matched_feature_timestamps: 66, executable_feature_timestamps: 64 },
          gate: { required_forward_days: 28, covered_days: 1.09, remaining_days: 26.91,
            forward_days_satisfied: false, note: "Forward days alone authorize nothing." },
          collector: { state: "STALE", last_collected_at: "2026-09-24T12:27:09+00:00", age_ms: 1 },
          source_universe_verified: true } }),
    } as Response);
    render(<App />);
    await screen.findByText("No positions recorded for this run.");
    fireEvent.click(screen.getByRole("button", { name: "Alpha Lab" }));
    const waiting = screen.getByRole("region", { name: "Next evidence gate" });
    expect(waiting.textContent).toContain("WAITING_FOR_DATA");
    expect(waiting.textContent).toContain("26.91");
    expect(waiting.textContent).toContain("STALE");
    expect(waiting.textContent).toContain("Forward days alone authorize nothing.");
    fireEvent.click(screen.getByRole("button", { name: "System" }));
    expect(screen.getByText("Prospective collector").nextSibling?.textContent).toBe("STALE");
  });
  it("keeps the research selector usable after a rejected search selection", async () => {
    const good = { ...fixture,
      searches: [{ search_id: "TRADEV2_FINAL_ALPHA_003" }, { search_id: "TRADEV2_ALPHA_SEARCH_004" }],
      campaign: { search_id: "TRADEV2_ALPHA_SEARCH_004", families: [], promoted_candidates: [] } };
    const fetcher = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("search_id=TRADEV2_FINAL_ALPHA_003"))
        return { ok: false, status: 404, json: async () => ({}) } as Response;
      return { ok: true, json: async () => good } as Response;
    });
    render(<App />);
    await screen.findByText("No positions recorded for this run.");
    fireEvent.click(screen.getByRole("button", { name: "Alpha Lab" }));
    fireEvent.change(screen.getByLabelText("Research search"), {
      target: { value: "TRADEV2_FINAL_ALPHA_003" },
    });
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("404"));
    expect(screen.getByText("Evidence unavailable")).toBeTruthy();
    expect(screen.getByLabelText("Research search")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Reset research search" }));
    await screen.findByText("Search 004 candidates");
    expect(screen.queryByRole("alert")).toBeNull();
    const last = String(fetcher.mock.calls[fetcher.mock.calls.length - 1][0]);
    expect(last).not.toContain("search_id=");
  });
});
