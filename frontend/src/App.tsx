import React, { useEffect, useState } from "react";
import { searchTrials, getPassword, clearPassword, setAuthErrorHandler } from "./api";
import { SearchResponse } from "./types";
import LoginScreen from "./components/LoginScreen";
import SearchForm from "./components/SearchForm";
import TrialCard from "./components/TrialCard";
import ResultsMeta from "./components/ResultsMeta";
import MonitoringPage from "./components/MonitoringPage";
import AgentPage from "./components/AgentPage";

type Tab = "search" | "agent" | "monitoring";

export default function App() {
  const [authed, setAuthed] = useState<boolean>(() => Boolean(getPassword()));
  const [tab, setTab] = useState<Tab>("search");
  const [loading, setLoading] = useState(false);

  // A 401 from any API call (wrong/expired password) drops back to login
  useEffect(() => {
    setAuthErrorHandler(() => setAuthed(false));
  }, []);

  if (!authed) {
    return <LoginScreen onSuccess={() => setAuthed(true)} />;
  }
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  async function handleSearch(symptoms: string, maxResults: number, statusFilter: string) {
    setLoading(true);
    setError(null);
    setResponse(null);
    setHasSearched(true);
    try {
      const data = await searchTrials({ symptoms, max_results: maxResults, status_filter: statusFilter });
      setResponse(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error occurred");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col">
      {/* ── Hero / Header ────────────────────────────────────────────── */}
      <header className="bg-gradient-to-br from-brand-700 via-brand-600 to-brand-800 text-white">
        <div className="max-w-4xl mx-auto px-4 pt-10 pb-12">
          <div className="flex items-center justify-between gap-2 mb-3">
            <span className="inline-flex items-center gap-1.5 bg-white/20 text-white text-xs font-semibold px-3 py-1 rounded-full backdrop-blur-sm">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse-slow" />
              AI-Powered · 62,000+ Trials
            </span>
            <nav className="flex gap-1 bg-white/10 rounded-full p-1 backdrop-blur-sm">
              {(["search", "agent", "monitoring"] as Tab[]).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`px-3.5 py-1 rounded-full text-xs font-semibold capitalize transition-colors ${
                    tab === t ? "bg-white text-brand-700" : "text-white/80 hover:text-white"
                  }`}
                >
                  {t}
                </button>
              ))}
            </nav>
          </div>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight mb-2">
            Clinical Trial Search
          </h1>
          <p className="text-brand-100 text-base max-w-xl leading-relaxed">
            Describe your symptoms in plain language. BioMistral-7B screens trial
            eligibility and ranks results by confidence — no medical jargon required.
          </p>
        </div>
      </header>

      {/* ── Search form ──────────────────────────────────────────────── */}
      {tab === "search" && (
        <div className="bg-gradient-to-b from-brand-700 to-transparent">
          <div className="max-w-4xl mx-auto px-4 -mt-4 pb-6">
            <SearchForm onSearch={handleSearch} loading={loading} />
          </div>
        </div>
      )}

      {/* ── Main content ─────────────────────────────────────────────── */}
      <main className={`flex-1 max-w-4xl mx-auto w-full px-4 pb-16 space-y-4 ${tab !== "search" ? "pt-8" : ""}`}>
        {tab === "monitoring" && <MonitoringPage />}
        {tab === "agent" && <AgentPage />}
        {tab === "search" && (
        <>
        {/* Error */}
        {error && (
          <div className="animate-fade-in flex items-start gap-3 rounded-xl bg-rose-50 border border-rose-200 p-4 text-sm text-rose-700">
            <svg className="w-5 h-5 shrink-0 mt-0.5 text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div>
              <p className="font-semibold">Search failed</p>
              <p className="mt-0.5 text-rose-600">{error}</p>
            </div>
          </div>
        )}

        {/* Loading skeletons */}
        {loading && (
          <div className="space-y-3 animate-fade-in">
            <div className="flex items-center gap-2 text-sm text-slate-500 mb-2">
              <svg className="w-4 h-4 animate-spin text-brand-500" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Searching 62,000+ trials and screening eligibility…
            </div>
            {[0.9, 0.75, 0.6].map((w, i) => (
              <div key={i} className="bg-white rounded-2xl border border-slate-100 shadow-card p-5 animate-pulse">
                <div className="flex items-start justify-between gap-4 mb-4">
                  <div className="flex-1 space-y-2">
                    <div className="h-4 bg-slate-200 rounded-lg" style={{ width: `${w * 100}%` }} />
                    <div className="h-3 bg-slate-100 rounded w-24" />
                  </div>
                  <div className="flex gap-2">
                    <div className="h-6 w-20 bg-slate-200 rounded-full" />
                    <div className="h-6 w-24 bg-slate-100 rounded-full" />
                  </div>
                </div>
                <div className="space-y-2">
                  <div className="h-3 bg-slate-100 rounded w-full" />
                  <div className="h-3 bg-slate-100 rounded w-5/6" />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Results */}
        {response && !loading && (
          <div className="animate-fade-in space-y-4">
            <ResultsMeta response={response} />
            {response.results.length === 0 ? (
              <div className="flex flex-col items-center py-16 text-center">
                <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mb-4">
                  <svg className="w-8 h-8 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                      d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                </div>
                <p className="text-slate-600 font-medium">No eligible trials found</p>
                <p className="text-sm text-slate-400 mt-1">Try adding more detail — age, diagnosis, medications, or lab values</p>
              </div>
            ) : (
              <div className="space-y-3">
                {response.results.map((result, i) => (
                  <TrialCard key={result.nct_id} result={result} rank={i + 1} />
                ))}
              </div>
            )}
          </div>
        )}

        {/* Empty state before first search */}
        {!hasSearched && !loading && (
          <div className="text-center py-12">
            <p className="text-sm text-slate-400">Enter your symptoms above to find matching trials</p>
          </div>
        )}
        </>
        )}
      </main>

      <footer className="border-t border-slate-200 bg-white py-5 text-center text-xs text-slate-400">
        For research purposes only &mdash; always consult your physician before enrolling in a clinical trial.
        <span className="mx-2 text-slate-200">|</span>
        Data from ClinicalTrials.gov
      </footer>
    </div>
  );
}
