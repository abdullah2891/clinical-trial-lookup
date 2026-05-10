import React, { useState } from "react";
import { searchTrials } from "./api";
import { SearchResponse } from "./types";
import SearchForm from "./components/SearchForm";
import TrialCard from "./components/TrialCard";
import ResultsMeta from "./components/ResultsMeta";

export default function App() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<SearchResponse | null>(null);

  async function handleSearch(symptoms: string, maxResults: number, statusFilter: string) {
    setLoading(true);
    setError(null);
    setResponse(null);
    try {
      const data = await searchTrials({ symptoms, max_results: maxResults, status_filter: statusFilter });
      setResponse(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 shadow-sm">
        <div className="max-w-4xl mx-auto px-4 py-6">
          <h1 className="text-2xl font-bold text-slate-900">Clinical Trial Search</h1>
          <p className="mt-1 text-sm text-slate-500">
            Describe your symptoms in plain language — AI screens trial eligibility using BioMistral-7B
          </p>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8 space-y-6">
        {/* Search form */}
        <SearchForm onSearch={handleSearch} loading={loading} />

        {/* Error */}
        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Loading skeleton */}
        {loading && (
          <div className="space-y-4">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="bg-white rounded-xl border border-slate-200 p-6 animate-pulse">
                <div className="h-4 bg-slate-200 rounded w-3/4 mb-3" />
                <div className="h-3 bg-slate-200 rounded w-1/2 mb-2" />
                <div className="h-3 bg-slate-200 rounded w-2/3" />
              </div>
            ))}
          </div>
        )}

        {/* Results */}
        {response && !loading && (
          <>
            <ResultsMeta response={response} />
            {response.results.length === 0 ? (
              <div className="text-center py-12 text-slate-400">
                No matching trials found. Try broadening your symptom description.
              </div>
            ) : (
              <div className="space-y-4">
                {response.results.map((result) => (
                  <TrialCard key={result.nct_id} result={result} />
                ))}
              </div>
            )}
          </>
        )}
      </main>

      <footer className="mt-16 border-t border-slate-200 py-6 text-center text-xs text-slate-400">
        For research purposes only. Always consult your physician before enrolling in a clinical trial.
      </footer>
    </div>
  );
}
