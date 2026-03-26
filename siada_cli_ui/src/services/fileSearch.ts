/**
 * File Search Service
 * Provides file search functionality for @ autocomplete
 */

import * as fs from 'fs';
import * as path from 'path';
import type { Suggestion, FileSearchOptions } from '../types/autocomplete.js';

export class FileSearchService {
  private cwd: string;
  private maxResults: number;
  private maxDepth: number;
  private respectGitIgnore: boolean;
  private gitIgnorePatterns: Set<string>;

  constructor(
    cwd: string,
    options: {
      maxResults?: number;
      maxDepth?: number;
      respectGitIgnore?: boolean;
    } = {}
  ) {
    this.cwd = cwd;
    this.maxResults = options.maxResults || 20;
    this.maxDepth = options.maxDepth || 6;  // Balanced depth for performance
    this.respectGitIgnore = options.respectGitIgnore !== false;
    this.gitIgnorePatterns = new Set();
    
    if (this.respectGitIgnore) {
      this.loadGitIgnore();
    }
  }

  /**
   * Load .gitignore patterns
   */
  private loadGitIgnore(): void {
    try {
      const gitignorePath = path.join(this.cwd, '.gitignore');
      if (fs.existsSync(gitignorePath)) {
        const content = fs.readFileSync(gitignorePath, 'utf-8');
        content.split('\n').forEach(line => {
          const trimmed = line.trim();
          if (trimmed && !trimmed.startsWith('#')) {
            this.gitIgnorePatterns.add(trimmed);
          }
        });
      }
    } catch (error) {
      // Silently fail if .gitignore can't be loaded
    }
  }

  /**
   * Check if path should be ignored
   */
  private shouldIgnore(filePath: string): boolean {
    const basename = path.basename(filePath);
    
    // Always ignore common patterns
    const alwaysIgnore = [
      'node_modules',
      '.git',
      '.vscode',
      '.idea',
      'dist',
      'build',
      '__pycache__',
      '.DS_Store'
    ];
    
    if (alwaysIgnore.includes(basename)) {
      return true;
    }
    
    // Check gitignore patterns
    for (const pattern of this.gitIgnorePatterns) {
      if (this.matchesPattern(filePath, pattern)) {
        return true;
      }
    }
    
    return false;
  }

  /**
   * Simple pattern matching for gitignore
   */
  private matchesPattern(filePath: string, pattern: string): boolean {
    const basename = path.basename(filePath);
    
    // Simple glob matching
    if (pattern.includes('*')) {
      const regex = new RegExp('^' + pattern.replace(/\*/g, '.*') + '$');
      return regex.test(basename) || regex.test(filePath);
    }
    
    return basename === pattern || filePath.includes(pattern);
  }

  /**
   * Search for files matching pattern
   * Only searches for continuous matches (score >= 180) for better performance:
   * - Exact match
   * - Prefix match
   * - Continuous substring match in filename or path
   * No fuzzy matching to keep search fast and results precise
   */
  async search(pattern: string): Promise<Suggestion[]> {
    // Remove @ prefix if present
    const cleanPattern = pattern.replace(/^@/, '').trim();
    
    // If empty, return recent files or common directories
    if (!cleanPattern) {
      return this.getDefaultSuggestions();
    }
    
    // Search for continuous matches only
    const matches = await this.findMatchingFiles(cleanPattern, this.cwd, 0);
    
    // Sort by score, depth, length, and alphabetically
    this.sortMatches(matches);
    
    // Convert to suggestions
    return matches.slice(0, this.maxResults).map(match => ({
      label: match.path,
      value: match.path,
      type: 'file' as const,
      icon: this.getFileIcon(match.path)
    }));
  }
  
  /**
   * Sort matches by score, depth, length, and alphabetically
   */
  private sortMatches(matches: Array<{ path: string; score: number; depth: number }>): void {
    matches.sort((a, b) => {
      // Primary: score (descending)
      if (a.score !== b.score) {
        return b.score - a.score;
      }
      
      // Secondary: depth (ascending - prefer shallower paths)
      if (a.depth !== b.depth) {
        return a.depth - b.depth;
      }
      
      // Tertiary: path length (ascending - prefer shorter names)
      if (a.path.length !== b.path.length) {
        return a.path.length - b.path.length;
      }
      
      // Quaternary: alphabetical
      return a.path.localeCompare(b.path);
    });
  }

