from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import json
import os
import logging
from io import BytesIO
from datetime import datetime
import traceback
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import the comprehensive SDS generator
try:
    from sds_generator import (
        SDSGenerator, 
        generate_sds_from_smiles, 
        generate_sds_docx_from_smiles,
        get_sds_section_names
    )
except ImportError as e:
    logging.error(f"Failed to import SDS generator: {e}")
    raise

# Configure logging
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/app.log') if os.path.exists('logs') else logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Configure CORS
cors_origins = os.getenv('CORS_ORIGINS', 'http://localhost:3000').split(',')
CORS(app, origins=cors_origins, methods=['GET', 'POST'], allow_headers=['Content-Type'])

# Initialize SDS Generator with error handling
try:
    sds_generator = SDSGenerator()
    logger.info("SDS Generator initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize SDS Generator: {e}")
    sds_generator = None


@app.before_request
def log_request_info():
    """Log incoming requests for debugging"""
    if not request.path.startswith('/api/health'):  # Don't log health checks
        logger.info(f"Request: {request.method} {request.path} from {request.remote_addr}")


@app.after_request
def after_request(response):
    """Add security headers and log responses"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response


@app.route('/', methods=['GET'])
def root():
    """Root endpoint with API information"""
    return jsonify({
        "service": "SDS Generation System",
        "version": "3.0",
        "status": "operational",
        "endpoints": {
            "health": "/api/health",
            "validate": "/api/validate",
            "generate_sds": "/api/sds",
            "download_docx": "/api/sds/docx",
            "download_json": "/api/sds/json",
            "sections": "/api/sections"
        },
        "documentation": "POST SMILES string to generate comprehensive Safety Data Sheets"
    })


@app.route('/api/health', methods=['GET'])
def health():
    """Enhanced health check endpoint with system information"""
    try:
        # Test RDKit availability
        from rdkit import Chem
        rdkit_version = Chem.rdMolDescriptors.CalcMolFormula(Chem.MolFromSmiles('CCO'))
        rdkit_status = "operational"
        
        # Test SDS generator
        sds_status = "operational" if sds_generator is not None else "failed"
        
        # Check environment variables
        env_status = {
            "mistral_api_key": "configured" if os.getenv('MISTRAL_API_KEY') else "missing",
            "port": os.getenv('PORT', '5000'),
            "flask_env": os.getenv('FLASK_ENV', 'development')
        }
        
        return jsonify({
            "status": "healthy",
            "service": "SDS Generation System",
            "timestamp": datetime.now().isoformat(),
            "components": {
                "rdkit": rdkit_status,
                "sds_generator": sds_status,
                "environment": env_status
            },
            "endpoints": [
                "/api/sds - Get SDS as JSON",
                "/api/sds/docx - Download SDS as Word document", 
                "/api/sds/json - Download SDS as JSON file",
                "/api/sections - Get section information",
                "/api/validate - Validate SMILES string"
            ]
        }), 200
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500


@app.route('/api/validate', methods=['POST'])
def validate_smiles():
    """Validate SMILES string before processing"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"valid": False, "error": "JSON body required"}), 400
            
        smiles = data.get('smiles', '').strip()
        
        if not smiles:
            return jsonify({"valid": False, "error": "SMILES string is required"}), 400
        
        # Validate with RDKit
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


@app.route('/api/sds', methods=['POST'])
def get_sds():
    """Generate and return comprehensive SDS data as JSON"""
    if sds_generator is None:
        return jsonify({"error": "SDS Generator not available"}), 503
        
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body with SMILES required"}), 400
            
        smiles = data.get('smiles', '').strip()
        
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

        compound_name = sds.get('Section1', {}).get('data', {}).get('Product Identifier', 'Unknown')
        logger.info(f"SDS generated successfully for: {compound_name}")
        return jsonify(response_data)

    except ImportError as e:
        logger.error(f"Import error: {str(e)}")
        return jsonify({"error": "Required dependencies not available", "details": str(e)}), 500
    except Exception as e:
        logger.error(f"SDS generation error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({"error": "Failed to generate SDS", "details": str(e)}), 500


@app.route('/api/sds/docx', methods=['POST'])
def download_docx():
    """Generate and download SDS as Word document"""
    if sds_generator is None:
        return jsonify({"error": "SDS Generator not available"}), 503
        
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body with SMILES required"}), 400
            
        smiles = data.get('smiles', '').strip()

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
        
        # Clean filename
        safe_compound_name = "".join(c for c in compound_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        filename = f"SDS_{safe_compound_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"

        logger.info(f"DOCX generated successfully: {filename}")

        return send_file(
            docx_buffer,
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    except Exception as e:
        logger.error(f"DOCX generation error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({"error": "Failed to generate Word document", "details": str(e)}), 500


@app.route('/api/sds/json', methods=['POST'])
def download_json():
    """Generate and download SDS as JSON file"""
    if sds_generator is None:
        return jsonify({"error": "SDS Generator not available"}), 503
        
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body with SMILES required"}), 400
            
        smiles = data.get('smiles', '').strip()

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


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        "error": "Endpoint not found",
        "available_endpoints": [
            "GET /api/health",
            "POST /api/validate", 
            "POST /api/sds",
            "POST /api/sds/docx",
            "POST /api/sds/json",
            "GET /api/sections"
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
    # Ensure necessary directories exist
    os.makedirs('temp', exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    
    port = int(os.getenv("PORT", 5000))
    
    print("=" * 60)
    print("🧪 SDS Generation System Backend")
    print("=" * 60)
    print(f"✅ Backend running at http://0.0.0.0:{port}")
    print(f"🎯 Environment: {os.getenv('FLASK_ENV', 'development')}")
    print("📋 Available endpoints:")
    print("   • GET  / - Service information")
    print("   • GET  /api/health - Health check")
    print("   • POST /api/validate - Validate SMILES")
    print("   • POST /api/sds - Get SDS as JSON")
    print("   • POST /api/sds/docx - Download Word document")
    print("   • POST /api/sds/json - Download JSON file")
    print("   • GET  /api/sections - Get section info")
    print("=" * 60)
    
    # Run Flask app
    app.run(
        host='0.0.0.0', 
        port=port,
        debug=False,
        threaded=True
    )
