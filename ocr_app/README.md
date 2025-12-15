# OCR Medical Document Processing Backend

This folder contains a simple Python web service designed for deployment on Google Cloud Run.  It accepts PDF or image files via a multipart form upload, saves them to Cloud Storage, extracts text using Document AI, and persists the results to Firestore.  The service can handle multiple files in a single request, making it suitable for drag‑and‑drop interfaces in medical workflows.

## Prerequisites

To use this backend you’ll need:

1. **A Google Cloud project with the following services enabled**:
   - Document AI
   - Cloud Storage
   - Firestore (in Native mode)
   - Cloud Run or Cloud Functions for deployment
2. **A Document AI processor ID** – the code expects a generic OCR processor (type `Document OCR`).  You can create one in the Document AI console; note the processor ID and region.
3. **A Cloud Storage bucket** where uploaded documents will be stored.  The bucket name must be configured via an environment variable.
4. **Service account permissions** allowing access to the processor, the bucket, and Firestore.  Assign the roles `Document AI API User`, `Storage Object Admin`, and `Datastore User` (Firestore permissions) to the service account used by Cloud Run.

## Environment variables

The service reads configuration from environment variables.  When deploying to Cloud Run, set the following variables:

| Variable | Description |
|---------|-------------|
| `PROJECT_ID` | Google Cloud project ID. |
| `PROCESSOR_ID` | ID of your Document AI processor. |
| `PROCESSOR_LOCATION` | Region of the processor (e.g. `us`). |
| `BUCKET_NAME` | Name of the Cloud Storage bucket for uploads. |

## API endpoints

The service exposes a single endpoint:

### `POST /upload`

Accepts one or more files via a multipart form field named `files`.  For each file:

1. Saves the file to the configured Cloud Storage bucket.
2. Sends the file bytes to the Document AI OCR processor.
3. Stores the extracted plain text and the full processor response in Firestore under the `documents` collection.

The response is JSON with an array of objects containing the original filename and the extracted text.  You can expand the code to include additional fields (e.g. summaries or structured data) depending on your needs.

## Deploying to Cloud Run

1. Build the container image:

```bash
gcloud builds submit --tag gcr.io/<PROJECT_ID>/ocr-backend ./ocr_app
```

2. Deploy to Cloud Run:

```bash
gcloud run deploy tbi-backend \
    --image gcr.io/<PROJECT_ID>/ocr-backend \
    --platform managed \
    --region us-central1 \
    --allow-unauthenticated \
    --set-env-vars PROJECT_ID=<PROJECT_ID>,PROCESSOR_ID=<PROCESSOR_ID>,PROCESSOR_LOCATION=us,BUCKET_NAME=<BUCKET_NAME>
```

Replace placeholders (`<PROJECT_ID>`, `<PROCESSOR_ID>`, etc.) with your actual values.  You can restrict unauthenticated access if the service is internal; in that case remove `--allow-unauthenticated` and configure IAM accordingly.

## Front‑end integration

To integrate this backend with a front‑end drag‑and‑drop interface, send a `multipart/form-data` POST request to `/upload` containing one or more files named `files`.  The endpoint returns the extracted text for each file, which you can display or further process on the client side.
