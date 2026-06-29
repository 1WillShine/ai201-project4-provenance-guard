# Provenance Guard — Planning Document

## Architecture Narrative

A submitted piece of text enters the system via `POST /submit`. It is tagged with a unique `content_id` (UUID) and routed through two independent detection signals: (1) an LLM-based semantic classifier powered by Groq, and (2) a stylometric heuristics analyzer that computes statistical properties of the text. The two signal scores are combined into a single calibrated confidence score, which is then mapped to one of three transparency label variants. The result — `content_id`, `attribution`, `confidence`, and `label` — is returned to the caller, and a structured entry is written to the audit log simultaneously.

Appeals enter via `POST /appeal`. The endpoint looks up the original submission by `content_id`, records the creator's reasoning, updates the status to `"under_review"`, and appends an appeal entry to the audit log. No automated re-classification is performed — a human reviewer would inspect the queue.

## Architecture

```
POST /submit
    │
    ▼
[Input Validation]
    │  text, creator_id
    ▼
[Signal 1: LLM Classifier] ──── Groq llama-3.3-70b-versatile
    │  llm_score: 0.0–1.0 (1.0 = confident AI)
    ▼
[Signal 2: Stylometric Heuristics] ── Pure Python
    │  style_score: 0.0–1.0 (1.0 = AI-like uniformity)
    ▼
[Confidence Scoring]
    │  combined_score = 0.6 * llm_score + 0.4 * style_score
    ▼
[Transparency Label Generator]
    │  score > 0.75  → "High-confidence AI" label
    │  score < 0.35  → "High-confidence Human" label
    │  else          → "Uncertain" label
    ▼
[Audit Logger] ── writes structured JSON entry
    │
    ▼
JSON Response → content_id, attribution, confidence, label

──────────────────────────────────────────────────

POST /appeal
    │
    ▼
[Lookup content_id in log]
    │
    ▼
[Update status → "under_review"]
    │
    ▼
[Audit Logger] ── appends appeal entry with reasoning
    │
    ▼
JSON Response → confirmation + updated status
```

---

## Detection Signals

### Signal 1: LLM-Based Semantic Classifier (Groq)

**What it measures:** The overall coherence, stylistic consistency, and semantic patterns of the text. LLMs are sensitive to the "flavor" of AI-generated prose: balanced sentence structures, hedged language ("it is important to note that"), overuse of discourse markers ("furthermore," "additionally"), and an absence of idiosyncratic personal voice.

**Output:** A float between 0.0 and 1.0, where 1.0 = high confidence the text is AI-generated. The model is prompted to return a JSON object with a single `score` field.

**Blind spot:** This signal can be fooled by highly polished human writing (academic prose, formal essays) which can superficially resemble AI output. Conversely, heavily edited AI text that has been humanized may score low.

---

### Signal 2: Stylometric Heuristics (Pure Python)

**What it measures:** Statistical properties that differ between human and AI writing:
- **Sentence length variance** — AI text tends to produce sentences of similar length; human writing is more erratic.
- **Type-token ratio (TTR)** — vocabulary diversity. AI text can be wordy but repetitive; high TTR suggests human variety.
- **Punctuation density** — humans use em-dashes, ellipses, fragments; AI text is punctuation-conservative.
- **Average sentence complexity** (words per sentence) — AI averages a sweet spot; very short or very long sentences suggest human.

Each metric is normalized to [0, 1] and averaged into a single `style_score`, where 1.0 = AI-like (uniform, low-variance, low punctuation diversity).

**Output:** A float between 0.0 and 1.0.

**Blind spot:** Formal human writing (legal documents, academic papers) will score as AI-like on these heuristics because it is intentionally uniform. A non-native English speaker writing carefully may also score high. This is exactly the false-positive scenario we care most about — hence the appeals workflow and the asymmetric label thresholds.

---

## Uncertainty Representation

| Combined Score | Meaning | Label Variant |
|---|---|---|
| > 0.75 | Confident the content is AI-generated | High-confidence AI |
| 0.35 – 0.75 | System cannot reliably distinguish | Uncertain |
| < 0.35 | Confident the content is human-written | High-confidence Human |

