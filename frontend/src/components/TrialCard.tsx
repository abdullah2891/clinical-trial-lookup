import React, { useState } from "react";
import { ScreeningResult } from "../types";

interface Props {
  result: ScreeningResult;
}

function ConfidenceBadge({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  const color =
    pct >= 80 ? "bg-green-100 text-green-800" :
    pct >= 60 ? "bg-yellow-100 text-yellow-800" :
    "bg-red-100 text-red-800";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${color}`}>
      {pct}% confidence
    </span>
  );
}

function EligibilityBadge({ eligible }: { eligible: boolean }) {
  return eligible ? (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-green-500 text-white">
      Likely Eligible
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-red-500 text-white">
      Likely Ineligible
    </span>
  );
}

export default function TrialCard({ result }: Props) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className={`bg-white rounded-xl border shadow-sm transition-shadow hover:shadow-md ${
      result.eligible ? "border-green-200" : "border-slate-200"
    }`}>
      <div className="p-5">
        {/* Header row */}
        <div className="flex flex-wrap items-start justify-between gap-2 mb-3">
          <div className="flex-1 min-w-0">
            <a
              href={result.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-base font-semibold text-slate-900 hover:text-brand-600 transition-colors line-clamp-2"
            >
              {result.title}
            </a>
            <p className="mt-0.5 text-xs text-slate-400 font-mono">{result.nct_id}</p>
          </div>
          <div className="flex flex-col items-end gap-1 shrink-0">
            <EligibilityBadge eligible={result.eligible} />
            <ConfidenceBadge confidence={result.confidence} />
          </div>
        </div>

        {/* Reason */}
        <p className="text-sm text-slate-600 leading-relaxed">{result.reason}</p>

        {/* Expand toggle */}
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-3 text-xs text-brand-600 hover:text-brand-700 font-medium"
        >
          {expanded ? "Hide details" : "Show criteria breakdown"}
        </button>

        {/* Expanded criteria */}
        {expanded && (
          <div className="mt-3 space-y-3">
            {result.key_criteria_met.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-green-700 mb-1">Criteria met</p>
                <ul className="space-y-1">
                  {result.key_criteria_met.map((c, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-slate-700">
                      <span className="text-green-500 mt-0.5 shrink-0">&#10003;</span>
                      {c}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {result.key_criteria_failed.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-red-700 mb-1">Criteria not met</p>
                <ul className="space-y-1">
                  {result.key_criteria_failed.map((c, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-slate-700">
                      <span className="text-red-500 mt-0.5 shrink-0">&#10007;</span>
                      {c}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <a
              href={result.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block mt-1 text-xs text-brand-600 underline underline-offset-2"
            >
              View full trial on ClinicalTrials.gov
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
