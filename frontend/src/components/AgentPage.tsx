import React, { useState } from "react";
import { streamAgentSearch } from "../api";
import { AgentEvent, AgentTrial, RetrievalResult } from "../types";

const EXAMPLE_QUESTIONS = [
  "Are there immunotherapy trials for stage III lung cancer that allow prior chemotherapy?",
  "What trials exist for treatment-resistant depression that don't involve SSRIs?",
  "Which Parkinson's trials accept patients already on levodopa?",
];

interface TimelineItem {
  event: AgentEvent;
  key: string;
}

function SubQuestionsCard({ subs }: { subs: string[] }) {
  return (
    <div className="rounded-xl bg-white border border-slate-100 shadow-card p-4 animate-fade-in">
      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
        1 · Question decomposed
      </p>
      <div className="flex flex-wrap gap-1.5">
        {subs.map((q) => (
          <span key={q} className="text-xs bg-brand-50 text-brand-700 border border-brand-100 px-2.5 py-1 rounded-full">
            {q}
          </span>
        ))}
      </div>
    </div>
  );
}

function RetrievalCard({ round, results, total }: { round: number; results: RetrievalResult[]; total: number }) {
  return (
    <div className="rounded-xl bg-white border border-slate-100 shadow-card p-4 animate-fade-in">
      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
        Retrieval round {round} · {total} unique trials so far
      </p>
      <ul className="space-y-1.5">
        {results.map((r) => (
          <li key={r.query} className="text-xs text-slate-600 flex items-start gap-2">
            <svg className="w-3.5 h-3.5 mt-0.5 shrink-0 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <span>
              <span className="text-slate-800">{r.query}</span>
              <span className="text-slate-400"> — {r.count} trials</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function AnalysisCard({ iteration, decision, reasoning, newQueries }: {
  iteration: number; decision: string; reasoning: string; newQueries: string[];
}) {
  const refine = decision === "refine";
  return (
    <div className={`rounded-xl border shadow-card p-4 animate-fade-in ${
      refine ? "bg-amber-50 border-amber-200" : "bg-emerald-50 border-emerald-200"
    }`}>
      <p className="text-xs font-semibold uppercase tracking-wider mb-1.5 flex items-center gap-2">
        <span className={refine ? "text-amber-700" : "text-emerald-700"}>
          Analysis {iteration} · {refine ? "needs refinement" : "ready to answer"}
        </span>
      </p>
      <p className="text-sm text-slate-700 leading-relaxed">{reasoning}</p>
      {refine && newQueries.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {newQueries.map((q) => (
            <span key={q} className="text-xs bg-white text-amber-700 border border-amber-200 px-2.5 py-1 rounded-full">
              → {q}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function AnswerCard({ answer, trials }: { answer: string; trials: AgentTrial[] }) {
  return (
    <div className="rounded-2xl bg-white border-2 border-brand-200 shadow-card-hover p-5 animate-fade-in">
      <p className="text-xs font-semibold text-brand-600 uppercase tracking-wider mb-2">Answer</p>
      <p className="text-sm text-slate-800 leading-relaxed whitespace-pre-wrap">{answer}</p>
      {trials.length > 0 && (
        <div className="mt-4 pt-3 border-t border-slate-100 space-y-2">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Cited trials</p>
          {trials.map((t) => (
            <a key={t.nct_id} href={t.url} target="_blank" rel="noopener noreferrer"
              className="block rounded-lg border border-slate-100 hover:border-brand-200 hover:bg-brand-50/40 px-3 py-2 transition-colors">
              <span className="text-xs font-mono text-slate-400">{t.nct_id}</span>
              <p className="text-sm text-slate-800 leading-snug">{t.title}</p>
              {t.conditions.length > 0 && (
                <p className="text-xs text-slate-400 mt-0.5">{t.conditions.join(" · ")}</p>
              )}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

export default function AgentPage() {
  const [question, setQuestion] = useState("");
  const [items, setItems] = useState<TimelineItem[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Clarifying questions the agent asked, and the user's typed answers
  const [pendingQuestions, setPendingQuestions] = useState<string[] | null>(null);
  const [answers, setAnswers] = useState<Record<number, string>>({});

  async function runStream(text: string, clarifications: string) {
    setError(null);
    setRunning(true);
    setPendingQuestions(null);
    setItems([]);
    let i = 0;
    try {
      await streamAgentSearch(
        text,
        (event) => {
          if (event.type === "error") {
            setError(event.detail);
            return;
          }
          if (event.type === "done") return;
          if (event.type === "clarification") {
            setPendingQuestions(event.questions);
            setAnswers({});
            return;
          }
          i += 1;
          setItems((prev) => [...prev, { event, key: `${event.type}-${i}` }]);
        },
        clarifications,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Agent search failed");
    } finally {
      setRunning(false);
    }
  }

  async function handleAsk(q?: string) {
    const text = (q ?? question).trim();
    if (text.length < 3 || running) return;
    if (q) setQuestion(q);
    await runStream(text, "");
  }

  async function handleSubmitClarifications() {
    if (!pendingQuestions || running) return;
    // Fold the Q/A pairs into a single clarifications string
    const clarifications = pendingQuestions
      .map((q, idx) => (answers[idx]?.trim() ? `${q} ${answers[idx].trim()}` : ""))
      .filter(Boolean)
      .join(" | ");
    if (!clarifications) return;
    await runStream(question.trim(), clarifications);
  }

  return (
    <div className="animate-fade-in space-y-4">
      <div>
        <h2 className="text-lg font-bold text-slate-900">Agentic Trial Research</h2>
        <p className="text-xs text-slate-500 mt-0.5">
          A LangGraph agent decomposes your question, searches the trial database in
          multiple directions, and refines until it can answer — watch it work below.
        </p>
      </div>

      {/* Question input */}
      <div className="bg-white rounded-2xl shadow-card border border-slate-100 p-4">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={2}
          placeholder="Ask a research question about clinical trials…"
          className="w-full text-sm text-slate-800 placeholder-slate-400 bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:bg-white focus:border-transparent resize-none transition-all"
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleAsk();
          }}
        />
        <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-slate-400 mr-0.5">Try:</span>
          {EXAMPLE_QUESTIONS.map((q) => (
            <button key={q} type="button" onClick={() => handleAsk(q)} disabled={running}
              className="text-xs bg-slate-100 hover:bg-brand-50 text-slate-600 hover:text-brand-700 border border-slate-200 hover:border-brand-200 px-2.5 py-1 rounded-full transition-colors text-left disabled:opacity-50">
              {q.length > 52 ? q.slice(0, 49) + "…" : q}
            </button>
          ))}
          <button
            onClick={() => handleAsk()}
            disabled={running || question.trim().length < 3}
            className="ml-auto inline-flex items-center gap-2 px-4 py-2 bg-brand-600 text-white text-sm font-semibold rounded-xl hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-sm shadow-brand-600/30"
          >
            {running ? (
              <>
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Thinking…
              </>
            ) : (
              "Ask agent"
            )}
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-xl bg-rose-50 border border-rose-200 px-4 py-3 text-sm text-rose-700">
          {error}
        </div>
      )}

      {/* Streaming timeline */}
      <div className="space-y-3">
        {items.map(({ event, key }) => {
          switch (event.type) {
            case "sub_questions":
              return <SubQuestionsCard key={key} subs={event.sub_questions} />;
            case "retrieval":
              return <RetrievalCard key={key} round={event.round} results={event.results} total={event.total_unique} />;
            case "analysis":
              return <AnalysisCard key={key} iteration={event.iteration} decision={event.decision}
                reasoning={event.reasoning} newQueries={event.new_queries} />;
            case "answer":
              return <AnswerCard key={key} answer={event.answer} trials={event.trials} />;
            default:
              return null;
          }
        })}
        {/* Optional refinement — search already ran; these narrow the match */}
        {pendingQuestions && !running && (
          <div className="rounded-2xl bg-white border border-amber-200 shadow-card p-5 animate-fade-in">
            <div className="flex items-center gap-2 mb-1">
              <svg className="w-4 h-4 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <p className="text-sm font-semibold text-slate-800">
                Want better matches? Add a few details (optional)
              </p>
            </div>
            <p className="text-xs text-slate-500 mb-3">
              Results above are based on your original question. Answer any of these to refine.
            </p>
            <div className="space-y-3">
              {pendingQuestions.map((q, idx) => (
                <div key={idx}>
                  <label className="block text-sm text-slate-600 mb-1">{q}</label>
                  <input
                    type="text"
                    value={answers[idx] ?? ""}
                    onChange={(e) => setAnswers((a) => ({ ...a, [idx]: e.target.value }))}
                    onKeyDown={(e) => { if (e.key === "Enter") handleSubmitClarifications(); }}
                    placeholder="Your answer…"
                    className="w-full text-sm text-slate-800 placeholder-slate-400 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:bg-white focus:border-transparent transition-all"
                  />
                </div>
              ))}
            </div>
            <div className="mt-4">
              <button
                onClick={handleSubmitClarifications}
                disabled={!Object.values(answers).some((a) => a.trim())}
                className="inline-flex items-center gap-2 px-4 py-2 bg-brand-600 text-white text-sm font-semibold rounded-xl hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-sm shadow-brand-600/30"
              >
                Refine search
              </button>
            </div>
          </div>
        )}

        {running && (
          <div className="flex items-center gap-2 text-sm text-slate-400 px-1">
            <span className="w-1.5 h-1.5 rounded-full bg-brand-400 animate-pulse-slow" />
            agent working…
          </div>
        )}
      </div>
    </div>
  );
}
