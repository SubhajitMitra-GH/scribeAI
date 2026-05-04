import os
import time
import uuid
import json
import mimetypes
import traceback
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# New GenAI Library Import
from google import genai
from google.genai import types

# Audio Conversion Import
from pydub import AudioSegment

load_dotenv()

# --- Configuration ---
api_key = os.environ.get("GOOGLE_API_KEY")
if not api_key:
    print("FATAL: GOOGLE_API_KEY environment variable not set.")

# Initialize the Gemini Client
client = genai.Client(api_key=api_key)
MODEL_ID = 'gemini-2.5-flash'

# --- Filesystem Paths ---
TEMP_DIR = "/tmp"
os.makedirs(TEMP_DIR, exist_ok=True)

app = Flask(__name__)
CORS(app)

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

# --- Helper Functions ---

def get_extension_from_mimetype(mime_type):
    if not mime_type: return '.dat'
    mapping = {
        'audio/webm': '.webm',
        'audio/mpeg': '.mp3',
        'audio/mp4': '.m4a',
        'audio/wav': '.wav',
        'audio/x-wav': '.wav',
        'audio/ogg': '.ogg'
    }
    return mapping.get(mime_type, mimetypes.guess_extension(mime_type) or '.dat')

def wait_for_file_active(file_response, timeout_sec=30):
    """Waits for the File to become active using the new Client.files.get method."""
    start_time = time.time()
    print(f"Waiting for file {file_response.name} to become active...")
    
    file = client.files.get(name=file_response.name)
    while file.state == "PROCESSING":
        if time.time() - start_time > timeout_sec:
            raise Exception(f"File processing timed out after {timeout_sec} seconds.")
        time.sleep(2)
        file = client.files.get(name=file_response.name)
    
    if file.state == "ACTIVE":
        print(f"File {file.name} is now ACTIVE.")
        return file
    else:
        raise Exception(f"File {file.name} failed to process. State: {file.state}")

# --- Flask Routes ---

@app.route('/process_audio', methods=['POST'])
def process_audio():
    print("\n--- Request received for detailed form processing ---")
    if 'audio_data' not in request.files:
        return jsonify({'error': 'No audio file found'}), 400

    audio_file = request.files['audio_data']
    mime_type = audio_file.mimetype
    extension = get_extension_from_mimetype(mime_type)
    
    # Define paths for both the raw upload and the converted WAV
    base_uuid = str(uuid.uuid4())
    temp_audio_path = os.path.join(TEMP_DIR, f"temp_raw_{base_uuid}{extension}")
    clean_wav_path = os.path.join(TEMP_DIR, f"clean_audio_{base_uuid}.wav")
    
    uploaded_file = None
    
    try:
        # 1. Save the raw file from the frontend
        audio_file.save(temp_audio_path)

        # 2. Convert to a clean WAV file using pydub
        print(f"Converting {temp_audio_path} to clean WAV format...")
        audio = AudioSegment.from_file(temp_audio_path)
        audio.export(clean_wav_path, format="wav")

        # 3. Upload the CLEAN WAV file to Google
        print(f"Uploading clean audio to Google: {clean_wav_path}")
        uploaded_file = client.files.upload(
            file=clean_wav_path,
            config={'mime_type': 'audio/wav'}
        )
        
        # 4. Wait for file to be active
        active_file = wait_for_file_active(uploaded_file)

        # 5. Transcribe audio
        print("Transcribing audio...")
        transcription_response = client.models.generate_content(
            model=MODEL_ID,
            contents=[
                "Please transcribe the following audio file. Provide only the text transcription and nothing else.",
                active_file
            ]
        )
        transcribed_text = transcription_response.text
        print(f"Full Transcription: '{transcribed_text}'")

        if not transcribed_text or not transcribed_text.strip():
            return jsonify({'error': 'No speech detected.'})

        # 6. Structured extraction
        schema_description = "\n".join([f'- "{key}": "{description}"' for key, description in VOICE_FILLABLE_SCHEMA.items()])
        prompt = f"""
        You are an expert medical scribe specializing in dental forms. 
        Analyze the transcript and fill in the values for the following JSON schema. 
        ONLY fill the fields listed below. Do not attempt to answer Yes/No questions.

        JSON Schema to fill:
        {schema_description}

        Extraction Rules:
        - JSON object must only contain keys listed in schema.
        - If missing, value must be "".
        - Translate non-English to English.
        - Normalize data (digits for ages, clear date formats).
        - Output MUST be a single, valid JSON object only.

        Transcript: {transcribed_text}
        """
        
        extraction_response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type='application/json'
            )
        )
        
        extracted_data = json.loads(extraction_response.text)
        return jsonify({
            'transcribed_text': transcribed_text,
            'extracted_data': extracted_data
        })

    except Exception as e:
        print("\n=== ERROR IN /process_audio ===")
        traceback.print_exc()
        print("===============================\n")
        return jsonify({'error': str(e)}), 500
    finally:
        # Safe cleanup process for ALL files
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)
        if os.path.exists(clean_wav_path):
            os.remove(clean_wav_path)
            
        # Verify uploaded_file actually exists and has a name before trying to delete
        if uploaded_file and hasattr(uploaded_file, 'name'):
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception as e:
                print(f"Warning: Failed to delete file from Google servers: {e}")

@app.route('/transcribe', methods=['POST'])
def transcribe_field():
    print("\n--- Request received for single field transcription ---")
    if 'audio_data' not in request.files:
        return jsonify({'error': 'No audio file found'}), 400

    audio_file = request.files['audio_data']
    mime_type = audio_file.mimetype
    extension = get_extension_from_mimetype(mime_type)
    
    # Define paths for both the raw upload and the converted WAV
    base_uuid = str(uuid.uuid4())
    temp_audio_path = os.path.join(TEMP_DIR, f"temp_raw_{base_uuid}{extension}")
    clean_wav_path = os.path.join(TEMP_DIR, f"clean_audio_{base_uuid}.wav")
    
    uploaded_file = None
    
    try:
        # 1. Save raw file
        audio_file.save(temp_audio_path)
        
        # 2. Convert to WAV
        print(f"Converting {temp_audio_path} to clean WAV format...")
        audio = AudioSegment.from_file(temp_audio_path)
        audio.export(clean_wav_path, format="wav")

        # 3. Upload clean WAV
        print(f"Uploading clean audio to Google: {clean_wav_path}")
        uploaded_file = client.files.upload(
            file=clean_wav_path,
            config={'mime_type': 'audio/wav'}
        )
        
        active_file = wait_for_file_active(uploaded_file)

        print("Transcribing audio...")
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=["Transcribe this audio. Only the text.", active_file]
        )
        
        print(f"Transcription result: '{response.text}'")
        return jsonify({'text': response.text})

    except Exception as e:
        print("\n=== ERROR IN /transcribe ===")
        traceback.print_exc()
        print("============================\n")
        return jsonify({'error': str(e)}), 500
    finally:
        # Safe cleanup process for ALL files
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)
        if os.path.exists(clean_wav_path):
            os.remove(clean_wav_path)
            
        if uploaded_file and hasattr(uploaded_file, 'name'):
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception as e:
                print(f"Warning: Failed to delete file from Google servers: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
