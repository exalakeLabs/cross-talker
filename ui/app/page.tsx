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
  diagnostic_detail: string | null;
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
  recap: {
    provider_emphases: {
      provider: string;
      initial_position: string;
      main_emphases: string[];
      evolution: string;
      final_conclusion: string;
    }[];
    agreements: string[];
    disagreements: {
      topic: string;
      positions: Record<string, string>;
      nature: string;
    }[];
    overall_synthesis: string;
    unresolved_questions: string[];
    generated_by: string;
  } | null;
  recap_error: string | null;
};

type Health = {
  status: string;
  configured_providers: string[];
  max_rounds?: number;
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
  const [view, setView] = useState<"exchanges" | "diagnostics">("exchanges");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [composerOpen, setComposerOpen] = useState(false);
  const [newPrompt, setNewPrompt] = useState("");
  const [availableProviders, setAvailableProviders] = useState<string[]>([
    "openai",
    "anthropic",
  ]);
  const [selectedProviders, setSelectedProviders] = useState<string[]>([
    "openai",
    "anthropic",
  ]);
  const [rounds, setRounds] = useState(2);
  const [maxRounds, setMaxRounds] = useState(20);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");

  const fetchRun = useCallback(async (id: string) => {
    const response = await fetch(`${API}/v1/runs/${id}`, { cache: "no-store" });
    if (!response.ok) throw new Error("Unable to load the selected run.");
    const run: Run = await response.json();
    setCurrent(run);
    setDetail((selected) =>
      selected
        ? run.exchanges.find((item) => item.exchange_id === selected.exchange_id) ??
          null
        : null,
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

  useEffect(() => {
    void fetch(`${API}/health`, { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) return;
        const health: Health = await response.json();
        if (typeof health.max_rounds === "number") {
          setMaxRounds(health.max_rounds);
          setRounds((current) => Math.min(current, health.max_rounds ?? 20));
        }
        if (health.configured_providers.length) {
          setAvailableProviders(health.configured_providers);
          setSelectedProviders(health.configured_providers);
          if (health.configured_providers.length === 1) setRounds(0);
        }
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!composerOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !submitting) setComposerOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [composerOpen, submitting]);

  function toggleProvider(name: string) {
    setSelectedProviders((selected) => {
      const next = selected.includes(name)
        ? selected.filter((providerName) => providerName !== name)
        : [...selected, name];
      if (next.length < 2) setRounds(0);
      return next;
    });
  }

  async function submitPrompt(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!newPrompt.trim() || selectedProviders.length === 0) return;
    setSubmitting(true);
    setSubmitError("");
    try {
      const response = await fetch(`${API}/v1/cross-talk`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: newPrompt.trim(),
          providers: selectedProviders,
          rounds: selectedProviders.length > 1 ? rounds : 0,
        }),
      });
      if (!response.ok) {
        const failure = await response.json().catch(() => null);
        throw new Error(failure?.detail ?? "The cross-talk run failed.");
      }
      const result = await response.json();
      setNewPrompt("");
      setComposerOpen(false);
      await refresh(true);
      await fetchRun(result.run_id);
    } catch (caught) {
      setSubmitError(
        caught instanceof Error ? caught.message : "The cross-talk run failed.",
      );
    } finally {
      setSubmitting(false);
    }
  }

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
          <button
            className="new-run-button"
            onClick={() => {
              setSubmitError("");
              setComposerOpen(true);
            }}
          >
            + New cross-talk
          </button>
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
                <div className="view-tabs" aria-label="Run view">
                  <button
                    className={view === "exchanges" ? "active" : ""}
                    onClick={() => setView("exchanges")}
                  >
                    Exchanges
                  </button>
                  <button
                    className={view === "diagnostics" ? "active" : ""}
                    onClick={() => setView("diagnostics")}
                  >
                    Diagnostics
                    {current.exchanges.some((item) => item.status === "failed") && (
                      <i aria-label="This run contains failures" />
                    )}
                  </button>
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

              {view === "exchanges" ? (
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
              ) : (
                <section className="diagnostics">
                  <header>
                    <div>
                      <small>Service-side provider activity</small>
                      <h3>Run diagnostics</h3>
                    </div>
                    <p>
                      <b>{exchanges.filter((item) => item.status === "failed").length}</b>
                      {" "}failures · <b>{exchanges.length}</b> calls
                    </p>
                  </header>
                  {current.recap ? (
                    <section className="run-recap">
                      <header>
                        <div>
                          <small>Cross-model synthesis</small>
                          <h3>Discussion recap</h3>
                        </div>
                        <span>Generated by {providerName(current.recap.generated_by)}</span>
                      </header>

                      <div className="emphasis-grid">
                        {current.recap.provider_emphases.map((item) => (
                          <article key={item.provider}>
                            <header>
                              <b>{providerName(item.provider)}</b>
                              <small>Provider emphasis</small>
                            </header>
                            <div>
                              <h4>Initial position</h4>
                              <p>{item.initial_position}</p>
                              <h4>Main emphases</h4>
                              <ul>
                                {item.main_emphases.map((emphasis) => (
                                  <li key={emphasis}>{emphasis}</li>
                                ))}
                              </ul>
                              <h4>Evolution</h4>
                              <p>{item.evolution}</p>
                              <h4>Final conclusion</h4>
                              <p>{item.final_conclusion}</p>
                            </div>
                          </article>
                        ))}
                      </div>

                      <div className="consensus-grid">
                        <article className="agreement">
                          <header><b>Agreement</b><small>{current.recap.agreements.length} points</small></header>
                          <ul>
                            {current.recap.agreements.map((item) => (
                              <li key={item}>{item}</li>
                            ))}
                            {!current.recap.agreements.length && <li>No clear agreement identified.</li>}
                          </ul>
                        </article>
                        <article className="unresolved">
                          <header><b>Unresolved</b><small>{current.recap.unresolved_questions.length} questions</small></header>
                          <ul>
                            {current.recap.unresolved_questions.map((item) => (
                              <li key={item}>{item}</li>
                            ))}
                            {!current.recap.unresolved_questions.length && <li>No unresolved questions identified.</li>}
                          </ul>
                        </article>
                      </div>

                      <article className="disagreement">
                        <header>
                          <b>Disagreement</b>
                          <small>{current.recap.disagreements.length} topics</small>
                        </header>
                        {current.recap.disagreements.length ? (
                          <div className="disagreement-table">
                            {current.recap.disagreements.map((item) => (
                              <div className="disagreement-row" key={item.topic}>
                                <div>
                                  <b>{item.topic}</b>
                                  <small>{item.nature}</small>
                                </div>
                                <dl>
                                  {Object.entries(item.positions).map(([name, position]) => (
                                    <div key={name}>
                                      <dt>{providerName(name)}</dt>
                                      <dd>{position}</dd>
                                    </div>
                                  ))}
                                </dl>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p>No material disagreement was identified.</p>
                        )}
                      </article>

                      <article className="synthesis">
                        <header><b>Overall synthesis</b></header>
                        <p>{current.recap.overall_synthesis}</p>
                      </article>
                    </section>
                  ) : (
                    <p className={`recap-unavailable ${current.recap_error ? "failed" : ""}`}>
                      {current.recap_error
                        ? `Recap generation failed: ${current.recap_error}`
                        : "No synthesized recap is available for this run."}
                    </p>
                  )}
                  <div className="diagnostic-divider">
                    <span>Provider call log</span>
                  </div>
                  <div className="diagnostic-list">
                    {exchanges.map((exchange) => (
                      <article
                        className={`diagnostic-event ${exchange.status}`}
                        key={exchange.exchange_id}
                      >
                        <span className="event-marker" />
                        <div className="event-body">
                          <header>
                            <div>
                              <span className={`event-status ${exchange.status}`}>
                                {exchange.status}
                              </span>
                              <b>{providerName(exchange.provider)}</b>
                              <code>{exchange.model}</code>
                            </div>
                            <time>{formatDate(exchange.requested_at)}</time>
                          </header>
                          <dl>
                            <div><dt>Level</dt><dd>{exchange.round}</dd></div>
                            <div><dt>Duration</dt><dd>{latency(exchange.requested_at, exchange.responded_at)}</dd></div>
                            <div><dt>Exchange</dt><dd><code>{exchange.exchange_id.slice(0, 12)}…</code></dd></div>
                          </dl>
                          {exchange.error ? (
                            <>
                              <p className="event-error">{exchange.error}</p>
                              <pre>{exchange.diagnostic_detail ?? "No additional diagnostic detail was captured."}</pre>
                            </>
                          ) : (
                            <p className="event-success">
                              Provider response completed successfully
                              {exchange.answer ? ` · ${exchange.answer.length.toLocaleString()} characters` : ""}.
                            </p>
                          )}
                        </div>
                      </article>
                    ))}
                    {!exchanges.length && (
                      <p className="empty-diagnostics">No provider calls match this filter.</p>
                    )}
                  </div>
                </section>
              )}
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

      {composerOpen && (
        <div
          className="modal-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !submitting) {
              setComposerOpen(false);
            }
          }}
        >
          <section
            aria-labelledby="new-cross-talk-title"
            aria-modal="true"
            className="composer"
            role="dialog"
          >
            <header>
              <div>
                <small>New conversation</small>
                <h2 id="new-cross-talk-title">Start a cross-talk run</h2>
              </div>
              <button
                aria-label="Close new prompt"
                disabled={submitting}
                onClick={() => setComposerOpen(false)}
              >
                ×
              </button>
            </header>
            <form onSubmit={submitPrompt}>
              <label className="prompt-field">
                <span>Prompt</span>
                <textarea
                  autoFocus
                  disabled={submitting}
                  maxLength={100000}
                  placeholder="What should the models investigate, debate, or verify?"
                  required
                  rows={6}
                  value={newPrompt}
                  onChange={(event) => setNewPrompt(event.target.value)}
                />
                <small>{newPrompt.length.toLocaleString()} / 100,000</small>
              </label>

              <fieldset>
                <legend>Models</legend>
                <div className="model-options">
                  {availableProviders.map((name) => (
                    <label
                      className={`model-option ${name} ${
                        selectedProviders.includes(name) ? "checked" : ""
                      }`}
                      key={name}
                    >
                      <input
                        checked={selectedProviders.includes(name)}
                        disabled={submitting}
                        onChange={() => toggleProvider(name)}
                        type="checkbox"
                      />
                      <span className="model-icon">
                        {name === "anthropic" ? "C" : "O"}
                      </span>
                      <span>
                        <b>{providerName(name)}</b>
                        <small>
                          {name === "anthropic"
                            ? "Claude Sonnet"
                            : "GPT model"}
                        </small>
                      </span>
                      <i>✓</i>
                    </label>
                  ))}
                </div>
                {selectedProviders.length === 0 && (
                  <p className="field-error">Select at least one model.</p>
                )}
              </fieldset>

              <label className="round-field">
                <span>
                  Review levels
                  <small>
                    {selectedProviders.length < 2
                      ? "A second model is required for cross-checking."
                      : `Each model reviews the other model at every level. Maximum ${maxRounds}.`}
                  </small>
                </span>
                <input
                  disabled={submitting || selectedProviders.length < 2}
                  max={maxRounds}
                  min={0}
                  onChange={(event) => setRounds(Number(event.target.value))}
                  type="number"
                  value={selectedProviders.length < 2 ? 0 : rounds}
                />
              </label>

              {submitError && <p className="submit-error">{submitError}</p>}

              <footer>
                <p>
                  {selectedProviders.length || 0} model
                  {selectedProviders.length === 1 ? "" : "s"} ·{" "}
                  {selectedProviders.length > 1 ? rounds + 1 : 1} total level
                  {selectedProviders.length > 1 && rounds !== 0 ? "s" : ""}
                </p>
                <div>
                  <button
                    disabled={submitting}
                    onClick={() => setComposerOpen(false)}
                    type="button"
                  >
                    Cancel
                  </button>
                  <button
                    className="submit-run"
                    disabled={
                      submitting ||
                      !newPrompt.trim() ||
                      selectedProviders.length === 0
                    }
                    type="submit"
                  >
                    {submitting ? "Models are responding…" : "Start cross-talk"}
                  </button>
                </div>
              </footer>
            </form>
          </section>
        </div>
      )}
    </main>
  );
}
