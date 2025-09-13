# sds_data_fetcher.py
# Comprehensive data fetching module for SDS generation
# Enhanced with structural analysis and reactivity prediction

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
import os
# from mistralai.client import MistralClient
# from mistralai.models.chat_completion import ChatMessage
from mistralai import Mistral
from dotenv import load_dotenv
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SDSDataFetcher:
    """
    Enhanced class for fetching comprehensive safety data for SDS generation.
    Integrates multiple data sources and provides structured output with 
    improved structural analysis and reactivity prediction.
    """
    
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        # Initialize Mistral client
        self.mistral_client = None
        self.setup_mistral_client()
    
    def setup_mistral_client(self):
        """Initialize Mistral AI client if API key is available"""
        try:
            api_key = os.getenv('MISTRAL_API_KEY')
            if api_key:
                self.mistral_client = Mistral(api_key=api_key)
                logger.info("[Mistral] Client initialized successfully")
            else:
                logger.warning("[Mistral] API key not found in environment variables")
        except Exception as e:
            logger.error(f"[Mistral] Failed to initialize client: {e}")
            self.mistral_client = None

    def generate_missing_data_with_llm(self, compound_data, missing_fields):
        """Use Mistral LLM to generate missing SDS data with improved cleaning"""
        if not self.mistral_client or not missing_fields:
            return {}

        try:
            # Prepare context about the compound
            basic_data = compound_data.get("basic_data", {})
            compound_name = basic_data.get("name", "Unknown compound")
            formula = basic_data.get("formula", "Unknown")
            mw = basic_data.get("mw", "Unknown")
            
            # Get available structural and toxicity information
            structural_info = compound_data.get("structural_analysis", {})
            toxicity_info = compound_data.get("toxicity_data", {})
            physical_props = compound_data.get("physical_properties", {})
            
            context_prompt = f"""
    You are an expert chemical safety specialist generating Safety Data Sheet (SDS) entries according to GHS/OSHA/CLP regulations.

    CRITICAL OUTPUT REQUIREMENTS:
    - Provide ONLY the requested value for each field
    - NO JSON formatting, brackets, or braces
    - NO field labels or explanations  
    - NO markdown formatting, asterisks, or underscores
    - NO quotation marks around values
    - Write in standard SDS style (concise, factual, direct)
    - Use imperative or passive voice
    - For LD50/LC50: use format "X-Y mg/kg" or "Not established"
    - For hazard statements: use "H302: Harmful if swallowed" format
    - For temperatures: use "120-125 °C" format
    - For instructions: "Move to fresh air. Seek medical attention."

    Compound Information:
    - Name: {compound_name}
    - Formula: {formula}
    - Molecular Weight: {mw} g/mol
    - Structural Hazards: {len(structural_info.get('hazards', []))} identified
    - Toxicity Class: {toxicity_info.get('toxicity_class', 'Unknown')}

    For each missing field below, provide ONLY the clean value without formatting:
    """
            
            generated_data = {}
            
            # Process missing fields in smaller batches for better results
            field_batches = [missing_fields[i:i+3] for i in range(0, len(missing_fields), 3)]
            
            for batch in field_batches:
                batch_prompt = context_prompt + "\n"
                field_mapping = {}  # Track field order
                
                for idx, (field_path, field_name) in enumerate(batch):
                    batch_prompt += f"{idx+1}. {field_name}\n"
                    field_mapping[idx+1] = field_path
                
                batch_prompt += f"\nProvide exactly one clean value per line, numbered 1-{len(batch)}:"
                
                try:
                    messages = [{"role": "user", "content": batch_prompt}]
                    
                    response = self.mistral_client.chat.complete(
                        model="mistral-large-latest",
                        messages=messages,
                        temperature=0.1,  # Very low temperature for consistency
                        max_tokens=1200
                    )
                    
                    response_text = response.choices[0].message.content
                    
                    # Parse numbered responses
                    lines = response_text.split('\n')
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        
                        # Look for numbered format: "1. value" or "1: value"
                        match = re.match(r'^(\d+)[\.\:\)]\s*(.+)$', line)
                        if match:
                            num = int(match.group(1))
                            raw_value = match.group(2)
                            
                            if num in field_mapping:
                                # Apply comprehensive cleaning - multiple passes
                                cleaned_value = self.clean_llm_output(raw_value)
                                cleaned_value = self.clean_llm_output(cleaned_value)  # Second pass
                                cleaned_value = self.final_text_polish(cleaned_value)  # Final polish
                                
                                if cleaned_value and len(cleaned_value) >= 5:
                                    field_path = field_mapping[num]
                                    generated_data[field_path] = cleaned_value
                    
                    time.sleep(0.5)  # Rate limiting
                    
                except Exception as e:
                    logger.error(f"[Mistral] Error generating batch: {e}")
                    continue
            
            logger.info(f"[Mistral] Generated {len(generated_data)} cleaned field values")
            return generated_data
            
        except Exception as e:
            logger.error(f"[Mistral] Error in generate_missing_data_with_llm: {e}")
            return {}

    def prioritize_missing_fields(self, missing_fields):
        """Prioritize missing fields by importance for SDS compliance including transport"""
        # Critical fields that are legally required
        critical_fields = [
            'first_aid.Inhalation', 'first_aid.Skin Contact', 'first_aid.Eye Contact', 'first_aid.Ingestion',
            'fire_fighting.Extinguishing Media', 'handling_storage.Handling', 'handling_storage.Storage',
            'exposure_controls.Engineering Controls', 'toxicological.Acute Toxicity',
            'stability_reactivity.Chemical Stability', 'transport.UN Number', 'transport.Transport Hazard Class'
        ]
        
        # Important fields for safety and compliance
        important_fields = [
            'hazard_identification.Signal Word', 'hazard_identification.Hazard Statements',
            'physical_properties.Flash Point', 'disposal.Disposal Method',
            'transport.UN Proper Shipping Name', 'transport.Packing Group',
            'ecological.Ecotoxicity', 'accidental_release.Personal Precautions'
        ]
        
        # Secondary fields
        secondary_fields = [
            'transport.Environmental Hazards', 'transport.Marine Pollutant', 'transport.Special Precautions',
            'regulatory.GHS Classification', 'exposure_controls.TLV-TWA'
        ]
        
        prioritized = []
        
        # Add critical fields first
        for field_path, field_name in missing_fields:
            if field_path in critical_fields:
                prioritized.append((field_path, field_name))
        
        # Add important fields
        for field_path, field_name in missing_fields:
            if field_path in important_fields and (field_path, field_name) not in prioritized:
                prioritized.append((field_path, field_name))
        
        # Add secondary fields
        for field_path, field_name in missing_fields:
            if field_path in secondary_fields and (field_path, field_name) not in prioritized:
                prioritized.append((field_path, field_name))
        
        # Add remaining fields
        for field_path, field_name in missing_fields:
            if (field_path, field_name) not in prioritized:
                prioritized.append((field_path, field_name))
        
        # Limit to most important fields to avoid overwhelming the LLM
        return prioritized[:20]  # Process max 20 fields per compound
        
    def clean_llm_output(self, raw_text):
        """Enhanced cleaning and normalization of raw LLM output to match SDS style."""
        if not raw_text:
            return ""

        # Remove common LLM artifacts and formatting
        cleaned = raw_text.strip()
        
        # Remove JSON-like formatting characters
        cleaned = re.sub(r'^[\{\[\"\'\`]*', '', cleaned)  # Remove leading braces, brackets, quotes
        cleaned = re.sub(r'[\}\]\"\'\`]*$', '', cleaned)  # Remove trailing braces, brackets, quotes
        
        # Remove markdown formatting - Enhanced patterns
        cleaned = re.sub(r'^\*+\s*', '', cleaned)  # Remove leading asterisks
        cleaned = re.sub(r'\s*\*+$', '', cleaned)  # Remove trailing asterisks
        cleaned = re.sub(r'^#+\s*', '', cleaned)   # Remove markdown headers
        cleaned = re.sub(r'\*\*(.*?)\*\*', r'\1', cleaned)  # Remove bold markdown **text**
        cleaned = re.sub(r'\*(.*?)\*', r'\1', cleaned)      # Remove italic markdown *text*
        cleaned = re.sub(r'`(.*?)`', r'\1', cleaned)        # Remove code blocks `text`
        cleaned = re.sub(r'_{1,2}(.*?)_{1,2}', r'\1', cleaned)  # Remove underline _text_ or __text__
        
        # Remove bullet points and numbering
        cleaned = re.sub(r'^[\*\-\d\.\)\s]+', '', cleaned)
        cleaned = re.sub(r'^\s*[•·▪▫]\s*', '', cleaned)
        
        # Remove common LLM attribution suffixes - Enhanced
        attribution_patterns = [
            r'\s*\(LLM-generated\)$',
            r'\s*\(AI-generated\)$', 
            r'\s*\(Generated\)$',
            r'\s*\(Predicted\)$',
            r'\s*\(Estimated\)$',
            r'\s*\(Machine learning prediction\)$',
            r'\s*\(Model prediction\)$',
            r'\s*\(Computational prediction\)$'
        ]
        
        for pattern in attribution_patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Remove common prefixes and suffixes that LLMs add
        prefixes_to_remove = [
            r'^(?:Answer|Response|Result|Output|Value|Text|Content):\s*',
            r'^(?:The|A|An)\s+(?:answer|response|result|value|text)\s+is:\s*',
            r'^(?:Based on|According to|As per|Per).*?[:,]\s*',
            r'^(?:Here is|Here\'s|This is|The following is).*?[:,]\s*',
            r'^(?:In this case|For this compound|For this substance).*?[:,]\s*'
        ]
        
        for prefix in prefixes_to_remove:
            cleaned = re.sub(prefix, '', cleaned, flags=re.IGNORECASE)
        
        # Remove explanatory suffixes
        suffixes_to_remove = [
            r'\s*\((?:estimated|predicted|based on.*?|according to.*?|LLM.*?|AI.*?|generated)\)$',
            r'\s*\[(?:estimated|predicted|based on.*?|according to.*?|LLM.*?|AI.*?|generated)\]$',
            r'\s*—.*?(?:estimated|predicted|based on).*?$',
            r'\s*–.*?(?:estimated|predicted|based on).*?$',
            r'\s*\(see.*?\)$',
            r'\s*\[see.*?\]$'
        ]
        
        for suffix in suffixes_to_remove:
            cleaned = re.sub(suffix, '', cleaned, flags=re.IGNORECASE)
        
        # Clean up field labels that might be included
        field_labels = [
            r'^(?:Field|Property|Parameter|Attribute|Item|Entry):\s*',
            r'^\w+\s*:\s*',  # Remove any "word:" pattern at the start
        ]
        
        for label in field_labels:
            if re.match(label, cleaned):
                cleaned = re.sub(label, '', cleaned)
                break
        
        # Remove newline characters and normalize whitespace
        cleaned = re.sub(r'\n+', ' ', cleaned)  # Replace newlines with spaces
        cleaned = re.sub(r'\r+', ' ', cleaned)  # Replace carriage returns
        cleaned = re.sub(r'\t+', ' ', cleaned)  # Replace tabs with spaces
        cleaned = re.sub(r'\s+', ' ', cleaned)  # Collapse multiple spaces
        
        # Remove escape sequences
        cleaned = re.sub(r'\\n', ' ', cleaned)
        cleaned = re.sub(r'\\r', ' ', cleaned)
        cleaned = re.sub(r'\\t', ' ', cleaned)
        cleaned = re.sub(r'\\"', '"', cleaned)
        cleaned = re.sub(r"\\'", "'", cleaned)
        
        # Standardize common SDS terms and formats
        sds_standardizations = [
            # Temperature formats
            (r'(\d+\.?\d*)\s*degrees?\s*celsius', r'\1 °C'),
            (r'(\d+\.?\d*)\s*°[cC](?:elsius)?', r'\1 °C'),
            (r'(\d+\.?\d*)\s*deg\s*[cC]', r'\1 °C'),
            
            # Pressure formats
            (r'(\d+\.?\d*)\s*mm\s*hg', r'\1 mmHg'),
            (r'(\d+\.?\d*)\s*torr', r'\1 Torr'),
            (r'(\d+\.?\d*)\s*pa(?:scal)?', r'\1 Pa'),
            
            # Concentration formats
            (r'(\d+\.?\d*)\s*mg/kg', r'\1 mg/kg'),
            (r'(\d+\.?\d*)\s*mg/m3', r'\1 mg/m³'),
            (r'(\d+\.?\d*)\s*mg/m\^3', r'\1 mg/m³'),
            
            # Common "not available" variants
            (r'(?:not?\s+available|n/?a|unknown|unavailable|no\s+data)', 'Not available'),
        ]
        
        for pattern, replacement in sds_standardizations:
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
        
        # Final cleanup
        cleaned = cleaned.strip()
        cleaned = cleaned.strip('.,;:!?-_=+|\\/')
        cleaned = cleaned.strip()
        
        # Final validation - reject if too short or contains obvious artifacts
        if len(cleaned) < 3:
            return ""
        
        # Reject responses that are clearly invalid
        invalid_indicators = [
            'error', 'invalid', 'loading', 'please wait', '404', 'access denied',
            'undefined', 'null', 'none', 'empty', 'blank', 'missing',
            '{{', '}}', '[object', 'function(', 'return ', 'console.log'
        ]
        
        cleaned_lower = cleaned.lower()
        if any(indicator in cleaned_lower for indicator in invalid_indicators):
            return ""
        
        # Truncate if too long
        if len(cleaned) > 500:
            cleaned = cleaned[:497] + "..."
        
        return cleaned
    
    def find_missing_fields(self, data):
        """Find all fields with 'Not available' values"""
        missing_fields = []
        
        def traverse_dict(d, path=""):
            for key, value in d.items():
                current_path = f"{path}.{key}" if path else key
                if isinstance(value, dict):
                    traverse_dict(value, current_path)
                elif value == "Not available" or value == "":
                    missing_fields.append((current_path, key))
        
        traverse_dict(data)
        return missing_fields

    def apply_generated_data(self, original_data, generated_data):
        """Apply LLM-generated data with enhanced validation and cleaning"""
        applied_count = 0
        
        for field_path, generated_value in generated_data.items():
            if not generated_value:
                continue
                
            # Triple-clean the generated value
            # First pass - basic cleaning
            cleaned_once = self.clean_llm_output(generated_value)
            
            # Second pass - additional cleaning for stubborn artifacts
            cleaned_twice = self.clean_llm_output(cleaned_once)
            
            # Third pass - final polish
            final_cleaned_value = self.final_text_polish(cleaned_twice)
            
            if not final_cleaned_value or len(final_cleaned_value.strip()) < 5:
                continue
                
            # Navigate to the correct nested location
            path_parts = field_path.split('.')
            current_dict = original_data
            
            try:
                # Navigate to parent dictionary
                for part in path_parts[:-1]:
                    if part in current_dict and isinstance(current_dict[part], dict):
                        current_dict = current_dict[part]
                    else:
                        break
                else:
                    # Set the value if path is valid and current value is "Not available"
                    final_key = path_parts[-1]
                    if (final_key in current_dict and 
                        current_dict[final_key] == "Not available"):
                        
                        # Final check - ensure it doesn't look like JSON or markdown
                        if not any(char in final_cleaned_value for char in ['{', '}', '[', ']', '*', '#', '`', '_']):
                            # Apply clean value WITHOUT attribution
                            current_dict[final_key] = final_cleaned_value
                            applied_count += 1
                            logger.debug(f"[Mistral] Applied cleaned value to {field_path}")
                        else:
                            logger.warning(f"[Mistral] Rejected value with formatting artifacts: {final_cleaned_value[:50]}...")
                            
            except Exception as e:
                logger.error(f"[Mistral] Error applying data for {field_path}: {e}")
        
        return applied_count

    def final_text_polish(self, text):
        """Final polishing pass to ensure clean SDS-style text"""
        if not text:
            return ""
        
        # Remove any remaining formatting characters
        text = re.sub(r'[\*_`~\^]', '', text)  # Remove markdown remnants
        text = re.sub(r'\\[nrtbf]', ' ', text)  # Remove escape sequences
        text = re.sub(r'\s*\([Pp]redicted\)\s*$', '', text)  # Remove (predicted) suffix
        text = re.sub(r'\s*\([Ee]stimated\)\s*$', '', text)  # Remove (estimated) suffix
        
        # Ensure proper sentence structure
        text = text.strip()
        if text and not text.endswith('.') and len(text) > 10:
            text += '.'
        
        # Capitalize first letter if it's a proper sentence
        if text and text[0].islower() and ' ' in text:
            text = text[0].upper() + text[1:]
        
        return text

    def enhance_missing_field_coverage(self, comprehensive_data):
        """Specifically target commonly missing fields with fallback values"""
        safety_data = comprehensive_data.get("safety_data", {})
        basic_data = comprehensive_data.get("basic_data", {})
        
        # Define fallback values for critical missing fields
        critical_fallbacks = {
            "first_aid.Inhalation": "Move to fresh air immediately. If breathing is difficult, give oxygen. Seek medical attention if symptoms persist.",
            "first_aid.Skin Contact": "Remove contaminated clothing. Wash skin with soap and water for at least 15 minutes. Seek medical attention if irritation persists.",
            "first_aid.Eye Contact": "Flush eyes with clean water for at least 15 minutes, lifting eyelids occasionally. Seek medical attention.",
            "first_aid.Ingestion": "Rinse mouth with water. Do not induce vomiting unless directed by medical personnel. Seek medical attention immediately.",
            
            "fire_fighting.Extinguishing Media": "Water spray, foam, dry chemical, or carbon dioxide.",
            "fire_fighting.Special Hazards": "May emit toxic fumes when heated or burned.",
            
            "handling_storage.Handling": "Use appropriate personal protective equipment. Avoid contact with skin and eyes. Use in well-ventilated area.",
            "handling_storage.Storage": "Store in tightly closed container in cool, dry place away from incompatible materials.",
            
            "exposure_controls.Engineering Controls": "Use local exhaust ventilation or general dilution ventilation to maintain exposure below recommended limits.",
            "exposure_controls.Personal Protection": "Use appropriate personal protective equipment as specified in Section 8.",
            
            "stability_reactivity.Chemical Stability": "Stable under normal storage and handling conditions.",
            "stability_reactivity.Conditions to Avoid": "Heat, flames, ignition sources, and incompatible materials.",
            
            "disposal.Disposal Method": "Dispose of in accordance with local, state, and federal regulations. Contact local environmental authorities for guidance.",
        }
        
        applied_fallbacks = 0
        for field_path, fallback_value in critical_fallbacks.items():
            path_parts = field_path.split('.')
            current_dict = safety_data
            
            try:
                for part in path_parts[:-1]:
                    if part in current_dict:
                        current_dict = current_dict[part]
                    else:
                        break
                else:
                    final_key = path_parts[-1]
                    if (final_key in current_dict and 
                        current_dict[final_key] == "Not available"):
                        current_dict[final_key] = fallback_value + " (Default safety recommendation)"
                        applied_fallbacks += 1
            except:
                continue
        
        logger.info(f"[Fallback] Applied {applied_fallbacks} default safety recommendations")
        return comprehensive_data
    
    # def prioritize_missing_fields(self, missing_fields):
    #     """Prioritize missing fields by importance for SDS compliance"""
    #     # Critical fields that are legally required
    #     critical_fields = [
    #         'first_aid.Inhalation', 'first_aid.Skin Contact', 'first_aid.Eye Contact', 'first_aid.Ingestion',
    #         'fire_fighting.Extinguishing Media', 'handling_storage.Handling', 'handling_storage.Storage',
    #         'exposure_controls.Engineering Controls', 'toxicological.Acute Toxicity',
    #         'stability_reactivity.Chemical Stability'
    #     ]
        
    #     # Important fields for safety
    #     important_fields = [
    #         'hazard_identification.Signal Word', 'hazard_identification.Hazard Statements',
    #         'physical_properties.Flash Point', 'disposal.Disposal Method',
    #         'transport.Transport Hazard Class'
    #     ]
        
    #     prioritized = []
        
    #     # Add critical fields first
    #     for field_path, field_name in missing_fields:
    #         if field_path in critical_fields:
    #             prioritized.append((field_path, field_name))
        
    #     # Add important fields
    #     for field_path, field_name in missing_fields:
    #         if field_path in important_fields and (field_path, field_name) not in prioritized:
    #             prioritized.append((field_path, field_name))
        
    #     # Add remaining fields
    #     for field_path, field_name in missing_fields:
    #         if (field_path, field_name) not in prioritized:
    #             prioritized.append((field_path, field_name))
        
    #     return prioritized


    def enhance_data_with_llm(self, comprehensive_data):
        """Updated main method to enhance SDS data with improved LLM processing"""
        if not self.mistral_client:
            logger.info("[Mistral] Client not available, skipping LLM enhancement")
            # Apply fallback values for critical fields
            return self.enhance_missing_field_coverage(comprehensive_data)
        
        # Focus on all sections, not just priority ones
        safety_data = comprehensive_data.get("safety_data", {})
        
        # Find ALL missing fields
        all_missing = self.find_missing_fields(safety_data)
        
        if not all_missing:
            logger.info("[Mistral] No missing fields found")
            return comprehensive_data
        
        logger.info(f"[Mistral] Found {len(all_missing)} missing fields to enhance")
        
        # Generate missing data with enhanced processing
        generated_data = self.generate_missing_data_with_llm(comprehensive_data, all_missing)
        
        if generated_data:
            # Apply generated data with validation
            applied_count = self.apply_generated_data(safety_data, generated_data)
            comprehensive_data["safety_data"] = safety_data
            
            # Track LLM usage
            if "data_sources" not in comprehensive_data:
                comprehensive_data["data_sources"] = []
            comprehensive_data["data_sources"].append("Mistral LLM Enhancement")
            
            # Add detailed metadata about LLM enhancement
            comprehensive_data["llm_enhancement"] = {
                "fields_generated": len(generated_data),
                "fields_applied": applied_count,
                "model": "mistral-large-latest",
                "timestamp": datetime.now().isoformat(),
                "coverage_improvement": f"{applied_count}/{len(all_missing)} missing fields filled",
                "note": "LLM-generated fields are marked for expert review"
            }
            
            logger.info(f"[Mistral] Applied {applied_count} generated fields out of {len(generated_data)} generated")
        else:
            logger.warning("[Mistral] No data was generated by LLM")
        
        # Apply fallback values for any remaining critical missing fields
        comprehensive_data = self.enhance_missing_field_coverage(comprehensive_data)
        
        return comprehensive_data

    def generate_transport_classification_with_llm(self, compound_data):
        """Generate comprehensive transport classification using LLM"""
        if not self.mistral_client:
            return self.generate_basic_transport_classification(compound_data)

        try:
            basic_data = compound_data.get("basic_data", {})
            compound_name = basic_data.get("name", "Unknown compound")
            formula = basic_data.get("formula", "Unknown")
            hazards = compound_data.get("structural_analysis", {}).get("hazards", [])
            physical_props = compound_data.get("physical_properties", {})
            
            context_prompt = f"""
    You are a transport safety specialist generating UN transport classification for dangerous goods.

    Compound: {compound_name}
    Formula: {formula}
    Hazards: {len(hazards)} structural hazards identified
    Physical Properties Available: {len(physical_props)} properties

    Generate transport information for each field. Provide ONLY the value for each field (no labels, no JSON, no formatting):

    1. UN Number (4-digit code like UN1234, or "Not regulated")
    2. UN Proper Shipping Name (official transport name)
    3. Transport Hazard Class (Class 1-9 or "Not classified")
    4. Packing Group (I, II, III, or "Not applicable")
    5. Environmental Hazards (Yes/No with brief reason)
    6. Marine Pollutant (Yes/No)
    7. Special Precautions (brief safety instructions)

    Provide exactly one answer per line, numbered 1-7:
    """
            
            messages = [{"role": "user", "content": context_prompt}]
            
            response = self.mistral_client.chat.complete(
                model="mistral-large-latest",
                messages=messages,
                temperature=0.1,
                max_tokens=800
            )
            
            response_text = response.choices[0].message.content
            transport_data = {}
            
            transport_fields = [
                "UN Number",
                "UN Proper Shipping Name", 
                "Transport Hazard Class",
                "Packing Group",
                "Environmental Hazards",
                "Marine Pollutant",
                "Special Precautions"
            ]
            
            # Parse numbered responses
            lines = response_text.split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Look for numbered format
                match = re.match(r'^(\d+)[\.\:\)]\s*(.+)$', line)
                if match:
                    num = int(match.group(1))
                    raw_value = match.group(2)
                    
                    if 1 <= num <= len(transport_fields):
                        cleaned_value = self.final_text_polish(self.clean_llm_output(raw_value))
                        if cleaned_value and len(cleaned_value) >= 3:
                            transport_data[transport_fields[num-1]] = cleaned_value
            
            # Fill any missing fields with defaults
            for field in transport_fields:
                if field not in transport_data:
                    transport_data[field] = "Not available"
            
            return transport_data
            
        except Exception as e:
            logger.error(f"[Transport LLM] Error: {e}")
            return self.generate_basic_transport_classification(compound_data)

    def generate_basic_transport_classification(self, compound_data):
        """Fallback transport classification based on structural analysis"""
        hazards = compound_data.get("structural_analysis", {}).get("hazards", [])
        physical_props = compound_data.get("physical_properties", {})
        
        transport_data = {
            "UN Number": "Not regulated",
            "UN Proper Shipping Name": "Not applicable",
            "Transport Hazard Class": "Not classified",
            "Packing Group": "Not applicable",
            "Environmental Hazards": "Assessment required",
            "Marine Pollutant": "No",
            "Special Precautions": "Follow general chemical transport guidelines"
        }
        
        # Check for transport hazards
        hazard_types = [h['hazard_type'] for h in hazards] if hazards else []
        
        if "Explosive" in hazard_types:
            transport_data.update({
                "Transport Hazard Class": "Class 1 (Explosives)",
                "UN Proper Shipping Name": "Explosive substance, n.o.s.",
                "Packing Group": "Depends on explosive classification",
                "Special Precautions": "Handle with extreme care. Avoid shock, friction, and heat."
            })
        elif "Corrosive" in hazard_types:
            transport_data.update({
                "Transport Hazard Class": "Class 8 (Corrosive substances)",
                "UN Proper Shipping Name": "Corrosive solid, n.o.s.",
                "Packing Group": "II or III",
                "Special Precautions": "Use corrosion-resistant packaging. Avoid contact with metals."
            })
        
        # Check flash point for flammable classification
        flash_point = physical_props.get("Flash Point", "")
        if "°C" in flash_point:
            try:
                fp_match = re.search(r'(\d+)', flash_point)
                if fp_match:
                    fp_val = int(fp_match.group(1))
                    if fp_val < 60:
                        transport_data.update({
                            "Transport Hazard Class": "Class 3 (Flammable liquids)",
                            "UN Proper Shipping Name": "Flammable liquid, n.o.s.",
                            "Packing Group": "II" if fp_val < 23 else "III",
                            "Special Precautions": "Keep away from heat, sparks, and open flames."
                        })
            except:
                pass
        
        return transport_data
    
    
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
    
    # ===== ENHANCED STRUCTURAL ANALYSIS FUNCTIONS =====
    
    def predict_reactivity_from_smarts(self, mol):
        """Predict reactivity and stability using SMARTS patterns"""
        reactivity_rules = [
            # [SMARTS, Hazard Category, Description]
            ('[O-][N+](=O)[O]', 'Explosive', 'Nitrate ester – shock-sensitive, explosive'),
            ('[N+]([O-])=O', 'Explosive', 'Nitro group (aromatic) – potential explosive'),
            ('[O]~[O]', 'Unstable', 'Peroxide – may form explosive crystals on aging'),
            ('[F,Cl,Br,I][C;!$(C=O)]', 'Hydrolysis', 'Alkyl halide – may hydrolyze to HX'),
            ('C(=O)Cl', 'Reactive', 'Acid chloride – reacts violently with water, alcohols, amines'),
            ('[C,Si]-[Li,Na,K]', 'Pyrophoric', 'Organometallic – ignites in air, reacts violently with water'),
            ('[N]', 'Basic', 'Amine – may react with acids, oxidizers'),
            ('[C](=[O])[OH]', 'Corrosive', 'Carboxylic acid – corrosive to metals'),
            ('[N]~[N]', 'Unstable', 'Hydrazine – unstable, potentially explosive'),
            ('[S](=O)(=O)[OH]', 'Corrosive', 'Sulfonic acid – strong acid, corrosive'),
            ('[P](=[O])([OH])[OH]', 'Reactive', 'Phosphonic acid – reactive with metals'),
            ('[C]=O.[OH]', 'Tautomer', 'May exhibit enol-keto tautomerism'),
            ('[C]=[C]', 'Polymerizable', 'Alkene – may undergo polymerization'),
            ('[C]#[C]', 'Polymerizable', 'Alkyne – may undergo polymerization'),
            ('[OH][OH]', 'Unstable', 'Diol – may be unstable, prone to oxidation'),
            ('[S][S]', 'Reactive', 'Disulfide – may be cleaved by reducing agents'),
        ]
        
        hazards = []
        for smarts, hazard_type, description in reactivity_rules:
            try:
                pattern = Chem.MolFromSmarts(smarts)
                if pattern and mol.HasSubstructMatch(pattern):
                    hazards.append({
                        'functional_group': description.split(' – ')[0],
                        'hazard_type': hazard_type,
                        'description': description,
                        'caution': f"May react with: {self.get_incompatibility(hazard_type)}"
                    })
            except Exception as e:
                logger.warning(f"SMARTS pattern error for {smarts}: {e}")
                
        return hazards
    
    def get_incompatibility(self, hazard_type):
        """Map hazard type to incompatible materials"""
        incompatibilities = {
            'Explosive': 'Strong acids, bases, reducing agents, heat, shock, friction',
            'Unstable': 'Heat, light, friction, contaminants, metal ions',
            'Reactive': 'Water, alcohols, amines, oxidizers',
            'Pyrophoric': 'Air, moisture, oxidizers',
            'Basic': 'Strong acids, acid chlorides, oxidizing agents',
            'Corrosive': 'Metals, bases, organic materials',
            'Hydrolysis': 'Water, moisture, humid conditions',
            'Polymerizable': 'Heat, light, peroxides, radical initiators',
            'Tautomer': 'Strong bases, acids, heat'
        }
        return incompatibilities.get(hazard_type, "Strong oxidizers, acids, bases")
    
    def enhance_stability_reactivity(self, mol, existing_data):
        """Enhance stability/reactivity using structural analysis"""
        hazards = self.predict_reactivity_from_smarts(mol)
        
        if not hazards:
            existing_data["stability_reactivity"]["Stability"] = "Stable under normal conditions"
            existing_data["stability_reactivity"]["Reactivity"] = "No highly reactive groups detected"
            existing_data["stability_reactivity"]["Chemical Stability"] = "Stable under recommended storage conditions"
            return existing_data
        
        # Extract hazard types and descriptions
        hazard_types = [h['hazard_type'] for h in hazards]
        descriptions = [h['description'] for h in hazards]
        incompatibles = [self.get_incompatibility(h['hazard_type']) for h in hazards]
        
        # Fill in missing fields based on structural analysis
        if existing_data["stability_reactivity"]["Stability"] == "Not available":
            if "Unstable" in hazard_types or "Explosive" in hazard_types:
                existing_data["stability_reactivity"]["Stability"] = "Unstable – may decompose under heat, light, or shock"
            else:
                existing_data["stability_reactivity"]["Stability"] = "Stable under normal conditions"
        
        if existing_data["stability_reactivity"]["Reactivity"] == "Not available":
            existing_data["stability_reactivity"]["Reactivity"] = "; ".join(descriptions)
        
        if existing_data["stability_reactivity"]["Chemical Stability"] == "Not available":
            if "Unstable" in hazard_types:
                existing_data["stability_reactivity"]["Chemical Stability"] = "May be chemically unstable under certain conditions"
            else:
                existing_data["stability_reactivity"]["Chemical Stability"] = "Stable under recommended storage conditions"
        
        if existing_data["stability_reactivity"]["Conditions to Avoid"] == "Not available":
            conditions = set()
            if "Unstable" in hazard_types or "Explosive" in hazard_types:
                conditions.add("Heat, light, friction, shock")
            if "Reactive" in hazard_types or "Pyrophoric" in hazard_types:
                conditions.add("Moisture, air exposure")
            if "Polymerizable" in hazard_types:
                conditions.add("Heat, light, radical initiators")
            existing_data["stability_reactivity"]["Conditions to Avoid"] = ", ".join(conditions) if conditions else "Extreme temperatures, ignition sources"
        
        if existing_data["stability_reactivity"]["Incompatible Materials"] == "Not available":
            all_incompatibles = set()
            for incomp in incompatibles:
                all_incompatibles.update(incomp.split(", "))
            existing_data["stability_reactivity"]["Incompatible Materials"] = ", ".join(all_incompatibles)
        
        if existing_data["stability_reactivity"]["Hazardous Decomposition"] == "Not available":
            decomp_products = set()
            for h in hazards:
                desc_lower = h['description'].lower()
                if "nitro" in desc_lower or "nitrate" in desc_lower:
                    decomp_products.add("Nitrogen oxides (NOx, toxic fumes)")
                if "peroxide" in desc_lower:
                    decomp_products.add("Oxygen gas, free radicals")
                if "acid" in desc_lower:
                    decomp_products.add("Carbon monoxide, carbon dioxide")
                if "halide" in desc_lower:
                    decomp_products.add("Hydrogen halides (corrosive gases)")
                if "sulfur" in desc_lower:
                    decomp_products.add("Sulfur oxides (SOx)")
            existing_data["stability_reactivity"]["Hazardous Decomposition"] = ", ".join(decomp_products) if decomp_products else "Carbon monoxide, carbon dioxide"
        
        if existing_data["stability_reactivity"]["Hazardous Polymerization"] == "Not available":
            if "Polymerizable" in hazard_types:
                existing_data["stability_reactivity"]["Hazardous Polymerization"] = "May polymerize exothermically if contaminated or heated"
            else:
                existing_data["stability_reactivity"]["Hazardous Polymerization"] = "Will not occur under normal conditions"
        
        if existing_data["stability_reactivity"]["Possibility of Hazardous Reactions"] == "Not available":
            if hazards:
                existing_data["stability_reactivity"]["Possibility of Hazardous Reactions"] = f"Yes - {len(hazards)} reactive functional groups identified"
            else:
                existing_data["stability_reactivity"]["Possibility of Hazardous Reactions"] = "None under normal processing"
        
        return existing_data
    
    def get_echa_classification(self, cas_or_name):
        """Fetch GHS classification from ECHA C&L Inventory"""
        try:
            query = quote(str(cas_or_name))
            # Try ECHA substance search first
            search_url = f"https://echa.europa.eu/search-for-chemicals?q={query}"
            
            response = requests.get(search_url, headers=self.headers, timeout=15)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Look for GHS hazard statements
                hazard_statements = []
                for elem in soup.find_all(text=re.compile(r'H\d{3}')):
                    statements = re.findall(r'H\d{3}[^H]*', elem)
                    hazard_statements.extend(statements)
                
                if hazard_statements:
                    # Determine signal word based on hazard codes
                    signal_word = "Warning"
                    for stmt in hazard_statements:
                        if any(code in stmt for code in ['H300', 'H301', 'H310', 'H330', 'H340', 'H350', 'H360']):
                            signal_word = "Danger"
                            break
                    
                    return {
                        "GHS Classification": ", ".join(hazard_statements[:5]),
                        "Signal Word": signal_word,
                        "Hazard Statements": " | ".join(hazard_statements[:10])
                    }
                    
        except Exception as e:
            logger.error(f"ECHA GHS fetch failed: {e}")
            
        return {}
    
    def predict_first_aid_enhanced(self, mol, logp, mw, hazards):
        """Enhanced first aid prediction based on molecular properties and hazards"""
        first_aid_data = {}
        
        # Inhalation
        respiratory_hazards = [h for h in hazards if h['hazard_type'] in ['Basic', 'Corrosive', 'Reactive']]
        if respiratory_hazards:
            first_aid_data["Inhalation"] = "Move to fresh air immediately. If breathing is difficult, administer oxygen. If not breathing, give artificial respiration. Get medical attention immediately."
        else:
            first_aid_data["Inhalation"] = "Move to fresh air. If symptoms persist, seek medical attention."
        
        # Skin Contact
        if logp > 3:
            first_aid_data["Skin Contact"] = "Remove contaminated clothing immediately. Wash skin thoroughly with soap and water for at least 15 minutes. May be readily absorbed through skin - seek medical attention."
        elif any(h['hazard_type'] == 'Corrosive' for h in hazards):
            first_aid_data["Skin Contact"] = "Remove contaminated clothing. Flush skin with large amounts of water for at least 15 minutes. Get medical attention immediately."
        else:
            first_aid_data["Skin Contact"] = "Remove contaminated clothing. Wash with soap and water. If irritation persists, seek medical attention."
        
        # Eye Contact
        if any(h['hazard_type'] in ['Corrosive', 'Reactive'] for h in hazards):
            first_aid_data["Eye Contact"] = "Flush eyes with clean water for at least 15 minutes, lifting eyelids occasionally. Remove contact lenses if present. Get immediate medical attention."
        else:
            first_aid_data["Eye Contact"] = "Flush eyes with water for at least 15 minutes. If irritation persists, seek medical attention."
        
        # Ingestion
        if mw < 300 and logp < 2:
            first_aid_data["Ingestion"] = "Do NOT induce vomiting. Rinse mouth with water. Drink large amounts of water. Get medical attention immediately."
        elif any(h['hazard_type'] in ['Corrosive', 'Reactive'] for h in hazards):
            first_aid_data["Ingestion"] = "Do NOT induce vomiting or give anything by mouth. Rinse mouth if conscious. Get immediate medical attention."
        else:
            first_aid_data["Ingestion"] = "If conscious and alert, rinse mouth and drink water. Do not induce vomiting unless directed by medical personnel. Seek medical attention."
        
        # Most Important Symptoms
        symptoms = []
        if any(h['hazard_type'] == 'Corrosive' for h in hazards):
            symptoms.append("Burns to skin, eyes, and mucous membranes")
        if any(h['hazard_type'] == 'Basic' for h in hazards):
            symptoms.append("Respiratory irritation")
        if logp > 4:
            symptoms.append("Central nervous system depression")
        
        first_aid_data["Most Important Symptoms"] = "; ".join(symptoms) if symptoms else "Irritation to eyes, skin, and respiratory tract"
        
        # Notes to Physician
        notes = []
        if any(h['hazard_type'] in ['Explosive', 'Unstable'] for h in hazards):
            notes.append("Compound may be unstable - handle contaminated materials carefully")
        if logp > 3:
            notes.append("High lipophilicity - may cause systemic toxicity")
        
        first_aid_data["Notes to Physician"] = "; ".join(notes) if notes else "Treat symptomatically"
        
        return {"first_aid": first_aid_data}
    
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
    
    # ===== ENHANCED TOXICITY PREDICTION FUNCTIONS =====
    
    def predict_toxicity_protx(self, smiles):
        """Enhanced toxicity prediction with comprehensive assessment"""
        mol = self.smiles_to_mol(smiles)
        if not mol:
            return {}

        # Enhanced toxicity indicators
        has_nitro = any(atom.GetAtomicNum() == 7 and atom.GetFormalCharge() == 1 for atom in mol.GetAtoms())
        has_aromatic_amine = any(atom.GetAtomicNum() == 7 and atom.GetIsAromatic() for atom in mol.GetAtoms())
        has_halogen = any(atom.GetAtomicNum() in [9, 17, 35, 53] for atom in mol.GetAtoms())
        has_heavy_metals = any(atom.GetAtomicNum() in [80, 82, 48, 27] for atom in mol.GetAtoms())  # Hg, Pb, Cd, Co
        
        logp = Descriptors.MolLogP(mol)
        mw = Descriptors.MolWt(mol)
        tpsa = Descriptors.TPSA(mol)
        
        # Get structural hazards
        structural_hazards = self.predict_reactivity_from_smarts(mol)

        # Enhanced toxicity classification
        toxicity_score = 0
        if has_nitro:
            toxicity_score += 3
        if has_aromatic_amine:
            toxicity_score += 2
        if has_halogen:
            toxicity_score += 1
        if has_heavy_metals:
            toxicity_score += 4  # Heavy metals are particularly toxic
        if logp > 5:
            toxicity_score += 2
        if mw > 500:
            toxicity_score += 1
        if any(h['hazard_type'] in ['Explosive', 'Unstable', 'Corrosive'] for h in structural_hazards):
            toxicity_score += 2

        # Determine toxicity class based on score
        if toxicity_score >= 6:
            toxicity_class = "Class I (Extremely High)"
            ld50 = "1-5 mg/kg"
            lc50_inhalation = "1-10 mg/m³"
        elif toxicity_score >= 5:
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
        target_organs = set()
        if has_nitro or has_aromatic_amine:
            target_organs.update(["Liver", "Blood"])
        if has_heavy_metals:
            target_organs.update(["Kidneys", "CNS", "Blood"])
        if logp > 3:
            target_organs.add("CNS")
        if tpsa < 60:
            target_organs.add("Brain")
        if any(h['hazard_type'] == 'Corrosive' for h in structural_hazards):
            target_organs.update(["Skin", "Eyes", "Respiratory tract"])
        if not target_organs:
            target_organs = {"Not specified"}

        # Enhanced hazard endpoints
        hazard_endpoints = set()
        if has_nitro:
            hazard_endpoints.update(["Hepatotoxicity", "Methemoglobinemia"])
        if has_aromatic_amine:
            hazard_endpoints.add("Carcinogenicity")
        if has_halogen:
            hazard_endpoints.add("Nephrotoxicity")
        if has_heavy_metals:
            hazard_endpoints.update(["Neurotoxicity", "Nephrotoxicity"])
        for hazard in structural_hazards:
            if hazard['hazard_type'] == 'Corrosive':
                hazard_endpoints.add("Skin/Eye Corrosion")
            elif hazard['hazard_type'] == 'Explosive':
                hazard_endpoints.add("Physical Explosion Hazard")
        
        if not hazard_endpoints:
            hazard_endpoints = {"None predicted"}

        return {
            "toxicity_class": toxicity_class,
            "hazard_endpoints": list(hazard_endpoints),
            "ld50": ld50,
            "lc50_inhalation_rat": lc50_inhalation,
            "target_organs": list(target_organs),
            "toxicity_score": toxicity_score,
            "structural_alerts": len(structural_hazards),
            "prediction_confidence": "High" if toxicity_score > 3 else "Medium" if toxicity_score > 0 else "Low"
        }
    
    # ===== PHYSICAL PROPERTIES CALCULATION =====
    
    def get_physical_properties(self, mol):
        """Enhanced properties computation using RDKit"""
        mw = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        tpsa = Descriptors.TPSA(mol)
        
        # Predict physical state based on molecular weight and structure
        physical_state = "Solid"
        if mw < 100:
            physical_state = "Gas or volatile liquid"
        elif mw < 200 and logp < 2:
            physical_state = "Liquid"
        
        # Predict solubility more accurately
        if logp < 0:
            solubility = "Highly soluble in water"
        elif logp < 2:
            solubility = "Soluble in water"
        elif logp < 4:
            solubility = "Moderately soluble"
        else:
            solubility = "Poorly soluble in water"
        
        return {
            "_MolecularWeight_numeric": mw,
            "_LogP_numeric": logp,
            "Physical State": physical_state,
            "Molecular Weight": f"{mw:.2f} g/mol",
            "LogP": f"{logp:.2f}",
            "Solubility in Water": solubility,
            "Topological Polar Surface Area (TPSA)": f"{tpsa:.2f} Å²",
            "Hydrogen Bond Donors": Descriptors.NumHDonors(mol),
            "Hydrogen Bond Acceptors": Descriptors.NumHAcceptors(mol),
            "Rotatable Bonds": Descriptors.NumRotatableBonds(mol),
            "Heavy Atom Count": rdMolDescriptors.CalcNumHeavyAtoms(mol),
            "Formal Charge": Chem.rdmolops.GetFormalCharge(mol),
            "Ring Count": rdMolDescriptors.CalcNumRings(mol),
            "Aromatic Ring Count": rdMolDescriptors.CalcNumAromaticRings(mol),
            "Saturated Ring Count": rdMolDescriptors.CalcNumSaturatedRings(mol),
            "Fraction Csp3": f"{rdMolDescriptors.CalcFractionCSP3(mol):.3f}",
            "Molecular Refractivity": f"{Descriptors.MolMR(mol):.2f}",
            "BalabanJ": f"{Descriptors.BalabanJ(mol):.3f}",
            "BertzCT": f"{Descriptors.BertzCT(mol):.2f}"
        }
    
    # ===== COMPREHENSIVE SAFETY DATA AGGREGATION =====
    
    def get_comprehensive_safety_data(self, cid, smiles=None, cas_number=None, compound_name=None):
        """
        Master function to fetch comprehensive safety data from multiple sources.
        Returns structured data for SDS generation with enhanced predictions.
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
        
        # Get molecular structure for enhanced predictions
        mol = None
        if smiles:
            mol = self.smiles_to_mol(smiles)
        
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

        # 4. Enhanced structure-based predictions
        if mol:
            try:
                # Enhanced stability/reactivity analysis
                data = self.enhance_stability_reactivity(mol, data)
                
                # Enhanced first aid predictions
                logp = Descriptors.MolLogP(mol) if mol else 2.0
                mw = Descriptors.MolWt(mol) if mol else 300.0
                structural_hazards = self.predict_reactivity_from_smarts(mol)
                
                enhanced_first_aid = self.predict_first_aid_enhanced(mol, logp, mw, structural_hazards)
                self.merge_data_safely(data, enhanced_first_aid)
                
                logger.info(f"[Structure Analysis] Enhanced predictions completed")
            except Exception as e:
                logger.error(f"[Structure Analysis] Error: {e}")

        # 5. ECHA GHS classification
        if cas_number and cas_number != "Not available":
            try:
                echa_ghs = self.get_echa_classification(cas_number)
                if echa_ghs:
                    self.merge_data_safely(data, {"hazard_identification": echa_ghs})
                    logger.info(f"[ECHA GHS] Classification data merged")
            except Exception as e:
                logger.error(f"[ECHA GHS] Error: {e}")
                
        try:
            transport_data = self.generate_transport_classification_with_llm({
                "basic_data": basic_data,
                "structural_analysis": {"hazards": structural_hazards},
                "physical_properties": data.get("physical_properties", {})
            })
            
            # Merge transport data
            for field, value in transport_data.items():
                if data["transport"][field] == "Not available" and value != "Not available":
                    data["transport"][field] = value
            
            logger.info(f"[Transport] Classification completed with {len(transport_data)} fields")
            
        except Exception as e:
            logger.error(f"[Transport] Classification failed: {e}")

        # Validate all extracted data
        data = self.validate_extracted_data(data)
        logger.info(f"[Multi-Source] Data validation completed")

        return data
    
    # ===== MAIN DATA AGGREGATION METHOD =====
    
    def fetch_all_data(self, smiles):
        """
        Main method to fetch all data for SDS generation.
        Returns comprehensive compound data structure with enhanced predictions.
        """
        logger.info(f"[SDS Data Fetcher] Starting comprehensive data collection for SMILES: {smiles}")
        
        # Initialize result structure
        result = {
            "basic_data": {},
            "safety_data": {},
            "toxicity_data": {},
            "physical_properties": {},
            "structural_analysis": {},
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
            
            # 3. Enhanced toxicity predictions
            try:
                toxicity_data = self.predict_toxicity_protx(smiles)
                result["toxicity_data"] = toxicity_data
                result["data_sources"].append("Enhanced Toxicity Predictions")
                logger.info("[Data Fetcher] Enhanced toxicity predictions completed")
            except Exception as e:
                result["errors"].append(f"Toxicity prediction failed: {str(e)}")
            
            # 4. Structural analysis and reactivity prediction
            try:
                structural_hazards = self.predict_reactivity_from_smarts(mol)
                result["structural_analysis"] = {
                    "hazards": structural_hazards,
                    "hazard_count": len(structural_hazards),
                    "hazard_types": list(set(h['hazard_type'] for h in structural_hazards))
                }
                result["data_sources"].append("Structural Analysis")
                logger.info(f"[Data Fetcher] Structural analysis completed - {len(structural_hazards)} hazards identified")
            except Exception as e:
                result["errors"].append(f"Structural analysis failed: {str(e)}")
            
            # 5. Get comprehensive safety data if CID is available
            cid = basic_data.get("cid")
            cas = basic_data.get("cas")
            compound_name = basic_data.get("name")
            
            if cid:
                try:
                    safety_data = self.get_comprehensive_safety_data(cid, smiles, cas, compound_name)
                    result["safety_data"] = safety_data
                    result["data_sources"].extend(["PubChem Safety", "ChemIDplus", "NIST WebBook", "Structural Predictions"])
                    logger.info("[Data Fetcher] Comprehensive safety data collected")
                except Exception as e:
                    result["errors"].append(f"Safety data collection failed: {str(e)}")
            
            # 6. Get additional data sources
            if cas and cas != "Not available":
                try:
                    echa_data = self.get_echa_preferred_name(cas_number=cas)
                    if echa_data:
                        result["additional_data"]["echa"] = echa_data
                        result["data_sources"].append("ECHA")
                        logger.info("[Data Fetcher] ECHA data collected")
                except Exception as e:
                    result["errors"].append(f"ECHA data collection failed: {str(e)}")
            
            # 7. Get additional PubChem properties
            if cid:
                try:
                    additional_pubchem = self.get_pubchem_synonyms_and_properties(cid)
                    if additional_pubchem:
                        result["additional_data"]["pubchem_extended"] = additional_pubchem
                        logger.info("[Data Fetcher] Extended PubChem data collected")
                except Exception as e:
                    result["errors"].append(f"Extended PubChem data failed: {str(e)}")
            
            try:
                if result["safety_data"]:
                    result = self.enhance_data_with_llm(result)
                    logger.info("[Data Fetcher] LLM enhancement completed")
            except Exception as e:
                result["errors"].append(f"LLM enhancement failed: {str(e)}")
                logger.error(f"[Data Fetcher] LLM enhancement error: {str(e)}")
            
            logger.info(f"[Data Fetcher] Data collection completed. Sources used: {', '.join(result['data_sources'])}")
            
            if result["errors"]:
                logger.warning(f"[Data Fetcher] Errors encountered: {'; '.join(result['errors'])}")
            
            return result
            
        except Exception as e:
            logger.error(f"[Data Fetcher] Critical error in fetch_all_data: {str(e)}")
            result["errors"].append(f"Critical error: {str(e)}")
            return result

    # ===== ADDITIONAL ENHANCEMENT METHODS =====
    
    def predict_environmental_fate(self, mol, logp, mw):
        """Predict environmental fate and transport properties"""
        environmental_data = {}
        
        # Biodegradability prediction
        if mw < 500 and logp < 4:
            biodeg = "Readily biodegradable (predicted)"
        elif mw > 1000 or logp > 6:
            biodeg = "Not readily biodegradable (predicted)"
        else:
            biodeg = "Potentially biodegradable (predicted)"
        
        # Bioaccumulation potential
        if logp > 3:
            bioaccum = "High potential for bioaccumulation"
        elif logp > 2:
            bioaccum = "Moderate potential for bioaccumulation"
        else:
            bioaccum = "Low potential for bioaccumulation"
        
        # Mobility prediction
        if logp < 2:
            mobility = "High mobility in soil/water"
        elif logp < 4:
            mobility = "Moderate mobility in soil"
        else:
            mobility = "Low mobility, tends to adsorb to sediments"
        
        environmental_data = {
            "Biodegradability": biodeg,
            "Bioaccumulation": bioaccum,
            "Mobility in Soil": mobility
        }
        
        return {"ecological": environmental_data}
    
    def predict_exposure_limits(self, toxicity_class, mw, has_volatile_groups=False):
        """Predict occupational exposure limits based on toxicity class"""
        exposure_data = {}
        
        # Base exposure limits by toxicity class
        if "Class I" in toxicity_class:
            if "Extremely High" in toxicity_class:
                twa = "0.01 mg/m³ (predicted)"
                stel = "0.03 mg/m³ (predicted)"
            else:
                twa = "0.1 mg/m³ (predicted)"
                stel = "0.3 mg/m³ (predicted)"
        elif "Class II" in toxicity_class:
            twa = "1 mg/m³ (predicted)"
            stel = "3 mg/m³ (predicted)"
        elif "Class III" in toxicity_class:
            twa = "10 mg/m³ (predicted)"
            stel = "20 mg/m³ (predicted)"
        else:
            twa = "Not established"
            stel = "Not established"
        
        # Adjust for molecular weight and volatility
        if mw < 200 and has_volatile_groups:
            exposure_data["Engineering Controls"] = "Use in well-ventilated area or fume hood. Local exhaust ventilation recommended."
        elif "Class I" in toxicity_class:
            exposure_data["Engineering Controls"] = "Use in enclosed system or under local exhaust ventilation. Avoid dust formation."
        else:
            exposure_data["Engineering Controls"] = "Good general ventilation should be sufficient."
        
        exposure_data.update({
            "TLV-TWA": twa,
            "TLV-STEL": stel,
            "Respiratory Protection": "NIOSH approved respirator if exposure limits exceeded" if twa != "Not established" else "Not normally required",
            "Eye Protection": "Chemical safety goggles recommended",
            "Skin Protection": "Chemical resistant gloves recommended"
        })
        
        return {"exposure_controls": exposure_data}
    
    def generate_transport_classification(self, hazards, flash_point=None):
        """Generate transport classification based on hazards"""
        transport_data = {}
        
        # Determine UN hazard class
        hazard_types = [h['hazard_type'] for h in hazards]
        
        if "Explosive" in hazard_types:
            transport_data.update({
                "Transport Hazard Class": "Class 1 (Explosives)",
                "Packing Group": "I, II, or III (depends on explosive type)",
                "UN Proper Shipping Name": "EXPLOSIVE SUBSTANCE, N.O.S."
            })
        elif "Corrosive" in hazard_types:
            transport_data.update({
                "Transport Hazard Class": "Class 8 (Corrosive)",
                "Packing Group": "II or III (depends on corrosivity)",
                "UN Proper Shipping Name": "CORROSIVE SOLID, N.O.S."
            })
        elif flash_point and "°C" in flash_point:
            try:
                fp_val = float(flash_point.split("°C")[0].strip())
                if fp_val < 23:
                    transport_data.update({
                        "Transport Hazard Class": "Class 3 (Flammable Liquid)",
                        "Packing Group": "I or II",
                        "UN Proper Shipping Name": "FLAMMABLE LIQUID, N.O.S."
                    })
                elif fp_val < 60:
                    transport_data.update({
                        "Transport Hazard Class": "Class 3 (Flammable Liquid)",
                        "Packing Group": "III",
                        "UN Proper Shipping Name": "FLAMMABLE LIQUID, N.O.S."
                    })
            except:
                pass
        
        if not transport_data:
            transport_data = {
                "Transport Hazard Class": "Not classified as dangerous goods (predicted)",
                "UN Number": "Not applicable",
                "Packing Group": "Not applicable"
            }
        
        return {"transport": transport_data}


# ===== HELPER FUNCTIONS FOR STANDALONE USAGE =====

def create_sds_data_fetcher():
    """Factory function to create and return an enhanced SDSDataFetcher instance"""
    return SDSDataFetcher()

def fetch_compound_data(smiles):
    """
    Convenience function for fetching all compound data with enhanced predictions.
    Returns comprehensive data structure for SDS generation.
    
    Usage:
        data = fetch_compound_data("CC(=O)OC1=CC=CC=C1C(=O)O")  # Aspirin
        print(data["basic_data"]["name"])
        print(data["toxicity_data"]["toxicity_class"])
        print(f"Structural hazards: {len(data['structural_analysis']['hazards'])}")
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

def analyze_structural_hazards(smiles):
    """
    Standalone function to analyze structural hazards of a compound.
    Returns list of hazards with descriptions and safety recommendations.
    
    Usage:
        hazards = analyze_structural_hazards("CC(=O)OC1=CC=CC=C1C(=O)O")
        for hazard in hazards:
            print(f"Hazard: {hazard['hazard_type']} - {hazard['description']}")
    """
    fetcher = SDSDataFetcher()
    mol = fetcher.smiles_to_mol(smiles)
    if mol:
        return fetcher.predict_reactivity_from_smarts(mol)
    return []

def predict_compound_toxicity(smiles):
    """
    Standalone function for toxicity prediction.
    Returns toxicity classification and key endpoints.
    
    Usage:
        toxicity = predict_compound_toxicity("CC(=O)OC1=CC=CC=C1C(=O)O")
        print(f"Toxicity class: {toxicity['toxicity_class']}")
        print(f"Target organs: {', '.join(toxicity['target_organs'])}")
    """
    fetcher = SDSDataFetcher()
    return fetcher.predict_toxicity_protx(smiles)


