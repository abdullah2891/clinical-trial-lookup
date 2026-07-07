"""
Agentic RAG over the clinical-trials vector store, orchestrated with LangGraph.

Graph (mirrors the whiteboard architecture):

    user question
      → decompose   (LLM splits into 2-4 sub-questions)
      → retrieve    (pgvector ANN per pending query, merged by nct_id)
      → analyze     (LLM: enough evidence? ambiguous? need tighter/different queries?)
          ├─ refine → retrieve   (new queries, max MAX_ITERATIONS rounds)
          └─ answer → answer     (LLM synthesizes final answer citing trials)
      → END

Every node completion is streamed to the caller as an event dict, which the
API layer forwards to the UI as Server-Sent Events. LangGraph runs are traced
to LangSmith automatically when LANGCHAIN_API_KEY is set.

Dependencies: langgraph, openai, etl.embedder (pgvector retrieval).

Usage:
    agent = AgenticRAG()
    async for event in agent.stream("Are there immunotherapy trials for stage III NSCLC?"):
        print(event)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Annotated, AsyncGenerator, TypedDict

from langgraph.graph import END, StateGraph
from openai import AsyncOpenAI

from etl.embedder import TrialEmbedder

logger = logging.getLogger(__name__)

AGENT_MODEL = os.getenv("AGENT_MODEL", "gpt-4o-mini")
MAX_ITERATIONS = 3
TOP_K_PER_QUERY = 8
MAX_TRIALS_FOR_ANALYSIS = 24
MAX_CLARIFYING_QUESTIONS = 3

TRIAGE_PROMPT = """You are a clinical research assistant. Before searching a database of \
clinical trials, decide whether the user's question is specific enough to find well-matched trials.

A question is SPECIFIC enough if it names a condition plus at least one meaningful narrowing \
detail (e.g. disease subtype/stage, patient age, prior treatments, biomarkers, or a clear \
research angle).

A question is AMBIGUOUS if it is so broad that retrieval would return scattered, poorly-matched \
trials (e.g. "trials for cancer", "help me find a study", "diabetes trials").

If ambiguous, ask 1-3 short, high-value clarifying questions that would most improve trial \
matching (condition specifics, stage, age, prior treatment, key eligibility factors). Do NOT ask \
more than needed; prefer the single most useful question.

User question: {question}

Respond with ONLY a JSON object:
{{"specific_enough": true or false, "clarifying_questions": ["...", "..."]}}"""

DECOMPOSE_PROMPT = """You are a clinical research assistant. Split the user's question about \
clinical trials into 2-4 focused sub-questions suitable for semantic search over a database \
of trial descriptions (title, conditions, eligibility criteria).

User question: {question}

Respond with ONLY a JSON object: {{"sub_questions": ["...", "..."]}}"""

ANALYZE_PROMPT = """You are a clinical research assistant deciding whether retrieved trials \
answer the user's question.

User question: {question}

Retrieved trials so far (round {iteration} of {max_iterations}):
{trial_summaries}

Decide:
- "answer" if the trials above are sufficient to answer the question.
- "refine" if the evidence is ambiguous or off-target and you need tighter or \
different-direction search queries. Provide 1-3 new queries that are MORE SPECIFIC or \
explore a DIFFERENT angle than previous queries: {previous_queries}

Respond with ONLY a JSON object:
{{"decision": "answer" or "refine", "reasoning": "one or two sentences", "new_queries": ["..."]}}"""

ANSWER_PROMPT = """You are a clinical research assistant. Answer the user's question using ONLY \
the retrieved trials below. Be concise (3-6 sentences), mention specific trials by NCT ID where \
relevant, and note important eligibility caveats. If the trials don't fully answer the question, \
say what's missing.

User question: {question}

Retrieved trials:
{trial_summaries}

Respond with ONLY a JSON object:
{{"answer": "...", "relevant_nct_ids": ["NCT...", "..."]}}"""


def _merge_trials(existing: dict, new: dict) -> dict:
    """Reducer: accumulate retrieved trials across rounds, keyed by nct_id."""
    merged = dict(existing)
    merged.update(new)
    return merged


class AgentState(TypedDict):
    question: str
    clarifications: str
    effective_question: str
    allow_clarification: bool
    route: str
    needs_clarification: bool
    clarifying_questions: list[str]
    sub_questions: list[str]
    pending_queries: list[str]
    all_queries: list[str]
    trials: Annotated[dict, _merge_trials]
    retrieval_log: list[dict]
    iteration: int
    decision: str
    reasoning: str
    answer: str
    relevant_nct_ids: list[str]


# Sentinel from the UI's "Search anyway" button: proceed past triage without
# adding anything to the query.
SKIP_CLARIFICATION = "skip"


def _compose_question(question: str, clarifications: str) -> str:
    """Fold the user's clarifying answers into the effective search question."""
    clar = (clarifications or "").strip()
    if not clar or clar.lower() == SKIP_CLARIFICATION:
        return question
    return f"{question}\n\nAdditional patient details: {clar}"


