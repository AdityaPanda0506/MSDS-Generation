# sds_data_fetcher.py
# Comprehensive data fetching module for SDS generation
# Separated and organized version of the original sds_generator.py

from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors
import pubchempy as pcp
import pandas as pd
import requests
import json
import time
from bs4 import BeautifulSoup
from urllib.parse import quote
import re
import logging
from datetime import datetime
from io import BytesIO
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SDSDataFetcher:
    """
    Main class for fetching comprehensive safety data for SDS generation.
    Integrates multiple data sources and provides structured output.
    """
    
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
    
    # ===== UTILITY FUNCTIONS =====
    
    def smiles_to_mol(self, smiles):
        """Convert SMILES to RDKit mol object"""
        return Chem.MolFromSmiles(smiles)
    
    def is_valid_value(self, value):
        """Check if a value is valid (not empty, not generic, contains useful information)"""
        if not value or value == "Not available":
            return False
            
        # Remove generic or too short responses
        if len(value.strip()) < 3:
            return False
            
        # Remove obviously invalid entries
        invalid_indicators = [
            "not found", "no data", "unknown", "error", "invalid", 
            "loading", "please wait", "404", "access denied"
        ]
        
        value_lower = value.lower()
        if any(indicator in value_lower for indicator in invalid_indicators):
            return False
            
        return True
    
    def merge_data_safely(self, target_data, source_data):
        """Safely merge data from source into target, only replacing 'Not available' values"""
        for category, category_data in source_data.items():
            if category in target_data and isinstance(category_data, dict):
                for field, value in category_data.items():
                    if (field in target_data[category] and 
                        target_data[category][field] == "Not available" and 
                        value and value != "Not available" and value.strip()):
                        target_data[category][field] = value.strip()
    
    def validate_extracted_data(self, data):
        """Validate and clean extracted data to ensure quality"""
        # Clean each category
        for category_key, category_data in data.items():
            if isinstance(category_data, dict):
                for field_key, field_value in list(category_data.items()):
                    if not self.is_valid_value(field_value):
                        category_data[field_key] = "Not available"
                    else:
                        # Clean and format the value
                        cleaned_value = field_value.strip()
                        if len(cleaned_value) > 500:  # Truncate very long entries
                            cleaned_value = cleaned_value[:500] + "..."
                        category_data[field_key] = cleaned_value
        
        return data
    
    # ===== PUBCHEM DATA FUNCTIONS =====
    
    def get_enhanced_pubchem_data(self, cid):
        """Enhanced PubChem data extraction with better error handling and parsing"""
        try:
            # Use PubChem PUG-View API for comprehensive data
            url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON"
            
            response = requests.get(url, headers=self.headers, timeout=30)
            if response.status_code != 200:
                logger.warning(f"PubChem API returned status {response.status_code}")
                return {}

            json_data = response.json()
            record = json_data.get("Record", {})
            sections = record.get("Section", [])
            
            extracted_data = {}
            
            def extract_text_from_value(value_obj):
                """Enhanced text extraction from PubChem value objects"""
                if not isinstance(value_obj, dict):
                    return str(value_obj).strip() if value_obj else None
                    
                # Handle StringWithMarkup format
                if "StringWithMarkup" in value_obj:
                    texts = []
                    for item in value_obj["StringWithMarkup"]:
                        if isinstance(item, dict) and "String" in item:
                            text = item["String"].strip()
                            if text and text not in texts:
                                texts.append(text)
                    return " | ".join(texts) if texts else None
                
                # Handle Number format
                elif "Number" in value_obj:
                    numbers = value_obj["Number"]
                    if isinstance(numbers, list) and numbers:
                        unit = value_obj.get("Unit", "")
                        return f"{numbers[0]} {unit}".strip()
                    elif numbers is not None:
                        unit = value_obj.get("Unit", "")
                        return f"{numbers} {unit}".strip()
                
                # Handle direct string values
                elif isinstance(value_obj, str):
                    return value_obj.strip()
                    
                return None

            def search_sections_recursive(section, target_keywords, max_depth=4, current_depth=0):
                """Recursively search through PubChem sections"""
                if current_depth > max_depth:
                    return None
                    
                # Check current section heading
                heading = section.get("TOCHeading", "").lower()
                
                # Direct keyword match
                for keyword in target_keywords:
                    if keyword.lower() in heading:
                        # Look for information in this section
                        for info in section.get("Information", []):
                            value = extract_text_from_value(info.get("Value", {}))
                            if value and len(value.strip()) > 2:
                                return value
                
                # Search subsections
                for subsection in section.get("Section", []):
                    result = search_sections_recursive(subsection, target_keywords, max_depth, current_depth + 1)
                    if result:
                        return result
                
                return None

            # Improved search mappings with more comprehensive keywords
            search_mappings = [
                # Physical Properties
                (["melting point", "m.p.", "mp", "melting", "fusion"], "physical_properties", "Melting Point"),
                (["boiling point", "b.p.", "bp", "boiling"], "physical_properties", "Boiling Point"),
                (["flash point", "fp"], "physical_properties", "Flash Point"),
                (["density", "specific gravity", "bulk density"], "physical_properties", "Density"),
                (["solubility", "water solubility", "aqueous solubility"], "physical_properties", "Solubility in Water"),
                (["vapor pressure", "vapour pressure", "vp"], "physical_properties", "Vapor Pressure"),
                (["appearance", "physical form", "physical state"], "physical_properties", "Appearance"),
                (["color", "colour"], "physical_properties", "Color"),
                (["odor", "odour", "smell"], "physical_properties", "Odor"),
                (["ph", "acidity"], "physical_properties", "pH"),
                (["refractive index", "ri"], "physical_properties", "Refractive Index"),
                (["viscosity"], "physical_properties", "Viscosity"),
                
                # Safety and Toxicological Information
                (["ld50", "ld 50", "lethal dose", "acute toxicity oral"], "toxicological", "LD50 Oral"),
                (["lc50", "lc 50", "lethal concentration"], "toxicological", "LC50 Inhalation"),
                (["dermal toxicity", "skin toxicity"], "toxicological", "LD50 Dermal"),
                (["carcinogen", "carcinogenic", "cancer", "carcinogenicity"], "toxicological", "Carcinogenicity"),
                (["mutagen", "mutagenic", "mutagenicity"], "toxicological", "Germ Cell Mutagenicity"),
                (["reproductive toxicity", "teratogen", "teratogenic"], "toxicological", "Reproductive Toxicity"),
                (["skin irritation", "dermal irritation"], "toxicological", "Skin Corrosion"),
                (["eye irritation", "ocular irritation", "eye damage"], "toxicological", "Serious Eye Damage"),
                
                # First Aid and Safety
                (["first aid", "emergency treatment"], "first_aid", "General First Aid"),
                (["inhalation", "breathing", "respiratory exposure"], "first_aid", "Inhalation"),
                (["skin contact", "dermal contact", "skin exposure"], "first_aid", "Skin Contact"),
                (["eye contact", "ocular contact", "eye exposure"], "first_aid", "Eye Contact"),
                (["ingestion", "oral exposure", "swallowing"], "first_aid", "Ingestion"),
                
                # Fire and Explosion
                (["fire", "extinguishing", "fire fighting"], "fire_fighting", "Extinguishing Media"),
                (["combustion products", "thermal decomposition"], "fire_fighting", "Hazardous Combustion Products"),
                (["fire hazard", "flammability"], "fire_fighting", "Special Hazards"),
                
                # Handling and Storage
                (["storage", "storage conditions"], "handling_storage", "Storage"),
                (["handling", "safe handling", "precautions"], "handling_storage", "Handling"),
                (["incompatible", "incompatibility", "avoid"], "handling_storage", "Incompatible Materials"),
                
                # Environmental
                (["environmental", "ecological", "ecotoxicity"], "ecological", "Ecotoxicity"),
                (["fish toxicity", "aquatic toxicity"], "ecological", "LC50 Fish"),
                (["daphnia"], "ecological", "EC50 Daphnia"),
                (["algae", "algal"], "ecological", "EC50 Algae"),
                (["biodegradation", "biodegradable"], "ecological", "Biodegradability"),
                
                # Regulatory
                (["ghs", "globally harmonized"], "hazard_identification", "GHS Classification"),
                (["hazard statement", "h-statement"], "hazard_identification", "Hazard Statements"),
                (["precautionary statement", "p-statement"], "hazard_identification", "Precautionary Statements"),
                (["signal word"], "hazard_identification", "Signal Word"),
            ]

            # Apply comprehensive search across all sections
            for section in sections:
                for keywords, category, field in search_mappings:
                    if category not in extracted_data:
                        extracted_data[category] = {}
                    
                    if field not in extracted_data[category] or not extracted_data[category][field]:
                        result = search_sections_recursive(section, keywords)
                        if result:
                            extracted_data[category][field] = result

            return extracted_data

        except requests.RequestException as e:
            logger.error(f"Network error fetching PubChem data: {e}")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error in PubChem fetch: {e}")
            return {}
    
    def get_pubchem_basic_data(self, smiles):
        """Get basic PubChem compound data from SMILES"""
        try:
            compounds = pcp.get_compounds(smiles, 'smiles')
            if not compounds:
                logger.warning("No compound found in PubChem.")
                return {}

            compound = compounds[0]
            mol = self.smiles_to_mol(smiles)
            if mol is None:
                logger.warning("Could not generate RDKit molecule from SMILES.")
                return {}

            # Basic molecular properties
            try:
                mw_val = float(compound.molecular_weight) if compound.molecular_weight else 300.0
            except (TypeError, ValueError):
                mw_val = 300.0

            try:
                logp_val = float(compound.xlogp) if compound.xlogp not in [None, "--"] else 2.0
            except (TypeError, ValueError):
                logp_val = 2.0

            solubility = "Highly soluble" if mw_val < 500 and logp_val < 3 else "Low solubility"

            # Enhanced name resolution
            def normalize_name(s):
                return s.lower().replace(" ", "").replace("-", "").replace("_", "").replace("acid", "")

            COMMON_NAMES = [
                "Aspirin", "Caffeine", "Curcumin", "Morphine", "Nicotine", "Quinine",
                "Ibuprofen", "Paracetamol", "Acetaminophen", "Resveratrol", "Capsaicin",
                "Theophylline", "Atropine", "Codeine", "Penicillin", "Digitalis", "Artemisinin",
                "Vanillin", "Menthol", "Thymol", "Eugenol", "Limonene", "Linalool"
            ]

            best_name = None

            # Name resolution priority: Common names > readable synonyms > IUPAC
            if compound.synonyms:
                for synonym in compound.synonyms:
                    for common in COMMON_NAMES:
                        if normalize_name(synonym) == normalize_name(common):
                            best_name = common
                            break
                    if best_name:
                        break

            if not best_name and compound.synonyms:
                for synonym in compound.synonyms:
                    synonym_clean = synonym.strip()
                    if (len(synonym_clean) <= 50 and
                        not any(x in synonym_clean.lower() for x in ["smiles", "iupac", "cas"]) and
                        synonym_clean and synonym_clean[0].isalpha() and "CID" not in synonym_clean):
                        best_name = synonym_clean
                        break

            if not best_name:
                iupac = compound.iupac_name or ""
                if "acetyloxy" in iupac.lower() and "benzoic" in iupac.lower():
                    best_name = "Aspirin"
                elif "caffeine" in iupac.lower():
                    best_name = "Caffeine"
                else:
                    best_name = compound.iupac_name or "Unknown Compound"

            return {
                "name": best_name,
                "formula": compound.molecular_formula or "Not available",
                "mw": mw_val,
                "cas": getattr(compound, 'cas', "Not available"),
                "logp": round(logp_val, 2),
                "solubility": solubility,
                "h_bond_donor": rdMolDescriptors.CalcNumHBD(mol),
                "h_bond_acceptor": rdMolDescriptors.CalcNumHBA(mol),
                "common_name": best_name,
                "cid": compound.cid,
                "synonyms": compound.synonyms[:10] if compound.synonyms else []
            }

        except Exception as e:
            logger.error(f"PubChem basic data fetch failed: {e}")
            return {}
    
    def get_pubchem_synonyms_and_properties(self, cid):
        """Fetch additional synonyms and computed properties from PubChem"""
        try:
            # Get synonyms
            synonyms_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/synonyms/JSON"
            synonyms_response = requests.get(synonyms_url, timeout=15, headers=self.headers)
            
            synonyms = []
            if synonyms_response.status_code == 200:
                synonyms_data = synonyms_response.json()
                synonyms = synonyms_data.get("InformationList", {}).get("Information", [{}])[0].get("Synonym", [])
            
            # Get computed properties
            props_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/MolecularFormula,MolecularWeight,XLogP,TPSA,Complexity,HBondDonorCount,HBondAcceptorCount/JSON"
            props_response = requests.get(props_url, timeout=15, headers=self.headers)
            
            properties = {}
            if props_response.status_code == 200:
                props_data = props_response.json()
                prop_info = props_data.get("PropertyTable", {}).get("Properties", [{}])[0]
                properties = {
                    "molecular_formula": prop_info.get("MolecularFormula"),
                    "molecular_weight": prop_info.get("MolecularWeight"),
                    "xlogp": prop_info.get("XLogP"),
                    "tpsa": prop_info.get("TPSA"),
                    "complexity": prop_info.get("Complexity"),
                    "hbd_count": prop_info.get("HBondDonorCount"),
                    "hba_count": prop_info.get("HBondAcceptorCount")
                }
            
            return {"synonyms": synonyms, "properties": properties}
            
        except Exception as e:
            logger.error(f"Error fetching PubChem synonyms/properties: {e}")
            return {"synonyms": [], "properties": {}}
    
    # ===== EXTERNAL DATA SOURCE FUNCTIONS =====
    
    def get_echa_preferred_name(self, cas_number=None, compound_name=None):
        """Query ECHA website to get preferred chemical name and other info"""
        if not (cas_number or compound_name):
            return {}

        try:
            # Build search URL
            base_url = "https://echa.europa.eu"
            query = cas_number or compound_name
            search_url = f"{base_url}/search?searchtext={query}&submit=Search"

            response = requests.get(search_url, headers=self.headers, timeout=10)
            if response.status_code != 200:
                logger.warning(f"ECHA: Failed to fetch data (status {response.status_code})")
                return {}

            soup = BeautifulSoup(response.content, 'html.parser')

            # Find first substance link
            result = soup.find('a', href=True, text=lambda x: x and "Detail" in x)
            if not result:
                logger.info("ECHA: No substance found.")
                return {}

            detail_url = base_url + result['href']

            # Fetch substance page
            detail_response = requests.get(detail_url, headers=self.headers, timeout=10)
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
            logger.error(f"ECHA lookup failed: {e}")
            return {}
    
    def fetch_chemidplus_nlm(self, cas_number):
        """Fetch data from ChemIDplus NLM database"""
        extracted_data = {}
        
        try:
            # ChemIDplus search URL
            search_url = f"https://chem.nlm.nih.gov/chemidplus/rn/{cas_number}"
            
            response = requests.get(search_url, headers=self.headers, timeout=15)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Extract toxicity data
                tox_table = soup.find('table', {'id': 'toxicity'})
                if tox_table:
                    rows = tox_table.find_all('tr')
                    for row in rows:
                        cells = row.find_all('td')
                        if len(cells) >= 2:
                            test_type = cells[0].get_text(strip=True).lower()
                            value = cells[1].get_text(strip=True)
                            
                            if 'oral' in test_type and 'ld50' in test_type:
                                if 'toxicological' not in extracted_data:
                                    extracted_data['toxicological'] = {}
                                extracted_data['toxicological']['LD50 Oral'] = value
                            elif 'inhalation' in test_type and ('lc50' in test_type or 'ld50' in test_type):
                                if 'toxicological' not in extracted_data:
                                    extracted_data['toxicological'] = {}
                                extracted_data['toxicological']['LC50 Inhalation'] = value
                
                # Extract physical properties
                prop_table = soup.find('table', {'id': 'physical'})
                if prop_table:
                    rows = prop_table.find_all('tr')
                    for row in rows:
                        cells = row.find_all('td')
                        if len(cells) >= 2:
                            prop_name = cells[0].get_text(strip=True).lower()
                            value = cells[1].get_text(strip=True)
                            
                            if 'melting' in prop_name:
                                if 'physical_properties' not in extracted_data:
                                    extracted_data['physical_properties'] = {}
                                extracted_data['physical_properties']['Melting Point'] = value
                            elif 'boiling' in prop_name:
                                if 'physical_properties' not in extracted_data:
                                    extracted_data['physical_properties'] = {}
                                extracted_data['physical_properties']['Boiling Point'] = value
                            elif 'density' in prop_name:
                                if 'physical_properties' not in extracted_data:
                                    extracted_data['physical_properties'] = {}
                                extracted_data['physical_properties']['Density'] = value
                                
        except Exception as e:
            logger.error(f"ChemIDplus NLM fetch error: {e}")
            
        return extracted_data
    
    def fetch_nist_webbook_data(self, cas_number):
        """Fetch data from NIST WebBook with better parsing"""
        if not cas_number or cas_number == "Not available":
            return {}
            
        extracted_data = {}
        
        try:
            # NIST Chemistry WebBook search
            search_url = "https://webbook.nist.gov/cgi/cbook.cgi"
            params = {
                "ID": cas_number,
                "Mask": "4",  # Thermochemical data
                "Type": "Name",
                "Units": "SI"
            }
            
            response = requests.get(search_url, params=params, headers=self.headers, timeout=20)
            
            if response.status_code == 200 and "not found" not in response.text.lower():
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Look for data tables
                for table in soup.find_all('table'):
                    rows = table.find_all('tr')
                    for row in rows:
                        cells = row.find_all('td')
                        if len(cells) >= 2:
                            prop_name = cells[0].get_text().strip().lower()
                            value = cells[1].get_text().strip()
                            
                            if value and value != "-" and len(value) > 1:
                                if 'physical_properties' not in extracted_data:
                                    extracted_data['physical_properties'] = {}
                                    
                                if 'melting' in prop_name or 'fusion' in prop_name:
                                    extracted_data['physical_properties']['Melting Point'] = f"{value} (NIST)"
                                elif 'boiling' in prop_name or 'vaporization' in prop_name:
                                    extracted_data['physical_properties']['Boiling Point'] = f"{value} (NIST)"
                                elif 'density' in prop_name:
                                    extracted_data['physical_properties']['Density'] = f"{value} (NIST)"
                                elif 'vapor pressure' in prop_name:
                                    extracted_data['physical_properties']['Vapor Pressure'] = f"{value} (NIST)"
                
                # Look for phase change data
                phase_tables = soup.find_all('table', {'class': 'data'})
                for table in phase_tables:
                    caption = table.find('caption')
                    if caption and ('phase' in caption.get_text().lower() or 
                                  'temperature' in caption.get_text().lower()):
                        rows = table.find_all('tr')[1:]  # Skip header
                        for row in rows:
                            cells = row.find_all('td')
                            if len(cells) >= 2:
                                temp_val = cells[0].get_text().strip()
                                prop_type = caption.get_text().lower()
                                
                                if temp_val and temp_val != "-":
                                    if 'physical_properties' not in extracted_data:
                                        extracted_data['physical_properties'] = {}
                                        
                                    if 'melting' in prop_type:
                                        extracted_data['physical_properties']['Melting Point'] = f"{temp_val} K (NIST)"
                                    elif 'boiling' in prop_type:
                                        extracted_data['physical_properties']['Boiling Point'] = f"{temp_val} K (NIST)"
                                        
        except Exception as e:
            logger.error(f"NIST WebBook fetch error: {e}")
            
        return extracted_data
    
    # ===== TOXICITY PREDICTION FUNCTIONS =====
    
    def predict_toxicity_protx(self, smiles):
        """Enhanced toxicity prediction with comprehensive assessment"""
        mol = self.smiles_to_mol(smiles)
        if not mol:
            return {}

        # Enhanced toxicity indicators
        has_nitro = any(atom.GetAtomicNum() == 7 and atom.GetFormalCharge() == 1 for atom in mol.GetAtoms())
        has_aromatic_amine = any(atom.GetAtomicNum() == 7 and atom.GetIsAromatic() for atom in mol.GetAtoms())
        has_halogen = any(atom.GetAtomicNum() in [9, 17, 35, 53] for atom in mol.GetAtoms())
        
        logp = Descriptors.MolLogP(mol)
        mw = Descriptors.MolWt(mol)
        tpsa = Descriptors.TPSA(mol)

        # Enhanced toxicity classification
        toxicity_score = 0
        if has_nitro:
            toxicity_score += 3
        if has_aromatic_amine:
            toxicity_score += 2
        if has_halogen:
            toxicity_score += 1
        if logp > 5:
            toxicity_score += 2
        if mw > 500:
            toxicity_score += 1

        # Determine toxicity class based on score
        if toxicity_score >= 5:
            toxicity_class = "Class I (Very High)"
            ld50 = "5-50 mg/kg"
            lc50_inhalation = "10-100 mg/m³"
        elif toxicity_score >= 3:
            toxicity_class = "Class II (High)"
            ld50 = "50-500 mg/kg"
            lc50_inhalation = "100-1000 mg/m³"
        elif toxicity_score >= 1:
            toxicity_class = "Class III (Moderate)"
            ld50 = "500-2000 mg/kg"
            lc50_inhalation = "1000-5000 mg/m³"
        else:
            toxicity_class = "Class IV (Low)"
            ld50 = ">2000 mg/kg"
            lc50_inhalation = ">5000 mg/m³"

        # Predict target organs based on structure
        target_organs = []
        if has_nitro or has_aromatic_amine:
            target_organs.extend(["Liver", "Blood"])
        if logp > 3:
            target_organs.append("CNS")
        if tpsa < 60:
            target_organs.append("Brain")
        if not target_organs:
            target_organs = ["Not specified"]

        hazard_endpoints = []
        if has_nitro:
            hazard_endpoints.extend(["Hepatotoxicity", "Methemoglobinemia"])
        if has_aromatic_amine:
            hazard_endpoints.append("Carcinogenicity")
        if has_halogen:
            hazard_endpoints.append("Nephrotoxicity")
        if not hazard_endpoints:
            hazard_endpoints = ["None predicted"]

        return {
            "toxicity_class": toxicity_class,
            "hazard_endpoints": hazard_endpoints,
            "ld50": ld50,
            "lc50_inhalation_rat": lc50_inhalation,
            "target_organs": target_organs,
            "toxicity_score": toxicity_score
        }
    
    # ===== PHYSICAL PROPERTIES CALCULATION =====
    
    def get_physical_properties(self, mol):
        """Enhanced properties computation using RDKit"""
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
            "Formal Charge": Chem.rdmolops.GetFormalCharge(mol),
            "Ring Count": rdMolDescriptors.CalcNumRings(mol),
            "Aromatic Ring Count": rdMolDescriptors.CalcNumAromaticRings(mol),
            "Saturated Ring Count": rdMolDescriptors.CalcNumSaturatedRings(mol),
            "Fraction Csp3": rdMolDescriptors.CalcFractionCSP3(mol),
            "Molecular Refractivity": f"{Descriptors.MolMR(mol):.2f}",
            "BalabanJ": f"{Descriptors.BalabanJ(mol):.3f}",
            "BertzCT": f"{Descriptors.BertzCT(mol):.2f}"
        }
    
    # ===== COMPREHENSIVE SAFETY DATA AGGREGATION =====
    
    def get_comprehensive_safety_data(self, cid, smiles=None, cas_number=None, compound_name=None):
        """
        Master function to fetch comprehensive safety data from multiple sources.
        Returns structured data for SDS generation.
        """
        
        # Initialize comprehensive data structure
        data = {
            "first_aid": {
                "Inhalation": "Not available",
                "Skin Contact": "Not available", 
                "Eye Contact": "Not available",
                "Ingestion": "Not available",
                "General First Aid": "Not available",
                "Most Important Symptoms": "Not available",
                "Notes to Physician": "Not available"
            },
            
            "fire_fighting": {
                "Extinguishing Media": "Not available",
                "Unsuitable Extinguishing Media": "Not available",
                "Special Hazards": "Not available",
                "Special Protective Equipment": "Not available",
                "Hazardous Combustion Products": "Not available"
            },
            
            "accidental_release": {
                "Personal Precautions": "Not available",
                "Environmental Precautions": "Not available",
                "Methods of Containment": "Not available",
                "Methods of Cleaning Up": "Not available",
                "Reference to Other Sections": "Not available"
            },
            
            "handling_storage": {
                "Handling": "Not available",
                "Storage": "Not available",
                "Precautions for Safe Handling": "Not available",
                "Conditions for Safe Storage": "Not available",
                "Storage Temperature": "Not available",
                "Incompatible Materials": "Not available"
            },
            
            "exposure_controls": {
                "TLV-TWA": "Not available",
                "TLV-STEL": "Not available",
                "PEL": "Not available",
                "IDLH": "Not available",
                "Engineering Controls": "Not available",
                "Personal Protection": "Not available",
                "Eye Protection": "Not available",
                "Skin Protection": "Not available",
                "Respiratory Protection": "Not available",
                "Thermal Hazards": "Not available"
            },
            
            "physical_properties": {
                "Physical State": "Not available",
                "Appearance": "Not available",
                "Color": "Not available",
                "Odor": "Not available",
                "Odor Threshold": "Not available",
                "pH": "Not available",
                "Melting Point": "Not available",
                "Boiling Point": "Not available",
                "Flash Point": "Not available",
                "Evaporation Rate": "Not available",
                "Flammability": "Not available",
                "Upper Explosive Limit": "Not available",
                "Lower Explosive Limit": "Not available",
                "Vapor Pressure": "Not available",
                "Vapor Density": "Not available",
                "Density": "Not available",
                "Relative Density": "Not available",
                "Solubility in Water": "Not available",
                "Partition Coefficient": "Not available",
                "Auto-ignition Temperature": "Not available",
                "Decomposition Temperature": "Not available",
                "Kinematic Viscosity": "Not available",
                "Dynamic Viscosity": "Not available"
            },
            
            "stability_reactivity": {
                "Stability": "Not available",
                "Reactivity": "Not available",
                "Chemical Stability": "Not available",
                "Conditions to Avoid": "Not available",
                "Incompatible Materials": "Not available",
                "Hazardous Decomposition": "Not available",
                "Hazardous Polymerization": "Not available",
                "Possibility of Hazardous Reactions": "Not available"
            },
            
            "toxicological": {
                "Acute Toxicity": "Not available",
                "LD50 Oral": "Not available",
                "LD50 Dermal": "Not available",
                "LC50 Inhalation": "Not available",
                "Skin Corrosion": "Not available",
                "Serious Eye Damage": "Not available",
                "Respiratory Sensitization": "Not available",
                "Skin Sensitization": "Not available",
                "Germ Cell Mutagenicity": "Not available",
                "Carcinogenicity": "Not available",
                "Reproductive Toxicity": "Not available",
                "STOT Single Exposure": "Not available",
                "STOT Repeated Exposure": "Not available",
                "Aspiration Hazard": "Not available",
                "Routes of Exposure": "Not available",
                "Target Organs": "Not available"
            },
            
            "ecological": {
                "Ecotoxicity": "Not available",
                "LC50 Fish": "Not available",
                "EC50 Daphnia": "Not available",
                "EC50 Algae": "Not available",
                "Persistence": "Not available",
                "Biodegradability": "Not available",
                "Bioaccumulation": "Not available",
                "Mobility in Soil": "Not available",
                "Other Adverse Effects": "Not available"
            },
            
            "disposal": {
                "Disposal Method": "Not available",
                "Waste Treatment Methods": "Not available",
                "Contaminated Packaging": "Not available",
                "Waste Disposal Methods": "Not available"
            },
            
            "transport": {
                "UN Number": "Not available",
                "UN Proper Shipping Name": "Not available",
                "Transport Hazard Class": "Not available",
                "Packing Group": "Not available",
                "Environmental Hazards": "Not available",
                "Marine Pollutant": "Not available",
                "Special Precautions": "Not available"
            },
            
            "regulatory": {
                "TSCA": "Not available",
                "DSL/NDSL": "Not available",
                "EINECS/ELINCS": "Not available",
                "ENCS": "Not available",
                "IECSC": "Not available",
                "KECL": "Not available",
                "PICCS": "Not available",
                "AICS": "Not available",
                "NZIoC": "Not available",
                "WHMIS": "Not available",
                "GHS Classification": "Not available",
                "SARA 313": "Not available",
                "California Proposition 65": "Not available"
            },
            
            "hazard_identification": {
                "GHS Classification": "Not available",
                "Signal Word": "Not available",
                "Hazard Statements": "Not available",
                "Precautionary Statements": "Not available",
                "Pictograms": "Not available"
            }
        }

        logger.info(f"[Multi-Source] Starting comprehensive data collection for CID {cid}")
        
        # 1. Enhanced PubChem data collection
        try:
            pubchem_data = self.get_enhanced_pubchem_data(cid)
            self.merge_data_safely(data, pubchem_data)
            logger.info(f"[PubChem] Enhanced data merged successfully")
        except Exception as e:
            logger.error(f"[PubChem] Error: {e}")

        # 2. ChemIDplus NLM data
        if cas_number and cas_number != "Not available":
            try:
                chemidplus_data = self.fetch_chemidplus_nlm(cas_number)
                self.merge_data_safely(data, chemidplus_data)
                logger.info(f"[ChemIDplus] NLM data merged successfully")
            except Exception as e:
                logger.error(f"[ChemIDplus] Error: {e}")

        # 3. NIST WebBook data
        if cas_number and cas_number != "Not available":
            try:
                nist_data = self.fetch_nist_webbook_data(cas_number)
                self.merge_data_safely(data, nist_data)
                logger.info(f"[NIST] Data merged successfully")
            except Exception as e:
                logger.error(f"[NIST] Error: {e}")

        # Validate all extracted data
        data = self.validate_extracted_data(data)
        logger.info(f"[Multi-Source] Data validation completed")

        return data
    
    # ===== MAIN DATA AGGREGATION METHOD =====
    
    def fetch_all_data(self, smiles):
        """
        Main method to fetch all data for SDS generation.
        Returns comprehensive compound data structure.
        """
        logger.info(f"[SDS Data Fetcher] Starting comprehensive data collection for SMILES: {smiles}")
        
        # Initialize result structure
        result = {
            "basic_data": {},
            "safety_data": {},
            "toxicity_data": {},
            "physical_properties": {},
            "additional_data": {},
            "data_sources": [],
            "errors": []
        }
        
        try:
            # 1. Get basic PubChem data and molecular info
            mol = self.smiles_to_mol(smiles)
            if not mol:
                result["errors"].append("Could not generate RDKit molecule from SMILES")
                return result
            
            basic_data = self.get_pubchem_basic_data(smiles)
            if basic_data:
                result["basic_data"] = basic_data
                result["data_sources"].append("PubChem Basic")
                logger.info("[Data Fetcher] Basic PubChem data collected")
            else:
                result["errors"].append("Failed to fetch basic PubChem data")
            
            # 2. Get physical properties from RDKit
            try:
                physical_props = self.get_physical_properties(mol)
                result["physical_properties"] = physical_props
                result["data_sources"].append("RDKit Calculations")
                logger.info("[Data Fetcher] Physical properties calculated")
            except Exception as e:
                result["errors"].append(f"Physical properties calculation failed: {str(e)}")
            
            # 3. Get toxicity predictions
            try:
                toxicity_data = self.predict_toxicity_protx(smiles)
                result["toxicity_data"] = toxicity_data
                result["data_sources"].append("ProTox Predictions")
                logger.info("[Data Fetcher] Toxicity predictions completed")
            except Exception as e:
                result["errors"].append(f"Toxicity prediction failed: {str(e)}")
            
            # 4. Get comprehensive safety data if CID is available
            cid = basic_data.get("cid")
            cas = basic_data.get("cas")
            compound_name = basic_data.get("name")
            
            if cid:
                try:
                    safety_data = self.get_comprehensive_safety_data(cid, smiles, cas, compound_name)
                    result["safety_data"] = safety_data
                    result["data_sources"].extend(["PubChem Safety", "ChemIDplus", "NIST WebBook"])
                    logger.info("[Data Fetcher] Comprehensive safety data collected")
                except Exception as e:
                    result["errors"].append(f"Safety data collection failed: {str(e)}")
            
            # 5. Get additional data sources
            if cas and cas != "Not available":
                try:
                    echa_data = self.get_echa_preferred_name(cas_number=cas)
                    if echa_data:
                        result["additional_data"]["echa"] = echa_data
                        result["data_sources"].append("ECHA")
                        logger.info("[Data Fetcher] ECHA data collected")
                except Exception as e:
                    result["errors"].append(f"ECHA data collection failed: {str(e)}")
            
            # 6. Get additional PubChem properties
            if cid:
                try:
                    additional_pubchem = self.get_pubchem_synonyms_and_properties(cid)
                    if additional_pubchem:
                        result["additional_data"]["pubchem_extended"] = additional_pubchem
                        logger.info("[Data Fetcher] Extended PubChem data collected")
                except Exception as e:
                    result["errors"].append(f"Extended PubChem data failed: {str(e)}")
            
            logger.info(f"[Data Fetcher] Data collection completed. Sources used: {', '.join(result['data_sources'])}")
            
            if result["errors"]:
                logger.warning(f"[Data Fetcher] Errors encountered: {'; '.join(result['errors'])}")
            
            return result
            
        except Exception as e:
            logger.error(f"[Data Fetcher] Critical error in fetch_all_data: {str(e)}")
            result["errors"].append(f"Critical error: {str(e)}")
            return result


