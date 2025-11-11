import os
import google.generativeai as genai
from flask import Flask, request, jsonify
from flask_cors import CORS
import uuid
import json
from dotenv import load_dotenv
import mimetypes
import time # Import the time module

# --- Configuration ---
load_dotenv()

# 1. Configure Gemini
try:
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
except KeyError:
    print("FATAL: GOOGLE_API_KEY environment variable not set.")
    pass

# --- Filesystem Paths ---
# We still need the /tmp directory to save the audio file temporarily
TEMP_DIR = "/tmp"
os.makedirs(TEMP_DIR, exist_ok=True)

# --- Initializations ---
app = Flask(__name__)
CORS(app)

# Initialize the Generative AI model
try:
    gemini_model = genai.GenerativeModel('gemini-2.5-flash-preview-09-2025')
except Exception as e:
    print(f"Error initializing Gemini model: {e}")
    gemini_model = None

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


# --- Helper Function ---
def get_extension_from_mimetype(mime_type):
    """Gets a file extension from a MIME type."""
    if not mime_type:
        return '.dat' # default extension
    
    if mime_type == 'audio/webm':
        return '.webm'
    if mime_type == 'audio/mpeg':
        return '.mp3'
    if mime_type == 'audio/mp4': # m4a is often sent as audio/mp4
        return '.m4a'
    if mime_type == 'audio/wav' or mime_type == 'audio/x-wav':
        return '.wav'
    if mime_type == 'audio/ogg':
        return '.ogg'
    
    # Use mimetypes library as a fallback
    extension = mimetypes.guess_extension(mime_type)
    return extension if extension else '.dat'

def wait_for_file_active(file_response, timeout_sec=30):
    """Waits for the Google File API to mark the file as ACTIVE."""
    start_time = time.time()
    print(f"Waiting for file {file_response.name} to become active...")
    file = genai.get_file(file_response.name)
    while file.state.name == 'PROCESSING':
        if time.time() - start_time > timeout_sec:
            raise Exception(f"File processing timed out after {timeout_sec} seconds.")
        time.sleep(1) # Wait 1 second before checking again
        file = genai.get_file(file_response.name)
    
    if file.state.name == 'ACTIVE':
        print(f"File {file.name} is now ACTIVE.")
        return file
    else:
        raise Exception(f"File {file.name} failed to process. State: {file.state.name}")

# --- Flask Routes ---

@app.route('/process_audio', methods=['POST'])
def process_audio():
    print("\n--- Request received for detailed form processing ---")
    if gemini_model is None:
        return jsonify({'error': 'Gemini model failed to load. Check server logs.'}), 500

    if 'audio_data' not in request.files:
        return jsonify({'error': 'No audio file found'}), 400

    audio_file = request.files['audio_data']
    
    # --- FIX: Use the browser's MIME type to determine extension ---
    mime_type = audio_file.mimetype
    extension = get_extension_from_mimetype(mime_type)
    temp_audio_path = os.path.join(TEMP_DIR, f"temp_audio_{uuid.uuid4()}{extension}")
    print(f"Detected MIME type: {mime_type}, saving to {temp_audio_path}")
    # --- End Fix ---

    audio_file_response = None # To hold the Google File API response
    
    try:
        audio_file.save(temp_audio_path)
        print(f"Audio saved to: {temp_audio_path}")

        # 1. Upload audio to Google File API for transcription
        print(f"Uploading audio to Google File API: {temp_audio_path}")
        # --- FIX: Use the original mime_type from the request ---
        audio_file_response = genai.upload_file(
            path=temp_audio_path,
            display_name=os.path.basename(temp_audio_path),
            mime_type=mime_type 
        )
        # --- End Fix ---
        
        # --- FIX: Wait for file to be ACTIVE ---
        active_file_response = wait_for_file_active(audio_file_response)
        # --- End Fix ---

        # 2. Transcribe the entire conversation using Gemini
        print("Transcribing audio via Gemini API...")
        transcription_prompt = [
            "Please transcribe the following audio file. Provide only the text transcription and nothing else.",
            active_file_response # Use the active file
        ]
        transcription_response = gemini_model.generate_content(transcription_prompt)
        transcribed_text = transcription_response.text
        print(f"Full Transcription: '{transcribed_text}'")

        if not transcribed_text.strip():
            return jsonify({'error': 'No speech detected.'})

        # 3. Use a sophisticated prompt to extract all fields into a JSON object
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
        # CRITICAL: Always clean up the temporary file
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)
            print(f"Cleaned up temp file: {temp_audio_path}")
        # CRITICAL: Always clean up the uploaded file from Google
        try:
            if audio_file_response:
                genai.delete_file(audio_file_response.name)
                print(f"Cleaned up uploaded file: {audio_file_response.name}")
        except Exception as e:
            print(f"Error cleaning up uploaded file (it may auto-delete): {e}")

@app.route('/transcribe', methods=['POST'])
def transcribe_field():
    print("\n--- Request received for single field transcription ---")
    if gemini_model is None:
        return jsonify({'error': 'Gemini model failed to load. Check server logs.'}), 500

    if 'audio_data' not in request.files:
        return jsonify({'error': 'No audio file found'}), 400

    audio_file = request.files['audio_data']

    # --- FIX: Use the browser's MIME type to determine extension ---
    mime_type = audio_file.mimetype
    extension = get_extension_from_mimetype(mime_type)
    temp_audio_path = os.path.join(TEMP_DIR, f"temp_audio_{uuid.uuid4()}{extension}")
    print(f"Detected MIME type: {mime_type}, saving to {temp_audio_path}")
    # --- End Fix ---
    
    audio_file_response = None # To hold the Google File API response
    
    try:
        audio_file.save(temp_audio_path)
        print(f"Audio saved to: {temp_audio_path}")
        
        # 1. Upload audio to Google File API
        print(f"Uploading audio to Google File API: {temp_audio_path}")
        # --- FIX: Use the original mime_type from the request ---
        audio_file_response = genai.upload_file(
            path=temp_audio_path,
            display_name=os.path.basename(temp_audio_path),
            mime_type=mime_type
        )
        # --- End Fix ---
        
        # --- FIX: Wait for file to be ACTIVE ---
        active_file_response = wait_for_file_active(audio_file_response)
        # --- End Fix ---

        # 2. Transcribe audio using Gemini
        print("Transcribing audio via Gemini API...")
        transcription_prompt = [
            "Please transcribe the following audio file. Provide only the text transcription and nothing else.",
            active_file_response # Use the active file
        ]
        transcription_response = gemini_model.generate_content(transcription_prompt)
        transcribed_text = transcription_response.text
        print(f"Transcription result: '{transcribed_text}'")

        if not transcribed_text.strip():
            return jsonify({'text': ''})

        return jsonify({'text': transcribed_text})

    except Exception as e:
        print(f"An error occurred during transcription: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        # CRITICAL: Always clean up the temporary file
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)
            print(f"Cleaned up temp file: {temp_audio_path}")
        # CRITICAL: Always clean up the uploaded file from Google
        try:
            if audio_file_response:
                genai.delete_file(audio_file_response.name)
                print(f"Cleaned up uploaded file: {audio_file_response.name}")
        except Exception as e:
            print(f"Error cleaning up uploaded file (it may auto-delete): {e}")

# This block is for local development.
# Render will use a WSGI server like Gunicorn and will not run this.
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)