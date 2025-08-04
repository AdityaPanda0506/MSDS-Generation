# backend/main.py
from flask import Flask, request, jsonify, send_file, make_response
from flask_cors import CORS  # To allow React frontend
import json
import os
import tempfile

# Import your core logic
from sds_generator import generate_sds, generate_pdf

app = Flask(__name__)
CORS(app)  # Allow requests from React (localhost:3000)

@app.route('/api/sds', methods=['GET'])
def get_sds():
    smiles = request.args.get('smiles', '').strip()
    if not smiles:
        return jsonify({"error": "SMILES string is required"}), 400

    mol = None
    try:
        from rdkit import Chem
        mol = Chem.MolFromSmiles(smiles)
    except Exception as e:
        pass

    if mol is None:
        return jsonify({"error": "Invalid SMILES format"}), 400

    sds = generate_sds(smiles)
    if sds is None:
        return jsonify({"error": "Could not generate SDS"}), 500

    return jsonify(sds)

@app.route('/api/sds/pdf', methods=['GET'])
def get_pdf():
    smiles = request.args.get('smiles', '').strip()
    if not smiles:
        return jsonify({"error": "SMILES string is required"}), 400

    from rdkit import Chem
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return jsonify({"error": "Invalid SMILES"}), 400

    sds = generate_sds(smiles)
    compound_name = sds["Section1"]["data"].get("Product Identifier", "Unknown_Compound")

    # Generate PDF
    pdf_path = generate_pdf(sds, compound_name)
    if not pdf_path or not os.path.exists(pdf_path):
        return jsonify({"error": "PDF generation failed"}), 500

    # Serve the PDF
    response = make_response(send_file(pdf_path, as_attachment=True, 
                                       download_name=f"SDS_{compound_name}.pdf", 
                                       mimetype='application/pdf'))
    # Optional: Delete file after sending
    @response.call_on_close
    def cleanup():
        try:
            os.remove(pdf_path)
        except:
            pass

    return response

@app.route('/api/sds/json', methods=['GET'])
def get_json():
    smiles = request.args.get('smiles', '').strip()
    if not smiles:
        return jsonify({"error": "SMILES string is required"}), 400

    from rdkit import Chem
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return jsonify({"error": "Invalid SMILES"}), 400

    sds = generate_sds(smiles)
    if sds is None:
        return jsonify({"error": "Failed to generate SDS"}), 500

    # Return JSON directly
    response = app.response_class(
        response=json.dumps(sds, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename=sds_{compound_name}.json'}
    )
    return response

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "message": "Backend is running"}), 200

if __name__ == '__main__':
    # Create temp dir if not exists
    os.makedirs('temp', exist_ok=True)
    print("✅ Backend running at http://localhost:5000")
    print("🎯 Connect React to http://localhost:5000")
    app.run(host='127.0.0.1', port=5000, debug=True)