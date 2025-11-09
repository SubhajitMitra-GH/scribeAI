import os
import google.generativeai as genai
import whisper
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import uuid
import json
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()

try:
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
except KeyError:
    print("FATAL: GOOGLE_API_KEY environment variable not set.")
    # In a serverless environment, we still want the app to load
    # The function will just fail if this key is missing.
    pass

# --- Vercel-Specific Paths ---
# We can only write to the /tmp directory in a Vercel Serverless Function
TEMP_DIR = "/tmp"
CACHE_DIR = "/tmp/whisper_models"

# Ensure cache directory exists
os.makedirs(CACHE_DIR, exist_ok=True)

# --- Initializations ---
app = Flask(__name__)
CORS(app)

print("Loading Whisper model...")
try:
    # Use the /tmp directory for downloading the model
    # This caches the model between "warm" invocations
    whisper_model = whisper.load_model("tiny", download_root=CACHE_DIR)
    print("Whisper model loaded successfully.")
except Exception as e:
    print(f"Error loading Whisper model: {e}")
    # Don't exit, allow the app to be deployed, but log the error
    whisper_model = None

gemini_model = genai.GenerativeModel('gemini-2.5-flash')


# --- VOICE-FILLABLE SCHEMA ---
VOICE_FILLABLE_SCHEMA = {
    'organised_by': "The name of the organization conducting the event.",
    'department': "The specific department involved.",
    'event_date': "The date of the event.",
    'event_place': "The city or location of the event.",
    'event_district': "The district where the event is taking place.",
    'patient_name': "The patient's full name.",
    'patient_age': "The patient's age in years.",
    'patient_contact': "The patient's contact phone number.",
    'patient_education': "The patient's educational qualifications.",
    'family_monthly_income': "The monthly income of the patient's family.",
    'chief_complaint': "The primary medical or dental complaint from the patient, in their own words.",
    'past_medical_history_others': "Any other past medical conditions mentioned that are not in the Yes/No list.",
    'past_dental_visit_details': "Details about the last dental visit if mentioned (e.g., 'about a year ago for a cleaning').",
    'personal_habits_others': "Any other personal habits mentioned besides smoking or alcohol.",
    'clinical_decayed': "Description or count of decayed teeth.",
    'clinical_missing': "Description or count of missing teeth.",
    'clinical_filled': "Description or count of filled teeth.",
    'clinical_pain': "Details about any dental pain the patient is experiencing.",
    'clinical_fractured_teeth': "Details about any fractured teeth.",
    'clinical_mobility': "Details about any mobile or loose teeth.",
    'clinical_examination_others': "Any other clinical findings mentioned.",
    'oral_mucosal_lesion': "Description of any oral mucosal lesions observed.",
    'teeth_cleaning_method': "The method the patient uses for cleaning their teeth (e.g., 'brush and paste twice a day').",
    'doctors_name': "The name of the examining doctor.",
    'treatment_plan': "The proposed treatment plan based on the examination."
}


# --- Flask Routes ---

@app.route('/process_audio', methods=['POST'])
def process_audio():
    print("\n--- Request received for detailed form processing ---")
    if whisper_model is None:
        return jsonify({'error': 'Whisper model failed to load. Check server logs.'}), 500

    if 'audio_data' not in request.files:
        return jsonify({'error': 'No audio file found'}), 400

    audio_file = request.files['audio_data']
    # Use the /tmp directory for saving the temporary file
    temp_audio_path = os.path.join(TEMP_DIR, f"temp_audio_{uuid.uuid4()}.webm")
    audio_file.save(temp_audio_path)
    print(f"Audio saved to: {temp_audio_path}")

    try:
        # 1. Transcribe the entire conversation
        print("Transcribing audio...")
        result = whisper_model.transcribe(temp_audio_path, fp16=False)
        transcribed_text = result['text']
        print(f"Full Transcription: '{transcribed_text}'")

        if not transcribed_text.strip():
            return jsonify({'error': 'No speech detected.'})

        # 2. Use a sophisticated prompt to extract all fields into a JSON object
        print("Extracting structured data with Gemini...")
        
        schema_description = "\n".join([f'- "{key}": "{description}"' for key, description in VOICE_FILLABLE_SCHEMA.items()])

        prompt = f"""
        You are an expert medical scribe specializing in dental forms. Your task is to analyze a conversation transcript and extract key information into a structured JSON object.

        Analyze the transcript and fill in the values for the following JSON schema. ONLY fill the fields listed below. Do not attempt to answer Yes/No questions.

        JSON Schema to fill:
        {schema_description}

        Extraction Rules:
        - The JSON object must only contain the keys listed in the schema above.
        - If information for a key is not in the transcript, the value must be an empty string "".
        - Translate any non-English information (e.g., Hindi, Tamil) into English.
        - Normalize data: write ages and numbers as digits. Format dates clearly.
        - Your final output MUST be a single, valid JSON object and nothing else. Do not add explanations.

        Transcript:
        ---
        {transcribed_text}
        ---

        JSON Output:
        """
        
        response = gemini_model.generate_content(prompt)
        
        response_text = response.text.strip().replace('```json', '').replace('```', '')
        print(f"Gemini Raw Response: {response_text}")

        extracted_data = json.loads(response_text)
        print(f"Successfully Parsed JSON: {extracted_data}")

        return jsonify({
            'transcribed_text': transcribed_text,
            'extracted_data': extracted_data
        })

    except json.JSONDecodeError:
        print("Error: Failed to decode JSON from Gemini's response.")
        return jsonify({'error': "AI response was not valid JSON. Please check server logs."}), 500
    except Exception as e:
        print(f"An error occurred: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)
            print(f"Cleaned up temp file: {temp_audio_path}")

@app.route('/transcribe', methods=['POST'])
def transcribe_field():
    print("\n--- Request received for single field transcription ---")
    if whisper_model is None:
        return jsonify({'error': 'Whisper model failed to load. Check server logs.'}), 500

    if 'audio_data' not in request.files:
        return jsonify({'error': 'No audio file found'}), 400

    audio_file = request.files['audio_data']
    # Use the /tmp directory for saving the temporary file
    temp_audio_path = os.path.join(TEMP_DIR, f"temp_audio_{uuid.uuid4()}.webm")
    audio_file.save(temp_audio_path)
    print(f"Audio saved to: {temp_audio_path}")

    try:
        print("Transcribing audio...")
        result = whisper_model.transcribe(temp_audio_path, fp16=False)
        transcribed_text = result['text']
        print(f"Transcription result: '{transcribed_text}'")

        if not transcribed_text.strip():
            return jsonify({'text': ''})

        return jsonify({'text': transcribed_text})

    except Exception as e:
        print(f"An error occurred during transcription: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)
            print(f"Cleaned up temp file: {temp_audio_path}")

# This check is not strictly needed for Vercel, but it's good practice
# and allows you to still run `python api/app.py` locally for testing.
if __name__ == '__main__':
    app.run(debug=True)
