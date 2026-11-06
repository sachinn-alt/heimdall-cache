# HeimdallCache 🌈👁️

> **The All-Seeing Living Semantic Cache for Bifrost Gateway, Powered by Tavily.**

HeimdallCache is an enterprise-grade living semantic cache middleware and proxy extension for the open-source **Bifrost AI Gateway** (`maximhq/bifrost`). It solves the critical flaw of traditional semantic caching—**factual staleness and cache poisoning**—by actively monitoring perishable claims (pricing, API signatures, executive leadership, policies) and using **Tavily Search** to execute real-time drift probes, calculate claim freshness scores, and autonomously hot-invalidate decaying cache vectors.

---

## 🏆 Global AI Hackathon Tracks Addressed
- **Bifrost Priority Track:** *Open-Source Bifrost Gateway* (Advanced Semantic Caching Strategy & Living Middleware)
- **Tavily Track Partner:** *Stale-Answer Detector* (Factual Drift Extraction, Freshness Scoring & Real-Time Verification)

---

## Key Features
- **Zero-Staleness Semantic Caching:** Sub-millisecond cache hits for stable queries, with autonomous invalidation when real-world facts change.
- **Perishable Entity Decomposition:** Extracts volatile claims (pricing, versions, people, rules) and assigns dynamic half-life decay.
- **Tavily Delta-Probing:** Surgically queries Tavily Search API when cache similarity is high but the claim age exceeds volatility thresholds.
- **Self-Healing Cache Invalidation:** Automatically evicts stale answers, fetches live ground truth, and hot-patches the cache vector.
- **Visual Operator Dashboard:** Live radar displaying cache hit rates, token savings, factual freshness gauges, and source citations.
- **Drop-In OpenAI & Bifrost Compatibility:** Acts as a transparent proxy layer for any OpenAI or Bifrost compatible client.
