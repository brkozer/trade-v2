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
  experiments?: RecordData[];
  symbols?: RecordData[];
  performance?: RecordData;
  evidence: { integrity: string; errors: string[]; journals: number };
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
function formatted(value: unknown, decimals: number): string {
  if (value === null || value === undefined || value === "") return "Unknown";
  const parsed = Number(value);
  return Number.isFinite(parsed)
    ? parsed.toLocaleString("en-US", {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      })
    : "Unknown";
}
function Badge({ value }: { value: unknown }) {
  const text = display(value);
  return (
    <span
      className={
        "badge " +
        (/UNKNOWN|STALE|INSUFFICIENT|REJECT|FAILED|DISABLED|BLOCKED|STOPPED|UNVERIFIED/i.test(text)
          ? "amber"
          : "")
      }
    >
      {text}
    </span>
  );
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
function Ledger({ title, events }: { title: string; events: Event[] }) {
  return (
    <section className="panel">
      <div className="panel-title">
        <h2>{title}</h2>
        <span>{events.length} records · latest window</span>
      </div>
      {events.length ? (
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
function Campaign({ campaign, searches }: { campaign: RecordData | null; searches: RecordData[] }) {
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
          ["Final holdout", campaign?.final_holdout_state ? "NOT ACQUIRED" : null],
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
                      <strong>{formatted(((f.forward ?? f.oos) as RecordData | undefined)?.mean_net_r, 3)} R</strong>
                      <small>{display(((f.forward ?? f.oos) as RecordData | undefined)?.trades)} trades · {formatted(((f.forward ?? f.oos) as RecordData | undefined)?.total_net_pnl, 2)} USDT net</small>
                      <Details value={f.forward ?? f.oos} />
                    </td>
                    <td>
                      {display(f.positive_folds ?? (Array.isArray(f.folds) ?
                        f.folds.filter((fold: RecordData) => Number(((fold.forward ?? fold.validation) as RecordData | undefined)?.total_net_pnl) > 0).length : null))} positive folds
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
        <Metrics values={[["Forward net R · HISTORICAL", (detail.forward as RecordData | undefined)?.mean_net_r],
          ["Forward trades", (detail.forward as RecordData | undefined)?.trades],
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
              Snapshot index · {low} to {high} USDT. Source values available
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
            Insufficient equity observations to draw a curve.
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
      <Ledger title="Closed trade evidence" events={data.events.trade ?? []} />
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
  const heading = useRef<HTMLHeadingElement>(null);
  const initialPage = useRef(true);
  const [tab, setTab] = useState("position");
  useEffect(() => {
    document.title = `${page} | Trade v2`;
    if (initialPage.current) {
      initialPage.current = false;
    } else {
      heading.current?.focus();
    }
  }, [page]);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    setData(null);
    async function load() {
      try {
        const response = await fetch(`/api/v1/workstation?mode=${mode}`, {
          signal: controller.signal,
        });
        if (!response.ok)
          throw new Error(`Evidence API returned ${response.status}`);
        setData((await response.json()) as Snapshot);
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
  }, [mode, refresh]);
  const account = data?.account;
  const events = data?.events ?? {};
  const runtime = data?.runtime;
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
                    <span>
                      {mode.toUpperCase()} simulation · {runtime?.status === "STOPPED" ? "last run, not current account" : "CURRENT runtime"} · record age{" "}
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
                      ["Public market", data.system.public_market],
                      ["Equity · USDT", account?.equity],
                      ["Start equity", account?.start_equity],
                      ["Equity delta", account?.equity_delta],
                      ["Realized PnL", account?.realized_pnl],
                      ["Unrealized PnL", account?.unrealized_pnl],
                      ["Known fees", account?.known_fees ?? account?.fees],
                      ["Funding", account?.funding],
                      ["Drawdown", account?.drawdown],
                      ["Open risk", account?.open_risk],
                      [
                        "Net completeness",
                        account?.net_complete ?? account?.net_completeness,
                      ],
                    ]}
                  />
                  <div className="section-tabs" aria-label="Execution evidence">
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
                        <span>{events[kind]?.length ?? 0}</span>
                      </button>
                    ))}
                  </div>
                  <Ledger
                    title={plural(tab)}
                    events={events[tab] ?? []}
                  />
                </>
              ) : null}
              {page === "Alpha Lab" ? (
                <Campaign campaign={data.campaign} searches={data.searches ?? []} />
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
                    ) : <p className="empty">No per-symbol evidence available.</p>}
                  </section>
                  <Ledger
                    title="Market observations"
                    events={(events.market ?? []).filter((e) =>
                      display(e.payload.symbol)
                        .toLowerCase()
                        .includes(filter.toLowerCase()),
                    )}
                  />
                  <Ledger
                    title="Rejection waterfall evidence"
                    events={(events.rejection ?? []).filter((e) =>
                      display(e.payload.symbol)
                        .toLowerCase()
                        .includes(filter.toLowerCase()),
                    )}
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
                      ["Paired stress records", data.experiments?.length],
                      ["Complete", data.campaign?.complete],
                      ["Holdout state", data.campaign?.final_holdout_state ? "NOT ACQUIRED" : null],
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
                    <div className="panel-title"><h2>Paired execution-cost stress</h2>
                      <label>Filter experiments{" "}<input value={experimentFilter}
                        onChange={(e) => setExperimentFilter(e.target.value)}
                        placeholder="Family or treatment" /></label></div>
                    {(data.experiments ?? []).length ? (
                      <div className="table-scroll"><table>
                        <caption className="sr-only">Common-opportunity paired stress comparisons</caption>
                        <thead><tr>{["Family", "Fold", "Treatment", "Common n", "Mean paired Δ · USDT", "CI", "Status"].map((name) =>
                          <th scope="col" key={name}>{name}</th>)}</tr></thead>
                        <tbody>{(data.experiments ?? []).filter((row) =>
                          `${row.hypothesis} ${row.treatment}`.toLowerCase().includes(experimentFilter.toLowerCase())).map((row, index) =>
                          <tr key={`${row.hypothesis}-${row.checkpoint}-${row.treatment}-${index}`}>
                            <th scope="row">{display(row.hypothesis)}</th><td>{display(row.checkpoint)}</td>
                            <td>{display(row.treatment)}</td><td>{display(row.n)}</td>
                            <td>{formatted(row.mean_paired_delta, 3)}</td><td>{display(row.ci)}</td>
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
