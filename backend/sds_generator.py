# sds_generator.py
# Pure Flask/Python backend module — no Streamlit, no frontend deps

from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors
import pubchempy as pcp
import pandas as pd
from datetime import datetime
from io import BytesIO
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import RGBColor
from docx.oxml import OxmlElement


# -----------------------------
# Utility Functions
# -----------------------------

def smiles_to_mol(smiles):
    """Convert SMILES to RDKit mol object"""
    return Chem.MolFromSmiles(smiles)


def get_pubchem_data(smiles):
    """Fetch data from PubChem with safe type handling"""
    try:
        compounds = pcp.get_compounds(smiles, 'smiles')
        if compounds:
            c = compounds[0]
            mol = smiles_to_mol(smiles)
            if mol is None:
                print("Warning: Could not generate RDKit molecule from SMILES.")
                return {}

            # Handle molecular weight
            try:
                mw_val = float(c.molecular_weight) if c.molecular_weight else 300.0
            except (TypeError, ValueError):
                mw_val = 300.0

            # Handle LogP
            try:
                logp_val = float(c.xlogp) if c.xlogp not in [None, "--"] else 2.0
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
    mol = smiles_to_mol(smiles)
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
    """Map section number to title"""
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
    """Generate full SDS dictionary from SMILES"""
    mol = smiles_to_mol(smiles)
    if not mol:
        return None

    pubchem = get_pubchem_data(smiles)
    protx = predict_toxicity_protx(smiles)
    props = get_physical_properties(mol)

    sds = {
        f"Section{i}": {
            "title": section_name(i),
            "data": {},
            "notes": []
        } for i in range(1, 17)
    }

    # Section 1
    sds["Section1"]["data"] = {
        "Product Identifier": pubchem.get("name", "Unknown Compound"),
        "Company": "Automated SDS Generator",
        "Address": "N/A",
        "Emergency Phone": "N/A",
        "Recommended Use": "Research Use Only"
    }

    # Section 2
    sds["Section2"]["data"] = {
        "Name": pubchem.get("name", "Unknown"),
        "CAS Number": pubchem.get("cas", "Not available"),
        "Molecular Formula": pubchem.get("formula", "Not available"),
        "Purity/Concentration": "100% (pure compound)"
    }

    # Section 3: Hazards Identification
    is_flammable = pubchem.get("logp", 0) > 1.5
    is_toxic = protx.get("toxicity_class") in ["Class I", "II", "III", "IV"]

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

    health_effects = (
        "This substance is harmful if inhaled, swallowed, or absorbed through the skin. "
        + ("It may cause central nervous system depression, organ damage, or acute toxicity. " if is_toxic else "")
        + ("Vapors may cause dizziness or asphyxiation in high concentrations. " if is_flammable else "")
        + "Chronic exposure may lead to liver, kidney, or respiratory damage."
    )

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

    # Section 4
    sds["Section4"]["data"] = {
        "Inhalation": "Move to fresh air. If breathing is difficult, give oxygen.",
        "Skin Contact": "Flush with plenty of water. Remove contaminated clothing.",
        "Eye Contact": "Flush with water for at least 15 minutes.",
        "Ingestion": "Do NOT induce vomiting. Rinse mouth and consult a physician."
    }

    # Section 5
    flash_point = "13°C" if pubchem.get("logp", 0) > 1 else "Not flammable"
    sds["Section5"]["data"] = {
        "Flash Point": flash_point,
        "Flammable Limits": "3.3% - 19% in air",
        "Extinguishing Media": "Dry chemical, CO2, alcohol-resistant foam",
        "Special Hazards": "Vapors may form explosive mixtures with air."
    }

    # Section 6
    sds["Section6"]["data"] = {
        "Personal Precautions": "Wear PPE, ensure ventilation",
        "Environmental Precautions": "Prevent entry into drains or waterways",
        "Methods of Containment": "Absorb with inert material (sand, vermiculite)"
    }

    # Section 7
    sds["Section7"]["data"] = {
        "Handling": "Ground containers, use explosion-proof equipment",
        "Storage": "Store in a cool, well-ventilated place away from ignition sources"
    }

    # Section 8
    sds["Section8"]["data"] = {
        "TLV-TWA": "100 ppm (300 mg/m³) for ethanol-like compounds",
        "Engineering Controls": "Local exhaust ventilation",
        "Personal Protection": "Safety goggles, gloves, lab coat"
    }

    # Section 9
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

    # Section 10
    sds["Section10"]["data"] = {
        "Stability": "Stable under normal conditions",
        "Conditions to Avoid": "Heat, flames, sparks",
        "Incompatible Materials": "Strong oxidizing agents",
        "Hazardous Decomposition": "Carbon monoxide, carbon dioxide"
    }

    # Section 11
    sds["Section11"]["data"] = {
        "LD50 Oral Rat": protx.get("ld50"),
        "LC50 Inhalation Rat": "Not available",
        "Carcinogenicity": "Suspected" if "Hepatotoxicity" in protx.get("hazard_endpoints", []) else "Not suspected",
        "Mutagenicity": "Positive" if "Hepatotoxicity" in protx.get("hazard_endpoints", []) else "Negative",
        "Toxicity Class": protx.get("toxicity_class", "Class IV")
    }

    # Section 12
    sds["Section12"]["data"] = {
        "Ecotoxicity": "Toxic to aquatic life" if protx.get("toxicity_class") in ["Class I", "Class II"] else "Low concern",
        "Biodegradability": "Yes",
        "Persistence": "Low",
        "Bioaccumulation": "Low potential"
    }

    # Section 13
    sds["Section13"]["data"] = {
        "Disposal Method": "Dispose in accordance with local regulations",
        "Contaminated Packaging": "Rinse and recycle or dispose properly"
    }

    # Section 14
    sds["Section14"]["data"] = {
        "UN Number": "UN1170",
        "Proper Shipping Name": "Ethanol or Ethyl Alcohol",
        "Transport Hazard Class": "3 (Flammable Liquid)",
        "Packing Group": "II"
    }

    # Section 15
    sds["Section15"]["data"] = {
        "TSCA": "Listed",
        "DSL": "Listed",
        "WHMIS": "Classified",
        "GHS Regulation": "GHS Rev 9 compliant"
    }

    # Section 16
    sds["Section16"]["data"] = {
        "Date Prepared": pd.Timestamp.now().strftime("%Y-%m-%d"),
        "Revision Number": "1.0",
        "Prepared By": "Automated ADMET-SDS System",
        "Disclaimer": "Generated for research use only. Verify with lab testing."
    }

    return sds


