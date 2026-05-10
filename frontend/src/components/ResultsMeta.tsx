import React from "react";
import { SearchResponse } from "../types";

interface Props {
  response: SearchResponse;
}

export default function ResultsMeta({ response }: Props) {
  const eligibleCount = response.results.filter((r) => r.eligible).length;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-slate-500">
      <div>
        Showing <span className="font-medium text-slate-700">{response.results.length}</span> results
        for <span className="font-medium text-slate-700">{response.normalized_condition}</span>
        {" "}({response.candidates_retrieved} candidates screened)
      </div>
      <div className="flex items-center gap-4">
        <span>
          <span className="font-medium text-green-600">{eligibleCount}</span> likely eligible
        </span>
        <span className="text-slate-300">|</span>
        <span>{Math.round(response.latency_ms)}ms</span>
      </div>
    </div>
  );
}
