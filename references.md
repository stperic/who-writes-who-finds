# References, grouped by talk section

Every source below was verified by fetching it (Aug 2026). Figures are quoted as
the primary source states them. Accuracy notes are at the bottom: read them
before putting any number on a slide. No em dashes (public-facing rule).

Freshness: capability claims favor 2026 sources; the methodology and human-factors
anchors are older on purpose (they are stable science, not capability claims).

---

## Opener: developers trust AI's security

- **Perry, Srivastava, Kumar, Boneh. "Do Users Write More Insecure Code with AI Assistants?" ACM CCS 2023.**
  https://doi.org/10.1145/3576915.3623157 (preprint arXiv:2211.03622)
  Participants with an AI assistant wrote significantly less secure code, yet were more likely to believe it was secure.
- **Snyk. "2023 AI Code Security Report."**
  https://go.snyk.io/2023-ai-code-security-report.html
  75.8% of developers believe AI-generated code is more secure than human-written code. (Your slide-2 figure, exact.)
- **Sonar. "State of Code" developer survey, Jan 2026 (1,100+ developers).**
  https://www.sonarsource.com/company/press-releases/sonar-data-reveals-critical-verification-gap-in-ai-coding/
  96% do not fully trust AI code correctness, but only 48% always verify before committing: the "verification gap."

## AI writes the bug (who-introduces axis)

- **Pearce, Ahmad, Tan, Dolan-Gavitt, Karri. "Asleep at the Keyboard? Assessing the Security of GitHub Copilot's Code Contributions." IEEE S&P 2022.**
  https://arxiv.org/abs/2108.09293
  ~40% of 1,689 Copilot-generated programs (MITRE Top-25 CWE scenarios) were vulnerable.
- **Sandoval, Pearce, Nys, Karri, Garg, Dolan-Gavitt. "Lost at C." USENIX Security 2023.**
  https://www.usenix.org/conference/usenixsecurity23/presentation/sandoval
  In a 58-participant C study, AI assistance did NOT significantly raise critical-bug rates. Muted counterpoint to Perry; the pair shows the field is unsettled.
- **Veracode. "Spring 2026 GenAI Code Security Update." Mar 2026.**
  https://www.veracode.com/blog/spring-2026-genai-code-security/
  Across 80 tasks and 150+ models, only ~55% of AI-generated code passed security review (45% introduced a vulnerability); XSS secure 15% of the time, log injection 13%.
- **Georgia Tech SSLab "Vibe Security Radar" (Hanqing Zhao), `https://vibesecradar.com/` and `https://github.com/HQ1995/vibe-security-radar` (Sept 2026 ledger; initial coverage via InfoSecurity Magazine, 26 Mar 2026).**
  https://vibesecradar.com/
  https://github.com/HQ1995/vibe-security-radar
  https://www.infosecurity-magazine.com/news/ai-generated-code-vulnerabilities/
  Catalog grew from 74 AI-contributed CVEs through March 2026 (Jan 6, Feb 15, Mar 35) to **312 evidence-linked vulnerabilities through September 26, 2026** (237 AI root cause, 75 flawed AI code). Top categories: Injection & unsafe execution (116, 37%) and Authentication & access control (75, 24%), totaling 61%.
- **Cloud Security Alliance. "Vibe Coding Security Debt: AI-Generated Vulnerabilities at Scale." Apr 2026.**
  https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-codegen-vulnerability-debt-20260406-csa/
  Industry synthesis: 45-70% of AI code fails security tests (method-dependent); 19.7% of AI-suggested Python/JS dependencies were hallucinated packages.

## AI catches the bug (who-finds axis)

- **Google Project Zero + DeepMind. "From Naptime to Big Sleep." Oct/Nov 2024.**
  https://projectzero.google/2024/10/from-naptime-to-big-sleep.html
  "The first public example of an AI agent finding a previously unknown exploitable memory-safety issue in widely used real-world software" (a stack buffer underflow in SQLite). Quote the full hedge.
- **DARPA AI Cyber Challenge (AIxCC) Final, DEF CON 33, Aug 2025.**
  https://www.darpa.mil/news/2025/aixcc-results
  Autonomous cyber reasoning systems found 86% of synthetic vulnerabilities and patched 68%; also surfaced real zero-days. Winner Team Atlanta (system ATLANTIS).
