# Theo Technical Documentation

## How PII Detection Works

Theo's PII detection has **3 layers**:

1. **Microsoft Presidio** - Core NLP-based entity recognition
2. **Custom Pattern Recognizers** - Regex patterns for conversational PII
3. **Profile Building & Inference** - Aggregation and AI-powered insights

---

## Layer 1: Microsoft Presidio (Core Engine)

Presidio is Microsoft's open-source PII detection library. When you initialize `AnalyzerEngine()` in `core/pii_analyzer.py:217`, it automatically loads:

### Built-in Recognizers

| Type | How It Works |
|------|--------------|
| **SpacyRecognizer** | Uses spaCy's `en_core_web_lg` NLP model for Named Entity Recognition (NER). Detects `PERSON`, `LOCATION`, `DATE_TIME`, `NRP` (nationality/religion/political group) |
| **Pattern Recognizers** | Regex + checksum validation for structured data: credit cards (Luhn algorithm), SSNs, phone numbers, emails, IBANs, etc. |
| **Context Enhancers** | Boosts confidence when contextual words appear nearby (e.g., "my phone number is" before digits) |

### How spaCy NER Works

When you type "My name is John and I live in Schenectady":

1. **Tokenization**: Text is split into tokens: `["My", "name", "is", "John", "and", "I", "live", "in", "Schenectady"]`
2. **Part-of-speech tagging**: Each word is tagged (noun, verb, proper noun, etc.)
3. **Dependency parsing**: Grammatical relationships are mapped
4. **NER classification**: The neural network (trained on OntoNotes 5.0 corpus) classifies spans:
   - "John" → `PERSON` (confidence ~0.85)
   - "Schenectady" → `GPE` (geopolitical entity) → mapped to `LOCATION`

---

## Layer 2: Custom Pattern Recognizers

Presidio doesn't detect conversational PII like "I'm a college student". Theo adds 5 custom recognizers using **regex patterns** with confidence scores.

### Education Recognizer

**File**: `core/pii_analyzer.py:85-106`

```python
Pattern(
    "education_student",
    r"\b(college|university|high school|grad|graduate|undergraduate|"
    r"freshman|sophomore|junior|senior|PhD|masters|bachelor|associate)\s*"
    r"(student|degree|program)?\b",
    0.7  # 70% confidence
)
```

**Matches**: "college student", "PhD program", "undergraduate", "freshman"

**How it works**:
- `\b` = word boundary (prevents matching "colleague")
- `(...)` = capture group with alternatives separated by `|`
- `\s*` = optional whitespace
- `?` = optional second word ("student", "degree", etc.)
- `0.7` = confidence score assigned when pattern matches

### Age Recognizer

**File**: `core/pii_analyzer.py:159-184`

```python
Pattern(
    "explicit_age",
    r"\b(I am|I\'m|I was|turned|turning)\s*\d{1,3}\s*(years old|year old|yo)?\b",
    0.85  # 85% confidence - very specific pattern
)
```

**Matches**: "I am 25", "I'm 21 years old", "turned 30"

**Higher confidence (0.85)** because this pattern is very specific and unlikely to false-positive.

### Occupation Recognizer

**File**: `core/pii_analyzer.py:109-132`

Two patterns with different confidences:
- **Job titles** (0.6): "engineer", "doctor", "CEO"
- **Work context** (0.5): "work at", "employed by" - lower because it needs more context

### Relationship Recognizer

**File**: `core/pii_analyzer.py:135-156`

**Matches**: "my husband", "wife", "married", "divorced"

### Health Recognizer

**File**: `core/pii_analyzer.py:187-209`

```python
Pattern(
    "health_condition",
    r"\b(diagnosed with|suffering from|have|had)\s+"
    r"(diabetes|cancer|asthma|depression|anxiety|ADHD|...)\b",
    0.8
)
```

**Matches**: "diagnosed with diabetes", "have depression"

---

## Layer 3: Analysis Flow

When you send a message, here's the complete flow:

### Step 1: Analyze Text

**File**: `core/pii_analyzer.py:231-268`

```python
results = self.analyzer.analyze(
    text=text,
    entities=None,  # Detect ALL entity types
    language='en'
)
```

Presidio runs **all recognizers** (built-in + custom) and returns a list of `RecognizerResult` objects:

```python
RecognizerResult(
    entity_type='LOCATION',
    start=22,           # Character position in text
    end=33,
    score=0.85          # Confidence 0.0-1.0
)
```

### Step 2: Filter by Confidence Threshold

```python
confidence_threshold: float = 0.4  # Default threshold

for result in results:
    if result.score >= confidence_threshold:
        # Include this entity
```

**Why 0.4?** Lower threshold catches more PII but may have false positives. Higher threshold (0.6+) is more precise but may miss things.

### Step 3: Convert to PIIEntity

```python
entity = PIIEntity(
    text=text[result.start:result.end],  # Extract actual text
    entity_type=result.entity_type,
    score=result.score,
    start=result.start,
    end=result.end,
    color=COLOR_GUIDE.get(result.entity_type, DEFAULT_COLOR),
    message_index=message_index  # Which message in conversation
)
```

The `COLOR_GUIDE` dictionary (`core/pii_analyzer.py:14-79`) assigns a unique color to each entity type for UI highlighting.

---

## Layer 4: Profile Building

**File**: `core/profile_builder.py`

### Categorization

Entities are grouped into **12 categories** via `ENTITY_CATEGORIES` mapping:

