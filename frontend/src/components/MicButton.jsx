import React, { useState, useRef } from 'react';

// --- NEW/UPDATED ICONS ---

// 1. Microphone Icon (Idle)
const MicIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" className="bi bi-mic-fill" viewBox="0 0 16 16">
        <path d="M5 3a3 3 0 0 1 6 0v5a3 3 0 0 1-6 0z"/>
        <path d="M3.5 6.5A.5.5 0 0 1 4 7v1a4 4 0 0 0 8 0V7a.5.5 0 0 1 1 0v1a5 5 0 0 1-4.5 4.975V15h3a.5.5 0 0 1 0 1h-7a.5.5 0 0 1 0-1h3v-2.025A5 5 0 0 1 3 8V7a.5.5 0 0 1 .5-.5"/>
    </svg>
);

// 2. Stop Icon (Recording)
const StopIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" className="bi bi-stop-fill" viewBox="0 0 16 16">
        <path d="M5 3.5h6A1.5 1.5 0 0 1 12.5 5v6A1.5 1.5 0 0 1 11 12.5H5A1.5 1.5 0 0 1 3.5 11V5A1.5 1.5 0 0 1 5 3.5"/>
    </svg>
);

// 3. Spinner Icon (Processing)
const SpinnerIcon = () => (
    <svg className="animate-spin" xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
    </svg>
);

// --- UPDATED MICBUTTON COMPONENT ---

function MicButton({ onTranscription, fieldId, onStatusChange }) {
    const [isRecording, setIsRecording] = useState(false);
    const [isProcessing, setIsProcessing] = useState(false); // <-- ADDED STATE
    const mediaRecorderRef = useRef(null);
    const audioChunksRef = useRef([]);

    const handleMicClick = () => {
        if (isRecording) {
            stopRecording();
        } else {
            startRecording();
        }
    };

    const startRecording = () => {
        navigator.mediaDevices.getUserMedia({ audio: true })
            .then(stream => {
                setIsRecording(true);
                onStatusChange(`Recording for ${fieldId}...`, 'blue');
                const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
                mediaRecorderRef.current = mediaRecorder;
                audioChunksRef.current = [];

                mediaRecorder.addEventListener("dataavailable", event => {
                    audioChunksRef.current.push(event.data);
                });

                mediaRecorder.addEventListener("stop", async () => {
                    const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
                    await transcribeAudio(audioBlob);
                });

                mediaRecorder.start();
            })
            .catch(err => {
                console.error("Mic access error:", err);
                onStatusChange("Error: Could not access microphone.", 'red');
            });
    };

    const stopRecording = () => {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
            mediaRecorderRef.current.stop();
            mediaRecorderRef.current.stream.getTracks().forEach(track => track.stop());
            setIsRecording(false);
            onStatusChange(`Transcribing for ${fieldId}...`, 'blue');
            // Note: isProcessing will be set to true inside transcribeAudio
        }
    };

    const transcribeAudio = async (audioBlob) => {
        setIsProcessing(true); // <-- SET PROCESSING TRUE
        const formData = new FormData();
        formData.append('audio_data', audioBlob);

        try {
            const response = await fetch('http://127.0.0.1:5000/transcribe', {
                method: 'POST',
                body: formData
            });
            if (!response.ok) throw new Error('Server error during transcription');

            const result = await response.json();
            if (result.error) throw new Error(result.error);
            
            onTranscription(fieldId, result.text);
            onStatusChange(`Transcription completed.`, 'green');

        } catch (error) {
            console.error('Error transcribing audio:', error);
            onStatusChange(`Error: ${error.message}`, 'red');
        } finally {
            audioChunksRef.current = [];
            setIsProcessing(false); // <-- SET PROCESSING FALSE
        }
    };

    // --- UPDATED RENDER ---
    
    // Dynamically set classes based on state
    const buttonClasses = `absolute inset-y-0 right-0 flex items-center pr-3 ${
        isProcessing
            ? 'cursor-not-allowed text-gray-400'
            : isRecording
            ? 'animate-pulse text-red-500'
            : 'text-gray-500 hover:text-blue-600'
    }`;

    return (
        <button
            type="button"
            onClick={handleMicClick}
            disabled={isProcessing} // Disable button while processing
            className={buttonClasses}
            aria-label={`Transcribe for ${fieldId}`}
        >
            {/* Conditionally render the correct icon */}
            {isProcessing ? (
                <SpinnerIcon />
            ) : isRecording ? (
                <StopIcon />
            ) : (
                <MicIcon />
            )}
        </button>
    );
}

export default MicButton;
