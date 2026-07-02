import React, { useState } from "react";
import { ScreeningResult } from "../types";

interface Props {
  result: ScreeningResult;
  rank: number;
}

function ConfidenceBar({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  const color =
    pct >= 75 ? "bg-emerald-500" :
    pct >= 50 ? "bg-amber-400" :
    "bg-rose-400";
  const label =
    pct >= 75 ? "text-emerald-700" :
    pct >= 50 ? "text-amber-700" :
    "text-rose-600";
  return (
    <div className="flex items-center gap-2 min-w-[100px]">
      <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={`text-xs font-semibold tabular-nums ${label}`}>{pct}%</span>
    </div>
  );
}

export default function TrialCard({ result, rank }: Props) {
  const [expanded, setExpanded] = useState(false);
  const hasCriteria = result.key_criteria_met.length > 0 || result.key_criteria_failed.length > 0;

  return (
    <article className="bg-white rounded-2xl border border-emerald-200 shadow-card hover:shadow-card-hover transition-shadow overflow-hidden animate-fade-in">
      {/* Left accent stripe */}
      <div className="flex">
        <div className="w-1 shrink-0 rounded-l-2xl bg-emerald-400" />

        <div className="flex-1 p-5">
          {/* Header */}
          <div className="flex flex-wrap items-start gap-3 mb-3">
            {/* Rank bubble */}
            <span className="shrink-0 mt-0.5 w-6 h-6 rounded-full bg-slate-100 text-slate-500 text-xs font-bold flex items-center justify-center">
              {rank}
            </span>

            <div className="flex-1 min-w-0">
              <a
                href={result.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm font-semibold text-slate-900 hover:text-brand-600 transition-colors line-clamp-2 leading-snug"
              >
                {result.title}
              </a>
              <p className="mt-1 text-xs font-mono text-slate-400">{result.nct_id}</p>
            </div>

            {/* Eligibility badge + confidence */}
            <div className="shrink-0 flex flex-col items-end gap-1.5">
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-500 text-white">
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                </svg>
                Likely Eligible
              </span>
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-slate-400">Confidence</span>
                <ConfidenceBar confidence={result.confidence} />
              </div>
            </div>
          </div>

          {/* AI reason */}
          {result.reason && (
            <p className="text-sm text-slate-600 leading-relaxed bg-slate-50 rounded-xl px-4 py-3 border border-slate-100">
              {result.reason}
            </p>
          )}

          {/* Expand toggle */}
          {hasCriteria && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-brand-600 hover:text-brand-700 transition-colors"
            >
              <svg
                className={`w-3.5 h-3.5 transition-transform ${expanded ? "rotate-90" : ""}`}
                fill="none" viewBox="0 0 24 24" stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
              {expanded ? "Hide criteria breakdown" : "View criteria breakdown"}
            </button>
          )}

          {/* Expanded criteria breakdown */}
          {expanded && hasCriteria && (
            <div className="mt-3 grid sm:grid-cols-2 gap-3 animate-fade-in">
              {result.key_criteria_met.length > 0 && (
                <div className="rounded-xl bg-emerald-50 border border-emerald-100 p-3">
                  <p className="text-xs font-semibold text-emerald-700 mb-2 flex items-center gap-1">
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                    </svg>
                    Criteria met ({result.key_criteria_met.length})
                  </p>
                  <ul className="space-y-1.5">
                    {result.key_criteria_met.map((c, i) => (
                      <li key={i} className="text-xs text-emerald-800 leading-snug flex items-start gap-1.5">
                        <span className="shrink-0 mt-0.5 text-emerald-400">•</span>
                        {c}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {result.key_criteria_failed.length > 0 && (
                <div className="rounded-xl bg-rose-50 border border-rose-100 p-3">
                  <p className="text-xs font-semibold text-rose-700 mb-2 flex items-center gap-1">
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                    Not met ({result.key_criteria_failed.length})
                  </p>
                  <ul className="space-y-1.5">
                    {result.key_criteria_failed.map((c, i) => (
                      <li key={i} className="text-xs text-rose-800 leading-snug flex items-start gap-1.5">
                        <span className="shrink-0 mt-0.5 text-rose-400">•</span>
                        {c}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* CTA link */}
          <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between">
            <a
              href={result.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs font-medium text-brand-600 hover:text-brand-700 transition-colors"
            >
              View full trial on ClinicalTrials.gov
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </a>
          </div>
        </div>
      </div>
    </article>
  );
}
