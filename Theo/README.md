# Theo - Conversational PII Tracker

This is a privacy awareness tool that tracks Personally Identifiable Information (PII) across multiple messages in a conversation. Unlike single-prompt analyzers, this project shows users how seemingly innocuous pieces of information can combine to create a detailed personal profile.

## Quick Start

### Prerequisites

- Python 3.9+
- pip

### Installation

1. **Navigate to the Theo directory:**
   ```bash
   cd Theo
   ```

2. **Create and activate a virtual environment:**
   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate

   # macOS/Linux
   python -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Download the spaCy language model:**
   ```bash
   python -m spacy download en_core_web_lg
   ```

5. **Set up your environment variables:**
   ```bash
   # Copy the example .env file
   cp .env.example .env

   # Edit .env and add your OpenAI API key (for AI inference)
   # OPENAI_API_KEY=sk-your-key-here
   ```

   Or on Windows:
   ```cmd
   copy .env.example .env
   ```

   Then open `.env` in a text editor and add your OpenAI API key.

6. **Run the server:**
   ```bash
   python server.py
   ```

7. **Open your browser to:** http://localhost:5001

## Demo Walkthrough

### Scenario: Showing how PII accumulates

1. **Start the server** and open http://localhost:5001

2. **Send your first message** (as User):
   ```
   I am a college student studying computer science.
   ```
   - Notice the "EDUCATION_LEVEL" PII is detected and highlighted
   - The identifiability score increases slightly

3. **Send a second message:**
   ```
   I live in Schenectady, New York.
   ```
   - "LOCATION" is detected
   - The score increases more significantly

4. **Send a third message:**
   ```
   My name is John and I'm 21 years old.
   ```
   - "PERSON" and "AGE" are detected
   - Watch the identifiability score jump higher

5. **Click "Generate Detailed Analysis"** (requires OpenAI API key):
   - The AI will explain that combining "college student" + "computer science" + "Schenectady" + "age 21" likely identifies you as a student at Union College
   - This demonstrates how individual pieces of non-sensitive information combine to become highly identifying

### Testing Assistant Messages

You can also analyze what an AI assistant might reveal:

1. Click the **"Assistant"** button to switch roles
2. Paste a simulated assistant response:
   ```
   Based on your location in Schenectady and your studies, you might be interested in the tech meetups at Union College. The computer science department there has great resources for students your age.
   ```
3. Notice how the assistant's response reinforces and confirms the inferred information

### Key Demo Points

- **Individual pieces seem harmless**: "I'm a student" or "I live in Schenectady" alone aren't very identifying
- **Combinations are powerful**: Together they narrow down to a very small population
- **The score visualizes risk**: Watch it climb from green (low) to red (critical)
- **Categories show breadth**: Multiple categories filled = more complete profile

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key for inference generation | None (inference disabled) |
| `FLASK_SECRET_KEY` | Session encryption key | Dev key (required in production) |
| `FLASK_ENV` | Environment mode | `development` |
| `FLASK_DEBUG` | Enable debug mode | `false` |
| `CORS_ORIGINS` | Allowed CORS origins | `http://localhost:5001,http://127.0.0.1:5001` |

### Production Deployment

For production use:

```bash
export FLASK_ENV=production
export FLASK_SECRET_KEY=your-secure-random-key
export FLASK_DEBUG=false
export CORS_ORIGINS=https://your-domain.com
```

## Project Structure

```
Theo/
├── server.py              # Flask application
├── requirements.txt       # Python dependencies
├── README.md              # This file
├── templates/
│   └── index.html         # Chat UI
├── static/
│   └── style.css          # Styling
└── core/
    ├── __init__.py        # Package exports
    ├── pii_analyzer.py    # Presidio + custom recognizers
    ├── session_manager.py # In-memory conversation storage
    ├── inference_engine.py # OpenAI integration
    └── profile_builder.py # PII aggregation & scoring
```

## Custom PII Recognizers

Theo extends Microsoft Presidio with custom recognizers for conversational PII:

| Recognizer | Detects |
|------------|---------|
| Education | "college student", "grad school", "majoring in" |
| Occupation | Job titles, "work at", "employed by" |
| Relationship | "my wife", "husband", "children", family terms |
| Age | "I'm 25", "years old", "in my thirties" |
| Health | Medical conditions, "diagnosed with", medications |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serve the chat UI |
| `/message` | POST | Add a message and analyze for PII |
| `/profile` | GET | Get the current PII profile |
| `/conversation` | GET | Get all messages in the session |
| `/infer` | POST | Generate AI inference from accumulated PII |
| `/reset` | POST | Clear the conversation and start fresh |
| `/health` | GET | Health check endpoint |

## Technologies Used

- **Flask** - Web framework
- **Microsoft Presidio** - PII detection engine
- **spaCy** - NLP for entity recognition
- **OpenAI API** - AI-powered inference generation

## Troubleshooting

### "No module named 'presidio_analyzer'"
```bash
pip install presidio-analyzer presidio-anonymizer
```

### "Can't find model 'en_core_web_lg'"
```bash
python -m spacy download en_core_web_lg
```

### Inference button is disabled
Add your OpenAI API key to the `.env` file and restart the server:
```
OPENAI_API_KEY=sk-your-key-here
```

### Session data not persisting
Theo uses in-memory storage by design. Data resets when the server restarts or the browser session ends.

## License

This project is for educational and demonstration purposes.
