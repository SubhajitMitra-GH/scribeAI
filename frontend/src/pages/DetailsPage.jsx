import React, { useState, useRef } from 'react';
import Header from '../components/Header';
import StatusDisplay from '../components/StatusDisplay';
import Controls from '../components/Controls';
import MedicalForm from '../components/MedicalForm';
import myBackgroundImage from '../assets/DetailsBgd.jpg';

// --- ICONS (for the new buttons) ---
const SaveIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
    </svg>
);
const ExportIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
    </svg>
);


function DetailsPage() {
    // State for the main status display
    const [status, setStatus] = useState({
        message: "Start recording the consultation or use the mic on any field.",
        color: 'blue'
    });

    // State for the global recording feature
    const [isRecording, setIsRecording] = useState(false);
    const [isProcessing, setIsProcessing] = useState(false);

    // Refs
    const formRef = useRef(null);
    const mediaRecorderRef = useRef(null);
    const audioChunksRef = useRef([]);

    // --- Global Recording Logic (Unchanged) ---
    const handleApiResponse = (result) => {
        if (result.error) {
            setStatus({ message: `Error: ${result.error}`, color: 'red' });
            return;
        }
        const data = result.extracted_data;
        if (formRef.current) { formRef.current.fillForm(data); }
        const filledCount = Object.values(data).filter(Boolean).length;
        setStatus({
            message: `Analysis complete. ${filledCount} fields were filled. Please review.`,
            color: 'green'
        });
    };
    const processAudio = async () => {
        setStatus({ message: 'Transcribing and analyzing... Please wait.', color: 'blue' });
        setIsProcessing(true);
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        const audioFormData = new FormData();
        audioFormData.append('audio_data', audioBlob, 'consultation.webm');
        try {
            const response = await fetch('http://127.0.0.1:5000/process_audio', {
                method: 'POST',
                body: audioFormData
            });
            if (!response.ok) {
                const errorResult = await response.json();
                throw new Error(errorResult.error || `Server error: ${response.statusText}`);
            }
            const result = await response.json();
            handleApiResponse(result);
        } catch (error) {
            console.error('Error processing audio:', error);
            setStatus({ message: `Error: ${error.message}`, color: 'red' });
        } finally {
            setIsProcessing(false);
            audioChunksRef.current = [];
        }
    };
    const startRecording = () => {
        navigator.mediaDevices.getUserMedia({ audio: true })
            .then(stream => {
                const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
                mediaRecorderRef.current = mediaRecorder;
                audioChunksRef.current = [];
                mediaRecorder.addEventListener("dataavailable", event => {
                    audioChunksRef.current.push(event.data);
                });
                mediaRecorder.addEventListener("stop", processAudio);
                mediaRecorder.start();
                setIsRecording(true);
                setStatus({ message: 'Recording full consultation...', color: 'red' });
            })
            .catch(err => {
                console.error("Mic access error:", err);
                setStatus({ message: "Error: Could not access microphone.", color: 'red' });
            });
    };
    const stopRecording = () => {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
            mediaRecorderRef.current.stop();
            mediaRecorderRef.current.stream.getTracks().forEach(track => track.stop());
            setIsRecording(false);
        }
    };
    // --- End of Recording Logic ---


    // --- NEW: Button Logic ---

    /**
     * Resets just the form fields. Does not save or clear cache.
     */
    const handleResetForm = () => {
        if (formRef.current) {
            formRef.current.resetForm();
        }
        if (isRecording) {
            stopRecording();
        }
        setStatus({
            message: "Form cleared. Ready for next entry.",
            color: 'blue'
        });
    };
    
    /**
     * NEW: (Submit Button) Saves the current form data to localStorage and clears the form.
     */
    const handleSubmitRecord = () => {
         if (!formRef.current) {
            setStatus({ message: 'Error: Form reference is not available.', color: 'red' });
            return;
        }
        const currentFormData = formRef.current.getFormData();
        
        // Check if form is empty
        const isFormEmpty = Object.values(currentFormData).every(val => val === '');
        if (isFormEmpty) {
             setStatus({ message: 'Form is empty, nothing to submit.', color: 'blue' });
             return;
        }

        // 1. Get existing records
        let allRecords = [];
        try {
            allRecords = JSON.parse(localStorage.getItem('dentalCampRecords') || '[]');
        } catch (e) {
            console.error("Error parsing records from localStorage", e);
            allRecords = []; // Start fresh if cache is corrupt
        }

        // 2. Add new record
        allRecords.push(currentFormData);

        // 3. Save updated records back
        try {
            localStorage.setItem('dentalCampRecords', JSON.stringify(allRecords));
            setStatus({
                message: `Record submitted. Total: ${allRecords.length}. Ready for next entry.`,
                color: 'green'
            });
            // 4. Reset form for next entry
            handleResetForm();
        } catch (e) {
            console.error("Error saving records to localStorage", e);
            setStatus({ message: 'Error saving to local record cache.', color: 'red' });
        }
    };

    /**
     * NEW: (Export Button) Downloads ALL records from localStorage into one CSV.
     */
    const handleExportToCsv = () => {
        // 1. Get all records from cache
        let allRecords = [];
        try {
            allRecords = JSON.parse(localStorage.getItem('dentalCampRecords') || '[]');
        } catch (e) {
            console.error("Error parsing records from localStorage", e);
             setStatus({ message: 'Error reading local cache.', color: 'red' });
            return;
        }

        if (allRecords.length === 0) {
            setStatus({ message: 'No records saved to export.', color: 'blue' });
            return;
        }
        
        // 2. Generate CSV
        const headers = Object.keys(allRecords[0]);
        const headerRow = headers.join(',');
        
        const dataRows = allRecords.map(record => {
            const sanitizedValues = headers.map(header => {
                const value = record[header] || '';
                const stringValue = String(value);
                if (stringValue.includes(',') || stringValue.includes('\n') || stringValue.includes('"')) {
                    return `"${stringValue.replace(/"/g, '""')}"`;
                }
                return stringValue;
            });
            return sanitizedValues.join(',');
        }).join('\n'); // Join all rows with a newline

        const csvContent = "data:text/csv;charset=utf-8,"
            + headerRow + "\n"
            + dataRows;

        // 3. Trigger download
        const encodedUri = encodeURI(csvContent);
        const link = document.createElement("a");
        link.setAttribute("href", encodedUri);
        link.setAttribute("download", "dental_camp_records_export.csv");
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        setStatus({ message: `Successfully exported ${allRecords.length} records.`, color: 'green' });
    };
    
    /**
     * NEW: (Clear Button) Clears the localStorage cache to start a new day/session.
     */
    const handleClearCache = () => {
         if (window.confirm("Are you sure you want to clear all submitted data? This will start a new CSV file.")) {
             localStorage.removeItem('dentalCampRecords');
             setStatus({ message: 'Cleared local data. Ready to start a new session.', color: 'blue' });
         }
    }
    
    // --- Shared Logic ---
    const handleStatusChange = (message, color) => {
        setStatus({ message, color });
    };