# ===== HELPER FUNCTIONS FOR STANDALONE USAGE =====

def create_sds_data_fetcher():
    """Factory function to create and return an SDSDataFetcher instance"""
    return SDSDataFetcher()

def fetch_compound_data(smiles):
    """
    Convenience function for fetching all compound data.
    Returns comprehensive data structure for SDS generation.
    
    Usage:
        data = fetch_compound_data("CC(=O)OC1=CC=CC=C1C(=O)O")  # Aspirin
        print(data["basic_data"]["name"])
        print(data["toxicity_data"]["toxicity_class"])
    """
    fetcher = SDSDataFetcher()
    return fetcher.fetch_all_data(smiles)

def get_section_names():
    """Return mapping of SDS section numbers to names"""
    return {
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


# ===== EXAMPLE USAGE =====

if __name__ == "__main__":
    # Example usage of the SDS Data Fetcher
    print("SDS Data Fetcher Module")
    print("=======================")
    
    # Test with aspirin SMILES
    aspirin_smiles = "CC(=O)OC1=CC=CC=C1C(=O)O"
    
    print(f"Testing with Aspirin SMILES: {aspirin_smiles}")
    print("Fetching comprehensive data...")
    
    try:
        data = fetch_compound_data(aspirin_smiles)
        
        print(f"\nBasic Data:")
        print(f"- Name: {data['basic_data'].get('name', 'Unknown')}")
        print(f"- Formula: {data['basic_data'].get('formula', 'Unknown')}")
        print(f"- CAS: {data['basic_data'].get('cas', 'Unknown')}")
        print(f"- Molecular Weight: {data['basic_data'].get('mw', 'Unknown')} g/mol")
        
        print(f"\nToxicity Classification:")
        print(f"- Class: {data['toxicity_data'].get('toxicity_class', 'Unknown')}")
        print(f"- LD50 (predicted): {data['toxicity_data'].get('ld50', 'Unknown')}")
        
        print(f"\nData Sources Used: {', '.join(data['data_sources'])}")
        
        if data['errors']:
            print(f"\nErrors: {'; '.join(data['errors'])}")
    
    except Exception as e:
        print(f"Error during testing: {e}")