  /**
   * Get default suggestions when no pattern
   */
  private getDefaultSuggestions(): Suggestion[] {
    const defaults: string[] = [];
    
    try {
      // Add common directories first
      const commonDirs = ['src', 'tests', 'docs', 'lib', 'app'];
      for (const dir of commonDirs) {
        const dirPath = path.join(this.cwd, dir);
        if (fs.existsSync(dirPath) && fs.statSync(dirPath).isDirectory()) {
          defaults.push(dir + '/');
        }
      }
      
      // Add all files and directories in current directory (not just first 10)
      const files = fs.readdirSync(this.cwd);
      for (const file of files) {
        // Skip common directories already added
        if (commonDirs.includes(file)) {
          continue;
        }
        
        if (!this.shouldIgnore(file)) {
          const fullPath = path.join(this.cwd, file);
          const stat = fs.statSync(fullPath);
          defaults.push(stat.isDirectory() ? file + '/' : file);
        }
      }
    } catch (error) {
      // Return empty if error
    }
    
    // Return all suggestions (will be limited by maxResults in search())
    return defaults.map(file => ({
      label: file,
      value: file,
      type: 'file' as const,
      icon: this.getFileIcon(file)
    }));
  }

  /**
   * Find files matching pattern with scores
   * Only collects continuous matches (score >= 180) for better performance
   * @param pattern - Search pattern
   * @param currentPath - Current directory path
   * @param depth - Current recursion depth
   */
  private async findMatchingFiles(
    pattern: string,
    currentPath: string = this.cwd,
    depth: number = 0
  ): Promise<Array<{ path: string; score: number; depth: number }>> {
    if (depth > this.maxDepth) {
      return [];
    }
    
    const results: Array<{ path: string; score: number; depth: number }> = [];
    
    try {
      const entries = fs.readdirSync(currentPath);
      
      for (const entry of entries) {
        const fullPath = path.join(currentPath, entry);
        
        if (this.shouldIgnore(fullPath)) {
          continue;
        }
        
        const relativePath = path.relative(this.cwd, fullPath);
        
        // Check if matches pattern and calculate score
        if (this.matches(relativePath, pattern) || this.matches(entry, pattern)) {
          const stat = fs.statSync(fullPath);
          const finalPath = stat.isDirectory() ? relativePath + '/' : relativePath;
          const score = this.calculateMatchScore(relativePath, entry, pattern);
          
          // Only collect continuous matches (score >= 180)
          if (score >= 180) {
            const pathDepth = relativePath.split(path.sep).length;
            results.push({ 
              path: finalPath, 
              score, 
              depth: pathDepth 
            });
          }
        }
        
        // Recursively search directories
        if (fs.statSync(fullPath).isDirectory()) {
          const subResults = await this.findMatchingFiles(pattern, fullPath, depth + 1);
          results.push(...subResults);
        }
        
        // Early termination to avoid searching too many files
        if (results.length >= this.maxResults * 2) {
          break;
        }
      }
    } catch (error) {
      // Skip directories we can't read
    }
    
    return results;
  }

  /**
   * Calculate match score for a file path
   * Higher score = better match
   * 
   * Priority: Continuous matches > Fuzzy matches
   * Score ranges:
   * - 200+: Exact or continuous matches (highest priority)
   * - 100-199: Continuous substring matches
   * - 0-99: Fuzzy/word boundary matches
   */
  private calculateMatchScore(relativePath: string, fileName: string, pattern: string): number {
    const lowerFileName = fileName.toLowerCase();
    const lowerPath = relativePath.toLowerCase();
    const lowerPattern = pattern.toLowerCase();
    
    // 1. Exact match (300 points) - highest priority
    if (lowerFileName === lowerPattern || lowerPath === lowerPattern) {
      return 300;
    }
    
    // 2. Prefix match (250 points) - file/path starts with pattern
    if (lowerFileName.startsWith(lowerPattern)) {
      return 250;
    }
    
    // 3. Continuous substring match in fileName (200 points)
    // This is a CONTINUOUS match, not fuzzy
    if (lowerFileName.includes(lowerPattern)) {
      return 200;
    }
    
    // 4. Continuous substring match in full path (180 points)
    // Also continuous, not fuzzy
    if (lowerPath.includes(lowerPattern)) {
      return 180;
    }
    
    // 5. Word boundary match (90 points) - fuzzy match category
    // - Camel case: "uac" matches "useAtCompletion"
    // - Path separator: "hooks/use" matches "src/hooks/useXxx"
    if (this.matchesWordBoundary(lowerFileName, lowerPattern)) {
      return 90;
    }
    
    // 6. Fuzzy match (0-80 points) - lowest priority
    // Characters match in order but not continuously
    return this.calculateFuzzyScore(lowerFileName, lowerPattern);
  }

