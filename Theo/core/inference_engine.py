"""
Inference Engine for Theo - Conversational PII Tracker
Uses OpenAI to generate inferences from combined PII data.
"""

import os
from typing import Optional
from openai import OpenAI


INFERENCE_PROMPT_TEMPLATE = """You are a privacy analyst helping users understand what can be inferred about them from the personal information they've shared in a conversation with an AI.

Given the following pieces of personal information revealed during a conversation:

{pii_context}

Please analyze what additional information can be inferred or deduced about this person. Be specific about:
1. **Likely identifiers**: Specific schools, employers, organizations they might be associated with
2. **Demographic profile**: What can be inferred about their life circumstances
3. **Location narrowing**: How the combination of information helps pinpoint their location
4. **Identity risk**: How identifiable this person is based on the combination of information

Important guidelines:
- Be specific with inferences (e.g., "likely attends Union College" rather than "attends college in that area")
- Explain your reasoning briefly
- Focus on how pieces of information COMBINE to reveal more than they would individually
- Rate the overall identifiability from 1-10 with explanation

Format your response as a clear, organized analysis that a non-technical user can understand."""


class InferenceEngine:
    """Generates inferences from PII using OpenAI API."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the inference engine.

        Args:
            api_key: OpenAI API key. If not provided, reads from OPENAI_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.client = None

        if self.api_key:
            self.client = OpenAI(api_key=self.api_key)

    def is_available(self) -> bool:
        """Check if the inference engine is available (API key configured)."""
        return self.client is not None

    def generate_inference(
        self,
        pii_context: str,
        model: str = "gpt-4o-mini"
    ) -> str:
        """
        Generate inferences from PII context.

        Args:
            pii_context: Formatted string of PII data from ProfileBuilder
            model: OpenAI model to use

        Returns:
            Generated inference text

        Raises:
            ValueError: If API key is not configured
            Exception: If API call fails
        """
        if not self.client:
            raise ValueError(
                "OpenAI API key not configured. "
                "Set OPENAI_API_KEY environment variable."
            )

        if not pii_context or pii_context == "No personal information detected yet.":
            return "No personal information has been detected yet. Share some messages to see what can be inferred."

        prompt = INFERENCE_PROMPT_TEMPLATE.format(pii_context=pii_context)

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful privacy analyst."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=1000
            )

            return response.choices[0].message.content

        except Exception as e:
            raise Exception(f"Failed to generate inference: {str(e)}")

    def generate_quick_inference(
        self,
        pii_context: str,
        model: str = "gpt-4o-mini"
    ) -> str:
        """
        Generate a brief, one-paragraph inference.

        Args:
            pii_context: Formatted string of PII data
            model: OpenAI model to use

        Returns:
            Brief inference text
        """
        if not self.client:
            return "Configure OPENAI_API_KEY to enable AI-powered inference."

        if not pii_context or pii_context == "No personal information detected yet.":
            return "No personal information detected yet."

        quick_prompt = f"""Based on this personal information:

{pii_context}

In 2-3 sentences, what is the most significant inference that can be made by combining these pieces of information? Focus on the most identifying combination."""

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": quick_prompt
                    }
                ],
                temperature=0.7,
                max_tokens=200
            )

            return response.choices[0].message.content

        except Exception:
            return "Unable to generate inference at this time."
