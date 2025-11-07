import os
import google.generativeai as genai
import whisper
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import uuid
import json
from dotenv import load_dotenv # <-- 1. IMPORT THE LIBRARY

# --- Configuration ---
load_dotenv() # <-- 2. LOAD THE .env FILE

try:
    # This will now find the key loaded from your .env file
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"]) 
except KeyError:
    print("FATAL: GOOGLE_API_KEY environment variable not set.")
    exit()


# --- Initializations ---
app = Flask(__name__)
CORS(app)

print("Loading Whisper model...")
try:
    whisper_model = whisper.load_model("base") # Using 'base' for better accuracy on longer audio
    print("Whisper model loaded successfully.")
except Exception as e:
    print(f"Error loading Whisper model: {e}")
    exit()

gemini_model = genai.GenerativeModel('gemini-2.5-flash')


# --- VOICE-FILLABLE SCHEMA ---
# This schema ONLY includes the fields that we want the AI to fill via voice.
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
    if 'audio_data' not in request.files:
        return jsonify({'error': 'No audio file found'}), 400

    audio_file = request.files['audio_data']
    temp_audio_path = f"temp_audio_{uuid.uuid4()}.webm"
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
        
        # Create a string representing the desired JSON keys from our new schema
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
        
        # Clean the response to get a valid JSON string
        response_text = response.text.strip().replace('```json', '').replace('```', '')
        print(f"Gemini Raw Response: {response_text}")

        # Parse the JSON string into a Python dictionary
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

# --- A new, simpler route for transcribing single fields ---
@app.route('/transcribe', methods=['POST'])
def transcribe_field():
    print("\n--- Request received for single field transcription ---")
    if 'audio_data' not in request.files:
        return jsonify({'error': 'No audio file found'}), 400

    audio_file = request.files['audio_data']
    # Use a unique filename to avoid conflicts
    temp_audio_path = f"temp_audio_{uuid.uuid4()}.webm"
    audio_file.save(temp_audio_path)
    print(f"Audio saved to: {temp_audio_path}")

    try:
        # 1. Transcribe the audio
        print("Transcribing audio...")
        # Using fp16=False is recommended for higher accuracy
        result = whisper_model.transcribe(temp_audio_path, fp16=False)
        transcribed_text = result['text']
        print(f"Transcription result: '{transcribed_text}'")

        if not transcribed_text.strip():
            return jsonify({'text': ''}) # Return empty if no speech detected

        # 2. Return the transcribed text
        return jsonify({'text': transcribed_text})

    except Exception as e:
        print(f"An error occurred during transcription: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        # 3. Clean up the temporary file
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)
            print(f"Cleaned up temp file: {temp_audio_path}")
if __name__ == '__main__':
    app.run(debug=True)
