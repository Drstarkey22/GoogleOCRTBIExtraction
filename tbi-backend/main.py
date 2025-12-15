from fastapi import FastAPI, Request
import uvicorn
from googleapiclient.discovery import build
from google.cloud import documentai_v1 as documentai
from google.auth import default
from io import BytesIO
from googleapiclient.http import MediaIoBaseDownload
import os
import json

import vertexai
from vertexai.generative_models import GenerativeModel


app = FastAPI()

# ---------- CONFIG FROM ENVIRONMENT ----------

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
DOC_PROCESSOR_LOCATION = "us"  # Document AI region
DOC_PROCESSOR_ID = os.environ.get("DOC_AI_PROCESSOR_ID")  # e.g. 26145f8a54ef762a

VERTEX_LOCATION = os.environ.get("VERTEX_LOCATION", "us-central1")
GEMINI_MODEL_NAME = os.environ.get("GEMINI_MODEL_NAME", "gemini-1.5-pro")


# ---------- DRIVE HELPERS ----------

def get_drive_client():
    creds, _ = default(scopes=["https://www.googleapis.com/auth/drive.readonly"])
    return build("drive", "v3", credentials=creds)


def download_pdf_from_drive(file_id: str) -> bytes:
    drive = get_drive_client()
    request = drive.files().get_media(
        fileId=file_id,
        supportsAllDrives=True,  # important for Shared Drives
    )

    fh = BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    return fh.getvalue()


# ---------- DOCUMENT AI OCR ----------

def run_document_ocr(pdf_bytes: bytes) -> str:
    if not PROJECT_ID:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT env var is not set.")
    if not DOC_PROCESSOR_ID:
        raise RuntimeError("DOC_AI_PROCESSOR_ID env var is not set.")

    client = documentai.DocumentProcessorServiceClient()
    name = client.processor_path(PROJECT_ID, DOC_PROCESSOR_LOCATION, DOC_PROCESSOR_ID)

    raw_document = documentai.RawDocument(
        content=pdf_bytes,
        mime_type="application/pdf",
    )
    request = documentai.ProcessRequest(
        name=name,
        raw_document=raw_document,
    )
    result = client.process_document(request=request)
    return result.document.text


# ---------- GEMINI PROMPT FOR CTSIB ----------

def build_ctsib_prompt(ocr_text: str) -> str:
    return f"""
You are an assistant that extracts structured numerical CTSIB (Clinical Test of Sensory Interaction on Balance) results.

The input is OCR text from a CTSIB report. The report always contains four baseline conditions:

1. Standard (Eyes Open/Firm)
2. Proprioception (Eyes Closed/Firm)
3. Vision (Eyes Open/Foam)
4. Vestibular (Eyes Closed/Foam)

Extract the following fields:

For each condition, return:
{{
  "label": "EO_FIRM" | "EC_FIRM" | "EO_FOAM" | "EC_FOAM",
  "path_length_cm": number | null,
  "percentile": number | null
}}

Where the mapping is:
- Standard (Eyes Open/Firm) -> EO_FIRM
- Proprioception (Eyes Closed/Firm) -> EC_FIRM
- Vision (Eyes Open/Foam) -> EO_FOAM
- Vestibular (Eyes Closed/Foam) -> EC_FOAM

Also extract:
- composite_path_length_cm: number | null
- summary_flags: list of clinically relevant notes, such as:
  "bottom_quartile_performance",
  "high_sway_foam_conditions",
  "vestibular_impairment_likely"

RULES:
- Percentile values are reported as "Percentile=1%" etc. Convert "1%" -> 1 (integer).
- Path Length should be numeric only (strip "cm").
- If any value is missing, return null for that field.
- If you are unsure, be conservative and set null.
- Do NOT include any keys other than the ones defined in the schema above.
- Do NOT include explanations or any text outside JSON.
- Output MUST be valid JSON.

Return a SINGLE JSON object with this schema:

{{
  "test_type": "CTSIB",
  "conditions": [
    {{
      "label": "...",
      "path_length_cm": ...,
      "percentile": ...
    }}
  ],
  "composite_path_length_cm": ...,
  "summary_flags": [ ... ]
}}

Here is the OCR text of the CTSIB report:

<<<REPORT_TEXT>>>
""".replace("<<<REPORT_TEXT>>>", ocr_text)


