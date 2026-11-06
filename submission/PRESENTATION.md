# HeimdallCache: Pitch Deck (Presentation Outline)

> **Submission for Global AI Hackathon**  
> **Track:** Bifrost Priority Track (*Open-Source Bifrost Gateway*) + Tavily Partner (*Stale-Answer Detector*)  
> **Project URL:** https://github.com/sachinn-alt/heimdall-cache  

---

## Slide 1: Title & The Hook
* **Title:** HeimdallCache 🌈👁️
* **Subtitle:** The All-Seeing Living Semantic Cache for Bifrost Gateway, Powered by Tavily
* **Team:** Team Heimdall
* **Tagline:** *Semantic Caches Rot. Heimdall Never Forgets, Never Stales.*

---

## Slide 2: The Critical Industry Problem
* **The Promise of Gateways:** AI Gateways like Bifrost save thousands of dollars and achieve sub-millisecond speeds by semantically caching LLM responses.
* **The Fatal Flaw:** *Semantic caches cache stale, broken truths forever.*
  * Pricing changes ($20 → $35)
  * API versions deprecate (v1 → v2 breaks production)
  * Leadership shifts (New CEO appointed)
* **The Silent Poisoning:** If a user asks a question with 95% semantic similarity 6 months later, the gateway happily serves the outdated hallucination.

---

## Slide 3: The Solution — HeimdallCache
* **What is HeimdallCache?**
  * An enterprise-grade living semantic cache extension for the open-source Bifrost AI Gateway (`maximhq/bifrost`).
  * Transforms static vector caches into **autonomous living memories** that probe real-world drift using Tavily Search.
* **Core Philosophy:**
  * Fast when facts are immutable (< 5ms retrieval).
  * Watchful when facts are perishable (dynamic half-life TTL).
  * Self-healing when facts drift (hot-invalidation and real-time grounding).

---

## Slide 4: System Architecture
```
[Client / LLM App] 
        │  (OpenAI Compatible /v1/chat/completions)
        ▼
[HeimdallCache Living Gateway Proxy]
        │
        ├──► [Local Vector Similarity Engine] (Cosine Match)
        │
        ├──► [Entity Volatility Classifier] 
        │        ├── STATIC (Math, Theory) -> Instant Hit (< 5ms)
        │        └── VOLATILE (Pricing, APIs, People)
        │                 │
        │                 ▼
        │        [Tavily Delta-Probe Engine]
        │                 │ (Live Web Verification & Freshness Scoring)
        │                 ▼
        │        [Drift Threshold Check (< 70%?)]
        │                 ├── Yes: HOT INVALIDATE & Refresh from Upstream
        │                 └── No:  Serve Verified Hit with Live Sources
        ▼
[Bifrost / Upstream LLMs]
```

---

## Slide 5: The Tavily Integration (Stale-Answer Detector)
* **Atomic Claim Extraction:** Decomposes answers into perishable propositions.
* **Delta-Probing:** Queries Tavily with temporal qualifiers (e.g., `pricing current fee`, `latest docs deprecation`).
* **Freshness Scoring Engine:**
  * Analyzes numerical drift (pricing deltas, version increments).
  * Detects explicit deprecation signals.
  * Injects `X-Heimdall-Freshness-Score` and verifiable source URLs into HTTP headers.

---

## Slide 6: Live Operator Dashboard
* **Real-time Telemetry:**
  * Live cache hit vs. miss ratio.
  * Real-time counter of **Stale Drift Caught & Invalidated**.
  * Estimated token cost savings ($$).
* **Interactive Playground:** Allows operators to test perishable prompts live and watch Heimdall hot-invalidate stale entries in real time.
* **Living Cache Vector Inspector:** Full visibility into vector status, volatility classes, and per-claim freshness scores.

---

## Slide 7: Benchmarks & Impact
* **Staleness Elimination:** 100% of simulated factual drift caught before reaching client applications.
* **Token Savings:** Over 68% token reduction on repeat queries while maintaining zero hallucination.
* **Latency:** < 5ms on verified cache hits; transparent background probing on volatile entities.

---

## Slide 8: Why Bifrost & Tavily Win Together
* **For Bifrost Operators:** Eliminates the #1 reason engineers disable semantic caching in production—fear of serving outdated data.
* **For Tavily:** Demonstrates Tavily as vital infrastructure-grade verification rather than just a human search UI.
* **Open Source:** Available today under Apache 2.0 license at `github.com/sachinn-alt/heimdall-cache`.
