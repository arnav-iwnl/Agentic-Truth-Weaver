"""Agentic truth-assessment model built on top of Gemini and Pinecone RAG.

This module takes a user query + retrieved contexts and returns a rich
fact-checking payload including:
  - fact/myth classification
  - 1–10 truth likelihood score
  - narrative divergence analysis
  - semantic drift analysis
  - dynamic trust index (DTI) per source

Gemini API key must be provided via the GEMINI_API_KEY environment variable.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import google.generativeai as genai


_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "models/gemini-2.5-pro")


def _ensure_configured() -> None:
    """Configure the Gemini client once.

    Safe to call multiple times.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY environment variable is required to use the agentic model."
        )
    genai.configure(api_key=api_key)


def _build_context_summary(contexts: List[Dict[str, Any]]) -> str:
    """Turn Pinecone matches into a compact, LLM-friendly summary string."""
    lines: List[str] = []
    for i, ctx in enumerate(contexts, start=1):
        meta = ctx.get("metadata", {}) or {}
        title = meta.get("title", "")
        site = meta.get("site", "unknown")
        category = meta.get("category") or meta.get("section") or "unknown"
        url = meta.get("url", "")
        ts = meta.get("timestamp", "")
        parts = [
            f"DOC {i}",
            f"site={site}",
            f"category={category}",
        ]
        if ts:
            parts.append(f"timestamp={ts}")
        if title:
            parts.append(f"title={title}")
        if url:
            parts.append(f"url={url}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def _call_gemini_json(prompt: str) -> Dict[str, Any]:
    """Call Gemini and parse a strict-JSON response.

    On parsing failure, returns a minimal error payload instead of raising.
    """
    _ensure_configured()
    model = genai.GenerativeModel(_MODEL_NAME)
    resp = model.generate_content(prompt)
    text = (resp.text or "").strip()
    # Try to locate a JSON object in the response.
    try:
        # Some models may wrap JSON in markdown fences; strip common wrappers.
        if text.startswith("```"):
            # Remove first and last fenced code block markers.
            text = text.strip("`")
            # In worst case, just find the first "{" and last "}".
        if "{" in text and "}" in text:
            start = text.find("{")
            end = text.rfind("}") + 1
            text = text[start:end]
        return json.loads(text)
    except Exception:
        return {"_error": "Failed to parse Gemini JSON response", "raw": text}


def _truth_score_1_to_10(truth_likelihood: float) -> int:
    """Map [0.0, 1.0] truth likelihood to integer 1–10.

    0.0 -> 1 (definitely myth), 1.0 -> 10 (definitely fact).
    """
    tl = max(0.0, min(1.0, float(truth_likelihood)))
    return int(round(1 + tl * 9))


def _fact_check_analysis(query: str, contexts: List[Dict[str, Any]]) -> Dict[str, Any]:
    context_summary = _build_context_summary(contexts)
    prompt = f'''
You are a rigorous fact-checking AI working with a trusted-news retrieval system.

User query / claim:
"""{query}"""

Retrieved evidence (each DOC is from a trusted or semi-trusted news source):
{context_summary}

Tasks:
1. Decide whether the *main claim implied by the query* is overall FACT, MYTH, MIXED, or UNCERTAIN.
2. Provide a continuous truth_likelihood in [0, 1], where:
   - 0   = definitely false / myth
   - 0.5 = unclear or mixed
   - 1   = definitely true / fact
3. Provide a short, user-facing answer summarizing the factual situation.
4. Cite which DOC indices (e.g., 1, 3) most strongly support your decision.

Respond in STRICT JSON (no extra text):
{
  "verdict": "FACT|MYTH|MIXED|UNCERTAIN",
  "truth_likelihood": 0.0,
  "short_answer": "one or two sentence summary for end users",
  "reasoning": "brief technical reasoning for power users",
  "supporting_docs": [1]
}
'''
    data = _call_gemini_json(prompt)

    verdict = data.get("verdict", "UNCERTAIN")
    truth_likelihood = float(data.get("truth_likelihood", 0.5) or 0.5)
    score_1_to_10 = _truth_score_1_to_10(truth_likelihood)

    return {
        "verdict": verdict,
        "truth_likelihood": truth_likelihood,
        "truth_score_1_to_10": score_1_to_10,
        "short_answer": data.get("short_answer", ""),
        "reasoning": data.get("reasoning", ""),
        "supporting_docs": data.get("supporting_docs", []),
    }


def _narrative_divergence_analysis(query: str, contexts: List[Dict[str, Any]]) -> Dict[str, Any]:
    context_summary = _build_context_summary(contexts)
    prompt = f'''
You are a media analyst detecting narrative spin and emotional manipulation.

User text (what the user is asking or claiming):
"""{query}"""

Trusted-source context (titles, sites, and metadata only):
{context_summary}

Steps:
1. Infer a neutral, factual baseline about the topic using ONLY the context summary
   (treat these as calm, neutral news-style descriptions).
2. Compare the emotional tone, loaded language, and framing of the USER TEXT
   against that neutral baseline.
3. Identify any signs of fear-mongering, anger-incitement, exaggerated urgency,
   or clickbait-style sensationalism.

Output STRICT JSON:
{
  "baseline_summary": "neutral baseline summary based on context docs",
  "divergence_level": "LOW|MEDIUM|HIGH",
  "divergence_score_1_to_10": 1,
  "emotional_tone": ["fear", "anger"],
  "loaded_phrases": [
    {
      "phrase": "string",
      "category": "fear|anger|urgency|sensationalism",
      "explanation": "why it is manipulative or divergent"
    }
  ]
}
'''
    data = _call_gemini_json(prompt)

    level = data.get("divergence_level", "LOW")
    score_raw = data.get("divergence_score_1_to_10", 1)
    try:
        score = int(score_raw)
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


def _semantic_drift_analysis(query: str, contexts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Detect potential semantic drift across languages or outlets.

    We only have metadata (titles, sites). We treat each context title as a
    possible language- or framing-variant of the same underlying topic.
    """
    variants: List[Dict[str, Any]] = []
    for ctx in contexts:
        meta = ctx.get("metadata", {}) or {}
        title = meta.get("title")
        if not title:
            continue
        site = meta.get("site", "unknown")
        # Best-effort language guess based on site or script is delegated to Gemini.
        variants.append({
            "site": site,
            "title": title,
        })

    prompt = f'''
You are a multilingual fact-checking assistant that detects SEMANTIC DRIFT.

User query (original text):
"""{query}"""

Below are news titles from various outlets that are presumably about a
similar topic. Some may be in different languages or use different framing.

VARIANTS:
{json.dumps(variants, ensure_ascii=False)}

Tasks:
1. For each variant title, infer which language it is in and translate it
   into English.
2. Compare the meaning of each variant against the main intent of the
   USER QUERY. Decide if the meaning is:
   - "PRESERVED" (no meaningful change)
   - "WEAKENED" (downplaying danger/impact)
   - "STRENGTHENED" (exaggerating danger/impact)
   - "ALTERED" (introduces a different claim)
3. Assign a drift_score_1_to_10, where:
   - 1  = no drift at all
   - 5  = noticeable but moderate drift
   - 10 = severe distortion of meaning
4. Highlight specific words/phrases in the original variant that cause drift.

Output STRICT JSON:
{
  "overall_drift_score_1_to_10": 1,
  "overall_drift_level": "LOW|MEDIUM|HIGH",
  "per_variant": [
    {
      "site": "string",
      "original_title": "string",
      "language": "hi|en|...",
      "title_en": "translated title in English",
      "drift_type": "PRESERVED|WEAKENED|STRENGTHENED|ALTERED",
      "drift_score_1_to_10": 1,
      "drift_phrases": [
        {
          "original_phrase": "string",
          "translated_phrase_en": "string",
          "explanation": "how it changes meaning"
        }
      ]
    }
  ]
}
'''
    data = _call_gemini_json(prompt)

    overall_score = data.get("overall_drift_score_1_to_10", 1)
    try:
        overall_score = int(overall_score)
    except Exception:
        overall_score = 1
    overall_score = max(1, min(10, overall_score))

    level = data.get("overall_drift_level", "LOW")

    return {
        "overall_drift_score_1_to_10": overall_score,
        "overall_drift_level": level,
        "per_variant": data.get("per_variant", []),
    }


def _compute_dti_for_contexts(contexts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute a simple Dynamic Trust Index (1–10) per source.

    This is a placeholder scoring function based on static priors and can be
    extended later with a database-backed history of myths/corrections.
    """
    # Static priors; these could be loaded from config or a DB.
    base_reputation: Dict[str, int] = {
        # Example priors; tune as needed.
        "the_hindu": 9,
        "aaj_tak": 6,
    }

    site_scores: Dict[str, List[int]] = {}
    for ctx in contexts:
        meta = ctx.get("metadata", {}) or {}
        site = meta.get("site", "unknown")
        if site not in site_scores:
            # Default mid-level trust if unknown.
            site_scores[site] = []
        prior = base_reputation.get(site, 5)
        site_scores[site].append(prior)

    output_sources: List[Dict[str, Any]] = []
    for site, scores in site_scores.items():
        avg = sum(scores) / max(1, len(scores))
        score_int = max(1, min(10, int(round(avg))))
        if score_int >= 8:
            label = "High trust"
        elif score_int >= 5:
            label = "Moderate trust"
        else:
            label = "Low trust / high risk"
        output_sources.append(
            {
                "site": site,
                "dti_score_1_to_10": score_int,
                "dti_label": label,
            }
        )

    return {"sources": output_sources}


def analyze_query(query: str, contexts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Main entrypoint used by the API layer.

    Takes a raw user query and already-retrieved contexts and returns
    a rich analytical payload.
    """
    fact_check = _fact_check_analysis(query, contexts)
    narrative = _narrative_divergence_analysis(query, contexts)
    drift = _semantic_drift_analysis(query, contexts)
    dti = _compute_dti_for_contexts(contexts)

    # Decide color at the top level based on verdict and truth score.
    verdict = fact_check["verdict"].upper()
    score = fact_check["truth_score_1_to_10"]
    if verdict == "FACT" and score >= 7:
        color = "green"
    elif verdict == "MYTH" and score >= 7:
        color = "red"
    else:
        color = "yellow"  # mixed/uncertain or low-confidence

    # Final, user-facing answer comes from the fact-check short summary.
    answer = fact_check.get("short_answer") or fact_check.get("reasoning") or ""

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
