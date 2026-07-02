import React, { useState } from "react";

interface Props {
  onSearch: (symptoms: string, maxResults: number, statusFilter: string) => void;
  loading: boolean;
}

const EXAMPLES = [
  "58-year-old male, type 2 diabetes 8 years, HbA1c 8.2%, on metformin, BMI 29, no cardiovascular disease",
  "55-year-old female, treatment-resistant depression, failed 2 SSRIs, no psychosis, BMI 24",
  "67-year-old male, Parkinson's disease 3 years, Hoehn-Yahr stage 2, on levodopa",
  "70-year-old female, early Alzheimer's disease, MMSE 22, living at home, no severe comorbidities",
];

export default function SearchForm({ onSearch, loading }: Props) {
  const [symptoms, setSymptoms] = useState("");
  const [maxResults, setMaxResults] = useState(5);
  const [statusFilter, setStatusFilter] = useState("RECRUITING");
  const [showOptions, setShowOptions] = useState(false);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (symptoms.trim().length < 3) return;
    onSearch(symptoms.trim(), maxResults, statusFilter);
  }

  const canSearch = symptoms.trim().length >= 3 && !loading;

  return (
    <form onSubmit={handleSubmit} className="bg-white rounded-2xl shadow-xl shadow-brand-900/10 overflow-hidden">
      {/* Main input area */}
      <div className="p-4 sm:p-5">
        <label htmlFor="symptoms" className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
          Describe your symptoms or condition
        </label>
        <textarea
          id="symptoms"
          value={symptoms}
          onChange={(e) => setSymptoms(e.target.value)}
          rows={3}
          placeholder="e.g. 58-year-old male, type 2 diabetes 8 years, HbA1c 8.2%, on metformin, BMI 29, no cardiovascular disease"
          className="w-full text-sm text-slate-800 placeholder-slate-400 bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:bg-white focus:border-transparent resize-none transition-all"
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSubmit(e as any);
          }}
        />

        {/* Example chips */}
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          <span className="text-xs text-slate-400 mr-0.5 self-center">Try:</span>
          {EXAMPLES.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => setSymptoms(q)}
              className="text-xs bg-slate-100 hover:bg-brand-50 text-slate-600 hover:text-brand-700 border border-slate-200 hover:border-brand-200 px-2.5 py-1 rounded-full transition-colors text-left"
            >
              {q.length > 58 ? q.slice(0, 55) + "…" : q}
            </button>
          ))}
        </div>
      </div>

      {/* Bottom bar */}
      <div className="px-4 sm:px-5 py-3 bg-slate-50 border-t border-slate-100 flex flex-wrap items-center gap-3">
        {/* Advanced options toggle */}
        <button
          type="button"
          onClick={() => setShowOptions((v) => !v)}
          className="text-xs text-slate-500 hover:text-slate-700 flex items-center gap-1 transition-colors"
        >
          <svg className={`w-3.5 h-3.5 transition-transform ${showOptions ? "rotate-90" : ""}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          Options
        </button>

        {showOptions && (
          <>
            <div className="flex items-center gap-2">
              <label htmlFor="maxResults" className="text-xs text-slate-500 whitespace-nowrap">Results:</label>
              <select
                id="maxResults"
                value={maxResults}
                onChange={(e) => setMaxResults(Number(e.target.value))}
                className="text-xs rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-slate-700 focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                {[3, 5, 10, 20].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
            <div className="flex items-center gap-2">
              <label htmlFor="statusFilter" className="text-xs text-slate-500 whitespace-nowrap">Status:</label>
              <select
                id="statusFilter"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="text-xs rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-slate-700 focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                <option value="RECRUITING">Recruiting</option>
                <option value="ACTIVE_NOT_RECRUITING">Active, not recruiting</option>
                <option value="COMPLETED">Completed</option>
                <option value="">All statuses</option>
              </select>
            </div>
          </>
        )}

        <div className="ml-auto flex items-center gap-2">
          {symptoms.trim().length > 0 && symptoms.trim().length < 3 && (
            <span className="text-xs text-rose-400">Type at least 3 characters</span>
          )}
          <button
            type="submit"
            disabled={!canSearch}
            className="inline-flex items-center gap-2 px-5 py-2 bg-brand-600 text-white text-sm font-semibold rounded-xl hover:bg-brand-700 active:bg-brand-800 disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-sm shadow-brand-600/30"
          >
            {loading ? (
              <>
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Searching…
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                Search Trials
              </>
            )}
          </button>
        </div>
      </div>
    </form>
  );
}
