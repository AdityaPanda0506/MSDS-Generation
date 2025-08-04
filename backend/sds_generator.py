# sds_generator.py

import pubchempy as pcp
from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors
import pandas as pd
import json
import os
import pdfkit

# -----------------------------
# Utility Functions
# -----------------------------

def smiles_to_mol(smiles):
    """Convert SMILES to RDKit mol object"""
    mol = Chem.MolFromSmiles(smiles)
    return mol

def get_pubchem_data(smiles):
    """Fetch data from PubChem with safe type handling"""
    try:
        compounds = pcp.get_compounds(smiles, 'smiles')
        if compounds:
            c = compounds[0]
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                print("Warning: Could not generate RDKit molecule from SMILES.")
                return {}
            # Safely extract and convert properties with defaults
            mw = c.molecular_weight
            logp = c.xlogp
            try:
                mw_val = float(mw) if mw is not None else 300.0
            except (TypeError, ValueError):
                mw_val = 300.0
            try:
                logp_val = float(logp) if logp not in [None, "--"] else 2.0
            except (TypeError, ValueError):
                logp_val = 2.0
            solubility = "Highly soluble" if mw_val < 500 and logp_val < 3 else "Low solubility"
            return {
                "name": c.iupac_name or (c.synonyms[0] if c.synonyms else "Unknown"),
                "formula": c.molecular_formula or "Not available",
                "mw": mw_val,
                "cas": getattr(c, 'cas', "Not available"),
                "logp": round(logp_val, 2),
                "solubility": solubility,
                "h_bond_donor": rdMolDescriptors.CalcNumHBD(mol),
                "h_bond_acceptor": rdMolDescriptors.CalcNumHBA(mol),
            }
    except Exception as e:
        print(f"PubChem lookup failed: {e}")
    return {}

def predict_toxicity_protx(smiles):
    """Simulate ProTox-II prediction"""
    mol = Chem.MolFromSmiles(smiles)
    if not mol:
        return {}
    has_nitro = any(atom.GetAtomicNum() == 7 and atom.GetFormalCharge() == 1 for atom in mol.GetAtoms())
    return {
        "toxicity_class": "Class IV (Low)" if not has_nitro else "Class II (High)",
        "hazard_endpoints": ["Hepatotoxicity"] if has_nitro else ["None predicted"],
        "ld50": "5000 mg/kg" if not has_nitro else "50 mg/kg"
    }

def get_physical_properties(mol):
    """Compute properties using RDKit"""
    mw = Descriptors.MolWt(mol)
    logp = Descriptors.MolLogP(mol)
    tpsa = Descriptors.TPSA(mol)
    return {
        "_MolecularWeight_numeric": mw,
        "_LogP_numeric": logp,
        "Molecular Weight": f"{mw:.2f} g/mol",
        "LogP": f"{logp:.2f}",
        "Topological Polar Surface Area (TPSA)": f"{tpsa:.2f} Å²",
        "Hydrogen Bond Donors": Descriptors.NumHDonors(mol),
        "Hydrogen Bond Acceptors": Descriptors.NumHAcceptors(mol),
        "Rotatable Bonds": Descriptors.NumRotatableBonds(mol),
        "Heavy Atom Count": rdMolDescriptors.CalcNumHeavyAtoms(mol),
    }

def section_name(i):
    names = {
        1: "Chemical Product and Company Identification",
        2: "Composition and Information on Ingredients",
        3: "Hazards Identification",
        4: "First Aid Measures",
        5: "Fire and Explosion Data",
        6: "Accidental Release Measures",
        7: "Handling and Storage",
        8: "Exposure Controls/Personal Protection",
        9: "Physical and Chemical Properties",
        10: "Stability and Reactivity",
        11: "Toxicological Information",
        12: "Ecological Information",
        13: "Disposal Considerations",
        14: "Transport Information",
        15: "Other Regulatory Information",
        16: "Other Information"
    }
    return names.get(i, f"Section {i}")

