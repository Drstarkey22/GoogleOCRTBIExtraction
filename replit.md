# OCR Medical Document Processing App

## Overview
This is a medical document processing application that uses Google Document AI for OCR. The application has two components:

1. **Frontend** - A static HTML/JS drag-and-drop interface for uploading medical documents (served from Replit)
2. **Backend** - A Flask API deployed on Google Cloud Run that processes documents using Document AI, stores results in Firestore, and generates interpretation reports

## Project Structure
```
front_end/          # Static frontend files served by Replit
  index.html        # Main upload interface
  app.js            # Frontend JavaScript with drag-and-drop handling
server.py           # Simple Python HTTP server for serving frontend
main.py             # Backend Flask app (for reference/Cloud Run deployment)
requirements.txt    # Backend Python dependencies
report_template.html.jinja  # Jinja2 template for PDF reports
```

## Running Locally
The frontend is served on port 5000 using `python server.py`. It connects to the existing Cloud Run backend at:
`https://tbi-backend-447216852170.us-central1.run.app/upload`

## Backend Configuration (Google Cloud)
The backend requires these environment variables when deployed to Cloud Run:
- `PROJECT_ID` - Google Cloud project ID
- `PROCESSOR_ID` - Document AI OCR processor ID
- `PROCESSOR_LOCATION` - Region of processor (e.g., `us`)
- `BUCKET_NAME` - Cloud Storage bucket for uploads
- `GEN_EXTRACTOR_ID` - Custom extractor processor ID (optional)

## Features
- Drag-and-drop file upload for medical PDFs
- Document OCR using Google Document AI
- Structured field extraction for medical tests (RightEye, CTSIB/BTrackS, Creyos)
- Automatic interpretation report generation
- PDF report download

## CTSIB/BTrackS Field Mapping (Important)
The BTrackS/mCTSIB documents contain TWO types of values:
1. **Path Length (cm)** - The raw sway measurement in centimeters (e.g., 35, 33, 53, 153)
2. **Percentile** - The percentile ranking compared to normative data (e.g., 1%, 12%, 5%, 2%)

The report should display PERCENTILE values, not path lengths. The backend code maps:
- Path length fields → `standard_path_length`, `proprioception_path_length`, etc.
- Percentile fields → `standard_score_percentile`, `proprioception_score_percentile`, etc.

If the Document AI Custom Extractor returns incorrect field names, update the alias mapping in `main.py` within the `_merge_fields` function.
