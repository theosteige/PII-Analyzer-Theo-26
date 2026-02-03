"""
PII Analyzer for Theo - Conversational PII Tracker
Wraps Presidio AnalyzerEngine with custom recognizers for conversational PII.
"""

from typing import List, Dict, Optional
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
from presidio_analyzer.nlp_engine import NlpEngineProvider

from .session_manager import PIIEntity


# Color guide for different entity types
COLOR_GUIDE = {
    # Identity
    "PERSON": "#FF7D63",
    "NRP": "#ADDFFF",

    # Contact
    "PHONE_NUMBER": "#229954",
    "EMAIL_ADDRESS": "#8E44AD",
    "URL": "#F6358A",
    "IP_ADDRESS": "#E67E22",

    # Location
    "LOCATION": "#F1C40F",

    # Time
    "DATE_TIME": "#F67280",

    # Financial
    "CREDIT_CARD": "#1569C7",
    "IBAN_CODE": "#1589FF",
    "IN_PAN": "#14A3C7",
    "US_BANK_NUMBER": "#6698FF",
    "CRYPTO": "#82CAFF",
    "US_ITIN": "#AFDCEC",

    # Government IDs
    "IN_AADHAAR": "#34A56F",
    "IN_PASSPORT": "#617C58",
    "AU_ABN": "#3A5F0B",
    "AU_ACN": "#228B22",
    "SG_NRIC_FIN": "#355E3B",
    "AU_TFN": "#8A9A5B",
    "UK_NINO": "#3EA055",
    "US_SSN": "#2980B9",
    "US_PASSPORT": "#85BB65",
    "IN_VOTER": "#77DD77",

    # Medical
    "UK_NHS": "#872657",
    "AU_MEDICARE": "#7F525D",
    "MEDICAL_LICENSE": "#550A35",

    # Vehicle
    "IN_VEHICLE_REGISTRATION": "#FFBF00",
    "US_DRIVER_LICENSE": "#F9DB24",

    # Custom - Education
    "EDUCATION_LEVEL": "#9B59B6",
    "SCHOOL_NAME": "#8E44AD",

    # Custom - Employment
    "OCCUPATION": "#3498DB",
    "EMPLOYER": "#2980B9",

    # Custom - Relationships
    "RELATIONSHIP": "#E74C3C",
    "FAMILY_MEMBER": "#C0392B",

    # Custom - Age
    "AGE": "#1ABC9C",
    "AGE_GROUP": "#16A085",

    # Custom - Health
    "HEALTH_CONDITION": "#E91E63",
    "MEDICAL_TERM": "#C2185B",
}

# Default color for unknown entity types
DEFAULT_COLOR = "#95A5A6"


def create_education_recognizer() -> PatternRecognizer:
    """Create recognizer for education-related PII."""
    patterns = [
        Pattern(
            "education_student",
            r"\b(college|university|high school|grad|graduate|undergraduate|"
            r"freshman|sophomore|junior|senior|PhD|masters|bachelor|associate)\s*"
            r"(student|degree|program)?\b",
            0.7
        ),
        Pattern(
            "education_level",
            r"\b(studying|enrolled|attending|graduated from|degree in|major in|"
            r"majoring in)\b",
            0.6
        ),
    ]
    return PatternRecognizer(
        supported_entity="EDUCATION_LEVEL",
        patterns=patterns,
        name="Education Recognizer"
    )


def create_occupation_recognizer() -> PatternRecognizer:
    """Create recognizer for occupation-related PII."""
    patterns = [
        Pattern(
            "occupation_title",
            r"\b(engineer|developer|doctor|nurse|teacher|professor|lawyer|"
            r"accountant|manager|director|analyst|consultant|designer|"
            r"architect|scientist|researcher|writer|journalist|artist|"
            r"chef|pilot|mechanic|electrician|plumber|carpenter|"
            r"salesperson|marketer|CEO|CTO|CFO|VP|president)\b",
            0.6
        ),
        Pattern(
            "work_context",
            r"\b(work at|work for|employed by|job at|position at|"
            r"my company|my employer|my boss|my job)\b",
            0.5
        ),
    ]
    return PatternRecognizer(
        supported_entity="OCCUPATION",
        patterns=patterns,
        name="Occupation Recognizer"
    )


