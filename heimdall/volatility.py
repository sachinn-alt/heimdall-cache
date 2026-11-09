import re
import uuid
from typing import List, Tuple
from .models import Claim

PATTERNS = {
    "PRICING": re.compile(
        r"(?:\$|€|£|₹|\b(?:usd|eur|gbp|price|pricing|costs?|fees?|tier|per month|annual|billing|credits?|free tier)\b)",
        re.IGNORECASE,
    ),
    "API_VERSION": re.compile(
        r"\b(?:v\d+(?:\.\d+)*|version\s*\d+|deprecated|deprecation|breaking change|migration|sdk|endpoint|npm\s+i(?:nstall)?|pip\s+install)\b",
        re.IGNORECASE,
    ),
    "LEADERSHIP": re.compile(
        r"\b(?:ceo|cto|cfo|coo|founder|co-founder|president|executive|stepped down|appointed|leadership|head of)\b",
        re.IGNORECASE,
    ),
    "POLICY": re.compile(
        r"\b(?:policy|terms of service|tos|compliance|regulation|eu ai act|gdpr|copyright|license)\b",
        re.IGNORECASE,
    ),
    "TEMPORAL_MARKER": re.compile(
        r"\b(?:current(?:ly)?|as of|recently|latest|newest|released in 202\d|updated in 202\d)\b",
        re.IGNORECASE,
    ),
}

class VolatilityClassifier:
    """
    Decomposes responses into atomic claims and assigns volatility classes
    based on entity types and temporal vulnerability.
    """

    @staticmethod
    def extract_claims(text: str) -> List[Claim]:
        # Split text into sentences / statements
        raw_sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
        claims: List[Claim] = []

        for sentence in raw_sentences:
            s = sentence.strip()
            # Ignore tiny fragments, greetings, formatting lines
            if len(s) < 15 or s.startswith(("#", "-", "*", "`")):
                continue

            entity_type, volatility = VolatilityClassifier.classify_sentence(s)
            
            claims.append(
                Claim(
                    id=str(uuid.uuid4())[:8],
                    claim_text=s,
                    entity_type=entity_type,
                    volatility_level=volatility,
                    freshness_score=100.0,
                    is_stale=False,
                )
            )

        return claims

    @staticmethod
    def classify_sentence(sentence: str) -> Tuple[str, str]:
        matched_types = []
        for etype, pattern in PATTERNS.items():
            if pattern.search(sentence):
                matched_types.append(etype)

        if "PRICING" in matched_types or "API_VERSION" in matched_types or "LEADERSHIP" in matched_types:
            return matched_types[0], "HIGH"
        elif "POLICY" in matched_types or "TEMPORAL_MARKER" in matched_types:
            return matched_types[0], "MODERATE"
        else:
            return "GENERAL", "STATIC"

    @staticmethod
    def determine_max_volatility(claims: List[Claim]) -> str:
        if any(c.volatility_level == "HIGH" for c in claims):
            return "HIGH"
        if any(c.volatility_level == "MODERATE" for c in claims):
            return "MODERATE"
        return "STATIC"

classifier = VolatilityClassifier()
