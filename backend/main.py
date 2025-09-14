from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import json
import os
import logging
from io import BytesIO
from datetime import datetime
import traceback
from dotenv import load_dotenv

load_dotenv()

# Import the comprehensive SDS generator
from sds_generator import (
    SDSGenerator, 
    generate_sds_from_smiles, 
    generate_sds_docx_from_smiles,
    get_sds_section_names
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app, origins=[
    "http://localhost:3000",
    "https://medxai-sds-generator.vercel.app"
]) # Restrict CORS to React frontend

# Initialize SDS Generator
sds_generator = SDSGenerator()


@app.route('/api/health', methods=['GET'])
def health():
    """Enhanced health check endpoint with system information"""
    try:
        # Test RDKit availability
        from rdkit import Chem
        rdkit_version = Chem.rdMolDescriptors.CalcMolFormula(Chem.MolFromSmiles('CCO'))  # Test basic functionality
        rdkit_status = "operational"
    except Exception as e:
        rdkit_status = f"error: {str(e)}"
    
    return jsonify({
        "status": "ok",
        "message": "SDS Generation Backend is running",
        "timestamp": datetime.now().isoformat(),
        "components": {
            "rdkit": rdkit_status,
            "sds_generator": "loaded",
            "endpoints": [
                "/api/sds - Get SDS as JSON",
                "/api/sds/docx - Download SDS as Word document", 
                "/api/sds/json - Download SDS as JSON file",
                "/api/sections - Get section information",
                "/api/validate - Validate SMILES string"
            ]
        }
    }), 200


@app.route('/api/validate', methods=['POST'])
def validate_smiles():
    """Validate SMILES string before processing"""
    try:
        data = request.get_json()
        smiles = data.get('smiles', '').strip() if data else request.args.get('smiles', '').strip()
        
        if not smiles:
            return jsonify({"valid": False, "error": "SMILES string is required"}), 400
        
        # Import and validate with RDKit
        from rdkit import Chem
        mol = Chem.MolFromSmiles(smiles)
        
        if mol is None:
            return jsonify({"valid": False, "error": "Invalid SMILES format"}), 400
        
        # Get basic molecular information
        mol_formula = Chem.rdMolDescriptors.CalcMolFormula(mol)
        mol_weight = Chem.rdMolDescriptors.CalcExactMolWt(mol)
        
        return jsonify({
            "valid": True,
            "smiles": Chem.MolToSmiles(mol),  # Canonicalized SMILES
            "molecular_formula": mol_formula,
            "molecular_weight": round(mol_weight, 2),
            "message": "SMILES is valid and ready for SDS generation"
        })
        
    except Exception as e:
        logger.error(f"SMILES validation error: {str(e)}")
        return jsonify({"valid": False, "error": f"Validation failed: {str(e)}"}), 500


@app.route('/api/sections', methods=['GET'])
def get_sections():
    """Return SDS section information"""
    try:
        sections = get_sds_section_names()
        return jsonify({
            "sections": sections,
            "total_sections": len(sections),
            "description": "Standard SDS 16-section format"
        })
    except Exception as e:
        logger.error(f"Error getting sections: {str(e)}")
        return jsonify({"error": "Failed to retrieve section information"}), 500


