"""
Theo - Conversational PII Tracker
Flask server for analyzing PII across conversation messages.
"""

import os
import logging
import uuid
from pathlib import Path
from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file in the same directory as this script
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

from core import (
    SessionManager,
    PIIAnalyzer,
    ProfileBuilder,
    InferenceEngine,
    PIIEntity,
    ContextAnalyzer,
)

app = Flask(__name__)

# Security: Require secret key in production
secret_key = os.getenv("FLASK_SECRET_KEY")
is_development = os.getenv("FLASK_ENV", "development") == "development"
if not secret_key:
    if is_development:
        secret_key = "dev-only-not-for-production-change-me"
        logger.warning("Using default secret key. Set FLASK_SECRET_KEY in production!")
    else:
        raise ValueError("FLASK_SECRET_KEY environment variable must be set in production")
app.secret_key = secret_key

# Security: Restrict CORS origins
allowed_origins = os.getenv("CORS_ORIGINS", "http://localhost:5001,http://127.0.0.1:5001").split(",")
CORS(app, origins=allowed_origins)

# Initialize global components
session_manager = SessionManager()
pii_analyzer = PIIAnalyzer()
profile_builder = ProfileBuilder()
inference_engine = InferenceEngine()
context_analyzer = ContextAnalyzer(openai_client=inference_engine.client)


def get_session_id() -> str:
    """Get or create a session ID for the current user."""
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    return session["session_id"]


@app.route("/")
def index():
    """Serve the main chat UI."""
    return render_template("index.html")


@app.route("/message", methods=["POST"])
def add_message():
    """
    Add a message to the conversation and analyze for PII.

    Request body:
        {
            "content": "message text",
            "role": "user" or "assistant"
        }

    Returns:
        {
            "message": {...},
            "profile": {...},
            "quick_inference": "..."
        }
    """
    data = request.get_json(force=True)
    content = data.get("content", "").strip()
    role = data.get("role", "user")

    if not content:
        return jsonify({"error": "Message content is required"}), 400

    if role not in ["user", "assistant"]:
        return jsonify({"error": "Role must be 'user' or 'assistant'"}), 400

    session_id = get_session_id()
    conv_session = session_manager.get_or_create_session(session_id)
    message_index = len(conv_session.messages)

    # Analyze PII in the message
    pii_entities = pii_analyzer.analyze(content, message_index)

    # Add message to session
    message = session_manager.add_message(
        session_id=session_id,
        role=role,
        content=content,
        pii_entities=pii_entities
    )

    # Generate chatbot reply if this is a user message
    assistant_message = None
    if role == "user":
        try:
            # Build conversation history from session messages
            history = [
                {"role": m.role, "content": m.content}
                for m in conv_session.messages
            ]
            reply_text = inference_engine.generate_chat_reply(history)

            # Analyze assistant reply for PII
            assistant_index = len(conv_session.messages)
            reply_pii = pii_analyzer.analyze(reply_text, assistant_index)

            # Store assistant message
            assistant_message = session_manager.add_message(
                session_id=session_id,
                role="assistant",
                content=reply_text,
                pii_entities=reply_pii
            )
        except Exception as e:
            logger.error(f"Chat reply generation failed: {e}", exc_info=True)

    # Build updated profile (reflects both user + assistant messages)
    all_entities = session_manager.get_all_pii_entities(session_id)
    profile = profile_builder.build_profile(all_entities)

    # Generate quick inference if API key is available
    quick_inference = None
    if inference_engine.is_available() and len(all_entities) > 0:
        context = profile_builder.get_inference_context()
        quick_inference = inference_engine.generate_quick_inference(context)

    response_data = {
        "message": message.to_dict(),
        "profile": profile.to_dict(),
        "quick_inference": quick_inference
    }

    if assistant_message:
        response_data["assistant_message"] = assistant_message.to_dict()

    return jsonify(response_data)


