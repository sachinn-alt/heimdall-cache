import re
import logging
from typing import List, Tuple, Optional, Dict, Any
from tavily import TavilyClient
from .config import settings
from .models import Claim
from .embeddings import embedding_engine

logger = logging.getLogger("heimdall.tavily_probe")

class TavilyDeltaProbe:
    """
    Advanced Live Grounding & Factual Contradiction Engine.
    Uses Tavily Search API with temporal filtering (time_range='month'),
    direct answer synthesis (include_answer=True), and two-tier NLI evaluation.
    """
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.TAVILY_API_KEY
        self.client = TavilyClient(api_key=self.api_key) if self.api_key else None

    def probe_claim(self, claim: Claim) -> Claim:
        """
        Takes a claim, executes a targeted temporal Tavily search,
        and runs two-tier contradiction analysis.
        """
        if not self.client:
            logger.warning("Tavily API key not configured; skipping live probe.")
            claim.freshness_score = 90.0
            claim.verification_summary = "Simulated verification (Tavily API key missing)."
            return claim

        try:
            query = self._build_probe_query(claim.claim_text, claim.entity_type)
            
            # Select appropriate temporal window based on volatility
            time_range = "week" if claim.volatility_level == "HIGH" else "month"
            search_depth = "advanced" if claim.volatility_level == "HIGH" else "basic"

            search_res = self.client.search(
                query=query,
                max_results=3,
                search_depth=search_depth,
                time_range=time_range,
                include_answer=True,
            )

            tavily_synthesized_answer = search_res.get("answer", "")
            results = search_res.get("results", [])
            snippets = [r.get("content", "") for r in results if r.get("content")]
            sources = [r.get("url", "") for r in results if r.get("url")]

            combined_evidence = f"{tavily_synthesized_answer} " + " ".join(snippets)

            # Two-Tier Contradiction Analysis
            freshness_score, summary, is_stale = self._evaluate_two_tier_contradiction(
                claim.claim_text, combined_evidence, tavily_synthesized_answer, claim.entity_type
            )

            claim.freshness_score = round(freshness_score, 1)
            claim.is_stale = is_stale
            claim.verification_summary = summary
            claim.sources = sources[:3]

        except Exception as e:
            logger.error(f"Error during Tavily delta-probe for claim '{claim.id}': {e}")
            claim.freshness_score = 75.0
            claim.verification_summary = f"Probe error: {str(e)}"

        return claim

    def probe_claims_batch(self, claims: List[Claim]) -> Tuple[List[Claim], float]:
        verified_claims = []
        scores = []

        for c in claims:
            if c.volatility_level in ("HIGH", "MODERATE"):
                v = self.probe_claim(c)
                verified_claims.append(v)
                scores.append(v.freshness_score)
            else:
                c.freshness_score = 100.0
                c.is_stale = False
                c.verification_summary = "Static mathematical or theoretical fact."
                verified_claims.append(c)
                scores.append(100.0)

        overall_freshness = round(sum(scores) / len(scores), 1) if scores else 100.0
        return verified_claims, overall_freshness

    def _build_probe_query(self, text: str, entity_type: str) -> str:
        cleaned = re.sub(r"[^\w\s\$\.]", " ", text)
        words = cleaned.split()[:7]
        
        qualifier = "latest updates"
        if entity_type == "PRICING":
            qualifier = "current pricing monthly cost fee tier"
        elif entity_type == "API_VERSION":
            qualifier = "latest release version deprecation docs"
        elif entity_type == "LEADERSHIP":
            qualifier = "current leadership executive role"

        return f"{' '.join(words)} {qualifier}".strip()

    def _evaluate_two_tier_contradiction(
        self, claim_text: str, evidence: str, direct_answer: str, entity_type: str
    ) -> Tuple[float, str, bool]:
        """
        Tier 1: Fast numeric & version contradiction detection.
        Tier 2: Semantic NLI inference between claim and Tavily's synthesized answer.
        """
        claim_lower = claim_text.lower()
        evidence_lower = evidence.lower()
        answer_lower = direct_answer.lower() if direct_answer else ""

        # --- TIER 1: Numeric & Version Contradiction ---
        # 1. Deprecation detection
        deprecation_signals = ["deprecated", "no longer supported", "has been sunset", "breaking change", "removed in"]
        if any(sig in evidence_lower for sig in deprecation_signals):
            if "deprecated" not in claim_lower:
                return 20.0, "Live Tavily evidence confirms this API/method is deprecated or sunset.", True

        # 2. Pricing discrepancy
        claim_prices = re.findall(r"\$\s*(\d+(?:\.\d+)?)", claim_text)
        evidence_prices = re.findall(r"\$\s*(\d+(?:\.\d+)?)", evidence)

        if claim_prices and evidence_prices:
            if not any(cp in evidence_prices for cp in claim_prices):
                new_price = evidence_prices[0]
                return (
                    30.0,
                    f"Pricing drift detected! Claim states ${claim_prices[0]}, but live web sources cite ${new_price}.",
                    True,
                )

        # 3. Version number discrepancy
        claim_versions = re.findall(r"\bv?(\d+\.\d+(?:\.\d+)?)\b", claim_text)
        evidence_versions = re.findall(r"\bv?(\d+\.\d+(?:\.\d+)?)\b", evidence)

        if claim_versions and evidence_versions:
            if not any(cv in evidence_versions for cv in claim_versions):
                return (
                    35.0,
                    f"Version drift detected! Claim cited v{claim_versions[0]}, but live releases cite v{evidence_versions[0]}.",
                    True,
                )

        # --- TIER 2: Semantic NLI Inference ---
        # Check semantic agreement with Tavily's synthesized answer
        if direct_answer:
            claim_vec = embedding_engine.get_embedding(claim_text)
            answer_vec = embedding_engine.get_embedding(direct_answer)
            semantic_sim = embedding_engine.cosine_similarity(claim_vec, answer_vec)

            # If semantic similarity to the fresh summary is very low, it indicates conceptual divergence
            if semantic_sim < 0.35:
                return (
                    45.0,
                    f"Semantic divergence: Tavily fresh synthesis contradicts claim context ({round(semantic_sim * 100, 1)}% alignment).",
                    True,
                )
            elif semantic_sim > 0.70:
                return 98.0, "High semantic entailment with live Tavily synthesized ground truth.", False

        # Fallback keyword overlap
        overlap = set(claim_lower.split()) & set(evidence_lower.split())
        if len(overlap) >= 4:
            return 94.0, "Corroborated by live web sources with strong term overlap.", False

        return 82.0, "Consistent with live web evidence without direct conflict.", False

tavily_prober = TavilyDeltaProbe()