**Why these thresholds?** A false positive (labeling a human's work as AI) is worse than a false negative on a creative writing platform. The uncertain band is therefore wide (0.35–0.75 = a 40-point range) to catch borderline cases and send them to the uncertain label rather than risking a damaging false accusation.

A confidence of 0.60 means the system leans AI but not strongly — the uncertain label is shown, and the creator can appeal without stigma.

**Combining signals:** `combined = 0.6 * llm_score + 0.4 * style_score`. The LLM signal is weighted higher because it captures semantic patterns that heuristics miss, but the stylometric signal provides an independent structural check.

---

## Transparency Label Design

### Variant 1: High-Confidence AI (score > 0.75)

```
⚠️ AI-Generated Content Detected
Our system has analyzed this submission and found strong indicators that it was
generated by an AI writing tool rather than written by a human.
Confidence: [X]% | Signals: Semantic patterns, Writing style analysis
This label does not block publishing. If you believe this is incorrect,
you can submit an appeal — our team will review your submission personally.
```

### Variant 2: High-Confidence Human (score < 0.35)

```
✅ Likely Human-Written
Our system analyzed this submission and found strong indicators of authentic
human authorship — varied sentence structure, natural voice, and organic style.
Confidence: [X]% | Signals: Semantic patterns, Writing style analysis
AI detection is not perfect. This label reflects our best assessment, not a guarantee.
```

### Variant 3: Uncertain (score 0.35–0.75)

```
🔍 Authorship Uncertain
Our system could not confidently determine whether this content was written by
a human or generated by AI. It shows a mix of signals.
Confidence: [X]% | Signals: Semantic patterns, Writing style analysis
This content will be displayed without an authorship badge. If you are the
human author, you can submit an appeal to have your work reviewed.
```

---

## Appeals Workflow

- **Who can appeal:** Any creator who submitted the content (identified by `creator_id`).
- **What they provide:** `content_id` (from their original submission response) + `creator_reasoning` (free text explanation, e.g., "I wrote this myself; I am a non-native English speaker").
- **What the system does:**
  1. Looks up the original log entry by `content_id`.
  2. Updates the entry's `status` field from `"classified"` to `"under_review"`.
  3. Appends the `appeal_reasoning` and `appeal_timestamp` to the log entry.
  4. Returns a confirmation JSON to the caller.
- **What a human reviewer sees:** The `/log` endpoint returns all entries including appealed ones. Entries with `status: "under_review"` are the appeal queue. The reviewer sees the original scores, both signal values, the label, and the creator's stated reasoning.
- **What the system does NOT do:** Automated re-classification. A human makes the final call.

---

## Anticipated Edge Cases

1. **Formal non-native English writing:** A careful non-native speaker writing in a formal register produces text with low sentence-length variance and simple vocabulary — exactly what the stylometric heuristics flag as AI-like. This is the primary false-positive risk. Mitigation: the wide uncertain band (0.35–0.75) and the appeals workflow.

2. **Lightly edited AI output:** A user generates AI text, then manually edits it for voice and introduces typos, contractions, and idiosyncratic phrasing. The stylometric signal may drop significantly while the LLM semantic signal remains moderate. Combined, these borderline cases land in the uncertain zone — which is the correct honest answer.

3. **Very short text (< 3 sentences):** Stylometric metrics become unreliable with fewer than 3 sentences — variance calculations need a sample. The system should still return a result but the confidence score will naturally be lower (the stylometric component has less signal), biasing toward the uncertain label.

4. **Highly technical/domain-specific content:** Code snippets, legal boilerplate, or medical documentation have structural uniformity that resembles AI prose but is domain-mandated. These will likely score high on stylometrics even when human-authored.

---

## AI Tool Plan

### M3: Submission Endpoint + Signal 1
- **Sections provided to AI:** Detection signals section + architecture diagram
- **Ask AI to generate:** Flask app skeleton with `POST /submit` route stub + the `classify_with_llm()` function that calls Groq and returns a 0–1 score
- **Verification:** Call `classify_with_llm()` directly on 3 test strings before wiring into the endpoint. Confirm it returns a float, not a dict or string.

### M4: Signal 2 + Confidence Scoring
- **Sections provided:** Detection signals + uncertainty representation + diagram
- **Ask AI to generate:** `compute_stylometric_score()` function computing sentence variance, TTR, and punctuation density + `combine_scores()` logic using the 60/40 weighting
- **Verification:** Test both signals on the 4 sample inputs from the spec (clearly AI, clearly human, two borderline). Log both raw scores before combining. Ensure the final combined score produces all 3 label variants when tested on appropriate inputs.

### M5: Production Layer
- **Sections provided:** Label variants + appeals workflow + diagram
- **Ask AI to generate:** `generate_label()` function mapping score ranges to label text + `POST /appeal` endpoint
- **Verification:** Submit inputs targeting each of the 3 confidence zones. Confirm label text matches spec exactly. Submit an appeal with a valid `content_id` and verify `GET /log` shows `status: "under_review"` and `appeal_reasoning` populated.

---

## Stretch Features Considered

- **Ensemble detection (3+ signals):** Would add a perplexity-based signal using a local n-gram model. Deferred — would require significant additional setup time.
- **Provenance certificate:** Interesting UX problem. Would require a separate verification endpoint and credential store. Deferred.
