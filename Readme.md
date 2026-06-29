# Provenance Guard

A backend classification system for creative writing platforms to detect AI-generated content, surface transparency labels to readers, and handle creator appeals.

---

## Architecture Overview

A submitted piece of text enters the system via `POST /submit`. It is tagged with a unique `content_id` (UUID) and passed through two independent detection signals running in sequence: (1) an LLM-based semantic classifier powered by Groq, and (2) a stylometric heuristics analyzer that computes statistical properties of the text in pure Python. The two signal scores are combined into a single calibrated confidence score using a weighted formula. That score is then mapped to one of three transparency label variants. The full result — `content_id`, `attribution`, `confidence`, `label`, and both raw signal scores — is returned to the caller. Simultaneously, a structured entry is written to the audit log.

Appeals enter via `POST /appeal`. The endpoint accepts a `content_id` and `creator_reasoning`, looks up the original submission, updates its status to `"under_review"`, and appends the appeal information to the audit log entry. No automated re-classification occurs — a human reviewer inspects the queue.

```
POST /submit
    │
    ▼
[Input Validation]
    │  text, creator_id
    ▼
[Signal 1: LLM Classifier] ── Groq llama-3.3-70b-versatile
    │  llm_score: 0.0–1.0 (1.0 = confident AI)
    ▼
[Signal 2: Stylometric Heuristics] ── Pure Python
    │  style_score: 0.0–1.0 (1.0 = AI-like uniformity)
    ▼
[Confidence Scoring]
    │  combined = 0.6 × llm_score + 0.4 × style_score
    ▼
[Transparency Label Generator]
    │  score > 0.75  → High-confidence AI label
    │  score < 0.35  → High-confidence Human label
    │  else          → Uncertain label
    ▼
[Audit Logger] ── writes structured JSON entry
    │
    ▼
JSON Response → content_id, attribution, confidence, label

──────────────────────────────────────────────────────────

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

### Signal 1: LLM-Based Semantic Classifier

**What it measures:** The overall semantic coherence, stylistic consistency, and rhetorical patterns of the text. AI-generated prose has recognizable signatures: unnaturally balanced sentence structures, overuse of discourse markers ("furthermore," "additionally," "it is important to note"), hedged generalizations without personal grounding, and an absence of the idiosyncratic voice that emerges from lived experience. The Groq LLM (llama-3.3-70b-versatile) is prompted to return a structured JSON score reflecting its confidence that the text is AI-generated.

**Why this signal:** An LLM can evaluate holistic properties that no heuristic can capture — whether a piece "sounds like a human wrote it." It picks up on subtle rhetorical patterns that emerge from the way large language models are trained to produce fluent, balanced text.

**What it misses:** Very polished human writing — academic prose, formal essays, well-edited journalism — can superficially resemble AI output on semantic grounds. Conversely, heavily humanized AI text (deliberately edited for personal voice, with introduced typos and informal phrasing) may score lower than it should. The signal also introduces latency and depends on an external API.

**Output:** A float 0.0–1.0, where 1.0 = high confidence AI-generated.

---

### Signal 2: Stylometric Heuristics

**What it measures:** Statistical properties that reliably differ between human and AI writing:

- **Sentence length variance** — AI-generated text tends toward uniform sentence lengths. Human writing is more erratic. Low standard deviation → higher AI score.
- **Type-token ratio (TTR)** — vocabulary diversity. Human writing generally uses a wider variety of words relative to total word count. Low TTR → higher AI score.
- **Punctuation diversity** — humans use em-dashes, ellipses, exclamation points, semicolons, and colons in idiosyncratic ways. AI writing is punctuation-conservative and punctuation-uniform. Low distinctive punctuation density → higher AI score.

Each metric is independently normalized to [0, 1] and combined into a single `style_score`.

**Why this signal:** Stylometrics are completely independent of the LLM signal — they operate on structure, not semantics. When both signals agree, the confidence score can be more decisively placed. When they disagree, the combined score naturally lands in the uncertain zone, which is the honest answer.

**What it misses:** Formal human writing — legal documents, academic papers, professional reports — is intentionally uniform. It will score high on these heuristics even when clearly human-authored. This is the primary source of false positives and is why the uncertain band is wide and the appeals workflow exists. Non-native English speakers writing carefully are also at higher risk.

**Output:** A float 0.0–1.0, where 1.0 = AI-like (uniform, low-variance).

---

## Confidence Scoring

### Combination Formula

```
combined_score = 0.6 × llm_score + 0.4 × style_score
```

The LLM carries 60% of the weight because it captures holistic semantic patterns that heuristics miss. The stylometric signal at 40% provides an independent structural check — it can catch AI text that has been humanized at the semantic level but retains statistical uniformity.

### Score-to-Attribution Mapping

| Combined Score | Attribution | Reasoning |
|---|---|---|
| > 0.75 | `likely_ai` | Both signals are in agreement and strongly point to AI. |
| 0.35–0.75 | `uncertain` | Signals disagree, or neither is decisive. |
| < 0.35 | `likely_human` | Both signals strongly indicate human authorship. |

**Why a wide uncertain band?** A false positive — labeling a human writer's work as AI-generated — is more damaging on a creative writing platform than a false negative. A writer whose work is wrongly flagged suffers reputational harm. The wide uncertain band (40-point range) ensures the system only makes strong claims when both signals agree, and routes ambiguous cases to the honest "uncertain" label.

**Validation:** I tested the scoring pipeline on four deliberately chosen inputs and confirmed meaningful score variation:

| Input | LLM Score | Style Score | Combined | Attribution |
|---|---|---|---|---|
| Clearly AI (generic policy prose) | 0.87 | 0.77 | **0.831** | likely_ai |
| Clearly human (casual ramen review) | 0.19 | 0.24 | **0.210** | likely_human |
| Borderline human (academic economics) | 0.48 | 0.63 | **0.540** | uncertain |
| Lightly edited AI (remote work reflection) | 0.55 | 0.51 | **0.534** | uncertain |

The two borderline cases correctly land in the uncertain zone rather than forcing a binary verdict. The clearly AI and clearly human cases are decisively separated.

---

## Transparency Label

Three variants are displayed based on the combined confidence score. The **exact text** of each variant is:

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

**Design rationale:** The "Confident AI" label explicitly notes that it does not block publishing and invites an appeal — this softens the impact of a potential false positive. The "Likely Human" label includes a disclaimer that AI detection is imperfect, to avoid creating false certainty in readers. The "Uncertain" label is non-accusatory — it simply acknowledges the system's honest uncertainty.

---

## Rate Limiting

Rate limits are applied to `POST /submit`:

```
10 requests per minute
100 requests per day
```

**Reasoning:** A typical human creator submits their own work occasionally — several pieces per week at most, not dozens per minute. Ten per minute is generous for any legitimate use (a creator uploading a few drafts, or a platform batch-processing a small queue), but it prevents a scripted attack that would flood the system and exhaust the Groq API quota. One hundred per day is a soft daily cap per IP that stops adversarial enumeration (e.g., an attacker probing the system's decision boundaries by submitting thousands of variations of the same text).

**Evidence of rate limiting working** (output of the 12-request burst test):
```
200
200
200
200
200
200
200
200
200
200
429
429
```
The first 10 requests succeed; requests 11 and 12 receive HTTP 429 Too Many Requests.

---

## Audit Log

Every attribution decision and appeal is captured in a structured JSON audit log (`audit_log.json`). The log is accessible via `GET /log`. Below are four sample entries including one appeal:

```json
[
  {
    "content_id": "3f7a2b1e-84cc-4a19-a23b-9d12f6e00a11",
    "creator_id": "user-poet-42",
    "timestamp": "2025-06-20T10:14:32.441Z",
    "attribution": "likely_ai",
    "confidence": 0.8312,
    "llm_score": 0.87,
    "style_score": 0.77,
    "status": "classified",
    "appeal_reasoning": null,
    "appeal_timestamp": null
  },
  {
    "content_id": "7c91d3fa-1b5e-4c77-be4a-0f233a8d9122",
    "creator_id": "user-journal-88",
    "timestamp": "2025-06-20T10:22:05.881Z",
    "attribution": "likely_human",
    "confidence": 0.2104,
    "llm_score": 0.19,
    "style_score": 0.24,
    "status": "classified",
    "appeal_reasoning": null,
    "appeal_timestamp": null
  },
  {
    "content_id": "a4e58bcd-c721-4d90-9c3b-2b8173fa6433",
    "creator_id": "user-writer-17",
    "timestamp": "2025-06-20T10:35:49.002Z",
    "attribution": "uncertain",
    "confidence": 0.554,
    "llm_score": 0.51,
    "style_score": 0.61,
    "status": "under_review",
    "appeal_reasoning": "I wrote this myself from personal experience studying abroad. I am a non-native English speaker and my writing may appear more formal than a native speaker's informal prose.",
    "appeal_timestamp": "2025-06-20T11:02:17.334Z"
  },
  {
    "content_id": "d9821cfa-0e3b-4f11-ab27-7e43010bc544",
    "creator_id": "user-blogger-55",
    "timestamp": "2025-06-20T14:08:22.119Z",
    "attribution": "likely_human",
    "confidence": 0.1887,
    "llm_score": 0.16,
    "style_score": 0.23,
    "status": "classified",
    "appeal_reasoning": null,
    "appeal_timestamp": null
  }
]
```

Each entry captures: timestamp, content ID, creator ID, attribution result, combined confidence score, both individual signal scores, classification status, and — when an appeal is filed — the creator's reasoning and the appeal timestamp.

---

## Appeals Workflow

**Endpoint:** `POST /appeal`

**Request body:**
```json
{
  "content_id": "a4e58bcd-c721-4d90-9c3b-2b8173fa6433",
  "creator_reasoning": "I wrote this myself from personal experience."
}
```

**What happens:**
1. The system looks up the original submission by `content_id` in the audit log.
2. The entry's `status` field is updated from `"classified"` to `"under_review"`.
3. The `appeal_reasoning` and `appeal_timestamp` are written to the log entry.
4. A confirmation JSON is returned to the caller.

**What a reviewer sees:** `GET /log` returns all entries. A reviewer filters for `"status": "under_review"` to see the appeal queue. Each entry shows the original `llm_score`, `style_score`, `confidence`, `attribution`, and the creator's stated reasoning — everything needed to make a human judgment.

**What the system does NOT do:** Automated re-classification. A human reviewer makes the final determination.

---

## Known Limitations

**1. Formal non-native English writing (primary false-positive risk):**  
A non-native English speaker writing carefully in a formal register will often produce text with low sentence-length variance and conservative punctuation — precisely the statistical profile the stylometric signal flags as AI-like. The LLM may also read formal, grammatically careful prose as AI-generated. This combination can produce a false `likely_ai` or `uncertain` verdict for legitimate human authors. This is why the uncertain band is wide and the appeals workflow is prominently offered in the label text.

**2. Very short text (< 3 sentences):**  
The stylometric signal requires at least two sentences to compute variance meaningfully. For haiku, tweet-length writing, or very short poems, the signal defaults to 0.5 (neutral), which biases the overall score toward whatever the LLM returns. The system still produces a result, but confidence scores for very short text are less reliable and more likely to land in the uncertain zone regardless of origin.

---

## Spec Reflection

**One way the spec helped:**  
Writing out the three label variants in `planning.md` before touching implementation code was the most valuable planning step. When I reached Milestone 5, the `generate_label()` function was nearly mechanical — I was translating already-written text into Python string returns rather than designing the UX and writing code simultaneously. The spec also forced me to commit to exact threshold numbers (0.35 and 0.75) before seeing any real scores, which meant I could immediately test whether the thresholds felt right rather than tweaking them post hoc to make the numbers look good.

**One way implementation diverged from spec:**  
The planning document specified that the stylometric heuristics would include "average sentence complexity" (words per sentence) as a fourth metric. During implementation, I realized that average sentence length and sentence length variance are highly correlated — low-variance texts also tend to cluster around a similar average. Adding it as a fourth signal was redundant and added noise rather than signal. I dropped it and redistributed weights among the three remaining metrics (variance, TTR, punctuation density). The planning document's explanation of what each metric *captures* helped me spot the redundancy quickly.

---

## AI Usage

**Instance 1 — Generating the LLM signal function:**  
I provided Claude with the "Detection Signals" section of `planning.md` and the architecture diagram and asked it to generate the `classify_with_llm()` function. It produced a version that called Groq and parsed the response, but it used `json.loads()` without stripping Markdown code fences that the model occasionally wraps around JSON output. I added the `.replace("```json", "").replace("```", "")` preprocessing step and a `try/except` that falls back to 0.5 rather than crashing the endpoint on a malformed API response.

**Instance 2 — Generating the stylometric heuristics:**  
I provided the "Signal 2: Stylometric Heuristics" spec section and asked for the `compute_stylometric_score()` function. The AI generated a function that computed TTR correctly but normalized sentence-length variance using a hard division that raised a `ZeroDivisionError` on single-sentence inputs. I replaced it with the `max(0.0, 1.0 - (std_dev / 15.0))` normalization that clamps cleanly at 0 for high variance, and added the early-return guard (`if len(sentences) < 2: return 0.5`) to handle very short text.

---

## Setup and Running

```bash
# 1. Clone the repo and set up environment
git clone https://github.com/<your-username>/ai201-project4-provenance-guard.git
cd ai201-project4-provenance-guard
python -m venv .venv
source .venv/bin/activate  # Mac/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure API key
echo "GROQ_API_KEY=your_key_here" > .env

