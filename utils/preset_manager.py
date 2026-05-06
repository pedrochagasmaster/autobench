"""Preset management and discovery.

This module handles loading, listing, and formatting preset configurations.
"""

import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

logger = logging.getLogger(__name__)


class PresetManager:
    """Manages preset configurations."""
    
    def __init__(self, preset_dir: Optional[Path] = None):
        """Initialize preset manager.
        
        Args:
            preset_dir: Directory containing preset files. 
                       Defaults to 'presets' in package directory.
        """
        if not YAML_AVAILABLE:
            logger.warning("PyYAML not available. Preset functionality will be limited.")
            logger.warning("Install with: pip install pyyaml")
        
        if preset_dir is None:
            # Default to presets/ directory next to this file
            preset_dir = Path(__file__).parent.parent / 'presets'
        
        self.preset_dir = Path(preset_dir)
        self._presets: Dict[str, Dict[str, Any]] = {}
        self._load_presets()
    
    def _load_presets(self) -> None:
        """Load all preset files from preset directory."""
        if not YAML_AVAILABLE:
            logger.debug("Skipping preset loading (PyYAML not available)")
            return
        
        if not self.preset_dir.exists():
            logger.warning(f"Preset directory not found: {self.preset_dir}")
            logger.info(f"Create directory and add preset files: {self.preset_dir}")
            return
        
        preset_files = list(self.preset_dir.glob('*.yaml')) + list(self.preset_dir.glob('*.yml'))
        
        if not preset_files:
            logger.warning(f"No preset files found in: {self.preset_dir}")
            return
        
        for preset_file in preset_files:
            try:
                with open(preset_file, 'r') as f:
                    preset_data = yaml.safe_load(f)
                
                if preset_data is None:
                    logger.warning(f"Empty preset file: {preset_file.name}")
                    continue

                from .validators import ConfigValidator

                errors = ConfigValidator.validate(preset_data)
                if errors:
                    logger.error(
                        "Skipping invalid preset %s: %s",
                        preset_file.name,
                        "; ".join(errors),
                    )
                    continue
                
                preset_name = preset_file.stem
                self._presets[preset_name] = preset_data
                logger.debug(f"Loaded preset: {preset_name}")
            
            except yaml.YAMLError as e:
                logger.error(f"Invalid YAML in preset {preset_file.name}: {e}")
            except Exception as e:
                logger.error(f"Failed to load preset {preset_file.name}: {e}")
        
        logger.info(f"Loaded {len(self._presets)} preset(s) from {self.preset_dir}")
    
    def list_presets(self) -> List[str]:
        """Get list of available preset names.
        
        Returns:
            Sorted list of preset names
        """
        return sorted(self._presets.keys())
    
    def get_preset(self, name: str) -> Optional[Dict[str, Any]]:
        """Get preset configuration by name.
        
        Args:
            name: Preset name (without .yaml extension)
            
        Returns:
            Preset configuration dictionary, or None if not found
        """
        return self._presets.get(name)

    def load_preset(self, name: str) -> Optional[Dict[str, Any]]:
        """Backward-compatible alias used by shared preset workflows."""
        return self.get_preset(name)
    
    def preset_exists(self, name: str) -> bool:
        """Check if preset exists.
        
        Args:
            name: Preset name
            
        Returns:
            True if preset exists
        """
        return name in self._presets
    
    def get_preset_description(self, name: str) -> Optional[str]:
        """Get preset description.
        
        Args:
            name: Preset name
            
        Returns:
            Description string, or None if preset not found
        """
        preset = self.get_preset(name)
        return preset.get('description') if preset else None
    
    def format_preset_list(self) -> str:
        """Format preset list for display.
        
        Returns:
            Formatted string with preset list
        """
        if not YAML_AVAILABLE:
            return ("PyYAML is not installed. Install with: pip install pyyaml\n"
                   "Presets require YAML support.")
        
        if not self._presets:
            return (f"No presets available.\n\n"
                   f"Create preset files in: {self.preset_dir}\n"
                   f"Use: benchmark config generate <file> to create a template.")
        
        lines = ["Available Presets:", "=" * 80, ""]
        
        for name in self.list_presets():
            preset = self._presets[name]
            desc = preset.get('description', 'No description')
            posture = preset.get('compliance_posture', 'MISSING')
            
            # Format preset info
            lines.append(f"  {name}")
            lines.append(f"    {desc}")
            lines.append(f"    Compliance Posture: {posture}")
            
            # Show key optimization settings if available
            if 'optimization' in preset:
                opt = preset['optimization']
                if 'bounds' in opt and 'max_weight' in opt['bounds']:
                    lines.append(f"    Max Weight: {opt['bounds']['max_weight']}")
                if 'linear_programming' in opt and 'tolerance' in opt['linear_programming']:
                    lines.append(f"    Tolerance: {opt['linear_programming']['tolerance']}pp")
            
            lines.append("")
        
        lines.append("=" * 80)
        lines.append("Use: benchmark config show <preset> to see full details")
        
        return "\n".join(lines)
    
    def format_preset_detail(self, name: str) -> str:
        """Format preset details for display.
        
        Args:
            name: Preset name
            
        Returns:
            Formatted string with preset details
        """
        if not YAML_AVAILABLE:
            return "PyYAML is not installed. Install with: pip install pyyaml"
        
        preset = self.get_preset(name)
        if not preset:
            available = self.list_presets()
            if available:
                return (f"Preset '{name}' not found.\n\n"
                       f"Available presets: {', '.join(available)}\n"
                       f"Use: benchmark config list")
            else:
                return (f"Preset '{name}' not found.\n\n"
                       f"No presets available in: {self.preset_dir}")
        
        lines = [
            "=" * 80,
            f"Preset: {name}",
            "=" * 80,
        ]
        
        # Add metadata
        if 'version' in preset:
            lines.append(f"Version: {preset['version']}")
        if 'description' in preset:
            lines.append(f"Description: {preset['description']}")
        if 'compliance_posture' in preset:
            lines.append(f"Compliance Posture: {preset['compliance_posture']}")
        
        lines.extend(["", "Configuration:", "-" * 80])
        
        # Pretty print YAML
        config_yaml = yaml.dump(preset, default_flow_style=False, sort_keys=False)
        lines.extend(f"  {line}" if line else "" for line in config_yaml.split('\n'))
        
        lines.extend(["-" * 80, "", "Usage:", f"  benchmark share --csv data.csv --entity 'BANK' --metric txn_cnt --preset {name}"])
        
        return "\n".join(lines)
    
    def get_preset_choices(self) -> List[str]:
        """Get list of preset names for argparse choices.
        
        Returns:
            List of preset names, or empty list if none available
        """
        return self.list_presets()
