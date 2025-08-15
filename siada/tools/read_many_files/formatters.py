"""
Output formatting utilities for ReadManyFiles tool.
"""

from typing import List, Dict, Any
from .models import ProcessingStats


class ResultFormatter:
    """Result formatting utility class"""
    
    def __init__(self, target_dir: str):
        self.target_dir = target_dir
    
    def build_result(self, content_parts: List[Any], 
                    processed_files: List[str], 
                    skipped_files: List[Dict],
                    stats: ProcessingStats) -> Dict[str, Any]:
        """
        Build final tool result
        
        Args:
            content_parts: List of processed file contents
            processed_files: List of successfully processed file paths
            skipped_files: List of skipped file information
            stats: Processing statistics
            
        Returns:
            Dictionary with llmContent and returnDisplay
        """
        # Build LLM content
        if not content_parts:
            llm_content = ['No files matching the criteria were found or all were skipped.']
        else:
            llm_content = content_parts
        
        # Build display message
        display_message = self.build_display_message(
            processed_files, skipped_files, stats
        )
        
        return {
            'llmContent': llm_content,
            'returnDisplay': display_message.strip()
        }
    
    def build_display_message(self, processed_files: List[str], 
                             skipped_files: List[Dict],
                             stats: ProcessingStats) -> str:
        """
        Build detailed user interface display message
        
        Args:
            processed_files: List of successfully processed file paths
            skipped_files: List of skipped file information
            stats: Processing statistics
            
        Returns:
            Formatted display message string
        """
        lines = [f"### ReadManyFiles Result (Target Dir: `{self.target_dir}`)\n"]
        
        # Success section
        if processed_files:
            count = len(processed_files)
            lines.append(f"Successfully read and concatenated content from **{count} file(s)**.\n")
            
            # File type breakdown
            type_info = []
            if stats.text_files > 0:
                type_info.append(f"{stats.text_files} text")
            if stats.image_files > 0:
                type_info.append(f"{stats.image_files} image")
            if stats.pdf_files > 0:
                type_info.append(f"{stats.pdf_files} PDF")
            if stats.binary_files > 0:
                type_info.append(f"{stats.binary_files} binary")
            
            if type_info:
                lines.append(f"**File Types:** {', '.join(type_info)} files\n")
            
            # Size information
            if stats.total_size > 0:
                size_mb = stats.total_size / (1024 * 1024)
                if size_mb >= 1:
                    lines.append(f"**Total Size:** {size_mb:.1f} MB\n")
                else:
                    size_kb = stats.total_size / 1024
                    lines.append(f"**Total Size:** {size_kb:.1f} KB\n")
            
            # Processing time
            if stats.processing_time > 0:
                lines.append(f"**Processing Time:** {stats.processing_time:.2f} seconds\n")
            
            # File list
            if count <= 10:
                lines.append("**Processed Files:**")
                for file_path in processed_files:
                    lines.append(f"- `{file_path}`")
            else:
                lines.append("**Processed Files (first 10 shown):**")
                for file_path in processed_files[:10]:
                    lines.append(f"- `{file_path}`")
                lines.append(f"- ...and {count - 10} more.")
        
        # Skipped files section
        if skipped_files:
            if not processed_files:
                lines.append("No files were read and concatenated based on the criteria.\n")
            
            skipped_count = len(skipped_files)
            
            # Group skipped files by reason
            skip_by_reason = {}
            for item in skipped_files:
                reason = item['reason']
                if reason not in skip_by_reason:
                    skip_by_reason[reason] = []
                skip_by_reason[reason].append(item['path'])
            
            if skipped_count <= 10:
                lines.append(f"**Skipped {skipped_count} item(s):**")
            else:
                lines.append(f"**Skipped {skipped_count} item(s) (first 10 shown):**")
            
            shown_count = 0
            for reason, paths in skip_by_reason.items():
                if shown_count >= 10:
                    break
                
                for path in paths:
                    if shown_count >= 10:
                        break
                    lines.append(f"- `{path}` (Reason: {reason})")
                    shown_count += 1
            
            if skipped_count > 10:
                lines.append(f"- ...and {skipped_count - 10} more.")
        
        # Statistics summary
        if stats.total_files_found > 0:
            lines.append(f"\n**Summary:** Found {stats.total_files_found} files, "
                        f"processed {stats.processed_files}, "
                        f"skipped {stats.skipped_files}")
            
            if stats.error_files > 0:
                lines.append(f", {stats.error_files} errors")
        
        # No results case
        if not processed_files and not skipped_files:
            lines.append("No files were found matching the specified criteria.")
        
        return "\n".join(lines)
    
    def build_filter_skip_info(self, filter_counts: Dict[str, int]) -> List[Dict]:
        """
        Build skip information for filtered files
        
        Args:
            filter_counts: Dictionary of filter type to count
            
        Returns:
            List of skip information dictionaries
        """
        skip_info = []
        
        if filter_counts.get('git_ignored', 0) > 0:
            count = filter_counts['git_ignored']
            skip_info.append({
                'path': f'{count} files',
                'reason': 'Filtered by .gitignore rules'
            })
        
        return skip_info
    
    def create_error_result(self, error_message: str) -> Dict[str, Any]:
        """
        Create error result
        
        Args:
            error_message: Error message to display
            
        Returns:
            Error result dictionary
        """
        return {
            'llmContent': [f"Error: {error_message}"],
            'returnDisplay': f"## Error\n\n{error_message}"
        }
    
    def create_info_result(self, info_message: str) -> Dict[str, Any]:
        """
        Create informational result
        
        Args:
            info_message: Information message to display
            
        Returns:
            Info result dictionary
        """
        return {
            'llmContent': [info_message],
            'returnDisplay': f"## Information\n\n{info_message}"
        }
