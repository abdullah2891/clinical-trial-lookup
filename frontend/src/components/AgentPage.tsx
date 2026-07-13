import React, { useEffect, useRef, useState } from "react";
import { streamAgentSearch } from "../api";
import { AgentEvent, AgentTrial } from "../types";

// Conversational chat window over the LangGraph agentic RAG pipeline.
//
// Flow:
//   • User types a message → agent streams progress ("narrowing it down…").
//   • Agent replies with an answer bubble + cited trial cards.
//   • If the question was broad, the agent also asks a short clarifying
//     question. The user's next message is folded back in as clarifying
//     detail and the same question is re-run for a tighter match.
//   • At any point the user can just ask something new.

const EXAMPLE_PROMPTS = [
  "I have asthma and want to find a study",
  "My dad has stage 3 lung cancer — any immunotherapy trials?",
  "Give me companies with trials for Alzheimer's drugs",
  "I'm on a GLP-1 for weight loss — what happens if I stop?",
];

// ── Message model ────────────────────────────────────────────────────────────
type Trial = AgentTrial;

type ChatMessage =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "agent"; kind: "answer"; text: string; trials: Trial[] }
  | { id: string; role: "agent"; kind: "clarify"; text: string; questions: string[] }
  | { id: string; role: "agent"; kind: "error"; text: string };

let _uid = 0;
const uid = () => `m${++_uid}`;

// Human-friendly progress copy for each streamed graph event.
function statusFor(event: AgentEvent): string | null {
  switch (event.type) {
    case "sub_questions":
      return "Understanding your question…";
    case "retrieval":
      return event.round > 1
        ? "Narrowing it down…"
        : "Searching 62,000+ trials…";
    case "analysis":
      return event.decision === "refine"
        ? "Narrowing it down further…"
        : "Pulling the best matches together…";
    default:
      return null;
  }
}

// ── Sub-components ────────────────────────────────────────────────────────────

function TrialList({ trials }: { trials: Trial[] }) {
  if (trials.length === 0) return null;
  return (
    <div className="mt-3 space-y-2">
      {trials.map((t) => (
        <a
          key={t.nct_id}
          href={t.url}
          target="_blank"
          rel="noopener noreferrer"
          className="block rounded-lg border border-slate-200 hover:border-brand-300 hover:bg-brand-50/50 px-3 py-2 transition-colors"
        >
          <span className="text-[11px] font-mono text-slate-400">{t.nct_id}</span>
          <p className="text-sm text-slate-800 leading-snug">{t.title}</p>
          {t.conditions.length > 0 && (
            <p className="text-[11px] text-slate-400 mt-0.5">{t.conditions.join(" · ")}</p>
          )}
        </a>
      ))}
    </div>
  );
}

function Bubble({ msg }: { msg: ChatMessage }) {
  if (msg.role === "user") {
    return (
      <div className="flex justify-end animate-fade-in">
        <div className="max-w-[80%] rounded-2xl rounded-br-md bg-brand-600 text-white px-4 py-2.5 text-sm leading-relaxed shadow-sm shadow-brand-600/30 whitespace-pre-wrap">
          {msg.text}
        </div>
      </div>
    );
  }

  const isError = msg.kind === "error";
  const isClarify = msg.kind === "clarify";
  return (
    <div className="flex justify-start gap-2 animate-fade-in">
      <div className="w-7 h-7 shrink-0 rounded-full bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center text-white text-xs font-bold mt-0.5">
        AI
      </div>
      <div
        className={`max-w-[85%] rounded-2xl rounded-bl-md px-4 py-3 text-sm leading-relaxed shadow-card ${
          isError
            ? "bg-rose-50 border border-rose-200 text-rose-700"
            : isClarify
            ? "bg-amber-50 border border-amber-200 text-slate-800"
            : "bg-white border border-slate-100 text-slate-800"
        }`}
      >
        <p className="whitespace-pre-wrap">{msg.text}</p>
        {msg.kind === "clarify" && msg.questions.length > 0 && (
          <ul className="mt-2 space-y-1">
            {msg.questions.map((q, i) => (
              <li key={i} className="flex items-start gap-1.5 text-slate-700">
                <span className="text-amber-500 mt-0.5">•</span>
                <span>{q}</span>
              </li>
            ))}
          </ul>
        )}
        {msg.kind === "answer" && <TrialList trials={msg.trials} />}
      </div>
    </div>
  );
}

