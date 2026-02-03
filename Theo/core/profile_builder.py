"""
Profile Builder for Theo - Conversational PII Tracker
Aggregates PII across messages and categorizes into a user profile.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set
import hashlib

from .session_manager import PIIEntity


# Entity type to category mapping
ENTITY_CATEGORIES = {
    # Identity
    "PERSON": "identity",
    "NRP": "identity",

    # Contact
    "PHONE_NUMBER": "contact",
    "EMAIL_ADDRESS": "contact",
    "URL": "contact",
    "IP_ADDRESS": "contact",

    # Location
    "LOCATION": "location",

    # Time
    "DATE_TIME": "temporal",

    # Financial
    "CREDIT_CARD": "financial",
    "IBAN_CODE": "financial",
    "IN_PAN": "financial",
    "US_BANK_NUMBER": "financial",
    "CRYPTO": "financial",
    "US_ITIN": "financial",

    # Government IDs
    "IN_AADHAAR": "government_id",
    "IN_PASSPORT": "government_id",
    "AU_ABN": "government_id",
    "AU_ACN": "government_id",
    "SG_NRIC_FIN": "government_id",
    "AU_TFN": "government_id",
    "UK_NINO": "government_id",
    "US_SSN": "government_id",
    "US_PASSPORT": "government_id",
    "IN_VOTER": "government_id",
    "US_DRIVER_LICENSE": "government_id",

    # Medical
    "UK_NHS": "health",
    "AU_MEDICARE": "health",
    "MEDICAL_LICENSE": "health",
    "HEALTH_CONDITION": "health",
    "MEDICAL_TERM": "health",

    # Vehicle
    "IN_VEHICLE_REGISTRATION": "vehicle",

    # Education
    "EDUCATION_LEVEL": "education",
    "SCHOOL_NAME": "education",

    # Employment
    "OCCUPATION": "employment",
    "EMPLOYER": "employment",

    # Relationships
    "RELATIONSHIP": "relationships",
    "FAMILY_MEMBER": "relationships",

    # Age
    "AGE": "demographics",
    "AGE_GROUP": "demographics",
}

# Category display names and colors
CATEGORY_INFO = {
    "identity": {"name": "Identity", "color": "#FF7D63", "icon": "user"},
    "contact": {"name": "Contact Info", "color": "#8E44AD", "icon": "phone"},
    "location": {"name": "Location", "color": "#F1C40F", "icon": "map-marker"},
    "temporal": {"name": "Dates & Times", "color": "#F67280", "icon": "calendar"},
    "financial": {"name": "Financial", "color": "#1569C7", "icon": "credit-card"},
    "government_id": {"name": "Government IDs", "color": "#2980B9", "icon": "id-card"},
    "health": {"name": "Health", "color": "#872657", "icon": "heart"},
    "vehicle": {"name": "Vehicle", "color": "#FFBF00", "icon": "car"},
    "education": {"name": "Education", "color": "#9B59B6", "icon": "graduation-cap"},
    "employment": {"name": "Employment", "color": "#3498DB", "icon": "briefcase"},
    "relationships": {"name": "Relationships", "color": "#E74C3C", "icon": "users"},
    "demographics": {"name": "Demographics", "color": "#1ABC9C", "icon": "info-circle"},
}


@dataclass
class CategoryData:
    """Data for a single PII category."""
    name: str
    color: str
    icon: str
    entities: List[Dict] = field(default_factory=list)
    unique_values: Set[str] = field(default_factory=set)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "color": self.color,
            "icon": self.icon,
            "entities": self.entities,
            "unique_values": list(self.unique_values),
            "count": len(self.unique_values)
        }


@dataclass
class PIIProfile:
    """Aggregated PII profile from a conversation."""
    categories: Dict[str, CategoryData] = field(default_factory=dict)
    total_entities: int = 0
    identifiability_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "categories": {k: v.to_dict() for k, v in self.categories.items()},
            "total_entities": self.total_entities,
            "identifiability_score": self.identifiability_score,
            "summary": self._generate_summary()
        }

    def _generate_summary(self) -> List[str]:
        """Generate a human-readable summary of what's known."""
        summary = []
        for cat_key, cat_data in self.categories.items():
            if cat_data.unique_values:
                info = CATEGORY_INFO.get(cat_key, {"name": cat_key})
                values = ", ".join(list(cat_data.unique_values)[:3])
                if len(cat_data.unique_values) > 3:
                    values += f" (+{len(cat_data.unique_values) - 3} more)"
                summary.append(f"{info['name']}: {values}")
        return summary


