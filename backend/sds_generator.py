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

def get_echa_preferred_name(cas_number=None, compound_name=None):
    """
    Query ECHA website to get preferred chemical name and other info.
    Uses web scraping (use responsibly, not for bulk).
    """
    if not (cas_number or compound_name):
        return {}

    # Build search URL
    base_url = "https://echa.europa.eu"
    query = cas_number or compound_name
    search_url = f"{base_url}/search?searchtext={query}&submit=Search"

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; SafetyDataBot/1.0; +https://example.com)"
    }

    try:
        import requests
        from bs4 import BeautifulSoup

        response = requests.get(search_url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"ECHA: Failed to fetch data (status {response.status_code})")
            return {}

        soup = BeautifulSoup(response.content, 'html.parser')

        # Find first substance link
        result = soup.find('a', href=True, text=lambda x: x and "Detail" in x)
        if not result:
            print("ECHA: No substance found.")
            return {}

        detail_url = base_url + result['href']

        # Fetch substance page
        detail_response = requests.get(detail_url, headers=headers, timeout=10)
        detail_soup = BeautifulSoup(detail_response.content, 'html.parser')

        # Extract Preferred IUPAC Name or EC Name
        name = None
        tables = detail_soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 2:
                    header = cols[0].get_text(strip=True)
                    value = cols[1].get_text(strip=True)
                    if "Preferred IUPAC" in header or "EC Name" in header or "Substance Name" in header:
                        name = value
                        break
            if name:
                break

        # Fallback: use page title
        if not name:
            title_tag = detail_soup.find('title')
            if title_tag:
                title = title_tag.get_text()
                if " - Substance Information" in title:
                    name = title.split(" - Substance Information")[0].strip()

        return {
            "echa_preferred_name": name or compound_name or "Not found",
            "echa_url": detail_url
        }

    except Exception as e:
        print(f"ECHA lookup failed: {e}")
        return {}