- **Zhang, Li, Yang, Widyasari, Liu, et al. "TitanCA: Lessons from Orchestrating LLM Agents to Discover 100+ CVEs." arXiv:2604.17860, Apr 2026 (SMU + GovTech Singapore).**
  https://arxiv.org/abs/2604.17860
  An orchestrated multi-agent LLM pipeline discovered 203 confirmed zero-days and yielded 118 assigned CVEs in real open-source software.
- **XBOW. Top of HackerOne US bug-bounty leaderboard, Jun 2025.**
  https://xbow.com/blog/top-1-how-xbow-did-it
  An autonomous AI pentester out-ranked human researchers on a public leaderboard.

### AI catches the bug: the limits (keep it honest)

- **Yildiz, Teo, Lou, Feng, Wang, Divakaran. "Benchmarking LLMs and LLM-based Agents in Practical Vulnerability Detection for Code Repositories (JITVul)." ACL 2025.**
  https://aclanthology.org/2025.acl-long.1490/
  Links 879 CVEs across 91 vulnerability types to their vulnerability-introducing and fixing commits (JIT/SZZ setup) and demonstrates that ReAct agents with interprocedural context retrieval outperform isolated function/diff LLMs.
- **Kolega.Dev / RealVuln. "RealVuln: Benchmarking Rule-Based, General-Purpose LLM, and Security-Specialized Scanners on Real-World Code." arXiv:2604.13764, Apr 2026.**
  https://arxiv.org/abs/2604.13764
  Evaluates 15 scanners (3 Rule-Based SAST, 10 General-Purpose LLMs including Claude Sonnet 4.6, 2 Security-Specialized AI scanners) across 676 vulnerabilities and 120 false-positive traps; establishes a consistent 3-tier hierarchy (Security-Specialized Agent > General-Purpose Frontier LLM > Rule-Based SAST on recall-weighted F3).
- **Dahiya, Nehra, Dholariya, Shangari, Khatri. "Are Frontier LLMs Ready for Cybersecurity?" arXiv:2605.23243, May 2026.**
  https://arxiv.org/abs/2605.23243
  Every tested frontier model showed 10-50% false-positive rates (white-box) and only 4-8% ground-truth coverage (black-box): impractical for unassisted production triage.
- **Ahmed, Shiri Harzevili, Shin, Pham, Wang. "SecVulEval: Benchmarking LLMs for Real-World C/C++ Vulnerability Detection." arXiv:2505.19828, May 2025.**
  https://arxiv.org/abs/2505.19828
  Across 5,867 real CVEs, the best model reached only 23.83% F1 for pinpointing the vulnerable statement with correct reasoning.
- **Li, Li, Wu, et al. "Everything You Wanted to Know About LLM-based Vulnerability Detection But Were Afraid to Ask." arXiv:2504.13474, Apr 2025.**
  https://arxiv.org/abs/2504.13474
  With rich context, SOTA LLMs reach ~0.7 F1 on key CWEs, but most false positives stem from flawed reasoning: synthetic-good, real-world-shaky.

## Contamination control (grounds the "did it catch it, or remember it?" slide)

Genuine scientific disagreement here. Present both sides: it strengthens the
"re-measure as models improve" thesis rather than undercutting it.

- **Dozono, Engesser, Hummel, Pretschner, Roehm. "Should We Evaluate LLM Based Security Analysis Approaches on Open Source Systems?" ASE 2025 Industry Showcase, Nov 2025 (TU Munich + CQSE).**
  https://conf.researchr.org/details/ase-2025/ase-2025-industry-showcase/10/
  Same LLMs' detection precision fell from ~56% on an open-source benchmark (likely in training data) to ~34% on unseen commercial code; significant for 4 of 5 models. Best direct support for your contamination control.
- **Ramos, Mamede, Jain, Canelas, Gamboa, Le Goues. "Are Large Language Models Memorizing Bug Benchmarks?" arXiv:2411.13323, Nov 2024 (rev Mar 2025).**
  https://arxiv.org/abs/2411.13323
  Several code models show significant memorization of common bug benchmarks (e.g., Defects4J); leaderboard scores can reflect leakage, not skill.
- **Li, et al. "Out of Distribution, Out of Luck: How Well Can LLMs Trained on Vulnerability Datasets Detect Top 25 CWE Weaknesses?" arXiv:2507.21817, Jul 2025.**
  https://arxiv.org/abs/2507.21817
  A model at 0.703 in-distribution accuracy dropped to 0.493 on real-world out-of-distribution vulnerabilities.
