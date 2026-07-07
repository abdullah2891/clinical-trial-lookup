import React, { useCallback, useEffect, useRef, useState } from "react";
import { fetchExperiments, runExperiment } from "../api";
import { Experiment, ExperimentsResponse } from "../types";

const POLL_MS = 5000;

// Higher-is-better scores get traffic-light colors; error metrics stay neutral
const ERROR_METRICS = new Set(["confidence_abs_error"]);

function ScoreBadge({ metric, value }: { metric: string; value: number }) {
  if (ERROR_METRICS.has(metric)) {
    return (
      <span className="inline-block px-2 py-0.5 rounded-full text-xs font-medium tabular-nums bg-slate-100 text-slate-600">
        {metric.replace(/_/g, " ")}: {value.toFixed(3)}
      </span>
    );
  }
  const pct = Math.round(value * 100);
  const cls =
    pct >= 85 ? "bg-emerald-100 text-emerald-700" :
    pct >= 70 ? "bg-amber-100 text-amber-700" :
    "bg-rose-100 text-rose-700";
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold tabular-nums ${cls}`}>
      {metric.replace(/_/g, " ")}: {pct}%
    </span>
  );
}

function formatDate(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit",
  });
}

export default function MonitoringPage() {
  const [data, setData] = useState<ExperimentsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const resp = await fetchExperiments();
      setData(resp);
      setError(null);
      return resp;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load experiments");
      return null;
    }
  }, []);

  // Initial load + poll while an experiment is running
  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (data?.running && !pollRef.current) {
      pollRef.current = setInterval(load, POLL_MS);
    }
    if (!data?.running && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [data?.running, load]);

  async function handleRun(suite: "screener" | "agent" | "guardrail") {
    setStarting(true);
    setError(null);
    try {
      await runExperiment(suite);
      setData((d) => (d ? { ...d, running: true } : d));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start experiment");
    } finally {
      setStarting(false);
    }
  }

  const running = data?.running ?? false;

  return (
    <div className="animate-fade-in space-y-4">
      {/* Header row */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Model Monitoring</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Golden-set evaluations of the eligibility screener, logged to LangSmith
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {(["screener", "agent", "guardrail"] as const).map((suite) => (
            <button
              key={suite}
              onClick={() => handleRun(suite)}
              disabled={running || starting || data?.langsmith_configured === false}
              className="inline-flex items-center gap-2 px-3.5 py-2 bg-brand-600 text-white text-sm font-semibold rounded-xl hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-sm shadow-brand-600/30"
            >
              {running || starting ? (
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              ) : (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              )}
              Run {suite} eval
            </button>
          ))}
        </div>
      </div>

      {/* Running banner */}
      {running && (
        <div className="flex items-center gap-2 rounded-xl bg-brand-50 border border-brand-200 px-4 py-3 text-sm text-brand-700">
          <span className="w-2 h-2 rounded-full bg-brand-500 animate-pulse-slow" />
          Screening the golden set (~30s) — results appear below when done.
        </div>
      )}

      {/* Errors */}
      {error && (
        <div className="rounded-xl bg-rose-50 border border-rose-200 px-4 py-3 text-sm text-rose-700">
          {error}
        </div>
      )}
      {data?.last_error && !running && (
        <div className="rounded-xl bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-700">
          Last run failed: {data.last_error}
        </div>
      )}
      {data?.langsmith_configured === false && (
        <div className="rounded-xl bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-700">
          LangSmith is not configured on the server (LANGCHAIN_API_KEY missing).
        </div>
      )}

      {/* Experiments table */}
      {data && data.experiments.length > 0 && (
        <div className="bg-white rounded-2xl border border-slate-100 shadow-card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">
                <th className="px-4 py-3">Experiment</th>
                <th className="px-4 py-3">Suite</th>
                <th className="px-4 py-3">Date</th>
                <th className="px-4 py-3 text-center">Examples</th>
                <th className="px-4 py-3">Scores</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.experiments.map((exp: Experiment) => (
                <tr key={exp.name} className="hover:bg-slate-50 transition-colors">
                  <td className="px-4 py-3 font-mono text-xs text-slate-700">{exp.name}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${
                      exp.dataset === "agent" ? "bg-violet-100 text-violet-700" :
                      exp.dataset === "guardrail" ? "bg-rose-100 text-rose-700" :
                      "bg-sky-100 text-sky-700"
                    }`}>
                      {exp.dataset}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-500 whitespace-nowrap">{formatDate(exp.start_time)}</td>
                  <td className="px-4 py-3 text-center text-xs text-slate-600 tabular-nums">{exp.run_count ?? "—"}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {Object.entries(exp.scores).map(([metric, value]) => (
                        <ScoreBadge key={metric} metric={metric} value={value} />
                      ))}
                      {Object.keys(exp.scores).length === 0 && <span className="text-xs text-slate-400">—</span>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Empty state */}
      {data && data.experiments.length === 0 && data.langsmith_configured && !running && (
        <div className="flex flex-col items-center py-16 text-center">
          <p className="text-slate-600 font-medium">No experiments yet</p>
          <p className="text-sm text-slate-400 mt-1">Click "Run experiment" to evaluate the screener against the golden set</p>
        </div>
      )}

      {/* Loading initial */}
      {!data && !error && (
        <div className="flex items-center gap-2 text-sm text-slate-500 py-8 justify-center">
          <svg className="w-4 h-4 animate-spin text-brand-500" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          Loading experiments…
        </div>
      )}

      <p className="text-xs text-slate-400 text-center pt-2">
        Full traces and per-example scores at{" "}
        <a href="https://smith.langchain.com" target="_blank" rel="noopener noreferrer"
          className="text-brand-500 hover:text-brand-600 underline">
          smith.langchain.com
        </a>
      </p>
    </div>
  );
}