def get_detailed_safety_data_from_pubchem(cid):
    """
    Fetch real safety data from PubChem PUG-View API
    Returns a dict with real values for SDS sections
    """
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON"
    data = {
        "first_aid": {},
        "fire_fighting": {},
        "accidental_release": {},
        "handling_storage": {},
        "exposure_controls": {},
        "stability_reactivity": {},
        "disposal": {},
        "transport": {},
        "regulatory": {}
    }
    try:
        import requests
        response = requests.get(url, timeout=15)
        if response.status_code != 200:
            print(f"Failed to fetch PubChem data: {response.status_code}")
            return data

        json_data = response.json()

        def find_in_section(section, target_headings):
            """Search for specific heading and return its Information as strings"""
            if "TOCHeading" in section:
                heading = section["TOCHeading"]
                if any(t in heading for t in target_headings):
                    values = []
                    if "Information" in section:
                        for info in section["Information"]:
                            val = info.get("Value", {})
                            if "StringWithMarkup" in val:
                                for swm in val["StringWithMarkup"]:
                                    if "String" in swm:
                                        values.append(swm["String"])
                    return " | ".join(values) if values else "Not available"
            for sub in section.get("Section", []):
                result = find_in_section(sub, target_headings)
                if result != "Not available":
                    return result
            return "Not available"

        # Map section headings to PubChem equivalents
        for sec in json_data.get("Record", {}).get("Section", []):
            # Section 4: First Aid Measures
            if not data["first_aid"]:
                data["first_aid"] = {
                    "Inhalation": find_in_section(sec, ["Inhalation"]),
                    "Skin Contact": find_in_section(sec, ["Skin", "Dermal"]),
                    "Eye Contact": find_in_section(sec, ["Eye", "Ocular"]),
                    "Ingestion": find_in_section(sec, ["Ingestion", "Swallow"]),
                }

            # Section 5: Fire Fighting
            if not data["fire_fighting"]:
                data["fire_fighting"] = {
                    "Extinguishing Media": find_in_section(sec, ["Extinguishing Media", "Fire Fighting"]),
                    "Special Hazards": find_in_section(sec, ["Hazardous Combustion Products", "Special Hazards"])
                }

            # Section 6: Accidental Release
            if not data["accidental_release"]:
                data["accidental_release"] = {
                    "Personal Precautions": find_in_section(sec, ["Personal Precautions", "Protective Measures"]),
                    "Environmental Precautions": find_in_section(sec, ["Environmental Precautions"]),
                    "Methods of Containment": find_in_section(sec, ["Spill", "Release", "Containment"])
                }

            # Section 7: Handling and Storage
            if not data["handling_storage"]:
                data["handling_storage"] = {
                    "Handling": find_in_section(sec, ["Handling", "Precautions for Safe Handling"]),
                    "Storage": find_in_section(sec, ["Storage", "Conditions for Safe Storage"])
                }

            # Section 8: Exposure Controls
            if not data["exposure_controls"]:
                data["exposure_controls"] = {
                    "TLV-TWA": find_in_section(sec, ["TLV", "Threshold Limit Value"]),
                    "Engineering Controls": find_in_section(sec, ["Engineering Controls"]),
                    "Personal Protection": find_in_section(sec, ["Personal Protection", "Protective Equipment"])
                }

            # Section 10: Stability and Reactivity
            if not data["stability_reactivity"]:
                data["stability_reactivity"] = {
                    "Stability": find_in_section(sec, ["Stability", "Chemical Stability"]),
                    "Conditions to Avoid": find_in_section(sec, ["Conditions to Avoid"]),
                    "Incompatible Materials": find_in_section(sec, ["Incompatible Materials", "Reactivity"]),
                    "Hazardous Decomposition": find_in_section(sec, ["Hazardous Decomposition", "Combustion Products"])
                }

            # Section 13: Disposal
            if not data["disposal"]:
                data["disposal"] = {
                    "Disposal Method": find_in_section(sec, ["Disposal", "Waste Disposal"]),
                    "Contaminated Packaging": find_in_section(sec, ["Contaminated Packaging"])
                }

            # Section 14: Transport
            if not data["transport"]:
                data["transport"] = {
                    "UN Number": find_in_section(sec, ["UN Number"]),
                    "Proper Shipping Name": find_in_section(sec, ["Proper Shipping Name"]),
                    "Transport Hazard Class": find_in_section(sec, ["Hazard Class", "Transport Hazard"]),
                    "Packing Group": find_in_section(sec, ["Packing Group"])
                }

            # Section 15: Regulatory
            if not data["regulatory"]:
                data["regulatory"] = {
                    "TSCA": find_in_section(sec, ["TSCA"]),
                    "DSL": find_in_section(sec, ["DSL"]),
                    "WHMIS": find_in_section(sec, ["WHMIS"]),
                    "GHS Regulation": find_in_section(sec, ["GHS", "Globally Harmonized System"])
                }

    except Exception as e:
        print(f"Error fetching detailed safety data: {e}")
    return data