  /**
   * Check if pattern matches word boundaries (camelCase or path separators)
   */
  private matchesWordBoundary(text: string, pattern: string): boolean {
    // Extract capital letters and word boundaries
    const boundaries = text.match(/[A-Z]/g) || [];
    const boundaryStr = boundaries.join('').toLowerCase();
    
    if (boundaryStr.includes(pattern)) {
      return true;
    }
    
    // Check for acronym match: "uac" -> "useAtCompletion"
    let patternIndex = 0;
    for (let i = 0; i < text.length && patternIndex < pattern.length; i++) {
      const char = text[i];
      // Match on uppercase letters or after path separator
      if (char === pattern[patternIndex] && 
          (i === 0 || text[i - 1] === '/' || text[i - 1] === '\\' || /[A-Z]/.test(char))) {
        patternIndex++;
      }
    }
    
    return patternIndex === pattern.length;
  }

  /**
   * Calculate fuzzy match score
   * Returns 0-80 based on match quality
   * Note: Must be lower than word boundary match (90) to maintain priority
   */
  private calculateFuzzyScore(text: string, pattern: string): number {
    let score = 20; // Base score for any fuzzy match
    let textIndex = 0;
    let consecutiveMatches = 0;
    let totalMatches = 0;
    
    for (const char of pattern) {
      const nextIndex = text.indexOf(char, textIndex);
      if (nextIndex === -1) {
        return 0; // Not a match
      }
      
      // Bonus for consecutive characters
      if (nextIndex === textIndex) {
        consecutiveMatches++;
        score += 3;
      } else {
        consecutiveMatches = 0;
      }
      
      textIndex = nextIndex + 1;
      totalMatches++;
    }
    
    // Bonus for match density (how much of the text is matched)
    const density = totalMatches / text.length;
    score += Math.floor(density * 40);
    
    // Cap at 80 to ensure it's always lower than word boundary (90) and continuous matches (180+)
    return Math.min(score, 80);
  }

  /**
   * Check if text matches pattern (fuzzy)
   */
  private matches(text: string, pattern: string): boolean {
    const lowerText = text.toLowerCase();
    const lowerPattern = pattern.toLowerCase();
    
    // Exact substring match
    if (lowerText.includes(lowerPattern)) {
      return true;
    }
    
    // Fuzzy match (each character in pattern appears in order)
    let textIndex = 0;
    for (const char of lowerPattern) {
      textIndex = lowerText.indexOf(char, textIndex);
      if (textIndex === -1) {
        return false;
      }
      textIndex++;
    }
    
    return true;
  }

  /**
   * Get icon for file type
   */
  private getFileIcon(filePath: string): string {
    const ext = path.extname(filePath);
    
    // Directory
    if (filePath.endsWith('/')) {
      return ''; //📁
    }
    
    // // File type icons
    // const iconMap: Record<string, string> = {
    //   '.ts': '🔷',
    //   '.tsx': '⚛️',
    //   '.js': '🟨',
    //   '.jsx': '⚛️',
    //   '.py': '🐍',
    //   '.json': '📋',
    //   '.md': '📝',
    //   '.txt': '📄',
    //   '.yaml': '⚙️',
    //   '.yml': '⚙️',
    //   '.sh': '🔧',
    //   '.css': '🎨',
    //   '.html': '🌐',
    //   '.svg': '🖼️',
    //   '.png': '🖼️',
    //   '.jpg': '🖼️'
    // };
    
    // return iconMap[ext] || '📄';
    return ''; //📄
  }

  /**
   * Get file description
   */
  getFileDescription(filePath: string): string | undefined {
    try {
      const fullPath = path.join(this.cwd, filePath);
      const stat = fs.statSync(fullPath);
      
      if (stat.isDirectory()) {
        return 'Directory';
      }
      
      const sizeMB = stat.size / (1024 * 1024);
      if (sizeMB > 1) {
        return `${sizeMB.toFixed(2)} MB`;
      }
      
      const sizeKB = stat.size / 1024;
      return `${sizeKB.toFixed(0)} KB`;
    } catch {
      return undefined;
    }
  }
}