- **Euraste, Kaboré, Samhi, Barr, Klein, Bissyandé. "Learned or Memorized? Quantifying Memorization Advantage in Code LLMs." arXiv:2604.13997, Apr 2026. (COUNTERPOINT)**
  https://arxiv.org/abs/2604.13997
  Measured memorization advantage is low (<0.1) for newer models: contamination risk is task- and model-dependent, sometimes overstated.
- **"JavaVulBench: a Leakage-Aware Evaluation Mode." arXiv:2607.02825, Jul 2026. (method, not a number)**
  https://arxiv.org/abs/2607.02825
  Ships a per-model pre-training contamination audit that separates genuinely unseen CVEs from possibly-memorized ones: the same control your study applies.

## Survival and lifecycle (grounds the survival-time slides)

- **Alexopoulos, Brack, Wagner, Grube, Muhlhauser. "How Long Do Vulnerabilities Live in the Code? A Large-Scale Empirical Measurement Study on FOSS Vulnerability Lifetimes." USENIX Security 2022.**
  https://www.usenix.org/conference/usenixsecurity22/presentation/alexopoulos
  Average vulnerability lifetime is ~4 years (about 2 years for Chromium, 7 for OpenSSL). Use "average ~4 years," NOT median. Frame your 15.7-year outlier as far beyond this baseline.

## Human factors and review load (grounds the automation-bias slide)

- **Parasuraman, Riley. "Humans and Automation: Use, Misuse, Disuse, Abuse." Human Factors 39(2), 1997.**
  https://doi.org/10.1518/001872097778543886
- **Skitka, Mosier, Burdick. "Does Automation Bias Decision-Making?" Int. J. Human-Computer Studies 51(5), 1999.**
  https://doi.org/10.1006/ijhc.1999.0252
  Foundational automation-complacency work: people relax vigilance once an automated check pre-approves.
- **He, Agarwal, Denisov-Blanch, Azaletskiy, Koyejo, Vasilescu. "AI Writes Faster Than Humans Can Review: A Longitudinal Study of an Enterprise 2x Mandate." arXiv:2607.01904, Jul 2026.**
  https://arxiv.org/abs/2607.01904
  After an enterprise AI mandate, throughput hit 2.09x, per-reviewer load roughly doubled, and automated review overtook human review: the bottleneck moves to review.

## Capability trajectory (optional, for "the boundary moves")

- **Stanford HAI. "AI Index 2026." ~Apr 2026.**
  Autonomous cybersecurity agents solved 93% of tasks, up from ~15% in 2024.
  CAUTION: do NOT attribute code-insecurity percentages (e.g., 45%) to the AI Index; those trace to Veracode. Cite only the 93% agent-capability figure to the Index.

## Methodology

- **Sliwerski, Zimmermann, Zeller. "When Do Changes Induce Fixes?" MSR 2005.**
  https://doi.org/10.1145/1083142.1083147
  Origin of the SZZ algorithm, used to trace each CVE to its introducing commit.

---

## Accuracy notes (read before slide-building)

1. **Snyk 75.8%**: cite the 2023 AI Code Security Report, not 2024 reprints. Figure is exact.
2. **Alexopoulos**: headline is average ~4 years, NOT median. Do not say "median."
3. **Big Sleep**: use Google's exact hedge ("first public example of an AI agent finding a previously unknown exploitable memory-safety issue in widely used real-world software"), not "first AI-found vuln."
4. **Perry vs Sandoval**: opposite-leaning findings. Keep them distinct; together they justify "measure it yourself."
5. **Vibe Security Radar**: official site is now `https://vibesecradar.com/` and repo is `https://github.com/HQ1995/vibe-security-radar` (312 cases as of Sept 26, 2026, up from 74 in March 2026). Do not cite the old `vibe-radar-ten.vercel.app` URL.
6. **Contamination section** carries real disagreement (Dozono/Ramos/Li show inflation; Euraste shows low advantage). Present both.
7. **NOT verified, so omitted**: OpenAI "Aardvark" and "swarm of OpenAI agents breached Hugging Face" stories. Do not cite unless separately confirmed.
8. **Stanford AI Index**: 93% agent figure is safe; the code-insecurity percentages circulating under its name are misattributed (they are Veracode's).