return (
      <div
  className="relative font-sans text-gray-900"
  style={{
    backgroundImage: `url(${myBackgroundImage})`,
    backgroundAttachment: 'fixed',
    backgroundSize: 'cover',
    backgroundRepeat: 'no-repeat',
    backgroundPosition: 'center',
    minHeight: '100vh',
  }}
>
  <div className="absolute inset-0 bg-white/60 "></div>
<div className="relative container mx-auto max-w-5xl p-4 md:p-8">

                <Header />
                <main className="rounded-2xl bg-white/50 p-6 shadow-xl md:p-8">
                    <StatusDisplay status={status} isProcessing={isProcessing} />
                    
                    {/* This component will now correctly show only the record button */}
                    <Controls
                        isRecording={isRecording}
                        isProcessing={isProcessing}
                        onStart={startRecording}
                        onStop={stopRecording}
                    />
                    
                    <MedicalForm ref={formRef} onStatusChange={handleStatusChange} />

                    {/* --- THIS IS THE CHANGED PART --- */}
                    <div className="mt-8 border-t border-gray-200 pt-8 flex flex-col items-center justify-center space-y-4 md:flex-row md:space-x-4 md:space-y-0">
                        {/* ^--- I changed 'justify-end' to 'justify-center' on the line above
                        */}
                        
                        <button
                            onClick={handleResetForm}
                            disabled={isRecording || isProcessing}
                            className="w-full rounded-full bg-gray-500 px-8 py-3 font-bold text-white shadow-lg transition-all hover:bg-gray-600 focus:outline-none focus:ring-4 focus:ring-gray-300 disabled:opacity-50 md:w-auto"
                        >
                            Reset Current Form
                        </button>
                        
                        <button
                            onClick={handleSubmitRecord}
                            disabled={isRecording || isProcessing}
                            className="flex w-full items-center justify-center space-x-2 rounded-full bg-green-600 px-8 py-3 font-bold text-white shadow-lg transition-all hover:bg-green-700 focus:outline-none focus:ring-4 focus:ring-green-300 disabled:opacity-50 md:w-auto"
                        >
                            <SaveIcon />
                            <span>Submit Record</span>
                        </button>
                        
                        <button
                            onClick={handleExportToCsv}
                            disabled={isRecording || isProcessing}
                            className="flex w-full items-center justify-center space-x-2 rounded-full bg-blue-600 px-8 py-3 font-bold text-white shadow-lg transition-all hover:bg-blue-700 focus:outline-none focus:ring-4 focus:ring-blue-300 disabled:opacity-50 md:w-auto"
                        >
                            <ExportIcon />
                            <span>Export All to CSV</span>
                        </button>
                    </div>

                    {/* This "Clear All" button was already centered and remains so */}
                    <div className="mt-4 flex justify-center">
                         <button
                            onClick={handleClearCache}
                            disabled={isRecording || isProcessing}
                            className="text-sm text-red-500 hover:text-red-700 disabled:opacity-50"
                        >
                            Clear All Saved Data (Start New Day)
                        </button>
                    </div>
                </main>
            </div>
        </div>
    );;
}

export default DetailsPage;