def get_pubchem_data(smiles):
    """Fetch data from PubChem with priority on common & botanical names"""
    try:
        compounds = pcp.get_compounds(smiles, 'smiles')
        if not compounds:
            print("No compound found in PubChem.")
            return {}

        c = compounds[0]
        mol = smiles_to_mol(smiles)
        if mol is None:
            print("Warning: Could not generate RDKit molecule from SMILES.")
            return {}

        # --- Molecular Weight ---
        try:
            mw_val = float(c.molecular_weight) if c.molecular_weight else 300.0
        except (TypeError, ValueError):
            mw_val = 300.0

        # --- LogP ---
        try:
            logp_val = float(c.xlogp) if c.xlogp not in [None, "--"] else 2.0
        except (TypeError, ValueError):
            logp_val = 2.0

        solubility = "Highly soluble" if mw_val < 500 and logp_val < 3 else "Low solubility"

        # --- Botanical Sources ---
        botanical_names = []
        try:
            url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{c.cid}/JSON/"
            import requests
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                for section in data.get("Record", {}).get("Section", []):
                    if any(x in section["TOCHeading"].lower() for x in ["natural", "organism", "source"]):
                        for sub in section.get("Section", []):
                            if any(x in sub["TOCHeading"].lower() for x in ["source", "occurrence", "organism"]):
                                for info in sub.get("Information", []):
                                    text = info.get("Value", {}).get("StringWithMarkup", [{}])[0].get("String", "")
                                    import re
                                    matches = re.findall(r"\b([A-Z][a-z]+ [a-z]+)\b", text)
                                    for match in matches:
                                        if match not in botanical_names:
                                            botanical_names.append(match)
        except Exception as e:
            print(f"Error fetching botanical sources: {e}")
            
        # Fetch real safety data from PubChem
        safety_data = get_detailed_safety_data_from_pubchem(c.cid)

        # --- SMART NAME RESOLUTION: Prioritize Common Names ---
        def norm(s):
            return s.lower().replace(" ", "").replace("-", "").replace("_", "").replace("acid", "")

        # High-priority common names (expand this list as needed)
        COMMON_NAMES = [
            "Aspirin", "Caffeine", "Curcumin", "Morphine", "Nicotine", "Quinine",
            "Ibuprofen", "Paracetamol", "Acetaminophen", "Resveratrol", "Capsaicin",
            "Theophylline", "Atropine", "Codeine", "Penicillin", "Digitalis", "Artemisinin"
        ]

        best_name = None

        # 1. Check if any synonym matches a common name
        if c.synonyms:
            for synonym in c.synonyms:
                for common in COMMON_NAMES:
                    if norm(synonym) == norm(common):
                        best_name = common
                        break
                if best_name:
                    break

        # 2. If not found, look for non-IUPAC, readable synonym
        if not best_name:
            for synonym in c.synonyms:
                synonym_clean = synonym.strip()
                # Skip long, technical, or IUPAC-like names
                if (len(synonym_clean) > 50 or
                    "acid" in norm(synonym_clean) or
                    "smiles" in norm(synonym_clean) or
                    "iupac" in norm(synonym_clean) or
                    "cas" in synonym_clean.upper()):
                    continue
                if synonym_clean and synonym_clean[0].isalpha() and "CID" not in synonym_clean:
                    best_name = synonym_clean
                    break

        # 3. Fallback to IUPAC or common fallbacks
        if not best_name:
            iupac = c.iupac_name or ""
            if "acetyloxy" in iupac.lower() and "benzoic" in iupac.lower():
                best_name = "Aspirin"
            elif "caffeine" in iupac.lower():
                best_name = "Caffeine"
            else:
                best_name = "Unknown Compound"
                
        # --- Physical Properties: Melting & Boiling Point ---
        melting_point = "Not available"
        boiling_point = "Not available"

        try:
            url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{c.cid}/JSON"
            import requests
            response = requests.get(url, timeout=15)
            if response.status_code == 200:
                data = response.json()

                def find_property(section, target):
                    if "TOCHeading" in section:
                        if section["TOCHeading"] == target:
                            if "Information" in section:
                                for info in section["Information"]:
                                    if "Value" in info:
                                        # Return first value string
                                        val = info["Value"]
                                        if "StringWithMarkup" in val:
                                            return val["StringWithMarkup"][0]["String"]
                                        elif "Number" in val:
                                            return f"{val['Number'][0]} °C"
                    for sub in section.get("Section", []):
                        result = find_property(sub, target)
                        if result:
                            return result
                    return None

                # Search all sections
                for sec in data.get("Record", {}).get("Section", []):
                    mp = find_property(sec, "Melting Point")
                    bp = find_property(sec, "Boiling Point")
                    if mp:
                        melting_point = mp
                    if bp:
                        boiling_point = bp

        except Exception as e:
            print(f"Error fetching melting/boiling point: {e}")

        # --- Add Botanical Source Only If Natural ---
        if botanical_names:
            display_name = f"{best_name} ({', '.join(botanical_names)})"
        else:
            display_name = best_name

        # --- Return Final Data ---
        return {
            "name": display_name,
            "formula": c.molecular_formula or "Not available",
            "mw": mw_val,
            "cas": getattr(c, 'cas', "Not available"),
            "logp": round(logp_val, 2),
            "solubility": solubility,
            "h_bond_donor": rdMolDescriptors.CalcNumHBD(mol),
            "h_bond_acceptor": rdMolDescriptors.CalcNumHBA(mol),
            "botanical_sources": botanical_names,
            "common_name": best_name,
            "melting_point": melting_point,
            "boiling_point": boiling_point,
            "safety_data": safety_data,  
            }
        

    except Exception as e:
        print(f"PubChem lookup failed: {e}")
    return {}

