import { useEffect, useRef, useState } from "react";

type RecordData = Record<string, unknown>;
export type Event = {
  event_id: string;
  run_id: string;
  kind: string;
  recorded_ms: number;
  source_ms: number | null;
  source: string;
  payload: RecordData;
};
export type Snapshot = {
  generated_ms: number;
  runtime: {
    mode: string | null;
    run_id: string | null;
    status: string;
    candidate_id: string | null;
    candidate_stage: string | null;
    freshness: string;
    source_freshness: string;
    pending_halt?: boolean | null;
    halt_reason?: string | null;
    engine: string;
    safety: string;
    age_ms: number | null;
    source_ms: number | null;
    live: string;
  };
  account: RecordData | null;
  events: Record<string, Event[]>;
  manifests: RecordData[];
  campaign: RecordData | null;
  searches?: RecordData[];
  candidates?: RecordData[];
  experiments?: RecordData[];
  symbols?: RecordData[];
  performance?: RecordData;
  prospective?: RecordData;
  evidence: { integrity: string; errors: string[]; journals: number;
    research_integrity?: string; research_errors?: string[] };
  system: RecordData;
};
const pages = [
  "Trader",
  "Alpha Lab",
  "Symbols",
  "Experiments",
  "Performance",
  "System",
] as const;
const icons = ["◫", "⌁", "≡", "⊞", "↗", "⚙"];
function plural(kind: string): string {
  return kind === "opportunity"
    ? "Opportunities"
    : `${kind.charAt(0).toUpperCase()}${kind.slice(1)}s`;
}
export function display(value: unknown): string {
  return value === null || value === undefined
    ? "Unknown"
    : typeof value === "object"
      ? JSON.stringify(value)
      : String(value);
}
const DECIMAL_STRING = /^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$/;
/** Float statistics are rounded for display; exact decimal strings are shown verbatim. */
export function formatted(value: unknown, decimals: number): string {
  if (value === null || value === undefined || value === "") return "Unknown";
  if (typeof value === "string")
    return DECIMAL_STRING.test(value.trim()) ? value.trim() : display(value);
  if (typeof value !== "number") return display(value);
  return Number.isFinite(value)
    ? value.toLocaleString("en-US", {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      })
    : "Unknown";
}
const WARNING_TONE = new RegExp([
  "UNKNOWN", "STALE", "INSUFFICIENT", "REJECT", "FAIL", "DISABLED", "BLOCKED", "STOPPED",
  "UNVERIFIED", "UNAVAILABLE", "UNSUPPORTED", "NOT_RUNNING", "NOT_COMPLETED", "UNACCEPTED",
  "STARTING", "NO PROMOTION", "NO_PROSPECTIVE", "WAITING", "DISCOVERY_ONLY", "INTEGRITY",
  "LATCHED", "INCOMPLETE",
].join("|"), "i");
/** Healthy styling is never the fallback for an unrecognised or adverse state. */
export function badgeTone(text: string): "amber" | "" {
  return WARNING_TONE.test(text) ? "amber" : "";
}
function Badge({ value }: { value: unknown }) {
  const text = display(value);
  return <span className={`badge ${badgeTone(text)}`.trim()}>{text}</span>;
}
/** Trader wording follows the runtime evidence instead of assuming a current account. */
export function runtimeContext(status: string | undefined, freshness: string | undefined): string {
  if (status === "STOPPED" || status === "FAILED") return "last run, not current account";
  if (status === "NOT_RUNNING") return "no run recorded";
  if (status === "UNKNOWN" || status === undefined) return "evidence unverified";
  if (freshness === "FRESH") return "current runtime · fresh record";
  return "stale record, not current account";
}
function forwardOf(family: RecordData): RecordData | undefined {
  return (family.forward ?? family.oos) as RecordData | undefined;
}
/** Count positive folds only when every fold's net PnL is known. */
export function positiveFolds(family: RecordData): number | null {
  if (typeof family.positive_folds === "number") return family.positive_folds;
  if (!Array.isArray(family.folds)) return null;
  const values = family.folds.map((fold: RecordData) =>
    ((fold.forward ?? fold.validation) as RecordData | undefined)?.total_net_pnl);
  if (values.some((value) => typeof value !== "number" || !Number.isFinite(value))) return null;
  return values.filter((value) => (value as number) > 0).length;
}
function Metrics({ values }: { values: [string, unknown][] }) {
  return (
    <div className="metrics">
      {values.map(([label, value]) => (
        <div className="metric" key={label}>
          <span>{label}</span>
          <strong className={value == null ? "unknown" : String(value).length > 20 ? "long-value" : ""}>
            {display(value)}
          </strong>
        </div>
      ))}
    </div>
  );
}
function Details({ value }: { value: unknown }) {
  return (
    <details>
      <summary>Inspect evidence</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}
function Ledger({ title, events, refused = false }: { title: string; events: Event[]; refused?: boolean }) {
  return (
    <section className="panel">
      <div className="panel-title">
        <h2>{title}</h2>
        <span>{refused ? "Unknown" : events.length} records · latest window</span>
      </div>
      {refused ? (
        <div className="empty" role="status">
          <span>!</span>
          <p>Evidence refused: journal integrity is not verified.</p>
          <small>Records may exist but are withheld until the journal verifies; nothing is shown as zero.</small>
        </div>
      ) : events.length ? (
        <div className="table-scroll">
          <table>
            <caption className="sr-only">{title}</caption>
            <thead>
              <tr>
                <th scope="col">Recorded UTC</th>
                <th scope="col">Symbol / identity</th>
                <th scope="col">Status / reason</th>
                <th scope="col">Source</th>
                <th scope="col">Evidence</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr key={event.event_id}>
                  <td>{new Date(event.recorded_ms).toISOString()}</td>
                  <td>
                    {display(
                      event.payload.symbol ??
                        event.payload.candidate_id ??
                        event.run_id,
                    )}
                  </td>
                  <td>
                    <Badge
                      value={
                        event.payload.status ??
                        event.payload.reason ??
                        event.kind
                      }
                    />
                  </td>
                  <td>{event.source}</td>
                  <td>
                    <Details value={event} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="empty">
          <span>∅</span>
          <p>No {title.toLowerCase()} recorded for this run.</p>
          <small>
            Evidence appears after a paper or shadow session produces records.
          </small>
        </div>
      )}
    </section>
  );
}
const DISCOVERY_ROLE = "DISCOVERY_ONLY_NOT_FRESH_VALIDATION";
export function isDiscovery(campaign: RecordData | null | undefined): boolean {
  return campaign?.evidence_role === DISCOVERY_ROLE;
}
function Campaign({ campaign, searches, candidates }: {
  campaign: RecordData | null; searches: RecordData[]; candidates: RecordData[] }) {
  if (campaign && isDiscovery(campaign))
    return <DiscoveryCampaign campaign={campaign} searches={searches} candidates={candidates} />;
  if (campaign?.search_id === "TRADEV2_ALPHA_SEARCH_004")
    return <Search004Campaign campaign={campaign} searches={searches} />;
  return <HistoricalCampaign campaign={campaign} searches={searches} />;
}
function DiscoveryCampaign({ campaign, searches, candidates }: {
  campaign: RecordData; searches: RecordData[]; candidates: RecordData[] }) {
  const [filter, setFilter] = useState("");
  const dataset = campaign.dataset as RecordData | undefined;
  const visible = candidates.filter((row) => `${row.label} ${row.status} ${row.family}`
    .toLowerCase().includes(filter.toLowerCase()));
  const frozen = "frozen_candidate" in campaign
    ? (campaign.frozen_candidate === null ? "NONE" : display(campaign.frozen_candidate))
    : null;
  return <>
    <div className="notice"><Badge value="DISCOVERY_ONLY" />
      <span>Reused, already-consumed history. This search cannot satisfy fresh validation;
        a passing result would only be a frozen candidate awaiting genuinely new data.</span></div>
    <Metrics values={[["Completed searches", searches.length], ["Search", campaign.search_id],
      ["Family", campaign.family], ["Status", campaign.status],
      ["Dataset", dataset?.id ?? dataset?.dataset_id],
      ["Dataset role", dataset?.role ?? dataset?.evidence_role],
      ["Configurations", campaign.trial_count], ["Evaluations", campaign.evaluation_count],
      ["Frozen candidate", frozen], ["Promotion", campaign.promotion]]} />
    <section className="panel"><div className="panel-title"><h2>Frozen configurations</h2>
      <div className="filters"><label>Filter configurations <input value={filter}
        onChange={(event) => setFilter(event.target.value)} placeholder="Lookback or gate" /></label></div></div>
      {visible.length ? <div className="table-scroll"><table>
        <caption className="sr-only">Discovery configurations and forward evidence</caption>
        <thead><tr>{["Configuration", "Trades", "Gross R", "Net R", "Positive folds", "Base · USDT",
          "Wide · USDT", "Severe · USDT", "Holm p", "Gate"].map((name) =>
          <th scope="col" key={name}>{name}</th>)}</tr></thead>
        <tbody>{visible.map((row) => { const costs = row.costs as RecordData | undefined;
          return <tr key={String(row.label)}><th scope="row">{display(row.label)}</th>
            <td>{display(row.forward_trades)}</td><td>{formatted(row.forward_mean_gross_r, 4)}</td>
            <td>{formatted(row.forward_mean_net_r, 4)}</td><td>{display(row.positive_folds)}</td>
            <td>{formatted(costs?.base_taker, 2)}</td><td>{formatted(costs?.wide_costs, 2)}</td>
            <td>{formatted(costs?.severe_plausible, 2)}</td><td>{display(row.holm_pvalue)}</td>
            <td><Badge value={row.status} /></td></tr>; })}</tbody></table></div>
        : <p className="empty">{candidates.length ? "No configurations match this filter."
          : "No configuration rows in this sealed result."}</p>}
      <p>{display(campaign.mechanism)}</p>
    </section>
    <section className="panel"><h2>Evidence boundary</h2>
      <p>Forward folds reuse consumed history; cost arms are declared sensitivities, not calibrated
        fills. Smaller severe-arm losses reflect half size and missed fills, not robustness. No live,
        testnet, paper or prospective-shadow authority follows from this result.</p>
      <Details value={{ dataset: campaign.dataset, preregistration_sha256: campaign.preregistration_sha256,
        status: campaign.status, promotion: campaign.promotion, configurations: candidates }} /></section>
  </>;
}
export function ProspectiveGate({ prospective }: { prospective: RecordData | undefined }) {
  const candles = prospective?.candles as RecordData | null | undefined;
  const oi = prospective?.open_interest as RecordData | null | undefined;
  const alignment = prospective?.alignment as RecordData | null | undefined;
  const gate = prospective?.gate as RecordData | undefined;
  const collector = prospective?.collector as RecordData | undefined;
  const chains = (Array.isArray(prospective?.oi_chains) ? prospective.oi_chains : []) as RecordData[];
  const status = prospective?.status;
  return <section className="panel" aria-label="Next evidence gate">
    <div className="panel-title"><h2>Next evidence gate · prospective public data</h2>
      <Badge value={status} /></div>
    {status === "CHAIN_INTEGRITY_FAILED" ? <div role="alert" className="notice error">
      Prospective chain integrity failed: {display(prospective?.error)}. Counts are withheld.</div> : null}
    {status === "NO_PROSPECTIVE_DATA" ? <p>No prospective candle or open-interest chunks are present in
      this installation&apos;s data directory. Coverage and collector state remain Unknown.</p> : null}
    <Metrics values={[["Candle chunks", candles?.chunks], ["Bars per symbol", candles?.points_per_symbol],
      ["Contemporaneous bars", candles?.contemporaneous_points_per_symbol],
      ["Backfilled bars", candles?.backfilled_points_per_symbol],
      ["Symbols", candles?.symbols], ["First bar UTC", candles?.first_utc],
      ["Last close UTC", candles?.last_close_utc], ["Current OI chain", oi?.chain_id],
      ["OI points in chain", oi?.points_per_symbol],
      ["Recorded OI gaps", chains.filter((row) => row.gap_before != null).length],
      ["Matched feature timestamps", alignment?.matched_feature_timestamps],
      ["Executable feature timestamps", alignment?.executable_feature_timestamps],
      ["Gap-free contemporaneous days", gate?.covered_days],
      ["Required forward days", gate?.required_forward_days],
      ["Remaining days", gate?.remaining_days], ["Collector", collector?.state],
      ["Last collection UTC", collector?.last_collected_at],
      ["Source universe verified", prospective?.source_universe_verified]]} />
    {gate?.basis ? <p>Gate basis: {display(gate.basis)}.</p> : null}
    {chains.filter((row) => row.gap_before != null).map((row) => {
      const gap = row.gap_before as RecordData;
      return <p key={String(row.chain_id)}>{display(row.chain_id)} starts after an unobserved gap of{" "}
        {display(gap.missing_points_per_symbol)} points per symbol ({display(gap.reason)}). The gap is
        recorded, never backfilled.</p>; })}
    <p>{display(gate?.note ?? "Forward days alone authorize nothing; a new preregistration, "
      + "independently dated training and chronological validation are required.")}</p>
    <Details value={prospective ?? null} />
  </section>;
}
function Search004Campaign({ campaign, searches }: { campaign: RecordData; searches: RecordData[] }) {
  const [filter, setFilter] = useState("");
  const [selectedFamily, setSelectedFamily] = useState("");
  const families = (Array.isArray(campaign.families) ? campaign.families : []) as RecordData[];
  const tested = families.filter((row) => row.status !== "UNSUPPORTED_WITH_CURRENT_DATA");
  const visible = families.filter((row) => `${row.family} ${row.status} ${row.reason}`
    .toLowerCase().includes(filter.toLowerCase()));
  const detail = families.find((row) => row.family === selectedFamily);
  return <>
    <div className="notice"><Badge value="NO PROMOTION" />
      <span>Search 004 · newly acquired public history, not a fresh post-search holdout.
        Six forward days cannot establish prospective edge.</span></div>
    <Metrics values={[["Completed searches", searches.length], ["Search", campaign.search_id],
      ["Dataset", (campaign.dataset as RecordData | undefined)?.dataset_id],
      ["Families investigated", families.length], ["Families evaluated", tested.length],
      ["Configurations", campaign.trial_count], ["Replays", campaign.evaluation_count],
      ["Rejected", families.filter((row) => row.status === "REJECTED").length],
      ["Unsupported", families.filter((row) => row.status === "UNSUPPORTED_WITH_CURRENT_DATA").length],
      ["Promoted", Array.isArray(campaign.promoted_candidates) ? campaign.promoted_candidates.length : null]]} />
    <section className="panel"><div className="panel-title"><h2>Search 004 candidates</h2>
      <div className="filters"><label>Filter families <input value={filter}
        onChange={(event) => setFilter(event.target.value)} placeholder="Family or status" /></label>
        <label>Candidate detail <select value={selectedFamily}
          onChange={(event) => setSelectedFamily(event.target.value)}>
          <option value="">Select a family</option>{families.map((row) =>
            <option value={String(row.family)} key={String(row.family)}>{String(row.family)}</option>)}
        </select></label></div></div>
      <div className="table-scroll"><table><caption className="sr-only">Search 004 family evidence</caption>
        <thead><tr>{["Family", "Forward net R", "Trades", "Positive folds", "Base · USDT", "Wide · USDT", "Severe · USDT", "Neighbor folds", "State"].map((name) =>
          <th scope="col" key={name}>{name}</th>)}</tr></thead>
        <tbody>{visible.map((row) => { const costs = row.costs as RecordData | undefined;
          return <tr key={String(row.family)}><th scope="row">{display(row.family)}</th>
            <td>{formatted(row.forward_mean_net_r, 3)}</td><td>{row.status === "UNSUPPORTED_WITH_CURRENT_DATA" ? "—" : display(row.forward_trades)}</td>
            <td>{display(row.positive_folds)}</td><td>{formatted(costs?.base_taker, 2)}</td>
            <td>{formatted(costs?.wide_costs, 2)}</td><td>{formatted(costs?.severe_plausible, 2)}</td>
            <td>{display(row.neighbor_positive_folds)}</td><td><Badge value={row.status} /></td></tr>; })}</tbody>
      </table></div>{!visible.length ? <p className="empty">No families match this filter.</p> : null}
    </section>
    {detail ? <section className="panel" aria-label="Selected candidate detail"><div className="panel-title">
      <h2>{display(detail.family)}</h2><Badge value={detail.status} /></div>
      <p>{display(detail.mechanism ?? detail.reason)}</p><Metrics values={[
        ["Forward net R", detail.forward_mean_net_r], ["Trades", detail.forward_trades],
        ["Positive folds", detail.positive_folds], ["Worst fold drawdown %", detail.max_drawdown_pct],
        ["Max symbol concentration", detail.max_symbol_concentration],
        ["Max day concentration", detail.max_day_concentration],
        ["Beta attribution", detail.beta_attribution]]} />
      <p>Decision: {display(detail.reason)}</p><Details value={detail} /></section> : null}
    <section className="panel"><h2>Evidence boundary</h2>
      <p>The final 232 bars were not replayed; this adjacent tail is not an independent final holdout.
        Historic maker fills and orderbook flow are unavailable. No candidate passed all cost and robustness gates.</p>
      <Details value={{ dataset: campaign.dataset, validation: campaign.validation_design,
        costs: campaign.cost_assumptions, promotion: campaign.promotion_note }} /></section>
  </>;
}
function HistoricalCampaign({ campaign, searches }: { campaign: RecordData | null; searches: RecordData[] }) {
  const [filter, setFilter] = useState("");
  const [selectedFamily, setSelectedFamily] = useState("");
  const families = (
    Array.isArray(campaign?.families) ? campaign.families : []
  ) as RecordData[];
  const query = filter.trim().toLowerCase();
  const selected = families.filter((f) =>
    [f.family, f.mechanism, f.status, ...(Array.isArray(f.reasons) ? f.reasons : [])]
      .map(String)
      .join(" ")
      .toLowerCase()
      .includes(query),
  );
  const detail = families.find((family) => family.family === selectedFamily);
  const rejected = families.filter((family) => family.status === "REJECTED").length;
  return (
    <>
      <div className="notice">
        Discovery → Chronological validation → Holdout → Prospective{" "}
        <span>
          Historical source data was already used in legacy research. These validation
          periods are not a fresh final holdout.
        </span>
      </div>
      <Metrics
        values={[
          ["Completed searches", searches.length],
          ["Search", campaign?.search_id],
          ["Families evaluated · HISTORICAL", families.length],
          ["Rejected · HISTORICAL", rejected],
          [
            "Configurations tested",
            (campaign?.search_budget as RecordData | undefined)?.configurations,
          ],
          ["Total replays", (campaign?.search_budget as RecordData | undefined)?.total_replays],
          ["Inner trials", (campaign?.search_budget as RecordData | undefined)?.selection_evaluations],
          ["Final holdout", campaign?.final_holdout_state],
          [
            "Promoted · HISTORICAL",
            Array.isArray(campaign?.promoted_candidates)
              ? campaign.promoted_candidates.length
              : null,
          ],
        ]}
      />
      <section className="panel">
        <div className="panel-title">
          <h2>Candidate families</h2>
          <div className="filters">
            <label>Filter families{" "}<input value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Family, status, reason" /></label>
            <label>Candidate detail{" "}<select value={selectedFamily}
              onChange={(e) => setSelectedFamily(e.target.value)}>
              <option value="">Select a family</option>
              {families.map((family) => <option key={String(family.family)}
                value={String(family.family)}>{String(family.family)}</option>)}
            </select></label>
          </div>
        </div>
        {selected.length ? (
          <div className="table-scroll">
            <table>
              <caption className="sr-only">
                Research families and validation evidence
              </caption>
              <thead>
                <tr>
                  {[
                    "Family / mechanism",
                    "Discovery",
                    "Chronological validation · reused history",
                    "Robustness",
                    "Lifecycle",
                    "Details",
                  ].map((c) => (
                    <th scope="col" key={c}>
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {selected.map((f) => (
                  <tr key={String(f.family)}>
                    <td>
                      <strong>{display(f.family)}</strong>
                      <small>{display(f.mechanism)}</small>
                    </td>
                    <td>
                      <strong>{(f.discovery as RecordData | undefined)?.mean_net_r == null
                        ? `${display((f.discovery as RecordData | undefined)?.eligible_trials)} eligible inner trials`
                        : `${formatted((f.discovery as RecordData).mean_net_r, 3)} R`}</strong>
                      <Details value={f.discovery} />
                    </td>
                    <td>
                      <strong>{formatted(forwardOf(f)?.mean_net_r, 3)} R</strong>
                      <small>{display(forwardOf(f)?.trades)} trades · {formatted(forwardOf(f)?.total_net_pnl, 2)} USDT net</small>
                      <Details value={forwardOf(f)} />
                    </td>
                    <td>
                      {display(positiveFolds(f))} positive folds
                      <small>Adjusted p: {display(f.adjusted_pvalue)}</small>
                      <small>Wide costs: {formatted(((f.stress_total_net_pnl ?? f.stress) as RecordData | undefined)?.wide_costs, 2)} USDT</small>
                      <small>Severe: {formatted((f.stress_total_net_pnl as RecordData | undefined)?.severe_plausible, 2)} USDT</small>
                      <small>Neighbor: {display((f.parameter_stability as RecordData | undefined)?.neighbor_positive_folds)} positive folds</small>
                    </td>
                    <td>
                      <Badge value={f.status} />
                    </td>
                    <td>
                      <Details value={f} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty">
            {families.length
              ? "No families match this filter."
              : "No research campaign artifact available."}
          </p>
        )}
      </section>
      {detail ? <section className="panel" aria-label="Selected candidate detail">
        <div className="panel-title"><h2>{display(detail.family)}</h2>
          <Badge value={detail.status} /></div>
        <p>{display(detail.mechanism)}</p>
        <Metrics values={[[detail.forward ? "Forward net R · HISTORICAL" : "Validation net R · HISTORICAL",
          forwardOf(detail)?.mean_net_r],
          [detail.forward ? "Forward trades" : "Validation trades", forwardOf(detail)?.trades],
          ["Adjusted p", detail.adjusted_pvalue],
          ["Positive neighbor folds", (detail.parameter_stability as RecordData | undefined)?.neighbor_positive_folds]]} />
        <p>Decision: {Array.isArray(detail.reasons) ? detail.reasons.join("; ") : "Unknown"}</p>
        <Details value={detail} />
      </section> : null}
      <section className="panel">
        <h2>Research protocol & cost sensitivity</h2>
        <Details
          value={{
            validation: campaign?.validation_design ?? null,
            costs: campaign?.cost_assumptions ?? null,
            search_budget: campaign?.search_budget ?? null,
            concentration: "Per-family details preserve symbol/day/regime shares",
            beta_attribution: "Per-family details preserve descriptive BTC/ETH slopes",
            prospective_status: "NO_ACCEPTED_PROSPECTIVE_EVIDENCE",
          }}
        />
      </section>
    </>
  );
}
function Performance({ data }: { data: Snapshot }) {
  const curve = [...(data.events.account ?? [])].reverse();
  const points = curve
    .map((e, i) => ({ i, value: e.payload.equity }))
    .filter(
      (p) =>
        p.value !== null &&
        p.value !== undefined &&
        Number.isFinite(Number(p.value)),
    );
  const nums = points.map((p) => Number(p.value));
  const low = Math.min(...nums),
    high = Math.max(...nums);
  // Plot coordinates are approximate; the caption repeats the exact source strings.
  const lowLabel = display(points[nums.indexOf(low)]?.value);
  const highLabel = display(points[nums.indexOf(high)]?.value);
  const refused = data.evidence.integrity === "FAILED";
  return (
    <>
      <Metrics
        values={[
          ["Realized PnL", data.account?.realized_pnl],
          ["Unrealized PnL", data.account?.unrealized_pnl],
          ["Known fees", data.account?.fees ?? data.account?.known_fees],
          ["Funding", data.account?.funding],
          ["Closed-trade net · window", data.performance?.net_usdt],
          ["Closed-trade net R · window", data.performance?.net_r],
        ]}
      />
      <section className="panel">
        <h2>Simulated equity · observed snapshots</h2>
        {points.length > 1 ? (
          <>
          <figure>
            <svg
              className="chart"
              role="img"
              aria-label="Observed simulated equity curve"
              viewBox="0 0 800 200"
            >
              <polyline
                fill="none"
                stroke="#68dbc1"
                strokeWidth="2"
                points={points
                  .map(
                    (p) =>
                      `${(p.i / Math.max(1, curve.length - 1)) * 780 + 10},${180 - ((Number(p.value) - low) / Math.max(high - low, 1)) * 160}`,
                  )
                  .join(" ")}
              />
            </svg>
            <figcaption>
              Snapshot index · {lowLabel} to {highLabel} USDT. Source values available
              below; no interpolated missing balances.
            </figcaption>
          </figure>
          <div className="table-scroll">
            <table>
              <caption>Observed simulated equity snapshots</caption>
              <thead><tr><th scope="col">Recorded UTC</th><th scope="col">Equity · USDT</th></tr></thead>
              <tbody>{curve.filter((event) => event.payload.equity != null).map((event) =>
                <tr key={event.event_id}><td>{new Date(event.recorded_ms).toISOString()}</td>
                  <td>{display(event.payload.equity)}</td></tr>)}</tbody>
            </table>
          </div>
          </>
        ) : (
          <p className="empty">
            {refused ? "Evidence refused: journal integrity is not verified."
              : "Insufficient equity observations to draw a curve."}
          </p>
        )}
        <Details
          value={curve.map((e) => ({
            recorded_ms: e.recorded_ms,
            ...e.payload,
          }))}
        />
      </section>
      <section className="panel">
        <h2>Attribution coverage</h2>
        <p>Observed closed-trade window only. Unrecorded strategy, regime, R and
          execution-cost components remain Unknown.</p>
        <Details value={data.performance ?? null} />
      </section>
      <Ledger title="Closed trade evidence" events={data.events.trade ?? []} refused={refused} />
    </>
  );
}
export function App() {
  const [page, setPage] = useState<(typeof pages)[number]>("Trader");
  const [mode, setMode] = useState("paper");
  const [data, setData] = useState<Snapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [filter, setFilter] = useState("");
  const [experimentFilter, setExperimentFilter] = useState("");
  const [searchId, setSearchId] = useState("");
  const [knownSearches, setKnownSearches] = useState<RecordData[]>([]);
  const heading = useRef<HTMLHeadingElement>(null);
  // Compare with the previous page so StrictMode's re-run effect cannot steal initial focus.
  const previousPage = useRef<(typeof pages)[number]>(page);
  const [tab, setTab] = useState("position");
  useEffect(() => {
    document.title = `${page} | Trade v2`;
    if (previousPage.current !== page) {
      previousPage.current = page;
      heading.current?.focus();
    }
  }, [page]);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    setData(null);
    async function load() {
      try {
        const response = await fetch(`/api/v1/workstation?mode=${mode}${searchId ? `&search_id=${encodeURIComponent(searchId)}` : ""}`, {
          signal: controller.signal,
        });
        if (!response.ok)
          throw new Error(`Evidence API returned ${response.status}`);
        const snapshot = (await response.json()) as Snapshot;
        setData(snapshot);
        setKnownSearches(snapshot.searches ?? []);
        setError(null);
      } catch (e) {
        if (!controller.signal.aborted) {
          setError(e instanceof Error ? e.message : "Evidence unavailable");
          setData(null);
        }
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(load, 15000);
      }
    }
    void load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [mode, refresh, searchId]);
  const account = data?.account;
  const events = data?.events ?? {};
  const runtime = data?.runtime;
  const searches = data?.searches ?? knownSearches;
  const trialLedger = data?.campaign?.search_id === "TRADEV2_ALPHA_SEARCH_004"
    || isDiscovery(data?.campaign);
  const prospective = data?.prospective as RecordData | undefined;
  const refused = data?.evidence.integrity === "FAILED";
  const researchErrors = data?.evidence.research_errors ?? [];
  return (
    <div className="shell">
      <a className="skip" href="#content">
        Skip to content
      </a>
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setPage("Trader");
          }}
        >
          <span className="brand-icon">
            T<span>²</span>
          </span>
          <span>
            TRADE <b>v2</b>
            <small>QUANT WORKSTATION</small>
          </span>
        </a>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Primary">
          {pages.map((name, i) => (
            <button
              key={name}
              className={name === page ? "active" : ""}
              aria-current={name === page ? "page" : undefined}
              onClick={() => setPage(name)}
            >
              <span aria-hidden="true">{icons[i]}</span>
              {name}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="dot" /> Research & simulation
          <small>Bybit Linear · USDT</small>
          <Badge value="LIVE_DISABLED" />
          <p>Evidence before deployment.</p>
        </div>
      </aside>
      <div className="workspace">
        <header>
          <div className="breadcrumb">
            WORKSPACE <span>/</span> {page}
          </div>
          <div className="toolbar">
            <label>
              Mode{" "}
              <select value={mode} onChange={(e) => setMode(e.target.value)}>
                <option value="paper">Paper</option>
                <option value="shadow">Shadow</option>
              </select>
            </label>
            <button onClick={() => setRefresh((v) => v + 1)}>↻ Refresh</button>
            <Badge
              value={
                error ? "API UNAVAILABLE" : (runtime?.safety ?? "UNKNOWN")
              }
            />
          </div>
        </header>
        <main id="content" tabIndex={-1}>
          <div className="page-heading">
            <div>
              <div className="eyebrow">RESEARCH / SIMULATED EXECUTION</div>
              <h1 ref={heading} tabIndex={-1}>
                {page}
              </h1>
              <p>
                {
                  {
                    Trader:
                      "Account, execution and the evidence behind every decision.",
                    "Alpha Lab":
                      "Search broadly. Validate chronologically. Preserve every result.",
                    Symbols:
                      "Point-in-time market observations and opportunity coverage.",
                    Experiments:
                      "Reproducible searches, hypotheses and validation records.",
                    Performance:
                      "Observed simulation accounting. Unknown values remain unknown.",
                    System:
                      "Runtime integrity, provenance and operational boundaries.",
                  }[page]
                }
              </p>
            </div>
            <div className="run-label">
              RUN <strong>{runtime?.run_id ?? "No run selected"}</strong>
              <small>
                {data
                  ? new Date(data.generated_ms).toISOString()
                  : "Waiting for evidence API"}
              </small>
            </div>
          </div>
          {(page === "Alpha Lab" || page === "Experiments") && searches.length ? (
            <section className="panel">
              <label>Research search <select value={searchId || String(data?.campaign?.search_id ?? "")}
                onChange={(event) => setSearchId(event.target.value)}>
                {searches.map((search) => <option key={String(search.search_id)}
                  value={String(search.search_id)}>{display(search.search_id)}</option>)}
              </select></label>
              <p>Sealed campaigns remain separately inspectable; selecting one does not rerun it.</p>
              {searchId ? <button onClick={() => setSearchId("")}>Reset research search</button> : null}
            </section>
          ) : null}
          {error ? (
            <div role="alert" className="notice error">
              {error}. Cached values have been removed. Check the local API and
              refresh.
            </div>
          ) : null}
          {!data ? (
            <section className="panel empty">
              <h2>{error ? "Evidence unavailable" : "Loading evidence"}</h2>
              <p>No account values or research outcomes are assumed.</p>
            </section>
          ) : (
            <>
              {page === "Trader" ? (
                <>
                  <div className="notice">
                    <Badge value={runtime?.status} />
                    <Badge value={runtime?.freshness} />
                    <span>
                      {mode.toUpperCase()} simulation · {runtimeContext(runtime?.status, runtime?.freshness)} · record age{" "}
                      {runtime?.age_ms === null
                        ? "unknown"
                        : `${Math.round((runtime?.age_ms ?? 0) / 1000)}s`}{" "}
                      · journal {data.evidence.integrity.toLowerCase()}
                    </span>
                    <span className="notice-end">Live execution disabled</span>
                  </div>
                  <Metrics
                    values={[
                      ["Selected candidate", runtime?.candidate_id],
                      ["Candidate stage", runtime?.candidate_stage],
                      ["Halt latch", runtime?.pending_halt == null ? null
                        : runtime.pending_halt ? `LATCHED · ${display(runtime.halt_reason)}` : "CLEAR"],
                      ["Public market", data.system.public_market],
                      ["Equity · USDT", account?.equity],
                      ["Start equity", account?.start_equity],
                      ["Equity delta", account?.equity_delta],
                      ["Realized PnL", account?.realized_pnl],
                      ["Unrealized PnL", account?.unrealized_pnl],
                      ["Known fees", account?.known_fees ?? account?.fees],
                      ["Funding", account?.funding],
                      ["Funding completeness", account?.funding_completeness],
                      ["Drawdown", account?.drawdown],
                      ["Open risk", account?.open_risk],
                      [
                        "Net completeness",
                        account?.net_complete ?? account?.net_completeness,
                      ],
                    ]}
                  />
                  <div className="section-tabs" role="group" aria-label="Execution evidence">
                    {[
                      "position",
                      "order",
                      "trade",
                      "opportunity",
                      "decision",
                      "rejection",
                    ].map((kind) => (
                      <button
                        key={kind}
                        aria-pressed={tab === kind}
                        className={tab === kind ? "selected" : ""}
                        onClick={() => setTab(kind)}
                      >
                        {plural(kind)}{" "}
                        <span>{refused ? "Unknown" : events[kind]?.length ?? 0}</span>
                      </button>
                    ))}
                  </div>
                  <Ledger
                    title={plural(tab)}
                    events={events[tab] ?? []}
                    refused={refused}
                  />
                </>
              ) : null}
              {(page === "Alpha Lab" || page === "Experiments") && researchErrors.length ? (
                <div role="alert" className="notice error">
                  Sealed research integrity failed for {researchErrors.join(", ")}. Those artifacts
                  are withheld; the search shown below is the latest one that verified.
                </div>
              ) : null}
              {page === "Alpha Lab" ? (
                <>
                  <Campaign campaign={data.campaign} searches={data.searches ?? []}
                    candidates={data.candidates ?? []} />
                  <ProspectiveGate prospective={prospective} />
                </>
              ) : null}
              {page === "Symbols" ? (
                <>
                  <section className="panel">
                    <label>
                      Filter symbol{" "}
                      <input
                        value={filter}
                        onChange={(e) => setFilter(e.target.value)}
                        placeholder="BTCUSDT"
                      />
                    </label>
                    <p>
                      Showing source market observations. Watch status, net R,
                      fee tier and spread remain unknown unless included in the
                      source record.
                    </p>
                  </section>
                  <section className="panel">
                    <h2>Per-symbol evidence · latest window</h2>
                    {(data.symbols ?? []).length ? (
                      <div className="table-scroll">
                        <table>
                          <caption className="sr-only">Per-symbol simulated evidence</caption>
                          <thead><tr>{["Symbol", "Signals", "Opportunities", "Entries", "Closed trades", "Net USDT", "Net R", "Spread bps", "Freshness ms", "Rejections"].map((name) =>
                            <th scope="col" key={name}>{name}</th>)}</tr></thead>
                          <tbody>{(data.symbols ?? []).filter((row) =>
                            display(row.symbol).toLowerCase().includes(filter.toLowerCase())).map((row) =>
                            <tr key={String(row.symbol)}>
                              <th scope="row">{display(row.symbol)}</th>
                              <td>{display(row.signals)}</td><td>{display(row.opportunities)}</td>
                              <td>{display(row.entries)}</td><td>{display(row.closed_trades)}</td>
                              <td>{display(row.net_usdt)}</td><td>{display(row.net_r)}</td>
                              <td>{display(row.spread_bps)}</td><td>{display(row.source_age_ms)}</td>
                              <td>{display(row.rejections)}</td>
                            </tr>)}</tbody>
                        </table>
                      </div>
                    ) : <p className="empty">{refused ? "Evidence refused: journal integrity is not verified."
                      : "No per-symbol evidence available."}</p>}
                  </section>
                  <Ledger
                    title="Market observations"
                    events={(events.market ?? []).filter((e) =>
                      display(e.payload.symbol)
                        .toLowerCase()
                        .includes(filter.toLowerCase()),
                    )}
                    refused={refused}
                  />
                  <Ledger
                    title="Rejection waterfall evidence"
                    events={(events.rejection ?? []).filter((e) =>
                      display(e.payload.symbol)
                        .toLowerCase()
                        .includes(filter.toLowerCase()),
                    )}
                    refused={refused}
                  />
                </>
              ) : null}
              {page === "Experiments" ? (
                <>
                  <div className="notice">HISTORICAL / IMMUTABLE · consumed search and paired stress evidence</div>
                  <Metrics
                    values={[
                      ["Search ID", data.campaign?.search_id],
                      ["Completed searches", data.searches?.length],
                      [trialLedger ? "Recorded evaluations" : "Paired stress records", data.experiments?.length],
                      ["Complete", data.campaign?.complete],
                      ["Evidence role", data.campaign?.evidence_role ?? "HISTORICAL_CAMPAIGN"],
                      ["Holdout state", data.campaign?.final_holdout_state
                        ?? data.campaign?.promotion_note ?? data.campaign?.promotion],
                    ]}
                  />
                  <section className="panel">
                    <h2>Search history and campaign design</h2>
                    <Details value={{ searches: data.searches ?? [],
                      validation: data.campaign?.validation_design,
                      costs: data.campaign?.cost_assumptions }} />
                    <p>All research periods reuse historical data. No experiment here is fresh final holdout evidence.</p>
                  </section>
                  <section className="panel">
                    <div className="panel-title"><h2>{trialLedger ? "Chronological trial ledger" : "Paired execution-cost stress"}</h2>
                      <label>Filter experiments{" "}<input value={experimentFilter}
                        onChange={(e) => setExperimentFilter(e.target.value)}
                        placeholder="Family or treatment" /></label></div>
                    {(data.experiments ?? []).length ? (
                      <div className="table-scroll"><table>
                        <caption className="sr-only">{trialLedger ? "Chronological trial ledger"
                          : "Common-opportunity paired stress comparisons"}</caption>
                        <thead><tr>{["Family", "Fold", "Treatment", "Trade n", trialLedger ? "Net R" : "Mean paired Δ · USDT", "CI", "Status"].map((name) =>
                          <th scope="col" key={name}>{name}</th>)}</tr></thead>
                        <tbody>{(data.experiments ?? []).filter((row) =>
                          `${row.hypothesis} ${row.treatment}`.toLowerCase().includes(experimentFilter.toLowerCase())).map((row, index) =>
                          <tr key={`${row.hypothesis}-${row.checkpoint}-${row.treatment}-${index}`}>
                            <th scope="row">{display(row.hypothesis)}</th><td>{display(row.checkpoint)}</td>
                            <td>{display(row.treatment)}</td><td>{display(row.n)}</td>
                            <td>{formatted(row.net_r ?? row.mean_paired_delta, 3)}</td><td>{display(row.ci)}</td>
                            <td><Badge value={row.status} /></td>
                          </tr>)}</tbody>
                      </table></div>
                    ) : <p className="empty">No paired execution-cost evidence recorded.</p>}
                    <p>Opportunity-intent pairing is descriptive; portfolio refilling was replayed separately. CI is Unknown.</p>
                  </section>
                  <section className="panel">
                    <h2>Run manifests</h2>
                    {data.manifests.length ? (
                      data.manifests.map((m, i) => (
                        <Details key={i} value={m} />
                      ))
                    ) : (
                      <p>No run manifests available.</p>
                    )}
                  </section>
                </>
              ) : null}
              {page === "Performance" ? <Performance data={data} /> : null}
              {page === "System" ? (
                <>
                  <Metrics
                    values={[
                      ["API", data.system.api],
                      ["Authority", data.system.authority],
                      ["Journal integrity", data.evidence.integrity],
                      ["Research integrity", data.evidence.research_integrity],
                      ["Runtime", runtime?.status],
                      ["Candidate", runtime?.candidate_id],
                      ["Candidate stage", runtime?.candidate_stage],
                      ["Public Bybit", data.system.public_market],
                      ["Software Git SHA", typeof data.system.git_sha === "string" ? data.system.git_sha.slice(0, 12) : null],
                      ["Frontend", "RENDERED_LOCAL"],
                      ["Source freshness", runtime?.source_freshness],
                      ["Engine observation", runtime?.engine],
                      ["Safety", runtime?.safety],
                      ["Reconciliation", data.system.reconciliation],
                      ["Protection", data.system.protection],
                      ["Testnet", data.system.testnet === "DEDICATED_AUTHORIZATION_REQUIRED" ? "AUTHORIZATION REQUIRED" : data.system.testnet],
                      ["Public recorder", (data.system.public_recorder as RecordData | undefined)?.status],
                      ["Prospective data", prospective?.status],
                      ["Prospective collector", (prospective?.collector as RecordData | undefined)?.state],
                      ["Live barrier", data.system.live],
                    ]}
                  />
                  <section className="panel">
                    <h2>Evidence health</h2>
                    <Details value={data.evidence} />
                    <p>
                      Freshness is recomputed at request time. A verified
                      historical journal does not establish current operational
                      safety.
                    </p>
                  </section>
                  <section className="panel">
                    <h2>Runtime provenance</h2>
                    <Details value={{ runtime, manifests: data.manifests,
                      public_recorder: data.system.public_recorder }} />
                  </section>
                </>
              ) : null}
            </>
          )}
        </main>
        <footer>
          Trade v2{" "}
          <span>
            Read-only workstation · monetary values retain source precision
          </span>
          <span>v0.1 / EVIDENCE FIRST</span>
        </footer>
      </div>
    </div>
  );
}
