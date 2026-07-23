"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type Exchange = {
  exchange_id: string;
  provider: string;
  model: string;
  round: number;
  prompt_sent: string;
  answer: string | null;
  status: string;
  error: string | null;
  requested_at: string;
  responded_at: string | null;
};

type Run = {
  run_id: string;
  original_prompt: string;
  rounds_requested: number;
  status: string;
  created_at: string;
  completed_at: string | null;
  exchanges: Exchange[];
};

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function latency(start: string, end: string | null) {
  if (!end) return "Pending";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

function providerName(value: string) {
  return value === "anthropic" ? "Claude" : value === "openai" ? "OpenAI" : value;
}

export default function Home() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [current, setCurrent] = useState<Run | null>(null);
  const [detail, setDetail] = useState<Exchange | null>(null);
  const [query, setQuery] = useState("");
  const [provider, setProvider] = useState("all");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const fetchRun = useCallback(async (id: string) => {
    const response = await fetch(`${API}/v1/runs/${id}`, { cache: "no-store" });
    if (!response.ok) throw new Error("Unable to load the selected run.");
    const run: Run = await response.json();
    setCurrent(run);
    setDetail((selected) =>
      selected
        ? run.exchanges.find((item) => item.exchange_id === selected.exchange_id) ??
          run.exchanges[0] ??
          null
        : run.exchanges[0] ?? null,
    );
  }, []);

  const refresh = useCallback(
    async (quiet = false) => {
      if (!quiet) setLoading(true);
      try {
        const response = await fetch(`${API}/v1/runs?limit=100`, { cache: "no-store" });
        if (!response.ok) throw new Error("Unable to load run history.");
        const history: Run[] = await response.json();
        setRuns(history);
        setError("");
        if (history.length) {
          await fetchRun(history[0].run_id);
        }
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Backend unavailable.");
      } finally {
        if (!quiet) setLoading(false);
      }
    },
    [fetchRun],
  );

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(true), 4000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const filteredRuns = useMemo(() => {
    const term = query.trim().toLowerCase();
    return runs.filter(
      (run) =>
        !term ||
        run.original_prompt.toLowerCase().includes(term) ||
        run.run_id.toLowerCase().includes(term),
    );
  }, [query, runs]);

  const providers = useMemo(
    () => [...new Set((current?.exchanges ?? []).map((item) => item.provider))],
    [current],
  );

  const exchanges = useMemo(
    () =>
      (current?.exchanges ?? []).filter(
        (item) => provider === "all" || item.provider === provider,
      ),
    [current, provider],
  );

  return (
    <main>
      <header className="topbar">
        <div className="brand">
          <span className="logo">↔</span>
          <div>
            <h1>Cross Talker</h1>
            <p>Interaction ledger</p>
          </div>
        </div>
        <div className="top-actions">
          <span className={error ? "connection down" : "connection"}>
            <i /> {error ? "Backend offline" : "Auto-syncing"}
          </span>
          <button onClick={() => void refresh()}>Refresh</button>
        </div>
      </header>

      <div className="workspace">
        <aside className="history">
          <div className="section-title">
            <div>
              <small>History</small>
              <h2>Model runs</h2>
            </div>
            <b>{runs.length}</b>
          </div>
          <label className="search">
            <span>⌕</span>
            <input
              aria-label="Search runs"
              placeholder="Search prompts or IDs"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          <div className="run-list">
            {loading && <p className="message">Loading interactions…</p>}
            {!loading && error && (
              <p className="message error">
                {error}
                <small>Start the Python API on port 8000.</small>
              </p>
            )}
            {filteredRuns.map((run) => (
              <button
                className={`run-card ${current?.run_id === run.run_id ? "active" : ""}`}
                key={run.run_id}
                onClick={() => void fetchRun(run.run_id)}
              >
                <span className="card-meta">
                  <i className={run.status}>{run.status}</i>
                  <time>{formatDate(run.created_at)}</time>
                </span>
                <strong>{run.original_prompt}</strong>
                <span className="card-meta">
                  <span>{run.rounds_requested + 1} levels</span>
                  <code>#{run.run_id.slice(0, 8)}</code>
                </span>
              </button>
            ))}
          </div>
        </aside>

        <section className="ledger">
          {current ? (
            <>
              <div className="run-heading">
                <div>
                  <small>Original prompt</small>
                  <h2>{current.original_prompt}</h2>
                  <p>
                    <span className={`pill ${current.status}`}>{current.status}</span>
                    {formatDate(current.created_at)}
                    <code>{current.run_id}</code>
                  </p>
                </div>
                <div className="stats">
                  <span>
                    <b>{current.rounds_requested + 1}</b> Levels
                  </span>
                  <span>
                    <b>{current.exchanges.length}</b> Exchanges
                  </span>
                  <span>
                    <b>{providers.length}</b> Providers
                  </span>
                </div>
              </div>

              <div className="toolbar">
                <div className="legend">
                  <span><i className="openai" /> OpenAI</span>
                  <span><i className="anthropic" /> Claude</span>
                </div>
                <label>
                  Provider
                  <select value={provider} onChange={(e) => setProvider(e.target.value)}>
                    <option value="all">All providers</option>
                    {providers.map((name) => (
                      <option key={name} value={name}>{providerName(name)}</option>
                    ))}
                  </select>
                </label>
              </div>

              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Level</th>
                      <th>Provider / model</th>
                      <th>Prompt sent</th>
                      <th>Answer returned</th>
                      <th>Timing</th>
                    </tr>
                  </thead>
                  <tbody>
                    {exchanges.map((exchange, index) => (
                      <tr
                        key={exchange.exchange_id}
                        className={`${index === 0 || exchanges[index - 1].round !== exchange.round ? "level-start" : ""} ${detail?.exchange_id === exchange.exchange_id ? "selected" : ""}`}
                        onClick={() => setDetail(exchange)}
                      >
                        <td className="level">
                          <b>{exchange.round}</b>
                          <small>{exchange.round ? "Review" : "Initial"}</small>
                        </td>
                        <td>
                          <div className={`provider ${exchange.provider}`}>
                            <span>{exchange.provider === "anthropic" ? "C" : "O"}</span>
                            <div>
                              <b>{providerName(exchange.provider)}</b>
                              <small>{exchange.model}</small>
                            </div>
                          </div>
                        </td>
                        <td><p className="clamp">{exchange.prompt_sent}</p></td>
                        <td><p className="clamp">{exchange.answer ?? exchange.error ?? "Pending"}</p></td>
                        <td>
                          <b className="timing">{latency(exchange.requested_at, exchange.responded_at)}</b>
                          <small>{formatDate(exchange.requested_at)}</small>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            !loading && !error && <p className="empty">No stored interactions yet.</p>
          )}
        </section>
      </div>

      {detail && (
        <aside className="inspector">
          <header>
            <div>
              <small>Exchange detail</small>
              <h2>Level {detail.round} · {providerName(detail.provider)}</h2>
            </div>
            <button aria-label="Close details" onClick={() => setDetail(null)}>×</button>
          </header>
          <dl>
            <div><dt>Model</dt><dd>{detail.model}</dd></div>
            <div><dt>Latency</dt><dd>{latency(detail.requested_at, detail.responded_at)}</dd></div>
            <div><dt>Status</dt><dd>{detail.status}</dd></div>
            <div><dt>Exchange ID</dt><dd><code>{detail.exchange_id.slice(0, 12)}…</code></dd></div>
          </dl>
          <article>
            <header><b>Prompt sent</b><small>{detail.prompt_sent.length} chars</small></header>
            <pre>{detail.prompt_sent}</pre>
          </article>
          <div className="flow">↓ provider response</div>
          <article className="answer">
            <header><b>Answer returned</b><small>{detail.answer?.length ?? 0} chars</small></header>
            <pre>{detail.answer ?? detail.error ?? "Pending"}</pre>
          </article>
        </aside>
      )}
    </main>
  );
}
