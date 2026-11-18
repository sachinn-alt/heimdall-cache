import time
import uuid
import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
from .models import CacheEntry, ProxyMetrics
from .embeddings import embedding_engine
from .volatility import classifier
from .tavily_probe import tavily_prober
from .config import settings
from .storage import db_storage

logger = logging.getLogger("heimdall.living_cache")


class LivingSemanticCache:
    """
    High-Speed Living Semantic Cache for Bifrost Gateway.
    - Vectorized NumPy matrix similarity search (< 0.1ms)
    - Zero-blocking startup seeding (no HTTP calls at import time)
    - Smart TTL-aware Tavily Delta-Probing (respects volatility half-lives)
    - Eliminates double-probing when responses are already Tavily-grounded
    - Durable WAL-mode SQLite persistence
    """

    def __init__(self):
        self.entries: Dict[str, CacheEntry] = {}
        self.metrics = ProxyMetrics()
        self._vector_ids: List[str] = []
        self._vector_matrix: np.ndarray = np.empty((0, embedding_engine.dimension), dtype=np.float32)
        self._load_from_storage()

    def _rebuild_vector_index(self):
        ids = []
        vecs = []
        for eid, entry in self.entries.items():
            if entry.status == "EVICTED":
                continue
            if len(entry.embedding) != embedding_engine.dimension:
                entry.embedding = embedding_engine.get_embedding(entry.prompt)
            ids.append(eid)
            vecs.append(entry.embedding)
        self._vector_ids = ids
        if vecs:
            self._vector_matrix = np.asarray(vecs, dtype=np.float32)
        else:
            self._vector_matrix = np.empty((0, embedding_engine.dimension), dtype=np.float32)

    def _load_from_storage(self):
        try:
            persisted_entries = db_storage.load_all_entries()
            if persisted_entries:
                # Re-normalize embeddings deterministically so old non-CRC32 vectors match cleanly
                for entry in persisted_entries.values():
                    fresh_emb = embedding_engine.get_embedding(entry.prompt)
                    if entry.embedding != fresh_emb:
                        entry.embedding = fresh_emb
                        db_storage.save_entry(entry)
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

        self._rebuild_vector_index()

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

    def record_latency(self, is_cache_hit: bool, latency_ms: float):
        if is_cache_hit:
            prev = self.metrics.avg_cache_latency_ms
            self.metrics.avg_cache_latency_ms = round(
                latency_ms if prev == 0.0 else (prev * 0.8 + latency_ms * 0.2), 2
            )
        else:
            prev = self.metrics.avg_upstream_latency_ms
            self.metrics.avg_upstream_latency_ms = round(
                latency_ms if prev == 0.0 else (prev * 0.8 + latency_ms * 0.2), 2
            )

    def _find_best_match(self, prompt: str) -> Tuple[Optional[CacheEntry], float]:
        if not self._vector_ids:
            return None, 0.0
        query_vec = embedding_engine.get_embedding_np(prompt)
        sims = embedding_engine.batch_cosine_similarity(query_vec, self._vector_matrix)
        best_idx = int(np.argmax(sims))
        best_sim = float(sims[best_idx])
        best_entry = self.entries.get(self._vector_ids[best_idx])
        return best_entry, best_sim

    def _needs_probe(self, entry: CacheEntry, now: float) -> bool:
        age_seconds = now - entry.last_verified_at
        if entry.max_volatility == "HIGH":
            ttl_threshold = settings.TTL_VOLATILE_SECONDS
        elif entry.max_volatility == "STATIC":
            ttl_threshold = settings.TTL_STATIC_SECONDS
        else:
            ttl_threshold = settings.TTL_MODERATE_SECONDS

        return (
            age_seconds >= ttl_threshold
            or entry.overall_freshness < settings.FRESHNESS_THRESHOLD
            or entry.status == "DRIFT_DETECTED"
        )

    async def async_lookup(
        self, prompt: str
    ) -> Tuple[Optional[CacheEntry], str, float, Optional[Dict[str, Any]]]:
        """
        Fast, non-blocking semantic lookup with TTL-aware async Tavily delta-probing.
        """
        self.metrics.total_requests += 1
        best_entry, best_sim = self._find_best_match(prompt)

        if best_entry is None or best_sim < settings.SIMILARITY_THRESHOLD:
            self.metrics.cache_misses += 1
            self._sync_metrics()
            return None, "MISS", max(0.0, round(best_sim, 4)), None

        now = time.time()
        probed_now = False

        if self._needs_probe(best_entry, now):
            probed_now = True
            logger.info(f"Triggering async Tavily Delta-Probe for cached vector {best_entry.id}")
            verified_claims, freshness = await tavily_prober.async_probe_claims_batch(best_entry.claims)
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
                    "tavily_probed": True,
                    "volatility": best_entry.max_volatility,
                    "flagged_claims": [c.model_dump() for c in verified_claims if c.is_stale],
                    "sources": [s for c in verified_claims for s in c.sources][:3],
                }
                return None, "STALE_INVALIDATED", round(best_sim, 4), meta

            best_entry.status = "HEALTHY"

        # Verified Cache Hit
        best_entry.hit_count += 1
        self.metrics.cache_hits += 1
        self.metrics.tokens_saved += max(1, len(best_entry.response_text.split()))
        db_storage.save_entry(best_entry)
        self._sync_metrics()

        status = "HIT_VERIFIED" if best_entry.max_volatility in ("HIGH", "MODERATE") else "HIT_STATIC"
        meta = {
            "similarity": round(best_sim, 4),
            "freshness_score": best_entry.overall_freshness,
            "volatility": best_entry.max_volatility,
            "tavily_probed": probed_now,
            "verified_via": "Tavily Live Web Search" if probed_now else "Living Vector Memory (Verified Fresh)",
            "sources": [s for c in best_entry.claims for s in c.sources][:3],
        }
        return best_entry, status, round(best_sim, 4), meta

    async def async_store(
        self,
        prompt: str,
        response_text: str,
        sources: Optional[List[str]] = None,
        already_grounded: bool = False,
    ) -> CacheEntry:
        """
        Stores a response into the living vector cache.
        If `already_grounded=True` (just synthesized from Tavily), skips redundant double-probing!
        """
        entry_id = f"vec_{uuid.uuid4().hex[:8]}"
        embedding = embedding_engine.get_embedding(prompt)
        claims = classifier.extract_claims(response_text)
        max_volatility = classifier.determine_max_volatility(claims)
        sources_list = list(sources or [])[:3]

        if already_grounded:
            for c in claims:
                c.freshness_score = 98.0 if c.volatility_level != "STATIC" else 100.0
                c.is_stale = False
                c.verification_summary = "Freshly grounded via Tavily Live Search."
                if sources_list and not c.sources:
                    c.sources = sources_list
            verified_claims = claims
            freshness = 98.0 if max_volatility != "STATIC" else 100.0
        else:
            verified_claims, freshness = await tavily_prober.async_probe_claims_batch(claims)

        now = time.time()
        entry = CacheEntry(
            id=entry_id,
            prompt=prompt,
            response_text=response_text,
            embedding=embedding,
            created_at=now,
            last_verified_at=now,
            hit_count=0,
            claims=verified_claims,
            max_volatility=max_volatility,
            overall_freshness=freshness,
            status="HEALTHY",
        )

        # Evict any older stale/drifted entry with near-identical prompt so future hits match the fresh entry
        for existing in self.entries.values():
            if existing.status == "DRIFT_DETECTED":
                sim = embedding_engine.cosine_similarity(embedding, existing.embedding)
                if sim >= settings.SIMILARITY_THRESHOLD:
                    existing.status = "EVICTED"
                    db_storage.save_entry(existing)

        self.entries[entry_id] = entry
        db_storage.save_entry(entry)
        self._rebuild_vector_index()
        return entry

    # ---- Synchronous Wrappers (for CLI benchmarks / legacy callers) ----

    def lookup(self, prompt: str) -> Tuple[Optional[CacheEntry], str, float, Optional[Dict[str, Any]]]:
        try:
            asyncio.get_running_loop()
            # Inside an active loop (unlikely for sync caller) — do direct sync check
            best_entry, best_sim = self._find_best_match(prompt)
            if best_entry is None or best_sim < settings.SIMILARITY_THRESHOLD:
                self.metrics.total_requests += 1
                self.metrics.cache_misses += 1
                return None, "MISS", max(0.0, round(best_sim, 4)), None
            return best_entry, "HIT_STATIC", round(best_sim, 4), {"freshness_score": best_entry.overall_freshness}
        except RuntimeError:
            return asyncio.run(self.async_lookup(prompt))

    def store(self, prompt: str, response_text: str, already_grounded: bool = False) -> CacheEntry:
        try:
            asyncio.get_running_loop()
            return self._store_instant(prompt, response_text)
        except RuntimeError:
            return asyncio.run(self.async_store(prompt, response_text, already_grounded=already_grounded))

    def _store_instant(
        self,
        prompt: str,
        response_text: str,
        created_at: Optional[float] = None,
        last_verified_at: Optional[float] = None,
        freshness: float = 100.0,
        status: str = "HEALTHY",
        sources: Optional[List[str]] = None,
        hit_count: int = 0,
    ) -> CacheEntry:
        """Instant, zero-network seeding helper so startup never blocks on external APIs."""
        now = time.time()
        entry_id = f"vec_{uuid.uuid4().hex[:8]}"
        embedding = embedding_engine.get_embedding(prompt)
        claims = classifier.extract_claims(response_text)
        max_volatility = classifier.determine_max_volatility(claims)
        for c in claims:
            c.freshness_score = freshness
            c.is_stale = freshness < settings.FRESHNESS_THRESHOLD
            if sources:
                c.sources = sources[:3]

        entry = CacheEntry(
            id=entry_id,
            prompt=prompt,
            response_text=response_text,
            embedding=embedding,
            created_at=created_at or now,
            last_verified_at=last_verified_at or now,
            hit_count=hit_count,
            claims=claims,
            max_volatility=max_volatility,
            overall_freshness=freshness,
            status=status,
        )
        self.entries[entry_id] = entry
        db_storage.save_entry(entry)
        return entry

    def evict(self, entry_id: str):
        if entry_id in self.entries:
            self.entries[entry_id].status = "EVICTED"
            db_storage.save_entry(self.entries[entry_id])
            self._rebuild_vector_index()

    def list_entries(self, limit: int = 50) -> List[Dict[str, Any]]:
        sorted_entries = sorted(self.entries.values(), key=lambda e: e.last_verified_at, reverse=True)
        return [e.model_dump() for e in sorted_entries[:limit]]

    def seed_initial_scenarios(self):
        """Instantaneous deterministic seed vectors — zero blocking HTTP calls at boot!"""
        now = time.time()
        forty_five_days_ago = now - (45 * 24 * 3600)
        thirty_days_ago = now - (30 * 24 * 3600)

        # Scenario 1: Aged volatile pricing claim (will trigger fast live Tavily delta-probe on hit)
        self._store_instant(
            prompt="What is the monthly pricing for Twitter X Premium?",
            response_text="Twitter X Premium costs $8 per month for individual verification on the web.",
            created_at=forty_five_days_ago,
            last_verified_at=forty_five_days_ago,
            freshness=45.0,
            status="DRIFT_DETECTED",
            hit_count=14,
        )

        # Scenario 2: Static immutable CS theory (instant < 2ms hit forever, zero Tavily calls)
        self._store_instant(
            prompt="What is the time complexity of QuickSort in the average case?",
            response_text="The time complexity of QuickSort in the average case is O(n log n), and O(n^2) in the worst case when pivot selection produces unbalanced partitions.",
            created_at=thirty_days_ago,
            last_verified_at=now,
            freshness=100.0,
            status="HEALTHY",
            hit_count=48,
        )

        # Scenario 3: API Deprecation claim (demonstrates version/deprecation detection)
        self._store_instant(
            prompt="Is OpenAI text-davinci-003 still available for chat completions?",
            response_text="OpenAI text-davinci-003 was shut down and deprecated on January 4, 2024. Migrate workloads to gpt-3.5-turbo-instruct or gpt-4o-mini.",
            created_at=thirty_days_ago,
            last_verified_at=now,
            freshness=96.5,
            status="HEALTHY",
            sources=["https://platform.openai.com/docs/deprecations"],
            hit_count=22,
        )

        self._rebuild_vector_index()


cache = LivingSemanticCache()
