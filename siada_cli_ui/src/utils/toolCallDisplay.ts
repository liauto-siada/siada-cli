import type { ParsedToolCall } from './toolCallParser.js';

export interface ToolCallDisplayField {
  label: string;
  value: string;
}

export interface SemanticToolCallDisplay {
  heading: string;
  fields: ToolCallDisplayField[];
  compactSummary: string;
  compactPreview: string;
}

function clean(value: string | undefined): string {
  return (value || '').replace(/\s+/g, ' ').trim();
}

function truncate(value: string, limit = 72): string {
  const normalized = clean(value);
  const characters = Array.from(normalized);
  return characters.length > limit ? `${characters.slice(0, limit).join('')}…` : normalized;
}

function basename(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).at(-1) || path;
}

function compactDetails(details: string | undefined): string {
  return truncate(details || '');
}

function withFields(heading: string, fields: ToolCallDisplayField[], compactSummary: string, compactPreview: string): SemanticToolCallDisplay {
  return {
    heading,
    fields: fields.filter(field => field.value),
    compactSummary: truncate(compactSummary),
    compactPreview: truncate(compactPreview),
  };
}

export function getSemanticToolCallDisplay(tool: ParsedToolCall): SemanticToolCallDisplay | null {
  const details = clean(tool.details);

  switch (tool.type) {
    case 'analyze': {
      const path = tool.path || details;
      const preview = path ? basename(path) : '';
      return withFields(
        'Analyze definitions',
        path ? [{ label: 'file', value: path }] : [],
        `Analyze ${preview || 'definitions'}`,
        preview,
      );
    }
    case 'memory_search': {
      const query = details;
      const preview = truncate(query);
      return withFields(
        'Search memory',
        query ? [{ label: 'query', value: query }] : [],
        `Search memory${preview ? ` · ${preview}` : ''}`,
        preview ? `query: ${preview}` : '',
      );
    }
    case 'memory_write': {
      const preview = compactDetails(tool.details);
      const target = tool.target;
      const operation = [tool.action, target].filter(Boolean).join(' / ');
      const fields: ToolCallDisplayField[] = [];
      if (tool.action) fields.push({ label: 'action', value: tool.action });
      if (target) fields.push({ label: 'target', value: target });
      if (details) fields.push({ label: 'content', value: details });
      const compactPreview = [operation ? `[${operation}]` : '', preview].filter(Boolean).join(' ');
      return withFields(
        'Save memory',
        fields,
        `Save memory${compactPreview ? ` · ${compactPreview}` : ''}`,
        truncate(compactPreview),
      );
    }
    case 'fact_store': {
      const preview = compactDetails(tool.details);
      const operation = [tool.action, tool.target].filter(Boolean).join(' / ');
      const detailLabel = tool.action === 'search' ? 'query'
        : tool.action === 'probe' || tool.action === 'related' ? 'entity'
          : tool.action === 'reason' ? 'entities'
            : tool.action === 'add' || tool.action === 'update' ? 'content'
              : 'details';
      const fields: ToolCallDisplayField[] = [];
      if (tool.action) fields.push({ label: 'action', value: tool.action });
      if (tool.target) fields.push({ label: tool.action === 'add' ? 'category' : 'target', value: tool.target });
      if (details) fields.push({ label: detailLabel, value: details });
      const compactPreview = [operation ? `[${operation}]` : '', preview].filter(Boolean).join(' ');
      return withFields(
        'Fact memory',
        fields,
        `Fact memory${compactPreview ? ` · ${compactPreview}` : ''}`,
        truncate(compactPreview),
      );
    }
    case 'fact_feedback': {
      const preview = compactDetails(tool.details);
      const outcome = [tool.target, tool.action].filter(Boolean).join(' ');
      const compactPreview = [outcome, preview].filter(Boolean).join(preview && outcome ? ': ' : '');
      const fields: ToolCallDisplayField[] = [];
      if (tool.target) fields.push({ label: 'fact', value: tool.target });
      if (tool.action) fields.push({ label: 'action', value: tool.action });
      if (details) fields.push({ label: 'comment', value: details });
      return withFields(
        'Fact feedback',
        fields,
        `Fact feedback${compactPreview ? ` · ${compactPreview}` : ''}`,
        truncate(compactPreview),
      );
    }
    case 'sub_agent': {
      const task = details;
      const preview = truncate(task);
      return withFields(
        'Delegate sub-agent',
        task ? [{ label: 'task', value: task }] : [],
        `Delegate sub-agent${preview ? ` · ${preview}` : ''}`,
        preview ? `task: ${preview}` : '',
      );
    }
    case 'undo_edit': {
      const path = tool.path || details;
      const preview = path ? basename(path) : '';
      return withFields(
        'Undo edit',
        path ? [{ label: 'file', value: path }] : [],
        `Undo edit${preview ? ` · ${preview}` : ''}`,
        preview,
      );
    }
    default:
      return null;
  }
}