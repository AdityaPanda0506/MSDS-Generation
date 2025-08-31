# backend/main.py
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import json
import os
from io import BytesIO

# Import your core logic
from sds_generator import generate_sds, generate_docx  # Updated: generate_docx returns BytesIO

app = Flask(__name__)
CORS(app)  # Allow React frontend (localhost:3000)

@app.route('/api/sds', methods=['GET'])
def get_sds():
    """Return SDS data as JSON (for preview or processing)"""
    smiles = request.args.get('smiles', '').strip()
    if not smiles:
        return jsonify({"error": "SMILES string is required"}), 400

    try:
        from rdkit import Chem
        mol = Chem.MolFromSmiles(smiles)
    except Exception as e:
        return jsonify({"error": "RDKit initialization failed", "details": str(e)}), 500

    if mol is None:
        return jsonify({"error": "Invalid SMILES format"}), 400

    sds = generate_sds(smiles)
    if sds is None:
        return jsonify({"error": "Could not generate SDS"}), 500

    return jsonify(sds)


@app.route('/api/sds/docx', methods=['GET'])
def get_docx():
    """Generate and return SDS as a downloadable Word (.docx) document"""
    smiles = request.args.get('smiles', '').strip()
    if not smiles:
        return jsonify({"error": "SMILES string is required"}), 400

    try:
        from rdkit import Chem
        mol = Chem.MolFromSmiles(smiles)
    except Exception as e:
        return jsonify({"error": "RDKit error", "details": str(e)}), 500

    if mol is None:
        return jsonify({"error": "Invalid SMILES"}), 400

    sds = generate_sds(smiles)
    if sds is None:
        return jsonify({"error": "Failed to generate SDS"}), 500

    compound_name = sds["Section1"]["data"].get("Product Identifier", "Unknown_Compound")

    # Generate DOCX in memory
    try:
        docx_buffer = generate_docx(sds, compound_name)
    except Exception as e:
        return jsonify({"error": "DOCX generation failed", "details": str(e)}), 500

    # Send file directly from memory
    return send_file(
        docx_buffer,
        as_attachment=True,
        download_name=f"SDS_{compound_name}.docx",
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


@app.route('/api/sds/json', methods=['GET'])
def get_json():
    """Return SDS as downloadable JSON file"""
    smiles = request.args.get('smiles', '').strip()
    if not smiles:
        return jsonify({"error": "SMILES string is required"}), 400

    try:
        from rdkit import Chem
        mol = Chem.MolFromSmiles(smiles)
    except Exception as e:
        return jsonify({"error": "RDKit error", "details": str(e)}), 500

    if mol is None:
        return jsonify({"error": "Invalid SMILES"}), 400

    sds = generate_sds(smiles)
    if sds is None:
        return jsonify({"error": "Failed to generate SDS"}), 500

    compound_name = sds["Section1"]["data"].get("Product Identifier", "Unknown_Compound")

    # Serialize to JSON and serve as file
    json_data = json.dumps(sds, indent=2)
    buffer = BytesIO(json_data.encode('utf-8'))
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"sds_{compound_name}.json",
        mimetype='application/json'
    )


@app.route('/api/sds/pdf', methods=['GET'])
def get_pdf():
    """Generate and return SDS as a very simple PDF (placeholder implementation)."""
    smiles = request.args.get('smiles', '').strip()
    if not smiles:
        return jsonify({"error": "SMILES string is required"}), 400

    try:
        from rdkit import Chem
        mol = Chem.MolFromSmiles(smiles)
    except Exception as e:
        return jsonify({"error": "RDKit error", "details": str(e)}), 500

    if mol is None:
        return jsonify({"error": "Invalid SMILES"}), 400

    sds = generate_sds(smiles)
    if sds is None:
        return jsonify({"error": "Failed to generate SDS"}), 500

    compound_name = sds["Section1"]["data"].get("Product Identifier", "Unknown_Compound")

    # Simple PDF generation using reportlab (fallback text-only)
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        pdf_buffer = BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=letter)
        width, height = letter
        y = height - 50
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, y, f"Safety Data Sheet: {compound_name}")
        y -= 30
        c.setFont("Helvetica", 9)
        for section_key, section in sds.items():
            title = section.get('title', section_key)
            c.setFont("Helvetica-Bold", 11)
            if y < 80:
                c.showPage(); y = height - 50
            c.drawString(50, y, title)
            y -= 16
            c.setFont("Helvetica", 8)
            for k, v in section.get('data', {}).items():
                line = f"{k}: {v if not isinstance(v, list) else ', '.join(map(str, v))}"[:180]
                if y < 60:
                    c.showPage(); y = height - 50; c.setFont("Helvetica", 8)
                c.drawString(60, y, line)
                y -= 12
        c.save()
        pdf_buffer.seek(0)
    except Exception as e:
        return jsonify({"error": "PDF generation failed", "details": str(e)}), 500

    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"SDS_{compound_name}.pdf",
        mimetype='application/pdf'
    )


@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "ok", "message": "Backend is running"}), 200


if __name__ == '__main__':
    # Ensure temp directory exists (optional, if you ever use it)
    os.makedirs('temp', exist_ok=True)
    print("✅ Backend running at http://localhost:5000")
    print("🎯 Connect React frontend to http://localhost:5000")
    app.run(host='127.0.0.1', port=5000, debug=True)