@app.route("/analyze-preview", methods=["POST"])
def analyze_preview():
    """
    Analyze draft text for PII without storing it.
    Returns entities with is_new flags and projected score delta.

    Request body:
        { "content": "draft text" }

    Returns:
        {
            "entities": [...],
            "current_score": float,
            "projected_score": float,
            "score_delta": float,
            "new_entity_types": [...]
        }
    """
    data = request.get_json(force=True)
    content = data.get("content", "").strip()

    if not content:
        return jsonify({
            "entities": [],
            "current_score": 0,
            "projected_score": 0,
            "score_delta": 0,
            "new_entity_types": [],
            "context_warnings": [],
        })

    session_id = get_session_id()

    # Analyze PII in draft (not stored)
    preview_entities = pii_analyzer.analyze(content, message_index=-1)

    # Get existing entities for this session
    existing_entities = session_manager.get_all_pii_entities(session_id)

    # Use temp builders to avoid mutating global profile_builder state
    temp_current_builder = ProfileBuilder()
    current_profile = temp_current_builder.build_profile(existing_entities)
    current_score = current_profile.identifiability_score

    temp_projected_builder = ProfileBuilder()
    combined_entities = existing_entities + preview_entities
    projected_profile = temp_projected_builder.build_profile(combined_entities)
    projected_score = projected_profile.identifiability_score

    # Determine which entity values are new
    existing_values = {e.text.lower().strip() for e in existing_entities}
    existing_types = {e.entity_type for e in existing_entities}

    new_entity_types = []
    entities_response = []
    for entity in preview_entities:
        is_new = entity.text.lower().strip() not in existing_values
        if is_new and entity.entity_type not in existing_types:
            if entity.entity_type not in new_entity_types:
                new_entity_types.append(entity.entity_type)
        entities_response.append({
            "text": entity.text,
            "entity_type": entity.entity_type,
            "score": entity.score,
            "start": entity.start,
            "end": entity.end,
            "color": entity.color,
            "is_new": is_new
        })

    # Cross-message contextual analysis
    context_warnings = []
    try:
        conv_session = session_manager.get_session(session_id)
        if conv_session and len(conv_session.messages) > 0:
            message_texts = [m.content for m in conv_session.messages]

            # Build PII summary from existing entities
            pii_summary_parts = []
            for entity in existing_entities:
                pii_summary_parts.append(
                    f"[msg {entity.message_index}] {entity.entity_type}: {entity.text}"
                )
            existing_pii_summary = "\n".join(pii_summary_parts) if pii_summary_parts else ""

            # Collect direct PII entity texts for deduplication
            direct_entity_texts = [e.text for e in preview_entities]

            warnings = context_analyzer.analyze_draft_in_context(
                messages=message_texts,
                draft=content,
                existing_pii_summary=existing_pii_summary,
                direct_pii_entities=direct_entity_texts,
            )
            context_warnings = [w.to_dict() for w in warnings]
    except Exception as e:
        logger.error(f"Context analysis failed (non-fatal): {e}", exc_info=True)

    return jsonify({
        "entities": entities_response,
        "current_score": round(current_score, 1),
        "projected_score": round(projected_score, 1),
        "score_delta": round(projected_score - current_score, 1),
        "new_entity_types": new_entity_types,
        "context_warnings": context_warnings,
    })


@app.route("/profile", methods=["GET"])
def get_profile():
    """
    Get the current PII profile for the session.

    Returns:
        {
            "profile": {...},
            "message_count": int,
            "inference_available": bool
        }
    """
    session_id = get_session_id()

    all_entities = session_manager.get_all_pii_entities(session_id)
    profile = profile_builder.build_profile(all_entities)

    conv_session = session_manager.get_session(session_id)

    return jsonify({
        "profile": profile.to_dict(),
        "message_count": len(conv_session.messages) if conv_session else 0,
        "inference_available": inference_engine.is_available()
    })


@app.route("/conversation", methods=["GET"])
def get_conversation():
    """
    Get all messages in the current conversation.

    Returns:
        {
            "messages": [...],
            "session_id": "..."
        }
    """
    session_id = get_session_id()
    conv_session = session_manager.get_session(session_id)

    if not conv_session:
        return jsonify({
            "messages": [],
            "session_id": session_id
        })

    return jsonify({
        "messages": [m.to_dict() for m in conv_session.messages],
        "session_id": session_id
    })


@app.route("/infer", methods=["POST"])
def generate_inference():
    """
    Generate a detailed inference from the accumulated PII.

    Returns:
        {
            "inference": "...",
            "profile_hash": "..."
        }
    """
    if not inference_engine.is_available():
        return jsonify({
            "error": "OpenAI API key not configured. Set OPENAI_API_KEY environment variable."
        }), 503

    session_id = get_session_id()
    conv_session = session_manager.get_session(session_id)

    if not conv_session or len(conv_session.messages) == 0:
        return jsonify({
            "inference": "No messages in the conversation yet. Add some messages to see what can be inferred.",
            "profile_hash": ""
        })

    # Check cache
    all_entities = session_manager.get_all_pii_entities(session_id)
    profile = profile_builder.build_profile(all_entities)
    current_hash = profile_builder.get_profile_hash()

    if conv_session.inference_cache_hash == current_hash and conv_session.last_inference:
        return jsonify({
            "inference": conv_session.last_inference,
            "profile_hash": current_hash,
            "cached": True
        })

    # Generate new inference
    context = profile_builder.get_inference_context()

    try:
        inference = inference_engine.generate_inference(context)
        session_manager.update_inference(session_id, inference, current_hash)

        return jsonify({
            "inference": inference,
            "profile_hash": current_hash,
            "cached": False
        })

    except Exception as e:
        logger.error(f"Inference generation failed: {e}", exc_info=True)
        return jsonify({"error": "Failed to generate inference. Please try again."}), 500


@app.route("/reset", methods=["POST"])
def reset_session():
    """
    Reset the current session, clearing all messages and PII data.

    Returns:
        {"success": true}
    """
    session_id = get_session_id()
    session_manager.reset_session(session_id)

    # Generate new session ID
    session["session_id"] = str(uuid.uuid4())

    return jsonify({"success": True, "new_session_id": session["session_id"]})


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "inference_available": inference_engine.is_available()
    })


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  Theo - Conversational PII Tracker")
    print("=" * 60)
    print(f"  .env file: {env_path} ({'found' if env_path.exists() else 'NOT FOUND'})")
    print(f"  OpenAI Inference: {'Enabled' if inference_engine.is_available() else 'Disabled (set OPENAI_API_KEY in .env)'}")
    print(f"  Environment: {'Development' if is_development else 'Production'}")
    print("=" * 60 + "\n")

    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true" or is_development
    app.run(debug=debug_mode, port=5001)