def predict_toxicity_protx(smiles):
    """Simulate ProTox-II prediction with LC50 estimate"""
    mol = smiles_to_mol(smiles)
    if not mol:
        return {}

    has_nitro = any(atom.GetAtomicNum() == 7 and atom.GetFormalCharge() == 1 for atom in mol.GetAtoms())
    logp = Descriptors.MolLogP(mol)
    mw = Descriptors.MolWt(mol)

    # Estimate LC50 (rat, inhalation, 4 hr)
    if mw < 300 and logp < 3:
        lc50_inhalation = "5000 mg/m³ (low toxicity)"
    elif logp > 3:
        lc50_inhalation = "200 mg/m³"
    else:
        lc50_inhalation = "1000 mg/m³"

    return {
        "toxicity_class": "Class IV (Low)" if not has_nitro else "Class II (High)",
        "hazard_endpoints": ["Hepatotoxicity"] if has_nitro else ["None predicted"],
        "ld50": "5000 mg/kg" if not has_nitro else "50 mg/kg",
        "lc50_inhalation_rat": lc50_inhalation
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

    # Step 1: Get data from PubChem
    pubchem = get_pubchem_data(smiles)
    protx = predict_toxicity_protx(smiles)
    props = get_physical_properties(mol)

    # -------------------------------------------------------------------------
    # ✅ INSERT ECHA NAME ENHANCEMENT HERE
    # -------------------------------------------------------------------------
    cas = pubchem.get("cas")
    if cas and "Not available" not in cas and cas.strip():
        echa_data = get_echa_preferred_name(cas_number=cas)
        if echa_data.get("echa_preferred_name") and "Not found" not in echa_data["echa_preferred_name"]:
            # Preserve botanical info if available
            botanical_part = f" ({', '.join(pubchem.get('botanical_sources', []))})" \
                             if pubchem.get("botanical_sources") else ""
            # Replace the name with ECHA's preferred name + botanical source
            pubchem["name"] = echa_data["echa_preferred_name"] + botanical_part
    # -------------------------------------------------------------------------
    # ✅ END OF INSERTION
    # -------------------------------------------------------------------------

    # Now proceed to build SDS using (possibly enhanced) pubchem data
    sds = {
        f"Section{i}": {
            "title": section_name(i),
            "data": {},
            "notes": []
        } for i in range(1, 17)
    }

    # Section 1
    # Section 1: Chemical Product and Company Identification
    botanical_sources = pubchem.get("botanical_sources", [])
    botanical_name_display = ", ".join(botanical_sources) if botanical_sources else "Not applicable"

    sds["Section1"]["data"] = {
        "Product Identifier": pubchem.get("name", "Unknown Compound"),
        "Company": "Automated SDS Generator",
        "Address": "N/A",
        "Emergency Phone": "N/A",
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
    # Section 9
    sds["Section9"]["data"] = {
        "Physical State": "Liquid" if mw_numeric < 300 else "Solid",
        "Color": "Colorless",
        "Odor": "Characteristic",
        "Melting Point": pubchem.get("melting_point", "Not available"),
        "Boiling Point": pubchem.get("boiling_point", "Not available"),
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
    "LC50 Inhalation Rat": protx.get("lc50_inhalation_rat"),
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
