// Basic drag-and-drop uploader for medical documents

const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const fileList = document.getElementById('file-list');
const resultDiv = document.getElementById('result');

// Replace this with your deployed Cloud Run service URL, e.g. https://tbi-backend-abcdef-uc.a.run.app/upload
const BACKEND_UPLOAD_URL = 'REPLACE_WITH_BACKEND_URL';

dropZone.addEventListener('click', () => fileInput.click());

dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('hover');
});

dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('hover');
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('hover');
    const files = Array.from(e.dataTransfer.files);
    handleFiles(files);
});

fileInput.addEventListener('change', () => {
    const files = Array.from(fileInput.files);
    handleFiles(files);
});

function handleFiles(files) {
    fileList.innerHTML = '';
    resultDiv.style.display = 'none';
    const formData = new FormData();
    files.forEach((file) => {
        formData.append('files', file);
        const item = document.createElement('div');
        item.className = 'file-item';
        item.textContent = file.name;
        fileList.appendChild(item);
    });
    if (files.length > 0) {
        uploadFiles(formData);
    }
}

async function uploadFiles(formData) {
    dropZone.textContent = 'Uploading…';
    try {
        const response = await fetch(BACKEND_UPLOAD_URL, {
            method: 'POST',
            body: formData,
        });
        if (!response.ok) {
            throw new Error(`Upload failed: ${response.statusText}`);
        }
        const data = await response.json();
        showResults(data);
    } catch (error) {
        resultDiv.style.display = 'block';
        resultDiv.innerHTML = `<strong>Error:</strong> ${error.message}`;
    } finally {
        dropZone.textContent = 'Drag & drop files here or click to select';
    }
}

function showResults(data) {
    resultDiv.style.display = 'block';
    resultDiv.innerHTML = '';
    data.forEach((entry) => {
        const div = document.createElement('div');
        div.innerHTML = `<strong>${entry.filename}</strong>`;
        // Display the rendered HTML report if available
        if (entry.report_html) {
            div.innerHTML += `<div style="border:1px solid #ccc;padding:8px;margin-top:4px;">${entry.report_html}</div>`;
        }
        // Provide a link to download the PDF report if available
        if (entry.report_pdf_gcs_uri) {
            // Convert gs:// URI to HTTPS URL for download (publicly accessible if bucket is public)
            const httpsUrl = entry.report_pdf_gcs_uri.startsWith('gs://')
                ? 'https://storage.googleapis.com/' + entry.report_pdf_gcs_uri.substring(5)
                : entry.report_pdf_gcs_uri;
            div.innerHTML += `<p><a href="${httpsUrl}" target="_blank">Download PDF Report</a></p>`;
        }
        // If no report, fallback to showing text
        if (!entry.report_html && entry.text) {
            div.innerHTML += `<br/><pre>${entry.text}</pre>`;
        }
        resultDiv.appendChild(div);
    });
}
