document.addEventListener('DOMContentLoaded', () => {
    const uploadForm = document.getElementById('upload-form');
    const audioFileInput = document.getElementById('audio-file');
    const fileNameDisplay = document.getElementById('file-name');
    const analyzeButton = document.getElementById('analyze-button');
    const loadingSection = document.getElementById('loading');
    const resultsSection = document.getElementById('results');
    const transcriptDiv = document.getElementById('transcript');
    const feedbackDiv = document.getElementById('feedback');
    const strengthsList = document.getElementById('strengths-list');
    const weaknessesList = document.getElementById('weaknesses-list');
    const ratingValue = document.getElementById('rating-value');

    // Update file name display when a file is selected
    audioFileInput.addEventListener('change', () => {
        if (audioFileInput.files.length > 0) {
            fileNameDisplay.textContent = audioFileInput.files[0].name;
        } else {
            fileNameDisplay.textContent = 'No file chosen';
        }
    });

    // Handle form submission
    uploadForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        // Validate file selection
        if (audioFileInput.files.length === 0) {
            alert('Please select an audio file');
            return;
        }
        
        // Check file type
        const file = audioFileInput.files[0];
        const fileType = file.type;
        if (!fileType.startsWith('audio/')) {
            alert('Please select a valid audio file');
            return;
        }
        
        // Show loading, hide results
        loadingSection.classList.remove('hidden');
        resultsSection.classList.add('hidden');
        analyzeButton.disabled = true;
        
        // Create form data for file upload
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            // Send request to server
            const response = await fetch('/transcribe_analyze', {
                method: 'POST',
                body: formData
            });
            
            // Parse response
            const data = await response.json();
            
            if (response.ok) {
                // Display results
                transcriptDiv.textContent = data.transcript || 'No transcript generated';
                feedbackDiv.textContent = data.feedback || 'No feedback generated';
                
                // Display strengths
                strengthsList.innerHTML = '';
                if (data.strengths && data.strengths.length > 0) {
                    data.strengths.forEach(strength => {
                        const li = document.createElement('li');
                        li.textContent = strength;
                        strengthsList.appendChild(li);
                    });
                } else {
                    const li = document.createElement('li');
                    li.textContent = 'No specific strengths identified';
                    li.classList.add('no-items');
                    strengthsList.appendChild(li);
                }
                
                // Display weaknesses
                weaknessesList.innerHTML = '';
                if (data.weaknesses && data.weaknesses.length > 0) {
                    data.weaknesses.forEach(weakness => {
                        const li = document.createElement('li');
                        li.textContent = weakness;
                        weaknessesList.appendChild(li);
                    });
                } else {
                    const li = document.createElement('li');
                    li.textContent = 'No specific areas for improvement identified';
                    li.classList.add('no-items');
                    weaknessesList.appendChild(li);
                }
                
                // Display rating
                ratingValue.textContent = data.rating || '0';
                
                // Set rating color based on value
                if (data.rating) {
                    if (data.rating >= 8) {
                        ratingValue.className = 'rating-high';
                    } else if (data.rating >= 5) {
                        ratingValue.className = 'rating-medium';
                    } else {
                        ratingValue.className = 'rating-low';
                    }
                }
                
                resultsSection.classList.remove('hidden');
            } else {
                // Show error
                alert(`Error: ${data.error || 'Unknown error occurred'}`);
            }
        } catch (error) {
            console.error('Error:', error);
            alert('An error occurred during processing. Please try again.');
        } finally {
            // Hide loading
            loadingSection.classList.add('hidden');
            analyzeButton.disabled = false;
        }
    });
});