def create_relationship_recognizer() -> PatternRecognizer:
    """Create recognizer for relationship-related PII."""
    patterns = [
        Pattern(
            "family_relationship",
            r"\b(my\s+)?(husband|wife|spouse|partner|boyfriend|girlfriend|"
            r"mother|father|mom|dad|son|daughter|brother|sister|"
            r"grandmother|grandfather|grandma|grandpa|aunt|uncle|"
            r"cousin|niece|nephew|in-law|stepmother|stepfather)\b",
            0.7
        ),
        Pattern(
            "marital_status",
            r"\b(married|single|divorced|widowed|engaged|dating)\b",
            0.6
        ),
    ]
    return PatternRecognizer(
        supported_entity="RELATIONSHIP",
        patterns=patterns,
        name="Relationship Recognizer"
    )


def create_age_recognizer() -> PatternRecognizer:
    """Create recognizer for age-related PII."""
    patterns = [
        Pattern(
            "explicit_age",
            r"\b(I am|I\'m|I was|turned|turning)\s*\d{1,3}\s*(years old|year old|yo)?\b",
            0.85
        ),
        Pattern(
            "age_number",
            r"\b\d{1,2}\s*(years old|year old|yo)\b",
            0.8
        ),
        Pattern(
            "age_group",
            r"\b(teenager|teen|adolescent|young adult|middle-aged|elderly|"
            r"senior citizen|in my\s*(twenties|thirties|forties|fifties|sixties|"
            r"70s|80s|90s|20s|30s|40s|50s|60s))\b",
            0.7
        ),
    ]
    return PatternRecognizer(
        supported_entity="AGE",
        patterns=patterns,
        name="Age Recognizer"
    )


def create_health_recognizer() -> PatternRecognizer:
    """Create recognizer for health-related PII."""
    patterns = [
        Pattern(
            "health_condition",
            r"\b(diagnosed with|suffering from|have|had)\s+"
            r"(diabetes|cancer|asthma|depression|anxiety|ADHD|autism|"
            r"arthritis|hypertension|heart disease|epilepsy|"
            r"multiple sclerosis|Parkinson|Alzheimer|HIV|AIDS)\b",
            0.8
        ),
        Pattern(
            "medical_context",
            r"\b(my doctor|my therapist|my psychiatrist|my medication|"
            r"taking pills|prescription|hospital visit|surgery|treatment)\b",
            0.6
        ),
    ]
    return PatternRecognizer(
        supported_entity="HEALTH_CONDITION",
        patterns=patterns,
        name="Health Recognizer"
    )


class PIIAnalyzer:
    """Enhanced PII analyzer with custom recognizers for conversational context."""

    def __init__(self):
        """Initialize the analyzer with Presidio and custom recognizers."""
        self.analyzer = AnalyzerEngine()

        # Add custom recognizers
        custom_recognizers = [
            create_education_recognizer(),
            create_occupation_recognizer(),
            create_relationship_recognizer(),
            create_age_recognizer(),
            create_health_recognizer(),
        ]

        for recognizer in custom_recognizers:
            self.analyzer.registry.add_recognizer(recognizer)

    def analyze(
        self,
        text: str,
        message_index: int = 0,
        confidence_threshold: float = 0.4
    ) -> List[PIIEntity]:
        """
        Analyze text for PII entities.

        Args:
            text: The text to analyze
            message_index: Index of the message in the conversation
            confidence_threshold: Minimum confidence score to include entity

        Returns:
            List of PIIEntity objects
        """
        results = self.analyzer.analyze(
            text=text,
            entities=None,  # Detect all entities
            language='en'
        )

        entities = []
        for result in results:
            if result.score >= confidence_threshold:
                entity = PIIEntity(
                    text=text[result.start:result.end],
                    entity_type=result.entity_type,
                    score=result.score,
                    start=result.start,
                    end=result.end,
                    color=COLOR_GUIDE.get(result.entity_type, DEFAULT_COLOR),
                    message_index=message_index
                )
                entities.append(entity)

        return entities

    def get_supported_entities(self) -> List[str]:
        """Get list of all supported entity types."""
        return self.analyzer.get_supported_entities()