def generate_docx(sds, compound_name="Unknown Compound"):
    """
    Generate a Word document (.docx) in memory and return BytesIO buffer.
    Compatible with Flask send_file().
    """
    doc = Document()

    # Set margins
    for section in doc.sections:
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)

    # Title
    title = doc.add_heading('Safety Data Sheet (SDS)', 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    subtitle = doc.add_paragraph(f"Compound: {compound_name}")
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER

    generated_on = datetime.now().strftime("%Y-%m-%d %H:%M")
    p = doc.add_paragraph(f"Generated on: {generated_on}", style='Caption')
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph()

    # Add all 16 sections
    for i in range(1, 17):
        section_key = f"Section{i}"
        section = sds.get(section_key, {})
        title = section.get("title", f"Section {i}")

        doc.add_heading(f"{i}. {title}", level=1)

        data = section.get("data", {})
        if not data:
            doc.add_paragraph("No data available.")
        else:
            table = doc.add_table(rows=0, cols=2)
            table.style = 'Table Grid'
            for key, value in data.items():
                row = table.add_row()
                cell_key = row.cells[0]
                cell_val = row.cells[1]

                # Bold key
                run_key = cell_key.paragraphs[0].add_run(str(key))
                run_key.bold = True

                # Format value
                if isinstance(value, list):
                    val_text = ", ".join(str(v) for v in value if v) or "Not available"
                elif not value or value == "Not available":
                    val_text = "Not available"
                else:
                    val_text = str(value)

                cell_val.text = val_text

        doc.add_paragraph()  # Space between sections

    # Footer / Disclaimer
    disclaimer = doc.add_paragraph()
    run = disclaimer.add_run(
        "Disclaimer: This report is generated for research use only. "
        "Verify with lab testing and official sources before handling chemicals."
    )
    run.italic = True
    run.font.size = Pt(10)
    disclaimer.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Save to BytesIO
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)  # Reset pointer to start

    return buffer
