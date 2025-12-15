"""
Flask application for processing uploaded documents with Google Document AI and storing results in Firestore.

The `/upload` endpoint accepts multiple files via multipart/form-data.  Each file is uploaded to Cloud Storage, processed with the configured Document AI OCR processor, and stored in Firestore along with the extracted text.

Environment variables required:

* `PROJECT_ID` – ID of the Google Cloud project.
* `PROCESSOR_ID` – ID of the Document AI processor (OCR).
* `PROCESSOR_LOCATION` – Region of the processor, e.g. `us`.
* `BUCKET_NAME` – Name of the Cloud Storage bucket to store uploads.

You can deploy this application to Cloud Run by building the container image and setting these variables during deployment.
"""

import os
from typing import List, Dict

from flask import Flask, request, jsonify
from flask_cors import CORS

from google.cloud import storage  # type: ignore
from google.cloud import firestore  # type: ignore
from google.cloud import documentai_v1 as documentai  # type: ignore
from google.cloud import documentai_v1beta3 as documentai_beta  # type: ignore
from jinja2 import Template  # type: ignore
import pdfkit  # type: ignore
from datetime import datetime
from google.protobuf.json_format import MessageToDict  # type: ignore
import json

app = Flask(__name__)
CORS(app)

PROJECT_ID = os.getenv("PROJECT_ID")
OCR_LOCATION = os.getenv("OCR_LOCATION", os.getenv("LOCATION", "us"))
PROCESSOR_ID = os.getenv("PROCESSOR_ID")
PROCESSOR_LOCATION = os.getenv("PROCESSOR_LOCATION", "us")
BUCKET_NAME = os.getenv("BUCKET_NAME")
GEN_EXTRACTOR_ID = os.getenv("GEN_EXTRACTOR_ID") or os.getenv("EXTRACTOR_PROCESSOR_ID")
GEN_EXTRACTOR_LOCATION = os.getenv("GEN_EXTRACTOR_LOCATION", os.getenv("EXTRACTOR_LOCATION", "us"))

# Path to the report template file. By default we use the HTML-based Jinja2
# template which is converted to a PDF. You can override this via the
# REPORT_TEMPLATE_PATH environment variable when deploying.
TEMPLATE_PATH = os.getenv("REPORT_TEMPLATE_PATH", "report_template.html.jinja")


def get_storage_client() -> storage.Client:
    """Instantiate and return a Cloud Storage client."""
    return storage.Client(project=PROJECT_ID)


def get_firestore_client() -> firestore.Client:
    """Instantiate and return a Firestore client."""
    return firestore.Client(project=PROJECT_ID)


def process_document(content: bytes, mime_type: str = "application/pdf") -> documentai.Document:
    """Send the given bytes to the Document AI OCR processor and return the processed document.

    Args:
        content: Raw bytes of the document to process.
        mime_type: MIME type of the document (default: application/pdf).

    Returns:
        A `documentai.Document` object containing extracted text and layout information.
    """
    if not (PROJECT_ID and PROCESSOR_ID):
        raise RuntimeError("PROJECT_ID and PROCESSOR_ID must be set in environment variables")
    name = f"projects/{PROJECT_ID}/locations/{PROCESSOR_LOCATION}/processors/{PROCESSOR_ID}"
    client = documentai.DocumentProcessorServiceClient(client_options={"api_endpoint": f"{OCR_LOCATION}-documentai.googleapis.com"})
    raw_document = documentai.RawDocument(content=content, mime_type=mime_type)
    request = documentai.ProcessRequest(name=name, raw_document=raw_document)
    result = client.process_document(request=request)
    return result.document


def upload_to_bucket(file_obj, filename: str) -> str:
    """Upload the file object to the configured bucket and return its public URI.

    Args:
        file_obj: A file-like object positioned at the beginning of the file.
        filename: Name to use for the blob in Cloud Storage.

    Returns:
        The URI of the uploaded object (gs://bucket/file).
    """
    if not BUCKET_NAME:
        raise RuntimeError("BUCKET_NAME must be set in environment variables")
    client = get_storage_client()
    bucket = client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)
    # Upload file content
    blob.upload_from_file(file_obj)
    return f"gs://{BUCKET_NAME}/{filename}"

