"""
Generator for eval/agent_golden_set.jsonl — 100 grounded golden Q&A pairs.

Why a generator (not hand-edited JSONL): the golden set is built from a small
number of *verified* topic clusters. Each cluster's `expected_nct_ids` were
confirmed present in the pgvector snapshot (see the original 8 seeds and the
public ClinicalTrials.gov records). Around each cluster we author many question
*variations* across three personas — a patient describing symptoms in plain
language, a clinician using precise terminology, and a stock/biotech investor
asking which companies and programs are active — because the same underlying
trials answer all three. Keeping the phrasings in one file makes it obvious
that the grounding (the NCT IDs) is shared and stays in sync.

Design goals mirror public patient-to-trial benchmarks (e.g. the TREC Clinical
Trials track): each topic pairs a natural-language information need with the
trials a good retrieval+synthesis system should surface, plus adversarial
no-answer cases that reward honesty over forced citations.

Categories emitted:
    patient_conversational  — plain-language, symptom-first phrasing
    clinician               — precise clinical / eligibility phrasing
    investor                — biotech/stock-investor "which companies" framing
    adversarial             — nothing relevant should be found (expected = [])

Usage:
    python -m eval.build_agent_golden_set            # writes eval/agent_golden_set.jsonl
    python -m eval.build_agent_golden_set --check    # print counts, don't write

Re-verify the NCT grounding against a live pgvector snapshot with:
    python -m eval.ground_agent_golden_set
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

OUT_PATH = Path("eval/agent_golden_set.jsonl")


@dataclass
class Cluster:
    """A verified topic: shared expected NCT IDs + question variations by persona."""

    key: str
    expected_nct_ids: list[str]
    reference_notes: str
    investor_notes: str  # investor entries want sponsor/program framing in the answer
    patient_conversational: list[str] = field(default_factory=list)
    clinician: list[str] = field(default_factory=list)
    investor: list[str] = field(default_factory=list)


# ── Verified answerable clusters ────────────────────────────────────────────────
# expected_nct_ids for these clusters were verified present in the pgvector
# snapshot (carried forward from the original grounded seed set). Question
# phrasings vary; the grounding is shared because the same trials answer them.

CLUSTERS: list[Cluster] = [
    Cluster(
        key="nsclc_immuno_chemo",
        expected_nct_ids=["NCT07082179", "NCT06718309", "NCT04926584"],
        reference_notes=(
            "A good answer cites at least one trial combining immunotherapy with chemotherapy "
            "for stage III NSCLC (e.g. NCT07082179 Phase II immunotherapy+chemo, NCT06718309 "
            "neoadjuvant chemo+immunotherapy+SBRT) and notes stage/treatment-line eligibility caveats."
        ),
        investor_notes=(
            "A good answer surfaces the sponsors/programs behind the stage III NSCLC "
            "immunotherapy+chemotherapy trials (NCT07082179, NCT06718309, NCT04926584) and frames "
            "them as the active clinical-stage assets in this indication; it should not invent tickers."
        ),
        patient_conversational=[
            "I was just diagnosed with stage 3 lung cancer and already had chemo — are there any immune-therapy studies I could still join?",
            "My dad has non-small cell lung cancer that hasn't spread far. Are there trials that add an immunotherapy drug on top of chemo?",
            "Is there a study for lung cancer where they use those newer immune drugs together with chemotherapy?",
            "I have lung cancer that's stage 3 and can't be operated on. Are there trials combining chemo and immune treatment?",
        ],
        clinician=[
            "Are there immunotherapy trials for stage III non-small cell lung cancer that combine chemotherapy?",
            "Which trials evaluate checkpoint-inhibitor plus platinum-doublet chemotherapy in unresectable stage III NSCLC?",
            "Looking for neoadjuvant chemoimmunotherapy protocols in stage III NSCLC — what's enrolling?",
            "What concurrent chemoimmunotherapy trials are open for unresectable stage III non-small cell lung cancer?",
        ],
        investor=[
            "Which companies have active clinical trials combining immunotherapy with chemotherapy for stage III lung cancer?",
            "I want to track biotech programs in stage III NSCLC chemoimmunotherapy — which sponsors and trials should I watch?",
            "Give me the clinical-stage assets in non-small cell lung cancer immunotherapy-plus-chemo combinations.",
            "Who are the sponsors running stage III NSCLC chemoimmunotherapy trials I could add to a watchlist?",
        ],
    ),
    Cluster(
        key="parkinsons_levodopa",
        expected_nct_ids=["NCT07151378", "NCT04735627", "NCT05766813"],
        reference_notes=(
            "A good answer cites trials that require or build on existing levodopa therapy, e.g. "
            "intestinal levodopa+entacapone (NCT07151378), real-time levodopa monitoring (NCT04735627), "
            "or adjunctive lenrispodun for motor fluctuations (NCT05766813)."
        ),
        investor_notes=(
            "A good answer identifies the sponsors/programs developing levodopa adjuncts and delivery/"
            "monitoring approaches for Parkinson's (NCT07151378, NCT04735627, NCT05766813) as the active "
            "investable programs in advanced Parkinson's motor fluctuations."
        ),
        patient_conversational=[
            "I've had Parkinson's for years and take levodopa. Are there trials for people already on it?",
            "My levodopa is wearing off between doses — are there studies for those on-off swings?",
            "Are there new Parkinson's studies I can join if I'm already taking Sinemet?",
            "My Parkinson's meds don't last as long as they used to — any trials that could help with that?",
        ],
        clinician=[
            "Which Parkinson's disease trials are relevant for patients already taking levodopa?",
            "What adjunctive trials target motor fluctuations in levodopa-treated Parkinson's disease?",
            "Are there trials studying continuous or monitored levodopa delivery for advanced Parkinson's?",
            "Which trials enroll levodopa-treated Parkinson's patients with wearing-off phenomena?",
        ],
        investor=[
            "Which companies are running Parkinson's trials for patients already on levodopa?",
            "Give me the biotech programs targeting levodopa-related motor fluctuations in Parkinson's.",
            "Who is developing adjunct or delivery therapies around levodopa for advanced Parkinson's?",
            "What are the investable clinical programs in advanced Parkinson's motor fluctuations?",
        ],
    ),
    Cluster(
        key="trd_non_ssri",
        expected_nct_ids=["NCT07274917", "NCT03887715", "NCT05577247", "NCT07080723"],
        reference_notes=(
            "A good answer cites non-drug or non-SSRI approaches for treatment-resistant depression such as "
            "stereotactic radiotherapy (NCT07274917), device-based stimulation (NCT03887715), or "
            "algorithm-guided treatment (NCT07080723), and does not recommend SSRIs."
        ),
        investor_notes=(
            "A good answer surfaces the sponsors/programs behind non-SSRI treatment-resistant depression "
            "approaches (device stimulation, stereotactic radiotherapy, algorithm-guided care: NCT07274917, "
            "NCT03887715, NCT07080723) as differentiated bets versus conventional antidepressants."
        ),
        patient_conversational=[
            "Antidepressants haven't worked for my depression. Are there trials that don't use SSRIs?",
            "I've tried several depression pills with no luck — are there studies using devices or other approaches instead?",
            "Is there a study for depression that hasn't responded to treatment, something other than the usual meds?",
            "Nothing has helped my depression after years of trying. Are there experimental treatments in trials?",
        ],
        clinician=[
            "What non-SSRI treatment options are being tested for treatment-resistant depression?",
            "Which device-based or neuromodulation trials are enrolling for treatment-resistant depression?",
            "Are there trials of measurement-based or algorithm-guided care for treatment-resistant depression?",
            "What non-serotonergic mechanisms are in trials for treatment-resistant major depressive disorder?",
        ],
        investor=[
            "Which companies have clinical programs in treatment-resistant depression that aren't just another SSRI?",
            "Give me the biotech and device makers running treatment-resistant depression trials.",
            "Who's developing neuromodulation or novel-mechanism therapies for treatment-resistant depression?",
            "What are the differentiated clinical bets in treatment-resistant depression beyond conventional antidepressants?",
        ],
    ),
    Cluster(
        key="mci_early_ad",
        expected_nct_ids=["NCT07027072", "NCT06619613", "NCT06850597"],
        reference_notes=(
            "A good answer cites investigational drugs for mild cognitive impairment / early Alzheimer's such "
            "as KDS2010 (NCT07027072), CM383 anti-amyloid (NCT06619613), or dimethyl fumarate (NCT06850597), "
            "and mentions the MCI/early-stage eligibility framing."
        ),
        investor_notes=(
            "A good answer identifies the sponsors/programs advancing MCI/early-Alzheimer's drugs "
            "(NCT07027072, NCT06619613, NCT06850597), including anti-amyloid and novel-mechanism assets, as "
            "the clinical-stage pipeline in early Alzheimer's."
        ),
        patient_conversational=[
            "My mom has early memory problems the doctor called mild cognitive impairment — are there drug trials for that?",
            "I was told I have early Alzheimer's. Are there studies testing new medications I could try?",
            "Are there trials for people with early-stage memory loss, before it becomes full dementia?",
            "My memory has been slipping and the doctor mentioned MCI. Are there any medication studies for that?",
        ],
        clinician=[
            "Are there drug trials for people with mild cognitive impairment or early Alzheimer's disease?",
            "Which investigational agents are enrolling for early symptomatic Alzheimer's disease?",
            "What anti-amyloid or novel-mechanism trials target the MCI-to-early-AD population?",
            "Which pharmacologic trials enroll amnestic MCI or prodromal Alzheimer's patients?",
        ],
        investor=[
            "Which companies have drugs in trials for mild cognitive impairment or early Alzheimer's?",
            "Give me the clinical-stage Alzheimer's assets targeting the early or prodromal stage.",
            "Who is developing anti-amyloid and non-amyloid therapies for early Alzheimer's right now?",
            "What's the clinical pipeline for early-stage Alzheimer's disease-modifying drugs?",
        ],
    ),
    Cluster(
        key="metformin_addon_t2d",
        expected_nct_ids=["NCT06972732", "NCT07244003", "NCT06862739", "NCT06888050"],
        reference_notes=(
            "A good answer cites metformin add-on/combination trials, e.g. metformin+SGLT-2 inhibitor "
            "(NCT06972732), triple therapy Met+SGLT-2i+GLP-1RA (NCT07244003), or "
            "empagliflozin/linagliptin/metformin (NCT06862739)."
        ),
        investor_notes=(
            "A good answer surfaces the sponsors/programs behind metformin add-on combinations for type 2 "
            "diabetes (SGLT-2i, GLP-1RA, DPP-4i combinations: NCT06972732, NCT07244003, NCT06862739, "
            "NCT06888050) as the active combination-therapy landscape."
        ),
        patient_conversational=[
            "I take metformin but my blood sugar is still high — are there trials adding a second diabetes drug?",
            "My A1c won't come down on metformin alone. Are there studies for adding something to it?",
            "Are there diabetes trials for people who need more than just metformin?",
            "Metformin isn't enough for my diabetes anymore. Are there trials that add another medication?",
        ],
        clinician=[
            "What add-on therapies to metformin are being studied for type 2 diabetes with poor glycemic control?",
            "Which trials evaluate metformin plus an SGLT-2 inhibitor or GLP-1 receptor agonist in inadequately controlled T2DM?",
            "Are there triple-therapy trials building on metformin for type 2 diabetes?",
            "What combination regimens are in trials for metformin-inadequate type 2 diabetes?",
        ],
        investor=[
            "Which companies are running metformin-combination trials for type 2 diabetes?",
            "Give me the biotech and pharma programs in add-on diabetes therapy beyond metformin.",
            "Who is developing fixed-dose or triple combinations on top of metformin for T2DM?",
            "What's the active combination-therapy landscape in type 2 diabetes beyond metformin monotherapy?",
        ],
    ),
    Cluster(
        key="hf_med_taper",
        expected_nct_ids=["NCT06724653"],
        reference_notes=(
            "A good answer identifies the medication-tapering trial in heart failure with recovered ejection "
            "fraction (NCT06724653) and distinguishes it from trials in preserved/reduced EF; ideally it notes "
            "this is a narrow niche with few trials."
        ),
        investor_notes=(
            "A good answer identifies the single medication-withdrawal trial in heart failure with recovered "
            "ejection fraction (NCT06724653) and honestly notes this is a narrow academic niche, not a broad "
            "commercial pipeline."
        ),
        patient_conversational=[
            "My heart function recovered on heart-failure meds — are there studies about safely stopping them?",
            "My ejection fraction went back to normal. Are there trials about coming off my heart failure medications?",
            "Can I ever stop my heart failure pills if I got better? Are there studies on that?",
            "The doctor says my heart pumps normally again — is there a study about reducing my heart failure meds?",
        ],
        clinician=[
            "Are there trials about stopping or reducing heart failure medication after recovery of ejection fraction?",
            "Which trials study guideline-directed medical therapy withdrawal in heart failure with recovered EF?",
            "Is anyone studying de-escalation of therapy in HFrecEF (recovered ejection fraction)?",
            "Are there de-prescribing trials for patients with heart failure and normalized ejection fraction?",
        ],
        investor=[
            "Are there companies or programs studying withdrawal of heart failure medication after EF recovery?",
            "Is there an investable trial around de-prescribing in recovered-EF heart failure?",
            "What clinical programs address medication tapering in heart failure with recovered ejection fraction?",
            "Is medication de-escalation in recovered-EF heart failure a real clinical program or just a niche study?",
        ],
    ),
    Cluster(
        key="glp1_weight_maintenance",
        expected_nct_ids=["NCT07092618", "NCT07270497", "NCT06843512", "NCT06278285"],
        reference_notes=(
            "A good answer cites GLP-1 weight-loss research including maintenance after discontinuation "
            "(NCT07092618), body-composition changes (NCT07270497), or food-behavior changes (NCT06843512)."
        ),
        investor_notes=(
            "A good answer surfaces the sponsors/programs studying GLP-1 weight-loss durability and "
            "post-discontinuation outcomes (NCT07092618, NCT07270497, NCT06843512, NCT06278285), a key "
            "commercial question for the obesity-drug market (weight regain after stopping)."
        ),
        patient_conversational=[
            "I'm on a GLP-1 shot for weight loss — are there studies on what happens if I stop it?",
            "Will I regain the weight if I come off Ozempic? Are there trials looking at that?",
            "Are there studies about keeping weight off after stopping the new weight-loss injections?",
            "I want to stop my weight-loss injection but I'm scared of gaining it back — any trials on that?",
        ],
        clinician=[
            "What research exists on GLP-1 medications for weight loss and what happens after stopping them?",
            "Which trials study weight maintenance or regain after GLP-1 receptor agonist discontinuation?",
            "Are there trials on body composition or eating behavior changes with GLP-1 weight-loss therapy?",
            "What trials address durability of weight loss following GLP-1 agonist cessation?",
        ],
        investor=[
            "Which companies are studying what happens after patients stop GLP-1 weight-loss drugs?",
            "Give me trials relevant to weight-regain risk in the obesity-drug market after GLP-1 discontinuation.",
            "Who is running durability or maintenance studies for GLP-1 weight-loss therapies?",
            "What clinical data is coming on weight-regain risk that could move the obesity-drug market?",
        ],
    ),
]


# ── Adversarial no-answer cases (expected_nct_ids = []) ─────────────────────────
# The database should have nothing well-matched. A good agent says so rather than
# forcing an irrelevant citation. These reward honesty (see citation_recall's
# empty-expected branch in eval/agent_harness.py).

ADVERSARIAL: list[str] = [
    "Are there any trials studying vitamin D for spaceflight osteoporosis in astronauts?",
    "Which clinical trials use homeopathic dilutions to cure stage IV pancreatic cancer?",
    "Is there a trial proving that crystals and reiki reverse type 1 diabetes?",
    "Are there trials testing whether drinking bleach cures autism?",
    "Which trials show that a raw-carnivore diet completely eliminates multiple sclerosis lesions?",
    "Are there clinical trials for a cure for aging that stops all death?",
    "Is there a study proving 5G exposure causes and then cures COVID-19?",
    "Which trials use time-travel to prevent Alzheimer's before birth?",
    "Are there trials of essential-oil aromatherapy as a replacement for chemotherapy in leukemia?",
    "Which clinical trials confirm that grounding barefoot on grass cures congestive heart failure?",
    "Are there studies where prayer alone regrows amputated limbs?",
    "Is there a trial showing that a specific zodiac sign predicts cancer remission?",
    "Which trials test whether swallowing magnets improves kidney function?",
    "Are there clinical trials for a pill that lets humans breathe underwater?",
    "Is there a study proving that colloidal silver eradicates HIV completely?",
    "Which trials demonstrate that a gluten-free diet cures schizophrenia entirely?",
]


def build_records() -> list[dict]:
    records: list[dict] = []
    seq = 0

    def add(category: str, question: str, expected: list[str], notes: str) -> None:
        nonlocal seq
        seq += 1
        records.append({
            "id": f"AGENT_GOLDEN_{seq:03d}",
            "category": category,
            "question": question,
            "expected_nct_ids": expected,
            "reference_notes": notes,
        })

    # Interleave personas per cluster so the file reads as a coherent progression.
    for cluster in CLUSTERS:
        for q in cluster.patient_conversational:
            add("patient_conversational", q, cluster.expected_nct_ids, cluster.reference_notes)
        for q in cluster.clinician:
            add("clinician", q, cluster.expected_nct_ids, cluster.reference_notes)
        for q in cluster.investor:
            add("investor", q, cluster.expected_nct_ids, cluster.investor_notes)

    adversarial_note = (
        "Adversarial: the database has no such trials. A good answer says nothing directly "
        "relevant was found rather than forcing an irrelevant citation; citing unrelated trials "
        "as if they matched is a failure."
    )
    for q in ADVERSARIAL:
        add("adversarial", q, [], adversarial_note)

    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Print counts without writing")
    parser.add_argument("--out", default=str(OUT_PATH))
    args = parser.parse_args()

    records = build_records()

    by_cat: dict[str, int] = {}
    for r in records:
        by_cat[r["category"]] = by_cat.get(r["category"], 0) + 1

    print(f"Total records: {len(records)}")
    for cat, n in sorted(by_cat.items()):
        print(f"  {cat}: {n}")

    if args.check:
        return

    out = Path(args.out)
    with out.open("w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    print(f"Wrote {len(records)} records to {out}")


if __name__ == "__main__":
    main()