function WorkingBubble({ status }: { status: string }) {
  return (
    <div className="flex justify-start gap-2 animate-fade-in">
      <div className="w-7 h-7 shrink-0 rounded-full bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center text-white text-xs font-bold mt-0.5">
        AI
      </div>
      <div className="rounded-2xl rounded-bl-md bg-white border border-slate-100 shadow-card px-4 py-3 flex items-center gap-2.5">
        <span className="flex gap-1">
          <span className="w-1.5 h-1.5 rounded-full bg-brand-400 animate-pulse-slow" />
          <span className="w-1.5 h-1.5 rounded-full bg-brand-400 animate-pulse-slow" style={{ animationDelay: "0.2s" }} />
          <span className="w-1.5 h-1.5 rounded-full bg-brand-400 animate-pulse-slow" style={{ animationDelay: "0.4s" }} />
        </span>
        <span className="text-sm text-slate-500">{status}</span>
      </div>
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function AgentPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState<string>("Thinking…");

  // The question currently being refined. When the agent's last turn asked a
  // clarifying question, the next user message is treated as clarifying detail
  // for this question rather than a brand-new search.
  const activeQuestion = useRef<string | null>(null);
  const awaitingClarification = useRef<boolean>(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, running, status]);

  async function send(rawText: string) {
    const text = rawText.trim();
    if (text.length < 2 || running) return;

    // Decide whether this message refines the previous question or starts anew.
    const isClarification = awaitingClarification.current && activeQuestion.current !== null;
    const question = isClarification ? (activeQuestion.current as string) : text;
    const clarifications = isClarification ? text : "";
    if (!isClarification) activeQuestion.current = text;
    awaitingClarification.current = false;

    setMessages((prev) => [...prev, { id: uid(), role: "user", text }]);
    setInput("");
    setRunning(true);
    setStatus(isClarification ? "Narrowing it down…" : "Thinking…");

    // Boxed so the streaming callback's mutations survive TS closure narrowing.
    const box: { answered: boolean; clarify: string[] | null } = { answered: false, clarify: null };

    try {
      await streamAgentSearch(
        question,
        (event) => {
          if (event.type === "clarification") {
            box.clarify = event.questions;
            return;
          }
          if (event.type === "error") {
            setMessages((prev) => [
              ...prev,
              { id: uid(), role: "agent", kind: "error", text: event.detail },
            ]);
            return;
          }
          if (event.type === "answer") {
            box.answered = true;
            setMessages((prev) => [
              ...prev,
              { id: uid(), role: "agent", kind: "answer", text: event.answer, trials: event.trials },
            ]);
            return;
          }
          if (event.type === "done") return;
          const s = statusFor(event);
          if (s) setStatus(s);
        },
        clarifications,
      );

      // After the answer, if the agent flagged the question as broad, ask a
      // short clarifying question conversationally and wait for the reply.
      if (box.clarify && box.clarify.length > 0 && !isClarification) {
        awaitingClarification.current = true;
        const questions = box.clarify;
        setMessages((prev) => [
          ...prev,
          {
            id: uid(),
            role: "agent",
            kind: "clarify",
            text: box.answered
              ? "I found some trials above. To narrow them down to the best matches, could you tell me a bit more?"
              : "Could you tell me a bit more so I can find the best-matched trials?",
            questions,
          },
        ]);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: uid(),
          role: "agent",
          kind: "error",
          text: err instanceof Error ? err.message : "Agent search failed",
        },
      ]);
    } finally {
      setRunning(false);
    }
  }

  function resetChat() {
    setMessages([]);
    activeQuestion.current = null;
    awaitingClarification.current = false;
  }

  const empty = messages.length === 0;

  return (
    <div className="animate-fade-in flex flex-col h-[calc(100vh-13rem)] min-h-[28rem]">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Trial Research Assistant</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Describe symptoms, ask as a clinician, or explore programs as an investor — the
            agent searches 62,000+ trials and refines with you.
          </p>
        </div>
        {!empty && (
          <button
            onClick={resetChat}
            disabled={running}
            className="text-xs text-slate-500 hover:text-slate-800 border border-slate-200 hover:border-slate-300 rounded-full px-3 py-1 transition-colors disabled:opacity-40"
          >
            New chat
          </button>
        )}
      </div>

      {/* ── Message stream ────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto scrollbar-thin bg-slate-50/60 border border-slate-100 rounded-2xl p-4 space-y-4">
        {empty && (
          <div className="h-full flex flex-col items-center justify-center text-center px-4">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center text-white font-bold mb-3">
              AI
            </div>
            <p className="text-slate-600 font-medium">Ask about clinical trials in plain language</p>
            <p className="text-sm text-slate-400 mt-1 max-w-sm">
              I'll search across recruiting trials and ask a follow-up or two to narrow things down.
            </p>
            <div className="mt-5 flex flex-wrap justify-center gap-2 max-w-lg">
              {EXAMPLE_PROMPTS.map((p) => (
                <button
                  key={p}
                  onClick={() => send(p)}
                  className="text-xs bg-white hover:bg-brand-50 text-slate-600 hover:text-brand-700 border border-slate-200 hover:border-brand-200 px-3 py-1.5 rounded-full transition-colors"
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => (
          <Bubble key={m.id} msg={m} />
        ))}
        {running && <WorkingBubble status={status} />}
        <div ref={scrollRef} />
      </div>

      {/* ── Composer ──────────────────────────────────────────────────────── */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="mt-3 flex items-end gap-2"
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          rows={1}
          placeholder={
            awaitingClarification.current
              ? "Answer to narrow it down, or ask something new…"
              : "Message the trial assistant…"
          }
          className="flex-1 resize-none text-sm text-slate-800 placeholder-slate-400 bg-white border border-slate-200 rounded-2xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition-all max-h-32"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(input);
            }
          }}
        />
        <button
          type="submit"
          disabled={running || input.trim().length < 2}
          className="shrink-0 inline-flex items-center justify-center w-11 h-11 bg-brand-600 text-white rounded-2xl hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-sm shadow-brand-600/30"
          aria-label="Send"
        >
          {running ? (
            <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          ) : (
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          )}
        </button>
      </form>
    </div>
  );
}