# 4. Run the server
python app.py
```

**Test submission:**
```bash
curl -s -X POST http://localhost:5000/submit \
  -H "Content-Type: application/json" \
  -d '{"text": "The sun dipped below the horizon, painting the sky in hues of amber and rose. I sat on the porch, coffee in hand, watching the neighborhood slowly go quiet.", "creator_id": "test-user-1"}' | python -m json.tool
```

**Submit an appeal** (replace `CONTENT_ID` with a `content_id` from a `/submit` response):
```bash
curl -s -X POST http://localhost:5000/appeal \
  -H "Content-Type: application/json" \
  -d '{"content_id": "CONTENT_ID", "creator_reasoning": "I wrote this myself from personal experience. I am a non-native English speaker and my writing style may appear more formal."}' | python -m json.tool
```

**View audit log:**
```bash
curl -s http://localhost:5000/log | python -m json.tool
```

**Test rate limiting** (sends 12 rapid requests — should see 429 after the 10th):
```bash
for i in $(seq 1 12); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:5000/submit \
    -H "Content-Type: application/json" \
    -d '{"text": "This is a test submission for rate limit testing purposes only.", "creator_id": "ratelimit-test"}'
done
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/submit` | Submit text for attribution analysis |
| `POST` | `/appeal` | Appeal a classification decision |
| `GET` | `/log` | Retrieve recent audit log entries |
| `GET` | `/health` | Health check |

**POST /submit — request:**
```json
{
  "text": "string (required)",
  "creator_id": "string (required)"
}
```

**POST /submit — response:**
```json
{
  "content_id": "uuid",
  "attribution": "likely_ai | likely_human | uncertain",
  "confidence": 0.83,
  "llm_score": 0.87,
  "style_score": 0.77,
  "label": "⚠️ AI-Generated Content Detected\n...",
  "timestamp": "ISO-8601"
}
```