def _summarize_trials(trials: dict, limit: int = MAX_TRIALS_FOR_ANALYSIS) -> str:
    """Compact, LLM-friendly digest of retrieved trials."""
    lines = []
    ranked = sorted(trials.values(), key=lambda t: -t.get("similarity", 0.0))[:limit]
    for t in ranked:
        conditions = ", ".join(t.get("conditions") or [])[:100]
        criteria = (t.get("eligibility_summary") or "")[:200].replace("\n", " ")
        lines.append(f"- {t['nct_id']} | {t['title'][:110]} | conditions: {conditions} | criteria: {criteria}")
    return "\n".join(lines) if lines else "(none)"


class AgenticRAG:
    """LangGraph-orchestrated multi-query retrieval agent over pgvector."""

    def __init__(self) -> None:
        self._llm = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
        self._embedder = TrialEmbedder()
        self._graph = self._build_graph()

    # ── LLM helper ──────────────────────────────────────────────────────────────

    async def _llm_json(self, prompt: str) -> dict:
        resp = await self._llm.chat.completions.create(
            model=AGENT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=600,
            temperature=0.2,
        )
        try:
            return json.loads(resp.choices[0].message.content or "{}")
        except json.JSONDecodeError:
            logger.warning("Agent LLM returned invalid JSON")
            return {}

    # ── Graph nodes ─────────────────────────────────────────────────────────────

    async def _triage(self, state: AgentState) -> dict:
        """Entry gate: ask clarifying questions when the query is too broad."""
        effective = _compose_question(state["question"], state["clarifications"])

        # Skip clarification if disabled (evals), or already answered by the user.
        if not state["allow_clarification"] or state["clarifications"].strip():
            return {"route": "proceed", "effective_question": effective}

        raw = await self._llm_json(TRIAGE_PROMPT.format(question=state["question"]))
        questions = [str(q) for q in raw.get("clarifying_questions", [])][:MAX_CLARIFYING_QUESTIONS]
        if raw.get("specific_enough", True) or not questions:
            return {"route": "proceed", "effective_question": effective}
        return {
            "route": "clarify",
            "needs_clarification": True,
            "clarifying_questions": questions,
            "effective_question": effective,
        }

    async def _decompose(self, state: AgentState) -> dict:
        raw = await self._llm_json(DECOMPOSE_PROMPT.format(question=state["effective_question"]))
        subs = [str(q) for q in raw.get("sub_questions", [])][:4] or [state["effective_question"]]
        return {"sub_questions": subs, "pending_queries": subs, "all_queries": subs}

    async def _retrieve(self, state: AgentState) -> dict:
        new_trials: dict = {}
        log = []
        for query in state["pending_queries"]:
            try:
                rows = await self._embedder.search_similar(query, top_k=TOP_K_PER_QUERY)
            except Exception as exc:
                logger.warning("Retrieval failed for '%s': %s", query, exc)
                rows = []
            for row in rows:
                row["similarity"] = float(row.get("similarity", 0.0))
                new_trials[row["nct_id"]] = row
            log.append({
                "query": query,
                "count": len(rows),
                "top": [
                    {"nct_id": r["nct_id"], "title": r["title"], "similarity": round(float(r["similarity"]), 3)}
                    for r in rows[:3]
                ],
            })
        return {"trials": new_trials, "retrieval_log": log}

    async def _analyze(self, state: AgentState) -> dict:
        iteration = state["iteration"] + 1
        raw = await self._llm_json(ANALYZE_PROMPT.format(
            question=state["effective_question"],
            iteration=iteration,
            max_iterations=MAX_ITERATIONS,
            trial_summaries=_summarize_trials(state["trials"]),
            previous_queries=json.dumps(state["all_queries"]),
        ))
        decision = raw.get("decision", "answer")
        seen = {q.strip().lower() for q in state["all_queries"]}
        new_queries = [
            str(q) for q in raw.get("new_queries", [])
            if str(q).strip().lower() not in seen
        ][:3]
        if decision == "refine" and (iteration >= MAX_ITERATIONS or not new_queries):
            decision = "answer"  # budget exhausted or no genuinely new queries
        return {
            "iteration": iteration,
            "decision": decision,
            "reasoning": str(raw.get("reasoning", "")),
            "pending_queries": new_queries if decision == "refine" else [],
            "all_queries": state["all_queries"] + (new_queries if decision == "refine" else []),
        }

    async def _answer(self, state: AgentState) -> dict:
        raw = await self._llm_json(ANSWER_PROMPT.format(
            question=state["effective_question"],
            trial_summaries=_summarize_trials(state["trials"]),
        ))
        return {
            "answer": str(raw.get("answer", "I could not synthesize an answer from the retrieved trials.")),
            "relevant_nct_ids": [str(n) for n in raw.get("relevant_nct_ids", [])],
        }

    # ── Graph wiring ────────────────────────────────────────────────────────────

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("triage", self._triage)
        graph.add_node("decompose", self._decompose)
        graph.add_node("retrieve", self._retrieve)
        graph.add_node("analyze", self._analyze)
        graph.add_node("answer", self._answer)

        graph.set_entry_point("triage")
        graph.add_conditional_edges(
            "triage",
            lambda s: s["route"],
            {"clarify": END, "proceed": "decompose"},
        )
        graph.add_edge("decompose", "retrieve")
        graph.add_edge("retrieve", "analyze")
        graph.add_conditional_edges(
            "analyze",
            lambda s: s["decision"],
            {"refine": "retrieve", "answer": "answer"},
        )
        graph.add_edge("answer", END)
        return graph.compile()

    @staticmethod
    def _initial_state(question: str, clarifications: str, allow_clarification: bool) -> "AgentState":
        return {
            "question": question,
            "clarifications": clarifications,
            "effective_question": question,
            "allow_clarification": allow_clarification,
            "route": "",
            "needs_clarification": False,
            "clarifying_questions": [],
            "sub_questions": [],
            "pending_queries": [],
            "all_queries": [],
            "trials": {},
            "retrieval_log": [],
            "iteration": 0,
            "decision": "",
            "reasoning": "",
            "answer": "",
            "relevant_nct_ids": [],
        }

    # ── Public non-streaming API (used by the eval harness) ────────────────────

    async def run(self, question: str, clarifications: str = "") -> dict:
        """Run the full graph and return the final state summary. Evals never
        clarify (allow_clarification=False) so the agent always answers."""
        final = await self._graph.ainvoke(
            self._initial_state(question, clarifications, allow_clarification=False)
        )
        return {
            "answer": final["answer"],
            "relevant_nct_ids": final["relevant_nct_ids"],
            "retrieved_nct_ids": sorted(final["trials"].keys()),
            "sub_questions": final["sub_questions"],
            "iterations": final["iteration"],
        }

    # ── Public streaming API ────────────────────────────────────────────────────

    async def stream(self, question: str, clarifications: str = "") -> AsyncGenerator[dict, None]:
        """Yield UI-facing events as each graph node completes."""
        initial = self._initial_state(question, clarifications, allow_clarification=True)
        trials_seen: dict = {}
        round_no = 0

        async for update in self._graph.astream(initial, stream_mode="updates"):
            for node, out in update.items():
                if node == "triage" and out.get("needs_clarification"):
                    yield {"type": "clarification", "questions": out["clarifying_questions"]}
                elif node == "decompose":
                    yield {"type": "sub_questions", "sub_questions": out["sub_questions"]}
                elif node == "retrieve":
                    round_no += 1
                    trials_seen.update(out.get("trials", {}))
                    yield {
                        "type": "retrieval",
                        "round": round_no,
                        "results": out.get("retrieval_log", []),
                        "total_unique": len(trials_seen),
                    }
                elif node == "analyze":
                    yield {
                        "type": "analysis",
                        "iteration": out["iteration"],
                        "decision": out["decision"],
                        "reasoning": out["reasoning"],
                        "new_queries": out.get("pending_queries", []),
                    }
                elif node == "answer":
                    cited = [
                        {
                            "nct_id": t["nct_id"],
                            "title": t["title"],
                            "url": t.get("url") or f"https://clinicaltrials.gov/study/{t['nct_id']}",
                            "conditions": (t.get("conditions") or [])[:4],
                            "similarity": round(float(t.get("similarity", 0.0)), 3),
                        }
                        for nct_id, t in trials_seen.items()
                        if nct_id in set(out.get("relevant_nct_ids", []))
                    ]
                    yield {"type": "answer", "answer": out["answer"], "trials": cited}
        yield {"type": "done"}
