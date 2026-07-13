import React, { useEffect, useState } from "react";
import { getPassword, setAuthErrorHandler } from "./api";
import LoginScreen from "./components/LoginScreen";
import MonitoringPage from "./components/MonitoringPage";
import AgentPage from "./components/AgentPage";

type Tab = "chat" | "monitoring";

export default function App() {
  const [authed, setAuthed] = useState<boolean>(() => Boolean(getPassword()));
  const [tab, setTab] = useState<Tab>("chat");

  // A 401 from any API call (wrong/expired password) drops back to login
  useEffect(() => {
    setAuthErrorHandler(() => setAuthed(false));
  }, []);

  if (!authed) {
    return <LoginScreen onSuccess={() => setAuthed(true)} />;
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
              {(["chat", "monitoring"] as Tab[]).map((t) => (
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
            Clinical Trial Assistant
          </h1>
          <p className="text-brand-100 text-base max-w-xl leading-relaxed">
            Chat in plain language. A LangGraph agent screens eligibility across
            62,000+ trials, asks a follow-up or two, and narrows to the best matches.
          </p>
        </div>
      </header>

      {/* ── Main content ─────────────────────────────────────────────── */}
      <main className="flex-1 max-w-4xl mx-auto w-full px-4 pb-16 pt-8">
        {tab === "chat" && <AgentPage />}
        {tab === "monitoring" && <MonitoringPage />}
      </main>

      <footer className="border-t border-slate-200 bg-white py-5 text-center text-xs text-slate-400">
        For research purposes only &mdash; always consult your physician before enrolling in a clinical trial.
        <span className="mx-2 text-slate-200">|</span>
        Data from ClinicalTrials.gov
      </footer>
    </div>
  );
}
