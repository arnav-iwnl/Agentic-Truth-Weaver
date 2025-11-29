"""
Agentic truth-assessment model with Hybrid-RAG:
- Uses retrieved Pinecone metadata (titles, sites, categories)
- If evidence is irrelevant → fall back to Gemini’s internal knowledge
- Strict JSON, no hallucinations
- Fact check, narrative divergence, semantic drift, and DTI
"""

from __future__ import annotations
import os
import json
from typing import Any, Dict, List

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "models/gemini-2.5-pro")


# ----------------------------------------------------
# GEMINI CLIENT
# ----------------------------------------------------
def _ensure_configured():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing.")
    genai.configure(api_key=api_key)


# ----------------------------------------------------
# ROBUST JSON PARSER
# ----------------------------------------------------
def _extract_json(raw: str) -> Dict[str, Any]:
    raw = raw.strip()

    # strip code fences
    if raw.startswith("```"):
        raw = raw.strip("`").strip()

    # extract first JSON object
    if "{" in raw and "}" in raw:
        raw = raw[raw.find("{") : raw.rfind("}") + 1]

    try:
        return json.loads(raw)
    except Exception:
        return {"_error": "JSON_PARSE_ERROR", "raw": raw}


def _call_gemini_json(prompt: str) -> Dict[str, Any]:
    _ensure_configured()
    model = genai.GenerativeModel(_MODEL_NAME)
    resp = model.generate_content(prompt)
    text = getattr(resp, "text", "") or ""
    return _extract_json(text)


# ----------------------------------------------------
# SCORING
# ----------------------------------------------------
def _truth_score_1_to_10(v: float) -> int:
    v = max(0.0, min(1.0, float(v)))
    return int(round(1 + v * 9))


# ----------------------------------------------------
# HELPERS
# ----------------------------------------------------
def _summarize_contexts(contexts: List[Dict[str, Any]]) -> str:
    """
    Converts Pinecone metadata-only contexts into a compact summary.
    """
    lines = []
    for i, ctx in enumerate(contexts, start=1):
        m = ctx.get("metadata", {})
        title = m.get("title", "n/a")
        site = m.get("site", "unknown")
        category = m.get("category") or "unknown"
        timestamp = m.get("timestamp", "")
        url = m.get("url", "")

        parts = [f"DOC {i}", f"site={site}", f"category={category}"]
        if timestamp:
            parts.append(f"timestamp={timestamp}")
        if title:
            parts.append(f"title={title}")
        if url:
            parts.append(f"url={url}")

        lines.append(" | ".join(parts))

    return "\n".join(lines)


# ----------------------------------------------------
# FACT-CHECK ANALYSIS (Hybrid RAG)
# ----------------------------------------------------
def _fact_check_analysis(query: str, contexts: List[Dict[str, Any]]) -> Dict[str, Any]:
    context_summary = _summarize_contexts(contexts)

    prompt = f"""
You are an elite fact-checking AI.

You receive:
1. A user claim.
2. Retrieved evidence from a news vector database.
   • Evidence may be irrelevant or mismatched.
3. If evidence is relevant → rely primarily on it.
4. If evidence is irrelevant → fall back to your own general world knowledge.
5. NEVER hallucinate — if unsure, mark as UNCERTAIN.

USER QUERY:
\"\"\"{query}\"\"\"

RETRIEVED EVIDENCE (metadata only):
{context_summary}

TASKS:
1. Detect if retrieved evidence is relevant to the claim.
2. Extract the main factual claim implied by the query.
3. If relevant evidence exists:
     - Compare the claim to the evidence.
     - Determine if it is supported or contradicted.
4. If evidence is irrelevant:
     - State irrelevance.
     - Fall back to general knowledge to evaluate the claim.
5. Produce:
     - verdict: FACT / MYTH / MIXED / UNCERTAIN
     - truth_likelihood: 0–1
     - short_answer: very brief factual reply
     - reasoning: explain relevance & logic
     - supporting_docs: which DOC indices were used (empty if irrelevant)

STRICT JSON ONLY:
{{
  "relevance": "RELEVANT|IRRELEVANT",
  "claim_extracted": "",
  "verdict": "FACT|MYTH|MIXED|UNCERTAIN",
  "truth_likelihood": 0.0,
  "short_answer": "",
  "reasoning": "",
  "supporting_docs": []
}}
"""

    data = _call_gemini_json(prompt)

    verdict = data.get("verdict", "UNCERTAIN")
    likelihood = float(data.get("truth_likelihood", 0.5))
    score10 = _truth_score_1_to_10(likelihood)

    return {
        "verdict": verdict,
        "truth_likelihood": likelihood,
        "truth_score_1_to_10": score10,
        "short_answer": data.get("short_answer", ""),
        "reasoning": data.get("reasoning", ""),
        "supporting_docs": data.get("supporting_docs", []),
        "relevance": data.get("relevance", "UNKNOWN"),
    }


