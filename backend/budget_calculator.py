"""
AluQuote AI - Budget Calculator Module (The "30-Year Expert Engineer" Brain) - ENHANCED
Applies industry heuristics and expert logic for accurate aluminum fabrication budgeting

REGRA FUNDAMENTAL: Quantidades do DXF PREVALECEM sobre quantidades do PDF
- Se há ficheiro DXF, as quantidades vêm do DXF
- O PDF serve para correlacionar ESPECIFICAÇÕES (materiais, acabamentos, tolerâncias)
- Só se não houver DXF é que as quantidades do PDF são usadas
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
import math
import re

# Import FLYSTEEL cost database
try:
    from cost_database import cost_db, CostDatabase, SteelProfile, CladdingItem
    HAS_COST_DB = True
except ImportError:
    HAS_COST_DB = False
    cost_db = None


@dataclass
class PricingParameters:
    """Global pricing parameters"""
    lme_price_usd_kg: float = 2.35
    lme_hedging_buffer_pct: float = 5.0
    billet_premium_usd_kg: float = 0.45
    alloy_6063_premium_pct: float = 0.0
    alloy_6060_premium_pct: float = 2.0
    alloy_6082_premium_pct: float = 8.0
    anodizing_natural_eur_m2: float = 12.0
    anodizing_colored_eur_m2: float = 18.0
    powder_coating_standard_eur_m2: float = 15.0
    powder_coating_qualicoat_eur_m2: float = 22.0
    powder_coating_seaside_eur_m2: float = 35.0
    labor_rate_eur_hr: float = 35.0
    cutting_time_mins: float = 2.0
    machining_time_per_hole_mins: float = 5.0
    assembly_time_per_component_mins: float = 8.0
    base_waste_factor_pct: float = 8.0
    complexity_waste_factor_pct: float = 4.0
    overhead_factor_pct: float = 15.0
    profit_margin_pct: float = 20.0
    eur_to_usd: float = 1.08
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "lme_price_usd_kg": self.lme_price_usd_kg,
            "lme_hedging_buffer_pct": self.lme_hedging_buffer_pct,
            "billet_premium_usd_kg": self.billet_premium_usd_kg,
            "surface_treatments": {
                "anodizing_natural": self.anodizing_natural_eur_m2,
                "anodizing_colored": self.anodizing_colored_eur_m2,
                "powder_coating_standard": self.powder_coating_standard_eur_m2,
                "powder_coating_qualicoat": self.powder_coating_qualicoat_eur_m2,
                "powder_coating_seaside": self.powder_coating_seaside_eur_m2
            },
            "labor_rate_eur_hr": self.labor_rate_eur_hr,
            "waste_factor_pct": self.base_waste_factor_pct,
            "overhead_factor_pct": self.overhead_factor_pct,
            "profit_margin_pct": self.profit_margin_pct
        }


@dataclass
class BudgetLineItem:
    """Single line item in the budget"""
    line_id: int
    reference: str
    description: str
    quantity: int
    
    # Source tracking
    quantity_source: str = ""  # 'dxf', 'pdf', 'estimated'
    specs_source: str = ""  # 'dxf', 'pdf', 'both'
    
    # Geometry data (from DXF)
    profile_id: Optional[str] = None
    perimeter_mm: float = 0.0
    area_mm2: float = 0.0
    length_mm: float = 0.0
    weight_kg: float = 0.0
    complexity_score: float = 1.0
    holes_count: int = 0
    entity_type: str = ""
    
    # Specifications (from PDF or DXF)
    material: Optional[str] = None
    finish: Optional[str] = None
    thickness_mm: Optional[float] = None
    
    # Calculated costs
    raw_material_cost: float = 0.0
    transformation_cost: float = 0.0
    surface_treatment_cost: float = 0.0
    labor_cost: float = 0.0
    accessories_cost: float = 0.0
    
    # Totals
    unit_cost: float = 0.0
    total_cost: float = 0.0
    
    # Metadata
    correlation_confidence: float = 0.0
    correlation_method: str = ""
    notes: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "line_id": self.line_id,
            "reference": self.reference,
            "description": self.description,
            "quantity": self.quantity,
            "quantity_source": self.quantity_source,
            "specs_source": self.specs_source,
            "profile_id": self.profile_id,
            "geometry": {
                "perimeter_mm": round(self.perimeter_mm, 2),
                "area_mm2": round(self.area_mm2, 2),
                "length_mm": round(self.length_mm, 2),
                "weight_kg": round(self.weight_kg, 4),
                "complexity_score": round(self.complexity_score, 2),
                "holes_count": self.holes_count,
                "entity_type": self.entity_type
            },
            "specifications": {
                "material": self.material,
                "finish": self.finish,
                "thickness_mm": self.thickness_mm
            },
            "costs": {
                "raw_material": round(self.raw_material_cost, 2),
                "transformation": round(self.transformation_cost, 2),
                "surface_treatment": round(self.surface_treatment_cost, 2),
                "labor": round(self.labor_cost, 2),
                "accessories": round(self.accessories_cost, 2)
            },
            "unit_cost": round(self.unit_cost, 2),
            "total_cost": round(self.total_cost, 2),
            "correlation_confidence": round(self.correlation_confidence, 2),
            "correlation_method": self.correlation_method,
            "notes": self.notes
        }


@dataclass
class BudgetSummary:
    """Complete budget summary"""
    project_name: str
    created_at: str
    
    # Source info
    has_dxf: bool = False
    has_pdf: bool = False
    dxf_files_count: int = 0
    pdf_files_count: int = 0
    
    # Totals
    total_profiles: int = 0
    total_quantity: int = 0
    total_weight_kg: float = 0.0
    total_length_mm: float = 0.0
    
    # Cost breakdown
    raw_material_total: float = 0.0
    transformation_total: float = 0.0
    surface_treatment_total: float = 0.0
    labor_total: float = 0.0
    accessories_total: float = 0.0
    waste_cost: float = 0.0
    overhead_cost: float = 0.0
    subtotal: float = 0.0
    profit_margin: float = 0.0
    total_quote: float = 0.0
    
    # Metadata
    waste_percentage_applied: float = 0.0
    average_complexity: float = 0.0
    estimated_production_hours: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_name": self.project_name,
            "created_at": self.created_at,
            "sources": {
                "has_dxf": self.has_dxf,
                "has_pdf": self.has_pdf,
                "dxf_files_count": self.dxf_files_count,
                "pdf_files_count": self.pdf_files_count
            },
            "quantities": {
                "total_profiles": self.total_profiles,
                "total_quantity": self.total_quantity,
                "total_weight_kg": round(self.total_weight_kg, 2),
                "total_length_mm": round(self.total_length_mm, 2)
            },
            "cost_breakdown": {
                "raw_material": round(self.raw_material_total, 2),
                "transformation": round(self.transformation_total, 2),
                "surface_treatment": round(self.surface_treatment_total, 2),
                "labor": round(self.labor_total, 2),
                "accessories": round(self.accessories_total, 2),
                "waste_allowance": round(self.waste_cost, 2),
                "overhead": round(self.overhead_cost, 2)
            },
            "totals": {
                "subtotal": round(self.subtotal, 2),
                "profit_margin": round(self.profit_margin, 2),
                "total_quote": round(self.total_quote, 2)
            },
            "metrics": {
                "waste_percentage": round(self.waste_percentage_applied, 1),
                "average_complexity": round(self.average_complexity, 2),
                "production_hours": round(self.estimated_production_hours, 1)
            }
        }


class BudgetCalculator:
    """
    The "30-Year Expert Engineer" Logic Engine - ENHANCED
    
    REGRAS DE PREVALÊNCIA:
    1. Se há DXF: quantidades e geometrias VÊM DO DXF
    2. PDF serve para: especificações (materiais, acabamentos, tolerâncias)
    3. Correlação: referências do PDF são mapeadas para perfis do DXF
    4. Se não há DXF: usa quantidades do PDF como fallback
    """
    
    ALUMINUM_DENSITY_KG_M3 = 2700
    
    def __init__(self, params: Optional[PricingParameters] = None):
        self.params = params or PricingParameters()
        self.line_items: List[BudgetLineItem] = []
        self.summary: Optional[BudgetSummary] = None
        self.correlation_log: List[Dict] = []
        
    def correlate_data(self, dxf_data: Dict[str, Any], 
                       pdf_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Cross-reference DXF geometry with PDF specifications
        DXF quantities ALWAYS prevail over PDF quantities
        """
        correlations = []
        has_dxf = dxf_data.get('success', False) and len(dxf_data.get('profiles', [])) > 0
        has_pdf = pdf_data.get('success', False) and len(pdf_data.get('bom_items', [])) > 0
        
        dxf_profiles = dxf_data.get('profiles', [])
        dxf_materials = dxf_data.get('material_quantities', [])
        pdf_items = pdf_data.get('bom_items', [])
        pdf_constraints = pdf_data.get('constraints', [])
        
        # Build lookup indexes
        pdf_lookup = self._build_pdf_lookup(pdf_items)
        constraints_by_type = self._index_constraints(pdf_constraints)
        
        if has_dxf:
            # PRIMARY PATH: DXF exists - use DXF quantities
            self.correlation_log.append({
                "action": "using_dxf_as_primary",
                "dxf_profiles": len(dxf_profiles),
                "dxf_materials": len(dxf_materials)
            })
            
            # Process each DXF profile
            for profile in dxf_profiles:
                correlation = self._correlate_profile_with_pdf(profile, pdf_lookup, constraints_by_type)
                correlations.append(correlation)
            
            # Also process material quantities from blocks
            for material_qty in dxf_materials:
                if material_qty.get('source') == 'block_count':
                    correlation = self._create_material_correlation(material_qty, pdf_lookup, constraints_by_type)
                    if correlation:
                        correlations.append(correlation)
        
        elif has_pdf:
            # FALLBACK PATH: No DXF - use PDF quantities
            self.correlation_log.append({
                "action": "using_pdf_as_fallback",
                "pdf_items": len(pdf_items)
            })
            
            for pdf_item in pdf_items:
                correlation = {
                    "pdf_item": pdf_item,
                    "dxf_profile": None,
                    "correlation_confidence": 0.5,
                    "correlation_method": "pdf_only",
                    "quantity_source": "pdf"
                }
                correlations.append(correlation)
        
        # FALLBACK: If no correlations but we have constraints/dimensions, create estimated items
        if not correlations:
            correlations = self._create_fallback_correlations(pdf_data, dxf_data)
        
        return correlations
    
    def _create_fallback_correlations(self, pdf_data: Dict[str, Any], 
                                       dxf_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Create fallback correlations when no structured BOM items found.
        Uses constraints, dimensions, and any extracted data.
        """
        correlations = []
        
        self.correlation_log.append({
            "action": "creating_fallback_items",
            "reason": "no_structured_data_found"
        })
        
        # Try to create items from PDF constraints and dimensions
        pdf_constraints = pdf_data.get('constraints', [])
        pdf_dimensions = pdf_data.get('dimension_specs', [])
        pdf_materials = pdf_data.get('material_specs', [])
        
        # Group constraints by type to create meaningful items
        constraint_groups = {}
        for constraint in pdf_constraints:
            ctype = constraint.get('constraint_type', 'other')
            if ctype not in constraint_groups:
                constraint_groups[ctype] = []
            constraint_groups[ctype].append(constraint)
        
        # Create items from material grades found
        material_items = constraint_groups.get('material_grade', [])
        for i, mat in enumerate(material_items[:10]):  # Limit to 10
            correlations.append({
                "pdf_item": {
                    "reference": f"MAT-{i+1:02d}",
                    "description": f"Material: {mat.get('value', 'Alumínio')}",
                    "quantity": 1,
                    "notes": mat.get('context', '')[:100]
                },
                "dxf_profile": None,
                "correlation_confidence": 0.3,
                "correlation_method": "constraint_extraction",
                "quantity_source": "estimated",
                "specifications": {
                    "material": mat.get('value')
                }
            })
        
        # Create items from surface treatments found
        treatment_items = constraint_groups.get('surface_treatment', [])
        for i, treat in enumerate(treatment_items[:5]):  # Limit to 5
            correlations.append({
                "pdf_item": {
                    "reference": f"TRAT-{i+1:02d}",
                    "description": f"Tratamento: {treat.get('value', 'Lacagem')}",
                    "quantity": 1,
                    "notes": treat.get('context', '')[:100]
                },
                "dxf_profile": None,
                "correlation_confidence": 0.3,
                "correlation_method": "constraint_extraction",
                "quantity_source": "estimated",
                "specifications": {
                    "finish": treat.get('value')
                }
            })
        
        # Create items from dimension specs
        unique_dims = set()
        for dim in pdf_dimensions[:20]:
            dim_raw = dim.get('raw', '') or dim.get('dimensions', '')
            if dim_raw and dim_raw not in unique_dims:
                unique_dims.add(dim_raw)
                # Try to parse dimensions
                length = self._parse_dimension(dim_raw)
                if length and length > 50:  # Filter out very small values
                    correlations.append({
                        "pdf_item": {
                            "reference": f"DIM-{len(correlations)+1:02d}",
                            "description": f"Elemento {dim_raw}",
                            "quantity": 1,
                            "length_mm": length
                        },
                        "dxf_profile": None,
                        "correlation_confidence": 0.25,
                        "correlation_method": "dimension_extraction",
                        "quantity_source": "estimated"
                    })
        
        # If still no correlations, create a placeholder with summary info
        if not correlations:
            total_constraints = len(pdf_constraints)
            total_dims = len(pdf_dimensions)
            
            correlations.append({
                "pdf_item": {
                    "reference": "PROJ-01",
                    "description": f"Projeto (análise automática: {total_constraints} specs, {total_dims} dimensões)",
                    "quantity": 1,
                    "notes": "Dados extraídos de desenhos técnicos. Revisão manual recomendada."
                },
                "dxf_profile": None,
                "correlation_confidence": 0.1,
                "correlation_method": "placeholder",
                "quantity_source": "estimated"
            })
        
        return correlations
    
    def _parse_dimension(self, dim_str: str) -> Optional[float]:
        """Parse dimension string to get length in mm"""
        if not dim_str:
            return None
        
        # Try to find numeric values
        numbers = re.findall(r'(\d+(?:[.,]\d+)?)', str(dim_str))
        if numbers:
            try:
                # Return the largest number (likely the main dimension)
                values = [float(n.replace(',', '.')) for n in numbers]
                return max(values)
            except:
                pass
        return None
    
    def _build_pdf_lookup(self, pdf_items: List[Dict]) -> Dict[str, List[Dict]]:
        """Build lookup index from PDF items"""
        lookup = {
            'by_reference': {},
            'by_description': {},
            'all_items': pdf_items
        }
        
        for item in pdf_items:
            ref = item.get('reference', '').upper().strip()
            desc = item.get('description', '').lower().strip()
            
            if ref:
                # Index by various forms of reference
                lookup['by_reference'][ref] = item
                # Also try without separators
                ref_clean = re.sub(r'[\-_\s]', '', ref)
                lookup['by_reference'][ref_clean] = item
            
            if desc:
                # Index first 30 chars of description
                desc_key = desc[:30]
                lookup['by_description'][desc_key] = item
        
        return lookup
    
    def _index_constraints(self, constraints: List[Dict]) -> Dict[str, List[Dict]]:
        """Index constraints by type"""
        indexed = {}
        for c in constraints:
            ctype = c.get('constraint_type', 'other')
            if ctype not in indexed:
                indexed[ctype] = []
            indexed[ctype].append(c)
        return indexed
    
    def _correlate_profile_with_pdf(self, profile: Dict, pdf_lookup: Dict, 
                                    constraints: Dict) -> Dict[str, Any]:
        """Correlate a DXF profile with PDF items for specifications"""
        profile_id = profile.get('profile_id', '')
        layer = profile.get('layer', '')
        
        # Try to find matching PDF item
        matched_pdf = None
        confidence = 0.0
        method = "none"
        
        # Strategy 1: Match by layer name as reference
        layer_upper = layer.upper()
        if layer_upper in pdf_lookup.get('by_reference', {}):
            matched_pdf = pdf_lookup['by_reference'][layer_upper]
            confidence = 0.9
            method = "layer_to_reference"
        
        # Strategy 2: Match profile_id patterns
        if not matched_pdf:
            for ref, item in pdf_lookup.get('by_reference', {}).items():
                if ref in profile_id.upper() or profile_id.upper() in ref:
                    matched_pdf = item
                    confidence = 0.8
                    method = "profile_id_match"
                    break
        
        # Strategy 3: Search in all items for material hints
        if not matched_pdf and profile.get('material_hint'):
            material_hint = profile['material_hint'].lower()
            for item in pdf_lookup.get('all_items', []):
                item_desc = item.get('description', '').lower()
                if material_hint in item_desc:
                    matched_pdf = item
                    confidence = 0.6
                    method = "material_hint"
                    break
        
        # Extract specifications from matched PDF or constraints
        specs = self._extract_specifications(matched_pdf, constraints)
        
        return {
            "dxf_profile": profile,
            "pdf_item": matched_pdf,
            "correlation_confidence": confidence,
            "correlation_method": method,
            "quantity_source": "dxf",  # ALWAYS from DXF when DXF exists
            "specifications": specs
        }
    
    def _create_material_correlation(self, material_qty: Dict, pdf_lookup: Dict,
                                     constraints: Dict) -> Optional[Dict]:
        """Create correlation from material quantity (blocks)"""
        ref = material_qty.get('profile_reference', '')
        
        matched_pdf = pdf_lookup.get('by_reference', {}).get(ref.upper())
        specs = self._extract_specifications(matched_pdf, constraints)
        
        return {
            "dxf_profile": None,
            "material_quantity": material_qty,
            "pdf_item": matched_pdf,
            "correlation_confidence": 0.7 if matched_pdf else 0.5,
            "correlation_method": "block_count",
            "quantity_source": "dxf",
            "specifications": specs
        }
    
    def _extract_specifications(self, pdf_item: Optional[Dict], 
                                constraints: Dict) -> Dict[str, Any]:
        """Extract specifications from PDF item and constraints"""
        specs = {
            "material": None,
            "finish": None,
            "thickness_mm": None,
            "certifications": [],
            "constraints": []
        }
        
        if pdf_item:
            specs["material"] = pdf_item.get('material')
            specs["finish"] = pdf_item.get('finish')
            specs["thickness_mm"] = pdf_item.get('thickness_mm')
        
        # Add from constraints
        if 'material_grade' in constraints and constraints['material_grade']:
            if not specs["material"]:
                specs["material"] = constraints['material_grade'][0].get('value')
        
        if 'surface_treatment' in constraints and constraints['surface_treatment']:
            if not specs["finish"]:
                specs["finish"] = constraints['surface_treatment'][0].get('value')
        
        if 'certification' in constraints:
            specs["certifications"] = [c.get('value') for c in constraints['certification']]
        
        # Collect all high-importance constraints
        for ctype, clist in constraints.items():
            for c in clist:
                if c.get('importance') == 'high':
                    specs["constraints"].append({
                        "type": ctype,
                        "value": c.get('value'),
                        "context": c.get('context', '')[:100]
                    })
        
        return specs
    
    def calculate_budget(self, dxf_data: Dict[str, Any], 
                        pdf_data: Dict[str, Any],
                        surface_treatment: str = "powder_coating_standard",
                        project_name: str = "Novo Orçamento") -> Dict[str, Any]:
        """
        Main budget calculation method
        REGRA: Quantidades DXF prevalecem sobre PDF
        """
        # Determine what data we have
        has_dxf = dxf_data.get('success', False) and len(dxf_data.get('profiles', [])) > 0
        has_pdf = pdf_data.get('success', False)
        
        # Correlate data sources
        correlations = self.correlate_data(dxf_data, pdf_data)
        
        # Reset line items
        self.line_items = []
        line_id = 0
        
        for correlation in correlations:
            line_id += 1
            
            dxf_profile = correlation.get('dxf_profile')
            material_qty = correlation.get('material_quantity')
            pdf_item = correlation.get('pdf_item')
            specs = correlation.get('specifications', {})
            quantity_source = correlation.get('quantity_source', 'estimated')
            
            # Determine quantity based on source priority
            if dxf_profile:
                # QUANTITY FROM DXF
                quantity = dxf_profile.get('quantity', 1)
                reference = dxf_profile.get('layer', '') or dxf_profile.get('profile_id', '')
                description = f"{dxf_profile.get('entity_type', 'Perfil')} - {dxf_profile.get('layer', '')}"
            elif material_qty:
                # QUANTITY FROM DXF BLOCKS
                quantity = material_qty.get('quantity', 1)
                reference = material_qty.get('profile_reference', '')
                description = material_qty.get('description', 'Bloco DXF')
            elif pdf_item:
                # FALLBACK: QUANTITY FROM PDF (only if no DXF)
                quantity = int(pdf_item.get('quantity', 1))
                reference = pdf_item.get('reference', '')
                description = pdf_item.get('description', '')
            else:
                continue
            
            # Create budget line
            line = BudgetLineItem(
                line_id=line_id,
                reference=reference,
                description=description,
                quantity=max(1, int(quantity)),
                quantity_source=quantity_source,
                specs_source="both" if pdf_item and dxf_profile else ("dxf" if dxf_profile else "pdf"),
                correlation_confidence=correlation.get('correlation_confidence', 0),
                correlation_method=correlation.get('correlation_method', ''),
                material=specs.get('material'),
                finish=specs.get('finish') or self._treatment_to_finish(surface_treatment),
                thickness_mm=specs.get('thickness_mm')
            )
            
            # Apply geometry from DXF if available
            if dxf_profile:
                line.profile_id = dxf_profile.get('profile_id')
                line.perimeter_mm = dxf_profile.get('perimeter_mm', 0)
                line.area_mm2 = dxf_profile.get('area_mm2', 0)
                line.length_mm = dxf_profile.get('length_mm', 0) or max(
                    dxf_profile.get('bounding_box', {}).get('width', 0),
                    dxf_profile.get('bounding_box', {}).get('height', 0)
                )
                line.weight_kg = dxf_profile.get('weight_kg', 0)
                line.complexity_score = dxf_profile.get('complexity_score', 1.0)
                line.entity_type = dxf_profile.get('entity_type', '')
                line.holes_count = len([f for f in dxf_profile.get('features', []) 
                                       if f.get('feature_type') == 'hole'])
            elif material_qty:
                line.perimeter_mm = material_qty.get('unit_length_mm', 0)
                line.area_mm2 = material_qty.get('unit_area_mm2', 0)
                line.length_mm = material_qty.get('unit_length_mm', 0)
            
            # Use length from PDF if DXF doesn't have it
            if line.length_mm == 0 and pdf_item:
                line.length_mm = pdf_item.get('length_mm') or 0
            
            # Calculate costs
            self._calculate_line_costs(line, surface_treatment)
            
            self.line_items.append(line)
        
        # Generate summary
        self._calculate_summary(project_name, has_dxf, has_pdf, dxf_data, pdf_data)
        
        return {
            "success": True,
            "line_items": [item.to_dict() for item in self.line_items],
            "summary": self.summary.to_dict() if self.summary else None,
            "parameters": self.params.to_dict(),
            "correlation_log": self.correlation_log,
            "data_sources": {
                "dxf_used": has_dxf,
                "pdf_used": has_pdf,
                "quantity_source": "dxf" if has_dxf else "pdf"
            }
        }
    
    def _treatment_to_finish(self, treatment: str) -> str:
        """Convert treatment code to readable finish name"""
        mapping = {
            "none": "Sem acabamento",
            "anodizing_natural": "Anodização natural",
            "anodizing_colored": "Anodização colorida",
            "powder_coating_standard": "Lacagem standard",
            "powder_coating_qualicoat": "Lacagem Qualicoat",
            "powder_coating_seaside": "Lacagem Seaside"
        }
        return mapping.get(treatment, treatment)
    
    def _try_calculate_from_cost_db(self, line: BudgetLineItem) -> bool:
        """
        Try to calculate costs using FLYSTEEL cost database.
        Returns True if successful, False to fall back to default calculation.
        """
        if not HAS_COST_DB or cost_db is None:
            return False
        
        # Extract profile designation from description or reference
        profile_name = None
        search_terms = [line.description, line.reference, line.profile_id or ""]
        
        # Common steel profile patterns
        profile_patterns = [
            r'(IPE\s*\d+)',
            r'(HEB\s*\d+)',
            r'(HEA\s*\d+)',
            r'(UPN\s*\d+)',
            r'(RHS\s*[\d]+[xX][\d]+[xX][\d]+)',
            r'(SHS\s*[\d]+[xX][\d]+[xX][\d]+)',
            r'(TUBO\s+RED[.\s]+[\d.]+[*xX][\d.]+)',
            r'(MADRE\s+[CZ]\s+[\d]+)',
            r'(OMEGA\s*\d+)',
            r'(CHAPA\s+PRETA\s+\d+MM)',
        ]
        
        for term in search_terms:
            if not term:
                continue
            term_upper = term.upper()
            for pattern in profile_patterns:
                match = re.search(pattern, term_upper)
                if match:
                    profile_name = match.group(1)
                    break
            if profile_name:
                break
        
        if not profile_name:
            return False
        
        # Try to find profile in database
        profile = cost_db.find_profile(profile_name)
        if not profile:
            return False
        
        # Calculate length in meters
        length_m = line.length_mm / 1000 if line.length_mm > 0 else 1.0
        
        # Calculate costs using the profile data
        cost_data = profile.calculate_cost(length_m)
        
        # Apply quantity
        qty = max(1, line.quantity)
        
        # Update line item with calculated values
        line.weight_kg = cost_data["weight_kg"]
        line.raw_material_cost = cost_data["cost_material"] * qty
        line.transformation_cost = cost_data["cost_fabrication"] * qty
        line.surface_treatment_cost = cost_data["cost_painting"] * qty
        line.labor_cost = (cost_data["cost_assembly"] + cost_data["cost_lifting"]) * qty
        line.accessories_cost = (cost_data["cost_consumables"] + cost_data["cost_transport"]) * qty
        
        # Calculate totals
        line.unit_cost = cost_data["total_cost"]
        line.total_cost = line.unit_cost * qty
        
        # Add note about source
        line.notes = f"Custos FLYSTEEL: {profile.designation}"
        
        return True
    
    def _try_calculate_cladding_from_cost_db(self, description: str, quantity: float, 
                                              unit: str) -> Optional[Dict[str, float]]:
        """
        Try to calculate cladding costs using FLYSTEEL cost database.
        Returns cost dict if successful, None otherwise.
        """
        if not HAS_COST_DB or cost_db is None:
            return None
        
        # Search patterns for cladding items
        cladding_patterns = [
            (r'painel.*fachada.*la.*rocha.*50', "PAINEL FACHADA LA ROCHA 50MM"),
            (r'painel.*fachada.*pir.*50', "PAINEL FACHADA PIR 50MM"),
            (r'painel.*fachada.*poliuretano.*30', "PAINEL FACHADA POLIURETANO 30MM"),
            (r'painel.*cobertura.*la.*rocha.*50', "PAINEL COBERTURA LA ROCHA 50MM"),
            (r'painel.*cobertura.*la.*rocha.*80', "PAINEL COBERTURA LA ROCHA 80MM"),
            (r'painel.*cobertura.*poliuretano.*30', "PAINEL COBERTURA POLIURETANO 30MM"),
            (r'caleira.*dupla', "CALEIRA DUPLA ISOLADA"),
            (r'caleira.*simples', "CALEIRA SIMPLES GALVANIZADA"),
            (r'claraboia.*1.0|claraboia.*1x1', "CLARABOIA FIXA 1.0X1.0"),
            (r'claraboia.*1.5|claraboia.*1,5', "CLARABOIA FIXA 1.5X1.5"),
            (r'area.*luz', "AREA DE LUZ"),
            (r'anticume', "ANTICUME"),
            (r'cume', "CUME"),
            (r'porta.*emergencia.*900|porta.*emergencia.*0.9', "PORTA EMERGENCIA 900X2150"),
            (r'porta.*emergencia.*1200|porta.*emergencia.*1.2', "PORTA EMERGENCIA 1200X2150"),
            (r'porta.*sectorial.*3|portao.*3', "PORTA SECTORIAL 3000X3000"),
            (r'porta.*sectorial.*4|portao.*4', "PORTA SECTORIAL 4000X4000"),
            (r'pintura.*intumescente.*r60|intumescente.*r60', "PINTURA INTUMESCENTE R60"),
            (r'pintura.*intumescente.*r30|intumescente.*r30', "PINTURA INTUMESCENTE R30"),
            (r'pintura.*intumescente.*r90|intumescente.*r90', "PINTURA INTUMESCENTE R90"),
            (r'contra.*fachada', "CONTRA FACHADA CHAPA SIMPLES"),
            (r'chapa.*simples.*fachada', "CHAPA SIMPLES FACHADA"),
            (r'remates', "REMATES FACHADA"),
        ]
        
        desc_lower = description.lower()
        item_name = None
        
        for pattern, name in cladding_patterns:
            if re.search(pattern, desc_lower):
                item_name = name
                break
        
        if not item_name:
            return None
        
        item = cost_db.find_cladding(item_name)
        if not item:
            return None
        
        cost_data = item.calculate_cost(quantity)
        return cost_data
    
    def _calculate_line_costs(self, line: BudgetLineItem, surface_treatment: str):
        """Calculate all costs for a single line item"""
        p = self.params
        
        # Try to use FLYSTEEL cost database for steel profiles
        if HAS_COST_DB and self._try_calculate_from_cost_db(line):
            return  # Cost calculated from database
        
        # 1. Raw Material Cost
        effective_lme = p.lme_price_usd_kg * (1 + p.lme_hedging_buffer_pct / 100)
        material_price_kg = (effective_lme + p.billet_premium_usd_kg) / p.eur_to_usd
        
        # Calculate weight if not provided
        if line.weight_kg <= 0 and line.area_mm2 > 0:
            thickness = line.thickness_mm or 2.0
            volume_mm3 = line.perimeter_mm * thickness * max(line.length_mm, 1000)
            line.weight_kg = (volume_mm3 / 1e9) * self.ALUMINUM_DENSITY_KG_M3
        elif line.weight_kg <= 0 and line.perimeter_mm > 0:
            # Estimate from perimeter
            thickness = line.thickness_mm or 2.0
            volume_mm3 = line.perimeter_mm * thickness * thickness
            line.weight_kg = (volume_mm3 / 1e9) * self.ALUMINUM_DENSITY_KG_M3
        elif line.weight_kg <= 0 and line.length_mm > 0:
            # Estimate from length (assume standard profile)
            # Typical aluminum profile: ~0.5 kg/m
            line.weight_kg = (line.length_mm / 1000) * 0.5
            line.perimeter_mm = line.length_mm * 0.1  # Rough estimate
        elif line.weight_kg <= 0:
            # Minimum fallback for items without geometry
            # Assume 1m standard profile (~0.5kg)
            line.weight_kg = 0.5
            line.length_mm = 1000
            line.perimeter_mm = 100
        
        line.raw_material_cost = line.weight_kg * material_price_kg * line.quantity
        
        # 2. Transformation Cost
        extrusion_rate = 1.50 * line.complexity_score
        line.transformation_cost = line.weight_kg * extrusion_rate * line.quantity
        
        # 3. Surface Treatment Cost
        treatment_rates = {
            "anodizing_natural": p.anodizing_natural_eur_m2,
            "anodizing_colored": p.anodizing_colored_eur_m2,
            "powder_coating_standard": p.powder_coating_standard_eur_m2,
            "powder_coating_qualicoat": p.powder_coating_qualicoat_eur_m2,
            "powder_coating_seaside": p.powder_coating_seaside_eur_m2,
            "none": 0.0
        }
        
        treatment_rate = treatment_rates.get(surface_treatment, p.powder_coating_standard_eur_m2)
        surface_area_m2 = (line.perimeter_mm * max(line.length_mm, 1000)) / 1e6
        line.surface_treatment_cost = surface_area_m2 * treatment_rate * line.quantity
        
        # 4. Labor Cost
        cutting_time = p.cutting_time_mins
        machining_time = line.holes_count * p.machining_time_per_hole_mins
        complexity_time = (line.complexity_score - 1) * 5
        assembly_time = p.assembly_time_per_component_mins
        
        total_labor_mins = (cutting_time + machining_time + complexity_time + assembly_time) * line.quantity
        line.labor_cost = (total_labor_mins / 60) * p.labor_rate_eur_hr
        
        # 5. Accessories Cost
        line.accessories_cost = line.raw_material_cost * 0.08
        
        # Calculate totals
        line.unit_cost = (
            line.raw_material_cost + 
            line.transformation_cost + 
            line.surface_treatment_cost + 
            line.labor_cost + 
            line.accessories_cost
        ) / max(line.quantity, 1)
        
        line.total_cost = line.unit_cost * line.quantity
    
    def _calculate_summary(self, project_name: str, has_dxf: bool, has_pdf: bool,
                          dxf_data: Dict, pdf_data: Dict):
        """Calculate budget summary"""
        p = self.params
        
        self.summary = BudgetSummary(
            project_name=project_name,
            created_at=datetime.now().isoformat(),
            has_dxf=has_dxf,
            has_pdf=has_pdf,
            dxf_files_count=1 if has_dxf else 0,
            pdf_files_count=1 if has_pdf else 0
        )
        
        # Aggregate line items
        self.summary.total_profiles = len(self.line_items)
        self.summary.total_quantity = sum(item.quantity for item in self.line_items)
        self.summary.total_weight_kg = sum(item.weight_kg * item.quantity for item in self.line_items)
        self.summary.total_length_mm = sum(item.length_mm * item.quantity for item in self.line_items)
        
        self.summary.raw_material_total = sum(item.raw_material_cost for item in self.line_items)
        self.summary.transformation_total = sum(item.transformation_cost for item in self.line_items)
        self.summary.surface_treatment_total = sum(item.surface_treatment_cost for item in self.line_items)
        self.summary.labor_total = sum(item.labor_cost for item in self.line_items)
        self.summary.accessories_total = sum(item.accessories_cost for item in self.line_items)
        
        # Average complexity
        if self.line_items:
            self.summary.average_complexity = sum(
                item.complexity_score for item in self.line_items
            ) / len(self.line_items)
        
        # Waste factor
        waste_pct = p.base_waste_factor_pct + (self.summary.average_complexity - 1) * p.complexity_waste_factor_pct
        self.summary.waste_percentage_applied = min(waste_pct, 20.0)
        self.summary.waste_cost = self.summary.raw_material_total * (self.summary.waste_percentage_applied / 100)
        
        # Subtotal
        direct_costs = (
            self.summary.raw_material_total +
            self.summary.transformation_total +
            self.summary.surface_treatment_total +
            self.summary.labor_total +
            self.summary.accessories_total +
            self.summary.waste_cost
        )
        
        # Overhead
        self.summary.overhead_cost = direct_costs * (p.overhead_factor_pct / 100)
        self.summary.subtotal = direct_costs + self.summary.overhead_cost
        
        # Profit margin
        self.summary.profit_margin = self.summary.subtotal * (p.profit_margin_pct / 100)
        self.summary.total_quote = self.summary.subtotal + self.summary.profit_margin
        
        # Production hours
        self.summary.estimated_production_hours = self.summary.labor_total / p.labor_rate_eur_hr
    
    def get_ai_recommendations(self) -> List[Dict[str, str]]:
        """Generate AI-powered recommendations"""
        recommendations = []
        
        if not self.summary:
            return recommendations
        
        # Material optimization
        if self.summary.waste_percentage_applied > 12:
            recommendations.append({
                "category": "Otimização de Material",
                "priority": "high",
                "suggestion": f"Fator de desperdício elevado ({self.summary.waste_percentage_applied:.1f}%) devido a perfis complexos. Considere otimização de corte ou padrões alternativos.",
                "potential_savings": f"€{self.summary.waste_cost * 0.3:.2f}"
            })
        
        # Labor efficiency
        avg_labor = self.summary.labor_total / max(self.summary.total_quantity, 1)
        if avg_labor > 15:
            recommendations.append({
                "category": "Eficiência de Mão-de-Obra",
                "priority": "medium",
                "suggestion": "Custo de mão-de-obra por unidade elevado. Considere automação CNC para operações repetitivas.",
                "potential_savings": f"€{self.summary.labor_total * 0.2:.2f}"
            })
        
        # LME Hedging
        recommendations.append({
            "category": "Proteção de Preço",
            "priority": "low",
            "suggestion": f"Buffer de hedging LME atual é {self.params.lme_hedging_buffer_pct}%. Considere contratos forward se o projeto exceder 3 meses.",
            "potential_savings": "Variável"
        })
        
        # Volume discount
        if self.summary.total_weight_kg > 1000:
            recommendations.append({
                "category": "Desconto de Volume",
                "priority": "medium",
                "suggestion": f"Volume de encomenda ({self.summary.total_weight_kg:.0f} kg) qualifica para preço de volume. Negocie com fornecedores desconto de 5-8%.",
                "potential_savings": f"€{self.summary.raw_material_total * 0.06:.2f}"
            })
        
        # Data quality
        low_confidence = len([i for i in self.line_items if i.correlation_confidence < 0.5])
        if low_confidence > 0:
            recommendations.append({
                "category": "Qualidade de Dados",
                "priority": "high",
                "suggestion": f"{low_confidence} itens têm baixa confiança de correlação. Revise manualmente as referências para maior precisão.",
                "potential_savings": "N/A"
            })
        
        return recommendations


def calculate_quick_estimate(weight_kg: float, complexity: str = "medium") -> Dict[str, float]:
    """Quick estimation without detailed geometry"""
    complexity_factors = {"low": 1.0, "medium": 1.5, "high": 2.0}
    factor = complexity_factors.get(complexity, 1.5)
    base_rate = 10.0 * factor
    
    return {
        "estimated_total": round(weight_kg * base_rate, 2),
        "price_per_kg": base_rate,
        "complexity_factor": factor
    }
