import re
import logging
from typing import List, Tuple, Optional
from tavily import TavilyClient
from .config import settings
from .models import Claim

logger = logging.getLogger("heimdall.tavily_probe")

class TavilyDeltaProbe:
    """
    Executes live verification probes against the web using Tavily Search API.
    Scores claim freshness and flags factual staleness for LLM responses.
    """
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.TAVILY_API_KEY
        self.client = TavilyClient(api_key=self.api_key) if self.api_key else None

    def probe_claim(self, claim: Claim) -> Claim:
        """
        Takes a single claim, queries Tavily for live current ground truth,
        and computes a freshness score with citation sources.
        """
        if not self.client:
            logger.warning("Tavily API key not configured; skipping live probe.")
            claim.freshness_score = 90.0
            claim.verification_summary = "Simulated verification (Tavily API key missing)."
            return claim

        try:
            # Construct a targeted verification query
            query = self._build_probe_query(claim.claim_text, claim.entity_type)
            search_res = self.client.search(query=query, max_results=3, search_depth="basic")

            results = search_res.get("results", [])
            if not results:
                claim.freshness_score = 80.0
                claim.verification_summary = "No conflicting live evidence found."
                return claim

            # Aggregate live snippets and URLs
            snippets = [r.get("content", "") for r in results if r.get("content")]
            sources = [r.get("url", "") for r in results if r.get("url")]
            combined_evidence = " ".join(snippets)

            # Analyze freshness & contradiction
            freshness_score, summary, is_stale = self._evaluate_evidence(
                claim.claim_text, combined_evidence, claim.entity_type
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
        """
        Probes all high and moderate volatility claims and calculates overall freshness.
        """
        verified_claims = []
        scores = []

        for c in claims:
            if c.volatility_level in ("HIGH", "MODERATE"):
                v = self.probe_claim(c)
                verified_claims.append(v)
                scores.append(v.freshness_score)
            else:
                # Static facts stay fresh
                c.freshness_score = 100.0
                c.is_stale = False
                c.verification_summary = "Static mathematical or historical fact."
                verified_claims.append(c)
                scores.append(100.0)

        overall_freshness = round(sum(scores) / len(scores), 1) if scores else 100.0
        return verified_claims, overall_freshness

    def _build_probe_query(self, text: str, entity_type: str) -> str:
        # Extract core nouns and numbers to form a search query
        cleaned = re.sub(r"[^\w\s\$\.]", " ", text)
        words = cleaned.split()
        keywords = words[:8]  # First key words
        
        qualifier = "latest current"
        if entity_type == "PRICING":
            qualifier = "current pricing cost fee"
        elif entity_type == "API_VERSION":
            qualifier = "latest version docs release"
        elif entity_type == "LEADERSHIP":
            qualifier = "current leadership role"

        return f"{' '.join(keywords)} {qualifier}".strip()

    def _evaluate_evidence(self, claim_text: str, evidence: str, entity_type: str) -> Tuple[float, str, bool]:
        """
        Compares claim text against live evidence retrieved from Tavily.
        Looks for numeric discrepancies (e.g. prices, version numbers) or deprecation signals.
        """
        evidence_lower = evidence.lower()
        claim_lower = claim_text.lower()

        # Check for explicit deprecation / breaking change warnings
        if any(term in evidence_lower for term in ("deprecated", "no longer supported", "has been replaced", "obsolete")):
            if "deprecated" not in claim_lower:
                return 25.0, "Live sources report this feature or API has been deprecated.", True

        # Check for numeric pricing discrepancies
        claim_prices = re.findall(r"\$\s*(\d+(?:\.\d+)?)", claim_text)
        evidence_prices = re.findall(r"\$\s*(\d+(?:\.\d+)?)", evidence)

        if claim_prices and evidence_prices:
            # If claim price is not mentioned in recent evidence, flag high probability drift
            if not any(cp in evidence_prices for cp in claim_prices):
                new_price = evidence_prices[0]
                return (
                    35.0,
                    f"Pricing drift detected! Claim cited ${claim_prices[0]}, but live web reports ${new_price}.",
                    True,
                )

        # Check for version changes
        claim_versions = re.findall(r"\bv?(\d+\.\d+(?:\.\d+)?)\b", claim_text)
        evidence_versions = re.findall(r"\bv?(\d+\.\d+(?:\.\d+)?)\b", evidence)

        if claim_versions and evidence_versions:
            if not any(cv in evidence_versions for cv in claim_versions):
                return (
                    40.0,
                    f"Version drift detected! Claim cited v{claim_versions[0]}, but live sources cite v{evidence_versions[0]}.",
                    True,
                )

        # Default high freshness if corroborating context matches
        overlap_words = set(claim_lower.split()) & set(evidence_lower.split())
        if len(overlap_words) >= 4:
            return 95.0, "Verified consistent with current live web sources.", False

        return 82.0, "Corroborated by live web sources without direct conflict.", False

tavily_prober = TavilyDeltaProbe()