def upload_json_to_bucket(data: Dict, filename: str) -> str:
    """Upload a JSON-serializable dictionary as a JSON file to Cloud Storage.

    Args:
        data: Dictionary to serialize to JSON and upload.
        filename: Name of the JSON file in Cloud Storage.

    Returns:
        gs:// URI of the uploaded JSON file.
    """
    if not BUCKET_NAME:
        raise RuntimeError("BUCKET_NAME must be set in environment variables")
    client = get_storage_client()
    bucket = client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_string(json.dumps(data), content_type="application/json")
    return f"gs://{BUCKET_NAME}/{filename}"

def upload_bytes_to_bucket(data: bytes, filename: str, content_type: str = "application/octet-stream") -> str:
    """Upload raw bytes (e.g. PDF) to Cloud Storage and return the gs:// URI.

    Args:
        data: Binary data to upload.
        filename: The name of the object in Cloud Storage.
        content_type: Optional MIME type of the object.

    Returns:
        The gs:// URI of the uploaded object.
    """
    if not BUCKET_NAME:
        raise RuntimeError("BUCKET_NAME must be set in environment variables")
    client = get_storage_client()
    bucket = client.bucket(BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_string(data, content_type=content_type)
    return f"gs://{BUCKET_NAME}/{filename}"

def interpret_dysfunction(score: int) -> str:
    """Return qualitative interpretation based on dysfunction score."""
    if score <= 24:
        return "Severe dysfunction \U0001F6A9"
    elif score < 50:
        return "Moderate dysfunction \U0001F7E0"
    elif score < 75:
        return "Mild dysfunction \U0001F7E1"
    else:
        return "Normal"

def interpret_percentile(pct: int) -> str:
    """Interpret percentile scores for posturography fields."""
    if pct < 25:
        return "Abnormal"
    elif pct < 75:
        return "Below Average"
    else:
        return "Normal"

def interpret_psy_score(score: int, scale: str) -> str:
    """Interpret neuropsychiatric scores."""
    if scale == "rpq":
        if score < 16:
            return "Not indicative of Post-Concussion Syndrome"
        elif score <= 35:
            return "Indicative of Post-Concussion Syndrome \U0001F7E0"
        else:
            return "PCS; predictive of moderate–severe functional limitations \U0001F6A9"
    if scale == "pcl":
        if score < 31:
            return "Sub-threshold; does not meet criteria for PTSD"
        elif score <= 33:
            return "Probable PTSD \U0001F7E0"
        else:
            return "Significant likelihood of PTSD \U0001F6A9"
    if scale == "psqi":
        return "Good sleep quality" if score <= 5 else "Poor sleep quality \U0001F6A9"
    if scale == "phq":
        if score <= 4:
            return "Minimal depression"
        elif score <= 9:
            return "Mild depression \U0001F7E1"
        elif score <= 14:
            return "Moderate depression \U0001F7E0"
        elif score <= 19:
            return "Moderately severe depression \U0001F6A9"
        else:
            return "Severe depression \U0001F6A9"
    if scale == "gad":
        if score <= 4:
            return "Minimal anxiety"
        elif score <= 9:
            return "Mild anxiety \U0001F7E1"
        elif score <= 14:
            return "Moderate anxiety \U0001F7E0"
        else:
            return "Severe anxiety \U0001F6A9"
    return ""

def render_report(fields: Dict, patient_name: str, dob: str, doi: str, dos: str, vng: bool, ct_sib: bool, creyos: bool) -> str:
    """Render the final interpretation report using a Jinja2 template."""
    # Compute age from date of birth
    age = ""
    try:
        age = (datetime.now().date() - datetime.strptime(dob, "%m/%d/%Y").date()).days // 365
    except Exception:
        age = ""
    # Prepare interpretation values
    pursuits_score = int(fields.get("pursuits_score", 0) or 0)
    saccades_score = int(fields.get("saccades_score", 0) or 0)
    raw_fx = (fields.get("fixations_score") or fields.get("Fixations score") or "").strip()
    fixations_score = int(raw_fx) if raw_fx.isdigit() else None
    raw_ds = (fields.get("dysfunctional_scale") or fields.get("Dysfunctional scale") or fields.get("eyeq_score") or "").strip()
    dysfunctional_scale = int(raw_ds) if raw_ds.isdigit() else None
    def _parse_percentile(val) -> int:
        """Parse a percentile value, stripping %, ordinal suffixes, and extracting just the number."""
        import re
        if val is None:
            return 0
        s = str(val).replace("%", "").replace("nd", "").replace("rd", "").replace("th", "").replace("st", "").strip()
        # Extract first number from string
        match = re.search(r'\d+', s)
        return int(match.group()) if match else 0

    standard_score = _parse_percentile(fields.get("standard_score_percentile"))
    proprio_score = _parse_percentile(fields.get("proprioception_score_percentile"))
    visual_score = _parse_percentile(fields.get("visual_score_percentile"))
    vestibular_score = _parse_percentile(fields.get("vestibular_score_percentile"))
    # Neuropsychiatric scores
    rpq_score = int(fields.get("rpq_score", 0) or 0)
    pcl_5_score = int(fields.get("pcl_5_score", 0) or 0)
    psqi_score = int(fields.get("psqi_score", 0) or 0)
    phq_9_score = int(fields.get("phq_9_score", 0) or 0)
    gad_7_score = int(fields.get("gad_7_score", 0) or 0)
    # Load template (HTML)
    with open(TEMPLATE_PATH) as tf:
        template = Template(tf.read())
    return template.render(
        patient_full_name=patient_name,
        dob=dob,
        doi=doi,
        dos=dos,
        age=age,
        vng=vng,
        ct_sib=ct_sib,
        creyos=creyos,
        pursuits_score=pursuits_score,
        saccades_score=saccades_score,
        fixations_score=(fixations_score if fixations_score is not None else "N/A"),
        dysfunctional_scale=(dysfunctional_scale if dysfunctional_scale is not None else "N/A"),
        pursuits_interpretation=interpret_dysfunction(pursuits_score),
        saccades_interpretation=interpret_dysfunction(saccades_score),
        fixations_interpretation=(interpret_dysfunction(fixations_score) if isinstance(fixations_score, int) else "N/A"),
        dysfunctional_interpretation=(interpret_dysfunction(dysfunctional_scale) if isinstance(dysfunctional_scale, int) else "N/A"),
        standard_score=standard_score,
        proprioception_score=proprio_score,
        visual_score=visual_score,
        vestibular_score=vestibular_score,
        standard_interpretation=interpret_percentile(standard_score),
        proprioception_interpretation=interpret_percentile(proprio_score),
        visual_interpretation=interpret_percentile(visual_score),
        vestibular_interpretation=interpret_percentile(vestibular_score),
        rpq_score=rpq_score,
        pcl_5_score=pcl_5_score,
        psqi_score=psqi_score,
        phq_9_score=phq_9_score,
        gad_7_score=gad_7_score,
        rpq_interpretation=interpret_psy_score(rpq_score, "rpq"),
        pcl_5_interpretation=interpret_psy_score(pcl_5_score, "pcl"),
        psqi_interpretation=interpret_psy_score(psqi_score, "psqi"),
        phq_9_interpretation=interpret_psy_score(phq_9_score, "phq"),
        gad_7_interpretation=interpret_psy_score(gad_7_score, "gad"),
    )

def html_to_pdf(html_content: str) -> bytes:
    """Convert an HTML string to PDF bytes using pdfkit.

    Requires wkhtmltopdf to be installed in the container.

    Args:
        html_content: HTML content to convert.

    Returns:
        PDF content as bytes.
    """
    # pdfkit.from_string returns bytes when output_path=False
    return pdfkit.from_string(html_content, False)

def extract_fields_generative(gcs_uri: str) -> Dict:
    """Extract structured fields using Document AI Custom Extractor.

    Replaces the (unsupported) GenerativeExtractRequest/generative_extract path.
    Downloads the PDF bytes from GCS and sends raw bytes to the Custom Extractor.
    """
    if not GEN_EXTRACTOR_ID:
        return {}

    if not gcs_uri.startswith("gs://"):
        raise ValueError(f"Expected gs:// URI, got: {gcs_uri}")

    # Parse gs://bucket/object
    _, _, rest = gcs_uri.partition("gs://")
    bucket_name, _, blob_name = rest.partition("/")
    if not bucket_name or not blob_name:
        raise ValueError(f"Invalid GCS URI: {gcs_uri}")

    # Download bytes from GCS
    storage_client = get_storage_client()
    data = storage_client.bucket(bucket_name).blob(blob_name).download_as_bytes()

    # Call Custom Extractor with raw bytes
    client = documentai_beta.DocumentProcessorServiceClient(
        client_options={"api_endpoint": f"{GEN_EXTRACTOR_LOCATION}-documentai.googleapis.com"}
    )
    name = f"projects/{PROJECT_ID}/locations/{GEN_EXTRACTOR_LOCATION}/processors/{GEN_EXTRACTOR_ID}"

    raw = documentai_beta.RawDocument(content=data, mime_type="application/pdf")
    req = documentai_beta.ProcessRequest(name=name, raw_document=raw)
    result = client.process_document(request=req)

    # Convert entities to dict
    out: Dict = {}
    for e in (getattr(result.document, "entities", None) or []):
        key = (getattr(e, "type_", "") or "").strip()
        if not key:
            continue

        val = ""
        nv = getattr(e, "normalized_value", None)
        if nv and getattr(nv, "text", ""):
            val = (nv.text or "").strip()
        if not val:
            val = (getattr(e, "mention_text", "") or "").strip()

        if val:
            out[key] = val

    return out



@app.route("/upload", methods=["OPTIONS"])
def upload_options():
    response = app.make_response("")
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

@app.route("/upload", methods=["POST"])
def upload_endpoint() -> tuple:
    """
    Upload 1–3 PDFs (RightEye, CTSIB/BTrackS, Creyos) and generate ONE comprehensive interpretation report.
    Numbers/values are pulled from the documents via generative extraction. Sections are omitted if a test isn't present.
    """
    if "files" not in request.files:
        return jsonify({"error": "No files part in the request"}), 400

    files: List = request.files.getlist("files")
    if not files:
        return jsonify({"error": "No files uploaded"}), 400

    db = get_firestore_client()

    merged_fields: Dict = {}
    file_results = []
    first_blob_uri = ""

    def _norm(k: str) -> str:
        import re
        return re.sub(r"[^a-z0-9]+", "", (k or "").lower())

    def _merge_fields(target: Dict, incoming: Dict) -> None:
        incoming = incoming or {}

        # Keep all original keys (so we can debug easily)
        for k, v in incoming.items():
            if v is None or v == "":
                continue
            target.setdefault(k, v)

        # Map common extractor keys into the variable names your Jinja template expects
        alias_map = {
            # RightEye
            "pursuits": "pursuits score",
            "pursuitsscore": "pursuits score",
            "saccades": "Saccades Score",
            "saccadesscore": "Saccades Score",
            "fixations": "Fixations score",
            "fixationsscore": "Fixations score",
            "eyeq": "Dysfunctional scale",
            "dysfunctionalscale": "Dysfunctional scale",
            "eyeqscore": "Dysfunctional scale",

            # CTSIB / BTrackS - Path Length (cm) values
            "standard": "standard_path_length",
            "standardscore": "standard_path_length",
            "standardpathlength": "standard_path_length",
            "proprioception": "proprioception_path_length",
            "proprioceptionscore": "proprioception_path_length",
            "proprioceptionpathlength": "proprioception_path_length",
            "visual": "visual_path_length",
            "visualscore": "visual_path_length",
            "visualpathlength": "visual_path_length",
            "vestibular": "vestibular_path_length",
            "vestibularscore": "vestibular_path_length",
            "vestibularpathlength": "vestibular_path_length",
            # CTSIB / BTrackS - Percentile values (these are what we want for the report)
            "standardpercentile": "standard_score_percentile",
            "standardscorepercentile": "standard_score_percentile",
            "proprioceptionpercentile": "proprioception_score_percentile",
            "proprioceptionscorepercentile": "proprioception_score_percentile",
            "visualpercentile": "visual_score_percentile",
            "visualscorepercentile": "visual_score_percentile",
            "vestibularpercentile": "vestibular_score_percentile",
            "vestibularscorepercentile": "vestibular_score_percentile",
            # Alternative percentile field names (abbreviated)
            "stdpercentile": "standard_score_percentile",
            "propercentile": "proprioception_score_percentile",
            "vispercentile": "visual_score_percentile",
            "vespercentile": "vestibular_score_percentile",
            # From baseline results table (STD %, PRO %, VIS %, VES %)
            "std": "standard_path_length",
            "pro": "proprioception_path_length",
            "vis": "visual_path_length",
            "ves": "vestibular_path_length",
            # Percentile variations with % column references
            "percentile1": "standard_score_percentile",
            "percentile2": "proprioception_score_percentile",
            "percentile3": "visual_score_percentile",
            "percentile4": "vestibular_score_percentile",
            # Baseline percentile fields
            "baselinestandardpercentile": "standard_score_percentile",
            "baselineproprioceptionpercentile": "proprioception_score_percentile",
            "baselinevisualpercentile": "visual_score_percentile",
            "baselinevestibularpercentile": "vestibular_score_percentile",

            # Creyos screens
            "rpq": "rpq score",
            "rpqscore": "rpq score",
            "pcl5": "pcl-5 score",
            "pcl5score": "pcl-5 score",
            "psqi": "psqi score",
            "psqiscore": "psqi score",
            "phq9": "phq-9 score",
            "phq9score": "phq-9 score",
            "gad7": "gad-7 score",
            "gad7score": "gad-7 score",

            # Patient fields (if your extractor returns them)
            "patientname": "patient_name",
            "dateofbirth": "dob",
            "dateofinjury": "doi",
            "dateoftesting": "dos",
            "assessmentdate": "dos",
        }

        norm_in = {_norm(k): v for k, v in incoming.items() if v not in (None, "")}
        for nk, out_key in alias_map.items():
            if nk in norm_in:
                target.setdefault(out_key, norm_in[nk])

    for file_storage in files:
        filename = file_storage.filename or "document"

        # Upload file to GCS
        file_storage.stream.seek(0)
        blob_uri = upload_to_bucket(file_storage.stream, filename)
        if not first_blob_uri:
            first_blob_uri = blob_uri

        # Extract fields from your generative extractor (this is the source of truth for numbers)
        try:
            gen_fields = extract_fields_generative(blob_uri)
        except Exception as e:
            file_results.append({"filename": filename, "error": f"extract_fields_generative failed: {e}"})
            continue

        _merge_fields(merged_fields, gen_fields)

        file_results.append({"filename": filename, "fields": gen_fields})

    # Prefer extracted patient fields; allow overrides if provided
    patient_name = request.form.get("patient_name") or merged_fields.get("patient_name") or ""
    dob = request.form.get("dob") or merged_fields.get("dob") or ""
    doi = request.form.get("doi") or merged_fields.get("doi") or ""
    dos = request.form.get("dos") or merged_fields.get("dos") or ""

    # Auto-detect which tests are present
    vng = any(k in merged_fields for k in ("pursuits score", "Saccades Score", "Fixations score"))
    ct_sib = any(k in merged_fields for k in ("standard_score_percentile", "proprioception_score_percentile", "visual_score_percentile", "vestibular_score_percentile", "standard_path_length", "proprioception_path_length", "visual_path_length", "vestibular_path_length"))
    creyos = any(k in merged_fields for k in ("rpq score", "pcl-5 score", "psqi score", "phq-9 score", "gad-7 score")) or any(k in merged_fields for k in ("attention_percentile","deductive_reasoning_percentile","episodic_memory_percentile","mental_rotation_percentile","planning_percentile","polygons_percentile","response_inhibition_percentile","spatial_short_term_memory_percentile","verbal_reasoning_percentile","verbal_short_term_memory_percentile","visuospatial_working_memory_percentile","working_memory_percentile"))

    # Render ONE final report
    html_report = render_report(
        fields=merged_fields,
        patient_name=patient_name,
        dob=dob,
        doi=doi,
        dos=dos,
        vng=vng,
        ct_sib=ct_sib,
        creyos=creyos,
    )

    # Convert HTML to PDF and upload
    pdf_gcs_uri = ""
    try:
        pdf_bytes = html_to_pdf(html_report)
        pdf_blob_name = f"interpretation_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
        pdf_gcs_uri = upload_bytes_to_bucket(pdf_bytes, pdf_blob_name, content_type="application/pdf")
    except Exception:
        pdf_gcs_uri = ""

    # Store one combined record
    db.collection("reports").add({
        "source_files": [fr.get("filename") for fr in file_results],
        "first_gcs_uri": first_blob_uri,
        "merged_fields": merged_fields,
        "report_html": html_report,
        "report_pdf_gcs_uri": pdf_gcs_uri,
        "patient_name": patient_name,
        "dob": dob,
        "doi": doi,
        "dos": dos,
        "tests_detected": {"VNG": vng, "CTSIB": ct_sib, "Creyos": creyos},
        "created_utc": datetime.utcnow().isoformat() + "Z",
    })

    return jsonify({
        "source_files": [fr.get("filename") for fr in file_results],
        "file_results": file_results,
        "tests_detected": {"VNG": vng, "CTSIB": ct_sib, "Creyos": creyos},
        "patient": {"patient_name": patient_name, "dob": dob, "doi": doi, "dos": dos},
        "merged_fields": merged_fields,
        "report_html": html_report,
        "report_pdf_gcs_uri": pdf_gcs_uri,
    }), 200


if __name__ == "__main__":
    # For local testing; in Cloud Run Gunicorn will handle serving the app
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)

CREYOS_DOMAIN_RULES = {
    "memory": [
        "visuospatial_working_memory_percentile",
        "working_memory_percentile",
        "spatial_short_term_memory_percentile",
        "verbal_short_term_memory_percentile",
        "episodic_memory_percentile"
    ],
    "visuospatial": ["polygons_percentile", "mental_rotation_percentile"],
    "reasoning": ["deductive_reasoning_percentile", "verbal_reasoning_percentile"],
    "attention": ["attention_percentile"],
    "executive": ["planning_percentile", "response_inhibition_percentile"]
}

def domain_impaired(fields, keys, threshold=20, min_count=2):
    vals = [int(fields.get(k, 100)) for k in keys if fields.get(k) is not None]
    return sum(v < threshold for v in vals) >= min_count

def creyos_abnormal(fields):
    return (
        int(fields.get("rpq_score", 0)) >= 16 or
        int(fields.get("pcl_5_score", 0)) >= 31 or
        int(fields.get("psqi_score", 0)) > 5 or
        int(fields.get("phq_9_score", 0)) >= 5 or
        int(fields.get("gad_7_score", 0)) >= 5
    )
