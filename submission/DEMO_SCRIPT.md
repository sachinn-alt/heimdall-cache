# HeimdallCache: 2-Minute Demo Video Script

**Recording Target Time:** 1:50 - 2:00  
**Video Resolution:** 1080p / 60fps  
**Setup:** Have `http://localhost:8000` open in your browser and a terminal on the side.

---

### [0:00 - 0:25] The Hook: The Hidden Disaster in Semantic Caching
* **Screen:** Show the Heimdall Dashboard or a slide showing an LLM Gateway.
* **Voiceover:**  
  *"Hey everyone! Today, AI gateways like Bifrost are deployed across thousands of production apps to slash latency and token bills using Semantic Caching. But there’s a fatal flaw no one talks about: **semantic caches cache stale, broken truths forever**.*  
  *If a customer asks for pricing or an API method, and your gateway cached an answer from 3 months ago, it will confidently serve that outdated, broken answer with a 98% similarity match.*  
  *Introducing **HeimdallCache**—the all-seeing living semantic cache for Bifrost Gateway, powered by Tavily."*

---

### [0:25 - 0:55] How It Works: The Architecture
* **Screen:** Show the Heimdall UI header and scroll down to the Live Playground.
* **Voiceover:**  
  *"HeimdallCache acts as a drop-in proxy for Bifrost and OpenAI. But unlike static caches, Heimdall decomposes every cached answer into atomic claims, categorizes them by volatility—like pricing, APIs, or leadership—and assigns them dynamic half-lives.*  
  *When a query hits the cache, Heimdall doesn't just return it blindly. It triggers an async **Tavily Delta-Probe** to re-verify perishable facts against the live web."*

---

### [0:55 - 1:30] The Live Demo: Catching Drift & Hot-Invalidation
* **Screen:** In the Live Playground, click **"Twitter X Pricing (Stale Test)"** and hit **"Execute via Heimdall"**.
* **Action:** Watch the status badge flash **"🚨 STALE DRIFT CAUGHT & HOT-INVALIDATED"**.
* **Voiceover:**  
  *"Watch this in action. Here we have a cached answer claiming Twitter X verification costs $8 per month. In a normal gateway, this stale answer is served immediately.*  
  *With HeimdallCache, the moment the request hits, Heimdall detects high-volatility pricing data, fires a Tavily Delta-Probe, and instantly detects factual drift! Look at the dashboard:*  
  *It catches the drift, hot-invalidates the decayed vector, pulls the latest ground truth via Tavily with 100% cited sources, and refreshes the living cache in real time!"*

---

### [1:30 - 1:50] The Static Test: Speed When Truth is Stable
* **Screen:** Click **"QuickSort Complexity (Static)"** and hit **"Execute"**.
* **Action:** Watch the badge instantly turn green: **"⚡ VERIFIED CACHE HIT (< 5ms)"**.
* **Voiceover:**  
  *"And when facts are immutable—like computer science theory or mathematical formulas—Heimdall serves verified cache hits in under 5 milliseconds with zero token cost."*

---

### [1:50 - 2:00] Conclusion & Call to Action
* **Screen:** Show the GitHub repository (`github.com/sachinn-alt/heimdall-cache`) and the metrics counter showing tokens saved.
* **Voiceover:**  
  *"HeimdallCache turns Bifrost's gateway into a self-healing, zero-staleness infrastructure with Tavily as the live truth anchor. The project is completely open source on GitHub. Thank you!"*
