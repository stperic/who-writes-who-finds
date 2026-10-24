# References, grouped by talk section

This working bibliography includes sources collected during preparation and later checks. Verification dates and access limitations are recorded where available. It is broader than the final slide citations. The remaining-slide review on October 18, 2026 rechecked Vibe Security Radar, Veracode, OWASP, GitHub rulesets, HHS and the human-factors sources. Do not assume every optional source was revalidated in that review.

For the current context and tracing extension, use [Agent context and OpenTelemetry](#agent-context-and-opentelemetry). Earlier preparation sections retain dated status descriptions; the current local readiness record governs executed replay claims.

Freshness: capability claims favor 2026 sources; the methodology and human-factors
anchors are older on purpose (they are stable science, not capability claims).

## Agent context and OpenTelemetry

Primary sources checked October 23, 2026. These support the context-selection, runtime-tracing and evidence-correlation concepts. They do not establish added detection in our experiments. D05 has captured component, provider, requirement-link, workflow and gate evidence; this presentation does not claim that D05 was instrumented with OpenTelemetry. The separate public CSRF PR's proposed controls remain unrun. The measured 24-case results and targeted recovery counts are unchanged.

### Supplying useful context

- **Anthropic, Effective context engineering for AI agents, September 29, 2025.** [Article](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents). Supports a small persistent project brief combined with selective retrieval of relevant files at runtime. File paths and other references can guide further retrieval. This is guidance on context management, not evidence that a larger context or a retrieval system improves security detection in every setting.
- **Anthropic, Introducing Contextual Retrieval, September 19, 2024.** [Article](https://www.anthropic.com/research/contextual-retrieval). Explains retrieval-augmented generation: retrieve relevant knowledge and supply it with the request. Its retrieval benchmark is separate from our security-review study; no benchmark improvement is transferred to the deck's results.
- **Claude Code, project instructions and skills.** [Project instructions](https://code.claude.com/docs/en/memory), [skills](https://code.claude.com/docs/en/skills). Persistent instructions capture project context, while skills package procedures that load when relevant. Keep instructions concise and check them for obsolete references and contradictions. These files guide a reviewer; they do not enforce merge authorization.
- **Claude Code, Best practices, and Anthropic, Writing effective tools, September 11, 2025.** [Coding guidance](https://code.claude.com/docs/en/best-practices), [tool design](https://www.anthropic.com/research/writing-tools-for-agents). Support referencing existing implementation patterns, supplying verification evidence and returning focused tool output. The tool-design example searches relevant log lines with nearby context instead of returning whole logs.
- **GitHub, Using Copilot code review.** [Documentation](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/use-code-review). Documents repository instructions, skills and MCP context. Review-comment attributions and session logs can identify referenced skills and invoked servers or tools. Record the context supplied and retrieved. These records establish access and inputs, not the causal influence of content on model reasoning. Availability of a connection alone does not establish that its context was retrieved.
- **Model Context Protocol, resources and tools, specification revision 2025-11-25.** [Resources](https://modelcontextprotocol.io/specification/2025-11-25/server/resources), [tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools). Resources expose contextual data; tools expose callable operations. Resource URIs and optional modification timestamps help identify content. They do not prove it matches the reviewed revision. The specifications discuss access checks, validation and trust in tool annotations; MCP is an interface, not a guarantee of trustworthy evidence.
- **OWASP, Threat Modeling Cheat Sheet.** [Guide](https://cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html). Supports using components, data flows, trust boundaries, data stores and external entities to understand the system. Offering a concise project map to a security agent is our application of this guidance, not a measured intervention in the original study.
- **Anthropic, Demystifying evals for AI agents, January 9, 2026.** [Article](https://www.anthropic.com/research/demystifying-evals-for-ai-agents). Supports realistic agent configurations, outcome-based evaluation, repeated trials and isolated, stable test environments. Freezing context selection before evaluating held-out full PRs is the proposed local pilot method, not an experiment completed by the presentation.

### Runtime signals and correlation

- **OpenTelemetry, Traces.** [Concepts](https://opentelemetry.io/docs/concepts/signals/traces/). A trace represents the instrumented path of a request or operation using spans with timing and relationships. Span links can associate asynchronous work. A span's completion or status does not independently establish a security assertion or approval.
- **OpenTelemetry, Context propagation.** [Concepts](https://opentelemetry.io/docs/concepts/context-propagation/). Explains carrying trace and span context across service boundaries, commonly with W3C Trace Context, and correlating signals. It warns about untrusted incoming context and sensitive outgoing baggage. A propagated identifier is not proof of producer identity.
- **OpenTelemetry, Logs.** [Concepts](https://opentelemetry.io/docs/concepts/signals/logs/). Logs record events and may carry trace and span IDs for correlation. Structured fields help connect an event to an operation, but a log statement is not a substitute for the retained test result it describes.
- **OpenTelemetry, Metrics.** [Concepts](https://opentelemetry.io/docs/concepts/signals/metrics/). Metrics capture measurements and commonly summarize counts, durations and other values over time. They answer aggregate questions; a metric alone does not reconstruct one review's complete evidence or authority.
- **OpenTelemetry, Resources.** [Concepts](https://opentelemetry.io/docs/concepts/resources/). Resource attributes describe the entity producing telemetry, such as its service, process, container or environment. This differs from an MCP resource, which exposes contextual content. Resource attributes assist attribution and filtering but do not authenticate a producer by themselves.

**Presentation design boundary:** Correlating a source revision, requirement version, test/result record, review run and runtime trace is a proposed evidence design. Keep source content, prompts, secrets and patient data in authorized evidence storage; use appropriate identifiers and references in telemetry. Requirement traceability, runtime tracing, result verification and human authorization answer different questions. None alone establishes all four.

---

## Opener: developers trust AI's security

- **Perry, Srivastava, Kumar, Boneh. "Do Users Write More Insecure Code with AI Assistants?" ACM CCS 2023.**
  https://doi.org/10.1145/3576915.3623157 (preprint arXiv:2211.03622)
  Participants with an AI assistant wrote significantly less secure code, yet were more likely to believe it was secure.
- **Snyk. "2023 AI Code Security Report."**
  https://go.snyk.io/2023-ai-code-security-report.html
  75.8% of developers believe AI-generated code is more secure than human-written code. (Earlier background figure, not the current slide 2.)
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
  About 45% of generated outputs were insecure in the 80-task benchmark, covering four languages and four vulnerability classes without security-specific prompting. The 150+ model count describes Veracode's cumulative testing program, not the model count for this benchmark. XSS was secure 15% of the time and log injection 13%.
- **Georgia Tech SSLab "Vibe Security Radar" (Hanqing Zhao), `https://vibesecradar.com/` and `https://github.com/HQ1995/vibe-security-radar` (Sept 2026 ledger; initial coverage via InfoSecurity Magazine, 26 Mar 2026).**
  https://vibesecradar.com/
  https://github.com/HQ1995/vibe-security-radar
  https://www.infosecurity-magazine.com/news/ai-generated-code-vulnerabilities/
  On October 18, 2026, the primary page listed 307 evidence-linked AI-contributed findings with an advisory-date cutoff of September 26, 2026. This selected public catalog is not a census or a universal defect rate. This checked count is retained as background in the archived deck and source materials.
- **Cloud Security Alliance. "Vibe Coding Security Debt: AI-Generated Vulnerabilities at Scale." Apr 2026.**
  https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-codegen-vulnerability-debt-20260406-csa/
  Industry synthesis: 45-70% of AI code fails security tests (method-dependent); 19.7% of AI-suggested Python/JS dependencies were hallucinated packages.

## AI catches the bug (who-finds axis)

- **Mozilla engineering team. "Behind the Scenes: Hardening Firefox with Claude Mythos Preview." Mozilla Hacks, 7 May 2026.**
  https://hacks.mozilla.org/2026/05/behind-the-scenes-hardening-firefox/
  271 bugs identified with Claude Mythos Preview were fixed in Firefox 150 (180 sec-high, 80 sec-moderate, 11 sec-low); further fixes in 149.0.2, 150.0.1 and 150.0.2. Maintainer-confirmed. Mozilla says these are bugs, not CVEs, that a single high bug is usually not enough to compromise Firefox, and that it generally does not build exploits. Used on the review-configuration slide. Verified 2026-10-17.
- **AISLE. "AISLE Discovers 38 CVEs in Healthcare Software Used by 100,000 Medical Providers." aisle.com blog, Q1 2026; HIPAA Journal coverage 29 Apr 2026.**
  https://aisle.com/blog/aisle-discovers-38-critical-security-vulnerabilities-in-healthcare-software-used-by-100000-providers
  https://www.hipaajournal.com/ai-analysis-38-flaws-openemr-platform/
  38 OpenEMR CVEs (39 GitHub advisories) found in Q1 2026 by an AI analyzer with repository context, more than half of that quarter's OpenEMR advisories. Supporting category mix computed 2026-10-17 from the GitHub advisory API over the 39 Q1 2026 advisories credited to AISLE's researchers (logins simecek, pavelkohout396, stanislavfortaisle): 24 authorization or access control, 10 XSS, 2 path traversal, 2 SQL injection, 1 session timeout. AISLE's own page returned 403 when fetched; HIPAA Journal fetched and confirms 38 of 39, two CVSS 10.0, and the Q1 2026 window.
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
  Average vulnerability lifetime is ~4 years (about 2 years for Chromium, 7 for OpenSSL). Use "average ~4 years," NOT median. Different population and metric. The external comparison and local 21-case distribution are retained as background in the archived deck and source materials.

## Human factors and review load (grounds the automation-bias slide)

- **Parasuraman, Riley. "Humans and Automation: Use, Misuse, Disuse, Abuse." Human Factors 39(2), 1997.**
  https://doi.org/10.1518/001872097778543886
- **Skitka, Mosier, Burdick. "Does Automation Bias Decision-Making?" Int. J. Human-Computer Studies 51(5), 1999.**
  https://doi.org/10.1006/ijhc.1999.0252
  General research on automation use, monitoring and biased decisions. These papers do not measure the OpenEMR review workflow or establish the effectiveness of the proposed review practices.
- **He, Agarwal, Denisov-Blanch, Azaletskiy, Koyejo, Vasilescu. "AI Writes Faster Than Humans Can Review: A Longitudinal Study of an Enterprise 2x Mandate." arXiv:2607.01904, Jul 2026.**
  https://arxiv.org/abs/2607.01904
  After an enterprise AI mandate, throughput hit 2.09x, per-reviewer load roughly doubled, and automated review overtook human review: the bottleneck moves to review.

## Capability trajectory (optional, for "the boundary moves")

- **September 2026 frontier releases (optional Q&A background, outside the revised main narrative).**
  https://blog.google/innovation-and-ai/technology/ai/google-ai-updates-september-2026/
  https://www.cnbc.com/2026/09/22/anthropic-openai-cheaper-ai-models.html
  https://technewscompany.com/news/september-2026-ai-model-wave-recap/
  Google's own September recap (posted 2 Oct 2026) names Gemini 3.8 Flash and Gemini 4 Argon (Argon limited to the Fairwind Program). Press roundups (CNBC 22 Sep 2026; Tech News Company 2 Oct 2026) report Claude Fable 5.1 and Claude Mythos 5.1 (Mythos trusted-access only), GPT-6 Astra, and later Claude Opus 5.5, Claude Sonnet 5.5, GPT-6 Luna and GPT-6.1 Sol, all in September 2026, after this study's 17 Aug 2026 runs. On stage say "new frontier models shipped in September 2026" and name models only from vendor pages. Verified 2026-10-17: Google recap and Tech News Company fetched; CNBC title and date from search results only (page returned 403).
- **Stanford HAI. "AI Index 2026." ~Apr 2026.**
  Autonomous cybersecurity agents solved 93% of tasks, up from ~15% in 2024.
  CAUTION: do NOT attribute code-insecurity percentages (e.g., 45%) to the AI Index; those trace to Veracode. Cite only the 93% agent-capability figure to the Index.

## Methodology

- **Sliwerski, Zimmermann, Zeller. "When Do Changes Induce Fixes?" MSR 2005.**
  https://doi.org/10.1145/1083142.1083147
  Origin of SZZ tracing. The local study documents manual provenance decisions and limitations in METHODS.md and cves.csv.

---

## CI/CD security tools and the existing-controls baseline

Official product documentation checked October 23, 2026. Used on slide 7 and in the pilot notes and Q&A. These sources document capabilities; the separate OpenEMR measurement is in the [Snyk Code follow-up](openemr-study/snyk-baseline/README.md).

- **Snyk Code:** https://docs.snyk.io/scan-with-snyk/snyk-code
  AI-based static application security testing, data-flow analysis, interfile analysis for supported languages except Ruby, and PR/CLI/CI/CD operation.
- **Snyk developer integrations:** https://docs.snyk.io/developer-tools/overview
  Repository PR checks and CI/CD integration options, including policy gates. Integration describes workflow placement and does not establish detection quality.
- **Snyk Open Source:** https://docs.snyk.io/scan-with-snyk/snyk-open-source
  Software composition analysis for vulnerabilities and license issues in dependencies. Distinguish this from Snyk Code when selecting a comparator.

**Study limit:** A separate Snyk Code baseline now reports **6/24 clear Caught, 1/24 borderline** on the selected OpenEMR cases; its provisional case matches await independent human verification. No Semgrep or CodeQL comparator was run. The current deck has not been updated with the Snyk result. The baseline is retrospective and uses whole-repository scans, while AI reviewers saw selected diffs, so it does not establish matched detection performance or additional catches in a live workflow. For a local pilot, record overlap, validated findings and triage effort under the deployed controls.

## Policy gates and the Jev review workflow

Sources checked October 18, 2026. The main slides explain a proposed review workflow and an executed local gate simulation. No live calls have been made with the current eight questions. The example percentages and approval events are illustrative fixtures. The original 24-CVE detection study remains a separate experiment.

- **Current workflow:** [Method and status](jev-study/workflow-v1/README.md), [eight Noul questions](jev-study/workflow-v1/questions.json), and [policy](jev-study/workflow-v1/policy.json). Independent category probabilities feed deterministic rules that combine specialized AI reviews, AppSec/owner approvals and checks. Required actions are deduplicated. Mandatory repository requirements remain in force. Candidate thresholds await independent review and evaluation.
- **Worked PR example:** [Walkthrough](jev-study/workflow-v1/PR-JOURNEY.md), [illustrative response](jev-study/workflow-v1/examples/typed-response.json), and [gate scenarios](jev-study/workflow-v1/examples/gate-scenarios.json). Historical OpenEMR payment change D05 supplies the case. The eight percentages are invented demonstration inputs. Personal-data access and authorization together trigger AppSec under the declared example policy. Other conditions add the relevant AI reviews, owner approvals and checks. Clean AI reports with missing AppSec approval leave the simulated gate pending.
- **Executed software validation:** [Validation record](jev-study/workflow-v1/results/validation.json), `quadrant-tool/jev_workflow_policy.py`, and `quadrant-tool/test_jev_workflow.py`. The complete local suite has 56 passing tests. Nine gate scenarios block eight incomplete workflows and accept the fully satisfied fixture. These are software tests and simulated events, not routing-accuracy measurements, actual approvals or a production CI/CD integration.
- **What remains pending:** Independent human workflow adjudication and threshold review before evaluation on the nine unqueried holdout changes. The original 14 cases remain development data. No downstream model was executed or compared, and no production enforcement, detection improvement or human-review effectiveness is established. The explicit AI model configurations are approved only within the simulation.
- **Earlier routing evidence:** The [original pilot archive](jev-study/results/2026-10-18-jev-1.14/report.json) and [later policy reanalysis](jev-study/v2/results/development-reanalysis/report.json) remain intact as background. Their probabilities came from different questions and cannot be counted as observations for the current workflow. The main presentation does not use the implementation-version comparison as its story.

- **TypeSafe Introduction:** https://docs.typesafe.ai/introduction
  The vendor calls Jev a System One model, not System 0.
- **TypeSafe Noul:** https://docs.typesafe.ai/primitives/noul
  Each question returns a yes probability, with no separate Choice-style confidence field. Store the 0-to-1 value and display it as a percentage. Probabilities need not sum to one and do not measure vulnerability severity or certify merge safety.
- **TypeSafe primitives:** https://docs.typesafe.ai/primitives
  Independent questions sharing a state can run in one request. Application code combines the answers. The current workflow defines eight Noul questions; optional true/false criteria describe the condition without changing the probabilistic output.
- **OpenRouter Jev and Decisions API:** https://openrouter.ai/docs/guides/community/jev and https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request
  Protocol references for the actual Jev adapter. The pilot sends typed questions through the Decisions API, not Chat Completions.
- **TypeSafe Intent routing:** https://docs.typesafe.ai/patterns/intent-routing
  Documents classification followed by routing in application code to different handlers, including human review. Applying that pattern to security PRs is our proposal.
- **TypeSafe Jev 1.13 jaggedness:** https://docs.typesafe.ai/model-jaggedness/jev-1.13
  Version-specific disclosures, last reviewed by the vendor October 2, 2026, include adversarial-content, irrelevant-context and option-order sensitivity. Do not assume these findings characterize every later release.
- **Li. Fast Models, Slow Evidence: A Paired and Self-Audited Evaluation of System-1 Decision Models for LLM Agent Harnesses. arXiv preprint, October 1, 2026:** https://arxiv.org/abs/2610.02267
  Reports that neither tested model beat chance on its zero-shot model-routing task. That is a different task from our reviewer-category pilot. It cautions against generalizing category-routing results to choosing the best downstream AI reviewer.
- **GitHub rulesets:** https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets
  Supports required reviews and status checks, including an expected app as the status source. Define and audit bypass permissions separately.
- **Open Policy Agent:** https://www.openpolicyagent.org/docs
  Separates policy decision-making from enforcement. It is an architectural example, not a required product in the proposed workflow.

## Remaining-slide review sources and limits

Sources checked October 18, 2026. The PR decision record separates evidence and approvals from model recommendations. The workflow, screening and human-review slides propose controls to evaluate. The slide 21 browser demo includes the observed-results recap. Slide 22 returns to workflow changes and fresh evidence. Keep historical reviewer findings distinct from routing and gate outcomes when adding demo results. Appendix numbering refreshed October 19, 2026.

- **OWASP, LLM Prompt Injection Prevention Cheat Sheet:** https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html . Supports the threat and defense discussion on slide 19. The pictured attack is illustrative, and no prompt-injection resistance measurement is claimed.
- **HHS OCR, HIPAA Breach Notification Rule:** https://www.hhs.gov/hipaa/for-professionals/breach-notification/index.html . The healthcare backup in the notes to slide 20 distinguishes a technical flaw from an incident requiring assessment. An AI report does not replace the organization's assessment or required approvals.
- **Local source of truth:** `openemr-study/data/original/numbers.md`, `cves.csv`, `METHODS.md`, and `openemr-study/data/original/fix_dates.csv`. The dot plot uses 21 fully traced scored cases and selected-commit-to-disclosure intervals. Private discovery and deployment exposure are not established.
- **Current workflow evidence:** `jev-study/workflow-v1/results/validation.json`. The eight questions have zero live calls. Nine local scenarios use invented probabilities and completion events. The source-code study and earlier routing pilot do not validate the current questions.

## Sources added for Jev and human review

These sources support slides 15 and 20 and the selected references on slide 30. Checked October 19, 2026.

- **IBM, What is loop engineering?** Ivan Belcic and Cole Stryker, July 17, 2026. https://www.ibm.com/think/topics/loop-engineering
  Explains comprehension debt, intent debt and cognitive surrender. The presenter also supplied an excerpt from the IBM video *What Is Loop Engineering? Building Better AI Agents*, about 07:55 to 10:25. These are explanatory sources rather than results from the OpenEMR experiment.
- **TypeSafe, Guardrails for LLMs:** https://docs.typesafe.ai/cookbooks/llm_guardrails
  A vendor cookbook applies typed questions to LLM inputs and outputs, then routes the returned probabilities through application policy. It illustrates an integration pattern rather than validating our PR screening or routing setup.
- **DeerFlow, Guardrails: Pre-Tool-Call Authorization:** https://github.com/bytedance/deer-flow/blob/main/backend/docs/GUARDRAILS.md
  Option 4 documents an optional TypeSafe (Jev) risk assessment before agent tool calls. Its code applies a configured threshold. This supports the existence of the integration, not its security effectiveness or production adoption.
- **TypeSafe, Introduction and Confidence:** https://docs.typesafe.ai/introduction and https://docs.typesafe.ai/confidence
  Jev supplies focused structured judgments. Noul probabilities concern whether a condition holds. They do not establish vulnerability severity or authorize merge, and operational thresholds require local evaluation.

The earlier appendix remains in `Archive/ISC2-deck-v5-before-appendix-refresh-20261019.pptx`. The current appendix is slides 36–42: exact prompts, the recent-case subset, inherited flaws, prompt tradeoffs, context results, the focused-model pilot and the four quadrants. Detailed citations are retained in this bibliography. Snyk Code and GitHub rulesets document existing controls and required-check mechanisms.

## Functional correctness, human intent and checker evaluation

Sources checked October 19, 2026. The added evidence slide is slide 13. Human-review notes are on slide 20; the ten-minute demo and its browser results recap are introduced on slide 21. These external studies remain separate from the OpenEMR reviewer experiment.

- **SusVibes, Zhao et al., Is Vibe Coding Safe? Benchmarking Vulnerability of Agent-Generated Code in Real-World Tasks**, arXiv:2512.03262v4, September 21, 2026. [Paper and Table 3](https://arxiv.org/html/2512.03262v4). The slide compares functional and combined functional/security pass rates for SWE-agent with Claude 4 Sonnet on 186 selected tasks. Both rates use the full task set. This is code-generation evidence, not a production defect rate.
- **TiCoder, LLM-based Test-driven Interactive Code Generation: User Study and Empirical Evaluation**, arXiv:2404.10100v2. [Paper and user-study Table II](https://arxiv.org/html/2404.10100v2). Fifteen programmers evaluated short code suggestions. The result supports studying human clarification through test feedback; it does not measure security-review effectiveness.
- **HiLDe: Intentional Code Generation via Human-in-the-Loop Decoding**, arXiv:2505.22906v1. [Paper](https://arxiv.org/html/2505.22906v1). Small study with eighteen participants, sixteen of them students. Both conditions used the same completion model, with added interaction and analysis in HiLDe. Keep the scope visible when discussing its vulnerability reduction.
- **Loop Engineering: Building Blocks, Adoption, and Impact**, arXiv:2608.21884v2. [Paper](https://arxiv.org/html/2608.21884v2). Supports discussion of independent verification, bounded permissions, stop conditions and escalation, while acknowledging limited systematic quality evidence. Used in the checker-evaluation notes on slide 22.

Demo application: prepare a separately labeled controlled authorization-failure variant of the historical OpenEMR payment replay. Define the expected access rule independently, retain the security test, and record functional results, security results, reviewer catches or misses and gate decisions for the same revision. The variant is not another historical CVE or a holdout. All execution results remain pending.

## Accuracy notes (read before slide-building)

1. **Snyk 75.8%**: cite the 2023 AI Code Security Report, not 2024 reprints. Figure is exact.
2. **Alexopoulos**: headline is average ~4 years, NOT median. Do not say "median."
3. **Big Sleep**: use Google's exact hedge ("first public example of an AI agent finding a previously unknown exploitable memory-safety issue in widely used real-world software"), not "first AI-found vuln."
4. **Perry vs Sandoval**: opposite-leaning findings. Keep them distinct; together they justify "measure it yourself."
5. **Vibe Security Radar**: official site is now `https://vibesecradar.com/` and repo is `https://github.com/HQ1995/vibe-security-radar` (307 findings on the page checked Oct 18, 2026, source cutoff Sept 26, 2026). Do not cite the old `vibe-radar-ten.vercel.app` URL.
6. **Contamination section** carries real disagreement (Dozono/Ramos/Li show inflation; Euraste shows low advantage). Present both.
7. **NOT verified, so omitted**: OpenAI "Aardvark" and "swarm of OpenAI agents breached Hugging Face" stories. Do not cite unless separately confirmed.
8. **Stanford AI Index**: 93% agent figure is safe; the code-insecurity percentages circulating under its name are misattributed (they are Veracode's).
9. **Mozilla 271**: say "bugs fixed in one Firefox release", never "271 CVEs" or "271 exploits". Maintainer report, not a recall estimate.
10. **Project Glasswing (Anthropic, May 2026) figures are NOT used on slides**: the 90.6% / 62.4% validation rates are disputed in independent coverage (VulnCheck via CSO Online found one directly attributable CVE), and Anthropic is the vendor of the models in this study. Do not add them.


## Presenter-run MedHallu benchmark

Added October 19, 2026, for slide 15 and the selected references on slide 30. This is separate from the 24-CVE OpenEMR detection study and the proposed eight-question PR workflow.

- **Eric St-Pierre, Medoya, A fast hallucination check that knows when it's unsure**, September 21, 2026. [Article](https://medoya.com/news/jev-model-matches-best-published-llm). Jev 1.13 returned a 228 ms median in an alternating same-session retiming. Reported cost was about $0.03 per 1,000 checks. The four proprietary LLM comparators were slower and more expensive in the reported configurations, with an accuracy tradeoff: Jev scored 92.9%, while the best LLM reached 95.1% with the same question.
- **Results, protocols and reproduction:** [jev-medhallu-benchmark](https://github.com/stperic/jev-medhallu-benchmark), including `bench/datasets/medhallu/PREREGISTRATION.md` and `bench/runs/medhallu/test-llm-authors-question/summary.md`. Timing used a longer LLM prompt than the best-accuracy comparison. GPT-OSS 120b on Cerebras matched Jev's median in a separate same-session follow-up, so the speed comparison is scoped to the four proprietary comparators. MedHallu contains synthetic hallucinations, and no-source checks exposed shortcut signals. Thresholds and calibration do not transfer automatically to PR review.

The completed benchmark supports considering focused judgments for frequent checks. It does not establish the routing accuracy, downstream vulnerability detection or production enforcement of the OpenEMR workflow. No new model calls were made for this presentation update.


## Sources retained from the final presentation review

Speaker notes now contain short speaking cues. The following primary-source links preserve the citations from the detailed preparation notes. The original and stronger prompt templates are included in `outputs/Review-prompt-reference.txt`.

- Slide 2: [Source](https://www.open-emr.org/wiki/index.php/OpenEMR_Cloud_Full_Stack_Data_Sheet).
- Slide 2: [Source](https://www.open-emr.org/releases/).
- Slide 9: [Source](https://docs.typesafe.ai/introduction).
- Slide 9: [Source](https://docs.typesafe.ai/primitives/noul).
- Slide 9: [Source](https://openrouter.ai/docs/guides/community/jev).
- Slide 10: [Source](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents).
- Slide 10: [Source](https://code.claude.com/docs/en/memory).
- Slide 10: [Source](https://code.claude.com/docs/en/skills).
- Slide 10: [Source](https://cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html).
- Slide 10: [Source](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/use-code-review).
- Slide 10: [Source](https://modelcontextprotocol.io/specification/2025-11-25/server/resources).
- Slide 10: [Source](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).
- Slide 18: [Source](https://github.com/ostf-spec/ostf).
- Slides 18, 20: [Source](https://github.com/ostf-spec/ostf/blob/main/scope.md).
- Slide 19: [Source](https://opentelemetry.io/docs/what-is-opentelemetry/).
- Slide 19: [Source](https://opentelemetry.io/docs/concepts/signals/traces/).
- Slide 19: [Source](https://opentelemetry.io/docs/concepts/context-propagation/).
- Slide 19: [Source](https://www.w3.org/TR/trace-context/).
- Slide 19: [Source](https://opentelemetry.io/docs/specs/otel/logs/data-model/).
- Slide 19: [Source](https://opentelemetry.io/docs/concepts/signals/metrics/).
- Slide 19: [Source](https://opentelemetry.io/docs/concepts/sampling/).
- Slide 19: [Source](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md).
- Slide 20: [Source](https://opentelemetry.io/docs/concepts/resources/).
- Slide 20: [Source](https://opentelemetry.io/docs/specs/semconv/registry/attributes/service/).
- Slide 20: [Source](https://opentelemetry.io/docs/specs/semconv/registry/attributes/deployment/).
- Slide 20: [Source](https://opentelemetry.io/docs/specs/otel/trace/api/#link).
- Slide 20: [Source](https://opentelemetry.io/docs/concepts/signals/baggage/#baggage-security-considerations).
- Slide 21: [Source](https://github.com/stperic/openemr-review-gate-demo/actions/runs/39543576669).
- Slides 22, 23: [Source](https://github.com/openemr/openemr/pull/11958).
- Slide 22: [Source](https://aisle.com/blog/aisle-discovers-38-critical-security-vulnerabilities-in-healthcare-software-used-by-100000-providers).
- Slide 35: [Source](https://github.com/stperic/who-writes-who-finds).
- Slide 35: [Source](https://github.com/stperic/openemr-review-gate-demo/blob/main/demo/REVIEW-PACKET.md).
- Slide 37: [Source](https://platform.claude.com/docs/en/models/sonnet-5/overview).
- Slide 37: [Source](https://platform.claude.com/docs/en/models/haiku-4-5/overview).
- Slide 37: [Source](https://support.claude.com/en/articles/8114494-how-up-to-date-is-claude-s-training-data).
