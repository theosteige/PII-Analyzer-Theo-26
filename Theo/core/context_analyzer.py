"""
Context Analyzer for Theo - Cross-Message PII Detection
Detects PII connections across conversation messages using coreference
resolution (fastcoref) and LLM-based contextual analysis (GPT-4o-mini).
"""

import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class WarningType(Enum):
    COREFERENCE = "coreference"
    RETROACTIVE = "retroactive"
    COMBINATORIAL = "combinatorial"
    DISAMBIGUATION = "disambiguation"


class WarningSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class CorefMention:
    text: str
    message_index: int
    start: int
    end: int


@dataclass(frozen=True)
class CorefChain:
    mentions: Tuple[CorefMention, ...]
    resolved_entity: str
    entity_type: str


@dataclass(frozen=True)
class CrossMessagePII:
    warning_type: WarningType
    description: str
    involved_messages: Tuple[int, ...]
    revealed_info: str
    severity: WarningSeverity
    confidence: float


@dataclass(frozen=True)
class ContextWarning:
    warning_type: WarningType
    severity: WarningSeverity
    title: str
    description: str
    involved_messages: Tuple[int, ...]
    source_texts: Tuple[str, ...]
    confidence: float

    def to_dict(self) -> dict:
        return {
            "warning_type": self.warning_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "involved_messages": list(self.involved_messages),
            "source_texts": list(self.source_texts),
            "confidence": self.confidence,
        }


CROSS_MESSAGE_SYSTEM_PROMPT = (
    "You are a privacy analyst that detects cross-message PII connections. "
    "Respond ONLY with a JSON array. No markdown, no explanation, just valid JSON."
)

CROSS_MESSAGE_USER_PROMPT = """Analyze these conversation messages for cross-message PII connections.

MESSAGES (indexed from 0):
{messages_block}

DRAFT MESSAGE (not yet sent):
{draft}

ALREADY DETECTED PII (per-message):
{pii_summary}

Find ONLY cross-message interactions where information from different messages combines to reveal more than each message alone. Look for:

1. RETROACTIVE: A later message makes an earlier vague reference identifiable (e.g., "the river" + "Go Union!" = Mohawk River near Union College)
2. COMBINATORIAL: Multiple pieces across messages narrow identity (e.g., "college student" + "Schenectady" + "engineering major" = likely Union College)
3. DISAMBIGUATION: A vague reference becomes specific through context from other messages (e.g., "my doctor" + "Albany Med" = specific hospital)

Do NOT flag things already caught by per-message PII detection.
Do NOT flag connections within a single message.
Focus on how the DRAFT message creates NEW connections with previous messages.

Return a JSON array of findings:
[
  {{
    "warning_type": "retroactive" | "combinatorial" | "disambiguation",
    "severity": "low" | "medium" | "high",
    "title": "Short title (max 60 chars)",
    "description": "What combining these messages reveals",
    "involved_message_indices": [0, 3],
    "source_quotes": ["quote from msg 0", "quote from msg 3"],
    "confidence": 0.85
  }}
]

Return [] if no cross-message connections found."""