class ProfileBuilder:
    """Builds and maintains a PII profile from conversation entities."""

    def __init__(self):
        """Initialize the profile builder."""
        self._initialize_profile()

    def _initialize_profile(self) -> None:
        """Initialize an empty profile with all categories."""
        self.profile = PIIProfile()
        for cat_key, cat_info in CATEGORY_INFO.items():
            self.profile.categories[cat_key] = CategoryData(
                name=cat_info["name"],
                color=cat_info["color"],
                icon=cat_info["icon"]
            )

    def build_profile(self, entities: List[PIIEntity]) -> PIIProfile:
        """
        Build a profile from a list of PII entities.

        Args:
            entities: List of PIIEntity objects from all messages

        Returns:
            PIIProfile with categorized and aggregated data
        """
        self._initialize_profile()

        for entity in entities:
            category = ENTITY_CATEGORIES.get(entity.entity_type, "identity")

            if category in self.profile.categories:
                self.profile.categories[category].entities.append({
                    "text": entity.text,
                    "type": entity.entity_type,
                    "score": entity.score,
                    "message_index": entity.message_index
                })
                self.profile.categories[category].unique_values.add(
                    entity.text.lower().strip()
                )

        self.profile.total_entities = len(entities)
        self.profile.identifiability_score = self._calculate_identifiability()

        return self.profile

    def _calculate_identifiability(self) -> float:
        """
        Calculate an identifiability score based on the profile.

        Higher scores mean the person is more identifiable.
        Score is 0-100.
        """
        score = 0.0

        # Weight factors for different categories
        weights = {
            "identity": 25,  # Names are highly identifying
            "government_id": 30,  # IDs are very identifying
            "contact": 20,  # Contact info is identifying
            "location": 15,  # Location helps narrow down
            "employment": 10,  # Employer + location is identifying
            "education": 10,  # School + year is identifying
            "health": 5,  # Health conditions less common
            "demographics": 5,  # Age helps narrow down
            "financial": 5,  # Financial info
            "relationships": 3,  # Family info
            "temporal": 2,  # Dates
            "vehicle": 2,  # Vehicle info
        }

        for cat_key, cat_data in self.profile.categories.items():
            unique_count = len(cat_data.unique_values)
            if unique_count > 0:
                weight = weights.get(cat_key, 1)
                # Diminishing returns for multiple values in same category
                category_score = weight * min(unique_count, 3) / 3
                score += category_score

        # Bonus for combinations that are especially identifying
        has_location = len(self.profile.categories.get("location", CategoryData("", "", "")).unique_values) > 0
        has_education = len(self.profile.categories.get("education", CategoryData("", "", "")).unique_values) > 0
        has_employment = len(self.profile.categories.get("employment", CategoryData("", "", "")).unique_values) > 0
        has_name = len(self.profile.categories.get("identity", CategoryData("", "", "")).unique_values) > 0

        if has_location and has_education:
            score += 10  # Location + education is very identifying
        if has_location and has_employment:
            score += 10  # Location + job is very identifying
        if has_name and has_location:
            score += 15  # Name + location is highly identifying

        return min(100.0, score)

    def get_profile_hash(self) -> str:
        """
        Get a hash of the current profile for caching purposes.

        Returns:
            MD5 hash of the profile's unique values
        """
        all_values = []
        for cat_data in self.profile.categories.values():
            all_values.extend(sorted(cat_data.unique_values))

        content = "|".join(all_values)
        return hashlib.md5(content.encode()).hexdigest()

    def get_inference_context(self) -> str:
        """
        Generate context string for LLM inference.

        Returns:
            Formatted string describing all known PII
        """
        context_parts = []

        for cat_key, cat_data in self.profile.categories.items():
            if cat_data.unique_values:
                values = ", ".join(cat_data.unique_values)
                context_parts.append(f"- {cat_data.name}: {values}")

        if not context_parts:
            return "No personal information detected yet."

        return "\n".join(context_parts)
