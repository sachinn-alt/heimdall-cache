import time
import uuid
import logging
from typing import Dict, List, Optional, Tuple, Any
from .models import CacheEntry, ProxyMetrics
from .embeddings import embedding_engine
from .volatility import classifier
from .tavily_probe import tavily_prober
from .config import settings
from .storage import db_storage

logger = logging.getLogger("heimdall.living_cache")

class LivingSemanticCache:
    """
    Living Semantic Cache for Bifrost Gateway.
    Combines vector similarity search with automated temporal decay,
    Tavily live-web freshness invalidation, and durable SQLite persistence.
    """
    def __init__(self):
        self.entries: Dict[str, CacheEntry] = {}
        self.metrics = ProxyMetrics()
        self._load_from_storage()

    def _load_from_storage(self):
        try:
            persisted_entries = db_storage.load_all_entries()
            if persisted_entries:
                self.entries = persisted_entries
                logger.info(f"Loaded {len(self.entries)} vector entries from SQLite persistence.")
            else:
                self.seed_initial_scenarios()

            saved_metrics = db_storage.load_metrics()
            if saved_metrics:
                self.metrics.total_requests = saved_metrics.get("total_requests", 0)
                self.metrics.cache_hits = saved_metrics.get("cache_hits", 0)
                self.metrics.cache_misses = saved_metrics.get("cache_misses", 0)
                self.metrics.stale_invalidations = saved_metrics.get("stale_invalidations", 0)
                self.metrics.tokens_saved = saved_metrics.get("tokens_saved", 0)
        except Exception as e:
            logger.error(f"Failed to load SQLite cache, falling back to clean memory: {e}")
            if not self.entries:
                self.seed_initial_scenarios()

    def _sync_metrics(self):
        try:
            db_storage.update_metrics(
                self.metrics.total_requests,
                self.metrics.cache_hits,
                self.metrics.cache_misses,
                self.metrics.stale_invalidations,
                self.metrics.tokens_saved,
            )
        except Exception as e:
            logger.error(f"Failed to sync metrics: {e}")

    def lookup(self, prompt: str) -> Tuple[Optional[CacheEntry], str, float, Optional[Dict[str, Any]]]:
        """
        Looks up a prompt in the semantic cache.
        Returns: (entry, status_code, similarity, metadata)
        """
        self.metrics.total_requests += 1
        query_vec = embedding_engine.get_embedding(prompt)

        best_entry: Optional[CacheEntry] = None
        best_sim = -1.0

        for entry in self.entries.values():
            if entry.status == "EVICTED":
                continue
            sim = embedding_engine.cosine_similarity(query_vec, entry.embedding)
            if sim > best_sim:
                best_sim = sim
                best_entry = entry

        # Cache Miss
        if best_entry is None or best_sim < settings.SIMILARITY_THRESHOLD:
            self.metrics.cache_misses += 1
            self._sync_metrics()
            return None, "MISS", max(0.0, best_sim), None

        # Check Living Freshness
        now = time.time()
        age_seconds = now - best_entry.last_verified_at

        ttl_threshold = settings.TTL_MODERATE_SECONDS
        if best_entry.max_volatility == "HIGH":
            ttl_threshold = settings.TTL_VOLATILE_SECONDS
        elif best_entry.max_volatility == "STATIC":
            ttl_threshold = settings.TTL_STATIC_SECONDS

        needs_probe = (
            best_entry.max_volatility == "HIGH" 
            or age_seconds >= ttl_threshold 
            or best_entry.overall_freshness < settings.FRESHNESS_THRESHOLD
        )

        if needs_probe:
            logger.info(f"Triggering Tavily Delta-Probe for cached vector {best_entry.id}")
            verified_claims, freshness = tavily_prober.probe_claims_batch(best_entry.claims)
            best_entry.claims = verified_claims
            best_entry.overall_freshness = freshness
            best_entry.last_verified_at = now

            if freshness < settings.FRESHNESS_THRESHOLD:
                self.metrics.stale_invalidations += 1
                best_entry.status = "DRIFT_DETECTED"
                db_storage.save_entry(best_entry)
                self._sync_metrics()
                meta = {
                    "invalidation_reason": "FACTUAL_DRIFT_DETECTED",
                    "freshness_score": freshness,
                    "flagged_claims": [c.model_dump() for c in verified_claims if c.is_stale],
                }
                return None, "STALE_INVALIDATED", best_sim, meta

        # Verified Cache Hit
        best_entry.hit_count += 1
        self.metrics.cache_hits += 1
        self.metrics.tokens_saved += len(best_entry.response_text.split())
        db_storage.save_entry(best_entry)
        self._sync_metrics()

        status = "HIT_VERIFIED" if best_entry.max_volatility in ("HIGH", "MODERATE") else "HIT_STATIC"
        meta = {
            "similarity": round(best_sim, 3),
            "freshness_score": best_entry.overall_freshness,
            "volatility": best_entry.max_volatility,
            "verified_via": "Tavily Live Web Search",
            "sources": [s for c in best_entry.claims for s in c.sources][:3],
        }
        return best_entry, status, best_sim, meta

    def store(self, prompt: str, response_text: str) -> CacheEntry:
        entry_id = f"vec_{uuid.uuid4().hex[:8]}"
        embedding = embedding_engine.get_embedding(prompt)
        claims = classifier.extract_claims(response_text)
        max_volatility = classifier.determine_max_volatility(claims)

        # Baseline verification probe
        verified_claims, freshness = tavily_prober.probe_claims_batch(claims)

        entry = CacheEntry(
            id=entry_id,
            prompt=prompt,
            response_text=response_text,
            embedding=embedding,
            created_at=time.time(),
            last_verified_at=time.time(),
            hit_count=0,
            claims=verified_claims,
            max_volatility=max_volatility,
            overall_freshness=freshness,
            status="HEALTHY",
        )

        self.entries[entry_id] = entry
        db_storage.save_entry(entry)
        return entry

    def evict(self, entry_id: str):
        if entry_id in self.entries:
            self.entries[entry_id].status = "EVICTED"
            db_storage.save_entry(self.entries[entry_id])

    def list_entries(self, limit: int = 50) -> List[Dict[str, Any]]:
        sorted_entries = sorted(self.entries.values(), key=lambda e: e.last_verified_at, reverse=True)
        return [e.model_dump() for e in sorted_entries[:limit]]

    def seed_initial_scenarios(self):
        stale_pricing_prompt = "What is the monthly pricing for Twitter X Premium?"
        stale_pricing_answer = "Twitter X Premium costs $8 per month for individual verification on the web."
        e1 = self.store(stale_pricing_prompt, stale_pricing_answer)
        e1.created_at = time.time() - (45 * 24 * 3600)
        db_storage.save_entry(e1)

        math_prompt = "What is the time complexity of QuickSort in the average case?"
        math_answer = "The time complexity of QuickSort in the average case is O(n log n)."
        self.store(math_prompt, math_answer)

cache = LivingSemanticCache()