def generate_sds(smiles):
    mol = smiles_to_mol(smiles)
    if not mol:
        return None
    pubchem = get_pubchem_data(smiles)
    protx = predict_toxicity_protx(smiles)
    sds = {
        f"Section{i}": {
            "title": section_name(i),
            "data": {},
            "notes": []
        } for i in range(1, 17)
    }
    sds["Section1"]["data"] = {
        "Product Identifier": pubchem.get("name", "Unknown Compound"),
        "Company": "Automated SDS Generator",
        "Address": "N/A",
        "Emergency Phone": "N/A",
        "Recommended Use": "Research Use Only"
    }
    sds["Section2"]["data"] = {
        "Name": pubchem.get("name", "Unknown"),
        "CAS Number": pubchem.get("cas", "Not available"),
        "Molecular Formula": pubchem.get("formula", "Not available"),
        "Purity/Concentration": "100% (pure compound)"
    }
    # Section 3: Hazards Identification (Enhanced)
    is_flammable = pubchem.get("logp", 0) > 1.5
    is_toxic = protx.get("toxicity_class", "Class V") in ["Class I", "II", "III", "IV"]
    has_health_hazard = is_toxic
    pictograms = []
    hazard_statements = []
    if is_flammable:
        pictograms.append("🔥 Flammable")
        hazard_statements.append("H225: Highly flammable liquid and vapor")
    if is_toxic:
        pictograms.append("💀 Acute Toxicity")
        hazard_statements.append("H301: Toxic if swallowed")
        hazard_statements.append("H331: Toxic if inhaled")
    signal_word = "Danger" if (is_flammable or is_toxic) else "Warning"
    health_effects = "This substance is harmful if inhaled, swallowed, or absorbed through the skin. "
    if is_toxic:
        health_effects += "It may cause central nervous system depression, organ damage, or acute toxicity. "
    if is_flammable:
        health_effects += "Vapors may cause dizziness or asphyxiation in high concentrations. "
    health_effects += "Chronic exposure may lead to liver, kidney, or respiratory damage."
    precautionary = [
        "P210: Keep away from heat, hot surfaces, sparks, open flames.",
        "P241: Use explosion-proof electrical/ventilation equipment.",
        "P261: Avoid breathing dust/fume/gas/mist/vapors/spray.",
        "P280: Wear protective gloves/protective clothing/eye protection/face protection.",
        "P305+P351+P338: IF IN EYES: Rinse cautiously with water for several minutes."
    ]
    sds["Section3"]["data"] = {
        "Signal Word": signal_word,
        "GHS Pictograms": ", ".join(pictograms) if pictograms else "Not classified",
        "Hazard Statements": hazard_statements if hazard_statements else ["No significant hazards identified"],
        "Precautionary Statements": precautionary,
        "Physical Hazards": "Flammable liquid and vapor" if is_flammable else "Not flammable",
        "Health Hazards": ", ".join([p.replace("💀 ", "") for p in pictograms if "💀" in p]) or "None identified",
        "Environmental Hazards": "Toxic to aquatic life" if protx.get("toxicity_class") in ["Class I", "Class II"] else "Low concern",
        "Routes of Exposure": "Inhalation, Skin Contact, Ingestion, Eye Contact",
        "Acute and Chronic Effects": health_effects,
        "Immediate Medical Attention": "Seek medical attention immediately in case of exposure. Show SDS to physician."
    }
    sds["Section4"]["data"] = {
        "Inhalation": "Move to fresh air. If breathing is difficult, give oxygen.",
        "Skin Contact": "Flush with plenty of water. Remove contaminated clothing.",
        "Eye Contact": "Flush with water for at least 15 minutes.",
        "Ingestion": "Do NOT induce vomiting. Rinse mouth and consult a physician."
    }
    flash_point = "13°C" if pubchem.get("logp", 0) > 1 else "Not flammable"
    sds["Section5"]["data"] = {
        "Flash Point": flash_point,
        "Flammable Limits": "3.3% - 19% in air",
        "Extinguishing Media": "Dry chemical, CO2, alcohol-resistant foam",
        "Special Hazards": "Vapors may form explosive mixtures with air."
    }
    sds["Section6"]["data"] = {
        "Personal Precautions": "Wear PPE, ensure ventilation",
        "Environmental Precautions": "Prevent entry into drains or waterways",
        "Methods of Containment": "Absorb with inert material (sand, vermiculite)"
    }
    sds["Section7"]["data"] = {
        "Handling": "Ground containers, use explosion-proof equipment",
        "Storage": "Store in a cool, well-ventilated place away from ignition sources"
    }
    sds["Section8"]["data"] = {
        "TLV-TWA": "100 ppm (300 mg/m³) for ethanol-like compounds",
        "Engineering Controls": "Local exhaust ventilation",
        "Personal Protection": "Safety goggles, gloves, lab coat"
    }
    props = get_physical_properties(mol)
    mw_numeric = props["_MolecularWeight_numeric"]
    sds["Section9"]["data"] = {
        "Physical State": "Liquid" if mw_numeric < 300 else "Solid",
        "Color": "Colorless",
        "Odor": "Characteristic",
        "Melting Point": "Not available",
        "Boiling Point": "Not available",
        "Solubility in Water": pubchem.get("solubility", "Data not available"),
        "Density": "Approx. 0.79 g/cm³ (for alcohols)",
        "Vapor Pressure": "< 1 mmHg at 25°C",
        **{k: v for k, v in props.items() if not k.startswith("_")}
    }
    sds["Section10"]["data"] = {
        "Stability": "Stable under normal conditions",
        "Conditions to Avoid": "Heat, flames, sparks",
        "Incompatible Materials": "Strong oxidizing agents",
        "Hazardous Decomposition": "Carbon monoxide, carbon dioxide"
    }
    sds["Section11"]["data"] = {
        "LD50 Oral Rat": protx.get("ld50"),
        "LC50 Inhalation Rat": "Not available",
        "Carcinogenicity": "Suspected" if "Hepatotoxicity" in protx.get("hazard_endpoints", []) else "Not suspected",
        "Mutagenicity": "Positive" if "Hepatotoxicity" in protx.get("hazard_endpoints", []) else "Negative",
        "Toxicity Class": protx.get("toxicity_class", "Class IV")
    }
    sds["Section12"]["data"] = {
        "Ecotoxicity": "Toxic to aquatic life" if protx.get("toxicity_class") in ["Class I", "Class II"] else "Low concern",
        "Biodegradability": "Yes",
        "Persistence": "Low",
        "Bioaccumulation": "Low potential"
    }
    sds["Section13"]["data"] = {
        "Disposal Method": "Dispose in accordance with local regulations",
        "Contaminated Packaging": "Rinse and recycle or dispose properly"
    }
    sds["Section14"]["data"] = {
        "UN Number": "UN1170",
        "Proper Shipping Name": "Ethanol or Ethyl Alcohol",
        "Transport Hazard Class": "3 (Flammable Liquid)",
        "Packing Group": "II"
    }
    sds["Section15"]["data"] = {
        "TSCA": "Listed",
        "DSL": "Listed",
        "WHMIS": "Classified",
        "GHS Regulation": "GHS Rev 9 compliant"
    }
    sds["Section16"]["data"] = {
        "Date Prepared": pd.Timestamp.now().strftime("%Y-%m-%d"),
        "Revision Number": "1.0",
        "Prepared By": "Automated ADMET-SDS System",
        "Disclaimer": "Generated for research use only. Verify with lab testing."
    }
    return sds