class ContextAnalyzer:
    """Analyzes cross-message PII connections using coreference resolution and LLM."""

    def __init__(self, openai_client=None):
        self._openai_client = openai_client
        self._coref_model = None
        self._coref_available = None

    def _get_coref_model(self):
        """Lazy-load the FCoref model on first use."""
        if self._coref_available is False:
            return None

        if self._coref_model is not None:
            return self._coref_model

        try:
            from fastcoref import FCoref
            self._coref_model = FCoref(device="cpu")
            self._coref_available = True
            logger.info("fastcoref model loaded successfully")
            return self._coref_model
        except Exception as e:
            logger.warning(f"fastcoref unavailable, skipping coreference: {e}")
            self._coref_available = False
            return None

    def resolve_coreferences(
        self,
        messages: List[str],
        draft: str,
    ) -> List[CorefChain]:
        """Run coreference resolution across messages + draft.

        Concatenates messages with boundary markers, runs fastcoref,
        then maps spans back to per-message offsets.

        Returns chains that span multiple messages or involve the draft.
        """
        model = self._get_coref_model()
        if model is None:
            return []

        # Build concatenated text with boundary tracking
        boundaries = []  # (start_char, end_char, message_index)
        parts = []
        offset = 0
        all_texts = list(messages) + [draft]

        for idx, text in enumerate(all_texts):
            start = offset
            parts.append(text)
            offset += len(text)
            boundaries.append((start, offset, idx))
            # Add separator between messages
            if idx < len(all_texts) - 1:
                parts.append(" ")
                offset += 1

        full_text = "".join(parts)
        draft_index = len(messages)  # draft is the last "message"

        try:
            preds = model.predict(texts=[full_text])
            clusters = preds[0].get_clusters(as_strings=False)
            clusters_text = preds[0].get_clusters(as_strings=True)
        except Exception as e:
            logger.warning(f"Coreference resolution failed: {e}")
            return []

        chains = []
        for cluster_spans, cluster_strings in zip(clusters, clusters_text):
            mentions = []
            for (span_start, span_end), span_text in zip(cluster_spans, cluster_strings):
                # Find which message this span belongs to
                msg_idx = None
                local_start = span_start
                for b_start, b_end, b_idx in boundaries:
                    if b_start <= span_start < b_end:
                        msg_idx = b_idx
                        local_start = span_start - b_start
                        break

                if msg_idx is None:
                    continue

                mentions.append(CorefMention(
                    text=span_text,
                    message_index=msg_idx,
                    start=local_start,
                    end=local_start + len(span_text),
                ))

            # Only keep chains that span multiple messages or involve draft
            message_indices = {m.message_index for m in mentions}
            spans_multiple = len(message_indices) > 1
            involves_draft = draft_index in message_indices

            if spans_multiple or involves_draft:
                canonical = self._pick_canonical_mention(
                    [m.text for m in mentions]
                )
                chains.append(CorefChain(
                    mentions=tuple(mentions),
                    resolved_entity=canonical,
                    entity_type="COREFERENCE",
                ))

        return chains

    def _pick_canonical_mention(self, strings: List[str]) -> str:
        """Pick the best canonical name from a list of coreferent mentions.

        Heuristic: longest non-pronoun mention.
        """
        pronouns = {
            "i", "me", "my", "mine", "myself",
            "you", "your", "yours", "yourself",
            "he", "him", "his", "himself",
            "she", "her", "hers", "herself",
            "it", "its", "itself",
            "we", "us", "our", "ours", "ourselves",
            "they", "them", "their", "theirs", "themselves",
            "this", "that", "these", "those",
            "who", "whom", "whose", "which",
        }

        non_pronoun = [
            s for s in strings if s.lower().strip() not in pronouns
        ]
        candidates = non_pronoun if non_pronoun else strings

        return max(candidates, key=len)

    def analyze_cross_message_pii(
        self,
        messages: List[str],
        draft: str,
        existing_pii_summary: str,
    ) -> List[dict]:
        """Use LLM to find cross-message PII connections.

        Returns parsed JSON findings filtered by confidence > 0.5.
        """
        if not self._openai_client:
            return []

        if not messages:
            return []

        messages_block = "\n".join(
            f"[{i}] {msg}" for i, msg in enumerate(messages)
        )

        prompt = CROSS_MESSAGE_USER_PROMPT.format(
            messages_block=messages_block,
            draft=draft,
            pii_summary=existing_pii_summary or "None detected",
        )

        try:
            response = self._openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": CROSS_MESSAGE_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=1000,
            )

            raw = response.choices[0].message.content.strip()

            # Strip markdown code fences if present
            if raw.startswith("```"):
                lines = raw.split("\n")
                lines = lines[1:]  # remove opening fence
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                raw = "\n".join(lines)

            findings = json.loads(raw)

            if not isinstance(findings, list):
                return []

            return [
                f for f in findings
                if isinstance(f, dict) and f.get("confidence", 0) > 0.5
            ]

        except Exception as e:
            logger.warning(f"Cross-message LLM analysis failed: {e}")
            return []

    def generate_warnings(
        self,
        coref_chains: List[CorefChain],
        cross_message_results: List[dict],
        direct_pii_entities: List[str],
    ) -> List[ContextWarning]:
        """Merge coreference and LLM findings into deduplicated ContextWarnings.

        Sorted by severity (HIGH first) then confidence (descending).
        """
        warnings = []

        # Convert coreference chains to warnings
        for chain in coref_chains:
            msg_indices = tuple(sorted({m.message_index for m in chain.mentions}))
            source_texts = tuple(dict.fromkeys(m.text for m in chain.mentions))

            # Skip if the resolved entity is already detected by direct PII
            entity_lower = chain.resolved_entity.lower()
            already_detected = any(
                entity_lower in pii.lower() or pii.lower() in entity_lower
                for pii in direct_pii_entities
            )

            if len(msg_indices) > 1:
                warnings.append(ContextWarning(
                    warning_type=WarningType.COREFERENCE,
                    severity=WarningSeverity.MEDIUM if not already_detected else WarningSeverity.LOW,
                    title=f"Linked reference: \"{chain.resolved_entity}\"",
                    description=(
                        f"References across messages {list(msg_indices)} "
                        f"resolve to \"{chain.resolved_entity}\". "
                        f"This links information from multiple messages."
                    ),
                    involved_messages=msg_indices,
                    source_texts=source_texts,
                    confidence=0.75,
                ))

        # Convert LLM findings to warnings
        severity_map = {
            "low": WarningSeverity.LOW,
            "medium": WarningSeverity.MEDIUM,
            "high": WarningSeverity.HIGH,
        }
        type_map = {
            "retroactive": WarningType.RETROACTIVE,
            "combinatorial": WarningType.COMBINATORIAL,
            "disambiguation": WarningType.DISAMBIGUATION,
        }

        for finding in cross_message_results:
            warning_type = type_map.get(
                finding.get("warning_type", ""),
                WarningType.COMBINATORIAL,
            )
            severity = severity_map.get(
                finding.get("severity", "medium"),
                WarningSeverity.MEDIUM,
            )

            involved = finding.get("involved_message_indices", [])
            quotes = finding.get("source_quotes", [])

            warnings.append(ContextWarning(
                warning_type=warning_type,
                severity=severity,
                title=finding.get("title", "Cross-message connection"),
                description=finding.get("description", ""),
                involved_messages=tuple(involved),
                source_texts=tuple(quotes),
                confidence=finding.get("confidence", 0.6),
            ))

        # Deduplicate: if two warnings mention the same set of messages
        # and similar titles, keep the higher confidence one
        seen = {}
        deduped = []
        for w in warnings:
            key = (frozenset(w.involved_messages), w.warning_type)
            if key in seen:
                if w.confidence > seen[key].confidence:
                    deduped = [x for x in deduped if x is not seen[key]]
                    deduped.append(w)
                    seen[key] = w
            else:
                seen[key] = w
                deduped.append(w)

        # Sort: HIGH > MEDIUM > LOW, then by confidence descending
        severity_order = {
            WarningSeverity.HIGH: 0,
            WarningSeverity.MEDIUM: 1,
            WarningSeverity.LOW: 2,
        }

        return sorted(
            deduped,
            key=lambda w: (severity_order.get(w.severity, 1), -w.confidence),
        )

    def analyze_draft_in_context(
        self,
        messages: List[str],
        draft: str,
        existing_pii_summary: str,
        direct_pii_entities: Optional[List[str]] = None,
    ) -> List[ContextWarning]:
        """Main entry point: analyze a draft message in the context of prior messages.

        Runs coreference resolution and LLM analysis, merges results into warnings.
        Called by /analyze-preview.
        """
        if not messages:
            return []

        direct_entities = direct_pii_entities or []

        # Run coreference resolution
        coref_chains = self.resolve_coreferences(messages, draft)

        # Run LLM cross-message analysis
        cross_message_results = self.analyze_cross_message_pii(
            messages, draft, existing_pii_summary,
        )

        # Merge and generate warnings
        return self.generate_warnings(
            coref_chains, cross_message_results, direct_entities,
        )