```python
"PERSON": "identity",
"LOCATION": "location",
"EDUCATION_LEVEL": "education",
"OCCUPATION": "employment",
# etc.
```

### Deduplication

```python
self.profile.categories[category].unique_values.add(
    entity.text.lower().strip()  # Normalize: "John" and "john" → "john"
)
```

This prevents counting "Schenectady" twice if mentioned in multiple messages.

### Identifiability Score

**File**: `core/profile_builder.py:192-238`

The score (0-100) is calculated with:

**1. Category Weights:**
```python
weights = {
    "identity": 25,      # Names are highly identifying
    "government_id": 30, # SSN, passport = very identifying
    "contact": 20,       # Email, phone
    "location": 15,      # Narrows down geography
    "employment": 10,    # Job info
    "education": 10,     # School info
    # ...
}
```

**2. Diminishing Returns:**
```python
category_score = weight * min(unique_count, 3) / 3
```
Having 10 locations isn't 10x more identifying than having 1.

**3. Combination Bonuses:**
```python
if has_location and has_education:
    score += 10  # "College student in Schenectady" is very specific
if has_name and has_location:
    score += 15  # "John from Schenectady" narrows significantly
```

---

## Layer 5: AI Inference

**File**: `core/inference_engine.py`

### Context Generation

The `ProfileBuilder.get_inference_context()` creates a formatted string:

```
- Location: schenectady
- Education: college student
- Demographics: 21 years old
```

### OpenAI Prompt

**File**: `core/inference_engine.py:11-29`

```
You are a privacy analyst helping users understand what can be inferred...

Given the following pieces of personal information:
{pii_context}

Please analyze what additional information can be inferred...
- Likely identifiers: Specific schools, employers...
- Focus on how pieces COMBINE to reveal more than individually
```

### The "Aha" Moment

The AI might respond:

> "A college student aged 21 living in Schenectady, NY strongly suggests enrollment at **Union College** - a small liberal arts college that is the primary higher education institution in that city. Combined with the age, this person is likely a junior or senior. The small student body (~2,200) makes them potentially identifiable to anyone familiar with the school."

This is the core value of Theo: showing how **individually harmless information combines** to become highly identifying.

---

## Complete Data Flow Diagram

```
User Input: "I'm a 21 year old college student in Schenectady"
                    ↓
┌─────────────────────────────────────────────────────────┐
│                    PIIAnalyzer                          │
│  ┌─────────────────┐   ┌──────────────────────────┐    │
│  │ Presidio Engine │   │ Custom Recognizers       │    │
│  │ - SpacyNER      │   │ - Education (regex)      │    │
│  │ - Patterns      │   │ - Age (regex)            │    │
│  └────────┬────────┘   └────────────┬─────────────┘    │
│           │                          │                  │
│           └──────────┬───────────────┘                  │
│                      ↓                                  │
│         [LOCATION: Schenectady, 0.85]                   │
│         [EDUCATION_LEVEL: college student, 0.7]         │
│         [AGE: 21 year old, 0.85]                        │
└─────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│                  ProfileBuilder                         │
│  Categories:                                            │
│  - location: {schenectady}                              │
│  - education: {college student}                         │
│  - demographics: {21 year old}                          │
│                                                         │
│  Identifiability Score: 35 + 10 (combo bonus) = 45      │
└─────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│                  InferenceEngine                        │
│  OpenAI analyzes combinations →                         │
│  "Likely Union College student, junior/senior year"     │
└─────────────────────────────────────────────────────────┘
```

---

## File Reference

| File | Purpose |
|------|---------|
| `core/pii_analyzer.py` | Presidio wrapper + custom recognizers |
| `core/session_manager.py` | In-memory conversation storage |
| `core/profile_builder.py` | PII categorization and scoring |
| `core/inference_engine.py` | OpenAI integration for inference |
| `server.py` | Flask API endpoints |
| `templates/index.html` | Chat UI with highlighting |

---

## Supported Entity Types

### From Presidio (Built-in)

| Entity | Example |
|--------|---------|
| `PERSON` | "John Smith" |
| `LOCATION` | "New York", "Schenectady" |
| `PHONE_NUMBER` | "555-123-4567" |
| `EMAIL_ADDRESS` | "john@example.com" |
| `CREDIT_CARD` | "4111-1111-1111-1111" |
| `US_SSN` | "123-45-6789" |
| `DATE_TIME` | "January 15, 2024" |
| `IP_ADDRESS` | "192.168.1.1" |
| `IBAN_CODE` | "DE89370400440532013000" |
| `URL` | "https://example.com" |

### Custom (Theo-specific)

| Entity | Example |
|--------|---------|
| `EDUCATION_LEVEL` | "college student", "PhD program" |
| `OCCUPATION` | "engineer", "work at Google" |
| `RELATIONSHIP` | "my husband", "married" |
| `AGE` | "I'm 25 years old" |
| `HEALTH_CONDITION` | "diagnosed with diabetes" |

---

## Confidence Scores

| Score Range | Meaning |
|-------------|---------|
| 0.85 - 1.0 | High confidence (specific patterns, NER matches) |
| 0.6 - 0.84 | Medium confidence (good pattern match) |
| 0.4 - 0.59 | Low confidence (partial match, context-dependent) |
| < 0.4 | Filtered out (below threshold) |

The default threshold of **0.4** balances catching PII vs. avoiding false positives.