def extract_ctsib_from_text(ocr_text: str) -> dict:
    if not PROJECT_ID:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT env var is not set for Gemini.")

    vertexai.init(project=PROJECT_ID, location=VERTEX_LOCATION)
    model = GenerativeModel(GEMINI_MODEL_NAME)

    prompt = build_ctsib_prompt(ocr_text)
    response = model.generate_content(prompt)

    # Depending on SDK version, response.text or candidates[0].content.parts[0].text
    try:
        raw_text = response.text
    except AttributeError:
        raw_text = response.candidates[0].content.parts[0].text

    raw_text = raw_text.strip()
    data = json.loads(raw_text)
    return data


# ---------- CTSIB VALIDATION ----------

def validate_ctsib(ctsib: dict) -> dict:
    """
    Apply sanity checks to CTSIB JSON.
    Returns { "status": "ok" | "needs_review" | "invalid", "warnings": [...] }
    """
    warnings = []
    status = "ok"

    expected_labels = {"EO_FIRM", "EC_FIRM", "EO_FOAM", "EC_FOAM"}
    conditions = ctsib.get("conditions") or []

    # Ensure test_type
    if ctsib.get("test_type") != "CTSIB":
        warnings.append("test_type is not CTSIB")
        status = "needs_review"

    # Check that all four labels appear
    seen_labels = set()
    for cond in conditions:
        lbl = cond.get("label")
        if lbl:
            seen_labels.add(lbl)
    missing = expected_labels - seen_labels
    if missing:
        warnings.append(f"Missing conditions: {', '.join(sorted(missing))}")
        status = "needs_review"

    # Range checks for each condition
    for cond in conditions:
        lbl = cond.get("label", "UNKNOWN")
        pl = cond.get("path_length_cm")
        pct = cond.get("percentile")

        if pl is not None:
            try:
                pl_val = float(pl)
                if not (0 <= pl_val <= 1000):
                    warnings.append(f"{lbl}: path_length_cm out of expected range (0–1000): {pl}")
                    status = "needs_review"
            except Exception:
                warnings.append(f"{lbl}: path_length_cm is not numeric: {pl}")
                status = "needs_review"

        if pct is not None:
            try:
                pct_val = float(pct)
                if not (0 <= pct_val <= 100):
                    warnings.append(f"{lbl}: percentile out of expected range (0–100): {pct}")
                    status = "needs_review"
            except Exception:
                warnings.append(f"{lbl}: percentile is not numeric: {pct}")
                status = "needs_review"

    # Composite checks
    comp = ctsib.get("composite_path_length_cm")
    if comp is not None:
        try:
            comp_val = float(comp)
            if not (0 <= comp_val <= 4000):
                warnings.append(f"Composite path length out of range (0–4000): {comp}")
                status = "needs_review"
        except Exception:
            warnings.append(f"Composite path length is not numeric: {comp}")
            status = "needs_review"
    else:
        warnings.append("Composite path length missing.")
        status = max(status, "needs_review")

    # If JSON is obviously broken
    if not isinstance(conditions, list) or not conditions:
        warnings.append("conditions is missing or not a list.")
        status = "invalid"

    return {
        "status": status,
        "warnings": warnings
    }


# ---------- API ENDPOINT ----------

@app.post("/process-test")
async def process_test(request: Request):
    payload = await request.json()
    file_id = payload["fileId"]
    test_type = (payload.get("testType") or "").upper()
    patient_id = payload.get("patientId", "")
    dos_date = payload.get("dosDate", "")

    # 1. Download PDF from Drive
    pdf_bytes = download_pdf_from_drive(file_id)

    # 2. OCR via Document AI
    ocr_text = run_document_ocr(pdf_bytes)

    result = {
        "status": "ok",
        "chars": len(ocr_text),
        "testType": test_type,
    }

    # 3. If CTSIB, run Gemini extraction + validation
    if test_type == "CTSIB":
        try:
            ctsib_data = extract_ctsib_from_text(ocr_text)
            validation = validate_ctsib(ctsib_data)
            result["ctsib"] = ctsib_data
            result["ctsibValidation"] = validation
        except Exception as e:
            # Do not crash the whole request; log and mark as error
            print("CTSIB extraction error:", str(e))
            result["ctsibError"] = str(e)

    print(
        f"OCR OK for patient={patient_id}, date={dos_date}, "
        f"test={test_type}, chars={len(ocr_text)}"
    )

    return result


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080)
