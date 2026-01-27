from flask import Flask, request, send_file, jsonify
from presidio_analyzer import AnalyzerEngine, PatternRecognizer
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
from pprint import pprint
from flask_cors import CORS
from flask import Flask, request, jsonify, render_template



app = Flask(__name__)
CORS(app)

# initialize once globally - analyzer engine from Presidio
analyzer = AnalyzerEngine()

INPUT_FILE = "input.txt"
OUTPUT_FILE = "output.txt"

def process_text(text):
    return analyzer.analyze(text=text, entities=None, language='en')

def formatPII(analyzer_results, content):
    PII = []
    colorguide = {"PERSON": "#FF7D63",
    "PHONE_NUMBER": "#229954",

    "IP_ADDRESS": "#E67E22",
    "LOCATION": "#F1C40F",
    "DATE_TIME": "#F67280",

    "CREDIT_CARD": "#1569C7",
    "IBAN_CODE": "#1589FF",
    "IN_PAN": "#14A3C7",
    "US_BANK_NUMBER": "#6698FF",
    "CRYPTO": "#82CAFF",
    "NRP": "#ADDFFF",
    "US_ITN": "#AFDCEC",

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

    "UK_NHS": "#872657",
    "AU_MEDICARE": "#7F525D",
    "MEDICAL_LICENSE": "#550A35",

    "IN_VEHICLE_REGISTRATION": "#FFBF00",
    "US_DRIVER_LICENSE": "#F9DB24",

    "EMAIL_ADDRESS": "#8E44AD",
    "URL": "#F6358A"
                    }
    
    for result in analyzer_results:

        if (result.score >= 0.4): 
        # Let 0.4 be the threshhold confidence score. Anything below that is unlikely really PII. This can be modified.
            entity_type = result.entity_type
            newDict = {"content" : content[result.start:result.end],
                    "entity_type" : entity_type, 
                    "color" : colorguide[entity_type],
                    "score": result.score,
                    "start": result.start,
                    "end": result.end}
            PII.append(newDict)

    return PII

app = Flask(__name__)
CORS(app)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    data = request.get_json(force=True)  # force=True makes Flask accept even if Content-Type is off
    prompt = data.get("prompt", "")

    content = prompt
    results = process_text(content)
    PII = formatPII(results, content)

    listOfEntities = [
        {"text": item["content"], "color": item["color"], "entity_type": item["entity_type"], 
         "start": item["start"], "end": item["end"], "score": item["score"]}
        for item in PII
    ]

    # Return list of entities as json file since Flask uses JSON
    return jsonify(listOfEntities)


if __name__ == '__main__':
    app.run(debug=True)