# ----------------------------------------------------
# NARRATIVE DIVERGENCE ANALYSIS
# ----------------------------------------------------
def _narrative_divergence_analysis(query: str, contexts: List[Dict[str, Any]]) -> Dict[str, Any]:
    context_summary = _summarize_contexts(contexts)

    prompt = f"""
You measure narrative divergence between USER TEXT and factual evidence.

USER TEXT:
\"\"\"{query}\"\"\"

EVIDENCE (metadata only):
{context_summary}

TASKS:
1. Infer a factual baseline ONLY from context metadata.
2. Compare user tone vs. evidence tone.
3. Identify exaggeration, fear, urgency, or sensationalism.
4. Even if evidence is irrelevant, still evaluate the tone divergence.

STRICT JSON:
{{
  "baseline_summary": "",
  "divergence_level": "LOW|MEDIUM|HIGH",
  "divergence_score_1_to_10": 1,
  "emotional_tone": [],
  "loaded_phrases": [
    {{
      "phrase": "",
      "category": "",
      "explanation": ""
    }}
  ]
}}
"""

    data = _call_gemini_json(prompt)

    level = data.get("divergence_level", "LOW")
    try:
        score = int(data.get("divergence_score_1_to_10", 1))
    except Exception:
        score = 1
    score = max(1, min(10, score))

    return {
        "baseline_summary": data.get("baseline_summary", ""),
        "divergence_level": level,
        "divergence_score_1_to_10": score,
        "emotional_tone": data.get("emotional_tone", []),
        "loaded_phrases": data.get("loaded_phrases", []),
    }


# ----------------------------------------------------
# SEMANTIC DRIFT ANALYSIS
# ----------------------------------------------------
def _semantic_drift_analysis(query: str, contexts: List[Dict[str, Any]]) -> Dict[str, Any]:
    variants = []
    for ctx in contexts:
        m = ctx.get("metadata", {})
        title = m.get("title")
        if title:
            variants.append({"site": m.get("site", "unknown"), "title": title})

    prompt = f"""
You detect SEMANTIC DRIFT between USER QUERY and retrieved news titles.

USER QUERY:
\"\"\"{query}\"\"\"

VARIANT TITLES:
{json.dumps(variants, ensure_ascii=False)}

TASKS:
1. Detect the language of each title.
2. Translate each to English.
3. Compare meaning against USER QUERY.
4. Classify drift as:
   PRESERVED / WEAKENED / STRENGTHENED / ALTERED
5. Assign drift score 1–10.
6. Identify phrases causing drift.

STRICT JSON:
{{
  "overall_drift_score_1_to_10": 1,
  "overall_drift_level": "LOW|MEDIUM|HIGH",
  "per_variant": []
}}
"""

    data = _call_gemini_json(prompt)

    try:
        overall_score = int(data.get("overall_drift_score_1_to_10", 1))
    except Exception:
        overall_score = 1
    overall_score = max(1, min(10, overall_score))

    return {
        "overall_drift_score_1_to_10": overall_score,
        "overall_drift_level": data.get("overall_drift_level", "LOW"),
        "per_variant": data.get("per_variant", []),
    }


# ----------------------------------------------------
# DYNAMIC TRUST INDEX
# ----------------------------------------------------
def _compute_dti_for_contexts(contexts: List[Dict[str, Any]]):
    base_reputation = {
        "the_hindu": 9,
        "aaj_tak": 6,
    }

    site_scores = {}
    for ctx in contexts:
        m = ctx.get("metadata", {})
        site = m.get("site", "unknown")
        prior = base_reputation.get(site, 5)
        site_scores.setdefault(site, []).append(prior)

    output_sources = []
    for site, scores in site_scores.items():
        avg = sum(scores) / len(scores)
        score = max(1, min(10, int(round(avg))))

        label = (
            "High trust" if score >= 8
            else "Moderate trust" if score >= 5
            else "Low trust / high risk"
        )

        output_sources.append({
            "site": site,
            "dti_score_1_to_10": score,
            "dti_label": label,
        })

    return {"sources": output_sources}


# ----------------------------------------------------
# MAIN ENTRYPOINT
# ----------------------------------------------------
def analyze_query(query: str, contexts: List[Dict[str, Any]]) -> Dict[str, Any]:
    fact_check = _fact_check_analysis(query, contexts)
    narrative = _narrative_divergence_analysis(query, contexts)
    drift = _semantic_drift_analysis(query, contexts)
    dti = _compute_dti_for_contexts(contexts)

    verdict = fact_check["verdict"].upper()
    score = fact_check["truth_score_1_to_10"]

    if verdict == "FACT" and score >= 7:
        color = "green"
    elif verdict == "MYTH" and score >= 7:
        color = "red"
    else:
        color = "yellow"

    answer = (
        fact_check.get("short_answer")
        or fact_check.get("reasoning")
        or ""
    )

    return {
        "query": query,
        "contexts": contexts,
        "answer": answer,
        "color": color,
        "fact_check": fact_check,
        "narrative_divergence": narrative,
        "semantic_drift": drift,
        "dynamic_trust_index": dti,
    }
