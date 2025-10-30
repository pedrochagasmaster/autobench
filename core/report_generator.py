"""
ReportGenerator - Output report generation module.

Generates benchmark reports in multiple formats (Excel, CSV, JSON).
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    Generates benchmark reports in various formats.
    
    Supports:
    - Excel workbooks with multiple sheets
    - CSV exports
    - JSON structured data
    - Metadata and audit trails
    """
    
    def __init__(self, config: Any):
        """
        Initialize report generator.
        
        Parameters:
        -----------
        config : ConfigManager
            Configuration manager instance
        """
        self.config = config
        logger.info("Initialized ReportGenerator")
    
    def generate_report(
        self,
        results: Dict[str, Any],
        output_file: str,
        format: str = 'excel',
        analysis_type: str = 'rate',
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Generate benchmark report.
        
        Parameters:
        -----------
        results : Dict
            Analysis results
        output_file : str
            Output file path
        format : str
            Output format ('excel', 'csv', 'json')
        analysis_type : str
            Type of analysis performed
        metadata : Dict, optional
            Additional metadata to include
        """
        logger.info(f"Generating {format} report: {output_file}")
        
        if format == 'excel':
            self._generate_excel_report(results, output_file, analysis_type, metadata)
        elif format == 'csv':
            self._generate_csv_report(results, output_file, analysis_type, metadata)
        elif format == 'json':
            self._generate_json_report(results, output_file, analysis_type, metadata)
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        logger.info(f"Report saved to: {output_file}")
    
    def _generate_excel_report(
        self,
        results: Dict[str, Any],
        output_file: str,
        analysis_type: str,
        metadata: Optional[Dict[str, Any]]
    ) -> None:
        """Generate Excel workbook report."""
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment
            from openpyxl.utils.dataframe import dataframe_to_rows
        except ImportError:
            logger.error("openpyxl not installed. Install with: pip install openpyxl")
            raise
        
        # Store styles as instance variables for use in other methods
        self._font_class = Font
        self._fill_class = PatternFill
        self._align_class = Alignment
        
        wb = Workbook()
        
        # Remove default sheet
        if 'Sheet' in wb.sheetnames:
            wb.remove(wb['Sheet'])
        
        # Create Summary sheet
        ws_summary = wb.create_sheet("Summary")
        self._write_summary_sheet(ws_summary, results, analysis_type, metadata)
        
        # Create sheets for each result
        for i, (metric_name, result_data) in enumerate(results.items()):
            sheet_name = f"Metric_{i+1}_{metric_name[:20]}"  # Limit sheet name length
            ws = wb.create_sheet(sheet_name)
            self._write_metric_sheet(ws, metric_name, result_data, analysis_type)
        
        # Create Metadata sheet
        if metadata:
            ws_meta = wb.create_sheet("Metadata")
            self._write_metadata_sheet(ws_meta, metadata)
        
        # Save workbook
        wb.save(output_file)
    
    def _write_summary_sheet(
        self,
        worksheet: Any,
        results: Dict[str, Any],
        analysis_type: str,
        metadata: Optional[Dict[str, Any]]
    ) -> None:
        """Write summary information to worksheet."""
        # Header
        worksheet['A1'] = "Benchmark Analysis Summary"
        worksheet['A1'].font = self._font_class(bold=True, size=14)
        
        row = 3
        
        # Analysis info
        worksheet[f'A{row}'] = "Analysis Type:"
        worksheet[f'B{row}'] = analysis_type.upper()
        row += 1
        
        if metadata:
            worksheet[f'A{row}'] = "Entity:"
            worksheet[f'B{row}'] = metadata.get('entity', 'N/A')
            row += 1
            
            worksheet[f'A{row}'] = "Timestamp:"
            worksheet[f'B{row}'] = metadata.get('timestamp', datetime.now().isoformat())
            row += 1
            
            if 'dimensions' in metadata:
                worksheet[f'A{row}'] = "Dimensions:"
                worksheet[f'B{row}'] = ', '.join(metadata['dimensions'])
                row += 1
            
            worksheet[f'A{row}'] = "Privacy Rule:"
            worksheet[f'B{row}'] = f"{metadata.get('participants', 'N/A')} participants, " \
                                   f"{metadata.get('max_concentration', 'N/A')}% max"
            row += 2
        
        # Results summary
        worksheet[f'A{row}'] = "Metrics Analyzed:"
        worksheet[f'A{row}'].font = self._font_class(bold=True)
        row += 1
        
        for metric_name in results.keys():
            worksheet[f'A{row}'] = f"  • {metric_name}"
            row += 1
    
    def _write_metric_sheet(
        self,
        worksheet: Any,
        metric_name: str,
        result_data: Any,
        analysis_type: str
    ) -> None:
        """Write metric results to worksheet."""
        # Header
        worksheet['A1'] = f"Metric: {metric_name}"
        worksheet['A1'].font = self._font_class(bold=True, size=12)
        
        row = 3
        
        if isinstance(result_data, dict):
            # Write dictionary results as key-value pairs
            for key, value in result_data.items():
                worksheet[f'A{row}'] = str(key).replace('_', ' ').title()
                worksheet[f'B{row}'] = value
                row += 1
        elif isinstance(result_data, pd.DataFrame):
            # Write dataframe
            for r_idx, row_data in enumerate(result_data.itertuples(index=False), start=row):
                for c_idx, value in enumerate(row_data, start=1):
                    worksheet.cell(row=r_idx, column=c_idx, value=value)
    
    def _write_metadata_sheet(
        self,
        worksheet: Any,
        metadata: Dict[str, Any]
    ) -> None:
        """Write metadata to worksheet."""
        worksheet['A1'] = "Analysis Metadata"
        worksheet['A1'].font = self._font_class(bold=True, size=12)
        
        row = 3
        for key, value in metadata.items():
            worksheet[f'A{row}'] = str(key).replace('_', ' ').title()
            
            if isinstance(value, (list, dict)):
                worksheet[f'B{row}'] = json.dumps(value, indent=2)
            else:
                worksheet[f'B{row}'] = str(value)
            
            row += 1
    
    def _generate_csv_report(
        self,
        results: Dict[str, Any],
        output_file: str,
        analysis_type: str,
        metadata: Optional[Dict[str, Any]]
    ) -> None:
        """Generate CSV report."""
        # Flatten results to dataframe
        rows = []
        
        for metric_name, result_data in results.items():
            if isinstance(result_data, dict):
                row = {'metric': metric_name}
                row.update(result_data)
                rows.append(row)
            elif isinstance(result_data, pd.DataFrame):
                # Save each dataframe result as separate CSV
                df_output = Path(output_file).stem + f"_{metric_name}.csv"
                result_data.to_csv(df_output, index=False)
        
        if rows:
            df_results = pd.DataFrame(rows)
            df_results.to_csv(output_file, index=False)
    
    def _generate_json_report(
        self,
        results: Dict[str, Any],
        output_file: str,
        analysis_type: str,
        metadata: Optional[Dict[str, Any]]
    ) -> None:
        """Generate JSON report."""
        output_data = {
            'analysis_type': analysis_type,
            'metadata': metadata or {},
            'results': {}
        }
        
        for metric_name, result_data in results.items():
            if isinstance(result_data, dict):
                output_data['results'][metric_name] = result_data
            elif isinstance(result_data, pd.DataFrame):
                output_data['results'][metric_name] = result_data.to_dict(orient='records')
        
        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2, default=str)
    
    def create_audit_log(
        self,
        log_file: str,
        metadata: Dict[str, Any],
        results_summary: Dict[str, Any]
    ) -> None:
        """
        Create audit log file.
        
        Parameters:
        -----------
        log_file : str
            Path to log file
        metadata : Dict
            Analysis metadata
        results_summary : Dict
            Summary of results
        """
        logger.info(f"Creating audit log: {log_file}")
        
        with open(log_file, 'w') as f:
            f.write("=" * 80 + "\n")
            f.write("BENCHMARK ANALYSIS AUDIT LOG\n")
            f.write("=" * 80 + "\n\n")
            
            f.write("ANALYSIS METADATA\n")
            f.write("-" * 80 + "\n")
            for key, value in metadata.items():
                f.write(f"{key}: {value}\n")
            f.write("\n")
            
            f.write("RESULTS SUMMARY\n")
            f.write("-" * 80 + "\n")
            for key, value in results_summary.items():
                f.write(f"{key}: {value}\n")
            f.write("\n")
            
            f.write("=" * 80 + "\n")
            f.write(f"Log generated: {datetime.now().isoformat()}\n")