def generate_pdf(sds, compound_name="Unknown Compound"):
    """Generate a professional, styled PDF using pdfkit and return file path"""
    # Get current timestamp
    generated_on = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")

    # Build HTML with all 16 sections
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Safety Data Sheet - {compound_name}</title>
        <style>
            body {{
                font-family: 'Segoe UI', Arial, sans-serif;
                margin: 0;
                padding: 0;
                background: #f4f6f9;
                color: #333;
            }}
            .container {{
                max-width: 900px;
                margin: 20px auto;
                padding: 30px;
                background: white;
                border: 1px solid #ddd;
                border-radius: 12px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            }}
            .header {{
                text-align: center;
                margin-bottom: 20px;
                padding-bottom: 15px;
                border-bottom: 3px solid #1f77b4;
            }}
            .header h1 {{
                color: #1f77b4;
                margin: 0;
                font-size: 28px;
            }}
            .header p {{
                color: #555;
                font-style: italic;
                margin: 5px 0 0;
            }}
            .generated-on {{
                text-align: right;
                font-size: 14px;
                color: #666;
                margin-bottom: 20px;
            }}
            .section {{
                margin: 25px 0;
            }}
            .section-header {{
                background: #1f77b4;
                color: white;
                padding: 12px 16px;
                border-radius: 8px;
                font-size: 18px;
                font-weight: bold;
                display: flex;
                align-items: center;
                gap: 10px;
            }}
            .section-header .icon {{
                font-size: 20px;
            }}
            .section table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 10px;
                font-size: 14px;
            }}
            .section th {{
                background-color: #f0f4f8;
                color: #1f77b4;
                text-align: left;
                padding: 10px;
                border: 1px solid #ccc;
                font-weight: 600;
            }}
            .section td {{
                padding: 10px;
                border: 1px solid #ddd;
                background-color: #fcfcfc;
            }}
            .section tr:nth-child(even) td {{
                background-color: #f9f9f9;
            }}
            .section ul {{
                margin: 5px 0;
                padding-left: 20px;
            }}
            .section ul li {{
                margin: 5px 0;
            }}
            .hazard-warning {{
                background-color: #ffe6e6;
                border-left: 5px solid #ff4d4d;
                padding: 12px;
                margin: 10px 0;
                border-radius: 4px;
                font-weight: 500;
            }}
            .footer {{
                text-align: center;
                margin-top: 40px;
                padding-top: 15px;
                border-top: 1px solid #eee;
                color: #777;
                font-size: 13px;
            }}
            .disclaimer {{
                font-size: 12px;
                color: #999;
                font-style: italic;
                margin-top: 8px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Safety Data Sheet (SDS)</h1>
                <p>Generated from SMILES using AI & Cheminformatics</p>
            </div>
            <p class="generated-on"><strong>Compound:</strong> {compound_name} | <strong>Generated on:</strong> {generated_on}</p>
    """

    # Loop through all 16 sections
    for i in range(1, 17):
        section_key = f"Section{i}"
        section = sds.get(section_key, {})
        title = section.get("title", f"Section {i}")
        
        
        html_content += f"""
            <div class="section">
                <div class="section-header">
                    <span>{i}. {title}</span>
                </div>
                <table>
        """
        
        data = section.get("data", {})
        for key, value in data.items():
            if isinstance(value, list):
                value = "<br>".join([f"• {v}" for v in value if v]) or "Not available"
            elif not value or value == "Not available":
                value = "<em>Not available</em>"
            else:
                value = str(value)
            
            # Special styling for hazard section
            if i == 3 and "Hazard" in key:
                html_content += f"""
                    <tr>
                        <th>{key}</th>
                        <td class="hazard-warning">{value}</td>
                    </tr>
                """
            else:
                html_content += f"""
                    <tr>
                        <th>{key}</th>
                        <td>{value}</td>
                    </tr>
                """
        
        html_content += """
                </table>
            </div>
        """

    # Footer
    html_content += f"""
            <div class="footer">
                <p>Generated with ❤ for chemical safety</p>
                <div class="disclaimer">
                    Disclaimer: This report is generated for research use only. Verify with lab testing and official sources before use.
                </div>
            </div>
        </div>
    </body>
    </html>
    """

    # Save temporary HTML
    temp_html = "temp_sds.html"
    with open(temp_html, "w", encoding="utf-8") as f:
        f.write(html_content)

    # PDF filename
    pdf_path = f"sds_{compound_name.replace(' ', '_').replace('/', '_')}.pdf"

    try:
        # Configure pdfkit with wkhtmltopdf path
        config = pdfkit.configuration(wkhtmltopdf=r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe')
        pdfkit.from_file(temp_html, pdf_path, configuration=config)
        return pdf_path
    except Exception as e:
        st.error(f"PDF generation failed: {e}")
        return None
    finally:
        # Clean up temporary HTML
        if os.path.exists(temp_html):
            os.remove(temp_html)