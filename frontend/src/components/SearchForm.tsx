import React, { useState } from "react";

interface Props {
  onSearch: (symptoms: string, maxResults: number, statusFilter: string) => void;
  loading: boolean;
}

const EXAMPLE_QUERIES = [
  "chest tightness and shortness of breath for 3 months",
  "type 2 diabetes with peripheral neuropathy",
  "relapsing MS, failed two DMTs",
  "HER2 positive breast cancer, prior trastuzumab",
];

export default function SearchForm({ onSearch, loading }: Props) {
  const [symptoms, setSymptoms] = useState("");
  const [maxResults, setMaxResults] = useState(5);
  const [statusFilter, setStatusFilter] = useState("RECRUITING");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (symptoms.trim().length < 3) return;
    onSearch(symptoms.trim(), maxResults, statusFilter);
  }

  return (
    <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4">
      {/* Symptom textarea */}
      <div>
        <label htmlFor="symptoms" className="block text-sm font-medium text-slate-700 mb-1">
          Describe your symptoms or condition
        </label>
        <textarea
          id="symptoms"
          value={symptoms}
          onChange={(e) => setSymptoms(e.target.value)}
          rows={3}
          placeholder="e.g. chest tightness and shortness of breath for 3 months, diagnosed with mild heart failure"
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent resize-none"
        />
        <div className="mt-1 flex flex-wrap gap-2">
          {EXAMPLE_QUERIES.map((q) => (
            <button
              type="button"
              key={q}
              onClick={() => setSymptoms(q)}
              className="text-xs text-brand-600 hover:text-brand-700 underline underline-offset-2"
            >
              {q.length > 50 ? q.slice(0, 47) + "…" : q}
            </button>
          ))}
        </div>
      </div>

      {/* Options row */}
      <div className="flex flex-wrap gap-4 items-end">
        <div>
          <label htmlFor="maxResults" className="block text-xs font-medium text-slate-600 mb-1">
            Max results
          </label>
          <select
            id="maxResults"
            value={maxResults}
            onChange={(e) => setMaxResults(Number(e.target.value))}
            className="rounded-md border border-slate-300 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            {[3, 5, 10, 20].map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="statusFilter" className="block text-xs font-medium text-slate-600 mb-1">
            Trial status
          </label>
          <select
            id="statusFilter"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-md border border-slate-300 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            <option value="RECRUITING">Recruiting</option>
            <option value="ACTIVE_NOT_RECRUITING">Active, not recruiting</option>
            <option value="COMPLETED">Completed</option>
            <option value="">All</option>
          </select>
        </div>

        <button
          type="submit"
          disabled={loading || symptoms.trim().length < 3}
          className="ml-auto px-5 py-2 bg-brand-600 text-white text-sm font-medium rounded-lg hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? "Searching…" : "Search Trials"}
        </button>
      </div>
    </form>
  );
}