@app.route('/api/sds', methods=['GET', 'POST'])
def get_sds():
    """Generate and return comprehensive SDS data as JSON"""
    try:
        # Handle both GET and POST requests
        if request.method == 'POST':
            data = request.get_json()
            smiles = data.get('smiles', '').strip() if data else ''
        else:
            smiles = request.args.get('smiles', '').strip()
        
        if not smiles:
            return jsonify({"error": "SMILES string is required"}), 400

        logger.info(f"Generating SDS for SMILES: {smiles}")

        # Validate SMILES first
        from rdkit import Chem
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return jsonify({"error": "Invalid SMILES format"}), 400

        # Generate comprehensive SDS
        sds = generate_sds_from_smiles(smiles)
        
        if sds is None:
            return jsonify({"error": "Failed to generate SDS - no data returned"}), 500

        # Add metadata
        response_data = {
            "sds": sds,
            "metadata": {
                "smiles": smiles,
                "canonical_smiles": Chem.MolToSmiles(mol),
                "generation_time": datetime.now().isoformat(),
                "generator_version": "3.0",
                "sections_included": list(sds.keys()),
                "data_sources": ["PubChem", "RDKit", "Computational predictions"]
            }
        }

        logger.info(f"SDS generated successfully for: {sds.get('Section1', {}).get('data', {}).get('Product Identifier', 'Unknown')}")
        return jsonify(response_data)

    except ImportError as e:
        logger.error(f"Import error: {str(e)}")
        return jsonify({"error": "Required dependencies not available", "details": str(e)}), 500
    except Exception as e:
        logger.error(f"SDS generation error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({"error": "Failed to generate SDS", "details": str(e)}), 500


@app.route('/api/sds/docx', methods=['GET', 'POST'])
def download_docx():
    """Generate and download SDS as Word document"""
    try:
        # Handle both GET and POST requests
        if request.method == 'POST':
            data = request.get_json()
            smiles = data.get('smiles', '').strip() if data else ''
        else:
            smiles = request.args.get('smiles', '').strip()

        if not smiles:
            return jsonify({"error": "SMILES string is required"}), 400

        logger.info(f"Generating DOCX for SMILES: {smiles}")

        # Validate SMILES
        from rdkit import Chem
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return jsonify({"error": "Invalid SMILES format"}), 400

        # Generate DOCX buffer
        docx_buffer = generate_sds_docx_from_smiles(smiles)
        
        if docx_buffer is None:
            return jsonify({"error": "Failed to generate Word document"}), 500

        # Get compound name for filename
        sds = generate_sds_from_smiles(smiles)
        compound_name = "Unknown_Compound"
        if sds and "Section1" in sds:
            compound_name = sds["Section1"]["data"].get("Product Identifier", "Unknown_Compound")
        
        # Clean filename (remove invalid characters)
        safe_compound_name = "".join(c for c in compound_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        filename = f"SDS_{safe_compound_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"

        logger.info(f"DOCX generated successfully: {filename}")

        return send_file(
            docx_buffer,
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    except ImportError as e:
        logger.error(f"Import error for DOCX: {str(e)}")
        return jsonify({"error": "Required dependencies not available", "details": str(e)}), 500
    except Exception as e:
        logger.error(f"DOCX generation error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({"error": "Failed to generate Word document", "details": str(e)}), 500


@app.route('/api/sds/json', methods=['GET', 'POST'])
def download_json():
    """Generate and download SDS as JSON file"""
    try:
        # Handle both GET and POST requests
        if request.method == 'POST':
            data = request.get_json()
            smiles = data.get('smiles', '').strip() if data else ''
        else:
            smiles = request.args.get('smiles', '').strip()

        if not smiles:
            return jsonify({"error": "SMILES string is required"}), 400

        logger.info(f"Generating JSON export for SMILES: {smiles}")

        # Validate SMILES
        from rdkit import Chem
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return jsonify({"error": "Invalid SMILES format"}), 400

        # Generate SDS
        sds = generate_sds_from_smiles(smiles)
        if sds is None:
            return jsonify({"error": "Failed to generate SDS"}), 500

        # Prepare export data
        export_data = {
            "export_info": {
                "export_date": datetime.now().isoformat(),
                "smiles": smiles,
                "canonical_smiles": Chem.MolToSmiles(mol),
                "generator_version": "3.0",
                "format": "SDS JSON Export"
            },
            "sds": sds
        }

        # Get compound name for filename
        compound_name = sds.get("Section1", {}).get("data", {}).get("Product Identifier", "Unknown_Compound")
        safe_compound_name = "".join(c for c in compound_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        filename = f"SDS_{safe_compound_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        # Create JSON buffer
        json_data = json.dumps(export_data, indent=2, ensure_ascii=False)
        buffer = BytesIO(json_data.encode('utf-8'))
        buffer.seek(0)

        logger.info(f"JSON export generated successfully: {filename}")

        return send_file(
            buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/json'
        )

    except Exception as e:
        logger.error(f"JSON export error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({"error": "Failed to generate JSON export", "details": str(e)}), 500


@app.route('/api/sds/section/<int:section_num>', methods=['GET'])
def get_sds_section(section_num):
    """Get specific SDS section data"""
    try:
        if section_num < 1 or section_num > 16:
            return jsonify({"error": "Section number must be between 1 and 16"}), 400

        smiles = request.args.get('smiles', '').strip()
        if not smiles:
            return jsonify({"error": "SMILES string is required"}), 400

        # Validate SMILES
        from rdkit import Chem
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return jsonify({"error": "Invalid SMILES format"}), 400

        # Generate full SDS (cached approach would be better for production)
        sds = generate_sds_from_smiles(smiles)
        if sds is None:
            return jsonify({"error": "Failed to generate SDS"}), 500

        section_key = f"Section{section_num}"
        section_data = sds.get(section_key)
        
        if not section_data:
            return jsonify({"error": f"Section {section_num} not found"}), 404

        return jsonify({
            "section_number": section_num,
            "section": section_data,
            "smiles": smiles
        })

    except Exception as e:
        logger.error(f"Section retrieval error: {str(e)}")
        return jsonify({"error": "Failed to retrieve section", "details": str(e)}), 500


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        "error": "Endpoint not found",
        "available_endpoints": [
            "GET /api/health",
            "POST /api/validate", 
            "GET|POST /api/sds",
            "GET|POST /api/sds/docx",
            "GET|POST /api/sds/json",
            "GET /api/sections",
            "GET /api/sds/section/<int:section_num>"
        ]
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({
        "error": "Internal server error",
        "message": "An unexpected error occurred. Please check the logs."
    }), 500


if __name__ == '__main__':
    # Ensure temp directory exists (for any temporary file operations)
    os.makedirs('temp', exist_ok=True)
    
    print("=" * 60)
    print("🧪 SDS Generation System Backend")
    print("=" * 60)
    print("✅ Backend running at http://localhost:5000")
    print("🎯 React frontend should connect to http://localhost:5000")
    print("📋 Available endpoints:")
    print("   • GET  /api/health - Health check")
    print("   • POST /api/validate - Validate SMILES")
    print("   • GET  /api/sds - Get SDS as JSON")
    print("   • GET  /api/sds/docx - Download Word document")
    print("   • GET  /api/sds/json - Download JSON file")
    print("   • GET  /api/sections - Get section info")
    print("=" * 60)
    
    # Run Flask app
    app.run(
    host='0.0.0.0', 
    port=int(os.getenv("PORT", 5000)), 
    debug=False,  # Never enable debug in production
    threaded=True
    )
